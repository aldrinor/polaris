# Stage-0 lineage seam — Fable RE-GATE #2 verdict (post zero-grounding/scope-leak fix)

## Verdict: GO

My prior blocking finding (zero-grounding release via the coverage downgrade) is FIXED, the
scope leak is FIXED, and I found no new bug introduced by the helper/caller/tests. I re-ran the
suites myself: **37/37 pass** (`/home/polaris/conda_cu128/bin/python -m pytest tests/dr_benchmark/
test_stage0_lineage_seam.py test_stage0_lineage_sweep_integration.py` — 1.32s). Frozen-module
diff: **0 lines**. GHOST grep on ADDED lines: **0 hits** (4 pre-existing context hits on the full
diff, all non-proposing — same 4 as last round).

## 1. Zero-grounding fix (FIX A) — PASS, traced end-to-end

- New pure helper `_legacy_coverage_downgrade_applies` (`run_honest_sweep_r3.py:1937-1993`)
  refuses on ANY hard block: `if release_hard_block or (release_hard_block_reasons or []):
  return False` — exactly the guard I required (`release_hard_block` True OR
  `hard_block_reasons` non-empty).
- Caller at the outer disposition (`:19681-19701`) passes the REAL outcome fields:
  `bool(getattr(_release_outcome, "hard_block", False))` +
  `list(getattr(_release_outcome, "hard_block_reasons", []) or [])`, where `_release_outcome =
  getattr(four_role_result, "release_outcome", None)` (`:19619`) — fetched UNCONDITIONALLY, so
  the guard sees the outcome on BOTH the always-release ON and OFF paths.
- Trace against release_policy.py: ON-path zero-grounding → `ReleaseOutcome(released=False,
  hard_block=True, hard_block_reasons=["zero_grounding"], status=abort_no_verified_sections)`
  (`release_policy.py:584-608`) → helper returns False → NO downgrade, no contradictory
  manifest. OFF-path zero-grounding (the analogous hole I flagged) → `hard_block = not
  release_allowed and legacy_hard_block` with `legacy_hard_reasons=["zero_grounding"]`
  (`:560-576`) → helper returns False. Fabricated-with-redaction-off hard block likewise
  refused on both paths (also caught by the latch param — double-protected).
- Both `FourRoleEvaluationResult` constructors always set a non-None `release_outcome`
  (`sweep_integration.py:1114-1133`; seam `run_honest_sweep_r3.py:19568-19602`), so the
  getattr-None fallback is unreachable in production.

## 2. Scope leak fix (FIX B) — PASS

- Helper gates on `resolve_lineage(question_lineage) != LINEAGE_LEGACY_RACE_TASK → False`;
  the caller passes the PER-QUERY marker `q.get("question_lineage")` (`:19682`), never
  `lineage_from_env()`. Confirmed `resolve_lineage(None)` returns the default WITHOUT consulting
  env (`gate0_lineage.py:64-77` — env is only read by the separate `lineage_from_env`).
- So a non-legacy-bound query with the global selector ON → marker absent → default → False →
  no downgrade. Locked by
  `test_disposition_non_legacy_marked_query_with_selector_set_does_not_downgrade` (selector set
  via monkeypatch, marker None, asserts abort status preserved).

## 3. Terminals never downgrade — PASS

- Fabrication latch: explicit predicate param + hard_block (redaction-off) — both refuse.
- S0-must-cover / pending-rewrite: extra held_reasons break set-EQUALITY in
  `_legacy_coverage_shortfall_report_only` (unchanged, still pure).
- Insufficient-safety terminal: `released=True`, `status=released_insufficient_safety_evidence`
  (`release_policy.py:622-632`) → refused by the `release_released` guard; test asserts the
  label is PRESERVED, not overwritten.
- Already-released (success / disclosed-gaps): `release_released or summary_status in
  ("four_role_released", released_with_disclosed_gaps)` → refused.
- Seam-unadjudicated: `held_reasons=[_seam_held_reason]` ("seam_timeout"/"seam_error:*",
  `:19590`) can never equal `{d8_unsupported_residual_below_coverage}` → set-equality refuses;
  and the seam outcome's released=True cases are refused by the released guard.

## 4. Disposition test quality (FIX C) — PASS (genuinely behavioral)

