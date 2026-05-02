"""Small profile-scoped context loader for agent prompts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from ollama_tools.agent_profiles import normalize_agent_profile


@dataclass(frozen=True)
class ContextItem:
    path: str
    title: str
    text: str


@dataclass(frozen=True)
class ContextSelection:
    requested_profile: str
    active_profile: str
    routed: bool
    route_reason: str
    paths: list[str]


BASE_DOCS = ("docs/project-overview.md", "docs/devices.md")

PROFILE_DOCS: dict[str, tuple[str, ...]] = {
    "ops": ("docs/ops-runbook.md", "skills/systematic-debugging.md"),
    "home": ("docs/home-assistant.md", "docs/ops-runbook.md"),
    "code": ("skills/systematic-debugging.md",),
    "debug": ("skills/systematic-debugging.md",),
    "frontend": ("skills/frontend-design.md",),
    "writing": ("skills/humanizer.md",),
    "brief": ("skills/caveman.md",),
    "skill_creator": ("skills/skill-creator.md",),
}

KEYWORD_DOCS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("home assistant", "mqtt", "meshtastic", "sensor", "automation"), ("docs/home-assistant.md",)),
    (("docker", "ssh", "health", "disk", "memory", "uptime", "service"), ("docs/ops-runbook.md",)),
    (("bug", "error", "traceback", "failing", "debug", "root cause"), ("skills/systematic-debugging.md",)),
    (("frontend", "ui", "css", "layout", "responsive", "button", "pane"), ("skills/frontend-design.md",)),
    (("humanize", "rewrite", "prose", "polish", "docs"), ("skills/humanizer.md",)),
    (("skill", "skill.md", "trigger", "eval"), ("skills/skill-creator.md",)),
)

ROUTE_RULES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("debug", ("traceback", "exception", "keyerror", "error:", "failed", "failing", "broken", "bug", "root cause", "containerconfig"), "debugging/build failure terms"),
    ("skill_creator", ("skill.md", "skill creator", "new skill", "create a skill", "local skill", "skill profile", "trigger rule", "eval prompt"), "skill-creation terms"),
    ("home", ("home assistant", "hass", "mqtt", "meshtastic", "sensor", "automation", "command_line", "shell_command"), "Home Assistant/MQTT terms"),
    ("frontend", ("frontend", "ui", "css", "layout", "responsive", "pane", "button", "dropdown", "screen", "browser"), "frontend/UI terms"),
    ("writing", ("humanize", "rewrite", "polish", "prose", "status note", "make this sound"), "writing/prose terms"),
    ("brief", ("shorter", "terse", "brief", "caveman", "one line", "few words"), "brief-output terms"),
    ("ops", ("ssh", "docker", "disk", "memory", "uptime", "service", "health check", "partition", "df -h", "systemctl"), "ops/device terms"),
    ("research", ("search", "latest", "look up", "current docs", "compare", "source"), "research/current-info terms"),
)


def _read_context_file(context_dir: Path, rel_path: str) -> ContextItem | None:
    path = context_dir / rel_path
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="ignore").strip()
    if not text:
        return None
    title = rel_path.rsplit("/", 1)[-1].removesuffix(".md").replace("-", " ").title()
    return ContextItem(path=rel_path, title=title, text=text)


def select_context_paths(agent_profile: str, user_text: str | None = None) -> list[str]:
    """Return ordered context paths for a profile and optional user prompt."""
    profile = normalize_agent_profile(agent_profile)
    selected: list[str] = []

    def add_many(paths: tuple[str, ...]) -> None:
        for path in paths:
            if path not in selected:
                selected.append(path)

    add_many(BASE_DOCS)
    add_many(PROFILE_DOCS.get(profile, ()))

    query = (user_text or "").lower()
    if query:
        for keywords, paths in KEYWORD_DOCS:
            if any(keyword in query for keyword in keywords):
                add_many(paths)
    return selected


def route_agent_profile(agent_profile: str | None, user_text: str | None = None) -> tuple[str, str]:
    """Route general requests to a more specific profile using deterministic keywords."""
    requested = normalize_agent_profile(agent_profile)
    if requested != "general":
        return requested, ""
    query = (user_text or "").lower()
    if not query:
        return requested, ""
    normalized_query = re.sub(r"\s+", " ", query)
    for profile, keywords, reason in ROUTE_RULES:
        if any(keyword in normalized_query for keyword in keywords):
            return profile, reason
    return requested, ""


def select_context(root: Path, agent_profile: str | None, user_text: str | None = None) -> ContextSelection:
    requested = normalize_agent_profile(agent_profile)
    active, reason = route_agent_profile(requested, user_text)
    paths = [
        item.path
        for item in load_context_items(root, active, user_text)
    ]
    return ContextSelection(
        requested_profile=requested,
        active_profile=active,
        routed=active != requested,
        route_reason=reason,
        paths=paths,
    )


def load_context_items(root: Path, agent_profile: str, user_text: str | None = None) -> list[ContextItem]:
    context_dir = root / "context"
    return [
        item
        for rel_path in select_context_paths(agent_profile, user_text)
        if (item := _read_context_file(context_dir, rel_path)) is not None
    ]


def context_prompt(root: Path, agent_profile: str, user_text: str | None = None, max_chars: int = 7000) -> str:
    """Build a bounded prompt block from profile-scoped context docs."""
    items = load_context_items(root, agent_profile, user_text)
    if not items:
        return ""

    parts = [
        "\n\nProfile-scoped context follows. Use it when relevant, but do not treat it as higher priority than the user's request."
    ]
    used = sum(len(part) for part in parts)
    for item in items:
        block = f"\n\n[Context: {item.path}]\n{item.text}"
        if used + len(block) > max_chars:
            remaining = max_chars - used
            if remaining > 200:
                parts.append(block[:remaining] + "\n[context truncated]")
            break
        parts.append(block)
        used += len(block)
    return "".join(parts)
