# FX-08 PART A §-1.1 audit — Mirror pass-2 tolerant parse (I-ready-017 #1112)

**Standard:** §-1.1 on the documented real pass-2 body shapes from the held
drb_72 run (the plan's forensic log sweep; the manifest persists `final_verdicts`
but not raw pass-2 bodies). Replayed through the actual `_parse_pass2`.

## The bug (BUG-04, format half)
17 GROUNDED claims fail-closed to UNSUPPORTED purely on pass-2 output FORMAT —
GLM-5.1 emitted recoverable shapes the strict parser rejected.

## LOAD-BEARING SAFETY INVARIANT (verified against real code)
`mirror_adapter.py:337-344` raises `MirrorCitationError` (the ONLY grounding gate)
BEFORE `_parse_pass2` (:368); `verify_pass2_binding` (:378) gates the content_hash
after. So broadening pass-2 parsing CANNOT create a false-accept — an ungrounded
claim already failed closed before pass-2 runs. The Mirror `classification` is an
ADVISORY signal to the Judge (`role_pipeline.py:321` → `judge_adapter.py:116`
`MIRROR_SIGNAL`), NOT a hard gate.

## The fix, replayed on the documented real bodies (no spend)

| run body | new verdict | why |
|---|---|---|
| 00-028 `{"classification": 0}` | **RECOVER → "0"** | scalar int coerced to str (json_repair) |
| 00-078 `{"domain":"Economics","field":"labor"}` | **RECOVER → serialized** | genuine unrecognized GLM nested shape → serialize whole object |
| 05-004 `{}` | **FAIL-CLOSED** | empty object, no signal |
| echo-only `{"answer_text":..,"content_hash":..}` | **FAIL-CLOSED** | only echo/binding keys → no genuine verdict (no-false-accept guard preserved) |

**Audit verdict: PASS.** Grounded claims with recoverable shapes recover; empty
and echo/binding-only bodies still fail closed; the grounding gate is upstream
and untouched.

## §-1.1 design improvement over the plan (faithfulness-hardening)
The plan said "serialize the WHOLE object" for any non-empty no-classification
body. Investigation showed two existing tests are NO-FALSE-ACCEPT guards for
echo/binding-only bodies (`{content_hash}`, `{content_hash, answer_text}`), and
the Mirror classification feeds the Judge as an advisory signal. Blindly
serializing echo-only bodies would launder an echoed answer into a signal. So the
fix serializes ONLY when the payload has a genuine UNRECOGNIZED signal key
(payload keys minus {content_hash, rationale, answer_text, classification,
answer, category, label, class}); echo/binding-only bodies still fail closed.
**Both no-false-accept guards stay green** — no contract relaxation.

## Scope
This PR = PART A (tolerant parse). PART B (determinism: temperature=0 + seed +
claim-level dedup, run-once-fan-out) is split to **FX-08b** — it touches
`openrouter_role_transport.py` + `sweep_integration.py` with FX-11 collision-
avoidance, and the dedup (not temp/seed) is the real determinism guarantee.

## Offline smoke
`pytest tests/roles/` → **437 passed** (incl. 5 new FX-08 PART-A tests:
scalar-0 recovers, bool recovers, unrecognized-nested serializes, echo-only fails
closed, empty fails closed; + the pre-existing NEGATIVE-PROOF
`test_no_co_span_claim_still_unsupported_pass1_grounding_untouched` and the 2
no-false-accept guards all green).
