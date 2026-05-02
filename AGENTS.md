# Agent Profiles And Lightweight Subagents

Ollama Command Deck supports lightweight agent profiles. These are intentionally not
parallel always-on worker processes. They are focused prompt/tool profiles that
run on the same model and orchestration path as the normal Lilith agent.

This design is a better fit for small local Ollama systems because it avoids
running several model generations at once.

## Profiles

| Profile | Purpose |
|---|---|
| `general` | Default all-purpose assistant |
| `ops` | Device health, SSH, logs, disk, memory, Docker, services |
| `home` | Home Assistant, MQTT, Meshtastic, sensors, automations |
| `code` | Repo inspection, implementation planning, patches, tests |
| `builder` | Bounded code-writing feedback loop: inspect, patch, verify, revise, report |
| `research` | Search-backed summaries, documentation lookup, comparisons |
| `writing` | Humanized docs, status notes, explanations, polished prose |
| `brief` | Terse answers that preserve commands, facts, and risks |
| `debug` | Root-cause debugging for build, runtime, and integration failures |
| `frontend` | UI layout, responsive behavior, and frontend refinement |
| `skill_creator` | Local skills, trigger rules, context docs, and eval prompts |

## Web TUI

Use the `Agent:` dropdown in the header to choose the active profile.

Slash command:

```text
/agent_profile ops
/agent_profile home
/agent_profile code
/agent_profile builder
/agent_profile research
/agent_profile writing
/agent_profile brief
/agent_profile debug
/agent_profile frontend
/agent_profile skill_creator
/agent_profile general
```

The selected profile is saved with each chat session.

When `general` is selected, obvious prompts are routed automatically:

| Prompt mentions | Routed profile |
|---|---|
| Docker, SSH, disk, memory, uptime, services | `ops` |
| errors, tracebacks, `ContainerConfig`, failing builds | `debug` |
| implement, patch, write code, run tests, verify fixes | `builder` |
| Home Assistant, MQTT, Meshtastic, sensors, automations | `home` |
| UI, CSS, layout, pane, responsive behavior | `frontend` |
| humanize, rewrite, polish prose | `writing` |
| shorter, terse, caveman | `brief` |
| skill docs, trigger rules, eval prompts | `skill_creator` |
| search, latest, current docs | `research` |

The verbose pane shows the active profile, route reason, and context files for
each request.

## CLI

The headless CLI accepts `--agent-profile`:

```bash
./scripts/ollama_cli.py --agent-profile ops --json "check health on mqtt-node"
./scripts/ollama_cli.py --agent-profile home --json "write a Home Assistant sensor for mqtt-node health"
./scripts/ollama_cli.py --agent-profile code "look over this repo and suggest the next small fix"
./scripts/ollama_cli.py --agent-profile builder "implement this fix and run checks"
./scripts/ollama_cli.py --agent-profile frontend "tighten the verbose pane layout"
./scripts/ollama_cli.py --agent-profile skill_creator "draft an MQTT troubleshooting skill"
./scripts/ollama_cli.py --agent-profile caveman "say this shorter"
```

Inside the Docker deployment:

```bash
docker compose exec web python scripts/ollama_cli.py \
  --model qwen3.5:latest \
  --agent-profile ops \
  --json "check health on mqtt-node"
```

## Capability Model

Profiles do not bypass the tool registry. If a tool, hook, or skill is disabled,
the profile still cannot use it.

| Layer | Behavior |
|---|---|
| Agent profile | Adds task-specific system guidance |
| LangChain tools | Bound only when enabled by config/overrides |
| Hooks | Listed as capabilities and backed by the same tool functions |
| MCP server | Exposes the same operational functions to external clients |
| Skills | Enabled Markdown files can be loaded into CLI guidance |
| Context docs | Profile-scoped files from `context/` are injected only when selected |

## Profile-Scoped Context

The loader in `ollama_tools/context_loader.py` reads small Markdown files from
`context/` and injects only the ones selected for the active profile and current
prompt.

| Context path | Used by |
|---|---|
| `context/docs/project-overview.md` | All profiles |
| `context/docs/devices.md` | All profiles |
| `context/docs/ops-runbook.md` | `ops`, ops-like prompts |
| `context/docs/home-assistant.md` | `home`, Home Assistant/MQTT prompts |
| `context/skills/humanizer.md` | `writing`, prose/humanize prompts |
| `context/skills/caveman.md` | `brief` |
| `context/skills/systematic-debugging.md` | `debug`, `ops`, `code`, `builder`, bug/error/build prompts |
| `context/skills/frontend-design.md` | `frontend`, UI prompts |
| `context/skills/skill-creator.md` | `skill_creator`, skill/eval prompts |

Aliases:

| Alias | Resolves to |
|---|---|
| `caveman` | `brief` |
| `humanizer` | `writing` |
| `systematic-debugging` | `debug` |
| `skill-creator` | `skill_creator` |

Run deterministic routing checks:

```bash
python3 scripts/check_profile_context.py
```

## Current Limitations

- Profiles run one at a time.
- There is no autonomous multi-agent scheduler yet.
- There is no parallel subagent fan-out yet.
- Long-running monitor loops should still live in Home Assistant, systemd, or a purpose-built service.

## Next Useful Step

The next upgrade would be a small router that chooses a profile automatically:

| User asks about | Route to |
|---|---|
| Disk, logs, uptime, services, SSH hosts | `ops` |
| Home Assistant YAML, MQTT, Meshtastic | `home` |
| Repo files, bugs, tests, patches | `code` |
| Implementing fixes/features with verification | `builder` |
| Current docs, comparisons, web facts | `research` |

Keep the first version deterministic and visible: show the selected profile in
the verbose pane before running the agent.
