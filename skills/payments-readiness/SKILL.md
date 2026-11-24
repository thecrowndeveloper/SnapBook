---
name: payments-readiness
description: Prepare secure, compliant marketplace payment architecture, transaction lifecycle, webhook handling, reconciliation, refunds, and payouts. Use for payment planning and implementation; live payment activation requires explicit approval.
---
# Payments Readiness

Payments are not currently enabled for OneCre8. Sandbox code is not production readiness.

## Research
- Confirm business model, processor capabilities, local regulatory obligations, fees, currency, transaction states, refunds, chargebacks, payouts, custody/holding model, reconciliation, and fraud risks.
- Review processor docs and legal/regulatory requirements as current sources; escalate legal interpretation.

## Plan
- Specify transaction state machine, idempotency, webhook verification, ledger/audit trail, reconciliation, authorization, failure and retry paths, refunds/disputes, payout model, monitoring, and rollback.
- Use test/sandbox environments and synthetic data.

## Implement
- Never store raw card data unless specifically approved and supported by compliant architecture; prefer processor-hosted/tokenized flows.
- Verify webhook signatures, deduplicate events, enforce idempotency, and reconcile processor records against internal ledger.
- Keep secrets out of source, logs, and prompts.
- Test duplicate, out-of-order, forged, failed, partial, refunded, disputed, and timeout events.

## Gate
Live keys, charges, payouts, financial transfers, or activation must never be enabled without explicit authorization and legal, security, operational, and reconciliation readiness review.
