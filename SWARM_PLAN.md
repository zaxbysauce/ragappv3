# RAG Quality Fix List — 10 Targeted Remediations
Swarm: mega
Phase: 1 [COMPLETE] | Updated: 2026-04-16T02:08:48.461Z

---
## Phase 1: Config defaults alignment (Fixes 2, 7, 8, 9, 10) [COMPLETE]
- [x] 1.1: Fix per_doc_chunk_cap default from 2 to 5 in backend/app/config.py line 204. FR-002. [SMALL]
- [x] 1.2: Fix max_distance_threshold default from 1.0 to 0.5 in backend/app/config.py line 51. FR-008. [SMALL]
- [x] 1.3: Disable query transformation by default: set query_transformation_enabled=False and hyde_enabled=False. Update tests. FR-009. [SMALL]
- [x] 1.4: Change document_parsing_strategy default from 'fast' to 'auto'. FR-010. [SMALL]
- [x] 1.5: Change multi_scale_chunk_sizes default. FR-011. [SMALL]

---
## Phase 2: Code logic fixes (Fixes 1, 4, 5) [COMPLETE]
- [x] 2.1: Remove sort_key function and expanded_sources.sort in document_retrieval.py. FR-001. [SMALL]
- [x] 2.2: Fix exact-match promotion to rank 1. FR-005. [SMALL]
- [x] 2.3: Wire hybrid_alpha into rrf_fuse at vector_store.py line 574. FR-006. [SMALL]
- [x] 2.4: Wire hybrid_alpha into rrf_fuse at vector_store.py line 801. FR-006. [SMALL]

---
## Phase 3: Medium-risk structural changes (Fixes 3, 6) [COMPLETE]
- [x] 3.1: Contextual chunking: store context in metadata. FR-003. [SMALL]
- [x] 3.1.1: Amend contextual_chunking.py to dual-store: keep context prepended to chunk.text for enriched embeddings AND store in chunk.metadata['contextual_context']. Change lines 270-276: keep chunk.raw_text = chunk.text, add chunk.metadata['contextual_context'] = context, and restore chunk.text = f'{context}\n\n{chunk.text}'. Update test_contextual_chunking.py line 275: change assertEqual(chunk.text, 'Original chunk text') to assertEqual(chunk.text, 'Context for chunk\n\nOriginal chunk text'). Lines 205, 496, 526, 616 already check metadata which is correct for dual-store. [SMALL] (depends: 3.1)
- [x] 3.2: Prompt builder: surface contextual_context in header. FR-004. [SMALL]
- [x] 3.2.1: Amend prompt_builder.py line 185: change ctx_note[:120] to ctx_note[:200] for 200-char truncation per user decision. Update task 3.2 acceptance. [SMALL] (depends: 3.2)
- [x] 3.3: Context distiller: gate synthesis to NO_MATCH only. FR-007. [SMALL]

---
## Phase 4: Integration verification [COMPLETE]
- [x] 4.1: Run full test suite: pytest backend/tests/ -v --tb=short. Verify all existing tests pass. SC-011, SC-012. [SMALL]
- [x] 4.2: Verify telemetry and logging: spot-check 3 key log paths. [SMALL]
