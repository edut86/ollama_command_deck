# Ollama Command Deck

A local AI toolbox with a browser UI wrapping an Ollama API. Includes agent mode with tool use, text-to-speech, file/document/image upload, a document canvas, self-hosted Piper TTS, and Docker support.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for acknowledgements and
license notes for upstream projects used by this app.

---

## Quick Start

### Docker Setup

This is the recommended path for a new install:

```bash
git clone https://github.com/<your-github-user>/ollama_command_deck.git
cd ollama_command_deck
./scripts/setup_docker_paths.sh
```

The setup script writes a local `docker-compose.override.yml`, lets you choose
where `/config`, `/data`, `/workspace`, and SSH files come from, then offers to
build and start the Docker services.

If you skip the script's deploy prompt, start it manually:

```bash
./scripts/deploy_web.sh
```

Open `http://localhost:8765`; the first-run setup wizard appears.

### Local Python Setup

```bash
# Create virtualenv and install dependencies
python3 -m venv .venv
.venv/bin/pip install -U pip langchain langchain-ollama edge-tts pypdf python-docx pymupdf

# Start the browser UI
./scripts/ollama_web.py
```

Open `http://<your-hostname>:8765` from any device on the LAN.

The server binds to `0.0.0.0` by default so it is reachable from phones and other LAN devices. Configure the Ollama URL and other settings in `config.toml`.

### Deployable Docker Start

The deployable container runs as a non-root `ollama-hooks` user whose UID/GID is set at build time via Docker build args (defaults: `10001:10001`). The container's user home is `/data`, so `~/.ssh/config` resolves to `/data/.ssh/config`.

#### Recommended setup: agent's home = host's home

The most useful configuration binds the host user's home dir to `/data` and builds the image with that user's UID/GID. The agent then reads and writes the host user's real `~/.ssh/config`, `~/.config`, project repos, etc., and any files it creates have correct host ownership.

1. **Choose Docker mount paths:**
    ```bash
    ./scripts/setup_docker_paths.sh
    ```
    This writes `docker-compose.override.yml`, lets you choose `/config`, `/data`,
    `/workspace`, and SSH mount behavior, then offers to rebuild/recreate `web`.
2. **Build and start manually if you skipped the script's deploy prompt:**
    ```bash
    ./scripts/deploy_web.sh
    ```
3. **Open `http://localhost:8765`** — the first-run setup wizard appears.

Advanced manual setup:

1. **Edit `docker-compose.yml`** so the `web` service builds with your UID/GID and binds your home:
    ```yaml
    web:
      build:
        context: .
        dockerfile: Dockerfile
        args:
          APP_UID: "1000"        # output of `id -u` on the host
          APP_GID: "1000"        # output of `id -g` on the host
      restart: unless-stopped
      ports:
        - "8765:8765"
      volumes:
        - ./config-data:/config  # host-owned bind, no sudo needed
        - /home/<you>:/data      # agent's HOME is the host user's home
      environment:
        OLLAMA_HOOKS_CONFIG: /config/config.toml
        OLLAMA_HOOKS_DATA_DIR: /data
        OLLAMA_WEB_NO_VENV: "1"
    ```

The wizard asks for an admin username/password, Ollama API URL and optional API key/token, a working directory (e.g. `/data/git/<your-project>` to start the agent inside one of your repos), and whether to enable local command, SSH, internet search, MCP tooling, and **dangerous mode** (lifts the work-directory sandbox and the destructive-command blocklist; privilege-escalation tokens — `sudo`, `su`, `doas`, `pkexec`, `passwd`, `visudo` — stay blocked).

High-risk tools are disabled by default. The wizard warns that local commands, SSH, hooks, MCP tools, and writable workspaces can modify files or remote devices and may cause harm if misused.

#### Why build args, not a runtime `user:` override?

Using `user: "1000:1000"` at runtime makes the kernel treat the process as UID 1000 — but `/etc/passwd` inside the image still only has the build-time `ollama-hooks:x:10001:...` line. Tools like `ssh` call `getpwuid()` and bail with `No user exists for uid 1000` before doing anything else. Building the image with the right UID/GID writes a real `/etc/passwd` entry, so `ssh`, `sudo` (when allowed), and shell login all work normally.

