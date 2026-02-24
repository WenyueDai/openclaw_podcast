import hashlib
from pathlib import Path
from typing import Dict, Any
from openai import OpenAI

CACHE_DIR = Path("data/article_analysis")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

SYSTEM_PROMPT = """
You are a scientific analyst.

Given an article body, produce a structured analysis:

1. Core claim (2–3 sentences)
2. Method / approach
3. Why it matters
4. Technical terms explained simply
5. Limitations or uncertainties
6. Potential future implications

Be precise. Do not invent details.
Return plain text.
"""
import os
DEBUG_MODE = os.environ.get("DEBUG", "false").lower() == "true"

def hash_url(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:16]

def analyze_article(url: str, text: str, model: str = "openai/gpt-oss-120b") -> str:
    if not text.strip():
        return ""

    cache_file = CACHE_DIR / f"{hash_url(url)}.txt"

    # Cache check
    if not DEBUG_MODE and cache_file.exists():
        return cache_file.read_text()

    client = OpenAI(base_url="https://openrouter.ai/v1",api_key=os.environ['OPENROUTER_API_KEY']) 

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text[:6000]}  # limit context
        ],
        temperature=0.3,
        max_tokens=1200
    )

    analysis = response
    cache_file.write_text(analysis)
    return analysis
