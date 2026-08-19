import os
import time
import json
import asyncio
import websockets
import pyttsx3
import speech_recognition as sr

try:
    import openwakeword
    from openwakeword.model import Model
except ImportError:
    print("Warning: openwakeword not installed correctly. Wake word will use SpeechRecognition fallback.")
    openwakeword = None

CLOUD_URL = "wss://don-ai-brain.onrender.com/ws/laptop" # Now pointing to Render Cloud
WAKE_WORD_MODEL = "hey_jarvis" # Using pre-built model for now until we train 'hey don'

engine = pyttsx3.init()
engine.setProperty('rate', 170)

def speak(text):
    print(f"DON: {text}")
    engine.say(text)
    engine.runAndWait()

def listen_for_command():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        r.adjust_for_ambient_noise(source, duration=0.5)
        print("Listening for command...")
        try:
            audio = r.listen(source, timeout=5, phrase_time_limit=10)
            text = r.recognize_google(audio)
            print(f"You: {text}")
            return text
        except sr.WaitTimeoutError:
            return None
        except sr.UnknownValueError:
            print("Didn't catch that.")
            return None
        except Exception as e:
            print(f"Microphone error: {e}")
            return None

async def voice_client():
    print(f"Connecting to DON Voice Hub at {CLOUD_URL}...")
    try:
        async with websockets.connect(CLOUD_URL) as websocket:
            print("Connected! Voice Daemon running in background.")
            
            # Setup Wake Word Model
            if openwakeword:
                openwakeword.utils.download_models()
                oww_model = Model(wakeword_models=[WAKE_WORD_MODEL])
                print(f"Listening for '{WAKE_WORD_MODEL.replace('_', ' ')}'...")
            else:
                oww_model = None

            # To avoid high CPU, we need a PyAudio stream
            import pyaudio
            import numpy as np

            p = pyaudio.PyAudio()
            stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1280)

            while True:
                # 1. Listen for wake word
                if oww_model:
                    audio_chunk = np.frombuffer(stream.read(1280, exception_on_overflow=False), dtype=np.int16)
                    prediction = oww_model.predict(audio_chunk)
                    
                    if prediction[WAKE_WORD_MODEL] > 0.5:
                        print("Wake word detected!")
                        speak("Yes?")
                        stream.stop_stream()
                        
                        # 2. Record full sentence
                        cmd = listen_for_command()
                        if cmd:
                            # 3. Send to DON
                            await websocket.send(json.dumps({
                                "id": str(time.time()),
                                "tool": "voice_prompt",
                                "args": {"prompt": cmd}
                            }))
                            
                            # 4. Await response
                            resp_str = await websocket.recv()
                            resp = json.loads(resp_str)
                            speak(resp.get('result', 'Done'))
                        
                        stream.start_stream()
                else:
                    await asyncio.sleep(1)

    except Exception as e:
        print(f"Connection lost: {e}")

if __name__ == "__main__":
    asyncio.run(voice_client())
