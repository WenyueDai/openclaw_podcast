from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List


def concat_mp3_ffmpeg(part_files: List[Path], out_mp3: Path) -> None:
    if not part_files:
        raise RuntimeError("No MP3 parts to merge")

    list_file = out_mp3.parent / "ffmpeg_concat_list.txt"
    lines = [f"file '{p.as_posix()}'" for p in part_files]
    list_file.write_text("\n".join(lines), encoding="utf-8")

    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-c",
        "copy",
        str(out_mp3),
    ]
    subprocess.run(cmd, check=True)
