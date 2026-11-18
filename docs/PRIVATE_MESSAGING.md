# OneCre8 private messaging foundation

## Current scope

- A private conversation is created for each marketplace booking, including existing bookings during the database initialization migration.
- Only the booking client and the account attached to its creative professional can view or send messages.
- Messages are plain text, escaped by Jinja templates, limited to 2,000 characters and the latest 100 messages are loaded per thread.
- Participants may attach one JPG, PNG or WEBP image per message (maximum 5 MB and 20 megapixels). The server decodes and re-encodes it as WebP, strips source metadata through re-encoding, and stores it outside the public static/portfolio directories.
- Attachments are downloaded only through an authenticated route that checks booking participation; responses use attachment disposition and no-cache behavior.
- Contact and off-platform payment screening runs on the server before a message is inserted. Blocked attempts are not delivered; a policy event category is recorded for future moderation.
- A notification is created for the other booking participant after a successful send.
- Participants can report another participant's message for contact exchange, harassment, suspicious payment requests, inappropriate content or another concern. A reporter can submit one report per message.
- A moderator queue is restricted to account IDs explicitly configured in `ONECRE8_MODERATOR_USER_IDS` or exact, verified account email addresses explicitly configured in `ONECRE8_MODERATOR_EMAILS` (comma-separated). Email matching trims whitespace and ignores case; email-based access requires a non-empty `email_verified_at` timestamp; no account is granted moderation access by default.
- Moderators can mark a report under review, dismiss it with a note, or apply a temporary 24-hour, 72-hour or 7-day messaging restriction. Restricted users can still read conversations and may request a review through the published support process.
- Reports retain the reported message reference, reporter/reported account IDs, reason, optional details and review outcome for moderation.
- Message text is not interpreted as HTML and external links are not rendered as clickable links.

## Block-before-sending policy

The initial detector blocks obvious email addresses, phone-like number groups, social handles, external URLs, external messaging references and common off-platform payment instructions. Legitimate project details such as dates, prices, quantities and measurements should remain usable.

This is a first-pass automated detector, not a guarantee that all contact exchange can be identified. Deliberate obfuscation, screenshots, images, PDFs and video are not inspected by this text-only foundation. Detection rules require ongoing testing against false positives and evasion attempts. Do not represent this as foolproof.

## Security and privacy controls

- Authorization is checked server-side on every conversation request.
- CSRF protection remains active on message submissions.
- SQLite statements use bound parameters.
- Message content is rendered as escaped text.
- No email address, phone number or other direct contact details are added to the conversation UI.
- Policy events record user, booking, category and timestamp, not a duplicate copy of the rejected message.
- Message reports are unique per reporter/message and can only be submitted by a booking participant about the other participant's message. Moderator routes return 404 for non-configured accounts.
- Temporary messaging restrictions have explicit expiry timestamps and are enforced server-side before message submission; reading existing conversations remains available.

## Not yet included

Documents and video attachments, malware scanning, OCR/content extraction, read receipts, a full appeal workflow, retention and deletion workflows, and a complete end-to-end browser/screen-reader audit are not included in this foundation.

## Accessibility and quality

The inbox and conversation views use semantic headings, labels, a labelled conversation region, keyboard-operable forms, a visible policy explanation, responsive message layout and an aria-live message history. The image picker has a programmatic label, accepted formats and size limits are explained in text, and attachment downloads use descriptive link text. Automated tests cover core authorization, filtering, notification and legitimate-message cases. A manual keyboard, screen-reader, zoom/reflow and mobile browser audit remains necessary before claiming WCAG 2.2 AA conformance.
