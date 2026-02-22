from __future__ import annotations

import re
from typing import List

_sentence_end = re.compile(r"([.!?。！？])")


def chunk_text(text: str, max_chars: int) -> List[str]:
    text = text.strip()
    if not text:
        return []
    chunks: List[str] = []
    buf = ""

    for line in text.splitlines():
        add = line.strip()
        if not add:
            add = ""
        # keep paragraph breaks, but don't waste chunk budget
        candidate = (buf + "\n" + add).strip() if buf else add
        if len(candidate) <= max_chars:
            buf = candidate
        else:
            chunks.extend(_split_buf(buf, max_chars))
            buf = add

    if buf.strip():
        chunks.extend(_split_buf(buf, max_chars))

    return [c.strip() for c in chunks if c.strip()]


def _split_buf(buf: str, max_chars: int) -> List[str]:
    buf = (buf or "").strip()
    if not buf:
        return []
    if len(buf) <= max_chars:
        return [buf]

    parts = []
    cur = ""
    for token in _sentence_end.split(buf):
        if not token:
            continue
        if len(cur) + len(token) <= max_chars:
            cur += token
        else:
            if cur.strip():
                parts.append(cur.strip())
            cur = token
    if cur.strip():
        parts.append(cur.strip())

    out: List[str] = []
    for p in parts:
        if len(p) <= max_chars:
            out.append(p)
        else:
            for i in range(0, len(p), max_chars):
                out.append(p[i:i+max_chars])
    return out

import re

_URL_RE = re.compile(r"https?://\S+")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\)]+)\)")

def clean_for_tts(text: str) -> str:
    """
    Make a TTS-friendly version:
    - remove raw URLs
    - convert markdown links [title](url) -> title
    - remove "来源清单" section if present (optional but recommended)
    """
    if not text:
        return ""

    # [title](url) -> title
    text = _MD_LINK_RE.sub(r"\1", text)

    # remove raw urls
    text = _URL_RE.sub("", text)

    # OPTIONAL: drop trailing sources section if you keep one
    # adjust these keywords to your script style
    cut_keywords = ["来源清单", "Sources list", "Sources:", "References:"]
    for kw in cut_keywords:
        idx = text.find(kw)
        if idx != -1:
            text = text[:idx].rstrip()
            break

    # cleanup excessive spaces / blank lines
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
