# Backend Test-Suite Census (Phase 0) + Phase 1 Results

Status: **Phase 0 complete; Phase 1 (cross-test pollution) complete.** This is
the triage census that sequences the remediation work to make the full backend
suite a blocking CI gate.

## Phase 1 result (verified, full-suite re-run)

A single surgical fix — restoring the `app.*` `sys.modules` table in
`test_admin_token_warning`'s teardown (commit on this branch) — removed the
primary cross-test pollution source. Full-suite re-run on the same interpreter
and dep set:

| Metric | Baseline | After Phase 1 | Δ |
| --- | --- | --- | --- |
| Passed | 2776 | **3022** | **+246** |
| Failed | 937 | **727** | **−210** |
| Errors | 42 | **6** | **−36** |

- This recovered ~246 tests with a 19-line change, matching the plan's
  "~200–300" Phase 1 estimate but **without** the risky session-scoped
  data_dir / `app.*`-clearing rewrites the plan proposed (both of which the
  Phase 0 analysis showed to be unsafe/contradictory).
- **No residual pollution.** Previously-polluted modules now match their
  standalone failure counts exactly (e.g. `test_organizations_routes` 34→0;
  `test_groups_auth` 52→1, standalone is also 1). The `sys.modules`-rewrite
  grep found no second polluter of this kind.
- **No CI-gate regression.** All 8 current gate files still pass in isolation;
  `test_embeddings_cache` actually went 13 failures → 0 (its SSRF mocks were
  also victims of the dual-`settings` split).
- The 6 remaining errors are all `test_vault_document_permissions_regression`
  (`UNIQUE constraint failed: vaults.id`) — genuine double-setup, fails
  standalone too, → Phase 3.

### Post-Phase-1 failure buckets (727 failures)

With pollution gone, the SSRF picture changed materially: tests that the split
had forced onto the unresolvable `harrier-embed` URL now hit their intended
**mocked `localhost`** URL, which the guard blocks only for lack of the env
opt-in. So **Phase 2's `ALLOW_LOCAL_SERVICES=1` now fixes ~96 tests**
(`localhost`/`127.0.0.1` "resolves to private"), up from the ~17 estimated
pre-Phase-1. Remaining genuine buckets: async/await drift (~120), assertion
drift (~88), `must_change_password` fixture-schema drift (~76), MagicMock
comparison/timeout drift (~76), `harrier-embed`/`host.docker.internal` needing
HTTP mocking (~87), `csrf_protect` introspection drift (16), `FakeLLMClient`
kwarg drift (16), pyarrow/lancedb stub gaps → nightly (~12).

---

The remainder of this document is the original **Phase 0** census.

This document is produced from an actual full-suite run, not from estimates.
Per the repo review rules, every number below is backed by a reproducible
command and an artifact, and claims that have not yet been verified are marked
as such.

## How this was measured

```
cd backend
python -m pytest tests/ --tb=line -q -p no:cacheprovider --junit-xml=census.xml
```

- Interpreter: **Python 3.11.15** (matches the CI pin of 3.11, so these are
  real results — not the false `RuntimeError: There is no current event loop`
  failures that a 3.14 local interpreter produces).
- Dependency set: the reduced CI set (`requirements-ci.txt` +
  `requirements-dev.txt`). `lancedb` and `unstructured` are stubbed
  unconditionally by `backend/conftest.py`; `pyarrow`/`numpy`/`jwt` are stubbed
  only when the real package is absent.
- Wall clock: **2398.79s (~40 min)** for the full run.

Per-module data: `docs/engineering/test-suite-census.csv`.

## Headline numbers (verified)

| Metric | Count |
| --- | --- |
| Collected | **3814** |
| Passed | **2776** |
| Failed | **937** |
| Errors (setup/collection) | **42** |
| Skipped | **59** |

These match the figures the remediation plan was built on.

## Skips (verified)

All 59 skips are benign and expected under CI:

| Count | Reason |
| --- | --- |
| 57 | `Backend not running at http://localhost:...` — live end-to-end probes that require a running server. Correctly skipped in unit CI. |
| 2 | `ADMIN_SECRET_TOKEN env var is set` — `test_config_alignment.py` env-conditional skips. They fire because `conftest.pytest_configure` sets `ADMIN_SECRET_TOKEN=test-admin-key`. Accept, or move the token-set into a fixture if these two are wanted in CI. |

## Errors (verified) — 42 total, all setup-time

The 42 errors are **setup** errors (not flaky collection), in three modules:

| Module | Count | Root cause |
| --- | --- | --- |
| `test_rag_engine_filtering_adversarial` | 29 | `URLBlocked: URL host 'harrier-embed' did not resolve` — SSRF guard rejects an unresolvable Docker hostname during fixture setup. |
| `test_rag_engine_none_threshold_adversarial` | 7 | same `harrier-embed` SSRF setup failure. |
| `test_vault_document_permissions_regression` | 6 | `sqlite3.IntegrityError: UNIQUE constraint failed: vaults.id` — fixture inserts a vault row that already exists (double-setup / non-isolated DB). |

## Failure root-cause buckets (verified by signature clustering)

Signatures were normalized (addresses/ids/numbers/tmp paths stripped) and
counted suite-wide. The dominant buckets:

