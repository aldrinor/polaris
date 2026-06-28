HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. Same quality bar every iteration.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on remaining non-P0/P1; no iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# DIFF GATE iter 2 — I-deepfix-001 corrected-relaunch fix (your 4 iter-1 P1s addressed)

Patch: `.codex/I-deepfix-001/relaunch_diff.patch` (20 files: 11 source + 9 tests). Read the repo read-only at C:/POLARIS to verify. Confirm your 4 iter-1 P1s are resolved + no new P0/P1.

## YOUR ITER-1 P1s — how each was addressed (verify)

**P1-1 W7 detection + hard-gate** —
- `winner_firing_gate._w7_reranker_requested()` (now line ~107): `return bool(value) and value not in _OFF_VALUES` (value=lowered/stripped PG_RERANKER_MODEL) → slate's `qwen3` reads as REQUESTED; explicit off-values stay not-requested.
- W7 LOAD-FAILURE telemetry: new typed `RerankerLoadError` in `qwen_reranker_scorer.py` wraps ONLY the load region (import / from_pretrained / .to(device) / token-ids); `_score_one` forward-pass raises plain (structural-vs-transient split). `evidence_selector._maybe_rerank_selection` sets sticky module signal `_W7_RERANKER_LOAD_FAILED` True on `RerankerLoadError`, False on success; a plain forward-pass exception does NOT flip it (no false-poison of the long-lived console server). The gate call in `run_one_query` passes `w7_load_failed=getattr(_ev_sel_mod,"_W7_RERANKER_LOAD_FAILED",None)` (None on query 1 = pending; a prior selection's structural load-fail trips N+1).

**P1-2 W6 semantic_fell_back wired** —
- New `LiveRetrievalResult.semantic_relevance_fell_back: bool=False`; set True at the single B4 fallback site (live_retriever ~4429, `_b4_selected is None`); threaded through the FS-Researcher + IterResearch merge paths (OR-combined). Gate call passes `semantic_fell_back=bool(getattr(retrieval,"semantic_relevance_fell_back",False))`. So a requested semantic winner that fell back to lexical (cache may be non-False) is now caught as W6 dark.

**P1-3 wall bounds parallel_fetch** —
- `audit_ir/parallel_fetch.py`: new `overall_deadline_monotonic` param; batch_deadline = min(own-budget-deadline, overall_deadline_monotonic) (batch_start uses time.monotonic — same clock as `_retrieval_deadline`). `live_retriever` passes `overall_deadline_monotonic=_retrieval_deadline` into the parallel_fetch call. Effective fetch bound drops from ~3960s to ≤ the 1800s wall.

**P1-4 wall disclosure serialized** —
- `_retrieval_manifest_section` (run_honest_sweep_r3.py ~3691) now serializes `retrieval_wall_hit`, `retrieval_queries_skipped`, `retrieval_candidates_unclassified`, `semantic_relevance_fell_back` (getattr defaults → byte-identical OFF). New pure `retrieval_wall_disclosure(...)` helper + a §-1.3 disclosure line in the report.md Methods section when wall_hit. FS + IterResearch `merge_retrieval_results` OR-combine the booleans + SUM the counts onto the merged result (the production adaptive-qgen path).

Tests: 91 pass (5 new + 4 updated-existing dr/retrieval tests that now assert the WIRING: test_parallel_fetch_ifetch003 overall_deadline cap, test_render_disclosures wall line, test_fs_researcher/source_funnel merge+manifest serialization, test_winner_firing_gate W7-qwen3 + semantic_fell_back→W6). All 11 source files py_compile.

## OUT OF SCOPE (proven pre-existing, NOT deepfix-caused — do not flag)
- `tests/dr_benchmark/test_offline_e2e.py` ×8 fail with `GateError: served metadata missing surrogate field 'provider_name'` at `pathB_run_gate.py:724` — a file the deepfix NEVER touches (not in the 20-file patch); a serving-metadata fixture/config issue, same class as the known serving-identity drift; confirmed failing on base.
- `tests/polaris_graph/test_post_fetch_loop_timeout.py::...openalex_wedges` — the SERIAL path (PG_USE_PARALLEL_FETCH=0), untouched by P1-1..P1-4; the 30s>15s is CPU model-load latency on this box, not the fix.

## RESIDUAL RISK (agent-disclosed — adjudicate P-level)
- The scorer load-vs-forward split (RerankerLoadError boundary INSIDE qwen_reranker_scorer) is a STRUCTURAL guarantee, NOT offline-test-backed (no-GPU tests monkeypatch the scorer wholesale). The caller-side typed-vs-plain dispatch IS tested. Is structural-only acceptable, or must a boundary test be added?

## HARD CONSTRAINTS
Faithfulness engine UNTOUCHED. §-1.3 (degrade = disclosed down-weight, never a drop; the firing-gate abort is a config/wiring gate, not a faithfulness hold). Device/retry/wall env vars are LAUNCH-ENV reads (not slate force-on; must not trip SLATE-PURITY/NO-LOSER). Acceptance after APPROVE = pre-spend VM GPU smoke (4 models on assigned cards) → relaunch → COMPLETE+RENDER → §-1.1 audit.

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
Static review only — do NOT run code. APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
