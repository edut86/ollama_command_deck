#!/usr/bin/env python3
"""Hook wrapper for non-sudo commands on SSH config hosts."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ollama_tools.ssh_tools import run_ssh_command
from ollama_tools.tool_registry import hook_enabled


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("host")
    parser.add_argument("command")
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()
    try:
        if not hook_enabled("run_ssh"):
            raise RuntimeError("Hook 'run_ssh' is disabled by configuration.")
        result = run_ssh_command(args.host, args.command, timeout=args.timeout)
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
