# M-50 Code Audit Findings

Verdict: NOT READY - one blocker.

## Blocker

1. `src/polaris_graph/generator/multi_section_generator.py:3239` passes the wrong quote to the subsection LLM when `direct_quote` is thin but `_m42b_refetched_quote` is the qualifying quote. `_m50_select_candidate_trials()` correctly checks the two quote fields without `or` short-circuiting (`lines 1767-1773`), but it returns only `(anchor, row, biblio_num)`. The generation path then recomputes `quote = row.get("direct_quote") or row.get("_m42b_refetched_quote") or ""`, so any non-empty short `direct_quote` hides the richer refetched quote. This violates audit item 3 and the M-47 pass-2 pattern the implementation intended to copy. It also means the new `test_refetched_quote_qualifies` covers candidate selection only, not the actual LLM input.

Recommended fix: carry the selected quote out of `_m50_select_candidate_trials()` as part of the candidate tuple, or add a shared helper that returns the richer eligible quote and use it both in selection and `_gen_one()`. Add a test that monkeypatches `_call_m50_per_trial_subsection()` and asserts the refetched quote is passed when `direct_quote` is non-empty but under 100 chars.

## Non-Blocking Notes

- Strict gating is correct at candidate selection: `_M50_MIN_PRIMARIES_FOR_SUBSECTIONS = 2`, and `_m50_select_candidate_trials()` returns `[]` below threshold. One small telemetry wrinkle remains: if >=2 candidates are selected but fewer than 2 LLM calls return usable prose, `m50_per_trial_subsections_text` is suppressed while `m50_per_trial_subsections_entries` may still contain the successful singleton. That does not affect report output, but it can make `m50_per_trial_subsections.json` look like subsections shipped when the report block was suppressed.
- Indirect exclusion is sufficient for the T2D sweep context. `scripts/run_honest_sweep_r3.py` derives direct anchors from `per_query_trial_population_scope`, and `config/scope_templates/clinical.yaml` labels SURMOUNT-1/3/4 as `indirect_for_t2d` while SURMOUNT-2 is `direct`.
- The prompt names the required seven elements and requires per-claim citations. It also avoids drug-name leakage in the example skeleton.
- Placement between Trial Program Timeline and Limitations is logical.
- Parallelism uses the existing semaphore, so rate limiting is bounded with section generation. It still adds one LLM call per qualifying trial, but the concurrency shape is acceptable.
- Template-driven candidate selection is an acceptable generalization of the four named plan examples, as long as direct/indirect scope labels remain maintained.

## Verification

- `python -m pytest -q tests/polaris_graph/test_m50_per_trial_subsections.py` passed: 11/11.
- `pytest` was not directly on PATH; the module invocation worked.
