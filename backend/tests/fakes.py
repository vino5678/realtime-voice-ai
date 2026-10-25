"""A stand-in engine used ONLY by tests, to verify API/job plumbing and error handling.
A passing test that uses FakeEngine says nothing about real AI conversion."""
from __future__ import annotations

import shutil
from pathlib import Path

from app.errors import ServiceError
from app.services.engine_base import EngineStatus, VoiceEngine


class FakeEngine(VoiceEngine):
    id = "fake-test-engine"

    def __init__(self, state="ready", convert_fn=None, profile_error=None, convert_error=None):
        self.state = state
        self.convert_fn = convert_fn
        self.profile_error = profile_error
        self.convert_error = convert_error
        self.calls = {"create_profile": 0, "convert": 0}

    def status(self):
        return EngineStatus(self.state, self.id, "Fake engine (tests only)", "n/a", reason=None if self.state == "ready" else "not ready (test)", device="cpu")

    def start_loading(self):
        pass

    def create_profile(self, wav_paths, out_path: Path):
        self.calls["create_profile"] += 1
        if self.profile_error:
            raise self.profile_error
        out_path.write_bytes(b"FAKE-EMBEDDING")
        return {"clips": len(wav_paths)}

    def convert(self, source_wav: Path, profile_path: Path, out_wav: Path):
        self.calls["convert"] += 1
        if self.convert_error:
            raise self.convert_error
        if self.convert_fn:
            return self.convert_fn(source_wav, profile_path, out_wav)
        shutil.copy(source_wav, out_wav)
        return {}


__all__ = ["FakeEngine", "ServiceError"]
