"""API tests. They use FakeEngine, so they verify validation, status codes, job plumbing and
error handling. They do NOT demonstrate real AI conversion (see test_openvoice_real.py)."""
import tempfile
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.errors import ServiceError
from app.main import create_app
from app.services.openvoice_engine import OpenVoiceEngine
from tests.fakes import FakeEngine
from tests.synth import speech_like, wav_bytes


@pytest.fixture()
def env(tmp_path):
    s = Settings(data_dir=tmp_path / "data", model_dir=tmp_path / "models")
    eng = FakeEngine()
    app = create_app(s, eng)
    with TestClient(app) as c:
        yield c, eng, s


def enroll(c, mode="quick", seconds=8, consent="true", name="Test voice", data=None, filename="ref.wav"):
    data = data if data is not None else wav_bytes(speech_like(seconds))
    return c.post("/api/voices", data={"name": name, "mode": mode, "consent": consent}, files={"audio": (filename, data, "audio/wav")})


def make_voice(c):
    r = enroll(c)
    assert r.status_code == 201, r.text
    return r.json()["voice"]["id"]


def test_health_reports_engine_state(env):
    c, _, _ = env
    body = c.get("/api/health").json()
    assert body["inference"]["available"] is True


def test_model_status(env):
    c, eng, _ = env
    assert c.get("/api/model/status").json()["state"] == "ready"
    eng.state = "loading"
    assert c.get("/api/model/status").json()["state"] == "loading"


def test_enrollment_requires_consent(env):
    c, _, _ = env
    r = enroll(c, consent="false")
    assert r.status_code == 422 and r.json()["error"]["code"] == "consent_required"


def test_enrollment_invalid_fields(env):
    c, _, _ = env
    assert enroll(c, mode="turbo").json()["error"]["code"] == "invalid_mode"
    assert enroll(c, name="   ").json()["error"]["code"] == "invalid_name"
    r = c.post("/api/voices", data={"name": "x"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"


def test_enrollment_rejects_bad_audio(env):
    c, eng, _ = env
    assert enroll(c, data=b"").json()["error"]["code"] == "empty_file"
    assert enroll(c, data=b"\x1aE\xdf\xa3" + b"0" * 500, filename="a.webm").status_code == 415
    assert enroll(c, seconds=1).json()["error"]["code"] == "audio_too_short"
    r = enroll(c, data=wav_bytes(speech_like(8, speech_db=-12, clip=True)))
    assert r.json()["error"]["code"] == "poor_audio_quality"
    assert eng.calls["create_profile"] == 0  # nothing reached the model


def test_hq_requires_longer_recording(env):
    c, _, _ = env
    assert enroll(c, mode="hq", seconds=8).json()["error"]["code"] == "audio_too_short"
    assert enroll(c, mode="hq", seconds=30).status_code == 201


def test_enrollment_success_list_and_delete(env):
    c, _, _ = env
    r = enroll(c)
    assert r.status_code == 201
    v = r.json()["voice"]
    assert v["consent"]["confirmed"] is True and "reference recording is not kept" in v["artifact"]
    assert [x["id"] for x in c.get("/api/voices").json()["voices"]] == [v["id"]]
    assert c.delete(f"/api/voices/{v['id']}").json()["deleted"] is True
    assert c.get("/api/voices").json()["voices"] == []
    assert c.delete(f"/api/voices/{v['id']}").status_code == 404


def test_failed_enrollment_leaves_no_profile(tmp_path):
    s = Settings(data_dir=tmp_path / "d", model_dir=tmp_path / "m")
    app = create_app(s, FakeEngine(profile_error=ServiceError("enrollment_failed", "no")))
    with TestClient(app) as c:
        assert enroll(c).status_code == 422
        assert c.get("/api/voices").json()["voices"] == []


def test_enrollment_when_model_not_ready(tmp_path):
    s = Settings(data_dir=tmp_path / "d", model_dir=tmp_path / "m")
    with TestClient(create_app(s, FakeEngine(state="loading"))) as c:
        r = enroll(c)
        assert r.status_code == 503 and r.json()["error"]["code"] == "model_loading"


def test_path_traversal_ids_rejected(env):
    c, _, _ = env
    for bad in ("..%2F..%2Fetc", "..", "%2e%2e"):
        assert c.delete(f"/api/voices/{bad}").status_code in (404, 405)
        assert c.get(f"/api/jobs/{bad}").status_code in (404, 405)


def convert(c, voice_id, data=None, filename="src.wav"):
    data = data if data is not None else wav_bytes(speech_like(3))
    return c.post("/api/convert", data={"voice_id": voice_id}, files={"audio": (filename, data, "audio/wav")})


def wait(c, job_id, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        j = c.get(f"/api/jobs/{job_id}").json()["job"]
        if j["status"] in ("succeeded", "failed"):
            return j
        time.sleep(0.05)
    raise AssertionError("timeout")


def test_convert_missing_profile(env):
    c, _, _ = env
    r = convert(c, "0" * 32)
    assert r.status_code == 404 and r.json()["error"]["code"] == "voice_not_found"
    assert convert(c, "../x").status_code == 404


def test_convert_invalid_audio(env):
    c, _, _ = env
    vid = make_voice(c)
    assert convert(c, vid, data=b"").json()["error"]["code"] == "empty_file"
    assert convert(c, vid, data=b"not audio at all").status_code == 415
    assert convert(c, vid, data=wav_bytes(speech_like(0.1))).json()["error"]["code"] == "audio_too_short"
    assert convert(c, vid, data=wav_bytes(speech_like(3, speech_db=-80, noise_db=-90))).json()["error"]["code"] == "silent_audio"


def test_convert_success_and_download(env):
    c, eng, _ = env
    vid = make_voice(c)
    r = convert(c, vid)
    assert r.status_code == 202
    job = wait(c, r.json()["job"]["id"])
    assert job["status"] == "succeeded" and job["rtf"] is not None and job["processing_seconds"] is not None
    audio = c.get(job["audio_url"])
    assert audio.status_code == 200 and audio.headers["content-type"] == "audio/wav" and audio.content[:4] == b"RIFF"
    dl = c.get(job["audio_url"] + "?download=1")
    assert "attachment" in dl.headers["content-disposition"]
    assert c.delete(f"/api/jobs/{job['id']}").json()["deleted"] is True
    assert c.get(f"/api/jobs/{job['id']}").status_code == 404


def test_convert_inference_failure_is_honest(tmp_path):
    s = Settings(data_dir=tmp_path / "d", model_dir=tmp_path / "m")
    eng = FakeEngine(convert_error=ServiceError("inference_failed", "The voice model failed while converting this audio."))
    with TestClient(create_app(s, eng)) as c:
        vid = make_voice(c)
        job = wait(c, convert(c, vid).json()["job"]["id"])
        assert job["status"] == "failed" and job["error"]["code"] == "inference_failed" and job["audio_url"] is None


def test_missing_model_weights_reported_by_real_engine(tmp_path):
    s = Settings(data_dir=tmp_path / "d", model_dir=tmp_path / "empty-models")
    eng = OpenVoiceEngine(s)
    with TestClient(create_app(s, eng)) as c:
        eng._thread.join(10)
        st = c.get("/api/model/status").json()
        assert st["state"] == "unavailable" and "weights not found" in st["reason"]
        assert enroll(c).json()["error"]["code"] == "model_unavailable"


def test_unknown_route_uses_json_errors(env):
    c, _, _ = env
    r = c.get("/api/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
