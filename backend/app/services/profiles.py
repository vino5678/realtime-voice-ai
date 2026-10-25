"""Local voice-profile storage. Only server-generated ids ever touch the filesystem."""
from __future__ import annotations

import json
import logging
import re
import shutil
import uuid
from pathlib import Path

log = logging.getLogger("voicebridge.profiles")
_ID_RE = re.compile(r"^[0-9a-f]{32}$")
ARTIFACT = "embedding.pt"
META = "meta.json"


def new_id() -> str:
    return uuid.uuid4().hex


def is_valid_id(value: str) -> bool:
    return bool(_ID_RE.fullmatch(value or ""))


class ProfileStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def _dir(self, pid: str) -> Path:
        if not is_valid_id(pid):
            raise ValueError("invalid profile id")
        return self.root / pid

    def exists(self, pid: str) -> bool:
        if not is_valid_id(pid):
            return False
        d = self.root / pid
        return (d / META).is_file() and (d / ARTIFACT).is_file()

    def artifact_path(self, pid: str) -> Path:
        return self._dir(pid) / ARTIFACT

    def make_dir(self, pid: str) -> Path:
        d = self._dir(pid)
        d.mkdir(parents=True, exist_ok=False)
        return d

    def save_meta(self, pid: str, meta: dict) -> None:
        (self._dir(pid) / META).write_text(json.dumps(meta, indent=2), encoding="utf-8")

    def discard(self, pid: str) -> None:
        if is_valid_id(pid):
            shutil.rmtree(self.root / pid, ignore_errors=True)

    def get(self, pid: str) -> dict | None:
        if not self.exists(pid):
            return None
        try:
            return json.loads((self._dir(pid) / META).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.warning("profile_meta_unreadable id=%s", pid)
            return None

    def list(self) -> list[dict]:
        if not self.root.is_dir():
            return []
        items = [m for p in self.root.iterdir() if p.is_dir() and (m := self.get(p.name))]
        return sorted(items, key=lambda m: m.get("created_at", ""), reverse=True)

    def delete(self, pid: str) -> bool:
        if not is_valid_id(pid) or not (self.root / pid).is_dir():
            return False
        shutil.rmtree(self.root / pid)
        return True
