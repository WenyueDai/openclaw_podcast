from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime, time

import yaml

from src.utils.timeutils import load_tz, now_local_date, iso_now_local
from src.utils.io import ensure_dir, write_jsonl, write_text
from src.utils.dedup import SeenStore
from src.collectors.rss import collect_rss_items
from src.collectors.daily_knowledge import collect_daily_knowledge_items
from src.processing.rank import rank_and_limit
from src.processing.script_llm import build_podcast_script_llm_chunked, TRANSITION_MARKER
from src.outputs.obsidian import write_obsidian_daily
from src.outputs.tts_edge import tts_text_to_mp3_chunked
from src.outputs.audio import concat_mp3_with_transitions

from src.utils.text import clean_for_tts

from src.processing.article_extract import extract_article_text
from src.processing.article_analysis import analyze_article


import shutil
import os

#  DEBUG=true python run_daily.py
DEBUG_MODE = os.environ.get('DEBUG', 'false').lower() == 'true'
REGEN_FROM_CACHE = os.environ.get('REGEN_FROM_CACHE', 'false').lower() == 'true'

def load_config(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> int:
    repo_dir = Path(__file__).resolve().parent
    cfg = load_config(repo_dir / "config.yaml")

    tz = load_tz(cfg.get("timezone", "Europe/London"))

    run_date_env = (os.environ.get("RUN_DATE") or "").strip()
    if run_date_env:
        # expected YYYY-MM-DD
        today = run_date_env
        run_anchor = datetime.combine(datetime.fromisoformat(today).date(), time.min, tz)
    else:
        today = now_local_date(tz)
        run_anchor = datetime.now(tz)

    data_dir = Path(cfg["paths"]["data_dir"]) / today
    out_dir = Path(cfg["paths"]["output_dir"]) / today
    state_dir = Path(cfg["paths"]["state_dir"])
    vault_dir = Path(cfg["paths"]["obsidian_vault"])

    ensure_dir(data_dir)
    ensure_dir(out_dir)
    ensure_dir(state_dir)
    ensure_dir(vault_dir)

    seen = SeenStore(state_dir / "seen_ids.json")

    lookback_hours = int(os.environ.get("LOOKBACK_HOURS") or cfg.get("lookback_hours", 48))

    # 1) Collect (or regenerate from cached seed)
    seed_file = data_dir / "items.jsonl"
    if REGEN_FROM_CACHE and seed_file.exists():
        new_items: List[Dict[str, Any]] = []
        for line in seed_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                new_items.append(json.loads(line))
            except Exception:
                continue
    else:
        items: List[Dict[str, Any]] = []
        items.extend(collect_rss_items(cfg["rss_sources"], tz=tz, lookback_hours=lookback_hours, now_ref=run_anchor))
        if cfg.get("daily_knowledge", {}).get("enabled", True):
            items.extend(collect_daily_knowledge_items(tz=tz))

        # 2) Dedup across days
        new_items: List[Dict[str, Any]] = []
        for it in items:
            url = (it.get("url") or "").strip()

            if not url:
                continue
            if not DEBUG_MODE and seen.has(url):
                continue
            seen.add(url)
            body = extract_article_text(url)
            it['extracted_chars'] = len(body or "")
            it['has_fulltext'] = bool(body and len(body) > 1500)
            analysis = analyze_article(url, body)
            it['analysis'] = analysis

            new_items.append(it)
        seen.save()

        write_jsonl(seed_file, new_items)

    # 3) Rank + limit
    ranked = rank_and_limit(new_items, cfg)

    # 4) Obsidian Daily (minimal, link-first)
    daily_md = write_obsidian_daily(vault_dir=vault_dir, date_str=today, items=ranked, output_dir=out_dir)

    # 5) LLM podcast script
    script_text = build_podcast_script_llm_chunked(date_str=today, items=ranked, cfg=cfg)

    # Append explicit citations to comprehensive script (for website readers / Spotify notes)
    refs: List[str] = []
    refs.append("\n\nReferences:")
    for i, it in enumerate(ranked, 1):
        title = (it.get("title") or "(untitled)").strip()
        src = (it.get("source") or "unknown source").strip()
        url = (it.get("url") or "").strip()
        if url:
            refs.append(f"[{i}] {title} — {src} — {url}")
        else:
            refs.append(f"[{i}] {title} — {src}")
    script_text = script_text.rstrip() + "\n" + "\n".join(refs) + "\n"

    script_path = out_dir / f"podcast_script_{today}_llm.txt"
    write_text(script_path, script_text)
    script_text_clean = clean_for_tts(script_text)
    script_path_clean = out_dir / f"podcast_script_{today}_llm_clean.txt"
    write_text(script_path_clean, script_text_clean)


    # 6) TTS chunk + merge (transition SFX between papers/news, not between chunks)
    if cfg.get("podcast", {}).get("enabled", True) and script_text_clean.strip():
        voice = cfg["podcast"]["voice"]
        rate = str(cfg["podcast"].get("voice_rate", "+20%"))
        chunk_chars = int(cfg["podcast"]["tts_chunk_chars"])
        parts_dir = out_dir / "tts_parts"
        ensure_dir(parts_dir)

        raw_segments = [s.strip() for s in script_text.split(TRANSITION_MARKER) if s and s.strip()]
        groups = []
        for i, seg in enumerate(raw_segments, 1):
            seg_clean = clean_for_tts(seg)
            seg_dir = parts_dir / f"seg_{i:03d}"
            ensure_dir(seg_dir)
            seg_parts = tts_text_to_mp3_chunked(
                text=seg_clean,
                out_dir=seg_dir,
                voice=voice,
                chunk_chars=chunk_chars,
                rate=rate,
            )
            if seg_parts:
                groups.append(seg_parts)

        final_mp3 = out_dir / f"podcast_{today}.mp3"
        concat_mp3_with_transitions(groups, final_mp3)
        spotify_folder = repo_dir / 'spotify'
        episodes_dir = spotify_folder / 'episodes'
        ensure_dir(episodes_dir)
        dst_mp3 = episodes_dir / final_mp3.name
        shutil.copy2(final_mp3, dst_mp3)


    status = {
        "date": today,
        "time": iso_now_local(tz),
        "n_items_raw": len(new_items),
        "n_items_used": len(ranked),
        "lookback_hours": lookback_hours,
        "run_anchor": run_anchor.isoformat(timespec="seconds"),
        "obsidian_daily": str(daily_md),
        "output_dir": str(out_dir),
    }
    (out_dir / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(json.dumps(status, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
