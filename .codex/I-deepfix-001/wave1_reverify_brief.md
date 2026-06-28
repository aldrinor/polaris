HARD ITERATION CAP: 5 per document. This is iter 2 of 5 (FOCUSED RE-VERIFY).

REVIEW MODE: STATIC, FAST, NARROW. Iter-1 already reviewed the full wave-1 diff and APPROVED everything EXCEPT one P0 and one P2 (now fixed). Do NOT re-review the whole diff or explore the codebase. Read ONLY these changed functions in the working tree and confirm the two fixes are correct and introduce no new issue. Emit the schema at the end.

# I-deepfix-001 wave-1 iter-2 — verify the P0 + P2a fixes ONLY

## FIX 1 (was P0 — relevance gate not fail-open). Verify these 3 functions:
1. `src/polaris_graph/retrieval/prefetch_offtopic_filter.py::_similarity_scores` — now returns `None` (not `[0.0]*N`) on its 3 infra failures: (a) embedder has no embed_batch/encode, (b) zero-norm QUERY vector, (c) encode exception. A genuinely empty/zero-norm SNIPPET vector still appends a real `0.0`. Return type is now `Optional[list[float]]`.
2. `src/polaris_graph/retrieval/prefetch_offtopic_filter.py::filter_search_results` — when `sims is None`, returns kept=all candidates (FAIL-OPEN).
3. `src/polaris_graph/retrieval/evidence_selector.py::_semantic_relevance_scores` — filters out `None` per-anchor results; if EVERY anchor is None, returns `None` (so the live B4 gate at `live_retriever._relevance_threshold_select` falls back to the lexical cut, keeping candidates). A surviving anchor's genuine 0.0 for an empty-text row still yields 0.0 (intended drop).
CONFIRM: no path now converts a scorer/embedder ERROR into below-threshold 0.0 drops; an empty SNIPPET still scores 0.0 and drops (intended, documented); the change is purely fail-open and does not relax faithfulness.

## FIX 2 (was P2a — directive overmatch). Verify this:
`src/polaris_graph/retrieval/scope_query_validator.py::_IMPERATIVE_OPENER_RE` — narrowed to `^\s*(please\s|ignore\s|disregard\s|do not\s|don't\s)`; removed the polysemous research verbs (return/output/ensure/keep/put/format/note/never/always/make sure/remember). CONFIRM: a query like "return-to-work outcomes" / "output of the assay" / "ensure adequate dosing" is no longer classified a directive by `is_directive_clause`, while "ignore previous…" / "please respond only…" still are (and the high-precision `_DIRECTIVE_MARKERS` still catch "do not view"/"output format"/"respond only").

## New test added: `tests/polaris_graph/test_live_retriever_relevance_gate_b4.py::test_scorer_infra_failure_fails_open_to_lexical` (monkeypatches `_similarity_scores`->None, asserts `_relevance_threshold_select` returns (None,{},None) = lexical fallback, not a mass-drop).

P2b (constraints serialization) is intentionally deferred to wave-2 — do not flag it.

## Output schema (REQUIRED, last lines)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
