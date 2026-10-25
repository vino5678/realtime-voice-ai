r"""Run ONE real enrollment + conversion without the web app, to diagnose model problems.
    backend\.venv\Scripts\python.exe scripts\smoke_convert.py --ref my_voice.wav --src speech.wav --out out.wav
Use only recordings of voices you own or have permission to use. Inputs must be PCM WAV."""
import argparse
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.audio.wav import read_wav_file, remove_dc, write_wav  # noqa: E402
from app.config import load_settings  # noqa: E402
from app.services.jobs import validate_output  # noqa: E402
from app.services.openvoice_engine import OpenVoiceEngine  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--ref", required=True)
ap.add_argument("--src", required=True)
ap.add_argument("--out", default="converted.wav")
a = ap.parse_args()

eng = OpenVoiceEngine(load_settings())
t = time.perf_counter()
eng.start_loading()
eng._thread.join()
st = eng.status()
print(f"load: {st.state} ({time.perf_counter() - t:.1f}s) device={st.device} {st.reason or ''}")
if st.state != "ready":
    sys.exit(1)

ref, src = read_wav_file(Path(a.ref)), read_wav_file(Path(a.src))
with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    write_wav(d / "ref.wav", remove_dc(ref.samples), ref.sample_rate)
    write_wav(d / "src.wav", remove_dc(src.samples), src.sample_rate)
    t = time.perf_counter()
    eng.create_profile([d / "ref.wav"], d / "e.pt")
    print(f"enroll: {time.perf_counter() - t:.2f}s")
    t = time.perf_counter()
    eng.convert(d / "src.wav", d / "e.pt", Path(a.out))
    el = time.perf_counter() - t
out_s = validate_output(Path(a.out), src.duration)
print(f"convert: {el:.2f}s for {src.duration:.2f}s of audio -> RTF {el / src.duration:.2f} (this file only; first run includes warm-up). Output {out_s:.2f}s -> {a.out}")
print("Output is valid audio of plausible length. Listen to judge similarity; no similarity score was computed.")
