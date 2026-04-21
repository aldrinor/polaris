---
audit_type: code_review_pre_sweep
fix: M-28 Fix #1 (regulatory-anchor retrieval)
commit_range: 14b50a9..HEAD
verdict: NOT_READY
blockers: 1
mediums: 2
---

## 1. No Hard-Coded Agency/Domain Names In Python

Verdict: **BLOCKER**

`src/polaris_graph/retrieval/regulatory_expander.py` is behaviorally template-driven, but it does not satisfy the explicit "ZERO agency-specific strings anywhere in the .py file" requirement. The module docstring/comment text contains agency and host examples:

- `src/polaris_graph/retrieval/regulatory_expander.py:5` mentions FDA and `accessdata.fda.gov`.
- `src/polaris_graph/retrieval/regulatory_expander.py:6` mentions EMA, `ema.europa.eu`, Health Canada, and `hres.ca`.
- `src/polaris_graph/retrieval/regulatory_expander.py:8` mentions FDA.
- `src/polaris_graph/retrieval/regulatory_expander.py:22-23` lists FDA/EMA, Federal Register, SEC, and EPA examples.
- `src/polaris_graph/retrieval/regulatory_expander.py:58` uses `https://fda.gov/path` in a comment.

This is not a runtime hard-code, but it violates the audit criterion as written. Move examples to YAML/test fixtures or make comments fully generic before V18.

## 2. Generalization Safety

Verdict: **PASS**

The expander no-ops when there is no usable anchor list. `_extract_anchors()` returns `[]` for non-dict templates, missing `regulatory_anchors`, and non-list values at `src/polaris_graph/retrieval/regulatory_expander.py:47-51`; `expand_regulatory_queries()` then returns `[]` at `src/polaris_graph/retrieval/regulatory_expander.py:93-95`.

Manual check with the existing `tech` template, which has zero anchors, produced zero regulatory queries. A materials-science or other non-regulatory template with no `regulatory_anchors` should therefore emit no extra queries and not crash.

## 3. Anchor-List Robustness

Verdict: **PASS**

The parser handles the requested malformed cases:

- Missing key / wrong type / `None`: treated as empty at `src/polaris_graph/retrieval/regulatory_expander.py:47-51`.
- Non-string entries: skipped at `src/polaris_graph/retrieval/regulatory_expander.py:53-55`.
- Empty or whitespace-only entries: stripped/lowercased and dropped at `src/polaris_graph/retrieval/regulatory_expander.py:56-61`.
- URL paths or full URLs: rejected by the `/` check at `src/polaris_graph/retrieval/regulatory_expander.py:60`.
- Entries with spaces: rejected at `src/polaris_graph/retrieval/regulatory_expander.py:60`.
- Case duplicates: normalized to lowercase at `src/polaris_graph/retrieval/regulatory_expander.py:56` and deduped preserving order at `src/polaris_graph/retrieval/regulatory_expander.py:63-70`.

## 4. Serper `site:` Operator Correctness

Verdict: **PASS**

The emitted format is exactly `{question} site:{host}` at `src/polaris_graph/retrieval/regulatory_expander.py:96`. It is not reversed to `site:{host} {question}`.

## 5. Scope-Validator Interaction

Verdict: **PASS**

The scoped clinical query survives validation. `validate_amplified_queries()` dedupes and tokenizes at `src/polaris_graph/retrieval/scope_query_validator.py:137-150`, then keeps queries whose Jaccard score meets the floor at `src/polaris_graph/retrieval/scope_query_validator.py:151-154`.

Manual check for `tirzepatide safety site:fda.gov` against a tirzepatide/safety protocol kept the query. The site tokens increase the denominator, but the original question terms remain in the query, so the default floor does not kill the M-28 query for the clinical/tirzepatide case.

## 6. Cost Impact

Verdict: **MEDIUM**

The wiring blindly appends regulatory queries at `scripts/run_honest_sweep_r3.py:559-563`; there is no query-count cap or truncation step before calling `run_live_retrieval()` at `scripts/run_honest_sweep_r3.py:566-575`.

