"""
Notion integration — saves daily podcast script as a page in a Notion database.

Setup:
  1. Go to https://www.notion.so/my-integrations → New integration
  2. Copy the Internal Integration Token → NOTION_TOKEN in .env
  3. Create a database in Notion (table view works well)
  4. Open the database → click Share → invite your integration
  5. Copy the database ID from the URL:
       https://notion.so/yourworkspace/<DATABASE_ID>?v=...
     → NOTION_DATABASE_ID in .env

Required env vars:
  NOTION_TOKEN        — secret_xxxx
  NOTION_DATABASE_ID  — 32-char hex ID (with or without hyphens)
"""
from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.request


_API = "https://api.notion.com/v1"
_VERSION = "2022-06-28"


def _headers() -> Dict[str, str]:
    token = os.environ.get("NOTION_TOKEN", "").strip()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": _VERSION,
    }


def _post(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{_API}/{endpoint}",
        data=data,
        headers=_headers(),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _text_blocks(text: str) -> List[Dict[str, Any]]:
    """Split text into Notion paragraph blocks (max 2000 chars each)."""
    blocks = []
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        # Notion paragraph content limit is 2000 chars
        while para:
            chunk, para = para[:2000], para[2000:]
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": chunk}}]
                },
            })
    return blocks or [{"object": "block", "type": "paragraph",
                       "paragraph": {"rich_text": []}}]


def save_script_to_notion(
    date: str,
    script_path: Path,
    items: List[Dict[str, Any]],
) -> Optional[str]:
    """
    Create a Notion page for today's episode.
    Returns the page URL, or None if skipped/failed.
    """
    token = os.environ.get("NOTION_TOKEN", "").strip()
    db_id = os.environ.get("NOTION_DATABASE_ID", "").strip().replace("-", "")
    if not token or not db_id:
        print("[notion] NOTION_TOKEN or NOTION_DATABASE_ID not set — skipping", flush=True)
        return None

    if not script_path or not script_path.exists():
        print("[notion] Script file not found — skipping", flush=True)
        return None

    script_text = script_path.read_text(encoding="utf-8", errors="ignore")

    # Build item summary for the top of the page
    item_lines = []
    for it in items[:40]:
        title = (it.get("title") or "").strip()
        url = (it.get("url") or "").strip()
        src = (it.get("source") or "").strip()
        line = f"• {title}"
        if src:
            line += f"  [{src}]"
        if url:
            line += f"\n  {url}"
        item_lines.append(line)
    item_summary = "\n".join(item_lines)

    # Page title
    title_text = f"Knowledge Radio — {date}"

    # Blocks: divider, item list, divider, full script
    children: List[Dict[str, Any]] = [
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": f"Papers & News ({len(items)})"}}]
            },
        },
        *_text_blocks(item_summary),
        {"object": "block", "type": "divider", "divider": {}},
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "Podcast Script"}}]
            },
        },
        *_text_blocks(script_text),
    ]

    # Notion API: max 100 children per request — send in batches after page creation
    first_batch, rest = children[:100], children[100:]

    payload = {
        "parent": {"database_id": db_id},
        "properties": {
            "Name": {
                "title": [{"type": "text", "text": {"content": title_text}}]
            },
            "Date": {
                "date": {"start": date}
            },
        },
        "children": first_batch,
    }

    try:
        page = _post("pages", payload)
        page_id = page.get("id", "")
        page_url = page.get("url", "")

        # Append remaining blocks in batches of 100
        while rest:
            batch, rest = rest[:100], rest[100:]
            data = json.dumps({"children": batch}).encode()
            req = urllib.request.Request(
                f"{_API}/blocks/{page_id}/children",
                data=data,
                headers=_headers(),
                method="PATCH",
            )
            urllib.request.urlopen(req, timeout=30)

        print(f"[notion] Saved: {page_url}", flush=True)
        return page_url
    except Exception as e:
        print(f"[notion] Warning: failed to save — {e}", flush=True)
        return None
