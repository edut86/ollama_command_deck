# Monitoring MCP Skill

Deploy note: monitoring MCP tools are disabled by default in deploy mode. Enable them only when the target monitoring endpoints are trusted and intended for this app.

Use these monitoring integrations when the user asks about live system metrics, MQTT traffic, health, or time-window snapshots.

Available local tools:

- `current_datetime`: current local date/time, optionally for an IANA timezone.
- `mqtt_snapshot`: timed SSH MQTT/network sample.
- `netdata_node_info`: Netdata node information.
- `netdata_chart_data`: recent Netdata chart values.
- `prometheus_instant_query`: PromQL instant query.
- `prometheus_range_query`: PromQL range query.
- `glances_snapshot`: full Glances API snapshot.
- `glances_metric`: one Glances plugin metric.

Useful commands:

```bash
python3 -m ollama_tools.cli mqtt-snapshot server-01 --seconds 30
python3 -m ollama_tools.cli time --tz America/New_York
python3 -m ollama_tools.cli netdata-chart server-01 --chart system.net --seconds 30
PROMETHEUS_URL=http://localhost:9090 python3 -m ollama_tools.cli prom-query 'up'
python3 -m ollama_tools.cli glances server-01 --plugin network
```

Use external MCP examples from `mcp_servers/external/` for Netdata MCP endpoints and mcp-ssh-sre containers.
