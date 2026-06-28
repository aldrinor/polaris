HARD ITERATION CAP: 5 per document. This is iter 2 of 5.

CHANGES SINCE ITER 1 (you returned REQUEST_CHANGES — all findings adopted):
- P0-3b: the fail-closed gate now covers W5 reranker + W7 reranker (not just B4/W6) — a relevance-layer winner that degrades to full-weight/device=unavailable/load-fail REJECTS the run at a pre-generation seam (item 2). Cached embedder handle made retryable.
- P0-1/P1-9: the retrieval deadline is now relaunch-BLOCKING and a partial-fetch HANDOFF (proceed to tiering→…→render with disclosure), not a bare wall (item 4).
- GPU smoke now covers ALL 4 co-resident loads (embedder+W5 cuda:0, W7+mineru cuda:1) with nvidia-smi, not just mineru (item 3).
- Device knobs confirmed as launch-env reads only (not slate force-on). P1-8 scope-validator accepted as query-only (no source drop).
- Topology LOCKED: one document at a time with BOTH GPUs visible per run, OR two VMs each with both GPUs; never two single-GPU-pinned concurrent runs.
Please confirm these resolve your continuing-P0 + P1, or surface any remaining blocker.


- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# BRIEF GATE — I-deepfix-001 corrected-relaunch fix plan (winners must actually FIRE)

## You are reviewing a FIX PLAN (not a diff yet). Confirm the root-cause diagnosis + that the proposed fix set is correct, minimal, and §-1.3-safe. APPROVE the plan or REQUEST_CHANGES with the corrected plan.

## What happened
Two winners-only paid runs (FRONT=drb_72_ai_labor, MIDDLE=drb_76_gut_microbiota_crc) were launched on ONE VM with 2× RTX3090Ti (24GB each), EACH PINNED to a single GPU (CUDA_VISIBLE_DEVICES=0/1). A 7-agent line-by-line forensic read of both full logs found only 4 of 14 winners fired (W1 scope, W3 WRRF, W4 mineru25, W8 llm_tiering); W5+W6 dark-defective; W7/W10-W14 never reached (runs killed mid-retrieval). Purity held in retrieval (zero storm/agentic/deepener/iterresearch/MiniLM/gemma). The runs were killed by the operator after the OOM was found.

## ROOT CAUSES (confirm each)

### P0-2 — W6 embedder + B4 semantic relevance gate DARK (claimed GPU-independent code bug; I found nuance — adjudicate)
- Log: `cannot import name 'EmbeddingService' from 'src.polaris_graph.agents.nli_verifier'` (FRONT L60 / MIDDLE L61), then EVERY round "B4 relevance gate ON but semantic scorer unavailable — falling back LOUDLY to the legacy lexical cut".
- FACTS from code:
  - `EmbeddingService` is defined in `src/utils/embedding_service.py:75`. `nli_verifier.py` does NOT define or re-export it (grep: 0 hits).
  - `prefetch_offtopic_filter.py:104` does `from src.polaris_graph.agents.nli_verifier import EmbeddingService` (WRONG module) inside a try → except falls back to `SentenceTransformer(model_name)` (loads fine — log shows Qwen3-Embedding-8B 4/4 shards).
  - `_similarity_scores` (prefetch_offtopic_filter.py:128-196) supports BOTH `embed_batch` (EmbeddingService) AND `encode` (SentenceTransformer); only the `else` branch (neither) → None → "no embedder interface".
  - `evidence_selector.py:637-641` caches the `_load_embedder()` handle; sentinel `False` = "tried and failed" so the loud-fallback fires once and then the cached-failed handle persists every round.
- MY DIAGNOSIS (CONFIRM OR CORRECT): the wrong-module import is a real bug, but `_similarity_scores` should still work via `.encode()`. The persistent every-round lexical fallback means the cached embedder handle is `False` (load failed on first attempt) — likely because the first `_load_embedder` SentenceTransformer load raced/OOM'd on the crammed GPU, caching `False` permanently. So B4 darkness is plausibly a COMBINATION of (a) the wrong import (noise + prevents the EmbeddingService primary path) and (b) GPU pressure failing the embedder load → cached-False. Adjudicate whether the import fix ALONE suffices or whether (b) the GPU placement is also required, AND whether the cached-`False` should be made retryable.

