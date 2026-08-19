"""voice/wake.py — Heed wake-word engine (custom "Hey DON" ONNX).

Heed trains a custom wake word in seconds, runs at 1–15ms inference,
108 KB model. See docs/component-15 §2.
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

log = logging.getLogger("don.voice.wake")

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
DEFAULT_CONFIG = CONFIG_DIR / "voice.yaml"


def _load_config(path: Path | None = None) -> dict:
    path = path or DEFAULT_CONFIG
    if not path.exists():
        return {}
    with open(path) as fh:
        return yaml.safe_load(fh) or {}


class WakeWordDetector:
    """Heed-based wake word detector for custom "Hey DON" detection.

    Wraps heed-wakeword (pip install heed-wakeword). The model is
    trained separately and loaded at init time.
    """

    def __init__(self, config_path: Path | None = None):
        config = _load_config(config_path)
        wake_cfg = config.get("wake", {})
        self.model_path = wake_cfg.get("model_path", "models/wake/hey_don.onnx")
        self.threshold = wake_cfg.get("threshold", 0.5)
        self._detector = None

    def load(self) -> bool:
        """Load the wake word model. Returns True on success."""
        try:
            from heed import WakeWordDetector as HeedDetector  # type: ignore[import-untyped]

            self._detector = HeedDetector(
                model_path=self.model_path,
                threshold=self.threshold,
            )
            log.info("wake word model loaded: %s", self.model_path)
            return True
        except ImportError:
            log.warning("heed-wakeword not installed. pip install heed-wakeword")
            return False
        except Exception as exc:  # noqa: BLE001
            log.error("wake model load failed: %s", exc)
            return False

    def detect(self, audio_chunk: bytes) -> bool:
        """Process an audio chunk and return True if wake word detected.

        Args:
            audio_chunk: raw PCM audio (16kHz, 16-bit, mono).
        """
        if self._detector is None:
            return False
        try:
            return self._detector.detect(audio_chunk)
        except Exception as exc:  # noqa: BLE001
            log.error("wake detect error: %s", exc)
            return False
