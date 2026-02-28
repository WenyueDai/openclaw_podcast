"""
Notion integration — saves the daily digest as a Notion database page.

Setup:
  1. Go to https://www.notion.so/my-integrations → New integration (Internal)
  2. Copy the token → NOTION_TOKEN in .env
  3. Create a Notion database → Share → Connect to your integration
  4. Copy the database ID from the URL → NOTION_DATABASE_ID in .env

Required env vars:
  NOTION_TOKEN        — ntn_xxxx or secret_xxxx
  NOTION_DATABASE_ID  — 32-char hex ID (with or without hyphens)
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


_API = "https://api.notion.com/v1"
_VERSION = "2022-06-28"


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {os.environ.get('NOTION_TOKEN', '').strip()}",
        "Content-Type": "application/json",
        "Notion-Version": _VERSION,
    }


def _strip_html(s: str) -> str:
    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup(s, "html.parser").get_text(" ", strip=True)
    except ImportError:
        return re.sub(r'<[^>]+>', ' ', s).strip()


def _rich(text: str, url: str = "") -> Dict[str, Any]:
    obj: Dict[str, Any] = {"type": "text", "text": {"content": text[:2000]}}
    if url:
        obj["text"]["link"] = {"url": url}
    return obj


def _build_blocks(date: str, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build Notion blocks for the daily digest from ranked items."""
    blocks: List[Dict[str, Any]] = []

    def h2(text: str) -> Dict[str, Any]:
        return {"object": "block", "type": "heading_2",
                "heading_2": {"rich_text": [_rich(text)]}}

    def bullet(title: str, url: str, snippet: str, source: str) -> Dict[str, Any]:
        rich: List[Dict[str, Any]] = [_rich(title, url)]
        parts = []
        if snippet:
            parts.append(snippet)
        if source:
            parts.append(f"[{source}]")
        if parts:
            rich.append(_rich("  —  " + "  ".join(parts)))
        return {"object": "block", "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": rich}}

    protein = [x for x in items if x.get("bucket") == "protein"]
    news = [x for x in items if x.get("bucket") not in ("protein", "daily")]
    daily = [x for x in items if x.get("bucket") == "daily"]

    for section_title, section_items in [
        ("Protein Design & Research", protein + news),
        ("Daily Knowledge", daily),
    ]:
        if not section_items:
            continue
        blocks.append(h2(section_title))
        for it in section_items:
            title = (it.get("title") or "").strip()[:200]
            url = (it.get("url") or "").strip()
            snippet = _strip_html((it.get("one_liner") or it.get("snippet") or "").strip())
            source = (it.get("source") or "").strip()
            blocks.append(bullet(title, url, snippet, source))
        blocks.append({"object": "block", "type": "paragraph",
                       "paragraph": {"rich_text": []}})

    return blocks


def _api_call(method: str, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{_API}/{endpoint}", data=data, headers=_headers(), method=method
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def save_script_to_notion(
    date: str,
    script_path: Path,
    items: List[Dict[str, Any]],
    md_path: Optional[Path] = None,  # kept for backward compat, unused
) -> Optional[str]:
    """Save the daily digest to Notion. Returns page URL or None."""
    token = os.environ.get("NOTION_TOKEN", "").strip()
    db_id = os.environ.get("NOTION_DATABASE_ID", "").strip().replace("-", "")
    if not token or not db_id:
        print("[notion] NOTION_TOKEN or NOTION_DATABASE_ID not set — skipping", flush=True)
        return None

    blocks = _build_blocks(date, items)
    first_batch, rest_blocks = blocks[:100], blocks[100:]

    try:
        page = _api_call("POST", "pages", {
            "parent": {"database_id": db_id},
            "properties": {
                "Name": {"title": [{"type": "text", "text": {"content": f"Knowledge Radio — {date}"}}]},
                "Date": {"date": {"start": date}},
            },
            "children": first_batch,
        })

        page_id = page.get("id", "")
        page_url = page.get("url", "")

        while rest_blocks:
            batch, rest_blocks = rest_blocks[:100], rest_blocks[100:]
            _api_call("PATCH", f"blocks/{page_id}/children", {"children": batch})

        print(f"[notion] Saved: {page_url}", flush=True)
        return page_url
    except Exception as e:
        print(f"[notion] Warning: failed to save — {e}", flush=True)
        return None
