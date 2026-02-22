from datetime import datetime
import requests
from typing import List, Dict

def collect_daily_knowledge_items(*, tz) -> List[Dict]:
    items = []

    # 1️⃣ On This Day
    now = datetime.now(tz)
    mm = f"{now.month:02d}"
    dd = f"{now.day:02d}"

    url = f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/all/{mm}/{dd}"
    try:
        r = requests.get(url, timeout=20)
        data = r.json()
        for ev in data.get("events", [])[:2]:
            year = ev.get("year")
            text = ev.get("text", "")
            pages = ev.get("pages", [])
            if pages:
                title = pages[0].get("title")
                link = pages[0]["content_urls"]["desktop"]["page"]
                items.append({
                    "bucket": "daily",
                    "source": "Wikipedia On This Day",
                    "title": title,
                    "url": link,
                    "one_liner": f"{year}: {text}",
                    "tags": ["history", "wikipedia"]
                })
    except Exception:
        pass

    # 2️⃣ Random Article
    try:
        r = requests.get("https://en.wikipedia.org/api/rest_v1/page/random/summary")
        data = r.json()
        items.append({
            "bucket": "daily",
            "source": "Wikipedia Random",
            "title": data.get("title"),
            "url": data.get("content_urls", {}).get("desktop", {}).get("page"),
            "one_liner": data.get("extract"),
            "tags": ["random", "wikipedia"]
        })
    except Exception:
        pass

    return items
