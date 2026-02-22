from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Set


def _url_id(url: str) -> str:
    return hashlib.sha1(url.strip().encode("utf-8")).hexdigest()


class SeenStore:
    def __init__(self, path: Path):
        self.path = path
        self.ids: Set[str] = set()
        if path.exists():
            try:
                self.ids = set(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                self.ids = set()

    def has(self, url: str) -> bool:
        return _url_id(url) in self.ids

    def add(self, url: str) -> None:
        self.ids.add(_url_id(url))

    def save(self) -> None:
        self.path.write_text(json.dumps(sorted(self.ids)), encoding="utf-8")
