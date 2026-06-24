# Layer 7 — embedder_late_interaction (I-ret-002 #1294)

Single-vector embedders vs token-level **late-interaction MaxSim** (ColBERT) for POLARIS
retrieval. Per-layer ISOLATION bake-off: all else held fixed (IterResearch query gen frozen).

## Metric (dual-axis, brief §7)
- **Axis A** — `AUC(on-topic > off-topic)` separation (reuses the seam metric `auc_pos_gt_neg`).
- **Axis B** — reasoning-retrieval `recall@k` on NON-LEXICAL evidence (the late-interaction edge):
  per claim, is the gold non-lexically-overlapping supporting source in the candidate's top-k?

No banned §-1.1 proxy: every score is REAL model output vs a LABELED, two-family-adjudicated
ground truth. Nothing is hard-dropped (§-1.3): off-topic rows are KEPT as the negative class.

## Candidates (web-verified ids, 2026-06-23)
| name | hf_id | arch | role | gpu |
|---|---|---|---|---|
| all_minilm_l6_v2 | sentence-transformers/all-MiniLM-L6-v2 | single | candidate (FLOOR) | no |
| qwen3_embedding_8b | Qwen/Qwen3-Embedding-8B | single | candidate | yes |
| gte_modernbert_embed | Alibaba-NLP/gte-modernbert-base | single | candidate | no |
| granite_embedding_r2 | ibm-granite/granite-embedding-english-r2 | single | candidate | no |
| embeddinggemma_300m | google/embeddinggemma-300m | single | **yardstick** (Gemma lic) | no |
| gte_moderncolbert_v1 | lightonai/GTE-ModernColBERT-v1 | late_interaction | candidate (Apache-2.0) | yes |
| reason_moderncolbert | lightonai/Reason-ModernColBERT | late_interaction | **yardstick** (cc-by-nc-4.0) | yes |

Yardsticks are reported but `ineligible_to_win` — a non-commercial / Gemma-licensed model is
never crowned the deployable winner (sovereignty).

## Files
- `build_fixture.py` — builds the labeled fixture from banked `corpus_snapshot.json` + the
  two-family adjudication side files (`fixture_adjudication/`). Keywords PROPOSE; adjudication
  SCORES. `--require-adjudication` fails loud if no scored rows exist.
- `scorer.py` — shared scorer math (AUC, recall@k, cosine, MaxSim). Same code the GATE-0 canary
  blesses and `run_bakeoff.py` runs (anti-drb_72: one source of math).
- `run_bakeoff.py` — loads each candidate by exact id, asserts `loaded_id == requested_id`
  (Gate-B / I-arch-009 no-silent-MiniLM-fallback), scores both axes, writes ranked results JSON.
- `gate0.py` — GATE-0: scorer-math canary + per-candidate liveness (each model loads + scores a
  known on>off pair in the correct direction; stub/empty/load-fail/missing-key FAILS LOUD).
- `smoke_test.py` — OFFLINE stub smoke (mocked loaders, no GPU/network): py_compile + math
  canary + liveness (good PASS / stub FAIL / mismatch FAIL) + fixture build + honest skips.

## deps_needed (do NOT add to requirements.txt — reported per brief)
- `sentence-transformers` (single-vector embedders; already a POLARIS dep)
- `torch` (CUDA build on the GPU box)
- `pylate` (`pip install -U pylate`) — late-interaction ColBERT (GTE/Reason-ModernColBERT)
- `transformers` (pulled by the above)
- `einops` may be required by some modernBERT remote code (`trust_remote_code=True`)

## Run order (GPU box)
```
python gate0.py --live                         # GATE-0 must PASS first (math + liveness)
python build_fixture.py --require-adjudication  # fail loud if adjudication missing
python run_bakeoff.py --out results.json        # ranked per-axis results
```
Offline pre-check (no GPU/network): `python smoke_test.py` (must exit 0).

## External cross-check (brief execution-plan note)
BRIGHT (`xlangai/BRIGHT`, ICLR 2025) and MTEB-R are SUPPLEMENTAL axis-specific yardsticks for
the Axis-B reasoning-retrieval edge — a cross-check that the POLARIS-data winner is not a
domain overfit. They are NOT the per-layer winner metric (the POLARIS dual-axis metric is).
