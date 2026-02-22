from __future__ import annotations

import os
from typing import Any, Dict, List

from openai import OpenAI


SYSTEM_PROMPT = """You are a rigorous but engaging computational biologist and now work on making a podcast as editor and host.
Goal: Generate a 60-minute english podcast script based ONLY on TODAY_ITEMS.
Requirements:
- Keep source URLs.
- Do not invent details.
- Structure:
  1) Opening
  2) Innovation & Protein Design
  3) Daily Knowledge obtained from wikipedia, include one reflective angle or unexpected connection to modern science and society, or link to other wikipedia knowledge.
  4) Deep Dive (2 major selected item)
  5) Closing recap + source list
- Plain text only (no JSON, no markdown tables).
- For any technical term that might not be obvious (e.g. latent space,entropy regularizaiton), briefly explain in clear sentence suitable for ordinary listener.
- provide more precise and comprehensive knowledge; 
- the output should be able to directly feed in TSS to generate audio, so avoid * or other symbol that is not direcctly recognizable.
"""


def _client_from_config(cfg: Dict[str, Any]) -> OpenAI:
    api_key_env = cfg.get("llm", {}).get("api_key_env", "OPENROUTER_API_KEY")
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise RuntimeError(f"Missing env var {api_key_env} for OpenRouter API key")

    # OpenRouter is OpenAI-compatible
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )


def build_podcast_script_llm(*, date_str: str, items: List[Dict[str, Any]], cfg: Dict[str, Any]) -> str:
    client = _client_from_config(cfg)
    model = cfg["llm"]["model"]
    temperature = float(cfg["llm"].get("temperature", 0.25))
    max_tokens = int(cfg["llm"].get("max_output_tokens", 5200))

    # Compact input to avoid huge prompts
    lines: List[str] = []
    lines.append(f"DATE: {date_str}")
    lines.append("TODAY_ITEMS (title/url/source/snippet only):")
    for i, it in enumerate(items, start=1):
        title = (it.get("title") or "").strip()
        url = (it.get("url") or "").strip()
        src = (it.get("source") or "").strip()
        bucket = (it.get("bucket") or "").strip()
        snippet = (it.get("one_liner") or "").strip()
        if len(snippet) > 420:
            snippet = snippet[:417] + "..."
        lines.append(f"{i}. [{bucket}] {title}")
        lines.append(f"   source: {src}")
        lines.append(f"   url: {url}")
        if snippet:
            lines.append(f"   snippet: {snippet}")

    user_prompt = (
        "Generate transcript only based on TODAY_ITEMS"
        "Don't make up information" + "\n".join(lines)
    )

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    out = resp.choices[0].message.content or ""
    return out.strip()
