from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List

import edge_tts

from src.utils.text import chunk_text
from src.utils.io import ensure_dir


async def _save_one(text: str, voice: str, out_path: Path) -> None:
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(out_path))


def tts_text_to_mp3_chunked(*, text: str, out_dir: Path, voice: str, chunk_chars: int) -> List[Path]:
    ensure_dir(out_dir)
    chunks = chunk_text(text, max_chars=chunk_chars)
    part_files: List[Path] = []
    for idx, chunk in enumerate(chunks, start=1):
        out_path = out_dir / f"part_{idx:03d}.mp3"
        asyncio.run(_save_one(chunk, voice, out_path))
        part_files.append(out_path)
    return part_files
