"""Runtime settings, read from VB_* environment variables (all optional)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    model_dir: Path
    device: str = "auto"  # auto | cpu | cuda
    engine: str = "openvoice"
    max_upload_mb: float = 25.0
    max_source_seconds: float = 120.0
    min_source_seconds: float = 0.5
    quick_min_seconds: float = 3.0
    quick_max_seconds: float = 30.0
    hq_min_seconds: float = 20.0
    hq_max_seconds: float = 300.0
    output_ttl_minutes: float = 60.0
    max_queued_jobs: int = 4
    openvoice_tau: float = 0.3
    openvoice_watermark: bool = True
    allow_unsafe_checkpoint: bool = False

    @property
    def profiles_dir(self) -> Path:
        return self.data_dir / "profiles"

    @property
    def outputs_dir(self) -> Path:
        return self.data_dir / "outputs"

    @property
    def tmp_dir(self) -> Path:
        return self.data_dir / "tmp"

    @property
    def max_upload_bytes(self) -> int:
        return int(self.max_upload_mb * 1024 * 1024)

    def ensure_dirs(self) -> None:
        for d in (self.profiles_dir, self.outputs_dir, self.tmp_dir):
            d.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    return Settings(
        data_dir=Path(os.getenv("VB_DATA_DIR", REPO_ROOT / "storage")).resolve(),
        model_dir=Path(os.getenv("VB_MODEL_DIR", REPO_ROOT / "models")).resolve(),
        device=os.getenv("VB_DEVICE", "auto").strip().lower(),
        engine=os.getenv("VB_ENGINE", "openvoice").strip().lower(),
        max_upload_mb=_float("VB_MAX_UPLOAD_MB", 25.0),
        max_source_seconds=_float("VB_MAX_SOURCE_SECONDS", 120.0),
        output_ttl_minutes=_float("VB_OUTPUT_TTL_MINUTES", 60.0),
        max_queued_jobs=_int("VB_MAX_QUEUED_JOBS", 4),
        openvoice_tau=_float("VB_OPENVOICE_TAU", 0.3),
        openvoice_watermark=_bool("VB_OPENVOICE_WATERMARK", True),
        allow_unsafe_checkpoint=_bool("VB_ALLOW_UNSAFE_CHECKPOINT", False),
    )
