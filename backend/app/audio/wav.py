"""Minimal, dependency-light WAV reading/writing (PCM only, via the stdlib)."""
from __future__ import annotations

import io
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np


class AudioError(Exception):
    def __init__(self, code: str, message: str, status: int = 422):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@dataclass(frozen=True)
class Audio:
    samples: np.ndarray  # mono float32 in [-1, 1]
    sample_rate: int

    @property
    def duration(self) -> float:
        return len(self.samples) / self.sample_rate


def looks_like_wav(data: bytes) -> bool:
    return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"


def read_wav_bytes(data: bytes, max_seconds: float | None = None) -> Audio:
    if not looks_like_wav(data):
        raise AudioError("unsupported_format", "Only PCM WAV audio is accepted by the server.", 415)
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            ch, width, rate, frames = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            if frames == 0:
                raise AudioError("empty_audio", "The audio contains no samples.")
            if not 8000 <= rate <= 96000:
                raise AudioError("unsupported_sample_rate", f"Sample rate {rate} Hz is not supported (8-96 kHz).")
            if ch < 1 or ch > 8:
                raise AudioError("unsupported_channels", "Unsupported channel count.")
            if max_seconds is not None and frames / rate > max_seconds:
                raise AudioError("audio_too_long", f"Audio is longer than the {max_seconds:.0f} second limit.", 413)
            raw = w.readframes(frames)
    except (wave.Error, EOFError):
        raise AudioError("unsupported_format", "The file is not a readable PCM WAV (floating-point WAV is not supported).", 415)

    if len(raw) < frames * width * ch:
        raise AudioError("corrupt_audio", "The audio file is truncated or corrupted.")

    if width == 2:
        x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 1:
        x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        v = np.where(v & 0x800000, v - 0x1000000, v)
        x = (v / 8388608.0).astype(np.float32)
    elif width == 4:
        x = (np.frombuffer(raw, dtype="<i4").astype(np.float64) / 2147483648.0).astype(np.float32)
    else:
        raise AudioError("unsupported_format", "Unsupported WAV bit depth.", 415)

    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1).astype(np.float32)
    return Audio(x, rate)


def read_wav_file(path: Path, max_seconds: float | None = None) -> Audio:
    return read_wav_bytes(Path(path).read_bytes(), max_seconds)


def remove_dc(samples: np.ndarray) -> np.ndarray:
    return (samples - float(np.mean(samples))).astype(np.float32) if len(samples) else samples


def write_wav(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    pcm = np.round(np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sample_rate))
        w.writeframes(pcm.tobytes())
