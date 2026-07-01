#!/usr/bin/env bash
# =====================================================================================================
# I-deepfix-001 (#1344) — COMPLETE launch env for a SINGLE A100-80GB card (paid Gate-B run).
#
# WHY THIS FILE: the full-capability benchmark slate (scripts/dr_benchmark/run_gate_b.py
# _FULL_CAPABILITY_BENCHMARK_SLATE) force-sets almost every winner/loser flag, and run_gate_b_query
# sets the default-OFF winners programmatically. This file covers the GAPS the slate does NOT robustly
# guarantee on the launch: (1) GPU device placement (NO device var is in the slate) and (2) the WS-8 D4
# recency legs (deliberately OUT of the global slate). It also BELTS the four flags most exposed to a
# stray operator/.env drift, so a slate/code regression cannot silently dark a winner (the drb_72 class).
#
# Source it BEFORE launching the run, e.g.:
#     source .codex/I-deepfix-001/a100_complete_env.sh
#     python scripts/dr_benchmark/run_gate_b.py --only <slug>
#
# NO MODEL ENV VARS ARE SET HERE (operator directive + audit "models_all_correct"): the 4-role transport
# already resolves generator=glm-5.2 / judge=kimi-k2.6, and the slate force-exacts the mirror judge /
# evaluator to z-ai/glm-5.2. Setting a model env here would risk overriding a CORRECT resolution.
#
# ── WHO RELIES ON THE SLATE vs THIS ENV ──────────────────────────────────────────────────────────────
#   SLATE-COVERED (force-on / force-exact; belted below only so a stray .env cannot win):
#     W2  PG_QGEN_FS_RESEARCHER=1              (slate force-ON)
#     K10 PG_QGEN_ITERRESEARCH=0              (slate force-EXACT "0", REQUIRED-OFF loser)
#     K1  PG_STORM_ENABLED=0 / PG_STORM_ENABLED_IN_BENCHMARK=0   (slate force-EXACT "0", REQUIRED-OFF)
#     W5  PG_CONTENT_RELEVANCE_SCORE_CHUNK=2   (slate force-EXACT "2" — I-deepfix-001 FIX 3)
#   SLATE-ONLY (NOT belted here — the slate is authoritative): W1,W3,W4,W6-W14, M6, all fetch/wall knobs.
#   ENV-ONLY (the real gaps — the slate does NOT set these):
#     device placement (single A100 => everything on cuda:0): PG_EMBED_DEVICE / PG_RERANKER_DEVICE /
#       PG_NLI_DEVICE / PG_CONSOLIDATION_NLI_DEVICE / PG_CONTENT_RELEVANCE_DEVICE
#     WS-8 D4 recency: PG_DOCUMENT_TYPE_WEIGHT=1 + PG_COMPOSITION_RECENCY=1 (out of the global slate by
#       design — WS-8 journal-only-template scope; inert on non-journal templates, so safe to set here)
#     FIX-2 pre-spend guard kill-switch (default-ON; explicit for clarity): PG_WINNER_SLATE_PRESPEND_ASSERT
# =====================================================================================================

# ── SINGLE-CARD topology: pin all local models to the one A100 (cuda:0) ──────────────────────────────
# On an 80GB card the W6 embedder (~16GB) + W7 reranker (~8GB) + the W5 0.6B reranker + the two NLI
# cross-encoders co-reside with headroom. cuda:0 (NOT the 2-card cuda:1 split — gpu_device_split.py is
# for the 2x RTX3090Ti VM). CUDA_VISIBLE_DEVICES=0 neutralizes any stray cuda:1 from a prior 2-card env.
export CUDA_VISIBLE_DEVICES=0
export PG_EMBED_DEVICE=cuda:0             # W6 Qwen3-Embedding-8B (embedding_service.py:150)
export PG_RERANKER_DEVICE=cuda:0          # W7 Qwen3-Reranker-4B (qwen_reranker_scorer.py:83)
export PG_NLI_DEVICE=cuda:0               # FaithLens NLI cross-encoder (nli_verifier.py:95; default cuda:0)
export PG_CONSOLIDATION_NLI_DEVICE=cuda:0 # W10 consolidation NLI cross-encoder (consolidation_nli.py:73)
export PG_CONTENT_RELEVANCE_DEVICE=cuda:0 # W5 Qwen3-Reranker-0.6B (content_relevance_judge.py:374; default cuda->cuda:0)

# ── W5 one-pass OOM guard (also slate force-EXACT "2"; belt) ──────────────────────────────────────────
# Bounds the W5 reranker per-forward logits tensor so it never OOMs the co-resident embedder and silently
# demotes W5 to full-weight. Faithfulness-neutral (chunked scores are byte-identical to one-pass).
export PG_CONTENT_RELEVANCE_SCORE_CHUNK=2

# ── Winner / loser belts (all slate-covered; set here so a stray operator/.env cannot dark a winner) ──
export PG_QGEN_FS_RESEARCHER=1            # W2 FS-Researcher winner (belt vs slate/code drift — the drb_72 dark winner)
export PG_QGEN_ITERRESEARCH=0            # K10 IterResearch superseded by FS-Researcher (loser off)
export PG_STORM_ENABLED=0               # K1 storm_interviews module arm (loser off — operator: STORM entirely off)
export PG_STORM_ENABLED_IN_BENCHMARK=0  # K1 STORM benchmark gate arm (loser off — operator: STORM entirely off)

# ── WS-8 D4 recency (deliberately OUT of the global slate — must be set on the launch to activate) ────
# PG_DOCUMENT_TYPE_WEIGHT is a DOUBLE gate (=1 AND the scope template declares document_type_preference),
# so it is INERT (factor 1.0) on non-journal-class templates — safe to set globally. PG_COMPOSITION_RECENCY
# is default-ON; pinned for clarity. Together they arm the journal-class composition recency leg.
export PG_DOCUMENT_TYPE_WEIGHT=1         # WS-8 D4 recency gate (run_honest_sweep_r3.py:2733; double-gated, inert off-journal)
export PG_COMPOSITION_RECENCY=1          # WS-8 D4 composition recency leg (weighted_enrichment.py:339; default-ON)

# ── FIX-2 pre-spend winner-slate assertion kill-switch (default-ON; explicit belt) ───────────────────
# Fails the run CLOSED before any spend if the slate did not land a force-on/force-exact winner
# (esp. PG_QGEN_FS_RESEARCHER). Leave =1 for the paid run; set 0 only for a deliberate operator experiment.
export PG_WINNER_SLATE_PRESPEND_ASSERT=1
