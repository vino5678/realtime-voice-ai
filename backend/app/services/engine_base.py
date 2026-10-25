"""Engine interface. Model-specific code lives in subclasses, never in route handlers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class EngineStatus:
    state: str  # unavailable | loading | ready | error
    engine: str
    display_name: str
    license: str
    reason: str | None = None
    device: str | None = None
    sample_rate: int | None = None
    weights_hint: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class VoiceEngine(ABC):
    id: str = "base"

    @abstractmethod
    def status(self) -> EngineStatus: ...

    def refresh(self) -> None:
        """Optional hook, called when status is polled (e.g. retry after weights appear)."""
        return None

    @abstractmethod
    def start_loading(self) -> None:
        """Begin loading the model without blocking the caller."""

    @abstractmethod
    def create_profile(self, wav_paths: list[Path], out_path: Path) -> dict:
        """Run the model's real speaker-representation extraction and write it to out_path."""

    @abstractmethod
    def convert(self, source_wav: Path, profile_path: Path, out_wav: Path) -> dict:
        """Run real voice conversion and write the result to out_wav."""
