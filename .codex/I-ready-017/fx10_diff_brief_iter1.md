# FX-10 (#1115) diff-gate — ITER 1 of 5

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (REQUIRED — reply with EXACTLY this YAML, nothing else)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Bug (BUG, P2)
`CompletenessReport.covered_fraction` returns a vacuous 1.0 when `total_applicable==0`
(no checklist applied). The held drb_72 `manifest.completeness` reads
`{"covered_fraction": 1.0, "total_applicable": 0}` — presented as 100% complete when
nothing was checked (SQL 3VL: an empty applicable set is UNKNOWN/NULL, not TRUE).

## Fix (diff: `.codex/I-ready-017/fx10_codex_diff.patch`, vs FX-09 tip `61856dfd`)
1. `completeness_checker.py`: new `completeness_state` property → `'not_applicable'` if
   `total_applicable==0` else `'measured'`. `covered_fraction` stays NUMERIC (consumers
   compare it; never return None → no `None < 0.5` TypeError).
2. `run_honest_sweep_r3.py`: `completeness.json` + BOTH `manifest.completeness` blocks now
   carry `completeness_state` (+ `notes` on the success manifest). ON-mode neutral report
   tagged `notes=['no_checklist_loaded']`.
3. `evaluator_gate.py:184`: `comp_thin` now requires `completeness_state=='measured'` — a
   not_applicable completeness is ADVISORY (never flagged as thin). Robust even if a future
   not_applicable carried a low numeric; covered_fraction stays numeric (no TypeError).

## Evidence
- **§-1.1 on REAL output** (`outputs/audits/I-ready-017/fx10_s11_audit.md`): the held
  manifest `{covered_fraction:1.0, total_applicable:0}` replayed → new property tags
  `not_applicable`. PASS.
- **Consumer-safety (behavioral, real gate):** `test_fx10_completeness_state_iready017`
  drives the actual `compute_evaluator_gate`: judge flags completeness=needs_revision +
  **not_applicable** report → NO `judge_completeness_needs_revision` (advisory-skip, no
  TypeError); same judge + **measured 0.3** → IS flagged.
- **Offline smoke:** `pytest test_fx10... test_completeness_r6_gap3 test_m205_evaluator_gate`
  → 27 passed (4 FX-10 + 23 regression). All 3 modified files parse.

## Faithfulness check
Honesty fix (don't claim 100% complete when nothing was checked). No
grounding/strict_verify/4-role change; covered_fraction stays numeric; manifest key shape
only gains additive fields.

## Question
Is the not_applicable 3VL state correct and consumer-safe (advisory-skip, no TypeError,
genuine thin coverage still flagged), with no broken manifest consumer? Anything blocking?
