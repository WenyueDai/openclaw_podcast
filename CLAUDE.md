# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

An automated daily podcast generator for protein design research. Every day at 03:00 UTC, a GitHub Actions workflow collects papers from 79 RSS feeds + 35 PubMed queries, ranks them with a 10-tier algorithm, generates a narrated script via LLM, synthesizes audio (Edge TTS → MP3), uploads to a GitHub Release, and rebuilds a static GitHub Pages site — all without human intervention.

## Repository Layout

All Python pipeline code lives in `openclaw-knowledge-radio/`. The static site is in `docs/`. A Cloudflare Worker for visitor messages is in `visitor-message-worker/`.

```
openclaw-knowledge-radio/
├── run_daily.py          # Orchestrator / entry point
├── config.yaml           # RSS sources, ranking config, LLM settings, exclusions
├── requirements.txt
├── .env.example          # Copy to .env and fill in keys
├── src/
│   ├── collectors/       # Phase 1: RSS, PubMed, BioRxiv fetchers
│   ├── processing/       # Phase 2–3: article_analysis, rank, script_llm
│   ├── outputs/          # Phase 4–5: tts_edge, audio, github_publish, notion_publish
│   └── utils/            # dedup, io, text, timeutils
├── tools/                # Standalone scripts (build_site, sync_notion_notes, process_missed_papers, check_feeds)
└── state/                # Persistent JSON state (seen_ids, feedback, paper_notes, etc.)
```

## Setup

```bash
cd openclaw-knowledge-radio
bash install.sh            # Creates .venv, installs pip deps + ffmpeg
cp .env.example .env       # Fill in OPENROUTER_API_KEY and GITHUB_TOKEN (required)
```

Load env before running: `export $(cat .env | xargs)` or `source .env`.

## Running the Pipeline

All commands run from inside `openclaw-knowledge-radio/`:

```bash
# Normal run (today's episode)
python run_daily.py

# Regenerate from cached items (skip RSS/PubMed fetch, reuse analysis cache)
REGEN_FROM_CACHE=true python run_daily.py

# Specific past date
RUN_DATE=2026-02-20 python run_daily.py

# Debug mode (skips real LLM calls, uses cached/stub data)
DEBUG=true python run_daily.py

# Force re-upload MP3 even if Release already exists
FORCE_REPUBLISH=true python run_daily.py

# Check RSS feed health
python tools/check_feeds.py

# Rebuild the GitHub Pages site from existing state (no new episode)
python tools/build_site.py

# Diagnose missed papers + extract keywords for boosting
python tools/process_missed_papers.py

# Sync paper_notes.json → Notion stubs
python tools/sync_notion_notes.py
```

## CI/CD Workflows

| Workflow | Trigger | What it does |
|---|---|---|
| `daily_podcast.yml` | Cron 03:00 UTC | Full pipeline + prune old output dirs |
| `sync_notes.yml` | Push to `state/paper_notes.json` | Sync owner notes → Notion |
| `process_missed.yml` | Push to `state/missed_papers.json` | Diagnose missed papers + rebuild site |

Commits from CI use `[skip ci]` to avoid loops.

## Architecture: Pipeline Phases

`run_daily.py` has an **idempotency guard** — it checks `state/release_index.json` and exits early if today's episode is already published.

1. **Collect**: RSS (`src/collectors/rss.py`) + PubMed (`pubmed.py`) fetched in parallel. URL dedup via SHA1 against `state/seen_ids.json`.
2. **Analyse**: Parallel LLM calls (8 workers) in `src/processing/article_analysis.py` — full-text extraction + novelty scoring. Results cached per-article in `data/article_analysis/`.
3. **Rank**: `src/processing/rank.py` — 10-tier system (see below). Caps at 40 items total.
4. **Script**: `src/processing/script_llm.py` — OpenRouter (OpenAI-compatible) generates deep-dives (~250–300 words) and roundup blurbs per paper. Uses `[[TRANSITION]]` markers between segments.
5. **TTS**: `src/outputs/tts_edge.py` — Edge TTS primary, Kokoro local server fallback, gTTS last resort. Voice: `en-GB-RyanNeural` at `+35%` rate.
6. **Audio**: `src/outputs/audio.py` — ffmpeg concat with transition tones (C6 + E6 dings) + `atempo=1.2` (20% speedup).
7. **Publish**: GitHub Release upload → site rebuild → Notion digest → git commit/push.

