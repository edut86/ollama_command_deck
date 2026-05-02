# Profile Context Eval

Use these prompts manually after context/profile changes.

| Profile | Prompt | Expected behavior |
|---|---|---|
| `ops` | `check disk and docker health on server-01` | Gathers evidence first, summarizes in compact tables, no sudo |
| `home` | `make a Home Assistant command_line sensor for Lilith health` | Produces YAML and mentions SSH key/path requirements |
| `writing` | `humanize this status note: The deployment serves as a testament to...` | Rewrites prose, does not alter technical facts |
| `brief` | `explain how to deploy this in one minute` | Very terse, commands preserved |
| `debug` | `docker-compose up fails with KeyError ContainerConfig` | Root-cause path before fix, mentions Compose v1 recreate issue |
| `builder` | `implement this fix and run tests` | Inspects files, patches narrowly, verifies, revises at most twice |
| `frontend` | `add a compact verbose pane beside chat` | Talks layout, responsive behavior, existing UI patterns |
| `skill_creator` | `make a local skill for MQTT troubleshooting` | Defines triggers, body, non-use cases, and eval prompts |

Deterministic smoke test:

```bash
python3 scripts/check_profile_context.py
```
