Review the current PR, diff, branch, or local changes using the reviewing-code-core skill.

Execution steps:
1. Load reviewing-code-core.
2. If manifests, imports, lockfiles, scripts, install instructions, or external tools changed, also load reviewing-dependencies.
3. If README, docs, changelog, release notes, examples, PR text, comments, or docstrings changed, also load reviewing-doc-drift.
4. If auth, input handling, subprocesses, filesystem access, networking, parsing, secrets, or privileged actions are involved, also load reviewing-security.
5. Reconstruct intent before judging implementation.
6. Extract obligations.
7. Summarize actual behavior independently.
8. Compare obligations vs implementation.
9. Emit only evidence-backed findings.
10. If approving, list explicit positive evidence.

Output format:
VERDICT: APPROVED | REJECTED
RISK: CRITICAL | HIGH | MEDIUM | LOW
ISSUES:
FIXES:
