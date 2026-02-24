import subprocess
from pathlib import Path
from typing import List


# 规则：>10MB 就切；每段目标 <=9.9MB
THRESHOLD_BYTES = int(10.0 * 1024 * 1024)
TARGET_BYTES = int(9.9 * 1024 * 1024)


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


def concat_mp3_ffmpeg(part_files: List[Path], out_mp3: Path) -> None:
    if not part_files:
        raise RuntimeError("No MP3 parts to merge")

    # 1) 先按你原来逻辑合并成 out_mp3
    list_file = out_mp3.parent / "ffmpeg_concat_list.txt"
    lines = [f"file '{p.as_posix()}'" for p in part_files]
    list_file.write_text("\n".join(lines), encoding="utf-8")

    cmd = [
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(out_mp3),
    ]
    subprocess.run(cmd, check=True)

    # 2) 如果最终 out_mp3 > 10MB，则切成 <=9.9MB 的多段
    if out_mp3.stat().st_size > THRESHOLD_BYTES:
        parts = _split_mp3_into_size_limited_parts(out_mp3, TARGET_BYTES)

        # 如果确实被切成多个 part，那么删除原始大文件
        # （保留策略：你也可以改成不删；但你说要“output into pieces”，通常代表替换）
        if len(parts) > 1:
            out_mp3.unlink(missing_ok=True)
