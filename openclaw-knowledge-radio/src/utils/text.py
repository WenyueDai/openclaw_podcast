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
