# Home Assistant Context

Use this for Home Assistant, MQTT, Meshtastic, sensors, and automations.

The headless CLI is the preferred integration point for Home Assistant because
it returns JSON and uses the same enabled tool registry as the Web agent.

Remote command pattern:

```bash
ssh -o BatchMode=yes your-user@server-01 'cd /path/to/ollama-command-deck && docker compose exec -T web python scripts/ollama_cli.py --model qwen3.5:latest --agent-profile home --json "what time is it?"'
```

Setup requirements:

- Home Assistant needs an SSH private key.
- The matching public key must be in `/home/your-user/.ssh/authorized_keys` on
  `server-01`.
- The container should see the host SSH config through `/data/.ssh/config` when
  `/home/your-user` is mounted as `/data`.

When producing Home Assistant examples:

- Prefer YAML for `command_line`, `shell_command`, sensors, and automations.
- Use `value_json.text` or explicit JSON attributes when reading CLI output.
- Keep prompts short and deterministic for automations.
