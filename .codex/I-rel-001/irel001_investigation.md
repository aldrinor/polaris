# I-rel-001 (#1341) — A18 four_role_held reconcile investigation. HIGH CARE (faithfulness boundary).

## ROOT CAUSE
`release_policy.py:853-859` — the final `raise ReleaseInvariantError` in `assert_release_invariant()` fires when a
release-asserting status (`success`) has adjudicated=False AND no proven seam rescue AND body not withheld.
The TRIP HANDLER is `scripts/run_honest_sweep_r3.py` `except ReleaseInvariantError` (now ~line 14660 after the
I-render-003 helper shifted line numbers; was ~14617). It converts the raise into an UNCONDITIONAL hold:
`summary_status="four_role_held"` → manifest.status=abort_four_role_release_held, release_allowed=False.

Mechanism: live run reached A18 with status='success' but reconstruct_release_outcome_from_manifest derived
adjudicated=False (no release_disclosure["adjudicated"] AND empty four_role_evaluation.final_verdicts) — i.e. D8
never bound, because the entailment/D8 JUDGE errored (malformed JSON / 404 / error_body_200), NOT fabrication.
Conflicts with operator lock feedback_always_release_verifier_labels_never_holds_2026_06_14 (verifier never holds;
always release, label weak/unadjudicated).

## DISTINCTION THE FIX MUST PRESERVE
- FABRICATION (never relax): a cited citation identity NOT in the evidence pool. strict_verify checks span content
  NOT citation identity, so ONLY the standalone fabrication screen in build_seam_release_outcome catches an invented
  identity → must stay fail-closed (withhold body).
- UNADJUDICATED / transport-failure (should RELEASE-with-label per the lock): D8 didn't bind because the judge was
  unreachable/errored; the body is strict_verify-clean span-grounded prose → ship with a 'D8-unadjudicated/weak' label.

## MINIMAL HIGH-CARE FIX — single locus, the except ReleaseInvariantError handler
release_policy.py itself does NOT change. In the handler, when always_release_enabled() AND the trip is the
unadjudicated case (NOT a real fabrication latch / zero-grounding hard block), route through the SAME screen the
seam path uses instead of the unconditional hold:
1. call `build_seam_release_outcome(sections=multi.sections, evidence_for_gen=evidence_for_gen,
   is_clinical=_clinical_verified_only_surface, seam_held_reason="d8_unadjudicated_release_invariant",
   coverage_fraction=<coverage>)` — args confirmed in scope at the handler (multi, evidence_for_gen,
   _clinical_verified_only_surface) identical to the existing seam call.
2. SCREEN CLEAN (body_withheld=False) → summary_status=_outcome.status (released_with_disclosed_gaps),
   release_allowed=True, serialize release_disclosure adjudicated=False/body_withheld=False/
   compensating_screen_passed=True + the four_role_seam_unadjudicated gap (the 'D8-unadjudicated/weak' label). A
   re-run of assert_release_invariant then PASSES via seam_rescue_proven (release_policy.py:841-846). report.md is
   already the strict_verify'd span-grounded body → SAFE to ship as-is.
3. FABRICATED IDENTITY OR screen can't run → keep TODAY's exact fail-closed hold (four_role_held,
   release_allowed=False) — byte-identical for the unsafe case.

## FAITHFULNESS-CRITICAL coupling (the line not to cross)
On the WITHHOLD branch you MUST overwrite report.md with the degraded build_finalizer_artifact_body body and
preserve the raw as report_unredacted.md, exactly as the seam path (run_honest_sweep ~13564-13582) and the B16/B17
path do — because in the unadjudicated case the on-disk report.md was NOT D8-reconciled and NOT identity-screened,
so a withhold that leaves the raw body on disk would ship un-screened content (the §-1.1 audit reads report.md, not
the manifest). The CLEAN→ship branch is safe because report.md is already the strict_verify'd body. Mirror the
seam's write-failure fail-closed.

## RISK (must not cross): releasing-with-label could ship fabricated content ONLY if the clean→ship branch skips the
fabrication screen. Gate ship on build_seam_release_outcome returning body_withheld=False (screen ran AND found no
out-of-pool identity). strict_verify does NOT check citation identity, so the screen is the ONLY thing between
"unadjudicated" and "shipped an invented citation as fact." Clean screen = safe to ship with the weak label;
anything else = keep the existing hold.

## Files ALSO checked, clean
sweep_integration.py (genuine-D8 path sets adjudicated=True, absorbs per-claim judge errors → not the A18 trip),
reconstruct_release_outcome_from_manifest (run script ~456-487, derivation honest — bug is the handler RESPONSE),
build_seam_release_outcome (release_policy ~4212-4357, the correct safe template, REUSED not modified),
b18_b19_disposition (_B18_B19_CONVERTIBLE_HOLDS correctly EXCLUDES abort_four_role_release_held — not the fix path),
is_hard_block/compute_release_outcome seam branch (fabrication + zero-grounding hard line intact).

## Faithfulness gates that MUST NOT CHANGE
strict_verify, NLI entailment, span-grounding, provenance, per-claim 4-role verdict — all OUT of scope. This is a
release-policy/disposition reconcile: it changes WHICH terminal status an already-screened outcome carries, never a
per-claim faithfulness verdict.

## Tests
tests/roles/test_release_invariant_iarch007.py (assert_release_invariant legs — keep green; ADD "unadjudicated
success → screened → released_with_disclosed_gaps passes re-assert"), tests/polaris_graph/test_iarch007_regression.py
:452 test_invariant_a18_success_without_d8_is_a_violation (stays GREEN — the new screened-rescue path lives in the
handler UPSTREAM of the raise; the invariant itself is NOT loosened), :380 fabricated-identity-withholds-body + :607
real-drb90-held-manifest (must preserve), tests/roles/test_seam_parallel.py, test_iperm001_release.py,
test_b11_b20_always_emit_lane_sweep.py.

## Separate follow-up (out of scope): if the live run reached A18 because D8 NEVER fired at all (misconfigured seam
producing empty final_verdicts), that is a D8-didn't-fire bug, not a release-policy bug.