If you change the host user later (different machine, different UID), rebuild with `./scripts/deploy_web.sh`.

#### Editing config later

`/setup` can be reopened at any time. After first-run setup it asks for the existing user's credentials before unlocking the editor, then rewrites `config.toml` and rotates the session secret so all logged-in browsers must sign in again to pick up the new config. The lock screen also exposes a **forgot password — reset everything** button that wipes the user, all chat history, canvas files, and overrides, returning the install to first-run state.

The main UI shows a status banner with the current Ollama URL, enabled tools, and a red `⚠ DANGEROUS MODE` pill whenever dangerous mode is on.

#### Volume mount reference

`docker-compose.yml` controls what host paths back the container's `/config` and `/data`. Editing the compose file does **not** require an image rebuild — `docker-compose up -d` is enough; Docker recreates the affected container with the new mounts.

Prefer `./scripts/setup_docker_paths.sh` for this. It writes a local
`docker-compose.override.yml` instead of editing the base compose file, and it
uses `./scripts/deploy_web.sh` so Docker Compose v1 does not hit the
`ContainerConfig` recreate bug.

| Goal | Volume line |
|---|---|
| Recommended: full host-home access | `- /home/<you>:/data` |
| Limit to one project | `- /home/<you>/git/<project>:/data` |
| Use host SSH config and keys read-only | `- ~/.ssh:/data/.ssh:ro` |
| Use passphrase-protected SSH keys | Mount `$SSH_AUTH_SOCK` to `/ssh-agent` and set `SSH_AUTH_SOCK=/ssh-agent` |
| Seed only SSH config from the host (read-only) | `- ~/.ssh/config:/data/.ssh/config:ro` plus `- ~/.ssh/known_hosts:/data/.ssh/known_hosts:ro` |
| Keep config in-repo (host-owned, easy to back up) | `- ./config-data:/config` |
| Keep config in a Docker named volume | `- command-deck-config:/config` (and declare under top-level `volumes:`) |

Generated override example for using the host user's home as the agent home:

```yaml
services:
  web:
    volumes:
      - "./config-data:/config"
      - "/home/your-user:/data"
      - "/home/your-user/git:/workspace"
      - "/home/your-user/.ssh:/data/.ssh:ro"
      - "/run/user/<uid>/keyring/ssh:/ssh-agent"
    environment:
      SSH_AUTH_SOCK: "/ssh-agent"
```

With that layout, use these paths in the web setup wizard:

| Setup field | Value |
|---|---|
| Work directory | `/workspace` |
| SSH config path | `/data/.ssh/config` |
| known_hosts path | `/data/.ssh/known_hosts` |

The setup script detects a host `SSH_AUTH_SOCK` and writes the agent socket
mount automatically when you choose an SSH mount. This is needed for
passphrase-protected keys; mounting the private key file alone is not enough
because OpenSSH cannot prompt for the passphrase in batch mode.

Two pitfalls:
- **Named volumes are created as root.** A named `/config` or `/data` volume is owned by `root:root` on first create, so the non-root container user can't write to it. Either bind-mount a host path you already own (recommended), or `sudo chown -R <APP_UID>:<APP_GID> $(docker volume inspect <name> --format '{{.Mountpoint}}')` after first up.
- **Swapping a named volume for a bind mount discards the named volume's contents.** If you've been running with `command-deck-data` and switch to `- /home/<you>:/data`, the existing `users.json` and chat history aren't migrated. Either copy first (see below) or accept the wipe and re-run setup.

Migrating existing data into a host bind-mount before the swap:

```bash
docker volume inspect ollama_command_deck_command-deck-data --format '{{.Mountpoint}}'
# Copy contents into the new bind path; then edit docker-compose.yml and recreate
sudo cp -a <mountpoint>/. /home/<you>/
sudo chown -R $(id -u):$(id -g) /home/<you>/.ssh /home/<you>/web_sessions /home/<you>/canvas_files /home/<you>/users.json
docker-compose up -d
```

