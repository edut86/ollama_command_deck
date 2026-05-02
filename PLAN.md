# Ollama Command Deck — Plan and Feature Tracker

## Core Requirements

- Connect to Ollama API at `http://localhost:11434` (configurable via `config.toml` or env var)
- Browser UI accessible from any LAN device
- Terminal chat UI mirroring the browser UI feature set
- Agent mode with LangChain tool orchestration
- Self-hosted and cloud TTS options
- File upload and document analysis
- Docker support for easy deployment
- Deployable bundle staged under `ollama_command_deck` for later upload

---

## Implemented Features

### Browser UI (`scripts/ollama_web.py`)

#### Chat and Model Control
- [x] Model dropdown populated from Ollama `/api/tags` with capability icons (💬 🤖 🖼 💻 🧠 📄)
- [x] Default model: `qwen3.5:latest` (falls back to first available)
- [x] Unified Mode dropdown: 💬 Chat · 🤖 Agent · 💻 Coding · 🎨 Creative · ⚡ Concise · 📚 Teaching
- [x] Personality dropdown: default · friendly · snarky · rude · formal · pirate · philosopher · chef
- [x] Verbose toggle — shows `Model: <name>` cmd line + token stats per response; defaults ON
- [x] Keep alive checkbox — sends Ollama `keep_alive: "30m"` and persists in localStorage
- [x] Agent mode defaults ON
- [x] Personality defaults to `default`
- [x] Ollama API status indicator (green/red dot, polls every 15 s)

#### Streaming and Rendering
- [x] Live token-by-token streaming into chat window
- [x] Markdown rendering: code blocks with language header + Copy button, inline code, bold, italic, headers, lists, blockquotes
- [x] Live markdown rendering during streaming (safe with open code fences)
- [x] Final render + Copy button wiring after stream completes

#### Stop / Input Control
- [x] ⏹ Stop button aborts mid-generation via `AbortController`
- [x] Enter blocked while generation is in progress (typing still allowed to queue next message)

#### Agent Mode
- [x] LangChain tool orchestration with live `cmd:` progress lines before final answer
- [x] Tools: local shell, SSH, web search, current date/time, file write
- [x] Agent mode forced off for vision-only models (no tool-calling support)
- [x] Agent mode stays on for capable text models (qwen3.5, dolphin3, etc.) even with document uploads

#### File Upload
- [x] 📎 Attach button with file preview and ✕ remove
- [x] Images → base64 → vision model (auto-switch); thumbnail shown in chat
- [x] PDF (text-based) → `pypdf` text extraction → current text model
- [x] PDF (scanned/image-based) → `pymupdf` page rendering → vision model reads images (up to 4 pages)
- [x] Word .docx → `python-docx` paragraph + table extraction
- [x] Word .doc → error message (save as .docx)
- [x] CSV → text decode, capped at 500 rows
- [x] txt / md / json → direct text decode
- [x] Document context preamble explicitly tells agent not to search for the file
- [x] 20 MB payload cap for image/document uploads

#### Document Canvas
- [x] Floating draggable popup window (drag by title bar)
- [x] Resizable from bottom-right corner
- [x] Minimize to title bar
- [x] Auto: ON/OFF toggle — auto-appends every AI reply to canvas when on
- [x] Keyword detection — auto-appends when message contains canvas/document/draft/edit/etc.
- [x] → Canvas button on every AI reply for manual append
- [x] 📋 Send to AI — pastes canvas into input field for AI to read/edit
- [x] Canvas content injected as system context when relevant keywords detected in message
- [x] Export: .md, .txt, .rtf (Word/LibreOffice), PDF (print dialog), .csv
- [x] Clear, Copy all
- [x] Canvas open/closed and Auto state persisted in localStorage

#### Text-to-Speech
- [x] Edge TTS — Microsoft neural voices, MP3 server-side synthesis, internet required
- [x] Piper TTS — self-hosted offline, via `scripts/piper_server.py`; set `piper_url` in config.toml
- [x] Voice dropdown with Piper/Kokoro group and Edge TTS group
- [x] Speed slider (-75% to +100%) with named labels
- [x] Pitch, tone, and volume mixer using `ffmpeg`; offline pitch processing detects the source audio sample rate
- [x] 🔊 per-message speak button
- [x] 🔊 Read last button in footer
- [x] Stop playback button
- [x] Voice and speed saved to localStorage

