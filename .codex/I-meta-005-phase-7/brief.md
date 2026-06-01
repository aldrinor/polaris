REVIEW DISCIPLINE (read first): this is an ACCEPTANCE-CRITERIA review of THIS brief.
Do NOT run a repo-wide grep/audit. You may open at most: the brief, the substrate map
`.codex/I-meta-005-phase-7/substrate_map.txt`, and the 3-4 named substrate files
(code_executor.py, tool_registry.py, evidence_extractor.py, provenance_generator.py).
Read, reason, emit the verdict schema. Budget your exploration tightly.

HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-meta-005 Phase 7 (#991) — Quantified trade-off + decision artifacts (gap 9, PAL rewire) — BRIEF (iter 2)

The ONLY genuinely-new capability; EXTENDS the faithfulness wedge to COMPUTED numbers.

## Iter-2 → iter-3 changelog (all 4 iter-2 P1 + 3 P2 addressed)
- **P1-1 extractor contract:** the real `extract_numbers_from_evidence()` has NO byte span;
  so a sourced input binds by `ev_id` + `literal` and is verified by NUMERIC-VERBATIM
  presence of the literal in the ev_id row's `direct_quote` (Regime-A primitive; no new
  extractor spans) — §1.1/§1.2(i).
- **P1-2 modeled schema:** a modeled input now carries `base` (scalar for canonical outputs)
  + `sweep` (sensitivity); `solve_for` MUST be a modeled var whose sweep is the solve bracket
  — §1.2/§1.3.
- **P1-3 multi-number:** SENTENCE-level keep/drop (one calc number per sentence, consistent
  with `strict_verify`); a wrong number drops only its sentence — §1.5, P7-10.
- **P1-4 dependency:** every declared input MUST appear in the formula AST (no cited input
  that does not feed the output) — §1.2(iii), P7-11.
- **P2:** `execute_quantified_model` is ASYNC; `_canonical_display` pins display formatting for
  exact-string equality + replay; conflict = same name/unit inputs disagreeing >
  `PG_CALC_CONFLICT_REL_TOL` — §3.2, P7-13/P7-14.

