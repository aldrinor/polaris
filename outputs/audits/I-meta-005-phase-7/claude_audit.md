# Claude architect audit — I-meta-005 Phase 7 (#991): verifiable quantified trade-off

**Scope:** the gap-9 PAL rewire — extend the faithfulness wedge to COMPUTED numbers.
**The wedge invariant:** no FALSE computed number may reach `verified_text`. A number
survives ONLY if it is provably the declared output formula over declared,
evidence-verified inputs, computed deterministically in the sandbox.

## Chain-of-custody, end to end (where a false number would have to slip through)

1. **Extract** — `evidence_extractor.extract_numbers_from_evidence` (UNCHANGED). Real
   datapoints: evidence_id/label/value/unit/context.
2. **Model** — the Writer emits a raw JSON spec. `build_quantified_spec` is the
   gatekeeper:
   - **Sourced identity:** a sourced input must match EXACTLY ONE datapoint on ALL of
     (ev_id,label,context,value,unit). 0 or >=2 → reject. A repeated value for two
     different quantities cannot bind to the wrong one (P7-17).
   - **Literal + span:** the value's UNIQUE raw literal is located in the ev row's
     direct_quote/statement (or context) via extractor-equivalent normalization
     (scaled "$1.548 billion" → 1.548e9). No unique span → reject (P7-6, P7-16). A
     value not present in the cited evidence cannot become an input.
   - **Formula AST:** pure arithmetic over declared input names + a math allowlist
     (`_formula_names`). No attribute/subscript/comprehension/arbitrary call (P7-11).
   - **Material dependency (PRIMARY, numeric):** every declared input, perturbed at a
     non-degenerate point, must move ≥1 output, else reject. This kills canceling
     formulas (`x-x+y`, `irrelevant*0+y`) that cite a non-affecting input (P7-18) — a
     stricter gate than AST-occurrence.
3. **Execute (deterministic)** — `render_script` templates one `def _f_<out>(...)`
   per output returning the declared formula verbatim, base inputs as literals,
   sensitivity sweeps, brentq break-even only on a sign change. NO codegen LLM. The
   rendered script is re-validated by the UNCHANGED `validate_script`/`_validate_ast`
   (P7-2, P7-3). The executed number IS the declared formula over the declared inputs.
4. **Bind** — `bind_calc_tokens` renders the field's canonical `display_value`
   IMMEDIATELY followed by `[#calc:model_id:spec_hash:field]`.
5. **Verify (Regime C)** — `verify_modeled_atom`:
   - (model_id,spec_hash) must resolve in the RUN-SCOPED registry — stale/foreign →
     drop (P7-19). spec_hash binds the token to THIS run's model.
   - the number IMMEDIATELY before the token == the field's `display_value`
     (exact-string OR numeric backstop rel/abs 1e-9). Adjacency means a correct value
     elsewhere in the sentence cannot rescue a wrong adjacent number (P7-20).
   - every modeled input USED is labeled "(modeled assumption)" (P7-7/P7-8).
   - sourced inputs resolve in the pool; PASS returns the SOURCE-input ProvenanceTokens
     so resolve cites the inputs; the calc token is stripped (P7-12, no leak).
   - **Fail-closed sentence shape:** >1 calc token → drop; mixed `[#calc:]`+`[#ev:]` →
     drop (would launder an unverified Regime-A claim) — P7-21/P7-22.

## Adversarial probes run (each is a smoke assertion, not a claim)
- Wrong number adjacent to a correct token → DROP (P7-5, P7-20).
- Value not numeric-verbatim in the evidence → model skipped (P7-6).
- Duplicate datapoint identity → model skipped (P7-17).
- Cancellation / zero-effect dependency → model skipped (P7-18).
- Stale/foreign model reference → DROP (P7-19).
- Multiple calc numbers / mixed ev+calc in one sentence → DROP (P7-21/P7-22).
- Unlabeled modeled assumption → DROP (P7-7).
- Sandbox still rejects os/socket/subprocess; rendered script accepted (P7-2).
- Audit replay round-trips; spec_hash + display_value stable exact-string (P7-14).
- OFF byte-identity: strict_verify with/without the param identical (P7-1); sweep
  block + manifest key gated.

## OFF byte-identity wall
`quantified_models=None` (default) skips the Regime C router entirely → Regime A
unchanged. `_verifier_cleaned_text` + `resolve` gained a calc-token strip that is a
no-op when no calc token is present. The sweep block is `PG_ENABLE_QUANTIFIED_ANALYSIS`-
gated; `manifest["quantified_analysis"]` is added ON-mode only. No new served model;
Execute is spend-free (deterministic); only the Model spec-gen Writer call bills,
operator-gated (Phase 8).

## Honest residuals (classified, surfaced to Codex)
- **Modeled-label gate** requires the literal "(modeled assumption)" present once when
  the field uses modeled inputs, NOT per-input naming. The NUMBER is still
  executor-correct; this is disclosure completeness, not a false-number hole. P2/P3.
- **Perturb dependency** is point-perturbation; a piecewise-clamped input (e.g.
  `max(x,5)` at x<5) could be rejected as non-affecting at that operating point. This
  affects only whether a model is BUILT, never whether a false number SURVIVES. P2/P3.
- **Live Writer spec-gen + JSON parse** (`_q_spec_provider`) is the one seam not
  exercised spend-free; it is defensively wrapped (any failure → skip section, never
  abort) and first runs under the operator-gated Phase 8.

**Architect verdict:** the wedge holds across the audited paths; no false-number path
found. Two architect-found laundering vectors (mixed-token, multi-calc) were closed
before submission. Routing the diff to the Codex gate as the authority.
