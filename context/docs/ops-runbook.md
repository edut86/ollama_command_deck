# Ops Runbook

Use this for device, service, Docker, SSH, and deployment checks.

Operational habits:

- Gather current evidence before summarizing.
- Prefer read-only commands unless the user asks for a change.
- Use configured SSH aliases instead of inventing hostnames.
- Do not run `sudo`, `su`, `doas`, `pkexec`, or privilege escalation commands.
- Present command output as compact Markdown tables when useful.
- Keep verbose command traces separate from the final answer when the UI supports it.

Useful checks:

```bash
df -h
free -h
uptime
systemctl is-active docker
docker ps
docker compose ps
docker-compose ps
```

Deployment note:

Docker Compose v1.29 can fail during recreate with `KeyError: 'ContainerConfig'`.
Use `./scripts/deploy_web.sh`; it builds and starts both `piper` and `web`, and
removes stale service containers before bringing them up when Compose v1 is
detected.

SSH note:

When SSH works on the host but fails inside Docker, check whether the key is
passphrase-protected. The container needs the host ssh-agent socket mounted as
`/ssh-agent` with `SSH_AUTH_SOCK=/ssh-agent`; mounting `~/.ssh` alone may not be
enough in batch mode. Docker also may not resolve `.local` mDNS names, so the
SSH helper falls back to `.localdomain`/bare hostnames while preserving the
original `HostKeyAlias`.