## Iter-1 → iter-2 changelog (all 4 P1 + 4 P2 + D1-D5 adopted)
- **P1-1 (sourced-input value+span, not ev_id-only):** each sourced input now binds to a
  CONCRETE extracted data point — `{name, value, unit, ev_id, span:[start,end]}` — and the
  input's value MUST match the cited span via the SAME Regime-A numeric-verbatim check
  (the number appears verbatim in the evidence row's direct_quote at [start,end]). An input
  whose value does not verbatim-match its cited span → spec INVALID → whole model skipped
  (D4). A bare ev_id can no longer carry a wrong value (§1.1, §2.2).
- **P1-3 (deterministic Execute — NO free LLM codegen):** the spec's `formula` is a PURE
  arithmetic expression over the declared input names (AST-whitelisted: numbers, input
  Names, + - * / **, and an allowlist of numpy/math/scipy funcs). A DETERMINISTIC
  `render_script(spec)` templates the inputs + formula into a FIXED script skeleton; it runs
  via the EXISTING `code_executor.execute_analysis_script` (sandbox unchanged). The computed
  output is provably the declared formula over the declared inputs — the executor no longer
  trusts LLM-written Python (§1.3, §3.2). (Bonus: Execute is now SPEND-FREE even on-mode —
  no code-gen LLM call; only the Model spec-gen call remains.)
- **P1-2 (one number per calc token):** each `[#calc:...]` token binds to EXACTLY ONE
  rendered number = the canonical display value of one output field (§1.4, D1).
- **P1-4 (resolver + strip):** Regime C populates the input evidence citations and STRIPS the
  calc/model tokens after verification (no token leak), mirroring
  `resolve_provenance_to_citations` (§1.5, §3.3).
- **D1 (token grammar):** single ASCII delimiter-safe calc token. **D2 (tolerance):** canonical
  display-value equality + named rel/abs backstop. **D3 (section):** dedicated "Quantified
  trade-off" section after the verified sections, before Limitations; NOT folded into
  Integrative. **D4:** whole-model-skip on any invalid input. **D5:** confirmed.
- **P2s:** ASCII grammar (no `←`); display_value equality; smoke for value/unit mismatch +
  multi-number + wrong-field + formula-ignores-inputs + token-strip + audit-replay +
  conflicting-sourced-inputs.

## 1. Pipeline — Extract → Model → Execute(deterministic) → Bind → Verify(Regime C)
1.1 **Extract**: `evidence_extractor.extract_numbers_from_evidence()` → data points each
    `{evidence_id, value, unit, context, ...}` (NOTE iter-2 P1-1: the real extractor returns
    NO byte span — `evidence_extractor.py:85,:152-159`). So a sourced input binds by
    EV_ID + RAW LITERAL, and is verified by NUMERIC-VERBATIM PRESENCE of the literal in the
    ev_id row's `direct_quote` (the existing Regime-A primitive — no new extractor spans).
1.2 **Model**: the Writer emits a JSON `ModelSpec`:
    `{model_id, title, inputs:[ {name,datapoint_ref:{ev_id,value,unit}} (sourced) | {name,base:<scalar>,unit,sweep:[lo,hi,step],modeled:true} (modeled) ], outputs:[{name,unit,display_kind,formula}], sensitivity:[{input,output}], solve_for:{var,output}? ]}`.
    **Sourced-input identity (iter-4 P1 + iter-5 P1-1 — kills wrong-quantity binding):** a
    sourced input is NOT a free literal; it REFERENCES a CONCRETE extracted datapoint from
    `sourced_numbers` by `datapoint_ref:{ev_id, label, context, value, unit}`.
    `build_quantified_spec` REQUIRES that ref to match EXACTLY ONE entry in `sourced_numbers`
    on ALL of (evidence_id, label, context, value, unit) — EXACTLY-ONE-MATCH semantics: 0
    matches OR ≥2 matches (e.g. a row that repeats the same value+unit for two different
    quantities) → REJECT (whole model skipped, fail-closed). The full extracted identity
    (label+context, which the extractor produces — `evidence_extractor.py:152-159`), not just
    value+unit, is the disambiguator. The input's computational value IS that datapoint's
    `value`; `raw_literal` (the pre-normalization string, e.g. "$1.548 billion") is carried for
    the report display + the audit trail, while `value` (1548000000.0) is what the formula uses.
    Each **output** is `{name, unit, display_kind, formula}` (iter-4 P2: per-output formula —
    one canonical number per output; sensitivity/break-even numbers are DERIVED, each named
    `<output>@<input>=<x>` / `<output>.break_even` so every rendered number has a unique field
    id) where `display_kind ∈ {number, currency, percent, ratio, count}` pins
    `_canonical_display(value, unit, display_kind)` (iter-3/4 — ONE signature everywhere) for
    deterministic + replayable display_value. A **modeled** input carries `base`, `unit`,
    `sweep`. Every input is sourced or modeled — no third category. **`build_quantified_spec(
    question, sourced_numbers, evidence_rows, *, spec_llm)` VALIDATES:** (i) every sourced
    input's `datapoint_ref` matches EXACTLY ONE entry in `sourced_numbers` on ALL of (ev_id,
    label, context, value, unit) — 0 or ≥2 matches → REJECT (iter-5 P1-1); AND (iter-6 P1-1 —
    LITERAL+SPAN for citation resolution, since the extractor emits no span) `build_quantified_
    spec` LOCATES a UNIQUE raw literal for that datapoint in the ev_id row's `direct_quote`/
    `statement` (or `context`), parses it with extractor-EQUIVALENT normalization (so a scaled
    literal "$1.548 billion" → 1548000000.0 matches the datapoint `value`/`unit` — compare the
    NORMALIZED literal, not a verbatim string-match of the normalized value), and persists
    `{literal, start, end}` on the input; if NO unique literal span exists → REJECT
    (fail-closed). The persisted span is what `ProvenanceToken`/`resolve_provenance_to_citations`
    use to cite the input. (ii) every output's `formula` is a pure arithmetic AST over the
    declared input names; (iii) **every declared input MATERIALLY affects ≥1 output —
    NUMERICALLY NORMATIVE (iter-6 P1-2):** reject any declared input whose perturb (at
    NON-DEGENERATE points — `base*(1+δ)` for nonzero base, else 1.0, to avoid false-rejecting
    `x**2`@0 / `x*y`@0) changes NO output. This is the PRIMARY gate (not AST-occurrence): it
    rejects canceling/zero-effect formulas like `irrelevant*0 + y` or `x - x + y` that cite
    inputs not affecting the number. (iv) outputs non-empty; (v) every `sensitivity[].input` is
    a MODELED name AND `sensitivity[].output` is a declared output, with finite sweep values,
    nonzero directionally-valid `step`, and finite base/formula evaluation BEFORE execution
    (iter-5 P2-2); (vi) `solve_for.var` (if present) MUST be a MODELED input whose `sweep` is
    the `[lo,hi]` solve
    bracket and `solve_for.output` is a declared output. Any violation → return None (whole
    model skipped, D4).
