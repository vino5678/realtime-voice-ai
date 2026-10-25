# Architecture and Phase 2 questions

## Target architecture (Phases 1-4)

```
Speaker browser                                   Backend (FastAPI, local)
 mic -> getUserMedia (raw, no AGC/NS)
     -> AudioWorklet: 16/24 kHz chunks  --WS-->   chunk queue -> preprocess -> VC model (GPU/CPU)
                                        <--WS--   converted chunks
     -> jitter buffer -> MediaStreamDestination
     -> WebRTC peer connection  ---------------------------------> Listener browser
                       ^ signalling via WebSocket room (FastAPI)       plays remote stream
```

Open design choice for Phase 4: convert on the server and send converted audio back to the speaker's browser, which then
forwards it over WebRTC (simplest, adds one network hop), or convert on the server and send it to the listener directly
(fewer hops, more server work). Decide after measuring Phase 3 latency.

Phase 1 implements only: microphone capture, MediaRecorder recording, quality analysis, playback, `/api/health`.

## Folder structure

```
voice-bridge/
  backend/
    app/main.py            FastAPI app, /api/health
    tests/                 pytest
    requirements*.txt
  frontend/
    src/audio/             analysis.ts (quality checks), useRecorder.ts (mic + recording)
    src/components/        Waveform, TakeCard, ApiStatus
    src/App.tsx, styles.css
  scripts/dev.ps1          starts both servers
  docs/ARCHITECTURE.md
  # added later: backend/app/models/ (adapters), backend/app/enroll/, backend/app/rooms/, eval/ (metrics scripts)
  # storage/ is git-ignored and never served publicly
```

## Model-selection questions (answer before integrating anything)

Candidates to look at (I have NOT verified licences, quality or streaming behaviour of any of them; treat as a reading
list): RVC-family, so-vits-svc-family, Seed-VC, OpenVoice, kNN-VC, FreeVC, LLVC.

1. Licence: are code AND pretrained weights allowed for your intended use (local, commercial, hosted)? Any training-data restrictions?
2. Reference-voice mode: zero-shot from a short clip, or must a per-speaker model be trained? How much clean audio, and how long does training take?
3. Streaming: native chunked inference? Chunk size, look-ahead and context window (these set the minimum algorithmic latency).
4. Sample rate and input format; does it need pitch (F0) extraction or a content encoder that adds delay?
5. Hardware: VRAM and GPU needed for real-time factor < 1 at the chunk size; is CPU-only workable?
6. Runtime: runs on Windows with a PyTorch build you can install? ONNX/TensorRT export possible and does it preserve quality?
7. Content preservation: does it keep words, timing and prosody? Known failure modes (mumbling, language/accent limits)?
8. Language and speaking-style coverage matching your users.
9. Maintenance: active repository, pinned dependencies, security of loading `.pth`/pickle files.
10. Safety: does it support watermarking or consent hooks? How are voice profiles stored and deleted?

## Measurement plan (do not fill in with guesses)

| Metric | Method |
|--------|--------|
| Speaker similarity | Speaker-embedding cosine similarity (e.g. a pretrained speaker-verification model) on unseen sentences, plus a listening test |
| Intelligibility / WER | ASR (e.g. Whisper) on converted vs source audio, same sentences |
| Artifacts | Listening panel; log clipping, dropouts, buffer underruns |
| Latency | Chunk size + model time + network + jitter buffer + playback; verify with a loopback click test |
| RTF | Processing time / audio duration per chunk, p50 and p95 |
| CPU / RAM / VRAM | Windows Performance Monitor or `nvidia-smi` during a 10-minute run |
| Network stability | Throttle/packet-loss simulation, count glitches and reconnects |
