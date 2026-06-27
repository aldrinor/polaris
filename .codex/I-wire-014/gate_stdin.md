HARD ITERATION CAP: 5 per document. This is iter 1 of 5. Front-load ALL real findings now.
Reserve P0/P1 for real faithfulness/correctness risks ONLY: scope gate weakened (intent_frame MUST be advisory, not a relaxation), a canary that is not behavioral, a winner flag missing from the slate OR from the preflight-required list (silent-OFF risk), a faked/wrong dedup wire, magic numbers, silent except-pass. Cosmetics are P3/P2. Verdict APPROVE iff zero P0 AND zero P1. Emit the §8.3.9 schema.

STATIC review ONLY. READ these files, do NOT run pytest / do NOT execute anything:
- C:/POLARIS/.codex/I-wire-014/full_wire.patch  (the full 14-winner wiring diff)
- C:/POLARIS/src/polaris_graph/nodes/intent_frame.py  (NEW W1 module)
- C:/POLARIS/tests/polaris_graph/nodes/test_intent_frame.py  (NEW test)

ACCEPTANCE:
(1) ALL 14 winners wired: each winner flag is force-set in run_gate_b.py _FULL_CAPABILITY_BENCHMARK_SLATE (booleans + the string-valued PG_CLINICAL_PDF_EXTRACTOR=mineru25 / PG_EMBEDDER_MODEL=qwen3 / PG_RERANKER_MODEL=qwen3 / PG_CONTENT_RELEVANCE_RERANKER_MODEL) AND appears in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS (fail-closed before spend). Check the 11 front-half: PG_QGEN_FS_RESEARCHER, PG_SEARCH_FUSION_WRRF, PG_CLINICAL_PDF_EXTRACTOR, PG_CONTENT_RELEVANCE_JUDGE(+reranker), PG_EMBEDDER_MODEL, PG_RERANKER_MODEL, PG_CREDIBILITY_LLM_TIERING, PG_CONSOLIDATION_NLI, PG_ADEQUACY_CRAG, PG_SCOPE_INTENT_FRAME, + the W9 dedup flag. Flag ANY winner missing from slate OR preflight-required (that is the silent-OFF bug we are fixing).
(2) intent_frame.py is ADVISORY (runs before run_scope_gate, does NOT replace/relax it; scope gate stays binding) + FAIL-CLOSED (raises if enabled but the frame is empty/None). Faithfulness engine untouched.
(3) the firing canaries ([wrrf] / [content_relevance] / [credibility_llm_tiering] / [content_dedup] / [intent_frame]) log ONLY on real execution with real runtime counts — not a flag value/import/config echo.
(4) snake_case, module-level constants (no magic numbers), no silent except-pass, explicit imports.

Emit the §8.3.9 schema with a final line `verdict: APPROVE` or `verdict: REQUEST_CHANGES`.
