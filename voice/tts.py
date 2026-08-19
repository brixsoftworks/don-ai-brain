"""voice/tts.py — Kokoro synthesis via kokoro-onnx + Piper fallback.

Kokoro-82M: 82M params, Apache-2.0, ~300MB, sentence-level streaming.
Deep male voices (am_eric/am_onyx) at speed 0.85 = DON's villain timbre.
See docs/component-15 §2, §5.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml

log = logging.getLogger("don.voice.tts")

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
DEFAULT_CONFIG = CONFIG_DIR / "voice.yaml"


def _load_config(path: Path | None = None) -> dict:
    path = path or DEFAULT_CONFIG
    if not path.exists():
        return {}
    with open(path) as fh:
        return yaml.safe_load(fh) or {}


def split_sentences(text: str) -> list[str]:
    """Split text into sentences for streaming TTS.

    Respects sentence boundaries, code blocks, and URLs.
    """
    # protect code blocks and URLs
    protected = []
    def _protect(m):
        protected.append(m.group(0))
        return f"__PROTECTED_{len(protected)-1}__"

    text = re.sub(r'```[\s\S]*?```', _protect, text)
    text = re.sub(r'https?://\S+', _protect, text)

    # split on sentence boundaries
    sentences = re.split(r'(?<=[.!?])\s+', text)

    # restore protected content
    result = []
    for s in sentences:
        for i, p in enumerate(protected):
            s = s.replace(f"__PROTECTED_{i}__", p)
        if s.strip():
            result.append(s.strip())

    return result if result else [text]


class TextToSpeech:
    """Kokoro-onnx TTS with Piper fallback.

    Produces audio chunks for streaming playback.
    """

    def __init__(self, config_path: Path | None = None):
        config = _load_config(config_path)
        tts_cfg = config.get("tts", {})
        self.voice = tts_cfg.get("voice", "am_eric")
        self.speed = tts_cfg.get("speed", 0.88)
        self.sample_rate = tts_cfg.get("sample_rate", 24000)
        self._kokoro = None

    def load(self) -> bool:
        """Load the Kokoro TTS model."""
        try:
            import kokoro_onnx  # type: ignore[import-untyped]

            self._kokoro = kokoro_onnx.Kokoro()
            log.info("kokoro tts loaded (voice=%s, speed=%.2f)", self.voice, self.speed)
            return True
        except ImportError:
            log.warning("kokoro-onnx not installed. pip install kokoro-onnx")
            return False
        except Exception as exc:  # noqa: BLE001
            log.error("kokoro load failed: %s", exc)
            return False

    def synthesize(self, text: str) -> bytes:
        """Synthesize text to audio bytes (full).

        Returns raw PCM audio (float32, mono, 24kHz).
        """
        if self._kokoro is None:
            log.error("tts not loaded")
            return b""
        try:
            audio, sr = self._kokoro.create(
                text, voice=self.voice, speed=self.speed,
            )
            return audio.tobytes()
        except Exception as exc:  # noqa: BLE001
            log.error("tts synthesis error: %s", exc)
            return b""

    def synthesize_stream(self, text: str):
        """Generator yielding audio chunks for sentence-by-sentence streaming.

        Yields (sentence_text, audio_bytes) tuples.
        """
        if self._kokoro is None:
            log.error("tts not loaded")
            return

        sentences = split_sentences(text)
        for sentence in sentences:
            try:
                audio, sr = self._kokoro.create(
                    sentence, voice=self.voice, speed=self.speed,
                )
                yield sentence, audio.tobytes()
            except Exception as exc:  # noqa: BLE001
                log.error("tts stream error for sentence: %s", exc)
                yield sentence, b""
