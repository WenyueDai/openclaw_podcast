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
- CRITICAL: You MUST cover EVERY item in the batch. Do NOT skip or merge any items.
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
    One LLM call per item, in ranked order.

    Each item gets its own segment separated by TRANSITION_MARKER so that:
    - segment index i = ranked item i  (item_segments[i] == i)
    - audio order matches website display order
    - clicking highlight [N] always plays item N's SFX + content

    Items with fulltext get a deep-dive treatment (~220-340 words).
    Items without fulltext get a concise roundup treatment (~80-130 words).
    """
    client = _client_from_config(cfg)
    model = cfg["llm"]["model"]
    temperature = float(cfg["llm"].get("temperature", 0.25))

    podcast_cfg = (cfg.get("podcast") or {})
    chunk_cfg = (podcast_cfg.get("chunking") or {})

    fulltext_threshold = int(chunk_cfg.get("fulltext_threshold_chars", 2500))
    deep_max_tokens = int(chunk_cfg.get("deep_dive_max_tokens", 2600))
    roundup_max_tokens = int(chunk_cfg.get("roundup_max_tokens", 2200))

    ranked = list(items)
    segments: List[str] = []

    for idx, it in enumerate(ranked, 1):
        block = _format_item_block(it)
        if _fulltext_ok(it, fulltext_threshold):
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
        else:
            user = (
                f"DATE: {date_str}\n"
                f"ITEM #{idx}\n\n"
                f"{block}\n\n"
                "Write a concise 80–130 word roundup for this single item. "
                "Lead with the key finding, mention the source, no sign-off."
            )
            seg = _chat_complete(
                client,
                model=model,
                system=SYSTEM_ROUNDUP,
                user=user,
                temperature=temperature,
                max_tokens=roundup_max_tokens,
            ).strip()
        segments.append(seg)

    return f"\n\n{TRANSITION_MARKER}\n\n".join(segments).strip()


def build_podcast_script_llm_chunked_with_map(
    *, date_str: str, items: List[Dict[str, Any]], cfg: Dict[str, Any]
) -> tuple:
    """
    Same as build_podcast_script_llm_chunked but also returns item_segments.
    Since items are generated in ranked order, item_segments[i] == i always.
    Returns (script_text, item_segments).
    """
    script = build_podcast_script_llm_chunked(date_str=date_str, items=items, cfg=cfg)
    item_segments: List[int] = list(range(len(items)))
    return script, item_segments


# =========================
# Deep synthesis prompt (11-section intelligence briefing)
# =========================

SYSTEM_SYNTHESIS = """You are an expert scientific podcast host creating a daily deep intelligence briefing for a computational protein designer.

Generate a complete spoken podcast script covering exactly 11 sections in order.
Separate each section with exactly: [[TRANSITION]]

CRITICAL PRODUCTION RULES:
- Plain text only. No markdown, no asterisks, no dashes at line starts, no numbered lists with dots.
- For any list, use spoken transitions: "First,", "Second,", "Third,", "Finally," and so on.
- Write to be heard, not read. Full paragraphs, natural spoken English throughout.
- When citing papers, say the title naturally in speech.
- Do NOT invent numbers, methods, results, or author intent beyond what is provided.
- If details are missing, say: "The available information does not tell us X."
- Replace ALL instances of "this week" with "today".
- Each section should take roughly 3 to 5 minutes to narrate.

SECTION 1: What actually mattered today — field-level insights
Identify the 5 to 8 most important scientific insights across today's papers.
For each insight explain: Old belief, meaning what people previously assumed. New insight, meaning what these papers suggest instead. Why this matters, meaning why this changes understanding rather than just adding detail. Evidence, meaning what experiments or analysis make this convincing. Supporting papers. Design implication, meaning what this changes for protein or antibody design practice.
Focus on insights that change how someone should THINK, not just what they should know.

[[TRANSITION]]

SECTION 2: If I were designing a project inspired by today's papers
Propose 3 to 5 realistic project ideas inspired by today's papers.
For each: Project idea. Core hypothesis. Minimal test, meaning the smallest experiment or computation to test this. What success looks like. What would kill the idea early. Risk level, either high, medium, or low. Why this is worth trying.
Focus on realistic research directions someone in computational protein design could attempt.

[[TRANSITION]]

SECTION 3: Knowledge expansion — connect to broader science
For the most important insights, explain connections to protein physics, evolution, thermodynamics, statistical mechanics, information theory, machine learning, and structural biology.
Also explain: what earlier work this resembles, whether this is rediscovering an old idea with better tools, and what general scientific principle this reflects.
This section should help build deep mental models rather than just knowledge.

[[TRANSITION]]

SECTION 4: Clever methods and how they proved things
Identify the most interesting experimental or computational methods from today's papers.
For each: what question they were answering, why the method was clever, why simpler methods would fail, what controls made it convincing, what weakness this avoids, and whether this logic could be reused in protein design evaluation or filtering.
Prioritise adversarial testing, model stress tests, orthogonal validation, screening innovations, dataset design, and causal inference tricks.

[[TRANSITION]]

SECTION 5: New design heuristics I should adopt
Extract practical design rules such as "if X happens consider Y", "avoid trusting Z when W occurs", "this metric works only as a negative filter", "this signal indicates model uncertainty".
For each heuristic explain: the rule, when it works, when it fails, warning signs, and how it applies in antibody or protein design.
Focus on improving scientific judgment rather than generic advice.

