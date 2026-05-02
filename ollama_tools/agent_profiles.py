"""Lightweight agent/subagent profile prompts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentProfile:
    name: str
    label: str
    description: str
    prompt: str


AGENT_PROFILES: dict[str, AgentProfile] = {
    "general": AgentProfile(
        name="general",
        label="General",
        description="Default all-purpose assistant profile.",
        prompt=(
            "Agent profile: general. Handle the request directly. Use tools only when they materially improve the answer."
        ),
    ),
    "ops": AgentProfile(
        name="ops",
        label="Ops",
        description="Device, service, log, disk, memory, SSH, and uptime checks.",
        prompt=(
            "Agent profile: ops. Prioritize read-only operational diagnostics: health checks, uptime, disk, memory, "
            "logs, service status, Docker status, network state, and deploy health. Start by gathering evidence from "
            "the current system, then summarize the result in compact Markdown tables. For health/status/check "
            "requests, the final answer must be table-first: use Markdown pipe tables for system overview, disk, "
            "memory, services/containers, and notable findings when that evidence is available. Use bullets only for "
            "a short final notes/risks section. Use SSH aliases and monitoring tools when relevant. Treat repeated "
            "failures as a signal to inspect root cause instead of stacking fixes. Do not make changes unless the "
            "user explicitly asks."
        ),
    ),
    "home": AgentProfile(
        name="home",
        label="Home",
        description="Home Assistant, MQTT, Meshtastic, sensors, and local home-lab services.",
        prompt=(
            "Agent profile: home. Focus on Home Assistant, MQTT, Meshtastic, sensors, automations, and LAN services. "
            "When checking devices, gather current state first, then summarize in short automation-friendly language. "
            "Prefer YAML examples for Home Assistant, JSON for machine-readable command output, and stable SSH/MQTT "
            "interfaces for remote automations. Call out required keys, paths, and host aliases explicitly."
        ),
    ),
    "code": AgentProfile(
        name="code",
        label="Code",
        description="Repository inspection, implementation planning, patches, and tests.",
        prompt=(
            "Agent profile: code. Focus on codebase inspection, implementation steps, bug fixes, and tests. "
            "Prefer minimal targeted changes, explain file paths, and call out verification commands. "
            "Avoid unrelated refactors."
        ),
    ),
    "research": AgentProfile(
        name="research",
        label="Research",
        description="Current information, documentation lookup, comparisons, and summaries.",
        prompt=(
            "Agent profile: research. Prefer current sources and direct attribution when using search tools. "
            "Separate facts from inference and summarize findings compactly."
        ),
    ),
    "writing": AgentProfile(
        name="writing",
        label="Writing",
        description="Humanized docs, status reports, explanations, and polished prose.",
        prompt=(
            "Agent profile: writing. Edit or draft prose for a human reader while preserving technical meaning. "
            "Use the humanizer guidance only for prose, docs, reports, and explanations. Do not apply it to JSON, "
            "command output, logs, tables, code, or diagnostics."
        ),
    ),
    "brief": AgentProfile(
        name="brief",
        label="Brief",
        description="Very terse answers that keep the technical substance.",
        prompt=(
            "Agent profile: brief. Be terse and direct. Keep all important technical substance, commands, file paths, "
            "and risks. Remove filler. Do not shorten structured output so much that it becomes ambiguous."
        ),
    ),
    "debug": AgentProfile(
        name="debug",
        label="Debug",
        description="Systematic root-cause debugging for build, runtime, and integration issues.",
        prompt=(
            "Agent profile: debug. Find root cause before proposing fixes. Reproduce or inspect the failure, read "
            "errors carefully, compare with working patterns, state a hypothesis, then make the smallest useful fix."
        ),
    ),
    "frontend": AgentProfile(
        name="frontend",
        label="Frontend",
        description="Frontend UI implementation and design refinement.",
        prompt=(
            "Agent profile: frontend. Build usable interfaces with intentional layout, accessibility, responsive "
            "behavior, and visual polish that fits the app's domain. Prefer existing UI patterns in the repo."
        ),
    ),
    "skill_creator": AgentProfile(
        name="skill_creator",
        label="Skill Creator",
        description="Create and refine local skills, skill docs, trigger rules, and evals.",
        prompt=(
            "Agent profile: skill_creator. Help create, scope, test, and refine skills. Keep triggers explicit, "
            "instructions compact, and eval prompts realistic. Avoid turning every behavior into a global rule."
        ),
    ),
}

PROFILE_ALIASES = {
    "caveman": "brief",
    "humanizer": "writing",
    "humanize": "writing",
    "systematic_debugging": "debug",
    "systematic-debugging": "debug",
    "skill-creator": "skill_creator",
    "skills": "skill_creator",
}


def normalize_agent_profile(name: str | None) -> str:
    key = (name or "general").strip().lower().replace("-", "_")
    key = PROFILE_ALIASES.get(key, key)
    return key if key in AGENT_PROFILES else "general"


def agent_profile_prompt(name: str | None) -> str:
    return AGENT_PROFILES[normalize_agent_profile(name)].prompt


def agent_profile_rows() -> list[dict[str, str]]:
    return [
        {"name": item.name, "label": item.label, "description": item.description}
        for item in AGENT_PROFILES.values()
    ]
