"""Bounded overlapping windows and crossfade reconstruction for offline evaluation."""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class AudioWindow:
    start_sample: int
    end_sample: int
    samples: np.ndarray


def iter_audio_windows(
    samples: np.ndarray,
    sample_rate: int,
    window_seconds: float,
    overlap_seconds: float,
) -> Iterator[AudioWindow]:
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if not np.isfinite(window_seconds) or window_seconds <= 0:
        raise ValueError("window_seconds must be finite and positive")
    if not np.isfinite(overlap_seconds) or overlap_seconds < 0 or overlap_seconds >= window_seconds:
        raise ValueError("overlap_seconds must be non-negative and shorter than the window")
    if samples.ndim != 1:
        raise ValueError("samples must be mono")

    window_size = max(1, round(window_seconds * sample_rate))
    overlap_size = round(overlap_seconds * sample_rate)
    stride = window_size - overlap_size
    for start in range(0, len(samples), stride):
        if overlap_size and len(samples) - start <= overlap_size:
            break
        end = min(start + window_size, len(samples))
        yield AudioWindow(start, end, samples[start:end])


def stitch_crossfaded(converted_windows: Iterable[np.ndarray], overlap_samples: int) -> np.ndarray:
    windows = [np.asarray(window, dtype=np.float32) for window in converted_windows]
    if not windows:
        return np.empty(0, dtype=np.float32)
    if any(window.ndim != 1 for window in windows):
        raise ValueError("converted windows must be mono")
    if overlap_samples < 0:
        raise ValueError("overlap_samples must be non-negative")
    output = windows[0].copy()
    for window in windows[1:]:
        if overlap_samples == 0:
            output = np.concatenate((output, window))
            continue
        if len(output) < overlap_samples or len(window) < overlap_samples:
            raise ValueError("each adjacent converted window must contain the full overlap")
        ramp = np.linspace(0.0, 1.0, overlap_samples, endpoint=True, dtype=np.float32)
        blend = output[-overlap_samples:] * (1.0 - ramp) + window[:overlap_samples] * ramp
        output = np.concatenate((output[:-overlap_samples], blend, window[overlap_samples:]))
    return output
