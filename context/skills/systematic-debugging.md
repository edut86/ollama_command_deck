# Systematic Debugging Skill Profile

Use for bugs, build failures, production issues, broken deploys, integration
failures, performance problems, and repeated failed fixes.

Process:

1. Read the exact error and stack trace.
2. Reproduce or inspect the failure path.
3. Check recent changes and environment differences.
4. Compare broken behavior with a nearby working pattern.
5. State one root-cause hypothesis.
6. Test the smallest useful change.
7. Verify the result.

Do not propose fixes before evidence. If three attempts fail, stop and question
the architecture or assumptions before adding another patch.
