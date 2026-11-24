# OneCre8 Engineering Skill Stack

Skills are portable instruction packs under `skills/<name>/SKILL.md`. Each includes scope, research, planning, implementation, and verification gates. Apply relevant skills alongside the RPI workflow.

## Disciplines
| Skill | Standards/reference baseline | When |
|---|---|---|
| RPI workflow | Research–Plan–Implement evidence gates | Substantial changes |
| Architecture & code quality | Python conventions/PEP 8, modularity, maintainability | All code changes |
| Application security | OWASP ASVS, OWASP Top 10 awareness | Auth, data, routes, uploads, APIs |
| Privacy & data sharing | Nigeria NDPA 2023; applicable NDPC guidance | Personal data and data flows |
| QA, UX & accessibility | WCAG 2.2 AA target; automated + manual testing | UI and release changes |
| Production engineering | Reliability, recovery, safe releases, monitoring | Infrastructure and production |
| AI agent engineering | Least privilege, prompt-injection resilience, evidence-grounded reporting | AI-assisted work |
| Marketplace trust & safety | Abuse-case testing, fairness, moderation, appeals | User interactions and marketplace |
| Payments readiness | Processor docs, transaction integrity, legal/security readiness | Payment design and later implementation |

## Required workflow
1. Choose applicable skills and RPI depth.
2. Research the real code/data flow, standards and user constraints.
3. Plan scope, acceptance criteria, risks, tests, rollback and approval.
4. Implement in a branch with focused diffs.
5. Run tests and review changes; document checks not run.
6. Merge only after checks pass.
7. Verify deployment and actual behavior separately.

## Evidence policy
No compliance claims without scope, assessment method, findings, and evidence. Automated checks are not certifications. Do not store secrets, personal data, or sensitive logs in RPI records.

## Current launch-readiness work (not certification)
- Security verification against a scoped ASVS checklist.
- Data inventory, sharing map, retention/deletion review, processor review.
- User journey regression tests and responsive/accessibility checks.
- Backup restore drill, release/rollback rehearsal, monitoring and capacity baseline.
- Payment readiness assessment before any live activation.
