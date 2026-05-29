HARD ITERATION CAP: 5 per document. This is iter 1 of the M5 DESIGN review.
- Front-load ALL real findings. Reserve P0/P1 for real execution/safety risks.
- This is a DESIGN review — RULE on the writeback point + scope + safe rule BEFORE any code.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
writeback_point: <your ruling: which path/function + when>
scope_ruling: <benchmark-path / clinical-generator-path / both>
safe_rule: <the exact evaluator_agrees rule>
p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```

# Codex DESIGN review — I-meta-002 PR-9/M5: evaluator_agrees writeback (VERIFIED->true, else->false)

Your readiness ruling item 6 = M5: "evaluator_agrees writeback at the real VerifiedSentence/report
assembly point (VERIFIED->true, else->false)." Grounding revealed a path gap; please rule on the exact
writeback point + scope before I build. NO SPEND / NO NETWORK (M5 is wiring + offline tests).

## HARD CONSTRAINTS (operator-locked)
- §-1.1 clinical safety: evaluator_agrees drives what the Inspector/audit bundle shows as
  "evaluator-confirmed." Marking a FABRICATED/UNSUPPORTED claim as evaluator_agrees=True would be
  LETHAL. The rule must be fail-safe: a non-VERIFIED final verdict must NEVER yield evaluator_agrees=True.
- Frozen, no drift: claim_audit_scorer.py, runtime lock (NOT promoted). M5 only adds the writeback.
- D8 remains the single binding gate. M5 does not change release decisions; it populates the
  per-sentence evaluator_agrees field for audit/inspector fidelity.

## Grounded facts (file:line)
- `evaluator_agrees_from_verdict(final_verdict)` already exists (`sweep_integration.py:121-129`):
  VERIFIED->True, every other verdict (PARTIAL/UNSUPPORTED/FABRICATED/UNREACHABLE)->False.
- The 4-role evaluation (run in run_one_query's guarded branch, sweep path) produces
  `final_verdicts: dict[claim_id -> verdict]` and surfaces it in
  `manifest['four_role_evaluation']['final_verdicts']` (`run_honest_sweep_r3.py:3196-3204`). The
  run_one_query comment (3190-3195) explicitly says: "The sweep's SectionResult path holds
  SentenceVerification, NOT VerifiedSentence, so there is no VerifiedSentence object to write here —
  populating one would be fake wiring."
- **TWO strict_verify functions / TWO paths:**
  1. BENCHMARK/SWEEP path: `run_one_query` -> `multi_section_generator.strict_verify`
     (= `generator/provenance_generator.py:1428`) -> produces `SentenceVerification`
     (`provenance_generator.py:398-407`: sentence/tokens/is_verified/... — NO evaluator_agrees field).
     This is the path the DRB-EN benchmark actually runs through.
  2. CLINICAL-GENERATOR path: `clinical_generator/generator.py` -> `clinical_generator/strict_verify.py:312`
     -> produces `VerifiedSentence` (`verified_report.py:71`) with `evaluator_agrees`, assembled into
     `VerifiedReport` (`verified_report.py:410`, generator.py:297). Currently
     `evaluator_agrees=passed` at strict_verify.py:318 (placeholder that "mirrors verifier_pass"; the
     field docstring says "future Issue plugs in the real two-family judge to populate this
     independently").
- VerifiedSentence validator (`verified_report.py:148-156`): `evaluator_agrees=True` is FORBIDDEN when
  `verifier_pass=False` (a dropped sentence can never be evaluator-agreed). So the writeback may only
  set True on a kept (verifier_pass=True) sentence; setting False is always allowed.
- SEQUENCING: clinical_generator/strict_verify sets evaluator_agrees at sentence-CREATION time, which
  is BEFORE any 4-role eval. The 4-role final_verdicts only exist AFTER generation, in run_one_query
  (the sweep path). So a same-call writeback at creation time cannot see the 4-role verdict.

## The design questions (please rule)
1. `writeback_point` + `scope_ruling`: WHERE does evaluator_agrees writeback belong, given the path gap?
   Options I see:
   - (A) CLINICAL-GENERATOR path only: replace the strict_verify.py:318 `evaluator_agrees=passed`
     placeholder with the 4-role final_verdict — but that path does NOT currently run the 4-role eval,
     so it would need the 4-role eval wired into clinical_generator first (large; maybe out of M5 scope).
   - (B) SWEEP/BENCHMARK path: the sweep holds SentenceVerification (no evaluator_agrees field +
     no VerifiedSentence). The 4-role final_verdicts ARE in the manifest. Should M5 surface a
     per-claim evaluator_agrees MAP in the manifest (claim_id -> bool via evaluator_agrees_from_verdict)
     rather than mutating a VerifiedSentence that doesn't exist on this path? (run_one_query's own
     comment warns that writing a VerifiedSentence here would be "fake wiring".)
   - (C) A post-4-role writeback pass that, for whichever path carries VerifiedSentence, maps
     final_verdicts[claim_id] onto VerifiedSentence.evaluator_agrees (only flipping kept sentences;
     never True on verifier_pass=False).
   Which path is the "real assembly point" you meant, and is M5 scoped to the benchmark path (manifest
   map), the clinical-generator path (VerifiedSentence), or both?
2. `safe_rule`: confirm: evaluator_agrees = (final_verdict == VERIFIED) AND verifier_pass==True; any
   non-VERIFIED verdict -> False; never True on a dropped/verifier_pass=False sentence (respects the
   validator). Is mapping via the existing `evaluator_agrees_from_verdict` correct, plus the
   verifier_pass guard?
3. Is M5 actually required for the no-spend OFFLINE END-TO-END (roadmap item 9:
   "report->4-role manifest->evaluator_agrees->pathB PASS->...score_run->aggregate")? i.e., does the
   e2e need evaluator_agrees as a per-sentence field, or is the manifest final_verdicts map sufficient?
4. Any contamination / fail-open / double-write risk, or a simpler correct design I've missed?

Please APPROVE a concrete M5 design (writeback point + scope + safe rule) so I can build it, or
REQUEST_CHANGES with your ruling.
