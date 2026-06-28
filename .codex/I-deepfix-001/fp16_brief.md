HARD ITERATION CAP: 5 per document. This is iter 1 of 5. Front-load all findings; reserve P0/P1 for real execution risks. APPROVE iff zero NOVEL/continuing P0 AND zero P1.

# DIFF GATE — I-deepfix-001 P0-3b: load the Qwen3-Embedding-8B winner in FP16 (was FP32→OOM)

CONTEXT: the corrected-relaunch GPU smoke (pre-spend) caught that EmbeddingService loaded Qwen3-Embedding-8B via `SentenceTransformer(name, device=...)` with NO dtype → FP32 (~24-32GB) → OOM'd the 24GB cuda:0 card → `_load_embedder` returned None (W6 embedder DARK), making the static 2-GPU split impossible. (woveq68ub's ~16GB estimate was the FP16 size.)

THE FIX (this diff, `src/utils/embedding_service.py`): when the Qwen3-Embedding-8B selection is active (EMBEDDING_DIMENSIONS==4096), pass `model_kwargs={"torch_dtype": torch.float16}` to the SentenceTransformer constructor (all 3 call sites: device-pinned, TypeError-fallback, no-device). The MiniLM default (384-dim) is UNCHANGED (no model_kwargs) => byte-identical OFF path. `import torch` is LOCAL to the large-model branch.

LIVE VALIDATION ON THE VM (the strongest evidence): with PG_EMBEDDER_MODEL=qwen3 + PG_EMBED_DEVICE=cuda:0, `_load_embedder()` now returns EmbeddingService(Qwen/Qwen3-Embedding-8B), card0 199->15129 MiB (~15GB fp16, was ~24GB fp32 OOM/None), encode dim=4096, LOADER_OK. The full static split fits: cuda:0 embedder 15GB + W5 ~2GB; cuda:1 W7 8GB + mineru ~10GB — all <24GB, no OOM.

VERIFY: (1) the fp16 dtype is applied ONLY to the 4096/qwen3 path, MiniLM unchanged; (2) the local `import torch` is safe; (3) the 3 call sites are consistent; (4) no faithfulness/§-1.3 impact (this is a model-load precision change — fp16 embeddings for retrieval relevance are standard, the dim is unchanged at 4096); (5) any P0/P1.

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
Static review only. APPROVE iff zero P0/P1.
