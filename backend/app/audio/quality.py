"""Heuristic recording-quality checks. Mirrors frontend/src/audio/analysis.ts.

These are screening heuristics, not guarantees about conversion quality.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np


@dataclass
class Finding:
    id: str
    severity: str  # good | warn | bad
    title: str
    detail: str


@dataclass
class QualityReport:
    duration_sec: float
    sample_rate: int
    peak_db: float
    speech_db: float
    noise_floor_db: float
    snr_db: float
    clipped_pct: float
    verdict: str
    findings: list[Finding]

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def _db(x):
    return 20.0 * np.log10(np.maximum(x, 1e-9))


def frame_levels_db(samples: np.ndarray, sr: int, frame_ms: int = 20) -> np.ndarray:
    n = max(1, int(round(sr * frame_ms / 1000)))
    k = len(samples) // n
    if k == 0:
        return np.array([])
    frames = samples[: k * n].reshape(k, n).astype(np.float64)
    return _db(np.sqrt((frames ** 2).mean(axis=1)))


def _pct(sorted_vals: np.ndarray, p: float) -> float:
    if len(sorted_vals) == 0:
        return -120.0
    i = min(len(sorted_vals) - 1, max(0, int(round(p * (len(sorted_vals) - 1)))))
    return float(sorted_vals[i])


def analyze(samples: np.ndarray, sr: int, include_duration: bool = True) -> QualityReport:
    n = len(samples)
    duration = n / sr if sr else 0.0
    peak = float(np.max(np.abs(samples))) if n else 0.0
    clipped_pct = float(np.mean(np.abs(samples) >= 0.999) * 100) if n else 0.0
    levels = np.sort(frame_levels_db(samples, sr))
    noise = _pct(levels, 0.1)
    speech = _pct(levels, 0.9)
    snr = speech - noise
    peak_db = float(_db(peak))

    f: list[Finding] = []

    def add(i, sev, title, detail):
        f.append(Finding(i, sev, title, detail))

    if include_duration:
        if duration < 2:
            add("duration", "bad", "Too short", "Record at least a few seconds of continuous speech.")
        elif duration < 5:
            add("duration", "warn", "Short recording", "Longer samples usually give the model more to work with.")
        else:
            add("duration", "good", "Length is fine", f"{duration:.1f} seconds.")

    if speech < -60:
        add("level", "bad", "No signal detected", "The audio is almost silent.")
    elif speech < -40:
        add("level", "bad", "Far too quiet", "Move closer to the microphone or raise its input level.")
    elif speech < -32:
        add("level", "warn", "Quiet", "Speak a little louder or move closer to the microphone.")
    elif speech > -6:
        add("level", "warn", "Very loud", "Move back from the microphone or lower its input level.")
    else:
        add("level", "good", "Level is good", "Speech level is in a healthy range.")

    if clipped_pct > 0.5 or (peak_db > -0.1 and clipped_pct > 0.1):
        add("clipping", "bad", "Clipping", "The signal hit the maximum level and is distorted.")
    elif clipped_pct > 0.05 or peak_db > -1:
        add("clipping", "warn", "Close to clipping", "Peaks are very near the maximum level.")
    else:
        add("clipping", "good", "No clipping", f"Peak level {peak_db:.1f} dBFS.")

    if speech >= -60:
        if noise > -40:
            add("noise", "bad", "Noisy", "Background noise is high. Use a quieter room.")
        elif noise > -50:
            add("noise", "warn", "Some background noise", "A quieter room would improve results.")
        else:
            add("noise", "good", "Quiet background", f"Noise floor about {noise:.0f} dBFS.")
        if snr < 15:
            add("snr", "bad", "Speech barely stands out", f"Estimated signal-to-noise ratio {snr:.0f} dB.")
        elif snr < 25:
            add("snr", "warn", "Moderate signal-to-noise ratio", f"Estimated {snr:.0f} dB; more than 25 dB is better.")
        else:
            add("snr", "good", "Clear speech", f"Estimated signal-to-noise ratio {snr:.0f} dB.")

    rank = {"good": 0, "warn": 1, "bad": 2}
    verdict = max((x.severity for x in f), key=lambda s: rank[s], default="good")
    return QualityReport(duration, sr, peak_db, speech, noise, snr, clipped_pct, verdict, f)


def split_segments(
    samples: np.ndarray, sr: int, target_sec: float = 10.0, min_sec: float = 3.0, window_sec: float = 1.5
) -> list[np.ndarray]:
    """Cut a long recording into ~target_sec pieces at quiet points, dropping near-silent pieces."""
    n = max(1, int(round(sr * 0.02)))
    levels = frame_levels_db(samples, sr)
    if len(levels) == 0:
        return []
    target = int(target_sec * 50)
    win = int(window_sec * 50)
    min_frames = int(min_sec * 50)
    cuts = [0]
    pos = 0
    while len(levels) - pos > target + min_frames:
        lo, hi = pos + target - win, min(len(levels) - 1, pos + target + win)
        pos = lo + int(np.argmin(levels[lo : hi + 1]))
        cuts.append(pos)
    cuts.append(len(levels))
    speech = _pct(np.sort(levels), 0.9)
    if speech < -50:  # essentially silent: nothing usable
        return []
    floor = max(speech - 25, -60)
    out: list[np.ndarray] = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        if b - a < min_frames:
            continue
        active = float(np.mean(levels[a:b] > floor))
        if active >= 0.3:
            out.append(samples[a * n : b * n])
    return out
