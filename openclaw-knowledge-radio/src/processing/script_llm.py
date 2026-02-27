import os, json, requests
import time
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI


# =========================
# Client (OpenRouter / OpenAI-compatible)
# =========================

def _client_from_config(cfg: Dict[str, Any]) -> OpenAI:
    api_key_env = cfg.get("llm", {}).get("api_key_env", "OPENROUTER_API_KEY")
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise RuntimeError(f"Missing env var {api_key_env} for OpenRouter API key")
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )


def _chat_complete(
    client: OpenAI,
    *,
    model: str,
    system: str,
    user: str,
    temperature: float,
    max_tokens: int,
    retries: int = 3,
) -> str:
    err: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            err = e
            if attempt < retries:
                time.sleep(1.5 * attempt)
            else:
                raise
    raise err  # pragma: no cover


# =========================
# Helpers
# =========================

def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _clip(s: str, n: int) -> str:
    s = (s or "").strip()
    if n <= 0 or len(s) <= n:
        return s
    return s[: max(0, n - 3)] + "..."


def _chunk(xs: List[Any], n: int) -> List[List[Any]]:
    if n <= 0:
        return [xs]
    return [xs[i : i + n] for i in range(0, len(xs), n)]


def _item_meta(it: Dict[str, Any]) -> Tuple[str, str, str, str, str, int, bool]:
    title = (it.get("title") or "").strip()
    url = (it.get("url") or "").strip()
    src = (it.get("source") or "").strip()
    bucket = (it.get("bucket") or "").strip()
    snippet = (it.get("one_liner") or it.get("snippet") or "").strip()
    extracted_chars = _safe_int(it.get("extracted_chars", 0), 0)
    has_fulltext = bool(it.get("has_fulltext", False))
    return title, url, src, bucket, snippet, extracted_chars, has_fulltext


def _fulltext_ok(it: Dict[str, Any], threshold_chars: int) -> bool:
    _, _, _, _, _, extracted_chars, has_fulltext = _item_meta(it)
    return has_fulltext or (extracted_chars >= threshold_chars)


def _analysis_text(it: Dict[str, Any]) -> str:
    """
    What we feed the LLM for understanding.
    Prefer per-article analysis if you have it; fallback to snippet.
    """
    a = it.get("analysis")
    if isinstance(a, str) and a.strip():
        return a.strip()
    # Some users store analysis as dict; be defensive
    if isinstance(a, dict):
        # keep it compact
        parts = []
        for k in ["core_claim", "method", "results", "why_it_matters", "limitations", "terms"]:
            v = a.get(k)
            if v:
                parts.append(f"{k.upper()}: {str(v)}")
        if parts:
            return "\n".join(parts).strip()
    # fallback
    return (it.get("one_liner") or it.get("snippet") or "").strip()


def _format_item_block(it: Dict[str, Any]) -> str:
    title, url, src, bucket, snippet, extracted_chars, has_fulltext = _item_meta(it)
    tags = it.get("tags") or []
    tags_str = ", ".join([str(t) for t in tags]) if isinstance(tags, list) else str(tags)

    lines: List[str] = []
    lines.append(f"TITLE: {title}")
    if src:
        lines.append(f"SOURCE: {src}")
    if bucket:
        lines.append(f"BUCKET: {bucket}")
    if tags_str:
        lines.append(f"TAGS: {tags_str}")
    if url:
        lines.append(f"URL: {url}")
    if snippet:
        lines.append(f"RSS_SNIPPET: {_clip(snippet, 420)}")
    lines.append(f"EXTRACTED_CHARS: {extracted_chars}")
    lines.append(f"HAS_FULLTEXT: {has_fulltext}")
    notes = _analysis_text(it)
    if notes:
        lines.append("NOTES_FROM_PIPELINE:")
        lines.append(_clip(notes, 4000))  # keep prompts bounded
    else:
        lines.append("NOTES_FROM_PIPELINE: (none)")
    return "\n".join(lines)


# =========================
# Prompts (ENGLISH ONLY)
# =========================

TRANSITION_MARKER = "[[TRANSITION]]"

SYSTEM_DEEP_DIVE = """You are an expert English podcast host for a long-form run-friendly science/tech show.
This segment MUST be based ONLY on the provided item block and notes.

Style goals:
- High information density, low fluff.
- Conversational and slightly playful, but technically accurate.
- Start directly with the core innovation. No greetings or catchphrases.

Hard rules:
- Do NOT invent methods/results/numbers.
- Do NOT spend long time on minor parameter details unless critical to novelty.
- Prioritize: what is new, why it matters, what changed vs prior work.
- Use only NOTES_FROM_PIPELINE and metadata.
- If details are missing, explicitly say: "The available text does not provide details on X."
- Mention source name naturally when making a claim.
- No markdown symbols, TTS-friendly plain text.
- No ending phrases after each paper segment.

Length requirement:
- About 220–340 words per deep dive.
"""

