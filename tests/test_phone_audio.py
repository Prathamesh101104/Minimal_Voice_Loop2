import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location("server", ROOT / "server.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_normalize_vobiz_audio_converts_ulaw_to_pcm16():
    frame = bytes([0x00, 0x80, 0xFF, 0x55])
    pcm = module._normalize_vobiz_audio(frame, "audio/pcmu")
    assert len(pcm) == 8
    assert pcm[:2] != b"\x00\x00"


def test_normalize_vobiz_audio_converts_l16_to_little_endian():
    frame = bytes([0x00, 0x01, 0x02, 0x03])
    pcm = module._normalize_vobiz_audio(frame, "audio/L16")
    assert pcm == b"\x01\x00\x03\x02"


def test_selects_openai_when_gemini_is_missing(monkeypatch):
    monkeypatch.delenv("Gemini_API_Key", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "demo-key")
    module.config_state = {}
    assert module._select_phone_transcription_backend() == "openai"


def test_extract_vobiz_media_payload_from_bytes():
    payload = b"\x00\x01"
    media, track = module._extract_vobiz_media_payload(payload, "audio/x-l16")
    assert media == payload
    assert track == "inbound"


def test_extract_vobiz_media_payload_from_json_base64_string():
    import base64
    raw_audio = b"\x01\x02\x03\x04"
    b64_str = base64.b64encode(raw_audio).decode("utf-8")
    msg = {
        "event": "media",
        "streamId": "test-stream",
        "media": {
            "payload": b64_str,
            "track": "inbound"
        }
    }
    extracted_bytes, track = module._extract_vobiz_media_payload(msg, "audio/x-l16")
    assert extracted_bytes == raw_audio
    assert track == "inbound"

