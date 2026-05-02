# Local Command Skill

Deploy note: local command execution is high risk and is disabled by default in deploy mode. It must be enabled during first-run setup or in deploy configuration before LangChain, MCP, or hook surfaces can run local shell commands.

Run non-`sudo` local commands through the wrapper:

```bash
python3 -m ollama_tools.cli run-local "pwd"
python3 hooks/run_local.py "ls -la"
```

The wrapper rejects privilege escalation and a few obvious destructive patterns before execution.

For current date/time, prefer the dedicated time tool instead of shelling out:

```bash
python3 -m ollama_tools.cli time
python3 hooks/current_time.py --tz America/New_York
```