When to rebuild vs just `up -d`:

| You changed | What to run |
|---|---|
| `docker-compose.yml` (volumes, env, ports) | `docker-compose up -d` |
| `Dockerfile`, build `args:`, or anything in `scripts/` / `ollama_tools/` | `./scripts/deploy_web.sh` |
| `config.toml` (rendered inside the `/config` mount) | `docker-compose restart web` (or save via `/setup` — that already triggers a reload) |

If `docker-compose up -d` errors with `KeyError: 'ContainerConfig'`, that's a `docker-compose` v1 (Python) bug after image changes. Use:

```bash
./scripts/deploy_web.sh
```

The script detects `docker compose` v2 when available. It builds and starts
both `piper` and `web` so offline TTS does not end up half-configured. If only
`docker-compose` v1 is installed, it removes only the stale service containers
before recreating them without deleting named volumes. You can also migrate to
the newer `docker compose` (space, Go) plugin, which does not have this bug.

---

## Configuration

Edit `config.toml` in the project root:

```toml
[ollama]
url = "http://localhost:11434"

[web]
host = "0.0.0.0"
port = 8765

[tts]
piper_url = ""        # Leave blank to use Edge TTS; set to http://localhost:8880 for Piper

[search]
searxng_url = ""
brave_api_key = ""
```

Every key can also be overridden with an environment variable using the pattern `SECTION_KEY`, e.g. `OLLAMA_URL`, `WEB_PORT`, `TTS_PIPER_URL`.

---

## Recommended Models

Pull these on the Ollama host machine:

```bash
# Default / general chat
ollama pull qwen3.5:latest

# Vision (image upload and scanned PDF reading)
ollama pull llava:7b

# Uncensored agent-capable model
ollama pull dolphin3
```

| Model | Capabilities |
|---|---|
| `qwen3.5:latest` | 💬 Chat · 🤖 Agent · 🧠 Think · 📄 Document |
| `llava:7b` | 💬 Chat · 🖼 Vision · 📄 Document |
| `dolphin3` | 💬 Chat · 🤖 Agent · 📄 Document |
| `deepseek-coder-v2` | 💬 Chat · 🤖 Agent · 💻 Code · 📄 Document |
| `moondream` | 💬 Chat · 🖼 Vision |

The model dropdown in the browser UI shows capability icons next to each model name automatically.

---

## Browser UI

### Header Controls

| Control | Description |
|---|---|
| Model dropdown | Select from all models pulled on the Ollama server; shows capability icons |
| Mode dropdown | Switch between 💬 Chat · 🤖 Agent · 💻 Coding · 🎨 Creative · ⚡ Concise · 📚 Teaching |
| Personality dropdown | 🎭 default · 😊 friendly · 😏 snarky · 🙄 rude · 🎩 formal · 🏴‍☠️ pirate · 🧐 philosopher · 👨‍🍳 chef |
| Verbose button | Toggle token stats and model name display on each response |
| Keep alive checkbox | Sends `keep_alive: "30m"` to Ollama so the selected model stays loaded after replies |
| 📄 Canvas button | Open/close the document canvas popup |
| Ollama status dot | Green = API reachable, Red = offline, polls every 15 s |

**Defaults on page load:** Agent mode ON · Verbose ON · Personality default · Model `qwen3.5:latest` (if available)

---

## Headless CLI / Home Assistant

`scripts/ollama_cli.py` runs Lilith without the browser UI. It defaults to
`qwen3.5:9b`, agent mode on, and a sassy personality. It uses the same enabled
tool registry as the web agent, lists hooks/MCP/skills in the prompt, and loads
enabled skill Markdown as guidance.

```bash
./scripts/ollama_cli.py "check health on mqtt-node"
./scripts/ollama_cli.py --show-commands "is mqtt-node healthy?"
./scripts/ollama_cli.py --json "check disk usage on mqtt-node"
./scripts/ollama_cli.py --list-capabilities --json
```

Inside the Docker deployment:

```bash
docker compose exec web python scripts/ollama_cli.py --json "check health on mqtt-node"
```

