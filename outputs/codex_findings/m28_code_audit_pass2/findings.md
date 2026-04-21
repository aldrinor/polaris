---
audit_type: code_review_pre_sweep_pass2
fix: M-28 Fix #1 (regulatory-anchor retrieval)
commit_range: previous-audit-commit..HEAD
verdict: NOT_READY
blockers: 1
mediums: 0
regression_introduced: no
---

## 1. No Hard-Coded Agency/Domain/Clinical Terms In Python

Verdict: **BLOCKER**

The prior agency/host examples are removed from `src/polaris_graph/retrieval/regulatory_expander.py`; a direct grep found no concrete agency names or host strings such as FDA/EMA/SEC/EPA/Federal Register/accessdata/etc. in that module.

However, the stricter pass-2 criterion was "zero agency names, jurisdictional terms, or clinical-domain vocabulary." The module still contains clinical-domain vocabulary in its design-invariant prose:

- `src/polaris_graph/retrieval/regulatory_expander.py:19` says `Clinical, policy, due-diligence, environmental, materials, etc. all use the same expander code.`

This is only docstring text, not runtime behavior, but the prior blocker was also about docstrings/comments and the pass-2 instruction is explicitly text-level. The guard test does not catch this because its banned clinical list includes disease/drug/study terms but not the word `clinical` itself. Therefore the zero clinical-domain vocabulary requirement is not genuinely closed.

Guard-test mutation check: temporarily adding `fda` to `regulatory_expander.py` made `TestNoHardCodedHostsInModule` fail with `['fda']`, then the edit was reverted. So the guard works for its current banned list, but the list is incomplete for the pass-2 wording.

## 2. Generalization Safety

Verdict: **PASS**

The expander still no-ops for missing, empty, malformed, or zero-anchor templates. The real `tech` template loads with no `regulatory_anchors` field and `expand_regulatory_queries("q", tmpl)` returns `[]`.

## 3. Anchor-List Robustness

Verdict: **PASS**

`_extract_anchors()` still rejects non-dicts, non-list `regulatory_anchors`, non-string entries, empty strings, entries containing `/`, and entries containing whitespace. It lowercases and dedupes while preserving declared order.

## 4. Serper `site:` Operator Correctness

Verdict: **PASS**

The emitted format remains `{question} site:{anchor}`.

## 5. Scope-Validator Interaction

Verdict: **PASS**

No follow-up edit changes the downstream validator path. Anchor queries retain the base question text before the `site:` operator, so the prior validation finding remains closed.

## 6. Cost / Cap Enforcement

Verdict: **PASS**

`PG_SWEEP_MAX_REGULATORY_ANCHORS` is read inside `_max_anchors()` on every `expand_regulatory_queries()` call, not cached at import. The cap is applied after `_extract_anchors()` has normalized, filtered, and deduped anchors. Manual probe: 15 raw entries with duplicates/invalid forms produced 10 valid deduped queries at cap 10, 3 at cap 3, and all 12 valid unique anchors when cap was disabled with `0`.

## 7. Duplicate Amplified Queries

Verdict: **PASS**

Anchor-level dedupe happens before query construction in `_extract_anchors()`. Downstream query and URL dedupe behavior is unchanged from pass 1.

## 8. Test Coverage Completeness

Verdict: **PASS WITH CAVEAT**

The new tests cover the previously missing guard, cap behavior, and YAML loading path. `TestYamlTemplateIntegration` imports `load_scope_template()` and loads real templates under `config/scope_templates/`; it does not mock the YAML data.

Caveat: the guard test reads the module file from disk via `Path(...).read_text()`, so bytecode cache cannot fool it, but its banned-term list should include `clinical` if the zero clinical-domain vocabulary requirement is meant literally.

Focused test runs:

- `python -m pytest tests/polaris_graph/test_m28_regulatory_expander.py -q --no-header`: 31 passed.
- `TestNoHardCodedHostsInModule`: passed before mutation; failed as expected when `fda` was temporarily inserted.
- `TestAnchorCountCap` + `TestYamlTemplateIntegration`: 10 passed.

## 9. Template YAML Hygiene

Verdict: **PASS**

Manual real-template load check:

- `clinical`: dict, 7 anchors, 7 emitted queries.
- `policy`: dict, 8 anchors, 8 emitted queries.
- `due_diligence`: dict, 6 anchors, 6 emitted queries.
- `tech`: dict, no anchors, 0 emitted queries.

## 10. Regression Against V17 TOP-TIER Baseline

Verdict: **PASS**

The follow-up edits are limited to `regulatory_expander.py` and `test_m28_regulatory_expander.py`. I did not find a new runtime regression in the M-28 path. The remaining failure is a text-level generalization requirement breach, not a behavioral regression.

## Test-Count Claim

Claude's count claim is correct at collection time: `PYTHONPATH=src python -m pytest tests/polaris_graph/ -q --no-header` collected 699 tests. In this sandbox, the full suite did not complete cleanly because tests using `tmp_path` / `tempfile.TemporaryDirectory()` hit Windows permission errors in temp directories; both attempts still showed all 31 M-28 tests passing before the suite summary. The observed summary was `674 passed, 2 failed, 23 errors`, with the failures/errors attributable to temp-directory `PermissionError`, not M-28 code.

## Final Verdict

M-28 may not proceed to V18 sweep.
