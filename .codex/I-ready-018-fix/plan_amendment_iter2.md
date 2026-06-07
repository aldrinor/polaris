# Plan amendment — iter-2 response to Codex plan-gate findings

Addressing each iter-1 finding. Operator (2026-06-07) reviewed and stated "agree on everything" including A9/A10 being high-priority, and confirmed the GLM decision (keep GLM, swap Mirror provider to the most reliable one).

## P1 — PLAN-SEQUENCE-A9-A10 (RESOLVED: promote A9 + A10 to BLOCKING pre-canary fixes)
The plan's severity model and execution sequence are now reconciled: A9 and A10 are promoted into the pre-canary fix set with fail-loud + report-disclosure acceptance criteria. Operator has accepted them as blocking (no-silent-downgrade directive, `feedback_no_downgrade_without_operator_approval`). The paid canary does NOT run until A3, SLOT, BP, JO, A9, A10, GLM are all Codex-APPROVE + CI-green.

### FIX-A9 — quantified-analysis silent no-op (P0, fail-loud)
**Target:** `src/polaris_graph/` quantified-analysis path (the module that sets `manifest.quantified_analysis`; precise file:line confirmed at diff time). Evidence: `enabled=true, execution_success=false, fired=false, spec_produced=false, outputs=0` despite `sourced_numbers_extracted=111`.
**Change + AC:** when quantified-analysis is `enabled=true` but `execution_success=false`/`fired=false`, it MUST (a) emit a loud WARNING/structured error (never a silent pass), AND (b) surface the degradation in `report.md` (e.g. a Methods/Limitations line "quantified trade-off analysis: enabled but did not execute — N sourced numbers not modeled") AND in `manifest` as an explicit degradation flag. Root-cause WHY it no-op'd despite 111 numbers (separate investigation in the diff brief). Do NOT make it silently succeed; if the root cause is unfixable in this PR, the disclosure path is the floor.
**Offline smoke (no spend):** feed the frozen drb_72 manifest state (enabled+not-fired) through the disclosure path; assert the report + manifest carry the explicit degradation surface; assert no silent pass.

### FIX-A10 — retrieval fetch-failure not disclosed (P1, fail-loud + disclose)
**Target:** retrieval summary → report/manifest disclosure path (`live_retriever` parallel_fetch summary + the Methods/Limitations renderer in `run_honest_sweep_r3.py`). Evidence: `retrieval.failed=129`, `parallel_fetch_timeout_count=129`, fetched=26/155 (≈62% failed); `retrieval_trace` drop reasons `fetch_failed=163, content_starved=10`; NOT disclosed in report.
**Change + AC:** the report MUST disclose the fetch-success/failure rate (e.g. Methods: "retrieval: 26/155 candidates fetched; 129 failed/timeout") so a reader sees coverage was upstream-starved; emit a loud log when the failure rate exceeds a configurable threshold (env-driven per LAW VI, default e.g. 0.5). This is disclosure-first (not necessarily a hard abort — fetch failures from paywalls/timeouts are partly expected), but it must NOT be silent.
**Offline smoke (no spend):** render the disclosure from the frozen retrieval summary; assert the failure counts appear in report.md + manifest; assert the over-threshold loud-log fires.

### Revised sequence
1. FIX-A3 (P0) → 2. FIX-SLOT (P1) → 3. FIX-BP (P1) → 4. FIX-JO (P1) → 5. **FIX-A9 (P0)** → 6. **FIX-A10 (P1)** → 7. FIX-GLM (P2). Each: own branch + brief + Codex diff-gate (5-iter cap) + offline micro-smoke. THEN operator-budget-gated canary (NO-SPEND `--list` first; operator sets `PG_AUTHORIZED_SWEEP_APPROVAL`; real acceptance = fresh §-1.1 audit; expected outcome stays `release_allowed=False` unless genuine substantive coverage clears 0.70).

## P2 — FIX-A3-SMOKE-SHARPEN (accepted)
FIX-A3's smoke EXPLICITLY retires/inverts the existing I-gen-005 local-window-positive test: the prior test asserted the local-window fallback PASSES a number found outside the printed span ("span_imprecise but locally grounded; passing") — option B changes that policy, so that test is inverted to assert the claim now DROPS with `number_not_in_cited_span`. The separate I-gen-005 false-drop case it was protecting ("cancer-50% in an unrelated paragraph" → correctly fails) is retained as the regression guard, and a NEW false-drop guard (number genuinely inside its cited span → still passes) is added.

## P2 — FIX-SLOT-COVERAGE-WORDING (corrected)
Corrected: dropping placeholder prose **cannot INCREASE Gate-B coverage** (CoverageLedger uses a fixed required-set denominator). On this frozen run, placeholder prose appears in report/NLI surfaces but NOT in `four_role_claim_audit`, so coverage may remain UNCHANGED rather than strictly lower. The gate-neutrality claim is therefore "same-or-lower coverage, never higher → never relaxes the HOLD" (not "always lower"). The acceptance criterion is unchanged: drb_72 STILL HOLDS (`release_allowed=False`).

## P2 — FIX-JO-CONFIRMED / FIX-GLM-CONFIRMED (no change)
Both confirmed by Codex. FIX-JO stays per-question (env flag + `source_restriction: journal_only`); the "does not make drb_72 shippable" caveat stands. FIX-GLM: keep glm-5.1, config-only — demote Parasail (23/126 blank) and route the Mirror to the most reliable provider (Io Net: 0/39 blank) per operator instruction; no model swap, lock + 4-distinct-family slate intact.
