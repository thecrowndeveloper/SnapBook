# Level 3 — Deep playbook

For auth/authorization, privacy, payment, uploads, database changes, migrations, concurrency, infrastructure, deployment, or high-impact architecture.

## Research
- Trace the system end-to-end and identify trust boundaries.
- Inspect persistence, secrets/config, dependencies, external services, failure behavior, observability, and existing rollback/recovery.
- Review access control at each operation (not only UI), input validation, abuse controls, rate limits, and data lifecycle.
- Identify failure modes: partial writes, retries, race conditions, stale sessions, storage exhaustion, unavailable dependencies, rollback incompatibility.
- Record evidence and unresolved unknowns. If a material unknown remains, pause or constrain implementation.

## Plan
- Define scope, exclusions, API/data changes, compatibility and migration sequencing.
- Provide test matrix including negative/adversarial cases and operational failure cases.
- Risk register with severity, likelihood, mitigations, and residual risk.
- Define backup/restore or rollback steps, and how rollback will be verified.
- Identify destructive/irreversible/live actions requiring explicit approval.
- Include monitoring signals, release steps, and post-deploy verification.

## Implement
- Make changes in a dedicated branch and preserve reviewable commits.
- Tests must cover permissions, validation, failure handling, and regression paths.
- Run relevant automated checks; note environmental limits.
- Review changed files, dependency additions, secrets, migration reversibility, and log privacy.
- Do not perform irreversible or production-impacting actions without explicit approval.
- After deployment, verify runtime behavior, logs/metrics, and recovery plan; report evidence and residual risk.
