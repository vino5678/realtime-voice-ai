"""Synthetic test signals. These exercise plumbing and quality checks, NOT AI voice quality."""
from __future__ import annotations

import io
import wave

import numpy as np


def speech_like(seconds: float, sr: int = 24000, speech_db: float = -20.0, noise_db: float = -70.0, clip: bool = False, seed: int = 1):
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * sr)) / sr
    on = (t % 0.37) < 0.25
    env = np.where(on, np.sin(np.pi * (t % 0.37) / 0.25), 0.0)
    tone = (np.sin(2 * np.pi * 140 * t) + 0.5 * np.sin(2 * np.pi * 280 * t) + 0.3 * np.sin(2 * np.pi * 420 * t)) / 1.2
    x = env * tone * 10 ** (speech_db / 20) * 1.6 + rng.uniform(-1, 1, len(t)) * 10 ** (noise_db / 20) * 1.7
    if clip:
        x = np.clip(x * 6, -1, 1)
    return x.astype(np.float32)


def wav_bytes(samples: np.ndarray, sr: int = 24000, width: int = 2, channels: int = 1) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(sr)
        x = np.clip(samples, -1, 1)
        if channels > 1:
            x = np.repeat(x[:, None], channels, axis=1).reshape(-1)
        if width == 2:
            w.writeframes(np.round(x * 32767).astype("<i2").tobytes())
        elif width == 4:
            w.writeframes(np.round(x * 2147483647).astype("<i4").tobytes())
        elif width == 3:
            v = np.round(x * 8388607).astype(np.int32)
            b = np.stack([v & 255, (v >> 8) & 255, (v >> 16) & 255], axis=1).astype(np.uint8)
            w.writeframes(b.tobytes())
        elif width == 1:
            w.writeframes((np.round(x * 127) + 128).astype(np.uint8).tobytes())
    return buf.getvalue()
