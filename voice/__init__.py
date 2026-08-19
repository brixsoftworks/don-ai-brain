"""voice — voice pipeline: wake word, VAD, STT, TTS, streaming.

Stack: Heed (wake) + Silero VAD + whisper.cpp (STT) + Kokoro (TTS).
See docs/component-15.
"""
