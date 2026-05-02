"""Monitoring helpers for Netdata, Prometheus, Glances, and SSH snapshots."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .ssh_tools import parse_ssh_config, run_ssh_command


class MonitoringConfigError(RuntimeError):
    pass


def resolve_ssh_hostname(host: str) -> str:
    for item in parse_ssh_config():
        if item.alias == host:
            return item.hostname or item.alias
    return host


def _read_json(url: str, timeout: int = 20) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise MonitoringConfigError(f"Could not reach monitoring endpoint {url}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise MonitoringConfigError(f"Monitoring endpoint did not return JSON: {url}") from exc


def _base_from_env(env_name: str, default_template: str, host: str | None = None) -> str:
    value = os.environ.get(env_name)
    if value:
        return value.rstrip("/")
    if host:
        return default_template.format(host=resolve_ssh_hostname(host)).rstrip("/")
    raise MonitoringConfigError(f"Set {env_name}.")


def netdata_info(host: str) -> dict[str, Any]:
    base = _base_from_env("NETDATA_URL", "http://{host}:19999", host)
    return _read_json(f"{base}/api/v1/info")


def netdata_chart(host: str, chart: str = "system.net", seconds: int = 30, points: int = 30) -> dict[str, Any]:
    base = _base_from_env("NETDATA_URL", "http://{host}:19999", host)
    seconds = max(1, min(seconds, 3600))
    points = max(1, min(points, 300))
    params = urllib.parse.urlencode(
        {
            "chart": chart,
            "format": "json",
            "after": -seconds,
            "before": 0,
            "points": points,
        }
    )
    return _read_json(f"{base}/api/v1/data?{params}")


def prometheus_query(query: str) -> dict[str, Any]:
    base = _base_from_env("PROMETHEUS_URL", "")
    params = urllib.parse.urlencode({"query": query})
    return _read_json(f"{base}/api/v1/query?{params}")


def prometheus_query_range(query: str, seconds: int = 300, step: str = "15s") -> dict[str, Any]:
    base = _base_from_env("PROMETHEUS_URL", "")
    end = int(time.time())
    start = end - max(1, min(seconds, 86400))
    params = urllib.parse.urlencode({"query": query, "start": start, "end": end, "step": step})
    return _read_json(f"{base}/api/v1/query_range?{params}")


def glances_all(host: str) -> dict[str, Any]:
    base = _base_from_env("GLANCES_URL", "http://{host}:61208", host)
    try:
        return _read_json(f"{base}/api/4/all")
    except Exception:
        return _read_json(f"{base}/api/3/all")


def glances_plugin(host: str, plugin: str) -> dict[str, Any]:
    base = _base_from_env("GLANCES_URL", "http://{host}:61208", host)
    plugin = plugin.strip("/")
    try:
        return _read_json(f"{base}/api/4/{plugin}")
    except Exception:
        return _read_json(f"{base}/api/3/{plugin}")


def mqtt_ssh_snapshot(host: str, seconds: int = 30) -> dict[str, Any]:
    seconds = max(1, min(seconds, 120))
    command = (
        "hostname && date && "
        "echo '--- mqtt sockets before ---' && "
        "(ss -ntup 2>/dev/null | grep -Ei '(:1883|:8883|mqtt|mosquitto)' || true) && "
        "echo '--- interfaces before ---' && cat /proc/net/dev && "
        f"sleep {seconds} && date && "
        "echo '--- mqtt sockets after ---' && "
        "(ss -ntup 2>/dev/null | grep -Ei '(:1883|:8883|mqtt|mosquitto)' || true) && "
        "echo '--- interfaces after ---' && cat /proc/net/dev"
    )
    result = run_ssh_command(host, command, timeout=seconds + 20)
    return {
        "host": host,
        "seconds": seconds,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
