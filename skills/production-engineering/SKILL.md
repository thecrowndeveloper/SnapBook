---
name: production-engineering
description: Reliability, safe deployment, observability, backup and restore, performance, capacity, and incident response. Use for infrastructure, release, database, storage, concurrency, and production-impacting changes.
---
# Production Engineering & Reliability

## Research
- Inspect deployment architecture, runtime, storage, database, replicas, dependencies, logs/metrics, current backup, and recovery path.
- Identify failure modes: service outage, database loss, storage exhaustion, partial writes, timeouts, duplicate requests, races, dependency failures, and bad releases.

## Plan
- Define health signals, capacity assumptions, timeout/retry behavior, safe rollout, rollback, backup/restore evidence, and required approvals.
- Consider idempotency, concurrency, graceful degradation, and migration compatibility.

## Implement
- Keep environments and secrets separated; never commit secrets.
- Add meaningful health checks, structured safe logs, error monitoring, and metrics where justified.
- Backups must be independent of the primary volume and restore-tested.
- Avoid unnecessary infrastructure cost; scale based on evidence.
- Deploy gradually when possible and verify the actual release/runtime, not just merge status.

## Gate
Record release state, verification evidence, backup/restore status, residual risks, and rollback. Do not perform destructive, paid, irreversible, or live-impacting actions without required authorization. This skill is not a guarantee of uptime.
