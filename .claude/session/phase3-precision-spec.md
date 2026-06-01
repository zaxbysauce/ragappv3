# Phase 3 Spec — Retrieval Precision for Exact-Fact Queries (for sign-off)

Status: **SPEC ONLY — no code written.** Awaiting your approval before implementation.
Context: Thinking-mode quality. These address the turn-2 "silent parameters" failure where a
precise, exact-fact question was (a) not recognized as a follow-up so conversation context was
dropped, and (b) broadened by step-back into tangential retrieval. Instant mode is unaffected
(it already skips these via Phase 1).

The critic flagged 3.1 as the highest-risk change in the whole effort because a false positive
**replaces the user's query with an LLM rewrite**. So this spec leads with a concrete pattern set
and an explicit true/false-positive test matrix that must pass before merge.

---

## 3.1 — Widen follow-up detection (HIGH RISK)

### Problem (evidence)
`query_transformer.py:36-57` `is_followup_query` gates `rewrite_followup`
(`rag_engine.py:452-457`). "can you give me more detail on the silent parameters available?"
matches neither the explicit-phrase regex nor the short-pronoun gate, so the prior turn's
"install CDP server" context was never re-attached → retrieved as a decontextualized query.

### Why this is dangerous
A false positive (classifying a standalone question as a follow-up) makes `rewrite_followup`
discard the real question and search against an LLM rewrite derived from the *previous* turn —
silently wrong retrieval. So the bar is: **add patterns that only match clearly-referential
phrasings, and never match a self-contained question.**

### Proposed change (exact)
In `query_transformer.py`, keep the existing `_FOLLOWUP_REGEX` and the ≤80-char gate. Add a
SECOND, narrow regex that requires BOTH a referential lead-in AND the absence of a concrete
standalone subject. Concretely, extend the explicit-phrase alternation with anchored forms:

```
# additions to _FOLLOWUP_REGEX (all still ^...$ anchored, ≤80 chars enforced by caller)
r"(can you |could you |please )?(give|tell|show) me more (detail|info|information)( on| about)?|"
r"more (detail|info|information)( on| about)?|"
r"go deeper( on| into)?|"
r"what else( about)?|"
r"anything else( about)?"
```

KEY CONSTRAINT (the safety rule): the follow-up rewrite must only fire when the message is
**short AND referential**. The existing `len(query) > 80 → False` gate already bounds length.
Additionally, do NOT broaden the `^(what|how|why|when|where|which|who)\b` space — those are the
exact words that signal a self-contained question. "what are the silent parameters available?"
should be handled by **3.2 (precision), NOT 3.1 (rewrite)** — we do NOT want to rewrite it from
prior context; we want to retrieve it precisely. This division is deliberate.

### Required test matrix (must all pass before merge)
MUST classify as follow-up (True):
- "tell me more"
- "give me more detail on that"
- "more detail on the silent parameters"  ← but see note*
- "go deeper on this"
- "what else?"
- "and the enterprise tier?"  (existing short-pronoun gate)

MUST NOT classify as follow-up (False) — these are standalone, must retrieve literally:
- "what are the silent parameters available?"
- "how do I install the CDP server?"
- "list the command-line flags for the installer"
- "what is the default database port?"
- "can you give me a guide to install cdp server"  (a fresh request, not a follow-up)
- any message > 80 chars

*Note on ambiguity: "more detail on the silent parameters" is genuinely ambiguous — it's
referential ("more") but names a concrete subject ("silent parameters"). Decision needed from
you (see Open Questions). Recommended: treat as follow-up ONLY when it lacks a concrete noun
phrase, i.e. "more detail" / "more detail on that" = follow-up; "more detail on <specific
topic>" = standalone (let retrieval handle the specific topic). This is the safest split.

### Risk & mitigation
- Risk: rewrite hijacks a good query. Mitigation: the test matrix above is the gate; ship only
  if every "MUST NOT" case is False. Add them as parametrized unit tests in
  `test_query_transformer.py` (or a new `test_followup_detection.py`).
- Rollback: single regex revert; no schema/state change.

---

## 3.2 — Don't broaden exact-fact queries via step-back (MEDIUM RISK)

### Problem (evidence)
`query_transformer.py:60-84` `_is_exact_or_document_query` is the skip-gate for step-back/HyDE.
It catches quoted phrases, filenames, and ≤3-word non-questions, but MISSES procedural/exact
queries like "write me a guide to install cdp server" and "what are the silent parameters
available?". Step-back then broadens them, diluting the precise chunk in RRF fusion
(`rag_engine.py:1017` weights step-back at 0.5).

### Proposed change (exact)
Extend `_is_exact_or_document_query` (or add a sibling `_is_exact_fact_query`) to ALSO skip
broadening when the query contains strong specificity signals:

```
# skip step-back broadening when the query targets a concrete artifact/fact:
_EXACT_FACT_SIGNALS = re.compile(
    r"\b(parameter|parameters|flag|flags|argument|arguments|option|options|"
    r"command|commands|syntax|default|port|version|env(ironment)? variable|"
    r"setting|settings|config(uration)?|api key|endpoint|path|"
    r"install|installation|uninstall|setup|enable|disable|configure)\b",
    re.IGNORECASE,
)
```
If `_EXACT_FACT_SIGNALS.search(query)` → return True (skip broadening), so retrieval runs on the
literal query (plus the original arm only). The hybrid BM25 arm already favors exact terms, so
skipping step-back HELPS precision here.

### Why it's safer than 3.1
This only changes whether the OPTIONAL step-back variant is generated. The original query is
always retrieved regardless. Worst case: a query that *would* have benefited from broadening
doesn't get it → slightly lower recall on that query, never wrong retrieval. No query is ever
replaced.

### Required tests
- "what are the silent parameters available?" → `_is_exact_*` True (skip broadening)
- "how do I install the CDP server" → True (skip)
- "what is the default database port?" → True (skip)
- "tell me about the company's history" → False (broaden — conceptual, benefits from step-back)
- "explain the architecture" → False (broaden)
Add to `test_query_transformer.py`.

### Interaction with 3.1
3.1 routes short referential messages to rewrite; 3.2 routes specific factual messages away from
broadening. A message like "what are the silent parameters available?" is **standalone (3.1=False)
AND exact-fact (3.2=True)** → retrieved literally, not rewritten, not broadened. That is exactly
the behavior that would have fixed turn 2.

---

## 3.3 — max_distance_threshold (CONFIG-ONLY, already deferred)
No code. Recommend operator A/B from 0.5 → 0.6 AFTER Phase-0 logs quantify how often NO_MATCH is
distance-driven on short queries (`config.py:77` docstring already warns 0.5 over-filters short
queries). Revisit with data.

---

## Open questions for you (block implementation of 3.1/3.2)
1. **Ambiguous "more detail on <specific topic>"**: follow-up (rewrite from prior turn) or
   standalone (retrieve the topic)? Recommended: standalone when a concrete noun follows "on/about".
2. **3.2 signal list**: the `_EXACT_FACT_SIGNALS` list above is domain-flavored (install/config/
   params). Want it kept generic as proposed, or tuned to your corpus's vocabulary?
3. **Scope**: implement both 3.1 and 3.2, or 3.2 only first (lower risk, still fixes the
   broadening half of turn 2) and evaluate before touching the higher-risk 3.1?

## Validation plan when approved
- New parametrized tests for the full matrices above (true-positive AND true-negative).
- ruff + targeted pytest; behavioral-change trap: check existing `test_query_transformer.py`
  for assertions about which queries currently get broadened/rewritten and update with comments.
- No frontend impact.
