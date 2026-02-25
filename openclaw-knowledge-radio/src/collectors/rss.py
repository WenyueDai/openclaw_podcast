from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import feedparser
from dateutil import parser as dtparser

from src.utils.timeutils import cutoff_datetime


def _parse_dt(dt_str: str) -> Optional[datetime]:
    try:
        return dtparser.parse(dt_str)
    except Exception:
        return None


def collect_rss_items(sources: List[Dict[str, Any]], *, tz, lookback_hours: int, now_ref: Optional[datetime] = None) -> List[Dict[str, Any]]:
    upper = now_ref or datetime.now(tz)
    cutoff = cutoff_datetime(tz, lookback_hours, now_dt=upper)
    out: List[Dict[str, Any]] = []

    for src in sources:
        feed = feedparser.parse(src["url"])
        for e in getattr(feed, "entries", []) or []:
            title = (getattr(e, "title", "") or "").strip()
            url = (getattr(e, "link", "") or "").strip()

            # date
            dt = None
            for k in ["published", "updated", "created"]:
                v = getattr(e, k, None)
                if v:
                    dt = _parse_dt(v)
                    if dt:
                        break

            if dt is not None:
                try:
                    dt_local = dt.astimezone(tz)
                    # bounded window: [cutoff, upper)
                    if dt_local < cutoff or dt_local >= upper:
                        continue
                except Exception:
                    # if naive / weird, keep it (dedup handles repeats)
                    pass

            summary = (getattr(e, "summary", "") or "").strip()
            if len(summary) > 360:
                summary = summary[:357] + "..."

            out.append(
                {
                    "bucket": src.get("bucket", "protein"),
                    "source": src["name"],
                    "source_type": "rss",
                    "title": title,
                    "url": url,
                    "one_liner": summary or "",
                    "tags": list(src.get("tags", [])),
                }
            )
    return out
