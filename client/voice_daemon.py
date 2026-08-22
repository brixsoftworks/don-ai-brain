"""client/voice_daemon.py — DON Jarvis Voice Assistant.

Wires up the existing voice/ modules (wake, stt, tts, vad) into a single loop.
Each component is an open-source library installed from GitHub/PyPI.

Pipeline:
  OpenWakeWord  →  Silero VAD  →  faster-whisper  →  Gemini LLM  →  Kokoro TTS
      wake             silence         transcribe         think           speak
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import queue
import random
import re
import subprocess
import sys
import threading
import datetime
from collections import deque
from pathlib import Path

import numpy as np
import sounddevice as sd
from openai import AsyncOpenAI

# Add project root to path so voice/ modules can be found
_PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(_PROJECT_DIR))


# ─────────────────────────────────────────
#  Logging
# ─────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("don")

# Suppress noisy sub-module logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("faster_whisper").setLevel(logging.WARNING)
logging.getLogger("openwakeword").setLevel(logging.WARNING)

# ─────────────────────────────────────────
#  Configuration
# ─────────────────────────────────────────
PROJECT_DIR = Path(__file__).resolve().parent.parent
GEMINI_KEY  = os.environ["GEMINI_API_KEY"]
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"
MODEL_NAME  = "gemini-3.1-flash-lite"

SAMPLE_RATE   = 16000
CHUNK_MS      = 32          # ms per audio chunk (matches OWW's 1280 sample frames)
CHUNK_FRAMES  = int(SAMPLE_RATE * CHUNK_MS / 1000)  # = 1280
MAX_HISTORY   = 20          # conversation turns to remember
SILENCE_MS    = 1500        # ms of silence → end of utterance
SILENCE_CHUNKS = int(SILENCE_MS / CHUNK_MS)

SLEEP_WORDS = ["stop listening", "goodbye", "bye", "exit", "go to sleep", "sleep",
               "nevermind", "never mind", "that's all"]

# ─────────────────────────────────────────
#  smolagents LLM orchestration
# ─────────────────────────────────────────
from smolagents import ToolCallingAgent, LiteLLMModel
try:
    from client.agent_tools import execute_bash_command, get_time_date, run_web_automation
    _tools = [execute_bash_command, get_time_date, run_web_automation]
except ImportError:
    _tools = []
    log.warning("Could not import agent_tools.")

model = LiteLLMModel(
    model_id=f"gemini/{MODEL_NAME}",
    api_key=GEMINI_KEY,
)

agent = ToolCallingAgent(
    tools=_tools,
    model=model,
)
if "system_prompt" in agent.prompt_templates:
    agent.prompt_templates["system_prompt"] = "You are DON — a calm, capable, and slightly intimidating AI assistant. You run on the user's own machine with full control: system, web, apps, files. Reply concisely (1-2 sentences max for voice). Use tools to complete tasks. For pure conversation, reply directly.\n" + agent.prompt_templates["system_prompt"]

async def llm_call(user_text: str) -> str:
    """Call smolagents ToolCallingAgent."""
    try:
        reply = await asyncio.get_event_loop().run_in_executor(None, agent.run, user_text)
        return str(reply).strip()
    except Exception as exc:
        log.error("llm error: %s", exc)
        return "I ran into an issue, please try again."


# ─────────────────────────────────────────
#  TTS (Kokoro / edge-tts)
# ─────────────────────────────────────────
_tts_lock = threading.Lock()
_tts = None  # Lazy-loaded
_is_speaking = False


def _load_tts():
    global _tts
    if _tts is not None:
        return _tts
    sys.path.insert(0, str(PROJECT_DIR))
    from voice.tts import TextToSpeech
    _tts = TextToSpeech()
    if not _tts.load():
        log.warning("tts: all backends failed, using espeak fallback")
        _tts = None
    return _tts


def speak(text: str) -> None:
    """Speak text in a background thread (non-blocking)."""
    def _speak():
        global _is_speaking
        _is_speaking = True
        try:
            with _tts_lock:
                tts = _load_tts()
                if tts:
                    log.info("🔊 DON: %s", text)
                    print(f"\n🔊 DON: {text}")
                    audio = tts.synthesize(text)
                    tts.play(audio)
                else:
                    # espeak ultimate fallback
                    log.info("🔊 DON (espeak): %s", text)
                    print(f"\n🔊 DON: {text}")
                    subprocess.run(["espeak", "-s", "140", "-p", "30", text],
                                   capture_output=True)
        finally:
            _is_speaking = False

    threading.Thread(target=_speak, daemon=True).start()


# ─────────────────────────────────────────
#  Local fast-path commands (no LLM)
# ─────────────────────────────────────────
def handle_local(text: str) -> str | None:
    t = text.lower().strip()

    if any(x in t for x in ["what time", "what's the time", "current time"]):
        return datetime.datetime.now().strftime("It's %I:%M %p")

    if any(x in t for x in ["what day", "what's the date", "today's date"]):
        return datetime.datetime.now().strftime("Today is %A, %B %d")

    m = re.search(r"set volume to (\d+)", t)
    if m:
        vol = min(int(m.group(1)), 100)
        subprocess.run(f"pactl set-sink-volume @DEFAULT_SINK@ {vol}%", shell=True)
        return f"Volume set to {vol} percent"

    if any(x in t for x in ["mute", "silence"]):
        subprocess.run("pactl set-sink-mute @DEFAULT_SINK@ toggle", shell=True)
        return "Muted"

    if any(x in t for x in ["volume up", "louder"]):
        subprocess.run("pactl set-sink-volume @DEFAULT_SINK@ +10%", shell=True)
        return "Volume up"

    if any(x in t for x in ["volume down", "quieter"]):
        subprocess.run("pactl set-sink-volume @DEFAULT_SINK@ -10%", shell=True)
        return "Volume down"

    return None


# ─────────────────────────────────────────
#  Run bash command
# ─────────────────────────────────────────
def run_command(cmd: str) -> str:
    """Execute bash command. Web agent tasks run async."""
    if not cmd:
        return ""
    log.info("⚙️  Running: %s", cmd)
    print(f"  ⚙️  Running: {cmd}")

    if cmd.startswith("python client/web_agent.py"):
        # Run web agent, capture its Final Result line
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                cwd=str(PROJECT_DIR), timeout=180,
            )
            for line in reversed(result.stdout.splitlines()):
                if "Final Result:" in line:
                    return line.split("Final Result:", 1)[1].strip()
            
            if result.returncode != 0:
                err = result.stderr.strip()
                if not err:
                    err = result.stdout.strip()
                # Return the last 300 chars of the error
                return f"Web task failed: {err[-300:]}"
                
            # If no Final Result but code 0, it probably succeeded without returning a specific string
            return "Web task finished successfully."
        except subprocess.TimeoutExpired:
            return "That web task is taking too long."
        except Exception as exc:
            return f"Command failed: {exc}"
    else:
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                cwd=str(PROJECT_DIR), timeout=30,
            )
            return (result.stdout or result.stderr or "Done.").strip()[:300]
        except Exception as exc:
            return f"Error: {exc}"


# ─────────────────────────────────────────
#  Audio capture (shared ring buffer)
# ─────────────────────────────────────────
_audio_q: queue.Queue = queue.Queue()


def _audio_callback(indata, frames, time_info, status):
    """sounddevice callback — pushes raw chunks into queue."""
    _audio_q.put(bytes(indata))


# ─────────────────────────────────────────
#  Wake word detection (OpenWakeWord)
# ─────────────────────────────────────────
def _load_wake():
    from voice.wake import WakeWordDetector
    det = WakeWordDetector()
    ok = det.load()
    if not ok:
        log.warning("wake: openwakeword failed to load, using text-only detection")
    return det


# ─────────────────────────────────────────
#  STT — faster-whisper
# ─────────────────────────────────────────
def _load_stt():
    from voice.stt import SpeechToText
    stt = SpeechToText()
    stt.load()
    return stt


# ─────────────────────────────────────────
#  VAD — Silero
# ─────────────────────────────────────────
def _load_vad():
    try:
        from voice.vad import VoiceActivityDetector
        vad = VoiceActivityDetector()
        vad.load()
        return vad
    except Exception as exc:
        log.warning("vad: silero failed: %s — using energy-based fallback", exc)
        return None


def _is_speech(audio_bytes: bytes, vad) -> bool:
    """Return True if the chunk contains speech."""
    if vad is not None:
        try:
            audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            return vad.is_speech(audio) > 0.5
        except Exception:
            pass
    # Energy fallback
    audio = np.frombuffer(audio_bytes, dtype=np.int16)
    rms = np.sqrt(np.mean(audio.astype(np.float32) ** 2))
    return rms > 200


# ─────────────────────────────────────────
#  Record until silence
# ─────────────────────────────────────────
def collect_utterance(vad, stream) -> bytes:
    """Record audio chunks until silence detected. Returns raw PCM bytes."""
    print("  🎙️  Listening... (speak your command)")
    chunks = []
    silence_count = 0

    while True:
        try:
            chunk = _audio_q.get(timeout=0.5)
        except queue.Empty:
            continue

        if _is_speaking:
            # Ignore audio while DON is speaking
            chunks.clear()
            silence_count = 0
            continue

        chunks.append(chunk)
        if _is_speech(chunk, vad):
            silence_count = 0
        else:
            silence_count += 1
            if len(chunks) > 5 and silence_count >= SILENCE_CHUNKS:
                break

    return b"".join(chunks)


# ─────────────────────────────────────────
#  Main voice loop
# ─────────────────────────────────────────
async def voice_loop():
    print("\n  🔧 Loading voice components...")

    # Load components
    stt = _load_stt()
    vad = _load_vad()

    from voice.wake import WAKE_ALIASES

    print("✅ DON is ready. Say 'Hey DON' to wake me up.\n")
    speak("DON is online and ready.")
    print("  👂 Listening for wake word...\n")

    with sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        blocksize=CHUNK_FRAMES,
        dtype="int16",
        channels=1,
        callback=_audio_callback,
    ) as stream:

        while True:
            # 1. Wait for speech to start via VAD
            speech_started = False
            first_chunk = None
            while not _audio_q.empty():
                chunk = _audio_q.get()
                if _is_speaking:
                    continue
                if _is_speech(chunk, vad):
                    speech_started = True
                    first_chunk = chunk
                    break

            if not speech_started:
                await asyncio.sleep(0.05)
                continue

            # 2. Record utterance
            raw_audio = await asyncio.get_event_loop().run_in_executor(
                None, collect_utterance, vad, stream
            )
            
            # Prepend the trigger chunk so we don't clip the first 80ms
            if first_chunk and raw_audio:
                raw_audio = first_chunk + raw_audio

            if not raw_audio or len(raw_audio) < SAMPLE_RATE // 2:
                continue

            # 3. Transcribe utterance
            text = await asyncio.get_event_loop().run_in_executor(
                None, stt.transcribe_bytes, raw_audio
            )
            text = text.lower().strip()
            if not text:
                continue
                
            print(f"  [Transcribed: {text}]")

            # 4. Filter for wake word
            is_wake = False
            cmd_text = text
            for alias in WAKE_ALIASES:
                if alias in text:
                    is_wake = True
                    # Strip wake word, keep remaining command
                    cmd_text = text.replace(alias, "").strip()
                    # Remove any punctuation left behind
                    if cmd_text.startswith((",", ".", "-", " ", "!", "?")):
                        cmd_text = cmd_text.lstrip(",.- !?")
                    break

            if not is_wake:
                continue

            # ── Woken up! ──
            print(f"\n🔔 Wake word detected! [Heard: {text}]")
            
            if not cmd_text:
                responses = [
                    "Yes Boss. The universe is yours to command.",
                    "Yes Boss. Awaiting your grand design.",
                    "Yes Boss. I stand ready to alter reality at your word.",
                    "Yes Boss. Your wish is my absolute directive.",
                    "Yes Boss. How may I serve your brilliant intellect today?"
                ]
                speak(random.choice(responses))
                await asyncio.sleep(0.5)

            # ── Conversation loop ──
            print("  🎙️  Conversation mode (say 'sleep' to stop)\n")
            
            while True:
                if not cmd_text:
                    # Flush stale audio
                    while not _audio_q.empty():
                        _audio_q.get()

                    raw_audio = await asyncio.get_event_loop().run_in_executor(
                        None, collect_utterance, vad, stream
                    )

                    if not raw_audio or len(raw_audio) < SAMPLE_RATE // 2:
                        log.warning("utterance too short, going back to sleep")
                        speak("Going to sleep.")
                        break

                    print("  🧠 Transcribing...")
                    cmd_text = await asyncio.get_event_loop().run_in_executor(
                        None, stt.transcribe_bytes, raw_audio
                    )
                    # Strip punctuation that might be hallucinated
                    cmd_text = cmd_text.strip(" ,.-!?\n\t")
                    
                    # Filter common whisper silence hallucinations
                    lower_cmd = cmd_text.lower()
                    if lower_cmd in ["thank you", "thank you.", "thanks", "subscribe", "subscribe.", "amen", ""]:
                        cmd_text = ""
                    
                if not cmd_text:
                    continue

                print(f"  💬 You: {cmd_text}")

                if any(s in cmd_text.lower() for s in SLEEP_WORDS):
                    speak("Okay, going to sleep.")
                    print("  💤 Back to wake word mode.\n")
                    break

                # Local fast-path
                local = handle_local(cmd_text)
                if local:
                    speak(local)
                    cmd_text = ""
                    continue

                # Immediate auditory feedback for likely long-running tasks
                lower_cmd = cmd_text.lower()
                if any(w in lower_cmd for w in ["whatsapp", "instagram", "web", "browser", "chrome", "open"]):
                    speak("I am on it, sir.")
                elif any(w in lower_cmd for w in ["volume", "brightness", "terminal", "system"]):
                    speak("Executing.")

                # LLM
                print("  🤖 Thinking...")
                reply = await llm_call(cmd_text)

                speak(reply or "Done.")
                cmd_text = ""

            print("  👂 Listening for wake word...\n")


# ─────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────
async def main():
    while True:
        try:
            await voice_loop()
        except KeyboardInterrupt:
            print("\n👋 DON shutting down.")
            break
        except Exception as exc:
            log.error("voice loop crashed: %s — restarting in 3s", exc)
            await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
