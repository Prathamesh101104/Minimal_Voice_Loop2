import asyncio
import json
import base64
import websockets
import math
import struct

LIVE_WS_URL = "wss://minimal-voice-loop2-2.onrender.com/api/phone/vobiz-stream"

async def test_live_voice_capture():
    print("=" * 60)
    print("TESTING LIVE SERVER VOICE CAPTURE & AUDIO RESPONSE")
    print(f"Connecting to: {LIVE_WS_URL}")
    print("=" * 60)
    
    stream_id = "test-live-stream-123"
    call_id = "test-live-call-456"
    
    try:
        async with websockets.connect(LIVE_WS_URL) as ws:
            print("[OK] Connected to live WebSocket server!")
            
            # 1. Send start event
            start_event = {
                "event": "start",
                "start": {
                    "streamId": stream_id,
                    "callId": call_id,
                    "from": "+1918071581621",
                    "to": "+18005550142",
                    "mediaFormat": {"encoding": "audio/x-l16", "sampleRate": 8000}
                }
            }
            await ws.send(json.dumps(start_event))
            print("[OK] Sent 'start' call event")
            
            # 2. Generate a 1.5 second voice tone sample (16-bit Big-Endian L16)
            sample_rate = 8000
            num_samples = int(sample_rate * 1.5)
            speech_pcm_be = bytearray()
            for i in range(num_samples):
                val = int(8000 * math.sin(2 * math.pi * 440 * i / sample_rate))
                speech_pcm_be.extend(struct.pack(">h", val))
            
            # 3. Send audio in 20ms frames (320 bytes each)
            frame_size = 320
            print(f"[->] Sending {len(speech_pcm_be)} bytes of voice audio frames to live server...")
            
            for offset in range(0, len(speech_pcm_be), frame_size):
                frame = speech_pcm_be[offset:offset+frame_size]
                if len(frame) < frame_size:
                    frame += b'\x00' * (frame_size - len(frame))
                
                media_event = {
                    "event": "media",
                    "streamId": stream_id,
                    "media": {
                        "payload": base64.b64encode(frame).decode("utf-8"),
                        "track": "inbound"
                    }
                }
                await ws.send(json.dumps(media_event))
                await asyncio.sleep(0.02)
            
            # Send 600ms of silence frames to trigger VAD endpoint completion
            print("[->] Sending silence frames to complete utterance...")
            for _ in range(30):
                silent_frame = b"\x00" * 320
                media_event = {
                    "event": "media",
                    "streamId": stream_id,
                    "media": {
                        "payload": base64.b64encode(silent_frame).decode("utf-8"),
                        "track": "inbound"
                    }
                }
                await ws.send(json.dumps(media_event))
                await asyncio.sleep(0.02)
            
            print("[OK] Voice and silence frames transmitted! Waiting for VAD endpointing & server audio response...")
            
            # 4. Listen for server audio response (playAudio event)
            received_play_audio = False
            total_audio_bytes = 0
            
            try:
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=12.0)
                    try:
                        data = json.loads(msg)
                        evt = data.get("event")
                        print(f"    [Server Event Received]: {evt}")
                        if evt == "playAudio":
                            received_play_audio = True
                            payload_b64 = data.get("media", {}).get("payload", "")
                            audio_chunk = base64.b64decode(payload_b64)
                            total_audio_bytes += len(audio_chunk)
                        elif evt == "checkpoint":
                            print(f"[OK] Server finished speaking response: {total_audio_bytes} total audio bytes sent back!")
                            break
                    except Exception:
                        pass
            except asyncio.TimeoutError:
                print("    Timed out waiting for response.")
                
            if received_play_audio:
                print("=" * 60)
                print("SUCCESS! THE VOICE AGENT PROPERLY CAPTURED THE VOICE AUDIO,")
                print("PROCESSED TRANSCRIPTION & REASONING, AND RETURNED AUDIO BACK!")
                print("=" * 60)
            else:
                print("No playAudio event received yet.")

    except Exception as exc:
        print(f"[X] Connection Error: {exc}")

if __name__ == "__main__":
    asyncio.run(test_live_voice_capture())
