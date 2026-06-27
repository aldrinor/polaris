NON-INTERACTIVE BATCH MODE — CRITICAL: you are running under `codex exec` with NO interactive channel. The `request_user_input` tool does NOT exist here. NEVER call request_user_input. NEVER ask the user a question. If anything is ambiguous or a file seems missing, treat it as a review FINDING and proceed. Your entire job is to read the listed files and write the verdict. Do not stop for input.

HARD ITERATION CAP: 5 per document. This is iter 2 of 5. Front-load ALL real findings now. Reserve P0/P1 for real faithfulness/correctness risks. Verdict APPROVE iff zero P0 AND zero P1. Emit the §8.3.9 schema with a final `verdict:` line.

STATIC review ONLY. READ these files; do NOT run pytest/anything:
- C:/POLARIS/.codex/I-wire-014/full_wire.patch
- C:/POLARIS/src/polaris_graph/nodes/intent_frame.py
- C:/POLARIS/tests/polaris_graph/nodes/test_intent_frame.py

This is iter-2; the iter-1 P1s were: (P1-1) W1/W9 missing from fail-closed preflight; (P1-2) W9 dedup canary on wrong consumer (ContentDeduplicator vs Gate-B finding/basket dedup); (P1-3) [content_relevance] pre-execution config-echo canary; (P1-4) [credibility_llm_tiering] false-positive canary on full rules-floor fallback. VERIFY each is fixed:

(1) PG_SCOPE_INTENT_FRAME (W1) is now in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS; W9 is either a real required flag OR honestly reconciled as CRAG-transitive (covered by PG_ADEQUACY_CRAG, no fake required flag);
(2) [content_relevance] canary now fires post-scoring with real counts (scored/relevant/demoted/escalated), pre-exec echo removed;
(3) [credibility_llm_tiering] canary logs attempted/llm_success/fallback and treats zero llm_success as DEGRADED, not success;
(4) every other wired winner still in slate AND preflight-required; intent_frame advisory+fail-closed, scope gate binding, faithfulness frozen; snake_case/no-magic-number.

Emit the schema; final line `verdict: APPROVE` or `verdict: REQUEST_CHANGES`.
