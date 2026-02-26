# tts_edge.py

import asyncio
import os
from pathlib import Path
from typing import List, Tuple

import edge_tts
from gtts import gTTS

from src.utils.text import chunk_text
from src.utils.io import ensure_dir

MAX_MB = 9.5
MAX_BYTES = int(MAX_MB * 1024 * 1024)

# 防止无限递归：文本太短就不再拆（极端情况下可能仍会略超，但通常不会发生）
MIN_SPLIT_CHARS = 400

# 用于找“更自然”的切分点（尽量不把句子切碎）
SPLIT_PUNCT = [
    "\n", "。", "！", "？", ".", "!", "?",
    "；", ";", "，", ",", ":", "：",
]


def _voice_candidates(primary: str) -> List[str]:
    # fallback voices for temporary Edge endpoint/voice 403 issues
    common = [
        "en-US-GuyNeural",
        "en-US-AriaNeural",
        "en-GB-RyanNeural",
        "en-GB-SoniaNeural",
    ]
    out = [primary] + [v for v in common if v != primary]
    return out


async def _save_one(text: str, voice: str, rate: str, out_path: Path) -> None:
    last_err = None
    for v in _voice_candidates(voice):
        for attempt in range(1, 4):
            try:
                communicate = edge_tts.Communicate(text, v, rate=rate)
                await communicate.save(str(out_path))
                return
            except Exception as e:
                last_err = e
                await asyncio.sleep(0.8 * attempt)

    # Fallback: gTTS to keep pipeline alive if Edge endpoint rejects requests.
    try:
        tts = gTTS(text=text, lang="en", slow=False)
        tts.save(str(out_path))
        return
    except Exception:
        pass

    raise last_err


def _pick_split_point(text: str) -> int:
    """
    在文本中间附近找一个比较自然的切分点。
    找不到就硬切一半。
    """
    n = len(text)
    mid = n // 2
    if n < 2:
        return 1

    window = min(600, n // 3)  # 搜索窗口，够用且不太慢
    left = max(1, mid - window)
    right = min(n - 1, mid + window)

    # 优先找靠近 mid 的标点
    best_idx = None
    best_dist = None

    for i in range(left, right):
        if text[i] in SPLIT_PUNCT:
            dist = abs(i - mid)
            if best_idx is None or dist < best_dist:
                best_idx = i
                best_dist = dist

    if best_idx is None:
        return mid

    # 切在标点之后更自然
    return min(best_idx + 1, n - 1)


def _split_text_in_two(text: str) -> Tuple[str, str]:
    cut = _pick_split_point(text)
    a = text[:cut].strip()
    b = text[cut:].strip()

    # 兜底：如果某一半为空，就硬切
    if not a or not b:
        mid = len(text) // 2
        a = text[:mid].strip()
        b = text[mid:].strip()

    return a, b


def tts_text_to_mp3_chunked(
    text: str,
    out_dir: Path,
    voice: str,
    chunk_chars: int,
    rate: str = "+20%",
) -> List[Path]:
    """
    保持原函数签名与返回格式不变：
    - 输入：text, out_dir, voice, chunk_chars
    - 输出：List[Path]，文件名 part_001.mp3, part_002.mp3...
    额外能力：
    - 若某段生成的 mp3 > 9.5MB，会自动递归拆分文本，直到每个 mp3 <= 9.5MB
    """
    ensure_dir(out_dir)

    part_files: List[Path] = []
    counter = 0

    def next_path() -> Path:
        nonlocal counter
        counter += 1
        return out_dir / f"part_{counter:03d}.mp3"

    def generate_with_size_limit(one_text: str) -> None:
        """
        递归生成：如果超过大小限制，就删文件、分裂文本、继续生成。
        """
        out_path = next_path()
        asyncio.run(_save_one(one_text, voice, rate, out_path))

        try:
            size = os.path.getsize(out_path)
        except OSError:
            # 如果生成失败/文件不存在，直接不加入列表
            return

        if size <= MAX_BYTES:
            part_files.append(out_path)
            return

        # 太大：如果文本已经很短了，避免死循环——先保留（或你也可选择 raise）
        if len(one_text) < MIN_SPLIT_CHARS:
            part_files.append(out_path)
            return

        # 删掉超限文件，拆文本再来
        try:
            os.remove(out_path)
        except OSError:
            pass
        # 注意：我们“占用了”一个 part 编号，但文件删了
        # 这会导致编号有空洞吗？不会，因为我们删的是刚生成的那个编号；
        # 但 counter 已经前进了。为避免空洞，我们可以把 counter 回退 1。
        # 这里回退可确保最终文件编号连续。
        nonlocal_counter_back()

        a, b = _split_text_in_two(one_text)
        generate_with_size_limit(a)
        generate_with_size_limit(b)

    def nonlocal_counter_back() -> None:
        nonlocal counter
        counter -= 1

    # 初次按 chunk_chars 切
    chunks = chunk_text(text, max_chars=chunk_chars)

    # 逐块生成（每块如果超限会自己继续拆）
    for ch in chunks:
        ch = ch.strip()
        if not ch:
            continue
        generate_with_size_limit(ch)

    return part_files
