# Ollama API Skill

Deploy note: Ollama API access is enabled by default. First-run setup can store an optional API key/token outside the source tree.

Use `OLLAMA_BASE_URL` to target the Ollama server. The default is:

```bash
http://localhost:11434
```

Useful commands:

```bash
python3 -m ollama_tools.cli models
python3 scripts/ollama_tui.py
python3 scripts/ollama_web.py
```

When chatting in the terminal, list models first, select a model, then send messages through the TUI.
Use `/model` inside the TUI to reopen the model picker.

For browser chat, start `scripts/ollama_web.py` and open:

```text
http://127.0.0.1:8765
```

Use `OLLAMA_WEB_HOST` and `OLLAMA_WEB_PORT` to change the bind address.
If the requested port is busy, the web UI tries later ports and prints the actual URL.
In the browser UI, use the model dropdown, `/model` to list models, or `/model <name>` to switch.
When `.venv/bin/python` exists, the web UI automatically uses it so optional LangChain packages installed in `.venv` are available.
