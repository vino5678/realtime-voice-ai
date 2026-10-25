"""HTTP routes. Thin: validation and plumbing only. Model code lives in app/services."""
from __future__ import annotations

import asyncio
import logging
import re
import shutil
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from ..audio.quality import analyze, split_segments
from ..audio.wav import AudioError, read_wav_bytes, remove_dc, write_wav
from ..container import Container
from ..errors import ApiError, ServiceError
from ..services.profiles import is_valid_id, new_id

log = logging.getLogger("voicebridge.api")
router = APIRouter(prefix="/api")

CONSENT_TEXT = "I am the owner of this voice or have the speaker's explicit permission to create and use a voice profile from it."


def _vb(request: Request) -> Container:
    return request.app.state.vb


async def _read_upload(file: UploadFile, max_bytes: int) -> bytes:
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ApiError(413, "file_too_large", f"The file is larger than the {max_bytes // (1024 * 1024)} MB limit.")
    if len(data) == 0:
        raise ApiError(400, "empty_file", "The uploaded file is empty.")
    return data


def _decode(data: bytes, max_seconds: float):
    try:
        return read_wav_bytes(data, max_seconds)
    except AudioError as e:
        raise ApiError(e.status, e.code, e.message)


def _require_ready(vb: Container) -> None:
    st = vb.engine.status()
    if st.state != "ready":
        code = "model_loading" if st.state == "loading" else "model_unavailable"
        raise ApiError(503, code, st.reason or "The voice model is not ready.")


def _clean_name(name: str) -> str:
    n = re.sub(r"[\x00-\x1f\x7f]", "", name or "")
    n = re.sub(r"\s+", " ", n).strip()
    if not 1 <= len(n) <= 60:
        raise ApiError(422, "invalid_name", "Give the voice a name of 1 to 60 characters.")
    return n


def _prepare_enrollment(settings, mode: str, audio):
    x = remove_dc(audio.samples)
    sr = audio.sample_rate
    dur = len(x) / sr
    label, lo, hi = ("Quick enrollment", settings.quick_min_seconds, settings.quick_max_seconds) if mode == "quick" else (
        "High-quality enrollment", settings.hq_min_seconds, settings.hq_max_seconds)
    if dur < lo:
        raise ApiError(422, "audio_too_short", f"The recording is {dur:.1f} s. {label} needs at least {lo:.0f} s.")
    if dur > hi:
        raise ApiError(422, "audio_too_long", f"The recording is {dur:.0f} s. {label} accepts at most {hi:.0f} s.")
    report = analyze(x, sr, include_duration=False)
    bad = [f for f in report.findings if f.severity == "bad"]
    if bad:
        msg = " ".join(f"{f.title}: {f.detail}" for f in bad)
        raise ApiError(422, "poor_audio_quality", f"This recording is not usable. {msg}", details=report.to_dict())
    warnings = [f"{f.title}. {f.detail}" for f in report.findings if f.severity == "warn"]
    if mode == "quick":
        clips = [x]
    else:
        clips = split_segments(x, sr)
        if not clips:
            raise ApiError(422, "no_usable_speech", "No clear speech segments were found in this recording.")
    return clips, sr, report, warnings


@router.get("/model/status")
def model_status(request: Request) -> dict:
    engine = _vb(request).engine
    engine.refresh()
    return engine.status().to_dict()


@router.get("/voices")
def list_voices(request: Request) -> dict:
    return {"voices": _vb(request).profiles.list()}