SYSTEM_ROUNDUP = """You are an English podcast host doing concise roundup segments.
Use ONLY the provided item blocks and notes.

Style:
- Crisp, lively, and accessible. Keep it punchy.

Rules:
- For EACH item: 80–130 words.
- Lead with the key takeaway and novelty.
- Avoid low-value parameter minutiae unless crucial.
- Be concrete but never invent details or numbers.
- Mention source name in each item.
- No greetings, no sign-off after each item.
- No markdown symbols, TTS-friendly plain text.
"""

SYSTEM_OPENING = """You are an English podcast host.
Write a SUPER SHORT opening (35–60 words) for today's episode.
Tone: warm, energetic, a tiny bit playful.
Do NOT invent facts.
"""

SYSTEM_CLOSING = """You are an English podcast host.
Write a SUPER SHORT closing (25–45 words) that recaps and signs off.
Tone: upbeat, concise.
Do NOT invent facts.
"""

# Optional merge via LLM (disabled by default). If enabled, it must not delete content.
SYSTEM_MERGE_NO_DELETE = """You are the editor-in-chief assembling a final podcast script.

CRITICAL RULES:
- You MUST NOT delete or summarize away any substantive information.
- You MAY ONLY:
  - add very short transitions (1–2 sentences) between segments
  - reorder segments if needed
  - fix obvious formatting issues (whitespace)
- The final length should be approximately the sum of all segments (no compression).

Output in English, TTS-friendly.
- Don't need the opening and closing for the podcast, go directly to the knowledge.
"""


# =========================
# Single-call version (kept for compatibility)
# =========================

def build_podcast_script_llm(*, date_str: str, items: List[Dict[str, Any]], cfg: Dict[str, Any]) -> str:
    """
    Kept for backwards compatibility (one call). Still English-only.
    """
    client = _client_from_config(cfg)
    model = cfg["llm"]["model"]
    temperature = float(cfg["llm"].get("temperature", 0.25))
    max_tokens = int(cfg["llm"].get("max_output_tokens", 5200))

    blocks = []
    for i, it in enumerate(items, 1):
        blocks.append(f"=== ITEM {i} ===\n{_format_item_block(it)}")

    user = (
        f"DATE: {date_str}\n\n"
        "Generate an English podcast script ONLY from the items below.\n"
        "Do not invent details.\n"
        "Keep it TTS-friendly.\n\n"
        + "\n\n".join(blocks)
    )

    # Use roundup prompt style for a single call
    return _chat_complete(
        client,
        model=model,
        system=SYSTEM_ROUNDUP,
        user=user,
        temperature=temperature,
        max_tokens=max_tokens,
    ).strip()


# =========================
# Chunked multi-call version (Deep dive only if fulltext)
# =========================

