# Level 2 — Standard playbook

For multi-file features, normal bug fixes, or user-facing workflows.

## Research
- Trace UI/API entry point through handlers, data model, and downstream calls.
- Inspect nearby conventions, tests, configuration, and dependency use.
- Identify backward compatibility, permissions, and error paths.
- Record observed facts, assumptions, unknowns, and supporting evidence.

## Plan
- Goals, non-goals, impacted files/components, and data flow.
- Acceptance criteria with observable behavior.
- Risks with mitigation and regression targets.
- Test matrix: happy path, invalid input, permission/error path, regression.
- Rollback/revert plan and any human approval needed.

## Implement
- Small commits/diff; avoid opportunistic refactors.
- Add/update automated tests for criteria.
- Run targeted tests, relevant full checks, and static checks available.
- Review diff and test coverage against plan.
- Record deployment as not requested, pending, succeeded, or failed—never infer.
