HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Output schema (return EXACTLY this, no prose verdict):
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

---

# DIFF gate — I-cap-002 feature 4/4 (#1060): NLI entailment additive advisory annotation

DIFF gate. Review the committed code against the brief (`.codex/I-cap-002-nli/brief.md`, brief-gate
APPROVE iter-1 in `codex_brief_verdict.txt`). Patch: `.codex/I-cap-002-nli/codex_diff.patch` (branch
`bot/I-cap-002-nli` on `bot/I-cap-002-agentic`). **#1 thing to red-team: NO silent degrade — an
unavailable model must surface, never read as a clean pass.**

## What the diff does (5 files, +364)
1. **NEW `src/polaris_graph/retrieval/nli_benchmark_annotator.py`** (torch-free import — heavy deps lazy):
   - `NliUnavailableError`.
   - `build_nli_pairs(kept_sentences, ev_pool)` — PURE. Cleans the sentence with `strip_tokens`
     (brief-gate P2.1 — `[#ev:...]` won't be in the claim) and concatenates ALL cited spans per sentence
     (P2.2); resolves span text from the ev row via the `full_text/snippet/direct_quote/…` preference
     (mirrors `provenance.get_span_text`); skips sentences with no clean claim or no resolvable span.
   - `annotate_nli_entailment(pairs, *, threshold)` — lazy-imports `nli_verifier.load_nli_model`; RAISES
     `NliUnavailableError` if the model is None OR exposes neither `.score`/`.infer` (brief-gate P2.3 —
     MiniCheck `.score` AND FaithLens `.infer` both handled). Returns `{nli_status:"ok", model,
     sentences_checked, disputed_count, disputed:[…], min_prob, mean_prob, threshold, advisory:True}`.
2. **`run_honest_sweep_r3.py`** — advisory block AFTER the depth annotation, BEFORE the manifest write
   (status/release final), flag-gated `PG_NLI_IN_BENCHMARK` default OFF. Builds `kept_sentences` from
   `multi.sections[].kept_sentences_pre_resolve` (sv.sentence + sv.tokens), calls `build_nli_pairs` +
   `annotate_nli_entailment`, writes `nli_verification.json` then stamps `manifest['nli_verification']`.
   - `except NliUnavailableError` → loud log + `manifest['nli_verification']={"nli_status":"unavailable",…}`
     (surfaced, NOT silent). `except Exception` → `nli_status:"error"` (transient fault, advisory). Never
     mutates status/release_allowed/abort.
3. **`run_gate_b.py`** — `setdefault("PG_NLI_IN_BENCHMARK","1")` + `setdefault("PG_NLI_MODEL","flan-t5-large")`.
4. **Tests** (offline, scorer MOCKED — no torch): pair clean+multi-span concat; ok-path disputed
   detection; FaithLens `.infer`; model-None RAISES (not silent); empty-pairs ok; activation flag asserted.

## Red-team checklist — please confirm
- **No silent degrade (THE one):** model unavailable → `NliUnavailableError` → `nli_status:"unavailable"`
  surfaced in manifest + loud log. Is there ANY path where a missing/failed model yields an empty/clean
  `nli_verification` that reads as "NLI verified"? (The annotator raises; the block records unavailable.)
- **Advisory/non-gating:** the block only ADDS `manifest['nli_verification']` + sidecar; it never touches
  `status`/`release_allowed`/abort. Placed after they are final.
- **Faithfulness direction:** NLI scores span⊨sentence on ALREADY-delivered sentences; it produces no
  evidence and can only FLAG. Confirm it cannot inject/alter content.
- **Torch isolation:** the new module imports nothing heavy at module load (only `provenance` helpers);
  `load_nli_model` is imported lazily inside the async fn. Confirmed by a torch-free-import smoke.
- **Pair correctness:** does `build_nli_pairs` correctly strip tokens (P2.1) and concatenate all cited
  spans (P2.2)? Any span-resolution bug (wrong field, bad offset bounds) that would mis-score? Is
  skipping a sentence with no resolvable span the right call (vs disputing it)?
- **Flag OFF → byte-unchanged:** with `PG_NLI_IN_BENCHMARK` unset, is the block fully skipped (manifest
  identical to feature-3 HEAD)?
- **`.score`/`.infer` selection:** is `hasattr(scorer,'score')` then `hasattr(scorer,'infer')` the right
  precedence, matching `nli_verifier`'s own MiniCheck/FaithLens branching?

## Smoke evidence (offline, already run)
- torch-free import: `import nli_benchmark_annotator` → `torch` NOT in `sys.modules`.
- `pytest tests/polaris_graph/test_nli_benchmark_annotator.py tests/dr_benchmark/test_benchmark_stack_activation_meta007.py` → 10 passed.
- `pytest tests/dr_benchmark/` → 233 passed. `py_compile` + `ast.parse` on `run_honest_sweep_r3.py` → OK.
- (The live flan-t5-large run is the Tier-A VM run — §8.4 forbids loading the model in the dev loop.)

## Acceptance (GREEN)
Zero NOVEL/continuing P0, zero P1. The feature is flag-OFF-default + advisory + fail-LOUD-on-unavailable +
torch-isolated, so any residual concern about NLI threshold tuning / span heuristics is at most P2.

---

## ITER-2 CHANGELOG (your iter-1 REQUEST_CHANGES — all addressed in the patch above)
- **P1 FIXED:** all NLI setup (import, `PG_NLI_DISPUTE_THRESHOLD` float parse, pair build) is now INSIDE
  fail-open guards. Import failure → `nli_status:"error"` (separate `try`); threshold/build/annotate fault →
  `nli_status:"error"`; `NliUnavailableError` → `unavailable`. Nothing in the block can abort `run_one_query`.
- **P2.1 FIXED:** `_SPAN_TEXT_FIELDS` now tries `direct_quote`/`statement` BEFORE `full_text`/`snippet`.
- **P2.2 FIXED:** the result records `eligible_sentences` + `skipped_no_span` (also on unavailable/error).
- **P2.3 FIXED:** `build_nli_pairs` strips `[#calc:...]` + `(atom_NNN)` in addition to `[#ev:...]`.
- Tests added: calc/atom strip; `direct_quote` preferred over `full_text` for the span. 12/12 pass.