The budget variable name/commenting is misleading. `PG_SWEEP_MAX_SERPER` is read at `scripts/run_honest_sweep_r3.py:536`, but `run_live_retrieval()` uses `max_serper` as the number of Serper results per query, not as the number of amplified queries. The retriever loops over every effective query at `src/polaris_graph/retrieval/live_retriever.py:942`, calls Serper for each at `src/polaris_graph/retrieval/live_retriever.py:944-945`, and also calls S2 for each at `src/polaris_graph/retrieval/live_retriever.py:958-960`.

Impact: M-28 adds one Serper call and one S2 call per surviving anchor query. Clinical adds 7 anchors. The large clinical tirzepatide sweep item already has 30 hand-curated amplified queries, so M-28 raises the generic retrieval loop to roughly 38 query iterations including the original question. This is bounded by template size but not explicitly capped.

Mitigation before V18: add a clear query-count cap or reserve anchor slots intentionally, and consider suppressing S2 fanout for `site:` anchor queries because `site:` is a Serper/Google operator.

## 7. Duplicate Amplified Queries

Verdict: **PASS**

Exact duplicate query strings are collapsed downstream when a protocol is present. `run_live_retrieval()` prepends the research question and extends with amplified queries at `src/polaris_graph/retrieval/live_retriever.py:921-924`, then calls `validate_amplified_queries()` at `src/polaris_graph/retrieval/live_retriever.py:926-930`. The validator performs case-insensitive query dedupe at `src/polaris_graph/retrieval/scope_query_validator.py:137-143`.

URL-level dedupe also exists later via `seen_urls` at `src/polaris_graph/retrieval/live_retriever.py:939-950` and `src/polaris_graph/retrieval/live_retriever.py:961-965`. That dedupes results, not calls, so near-duplicate but non-identical site queries can still spend API budget.

## 8. Test Coverage Completeness

Verdict: **MEDIUM**

The 20 expander unit tests cover the core pure-function contract well, and the focused test run passed with `PYTHONPATH=src`: `27 passed` for `test_m28_regulatory_expander.py` plus existing scope-query-validator tests.

Coverage holes before sweep:

- No YAML integration test proves `load_scope_template()` can load the edited templates and expose `regulatory_anchors`.
- No scope-gate integration test proves the added YAML key is ignored safely by protocol construction.
- No sweep-wiring test proves `run_honest_sweep_r3.py` behaves when a template has zero anchors.
- No guard test enforces the "no agency strings in regulatory_expander.py" requirement, which is currently violated by comments/docstring text.
- No test covers query budget behavior or confirms anchors are capped/reserved under full-scale settings.

Manual checks showed the edited YAML templates load successfully and `tech` with zero anchors emits zero regulatory queries, but this should be automated before relying on it over repeated sweeps.

## 9. Template YAML Hygiene

Verdict: **PASS**

The three edited templates parse as dicts and expose the expected top-level `regulatory_anchors` lists:

- `config/scope_templates/clinical.yaml:115-122`
- `config/scope_templates/policy.yaml:82-90`
- `config/scope_templates/due_diligence.yaml:84-90`

A duplicate-key check across `config/scope_templates/*.yaml` passed. `load_scope_template()` also uses `yaml.safe_load()` and returns the parsed dict at `src/polaris_graph/nodes/scope_gate.py:211-218`; scope-gate protocol construction reads known fields and does not consume or reject unknown keys.

## 10. Regression Against V17 TOP-TIER Baseline

Verdict: **PASS WITH COST CAVEAT**

M-28 is retrieval-side and additive. It does not alter selector tier logic, outline planning, corpus approval thresholds, or the V17 topic-diversity signal that M-26a damaged. The primary behavioral blast radius is more retrieval calls and potentially more candidate URLs, with URL dedupe before fetch at `src/polaris_graph/retrieval/live_retriever.py:939-950`.

The main regression risk is budget/noise, not outline structure: anchor queries can add regulatory documents and consume Serper/S2 calls. This should not reproduce the M-26a selector regression, but the cost cap issue in section 6 should be fixed or explicitly accepted before full-scale V18.

## Final Verdict

M-28 may not proceed to V18 sweep.
