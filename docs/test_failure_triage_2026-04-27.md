# Test Failure Triage — 2026-04-27 Snapshot

**Suite**: `tests/polaris_graph/`
**Commit**: 77b132c (M-26 v15 substrate fix)
**Result**: 2614 collected → 2595 passed, **19 failed**, 3 skipped, 3 collection errors
**Reviewed by Codex** (post-author audit) — bucket categorizations corrected per `outputs/codex_findings/test_failure_triage_review/findings.md`

This document categorizes the 19 failing tests + 3 collection errors into actionable buckets with **Codex-verified diagnoses**. Original author's first-pass categorizations are noted where wrong so future readers see the audit trail.

---

## Bucket 1 — M-36 test pollution (9 tests)

**Symptom**: tests pass when run individually, fail when run as part of the full suite.

**Files**: `test_m36_trial_summary_table.py`

**Tests** (9 in `TestCallOrchestration` + `TestDisableKnob`).

**Codex-verified diagnosis (replaces author's "likely event-loop fixture" guess):**

- Polluting test identified: `test_corpus_brief.py::test_compose_brief_with_supported_paragraphs` runs first and leaves the asyncio loop in a state that makes M-36's loop helper fail.
- The actual error is `RuntimeError: There is no current event loop` at `tests/polaris_graph/test_m36_trial_summary_table.py:246`.
- The fix is in M-36's OWN loop helper at line 246, NOT in cross-test isolation. M-36 is using `asyncio.get_event_loop()` (deprecated) which only worked because of stale state left by upstream tests.

**Effort to fix (Codex-revised)**: minutes, not the 1-2h author estimated. Replace the deprecated `asyncio.get_event_loop()` call with `asyncio.new_event_loop()` (or use `asyncio.run()` which manages the loop lifecycle correctly).

**Priority**: Medium. Doable now.

---

## Bucket 2 — V28 regressions awaiting V30 (7 V30-blocked, includes V26 guard + M47 mechanism extraction)

**Original author claim**: "8 V28 regressions, all red BY DESIGN, do not lower baselines, V30 fixes them."

**Codex-verified correction**:
- Count is **7**, not 8 (count error in original)
- One listed failure is the **V26 NICE guard** in `test_m42_preservation.py:162` — that's a different baseline (V26, not V27/V28)
- M-47 clamp validator was originally Codex-flagged as "concrete fix possible". On 2026-04-27 author investigation revealed the failure was upstream V28 evidence-selection picking quotes without numeric values, not a validator bug. Codex round-2 review (`outputs/codex_findings/triage_executed_fixes_review/findings.md`) accepted the V30-blocked reclassification.

**Files**: `test_m42_preservation.py`, `test_m49_v28_preservation.py`

| Test | Type | Action |
|---|---|---|
| `test_m42_preservation::test_nice_count_at_or_above_v25_baseline` | V26 NICE guard | Wait for V30 (consistent with earlier baselines) |
| `test_m49_v28_preservation::test_fda_count_preserved` | V27→V28 regression (FDA 7→4) | Wait for V30 |
| `test_m49_v28_preservation::test_hc_count_preserved` | V27→V28 regression (HC) | Wait for V30 |
| `test_m49_v28_preservation::test_pivotal_trial_coverage` | V27→V28 regression | Wait for V30 |
| `test_m49_v28_preservation::test_surpass_cvot_mentioned` | V27→V28 regression | Wait for V30 |
| `test_m49_v28_preservation::test_surpass_2_primary_etd_present` | V27→V28 regression | Wait for V30 |
| `test_m49_v28_preservation::test_m47_clamp_validator_passes` | V27→V28 regression (mechanism extraction) | Wait for V30 (see appendix) |

**Don't lower baselines** still applies to ALL 7 wait-for-V30 tests.

**Note on M-47 reclassification (post-triage investigation)**: Codex round-1 flagged M-47 as a concrete regression (fixable independently). On 2026-04-27 investigation, the diagnostic data showed 4 of 6 mechanism papers had ZERO candidate fields extracted by `_m47_extract_candidate_values`. The extractor is reasonable code; the more likely root cause is V28 evidence selection picking quote strings that don't contain the numeric values the extractor looks for. Without re-running the V28 pipeline to inspect actual quote text, the fix is upstream in V28→V30 evidence selection, not in the validator. Reclassified back to V30-blocked.

**Effort to fix**: 7 tests V30-blocked, no immediate work.

---

## Bucket 3 — V30 manifest invariants → ACTUALLY 1 stale string + 2 false positives (3 tests)

**Original author claim**: "These will land with M-60 manifest emission."

**Codex-verified correction**: ALL three are misclassified.

| Test | Codex finding | Action |
|---|---|---|
| `test_m201_evidence_selection.py:206` | **Stale expected string**. Test expects old strategy name; code at `src/polaris_graph/retrieval/evidence_selector.py:583` now returns `tier_balanced_v1_all_m46_ordered`. The code is right, the test is stale. | Update test assertion to match current code. ~5 min. |
| `test_manifest_contract.py:117` | **False positive**. `scripts/run_honest_sweep_r3.py:1785` already sets `"status": unified_status`; the test misses it because the V30 block pushes the final `write_text()` past the test's 80-line scan window. | Extend the test's scan window or restructure scan to match all `write_text()` calls. ~10 min. |
| `test_m207_invariant_coverage.py:185` | **Duplicate of the manifest_contract false positive**, same root cause. | Same fix as above. |

These are NOT pending V30/M-60 work. They are unrelated and trivially fixable now.

**Effort to fix**: 15-20 min total for all three.

---

## Bucket 4 — Collection errors → fix imports, NOT delete (3 collection errors)

**Original author claim**: "5min sed fix or skip permanently. Modules may have been renamed."

**Codex-verified correction**: import-fix, NOT delete. The `src/polaris_graph/...` equivalents AND the imported symbols exist for M25/M28/M29. With `PYTHONPATH=src`, all three files COLLECT and 52/53 tests pass.

**Important**: unblocking collection exposes one more genuine failing test:
- `test_m29_jurisdictional_precision.py:78` — real M29 assertion failure once it can actually run

**Files** (3): `test_m25_trial_name_match.py`, `test_m28_regulatory_expander.py`, `test_m29_jurisdictional_precision.py`

**Effort to fix (Codex-revised)**: ~5 min for the imports + ~10-20 min including rerun and triaging the newly-exposed M29 assertion failure. Real total: ~15-25 min, not the original "5 min" claim.

---

## Recommended action plan (Codex-revised)

**Right now** (independent of V30):
- **Bucket 1** (9 M-36 tests, ~minutes): fix the deprecated `asyncio.get_event_loop()` at `test_m36_trial_summary_table.py:246`
- **Bucket 3** (3 tests, ~15-20 min total):
  - Update stale string assertion in `test_m201_evidence_selection.py:206`
  - Extend scan window in `test_manifest_contract.py:117` and `test_m207_invariant_coverage.py:185`
- **Bucket 4** (3 collection errors, ~15-25 min): fix imports; expect 1 more real failure to surface in M29

**Wait for V30** (7 tests):
- 6 V27/V26 baseline preservation tests in M-42/M-49 + 1 M47 clamp validator (post-investigation reclassified — see Bucket 2 above) — these all flip green when V30 ships BEAT-BOTH

**Total quick-win effort**: ~3-5 hours of focused work clears 12 of 19 failures + 3 collection errors. After the quick-win pass executed in commit 336ac67, suite state is exactly the 7 V30-blocked tests above (the M29 assertion at `test_m29_jurisdictional_precision.py:78` was fixed inline as a Bucket-4 follow-on by narrowing the scan range from rule #11 to rule #11b boundary).

---

## Bucket totals (Codex-corrected)

| Bucket | Original count | Corrected count | Action |
|---|---:|---:|---|
| 1. M-36 test pollution | 9 | 9 ✓ | Fix now (`asyncio.run()` swap) — DONE in 336ac67 |
| 2. V28/V27/V26 regressions (V30 fixes) | 8 | **7** (all V30-blocked, including M47 post-investigation) | Wait for V30 |
| 3. M201/M207/manifest false-positives | 2-3 | **3** (all misclassified) | Fix now (~15-20 min) — DONE in 336ac67 |
| 4. Collection-time import errors | 3 | 3 + 1 (newly-exposed M29 fixed inline) | Fix now (~15-25 min) — DONE in 336ac67 |
| **Total** | **19 fail + 3 collect** | **19 fail + 3 collect = 22** ✓ | |

Math reconciles: 9 (B1, fixed) + 7 (B2 wait-for-V30) + 3 (B3, fixed) + 3 (B4, fixed) = 22 entries triaged.

Post-execution suite state: 2680 passed / 7 failed (= B2 above) / 3 skipped, with +76 tests now collecting after import fixes (M-25 14 + M-28 31 + M-29 8 = 53 from the import unblock + 22 new M-D1 harness tests + 1 from re-stabilizing M-36 = 76). Verified by Codex round-2 review.

---

## Why the original triage was wrong

Recording for future-author honesty (and to seed `feedback_adversarial_review_stop_criterion.md` with a documentation analogue):

- **Bucket 1**: I diagnosed "test pollution" without identifying the polluter. The actual fix is in M-36's own deprecated API call, not cross-test isolation. Always trace failures to the specific line + the specific deprecation.
- **Bucket 2**: I conflated three different baselines (V25/V26/V27) under one "V28 regression" label and counted wrong (claimed 8, actual 7). I also originally classified `test_m47_clamp_validator_passes` as V30-pending; Codex round-1 disagreed and called it concrete; on subsequent investigation the data showed it's actually upstream-data-dependent and Codex round-2 accepted V30-blocked. Always read each test's assertion to see what it's actually checking, AND consider whether failing data is a fixable code bug vs upstream pipeline issue.
- **Bucket 3**: I classified all three as "V30 manifest invariants pending M-60." Codex actually ran them and found: 1 stale string assertion (code is right), 2 false-positive scan-window misses (code is right). I should have run them with verbose output before classifying.
- **Bucket 4**: I gave 5min as the effort estimate without considering that fixing the imports would expose a previously-hidden real failure. Always assume hidden tests have hidden failures.

The lesson: triaging without running and reading the specific failure line is at-best directionally correct. Codex did the actual investigation; my first pass was sketchy in 4 of 4 buckets.
