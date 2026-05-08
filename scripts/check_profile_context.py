#!/usr/bin/env python3
"""Deterministic checks for agent profile routing and context selection."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ollama_tools.context_loader import select_context  # noqa: E402


CASES = [
    ("general", "check disk and docker health on server-01", "ops", "docs/ops-runbook.md"),
    ("general", "make a Home Assistant command_line sensor for Lilith health", "home", "docs/home-assistant.md"),
    ("general", "humanize this status note", "writing", "skills/humanizer.md"),
    ("general", "answer this shorter", "brief", "skills/caveman.md"),
    ("general", "docker-compose up fails with KeyError ContainerConfig", "debug", "skills/systematic-debugging.md"),
    ("general", "implement this fix and run tests", "builder", "skills/systematic-debugging.md"),
    ("builder", "add a small feature and verify it", "builder", "skills/systematic-debugging.md"),
    ("general", "write a detailed research report on home battery backup to canvas", "deep_research", "docs/research-report.md"),
    ("deep_research", "solar inverter market trends", "deep_research", "docs/research-report.md"),
    ("general", "add a compact verbose pane beside chat", "frontend", "skills/frontend-design.md"),
    ("general", "make a local skill for MQTT troubleshooting", "skill_creator", "skills/skill-creator.md"),
    ("ops", "make this shorter", "ops", "docs/ops-runbook.md"),
    ("caveman", "what time is it", "brief", "skills/caveman.md"),
    ("humanizer", "rewrite this", "writing", "skills/humanizer.md"),
]


def main() -> int:
    failures: list[str] = []
    for requested, prompt, expected_profile, expected_path in CASES:
        selection = select_context(ROOT, requested, prompt)
        ok = selection.active_profile == expected_profile and expected_path in selection.paths
        status = "ok" if ok else "FAIL"
        print(
            f"{status}\trequested={requested}\tactive={selection.active_profile}"
            f"\texpected={expected_profile}\tpath={expected_path}"
        )
        if not ok:
            failures.append(
                f"{requested!r} / {prompt!r}: got {selection.active_profile} {selection.paths}, "
                f"expected {expected_profile} with {expected_path}"
            )
    if failures:
        print("\nFailures:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
