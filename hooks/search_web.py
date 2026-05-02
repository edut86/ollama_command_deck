#!/usr/bin/env python3
"""Hook wrapper for configured internet search."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ollama_tools.web_search import search_web
from ollama_tools.tool_registry import hook_enabled


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--count", type=int, default=5)
    args = parser.parse_args()
    try:
        if not hook_enabled("search_web"):
            raise RuntimeError("Hook 'search_web' is disabled by configuration.")
        print(json.dumps([item.__dict__ for item in search_web(args.query, args.count)], indent=2))
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
