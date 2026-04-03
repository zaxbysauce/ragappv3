# Code Review Rules

When reviewing code, default to skepticism and verification.

Mandatory rules:
- Never approve changes without positive evidence of what was checked.
- Never speculate about unopened files, unresolved symbols, or unverified dependencies.
- Treat release notes, PR descriptions, changelog bullets, comments, docstrings, examples, and tests as claims or hints, not proof.
- For every user-facing or shipped claim, find structural proof in code, tests, config, exports, routes, handlers, migrations, schemas, or actual end-to-end wiring.
- For every new or changed dependency, verify package existence, correct ecosystem, pinned version validity, and import/install consistency.
- Reject changes if a claimed feature is unsupported, a dependency is unverified, a critical trust boundary lacks validation, or a route/command/export is unwired.
- Separate judgment from remediation: classify issues first, then propose fixes.
- If no issues are found, state exactly which files, claims, interfaces, dependencies, and trust boundaries were checked.

Review output must use:
- VERDICT: APPROVED | REJECTED
- RISK: CRITICAL | HIGH | MEDIUM | LOW
- ISSUES:
- FIXES:
