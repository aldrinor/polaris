#!/usr/bin/env bash
# =====================================================================================================
# I-deepfix-001 (#1344) — COMPLETE launch env for the Box-C 2-card WORKFORCE Gate-B run.
# (L3 speed lever splits the local models across BOTH cards — see the topology block below. Originally
#  authored for a single A100-80GB card; the non-device belts/floors below are card-count-agnostic.)
#
# WHY THIS FILE: the full-capability benchmark slate (scripts/dr_benchmark/run_gate_b.py
# _FULL_CAPABILITY_BENCHMARK_SLATE) force-sets almost every winner/loser flag, and run_gate_b_query
# sets the default-OFF winners programmatically. This file covers the GAPS the slate does NOT robustly
# guarantee on the launch: (1) GPU device placement (NO device var is in the slate) and (2) the WS-8 D4
# recency legs (deliberately OUT of the global slate). It also BELTS the four flags most exposed to a
# stray operator/.env drift, so a slate/code regression cannot silently dark a winner (the drb_72 class).
#
# Source it LAST — AFTER any other env file / per-role `export PG_*_DEVICE=` — then verify + launch:
#     # ... any other env files / per-role device exports FIRST ...
#     source .codex/I-deepfix-001/a100_complete_env.sh
#     polaris_verify_device_pins || return 1   # FAIL LOUD if a stray later export re-collapsed the split
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
#     device placement (L3 2-card split: embedder + content-relevance -> cuda:0; reranker + NLI +
#       consolidation-NLI -> cuda:1): PG_EMBED_DEVICE / PG_RERANKER_DEVICE / PG_NLI_DEVICE /
#       PG_CONSOLIDATION_NLI_DEVICE / PG_CONTENT_RELEVANCE_DEVICE
#     WS-8 D4 recency: PG_DOCUMENT_TYPE_WEIGHT=1 + PG_COMPOSITION_RECENCY=1 (out of the global slate by
#       design — WS-8 journal-only-template scope; inert on non-journal templates, so safe to set here)
#     FIX-2 pre-spend guard kill-switch (default-ON; explicit for clarity): PG_WINNER_SLATE_PRESPEND_ASSERT
# =====================================================================================================

# ── SPEED LEVER L3 (dual-gated speed decision — both review gates APPROVE, with guards) ──────────────
# 2-CARD topology for the Box-C workforce run: expose BOTH cards and split the local models across them
# so the embedder and reranker/NLI legs no longer serialize on one card. This changes COMPUTE PLACEMENT
# ONLY — no model, no threshold, no verdict. FAITHFULNESS-NEUTRAL (strict_verify / NLI / 4-role D8 /
# provenance are byte-identical regardless of which card a tensor lands on).
#   cuda:0  <-  embedder (W6)  +  content-relevance judge (W5)
#   cuda:1  <-  reranker (W7)  +  FaithLens NLI  +  consolidation NLI (W10)
# ORDERING (BINDING, CORRECTED — correction 9): source THIS file LAST in the launch, AFTER any other env
# file or per-role `export PG_*_DEVICE=`. In the shell the LAST export WINS, so the prior "source FIRST"
# guidance was BACKWARDS — a per-role export running AFTER this file would silently re-collapse the split
# back onto one card. This file must be the FINAL device authority. As a belt, call
# `polaris_verify_device_pins` (defined at the end of this file) right before `python ...` to FAIL LOUD if
# any of the 5 device pins drifted (e.g. a stray later export slipped in).
# NOTE (memory: mineru-vLLM): on CLINICAL runs card 1 ALSO hosts a mineru-vLLM server
# (CUDA_VISIBLE_DEVICES=1), which would contend with the reranker/NLI legs pinned to cuda:1 here. This is
# a WORKFORCE run — no mineru-vLLM server is up — so BOTH cards are free and the split is safe. Re-check
# card-1 headroom before reusing this 2-card split on a clinical run.
export CUDA_VISIBLE_DEVICES=0,1           # expose BOTH cards (was 0); cuda:0/cuda:1 index into this set
export PG_EMBED_DEVICE=cuda:0             # W6 Qwen3-Embedding-8B (embedding_service.py:150) -> card 0
export PG_RERANKER_DEVICE=cuda:1          # W7 Qwen3-Reranker-4B (qwen_reranker_scorer.py:83) -> card 1
export PG_NLI_DEVICE=cuda:1               # FaithLens NLI cross-encoder (nli_verifier.py:95) -> card 1
export PG_CONSOLIDATION_NLI_DEVICE=cuda:1 # W10 consolidation NLI cross-encoder (consolidation_nli.py:73) -> card 1
export PG_CONTENT_RELEVANCE_DEVICE=cuda:0 # W5 Qwen3-Reranker-0.6B (content_relevance_judge.py:374) -> card 0 (co-resident w/ embedder)

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