1.3 **Execute (DETERMINISTIC)**: `render_script(spec)` templates the validated inputs +
    per-output formulas into a fixed skeleton: sourced inputs use their datapoint `value`;
    modeled inputs use their `base` for the canonical output of each `output.formula`;
    sensitivity = each `sensitivity[]`'s output formula swept over its modeled input's `sweep`;
    break-even = `scipy.optimize.brentq(solve_for.output.formula over solve_for.var, lo, hi)`
    ONLY when the `[lo,hi]` bracket yields a sign change + finite root (D5). Run via
    `code_executor.execute_analysis_script(rendered, input_data)` — sandbox unchanged. Every
    computed number is provably the declared output formula over the declared inputs.
1.4 **Bind**: each computed number rendered in the prose carries ONE ASCII calc token
    `[#calc:<model_id>:<spec_hash>:<field>]` placed IMMEDIATELY ADJACENT to (directly after)
    the rendered computed display value (iter-6 P2 — so the verifier binds the token to the
    EXACT number, not an input/modeled number elsewhere in the sentence). (D1; one number per
    token, P1-2; `spec_hash`
    binds the token to THIS run's model — iter-5 P1-2, prevents stale/colliding model_ids).
    `<field>` addresses EVERY computed number: an output (`<output>`), a sensitivity point
    (`<output>@<input>=<x>`), or a break-even (`<output>.break_even`). Modeled inputs labeled
    "(modeled assumption)" inline. EVERY computed field's canonical `display_value` (outputs +
    sensitivity points + break-even) + the spec + rendered script + `spec_hash` persist to
    `outputs/.../quantified_model.json` (iter-5 P2-1; gap-19 replay).
1.5 **Verify (Regime C) — SENTENCE-LEVEL (iter-2 P1-3, consistent with `strict_verify`)**: the
    binder emits AT MOST ONE calc number per sentence, so the unit of keep/drop is the
    SENTENCE. The CURRENT run's quantified model(s) reach verification via an explicit
    `quantified_models` registry threaded into `strict_verify` (iter-5 P1-2 — NOT a global;
    keyed by `(model_id, spec_hash)`). A sentence carrying a `[#calc:...]` token is
    force-routed (before Regime A) to `verify_modeled_atom`: (a) `(model_id, spec_hash, field)`
    resolves in the run-scoped registry (a stale/foreign model_id or spec_hash → FAIL); (b) the
    rendered number == that field's canonical `display_value` (D2: exact display-string match;
    named `PG_CALC_EQ_REL_TOL`/`PG_CALC_EQ_ABS_TOL` numeric backstop); (c) every `modeled=`
    input used is labeled "(modeled assumption)" in the sentence; (d) every sourced input of
    the model was verified at §1.2(i). PASS → `verify_modeled_atom` RETURNS the source-input
    `ProvenanceToken`s so `resolve_provenance_to_citations` cites the inputs, then STRIP the
    calc token (iter-5 P1-2 / P1-4). FAIL any → DROP the whole SENTENCE. Fail-closed. (A
    multi-number paragraph is multiple one-calc sentences; a wrong number drops only ITS
    sentence — P7-10.)