## Ranking Algorithm (10 Tiers)

The ranking in `src/processing/rank.py` is the core personalization mechanism:

| Tier | Signal | Notes |
|---|---|---|
| 0 | Researcher arXiv feeds | ~50 named researchers (Baker, Ovchinnikov, Rives, etc.) — hoisted before caps |
| 1 | Blog/Substack sources | BLOPIG, A-Alpha Bio, AlQuraishi, etc. — hoisted before caps |
| 2 | Absolute title keywords | AlphaFold, RFdiffusion, ProteinMPNN, ESMFold, Boltz, Chroma, etc. |
| 3 | Missed paper keywords | Extracted from `state/boosted_topics.json` (populated by `process_missed_papers.py`) |
| 4 | Feedback score | Time-decayed (14-day half-life) from `state/feedback.json` |
| 5 | Config topic keywords | 39 keywords from `config.yaml` (antibody design, diffusion, enzyme engineering, etc.) |
| 6 | Journal quality | Nature Biotech > PNAS > Nature > arXiv > news |
| 7 | Research bucket | protein/journal/ai_bio > news |
| 8 | Full-text available | |
| 9 | Text length | Tie-breaker |

Tier-0 and Tier-1 sources are **hoisted** (shown before bucket quotas apply) so they're never buried by mainstream journals.

## State Files

All state lives in `openclaw-knowledge-radio/state/` and is committed to the repo:

| File | Purpose |
|---|---|
| `seen_ids.json` | SHA1 URL dedup across runs |
| `release_index.json` | Date → GitHub Release audio URL |
| `feedback.json` | Owner paper selections (time-decayed boost) |
| `paper_notes.json` | Owner expert annotations per paper |
| `notion_created.json` | Tracks which notes were synced to Notion |
| `missed_papers.json` | Owner-submitted missed papers + diagnoses |
| `boosted_topics.json` | Keywords extracted from missed papers (feeds Tier-3) |
| `extra_rss_sources.json` | Auto-discovered RSS feeds |

## Key Configuration (`config.yaml`)

- `rss_sources`: 79 curated feeds organized by domain. Add/remove feeds here.
- `pubmed`: 35 keyword queries in 7 protein design categories.
- `excluded_terms`: Terms that disqualify an article (mouse models, neurogenesis, etc.).
- `ranking.topic_keywords`: 39 keywords for Tier-5 scoring.
- `ranking.absolute_title_keywords`: Landmark model names for Tier-2 automatic hoisting.
- `limits`: `max_items: 40`, `max_protein: 38`, per-source caps.
- `podcast.voice` / `podcast.rate`: Edge TTS voice and speed.
- `llm.model`: OpenRouter model for script generation.
- `llm.analysis_model`: OpenRouter model for article analysis.

## Cloudflare Worker (`visitor-message-worker/`)

Handles visitor form submissions and anonymous visit tracking for the GitHub Pages site.

```bash
cd visitor-message-worker
npm install
npm run dev      # Local dev
npm run deploy   # Deploy to Cloudflare
```

Endpoints: `POST /` (visitor message → Notion), `POST /visit` (visit tracking), `GET /visit-stats` (public count), `GET /stats?token=...` (owner stats).

## No Tests

There is no test suite. The primary way to validate changes:
- Run `python tools/check_feeds.py` after modifying RSS sources.
- Run `REGEN_FROM_CACHE=true python run_daily.py` to re-run the script/TTS/publish phases without re-fetching articles.
- GitHub Actions workflows serve as integration tests.
