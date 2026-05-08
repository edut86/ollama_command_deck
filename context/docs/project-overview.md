# Project Overview

Ollama Command Deck is a local Ollama assistant surface with a Web TUI, terminal TUI,
headless CLI, hooks, skills, and MCP-facing tool functions. The assistant is
named Lilith.

Source workflow:

- Edit the main source tree.
- Mirror deployable files into the release bundle.
- Copy the release bundle to `server-01:/path/to/ollama-command-deck`.
- Use `./scripts/deploy_web.sh` on `server-01` instead of raw
  `docker-compose build web && docker-compose up -d web`.
  The script builds/starts both `piper` and `web`, includes local
  `docker-compose.override.yml` when present, auto-detects GPU STT mode, and
  prints the HTTPS URL.

Default Docker deployment:

- Container service: `web`
- Offline TTS service: `piper`
- Common container name: `web`
- Web port: `8765`
- Web scheme: HTTPS by default in Docker. The container generates a self-signed
  certificate under `/config/tls` when `OLLAMA_WEB_AUTO_TLS=1`.
- In-container home/data path: `/data`
- Recommended setup UI SSH paths:
  - SSH config: `/data/.ssh/config`
  - known hosts: `/data/.ssh/known_hosts`
- For passphrase-protected SSH keys, mount the host `SSH_AUTH_SOCK` to
  `/ssh-agent` and set `SSH_AUTH_SOCK=/ssh-agent` in the web container.

Recent Web UI settings include assistant name, personality including `rude`,
text zoom, GPU selection, and an Ollama keep-alive checkbox that sends
`keep_alive: "30m"`.

Agent profiles are lightweight prompt/tool profiles. They do not spawn parallel
workers and they do not bypass the enabled tool registry.
