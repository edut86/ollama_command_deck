#!/usr/bin/env bash
set -euo pipefail

VOICE_DIR="${1:-$HOME/piper-voices}"
BASE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main"

mkdir -p "$VOICE_DIR"

download_voice() {
  local rel="$1"
  local file="${rel##*/}"
  if [[ -f "$VOICE_DIR/$file" ]]; then
    echo "Already present: $VOICE_DIR/$file"
    return
  fi
  echo "Downloading $file"
  curl -fL "$BASE_URL/$rel" -o "$VOICE_DIR/$file"
}

echo "Installing offline Piper voices into: $VOICE_DIR"

# HFC female is used by the Lilith Dark offline preset.
download_voice "en/en_US/hfc_female/medium/en_US-hfc_female-medium.onnx"
download_voice "en/en_US/hfc_female/medium/en_US-hfc_female-medium.onnx.json"

# Lessac is a good alternate female voice for comparison.
download_voice "en/en_US/lessac/medium/en_US-lessac-medium.onnx"
download_voice "en/en_US/lessac/medium/en_US-lessac-medium.onnx.json"

echo
echo "Done. If using Docker Compose, make sure the piper service mounts:"
echo "  $VOICE_DIR:/piper-voices:ro"
echo
echo "Then set the Web UI setup TTS URL to:"
echo "  http://piper:8880"
echo
echo "For non-Docker local testing:"
echo "  PIPER_VOICES_DIR=\"$VOICE_DIR\" python3 scripts/piper_server.py"
