---
audit_type: code_review_pre_sweep_pass3
fix: M-28 Fix #1 (regulatory-anchor retrieval)
commit_range: pass2-followup..HEAD
verdict: READY
blockers: 0
mediums: 0
regression_introduced: no
---

## 1. No Hard-Coded Agency/Domain/Clinical Terms In Python

Verdict: **PASS**

`src/polaris_graph/retrieval/regulatory_expander.py` no longer contains the pass-2 blocker text. The docstring now says:

- `Every domain supported by the scope_templates/ directory uses the same expander code.`

Forbidden-term scan for `fda|ema|sec\.gov|epa|clinical|tirzepatide|surpass|diabetes` returned zero matches with `rg -n -i`. The requested Git Bash `grep -iE ...` executable could not run in this sandbox because it failed to create its signal pipe with Win32 error 5; the equivalent regex scan was clean.

## 2. Guard Test Catches `clinical`

Verdict: **PASS**

`TestNoHardCodedHostsInModule` now includes `"clinical"` in its banned-substring list.

Mutation check:

- Temporarily changed the module docstring to include `clinical`.
- Ran `$env:PYTHONPATH='src'; python -m pytest tests/polaris_graph/test_m28_regulatory_expander.py::TestNoHardCodedHostsInModule -q`.
- The test failed as expected with leaks `['clinical']`.
- Reverted the temporary edit.
- Re-ran the same guard test; it passed.

`git diff -- src/polaris_graph/retrieval/regulatory_expander.py tests/polaris_graph/test_m28_regulatory_expander.py` showed no remaining diff after the revert.

## 3. Full `tests/polaris_graph/` Regression

Verdict: **PASS FOR M-28; ENV-LIMITED FULL SUITE**

Command form used on PowerShell:

- `$env:PYTHONPATH='src'; python -m pytest tests/polaris_graph/ -q`

Result:

- Collected 699 tests.
- M-28 test file reached 31/31 passing during the full run.
- Overall run ended `674 passed, 2 failed, 23 errors`.
- All failures/errors observed were Windows temp-directory permission failures, first under `C:\Users\msn\AppData\Local\Temp\pytest-of-msn`, then again under an audit-local `--basetemp`. The rerun also failed during pytest temp cleanup with `PermissionError`.

This matches the pass-2 environment limitation class and does not identify an M-28 code regression.

## 4. Generalization Safety

Verdict: **PASS**

The expander remains template-driven. No concrete agency, host, jurisdiction, or domain-specific vocabulary is present in the module.

## 5. Anchor-List Robustness

Verdict: **PASS**

The existing tests continue to cover missing, empty, malformed, invalid URL-like, whitespace-containing, duplicate, and non-string anchor entries.

## 6. Serper `site:` Operator Correctness

Verdict: **PASS**

Query emission remains `{question} site:{anchor}`.

## 7. Scope-Validator Interaction

Verdict: **PASS**

No change was made to validator interaction. Anchor-expanded queries still preserve the base question text before the `site:` operator.

## 8. Cost / Cap Enforcement

Verdict: **PASS**

The cap remains enforced through `PG_SWEEP_MAX_REGULATORY_ANCHORS`, read at call time, after anchor normalization and dedupe.

## 9. Template YAML Hygiene

Verdict: **PASS**

No Python hard-coding was reintroduced; concrete anchors remain in YAML templates and tests.

## 10. Regression Against V17 TOP-TIER Baseline

Verdict: **PASS**

No M-28 blocker or medium finding remains. The only unresolved observation is the host/sandbox temp-directory permission issue preventing this environment from producing a clean 699-pass full-suite summary.

## Final Verdict

M-28 Fix #1 is **READY** for V18 from the code-audit perspective.
