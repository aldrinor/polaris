HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex DIFF review — I-perm-000 activation: wire the READY permanent-fix flags into the Gate-B slate — ITER 1 of 5

You are the ONLY gate. Review `.codex/I-perm-activation/codex_diff.patch` (scripts/dr_benchmark/run_gate_b.py only).

## Why
The permanent-fix flags are DEFAULT OFF (byte-identical) and INERT in production unless the run slate sets them — the exact "fix built but not live, issue reappears next run" trap the operator flagged. This activates the two READY fixes through the established triple-lock (slate setdefault + `_BENCHMARK_FORCE_ON_FLAGS` override + `_BENCHMARK_PREFLIGHT_REQUIRED_FLAGS` fail-closed), matching the pattern used by PG_SWEEP_WEIGHTED_CORPUS_GATE / PG_GATE_B_CITED_SPAN / etc.

## What
- ADD `PG_ALWAYS_RELEASE=1` (#1195 keystone: WITHHOLD->ALWAYS-RELEASE+LABEL) and `PG_SWEEP_NUMERIC_SANITIZER=1` (#1201: drop DOI/URL/accession cruft) to the slate + force-on + required-flags.
- DELIBERATELY NOT activated: `PG_SWEEP_SELECTION_SCALE` (#1197) — the blueprint keeps it flag-OFF until I-perm-007 grows a real pool; I verified that activating it now scales the selection budget ABOVE the #1070/#1078 evidence-to-generation cap (5->12) and breaks `test_capped_finding_dedup_selection_respects_cap`. So leaving it off is correct, not an omission.

## CLAIMS LEDGER (verify each)
1. The 2 flags are in ALL THREE: `_FULL_CAPABILITY_BENCHMARK_SLATE`, `_BENCHMARK_FORCE_ON_FLAGS`, `_BENCHMARK_PREFLIGHT_REQUIRED_FLAGS` — so a stray operator `=0` cannot survive (force-on overrides; required fails closed). VERIFY all three.
2. NO numeric-floor mishandling: both are pure on/off ("1"), not the int-floor path. VERIFY they don't accidentally land in `_BENCHMARK_PREFLIGHT_FLOORS` / a numeric coercion.
3. Selection-scale correctly EXCLUDED (the cap conflict). VERIFY the diff does NOT activate PG_SWEEP_SELECTION_SCALE anywhere.
4. The activated behaviour is operator-DIRECTED (the always-release reframe) and faithfulness-safe: always-release converts report-level BLOCK->LABEL only (per-claim gates untouched); the sanitizer is strictly subtractive (drops cruft, never invents data).

## Evidence pack (ran this session)
- import probe: PG_ALWAYS_RELEASE in slate=True, required=True, force-on=True.
- `pytest <10 gate-b slate tests incl. test_capped_finding_dedup, test_super_heavy_preflight, test_benchmark_stack_activation>` -> **108 passed** (after excluding selection-scale; was 1 failed WITH selection-scale).
- Composed behavioral proof on saved drb_76 (flags ON): keystone releases (was withheld), sanitizer drops 4->0 DOI cruft, KF clean.

## Red-team focus
Does activating PG_ALWAYS_RELEASE in the REQUIRED slate have any path to a FAITHFULNESS regression (a fabricated/zero-grounding run mis-classified as released)? Is there any OTHER #1070-style cap or test the always-release / sanitizer activation silently conflicts with (like the selection-scale/cap conflict I caught)?

## Output schema (REQUIRED — last `verdict:` line parsed by CI)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

========== THE DIFF UNDER REVIEW ==========

diff --git a/scripts/dr_benchmark/run_gate_b.py b/scripts/dr_benchmark/run_gate_b.py
index ae367265..8ea12a72 100644
--- a/scripts/dr_benchmark/run_gate_b.py
+++ b/scripts/dr_benchmark/run_gate_b.py
@@ -616,6 +616,18 @@ _FULL_CAPABILITY_BENCHMARK_SLATE: dict[str, str] = {
     # operator =0 cannot survive the setdefault slate and silently restore the tier-count refusal on the
     # paid beat-both run (the I-cap-005 P1-1 force-on pattern).
     "PG_SWEEP_WEIGHTED_CORPUS_GATE": "1",
+    # I-perm-000 permanent-fix activation (#1194). Each fix is DEFAULT OFF (byte-identical) and is
+    # INERT in production unless the slate turns it on — the exact "fix built but not live" trap.
+    # Force-on + required below so a stray operator =0 cannot survive the setdefault slate and
+    # silently restore the pre-fix behaviour on the paid beat-both run.
+    #   PG_ALWAYS_RELEASE         (#1195 keystone) WITHHOLD->ALWAYS-RELEASE+LABEL: a held report ships
+    #                             with disclosed gaps instead of aborting (the drb_76 false hold).
+    #   PG_SWEEP_NUMERIC_SANITIZER(#1201) drop DOI/URL/accession cruft parsed as clinical data.
+    # NOT activated here: PG_SWEEP_SELECTION_SCALE (#1197) — the blueprint keeps it flag-OFF until
+    # I-perm-007 grows a real large pool (it is preventative; on the current corpus it would scale
+    # the budget ABOVE the #1070/#1078 evidence-to-generation cap and re-flood the generator).
+    "PG_ALWAYS_RELEASE": "1",
+    "PG_SWEEP_NUMERIC_SANITIZER": "1",
 }
 
 # Minimum effective values the run MUST meet — the preflight FAILS CLOSED if any is below these (i.e.
@@ -680,6 +692,12 @@ _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS = (
     # (abort_corpus_approval_denied) on a tier-skewed-but-legitimate ECONOMICS corpus. Fail closed if it
     # is not active so a tier-mix refusal can never silently reach the paid run.
     "PG_SWEEP_WEIGHTED_CORPUS_GATE",
+    # I-perm-000 permanent-fix (#1194): the keystone always-release + the numeric sanitizer + the
+    # are DEFAULT OFF; required here so the preflight FAILS CLOSED if either is off, i.e. the paid
+    # run can NEVER silently revert to the pre-fix withhold / DOI-cruft behaviour. (Selection-scale
+    # #1197 is deliberately NOT required — it stays flag-OFF until I-perm-007 grows a real pool.)
+    "PG_ALWAYS_RELEASE",
+    "PG_SWEEP_NUMERIC_SANITIZER",
 )
 
 # Codex diff-gate I-cap-005 P1-2: the minimum EFFECTIVE per-run budget cap. PG_MAX_COST_PER_RUN is an
@@ -730,6 +748,11 @@ _BENCHMARK_FORCE_ON_FLAGS = frozenset({
     "PG_SERPER_STOP_ON_ZERO_NEW",
     # BB-006: ingest the STORM interview-search-result URLs as URL-only seed candidates.
     "PG_STORM_INGEST_WEB_RESULTS",
+    # I-perm-000 (#1194): force-on the two ready permanent-fix flags so an explicit operator =0
+    # cannot survive the setdefault slate and silently revert to the pre-fix withhold / DOI-cruft
+    # behaviour. (PG_SWEEP_SELECTION_SCALE stays OFF until I-perm-007 grows a real pool.)
+    "PG_ALWAYS_RELEASE",
+    "PG_SWEEP_NUMERIC_SANITIZER",
 })
 
 # Flags/modes that the benchmark slate force-sets to a specific value that is