@router.post("/voices", status_code=201)
async def enroll_voice(
    request: Request,
    name: str = Form(...),
    mode: str = Form(...),
    consent: str = Form(...),
    audio: UploadFile = File(...),
) -> dict:
    vb = _vb(request)
    s = vb.settings
    clean = _clean_name(name)
    if mode not in ("quick", "hq"):
        raise ApiError(422, "invalid_mode", "mode must be 'quick' or 'hq'.")
    if consent.strip().lower() != "true":
        raise ApiError(422, "consent_required", "You must confirm you have permission to use this voice.")
    data = await _read_upload(audio, s.max_upload_bytes)
    decoded = _decode(data, s.hq_max_seconds + 5)
    _require_ready(vb)
    clips, sr, report, warnings = await run_in_threadpool(_prepare_enrollment, s, mode, decoded)

    s.ensure_dirs()
    pid = new_id()
    tmp = s.tmp_dir / f"enroll_{pid}"
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        paths = []
        for i, c in enumerate(clips):
            p = tmp / f"clip_{i}.wav"
            write_wav(p, c, sr)
            paths.append(p)
        vb.profiles.make_dir(pid)
        try:
            info = await asyncio.wrap_future(vb.jobs.run_exclusive(vb.engine.create_profile, paths, vb.profiles.artifact_path(pid)))
        except ServiceError as e:
            vb.profiles.discard(pid)
            raise ApiError(422 if e.code == "enrollment_failed" else 503, e.code, e.message)
        st = vb.engine.status()
        meta = {
            "id": pid,
            "name": clean,
            "mode": mode,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "engine": st.engine,
            "artifact": "OpenVoice tone-color (speaker) embedding generated by the model. The reference recording is not kept.",
            "reference_seconds": round(sum(len(c) for c in clips) / sr, 2),
            "segments": len(clips),
            "warnings": warnings,
            "consent": {"confirmed": True, "statement": CONSENT_TEXT, "at": datetime.now(timezone.utc).isoformat()},
        }
        vb.profiles.save_meta(pid, meta)
        log.info("enroll_ok profile=%s mode=%s seconds=%.1f segments=%d", pid, mode, meta["reference_seconds"], len(clips))
        return {"voice": meta, "quality": report.to_dict(), "engine_info": info}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@router.delete("/voices/{voice_id}")
def delete_voice(voice_id: str, request: Request) -> dict:
    if not _vb(request).profiles.delete(voice_id):
        raise ApiError(404, "voice_not_found", "That voice profile does not exist.")
    return {"deleted": True, "id": voice_id}


@router.post("/convert", status_code=202)
async def start_conversion(request: Request, voice_id: str = Form(...), audio: UploadFile = File(...)) -> dict:
    vb = _vb(request)
    s = vb.settings
    if not is_valid_id(voice_id) or not vb.profiles.exists(voice_id):
        raise ApiError(404, "voice_not_found", "Select an enrolled target voice first.")
    data = await _read_upload(audio, s.max_upload_bytes)
    decoded = _decode(data, s.max_source_seconds)
    if decoded.duration < s.min_source_seconds:
        raise ApiError(422, "audio_too_short", f"The audio is shorter than {s.min_source_seconds:.1f} s.")
    _require_ready(vb)
    x = remove_dc(decoded.samples)
    report = await run_in_threadpool(analyze, x, decoded.sample_rate, False)
    if report.speech_db < -50:
        raise ApiError(422, "silent_audio", "The source audio is silent or almost silent.")
    warnings = [f"{f.title}. {f.detail}" for f in report.findings if f.severity != "good"]

    s.ensure_dirs()
    job_id = uuid.uuid4().hex
    src = s.tmp_dir / f"{job_id}_src.wav"
    write_wav(src, x, decoded.sample_rate)
    try:
        job = vb.jobs.submit(job_id, src, decoded.duration, voice_id)
    except Exception:
        src.unlink(missing_ok=True)
        raise
    log.info("convert_queued job=%s profile=%s source_s=%.2f", job_id, voice_id, decoded.duration)
    return {"job": job.to_dict(), "warnings": warnings}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request) -> dict:
    job = _vb(request).jobs.get(job_id)
    if not job:
        raise ApiError(404, "job_not_found", "That conversion does not exist or has expired.")
    return {"job": job.to_dict()}


@router.get("/jobs/{job_id}/audio")
def get_job_audio(job_id: str, request: Request, download: int = 0):
    path = _vb(request).jobs.output_path(job_id)
    if path is None:
        raise ApiError(404, "audio_not_found", "The converted audio is not available.")
    disposition = "attachment" if download else "inline"
    return FileResponse(
        path,
        media_type="audio/wav",
        headers={"Content-Disposition": f'{disposition}; filename="converted.wav"', "Cache-Control": "no-store"},
    )


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str, request: Request) -> dict:
    if not _vb(request).jobs.delete(job_id):
        raise ApiError(404, "job_not_found", "That conversion does not exist, has expired, or is still running.")
    return {"deleted": True, "id": job_id}
