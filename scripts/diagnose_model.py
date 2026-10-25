r"""Find exactly why the voice model is not ready. Changes nothing, downloads nothing except what
wavmark itself may fetch. Run with the backend venv's Python:
    backend\.venv\Scripts\python.exe scripts\diagnose_model.py
Optional: add  --ref my_voice.wav  to also test real enrollment (use only a voice you may use)."""
import argparse
import importlib
import platform
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
ap = argparse.ArgumentParser()
ap.add_argument("--ref")
args = ap.parse_args()

failed = []


def stage(name, fn):
    t = time.perf_counter()
    try:
        out = fn()
        print(f"[ OK ] {name} ({time.perf_counter() - t:.1f}s){': ' + str(out) if out else ''}")
        return out
    except BaseException as e:  # noqa: BLE001
        print(f"[FAIL] {name} ({time.perf_counter() - t:.1f}s): {type(e).__name__}: {e}")
        traceback.print_exc(limit=6)
        failed.append(name)
        return None


print(f"Python {sys.version.split()[0]} on {platform.platform()}\n")
from app.config import load_settings  # noqa: E402

s = load_settings()
print(f"model_dir = {s.model_dir}\ndevice    = {s.device}   watermark = {s.openvoice_watermark}\n")

cands = ("openvoice_v2/converter", "openvoice_v2/checkpoints_v2/converter", "checkpoints_v2/converter")
found = next((s.model_dir / c for c in cands if (s.model_dir / c / "config.json").is_file() and (s.model_dir / c / "checkpoint.pth").is_file()), None)
stage("weights present", lambda: str(found) if found else (_ for _ in ()).throw(FileNotFoundError("no converter\\config.json + checkpoint.pth under models\\ - run scripts\\get_openvoice_weights.ps1")))
if found:
    stage("checkpoint size", lambda: f"{(found / 'checkpoint.pth').stat().st_size / 1e6:.0f} MB")

for m in ("numpy", "torch", "torchaudio", "scipy", "librosa", "soundfile", "inflect", "unidecode", "eng_to_ipa", "pypinyin", "cn2an", "jieba", "wavmark"):
    stage(f"import {m}", lambda m=m: getattr(importlib.import_module(m), "__version__", ""))

torch = importlib.import_module("torch") if "import torch" not in failed else None
conv_cls = stage("import openvoice.api.ToneColorConverter", lambda: importlib.import_module("openvoice.api").ToneColorConverter)
conv = None
if found and torch and conv_cls:
    device = "cuda:0" if (s.device in ("auto", "cuda") and torch.cuda.is_available()) else "cpu"

    def build(wm):
        try:
            return conv_cls(str(found / "config.json"), device=device, enable_watermark=wm)
        except TypeError:
            return conv_cls(str(found / "config.json"), device=device)

    conv = stage(f"construct converter (watermark={s.openvoice_watermark}, device={device})", lambda: build(s.openvoice_watermark))
    if conv is None and s.openvoice_watermark:
        print("       Retrying WITHOUT the watermark to isolate the cause...")
        conv = stage("construct converter (watermark=False)", lambda: build(False))
        if conv is not None:
            print("       => the watermark model is the problem. Set  $env:VB_OPENVOICE_WATERMARK=\"0\"  before starting the backend.")
    if conv is not None:
        stage("load checkpoint (safe loading)", lambda: conv.load_ckpt(str(found / "checkpoint.pth")))
        if args.ref:
            stage("real enrollment (extract_se)", lambda: tuple(conv.extract_se([args.ref]).shape))

print("\nVERDICT:", "no failures found - the backend should reach 'ready'" if not failed else f"first failing stage -> {failed[0]}")
