from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

import requests


def collect_daily_knowledge_items(*, tz) -> List[Dict[str, Any]]:
    # Wikipedia "On this day" REST API (events)
    now = datetime.now(tz)
    mm = f"{now.month:02d}"
    dd = f"{now.day:02d}"
    url = f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/all/{mm}/{dd}"

    out: List[Dict[str, Any]] = []
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        data = r.json()
        events = data.get("events", []) or []
        for ev in events[:2]:
            year = ev.get("year")
            text = (ev.get("text") or "").strip()
            pages = ev.get("pages") or []
            link = ""
            title = ""
            if pages:
                title = pages[0].get("normalizedtitle") or pages[0].get("title") or ""
                content_urls = pages[0].get("content_urls") or {}
                link = (content_urls.get("desktop") or {}).get("page") or ""
            if not title:
                title = f"On this day: {year}" if year else "On this day"
            if not link:
                link = "https://en.wikipedia.org/wiki/Main_Page"

            one = f"{year}: {text}" if year else text
            if len(one) > 280:
                one = one[:277] + "..."
            out.append(
                {
                    "bucket": "daily",
                    "source": "Wikipedia On This Day",
                    "source_type": "wiki",
                    "title": title,
                    "url": link,
                    "one_liner": one,
                    "tags": ["daily-knowledge"],
                }
            )
    except Exception:
        return []
    return out
