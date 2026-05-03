"""Central enable/disable policy for tools, hooks, MCPs, and skills."""

from __future__ import annotations

from dataclasses import dataclass

from .config import get_hook_enabled, get_skill_enabled, get_thunderbird_enabled, get_tool_enabled


@dataclass(frozen=True)
class ToolMeta:
    name: str
    kind: str
    description: str
    risk: str
    enabled: bool


TOOL_DESCRIPTIONS = {
    "ollama_models": ("tool", "List configured Ollama models", "low"),
    "current_datetime": ("tool", "Read current date/time", "low"),
    "internet_search": ("tool", "Search the internet", "medium"),
    "local_command": ("tool", "Run local shell commands", "high"),
    "ssh_command": ("tool", "Run commands on SSH aliases", "high"),
    "monitoring": ("tool", "Read monitoring systems such as Netdata, Glances, Prometheus, MQTT", "medium"),
    "thunderbird_readonly": ("tool", "Analyze read-only Thunderbird message snippets", "medium"),
}

HOOK_DESCRIPTIONS = {
    "current_time": ("hook", "Current time hook", "low"),
    "search_web": ("hook", "Internet search hook", "medium"),
    "run_local": ("hook", "Local command hook", "high"),
    "run_ssh": ("hook", "SSH command hook", "high"),
}

SKILL_DESCRIPTIONS = {
    "current_time": ("skill", "Current time skill", "low"),
    "ollama_api": ("skill", "Ollama API skill", "low"),
    "internet_search": ("skill", "Internet search skill", "medium"),
    "local_command": ("skill", "Local command skill", "high"),
    "device_ssh": ("skill", "Device SSH skill", "high"),
    "langchain_orchestrator": ("skill", "LangChain orchestration skill", "medium"),
    "monitoring_mcps": ("skill", "Monitoring MCP skill", "medium"),
}


def tool_enabled(name: str) -> bool:
    if name == "thunderbird_readonly":
        return get_thunderbird_enabled()
    if name in {"list_ssh_hosts"}:
        return get_tool_enabled("ssh_command")
    if name in {"mqtt_snapshot"}:
        return get_tool_enabled("ssh_command") and get_tool_enabled("monitoring")
    if name in {"netdata_node_info", "netdata_chart_data", "prometheus_instant_query", "prometheus_range_query", "glances_snapshot", "glances_metric"}:
        return get_tool_enabled("monitoring")
    return get_tool_enabled(name)


def hook_enabled(name: str) -> bool:
    return get_hook_enabled(name)


def skill_enabled(name: str) -> bool:
    return get_skill_enabled(name)


def require_tool(name: str) -> None:
    if not tool_enabled(name):
        raise RuntimeError(f"Tool '{name}' is disabled by configuration.")


def all_metadata() -> list[ToolMeta]:
    rows: list[ToolMeta] = []
    for name, (kind, desc, risk) in TOOL_DESCRIPTIONS.items():
        rows.append(ToolMeta(name, kind, desc, risk, tool_enabled(name)))
    for name, (kind, desc, risk) in HOOK_DESCRIPTIONS.items():
        rows.append(ToolMeta(name, kind, desc, risk, hook_enabled(name)))
    for name, (kind, desc, risk) in SKILL_DESCRIPTIONS.items():
        rows.append(ToolMeta(name, kind, desc, risk, skill_enabled(name)))
    return rows
