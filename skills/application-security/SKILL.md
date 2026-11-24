---
name: application-security
description: Secure web application engineering using threat modeling and OWASP verification guidance. Use for auth, permissions, sessions, forms, uploads, APIs, messaging, dependencies, or security review.
---
# Application Security

Use OWASP ASVS as a verification checklist reference and OWASP Top 10 for risk awareness. Do not claim certification or compliance without a documented assessment.

## Research
- Identify assets, entry points, trust boundaries, attacker goals, authorization rules, and sensitive data.
- Trace security controls to server-side handlers and data access—not only templates or JavaScript.
- Inspect secrets/configuration, dependencies, file processing, logs, and relevant prior controls.

## Plan
Include abuse cases and negative tests. For high-risk work, use Deep RPI and document rollback, residual risk, and approval requirements.

## Implementation and verification
- Authenticate and authorize every sensitive operation server-side; enforce ownership and role checks.
- Validate input, encode output by context, use parameterized queries, CSRF protections, secure session settings, and safe error handling.
- Protect uploads: allowlist types, size limits, safe names, content validation where practical, storage separation, and access controls.
- Consider rate limits, brute-force/abuse protection, security headers, dependency risks, and secret handling.
- Avoid leaking credentials, private data, tokens, or internal details through logs, responses, errors, or test fixtures.
- Add tests for unauthenticated, unauthorized, cross-user, malformed, boundary, and failure scenarios as applicable.

## Gate
Security findings must be categorized, evidenced, and tracked. Do not deploy high-risk changes with unresolved critical blockers. This skill is not a security certification or substitute for specialist review.
