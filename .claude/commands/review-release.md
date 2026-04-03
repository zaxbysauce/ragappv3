Review release notes, changelog bullets, README/docs edits, examples, and current code together.

Execution steps:
1. Load reviewing-code-core and reviewing-doc-drift.
2. Extract all atomic claims from release/docs/examples text.
3. For each claim, find structural proof in changed code, tests, config, exports, routes, handlers, or migrations.
4. Mark each claim as SUPPORTED, PARTIALLY_SUPPORTED, UNSUPPORTED, CONTRADICTED, or STEALTH_CHANGE.
5. Emit findings only for unsupported, contradicted, or material stealth changes.
6. Highlight missing migration notes for breaking changes.

Output format:
VERDICT: APPROVED | REJECTED
RISK: CRITICAL | HIGH | MEDIUM | LOW
ISSUES:
FIXES:
