from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List
from urllib.parse import quote
import requests


def collect_wiki_context_items(topics: List[str], *, date_str: str, max_items: int = 5) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for topic in topics[:max_items]:
        title = (topic or "").strip()
        if not title:
            continue
        try:
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'))}"
            r = requests.get(url, timeout=20)
            if r.status_code != 200:
                continue
            data = r.json()
            extract = (data.get("extract") or "").strip()
            page_url = ((data.get("content_urls") or {}).get("desktop") or {}).get("page") or f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"
            if not extract:
                continue
            items.append(
                {
                    "title": f"Wiki Context: {data.get('title', title)}",
                    "url": f"{page_url}?ctx_date={date_str}",
                    "canonical_url": page_url,
                    "source": f"Wikipedia: {data.get('title', title)}",
                    "published": datetime.utcnow().isoformat() + "Z",
                    "tags": ["wiki", "context"],
                    "bucket": "daily",
                    "analysis": extract,
                    "extracted_chars": len(extract),
                    "has_fulltext": True,
                    "kind": "wiki_context",
                }
            )
        except Exception:
            continue
    return items
