# Home Assistant Integration

This project includes a headless CLI for Home Assistant and other automations:

```bash
scripts/ollama_cli.py
```

The CLI runs Lilith without the browser UI. It uses the same LangChain agent
tool path as the Web TUI, reads the same tool enablement registry, and includes
enabled hooks/MCP/skills in the prompt context.

## Defaults

| Setting | Default |
|---|---|
| Model | `qwen3.5:9b` |
| Agent mode | Enabled |
| Personality | `sassy` by default; `default`, `sassy`, `snarky`, `rude`, and `formal` are available |
| Output | Plain text unless `--json` is used |

If `qwen3.5:9b` is not installed on the configured Ollama server, either pull it
or override the model:

```bash
docker compose exec web python scripts/ollama_cli.py --model qwen3.5:latest --json "what time is it?"
```

## Commands

Run from inside the deployment container:

```bash
docker compose exec web python scripts/ollama_cli.py --json "check health on mqtt-node"
docker compose exec web python scripts/ollama_cli.py --show-commands "is mqtt-node healthy?"
docker compose exec web python scripts/ollama_cli.py --list-capabilities --json
```

Run from a checkout on the host:

```bash
cd /path/to/ollama-command-deck
./scripts/ollama_cli.py --json "check disk usage on mqtt-node"
```

## JSON Response

`--json` returns a stable object for automations:

```json
{
  "ok": true,
  "model": "qwen3.5:latest",
  "agent": true,
  "personality": "sassy",
  "text": "Current local time: Tuesday, April 28, 2026 at 01:29:36 UTC.",
  "commands": ["time: local"],
  "stats": {
    "prompt_tokens": 2649,
    "response_tokens": 71,
    "total_duration_ms": 5044.443924,
    "tokens_per_second": 14.074891319973368
  },
  "capabilities": []
}
```

Failures also return JSON when `--json` is used:

```json
{
  "ok": false,
  "error": "model 'qwen3.5:9b' not found (status code: 404)"
}
```

## Home Assistant Examples

Example `shell_command`:

```yaml
shell_command:
  lilith_health_mqtt_node: >-
    ssh server-01 'cd /path/to/ollama-command-deck && docker compose exec -T web python scripts/ollama_cli.py --json "check health on mqtt-node"'
```

Example `command_line` sensor:

```yaml
command_line:
  - sensor:
      name: Lilith mqtt-node health
      command: >-
        ssh server-01 'cd /path/to/ollama-command-deck && docker compose exec -T web python scripts/ollama_cli.py --model qwen3.5:latest --json "give a one sentence health summary for mqtt-node"'
      scan_interval: 300
      value_template: "{{ value_json.text[:255] if value_json.ok else value_json.error[:255] }}"
      json_attributes:
        - ok
        - model
        - commands
        - stats
```

Keep prompts short for sensors. For longer reports, use a `shell_command`, write
the result to a file, or send it as a notification.

## Capability Model

The CLI sees the same enablement state as the Web TUI container:

| Capability source | How it is used |
|---|---|
| Tools | Bound to the LangChain agent when enabled |
| Hooks | Listed in the capability registry and represented by the same underlying tool functions |
| MCP server | Documents the same operational functions exposed to external MCP clients |
| Skills | Enabled Markdown files are loaded as bounded guidance |

Check the live registry:

```bash
docker compose exec web python scripts/ollama_cli.py --list-capabilities --json
```

## Notes

- The CLI inherits `OLLAMA_HOOKS_CONFIG=/config/config.toml` and `OLLAMA_HOOKS_DATA_DIR=/data` inside the container.
- SSH commands require enabled SSH tooling and usable SSH config inside `/data/.ssh/config`.
- If the SSH key is passphrase-protected, the container also needs the host ssh-agent mounted at `/ssh-agent` with `SSH_AUTH_SOCK=/ssh-agent`.
- Local commands obey the same safety policy and deploy-mode work-directory restrictions as the Web TUI.
- High-risk tools should stay disabled unless the deployment is intentionally trusted.
- Home Assistant should call the CLI with `--json` so errors are machine-readable.
