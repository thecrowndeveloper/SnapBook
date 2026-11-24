---
name: qa-accessibility
description: Test engineering, regression, browser verification, responsive design, UX quality, and WCAG accessibility. Use for UI changes, workflows, releases, and bug fixes.
---
# QA, UX, and Accessibility

Target WCAG 2.2 AA for applicable criteria. Do not claim conformance without an appropriate evaluation.

## Research
- Identify user journeys, affected states, devices/viewports, current tests, design conventions, and reported symptoms.
- Distinguish automated test evidence from actual browser/device observations.

## Plan
Define tests for normal, empty, loading, success, error, validation, permission, keyboard, mobile/reflow, and regression states as applicable.

## Implement and test
- Add unit/integration/end-to-end coverage for behavior at appropriate layers.
- Verify semantic HTML, labels, keyboard operation, focus visibility/order, contrast, zoom/reflow, touch targets, and error clarity.
- Check narrow/mobile, tablet, and desktop layouts; use real browser screenshots or automation when available.
- Do not use color alone to communicate status. Honor reduced-motion preferences where relevant.
- Run automated accessibility checks, but treat them as partial coverage.

## Gate
Map acceptance criteria to test results. Explicitly label checks not run and visual/device testing not performed. A passing compile or unit test does not prove usability or accessibility.
## OneCre8 Design Preservation
- Follow `docs/DESIGN-PRESERVATION.md`. The existing UI is the protected visual baseline; do not redesign or broadly restyle without explicit user approval.
- Inspect the affected page/styles first. Fix reported UI defects with the smallest targeted change and retain established visual tokens, layout, spacing, cards, typography, navigation, and imagery.
- Visual regression is part of acceptance; perform browser before/after comparison when available and report when it was not performed.
