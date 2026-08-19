"""voice/bridge.py — device bridge integration (audio in/out).

Connects the voice pipeline to the device bridge: receives audio frames
from clients, runs STT, and streams TTS audio back.

See docs/component-15 §4, §5.
"""
from __future__ import annotations

import asyncio
import logging

import numpy as np

from voice.stt import SpeechToText
from voice.tts import TextToSpeech
from voice.vad import VoiceActivityDetector
from voice.stream import VoiceStreamManager
from voice.wake import WakeWordDetector

log = logging.getLogger("don.voice.bridge")


class VoiceBridge:
    """Connects voice components to the device WebSocket bridge.

    Handles:
    - Wake word detection (Heed)
    - VAD (Silero) for speech start/end + barge-in
    - STT (whisper.cpp) for transcription
    - TTS (Kokoro) streaming for replies
    """

    def __init__(
        self,
        stt: SpeechToText,
        tts: TextToSpeech,
        vad: VoiceActivityDetector,
        wake: WakeWordDetector | None = None,
    ):
        self.stt = stt
        self.tts = tts
        self.vad = vad
        self.wake = wake
        self.stream_manager = VoiceStreamManager(tts)
        self._listening = False

    def process_audio_frame(self, audio_bytes: bytes, sample_rate: int = 16000) -> dict:
        """Process a single audio frame from the device.

        Returns:
            dict with keys:
            - wake_detected: bool
            - speech_prob: float
            - is_speech: bool (above threshold)
        """
        result = {"wake_detected": False, "speech_prob": 0.0, "is_speech": False}

        # convert bytes to numpy
        audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        # check wake word (if not already listening)
        if self.wake and not self._listening:
            result["wake_detected"] = self.wake.detect(audio_bytes)
            if result["wake_detected"]:
                self._listening = True
                log.info("wake word detected, listening...")

        # VAD
        prob = self.vad.is_speech(audio)
        result["speech_prob"] = prob
        result["is_speech"] = prob > self.vad.threshold

        return result

    def transcribe_audio(self, audio_bytes: bytes) -> str:
        """Transcribe a complete utterance."""
        self._listening = False
        return self.stt.transcribe_bytes(audio_bytes)

    async def stream_tts_reply(self, text: str) -> None:
        """Stream TTS audio for a reply text."""
        await self.stream_manager.stream_reply(text)

    def cancel_stream(self) -> None:
        """Cancel ongoing TTS playback (barge-in)."""
        self.stream_manager.cancel()
        self._listening = False

    def reset(self) -> None:
        """Reset state for a new interaction."""
        self._listening = False
        self.stream_manager.queue.reset()
