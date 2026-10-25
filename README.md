# Voice Bridge (Phase 2: file-based voice conversion)

Record or upload speech, enroll an **authorized** target voice, convert a speech file to that voice, listen to both, and
download the result. **This is not live conversion.** Real-time streaming is Phase 3 and has not been built or measured.

**Status honesty:** real model inference is verified locally for full files and offline audio windows. Live calling is
not implemented: the current OpenVoice adapter processes complete WAV files and the browser does not have an AI-converted
outgoing WebRTC track. The UI intentionally does not request the microphone for a call or send raw microphone audio.

Model: OpenVoice V2 tone-color converter, MIT licence. See `docs/MODEL_EVALUATION.md` for the selection rationale.

## 0. Update your existing project (PowerShell)

```powershell
cd C:\Users\vthin\Downloads\realtime-voice-ai\voice-bridge\voice-bridge
Expand-Archive -Path "$HOME\Downloads\voice-bridge-phase2.zip" -DestinationPath "$env:TEMP\vb2" -Force
Copy-Item "$env:TEMP\vb2\voice-bridge\*" -Destination . -Recurse -Force
```
Your `backend\.venv` and `frontend\node_modules` are not in the zip, so they are kept.

## 1. Check your hardware and packages

```powershell
backend\.venv\Scripts\python.exe scripts\check_env.py
```
Python 3.10 to 3.12 is expected. A GPU is optional; without CUDA the CPU path is used and conversion will be slower.

## 2. Install backend dependencies

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
# PyTorch, CPU build:
.\.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
# NVIDIA GPU instead? Use the command from https://pytorch.org/get-started/locally/ with this venv's python.
.\.venv\Scripts\python.exe -m pip install -r requirements-model.txt
cd ..
```

## 3. Install OpenVoice (code only; its pinned dependencies are skipped on purpose)

Needs Git (`winget install --id Git.Git -e`, then reopen PowerShell).
```powershell
git clone https://github.com/myshell-ai/OpenVoice.git third_party\OpenVoice
backend\.venv\Scripts\python.exe -m pip install --no-deps -e third_party\OpenVoice
```
OpenVoice's own `pip install -e .` pins `numpy==1.22.0` and other old versions that conflict with Python 3.11/3.12, which is why `--no-deps` is used.

## 4. Get the model weights (official source)

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\get_openvoice_weights.ps1
```
Downloads `converter/config.json` and `converter/checkpoint.pth` (about 131 MB) from the official Hugging Face repo
`myshell-ai/OpenVoiceV2` (MIT licence) into `models\openvoice_v2\converter\`. `models\` is git-ignored. The download is resumable: re-run the
script if it is interrupted. (The older S3 zip link from OpenVoice's USAGE.md returned 404.) If the backend is already running, it
notices the weights on the next status poll; no restart is needed.

## 5. Real inference smoke test (no web app)

Use PCM WAV files of voices you own or have permission to use (a reference of ~10 s, and some speech to convert):
```powershell
backend\.venv\Scripts\python.exe scripts\smoke_convert.py --ref C:\path\my_voice.wav --src C:\path\speech.wav --out converted.wav
```
It prints load time, device, enrollment time, conversion time and the real-time factor for that file, then check by listening. If it fails, send me the full output.

## 6. Run the app

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1
```
Or manually in two windows:
```powershell
# Window 1
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
# Window 2
cd frontend
npm install
npm run dev
```
Open http://localhost:5173. The model loads in the background; the header badge shows loading / ready / unavailable.

## 7. Check endpoints

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:8000/api/model/status
```

## 8. Run the tests

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
cd ..\frontend
npm run typecheck
npm run build
```
Or everything at once: `powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1`

Real-model pytest (optional, skipped unless you set both files):
```powershell
$env:VB_REAL_REF_WAV = "C:\path\my_voice.wav"
$env:VB_REAL_SRC_WAV = "C:\path\speech.wav"
cd backend; .\.venv\Scripts\python.exe -m pytest tests\test_openvoice_real.py -s
```

## 8a. Benchmark actual OpenVoice audio windows

The benchmark runs the installed OpenVoice model on overlapping full-file WAV windows using an already-enrolled profile.
It reports model-load time, per-window inference time, RTF, process CPU time, a lower bound on first-output latency, and
the duration of a crossfaded offline reconstruction. It does **not** prove natural-sounding boundaries or live-call
quality; listen to the optional output and test on your target hardware. Use only consented source audio and a profile
with recorded consent.

```powershell
backend\.venv\Scripts\python.exe scripts\benchmark_openvoice_windows.py `
  --source C:\path\to\consented_speech.wav `
  --voice-id YOUR_32_CHARACTER_VOICE_ID `
  --window-seconds 5 `
  --overlap-seconds 1 `
  --output C:\path\to\windowed_conversion.wav
