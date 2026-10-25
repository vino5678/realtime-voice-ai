"""OpenVoice V2 tone-color converter adapter.

Verified against the official OpenVoice API (openvoice/api.py):
  ToneColorConverter(config_path, device=...)
  .load_ckpt(path)
  .extract_se(ref_wav_list)                       -> tone-color embedding
  .convert(audio_src_path, src_se, tgt_se, output_path, tau, message)

This module imports torch/openvoice lazily so the API starts (and reports an honest
status) even when they are not installed.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from ..config import Settings
from ..errors import ServiceError
from .engine_base import EngineStatus, VoiceEngine

log = logging.getLogger("voicebridge.openvoice")

_CANDIDATE_DIRS = (
    "openvoice_v2/converter",
    "openvoice_v2/checkpoints_v2/converter",
    "checkpoints_v2/converter",
)
WEIGHTS_HINT = r"models\openvoice_v2\converter\config.json and checkpoint.pth"


class OpenVoiceEngine(VoiceEngine):
    id = "openvoice-v2-converter"

    def __init__(self, settings: Settings):
        self._s = settings
        self._lock = threading.Lock()
        self._state = "unavailable"
        self._reason: str | None = "The model has not been loaded yet."
        self._device: str | None = None
        self._sample_rate: int | None = None
        self._converter = None
        self._torch = None
        self._watermark_active = False
        self._thread: threading.Thread | None = None
        self._weights_seen = False

    # ---- status -------------------------------------------------------
    def status(self) -> EngineStatus:
        with self._lock:
            return EngineStatus(
                state=self._state,
                engine=self.id,
                display_name="OpenVoice V2 tone-color converter",
                license="MIT (OpenVoice V1 and V2, per the official model card)",
                reason=self._reason,
                device=self._device,
                sample_rate=self._sample_rate,
                weights_hint=WEIGHTS_HINT,
            )

    def _set(self, state: str, reason: str | None = None) -> None:
        with self._lock:
            self._state, self._reason = state, reason

    # ---- loading ------------------------------------------------------
    def _find_model_files(self) -> tuple[Path, Path] | None:
        for rel in _CANDIDATE_DIRS:
            d = self._s.model_dir / rel
            if (d / "config.json").is_file() and (d / "checkpoint.pth").is_file():
                return d / "config.json", d / "checkpoint.pth"
        return None

    def start_loading(self) -> None:
        with self._lock:
            if self._state in ("loading", "ready"):
                return
            self._state, self._reason = "loading", "Loading the voice model."
        self._thread = threading.Thread(target=self._load, name="openvoice-load", daemon=True)
        self._thread.start()

    def refresh(self) -> None:
        """If the weights were missing at start-up and have since been downloaded, load once."""
        with self._lock:
            waiting = self._state == "unavailable" and not self._weights_seen
        if waiting and self._find_model_files():
            self._weights_seen = True
            self.start_loading()

    def _pick_device(self, torch) -> str:
        want = self._s.device
        if want == "cpu":
            return "cpu"
        if want in ("cuda", "auto"):
            if torch.cuda.is_available():
                return "cuda:0"
            if want == "cuda":
                raise ServiceError("cuda_unavailable", "VB_DEVICE=cuda was requested but PyTorch cannot see a CUDA GPU.")
            return "cpu"
        raise ServiceError("bad_device", "VB_DEVICE must be auto, cpu or cuda.")

    def _load(self) -> None:
        try:
            found = self._find_model_files()
            if not found:
                self._set("unavailable", f"Model weights not found. Expected {WEIGHTS_HINT} (see README, step 'Get the model weights').")
                return
            cfg, ckpt = found
            self._weights_seen = True
            import torch  # noqa: WPS433

            device = self._pick_device(torch)
            from openvoice.api import ToneColorConverter  # noqa: WPS433

            try:
                conv = ToneColorConverter(str(cfg), device=device, enable_watermark=self._s.openvoice_watermark)
            except TypeError:  # older API without the enable_watermark argument
                conv = ToneColorConverter(str(cfg), device=device)
            try:
                conv.load_ckpt(str(ckpt))
            except Exception:
                if not self._s.allow_unsafe_checkpoint:
                    raise
                log.warning("safe checkpoint load failed; retrying with full pickle (VB_ALLOW_UNSAFE_CHECKPOINT=1)")
                data = torch.load(str(ckpt), map_location=device, weights_only=False)
                conv.model.load_state_dict(data["model"], strict=False)

            self._converter, self._torch = conv, torch
            self._device = device
            self._sample_rate = int(conv.hps.data.sampling_rate)
            self._watermark_active = (
                getattr(conv, "watermark_model", None) is not None if hasattr(conv, "watermark_model") else self._s.openvoice_watermark
            )
            self._set("ready", None)
            log.info("model_ready engine=%s device=%s sample_rate=%s watermark=%s", self.id, device, self._sample_rate, self._watermark_active)
        except ServiceError as e:
            self._set("unavailable", e.message)
        except ImportError as e:
            pkg = getattr(e, "name", None) or "a required package"
            hint = " Install it, or set VB_OPENVOICE_WATERMARK=0 to disable the optional watermark." if pkg == "wavmark" else ""
            self._set("unavailable", f"Python package '{pkg}' is missing or failed to import. See README, 'Install OpenVoice'.{hint}")
            log.exception("model_import_failed")
        except Exception:
            log.exception("model_load_failed")
            self._set(
                "error",
                "The model files were found but failed to load (see the server log). If the log mentions weights_only or "
                "UnpicklingError and the file came from the official MyShell source, you may set VB_ALLOW_UNSAFE_CHECKPOINT=1.",
            )

    # ---- inference ----------------------------------------------------
    def _require_ready(self) -> None:
        st = self.status()
        if st.state != "ready" or self._converter is None:
            raise ServiceError("model_not_ready", st.reason or "The voice model is not ready.")

    def create_profile(self, wav_paths: list[Path], out_path: Path) -> dict:
        self._require_ready()
        try:
            se = self._converter.extract_se([str(p) for p in wav_paths])
            if not hasattr(se, "detach"):
                raise ServiceError("inference_failed", "The model did not return a speaker embedding.")
            se = se.detach().cpu()
            self._torch.save(se, str(out_path))
            return {"embedding_shape": list(se.shape), "clips": len(wav_paths)}
        except ServiceError:
            raise
        except Exception:
            log.exception("create_profile_failed")
            raise ServiceError("enrollment_failed", "The voice model could not build a speaker embedding from this recording.")

    def convert(self, source_wav: Path, profile_path: Path, out_wav: Path) -> dict:
        self._require_ready()
        torch = self._torch
        try:
            tgt_se = torch.load(str(profile_path), map_location=self._device, weights_only=True)
            src_se = self._converter.extract_se([str(source_wav)])
            kwargs = dict(audio_src_path=str(source_wav), src_se=src_se, tgt_se=tgt_se, output_path=str(out_wav), tau=self._s.openvoice_tau)
            if self._watermark_active:
                kwargs["message"] = "voicebridge"
            self._converter.convert(**kwargs)
            return {"tau": self._s.openvoice_tau, "watermark": self._watermark_active}
        except Exception:
            log.exception("convert_failed")
            raise ServiceError("inference_failed", "The voice model failed while converting this audio. Check the server log.")
