# OpenClaw Knowledge Radio

A daily automated podcast for protein designers. Every morning, it collects the latest papers and news in protein design, antibody engineering, and computational biology — ranks them by relevance, generates a podcast script with an LLM, converts it to speech, and publishes everything to GitHub Pages and Notion.

**Live site:** [wenyuedai.github.io/openclaw_podcast](https://wenyuedai.github.io/openclaw_podcast)

---

## What it does each day

1. **Collects** from ~25 RSS feeds (Nature, arXiv, PNAS, Quanta) + PubMed keyword search + daily knowledge
2. **Filters** — removes duplicate URLs seen in previous days, excludes animal/cell-biology topics
3. **Analyzes** each article with a fast LLM to extract core claim, novelty, and relevance
4. **Ranks** by: user feedback → key author feeds → topic keywords → journal quality → fulltext availability
5. **Generates** a ~60-minute podcast script with a frontier LLM (OpenRouter)
6. **Synthesizes** speech via Microsoft Edge TTS (or Kokoro for higher quality locally)
7. **Publishes** the MP3 to a GitHub Release, rebuilds the GitHub Pages site, saves a digest to Notion
8. **Reports** to Slack with top picks, any errors, and an LLM-generated run analysis

---

## Feedback loop

On the GitHub Pages site, each paper has a checkbox. Check the ones you find interesting and click **Save feedback to GitHub**. The next day's run will:
- Boost papers from sources you liked
- Boost papers whose titles match keywords you've shown interest in
- Add up to 5 new PubMed search terms extracted from titles of papers you liked

---

## Repository layout

```
openclaw-knowledge-radio/       ← Python pipeline
├── run_daily.py                ← main entry point
├── config.yaml                 ← all settings (sources, limits, LLM, TTS)
├── requirements.txt
├── src/
│   ├── collectors/             ← RSS, PubMed, daily-knowledge fetchers
│   ├── processing/             ← ranking, article analysis, LLM script builder
│   └── outputs/                ← TTS, GitHub publish, Notion, Slack
├── tools/
│   └── build_site.py          ← generates docs/ (GitHub Pages site)
├── state/                      ← persistent state (seen URLs, release index, feedback)
└── output/                     ← per-day episode items + status (last 30 days)

docs/                           ← GitHub Pages site (auto-generated)
.github/workflows/
└── daily_podcast.yml           ← GitHub Actions cron job (runs at 05:00 UTC daily)
```

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/WenyueDai/openclaw_podcast.git
cd openclaw_podcast/openclaw-knowledge-radio
pip install -r requirements.txt
sudo apt install ffmpeg   # or brew install ffmpeg on macOS
```

### 2. Environment variables

Create `openclaw-knowledge-radio/.env`:

```env
OPENROUTER_API_KEY=sk-or-v1-...
GITHUB_TOKEN=ghp_...
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
NOTION_TOKEN=ntn_...
NOTION_DATABASE_ID=...
```

### 3. Run manually

```bash
cd openclaw-knowledge-radio
python run_daily.py
```

Optional flags:
```bash
DEBUG=true python run_daily.py          # skip seen-URL dedup (re-fetches everything)
REGEN_FROM_CACHE=true python run_daily.py   # reuse today's cached items.jsonl
RUN_DATE=2026-02-20 python run_daily.py     # generate for a specific date
LOOKBACK_HOURS=72 python run_daily.py       # look back further for papers
```

---

## GitHub Actions (automatic daily run)

The workflow at `.github/workflows/daily_podcast.yml` runs at **05:00 UTC every day** on GitHub's servers. No computer needs to be on.

Required repository secrets (Settings → Secrets → Actions):

| Secret | Description |
|--------|-------------|
| `GH_PAT` | GitHub PAT with `repo` + `workflow` scopes |
| `OPENROUTER_API_KEY` | OpenRouter API key |
| `SLACK_WEBHOOK_URL` | Slack Incoming Webhook URL |
| `NOTION_TOKEN` | Notion integration token (`ntn_...`) |
| `NOTION_DATABASE_ID` | Notion database ID |

To trigger manually: go to **Actions → Daily Podcast → Run workflow**.

---

## Configuration

All settings are in `config.yaml`:

- **RSS sources** — add/remove feeds, set bucket (`protein` / `journal` / `ai_bio` / `news`)
- **PubMed** — keyword search terms, lookback days, results per term
- **Limits** — max items total, per-bucket quotas, per-source news caps
- **Ranking** — absolute author priority, journal quality rules, topic boost keywords
- **Podcast** — TTS voice, speed, chunk size, target duration
- **LLM** — model for analysis vs. script generation (uses OpenRouter)

### Using Kokoro TTS (higher quality, offline)

```bash
# Start the Kokoro server (once)
docker run -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest

# Run with Kokoro as primary TTS
PREFER_KOKORO=true python run_daily.py
```

---

## Key sources covered

- **arXiv** — q-bio.BM, q-bio.QM, cs.LG, stat.ML
- **Nature family** — Nature, Nature Biotechnology, Nature Chemical Biology, Nature Structural & Molecular Biology, Nature Methods
- **Top journals** — PNAS, Protein Science, Protein Engineering Design & Selection
- **Key researchers** — David Baker, Sergey Ovchinnikov, Alexander Rives, Brian Hie, Charlotte Deane, Jeffrey Gray, Tanja Kortemme, Po-Ssu Huang, and more
- **PubMed** — 16 search terms covering protein/antibody/enzyme design + dynamic terms from your feedback
- **News** — Nature News, Quanta Magazine, Scientific American (capped at 1–3 per source)