```

### Local benchmark snapshot (2026-10-11)

The installed OpenVoice V2 model loaded successfully on CPU (PyTorch `2.14.1+cpu`, CUDA unavailable; converter rate
22,050 Hz). The measured source was a locally stored 22.802-second mono WAV and the target was an existing profile with
a recorded consent confirmation. This is a throughput check on generated audio, not a clean-speech quality evaluation.

| Window / overlap | Windows | Median inference | Effective RTF* | First output lower bound | Result |
|---|---:|---:|---:|---:|---|
| 2.0 s / 0.25 s | 13 | 1.566 s | 0.899 | 4.173 s | Stitched 22.763 s; max measured boundary sample step 0.039 |
| 5.0 s / 1.0 s | 6 | 3.551 s | 0.920 | 9.818 s | Stitched 22.759 s |

`* Effective RTF` includes repeated overlap work but divides by the original source duration. In the 2-second run,
average process use was 7.45 CPU-core equivalents; model inference does not use a GPU. The first window includes model
warm-up, and later 2-second calls took 1.328–1.749 seconds against a 1.75-second stride, leaving effectively no
headroom. First-output latency includes waiting for the complete first window plus its inference time, but excludes
network transport and client playback buffering. Crossfade/sample-step metrics do not establish intelligibility or
audible continuity. No two-device, Android, TURN, or real-network call test has been performed.

## 9. One conversion in the browser

1. Enable the microphone and record a reference (Quick: about 10 s of natural speech).
2. Under **Target voice**, choose Quick or High-quality, name it, pick the recording, tick the consent box, press Enroll voice.
3. Record (or upload) the speech to convert.
4. Under **Convert speech**, pick the source and the target voice, press Convert.
5. Compare Original and Converted, then download.

## Workflows

**Enrollment:** browser converts audio to mono 24 kHz WAV, the server validates length, silence, clipping and noise (heuristics),
HQ mode cuts long recordings into clips at quiet points, OpenVoice's `extract_se` builds the tone-color (speaker) embedding, and
only that embedding plus a consent record is stored. **The reference recording is deleted.** If any step fails, no profile is created.

**Conversion:** validate WAV, check not silent, queue one job at a time on a worker thread (the event loop is never blocked),
extract the source embedding, `convert()` with the target embedding, validate the output (exists, readable, not silent, length within
30% of source), then serve it. Real errors are shown; nothing is simulated.

## Settings (environment variables, all optional)

`VB_DEVICE` (auto|cpu|cuda), `VB_MODEL_DIR`, `VB_DATA_DIR`, `VB_OPENVOICE_TAU` (0.3), `VB_OPENVOICE_WATERMARK` (1; the model's optional
provenance watermark needs the `wavmark` package), `VB_ALLOW_UNSAFE_CHECKPOINT` (0), `VB_OUTPUT_TTL_MINUTES` (60), `VB_MAX_UPLOAD_MB` (25),
`VB_MAX_SOURCE_SECONDS` (120).

## Privacy and retention

* Voice data stays on your computer, under `storage\` (git-ignored). Your audio is never sent to external services. One caveat: the optional watermark package (`wavmark`) depends on `huggingface-hub`, so it may download its own small model on first use (not verified). Set `VB_OPENVOICE_WATERMARK=0` to avoid that.
* Source uploads are deleted as soon as the conversion finishes; converted files are deleted after 60 minutes, on delete, and at start-up.
* Voice profiles persist until you delete them (Delete voice button). Each stores a consent self-attestation, which is not identity verification.
* No authentication: do **not** expose this server beyond localhost without adding access controls.
* Checkpoints load with PyTorch safe loading by default. `VB_ALLOW_UNSAFE_CHECKPOINT=1` enables full pickle loading; use it only for the official file.

## Troubleshooting

**Model not ready? Run the diagnostic first.** It tests each stage in order (weights, every import, building the converter, loading the checkpoint) and names the first one that fails:
```powershell
backend\.venv\Scripts\python.exe scripts\diagnose_model.py
Invoke-RestMethod http://127.0.0.1:8000/api/model/status      # direct to the backend
Invoke-RestMethod http://localhost:5173/api/model/status      # through the Vite proxy (what the page uses)
```
The page's "Waiting for..." line now shows the actual reason from that endpoint. The enrolled-voices list is simply empty until you enroll a voice (`Invoke-RestMethod http://127.0.0.1:8000/api/voices` should return `{"voices": []}`).

| Symptom | Likely cause / action |
|---|---|
| Badge: "Voice model unavailable", reason mentions weights | Run step 4, restart the backend |
| Reason says a Python package is missing | `pip install <name>` into `backend\.venv`, restart; tell me the name so I can update the list |
| Reason mentions `wavmark` | Install it, or set `$env:VB_OPENVOICE_WATERMARK="0"` before starting |
| Model failed to load, log mentions `weights_only` | Official file with newer PyTorch: set `$env:VB_ALLOW_UNSAFE_CHECKPOINT="1"` |
| 503 `model_loading` | Wait; first load can take a while |
| Conversion slow | CPU path. Check `device` in the result panel |
| "Cannot reach the server" | Backend not running on port 8000 |

## Done vs pending

Done (code written; backend core unit-tested): model status, enrollment (quick and HQ), profile list/delete, file conversion jobs,
output validation, download, frontend integration, API tests (written, not yet run), setup scripts.
**Not yet demonstrated:** real model inference, enrollment quality, similarity, measured RTF on your hardware.
**Pending:** Phase 3 streaming, Phase 4 WebRTC rooms, similarity/WER evaluation tooling.
