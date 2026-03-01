#!/usr/bin/env python3
"""
Sync paper_notes.json → Notion deep-dive database.

Runs via GitHub Actions whenever paper_notes.json changes.
- First time a note is seen: creates a stub page in Notion.
- If the note text changes: updates the existing page (no duplicates).
"""
import json
import os
import requests
from pathlib import Path

NOTION_API_KEY  = os.environ["NOTION_API_KEY"]
DATABASE_ID     = os.environ.get("NOTION_DATABASE_ID", "3165f58ea8c280498f72c770028aec0d")

PACKAGE_DIR  = Path(__file__).resolve().parent.parent
NOTES_FILE   = PACKAGE_DIR / "state" / "paper_notes.json"
CREATED_FILE = PACKAGE_DIR / "state" / "notion_created.json"
OUTPUT_DIR   = PACKAGE_DIR / "output"

HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}


def _load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def _note_fields(val) -> tuple[str, str, str]:
    """Return (note_text, title, source) from either string or dict format."""
    if isinstance(val, str):
        return val, "", ""
    if isinstance(val, dict):
        return val.get("note", ""), val.get("title", ""), val.get("source", "")
    return "", "", ""


def _created_entry(entry) -> tuple[str, str]:
    """Return (page_id, saved_note) from either old string or new dict format."""
    if isinstance(entry, str):
        return entry, ""
    if isinstance(entry, dict):
        return entry.get("page_id", ""), entry.get("note", "")
    return "", ""


def _find_item_meta(date: str, url: str) -> tuple[str, str]:
    """Look up paper title and source from episode_items.json."""
    items_file = OUTPUT_DIR / date / "episode_items.json"
    if not items_file.exists():
        return "", ""
    try:
        raw = json.loads(items_file.read_text(encoding="utf-8"))
        items = raw.get("items", raw) if isinstance(raw, dict) else raw
        for item in items:
            if item.get("url") == url:
                return item.get("title", ""), item.get("source", "")
    except Exception:
        pass
    return "", ""


def _ensure_source_property() -> None:
    """Add a 'Source' select property to the database if it doesn't exist yet."""
    try:
        requests.patch(
            f"https://api.notion.com/v1/databases/{DATABASE_ID}",
            json={"properties": {"Source": {"select": {}}}},
            headers=HEADERS,
            timeout=30,
        )
    except Exception:
        pass


def create_notion_page(title: str, url: str, date: str, source: str, note: str) -> str:
    body = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "Name":   {"title":     [{"text": {"content": title[:2000]}}]},
            "Date":   {"date":      {"start": date}},
            "Note":   {"rich_text": [{"text": {"content": note[:2000]}}]},
            "Source": {"select":    {"name": "Daily Note"}},
        },
        "children": [
            # Owner's initial note in a green callout
            {
                "object": "block", "type": "callout",
                "callout": {
                    "icon": {"type": "emoji", "emoji": "✏️"},
                    "rich_text": [{"type": "text", "text": {"content": note[:2000]}}],
                    "color": "green_background",
                },
            },
            # Metadata line
            {
                "object": "block", "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {
                        "content": f"📅 {date}   |   📰 {source or 'Unknown source'}"
                    }}]
                },
            },
            # Bookmark to the paper
            {"object": "block", "type": "bookmark", "bookmark": {"url": url}},
            {"object": "block", "type": "divider", "divider": {}},
            # Empty deep-dive section for the owner to fill in
            {
                "object": "block", "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "Deep Dive Notes"}}],
                },
            },
            {
                "object": "block", "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": ""}}]},
            },
        ],
    }
    r = requests.post("https://api.notion.com/v1/pages", json=body, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()["id"]


def update_notion_page(page_id: str, note: str) -> None:
    """Update the Note property and the green callout block on an existing page."""
    # 1. Update the Note database property
    r = requests.patch(
        f"https://api.notion.com/v1/pages/{page_id}",
        json={"properties": {"Note": {"rich_text": [{"text": {"content": note[:2000]}}]}}},
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()

    # 2. Find the callout block (first child) and update its text
    r2 = requests.get(
        f"https://api.notion.com/v1/blocks/{page_id}/children",
        headers=HEADERS,
        timeout=30,
    )
    r2.raise_for_status()
    blocks = r2.json().get("results", [])
    for block in blocks:
        if block.get("type") == "callout":
            block_id = block["id"]
            requests.patch(
                f"https://api.notion.com/v1/blocks/{block_id}",
                json={"callout": {"rich_text": [{"type": "text", "text": {"content": note[:2000]}}]}},
                headers=HEADERS,
                timeout=30,
            ).raise_for_status()
            break


def main():
    notes   = _load_json(NOTES_FILE, {})
    created = _load_json(CREATED_FILE, {})

    _ensure_source_property()
    new_pages = 0
    updated   = 0
    for date, date_notes in sorted(notes.items()):
        for url, val in date_notes.items():
            key = f"{date}|{url}"

            note_text, saved_title, saved_source = _note_fields(val)
            if not note_text:
                continue

            # Prefer metadata from episode_items.json (more reliable)
            ep_title, ep_source = _find_item_meta(date, url)
            title  = ep_title  or saved_title  or url
            source = ep_source or saved_source or ""

            if key in created:
                page_id, prev_note = _created_entry(created[key])
                if note_text == prev_note:
                    continue  # unchanged — nothing to do
                # Note changed: update the existing Notion page
                try:
                    update_notion_page(page_id, note_text)
                    created[key] = {"page_id": page_id, "note": note_text}
                    print(f"↺ Updated: {title[:70]}")
                    updated += 1
                except Exception as e:
                    print(f"✗ Failed update for {url[:60]}: {e}")
            else:
                # New note: create a Notion page
                try:
                    page_id = create_notion_page(title, url, date, source, note_text)
                    created[key] = {"page_id": page_id, "note": note_text}
                    print(f"✓ Created: {title[:70]}")
                    new_pages += 1
                except Exception as e:
                    print(f"✗ Failed for {url[:60]}: {e}")

    CREATED_FILE.write_text(
        json.dumps(created, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nDone. Created {new_pages} new, updated {updated} existing Notion page(s).")


if __name__ == "__main__":
    main()