def build_podcast_script_llm_chunked(*, date_str: str, items: List[Dict[str, Any]], cfg: Dict[str, Any]) -> str:
    """
    Multi-call pipeline that increases detail.

    Policy:
    - Deep dive ONLY for items with full text signal:
        has_fulltext == True OR extracted_chars >= fulltext_threshold_chars
    - Mid-depth roundup for next items
    - Remaining items -> headlines only (no LLM)

    Final assembly defaults to deterministic concatenation (no compression).
    Optional merge LLM can be enabled, but is constrained to no-delete behavior.
   Remove the opening or closure, go directly to the knowledge.
    """
    client = _client_from_config(cfg)
    model = cfg["llm"]["model"]
    temperature = float(cfg["llm"].get("temperature", 0.25))
    max_tokens = int(cfg["llm"].get("max_output_tokens", 5200))

    # knobs
    podcast_cfg = (cfg.get("podcast") or {})
    chunk_cfg = (podcast_cfg.get("chunking") or {})

    fulltext_threshold = int(chunk_cfg.get("fulltext_threshold_chars", 2500))
    deep_dive_max = int(chunk_cfg.get("tierA_max", 3))          # deep dives count
    roundup_max = int(chunk_cfg.get("tierB_max", 15))           # roundup items count
    roundup_batch_size = int(chunk_cfg.get("tierB_batch_size", 5))

    deep_max_tokens = int(chunk_cfg.get("deep_dive_max_tokens", 2600))
    roundup_max_tokens = int(chunk_cfg.get("roundup_max_tokens", 2200))
    opening_max_tokens = int(chunk_cfg.get("opening_max_tokens", 140))
    closing_max_tokens = int(chunk_cfg.get("closing_max_tokens", 100))

    # merge behavior
    use_merge_llm = bool(chunk_cfg.get("use_merge_llm", False))
    merge_max_tokens = int(chunk_cfg.get("merge_max_tokens", max_tokens))

    ranked = list(items)  # already ranked upstream

    # ---- Select Deep Dive candidates: only fulltext-ok, in ranked order
    deep_items: List[Dict[str, Any]] = []
    rest: List[Dict[str, Any]] = []
    for it in ranked:
        if len(deep_items) < deep_dive_max and _fulltext_ok(it, fulltext_threshold):
            deep_items.append(it)
        else:
            rest.append(it)

    # ---- Roundup items: next roundup_max from rest
    roundup_items = rest[:roundup_max]
    headline_items = rest[roundup_max:]

    # ---- No opening: start directly with content
    opening = ""

    # ---- Deep dive segments (one call per item)
    deep_segments: List[str] = []
    for idx, it in enumerate(deep_items, 1):
        block = _format_item_block(it)
        user = (
            f"DATE: {date_str}\n"
            f"DEEP DIVE #{idx}\n\n"
            f"{block}\n\n"
            "Write a deep-dive segment that would take ~6–10 minutes to narrate.\n"
            "Be strict about what is known vs unknown.\n"
        )
        seg = _chat_complete(
            client,
            model=model,
            system=SYSTEM_DEEP_DIVE,
            user=user,
            temperature=temperature,
            max_tokens=deep_max_tokens,
        ).strip()
        deep_segments.append(seg)

    # ---- Roundup segments (batched)
    roundup_segments: List[str] = []
    for b_i, batch in enumerate(_chunk(roundup_items, roundup_batch_size), 1):
        blocks = []
        for j, it in enumerate(batch, 1):
            blocks.append(f"=== ITEM {j} ===\n{_format_item_block(it)}")
        user = (
            f"DATE: {date_str}\n"
            f"ROUNDUP BATCH #{b_i}\n\n"
            + "\n\n".join(blocks)
            + "\n\nWrite a mid-depth roundup for each item."
        )
        seg = _chat_complete(
            client,
            model=model,
            system=SYSTEM_ROUNDUP,
            user=user,
            temperature=temperature,
            max_tokens=roundup_max_tokens,
        ).strip()
        roundup_segments.append(seg)

    # ---- Headlines (no LLM)
    headlines_lines: List[str] = []
    if headline_items:
        headlines_lines.append("=== Quick Headlines ===")
        for it in headline_items:
            title, url, src, bucket, snippet, extracted_chars, has_fulltext = _item_meta(it)
            one = _clip(snippet, 180)
            if one:
                headlines_lines.append(f"- {title} ({src}) — {one}")
            else:
                headlines_lines.append(f"- {title} ({src})")
            if url:
                headlines_lines.append(f"  Source: {url}")
        headlines = "\n".join(headlines_lines).strip()
    else:
        headlines = ""

    # ---- No closing: keep flow dense and direct
    closing = ""

    # ---- Deterministic assembly (no compression)
    spoken_blocks: List[str] = []
    if opening:
        spoken_blocks.append(opening.strip())
    spoken_blocks.extend([s.strip() for s in deep_segments if s and s.strip()])
    spoken_blocks.extend([s.strip() for s in roundup_segments if s and s.strip()])
    if headlines and headlines.strip():
        spoken_blocks.append(headlines.strip())
    if closing:
        spoken_blocks.append(closing.strip())

    assembled = f"\n\n{TRANSITION_MARKER}\n\n".join(spoken_blocks).strip()

    # ---- Optional merge LLM: ONLY add transitions / formatting, no deletion
    if use_merge_llm:
        merge_user = (
            f"DATE: {date_str}\n"
            "You will receive a draft script. You must NOT delete content.\n"
            "Only add short transitions and fix whitespace.\n\n"
            "DRAFT:\n" + assembled
        )
        merged = _chat_complete(
            client,
            model=model,
            system=SYSTEM_MERGE_NO_DELETE,
            user=merge_user,
            temperature=temperature,
            max_tokens=merge_max_tokens,
        ).strip()
        return merged

    return assembled