For Home Assistant, call it through `command_line` or `shell_command` and use
`--json` when a machine-readable response is useful. The JSON response includes
`ok`, `text`, `commands`, `stats`, and the current capability registry.

See [HOME_ASSISTANT.md](HOME_ASSISTANT.md) for example sensors, shell commands,
model notes, and deployment caveats.

## Agent Profiles

Ollama Command Deck includes lightweight subagent-style profiles: `general`, `ops`,
`home`, `code`, `builder`, `research`, `writing`, `brief`, `debug`,
`frontend`, and `skill_creator`. They are focused prompt/tool/context profiles, not parallel
always-on workers, so they fit smaller local Ollama systems better.

Use the Web TUI `Agent:` dropdown, `/agent_profile ops`, or the CLI flag:

```bash
./scripts/ollama_cli.py --agent-profile ops --json "check health on mqtt-node"
./scripts/ollama_cli.py --agent-profile home --json "make a Home Assistant sensor for Lilith health"
./scripts/ollama_cli.py --agent-profile builder "implement this fix and run checks"
./scripts/ollama_cli.py --agent-profile debug "docker-compose up is failing with ContainerConfig"
```

See [AGENTS.md](AGENTS.md) for profile behavior and limitations.

When the Web TUI runs the `builder` profile, it appends a live Markdown trail to
`BUILDER_RUN.md` in the configured work directory. That file records the prompt,
commands, tool results, final response, and errors so you can verify that the
agent is operating inside the workspace even before it edits project files.
The runtime manages this file directly; Builder should not try to create it with
shell commands. Builder final responses include the runtime log path as an
application-added note so local models do not confuse it with model-written
files.
Builder local commands are also constrained to that configured work directory,
even if dangerous mode is enabled.
In Docker deploy mode, a missing work-directory setting falls back to
`/workspace` so Builder does not accidentally inspect the application source at
`/app`.
Builder receives a larger default tool budget than the other profiles so it can
inspect, patch, run verification, inspect failures, revise, and rerun before it
summarizes.

## Web UI Preferences

The Web UI defaults the assistant name to `Lilith`, but the name can be changed
from the header controls. The selected name is used for the visible chat label
and is injected into the web chat system prompt.

The browser remembers the last-used web settings, including model, agent/chat
mode, personality, agent profile, assistant name, verbose state, text zoom,
keep-alive, GPU selection, and theme.

During setup, **Require sign-in for the Web UI** can be turned off. This writes
`[auth] enabled = false` and skips the login page after setup. Use this only on
a trusted LAN or behind another authentication layer.

Profile-scoped context lives under `context/`. The app injects only the context
selected for the active profile and prompt, so writing/design/debug skills do
not leak into normal ops answers or JSON automation responses.

When the selected profile is `general`, the app can route obvious requests to a
more specific profile. For example, Docker/SSH health checks route to `ops`,
Home Assistant/MQTT prompts route to `home`, UI prompts route to `frontend`,
implementation/test feedback-loop prompts route to `builder`, and terse/caveman prompts route to `brief`. The verbose pane shows the active
profile and loaded context files for each request.

Check routing and context selection without calling a model:

```bash
python3 scripts/check_profile_context.py
```

### Footer Controls