- `_native_outcome` builds outcomes via the REAL `compute_release_outcome` with a real
  `ReleaseDecision` — no stubbed hard_block/status fields. The zero-grounding case asserts
  `outcome.hard_block is True` and `"zero_grounding" in hard_block_reasons` before driving the
  disposition, so the test would have caught the original bug (a predicate-only test could not).
- `_seam_disposition` runs the PRODUCTION `_legacy_coverage_downgrade_applies` with the exact
  argument shapes the caller uses; covers (i) default blocks, (ii) marked-legacy coverage-only
  downgrade WITH telemetry preservation (coverage_fraction + held_reasons asserted exact),
  (iii) fabrication/S0/rewrite/zero-grounding/safety never downgrade, (iv) the scope leak.
- Honest residual (non-blocking): the 4-line manifest MUTATION in `_seam_disposition` is a
  verbatim replay, not the production block itself — a drift in the production mutation lines
  (not the decision) would not be caught. The decision logic, which is where both bugs lived,
  IS the shared production helper. Same class as my prior test-strength caveat, materially
  improved. Also inert: the test derives summary_status from `outcome.status` where the OFF
  path uses "four_role_held" — the helper keys on `release_released`, so no behavioral gap.

## 5. FIX D (resume helper) + FIX E (drb_90) — PASS

- `_resume_effective_lineage` (`run_honest_sweep_r3.py:1996-2013`) is the ONE production
  resolution; the resume caller (`:9649-9664`) passes `expected_lineage=_resume_effective_lineage(q)`
  and the tests drive the SAME helper (`test_stage0_lineage_seam.py:315-373`) — a regression to
  bare `q.get(...)` now breaks `test_resume_seam_default_run_rejects_stored_legacy` (the exact
  direction Sol flagged). Bogus-marker fail-loud also locked.
- FIX E: `test_no_gold_drb_90_adas_liability_fails_loud_under_legacy` locks registration-passes
  BUT legacy-support-rejects AND legacy-canonical-resolution-rejects for drb_90. Matches Sol's §1
  hardening note.

## 6. Default byte-identity + GHOST — PASS

- Default path through the new block: marker absent → `resolve_lineage(None)`=drb_ii_idx →
  helper returns False at its FIRST check — no manifest key, no status change, no artifact byte.
  The only default-path execution additions are two idempotent imports + one pure call. All
  prior default-identity findings (manifest shape, snapshot no-key, forced flag, required
  tuple, scorer early-return) are untouched by FIX A-E.
- GHOST: frozen-module diff 0 lines; exact GHOST_BAN regex on ADDED lines = 0 hits; full-diff
  hits = the same 4 pre-existing non-proposing context lines as re-gate #1. Structural (a)-(e)
  unchanged-PASS: the guard only NARROWS when a severity relabel may occur (strictly safer),
  reads no content, imports no frozen module, tests live under tests/ with no generation-path
  reader, no new carrier types.

## 7. New-bug hunt on the fixes themselves — CLEAN

- Helper raises `GateZeroLineageError` on a corrupt/unknown marker — fail-loud by design, only
  the gate itself ever stamps the marker.
- Downgrade runs BEFORE `unified_status = to_unified_status(summary_status)` (`:19702-19706`)
  — ordering correct; "released_with_disclosed_gaps" is a pre-existing legal status shape (the
  always-release ON path already emits it through the same downstream).
- Telemetry block (`manifest["four_role_evaluation"]`, `:19713-19732`) still written AFTER the
  downgrade with untouched `four_role_result` fields — honest release_allowed=False telemetry
  preserved alongside the downgraded binding decision.
- Carried-over cosmetics (unchanged, non-blocking): top-level `manifest["disclosed_gaps"]` key
  vs `release_disclosure.disclosed_gaps`; the fetch-checkpoint carries no lineage stamp
  (question-SHA guard covers task-72; follow-up candidate).

## Operator's independent claims — CONFIRMED
37/37 pass (re-ran), frozen diff 0, ghost grep 0 on added lines, helper docstring/signature
match the required FIX A/B logic.

## Single most important remaining risk
The re-baseline itself: the legitimate legacy coverage-only downgrade path (and the marker
plumbing through a real resume) has now been proven by tests but never by a live legacy run —
first live run should have its manifest spot-checked for
`legacy_coverage_shortfall_report_only` consistency with `release_disclosure.hard_block=False`.
