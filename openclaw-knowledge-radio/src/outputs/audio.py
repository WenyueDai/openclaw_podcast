import subprocess
from pathlib import Path
from typing import List


# 规则：>10MB 就切；每段目标 <=9.9MB
THRESHOLD_BYTES = int(10.0 * 1024 * 1024)
TARGET_BYTES = int(9.9 * 1024 * 1024)


def _build_transition_sfx(out_dir: Path) -> Path:
    """Generate a short news-like transition cue if missing."""
    sfx = out_dir / "transition_sfx.mp3"
    # Rebuild every run so transition timing updates apply immediately.
    if sfx.exists():
        sfx.unlink(missing_ok=True)

    # 1.0s silence -> short cue -> 1.0s silence
    # So transitions feel like: pause, cue, pause, next news.
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono:d=1.0",
        "-f", "lavfi", "-i", "sine=frequency=1046:duration=0.12",
        "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono:d=0.06",
        "-f", "lavfi", "-i", "sine=frequency=1318:duration=0.12",
        "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono:d=1.0",
        "-filter_complex", "[0:a][1:a][2:a][3:a][4:a]concat=n=5:v=0:a=1[a]",
        "-map", "[a]",
        "-ar", "24000",
        "-ac", "1",
        "-codec:a", "libmp3lame",
        "-q:a", "4",
        str(sfx),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return sfx


def _ffprobe_duration_seconds(mp3_path: Path) -> float:
    # ffprobe 输出时长（秒）
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(mp3_path),
    ]
    out = subprocess.check_output(cmd).decode().strip()
    return float(out)


def _split_mp3_into_size_limited_parts(mp3_path: Path, target_bytes: int) -> List[Path]:
    """
    用 ffmpeg 按“估算时长”切分，尽量保证每段 <= target_bytes。
    生成文件名：<stem>_p001.mp3, <stem>_p002.mp3, ...
    """
    size = mp3_path.stat().st_size
    if size <= target_bytes:
        return [mp3_path]

    duration = _ffprobe_duration_seconds(mp3_path)
    if duration <= 0:
        return [mp3_path]

    # 估算每段时长：target_bytes / total_bytes * total_duration
    # 再乘一个安全系数，避免 VBR/头部开销导致略超
    safety = 0.97
    seg_dur = max(1.0, duration * (target_bytes / size) * safety)

    out_files: List[Path] = []
    part_idx = 1
    t = 0.0

    while t < duration - 0.01:
        out_part = mp3_path.with_name(f"{mp3_path.stem}_p{part_idx:03d}.mp3")

        # 先尝试按 seg_dur 切
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{t}",
            "-i", str(mp3_path),
            "-t", f"{seg_dur}",
            "-c", "copy",
            str(out_part),
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # 如果这一段仍然 > target_bytes，就缩短一点重切（最多重试 8 次）
        # 这样可以处理 VBR 或某些段密度较高导致偏大的情况
        tries = 0
        cur_dur = seg_dur
        while out_part.exists() and out_part.stat().st_size > target_bytes and tries < 8:
            out_part.unlink(missing_ok=True)
            cur_dur *= 0.92  # 每次缩短 8%
            cmd = [
                "ffmpeg", "-y",
                "-ss", f"{t}",
                "-i", str(mp3_path),
                "-t", f"{cur_dur}",
                "-c", "copy",
                str(out_part),
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            tries += 1

        out_files.append(out_part)
        t += cur_dur
        part_idx += 1

    return out_files


def _concat_sequence(seq: List[Path], out_mp3: Path) -> None:
    list_file = out_mp3.parent / "ffmpeg_concat_list.txt"
    lines = [f"file '{p.as_posix()}'" for p in seq]
    list_file.write_text("\n".join(lines), encoding="utf-8")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-codec:a", "libmp3lame", "-q:a", "4",
        str(out_mp3),
    ]
    subprocess.run(cmd, check=True)


def concat_mp3_ffmpeg(part_files: List[Path], out_mp3: Path) -> None:
    if not part_files:
        raise RuntimeError("No MP3 parts to merge")

    # Plain concat (no transitions) for backward compatibility.
    _concat_sequence(part_files, out_mp3)

    # If final >10MB, also generate chunk files for Telegram delivery limits.
    if out_mp3.stat().st_size > THRESHOLD_BYTES:
        _split_mp3_into_size_limited_parts(out_mp3, TARGET_BYTES)


def concat_mp3_with_transitions(groups: List[List[Path]], out_mp3: Path) -> None:
    """
    Concat TTS audio with transition SFX BETWEEN logical groups (paper/news),
    not between every internal TTS chunk.
    """
    non_empty = [g for g in groups if g]
    if not non_empty:
        raise RuntimeError("No MP3 groups to merge")

    sfx = _build_transition_sfx(out_mp3.parent)
    seq: List[Path] = []
    for i, grp in enumerate(non_empty):
        seq.extend(grp)
        if i < len(non_empty) - 1:
            seq.append(sfx)

    _concat_sequence(seq, out_mp3)

    if out_mp3.stat().st_size > THRESHOLD_BYTES:
        _split_mp3_into_size_limited_parts(out_mp3, TARGET_BYTES)
