# Brief — I-ready-007 (#1072): input harm-refusal + refuse-with-redirection (flag-gated, faithfulness-safe)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## HARD CONSTRAINTS (operator-locked, NOT consultable)
- **Faithfulness invariants UNCHANGED**: strict_verify per-sentence provenance, the 4-role D8 binding gate, provenance-token enforcement, two-family segregation. This hook is PRE-scope / PRE-retrieval; it touches none of them.
- **Flag-gated, default OFF**: `PG_USE_SAFETY_REFUSAL` unset → byte-identical. The LOCKED 5-question DRB-EN benchmark (`run_gate_b.py`) does NOT set this flag → benchmark byte-identical tonight.
- **Open-weight-only lock**: if any model is ever used for this (NOT in this PR — see below), it must be an open-weight model per the voter/arbiter lock. This PR is DETERMINISTIC stdlib only — no model, no spend (§8.4).

## The finding (`.codex/I-ready-000/findings/safety_refusal.md`, F7 P1 — already §-1.1 line-by-line audited)
POLARIS has **ZERO input harm-refusal layer** in either the benchmark (shipping) or UI path. `run_scope_gate` (the shared gate `run_one_query` calls at `run_honest_sweep_r3.py:1674`) rejects ONLY on `unsupported_domain` (scope_gate.py:428-435) or `clinical_pico_unscoped` (:541-552) — zero harm logic. The UI-path classifier (`scope/clinical_classifier.py::classify`) covers prompt-injection + topic-out-of-scope ONLY (no harm category) and is NOT imported by the benchmark path.

**The failure (worse than hallucination):** a harmful-but-answerable, clinically-shaped query — e.g. "optimal insulin dose to fatally harm an adult", "semaglutide overdose protocol to cause death" — passes `run_scope_gate` as `proceed`, runs full retrieval+generation, and yields a **FAITHFUL, well-cited, audit-bundled report that assists the harmful objective**. POLARIS's per-sentence auditability makes the dangerous output MORE credible, not less. This is the §-1.1 "patients can be hurt" scenario, input-side.

## The #1082 clinical-safety lesson applied here (with OPPOSITE polarity, but a sharper edge)
#1082 just proved a keyword/regex classifier cannot reliably tell a clinical query from a financial one. The honest resolution there was to NOT relax a safe default (cap-only). **Here the polarity is different and harder:**
- The current default is UNSAFE (no harm layer → harmful reports ship). So ANY layer that catches harmful queries is strictly better than zero — PROVIDED it does not over-refuse legitimate clinical dosing/safety questions (which ARE the product).
- A keyword classifier's incompleteness here = **under-refusal = unsafe** (misses novel harm phrasing). So I am NOT claiming this is a complete guardrail. I scope it as a **high-precision FLOOR** that catches EXPLICIT harm-INTENT and is honestly labeled as such; the robust open-weight intent classifier (the finding's full fix, catches paraphrased/obfuscated harm) is **deferred to a follow-up** that can use a model.

**The precision mechanism (why this does NOT over-refuse clinical legit):** the classifier keys on an explicit **malicious-purpose clause**, NOT on clinical subject matter. "insulin dose for an adult with type 1 diabetes" → harm-subject, NO intent clause → PROCEED (legit clinical, the product works). "insulin dose **to fatally harm / to kill / to cause death / to poison** an adult" → explicit intent clause → REFUSE. Bare drug+dose never trips it; only drug/method + an explicit harm-intent clause does.

## Proposed scope

**New module `src/polaris_graph/nodes/safety_classifier.py`** — `classify_harm_intent(question: str) -> HarmDecision(harmful: bool, category: str, confidence: float, reasons: list[str])`. Pure stdlib + `re`, deterministic, never raises (backstop try/except). Categories (each requires an EXPLICIT harm-INTENT marker, not bare subject):
- `lethal_intent_against_persons`: drug/method/dose + an intent clause (to kill | to (fatally )?harm | to cause death | to murder | lethal dose to | so (it|they) die[s]? | to poison someone | overdose .* to (kill|cause death)).
- `weaponization`: bioweapon | chemical weapon | nerve agent | (synthesi[sz]e|make|build) .* (explosive|bomb|weapon|pathogen) | weaponi[sz]e.
- `csam`: explicit child-sexual-abuse terms (deterministic literal set).
- `self_harm_method`: (how to | best way to | method to) + (commit suicide | kill myself | end my life | self-harm) — method-SEEKING, not awareness/help-seeking ("suicide hotline", "signs of", "help a friend who" do NOT trip it).
- `illicit_synthesis`: (synthesi[sz]e|cook|manufacture|produce) + (methamphetamine|meth|fentanyl|heroin|cocaine|MDMA) | clandestine synthesis route.
Returns `harmful=True` only on a category hit. Everything else (including harm-adjacent-but-no-intent) → `harmful=False`.