| Control | Description |
|---|---|
| Textarea | Type message; Enter sends, Shift+Enter inserts newline; typing is always allowed but Enter is blocked while a response is generating |
| 📎 Attach | Upload an image or document (see [File Upload](#file-upload)) |
| 🔊 Read | Read the last AI reply aloud with TTS |
| ⏹ Stop | Abort the current generation mid-stream |
| Send | Send the message |

### Chat Modes

Set via the Mode dropdown or `/chat_mode <mode>`:

| Mode | Behaviour |
|---|---|
| Chat (default) | Standard conversation |
| Agent | Routes every message through LangChain tool orchestration |
| Coding | Prioritises working code, fenced blocks, minimal idiomatic solutions |
| Creative | Expressive, multiple angles, vivid analogies |
| Concise | Shortest replies, bullets, no filler |
| Teaching | First-principles explanations, examples, follow-up questions |

### Personalities

Set via the Personality dropdown or `/chat_personality <name>`:

| Personality | Tone |
|---|---|
| default | No modifier |
| friendly | Warm, encouraging, conversational |
| snarky | Dry wit, playful sarcasm, always helpful |
| rude | Blunt, impatient, and abrasive while still bounded and useful |
| formal | Professional, precise, no contractions |
| pirate | Nautical metaphors, stays in character |
| philosopher | Reflective, probes assumptions, embraces nuance |
| chef | Culinary metaphors, warm, passionate |

### Markdown Rendering

AI responses render as formatted markdown:
- Fenced code blocks with language label and **Copy** button
- Inline code, bold, italic
- Headers, bullet lists, numbered lists, blockquotes
- Text streams live as it generates; code blocks render cleanly once the fence is closed

### Verbose Mode

When ON, a grey `cmd:` line appears at the start of each response showing:
- Which model handled the request (including after any auto-switches)
- Token counts, generation speed, and total time at the end

---

## Agent Mode

Requires `langchain` and `langchain-ollama` in `.venv`. When enabled, every message is routed through LangChain which automatically selects tools:

| Tool | What it does |
|---|---|
| `/local <cmd>` | Run a local non-sudo shell command |
| `/ssh <host> <cmd>` | Run a command on an SSH host from `~/.ssh/config` |
| `/search <query>` | Web search via SearxNG, Brave, or DuckDuckGo fallback |
| `current_datetime` | Current local date/time, optionally for an IANA timezone |
| `/write <path>` | Write a file (model uses this automatically) |

Live tool progress is shown as `cmd:` lines in the chat before the final answer.

---

## File Upload

Click the **📎** button to attach a file. The AI reads the content automatically.

| Format | How it's handled |
|---|---|
| Images (jpg, png, gif, webp, etc.) | Base64 → vision model (llava); auto-switches model |
| PDF — text-based | `pypdf` extracts all page text → current text model |
| PDF — scanned (image-based) | `pymupdf` renders pages as images → vision model reads them |
| Word .docx | `python-docx` extracts paragraphs and tables |
| Word .doc | Not supported — resave as .docx |
| CSV | Decoded as text, capped at 500 rows |
| txt, md, json | Read directly |

**Auto-model routing:**
- Image attached → auto-switches to a vision model (llava, moondream, etc.); agent mode forced off (vision models don't support tool-calling)
- Scanned PDF → renders pages as images → auto-switches to vision model
- Text document + capable text model (qwen3.5, etc.) → keeps current model and mode
- Text document + vision-only model → forced to Chat mode

---

## Document Canvas

Click **📄 Canvas** in the header to open a floating popup window for document creation and editing.

### Canvas Controls

| Control | Description |
|---|---|
| Drag title bar | Move the popup anywhere on screen |
| Resize (bottom-right corner) | Resize the window |
| `─` Minimize | Collapse to title bar only |
| Canvas: Manual | Canvas is written only when your prompt explicitly mentions canvas or you use a canvas button |
| 👁 Preview / ✏ Edit | Toggle formatted Markdown preview and editable source |
| 📋 Send to AI | Sends canvas content through the canvas chat path for reprocessing/replacement |
| Clear | Wipe the canvas |
| Copy | Copy all canvas text to clipboard |
| ⬇ .md | Export as Markdown |
| ⬇ .txt | Export as plain text |
| ⬇ .rtf | Export as Rich Text Format (opens in Word and LibreOffice Writer) |
| ⬇ PDF | Open browser print dialog → Save as PDF |
| ⬇ .csv | Export as CSV (opens in LibreOffice Calc and Excel) |
| ✕ Close | Close the canvas popup |

**→ Canvas** and **↻ Canvas** buttons appear on each AI reply to append or replace the canvas.

### Canvas Chat

The canvas popup includes its own chat bar. Canvas chat uses the current canvas and its own short canvas conversation memory, separate from the main chat history.

### Canvas State

Open/closed state, maximize state, saved canvas files, and canvas content are restored through browser state and the configured data directory.

## Deploy Bundle

Implementation and release packaging stages the uploadable bundle in:

```text
/path/to/ollama-command-deck
```

That directory should contain only required runtime code, Docker files, docs, examples, hooks, MCP servers, skills, and safe config examples. It must not contain `.venv`, `.git`, `.env*`, `.claude`, private keys, tokens, generated sessions, or canvas user data.

---

## Text-to-Speech

The browser UI supports two TTS backends:

### Edge TTS (default, internet required)

Microsoft Edge neural voices synthesised server-side and played as MP3. No API key needed.

```bash
.venv/bin/pip install edge-tts
```

### Piper TTS (self-hosted, offline)

```bash
# Install Piper in the virtualenv
.venv/bin/pip install piper-tts

# Download offline female voice models
./scripts/setup_offline_tts.sh ~/piper-voices

# Start the Piper server
PIPER_VOICES_DIR=~/piper-voices .venv/bin/python scripts/piper_server.py

# Start the web UI pointing at Piper
KOKORO_URL=http://localhost:8880 ./scripts/ollama_web.py
```

Or set `piper_url = "http://localhost:8880"` in `config.toml`.

The `Lilith Dark` voice preset prefers the local Piper voice `af_hfc_female`
when `KOKORO_URL`/`piper_url` is configured. If no offline TTS server is
configured, it falls back to Edge TTS and requires internet access.

### TTS Controls

| Control | Description |
|---|---|
| Voice dropdown | Piper/Kokoro voices (offline) grouped above Edge TTS voices (internet) |
| Speed slider | Slow → Fastest |
| Pitch slider | -12 → +12 semitones; Edge uses approximate pitch control, offline audio uses `ffmpeg` post-processing with the source sample rate |
| Tone dropdown | Natural, Dark, Bright, Radio, or Robotic |
| Volume slider | -50% → +50% gain |
| Text slider | 85% → 140% UI text zoom, persisted in the browser |
| Stop button | Cancel current playback |
| 🔊 Read (footer) | Read last reply aloud |
| 🔊 (per message) | Read that specific reply aloud |

---

## Docker

Run the web UI and Piper TTS server together:

```bash
# Download voices once on the Docker host
./scripts/setup_offline_tts.sh ~/piper-voices

# Build and start/recreate Piper and web
./scripts/deploy_web.sh

# Edit config on the host — takes effect on restart
nano config.toml
docker compose restart web
```

`docker-compose.yml` maps `~/piper-voices` to `/piper-voices` in the Piper
container and sets `KOKORO_URL=http://piper:8880` for the Web UI. In the setup
page, set the Piper / Kokoro URL to:

```text
http://piper:8880
```

---

## Slash Commands

| Command | Description |
|---|---|
| `/help` | Show all commands |
| `/model` | List available models |
| `/model <name>` | Switch model |
| `/hosts` | List SSH aliases from `~/.ssh/config` |
| `/ssh <host> <cmd>` | Run a command on an SSH host |
| `/local <cmd>` | Run a local non-sudo command |
| `/search <query>` | Web search |
| `/write <path>` | Write a file |
| `/agent on\|off` | Toggle agent mode |
| `/chat` | Switch to normal chat mode |
| `/verbose on\|off` | Toggle verbose stats |
| `/chat_mode <mode>` | Set mode: default, coding, creative, concise, teaching |
| `/chat_personality <name>` | Set personality |
| `/remember <text>` | Save a persistent memory note |
| `/memory` | List memory notes |
| `/forget <n>` | Delete memory note by number |
| `/clear` | Clear chat history |
| `/quit` | Exit |

---

## Security

The browser UI applies HTTP security headers on every response (`X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy`, `Content-Security-Policy`).

Additional hardening:
- TTS voice names are whitelisted — only known voice names are accepted
- TTS rate is validated by regex before use
- TTS payload is capped at 32 KB
- Chat-stream payload is capped at 20 MB (to accommodate image uploads)
- Path traversal protection on `/write` — writes blocked outside the home directory
- Shell command blocklist in `ollama_tools/safety.py` rejects dangerous patterns

---

## Internet Search

Priority: SearxNG → Brave Search → Google News RSS (news queries) → DuckDuckGo HTML fallback.

```bash
# SearxNG
export SEARXNG_URL="http://localhost:8080"

# Brave Search
export BRAVE_SEARCH_API_KEY="your-key"

# Disable no-key fallbacks
export DISABLE_DUCKDUCKGO_FALLBACK=1
```

---

## Project Layout

```
ollama_command_deck/
├── config.toml               — User-editable config (Ollama URL, web host/port, TTS, search)
├── docker-compose.yml        — Web UI + Piper TTS services
├── Dockerfile                — Web UI container
├── Dockerfile.piper          — Piper TTS server container
├── requirements.docker.txt   — Python deps for Docker build
├── ollama_tools/
│   ├── config.py             — Loads config.toml + env var overrides
│   ├── ollama_api.py         — Ollama HTTP client (list models, stream chat, vision support)
│   ├── langchain_orchestrator.py — LangChain agent with live tool streaming
│   ├── safety.py             — Shell command blocklist and pattern checks
│   ├── shell_tools.py        — Local command execution
│   ├── ssh_tools.py          — SSH host parsing and remote command execution
│   ├── time_tools.py         — Current date/time helper
│   ├── web_search.py         — SearxNG / Brave / DuckDuckGo search
│   └── monitoring.py         — Netdata, Prometheus, Glances, MQTT monitoring
├── scripts/
│   ├── ollama_web.py         — Browser UI server (all features)
│   ├── ollama_tui.py         — Terminal chat UI
│   └── piper_server.py       — Self-hosted Piper TTS HTTP server
├── mcp_servers/              — Optional MCP server entrypoints
├── hooks/                    — Direct wrapper scripts
└── skills/                   — Agent skill descriptions
```

### Current Time Tool

Use the dedicated time/date helper instead of shelling out:

```bash
python3 -m ollama_tools.cli time
python3 -m ollama_tools.cli time --tz America/New_York
python3 hooks/current_time.py --tz UTC
```

The MCP server and LangChain agent expose the same capability as `current_datetime`.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API base URL |
| `WEB_HOST` | `0.0.0.0` | Browser UI bind host |
| `WEB_PORT` | `8765` | Browser UI bind port |
| `TTS_PIPER_URL` | _(empty)_ | Piper/Kokoro TTS server URL |
| `KOKORO_URL` | _(empty)_ | Alias for `TTS_PIPER_URL` (set by Docker Compose) |
| `SEARXNG_URL` | _(empty)_ | SearxNG instance for web search |
| `BRAVE_SEARCH_API_KEY` | _(empty)_ | Brave Search API key |
| `DISABLE_DUCKDUCKGO_FALLBACK` | _(unset)_ | Set to `1` to require a configured search provider |
| `OLLAMA_WEB_PORT_SEARCH_LIMIT` | `20` | Ports to try if requested port is busy |
| `OLLAMA_WEB_NO_VENV` | _(unset)_ | Set to `1` to skip auto-reexec through `.venv` |
| `OLLAMA_TUI_NO_VENV` | _(unset)_ | Set to `1` to skip terminal TUI auto-reexec through `.venv` |
| `PROMETHEUS_URL` | _(empty)_ | Prometheus server URL |
| `OLLAMA_TUI_MOUSE` | _(unset)_ | Set to `1` to enable mouse wheel capture in TUI |

All config.toml keys can also be overridden with the pattern `SECTION_KEY` (e.g. `OLLAMA_URL`, `WEB_PORT`).

---

## Python Dependencies

| Package | Purpose |
|---|---|
| `langchain` + `langchain-ollama` | Agent mode / tool orchestration |
| `edge-tts` | Microsoft Edge neural TTS voices |
| `piper-tts` | Self-hosted offline TTS |
| `pypdf` | Text extraction from PDF files |
| `python-docx` | Text extraction from Word .docx files |
| `pymupdf` | Rendering scanned PDF pages as images for vision models |

Install all at once:

```bash
.venv/bin/pip install langchain langchain-ollama edge-tts pypdf python-docx pymupdf
```
