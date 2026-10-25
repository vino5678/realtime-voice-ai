"""REAL OpenVoice inference test. Skipped unless everything needed is present.

Needs: torch + openvoice installed, weights in models\\openvoice_v2\\converter, and two CONSENTED
recordings you provide:
    $env:VB_REAL_REF_WAV = "C:\\path\\to\\my_voice.wav"     # target voice (owner/permitted)
    $env:VB_REAL_SRC_WAV = "C:\\path\\to\\source_speech.wav"
Run:  python -m pytest tests\\test_openvoice_real.py -s
Passing means the model ran and produced a readable, non-silent file of plausible length.
It does NOT measure similarity or naturalness.
"""
import os
import time
from pathlib import Path

import pytest

from app.audio.wav import read_wav_file, remove_dc, write_wav
from app.config import load_settings
from app.services.jobs import validate_output
from app.services.openvoice_engine import OpenVoiceEngine

REF = os.getenv("VB_REAL_REF_WAV")
SRC = os.getenv("VB_REAL_SRC_WAV")

pytestmark = pytest.mark.skipif(not (REF and SRC and Path(REF).is_file() and Path(SRC).is_file()), reason="set VB_REAL_REF_WAV and VB_REAL_SRC_WAV to consented PCM WAV files")


def test_real_enroll_and_convert(tmp_path):
    eng = OpenVoiceEngine(load_settings())
    eng.start_loading()
    eng._thread.join(600)
    st = eng.status()
    if st.state != "ready":
        pytest.skip(f"model not ready: {st.state}: {st.reason}")

    ref = read_wav_file(Path(REF))
    src = read_wav_file(Path(SRC))
    ref_path, src_path = tmp_path / "ref.wav", tmp_path / "src.wav"
    write_wav(ref_path, remove_dc(ref.samples), ref.sample_rate)
    write_wav(src_path, remove_dc(src.samples), src.sample_rate)

    profile = tmp_path / "embedding.pt"
    eng.create_profile([ref_path], profile)
    assert profile.is_file()

    out = tmp_path / "out.wav"
    t0 = time.perf_counter()
    eng.convert(src_path, profile, out)
    elapsed = time.perf_counter() - t0
    dur = validate_output(out, src.duration)
    print(f"\nREAL RESULT device={st.device} source={src.duration:.2f}s output={dur:.2f}s time={elapsed:.2f}s RTF={elapsed / src.duration:.2f}")
