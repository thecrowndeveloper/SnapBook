# OneCre8 Media — Product Development Blueprint

## Vision
OneCre8 Media is a Nigerian creative-services marketplace where clients discover, compare, communicate with, book and pay creative professionals and access creative products, equipment rentals and spaces.

## Marketplace categories
1. Photography
2. Videography
3. Artwork
4. Photo Framing
5. Interior Design
6. Costume Rentals
7. Media Equipment (sale and rental)
8. Spaces & Studios (events, photography and content creation)

## Roles
- Client: search, shortlist, message, request quotes, book, pay, track fulfilment, request refunds and review completed work.
- Creative Professional (public replacement for Provider): create a profile, select categories, publish services/products/rentals, manage availability, enquiries, bookings, portfolio, earnings and reviews.
- Administrator: verification, moderation, reports, disputes, refunds, payment reconciliation, audit logs and analytics.

## Core journeys
1. Discover by category, service, product, professional and Nigerian location.
2. Compare public profiles, portfolios, prices, availability and transaction-verified ratings.
3. Keep enquiries, quotes and conversations inside OneCre8.
4. Confirm booking/order terms and pay through a supported payment provider.
5. Track fulfilment, completion, disputes and eligible payouts.
6. Invite a client to review only after an eligible completed transaction.

## Reviews
Star ratings are client-to-Creative-Professional feedback, not reciprocal ratings. A review must reference a completed, paid booking/order, be authored by the associated client, and be unique per transaction. Ratings are 1–5 stars with optional text. Professionals may respond; reported reviews enter moderation. Do not launch review submission until the marketplace booking lifecycle has a reliable Completed state and authenticated client ownership.

## Payments and revenue
Initial revenue model: commission on completed marketplace transactions. Evaluate Paystack and Flutterwave marketplace/split-settlement features, fees, refunds, disputes, payout support and regulatory requirements before selection. Verify payments server-side and through signed webhooks; use idempotency keys and immutable transaction records. Never store raw card data. Do not claim escrow unless a regulated provider and legal arrangement genuinely support it.

## Security and trust
Role-based authorization, object ownership checks, CSRF, secure cookies, HTTPS, password hashing, rate limits, upload validation, signed webhooks, idempotent payment handling, audit logs, privacy minimization, backups, recovery tests, reporting/blocking and documented incident response.

## Locations
Support all 36 Nigerian states, FCT/Abuja, all state capitals as initial city options, and extensible towns/cities. Use dependent searchable State and City selectors; do not limit professionals to capitals.

## Content and governance documents
Terms of Service; Privacy Policy; Content Policy; Booking/Cancellation/Refund Policy; Creative Professional Agreement; Payment/Commission Policy; Dispute/Complaint Policy. Cover copyright, model/subject consent, prohibited content, fraud, impersonation, fake reviews, harassment, privacy, moderation, appeals and enforcement. Obtain Nigerian legal review before public launch.

## Product phases
1. Brand and discovery: OneCre8 identity, Creative Professional wording, category search, locations, homepage sections, storefronts, camera hero artwork.
2. Marketplace operations: category-specific dashboards, equipment sales/rentals, spaces, calendars, messaging, quotations, booking/order lifecycle.
3. Trust and revenue: completed-transaction reviews, payment gateway, commissions, payouts, refunds, disputes, verification and moderation.
4. Launch readiness: security, reconciliation, backup/recovery, legal review, accessibility, performance and monitoring.

## Data architecture
Preserve existing user IDs, provider IDs, bookings and uploaded media. Keep legacy table names temporarily; use public terminology in the UI. Introduce marketplace booking/order entities and transaction-linked reviews additively with migrations, foreign keys, indexes and backups. Avoid destructive renames.

## Definition of done
Every feature must have a complete user journey, server-side validation, authorization, persistence, error handling, responsive UI, repeatable tests and deployment verification. A page rendering alone is not completion.
