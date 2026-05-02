# RAG evaluation harness

A lightweight, CI-safe harness for measuring retrieval and citation
quality of the RAG pipeline.

## Why

Unit tests prove the code paths are wired; this harness measures
**quality** end-to-end against a golden set. Defaults can only be
tuned with evidence (per the task instructions) — this is the evidence
generator.

## Components

* `eval_harness.py` — the metric primitives (recall@k, MRR, nDCG@k,
  citation validity, fact coverage) plus the `EvalRunner` aggregator.
* `run_eval.py` — CLI that consumes a golden JSONL + a results JSONL
  and emits a summary + machine-readable JSON report.
* `fixtures/golden.jsonl` — a tiny dataset that exercises every
  scoring path (retrieval recall, citation, memory recall, no-match).
* `test_eval_harness.py` (under `backend/tests/`) — unit tests over the
  metric math.

## Golden case shape

```json
{
    "id": "case-001",
    "vault_id": 1,
    "query": "What is the project deadline?",
    "expected_chunk_ids": ["chunk-1", "chunk-2"],
    "expected_source_labels": ["S1", "S2"],
    "expected_facts": ["October 15"],
    "expected_memories": ["M1"],
    "expect_no_match": false
}
```

Every field except `id` and `query` is optional. A case with no
`expected_chunk_ids` simply has `recall@k`, `MRR`, and `nDCG`
recorded as `null` so the summary doesn't average them in.

## Result shape

```json
{
    "id": "case-001",
    "retrieved_chunk_ids": ["chunk-1", "chunk-7"],
    "retrieved_source_labels": ["S1", "S2"],
    "answer": "We shipped X [S1] and Y [S2].",
    "cited_source_labels": ["S1", "S2"],
    "cited_memory_labels": [],
    "invalid_citations": [],
    "no_match_returned": false
}
```

## Running

```bash
cd backend
python -m tests.eval.run_eval \\
    --golden tests/eval/fixtures/golden.jsonl \\
    --results path/to/your/results.jsonl \\
    --out eval-report.json
```

The summary is printed to stdout; the JSON report contains per-case
metric breakdowns.

## Producing results

The harness intentionally does not call the live LLM or vector store
itself — wire it up however you like:

* **Mocked replay**: feed deterministic mock retrieval/citation
  output for fast CI smoke testing.
* **Live**: write a small adapter that runs `RAGEngine.query` for
  each golden case and records the actual retrieved chunk ids /
  citations into a results file.
* **A/B**: run the harness twice (with different config values) and
  compare reports.

## CI safety

Importing `eval_harness` is side-effect free. The unit tests in
`backend/tests/test_eval_harness.py` exercise every metric without
any backend dependency.
