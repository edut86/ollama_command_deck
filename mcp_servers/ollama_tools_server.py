#!/usr/bin/env python3
"""MCP server exposing local Ollama workflow tools.

Run with:
    python3 mcp_servers/ollama_tools_server.py
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - depends on optional package
    raise SystemExit("Install the optional MCP dependency first: python3 -m pip install mcp") from exc

from ollama_tools.ollama_api import list_models
from ollama_tools.monitoring import (
    glances_all,
    glances_plugin,
    mqtt_ssh_snapshot,
    netdata_chart,
    netdata_info,
    prometheus_query,
    prometheus_query_range,
)
from ollama_tools.shell_tools import run_local_command
from ollama_tools.ssh_tools import parse_ssh_config, run_ssh_command
from ollama_tools.time_tools import current_time
from ollama_tools.tool_registry import require_tool
from ollama_tools.web_search import search_web

mcp = FastMCP("ollama-tools")


@mcp.tool()
def ollama_models() -> list[dict]:
    """List models available from the configured Ollama API."""
    require_tool("ollama_models")
    return [model.__dict__ for model in list_models()]


@mcp.tool()
def local_command(command: str, cwd: str | None = None, timeout: int = 60) -> dict:
    """Run a non-sudo local shell command."""
    require_tool("local_command")
    result = run_local_command(command, cwd=cwd, timeout=timeout)
    return result.__dict__


@mcp.tool()
def ssh_hosts() -> list[dict]:
    """List SSH host aliases from ~/.ssh/config."""
    require_tool("ssh_command")
    return [host.__dict__ for host in parse_ssh_config()]


@mcp.tool()
def ssh_command(host: str, command: str, timeout: int = 60) -> dict:
    """Run a non-sudo command on an SSH host alias from ~/.ssh/config."""
    require_tool("ssh_command")
    result = run_ssh_command(host, command, timeout=timeout)
    return {
        "host": host,
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


@mcp.tool()
def internet_search(query: str, count: int = 5) -> list[dict]:
    """Search the internet using SEARXNG_URL or BRAVE_SEARCH_API_KEY."""
    require_tool("internet_search")
    return [item.__dict__ for item in search_web(query, count)]


@mcp.tool()
def current_datetime(timezone: str | None = None) -> dict:
    """Return the current date/time. Optionally pass an IANA timezone such as America/New_York."""
    require_tool("current_datetime")
    return current_time(timezone).__dict__


@mcp.tool()
def mqtt_snapshot(host: str, seconds: int = 30) -> dict:
    """Take a timed MQTT/network snapshot over SSH for an SSH alias."""
    require_tool("mqtt_snapshot")
    return mqtt_ssh_snapshot(host, seconds=seconds)


@mcp.tool()
def netdata_node_info(host: str) -> dict:
    """Fetch Netdata node info from http://<host>:19999/api/v1/info or NETDATA_URL."""
    require_tool("netdata_node_info")
    return netdata_info(host)


@mcp.tool()
def netdata_chart_data(host: str, chart: str = "system.net", seconds: int = 30, points: int = 30) -> dict:
    """Fetch recent Netdata chart data for a host."""
    require_tool("netdata_chart_data")
    return netdata_chart(host, chart=chart, seconds=seconds, points=points)


@mcp.tool()
def prometheus_instant_query(query: str) -> dict:
    """Run a Prometheus instant query using PROMETHEUS_URL."""
    require_tool("prometheus_instant_query")
    return prometheus_query(query)


@mcp.tool()
def prometheus_range_query(query: str, seconds: int = 300, step: str = "15s") -> dict:
    """Run a Prometheus range query using PROMETHEUS_URL."""
    require_tool("prometheus_range_query")
    return prometheus_query_range(query, seconds=seconds, step=step)


@mcp.tool()
def glances_snapshot(host: str) -> dict:
    """Fetch all Glances metrics from http://<host>:61208/api/4/all."""
    require_tool("glances_snapshot")
    return glances_all(host)


@mcp.tool()
def glances_metric(host: str, plugin: str) -> dict:
    """Fetch one Glances plugin metric, such as network, cpu, mem, fs, or processes."""
    require_tool("glances_metric")
    return glances_plugin(host, plugin)


if __name__ == "__main__":
    mcp.run()
