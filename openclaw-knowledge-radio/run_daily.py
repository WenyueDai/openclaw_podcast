from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Tuple
from datetime import datetime, time

import yaml

from src.utils.timeutils import load_tz, now_local_date, iso_now_local
from src.utils.io import ensure_dir, write_jsonl, write_text
from src.utils.dedup import SeenStore
from src.collectors.rss import collect_rss_items
from src.collectors.daily_knowledge import collect_daily_knowledge_items
from src.collectors.wiki_context import collect_wiki_context_items
from src.collectors.pubmed import collect_pubmed_items
from src.processing.rank import rank_and_limit
from src.processing.script_llm import build_podcast_script_llm_chunked, TRANSITION_MARKER
from src.outputs.tts_edge import tts_text_to_mp3_chunked
from src.outputs.audio import concat_mp3_with_transitions

from src.utils.text import clean_for_tts

from src.processing.article_extract import extract_article_text
from src.processing.article_analysis import analyze_article
from src.outputs.github_publish import upload_episode, push_site
from src.outputs.notion_publish import save_script_to_notion


import shutil
import os

#  DEBUG=true python run_daily.py
DEBUG_MODE = os.environ.get('DEBUG', 'false').lower() == 'true'
REGEN_FROM_CACHE = os.environ.get('REGEN_FROM_CACHE', 'false').lower() == 'true'

SITE_URL = "https://wenyuedai.github.io/openclaw_podcast"


