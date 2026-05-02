#!/usr/bin/env python3
"""Check which natural-language TUI prompts route to tools."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.ollama_tui as tui


SCENARIOS = [
    "can you check the mqtt network coming from server-01",
    "what is my network usage of mqtt-node",
    "is mqtt-node online?",
    "check status of mqtt-node",
    "show mqtt logs on mqtt-node",
    "ls /tmp on mqtt-node",
    "what files are in /var/log on mqtt-node",
    "cat /etc/hostname on mqtt-node",
    "find hostname under /etc on mqtt-node",
    "grep localhost in /etc/hosts on mqtt-node",
    "rsync /tmp from mqtt-node to here",
]


def main() -> int:
    for prompt in SCENARIOS:
        host = tui.find_mentioned_ssh_host(prompt)
        command, label = tui.natural_ssh_command(prompt)
        online = bool(tui.ONLINE_RE.search(prompt))
        routes = bool(host and (command or label == "Rsync request" or online))
        print(prompt)
        print(f"  host: {host}")
        print(f"  route: {label or ('Online check' if online else None)}")
        print(f"  status: {'OK' if routes else 'NO ROUTE'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
