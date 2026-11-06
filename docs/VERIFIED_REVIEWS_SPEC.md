# OneCre8 Media — Verified Review Implementation Specification

## Product rule
Clients review the Creative Professional's work. Initial release is one-way client-to-professional; professionals do not rate clients.

## Eligibility
A review is allowed only when the signed-in account is the client attached to the relevant marketplace booking/order; the transaction belongs to the Creative Professional being reviewed; payment is verified where required; the transaction has reached an explicit Completed state; and no review already exists for that transaction.

Confirmed is not Completed. Pending, Cancelled, refunded-before-fulfilment and disputed transactions are not reviewable until the applicable resolution rules permit it.

## Suggested data model
Table reviews: id; booking_id (NOT NULL, UNIQUE); client_user_id; creative_professional_id; rating (CHECK 1–5); review_text; professional_response; status (published, hidden, under_review); created_at; updated_at. Add foreign keys to the final canonical marketplace booking/order, users and professional profile. Add indexes on professional + status and client + created_at.

## Integration dependency
The current app has two separate booking concepts: legacy photographer bookings and marketplace service enquiries. Marketplace service records do not yet have a booking/order lifecycle or Completed status. Do not enable review submission against the legacy photographer table as if it were the new marketplace booking system. First implement a canonical marketplace booking/order record with client ownership, professional ownership, payment state and fulfilment status; then attach reviews to it.

## UI
Display average rating and review count on public Creative Professional profiles. Show dated review cards with stars and text. Allow one professional response. Provide report and moderation actions. Show the review form only on the client's completed transaction detail page.

## Required tests
Reject anonymous submission; reject non-client role; reject reviewing another client's transaction or another professional; reject pending, confirmed, cancelled or unpaid transactions; accept one eligible completed transaction; reject duplicate reviews through a UNIQUE constraint; reject ratings outside 1–5 in server and database validation; exclude hidden and under-review content from public averages.
