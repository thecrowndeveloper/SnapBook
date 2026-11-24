# Level 1 — Quick playbook

For low-risk, isolated work (copy, docs, small UI fix).

## Research
- Inspect the target and one relevant usage/caller.
- Note evidence (path/line, test output, or reproducible observation).
- State any assumptions and check that no wider impact is obvious.

## Plan
- One-sentence scope and explicit out-of-scope.
- At least one observable acceptance criterion.
- One targeted test or verification method.
- Rollback: revert the small change.

## Implement
- Make one coherent change.
- Run targeted check.
- Review diff for unrelated changes.
- Record exact command/result and any not-run checks.