### P0-3 — W5 relevance reranker (Qwen3-Reranker) CUDA-OOM every round → "full weight for all passages" (down-weight-no-drop = §-1.3-correct, but the winner is DARK)
- Cause: 8B embedder (~16GB) + mineru25 VLM (24GB, batch=8) + the reranker all default to cuda:0; single-GPU pin removed the 2nd-card escape. Device knobs found: W5 `PG_CONTENT_RELEVANCE_DEVICE` (content_relevance_judge.py:338, default "cuda"); W7 `qwen_reranker_scorer` device=None→"cuda" (:65); embedder `SentenceTransformer(model_name)` no device (prefetch_offtopic_filter.py:118 → cuda:0); NLI verifier HARDCODED `device="cuda:0"` (nli_verifier.py:92).

### P0-1 / P1-9 — no retrieval-phase wall-deadline; runs ground for tens of min on a 90s-per-URL fetch-timeout storm + AccessBypass daemon-thread leak (→125, never reaped). The proven hang-fixes (#1264/#1338) covered generate/verify, NOT retrieval.

### P1-8 — scope_query_validator drops snowball sub-queries to "0 unique candidates" (possible regression of I-retr-001 #1340). CONFIRM it drops only off-scope QUERIES, never sources.
### W2 (FS-Researcher qgen) + W7 (Qwen3-Reranker-4B) — ran/never-reached but NO identity tag in the log → cannot positively confirm vs a silent IterResearch/wrong-reranker swap.

