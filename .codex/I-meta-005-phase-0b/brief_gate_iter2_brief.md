HARD ITERATION CAP: 5. iter 2 of 5. Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex BRIEF re-gate iter 2 — Phase 0b (#984): re-diagnosed, brief rewritten around the REAL gap-#18 cause

iter 1 = REQUEST_CHANGES (3 P1: union rescue already exists; model path wrong; judge fails-OPEN). RE-DIAGNOSED on the
running verifier (scripts/rediagnose_gap18.py); brief rewritten at .codex/I-meta-005-phase-0b/brief.md (READ IT).
Output §8.3.9 YAML verdict FIRST.

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Confirm each iter-1 finding is CLOSED + the new diagnosis is REAL:
- iter-1 P1 (duplicate union rescue): the brief now targets a DIFFERENT, real delta — NOT a union-entailment duplicate.
  VERIFY the 3 deltas against the running verifier:
  * Delta 1 (PRIMARY): content-word-overlap floor (:1135-1144) computes overlap against the NARROW cited byte-range,
    so a grounded sentence whose FULL cited row shares vocab is dropped before the judge. Fix = port the ACCEPTED
    I-gen-005 _find_local_support_window (:651-771, already in the decimal lane) to the content-word lane (widen
    candidate to full cited rows, propose bounded <=400-char window, BIND, fail-closed). Is this a REAL distinct delta
    (the narrow-span content-floor drop genuinely fires today, and union entailment does NOT save it because the floor
    runs FIRST)? Re-run/inspect to confirm.
  * Delta 2: the local-window second-chance is decimal-gated (:1244 `if not sentence_dec_local: continue`) so non-numeric
    reasoning fails closed at :1284. Extending it to non-numeric prose — correct + does it preserve fail-closed?
  * Delta 3 (was iter-1 P1 #3): judge returns ("ENTAILED","judge_error: ...") on failure (entailment_judge.py:147,261)
    and the verifier never reads reason (:1204). Lane DROPS ENTAILED-with-`judge_error:`; test feeds the return-shape
    sentinel (not a raising fake). Confirm the fail-closed is correct + the test targets the real shape.
- iter-1 P1 (model path): brief now states the TRUTH — _get_judge() defaults to google/gemma-4-31b-it (NOT locked
  qwen/granite), 0b keeps the legacy judge seam (judge-agnostic rescue), migration deferred to a lock-governed issue.
  Is this honest + the right scope call?
- DEFERRED: no_provenance_token token-less reasoning attribution stays an absolute drop in 0b (structurally
  non-repairable, separate phase). Rule on whether deferring it is acceptable scope for 0b.

## The wedge + smoke
OFF byte-identical at strict_verify:1494; numeric/decimal/no-token-for-factual rules UNCHANGED; the bounded-window
BIND preserves the 2026-05-30 composition lock (whole-row PROPOSES, <=400-char window BINDS). 10-group heavy smoke
incl. judge_error-sentinel DROP + a union-already-works baseline + the I-gen-005 regressions stay green. Sufficient?

APPROVE iff the 3 deltas are real-and-distinct (not duplicates), the bounded-window BIND preserves the wedge +
composition lock, the judge-error sentinel is dropped fail-closed, the model-path + token-less deferrals are honestly
scoped, and the heavy smoke is sufficient. Front-load every real finding (5-cap).
