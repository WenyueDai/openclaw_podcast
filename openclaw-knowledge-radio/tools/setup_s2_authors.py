#!/usr/bin/env python3
"""
One-time tool: map tracked researcher names to their Semantic Scholar author IDs.

Run once from the repo root:
    S2_API_KEY=<your-key> python tools/setup_s2_authors.py

Writes state/s2_author_ids.json:
    {"David Baker": "1741101", "Sergey Ovchinnikov": "2286115", ...}

This file is used to verify that arXiv papers collected from author feeds
actually come from the correct researcher (guards against name collisions like
multiple "David Baker"s in academia).

The script prints each match so you can sanity-check before committing the file.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests
import yaml

REPO_DIR   = Path(__file__).resolve().parent.parent
STATE_DIR  = REPO_DIR / "state"
CONFIG     = REPO_DIR / "config.yaml"
OUTPUT     = STATE_DIR / "s2_author_ids.json"
S2_BASE    = "https://api.semanticscholar.org/graph/v1"
_DELAY     = 1.05


def _get(path: str, params: dict, api_key: str) -> dict | None:
    headers = {"x-api-key": api_key} if api_key else {}
    try:
        r = requests.get(f"{S2_BASE}{path}", params=params, headers=headers, timeout=15)
        if r.status_code == 200:
            return r.json()
        if r.status_code == 429:
            time.sleep(10)
            r = requests.get(f"{S2_BASE}{path}", params=params, headers=headers, timeout=15)
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        print(f"  [warn] request failed: {e}")
    return None


def search_author(name: str, institution_hint: str, api_key: str) -> tuple[str | None, str | None]:
    """
    Search S2 for an author by name.  Returns (author_id, matched_name) or (None, None).

    If institution_hint is provided, prefer the result whose affiliation contains it.
    """
    time.sleep(_DELAY)
    data = _get(
        "/author/search",
        {"query": name, "fields": "authorId,name,affiliations", "limit": 5},
        api_key,
    )
    if not data or not data.get("data"):
        return None, None

    candidates = data["data"]
    hint = (institution_hint or "").lower()

    # Prefer exact name match + institution hint
    if hint:
        for c in candidates:
            affils = " ".join(
                (a.get("name") or "") for a in (c.get("affiliations") or [])
            ).lower()
            if hint in affils:
                return c["authorId"], c["name"]

    # Fall back to first result
    return candidates[0]["authorId"], candidates[0]["name"]


def _collect_authors(cfg: dict) -> list[dict]:
    """
    Pull all tracked author names + institution hints from config.yaml.
    Sources: rss_sources with tag 'author', biorxiv_authors list.
    """
    authors = []
    seen_names: set[str] = set()

    # biorxiv_authors — has explicit name + optional institution
    for entry in cfg.get("biorxiv_authors", {}).get("authors", []):
        name = entry.get("name", "").strip()
        inst = entry.get("institution", "")
        if name and name not in seen_names:
            authors.append({"name": name, "institution": inst})
            seen_names.add(name)

    # rss_sources with tag 'author' — extract name from source name like "David Baker (arXiv)"
    import re
    for src in cfg.get("rss_sources", []):
        tags = src.get("tags") or []
        if "author" not in tags:
            continue
        raw = src.get("name", "")
        m = re.match(r"^(.+?)\s*\(", raw)
        name = (m.group(1) if m else raw).strip()
        if name and name not in seen_names:
            authors.append({"name": name, "institution": ""})
            seen_names.add(name)

    return authors


def main() -> None:
    api_key = os.environ.get("S2_API_KEY", "").strip()
    if not api_key:
        print("ERROR: S2_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    authors = _collect_authors(cfg)
    print(f"Found {len(authors)} tracked authors to resolve.\n")

    # Load existing mappings so we can update incrementally
    existing: dict[str, str] = {}
    if OUTPUT.exists():
        try:
            existing = json.loads(OUTPUT.read_text(encoding="utf-8"))
        except Exception:
            pass

    results: dict[str, str] = dict(existing)

    for entry in authors:
        name = entry["name"]
        inst = entry["institution"]

        if name in results:
            print(f"  [skip] {name} — already mapped to {results[name]}")
            continue

        author_id, matched_name = search_author(name, inst, api_key)
        if author_id:
            results[name] = author_id
            print(f"  [ok]   {name} → {author_id} (S2 name: \"{matched_name}\")")
        else:
            print(f"  [miss] {name} — not found in S2")

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {len(results)} author mappings to {OUTPUT}")


if __name__ == "__main__":
    main()