# ── DRB-II COVERAGE LEVERS (slate force-ON; belt here so a stray operator/.env cannot dark a lever) ───
# The 9 weight-and-consolidate breadth levers were BUILT + triple-gated but sat DARK (default-OFF, absent
# from the paid slate). run_gate_b.py now force-ON-pins + preflight-requires + allowlists each, and
# assert_coverage_levers_armed() fails the run CLOSED pre-spend if any is off. Belted here so a direct
# in-process launch (or a stray .env =0) cannot silently dark a lever. §-1.3 DNA-ALIGNED: breadth EMERGES
# from honest weighted multi-attribution — these arm the EXISTING default; NO forced cap/target/thinner/
# canary/number. FAITHFULNESS-NEUTRAL: every surfaced/routed source re-passes the UNCHANGED strict_verify.
# D1/D4 were the two dark ONLY on the Gate-B path (armed by run_honest_sweep_r3.main_async's
# apply_winner_slate_on_paid_path, which the Gate-B launcher never calls) — armed here + in the slate.
export PG_FACET_OUTLINE=1                # O1 facet outline (section count emerges from evidence clusters)
export PG_ROUTE_ALL_BASKETS=1           # F1 route-every-verified-basket (consolidate-don't-drop the stranded baskets)
export PG_EV_BUDGET_TRACKS_PAYLOAD=1    # F2 per-section evidence budget tracks full matched payload (ceiling removed)
export PG_WORD_BUDGET_TRACKS_PAYLOAD=1  # F5 per-section word budget tracks full routed payload (clamp removed)
export PG_EXPERT_FACET_PLANNER=1        # R1 expert facet planner (widen retrieval breadth; yield-keyed safety bounds)
export PG_FACET_COMPLETENESS=1          # R2 facet completeness (retrieval-breadth completeness pass)
export PG_QUALIFIER_ELABORATION=1       # D1 within-basket verbatim qualifier elaboration (keep-all; was Gate-B-dark)
export PG_ENRICHMENT_FACET_ROUTE=1      # D4 facet-routed enrichment placement (keep-all; was Gate-B-dark)
export PG_SUBTOPIC_DECOMPOSITION=1      # L2 sub-topic decomposition (one verbatim-span sentence per distinct atomic fact; keep-all)

# ── FIX-2 pre-spend winner-slate assertion kill-switch (default-ON; explicit belt) ───────────────────
# Fails the run CLOSED before any spend if the slate did not land a force-on/force-exact winner
# (esp. PG_QGEN_FS_RESEARCHER). Leave =1 for the paid run; set 0 only for a deliberate operator experiment.
export PG_WINNER_SLATE_PRESPEND_ASSERT=1

# ── correction 9 (task C): POST-SOURCE device-pin assertion ──────────────────────────────────────────
# Because THIS file must be sourced LAST (the last export wins, §L3 topology block above), a stray later
# per-role `export PG_*_DEVICE=` — or a prior CUDA_VISIBLE_DEVICES=0 that hid card 1 — would silently
# re-collapse the L3 2-card split onto ONE card and the run would OOM (or serialize) with NO error. Run
# `polaris_verify_device_pins || return 1` right before `python scripts/dr_benchmark/run_gate_b.py ...`
# to FAIL LOUD if any of the 5 device pins (or CUDA_VISIBLE_DEVICES) drifted from the L3 topology. Pure
# string compare — sets nothing, faithfulness-neutral; a device pin is COMPUTE PLACEMENT only.
polaris_verify_device_pins() {
    # expected L3 topology: embedder + content-relevance on card 0; reranker + NLI + consolidation-NLI on card 1.
    local ok=0
    local -a names=(CUDA_VISIBLE_DEVICES PG_EMBED_DEVICE PG_RERANKER_DEVICE PG_NLI_DEVICE PG_CONSOLIDATION_NLI_DEVICE PG_CONTENT_RELEVANCE_DEVICE)
    local -a want=("0,1" "cuda:0" "cuda:1" "cuda:1" "cuda:1" "cuda:0")
    local i name expected actual
    for i in "${!names[@]}"; do
        name="${names[$i]}"; expected="${want[$i]}"; actual="${!name}"
        if [ "$actual" != "$expected" ]; then
            echo "polaris_verify_device_pins: DEVICE-PIN DRIFT — $name='$actual' (expected '$expected'). A later export re-collapsed the L3 2-card split; refusing to launch." >&2
            ok=1
        fi
    done
    if [ "$ok" -eq 0 ]; then
        echo "polaris_verify_device_pins: OK — 5 device pins + CUDA_VISIBLE_DEVICES hold the L3 2-card split (embedder/W5 -> cuda:0; reranker/NLI/consolidation-NLI -> cuda:1)."
    fi
    return "$ok"
}

