"""Core tests: audio IO, quality checks, profile store, job manager, engine status.
Pure Python + numpy (no FastAPI needed). Run:  python -m unittest discover -s tests -v
"""
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

from app.audio.quality import analyze, split_segments
from app.audio.wav import AudioError, read_wav_bytes, write_wav, read_wav_file
from app.config import Settings
from app.errors import ApiError, ServiceError
from app.services.jobs import JobManager, validate_output
from app.services.openvoice_engine import OpenVoiceEngine
from app.services.profiles import ProfileStore, new_id, is_valid_id

from tests.fakes import FakeEngine
from tests.synth import speech_like, wav_bytes


def make_settings(tmp: Path, **kw) -> Settings:
    return Settings(data_dir=tmp / "data", model_dir=tmp / "models", **kw)


class WavTests(unittest.TestCase):
    def test_roundtrip_16bit(self):
        x = speech_like(2.0)
        a = read_wav_bytes(wav_bytes(x))
        self.assertEqual(a.sample_rate, 24000)
        self.assertAlmostEqual(a.duration, 2.0, places=2)
        self.assertLess(float(np.max(np.abs(a.samples - x))), 1e-3)

    def test_other_bit_depths_and_stereo(self):
        x = speech_like(1.0)
        for width in (1, 3, 4):
            a = read_wav_bytes(wav_bytes(x, width=width))
            self.assertEqual(len(a.samples), len(x), width)
        a = read_wav_bytes(wav_bytes(x, channels=2))
        self.assertEqual(len(a.samples), len(x))

    def test_empty_bytes_rejected(self):
        with self.assertRaises(AudioError) as c:
            read_wav_bytes(b"")
        self.assertEqual(c.exception.code, "unsupported_format")

    def test_not_a_wav_rejected(self):
        with self.assertRaises(AudioError) as c:
            read_wav_bytes(b"\x1aE\xdf\xa3" + b"0" * 100)  # WebM magic
        self.assertEqual(c.exception.code, "unsupported_format")

    def test_zero_frames_rejected(self):
        with self.assertRaises(AudioError) as c:
            read_wav_bytes(wav_bytes(np.zeros(0, dtype=np.float32)))
        self.assertEqual(c.exception.code, "empty_audio")

    def test_truncated_rejected(self):
        data = wav_bytes(speech_like(2.0))
        with self.assertRaises(AudioError):
            read_wav_bytes(data[: len(data) // 2])

    def test_too_long_rejected(self):
        with self.assertRaises(AudioError) as c:
            read_wav_bytes(wav_bytes(speech_like(3.0)), max_seconds=2)
        self.assertEqual(c.exception.code, "audio_too_long")

    def test_bad_sample_rate_rejected(self):
        with self.assertRaises(AudioError) as c:
            read_wav_bytes(wav_bytes(speech_like(1.0, sr=4000), sr=4000))
        self.assertEqual(c.exception.code, "unsupported_sample_rate")


class QualityTests(unittest.TestCase):
    def verdict(self, x, sr=24000):
        return analyze(x, sr)

    def test_clean_is_good(self):
        self.assertEqual(self.verdict(speech_like(8)).verdict, "good")

    def test_silence_is_bad(self):
        r = self.verdict(np.zeros(24000 * 5, dtype=np.float32))
        self.assertEqual(r.verdict, "bad")
        self.assertTrue(any(f.id == "level" and f.severity == "bad" for f in r.findings))

    def test_clipping_detected(self):
        r = self.verdict(speech_like(6, speech_db=-12, clip=True))
        self.assertTrue(any(f.id == "clipping" and f.severity == "bad" for f in r.findings))

    def test_noisy_detected(self):
        r = self.verdict(speech_like(6, noise_db=-32))
        self.assertTrue(any(f.id == "noise" and f.severity == "bad" for f in r.findings))

    def test_quiet_detected(self):
        r = self.verdict(speech_like(6, speech_db=-48, noise_db=-80))
        self.assertTrue(any(f.id == "level" and f.severity == "bad" for f in r.findings))

    def test_split_segments(self):
        x = speech_like(35)
        segs = split_segments(x, 24000)
        self.assertGreaterEqual(len(segs), 3)
        for s in segs:
            self.assertGreaterEqual(len(s) / 24000, 3.0)
            self.assertLessEqual(len(s) / 24000, 14.0)

    def test_split_drops_silence(self):
        self.assertEqual(split_segments(np.zeros(24000 * 20, dtype=np.float32), 24000), [])


class ProfileTests(unittest.TestCase):
    def test_id_validation_blocks_traversal(self):
        for bad in ("../x", "..\\x", "a" * 31, "G" * 32, "", "/etc/passwd", "0" * 32 + "/.."):
            self.assertFalse(is_valid_id(bad), bad)

    def test_lifecycle(self):
        with tempfile.TemporaryDirectory() as t:
            store = ProfileStore(Path(t) / "profiles")
            self.assertEqual(store.list(), [])
            pid = new_id()
            d = store.make_dir(pid)
            self.assertFalse(store.exists(pid))  # no artifact/meta yet: not enrolled
            (d / "embedding.pt").write_bytes(b"x")
            store.save_meta(pid, {"id": pid, "name": "A", "created_at": "2026-01-01"})
            self.assertTrue(store.exists(pid))
            self.assertEqual([m["id"] for m in store.list()], [pid])
            self.assertTrue(store.delete(pid))
            self.assertFalse(store.delete(pid))
            self.assertEqual(store.list(), [])

    def test_delete_rejects_bad_id(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertFalse(ProfileStore(Path(t)).delete("../.."))


def wait_done(jobs, job_id, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        j = jobs.get(job_id)
        if j and j.status in ("succeeded", "failed"):
            return j
        time.sleep(0.02)
    raise AssertionError("job did not finish")


class JobTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.s = make_settings(self.tmp)
        self.s.ensure_dirs()
        self.profiles = ProfileStore(self.s.profiles_dir)
        self.pid = new_id()
        d = self.profiles.make_dir(self.pid)
        (d / "embedding.pt").write_bytes(b"x")
        self.profiles.save_meta(self.pid, {"id": self.pid})

    def tearDown(self):
        self._tmp.cleanup()

    def source(self, seconds=2.0, samples=None):
        jid = new_id()
        p = self.s.tmp_dir / f"{jid}_src.wav"
        write_wav(p, speech_like(seconds) if samples is None else samples, 24000)
        return jid, p

    def run_job(self, engine, **src):
        jm = JobManager(self.s, engine, self.profiles)
        jid, p = self.source(**src)
        job = jm.submit(jid, p, 2.0, self.pid)
        done = wait_done(jm, job.id)
        jm.shutdown()
        return jm, done, p

    def test_success_records_metrics_and_cleans_tmp(self):
        jm, job, src = self.run_job(FakeEngine())
        self.assertEqual(job.status, "succeeded")
        self.assertIsNotNone(job.processing_seconds)
        self.assertIsNotNone(job.rtf)
        self.assertTrue(jm.output_path(job.id).is_file())
        self.assertFalse(src.exists())
        self.assertTrue(job.to_dict()["audio_url"].endswith("/audio"))

    def test_engine_error_is_reported_honestly(self):
        _, job, src = self.run_job(FakeEngine(convert_error=ServiceError("inference_failed", "model failed")))
        self.assertEqual(job.status, "failed")
        self.assertEqual(job.error["code"], "inference_failed")
        self.assertIsNone(job.to_dict()["audio_url"])
        self.assertFalse(src.exists())

    def test_unexpected_exception_hides_details(self):
        _, job, _ = self.run_job(FakeEngine(convert_error=RuntimeError("C:\\secret\\path boom")))
        self.assertEqual(job.status, "failed")
        self.assertNotIn("secret", str(job.error))

    def test_silent_output_rejected(self):
        def silent(src, prof, out):
            write_wav(out, np.zeros(48000, dtype=np.float32), 24000)

        _, job, _ = self.run_job(FakeEngine(convert_fn=silent))
        self.assertEqual(job.error["code"], "silent_output")

    def test_missing_output_rejected(self):
        _, job, _ = self.run_job(FakeEngine(convert_fn=lambda s, p, o: None))
        self.assertEqual(job.error["code"], "missing_output")

    def test_wrong_duration_rejected(self):
        def short(src, prof, out):
            write_wav(out, speech_like(0.5), 24000)

        _, job, _ = self.run_job(FakeEngine(convert_fn=short))
        self.assertEqual(job.error["code"], "unexpected_output_duration")

    def test_queue_limit(self):
        import threading

        gate = threading.Event()
        eng = FakeEngine(convert_fn=lambda s, p, o: (gate.wait(5), write_wav(o, speech_like(2.0), 24000)))
        s = make_settings(self.tmp, max_queued_jobs=1)
        jm = JobManager(s, eng, self.profiles)
        j1, p1 = self.source()
        jm.submit(j1, p1, 2.0, self.pid)
        j2, p2 = self.source()
        with self.assertRaises(ApiError) as c:
            jm.submit(j2, p2, 2.0, self.pid)
        self.assertEqual(c.exception.status, 429)
        gate.set()
        wait_done(jm, j1)
        jm.shutdown()

    def test_job_ids_validated(self):
        jm = JobManager(self.s, FakeEngine(), self.profiles)
        self.assertIsNone(jm.get("../etc"))
        self.assertFalse(jm.delete("../etc"))
        jm.shutdown()

    def test_validate_output_missing_file(self):
        with self.assertRaises(ServiceError):
            validate_output(self.tmp / "nope.wav", 1.0)


class EngineStatusTests(unittest.TestCase):
    def test_missing_weights_reported(self):
        with tempfile.TemporaryDirectory() as t:
            eng = OpenVoiceEngine(make_settings(Path(t)))
            self.assertEqual(eng.status().state, "unavailable")
            eng.start_loading()
            eng._thread.join(10)
            st = eng.status()
            self.assertEqual(st.state, "unavailable")
            self.assertIn("weights not found", st.reason)
            self.assertNotIn(t, st.reason)  # no absolute paths leaked

    def test_weights_downloaded_after_startup_trigger_one_retry(self):
        with tempfile.TemporaryDirectory() as t:
            eng = OpenVoiceEngine(make_settings(Path(t)))
            eng.start_loading()
            eng._thread.join(10)
            self.assertIn("weights not found", eng.status().reason)
            eng.refresh()  # still no weights: nothing happens
            self.assertIn("weights not found", eng.status().reason)
            d = Path(t) / "models" / "openvoice_v2" / "converter"
            d.mkdir(parents=True)
            (d / "config.json").write_text("{}")
            (d / "checkpoint.pth").write_bytes(b"x")
            first = eng._thread
            eng.refresh()
            self.assertIsNot(eng._thread, first)  # a new load attempt started
            eng._thread.join(10)
            self.assertNotIn("weights not found", eng.status().reason or "")
            again = eng._thread
            eng.refresh()
            self.assertIs(eng._thread, again)  # no retry loop

    def test_not_ready_engine_refuses_work(self):
        with tempfile.TemporaryDirectory() as t:
            eng = OpenVoiceEngine(make_settings(Path(t)))
            with self.assertRaises(ServiceError) as c:
                eng.convert(Path("a.wav"), Path("b.pt"), Path("c.wav"))
            self.assertEqual(c.exception.code, "model_not_ready")


if __name__ == "__main__":
    unittest.main()
