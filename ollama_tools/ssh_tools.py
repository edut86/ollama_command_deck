"""SSH config parsing and remote command helpers."""

from __future__ import annotations

import subprocess
import socket
from dataclasses import dataclass
from pathlib import Path

from .config import get_ssh_config_path, get_ssh_known_hosts_path
from .safety import validate_command
from .tool_registry import require_tool


@dataclass(frozen=True)
class SshHost:
    alias: str
    hostname: str | None = None
    user: str | None = None


def _ssh_config_path(path: str | None = None) -> Path:
    configured = path or get_ssh_config_path()
    return Path(configured).expanduser() if configured else Path.home() / ".ssh" / "config"


def _ssh_known_hosts_path() -> Path | None:
    configured = get_ssh_known_hosts_path()
    return Path(configured).expanduser() if configured else None


def parse_ssh_config(path: str | None = None) -> list[SshHost]:
    require_tool("ssh_command")
    config_path = _ssh_config_path(path)
    if not config_path.exists():
        return []

    hosts: list[SshHost] = []
    current_aliases: list[str] = []
    current: dict[str, str] = {}

    def flush() -> None:
        nonlocal current_aliases, current
        for alias in current_aliases:
            if any(char in alias for char in "*?!"):
                continue
            hosts.append(SshHost(alias=alias, hostname=current.get("hostname"), user=current.get("user")))
        current_aliases = []
        current = {}

    for raw_line in config_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        key, value = parts[0].lower(), parts[1].strip()
        if key == "host":
            flush()
            current_aliases = value.split()
        elif current_aliases and key in {"hostname", "user"}:
            current[key] = value
    flush()

    unique: dict[str, SshHost] = {}
    for host in hosts:
        unique.setdefault(host.alias, host)
    return sorted(unique.values(), key=lambda item: item.alias)


def _resolve_container_hostname(hostname: str | None) -> str | None:
    """Return a hostname override for container DNS edge cases.

    Docker containers often cannot resolve mDNS names such as foo.local even
    when the host can. If Docker has an alternate hosts entry like
    foo.localdomain, use that as an OpenSSH HostName override.
    """
    if not hostname:
        return None
    try:
        socket.getaddrinfo(hostname, None)
        return None
    except socket.gaierror:
        pass
    candidates: list[str] = []
    if hostname.endswith(".local"):
        candidates.append(hostname.removesuffix(".local") + ".localdomain")
        candidates.append(hostname.removesuffix(".local"))
    for candidate in candidates:
        try:
            socket.getaddrinfo(candidate, None)
            return candidate
        except socket.gaierror:
            continue
    return None


def run_ssh_command(host: str, command: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    require_tool("ssh_command")
    validate_command(command)
    config_path = _ssh_config_path()
    known_hosts_path = _ssh_known_hosts_path()
    configured_hosts = {item.alias: item for item in parse_ssh_config(str(config_path))}
    if configured_hosts and host not in configured_hosts:
        raise ValueError(f"SSH host '{host}' is not listed in {config_path}.")
    ssh_cmd = ["ssh", "-o", "BatchMode=yes"]
    if config_path.exists():
        ssh_cmd.extend(["-F", str(config_path)])
    if known_hosts_path:
        ssh_cmd.extend(["-o", f"UserKnownHostsFile={known_hosts_path}"])
    configured_hostname = configured_hosts.get(host).hostname if configured_hosts else None
    hostname_override = _resolve_container_hostname(configured_hostname)
    if hostname_override:
        ssh_cmd.extend(["-o", f"HostName={hostname_override}"])
        if configured_hostname:
            ssh_cmd.extend(["-o", f"HostKeyAlias={configured_hostname}"])
    ssh_cmd.extend([host, command])
    return subprocess.run(
        ssh_cmd,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