# ═════════════════════════════════════════════════════════════════════════════════════════════════════
# CLINICAL-RUN mineru vLLM extractor recipe (OPT-IN; NOT active on this WORKFORCE run — drb_72 is
# workforce so no clinical PDFs, no mineru server needed). This block documents the COHERENT path so the
# LAUNCHED server MATCHES the SHIPPED client and never 404s (I-deepfix-001 S1b install-coherence fix).
#
# THE COHERENCE RULE: the shipped client src/tools/access_bypass.py::_mineru25_extract reaches the GPU
# VLM via the PROVEN vlm-http-client protocol — it shells out to `mineru -b vlm-http-client -u <url>`,
# which talks to the mineru-vllm-server (the vLLM inference server). So the supervisor MUST launch
# mineru-vllm-server (NOT mineru-api — a DIFFERENT console script that serves POST /file_parse and does
# NOT accept the engine flags below; the client never calls it). Proven on the box: mineru-vllm-server
# wraps `vllm serve <MinerU2.5 model>`, accepts --gpu-memory-utilization/--max-num-seqs, /health -> 200,
# and the vlm-http-client CLI produced a real extraction (13/13 pages, 6 reconstructed HTML tables).
#
# On a CLINICAL run, card 1 hosts the mineru server ALONE — do NOT reuse the L3 workforce split above
# that also pins reranker/NLI/consolidation-NLI to cuda:1 (they would contend with the mineru server).
# `polaris_apply_clinical_device_topology` (defined at the very end of this file) MOVES those three legs
# off card 1 back onto card 0 and hides card 1 from the pipeline, and `polaris_verify_device_pins_clinical`
# FAILS LOUD if that isolation did not hold. Give mineru card 1; keep ALL local pipeline models on card 0.
#
#   # 1) launch the PROVEN inference server on the dedicated card (bounded 0.4 util per §8.4, tmux-supervised):
#   tmux new-session -d -s mineru_vllm \
#     "CUDA_VISIBLE_DEVICES=1 /root/mineru_svc/bin/mineru-vllm-server \
#        --host 127.0.0.1 --port 30024 --gpu-memory-utilization 0.4 --max-num-seqs 20 \
#        > /root/mineru_vllm_server.log 2>&1"
#   # 2) wait for /health 200 (vLLM model load ~1-2 min):
#   until [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:30024/health)" = "200" ]; do sleep 5; done
#   # 3) point the SHIPPED client at the PROVEN server + the isolated-venv mineru CLI (data-driven, LAW VI):
#   export PG_CLINICAL_PDF_EXTRACTOR=mineru25
#   export PG_MINERU25_BACKEND=vlm-http-client
#   export PG_MINERU25_SERVER_URL=http://127.0.0.1:30024
#   export PG_MINERU25_CLI_PATH=/root/mineru_svc/bin/mineru
#   # 4) ISOLATE the cards: move reranker/NLI/consolidation-NLI OFF card 1 (they were on cuda:1 for the
#   #    L3 workforce split above) so they do not contend with the mineru server, then FAIL LOUD if drift:
#   polaris_apply_clinical_device_topology
#   polaris_verify_device_pins_clinical || return 1
#   #    (do NOT call polaris_verify_device_pins here — that verifier expects the WORKFORCE 2-card split.)
#   # 5) launch:  python scripts/dr_benchmark/run_gate_b.py --only <clinical_slug>
#   # 6) §8.4 stewardship: KILL the server when the run completes or the card is idle:
#   #      tmux kill-session -t mineru_vllm
#
# Fail-loud contract (no silent degradation): with PG_MINERU25_BACKEND=vlm-http-client set, a missing
# PG_MINERU25_SERVER_URL or a missing PG_MINERU25_CLI_PATH RAISES inside _mineru25_extract, which the
# async wrapper turns into a DISCLOSED Docling degrade (prod has no docling -> PyMuPDF, still disclosed
# + W4-CANARY) — never a silent capability downgrade.
# ═════════════════════════════════════════════════════════════════════════════════════════════════════

