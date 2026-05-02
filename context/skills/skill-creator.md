# Skill Creator Skill Profile

Use when creating or improving skill docs, trigger rules, local context files,
or eval prompts.

Skill shape:

- Keep metadata and triggers explicit.
- Keep body instructions focused and under control.
- Put large examples or references in separate files.
- Prefer deterministic scripts for repetitive mechanical work.
- Add a few realistic eval prompts before expanding scope.
- Make skills profile-scoped unless they truly apply to every response.

Good skill docs say:

- when to use the skill
- when not to use it
- what output format is expected
- what constraints should never be violated
