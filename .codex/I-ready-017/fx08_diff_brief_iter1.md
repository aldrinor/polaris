# FX-08 (#1112) PART-A diff-gate — ITER 1 of 5

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

## Scope — this PR is FX-08 PART A (tolerant pass-2 parse) ONLY
PART B (determinism: temperature=0 + seed + claim-level dedup) is split to
**FX-08b (#1113)** per the plan ("ship tolerant-parse first; dedup follow-up") —
it touches different files with FX-11 collision-avoidance and the dedup is the
real determinism guarantee. Review ONLY PART A here; do not RC for PART B.

## Bug (BUG-04 format half)
17 GROUNDED claims fail-closed to UNSUPPORTED purely on pass-2 output FORMAT
(GLM-5.1 shapes like `{"classification": 0}`, `{"domain":..,"field":..}` the
strict parser rejected).

## LOAD-BEARING SAFETY INVARIANT (verified against real code)
`mirror_adapter.py:337-344` raises `MirrorCitationError` (the ONLY grounding gate)
BEFORE `_parse_pass2` (:368); `verify_pass2_binding` (:378) gates content_hash
after. The Mirror `classification` is advisory to the Judge (`role_pipeline.py:321`
→ `judge_adapter.py:116` `MIRROR_SIGNAL`), NOT a hard gate. So broadening pass-2
parsing cannot create a false-accept (an ungrounded claim already failed closed).

## Fix (diff: `.codex/I-ready-017/fx08_codex_diff.patch`, vs `ec3703e8`)
1. `_coerce_classification_value`: coerce int/float/bool → `str(value)` (bool is an
   int subclass; json_repair philosophy). Fixes `{"classification": 0}` → "0".
2. `_parse_pass2`: when `_recover_classification` returns None, serialize the WHOLE
   object as the non-gating verdict ONLY IF the payload has a GENUINE unrecognized
   signal key (`set(payload) - {content_hash, rationale, answer_text, classification,
   answer, category, label, class}` non-empty). Fixes `{"domain":..,"field":..}`.

## Faithfulness-HARDENING beyond the plan (please scrutinize)
The plan said "serialize the WHOLE object" for ANY non-empty no-classification
body. I did NOT do that: two existing tests are NO-FALSE-ACCEPT guards for
echo/binding-only bodies (`{content_hash}` and `{content_hash, answer_text}`), and
since classification is an advisory MIRROR_SIGNAL to the Judge, serializing an
echoed `answer_text` would launder it into a signal. So echo/binding-only bodies
(no genuine signal key) + empty `{}` STILL fail closed. **Both no-false-accept
guards stay green — no contract relaxation.** Is this the right call, or do you
want the plan's literal "whole object" (which I believe is less safe)?

## Evidence
- **§-1.1 on documented real bodies** (`outputs/audits/I-ready-017/fx08_s11_audit.md`):
  00-028 `{"classification":0}` → "0"; 00-078 `{"domain":..}` → serialized;
  05-004 `{}` → fail-closed; echo-only → fail-closed. PASS.
- **Offline smoke:** `pytest tests/roles/` → 437 passed (+5 new FX-08 PART-A tests;
  the NEGATIVE-PROOF `test_no_co_span_claim_still_unsupported_pass1_grounding_untouched`
  and both no-false-accept guards green).

## Question
Is PART A faithfulness-safe and correct — grounding gate untouched, broadened
pass-2 cannot false-accept, echo/binding-only + empty still fail closed, genuine
GLM nested shapes recovered? Anything blocking PART A? (Determinism is FX-08b.)
