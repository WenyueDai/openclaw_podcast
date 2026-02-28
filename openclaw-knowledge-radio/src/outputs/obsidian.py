from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from src.utils.io import ensure_dir, write_text


def _strip_html(s: str) -> str:
    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup(s, "html.parser").get_text(" ", strip=True)
    except ImportError:
        return re.sub(r'<[^>]+>', ' ', s).strip()


def _safe_tag(s: str) -> str:
    s = (s or "").strip().lower().replace(" ", "-")
    s = "".join(ch for ch in s if ch.isalnum() or ch in "-_")
    return s[:40] if s else "tag"


def write_obsidian_daily(*, vault_dir: Path, date_str: str, items: List[Dict[str, Any]], output_dir: Path) -> Path:
    daily_dir = vault_dir / "Daily"
    ensure_dir(daily_dir)

    lines: List[str] = []
    lines.append("---")
    lines.append(f"date: {date_str}")
    lines.append("type: daily-digest")
    lines.append("---")
    lines.append("")
    lines.append(f"# {date_str} Digest")
    lines.append("")

    protein = [x for x in items if x.get("bucket") == "protein"]
    daily = [x for x in items if x.get("bucket") == "daily"]
    other = [x for x in items if x.get("bucket") not in ("protein", "daily")]

    def add_section(title: str, xs: List[Dict[str, Any]]) -> None:
        if not xs:
            return
        lines.append(f"## {title}")
        for it in xs:
            t = (it.get("title") or "").strip()[:200]
            url = (it.get("url") or "").strip()
            one = _strip_html((it.get("one_liner") or "").strip())
            tags = it.get("tags") or []
            src = it.get("source") or ""
            tag_str = " ".join(f"#{_safe_tag(z)}" for z in tags[:6])
            if one:
                lines.append(f"- [{t}]({url}) — {one}  {tag_str}  (来源: {src})")
            else:
                lines.append(f"- [{t}]({url})  {tag_str}  (来源: {src})")
        lines.append("")

    add_section("Protein design / Innovation", protein + other)
    add_section("Daily knowledge", daily)

    mp3_path = output_dir / f"podcast_{date_str}.mp3"
    lines.append("## Podcast")
    lines.append(f"- file: {mp3_path}")
    lines.append("")

    out_path = daily_dir / f"{date_str}.md"
    write_text(out_path, "\n".join(lines))
    return out_path
