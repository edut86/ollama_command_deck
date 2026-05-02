#!/usr/bin/env python3
"""Hook wrapper for non-sudo local commands."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ollama_tools.shell_tools import run_local_command
from ollama_tools.tool_registry import hook_enabled


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("--cwd")
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()
    try:
        if not hook_enabled("run_local"):
            raise RuntimeError("Hook 'run_local' is disabled by configuration.")
        result = run_local_command(args.command, cwd=args.cwd, timeout=args.timeout)
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