| # | Bucket | Approx. count | Nature | Fix path |
| --- | --- | --- | --- | --- |
| 1 | `no such table: users` / `vault_members` / `org_members` | ~230 | **Mixed** — partly cross-test pollution, partly genuine fixture-schema drift (see below) | Phase 1 (pollution) + Phase 3 (genuine) |
| 2 | SSRF `... did not resolve` (`harrier-embed`, `host.docker.internal`, `reranker.local`, `old.example`) | ~200 | Host is unresolvable in CI | **HTTP mocking** (env var does NOT help — see note) |
| 3 | `AssertionError: <n> != <n>` (status codes / values) | ~93+ | Genuine behavioral drift | Phase 3 triage |
| 4 | `no such column: must_change_password` | 36 | Genuine fixture-schema drift | Phase 3 (update fixtures) |
| 5 | `pyarrow has no attribute 'schema'/'Array'` | ~40 | Stubbed pyarrow lacks real API | **Nightly** (real deps) |
| 6 | async-await drift (`coroutine not subscriptable/iterable`, `MagicMock can't be used in 'await'`) | ~60 | Genuine drift (sync tests on now-async code) | Phase 3 |
| 7 | SSRF `resolves to private ... ALLOW_LOCAL_SERVICES` (`127.0.0.1`, `localhost`) | ~17 | Guard blocks resolvable private IPs | **Phase 2 env var** (`ALLOW_LOCAL_SERVICES=1`) |
| 8 | `lancedb IvfPq() takes no arguments` | ~20 | Stubbed lancedb lacks real API | **Nightly** (real deps) |
| 9 | `module 'app.api.deps' has no attribute 'csrf_protect'` | 16 | Source-introspection drift after refactor | Phase 3 |
| 10 | `FakeLLMClient.chat_completion() unexpected kwarg 'max_tokens'` | 16 | Test-helper drift | Phase 3 |
| 11 | `'<=' not supported between MagicMock and int` | 15 | MagicMock used where numeric timeout expected | Phase 3 |
| 12 | `'State' object has no attribute 'rag_engine'/'secret_manager'` | ~17 | `app.state` not populated (lifespan not run for the test's app) | Phase 1/3 |
| 13 | `no current event loop` | 7 | Genuine on 3.11 (removed implicit-loop pattern) | Phase 3 |

### Critical correction to the plan's Phase 1 estimate

The plan assumed the `no such table` bucket (~230) is largely **pollution**, and
that fixing data isolation recovers ~200–300 failures. The census **disproves
that as stated**. Standalone re-runs:

| Module | In full suite | Standalone | Verdict |
| --- | --- | --- | --- |
| `test_organizations_routes` | 34 fail / 34 | **34 pass / 34** | **Pollution** |
| `test_groups_auth` | 52 fail / 52 | **51 pass, 1 fail** | 51 pollution + 1 genuine |
| `test_vault_org_routes_adversarial` | 40 fail / 41 | **40 fail / 41** | **Genuine** (not pollution) |
| `test_users_routes_adversarial` | fails | **fails standalone** (`must_change_password`) | **Genuine** schema drift |

So the `no such table` / `no such column` buckets are a **mix**: some modules
are pure pollution (recoverable by Phase 1), others fail identically in
isolation and are genuine fixture-schema drift (Phase 3). The pollution
sub-total confirmed so far is ~85 tests (`org_routes` 34 + `groups_auth` 51),
not the ~230 the bucket size implies. Per-module standalone verification is
therefore **mandatory** before attributing any failure to pollution.

### Note on the SSRF buckets (verified against `app/services/ssrf.py`)

`assert_url_safe` resolves the host via `getaddrinfo` **before** the private-IP
check (ssrf.py:100). Therefore:

- Setting `ALLOW_LOCAL_SERVICES=1` only unblocks hosts that **resolve** to a
  private/loopback IP (`127.0.0.1`, `localhost`) — bucket 7 (~17 tests).
- It does **not** help unresolvable Docker hostnames (`harrier-embed`,
  `host.docker.internal`) — bucket 2 (~200 tests). Those raise
  `did not resolve` regardless of the env var and require **HTTP mocking** (or
  the nightly job with real service hostnames mocked). The plan's Phase 2 is
  correct on this point; the headline win from the env var alone is small.

## Two design corrections to the plan (flagged for Phase 1)

1. **Phase 1a scope contradiction.** The plan says an *autouse session-scoped*
   fixture "gives every test its own fresh SQLite DB." A session-scoped fixture
   sets `data_dir` **once** for the whole session; it does **not** give each
   test a fresh DB. Per-test isolation requires *function* scope. The actual
   pollution vector is shared **mutable global state** (`settings` singleton,
   `app.dependency_overrides`, `database._pool_cache`), so the correct fix is a
   function-scoped **state-restoration** fixture, not a session-scoped data_dir.

2. **Phase 1b is unsafe as written.** "Re-clear `app.*` from `sys.modules`
   between tests" would split-brain the suite: test modules import `app`,
   `settings`, etc. at collection time and hold those references for the whole
   session. Clearing `sys.modules` only affects *new* imports, so a test would
   hold the *old* `app`/`settings` while freshly-imported route code sees *new*
   ones — creating more pollution, not less. This step should be dropped in
   favor of state restoration.

## Next steps (sequenced)

- **Phase 1 — DONE.** Root-cause fix in `test_admin_token_warning` (not a broad
  conftest fixture). +246 tests, no residual pollution. See Phase 1 section
  above.
- **Phase 2**: `ALLOW_LOCAL_SERVICES=1` in CI env — now worth **~96 tests**
  (revised up from ~17 once Phase 1 unmasked the real mocked-`localhost` URLs)
  + HTTP mocking for the ~87 unresolvable-host tests. Note: adding the env var
  is inert for the *current* 8-file gate (those files manage their own SSRF
  env), so it lands together with Phase 4 module additions rather than as a
  standalone no-op.
- **Phase 3**: per-module triage of genuine drift (async/await ~120, assertion
  ~88, `must_change_password` schema ~76, MagicMock ~76, csrf_protect 16,
  FakeLLMClient kwarg 16, event-loop 7).
- **Phase 5**: nightly job with real `lancedb`/`pyarrow`/`unstructured` for the
  stub-gap buckets (~12).

## Determinism note

The plan worried the baseline was non-deterministic. It is not: pytest collects
in a fixed order with no randomization, so the failure *set* is reproducible
run-to-run (the census, the 1–64 subset, and the post-fix full run all gave
consistent per-module counts). Pollution made results order-*dependent*, but
the order is constant, so repeated full runs were not needed to trust the
numbers. xdist (Phase 6) would change this and must be re-validated for
determinism when introduced.
