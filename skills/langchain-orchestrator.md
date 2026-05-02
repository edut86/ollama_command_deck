# LangChain Orchestrator Skill

Deploy note: the orchestrator now receives only tools enabled by configuration. High-risk tools such as local command and SSH remain unavailable unless explicitly enabled.

Use the LangChain orchestrator when the model should decide which local tool to call.

Install optional dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -U pip langchain langchain-ollama
```

Use inside the TUI:

```text
/agent "is mqtt-node online and what is its network usage?"
```

Toggle all normal messages through the agent with:

```text
/agent on
```

Switch back to normal chat with:

```text
/chat
```

Or start the TUI with LangChain as the default chat path:

```bash
OLLAMA_TUI_ORCHESTRATOR=langchain .venv/bin/python scripts/ollama_tui.py
```

The terminal TUI automatically re-runs itself with `.venv/bin/python` when `.venv` exists, so `python3 scripts/ollama_tui.py` can still use LangChain. Set `OLLAMA_TUI_NO_VENV=1` only when you intentionally want to bypass that.

The browser UI also exposes an Agent toggle and supports `/agent on`, `/agent off`, and `/chat`.
If LangChain is unavailable, browser Agent mode falls back to normal chat and disables the Agent toggle.
The browser UI displays Agent tool calls as `cmd:` transcript messages before the final answer.
If the model exhausts tool rounds or returns empty/thinking-only text, the orchestrator falls back to a visible answer built from collected tool output.

The orchestrator binds these tools to `ChatOllama`:

- `list_ssh_hosts`
- `ssh_command`
- `local_command`
- `internet_search`
- `current_datetime`
- `mqtt_snapshot`
- `netdata_node_info`
- `netdata_chart_data`
- `prometheus_instant_query`
- `prometheus_range_query`
- `glances_snapshot`
- `glances_metric`
