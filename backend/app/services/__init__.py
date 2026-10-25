from ..config import Settings
from .engine_base import VoiceEngine


def create_engine(settings: Settings) -> VoiceEngine:
    if settings.engine == "openvoice":
        from .openvoice_engine import OpenVoiceEngine

        return OpenVoiceEngine(settings)
    raise ValueError(f"Unknown VB_ENGINE '{settings.engine}'. Supported: openvoice")
