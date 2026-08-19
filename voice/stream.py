"""voice/stream.py — sentence splitter + chunk queue + cancel.

Manages the streaming pipeline: splits reply text into sentences,
sends each to TTS, queues audio chunks for device playback, and
handles barge-in cancellation.

See docs/component-15 §5.
"""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import AsyncIterator

from voice.tts import TextToSpeech, split_sentences

log = logging.getLogger("don.voice.stream")


class AudioChunkQueue:
    """Async queue of audio chunks for device playback."""

    def __init__(self):
        self._queue: deque[tuple[str, bytes]] = deque()
        self._cancelled = False
        self._event = asyncio.Event()

    def push(self, sentence: str, audio: bytes) -> None:
        self._queue.append((sentence, audio))
        self._event.set()

    async def next(self, timeout: float = 30.0) -> tuple[str, bytes] | None:
        """Get next chunk. Returns None on timeout or cancel."""
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return None
        if self._cancelled:
            return None
        if self._queue:
            return self._queue.popleft()
        self._event.clear()
        return None

    def cancel(self) -> None:
        """Cancel remaining chunks (barge-in)."""
        self._cancelled = True
        self._queue.clear()
        self._event.set()

    def reset(self) -> None:
        self._cancelled = False
        self._queue.clear()
        self._event.clear()

    @property
    def is_done(self) -> bool:
        return self._cancelled or (not self._queue and not self._event.is_set())


class VoiceStreamManager:
    """Manages the streaming TTS pipeline for a single reply.

    Usage:
        manager = VoiceStreamManager(tts)
        # start streaming in background
        asyncio.create_task(manager.stream_reply(reply_text))
        # read chunks for device playback
        chunk = await manager.queue.next()
    """

    def __init__(self, tts: TextToSpeech):
        self.tts = tts
        self.queue = AudioChunkQueue()

    async def stream_reply(self, text: str) -> None:
        """Split text into sentences and stream TTS audio chunks.

        Runs as an async task. Chunks are pushed to self.queue.
        """
        self.queue.reset()
        sentences = split_sentences(text)

        for sentence in sentences:
            if self.queue._cancelled:
                log.info("stream cancelled (barge-in)")
                break
            try:
                audio = self.tts.synthesize(sentence)
                if audio:
                    self.queue.push(sentence, audio)
            except Exception as exc:  # noqa: BLE001
                log.error("stream sentence error: %s", exc)

        # signal completion
        self.queue.push("", b"")

    def cancel(self) -> None:
        """Cancel the stream (barge-in triggered)."""
        self.queue.cancel()
