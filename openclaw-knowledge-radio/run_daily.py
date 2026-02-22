from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import yaml

from src.utils.timeutils import load_tz, now_local_date, iso_now_local
from src.utils.io import ensure_dir, write_jsonl, write_text
from src.utils.dedup import SeenStore
from src.collectors.rss import collect_rss_items
from src.collectors.daily_knowledge import collect_daily_knowledge_items
from src.processing.rank import rank_and_limit
from src.processing.script_llm import build_podcast_script_llm
from src.outputs.obsidian import write_obsidian_daily
from src.outputs.tts_edge import tts_text_to_mp3_chunked
from src.outputs.audio import concat_mp3_ffmpeg


def load_config(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> int:
    repo_dir = Path(__file__).resolve().parent
    cfg = load_config(repo_dir / "config.yaml")

    tz = load_tz(cfg.get("timezone", "Europe/London"))
    today = now_local_date(tz)

    data_dir = Path(cfg["paths"]["data_dir"]) / today
    out_dir = Path(cfg["paths"]["output_dir"]) / today
    state_dir = Path(cfg["paths"]["state_dir"])
    vault_dir = Path(cfg["paths"]["obsidian_vault"])

    ensure_dir(data_dir)
    ensure_dir(out_dir)
    ensure_dir(state_dir)
    ensure_dir(vault_dir)

    seen = SeenStore(state_dir / "seen_ids.json")

    lookback_hours = int(cfg.get("lookback_hours", 48))

    # 1) Collect
    items: List[Dict[str, Any]] = []
    items.extend(collect_rss_items(cfg["rss_sources"], tz=tz, lookback_hours=lookback_hours))
    if cfg.get("daily_knowledge", {}).get("enabled", True):
        items.extend(collect_daily_knowledge_items(tz=tz))

    # 2) Dedup across days
    new_items: List[Dict[str, Any]] = []
    for it in items:
        url = (it.get("url") or "").strip()
        if not url:
            continue
        if seen.has(url):
            continue
        seen.add(url)
        new_items.append(it)
    seen.save()

    write_jsonl(data_dir / "items.jsonl", new_items)

    # 3) Rank + limit
    ranked = rank_and_limit(new_items, cfg)

    # 4) Obsidian Daily (minimal, link-first)
    daily_md = write_obsidian_daily(vault_dir=vault_dir, date_str=today, items=ranked, output_dir=out_dir)

    # 5) LLM podcast script
    script_text = build_podcast_script_llm(date_str=today, items=ranked, cfg=cfg)
    script_path = out_dir / f"podcast_script_{today}_llm.txt"
    write_text(script_path, script_text)

    # 6) TTS chunk + merge
    if cfg.get("podcast", {}).get("enabled", True) and script_text.strip():
        voice = cfg["podcast"]["voice"]
        chunk_chars = int(cfg["podcast"]["tts_chunk_chars"])
        parts_dir = out_dir / "tts_parts"
        ensure_dir(parts_dir)

        part_files = tts_text_to_mp3_chunked(
            text=script_text,
            out_dir=parts_dir,
            voice=voice,
            chunk_chars=chunk_chars,
        )
        final_mp3 = out_dir / f"podcast_{today}.mp3"
        concat_mp3_ffmpeg(part_files, final_mp3)

    status = {
        "date": today,
        "time": iso_now_local(tz),
        "n_items_raw": len(new_items),
        "n_items_used": len(ranked),
        "obsidian_daily": str(daily_md),
        "output_dir": str(out_dir),
    }
    (out_dir / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(json.dumps(status, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
