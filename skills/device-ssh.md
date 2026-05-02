# Device SSH Skill

Deploy note: SSH execution is high risk and is disabled by default in deploy mode. If enabled, mount `~/.ssh/config` read-only so aliases can be discovered. Commands can affect remote devices and should be enabled only for trusted deployments.

Use SSH aliases from `~/.ssh/config`. Do not invent raw hostnames unless they are also configured as aliases.

Useful commands:

```bash
python3 -m ollama_tools.cli ssh-hosts
python3 -m ollama_tools.cli run-ssh <host-alias> "uptime"
```

Commands using `sudo`, `su`, `doas`, or `pkexec` are blocked.
