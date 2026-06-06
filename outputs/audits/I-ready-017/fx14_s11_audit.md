# FX-14 §-1.1 audit — custody-lane not_applicable marker (#1129)

**Standard:** §-1.1 over the REAL held drb_72 `run_artifacts/evidence_pool.json` (the in-memory pool
that reached the generator). The marker's `primary_trial_doi_seed_rows` count MUST EQUAL the raw count
of `query_origin=='primary_trial_doi_seed'` rows; the marker fires only when seeds reached generation
but the custody block did not run; the existing custody files stay byte-identical.

## The bug (firing-status-lie / §-1.1 anti-pattern)
`v29_primary_custody.json=[]` and `m44_primary_citation_telemetry.json={injection_log:[],
validator_violations:[]}` even when primary-trial DOI seeds reached generation. The M-44/M-52/V29
custody+injection block is gated on `if primary_trial_anchors:` (`multi_section_generator.py:4610`); in
the planner lane `_primary_anchors` is empty, so the block is skipped and both files are written
silently empty (`run_honest_sweep_r3.py:4331-4380`). An empty diagnostic that cannot be disambiguated
(no-activity vs not-applicable vs broken) is the firing-status-lie §-1.1 forbids.

## The fix (path B — telemetry-only; Codex plan-gate Q9 = retire-the-silence honestly)
- New pure decision helper `compute_custody_lane_status()` (next to `compute_run_health_gate`): returns
  a `not_applicable_planner_lane` marker ONLY when the flag is on AND >=1 `primary_trial_doi_seed` row
  is in `evidence_for_gen` AND both custody logs are empty; else `None`.
- Call site writes a SEPARATE `custody_lane_status.json` when the helper returns a marker. The two
  existing custody files are UNCHANGED (their dict/list contracts — asserted by m49/m53 tests — are
  preserved; a marker element in the v29 LIST would be misread by the m53 test as a failed anchor, so
  a companion file is the type-safe disambiguation).
- multi_section_generator.py UNCHANGED — ZERO generator behavior change (path A, which re-enables the
  injection block in the dormant lane, was REJECTED as faithfulness-adjacent; briefed to Codex).
- Flag-gated `PG_CUSTODY_LANE_MARKER` (default OFF → no file written → byte-identical); Gate-B slate
  forces it ON + the preflight requires it (so an explicit `=0` cannot survive the setdefault — the
  I-cap-005 P1-1 pattern).

## §-1.1 — count EQUALS the raw evidence_pool tally on the REAL held artifact
Held drb_72 `evidence_pool.json` = 21 rows; `query_origin` is a varying key present only on seed rows;
rows 19 & 20 carry `query_origin=='primary_trial_doi_seed'` → raw count = **2**.
`compute_custody_lane_status(<held rows>, m44_injection_empty=True, custody_log_empty=True,
marker_on=True)` returns a marker with `primary_trial_doi_seed_rows == 2` — EXACT match
(`test_held_drb72_count_is_2`). The held m44/v29 telemetry were indeed empty, so on a fresh planner-lane
run with the flag ON the marker WOULD fire here, replacing the silent empty with an explicit
not_applicable status. The agentic-seed and unlabeled rows are correctly NOT counted (only the 2 honest
primary-trial DOI seeds — the post-FX-15a label).

**Forensic-number correction:** the campaign forensic said "16+ primary_trial_doi_seed rows"; the real
artifact has 2. The 16 predated FX-15a (which mislabeled agentic seeds as primary_trial_doi); FX-15a
(verified) corrected the labels, so 2 is the honest count. §-1.1 on the real artifact caught the stale
number — exactly why this faithfulness-adjacent fix was authored against the real data.

## Offline smoke (proves the decision)
`pytest tests/polaris_graph/test_fx14_custody_lane_status_iready017.py` → 6 passed: marker when seeds
present + logs empty (counts only primary seeds, not agentic/plain); None when flag OFF (byte-identical);
None when no primary seeds (empty is honest); None when a custody log actually ran; non-dict rows
ignored (robust); held-drb72 count == 2.
Regression: m49 dict + m53 list custody-contract tests still pass (the two existing files unchanged);
the 6 m49 failures are PRE-EXISTING V28-fixture content drift (identical with FX-14 stashed). FL-05
sibling 8 + Gate-B slate/CLI 21 green.

## Faithfulness
Telemetry-only. No grounding / strict_verify / 4-role / generator change. The marker is DERIVED from
the evidence pool's own query_origin labels (cannot fabricate). It only ADDS a disambiguation file in a
previously-silent-empty case; no execution-path or existing-artifact change. No-silent-downgrade-aligned.
