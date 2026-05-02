# External Monitoring MCPs

These files are examples for connecting stronger monitoring MCPs alongside the local `ollama-tools` MCP server.

## Netdata MCP

Netdata Agents v2.6+ expose MCP at:

```text
http://HOST:19999/mcp
```

For this project, the local Python tools also support the Netdata HTTP API directly:

```bash
NETDATA_URL=http://server-01:19999 python3 -m ollama_tools.cli ...
```

If the SSH alias does not resolve from this machine, use the host IP from `~/.ssh/config`, such as:

```bash
NETDATA_URL=http://server-01.example.local:19999
```

## Prometheus MCP

Set:

```bash
export PROMETHEUS_URL=http://localhost:9090
```

Then the local MCP server exposes `prometheus_instant_query` and `prometheus_range_query`.

For MQTT-specific Prometheus metrics, run a Mosquitto/MQTT exporter and scrape it from Prometheus.

## Glances MCP

Start Glances web/API mode on the target host:

```bash
glances -w --disable-webui
```

Then query it from this project with:

```bash
GLANCES_URL=http://server-01.example.local:61208
```

The local MCP server exposes `glances_snapshot` and `glances_metric`.

## mcp-ssh-sre

`mcp-ssh-sre` is a read-only SSH diagnostics MCP. Use it when you want predefined SRE checks instead of general command execution.

The example compose file in this directory shows the shape of a deployment. Adjust host, user, key path, and port per target host.
