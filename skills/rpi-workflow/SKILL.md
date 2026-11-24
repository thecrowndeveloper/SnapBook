---
name: rpi-workflow
description: Portable Research-Plan-Implement workflow for changes to existing applications and greenfield systems. Use for feature work, bug fixes, migrations, security-sensitive changes, architecture decisions, and production releases.
---

# Research → Plan → Implement

Use this workflow to reduce premature edits and make work reviewable. It is a workflow aid, not a certified security auditor, autonomous production operator, or guarantee of defect-free code.

## Non-negotiable sequence
1. **Research:** inspect the actual repository, runtime, relevant tests, user constraints, and evidence. Separate observed facts, assumptions, and unknowns. Do not edit implementation files during research.
2. **Plan:** define scope, exclusions, acceptance criteria, affected surfaces, risks, mitigations, test strategy, rollback, and approval needs. Keep the plan proportional to risk.
3. **Implement:** follow the approved plan, make the smallest coherent change, add/update tests, run checks, review the diff, and report exact evidence and remaining gaps.

Do not skip a phase. For trivial changes, use the short playbook but still record the three phases briefly.

## Depth selection
- **Level 1 / Quick:** low-risk copy, docs, or isolated bug. Read relevant files and one neighboring convention; record concise findings; one acceptance criterion; targeted test.
- **Level 2 / Standard:** ordinary feature or multi-file change. Inspect call sites, data flow, tests, dependencies, and UX; produce a plan with scope and risk; test targeted behavior plus regression checks.
- **Level 3 / Deep:** auth, privacy, payments, uploads, database schema, migrations, deployment, concurrency, infrastructure, or high-impact architecture. Trace entry points and trust boundaries, data lifecycle, failure modes, dependencies and operational constraints; plan rollback and recovery; include adversarial cases; require human approval before irreversible or live-impacting actions.

If uncertain, select the deeper level.

## Phase gates
- Research gate: repository evidence is recorded; critical unknowns are either resolved or explicitly carried forward.
- Plan gate: acceptance criteria are testable, scope and rollback are explicit, and approval is recorded where required.
- Implement gate: test commands and results are recorded; diff reviewed; deployment state distinguished from code merge; unresolved items are stated.
- For live production changes, do not deploy, migrate, delete, rotate, charge, or alter external data without the applicable authorization. Verify production outcomes after action; never infer success from acceptance of a request.

## Records
Use JSON records under `records/` based on `templates/change-record.json`. Run:
`python tools/rpi/evidence_gate.py --record <record.json>`
The gate checks required fields and evidence presence, not the truth or quality of evidence. Keep secrets, personal data, tokens, and sensitive logs out of records.

## References
- Quick playbook: `playbooks/quick.md`
- Standard playbook: `playbooks/standard.md`
- Deep playbook: `playbooks/deep.md`
- Record templates: `templates/`
- Evidence validator: `tools/rpi/evidence_gate.py`
- Adversarial evaluation scenarios: `evals/adversarial-scenarios.md`
