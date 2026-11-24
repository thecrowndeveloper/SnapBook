---
name: architecture-code-quality
description: Research and implement maintainable application architecture, Python code quality, database integrity, and API design. Use for refactors, feature changes, module boundaries, and code review.
---
# Architecture & Code Quality

## Research
- Read relevant files, entry points, callers, tests, schema, and configuration before editing.
- Trace the full data flow; record observed facts, assumptions, and unknowns.
- Identify the smallest architectural boundary affected. Avoid inventing abstractions.

## Plan
- Define scope, non-goals, observable acceptance criteria, affected files, risks, regression tests, and rollback.
- Favor readable, cohesive modules and clear separation of concerns. Apply SOLID where it helps; avoid needless patterns.
- Consider schema integrity, backwards compatibility, migration safety, and failure paths.

## Implement
- Make the smallest coherent diff. Avoid unrelated refactors and new dependencies unless justified.
- Use clear names, focused functions, consistent Python conventions (PEP 8), appropriate typing, and explicit error handling.
- Validate inputs at boundaries; parameterize database queries; enforce invariants in the database where appropriate.
- Review changed code for duplication, complexity, hidden side effects, debug leftovers, secrets, and compatibility.
- Run relevant tests and static checks; record exact commands/results.

## Gate
Do not claim quality based on style alone. Test behavior and review the diff. Record unresolved debt rather than silently expanding scope.
## OneCre8 Design Preservation
- Follow `docs/DESIGN-PRESERVATION.md`. The existing UI is the protected visual baseline; do not redesign or broadly restyle without explicit user approval.
- Inspect the affected page/styles first. Fix reported UI defects with the smallest targeted change and retain established visual tokens, layout, spacing, cards, typography, navigation, and imagery.
- Visual regression is part of acceptance; perform browser before/after comparison when available and report when it was not performed.