[[TRANSITION]]

SECTION 6: Where the field might be heading — trend detection
Based on today's papers identify emerging trends such as physics-aware machine learning, uncertainty estimation, hybrid compute-experiment loops, generative design evolution, dataset-driven biology, or negative design approaches.
For each trend explain: the signal suggesting it, whether it seems real or hype, what would confirm it, and what to watch over the next 2 to 3 years.

[[TRANSITION]]

SECTION 7: Tensions, contradictions, and skepticism
Identify papers that disagree, fragile assumptions, results depending on dataset bias, claims that seem overstated, and missing validation steps.
Explain what additional evidence would strengthen confidence.
This section should protect against hype-driven conclusions.

[[TRANSITION]]

SECTION 8: What a very strong protein designer would notice — expert pattern recognition
Identify insights that an experienced protein designer would likely notice that most readers would miss. For example: hidden assumptions behind model confidence, subtle failure modes, signals of dataset bias, overfitting disguised as generalization, physics violations hidden by machine learning predictions, where results depend on favorable test cases, where authors accidentally reveal useful design rules.
For each observation explain: what most readers would see, what an experienced designer would notice instead, why this matters in practice, how it could influence design decisions, and which papers it relates to.

[[TRANSITION]]

SECTION 9: History and philosophy of science perspective
For the major ideas explain: what type of progress this is, whether incremental engineering, conceptual shift, tool-driven discovery, data-driven discovery, or theory-driven discovery. What past scientific developments this resembles. Whether this changes how science is done or just what is known. Whether this reflects normal science optimization or a paradigm change.
Focus on understanding the trajectory of the field.

[[TRANSITION]]

SECTION 10: Today's mental model update — most important section
Speak through five things to update in how to think about protein or antibody design.
Then five concrete experiments, analyses, or workflow changes worth testing.
Then three things these papers suggest we should question.
Then share the most non-obvious insight from today.
End with the most elegant scientific idea from today's reading.

[[TRANSITION]]

SECTION 11: Personal research expansion notes
Generate additional thinking prompts covering: questions worth exploring, ideas worth testing later, possible improvements to computational workflows, metrics worth tracking, failure modes worth monitoring, and new datasets worth watching.
This section should help expand domain knowledge through open-ended prompts.

WRITING STYLE:
Do NOT summarize paper by paper unless necessary. Prioritise synthesis, comparison, reasoning, and design implications. Always cite supporting paper titles. Prefer insight over coverage. Explain WHY things work, not just WHAT works. Generalize insights into rules that remain useful even if the specific paper disappeared. Write clearly and deeply. Treat this as a daily intelligence report that helps a scientist become more insightful, not just more informed. Focus on generating understanding, judgment, and research direction.
"""


def build_podcast_script_llm_synthesis(
    *,
    date_str: str,
    items: List[Dict[str, Any]],
    cfg: Dict[str, Any],
    shared_landscape: Optional[List[Dict]] = None,
) -> Tuple[str, List[int]]:
    """
    Generate a deep 11-section synthesis podcast from the top featured papers.

    shared_landscape: optional list of {title, year, cited_by_count} dicts
      from Semantic Scholar — foundational papers cited by multiple featured
      papers today.  Injected as grounding context before the paper blocks.

    All featured items map to segment -1 (the synthesis weaves papers together
    across sections rather than speaking about each paper in turn).
    Returns (script_text, item_segments).
    """
    client = _client_from_config(cfg)
    model = cfg["llm"]["model"]
    temperature = float(cfg["llm"].get("temperature", 0.25))
    max_tokens = int(cfg["llm"].get("max_output_tokens", 8192))

    blocks: List[str] = []
    for i, it in enumerate(items, 1):
        blocks.append(f"=== PAPER {i} ===\n{_format_item_block(it)}")

    # Build shared landscape block if available
    landscape_block = ""
    if shared_landscape:
        lines = ["SHARED REFERENCE LANDSCAPE (foundational papers cited by multiple of today's featured papers):"]
        for entry in shared_landscape:
            title = entry.get("title") or "(unknown)"
            year  = entry.get("year") or ""
            count = entry.get("cited_by_count", 0)
            lines.append(f"  Cited by {count} papers: \"{title}\" ({year})")
        landscape_block = (
            "\n".join(lines)
            + "\nUse this landscape in Section 1 (insights), Section 3 (knowledge expansion), "
            + "Section 6 (trends), and Section 9 (history) to ground the synthesis in today's actual theoretical backdrop.\n\n"
        )

    user = (
        f"DATE: {date_str}\n\n"
        + landscape_block
        + f"TODAY'S FEATURED PAPERS ({len(items)} papers):\n\n"
        + "\n\n".join(blocks)
        + "\n\nGenerate the complete 11-section deep intelligence podcast script based on these papers."
        + "\nSeparate each section with [[TRANSITION]] on its own line."
        + "\nDo not invent details beyond what is provided above."
    )

    script = _chat_complete(
        client,
        model=model,
        system=SYSTEM_SYNTHESIS,
        user=user,
        temperature=temperature,
        max_tokens=max_tokens,
    ).strip()

    # Synthesis weaves all papers together — no per-paper audio segment mapping
    item_segments: List[int] = [-1] * len(items)
    return script, item_segments
