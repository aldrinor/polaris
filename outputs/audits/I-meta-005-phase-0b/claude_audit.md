# Claude architect audit — I-meta-005 Phase 0b (verification-mode router, gap-#18)

## Scope
The three grounded-prose deltas in `verify_sentence_provenance`, gated on
`PG_VERIFICATION_MODE` {off, shadow, enforce}, default off (byte-identical):
- Delta 1: content-floor narrow-span wrongful drop — floor-clear PROPOSES a bounded
  ≤400-char full-cited-row window; the entailment judge BINDS downstream.
- Delta 2: non-numeric NEUTRAL bounded content-window re-judge (was decimal-gated).
- Delta 3: additive `judge_error` flag; enforce fail-closes on the judge fail-open sentinel.

## Dual-review findings + resolution
- **Architect P1 (Claude, in-workflow):** Delta 1 lacked the §3.3 entailment bind — under
  `PG_VERIFICATION_MODE=enforce` + `PG_STRICT_VERIFY_ENTAILMENT=off` it could launder a
  content-floor drop with no entailment backstop (proven with a contradicting judge never
  consulted). **Fixed:** Delta 1 PROPOSE gated on the entailment judge being active.
- **Architect P2 (Claude):** the Delta-1 positive test passed via narrow-span entailment, not
  the window bind. **Fixed:** S0b-2 uses a discriminating judge; S0b-9 proves the bind bites.
- **Codex diff-gate P1 (iter 1):** the gate `_entailment_mode() in (warn,enforce)` still
  fail-opened under `warn` (warn runs the judge but never drops). **Fixed:** Delta 1 PROPOSE
  and Delta 2 recovery gated on `_entailment_mode() == "enforce"` (the only mode where the bind
  drops). Added S0b-10 (warn no-launder: 0 judge calls, stays dropped).
- **Codex diff-gate P2 (iter 1):** S0b-1 used prefix assertions. **Fixed:** added a strict
  exact-`failure_reasons` wall.

## Verification
- Heavy smoke: 22/22 green (S0b-1..S0b-10), serialized (§8.4).
- OFF byte-identity: my change is byte-identical on the existing provenance/strict_verify suite
  (parent and HEAD produce the identical 31-pass/5-fail under `PYTHONPATH=src`; the 5 are a
  pre-existing double-import invocation artifact, proven by stash-and-rerun on parent).
- Codex diff-gate iter 2: **APPROVE** (re-verified the workspace code; warn probe → 0 judge
  calls, stays dropped; 22 passed).

## Verdict
APPROVE for merge. No live spend gated by this change (deltas inert under `off`; `enforce` is
opt-in and operator-gated via Gate-A before any production flip).
