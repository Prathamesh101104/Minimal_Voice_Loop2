#!/usr/bin/env python3
"""Simulate Vobiz WebSocket call to test voice capture locally."""
import asyncio
import json
import base64
import websockets
import uuid
from datetime import datetime

STREAM_URL = "ws://127.0.0.1:8000/api/phone/vobiz-stream"

async def test_vobiz_stream():
    """Simulate a Vobiz call with start event, media frames, and monitoring."""
    call_id = str(uuid.uuid4())
    stream_id = str(uuid.uuid4())
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Simulating Vobiz call: {call_id}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Stream URL: {STREAM_URL}")
    
    try:
        async with websockets.connect(STREAM_URL) as ws:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Connected to server")
            
            # Send "start" event
            start_event = {
                "event": "start",
                "start": {
                    "streamId": stream_id,
                    "callId": call_id,
                    "from": "+1234567890",
                    "to": "+1111111111",
                    "mediaFormat": {
                        "encoding": "audio/x-l16",
                        "sampleRate": 8000
                    }
                }
            }
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Sending start event...")
            await ws.send(json.dumps(start_event))
            
            # Wait a bit for server to process and send greeting
            await asyncio.sleep(0.5)
            
            # Send some audio frames (simulate caller audio - silence)
            for frame_num in range(5):
                # Create silent PCM frames (320 bytes = 160 samples at 16-bit)
                silent_frame = b'\x00' * 320
                
                media_event = {
                    "event": "media",
                    "streamId": stream_id,
                    "media": {
                        "payload": base64.b64encode(silent_frame).decode(),
                        "contentType": "audio/x-l16",
                        "sampleRate": 8000,
                        "track": "inbound"
                    }
                }
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Sending media frame {frame_num + 1}...")
                await ws.send(json.dumps(media_event))
                await asyncio.sleep(0.02)  # 20ms per frame
            
            # Listen for responses from server
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Listening for server responses...")
            try:
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    try:
                        data = json.loads(msg)
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Server event: {data.get('event', 'unknown')}")
                        if data.get('event') == 'playAudio':
                            audio_len = len(base64.b64decode(data.get('media', {}).get('payload', '')))
                            print(f"[{datetime.now().strftime('%H:%M:%S')}]   - Audio payload: {audio_len} bytes")
                    except json.JSONDecodeError:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Server sent binary: {len(msg)} bytes")
            except asyncio.TimeoutError:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] No more messages from server")
            
            # Send stop event
            stop_event = {
                "event": "stop",
                "streamId": stream_id
            }
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Sending stop event...")
            await ws.send(json.dumps(stop_event))
            await asyncio.sleep(0.5)
            
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Error: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Test complete")

if __name__ == "__main__":
    asyncio.run(test_vobiz_stream())
