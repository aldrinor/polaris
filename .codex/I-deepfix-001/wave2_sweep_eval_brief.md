HARD ITERATION CAP: 5 per document. This is iter 2 of 5 (FOCUSED RE-VERIFY).
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

REVIEW MODE: STATIC, FOCUSED. Iter-1 found 3 P1 + 2 P2; all fixed. Read `.codex/I-deepfix-001/wave2_sweep_eval.patch` + the changed regions and verify the FIXES below first; then a quick scan for any NOVEL P0/P1. No pytest/pipeline. Emit the schema at the end.

## CHANGES SINCE ITER 1 (verify these)
- **P1-A (B6b dropped whole basket) FIXED** scripts/run_honest_sweep_r3.py (~2434): the claim-shape gate no longer `continue`s (which suppressed the whole basket incl. SUPPORT lines). It now sets a `suppress_claim_header` flag → the header renders as `f"- {count} verified independent source(s):"` (no garbled claim text) while EVERY SUPPORT / GROUNDED-BUT-WEAK / CONTRADICTED sub-bullet + count STILL render. The wave-2 test now asserts the SUPPORT url IS present (only the garbled header text is gone). Verify: §-1.3 header-text-only, no source/count dropped.
- **P1-B (B3 missed Gate-B paths) FIXED** scripts/run_honest_sweep_r3.py: `_clean_question` is now threaded into the FS-Researcher scope-context, both FS/Iter seeds, CRAG derive_gap_queries, the CRAG no-gap fallback (`[_clean_question]`), the CRAG loop-back run_live_retrieval, and the R6 expansion run_live_retrieval. NOTE the iter-1 run_gate_b.py:1236/1241 refs were STALE (env-slate dict entries, not seeds); run_gate_b hands `q` wholesale to run_one_query which computes `_clean_question` from the intent frame, so Gate-B is fixed TRANSITIVELY by the run_one_query edits — no run_gate_b.py change. Verify: no remaining query-derived retrieval seed uses raw q["question"]; raw protocol question stays immutable.
- **P1-C (B4 green badge on same-family) FIXED**: run_honest_sweep_r3.py (~14481) now persists a `manifest['models']` block (generator/evaluator model+family + permit_same_family + family_segregated=(gen_family!=eval_family)); src/polaris_v6/api/artifact_to_slice_chain.py derives the badge from that block (deterministic strict_verify verifier ⇒ True; same-family LLM ⇒ False; absent/unknown ⇒ conservative False) — the strict_verify_v1 fallback that faked segregation is removed. (clinical_generator already honest — its evaluator genuinely IS the deterministic verifier.) Verify: a same-family all-GLM run CANNOT render a green segregated badge; no `family_segregation_passed=True` literal.
- **P2-A (B11 C2 discard valid slow response) FIXED** src/polaris_graph/roles/openrouter_role_transport.py: new pure `_nonignored_provider_remains()`; the min-tok/s slow-rotate only force-closes when ANOTHER non-ignored provider remains, else KEEPS the valid slow verdict (fail-open).
- **P2-B (name-only PT03 on legacy callers) FIXED** src/polaris_graph/evaluator/external_evaluator.py: the unknown-family fallback now FAILS PT03 unless the evaluator is the deterministic strict_verify verifier (`_PT03_DETERMINISTIC_VERIFIER_LABELS`); scripts/regate_v23.py now threads gen/eval families.
- Verified offline by the fix author: 23/23 standalone + 4/4 build_slice_chain badge checks; py_compile all; CRLF preserved on run_honest_sweep.

## (Original iter-1 brief context follows.)
REVIEW MODE: STATIC ONLY. Read `.codex/I-deepfix-001/wave2_sweep_eval.patch` + changed regions only. No pytest/pipeline.

# I-deepfix-001 WAVE 2 — WIRER-SWEEP-EVAL: run-script + evaluator + transport seams

Files: run_honest_sweep_r3.py (CRLF), external_evaluator.py, provider_routing.py (CRLF), openrouter_role_transport.py, clinical_generator/generator.py, polaris_v6/api/artifact_to_slice_chain.py, config/settings/openrouter_provider_routing.yaml (CRLF) + test.

## Seams wired
- **B3** clean-question substitution: when run_intent_frame fires, build a clean question (directive appendix stripped) and substitute it at the decompose + retrieval sites; protocol.json raw question stays IMMUTABLE.
- **B7** pass evidence_rows to assess_corpus_adequacy at all call sites (the kw-only param WIRER-RETRIEVE added) so the on_topic denominator fires.
- **B6(b)** claim-shape gate before emitting a corroboration basket HEADER in the render-corroboration block: skip a header whose claim is chrome/unrenderable OR lacks a predicate/verb + min content words (PG_CLAIM_SHAPE_GATE default-ON). Faithfulness-neutral render gate (drops a malformed HEADER line, never a source/finding).
- **B4** PT03 honest two-family check in external_evaluator: PT03 passes iff evaluator_model disclosed in report AND (gen_family != eval_family OR (PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY truthy AND the report honestly discloses non-segregation)). Matches the wave-1 Methods substrings "not family-segregated" / "same family '<fam>'" / "self-bias safeguard disabled". Also fixes the UI badge (artifact_to_slice_chain.py:334) + clinical_generator.py hardcode so a same-family run does NOT render a green "segregated" badge.
- **B11 C1** provider SLO prefs in provider_routing.apply_provider_routing: inject provider_block preferred_min_throughput + preferred_max_latency from per-role config (no-op when absent; PG_OPENROUTER_PROVIDER_SLO). Config yaml per-role keys.
- **B11 C2** min-tok/s slow-trickle force-close in openrouter_role_transport (PG_ROLE_MIN_TPS): if observed tok/s < threshold, force-close early reusing the EXISTING force-close so it re-enters the wired provider rotation — this is the part that flips adjudicated False->True on a trickle.
- **P2b** serialize intent_frame.constraints into summary + manifest (auditability).

## VERIFY HARDEST (adversarial)
1. **B4 disclosure HONESTY (clinical-safety P1 if wrong):** confirm PT03 + the UI badge + clinical hardcode now report non-segregation HONESTLY on a same-family (all-GLM) run — they must NOT assert "separate family"/green-segregated when gen_family == eval_family. Confirm the same-family PASS requires BOTH the permit flag AND an honest in-report disclosure (it must not silently hard-pass an undisclosed same-family run). Confirm the matched substrings are byte-consistent with the wave-1 Methods clause.
2. **B3 raw-question immutability:** confirm protocol.json's raw question is never mutated; only the in-memory decompose/retrieval input uses the cleaned text.
3. **B6(b) render-only:** confirm the claim-shape gate skips only a malformed basket HEADER line, never a SUPPORT source or a verified finding; fail-open (a gate error emits the header rather than dropping content).
4. **B11 faithfulness-neutral:** confirm provider-SLO + min-tok/s force-close are TRANSPORT reliability only (steer/retry to a healthy host) — they must not change any verdict, drop content, or relax a faithfulness check. Confirm C2 reuses the EXISTING force-close + rotation (no new un-bounded loop / no new hang class) and is bounded by the existing total deadline.
5. **B7 call-site parity:** confirm evidence_rows is passed as the kw-only param at every assess_corpus_adequacy call without changing the function's contract.
6. **CRLF:** run_honest_sweep_r3.py + provider_routing.py + the yaml are CRLF-in-HEAD; confirm the diff is a real partial change, not a whole-file EOL flip.
7. **No faithfulness-engine edit:** strict_verify / NLI / span / 4-role / provenance untouched.

## Output schema (REQUIRED, last lines)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
