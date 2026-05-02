#!/usr/bin/env python3
"""Lightweight Piper TTS HTTP server.

Exposes POST /v1/audio/speech — same interface the web UI expects.
Runs on port 8880 by default (override with PIPER_PORT env var).

Usage:
    .venv/bin/python scripts/piper_server.py

Environment variables:
    PIPER_PORT          Bind port (default 8880)
    PIPER_HOST          Bind host (default 0.0.0.0)
    PIPER_VOICES_DIR    Directory containing .onnx voice models
                        (default ~/piper-voices)
"""

from __future__ import annotations

import io
import json
import os
import struct
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VOICES_DIR = Path(os.environ.get("PIPER_VOICES_DIR", Path.home() / "piper-voices"))
HOST = os.environ.get("PIPER_HOST", "0.0.0.0")
PORT = int(os.environ.get("PIPER_PORT", "8880"))

# Map friendly voice names to model files
VOICE_MODELS: dict[str, Path] = {}

def _discover_voices() -> None:
    if not VOICES_DIR.exists():
        return
    for f in sorted(VOICES_DIR.glob("*.onnx")):
        name = f.stem  # e.g. en_US-amy-medium
        VOICE_MODELS[name] = f
        # Also register short aliases: "amy", "af_amy" etc.
        parts = name.split("-")
        if len(parts) >= 2:
            VOICE_MODELS[parts[1]] = f           # "amy"
            VOICE_MODELS["af_" + parts[1]] = f   # "af_amy" (Kokoro-style alias)
            VOICE_MODELS["bf_" + parts[1]] = f   # "bf_amy"

_discover_voices()

DEFAULT_VOICE = next(iter(VOICE_MODELS), None)


def _rate_to_length_scale(speed: float) -> float:
    """Piper uses length_scale: higher = slower. Invert speed."""
    speed = max(0.5, min(2.0, speed))
    return 1.0 / speed


def synthesise(text: str, voice_name: str, speed: float = 1.0) -> bytes:
    """Synthesise text with Piper and return WAV bytes."""
    from piper.voice import PiperVoice  # type: ignore

    model_path = VOICE_MODELS.get(voice_name) or VOICE_MODELS.get(DEFAULT_VOICE or "")
    if model_path is None:
        raise RuntimeError(f"No voice model found in {VOICES_DIR}")

    voice = PiperVoice.load(str(model_path), use_cuda=False)
    length_scale = _rate_to_length_scale(speed)

    from piper.config import SynthesisConfig  # type: ignore
    syn_config = SynthesisConfig(length_scale=length_scale)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)  # 16-bit
        wav.setframerate(voice.config.sample_rate)
        for chunk in voice.synthesize(text, syn_config=syn_config):
            wav.writeframes(chunk.audio_int16_bytes)
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    server_version = "PiperTTS/0.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[piper] {self.address_string()} {fmt % args}")

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json({"ok": True, "voices": list(VOICE_MODELS.keys())})
            return
        if self.path == "/v1/voices":
            self._json({"voices": list(VOICE_MODELS.keys())})
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if self.path != "/v1/audio/speech":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 32_000:
                self._json({"error": "payload too large"}, 413)
                return
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            text = str(payload.get("input", payload.get("text", ""))).strip()[:4000]
            voice = str(payload.get("voice", DEFAULT_VOICE or ""))
            speed = float(payload.get("speed", 1.0))
            if not text:
                self._json({"error": "no text"}, 400)
                return
            audio = synthesise(text, voice, speed)
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(audio)))
            self.end_headers()
            self.wfile.write(audio)
        except Exception as exc:
            self._json({"error": str(exc)}, 500)

    def _json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    if not VOICE_MODELS:
        print(f"[piper] WARNING: no .onnx voices found in {VOICES_DIR}")
        print(f"[piper] Download one with:")
        print(f"[piper]   wget -P {VOICES_DIR} https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx")
    else:
        print(f"[piper] Loaded voices: {', '.join(VOICE_MODELS.keys())}")
    print(f"[piper] Listening on http://{HOST}:{PORT}")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.serve_forever()
