#!/usr/bin/env python3
"""Headless Ollama Command Deck chat CLI for automations and Home Assistant."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ollama_tools.langchain_orchestrator import (  # noqa: E402
    LangChainUnavailableError,
    stream_langchain_agent_events,
)
from ollama_tools.ollama_api import ChatStats  # noqa: E402
from ollama_tools.agent_profiles import AGENT_PROFILES, PROFILE_ALIASES, agent_profile_prompt, normalize_agent_profile  # noqa: E402
from ollama_tools.context_loader import context_prompt, select_context  # noqa: E402
from ollama_tools.tool_registry import all_metadata  # noqa: E402
from scripts.ollama_tui import whitespace_columns_to_markdown  # noqa: E402


DEFAULT_MODEL = "qwen3.5:9b"
DEFAULT_PERSONALITY = "sassy"

PERSONALITIES = {
    "default": "Use a direct, practical tone.",
    "sassy": (
        "Personality: sassy, sharp, and lightly sarcastic, but always useful. "
        "Keep the jokes brief. Do not insult the user. Prioritize correct operations output."
    ),
    "snarky": (
        "Personality: snarky, dry, and visibly unimpressed, while still being useful. "
        "Use a sharp one-liner or dry aside in nearly every reply. Keep the bite playful: no insults, cruelty, harassment, or profanity."
    ),
    "rude": (
        "Personality: rude, impatient, and blunt, while still solving the user's problem accurately. "
        "Use short dismissive asides and direct corrections. Do not provide cheerful customer-service filler. "
        "Hard limits: no slurs, hate, harassment based on protected traits, threats, sexual content, or profanity."
    ),
    "formal": "Personality: formal, precise, and restrained.",
}

SKILL_FILE_NAMES = {
    "current_time": "current-time.md",
    "ollama_api": "ollama-api.md",
    "internet_search": "internet-search.md",
    "local_command": "local-command.md",
    "device_ssh": "device-ssh.md",
    "langchain_orchestrator": "langchain-orchestrator.md",
    "monitoring_mcps": "monitoring-mcps.md",
}


def _enabled_inventory() -> list[dict[str, Any]]:
    return [asdict(item) for item in all_metadata()]


def _load_enabled_skills(max_chars: int = 9000) -> str:
    """Load enabled local skill docs as model guidance, bounded for prompt size."""
    enabled = {
        item.name
        for item in all_metadata()
        if item.kind == "skill" and item.enabled
    }
    parts: list[str] = []
    used = 0
    skills_dir = ROOT / "skills"
    for skill_name in sorted(enabled):
        filename = SKILL_FILE_NAMES.get(skill_name, skill_name.replace("_", "-") + ".md")
        path = skills_dir / filename
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
        block = f"\n\n[Enabled skill: {skill_name}]\n{text}"
        if used + len(block) > max_chars:
            remaining = max_chars - used
            if remaining > 200:
                parts.append(block[:remaining] + "\n[skill text truncated]")
            break
        parts.append(block)
        used += len(block)
    return "".join(parts)


def _system_prompt(personality: str, agent_profile: str, user_text: str = "") -> str:
    inventory = _enabled_inventory()
    enabled_lines = [
        f"- {item['kind']}:{item['name']} risk={item['risk']} enabled={item['enabled']} - {item['description']}"
        for item in inventory
    ]
    skill_docs = _load_enabled_skills()
    profile_context = context_prompt(ROOT, agent_profile, user_text)
    personality_text = PERSONALITIES.get(personality, PERSONALITIES[DEFAULT_PERSONALITY])
    return (
        "Your name is Lilith. You are the headless CLI agent for Ollama Command Deck.\n"
        f"{personality_text}\n\n"
        f"{agent_profile_prompt(agent_profile)}\n\n"
        "Use the bound tools for SSH, local shell, internet search, time, Ollama, and monitoring work. "
        "The configured hooks and MCP server expose the same operational capabilities; respect the enabled/disabled registry below. "
        "Never claim you used a disabled tool. Never request or run sudo.\n\n"
        "For command or monitoring output, return clean Markdown tables using | separators and a header divider row. "
        "Never paste raw whitespace- or tab-aligned tables as the final answer. For health/status/check requests, "
        "the final answer must be table-first: include compact Markdown pipe tables for system overview, disk, "
        "memory, services/containers, and notable findings when that evidence is available. Use bullets only for "
        "short final notes/risks.\n\n"
        "Enabled capability registry:\n"
        + "\n".join(enabled_lines)
        + skill_docs
        + profile_context
    )


def _stats_to_dict(stats: ChatStats | None) -> dict[str, Any] | None:
    if stats is None:
        return None
    tokens_per_second = (stats.response_tokens / (stats.total_duration_ms / 1000)) if stats.total_duration_ms else 0.0
    return {
        "prompt_tokens": stats.prompt_tokens,
        "response_tokens": stats.response_tokens,
        "total_duration_ms": stats.total_duration_ms,
        "tokens_per_second": tokens_per_second,
    }


def run_agent(prompt: str, *, model: str, personality: str, agent_profile: str, max_tool_rounds: int, show_commands: bool) -> dict[str, Any]:
    context_selection = select_context(ROOT, agent_profile, prompt)
    agent_profile = context_selection.active_profile
    if context_selection.routed and show_commands:
        print(
            f"profile: routed {context_selection.requested_profile} -> {context_selection.active_profile} ({context_selection.route_reason})",
            file=sys.stderr,
        )
    if show_commands:
        print("context: " + ", ".join(context_selection.paths), file=sys.stderr)
    messages = [
        {"role": "system", "content": _system_prompt(personality, agent_profile, prompt)},
        {"role": "user", "content": prompt},
    ]
    commands: list[str] = []
    final_text = ""
    final_stats: ChatStats | None = None
    for event in stream_langchain_agent_events(model, messages, max_tool_rounds=max_tool_rounds):
        if event["type"] == "cmd":
            command = str(event.get("command") or "")
            commands.append(command)
            if show_commands:
                print(f"cmd: {command}", file=sys.stderr)
        elif event["type"] == "final":
            final_text = whitespace_columns_to_markdown(str(event.get("text") or ""))
            final_stats = event.get("stats")
    return {
        "ok": True,
        "model": model,
        "agent": True,
        "personality": personality,
        "requested_agent_profile": context_selection.requested_profile,
        "agent_profile": agent_profile,
        "routed": context_selection.routed,
        "route_reason": context_selection.route_reason,
        "context": context_selection.paths,
        "text": final_text,
        "commands": commands,
        "stats": _stats_to_dict(final_stats),
        "capabilities": _enabled_inventory(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="ollama-cli",
        description="Headless qwen/Lilith agent CLI for Ollama Command Deck automations.",
    )
    parser.add_argument("prompt", nargs="*", help="Prompt to send. If omitted, stdin is read.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--personality", default=DEFAULT_PERSONALITY, choices=sorted(PERSONALITIES))
    parser.add_argument("--agent-profile", default="general", choices=sorted(set(AGENT_PROFILES) | set(PROFILE_ALIASES)))
    parser.add_argument("--json", action="store_true", help="Print a JSON object for Home Assistant/automation use.")
    parser.add_argument("--show-commands", action="store_true", help="Print tool command trace to stderr.")
    parser.add_argument("--max-tool-rounds", type=int, default=6)
    parser.add_argument("--list-capabilities", action="store_true", help="Print configured tools/hooks/skills and exit.")
    args = parser.parse_args()

    if args.list_capabilities:
        data = {"ok": True, "capabilities": _enabled_inventory()}
        print(json.dumps(data, indent=2) if args.json else "\n".join(
            f"{item['kind']}\t{item['name']}\t{item['enabled']}\t{item['risk']}\t{item['description']}"
            for item in data["capabilities"]
        ))
        return 0

    prompt = " ".join(args.prompt).strip() if args.prompt else sys.stdin.read().strip()
    if not prompt:
        print("error: prompt is required", file=sys.stderr)
        return 2

    try:
        result = run_agent(
            prompt,
            model=args.model,
            personality=args.personality,
            agent_profile=args.agent_profile,
            max_tool_rounds=max(1, args.max_tool_rounds),
            show_commands=args.show_commands,
        )
    except (LangChainUnavailableError, ValueError, RuntimeError, Exception) as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(result["text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