## 2. HARD CONSTRAINTS
1. `PG_ENABLE_QUANTIFIED_ANALYSIS` (default OFF). OFF byte-identical (no PAL import/run;
   report+manifest unchanged).
2. Fail-closed: a sourced input's `literal` MUST be numeric-verbatim present in its ev_id row's
   `direct_quote`/`statement` AND parse to its `value`; whole model skipped on any invalid
   input (D4); a computed number ≠ its executed display_value is DROPPED; an unlabeled modeled
   assumption is DROPPED. No LLM-generated number in the verified core.
3. Sandbox unchanged (reuse `_validate_ast`/`execute_analysis_script`); do NOT widen the
   allowlist. The `formula` AST-whitelist is an ADDITIONAL gate, not a sandbox change.
4. Zero new served model. Execute is deterministic (no codegen LLM); only Model spec-gen calls
   the existing generator family. Regime C is pure (no LLM).
5. Money: BUILD + SMOKE spend-free (deterministic render_script + execute_analysis_script on
   FIXED specs/scripts; the Model spec-gen LLM call is faked/injected in tests; assert no live
   client). ON-mode only the Model spec-gen bills (operator-gated).
6. snake_case; no unittest.mock in src/; explicit imports; tolerances are named constants/env.

## 3. FILE-BY-FILE
1. **NEW `src/polaris_graph/synthesis/tradeoff_modeler.py`**: `ModelSpec` dataclass +
   `build_quantified_spec(question, sourced_numbers, evidence_rows, *, spec_llm) -> ModelSpec
   | None` (iter-3 P1-1: `evidence_rows` so it can look up each ev_id's `direct_quote`/
   `statement` to verify the input literal; Writer spec-gen + §1.2 validation incl. the
   literal numeric-verbatim check, the formula AST whitelist, and the NUMERIC dependency
   check) + `render_script(spec) -> str` (deterministic template) + `_validate_formula_ast` +
   `_canonical_display(value, unit, display_kind)`.
2. **NEW `src/polaris_graph/generator/quantified_analysis.py`**:
   `async def execute_quantified_model(spec, evidence_rows) -> QuantifiedResult | None`
   (ASYNC — `execute_analysis_script` is async, iter-2 P2; render_script → await
   execute_analysis_script → parse outputs → compute per-output canonical `display_value` via
   a PINNED formatter `_canonical_display(value, unit, display_kind)` (fixed per-display_kind format rule so the
   exact-string equality + audit replay are deterministic) → persist quantified_model.json) +
   `bind_calc_tokens(prose, result)` (attach one calc token per rendered number; one number
   per sentence).
3. **`src/polaris_graph/generator/provenance_generator.py`**: `strict_verify` (and
   `verify_sentence_provenance`) gain an OPTIONAL `quantified_models: dict[(model_id,spec_hash)
   -> QuantifiedResult] | None = None` param (iter-5 P1-2 — default None = OFF/legacy
   byte-identical; the existing signature is preserved additively). Regime C router (detect
   `[#calc:]` before Regime A) + `verify_modeled_atom` (§1.5; resolves the calc token against
   `quantified_models`, returns source-input `ProvenanceToken`s) + token-strip on PASS. Regime
   A unchanged.
4. **`scripts/run_honest_sweep_r3.py`**: gate `PG_ENABLE_QUANTIFIED_ANALYSIS`; ON-mode after
   verified sections run the pipeline, build the run-scoped `quantified_models` registry, pass
   it into `strict_verify` for the Quantified-trade-off section, render that dedicated verified
   section (D3, before Limitations), persist quantified_model.json + manifest
   `quantified_analysis` telemetry (incl. conflicting-sourced-input flag). OFF unchanged
   (`quantified_models=None`).