#### Security
- [x] HTTP security headers on all responses (CSP, X-Frame-Options, X-XSS-Protection, etc.)
- [x] TTS voice whitelist — only known voice names accepted
- [x] TTS rate validated by regex
- [x] TTS payload capped at 32 KB
- [x] Path traversal protection on `/write` (blocked outside home directory)
- [x] Shell command blocklist in `safety.py`
- [x] Deploy mode mini sign-on scaffolding with first-run admin setup
- [x] First-run risk warning for local commands, SSH, hooks, MCP tools, and writable workspaces
- [x] Central tool enablement registry for MCP/hooks/skills/tool gating
- [x] Docker runtime moved toward non-root user with persistent `/config`, `/data`, and `/workspace`

### Multi-GPU Support
- [x] `[gpu]` section in `config.toml` maps GPU index → Ollama URL + human label
- [x] GPU dropdown in header — hidden when only one GPU configured, shown when 2+ set
- [x] GPU selection persisted in localStorage; reloads model list for selected endpoint
- [x] All chat/stream calls route to selected GPU's Ollama URL
- [x] `/api/gpu-list` endpoint

### Speech-to-Text (Whisper STT)
- [x] 🎙 Mic button in footer — hidden until Whisper is confirmed available
- [x] Click-to-record / click-to-stop via `MediaRecorder` (WebM/Opus)
- [x] Red pulsing animation while recording
- [x] Audio POSTed to `/api/transcribe` → `faster-whisper` embedded in `ollama_web.py`
- [x] Transcribed text inserted into chat input
- [x] Whisper lazy-loaded on first use — does not block server startup
- [x] `[stt]` section in `config.toml`: `whisper_model`, `whisper_device`, `whisper_device_index`
- [x] Recommended: `medium` + `int8` on T400 (4 GB VRAM, ~1.9 GB)
- [x] `/api/stt-status` endpoint — JS checks on load to show/hide mic button

### Configuration (`ollama_tools/config.py`, `config.toml`)
- [x] `config.toml` in project root with sections: `[ollama]`, `[web]`, `[tts]`, `[search]`, `[stt]`, `[gpu]`
- [x] Priority: env var → config.toml → hardcoded default
- [x] `tomllib` on Python 3.11+; minimal fallback parser on 3.10

### Ollama API (`ollama_tools/ollama_api.py`)
- [x] `list_models()` → `OllamaModel` dataclass list
- [x] `stream_chat()` with optional `images` parameter for vision models
- [x] `stream_chat()` supports Ollama `keep_alive`
- [x] `ChatStats` dataclass (prompt tokens, response tokens, duration, speed)
- [x] Auto-enable `think: true` for qwen3, deepseek-r1, phi4-reasoning, qwq models

### LangChain Orchestrator (`ollama_tools/langchain_orchestrator.py`)
- [x] `stream_langchain_agent_events()` generator — yields `cmd` events live before each tool runs
- [x] `invoke_langchain_agent_with_trace()` — non-streaming version
- [x] `current_datetime` tool for local date/time and named IANA timezones
- [x] Strips `<think>...</think>` blocks from model output

### Safety (`ollama_tools/safety.py`)
- [x] BLOCKED_WORDS: chmod, chown, curl, wget, python, bash, nc, crontab, nsenter, etc.
- [x] BLOCKED_PATTERNS: eval, exec, `$()`, backticks, base64 decode, /proc/self, LD_PRELOAD

### Self-Hosted TTS (`scripts/piper_server.py`)
- [x] HTTP server exposing `POST /v1/audio/speech` (OpenAI-compatible interface)
- [x] Auto-discovers `.onnx` voice files in `PIPER_VOICES_DIR`
- [x] Returns `audio/wav`

