"""
bioRxiv author collector — fetches recent bioRxiv preprints and filters by tracked authors.

bioRxiv's RSS search returns 403, so we use their official content API instead:
  https://api.biorxiv.org/details/biorxiv/{start}/{end}/{cursor}/json

Returns items tagged ["protein-design", "author"] with source="<Name> (bioRxiv)"
so they are recognised as tier-0 by rank.py (_is_researcher_feed checks "biorxiv" in src).

Config section (config.yaml):
  biorxiv_authors:
    enabled: true
    lookback_days: 3
    authors:
      - name: "David Baker"
        match: "Baker, D"          # substring to find in the authors field
        institution: "Washington"  # optional: also require this in corresponding institution
      - name: "Frank DiMaio"
        match: "DiMaio, F"
"""
from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import requests

_API_BASE = "https://api.biorxiv.org/details/biorxiv"
_TIMEOUT = 20
_PAGE_SIZE = 100


def _fetch_page(start: str, end: str, cursor: int, session: requests.Session) -> dict:
    url = f"{_API_BASE}/{start}/{end}/{cursor}/json"
    resp = session.get(url, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def collect_biorxiv_author_items(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Fetch recent bioRxiv preprints and return those matching tracked authors.
    Items get source="<Name> (bioRxiv)" and tags=["protein-design", "author"]
    so rank.py treats them as tier-0 (biorxiv in source + author tag).
    """
    bio_cfg = cfg.get("biorxiv_authors") or {}
    if not bio_cfg.get("enabled", True):
        return []

    authors_cfg: List[Dict[str, Any]] = bio_cfg.get("authors") or []
    if not authors_cfg:
        return []

    lookback_days = int(bio_cfg.get("lookback_days", 3))
    today = date.today()
    start = (today - timedelta(days=lookback_days)).isoformat()
    end = today.isoformat()

    # Build lookup: match_string → (name, institution_filter)
    author_lookup: List[tuple] = []
    for a in authors_cfg:
        name = (a.get("name") or "").strip()
        match = (a.get("match") or "").strip()
        institution = (a.get("institution") or "").strip().lower()
        if name and match:
            author_lookup.append((name, match, institution))

    if not author_lookup:
        return []

    print(f"[biorxiv_authors] Fetching papers {start} → {end} for {len(author_lookup)} authors", flush=True)

    session = requests.Session()
    session.headers["User-Agent"] = "protein-design-podcast/1.0 (academic research)"

    # Paginate through all papers in the date window
    all_papers: List[dict] = []
    cursor = 0
    total = None
    while True:
        try:
            data = _fetch_page(start, end, cursor, session)
        except Exception as e:
            print(f"[biorxiv_authors] API error at cursor {cursor}: {e}", flush=True)
            break

        papers = data.get("collection") or []
        if total is None:
            try:
                total = int(data["messages"][0]["total"])
            except Exception:
                total = 0

        all_papers.extend(papers)
        cursor += len(papers)

        if not papers or cursor >= total:
            break
        time.sleep(0.3)  # be polite to the API

    print(f"[biorxiv_authors] Fetched {len(all_papers)} total papers from bioRxiv", flush=True)

    # Match against tracked authors
    items: List[Dict[str, Any]] = []
    matched_names: Dict[str, int] = {}

    for paper in all_papers:
        authors_str = paper.get("authors", "")
        institution = (paper.get("author_corresponding_institution") or "").lower()

        for (name, match, inst_filter) in author_lookup:
            if match not in authors_str:
                continue
            if inst_filter and inst_filter not in institution:
                continue

            doi = paper.get("doi", "")
            url = f"https://www.biorxiv.org/content/{doi}" if doi else ""
            if not url:
                continue

            title = (paper.get("title") or "").strip()
            abstract = (paper.get("abstract") or "").strip()
            pub_date = paper.get("date", end)

            items.append({
                "title": title,
                "url": url,
                "source": f"{name} (bioRxiv)",
                "published": pub_date,
                "snippet": abstract[:400] if abstract else "",
                "one_liner": "",
                "bucket": "protein",
                "tags": ["protein-design", "author"],
                "extracted_chars": len(abstract),
            })
            matched_names[name] = matched_names.get(name, 0) + 1
            break  # don't double-count if multiple patterns match

    if matched_names:
        print(f"[biorxiv_authors] Matched: {matched_names}", flush=True)
    else:
        print(f"[biorxiv_authors] No matches this window (normal on quiet days)", flush=True)

    return items
