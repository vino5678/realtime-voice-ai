r"""Hardware / dependency check. Run with the backend venv's Python:
    backend\.venv\Scripts\python.exe scripts\check_env.py
Changes nothing; installs nothing."""
import importlib.util
import os
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def ram_gb():
    try:
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [("l", ctypes.c_ulong), ("m", ctypes.c_ulong), ("total", ctypes.c_ulonglong), ("a", ctypes.c_ulonglong),
                        ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong), ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong)]

        s = MS()
        s.l = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s))
        return s.total / 2**30
    except Exception:
        try:
            return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30
        except Exception:
            return None


print(f"Python      : {sys.version.split()[0]} ({platform.machine()}) {'OK (3.10-3.12)' if (3, 10) <= sys.version_info[:2] <= (3, 12) else 'outside 3.10-3.12'}")
print(f"OS          : {platform.platform()}")
r = ram_gb()
print(f"RAM         : {r:.1f} GB" if r else "RAM         : unknown")
print(f"CPU threads : {os.cpu_count()}")
if importlib.util.find_spec("torch"):
    import torch

    print(f"PyTorch     : {torch.__version__}")
    print(f"CUDA        : {'available' if torch.cuda.is_available() else 'NOT available (CPU path will be used)'}")
    if torch.cuda.is_available():
        p = torch.cuda.get_device_properties(0)
        print(f"GPU         : {p.name}, {p.total_memory / 2**30:.1f} GB VRAM")
else:
    print("PyTorch     : NOT installed")
print("\nPackages:")
for m in ("fastapi", "uvicorn", "multipart", "numpy", "scipy", "librosa", "soundfile", "openvoice", "wavmark", "inflect", "unidecode", "eng_to_ipa", "pypinyin", "cn2an", "jieba"):
    print(f"  {m:<11}: {'ok' if importlib.util.find_spec(m) else 'MISSING'}")
print("\nModel weights:")
found = [d for d in ("openvoice_v2/converter", "openvoice_v2/checkpoints_v2/converter", "checkpoints_v2/converter") if (ROOT / "models" / d / "checkpoint.pth").is_file() and (ROOT / "models" / d / "config.json").is_file()]
if found:
    msg = "found in models/" + found[0]
else:
    msg = "NOT found (expected models\\openvoice_v2\\converter\\config.json and checkpoint.pth)"
print("  OpenVoice V2 converter: " + msg)
