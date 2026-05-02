# Current Time Skill

Deploy note: current date/time lookup is low risk and enabled by default in deploy mode.

Use this when the user asks for the current time, date, weekday, UTC timestamp, or time in a named timezone.

Useful commands:

```bash
python3 -m ollama_tools.cli time
python3 -m ollama_tools.cli time --tz America/New_York
python3 hooks/current_time.py --tz UTC
```

The tool returns structured JSON with:

- `timezone`
- `iso`
- `date`
- `time`
- `weekday`
- `utc_iso`

The LangChain agent and MCP server expose this as `current_datetime`.
