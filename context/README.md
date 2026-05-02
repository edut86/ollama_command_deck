# Context Docs

This directory holds small, profile-scoped context files for Lilith.

The loader in `ollama_tools/context_loader.py` injects only the files selected
for the active agent profile and the current prompt. Keep these files compact:
they are prompt guidance, not a knowledge base dump.

Current layout:

| Path | Purpose |
|---|---|
| `docs/` | Local setup, runbooks, and durable project context |
| `skills/` | Skill-style guidance that should be profile-scoped, not global |
| `evals/` | Small prompts for checking profile/context behavior |

Run the deterministic profile/context check from the repo root:

```bash
python3 scripts/check_profile_context.py
```
