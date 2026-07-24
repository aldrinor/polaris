# SOL re-gate #2 — Stage-0 lineage seam

## Verdict

**GO-WITH-CHANGES.**

The production safety fix is correct: the zero-grounding release regression and the global-selector
scope leak are resolved, terminal statuses are preserved, default behavior remains unchanged, and no
new production bug was found. However, the claimed behavioral/caller regression coverage is still
incomplete: the disposition tests duplicate the inline production mutation in a test helper, and the
resume tests do not fail if `run_one_query` stops calling the production helper. Fix those test
couplings before committing and starting the re-baseline.

| Focused item | Result |
|---|---|
| 1. FIX A — hard blocks never downgrade | **PASS** |
| 2. FIX B — per-query marker, not global selector | **PASS** |
| 3. Released/safety/disclosed terminals retain identity | **PASS** |
| 4. FIX C — genuinely behavioral disposition test | **FAIL** |
| 5. FIX D — one helper and regression-to-`q.get` detection | **FAIL** |
| 6. New bugs / default identity / GHOST | **PASS** |

## 1. FIX A — PASS

`_legacy_coverage_downgrade_applies` returns `False` if either
`release_hard_block` is true or `release_hard_block_reasons` is non-empty:
`scripts/run_honest_sweep_r3.py:1978-1980`.

The outer disposition passes the real `ReleaseOutcome.released`, `hard_block`, and
`hard_block_reasons` fields before performing any manifest mutation:
`scripts/run_honest_sweep_r3.py:19681-19701`.

Read-only reproduction using the real `ReleaseDecision` and `compute_release_outcome`:

```text
ordinary               abort_four_role_release_held False False []                  -> downgrade=True
zero_grounding         abort_four_role_release_held False True  ['zero_grounding']  -> downgrade=False
hard=False, reasons!=[]                                                            -> downgrade=False
```

Therefore a zero-grounded result, or any outcome carrying either hard-block signal, no longer
reaches the release mutation.

## 2. FIX B — PASS

The outer caller supplies `q.get("question_lineage")`, and the helper resolves that marker through
`resolve_lineage`; it does not read `PG_BENCHMARK_QUESTION_LINEAGE`:
`scripts/run_honest_sweep_r3.py:1968-1977,19681-19688`.

With the global selector set to `legacy_race_task` but the current query marker absent, the real
helper returned `False`. Both absent and explicit `drb_ii_idx` markers returned `False`. The scope
leak is closed.

## 3. Terminal preservation — PASS

The helper rejects every already-released outcome before considering coverage:
`scripts/run_honest_sweep_r3.py:1981-1985`. Real release-policy outcomes confirmed:

```text
released_insufficient_safety_evidence  released=True -> downgrade=False
released_with_disclosed_gaps           released=True -> downgrade=False
```

Plain success is covered by the same `release_released` guard. The explicit disclosed-gaps status
guard is additional defense. No released, insufficient-safety, or disclosed-gaps terminal is
re-labelled.

## 4. FIX C — FAIL

The cases themselves are good and use real `compute_release_outcome` objects plus the real
`_legacy_coverage_downgrade_applies` decision helper. They cover:

- default coverage-only hold;
- marked-legacy coverage-only downgrade;
- preserved coverage fraction and held reasons;
- fabrication, S0-must-cover, pending rewrite, zero-grounding, and insufficient-safety refusal;
- selector-on with no per-query marker.

But the test does **not** execute the production manifest mutation. It defines
`_seam_disposition` in the test and duplicates the caller's status derivation, manifest writes,
disclosed-gap append, marker write, and telemetry write:
`tests/dr_benchmark/test_stage0_lineage_seam.py:478-508`. The assertions at `:511-623` exercise
that test-side copy.

Consequently, a regression in the real caller at
`scripts/run_honest_sweep_r3.py:19681-19717`—wrong helper argument, omitted
`manifest["release_allowed"]`, incorrect terminal assignment, or lost telemetry—can leave every new
test green. This is the same mirror-of-caller false-confidence class identified in the prior gate.

**Residual fix:** extract the actual mutation into one production helper (for example, an
`_apply_legacy_coverage_downgrade` that owns the helper call, manifest mutation, and returned status)
and call that helper from both `run_one_query` and the tests, or exercise `run_one_query` at this seam
with a hermetic integration harness. Do not keep the mutation replay in the test.

## 5. FIX D — FAIL

The implementation half is correct:

- `_resume_effective_lineage` is one production helper:
  `scripts/run_honest_sweep_r3.py:1994-2008`.
- `run_one_query` calls it when loading the post-selection snapshot:
  `scripts/run_honest_sweep_r3.py:9658-9661`.
- tests call the same helper and correctly cover both mismatch directions and both matching
  directions: `tests/dr_benchmark/test_stage0_lineage_seam.py:315-373`.

But the stated regression property does not hold. The tests invoke the helper and loader directly;
they do not execute or inspect the `run_one_query` call site. If `run_one_query` regresses from
`expected_lineage=_resume_effective_lineage(q)` to `expected_lineage=q.get("question_lineage")`
while the helper remains, all of `:323-373` still pass.

**Residual fix:** add a caller-coupling test that exercises the real resume branch, or at minimum a
focused structural assertion that the `run_one_query` snapshot load supplies
`_resume_effective_lineage(q)`. The behavioral option is preferred.

## 6. No new production bug / default identity / GHOST — PASS

- The production helper is pure and conservative: default absent/explicit `drb_ii_idx` markers both
  return `False`; no default manifest/status mutation occurs.
- The no-gold `drb_90_adas_liability` case is now explicitly locked at
  `tests/dr_benchmark/test_stage0_lineage_seam.py:629-642`.
- Focused suite: **30/30 passed**.
- Additional Stage-0 integration and release-invariant checks passed. A broader bundle reported
  **33 passed, 2 failed** only because the unrelated saved-run fixture
  `outputs/audits/beatboth8/drb_76` is absent.
- Both changed files parse successfully; whitespace checks are clean.
- GHOST regex over `git diff -- scripts src` produced four explanatory/exclusion hits only
  (`binding by idx`, existing fail-closed relevance behavior, explicit “NO faithfulness gate”
  wording, and “NO binding”); none introduces admission, entailment, NLI, premise licensing, or
  post-generation content rewriting.
- Frozen-module diff is empty for:
  - `src/polaris_graph/generator/provenance_generator.py`
  - `src/polaris_graph/clinical_generator/strict_verify.py`

## Single most important remaining risk

**False-green regression coverage:** both new seam test harnesses can remain green after their
respective inline `run_one_query` callers stop using the correct production behavior. There is no
remaining production safety blocker in the reviewed diff, but this test-coupling gap should be fixed
before commit and re-baseline.
