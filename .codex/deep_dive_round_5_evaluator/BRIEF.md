# Deep-dive R5 — Evaluator advisory vs gating (BUG-M-205)

**Target**: M-205. The Qwen judge sees only report text (no evidence
pool). The rule-based evaluator does keyword-presence checks. Qwen's
`needs_revision` verdict doesn't block success — a run can ship
`success` with Qwen flagging real defects.

## Mandate

Produce fix spec.

1. Read `src/polaris_graph/evaluator/live_qwen_judge.py` and
   `src/polaris_graph/evaluator/external_evaluator.py`.
2. Identify: which evaluator outputs should be RELEASE-BLOCKING vs
   ADVISORY. What counts as a "critical" Qwen verdict?
3. Propose a gating policy. New manifest status options, if needed.
4. Spec 4-6 tests.

## Anti-circle-jerk

If making the evaluator gating is too blunt (e.g., Qwen's noise rate
is too high to gate on a single verdict), design a more nuanced policy
(e.g., gate only when 3+ axes return needs_revision; or require
groundedness below X to block).

## Output

`outputs/codex_findings/deep_dive_round_5/findings.md` with the usual
frontmatter.

## Context

- `outputs/codex_findings/full_audit_pass_1/findings.md` §6
- Prior rounds: R1-R4 committed
- Real artifact: `clinical_afib_anticoagulation/qwen_judge_output.json`
  shows `citation_tightness: needs_revision` while manifest status was
  `ok_thin_corpus` (now: `partial_thin_corpus` after R1)

## Duration

5-10 minutes.
