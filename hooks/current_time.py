#!/usr/bin/env python3
"""Hook wrapper for current local date/time."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ollama_tools.time_tools import current_time
from ollama_tools.tool_registry import hook_enabled


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tz", help="IANA timezone, e.g. America/New_York")
    args = parser.parse_args()
    try:
        if not hook_enabled("current_time"):
            raise RuntimeError("Hook 'current_time' is disabled by configuration.")
        print(json.dumps(current_time(args.tz).__dict__, indent=2))
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
