---
name: council-advisory-triage
description: How to distinguish blocking vs advisory findings from council review, especially final council. Prevents unnecessary rework from misclassified advisory concerns.
generated_from_knowledge:
  - 44e08dfa-4e15-4667-b450-8e2e236c0405
  - 728f248f-49b9-43ce-aed2-b5e971878b7e
confidence: 0.65
status: active
---

# Council Advisory Triage

## Trigger

Use this skill when:
- Receiving council review findings (especially final council)
- Determining if a council finding is blocking or advisory
- Deciding whether to rework code based on council feedback
- Writing phase council verdicts after reviewing findings

## Required Procedure

### 1. Classify each finding as BLOCKING or ADVISORY

**BLOCKING findings (must fix):**
- Security vulnerabilities (SQL injection, auth bypass, secret leakage)
- Logic errors that cause incorrect behavior
- Missing error handling for critical paths
- API contract violations that break consumers
- Race conditions in concurrent code
- Memory leaks or resource exhaustion

**ADVISORY findings (consider but not required):**
- Code style suggestions beyond project conventions
- "Could be more efficient" without performance impact
- Edge cases with extremely low probability
- Future-proofing suggestions without current need
- Personal preference disguised as best practice
- Minor naming or documentation improvements

### 2. Verify with evidence

For each BLOCKING finding, ask:
- [ ] Can I demonstrate the bug with a test case?
- [ ] Does this affect a critical user journey?
- [ ] Would this fail in production?
- [ ] Is there a security or data integrity risk?

A finding is BLOCKING only if at least one of these is YES. If none are YES, the finding is likely ADVISORY.

**Exception:** A council member may have identified a genuine blocking issue but phrased it as a suggestion. If a finding describes a real correctness or security defect — even if phrased softly — classify it as BLOCKING.

### 3. Handle overly conservative councils

Final council in particular tends to be conservative. When the council returns CONCERNS or REJECT:

1. Count required fixes vs advisory suggestions
2. If required fixes = 0, the verdict should be APPROVE with advisory notes
3. Document the rationale for treating advisory findings as non-blocking
4. Write the verdict honestly — don't upgrade advisory to blocking

**Note:** The same triage applies whether the council returns CONCERNS or REJECT — both can contain advisory-only feedback.

### 4. Escalation path

If a council member insists on an advisory finding being blocking:
- Request a specific test case that demonstrates the issue
- Ask for the severity rating with justification
- If no concrete evidence: mark as advisory and proceed

## Forbidden Shortcuts

- NEVER treat all council findings as blocking by default
- NEVER ignore blocking findings just because they're hard to fix
- NEVER let one council member's opinion override concrete evidence
- NEVER skip the classification step — always categorize each finding

## Delegation Template

When delegating a task affected by this skill, include:

```
SKILLS: file:.opencode/skills/generated/council-advisory-triage/SKILL.md
```

## Reviewer Checks

- [ ] Each council finding classified as BLOCKING or ADVISORY
- [ ] BLOCKING findings have test cases or concrete evidence
- [ ] Advisory findings documented but not blocking phase completion
- [ ] Verdict reflects required fixes only — suggestion count is irrelevant to the blocking decision

## Source Knowledge IDs

- 44e08dfa-4e15-4667-b450-8e2e236c0405 — Final council may flag advisory concerns as blocking
- 728f248f-49b9-43ce-aed2-b5e971878b7e — Council review catches cross-cutting anti-patterns
