"""Benchmark full-file OpenVoice inference on overlapping audio windows.

This is an offline measurement utility, not a streaming server or a quality test.
Use only consented source audio and an enrolled profile whose consent is recorded.
"""
from __future__ import annotations

import argparse
import math
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.audio.wav import read_wav_file, remove_dc, write_wav  # noqa: E402
from app.audio.windows import iter_audio_windows, stitch_crossfaded  # noqa: E402
from app.config import load_settings  # noqa: E402
from app.services.jobs import validate_output  # noqa: E402
from app.services.openvoice_engine import OpenVoiceEngine  # noqa: E402
from app.services.profiles import ProfileStore, is_valid_id  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="consented PCM WAV source speech")
    parser.add_argument("--voice-id", required=True, help="ID of an existing enrolled voice profile")
    parser.add_argument("--window-seconds", type=float, default=5.0)
    parser.add_argument("--overlap-seconds", type=float, default=1.0)
    parser.add_argument("--output", type=Path, help="optional path for the crossfaded WAV output")
    args = parser.parse_args()

    settings = load_settings()
    profiles = ProfileStore(settings.profiles_dir)
    if not is_valid_id(args.voice_id) or not profiles.exists(args.voice_id):
        parser.error("voice-id must identify an existing enrolled profile")
    metadata = profiles.get(args.voice_id)
    if not metadata or not metadata.get("consent", {}).get("confirmed"):
        parser.error("the selected profile has no recorded consent confirmation")
    if not args.source.is_file():
        parser.error(f"source WAV does not exist: {args.source}")
    if (
        not math.isfinite(args.window_seconds)
        or args.window_seconds <= 0
        or not math.isfinite(args.overlap_seconds)
        or not 0 <= args.overlap_seconds < args.window_seconds
    ):
        parser.error("window-seconds must be positive; overlap-seconds must be non-negative and shorter")

    source = read_wav_file(args.source, settings.max_source_seconds)
    source_samples = remove_dc(source.samples)
    engine = OpenVoiceEngine(settings)
    load_started = time.perf_counter()
    engine.start_loading()
    while engine.status().state == "loading" and time.perf_counter() - load_started < 600:
        time.sleep(0.1)
    load_seconds = time.perf_counter() - load_started
    status = engine.status()
    if status.state != "ready":
        print(f"Model unavailable: {status.state}: {status.reason}", file=sys.stderr)
        return 2

    windows = list(iter_audio_windows(source_samples, source.sample_rate, args.window_seconds, args.overlap_seconds))
    if len(windows) < 2:
        print("Use a source at least one window plus one stride long to measure repeated windows.", file=sys.stderr)
        return 2

    inference_seconds: list[float] = []
    cpu_seconds: list[float] = []
    converted: list = []
    overlap_model_samples = round(args.overlap_seconds * (status.sample_rate or source.sample_rate))
    profile_path = profiles.artifact_path(args.voice_id)
    with tempfile.TemporaryDirectory(prefix="vb-openvoice-bench-") as temp_dir:
        temp = Path(temp_dir)
        output_boundaries: list[int] = []
        stitched_samples = 0
        for index, window in enumerate(windows):
            input_path = temp / f"input_{index:04d}.wav"
            output_path = temp / f"output_{index:04d}.wav"
            write_wav(input_path, window.samples, source.sample_rate)
            cpu_before = os.times()
            if status.device and status.device.startswith("cuda"):
                engine._torch.cuda.synchronize()
            started = time.perf_counter()
            engine.convert(input_path, profile_path, output_path)
            if status.device and status.device.startswith("cuda"):
                engine._torch.cuda.synchronize()
            elapsed = time.perf_counter() - started
            cpu_after = os.times()
            output_duration = validate_output(output_path, len(window.samples) / source.sample_rate)
            audio = read_wav_file(output_path)
            converted.append(audio.samples)
            if index:
                output_boundaries.append(stitched_samples)
                stitched_samples += len(audio.samples) - overlap_model_samples
            else:
                stitched_samples = len(audio.samples)
            inference_seconds.append(elapsed)
            cpu_seconds.append((cpu_after.user - cpu_before.user) + (cpu_after.system - cpu_before.system))
            print(
                f"window={index + 1}/{len(windows)} source={len(window.samples) / source.sample_rate:.3f}s "
                f"inference={elapsed:.3f}s output={output_duration:.3f}s "
                f"rtf={elapsed / (len(window.samples) / source.sample_rate):.3f} "
                f"cpu_cores={cpu_seconds[-1] / max(elapsed, 1e-9):.2f}"
            )

        reconstructed = stitch_crossfaded(converted, overlap_model_samples)
        output_rate = status.sample_rate or source.sample_rate
        reconstructed_seconds = len(reconstructed) / output_rate
        boundary_steps = [
            abs(float(reconstructed[boundary] - reconstructed[boundary - 1]))
            for boundary in output_boundaries
            if 0 < boundary < len(reconstructed)
        ]
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            write_wav(args.output, reconstructed, output_rate)

    stride_seconds = args.window_seconds - args.overlap_seconds
    max_inference = max(inference_seconds)
    print(f"model={status.display_name} device={status.device} sample_rate={status.sample_rate} load={load_seconds:.2f}s")
    print(
        f"source={source.duration:.3f}s windows={len(windows)} window={args.window_seconds:.3f}s "
        f"overlap={args.overlap_seconds:.3f}s stride={stride_seconds:.3f}s"
    )
    print(
        f"inference_median={statistics.median(inference_seconds):.3f}s "
        f"inference_max={max_inference:.3f}s total_inference={sum(inference_seconds):.3f}s "
        f"effective_rtf={sum(inference_seconds) / source.duration:.3f}"
    )
    print(
        f"first_output_latency_lower_bound={args.window_seconds + inference_seconds[0]:.3f}s "
        f"max_window_exceeds_stride={max_inference > stride_seconds} "
        f"stitched_output={reconstructed_seconds:.3f}s "
        f"max_boundary_sample_step={max(boundary_steps, default=0.0):.6f}"
    )
    print(
        f"host_logical_cpus={os.cpu_count()} "
        f"avg_process_cpu_cores={statistics.mean(cpu / elapsed for cpu, elapsed in zip(cpu_seconds, inference_seconds)):.2f}"
    )
    if args.output:
        print(f"output={args.output.resolve()} (listen manually; intelligibility and similarity are not scored)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
