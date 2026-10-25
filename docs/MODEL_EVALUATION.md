# Phase 2 model evaluation

Facts below were checked on 11 Oct 2026 from the sources named in each row. "Not verified" means I could not
confirm it from an official source and it must not be relied on. No benchmark numbers are quoted because none were measured.

| Criterion | OpenVoice V2 (selected) | RVC | Seed-VC |
|---|---|---|---|
| Licence | **MIT**, code and weights (official model card, huggingface.co/myshell-ai/OpenVoiceV2; repo README) | Not verified from the official repo | **Not verified**: a third-party summary says the README states none. Check the repo's LICENSE before adopting |
| Reference-voice mode | Zero-shot from a reference clip (`extract_se`), no training (official API) | Per-speaker training; project advises at least ~10 min of clean speech (RVC README text) | Zero-shot (project README) |
| Streaming | No streaming API found; file/array conversion | Real-time GUI exists in the project/ecosystem | README claims real-time with ~300 ms algorithm delay + ~100 ms device delay and a GPU recommendation. **Unmeasured by me** |
| Windows / Python | Official guide is Linux + conda Python 3.9; community Windows guide exists. `setup.py` pins `numpy==1.22.0`, `librosa==0.9.1`, `gradio==3.48.0`, which conflict with Python 3.11/3.12 | Python 3.10+ per README | Python 3.10+ per README |
| Weights available | Official Hugging Face repo `myshell-ai/OpenVoiceV2`, `converter/config.json` + `converter/checkpoint.pth` (131 MB). The S3 zip link in USAGE.md returned 404 on 11 Oct 2026 | Needs `hubert_base.pt`, pretrained models, per-speaker model | Hugging Face `Plachta/Seed-VC` (project README) |
| Hardware | `device` argument; code supports CPU. Speed on your machine is **unmeasured** | Training needs more hardware | GPU strongly recommended (README) |

## Decision

**OpenVoice V2 tone-color converter** for Phase 2, because it is the only candidate that is (a) verifiably MIT-licensed,
(b) zero-shot from a short reference (needed for quick enrollment without training on user recordings), and
(c) simple enough to run file-based conversion on CPU.

Trade-offs, stated plainly:
* It converts timbre (tone colour). Prosody and accent of the source are largely kept, so it may not "become" the target as
  strongly as some other models. Similarity is unmeasured here; judge by listening.
* Its pinned dependencies do not install on Python 3.11/3.12, so the project installs it with `--no-deps` plus a
  hand-derived dependency list (`backend/requirements-model.txt`). This route is **unverified end to end**.
* No streaming interface was found. The repeated-window run below is an offline throughput/assembly experiment only, not live inference.

## Local repeated-window throughput measurement

Measured on the available Intel Core i5-13420H (12 logical CPUs), PyTorch CPU (no CUDA), with the installed OpenVoice V2 model and an enrolled profile carrying recorded consent. Startup cleanup had removed the earlier source WAV, so this rerun used a deterministic **synthetic, non-speech signal**. It is valid for throughput only; it cannot measure intelligibility, target similarity, or audible continuity.

| Input | Window / overlap / stride | Windows | Median inference | Max inference | Total inference | Effective RTF | First-output lower bound | CPU use |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 22.8 s synthetic signal | 2.0 s / 0.25 s / 1.75 s | 13 | 2.078 s | 2.909 s | 27.918 s | 1.224 | 4.909 s | 7.01 core-equivalents |
| 9.0 s synthetic signal | 5.0 s / 1.0 s / 4.0 s | 2 | 40.423 s | 41.656 s | 80.847 s | 8.983 | 46.656 s | 0.72 core-equivalents |

Both schedules were slower than their stride and had effective RTF above 1.0; the 5-second schedule was especially slow in this run. With a serial worker receiving one window per stride, the 5-second run would add about 36.4 seconds of backlog per new window after processing begins. The 2-second run's crossfade boundary sample-step metric was 0.015869 and stitched output duration was 22.763 seconds; the 5-second metric was 0.007477 and stitched duration was 8.985 seconds. Those sample steps do not establish perceptual seam quality. OpenVoice logged that the 2-second windows were too short to add its watermark. Do not treat these results as a live-call or speech-quality demonstration.

The alternative Seed-VC is not adopted. Its official repository's real-time claim is not a local measurement, and licensing/provenance terms for the exact checkpoints remain unverified. No weights were downloaded.

## For Phase 3

Evaluate Seed-VC (its real-time claims and LICENSE need verifying) and test OpenVoice chunked inference. Decide using
measured end-to-end latency on your hardware, not README claims.
