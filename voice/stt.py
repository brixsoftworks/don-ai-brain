"""voice/stt.py — whisper.cpp transcription (streaming, small model).

Best ARM CPU STT: handwritten NEON SIMD, single C++ binary, ~460MB.
See docs/component-15 §2, §4.
"""
from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

import yaml

log = logging.getLogger("don.voice.stt")

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
DEFAULT_CONFIG = CONFIG_DIR / "voice.yaml"


def _load_config(path: Path | None = None) -> dict:
    path = path or DEFAULT_CONFIG
    if not path.exists():
        return {}
    with open(path) as fh:
        return yaml.safe_load(fh) or {}


class SpeechToText:
    """whisper.cpp based STT for ARM CPU transcription."""

    def __init__(self, config_path: Path | None = None):
        config = _load_config(config_path)
        stt_cfg = config.get("stt", {})
        self.model_size = stt_cfg.get("model", "small")
        self.binary_path = stt_cfg.get("binary_path", "whisper-cli")
        self.threads = stt_cfg.get("threads", 4)
        self.language = stt_cfg.get("language", "en")

    def transcribe_file(self, audio_path: str | Path) -> str:
        """Transcribe an audio file to text.

        Args:
            audio_path: path to audio file (wav, mp3, etc.).
        Returns:
            transcribed text.
        """
        try:
            result = subprocess.run(
                [
                    self.binary_path,
                    "-m", self.model_size,
                    "-t", str(self.threads),
                    "-l", self.language,
                    "-f", str(audio_path),
                    "--no-prints",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                log.error("whisper failed: %s", result.stderr)
                return ""
            return result.stdout.strip()
        except FileNotFoundError:
            log.error("whisper-cli not found at %s", self.binary_path)
            return "[whisper.cpp not installed]"
        except subprocess.TimeoutExpired:
            log.error("whisper transcription timed out")
            return "[transcription timed out]"
        except Exception as exc:  # noqa: BLE001
            log.error("whisper error: %s", exc)
            return f"[stt error: {exc}]"

    def transcribe_bytes(self, audio_bytes: bytes, sample_rate: int = 16000) -> str:
        """Transcribe raw audio bytes.

        Writes to a temp file, transcribes, cleans up.
        """
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            return self.transcribe_file(tmp_path)
        finally:
            Path(tmp_path).unlink(missing_ok=True)
