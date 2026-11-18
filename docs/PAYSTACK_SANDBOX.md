# Paystack sandbox integration

This integration is a test-mode foundation only. Live collection, live settlements,
split payments, refunds, and professional payouts are not enabled.

## Required Railway variables (test values only)

Configure these only after obtaining test credentials from the Paystack dashboard:

- `PAYSTACK_SECRET_KEY`: test secret key beginning `sk_test_`
- `PAYSTACK_WEBHOOK_SECRET`: webhook signing secret beginning `whsec_` (recommended for the current timestamped signature)

Never add either secret to GitHub, source files, browser JavaScript, screenshots, or chat messages. Do not configure an `sk_live_` key. The application rejects any key that does not begin with `sk_test_`.

## Paystack dashboard

1. Use the Paystack test environment.
2. Configure the webhook URL as `https://YOUR-RAILWAY-DOMAIN/payments/paystack/webhook`.
3. Generate/enable a webhook signing secret and copy it directly into Railway as `PAYSTACK_WEBHOOK_SECRET`.
4. Use the test secret key as `PAYSTACK_SECRET_KEY`.
5. Keep all live credentials out of this deployment.

The webhook validates Paystack's timestamped `Paystack-Signature` against the raw request body and allows a five-minute clock window. A legacy `x-paystack-signature` HMAC is supported during the documented transition only.

## Current checkout scope

- Client must be logged in and own the booking.
- Booking must be accepted by the creative professional.
- Only fixed-price, bookable services are eligible; quote/enquiry services are excluded.
- The agreed fixed price is snapshotted when the client creates the booking; checkout uses that immutable booking price, not a later listing edit.
- Older bookings created before price snapshots have no confirmed price and are deliberately excluded from checkout; create a fresh request to establish an agreed price.
- Paystack's documented NGN minimum is enforced.
- The reference is generated server-side and unique.
- Callback and webhook both call Paystack's verify endpoint.
- A payment is marked successful only when the verified reference, exact amount, NGN currency, and test domain match.
- Webhook retries are idempotent; only one successful payment is allowed per booking.
- The payment record is a transaction ledger entry, not an escrow, split settlement, or payout mechanism.

## Local checks

Run:

```powershell
python -m py_compile app.py paystack_payments.py
python -m unittest discover -s tests -p "test_paystack_payments.py" -v
```

The automated tests mock Paystack HTTP calls. They do not move money and do not replace a manual end-to-end test using Paystack test cards/accounts.

## Not yet enabled / required before launch

- Live keys and live charges remain disabled.
- Payment status is not yet wired to automatic booking completion or provider payouts.
- No split settlement, commission deduction, escrow, refunds, chargeback workflow, or reconciliation is implemented.
- Do not promise a payment-protected booking or release a professional's work/payout based only on a browser redirect.
- Before live launch, review the Nigerian legal and regulatory model, merchant/subaccount onboarding, fee disclosures, refund/dispute process, data protection notices, and accounting/reconciliation.
- SQLite remains single-replica storage; do not scale replicas until PostgreSQL migration.
