"""
Notion integration — saves the daily digest markdown to a Notion database page.

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


def _rich(text: str, url: str = "") -> Dict[str, Any]:
    obj: Dict[str, Any] = {"type": "text", "text": {"content": text[:2000]}}
    if url:
        obj["text"]["link"] = {"url": url}
    return obj


def _md_to_blocks(md: str) -> List[Dict[str, Any]]:
    """Convert the daily digest markdown into Notion blocks."""
    blocks: List[Dict[str, Any]] = []
    # Regex for bullet items: - [title](url) — snippet  #tags  (来源: src)
    bullet_re = re.compile(r'^\s*-\s+\[([^\]]+)\]\(([^)]+)\)(.*)')

    for line in md.splitlines():
        # Skip frontmatter lines
        if line.strip() in ("---", ""):
            continue
        if line.startswith("date:") or line.startswith("type:"):
            continue

        # H1
        if line.startswith("# "):
            blocks.append({
                "object": "block", "type": "heading_1",
                "heading_1": {"rich_text": [_rich(line[2:].strip())]}
            })
            continue

        # H2
        if line.startswith("## "):
            blocks.append({
                "object": "block", "type": "heading_2",
                "heading_2": {"rich_text": [_rich(line[3:].strip())]}
            })
            continue

        # Bullet item with link
        m = bullet_re.match(line)
        if m:
            title, url, rest = m.group(1).strip(), m.group(2).strip(), m.group(3)
            # Strip tags (#xxx) and source annotation
            rest = re.sub(r'#\S+', '', rest)
            rest = re.sub(r'\(来源:.*?\)', '', rest)
            rest = rest.strip(" —").strip()
            rich: List[Dict[str, Any]] = [_rich(title, url)]
            if rest:
                rich.append(_rich(f"  —  {rest}"))
            blocks.append({
                "object": "block", "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": rich}
            })
            continue

        # Plain bullet (no link)
        if line.strip().startswith("- "):
            blocks.append({
                "object": "block", "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [_rich(line.strip()[2:])]}
            })
            continue

        # Everything else as a paragraph
        stripped = line.strip()
        if stripped:
            blocks.append({
                "object": "block", "type": "paragraph",
                "paragraph": {"rich_text": [_rich(stripped)]}
            })

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
    script_path: Path,          # kept for API compat; unused now
    items: List[Dict[str, Any]],
    md_path: Optional[Path] = None,
) -> Optional[str]:
    """Save the daily digest markdown to Notion. Returns page URL or None."""
    token = os.environ.get("NOTION_TOKEN", "").strip()
    db_id = os.environ.get("NOTION_DATABASE_ID", "").strip().replace("-", "")
    if not token or not db_id:
        print("[notion] NOTION_TOKEN or NOTION_DATABASE_ID not set — skipping", flush=True)
        return None

    # Prefer the markdown file; fall back to script
    source = md_path or script_path
    if not source or not source.exists():
        print("[notion] Source file not found — skipping", flush=True)
        return None

    md_text = source.read_text(encoding="utf-8", errors="ignore")
    blocks = _md_to_blocks(md_text)

    # Notion allows max 100 children on page creation
    first_batch, rest_blocks = blocks[:100], blocks[100:]

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

    # Append remaining blocks in batches of 100
    while rest_blocks:
        batch, rest_blocks = rest_blocks[:100], rest_blocks[100:]
        _api_call("PATCH", f"blocks/{page_id}/children", {"children": batch})

    print(f"[notion] Saved: {page_url}", flush=True)
    return page_url
