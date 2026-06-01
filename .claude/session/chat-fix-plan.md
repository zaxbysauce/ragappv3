# Chat System Fix Plan — FINAL (critic-revised) — awaiting user approval to execute

Scope decision (user): **Instant mode may be lower quality; Thinking mode keeps full quality.**
Execution scope (user): **All phases incl. verified 5.x.** Workflow: **worktree + branch, no push; show diff; local ci-compatibility-audit.**
Status: validated by explorers + reviewers + independent critic. NOT yet executed.

All line numbers verified against current source. Every fix lists: evidence, change, risk, tests, and behavioral-test-trap.

---

## PHASE 0 — Instrumentation (lands first; it's the gauge)

### 0.1 Apply settings.log_level to the root logger (LOG_LEVEL is currently dead)
- Evidence: `config.py:412` log_level="INFO"; `docker-compose.yml:113` passes it; `.env.example:255` documents it. No `basicConfig`/`dictConfig`/root `setLevel` anywhere in `backend/app/**` (only standalone scripts). Operator confirmed root logger at WARNING → all `[query]` INFO lines dropped.
- Change: add root logging config. **Critic caveat applied:** do it in `lifespan()` startup (not module-top) to avoid disturbing uvicorn's access-log handlers; verify access logs still format after applying.
  ```python
  # first lines of lifespan(), before run_migrations
  import logging
  logging.getLogger().setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
  # add a StreamHandler only if root has none, so app loggers emit without tearing out uvicorn's
  ```
- Risk: LOW-MED (was LOW). Verify uvicorn access logs unchanged after deploy.
- Test: unit asserting root effective level follows settings.log_level; manual `docker logs` shows `[query]`.

---

## PHASE 1 — Latency: two-tier pipeline (Instant fast, Thinking unchanged)

Thread resolved `mode` into aux gating. New per-mode flags default to the user-approved speed wins.

### 1.1 Skip step-back/query-transformation in Instant
- Evidence: `rag_engine.py:474` `if settings.query_transformation_enabled and active_client is not None:` (mode-agnostic).
- Change: `... and not (mode == ChatMode.INSTANT and settings.instant_skip_query_transformation)`. New flag `instant_skip_query_transformation: bool = True`.
- Risk: LOW (narrower Instant recall, accepted). Thinking unchanged.

### 1.2 Skip CRAG retrieval evaluation in Instant
- Evidence: gate `rag_engine.py:1227` inside `_execute_retrieval`; `mode` NOT passed (sig `:883-893`, call `:628-637` passes `active_client` only). `ChatMode.INSTANT/THINKING` confirmed (`chat_mode.py:5-7`).
- Change: add `mode: Optional[ChatMode] = None` param to `_execute_retrieval`, pass at call site, gate `... and not (mode == ChatMode.INSTANT and settings.instant_skip_retrieval_evaluation)`. New flag `instant_skip_retrieval_evaluation: bool = True`.
- Risk: LOW-MED (new param threaded through one call site/sig).

### 1.3 Skip distillation synthesis in Instant — DEFENSE-IN-DEPTH (not load-bearing)
- Critic finding: synthesis only runs on `eval_result=="NO_MATCH"` (`context_distiller.py:91-98`); with 1.2, Instant keeps `eval_result="CONFIDENT"` (`rag_engine.py:607/917`), so synthesis **already can't run in Instant**. 1.3 is belt-and-suspenders.
- Change: pass `None` client when `mode==INSTANT and settings.instant_skip_distillation_synthesis`. Flag `instant_skip_distillation_synthesis: bool = True`. Labeled non-load-bearing.
- Risk: NONE incremental.