## 4. GREEN (exit, #991)
- decision matrix + break-even/sensitivity where corpus supports; skipped cleanly otherwise.
- every computed number == its executed display_value (equality-verified) and traces to
  verified-literal sourced inputs (literal numeric-verbatim in direct_quote/statement) or labeled modeled assumptions; modeled-vs-sourced labeled.
- a wrong computed number / wrong-value sourced input / unlabeled modeled assumption is DROPPED.
- quantified conflicts (two sourced inputs for the same quantity disagree) surfaced + flagged.
- OFF byte-identical; sandbox unchanged; deterministic Execute (no codegen LLM); zero new model.

## 5. SMOKE (`tests/polaris_graph/synthesis/test_quantified_tradeoff_phase7.py`) — SPEND-FREE
- P7-1 OFF byte-identity. P7-2 sandbox unchanged (os/subprocess/socket script REJECTED).
- P7-3 deterministic Execute: render_script(spec)+execute_analysis_script computes the formula
  correctly, NO live client.
- P7-4 Regime C PASS (rendered == display_value, every sourced input literal verified in direct_quote/statement, modeled labeled).
- P7-5 Regime C FAIL on number ≠ display_value → DROP.
- P7-6 a sourced input `literal` is NOT numeric-verbatim present in its ev_id row's
  direct_quote/statement (wrong value attached to a real ev_id) → build_quantified_spec
  returns None (whole model skipped, fail-closed).
- P7-7 modeled assumption unlabeled → DROP. P7-8 labeled → VERIFIED.
- P7-9 input neither sourced nor modeled → None (fail-closed).
- P7-10 multi-number paragraph = one calc-number per SENTENCE; a wrong number drops only ITS
  sentence (the other sentences/numbers survive) — sentence-level, consistent with strict_verify.
- P7-11 formula AST rejects a non-arithmetic / disallowed-call formula → None; AND rejects a
  spec where a declared input is NOT in the formula dependency path (iter-2 P1-4) → None.
- P7-12 calc-token STRIP after verify (no token leak in verified_text).
- P7-13 conflict telemetry: two sourced inputs for the SAME quantity (same name/unit) whose
  values disagree by > `PG_CALC_CONFLICT_REL_TOL` (named) → flagged in manifest telemetry.
- P7-14 audit replay: quantified_model.json round-trips; `spec_hash` + per-output canonical
  `display_value` stable (exact-string).
- P7-15 modeled input base + sweep: canonical output uses `base`; sensitivity sweeps `sweep`;
  break-even only when `solve_for`'s bracket has a sign change (iter-2 P1-2).
- P7-16 (iter-6 P1-1) raw-literal recovery with a SCALED literal: a datapoint value
  1548000000.0 whose evidence says "$1.548 billion" → the unique literal is located, normalized
  to the value, and `{literal,start,end}` persisted; a value with NO unique literal span in the
  evidence → build_quantified_spec returns None (fail-closed).
- P7-17 (iter-5 P1-1) exact-one-match: a row REPEATING the same value+unit for two different
  quantities → ≥2 datapoint matches → REJECT (no wrong-quantity binding).
- P7-18 (iter-6 P1-2) cancellation/zero-effect dependency: `x - x + y` / `irrelevant*0 + y`
  citing a non-affecting input → REJECTED by the numeric perturb gate.
- P7-19 (iter-5 P1-2) run-scoped lookup: a calc token with a STALE/foreign `(model_id,
  spec_hash)` not in the run's `quantified_models` registry → Regime C FAIL → sentence dropped.
- P7-20 token adjacency: a calc token binds to the number it immediately follows, not a
  modeled/input number elsewhere in the sentence (iter-6 P2).
Then a generator/provenance regression subset (OFF byte-identity + Regime A unchanged).

(NOTE: this brief SUPERSEDES the substrate map `.codex/I-meta-005-phase-7/substrate_map.txt`
for the token grammar `[#calc:model_id:spec_hash:field]` + the DETERMINISTIC render_script
path; the map's older `[#model...]`/LLM-codegen references are stale — iter-6 P2.)

## 6. Output schema (REQUIRED)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
