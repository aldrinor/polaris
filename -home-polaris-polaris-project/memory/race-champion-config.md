---
name: race-champion-config
description: "The RACE champion recipe (0.4447, task 72) is raw-A compose, NOT the full gated v4 pipeline"
metadata: 
  node_type: memory
  type: project
  originSessionId: 21e87760-8436-4090-870d-99ef2121882e
---

The agreed RACE-optimization pipeline is **raw A, checks off, faithfulness FULL off** — build on top of that. Do NOT benchmark with the full gated v4 pipeline.

**Champion = 0.4447** (DeepResearch-Bench task 72, judge openai/gpt-5.5; Comp 0.4569 / Insight 0.4293 / IF 0.4587 / Read 0.4310). Recipe (`SECURED_0.44_champion/RECIPE.md`):
- Composer: `scripts/compose_agentic_report_s3gear329.py` (raw-A direct compose)
- Corpus: FROZEN `data/cp4_corpus_s3gear_329.json` (997 evidence / 329 clusters, domain=workforce)
- Config: `PG_OUTLINE_AGENT=1`, step3 control (quant-directive OFF), glm-5.2, faithfulness/gates OFF
- Champion commit lineage **df4118a**. Reproducible ±0.016 judge variance.
- NOTE: the composer still does SOME live agentic gap-fill retrieval (run_live_retrieval), so it needs a working browser to reproduce exactly.

**Confound trap (2026-07-19):** running the FULL gated v4 (`build_and_run_v4`→`run_one_query`) with LIVE retrieval + faithfulness ON scored only **0.3199** — apples-to-oranges (different composer, live-vs-frozen corpus, faithfulness on-vs-off). Faithfulness ON drops unverified claims → Comp/Read hit hardest (the drop signature). This is NOT a regression; it's the wrong pipeline. Also: build_and_run_v4 passes four_role_transport=None so the D8 verifier never binds → `released_with_disclosed_gaps`.

**Name-fix exoneration (2026-07-19):** codex-sol + fable + Kimi-K3 all ruled the review-readiness renames did NOT touch the champion backbone. Mechanical proof: composer script + frozen corpus + model IDs + all 328 migrated config defaults byte-identical across baseline vs renamed tree; the 188-module compose import closure contains ZERO renamed modules; the R098 (~2%) renames are pure os.getenv→resolve migration. 2 non-scoring rename stragglers to fix: `scripts/diagnostics/entailment_rotation_behavioral.py` (pathB_capture NameError), `scripts/operational_readiness_preflight.py:93` (stale pathB_runner path).

**Env facts for live runs on this box:** use `/home/polaris/pipeline-env/bin/python` (torch cu128, drives the Blackwell sm_120 GPU; /opt/conda cu124 can't). Browser libs missing system-wide — userspace fix (apt-get download + LD_LIBRARY_PATH) makes playwright chrome-headless-shell work, but CRAWL4AI still fails → some fetch backends dark. Reranker OOMs on the shared GPU unless `PG_CONTENT_RELEVANCE_SCORE_CHUNK=16` (byte-identical, memory-only). Kimi K3 = `moonshotai/kimi-k3` on OpenRouter, a reasoning model — needs a LARGE max_tokens (it burns tokens on reasoning before content).

See [[code-review-readiness]], [[investigate-then-consult]].
