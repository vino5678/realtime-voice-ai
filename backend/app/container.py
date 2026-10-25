from __future__ import annotations

from dataclasses import dataclass

from .config import Settings
from .services.engine_base import VoiceEngine
from .services.jobs import JobManager
from .services.profiles import ProfileStore


@dataclass
class Container:
    settings: Settings
    engine: VoiceEngine
    profiles: ProfileStore
    jobs: JobManager
