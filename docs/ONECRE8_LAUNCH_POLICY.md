# OneCre8 Media — launch policy implementation notes

**Status:** implementation draft on `feature/onecre8-launch-legal-auth`  
**Legal status:** draft only; not approved for use as final contractual terms.  
**Payment status:** live payments, collection, custody and payouts remain disabled.

## Confirmed launch decisions

- Commission: 10% of the eligible completed transaction amount.
- Subscription: free to join; no mandatory monthly subscription at launch.
- Delivery review: 72 hours after a valid delivery notification. The final rule must define what constitutes valid delivery, extensions, non-response and statutory-rights exceptions.
- Refunds and disputes: case-by-case, evidence-based review, with a response and appeal opportunity for both parties.
- Payment-processing fees: shown separately at checkout, not silently buried in the commission.
- Registration: Google OpenID Connect and email/password.
- Payments: disabled until a suitable authorised payment provider and Nigerian legal counsel approve the fund flow.

## Account and consent implementation

The registration form requires:
1. General Terms and Conditions.
2. Privacy Policy acknowledgement.
3. Marketplace Content and Review Policy.
4. Client Booking and Service Policy for clients, or Creative Professional Agreement for creative professionals.

The `legal_acceptances` table records user ID, document key, document version, timestamp and acceptance method. Versions are currently marked `0.1-draft`; they must be replaced with counsel-approved versions before the documents are used as final agreements.

The `users` table is extended with:
- `auth_provider`
- `google_subject`
- `email_verified_at`

Google sign-in requests only `openid email profile`. It does not request Gmail mailbox access. The callback requires Google's verified-email claim. A Google identity can be linked to an existing account only where the verified Google email matches that account's email.

Email/password registration continues to use the existing password-hash implementation. **Email verification delivery is not yet implemented** because the application does not yet have an approved outbound email service and sender configuration. Do not treat email/password accounts as email-verified until that feature is completed.

## Required Google Cloud configuration

Create a Google OAuth 2.0 Web application client. Configure the authorised redirect URI to:

```
https://YOUR-PRODUCTION-DOMAIN/auth/google/callback
```

For local development, add the corresponding local callback URI separately, for example:

```
http://127.0.0.1:5000/auth/google/callback
```

