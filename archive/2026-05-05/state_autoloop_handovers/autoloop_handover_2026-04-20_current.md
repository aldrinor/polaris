# POLARIS DR Auto-Loop — In-Flight Handover (2026-04-20 late)

## Stop condition

User mandate: beat BOTH ChatGPT DR and Gemini DR head-to-head on 7
dimensions (citations, regulatory, jurisdiction, claim-frames,
structure, contradictions, narrative depth). Competitor PDFs at
`state/compare_chatgpt_dr.txt` / `state/compare_gemini_dr.txt`.

## Current state

### M-30 COMPLETED (pass-5 baseline)
- Commits: `6056855` → `d6a66a8` → `2bd0845` → `46fa532` → `82b2625`
- V19's actual failure mode was `vs.`, closed by pass-1.
- Passes 2-5 addressed Codex-invented probes. Diminishing returns;
  advisor recommended shipping pass-5 as baseline rather than hunting
  hypothetical patterns not observed in V19 content.
- Verification: PT11 on V19 real report `passed=True`; 40/40 M-30
  tests; 747/747 full polaris_graph suite.
- Acceptable trade-off documented: rare false-FAIL on edge cases
  (e.g. `ACRONYM + present-tense -s verb not in list`) preferred
  over false-PASS that lets fabrication through the gate.

### V20 IN-FLIGHT (task bknzaqka8)
- Launched `scripts/run_full_scale_v10.py --out-root outputs/full_scale_v20`
- Stack: M-28 regulatory-anchor retrieval + M-29 jurisdictional-
  precision prompt + M-30 PT11 abbreviation-aware boundary.
- Watch for: (a) PT11 failures on real generator output (vs the
  pass-2+ hypothetical probes), (b) outline JSON decode recurrence
  (task #8 trigger), (c) BEAT-BOTH dimensions metrics.

### Expected signals when V20 completes
1. `release_allowed=True` (PT11 regression closed; pass-5 has vs.,
   Jan. A, U.S. A, et al. A, etc. A, U.S. FDA approved, modal
   cases all covered).
2. Regulatory citations ≥10 (M-28 working).
3. No `both agencies / regulators require / authorities generally`
   patterns (M-29 working).
4. Ideally: 5-section outline, 2000+ words (matching V18 ceiling).

### Next steps after V20 completes
1. Extract V20 metrics, compare to V18/V19.
2. Dispatch Codex DR audit pass 10 with BEAT-BOTH head-to-head
   brief. Verdict criterion: must exceed ChatGPT DR (21 cites,
   4830 words) AND Gemini DR (43 cites, 6835 words) on all 7
   dimensions. Anything less = continue loop.
3. If V20 beats both: STOP, declare victory, archive handover.
4. If V20 ties or loses: implement next reconciled-plan fix
   (Fix B: claim frames → Fix C: evidence-strength grammar → Fix A:
   primary-entity sub-sections). Codex code audit + sweep for each.

## Metric history

| Sweep | Cites | Reg | Words | Release | Notes |
|------:|------:|----:|------:|:-------:|:------|
| V17   | 24    | 0   | 2077  | YES     | TOP-TIER pass 8 threshold |
| V18   | 35    | 12  | 2922  | YES     | M-28 landed (regulatory) |
| V19   | —     | —   | 755   | NO      | PT11 false-fail on vs.; outline decode 3× fail → 3-section fallback |
| V20   | ?     | ?   | ?     | ?       | In-flight: M-30 + M-28 + M-29 stack |

## Reconciled Claude+Codex plan remaining

1. ✅ M-28 (regulatory retrieval) — V18 landed
2. ✅ M-29 (jurisdictional precision) — V19 landed silently
3. ✅ M-30 (PT11 abbreviation boundary) — V20 stack
4. ⏳ Fix B: primary-evidence claim frames (N + baseline + endpoint
   per named study). Prompt-only. Low risk.
5. ⏳ Fix C: evidence-strength grammar + broken-detector
   suppression. Low risk.
6. ⏳ Fix A: primary-entity sub-sections / trial matrix. Medium
   risk.
7. ⏳ M-31: outline JSON decode resilience (parked pending V20
   observation).

## Task list

1. ✅ M-30 (completed)
2. 🔄 Codex DR audit pass 10 — BEAT-BOTH (blocked by V20 completion)
3. ⏳ Fix B (blocked by #2)
4. ⏳ Fix C (blocked by #3)
5. ⏳ Fix A (blocked by #4)
6. ⏳ Deep-dive R2a-R2h (parked)
7. ⏳ M-9 Pass 9 (parked)
8. ⏳ M-31 outline resilience (parked pending V20)

## Lessons from the M-30 iteration

- Adversarial code audits can run indefinitely if the auditor is
  allowed to construct probes outside the actual failure domain.
  Future Codex briefs should require: "produce a probe from actual
  generated content, not constructed text."
- Code-audit READY is a gate, not a work product. If the fix
  addresses the observed failure + doesn't regress existing tests,
  ship it and run the sweep.
- The only true measure of BEAT-BOTH is comparing real DR output
  head-to-head with competitor output. Code audits verify
  correctness, not quality.
