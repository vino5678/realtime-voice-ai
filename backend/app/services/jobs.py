"""Conversion jobs. One worker thread keeps model access serialized and the event loop free."""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np

from ..audio.wav import AudioError, read_wav_file
from ..config import Settings
from ..errors import ApiError, ServiceError
from .engine_base import VoiceEngine
from .profiles import ProfileStore, is_valid_id

log = logging.getLogger("voicebridge.jobs")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Job:
    id: str
    profile_id: str
    source_seconds: float
    created_at: str
    status: str = "queued"  # queued | running | succeeded | failed
    started_at: str | None = None
    finished_at: str | None = None
    processing_seconds: float | None = None
    rtf: float | None = None
    output_seconds: float | None = None
    error: dict | None = None
    device: str | None = None
    engine: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "profile_id": self.profile_id,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "source_seconds": round(self.source_seconds, 3),
            "output_seconds": None if self.output_seconds is None else round(self.output_seconds, 3),
            "processing_seconds": None if self.processing_seconds is None else round(self.processing_seconds, 3),
            "rtf": None if self.rtf is None else round(self.rtf, 3),
            "device": self.device,
            "engine": self.engine,
            "error": self.error,
            "audio_url": f"/api/jobs/{self.id}/audio" if self.status == "succeeded" else None,
        }


def validate_output(path: Path, source_seconds: float) -> float:
    """Return the output duration, or raise ServiceError if the output is unusable."""
    if not path.is_file() or path.stat().st_size == 0:
        raise ServiceError("missing_output", "The model finished but produced no audio.")
    try:
        audio = read_wav_file(path)
        samples, sr = audio.samples, audio.sample_rate
    except AudioError:
        try:
            import soundfile as sf

            data, sr = sf.read(str(path), dtype="float32", always_2d=True)
            samples = data.mean(axis=1)
        except Exception:
            raise ServiceError("corrupt_output", "The converted audio could not be read back.")
    if len(samples) == 0 or not np.all(np.isfinite(samples)):
        raise ServiceError("corrupt_output", "The converted audio is empty or corrupted.")
    duration = len(samples) / sr
    if float(np.max(np.abs(samples))) < 10 ** (-60 / 20):
        raise ServiceError("silent_output", "The converted audio is silent.")
    ratio = duration / max(source_seconds, 1e-6)
    if not 0.7 <= ratio <= 1.3:
        raise ServiceError("unexpected_output_duration", f"The converted audio length ({duration:.1f} s) does not match the source ({source_seconds:.1f} s).")
    return duration


class JobManager:
    def __init__(self, settings: Settings, engine: VoiceEngine, profiles: ProfileStore):
        self._s, self._engine, self._profiles = settings, engine, profiles
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vc-worker")
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    # exclusive access to the model (also used by enrollment)
    def run_exclusive(self, fn: Callable, *args) -> Future:
        return self._executor.submit(fn, *args)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def cleanup_startup(self) -> None:
        for d in (self._s.tmp_dir, self._s.outputs_dir):
            if d.is_dir():
                for p in d.iterdir():
                    if p.is_file():
                        p.unlink(missing_ok=True)

    def sweep(self) -> None:
        ttl = self._s.output_ttl_minutes * 60
        now = time.time()
        if self._s.outputs_dir.is_dir():
            for p in self._s.outputs_dir.glob("*.wav"):
                if now - p.stat().st_mtime > ttl:
                    p.unlink(missing_ok=True)
                    with self._lock:
                        self._jobs.pop(p.stem, None)

    def submit(self, job_id: str, source_path: Path, source_seconds: float, profile_id: str) -> Job:
        self.sweep()
        with self._lock:
            active = sum(1 for j in self._jobs.values() if j.status in ("queued", "running"))
            if active >= self._s.max_queued_jobs:
                raise ApiError(429, "busy", "The converter is busy. Wait for a running conversion to finish and try again.")
            st = self._engine.status()
            job = Job(job_id, profile_id, source_seconds, _now(), device=st.device, engine=st.engine)
            self._jobs[job_id] = job
        self._executor.submit(self._run, job_id, source_path, self._profiles.artifact_path(profile_id))
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id) if is_valid_id(job_id) else None

    def output_path(self, job_id: str) -> Path | None:
        job = self.get(job_id)
        if not job or job.status != "succeeded":
            return None
        p = self._s.outputs_dir / f"{job_id}.wav"
        return p if p.is_file() else None

    def delete(self, job_id: str) -> bool:
        job = self.get(job_id)
        if not job or job.status in ("queued", "running"):
            return False
        (self._s.outputs_dir / f"{job_id}.wav").unlink(missing_ok=True)
        with self._lock:
            self._jobs.pop(job_id, None)
        return True

    def _run(self, job_id: str, source_path: Path, profile_path: Path) -> None:
        job = self._jobs[job_id]
        job.status, job.started_at = "running", _now()
        out = self._s.outputs_dir / f"{job_id}.wav"
        try:
            self._s.outputs_dir.mkdir(parents=True, exist_ok=True)
            t0 = time.perf_counter()
            self._engine.convert(source_path, profile_path, out)
            elapsed = time.perf_counter() - t0
            job.output_seconds = validate_output(out, job.source_seconds)
            job.processing_seconds = elapsed
            job.rtf = elapsed / max(job.source_seconds, 1e-6)
            job.status = "succeeded"
            log.info("convert_ok job=%s source_s=%.2f proc_s=%.2f rtf=%.2f device=%s", job_id, job.source_seconds, elapsed, job.rtf, job.device)
        except ServiceError as e:
            job.status, job.error = "failed", {"code": e.code, "message": e.message}
            out.unlink(missing_ok=True)
            log.warning("convert_failed job=%s code=%s", job_id, e.code)
        except Exception:
            log.exception("convert_unexpected job=%s", job_id)
            job.status = "failed"
            job.error = {"code": "internal_error", "message": "Conversion failed unexpectedly. Check the server log."}
            out.unlink(missing_ok=True)
        finally:
            job.finished_at = _now()
            source_path.unlink(missing_ok=True)