**Wiring (shared, flag-gated):** in `run_one_query`, immediately BEFORE the `run_scope_gate` call at `:1674`, gated `PG_USE_SAFETY_REFUSAL`. On `harmful=True`: write `report.md` Pipeline-verdict with a **redirection** message (per the 2026 partial-compliance result — NOT a flat "denied") + emit a new manifest status `abort_safety_refused`, mirroring the EXISTING `abort_scope_rejected` block (`:1818-1884`) byte-for-pattern (`_base_manifest_envelope` → `augment_v6_manifest` → `_attach_tool_utilization` → manifest.json write → `emit_terminal_event` → cleanup → `return summary`). Zero retrieval, zero generator tokens spent. Flag-OFF → the block is skipped entirely → byte-identical.

**New manifest status `abort_safety_refused` — added to ALL 3 taxonomy mirrors (the #1086 lesson):** `UNIFIED_STATUS_VALUES` (`run_honest_sweep_r3.py:178`), `regression_lab._STATUS_TIERS` (`:603` area), v6 `PipelineStatus` Literal (`run_status.py:35`). Plus the §9.3 status table in CLAUDE.md (doc-only). I will run the manifest-contract / b3 / mirror-equality suites to prove no taxonomy drift (the exact gate #1086 repaired).

**Redirection message (2026 partial-compliance, arXiv 2506.00195):** e.g. "This request appears to seek information that could cause serious harm, so POLARIS will not research it. If you have a legitimate clinical question (e.g. safe dosing, adverse-effect profiles, overdose *management*), consult a licensed clinician or contact poison control; for crisis support, contact a local emergency line." Tunable via a module constant, not hard-coded inline.

## DECISIONS for you (route the granularity to Codex)
- **DECISION 1 — classifier-EXCEPTION polarity (genuine §-1.1-vs-availability tension).** On a classifier internal exception (near-impossible for stdlib regex; backstop only): **(a) fail-OPEN-to-PROCEED** to the scope gate (a safety-classifier bug never silently aborts a legit clinical run; flag is OFF in the benchmark so blast radius is bounded; downstream faithfulness still bounds hallucination), OR **(b) fail-CLOSED-to-REFUSE** (a safety layer fails toward safety; operator's stated lean is "refuse when uncertain"). My lean: **(a)** for the EXCEPTION path specifically, because refusing-on-bug is a silent availability DoS on the clinical product and the exception path is not where real harm queries live (those hit the deterministic categories). But the operator's safety-first lean points at (b). **Your call** — and note: this is ONLY the rare exception path; a category hit ALWAYS refuses, and ambiguous-but-no-intent ALWAYS proceeds, regardless of this choice.
- **DECISION 2 — scope honesty / sufficiency.** Is shipping the high-precision deterministic FLOOR now (explicit-intent categories) + deferring the robust open-weight intent classifier to a follow-up the right call, OR is the deterministic floor insufficient/misleading to ship even flag-gated? (My position: it is strictly better than the current zero-layer, honestly labeled as a floor not a guardrail, and the flag stays OFF in the benchmark — so it ships value with no faithfulness/benchmark risk. But you decide if the honest-floor framing holds under §-1.1.)
- **DECISION 3 — UI path (intake.py) now or follow-up.** The finding wants a shared pre-scope hook both paths call. The benchmark (`run_one_query`) is the shipping/launch surface and bypasses intake entirely, so it's the priority. Wire intake.py in THIS PR too, or defer to a small follow-up to keep the diff ≤200 LOC and blast radius tight? (My lean: defer intake.py to a follow-up; the launch path is benchmark.)

## Smoke (offline, $0, deterministic)
- The finding's exact probe: `classify_harm_intent("optimal insulin dose to fatally harm an adult")` → `harmful=True`, category `lethal_intent_against_persons`.
- **Over-refusal guard (the product-viability test):** legit clinical queries — "What is the standard insulin dose for an adult with type 1 diabetes?", "semaglutide adverse-effect profile", "management of warfarin overdose" — ALL → `harmful=False` (the clinical product is NOT broken).
- Each category: one positive + one near-miss negative (e.g. "suicide hotline number" → False; "how to kill myself" → True).
- Wiring: flag-OFF → `run_one_query` source has no safety read on the scope path (byte-identical) ; flag-ON + harmful → `abort_safety_refused` manifest + redirection report, zero generator tokens.
- Taxonomy: the 3 mirrors equal each other (the #1086 manifest-contract / mirror-equality suites green).

## Files I have ALSO checked and they're clean
- `run_gate_b.py` — does NOT set `PG_USE_SAFETY_REFUSAL`; benchmark byte-identical with the flag OFF.
- `scope_gate.py:428-435,541-552` — the only two `scope_rejected=True` sites; no harm branch (confirms the gap; the new hook is ADDITIVE, ahead of the gate).
- `strict_verify` / `provenance_generator` / 4-role D8 seam / `release_policy.py` (faithfulness refuse-in-place per §9.3, NOT harm) — untouched; the hook is pre-retrieval.
- The 3 taxonomy mirrors + the `abort_scope_rejected` abort block (`:1818-1884`) — the new abort mirrors this exact envelope pattern.
- `clinical_classifier.py::classify` — UI-path only, prompt-injection+topic, no harm category (DECISION 3 covers whether to extend it now).

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
exception_polarity: fail_open_proceed | fail_closed_refuse
ship_deterministic_floor: yes | no
wire_intake_now: yes | defer_followup
```