## PROPOSED CORRECTED-RELAUNCH FIX SET (confirm scope: minimal to make winners FIRE + fail LOUD; not a rewrite)
1. **P0-2a import fix** — repoint `EmbeddingService` import (prefetch_offtopic_filter.py:104 + grep ALL `nli_verifier import EmbeddingService` sites) → `from src.utils.embedding_service import EmbeddingService`. Make the cached-`False` handle RETRYABLE (don't permanently poison on one transient load failure).
2. **P0-2b/P0-3b WINNER-FIRING fail-closed gate — covers W5 + W6 + W7 (per Codex iter-1)** — a REQUIRED-WINNER firing gate that REJECTS the run when a relevance-layer winner is structurally dark, at TWO seams: (i) PRE-SPEND GPU smoke (below) blocks before any paid token; (ii) a POST-RETRIEVAL / PRE-GENERATION assertion that ABORTS before the expensive generation if W6 embedder/B4 semantic scorer is structurally unavailable (import/load fail → lexical-cut), OR W5 content-relevance reranker logged `device=unavailable`/full-weight-fallback, OR W7 selection reranker failed to load. Make the cached embedder handle RETRYABLE (don't permanently poison on one transient load failure); only the STRUCTURAL-unavailable state (load/import fails, not a single transient encode) trips the gate. **Distinction (so this does NOT violate the operator's "verifier never holds the report" faithfulness rule):** this is a CONFIG/WIRING firing-gate (a winner is dark ⇒ the run is not winners-only ⇒ abort before producing a falsely-labeled deliverable), NOT a faithfulness hold on rendered claims — the faithfulness engine (strict_verify/4-role) still always releases + labels per §-1.3.
3. **P0-3 GPU placement (PRECISE — from a primary-source GPU-placement investigation; confirm it)** — relaunch with BOTH GPUs visible (`unset CUDA_VISIBLE_DEVICES`) and a STATIC 2-card split:
   - **card0 (~18GB):** W6 embedder Qwen3-Embedding-8B (~16GB) + W5 content-relevance reranker 0.6B (~2GB) + W10 consolidate-NLI cross-encoder (<1GB).
   - **card1 (~15-19GB):** W4 mineru25 VLM (~6-10GB, sizes batch to free mem) + W7 selection reranker Qwen3-Reranker-4B (~9GB).
   - **Code edits (4):** (a) `prefetch_offtopic_filter.py:118` + (b) `src/utils/embedding_service.py:122` — honor new `PG_EMBED_DEVICE` (try/except → no-arg fallback + LOUD log if the installed sentence-transformers rejects `device=`); (c) `qwen_reranker_scorer.py` / `evidence_selector.py:2558` — honor new `PG_RERANKER_DEVICE` for W7; (d) `nli_verifier.py:92` — replace hardcoded `device="cuda:0"` with `os.getenv("PG_NLI_DEVICE","cuda:0")` (LAW-VI; low priority, FaithLens off the critical path).
   - **Env knobs (no code):** `PG_MINERU25_DEVICE_MODE=cuda:1`, `PG_RERANKER_DEVICE=cuda:1`, `PG_EMBED_DEVICE=cuda:0`, `PG_CONTENT_RELEVANCE_DEVICE=cuda:0`. Do NOT re-pass the slate's winner force-ONs (run_gate_b sets PG_CLINICAL_PDF_EXTRACTOR=mineru25 / PG_RERANKER_MODEL=qwen3 / PG_EMBEDDER_MODEL=qwen3 / PG_CONTENT_RELEVANCE_JUDGE=1 / PG_CONSOLIDATION_NLI=1). The new `PG_*_DEVICE` reads are additive — NOT stripped by the SLATE-PURITY allowlist (it gates force-ON *values*, not device reads) — CONFIRM this holds (the device knobs must not trip the NO-LOSER/SLATE-PURITY gates).
   - **WHY the cert run didn't OOM (primary-source):** the cert run had mineru25 OFF + W7-4B OFF + small flan-t5 NLI, so cuda:0 held only the 8B embedder — huge headroom. The winners-ON deepfix path is the FIRST to co-resident all the heavy models; my single-GPU pin REMOVED a card. (NOT auto-spread.)
   - **PRE-SPEND GPU SMOKE (per Codex iter-1 — cover ALL 4 co-resident heavy loads, not just mineru):** with the static split env, load + nvidia-smi-verify each lands on its assigned card and NO OOM: W6 embedder Qwen3-8B on cuda:0, W5 0.6B reranker on cuda:0, W7 4B reranker on cuda:1, mineru25 1-PDF parse on cuda:1 — ideally co-resident (mineru sizes batch to FREE mem, so W7 must already be resident on cuda:1). TOP RISK = mineru honoring `cuda:1` on the installed build; if it grabs cuda:0 → co-OOM with the embedder; fallback = `PG_MINERU25_BACKEND=vlm-http-client` against `mineru-api` launched with `CUDA_VISIBLE_DEVICES=1`. Device knobs are LAUNCH-ENV reads (NOT slate force-on entries) so SLATE-PURITY/NO-LOSER don't need allowlist changes.
4. **P0-1/P1-9 retrieval wall-deadline — RELAUNCH-BLOCKING + partial-fetch HANDOFF (per Codex iter-1)** — NOT a bare run-level wall (that only yields a timeout artifact, never completes+renders). Add a per-question RETRIEVAL-PHASE deadline that, on expiry, force-HANDS-OFF the already-fetched partial corpus to tiering→consolidation→generation→verify→render WITH explicit disclosure of the partial-fetch cutoff (sources still pending are disclosed, never silently dropped — §-1.3). This is relaunch-blocking: without it a slow-fetch tail grinds (the 90s-timeout storm) and the run never reaches CLOSE.
5. **W2/W7 identity tags** — add a one-line slate-winner log tag for the qgen strategy + the reranker model so the next run positively confirms them.

## FAST-FOLLOW (confirm these can be deferred, NOT in the relaunch-blocking set)
- P1-5/6/7 fetch-layer perf: cancel/join the AccessBypass worker on timeout (bounded pool), lower the 90s per-URL ceiling, route direct-PDF URLs to Zyte httpResponseBody/PDF mode.
- P2-11 NUL-sanitize before readability; P2-12 schema-bind GLM tier parser; P3-13 reconcile the single cost cap ($50 vs $150 vs the $40 named).

## HARD CONSTRAINTS
Faithfulness engine untouched. §-1.3 weight-not-filter / consolidate-not-drop (every degrade must stay a disclosed DOWN-WEIGHT, never a drop). The 14 winners must all FIRE on the relaunch. Acceptance = a fresh run that COMPLETES + RENDERS, then a §-1.1 line-by-line audit (a killed/banked retrieval log structurally cannot validate a relevance-layer fix).

## QUESTIONS FOR YOU (Codex)
1. Is the P0-2 root-cause right? Is the import fix ALONE enough, or is the cached-`False`/GPU-pressure interaction the real darkener (so the fix MUST include GPU placement + retryable handle + the canary)?
2. Is the fail-closed canary the right safety (vs e.g. a hard pre-run probe)? Where should it live so it can't false-abort on a transient?
3. GPU topology: ONE-run-both-GPUs sequential vs TWO-VMs parallel — which, given the constraints?
4. Is the retrieval wall-deadline relaunch-BLOCKING or fast-follow?
5. Any P0/P1 in this plan I'm missing, or any proposed fix that violates §-1.3 / risks faithfulness?

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
Static review only — do NOT run code. Verdict APPROVE iff the plan's root-cause + fix set are correct with zero P0/P1 gaps.
