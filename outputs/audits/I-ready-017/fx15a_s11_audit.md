# FX-15a §-1.1 audit — agentic seed source-label correctness (I-ready-017 #1118)

**Standard:** §-1.1 line-by-line on the REAL held drb_72
`outputs/audits/I-ready-017/run_artifacts/retrieval_trace.jsonl` (the trace is run-time OUTPUT,
so the bug is confirmed on the real artifact; the fix is proven by offline smoke since a fresh
trace needs a live run).

## The bug, on the real artifact (RB-02a) — line-by-line
Trace row schema: `{kind, url, backend, ...}`; `backend` carries the candidate `source` label.
Of the 155 trace rows, **41 carry `backend == "primary_trial_doi"`**. Verdict per row:
- **true doi.org primary-trial seeds: 0**
- **MISLABELED ordinary web/nav: 41 (100%)** — by class: 33 web-article, 5 conference, 3 SERP/nav.

The drb_72 question is AI/labor economics (workforce) — it has NO primary-trial DOIs configured,
so EVERY `primary_trial_doi`-tagged row is an agentic-discovered web URL falsely labeled a
primary-trial DOI seed. Sample line-by-line verdicts (each = MISLABELED):
- `https://www.aeaweb.org/articles?id=10.1257/jep.29.3.3` — web-article, NOT a primary-trial DOI.
- `https://www.aeaweb.org/news/cnn-01-31-17` — news page.
- `https://www.aeaweb.org/conference/2019/preliminary/paper/Ri8niS2D` — conference program.
- `https://www.aeaweb.org/journals/search-results?from=a&page=156&per-page=21` — SERP/nav page.
- `https://www.aeaweb.org/forum/232/...` — forum page.

## The fix (label-only; behavior-preserving)
- `live_retriever.run_live_retrieval` gains `seed_source` / `seed_query_origin` params (defaults =
  the #817 DOI-lane labels); the seed injection uses them.
- The reserved-seed split now keys on the SET `{primary_trial_doi, agentic_seed, deepener_seed}` so
  the relabel changes NO selection — all seed classes stay reserved/undroppable exactly as before
  (FX-15b is what later makes the web-discovered classes droppable).
- The agentic caller (`run_honest_sweep_r3.py`) passes `seed_source='agentic_seed',
  seed_query_origin='agentic_seed'`; the citation-snowball **deepener** caller passes
  `seed_source='deepener_seed', seed_query_origin='deepener_seed'` (Codex iter-1 P1: deepener URLs
  are primary-trial-DERIVED but NOT direct DOI seeds, so they must not pollute `primary_trial_doi`
  telemetry either); the off-mode DOI caller keeps defaults.
- `plan_sufficiency_gate.SENTINEL_ORIGINS` adds `'agentic_seed'` and `'deepener_seed'` so
  fallback-eligibility is identical to the old `primary_trial_doi_seed` (a sentinel) — no
  plan-sufficiency behavior change.

After the fix, those 41 rows would carry `backend == 'agentic_seed'` (truthful); no ordinary web
URL would carry `primary_trial_doi`.

## Offline smoke (proves the fix)
`pytest tests/polaris_graph/test_fx15a_agentic_seed_label_iready017.py` → 6 passed:
- **seed-split SET**: a `primary_trial_doi` + an `agentic_seed` + a `deepener_seed` seed + a
  `serper` non-seed through `_rerank_and_reserve(fetch_cap=1)` → ALL three seeds reserved &
  prepended, none dropped (the relabel does not change selection).
- **`_SEED_SOURCE_LABELS == {primary_trial_doi, agentic_seed, deepener_seed}`**.
- **`agentic_seed` & `deepener_seed` ∈ SENTINEL_ORIGINS** (and `primary_trial_doi_seed` still present).
- **injection label (stubbed `_fetch_content`)**: `run_live_retrieval(seed_source='agentic_seed', ...)`
  → kept row `source/query_origin=='agentic_seed'`; `seed_source='deepener_seed'` → `'deepener_seed'`;
  the DOI default call → `'primary_trial_doi'` / `'primary_trial_doi_seed'` (no DOI-lane regression).
- Regression: `test_live_retriever_rerank` (8) + `test_bug776_layer4_doi_seeds` (5) +
  `test_retrieval_trace` (7) + `test_plan_sufficiency_phase3` (26) all pass.

## Faithfulness check
Telemetry-correctness ONLY. The relabel does NOT change retrieval selection (SET split keeps both
seed classes reserved), grounding, strict_verify, or the 4-role decision. It makes `query_origin`
truthful and keeps plan-sufficiency fallback-eligibility identical. Custody lane-awareness
(v29/m44 keyed on `primary_trial_anchors`) is FX-14, which builds on this relabel.
