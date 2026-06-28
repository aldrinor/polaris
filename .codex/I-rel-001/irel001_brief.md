HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Reserve P0/P1 for real execution risks; classify minor issues P2/P3.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on remaining-non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

REVIEW MODE: STATIC only. Do NOT run pytest / pipeline / broad exploration. Read the diff `.codex/I-rel-001/irel001_diff.patch` and the changed handler in scripts/run_honest_sweep_r3.py (the `except ReleaseInvariantError` block, search "I-rel-001") + the test. Emit the verdict schema at the end.

# I-rel-001 (#1341) — A18 four_role_held reconcile. HIGH CARE — FAITHFULNESS BOUNDARY.

## Problem
On a real paid run, status ended `abort_four_role_release_held`: the A18 release-invariant handler in run_honest_sweep_r3.py UNCONDITIONALLY held the report when D8 didn't adjudicate (adjudicated=False). The cause was a JUDGE TRANSPORT failure (entailment/D8 malformed-JSON / 404), NOT fabrication. This conflicts with the operator lock (always-release-with-labels: the verifier NEVER holds; weak/unadjudicated findings ship LABELED). Full analysis: .codex/I-rel-001/irel001_investigation.md.

## The change (the ONLY diff — handler reroute; release_policy.py UNCHANGED)
The `except ReleaseInvariantError` handler now, BEFORE the legacy unconditional hold, attempts a reroute gated STRICTLY:
- `_a18_always_release_enabled()` AND status was release-asserting AND run_dir is not None AND NOT `_final_outcome.hard_block` AND NOT `_final_outcome.body_withheld`.
Inside the gate it calls `build_seam_release_outcome(sections=multi.sections, evidence_for_gen=evidence_for_gen, is_clinical=_clinical_verified_only_surface, seam_held_reason="d8_unadjudicated_release_invariant", coverage_fraction=...)` — the SAME standalone fabrication screen the seam path uses — and then:
- **SCREEN CLEAN (`not body_withheld`)**: RELEASE with the 'D8-unadjudicated / weak' label. status=released_with_disclosed_gaps, release_allowed=True, serialize release_disclosure (adjudicated=False, body_withheld=False, compensating_screen_passed=True + the four_role_seam_unadjudicated gap) so a RE-RUN of assert_release_invariant PASSES via seam_rescue_proven. report.md is the already-strict_verify'd span-grounded body → NOT overwritten.
- **SCREEN WITHHOLD (body_withheld True — fabricated identity)**: keep the fail-closed hold (four_role_held, release_allowed=False) AND overwrite report.md with the degraded build_finalizer_artifact_body body, preserving the raw as report_unredacted.md (mirrors the seam withhold path). On overwrite failure → keep the hold + disclose the leak risk.
- **SCREEN COULD NOT RUN (exception)**: fall through to the legacy unconditional hold (no un-screened release).
- `if not _a18_rerouted:` keeps the EXISTING legacy A18 hold BYTE-IDENTICAL for every non-reroute shape (always-release OFF, non-release status, hard_block, already-withheld, screen-error).

## THE LINE NOT TO CROSS (verify hardest)
Releasing-with-label may ONLY happen when build_seam_release_outcome returns body_withheld=False (the fabrication screen ran AND found no out-of-evidence-pool citation identity). strict_verify does NOT check citation identity, so this screen is the ONLY thing between "unadjudicated" and "shipped a fabricated citation as fact." Confirm:
1. There is NO path where an un-screened body reaches report.md under a released status. (Clean branch ships report.md only because it is already the strict_verify'd body; withhold branch overwrites it.)
2. release_policy.py `assert_release_invariant` is UNCHANGED — the reroute is in the handler UPSTREAM of the raise; the invariant itself is not loosened.
3. No strict_verify / NLI / span / provenance / per-claim 4-role change.

## Validation (offline; I ran it — you do NOT need to)
- New tests (test_irel001_unadjudicated_release.py): 6 pass — unadjudicated+clean→released_with_disclosed_gaps + passes re-assert; fabricated-identity→withheld+report.md overwritten; existing test_invariant_a18_success_without_d8_is_a_violation stays GREEN.
- Regression: test_iarch007_regression.py + test_release_invariant_iarch007.py = 53 pass (incl. seam-fabricated-identity-withholds-body, real-drb90-held-manifest).

## Things to verify (be adversarial)
1. CAN FABRICATION SHIP? Trace every branch. Is ship strictly gated on body_withheld==False? Any exception/edge that releases an un-screened body?
2. Is the withhold branch's report.md overwrite + report_unredacted.md preservation correct, and does the overwrite-FAILURE path stay fail-closed?
3. Is the legacy hold truly byte-identical for the non-reroute shapes (hard_block, already-withheld, always-release-OFF, non-release status)?
4. Does serializing adjudicated=False + compensating_screen_passed=True correctly make seam_rescue_proven pass on re-assert WITHOUT loosening the invariant for a genuinely-unproven release?

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
