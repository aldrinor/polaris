HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

REVIEW DISCIPLINE (read first): this is a DIFF review of the Phase-7 implementation
against the APPROVED brief `.codex/I-meta-005-phase-7/brief.md`. Do NOT run a
repo-wide grep/audit. Open at most: this brief, `.codex/I-meta-005-phase-7/brief.md`,
the diff `.codex/I-meta-005-phase-7/codex_diff.patch`, and the 5 changed files if you
need full context (tradeoff_modeler.py, quantified_analysis.py, provenance_generator.py,
run_honest_sweep_r3.py block, test_quantified_tradeoff_phase7.py). Budget exploration
tightly. Emit the verdict schema.

# I-meta-005 Phase 7 (#991) — DIFF review: verifiable quantified trade-off (gap 9, PAL rewire)

## THE ONE QUESTION
This phase extends the faithfulness wedge to COMPUTED numbers. The wedge holds iff
**no FALSE computed number can survive verification**. Hunt for any path where a
number that is NOT the declared formula over declared, evidence-verified inputs
reaches `verified_text`. That is the only P0/P1 class that matters here. Everything
else is P2/P3.

## What the diff implements (verify against the brief)
1. **`synthesis/tradeoff_modeler.py`** (NEW):
   - `build_quantified_spec(question, sourced_numbers, evidence_rows, *, spec_llm)`:
     (i) each SOURCED input's `datapoint_ref` must match EXACTLY ONE entry in
     `sourced_numbers` on ALL of (evidence_id,label,context,value,unit) — 0 or >=2 ->
     None; AND a UNIQUE raw literal for that value is located in the ev row's
     direct_quote/statement (or context) via extractor-equivalent normalization
     (scaled literal "$1.548 billion" -> 1548000000.0), persisting {literal,start,end};
     no unique literal span -> None.
     (ii) every output `formula` is a pure-arithmetic AST (`_formula_names`) over the
     declared input names + an allowlist of math funcs; anything else -> None.
     (iii) **NUMERIC material-dependency perturb gate (PRIMARY)**: every declared input,
     perturbed at a non-degenerate point, must move >=1 output; else -> None (rejects
     `x - x + y`, `irrelevant*0 + y`).
     (iv) outputs non-empty; (v) sensitivity well-formedness; (vi) solve_for bracket.
   - `render_script(spec)`: DETERMINISTIC template — one `def _f_<out>(<all inputs>):
     return (<formula>)` per output, base inputs assigned as literals, outputs +
     sensitivity-sweep + brentq break-even (only on sign change) computed, JSON to
     stdout. NO codegen LLM. Runs via the EXISTING `code_executor.execute_analysis_script`
     (sandbox unchanged; the rendered script is re-validated by `validate_script`).
   - `_canonical_display(value,unit,display_kind)`: the ONE pinned formatter.
   - `_eval_formula`: a tiny AST interpreter (NO `eval`) used by the perturb gate.
2. **`generator/quantified_analysis.py`** (NEW):
   - `execute_quantified_model` (async): render -> execute -> pin per-field
     `display_value` + `modeled_used` + `sourced_tokens` -> persist quantified_model.json.
   - `bind_calc_tokens`: `{{calc:<field>}}` -> `<display_value>[#calc:model_id:spec_hash:field]`
     (token IMMEDIATELY adjacent to the number).
   - `detect_sourced_conflicts`: same-(label,unit) datapoints disagreeing > rel tol.
   - `render_decision_matrix_prose`: deterministic one-calc-per-sentence prose with
     `{{calc:}}` placeholders + "(modeled assumption)" labels (NOT an LLM call).
   - `run_quantified_section` (async): Extract -> (async `spec_provider` = the ONLY
     billed Writer call) -> build -> execute -> bind -> strict_verify(Regime C) ->
     resolve -> verified section + telemetry.
3. **`generator/provenance_generator.py`** (Regime C, additive):
   - `_CALC_TOKEN_RE`, `verify_modeled_atom`, router at the TOP of
     `verify_sentence_provenance` (BEFORE Regime A): if `quantified_models` is provided
     AND a `[#calc:]` token is present — fail-closed if >1 calc token OR a mixed
     `[#ev:]` token in the same sentence; else route to `verify_modeled_atom`.
   - `verify_modeled_atom` checks: (a) (model_id,spec_hash) in the RUN-SCOPED registry;
     (b) field exists; (c) the number IMMEDIATELY before the token == the field's
     canonical display_value (exact-string OR tight numeric backstop, tol 1e-9);
     (d) every modeled input USED is labeled "(modeled assumption)"; (e) sourced inputs
     resolve in the pool. PASS returns the SOURCE-input ProvenanceTokens (so resolve
     cites the inputs); the calc token is stripped in `resolve_provenance_to_citations`
     + `_verifier_cleaned_text`.
   - `strict_verify` gains optional `quantified_models=None` (default None = OFF
     byte-identical; Regime A untouched).
