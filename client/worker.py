import asyncio
import json
import websockets
import subprocess
import os

# Default to localhost for local testing, but allow overriding via environment variable
BASE_URL = os.getenv("RENDER_URL", "ws://localhost:8000")
# Make sure it uses wss:// if it's an https url, or ws:// if not provided correctly
if BASE_URL.startswith("http://"):
    BASE_URL = BASE_URL.replace("http://", "ws://")
elif BASE_URL.startswith("https://"):
    BASE_URL = BASE_URL.replace("https://", "wss://")

CLOUD_URL = f"{BASE_URL}/ws/laptop"

async def connect_to_cloud():
    print(f"Connecting to DON Cloud Hub at {CLOUD_URL}...")
    try:
        async with websockets.connect(CLOUD_URL) as websocket:
            print("Connected as Remote Worker!")
            while True:
                msg = await websocket.recv()
                payload = json.loads(msg)
                print(f"Received tool execution request: {payload['tool']}")
                
                # Execute native shell commands
                if payload['tool'] == 'run_command':
                    cmd = payload['args'].get('command', 'echo no-op')
                    print(f"Executing: {cmd}")
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                    output = result.stdout + result.stderr
                    if not output:
                        output = "Success (no output)"
                else:
                    output = f"Tool {payload['tool']} not implemented on worker yet."
                    
                await websocket.send(json.dumps({
                    "id": payload['id'],
                    "result": output
                }))
    except Exception as e:
        print(f"Connection failed: {e}. Retrying in 5 seconds...")
        await asyncio.sleep(5)
        await connect_to_cloud()

if __name__ == "__main__":
    asyncio.run(connect_to_cloud())
