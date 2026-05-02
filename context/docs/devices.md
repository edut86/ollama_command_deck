# Devices And Deployment

Keep this file local to your deployment. Do not commit real hostnames, IP
addresses, usernames, private paths, or key names.

Example host aliases:

| Host alias | Purpose | Notes |
|---|---|---|
| `server-01` | Docker deployment and Web TUI host | Replace with your SSH alias |
| `mqtt-node` | MQTT, Meshtastic, or sensor services | Replace with your SSH alias |
| `gpu-node` | Ollama or GPU host | Optional |

Preferred deployment command on your Docker host:

```bash
cd /path/to/ollama-command-deck && ./scripts/deploy_web.sh
```

Preferred CLI smoke test on your Docker host:

```bash
docker compose exec web python scripts/ollama_cli.py --model qwen3.5:latest --json "what time is it?"
```

Path expectations inside the container:

| In container | Host source |
|---|---|
| `/data` | Host app data directory or named volume |
| `/workspace` | Host workspace directory |
| `/data/.ssh/config` | Optional SSH config bind mount |
| `/data/.ssh/known_hosts` | Optional known hosts bind mount |
| `/ssh-agent` | Host `SSH_AUTH_SOCK` socket when keys need ssh-agent |

For local testing, use `scripts/setup_docker_paths.sh` to generate a
`docker-compose.override.yml` with your chosen host paths.