4. **`scripts/run_honest_sweep_r3.py`**: `PG_ENABLE_QUANTIFIED_ANALYSIS`-gated block
   (default OFF -> skipped, report+manifest byte-identical) that builds the run-scoped
   registry, appends the verified section before Limitations, and adds
   `manifest["quantified_analysis"]` ON-mode only.

## Adjacent files I ALSO checked and they're clean
- `code_executor.execute_analysis_script` / `validate_script` / `_validate_ast`:
  UNCHANGED. The rendered script passes the unchanged validator (P7-2) and os/socket/
  subprocess are still rejected.
- `evidence_extractor.extract_numbers_from_evidence`: UNCHANGED (still returns
  evidence_id/label/value/unit/context; my code reads those keys).
- Regime A (`verify_sentence_provenance` body below the router): UNCHANGED — the calc
  branch returns before it; `quantified_models=None` skips the router entirely.
- `resolve_provenance_to_citations`: only ADDED a `_CALC_TOKEN_RE.sub("")` strip;
  the `[#ev:]` strip + bibliography numbering path is unchanged.
- crown_jewels CJ-002/003/004 (provenance/strict_verify/zero-verified-abort) all green.

## Evidence (offline, spend-free)
- `tests/polaris_graph/synthesis/test_quantified_tradeoff_phase7.py`: 27 cases
  (P7-1..P7-22 + sweep orchestrator end-to-end + canonical-display) — ALL PASS.
  Key adversarial ones: P7-5 wrong number dropped; P7-6 literal-not-in-evidence ->
  None; P7-17 duplicate datapoint -> None; P7-18 cancellation formula -> None;
  P7-19 stale model_id -> drop; P7-20 token adjacency (correct value earlier, wrong
  value adjacent -> drop); P7-21 multi-calc -> drop; P7-22 mixed calc+ev -> drop.
- Regression: generator (32) + synthesis (40) + crown_jewels (47) = 126 green.
- OFF byte-identity: P7-1 asserts strict_verify with/without the param is identical;
  the sweep block + manifest key are gated.

## Architect adversarial findings ALREADY FIXED in this diff (verify they hold)
- Mixed `[#calc:]`+`[#ev:]` sentence would launder an unverified Regime-A claim ->
  now fail-closed dropped (P7-22).
- >1 calc token per sentence would leave the 2nd+ number unverified -> now fail-closed
  dropped (P7-21).

## Specifically pressure-test (front-load any P0/P1)
1. Can the adjacency check (`_CALC_ADJACENT_NUMBER_RE` = number at end of pre-token
   text; exact-string `before.endswith(display_value)` OR numeric backstop) be fooled
   into binding the token to a CORRECT number when the adjacent rendered number is
   actually WRONG? (P7-20 says no — confirm the regex + the OR logic.)
2. Is the numeric backstop (`_is_calc_equal`, rel/abs 1e-9) loose enough that a
   genuinely different number could pass? (It should be far too tight.)
3. Does `render_script` inline the declared formula faithfully such that the executed
   number IS the declared formula (no divergence between what's verified and what's
   computed)? Any way the Writer-influenced spec fields (formula/sweep/solve_for) reach
   the rendered script unvalidated?
4. The perturb dependency gate uses point-perturbation `base*(1+1e-3)`. Does any
   reachable spec let a cited input that does NOT affect the output survive? (Note the
   known piecewise-clamp edge — classify P2/P3 if it only affects whether a model is
   BUILT, not whether a false number SURVIVES.)
5. OFF byte-identity: is there ANY code path where `quantified_models=None` changes
   Regime A output, or where the OFF sweep adds the manifest key / changes report bytes?
6. Modeled-label gate requires the literal "(modeled assumption)" present once when
   `modeled_used` is non-empty (not per-input). Is one-label-present sufficient
   disclosure, or is per-input naming a real requirement? (Classify honestly — the
   NUMBER is still executor-correct; this is a disclosure-completeness question.)

## Output schema (REQUIRED)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