### 1.4 Follow-up rewrite — keep ON in Instant by default
- Evidence: `rag_engine.py:449-468`, uses `active_client` (4B in Instant). Flag `instant_skip_followup_rewrite: bool = False` (documented knob, no default change).
- **Corrected claim:** Instant fast-path is "embed → search → dedup → generate, **plus the optional follow-up rewrite when a follow-up is detected**." NOT "zero aux round-trips" (critic MUST-FIX #2).

---

## PHASE 2 — Correctness: fix the fabrication bug (Thinking-mode quality)

### 2.1 Robust "no relevant content" sentinel
- Evidence: `context_distiller.py:197` exact-match `== "NO_RELEVANT_CONTENT"`; a paraphrased refusal becomes injected evidence (turn-2 root cause).
- Change: case-insensitive prefix/substring match for the sentinel + a small refusal-pattern set; anything failing a positive-content check → treat as "no synthesis," keep deduped real chunks.
- Risk: LOW (strictly less fabrication).

### 2.2 Preserve provenance on synthesized sources (+ minimal wired frontend)
- Evidence: `context_distiller.py:203-208` `metadata={"synthesized": True}`, `score=top3[0].score`. Critic traced exact symptom: `document_retrieval.py:523-528` → "Unknown document" (no filename in metadata); borrowed distance score + no score_type → frontend `relevance.ts:15-20` renders "Highly Relevant."
- Change: carry originating `source_file/filename(s)` + ids into synthesized metadata; do NOT inherit a misleading high score. **Critic scope correction:** the "Synthesized from N sources" label is NOT wired in `SourceCards.tsx`. To honor the no-unwired-work rule, scope = (a) preserve provenance so it renders the real source filename(s) [backend-only, frontend already tolerates], and (b) OPTIONAL small `SourceCards.tsx` change to show a "Synthesized" badge — **included only if you want it; otherwise dropped, not deferred.**
- Risk: LOW-MED (touches synthesized-source display; frontend reads filename/score/score_type/snippet, no `synthesized` dependency).

### 2.3 Don't REPLACE real chunks with the lossy summary on NO_MATCH
- Evidence: `context_distiller.py:209` `return [synthetic] + rest` drops top-3 real chunks on the least-confident verdict.
- Change: keep top-3 real chunks; append the synthesized passage as a clearly-labeled hint (or skip synthesis-as-source entirely). Never replace.
- Risk: LOW (more grounding; slightly larger context).

### 2.4 Cap CRAG eval max_tokens — **8 → 64** (critic MUST-FIX #1)
- Evidence: `retrieval_evaluator.py:65` `max_tokens=1024` for one word. Parser fail-opens to CONFIDENT on empty/unparseable (`:68-87`).
- Change: `max_tokens=64` (not 8). Reasoning model needs slack before the word; 8 truncates → silent always-CONFIDENT, which defeats CRAG and masks 2.1/2.3.
- Risk: LOW. **Test 2.1/2.3 by FORCING NO_MATCH (mock), not via live eval** (critic order hazard).
- Test-trap: no test asserts 1024; the real trap is the evaluator-call assertions below.

---

## PHASE 3 — Precision for exact-fact queries — **DESIGN + TESTS REQUIRED (not blank-check)** (critic MUST-FIX #3)

Demoted from "safe as written." I will present a concrete regex + true/false-positive test matrix for your sign-off BEFORE implementing 3.1/3.2.

### 3.1 Widen follow-up detection — HIGH RISK, needs spec
- Evidence: `query_transformer.py:36-57`; "more detail on the silent parameters available?" matched neither gate (turn-2 contributor). Risk: a false positive replaces the user's query with an LLM rewrite (`rag_engine.py:447-466`). Regex is `^...$`-anchored — additions must stay anchored.
- Deliverable before code: exact added patterns + a test matrix (must-match follow-ups vs must-NOT-match standalone questions, incl. "what are the X available?").

### 3.2 Don't broaden exact-fact queries via step-back — needs spec
- Evidence: `query_transformer.py:60-84` skip gate misses guide/procedural queries. Deliverable: concrete heuristic + tests. Lower risk than 3.1.

### 3.3 max_distance_threshold — CONFIG-ONLY, deferred
- Evidence: `config.py:77` docstring warns 0.5 over-filters short queries. Recommend operator A/B (→0.6) AFTER Phase-0 logs quantify NO_MATCH-by-distance. No code change.

---

## PHASE 4 — Infra hygiene (config-only)

### 4.1 Move Instant endpoint off host.docker.internal
- Evidence: `config.py:48` `instant_chat_url=http://host.docker.internal:1234` (default mode), resolves to IPv6 per operator; Thinking already on direct IP. Operator setting change to direct host IP/loopback. Validate via Phase-0 logs. No code change.

---

## PHASE 5 — Now CONFIRMED (were verify-gated); both actionable

### 5.1 Extra DB connection per chat request — CONFIRMED (F-005)
- Evidence: `chat.py:483` and `chat.py:526` call standalone `evaluate_policy()`, which opens its OWN pool connection (`deps.py:454-455`), on top of `get_current_active_user`'s connection → **2 concurrent conns/request**; pool `max_size=10` (`lifespan.py:232`) → ~5 concurrent chat requests exhaust pool → queueing (a real "minutes under load" candidate). DI variant already exists: `get_evaluate_policy` (`deps.py:414-433`).
- Change: switch both `/chat` and `/chat/stream` to the DI `Depends(get_evaluate_policy)` variant → 1 conn/request. Apply to both routes for consistency.
- Risk: LOW-MED (route signature change; must preserve the vault_id-None admin branch). Test: permission still enforced (403 paths) + a pool-usage assertion if feasible.

### 5.2 Write lock on every vector search — CONFIRMED (F-006)
- Evidence: `vector_store.py:897-901` acquires write lock then calls `_maybe_create_vector_index()`; the freshness early-return (`:359-369`) is INSIDE the lock. Same `_write_lock` used by ingestion/delete (`:497,509,1110,1183`). During ingestion, search blocks up to 30s (`write_lock_timeout_seconds`).
- Change: hoist the read-only freshness check (`:337-369`) OUTSIDE the lock; acquire the lock ONLY for actual index creation (`:371-397`). Re-check freshness inside the lock (double-checked) to avoid a race.
- Risk: MED (concurrency-sensitive; needs double-check pattern + test for concurrent search-during-ingest). Highest-care item.

---

## Cross-cutting execution rules
- Isolation: dedicated worktree + branch; no push. Show diff; run ci-compatibility-audit locally (Py 3.11; ignore local 3.14 event-loop false failures).
- New config flags preserve CURRENT behavior except the approved Instant speed wins. Thinking defaults unchanged.
- Behavioral-change test traps CONFIRMED (must update with superseding comments, not just note):
  - `tests/test_context_distiller.py:298-300,312-318,433-434` assert synthesis-replaces-chunks + exact NO_RELEVANT_CONTENT → broken by 2.1/2.3.
  - `tests/test_settings_live_propagation.py:302-347` (`evaluator.evaluate.assert_awaited_once()` :347) → Instant variant broken by 1.2; check mode used.
- Every fix ships with a test asserting REAL behavior (AGENTS.md).
- Suggested order: 0 → 5.1 → 1.x → 2.x → 5.2 → (3.x spec for approval) → 4 (operator). Independently shippable.

## Out of scope (no action without instruction)
- Third dedicated utility LLM (use existing 4B via mode gating).
- Moving CRAG/distillation fully off hot path (fire-and-forget) — larger refactor; revisit post-logs.
- JWT expiry (F-008, LOW) — note only.
