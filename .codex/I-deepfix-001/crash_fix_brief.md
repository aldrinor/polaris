HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex diff gate — I-deepfix-001 (#1344): W10 consolidation-NLI CUBLAS-OOM crash fix

## The bug (traced from 3 crashed clinical runs drb_75/76/78; drb_72 workforce was clean)
The W10 consolidation-NLI cross-encoder (`cross-encoder/nli-deberta-v3-base`, `PG_CONSOLIDATION_NLI` winner, force-ON at run_gate_b.py:1355) crashes the run with `CUDA error: CUBLAS_STATUS_ALLOC_FAILED` during the fact-dedup/consolidation step on LARGE clinical corpora (890+ source/claim clusters). The `Batches: 0/32` log then `[multi_section] GH#423 fact_dedup pass failed` immediately precede it. It scales with corpus size and only bites the big clinical corpora (drb_72 at ~790 stayed under).

Two independent causes, both in `src/polaris_graph/synthesis/consolidation_nli.py`:
1. UNBOUNDED per-forward batch: `score_pairs` split pairs into only `min(workers=8, len(pairs))` chunks, so `chunk_size` GREW without bound with corpus size (~2500 pairs -> a ~5000-tuple `.predict`), run 8-wide concurrently on the cuda:0 card that already holds the Qwen3-Embedding-8B (~15GB) + Qwen3-Reranker-4B (~8GB) + W5 0.6B + NLI encoders. On the 890+ corpora a value-bucket tips the card over.
2. FALSE-GREEN degrade: fix-3 already added a CPU OOM-degrade for exactly this model, but its `_is_cuda_oom` matched only `"out of memory"`. The real crash is `CUBLAS_STATUS_ALLOC_FAILED` (no "out of memory" substring) -> the degrade NEVER fired -> the run died. The existing test used `"CUDA out of memory..."` (which matched), so it passed while production crashed.

## The fix (diff = .codex/I-deepfix-001/crash_fix_diff.patch, 2 files)
`consolidation_nli.py`:
- `_is_cuda_oom` (line ~152): ALSO return True for `cublas_status_alloc_failed` / `cublas_status_not_initialized` (OOM-equivalent card-full signatures). Routes them to the SAME existing already-tested CPU degrade. Unrelated errors still fail loud.
- NEW `PG_CONSOLIDATION_NLI_PREDICT_CHUNK` (default 256, <=0 disables) + `_predict_chunk()` helper; applied at the chunk build: `chunk_size = min(chunk_size, _pchunk)`. Caps the per-forward batch INDEPENDENT of corpus size -> peak GPU memory bounded by `workers * predict_chunk`, constant regardless of corpus.
`test_deepfix_consolidation_nli_oom_degrade.py`:
- `test_is_cuda_oom_detects_cublas_alloc_failed` — RED before the fix (old matcher missed CUBLAS), GREEN after; also asserts an unrelated error still fails loud.
- `test_predict_chunk_env_bounds_forward_batch` — the chunk-cap env (256 default / override / 0-disable).
All 8 tests in the file PASS locally (offline, no torch/GPU).

## Faithfulness-neutrality (the load-bearing claim — verify it)
Consolidation NLI is a §-1.3 CONSOLIDATION WEIGHT (corroboration baskets), NOT a faithfulness gate. It touches NO strict_verify / NLI-entailment-verifier / 4-role / provenance / span gate.
- Chunk cap: the grouping is an order-independent union-find over the gathered edges (`score_pairs` docstring guarantees identical output for any chunking/worker count). Smaller `.predict` forwards change only WHERE-in-a-batch a pair sits, never WHICH pairs are compared nor the entailment margin -> byte-identical edge list -> identical merged baskets.
- CUBLAS detect: only routes MORE error signatures to the EXISTING CPU degrade, whose test (`test_...:140`) already asserts CPU and GPU produce the identical argmax-entailment edge list. Adds zero new behavior beyond "recover instead of die".

## Confirm each (P-level if wrong)
1. Chunk cap is byte-identical to the verdict (union-find order-independence)? Any path where a smaller chunk changes which edges are emitted?
2. CUBLAS detect cannot swallow a genuinely-unrelated CUDA error that SHOULD fail loud (e.g. a shape/dtype bug that mentions cublas)? Is the substring match too broad?
3. Default behavior unchanged for small corpora (drb_72 etc.) — predict_chunk 256 vs the old ~small chunks: does it ever INCREASE chunk_size? (It only ever `min()`s it down.)
4. Any interaction with the W04 wall-deadline (more chunks = more loop iterations) that could truncate MORE and drop corroborators? §-1.3 says under-merge is safe, but flag if the truncation rate materially rises.

## Output schema (REQUIRED)
```yaml
verdict: APPROVE | REQUEST_CHANGES
faithfulness_neutral: true|false
frozen_engine_untouched: true|false
p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```