### Docker (`Dockerfile`, `Dockerfile.piper`, `docker-compose.yml`)
- [x] `web` service: python:3.12-slim, installs requirements.docker.txt, port 8765
- [x] `piper` service: python:3.12-slim + espeak-ng, port 8880, mounts `~/piper-voices`
- [x] `config.toml` volume-mounted read-only; changes take effect on `docker compose restart web`
- [x] `~/.config/ollama_tui` volume-mounted for persistent chat settings

### Terminal TUI (`scripts/ollama_tui.py`)
- [x] Model picker with arrow-key navigation
- [x] Streaming chat with live token display
- [x] All browser UI slash commands supported
- [x] Persistent settings in `~/.config/ollama_tui/settings.json`
- [x] Persistent memory in `~/.config/ollama_tui/memory.json`
- [x] Input history in `~/.config/ollama_tui/history.json`
- [x] Live GPU stats for `gpu-node` in verbose mode

### Headless CLI / Home Assistant (`scripts/ollama_cli.py`)
- [x] Headless Lilith agent CLI for automations and Home Assistant command-line integrations
- [x] Defaults: model `qwen3.5:9b`, agent mode enabled, personality `sassy`
- [x] Supports `--agent-profile` for lightweight subagent-style profile routing
- [x] Uses `stream_langchain_agent_events()` so enabled local, SSH, search, time, and monitoring tools are shared with the Web TUI agent
- [x] Injects the current enabled tools/hooks/skills registry into the system prompt
- [x] Loads enabled skill Markdown files as bounded prompt guidance
- [x] Supports `--json` output with `ok`, `text`, `commands`, `stats`, and `capabilities`
- [x] Supports `--list-capabilities --json` for Home Assistant diagnostics
- [x] Returns structured JSON errors when the requested model is not installed

### Agent Profiles / Lightweight Subagents (`ollama_tools/agent_profiles.py`)
- [x] Shared profile registry: `general`, `ops`, `home`, `code`, `builder`, `research`
- [x] Web TUI `Agent:` dropdown and `/agent_profile <name>` slash command
- [x] Session persistence for selected profile
- [x] CLI `--agent-profile` option
- [x] Profiles add focused system guidance without spawning parallel model workers
- [x] Expanded profiles: `writing`, `brief`, `debug`, `frontend`, `skill_creator`
- [x] Added `builder` profile for bounded inspect → patch → verify → revise code-writing loops
- [x] Added `context/` docs skeleton for durable project, ops, Home Assistant, skill, and eval context
- [x] Added `ollama_tools/context_loader.py` for profile-scoped context injection
- [x] Injects relevant context into CLI and Web prompts without making writing/design/debug skills global
- [x] Added small manual eval file at `context/evals/profile_context_eval.md`
- [x] Added deterministic auto-routing from `general` to specific profiles for obvious prompts
- [x] Added `context/docs/devices.md` for known hosts, deploy paths, and container paths
- [x] Web verbose pane now shows active profile, route reason, and loaded context files
- [x] Added `scripts/check_profile_context.py` for routing/context smoke tests

### Web UI Preferences / Access
- [x] Assistant name defaults to `Lilith` and can be changed in the Web UI
- [x] Web chat prompt receives the configured assistant name
- [x] Browser persists last-used model, mode, personality, profile, assistant name, verbose state, text zoom, keep-alive, GPU, and theme
- [x] Setup wizard can disable Web UI sign-in for trusted LAN/reverse-proxy deployments

---

## Python Dependencies

| Package | Required for |
|---|---|
| `langchain` + `langchain-ollama` | Agent mode |
| `edge-tts` | Cloud TTS |
| `piper-tts` | Offline TTS |
| `pypdf` | PDF text extraction |
| `python-docx` | Word .docx extraction |
| `pymupdf` | Scanned PDF page rendering |

---

## Notes

- Vision models (llava, moondream, etc.) don't support LangChain tool-calling — agent mode is automatically disabled when they are active
- Scanned PDFs are detected by near-zero text extraction; fallback renders up to 4 pages as images via pymupdf
- The agent is instructed not to search for uploaded documents — the extracted content is already in context
- `.doc` (legacy Word) is not supported; python-docx requires `.docx`
- `config.toml` keys can be overridden with env vars using the pattern `SECTION_KEY` (e.g. `OLLAMA_URL`)