def _notify_slack(date: str, ranked: List[Dict[str, Any]], cfg: Dict[str, Any]) -> None:
    """Post a summary to Slack via Incoming Webhook. No-op if SLACK_WEBHOOK_URL is unset."""
    import urllib.request
    webhook = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not webhook:
        return

    # Top 5 items for the digest
    lines = []
    for it in ranked[:5]:
        title = (it.get("title") or "").strip()
        url = (it.get("url") or "").strip()
        src = (it.get("source") or "").strip()
        entry = f"• <{url}|{title}>" if url else f"• {title}"
        if src:
            entry += f"  _{src}_"
        lines.append(entry)

    items_block = "\n".join(lines) if lines else "_(no items)_"
    total = len(ranked)
    text = (
        f":studio_microphone: *Knowledge Radio — {date}*\n"
        f"{total} papers & news selected | <{SITE_URL}|Listen on GitHub Pages>\n\n"
        f"*Top picks:*\n{items_block}"
    )

    payload = json.dumps({"text": text}).encode()
    req = urllib.request.Request(webhook, data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
        print("[slack] Notification sent", flush=True)
    except Exception as e:
        print(f"[slack] Warning: could not send notification — {e}", flush=True)

def load_config(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _resolve(base: Path, p: str) -> Path:
    """Resolve p against base when p is a relative path, otherwise return as-is."""
    resolved = Path(p)
    return resolved if resolved.is_absolute() else base / resolved


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

    data_dir = _resolve(repo_dir, cfg["paths"]["data_dir"]) / today
    out_dir = _resolve(repo_dir, cfg["paths"]["output_dir"]) / today
    state_dir = _resolve(repo_dir, cfg["paths"]["state_dir"])

    ensure_dir(data_dir)
    ensure_dir(out_dir)
    ensure_dir(state_dir)

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
        if cfg.get("pubmed", {}).get("enabled", False):
            items.extend(collect_pubmed_items(cfg, lookback_hours=lookback_hours))
        if cfg.get("daily_knowledge", {}).get("enabled", True):
            items.extend(collect_daily_knowledge_items(tz=tz))
        if cfg.get("wiki_context", {}).get("enabled", False):
            items.extend(
                collect_wiki_context_items(
                    cfg.get("wiki_context", {}).get("topics", []),
                    date_str=today,
                    max_items=int(cfg.get("wiki_context", {}).get("max_items", 4)),
                )
            )

        # 2) Dedup across days + topical filtering
        excluded_terms = list(cfg.get("excluded_terms", [
            "cell biology", "single-cell", "single cell", "animal model", "murine",
            "mouse", "mice", "rat", "zebrafish", "drosophila", "in vivo"
        ]))

        # First pass: filter and mark which items need fetch/analysis
        candidates: List[Dict[str, Any]] = []
        new_items: List[Dict[str, Any]] = []
        for it in items:
            url = (it.get("url") or "").strip()
            title = (it.get("title") or "")
            source = (it.get("source") or "")
            hay = f"{title} {source} {url}".lower()

            if not url:
                continue
            if any(t in hay for t in excluded_terms):
                continue

            # Wiki context items are pre-built summaries; keep them lightweight.
            if it.get("kind") == "wiki_context":
                new_items.append(it)
                continue

            if not DEBUG_MODE and seen.has(url):
                continue
            seen.add(url)
            candidates.append(it)
        seen.save()

        # Second pass: parallel article extract + analysis
        max_workers = int(cfg.get("fetch_workers", 8))
        analysis_model = cfg.get("llm", {}).get("analysis_model") or cfg.get("llm", {}).get("model")

        def _fetch_and_analyze(it: Dict[str, Any]) -> Dict[str, Any]:
            url = (it.get("url") or "").strip()
            body = extract_article_text(url)
            it["extracted_chars"] = len(body or "")
            it["has_fulltext"] = bool(body and len(body) > 1500)
            it["analysis"] = analyze_article(url, body, model=analysis_model)
            return it

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_fetch_and_analyze, it): it for it in candidates}
            for fut in as_completed(futures):
                try:
                    new_items.append(fut.result())
                except Exception:
                    new_items.append(futures[fut])

        write_jsonl(seed_file, new_items)

    # 3) Rank + limit
    ranked = rank_and_limit(new_items, cfg)

    # 4) Save ranked item list for the website (complete index, not just highlights)
    import json as _json
    import re as _re
    try:
        from bs4 import BeautifulSoup as _BS
        def _strip_html(s: str) -> str:
            return _BS(s, "html.parser").get_text(" ", strip=True)
    except ImportError:
        def _strip_html(s: str) -> str:
            return _re.sub(r'<[^>]+>', ' ', s).strip()

    def _best_summary(it: Dict[str, Any]) -> str:
        # Try one_liner / snippet first (strip HTML)
        raw = (it.get("one_liner") or it.get("snippet") or "").strip()
        clean = _strip_html(raw)
        if len(clean) > 30:
            return clean
        # Fall back to CORE CLAIM from LLM analysis
        analysis = (it.get("analysis") or "").strip()
        m = _re.search(r'CORE CLAIM:\s*(.+?)(?:\n[A-Z ]+:|$)', analysis, _re.S)
        if m:
            sentence = m.group(1).strip().split(". ")[0]
            if sentence and sentence.lower() != "not stated in source text":
                return sentence + ("." if not sentence.endswith(".") else "")
        return ""

    (out_dir / "episode_items.json").write_text(
        _json.dumps([
            {
                "title": (it.get("title") or "").strip(),
                "url": (it.get("url") or "").strip(),
                "source": (it.get("source") or "").strip(),
                "one_liner": _best_summary(it),
                "bucket": (it.get("bucket") or "").strip(),
            }
            for it in ranked
        ], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

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

        # Clean up intermediate TTS chunks and temp ffmpeg files
        pub_cfg = cfg.get("publish", {})
        if pub_cfg.get("cleanup_intermediate", True):
            shutil.rmtree(parts_dir, ignore_errors=True)
            for tmp in ["ffmpeg_concat_list.txt", "transition_sfx.mp3"]:
                p = out_dir / tmp
                if p.exists():
                    p.unlink()

        # Publish to GitHub Release + push GitHub Pages
        if pub_cfg.get("enabled", False):
            release_repo = pub_cfg.get("github_release_repo", "")
            if release_repo:
                upload_episode(
                    today,
                    final_mp3,
                    script_path_clean,
                    repo=release_repo,
                    state_dir=state_dir,
                )
            push_site(repo_dir, repo_dir.parent, today)

    status = {
        "date": today,
        "time": iso_now_local(tz),
        "n_items_raw": len(new_items),
        "n_items_used": len(ranked),
        "lookback_hours": lookback_hours,
        "run_anchor": run_anchor.isoformat(timespec="seconds"),
        "output_dir": str(out_dir),
    }
    (out_dir / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(json.dumps(status, indent=2))

    save_script_to_notion(today, script_path, ranked)
    _notify_slack(today, ranked, cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
