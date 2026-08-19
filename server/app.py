import asyncio
import json
import logging
import os
from typing import Dict, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from openai import AsyncOpenAI

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="DON Cloud Hub")

# Mount the static directory to serve the mobile web UI
app.mount("/ui", StaticFiles(directory="server/static", html=True), name="static")

# Connected clients
active_laptop: WebSocket | None = None
active_phone: WebSocket | None = None
pending_responses: Dict[str, asyncio.Future] = {}

# Initialize OpenAI Client (using OpenRouter for free models)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if OPENROUTER_API_KEY:
    client = AsyncOpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1"
    )
else:
    client = None
    logging.warning("OPENROUTER_API_KEY not found! LLM commands will fail.")

@app.websocket("/ws/laptop")
async def laptop_endpoint(websocket: WebSocket):
    global active_laptop
    await websocket.accept()
    active_laptop = websocket
    logging.info("Laptop worker connected!")
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            call_id = payload.get("id")
            if call_id in pending_responses:
                pending_responses[call_id].set_result(payload.get("result", ""))
    except WebSocketDisconnect:
        logging.info("Laptop worker disconnected.")
        active_laptop = None

@app.websocket("/ws/phone")
async def phone_endpoint(websocket: WebSocket):
    global active_phone, active_laptop
    await websocket.accept()
    active_phone = websocket
    logging.info("Phone connected!")
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            
            tool = payload.get("tool")
            if tool == "voice_prompt":
                prompt = payload.get("args", {}).get("prompt", "")
                logging.info(f"Received voice prompt from phone: {prompt}")
                
                if active_laptop is None:
                    await websocket.send_text("Laptop worker is offline.")
                    continue
                
                if not client:
                    await websocket.send_text("LLM API not configured.")
                    continue

                # 1. Ask OpenRouter what terminal command to run
                try:
                    response = await client.chat.completions.create(
                        model="openrouter/free",
                        messages=[
                            {"role": "system", "content": "You are a Linux terminal agent. Respond with ONLY a JSON object containing the exact bash command to fulfill the request. Example: {\"command\": \"date\"}. No other text or markdown is allowed."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0,
                        max_tokens=150
                    )
                    content = response.choices[0].message.content.strip()
                    
                    # Try to extract JSON if the model added padding
                    if "{" in content and "}" in content:
                        content = content[content.find("{"):content.rfind("}")+1]
                        
                    try:
                        data = json.loads(content)
                        bash_command = data.get("command", content)
                    except json.JSONDecodeError:
                        bash_command = content.replace("```bash", "").replace("```", "").strip()
                    
                    logging.info(f"AI decided to run: {bash_command}")
                    
                    # 2. Forward execution command to the laptop
                    call_id = f"cmd-{asyncio.get_event_loop().time()}"
                    future = asyncio.get_event_loop().create_future()
                    pending_responses[call_id] = future
                    
                    await active_laptop.send_text(json.dumps({
                        "id": call_id,
                        "tool": "run_command",
                        "args": {"command": bash_command}
                    }))
                    
                    # 3. Wait for laptop to execute
                    result = await asyncio.wait_for(future, timeout=30.0)
                    del pending_responses[call_id]
                    
                    # 4. Notify the phone
                    await websocket.send_text(f"Executed: {bash_command[:50]}... Result: {str(result)[:50]}")
                    
                except Exception as e:
                    logging.error(f"Error processing command: {e}")
                    await websocket.send_text(f"Error: {e}")
                    
    except WebSocketDisconnect:
        logging.info("Phone disconnected.")
        active_phone = None
