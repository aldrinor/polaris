HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-meta-005 Phase 7 (#991) — Quantified trade-off + decision artifacts (gap 9, PAL rewire) — BRIEF

You are reviewing ACCEPTANCE CRITERIA + ruling on the design decisions in §5. This is
the ONLY genuinely-new capability of the 9-phase re-architecture, and it EXTENDS the
faithfulness wedge to COMPUTED numbers (strictly stronger than ChatGPT/Gemini DR).

## 1. Goal (plan rows 84/95/100)
Trade-off NUMBERS in the report are COMPUTED by a deterministic sandbox (Program-Aided
Language / PAL), never LLM-generated, and every computed number is bound to provenance
and VERIFIED by equality — so a wrong arithmetic number cannot survive (kills gap-14 at
its source). The PAL substrate (`tools/code_executor.py` full sandbox runtime,
`tools/tool_registry.py`, `evidence_extractor`) is ~70% built but UNWIRED — the sweep
never imports it. Gap 9 = re-wire + provenance-binding + faithfulness-wedge extension,
NOT greenfield.

Pipeline: **Extract → Model → Execute → Bind → Verify**
1. **Extract** (sourced numbers): reuse `evidence_extractor.extract_numbers_from_evidence()`
   → data_points each with an `evidence_id`. ONLY numbers with an evidence_id are eligible
   model inputs (fail-closed).
2. **Model** (declarative spec): the Writer emits a JSON spec — `{title, inputs:[{name,
   value, unit, ev_id} | {name, sweep:[...], modeled:true}], formula, outputs,
   sensitivity_over}`. Every input is EITHER sourced (ev_id) OR modeled:true. NO third
   category.
3. **Execute** (deterministic PAL): hand the spec to `code_executor` →
   computed outputs + a sensitivity table (nested sweep over modeled assumptions) + a
   break-even solve (`scipy.optimize.brentq`, already allowlisted). Arithmetic is
   COMPUTED, never generated.
4. **Bind** (provenance): each computed number carries a `[#calc:<model_id>:<field>]` /
   `[#model:<name>←ev_017,ev_021:modeled=<vars>]` token declaring its inputs' evidence
   IDs + which variables are modeled. The spec + executed script persist to
   `outputs/.../quantified_model.json` (extends gap-19 audit/replay).
5. **Verify** (Regime C): a sentence carrying a `[#calc:]`/`[#model:]` token is
   force-routed to a NEW Regime C: (a) every ev_id exists AND is a declared input of the
   model spec; (b) the asserted number EQUALS the executed output within a float
   tolerance; (c) every `modeled=` variable is labeled "(modeled assumption)" in the
   sentence — else the sentence is DROPPED. Fail-closed on any mismatch.

## 2. HARD CONSTRAINTS
1. **Gated behind `PG_ENABLE_QUANTIFIED_ANALYSIS` (default OFF). OFF byte-identical** —
   the sweep does not import/run any PAL code; the report + manifest are unchanged.
2. **Fail-closed (faithfulness wedge — clinical/decision-lethal).** No model is built
   unless EVERY declared input is sourced (ev_id) or explicitly modeled:true. A computed
   number whose asserted value ≠ the executed output is DROPPED (never shipped). A
   modeled assumption that is not labeled is DROPPED. No silent fallback, no LLM-generated
   number in the verified core.
3. **Reuse the EXISTING validated sandbox** (`code_executor._validate_ast` import
   allowlist + reflection blocklist + socket-kill + restricted-env subprocess + 30s
   timeout). Do NOT widen the allowlist or weaken the sandbox.
4. **Zero new served model.** The spec-gen + code-gen use the existing generator family
   (DeepSeek-V4-Pro). No new model. Regime C verification is pure (no LLM): token parse +
   evidence lookup + float compare.
5. **Money / spend-discipline.** ON-mode the Model step (1 LLM spec call) + Execute step
   (1 LLM code-gen call) bill the generator — gated, operator-enabled. BUILD + SMOKE are
   SPEND-FREE: the executor is exercised via `code_executor.execute_analysis_script(script,
   input_data)` with a FIXED script string (no LLM); the spec-gen + code-gen LLM calls are
   faked/injected in tests. Assert no live client constructed in smoke.
6. snake_case; no `unittest.mock` in `src/`; explicit imports; no magic numbers (the
   equality tolerance is a named constant / env).

## 3. FILE-BY-FILE (per the substrate map .codex/I-meta-005-phase-7/substrate_map.txt)
1. **NEW `src/polaris_graph/synthesis/tradeoff_modeler.py`** (~300 lines, pure orchestration):
   `build_quantified_spec(question, sourced_numbers, *, spec_llm) -> ModelSpec | None`.
   Calls the Writer for a JSON spec; validates the schema (every input sourced|modeled;
   formula present; outputs declared; sensitivity_over ⊆ modeled inputs); FAIL-CLOSED →
   None when any declared input lacks a source AND is not modeled. Returns a typed
   `ModelSpec` dataclass.
2. **NEW `src/polaris_graph/generator/quantified_analysis.py`** (~250 lines):
   `execute_quantified_model(spec, evidence_rows, *, code_llm) -> QuantifiedResult | None`.
   Calls `code_executor.generate_and_execute_analysis` (or feeds the spec's formula to
   `execute_analysis_script`); captures computed outputs + sensitivity + break-even +
   the generated script; persists `quantified_model.json`; BINDS `[#calc:]`/`[#model:]`
   tokens to the prose sentences that report each number. Returns the result + the
   token→value map for Regime C.
3. **`src/polaris_graph/generator/provenance_generator.py`** (~150 lines added): a Regime C
   router (detect `[#calc:]`/`[#model:]` tokens BEFORE Regime A dispatch) + `verify_modeled_atom`
   implementing §1.5 (a)/(b)/(c), fail-closed. Regime A unchanged in guarantee.
4. **`scripts/run_honest_sweep_r3.py`**: gate `PG_ENABLE_QUANTIFIED_ANALYSIS`; ON-mode,
   after the verified sections, run Extract→Model→Execute→Bind→Verify and add the verified
   quantified-analysis prose + decision matrix to the report; persist `quantified_model.json`
   + manifest `quantified_analysis` telemetry. OFF: unchanged.

## 4. GREEN (exit, #991)
- decision matrix + break-even/sensitivity rendered WHERE the corpus supports it (sourced
  inputs exist); skipped cleanly (no model) when it does not.
- EVERY computed number traces to a verified `[#ev:]` span (sourced input) or a labeled
  modeled assumption; modeled-vs-sourced visibly labeled.
- A computed number whose value ≠ the executor output is DROPPED (equality-verified).
- qualitative conflicts surfaced (contradiction wiring).
- OFF byte-identical; sandbox unchanged; zero new served model.

## 5. DESIGN DECISIONS — RULE ON THESE (quality + safety impact)
- **D1 — token grammar.** Proposed: `[#calc:<model_id>:<output_field>]` for a computed
  output; `[#model:<input_name>←<ev_id,ev_id>:modeled=<var,var>]` for a modeled-input
  declaration. Is this grammar sufficient + parseable, or do you want a different scheme
  (e.g. a single `[#calc:...]` carrying both inputs + modeled flags)?
- **D2 — Regime C equality tolerance.** Proposed: relative tolerance `PG_CALC_EQ_REL_TOL`
  default 1e-6 (so a number printed to a few sig figs matches the full-precision executor
  output) with an absolute floor for near-zero. Acceptable, or stricter/looser?
- **D3 — where the quantified analysis lands.** Proposed: a dedicated verified
  "Quantified trade-off" section appended after the verified sections (its sentences go
  through Regime C). Alternative: fold it into the Phase-6 Integrative section. Which?
- **D4 — fail-closed granularity.** Proposed: if ANY declared input lacks a source and is
  not modeled, the WHOLE model is skipped (no partial model). Alternative: drop only the
  unsourced output. Which is safer for the wedge?
- **D5 — sensitivity/break-even scope.** Only emit break-even when the formula is solvable
  (brentq finds a sign change) and sensitivity only over modeled inputs. Confirm.

## 6. SMOKE (`tests/polaris_graph/synthesis/test_quantified_tradeoff_phase7.py`) — SPEND-FREE
- P7-1 OFF byte-identity (flag OFF → no PAL import/run; report+manifest unchanged).
- P7-2 sandbox unchanged: a script importing os/subprocess/socket is REJECTED by
  `validate_script` (reuse, prove not weakened).
- P7-3 Execute spend-free: `execute_analysis_script(fixed_script, input_data)` computes the
  right output with NO live client.
- P7-4 Regime C equality PASS: a sentence whose asserted number == executed output (within
  tol) + all ev_ids declared inputs + modeled vars labeled → VERIFIED.
- P7-5 Regime C equality FAIL: asserted number ≠ executed output → sentence DROPPED.
- P7-6 unsourced input → model skipped / output dropped (fail-closed).
- P7-7 modeled assumption unlabeled → sentence DROPPED.
- P7-8 modeled assumption labeled "(modeled assumption)" → VERIFIED.
- P7-9 spec validation: a spec with an input that is neither sourced nor modeled →
  build_quantified_spec returns None (fail-closed).
Then a generator/provenance regression subset for OFF byte-identity + Regime A unchanged.

## 7. Output schema (REQUIRED)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
design_rulings: {D1, D2, D3, D4, D5}
remaining_blockers_for_execution: [...]
```
