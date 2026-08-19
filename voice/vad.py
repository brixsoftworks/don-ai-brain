"""voice/vad.py — Silero VAD v6.2 wrapper.

Voice activity detection: start/end/barge-in. ~2MB, <1ms/chunk.
See docs/component-15 §2.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import yaml

log = logging.getLogger("don.voice.vad")

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
DEFAULT_CONFIG = CONFIG_DIR / "voice.yaml"


def _load_config(path: Path | None = None) -> dict:
    path = path or DEFAULT_CONFIG
    if not path.exists():
        return {}
    with open(path) as fh:
        return yaml.safe_load(fh) or {}


class VoiceActivityDetector:
    """Silero VAD wrapper for speech detection and barge-in."""

    def __init__(self, config_path: Path | None = None):
        config = _load_config(config_path)
        vad_cfg = config.get("vad", {})
        self.sample_rate = vad_cfg.get("sample_rate", 16000)
        self.threshold = vad_cfg.get("threshold", 0.5)
        self.silence_duration_ms = vad_cfg.get("silence_duration_ms", 600)
        self._model = None
        self._state = None

    def load(self) -> bool:
        """Load Silero VAD model."""
        try:
            import torch

            model, utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                trust_repo=True,
            )
            self._model = model
            self._utils = utils
            log.info("silero vad loaded")
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("silero vad load failed: %s", exc)
            return False

    def is_speech(self, audio_chunk: np.ndarray) -> float:
        """Return speech probability for an audio chunk.

        Args:
            audio_chunk: numpy array of float32 samples (16kHz).
        Returns:
            probability of speech (0.0–1.0).
        """
        if self._model is None:
            return 0.0
        try:
            import torch

            tensor = torch.from_numpy(audio_chunk).float()
            if tensor.dim() == 1:
                tensor = tensor.unsqueeze(0)
            prob = self._model(tensor, self.sample_rate).item()
            return prob
        except Exception as exc:  # noqa: BLE001
            log.error("vad detection error: %s", exc)
            return 0.0

    def detect_barge_in(self, audio_chunk: np.ndarray) -> bool:
        """Detect if user is interrupting (barge-in) during TTS playback."""
        return self.is_speech(audio_chunk) > self.threshold