Set these Railway service variables only after the Google OAuth client is created:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`

Keep the client secret private. Never commit it to GitHub. The Google button remains hidden until both values are configured.

## Payment and transaction requirements for a later release

No payment provider is integrated by this change. Before enabling checkout, implement and review:
- Server-side payment verification and signed webhooks.
- Idempotent transaction creation and payment reconciliation.
- A transaction ledger with gross amount, commission rate, commission amount, separately disclosed processing fee, professional net amount and currency.
- A 72-hour review state beginning only after a valid delivery event.
- Dispute holds only where supported by the payment provider and legally permitted.
- Refund, partial refund, reversal and payout audit trails.
- No representation that OneCre8 provides regulated escrow unless counsel and the provider approve that exact structure.

## Legal review required before public acceptance

Counsel should confirm:
- OneCre8's legal role in each service, sale and rental transaction.
- Commission calculation base and treatment of taxes, deposits, delivery charges, damage charges and processing fees.
- The enforceability and operation of the 72-hour review period.
- Consumer cancellation, refund, quality and complaint rights.
- Payment collection, settlement, delayed payout and dispute-hold arrangements.
- Data controller/processor roles, lawful bases, privacy contact, retention, transfers and breach response under Nigerian data-protection law.
- Professional status, intellectual property, portfolio permissions, liability, insurance and anti-circumvention provisions.
- Final company identity, registered address, effective dates, contact details and complaint escalation route.

## Safe release sequence

1. Review the feature branch and test registration, legal pages and acceptance logging locally.
2. Configure Google OAuth credentials in a non-production environment and test callback, account linking and role handling.
3. Complete outbound email verification before treating email addresses as verified.
4. Obtain written legal approval of final policy versions.
5. Keep live payments disabled until provider and counsel approval.
6. Merge only after review and regression tests. Do not modify or reset the production SQLite database or Railway volume as part of this work.


## Email verification and password recovery

Email/password registration now creates the account in a pending-verification state. The user is not allowed to log in until the email verification link is used. Verification links expire after 24 hours. Password reset links expire after one hour and are invalidated when the password is changed.

Configure the following Railway service variables before enabling email registration for real users:

- `SMTP_HOST` — SMTP server hostname.
- `SMTP_PORT` — currently configured for STARTTLS, normally `587`.
- `SMTP_USERNAME` — SMTP account username.
- `SMTP_PASSWORD` — SMTP credential or provider-issued API password; keep it secret.
- `MAIL_FROM` — verified sender address, for example `OneCre8 Media <accounts@your-domain>`.

The sender domain should be authenticated with the email provider (SPF and DKIM; configure DMARC as advised by the provider). Use a transactional email provider for production rather than a personal mailbox. Never put SMTP credentials in GitHub or source files.

If SMTP is not configured or delivery fails, account creation will not silently sign the user in. The user sees a message directing them to support; configure and test SMTP before public registration is opened.

## CI verification

A GitHub Actions workflow was added at `.github/workflows/onecre8-auth-checks.yml`. It compiles the Flask application and smoke-tests the registration pages, legal pages, legal acceptance records, verification gate, email verification, password login and one-time password-reset behavior. A successful workflow run must be checked before the pull request is approved.


Account verification and password-reset emails are limited to three messages per recipient and message type per hour. Password-reset requests use a generic response to reduce account-enumeration risk. Configure provider-level abuse protection and monitor delivery failures before launch.


## Resend transactional email configuration

The Flask application uses Python's standard-library SMTP client, so no Resend SDK or API key is added to the repository. Configure Resend as follows in the **non-production test environment first**:

| Environment variable | Value |
|---|---|
| `SMTP_HOST` | `smtp.resend.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USERNAME` | `resend` |
| `SMTP_PASSWORD` | Resend API key (secret; never commit or paste into chat) |
| `MAIL_FROM` | A sender address on a domain verified in Resend, e.g. `OneCre8 Media <accounts@your-verified-domain>` |

The current implementation opens an SMTP connection, upgrades it with STARTTLS, authenticates and sends a plain-text message. This matches Resend's documented STARTTLS configuration on port 587. Resend also documents SMTPS on port 465; the application currently uses STARTTLS, so use port 587 unless the transport implementation is deliberately changed.

### Resend setup checklist

1. Sign in to Resend and open **Domains**.
2. Add a domain OneCre8 owns or is authorised to send from. Prefer a dedicated sending subdomain if the primary domain already handles business email.
3. Add the DNS records Resend displays at the domain's DNS host. Do not guess or substitute DNS values. Complete the DKIM and SPF records, and configure DMARC in line with Resend's guidance and the domain's existing mail setup.
4. Wait until Resend marks the sending domain verified.
5. Create a restricted API key for the OneCre8 application. Give it only the permissions needed for sending email, if Resend offers that scope for the chosen key type.
6. In the **staging/test Railway environment**, add the five variables in the table above. Enter the API key directly in Railway's variable editor; do not send it to ChatGPT, paste it into a terminal command, or commit it to GitHub.
7. Set `MAIL_FROM` to an address on the verified domain. The address does not need to be a personal inbox, but the domain must be verified and the sender should be monitored.
8. Redeploy only the staging service after saving the variables.

### Safe test procedure

- Use an inbox controlled by the project owner or tester.
- Submit a test client registration and confirm the verification message arrives.
- Open the link and confirm the account can then log in.
- Test resend verification and forgot-password; confirm the reset message arrives and the link works once.
- Request a second reset after using the first link; confirm the old link is rejected.
- Check Resend's Emails dashboard for accepted, delivered, bounced or failed status.
- Check Railway logs for connection or authentication errors. Never print SMTP environment variables or message tokens in logs.
- Do not test with real customer addresses until the sender domain, content and privacy/legal notices are approved.

### Production gate

Do not add these credentials to the production Railway service until staging delivery succeeds and the registration release is approved. Adding variables to a live Railway service may trigger a redeployment. Keep production payment functions disabled. Rotate the Resend API key immediately if it is ever exposed, and update the secret only in the affected Railway environment.