# ── CLINICAL device-topology helpers (DEFINED but INERT on this WORKFORCE run — never called here) ────
# S1b REVISE FIX (clinical GPU-isolation P1): the L3 workforce split above pins reranker/NLI/consolidation-
# NLI to cuda:1, but on a CLINICAL run card 1 hosts the mineru vLLM server — so those three legs would
# CONTEND with the server on the same card. These two functions are the "clinical override exports off
# card 1 + a device-pin verifier that fails loud" the review asked for. A clinical operator calls them
# AFTER launching the mineru server (recipe above); this workforce run calls NEITHER (a bash function body
# runs only when the function is called), so defining them changes NOTHING here. COMPUTE-PLACEMENT ONLY /
# faithfulness-neutral — a device pin never touches a model, threshold, or verdict.

polaris_apply_clinical_device_topology() {
    # Collapse ALL local pipeline models onto card 0 and hide card 1 (the mineru server owns it via its
    # own CUDA_VISIBLE_DEVICES=1 child env). OVERRIDES the L3 workforce split so reranker/NLI/consolidation-
    # NLI no longer share a card with the mineru server.
    export CUDA_VISIBLE_DEVICES=0             # pipeline sees card 0 ONLY; card 1 is the mineru server's
    export PG_EMBED_DEVICE=cuda:0             # W6 embedder                 -> card 0
    export PG_RERANKER_DEVICE=cuda:0          # W7 reranker  MOVED off card 1 -> card 0 (was cuda:1 in L3)
    export PG_NLI_DEVICE=cuda:0               # FaithLens NLI MOVED off card 1 -> card 0 (was cuda:1 in L3)
    export PG_CONSOLIDATION_NLI_DEVICE=cuda:0 # W10 consolidation NLI MOVED off card 1 -> card 0 (was cuda:1)
    export PG_CONTENT_RELEVANCE_DEVICE=cuda:0 # W5 content-relevance        -> card 0
    echo "polaris_apply_clinical_device_topology: local models collapsed to cuda:0; card 1 reserved for the mineru vLLM server."
}

polaris_verify_device_pins_clinical() {
    # FAIL LOUD if the clinical isolation drifted: all 5 local models MUST be on cuda:0 (card 1 belongs to
    # the mineru server), CUDA_VISIBLE_DEVICES MUST hide card 1 from the pipeline, and the mineru client
    # MUST be wired to a launched server (else clinical PDFs would degrade instead of extract). Pure string
    # compare — sets nothing, faithfulness-neutral.
    local ok=0
    local -a names=(CUDA_VISIBLE_DEVICES PG_EMBED_DEVICE PG_RERANKER_DEVICE PG_NLI_DEVICE PG_CONSOLIDATION_NLI_DEVICE PG_CONTENT_RELEVANCE_DEVICE)
    local -a want=("0" "cuda:0" "cuda:0" "cuda:0" "cuda:0" "cuda:0")
    local i name expected actual
    for i in "${!names[@]}"; do
        name="${names[$i]}"; expected="${want[$i]}"; actual="${!name}"
        if [ "$actual" != "$expected" ]; then
            echo "polaris_verify_device_pins_clinical: DEVICE-PIN DRIFT — $name='$actual' (expected '$expected'). A local model is still on card 1 and would contend with the mineru vLLM server; refusing to launch. Run polaris_apply_clinical_device_topology first." >&2
            ok=1
        fi
    done
    if [ "${PG_MINERU25_BACKEND:-}" != "vlm-http-client" ]; then
        echo "polaris_verify_device_pins_clinical: PG_MINERU25_BACKEND='${PG_MINERU25_BACKEND:-}' (expected 'vlm-http-client' for the clinical mineru path)." >&2; ok=1
    fi
    if [ -z "${PG_MINERU25_SERVER_URL:-}" ]; then
        echo "polaris_verify_device_pins_clinical: PG_MINERU25_SERVER_URL is empty — the mineru vLLM server URL is required or the client degrades to Docling/PyMuPDF." >&2; ok=1
    fi
    if [ -z "${PG_MINERU25_CLI_PATH:-}" ]; then
        echo "polaris_verify_device_pins_clinical: PG_MINERU25_CLI_PATH is empty — the isolated-venv mineru CLI path is required for vlm-http-client extraction." >&2; ok=1
    fi
    if [ "$ok" -eq 0 ]; then
        echo "polaris_verify_device_pins_clinical: OK — all local models on cuda:0, card 1 reserved for the mineru vLLM server, and the mineru client is wired to the launched server."
    fi
    return "$ok"
}
