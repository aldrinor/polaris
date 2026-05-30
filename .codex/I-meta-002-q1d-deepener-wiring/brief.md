RULE NOW — emit the YAML verdict block FIRST. APPROVE this CONCRETE plan or REQUEST_CHANGES with specifics. This is the HIGHEST provenance-impedance fix (it feeds strict_verify) — top scrutiny. NOT unconditional no-spend (when ON+triggered it makes S2+LLM+fetch calls, bounded by PG_MAX_COST_PER_RUN).

HARD ITERATION CAP: 5. Iter 1 of 5. Front-load ALL findings; reserve P0/P1 for real execution risks.

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
p0: [...]
p1: [...]
p2: [...]
required_changes: [...]
convergence_call: accept_remaining
```

# Codex brief-gate (iter 1) — PR5 wire evidence_deepener into the launch sweep behind a flag + Stop-RAG conditional trigger (#942-deepener). TOP CODEX SCRUTINY (feeds strict_verify).

Codex-verified depth gap (#941): POLARIS's frontier-grade citation-snowball `evidence_deepener` (150-cap,
backward+forward S2 citation chase + recommendations + mechanism search) is wired ONLY into Pipeline B
graph.py — NOT the launch sweep. This wires it into `run_honest_sweep_r3.py` behind a flag with a Stop-RAG
value-based trigger (don't always-deepen). Lands on PR1 rerank (#959) + PR2 decomposition (#960) + PR4
clinical backend (#962).

## GROUNDED FACTS (verified; do not re-explore)
- `src/polaris_graph/agents/evidence_deepener.py:85` `async def deepen_evidence(client: OpenRouterClient,
  state)` — TWO args: an OpenRouterClient FIRST, then state. Gated by module constant `PG_EVIDENCE_DEEPENER`
  (default "1" = on). Reads `state["iteration_count"]`, `state["evidence"]` (list of dicts with
  `source_url`), `state["original_query"]`; returns `{}` if `SEMANTIC_SCHOLAR_API_KEY` absent (line 111-114). Returns `{"deepened_papers": [...],
  "deepener_stats": {...}}`. Each deepened paper (`_normalize_s2_paper` :711) has `paperId/title/abstract/
  url` (OA-PDF url else S2 url) + `full_text` (after `_fetch_full_text` :891, up to 25000 chars). Caps:
  PG_DEEPENER_EVIDENCE_CAP=150, PG_DEEPENER_TIMEOUT=720, per-op timeout 120.
- `run_honest_sweep_r3.py` R-6 expansion (~1850-1905): fires a SECOND `run_live_retrieval(...)` with
  expansion queries when completeness has uncovered topics, then MERGES — `existing_urls = {s.url for s in
  retrieval.classified_sources}`; append new `classified_sources`; renumber new `evidence_rows` as
  `ev_{base+i:03d}`; recompute `compute_tier_distribution` + `check_completeness`. THIS is the merge to reuse.
- `run_live_retrieval(..., seed_urls=[...])` (PR1-confirmed, live_retriever.py:1228-1234): seed URLs are
  injected as FRONT candidates that go through the SAME fetch → `classify_source_tier` (1646) →
  `is_content_starved` (1060, drops thin) → `_build_provenance_quote(content, head_chars=1500,
  window_chars=500)` (1098) → `evidence_rows.append({...})` chokepoint as every other source. A seed counts
  as T1 ONLY if the tier classifier confirms the fetched content (NO laundering). fetch_cap is bumped by the
  seed count (additive).

## CONCRETE PROPOSAL — OPTION A (PRIMARY, safest: reuse the EXACT chokepoint via seed_urls)
A. **New `src/polaris_graph/retrieval/deepener_sweep_adapter.py`** (pure orchestration helpers):
   - `build_deepener_state(evidence_rows, question) -> dict`: `{"iteration_count": 0, "evidence":
     [{"source_url": ev.get("source_url") or ev.get("url")} ... for ev in evidence_rows], "original_query":
     question}` (deepener reads `source_url` + `original_query`).
   - `discovered_urls(deepener_output, *, cap) -> list[str]`: extract `paper["url"]` (non-blank, deduped)
     from `deepener_output.get("deepened_papers", [])`, capped at `PG_SWEEP_DEEPENER_URL_CAP` (e.g. 20).
B. **Wire into `run_one_query`** AFTER the R-6 expansion block, BEFORE the adequacy==abort gate:
   - Gate: `PG_SWEEP_EVIDENCE_DEEPENER` (default "0" — it SPENDS) AND `SEMANTIC_SCHOLAR_API_KEY` present AND
     a **Stop-RAG conditional trigger** fires: only when the corpus is BORDERLINE — e.g. adequacy is not
     comfortably adequate OR completeness still has uncovered topics after R-6 (don't deepen an
     already-sufficient corpus). Propose the exact borderline predicate.
   - On trigger: `state = build_deepener_state(retrieval.evidence_rows, q["question"])`;
     `out = run_deepener_sync(state)` — the adapter's event-loop-guarded sync wrapper constructs an
     OpenRouterClient and calls the real `deepen_evidence(client, state)` (2-arg), closing the client;
     `urls = discovered_urls(out, cap=PG_SWEEP_DEEPENER_URL_CAP)`.
   - Feed those URLs through the IDENTICAL pipeline: `deep_retrieval = run_live_retrieval(research_question=
     q["question"], amplified_queries=[], protocol=protocol, max_serper=0/min, max_s2=0/min, fetch_cap=
     <bounded>, enable_openalex_enrich=True, enable_prefetch_filter=False, domain=q["domain"],
     seed_urls=urls)` — so every deepened paper is fetched + tier-classified + provenance-quoted through the
     SAME chokepoint (a thin/abstract-only paper is DROPPED by is_content_starved — correct fail-closed).
   - MERGE with the R-6 pattern (dedup by url, renumber `ev_{base+i:03d}`, recompute tier distribution +
     completeness). Log `[deepener] +N papers discovered, +M evidence rows after chokepoint`.
C. **Cost/safety:** default OFF. When ON+triggered: deepener S2+LLM calls (its own caps+720s timeout) + one
   bounded run_live_retrieval fetch pass, all under `PG_MAX_COST_PER_RUN` (BudgetExceededError still binds).
   NO laundering — deepened papers earn tier only from fetched content via the existing chokepoint.

## OPTION B (alternative — Codex rule which is safer): a `deepened_papers_to_evidence_rows` adapter that
builds evidence rows DIRECTLY from each paper's already-fetched `full_text` via `classify_source_tier` +
`is_content_starved` + `_build_provenance_quote` (no re-fetch, but REPLICATES the chokepoint row-build
logic — strict_verify-compatibility risk if the replication drifts from live_retriever's loop). Option A
re-fetches (redundant with the deepener's full_text) but reuses the EXACT chokepoint with ZERO new
row-build code — I judge A SAFER for a strict_verify-feeding path. Confirm or choose B with rationale.

## Constraints / frozen
- snake_case; explicit imports; no except:pass; fail-closed; ≤200 LOC. Untouched: strict_verify /
  provenance_generator / D8 / runtime lock / the 5 PR-10 contracts / the verified core. The deepener feeds
  INPUT evidence ONLY through the existing fetch/tier/provenance chokepoint — verification semantics
  unchanged. asyncio.run inside the sync sweep must not deadlock an existing event loop (run_one_query is
  sync top-level — confirm no running loop).

## The real risks to rule on
1. Option A vs B: which is safer for feeding strict_verify? (Claim: A — reuses the exact chokepoint, thin
   papers dropped by is_content_starved, zero row-build replication.)
2. The Stop-RAG borderline trigger: what exact predicate avoids always-deepening (waste) AND deepening a
   sufficient corpus, while firing when depth is actually needed? (adequacy borderline OR completeness
   uncovered>0 after R-6?)
3. asyncio.run(deepen_evidence(...)) from the sync run_one_query — any running-event-loop / re-entrancy
   risk? (run_one_query is called from the sync sweep main; confirm.)
4. Cost bound: default-OFF + PG_MAX_COST_PER_RUN + deepener caps + URL cap + bounded fetch pass — is the
   worst-case spend bounded and fail-loud (BudgetExceededError)?
5. NO laundering: confirm a deepened paper counts as T1 only if the tier classifier confirms FETCHED
   content (via seed_urls through the chokepoint), never on abstract/metadata alone.

APPROVE iff this wires the deepener behind a default-OFF flag + Stop-RAG trigger, routes every deepened
paper through the EXISTING fetch/tier/strict_verify chokepoint (no laundering, thin-drop fail-closed),
bounds spend under PG_MAX_COST_PER_RUN, leaves strict_verify/D8/verified-core untouched, and is testable
offline (FAKE deepener + FAKE transport).

---

## REVISED SPEC — Codex brief-gate iter-1 REQUEST_CHANGES adopted (binding, all built + diff-APPROVE'd)
1. EXACT trigger: `should_trigger_deepener` = flag_on AND has_s2_key AND has_seed_evidence AND
   (adequacy.decision != "proceed" OR completeness.total_uncovered > 0). Never fires on proceed+0.
2. Event-loop guard: `run_deepener_sync` runs `asyncio.run` normally; if a loop is already running, runs
   in an ISOLATED thread (never RuntimeError mid-sweep). Real path constructs OpenRouterClient and calls
   `deepen_evidence(client, state)` (2-arg), closing the client in finally.
3. Option A confirmed: discovered URLs fed via `run_live_retrieval(seed_urls=urls, seed_only=True)` — the
   new `seed_only` flag suppresses Serper/S2 + domain backends so ONLY the deepener URLs pass the existing
   fetch/tier/strict_verify chokepoint (no laundering; thin-drop fail-closed). fetch_cap=min(len,url_cap);
   url_cap normalized non-negative.
4. ATOMIC merge: stage classified_sources/evidence_rows in local copies, dedup by URL (seen-set updated,
   only accepted-source evidence rows appended → no inflation), renumber ev_{base+i:03d}, recompute
   dist/completeness/adequacy on the staged corpus, commit only on success; outer except fail-open.
5. Tests: trigger predicate; build_state (whitespace-url dropped); discovered_urls (dedup+cap, cap<=0→[]);
   run_deepener_sync (no-loop + inside-running-loop no-raise); no-laundering (is_content_starved drops
   thin); seed_only skips serper/s2/domain. NO SPEND offline.

---

## REVISED SPEC — Codex brief-gate iter-2 REQUEST_CHANGES adopted (binding)
P0 (doc-only contradiction, code was already correct): the GROUNDED FACTS section above now states the
ACTUAL `async def deepen_evidence(client: OpenRouterClient, state)` 2-arg signature (it previously said
1-arg). The shipped code (`run_deepener_sync` default closure) already constructs an `OpenRouterClient`,
calls `deepen_evidence(client, state)`, and closes the client in `finally` — diff iter-4 APPROVE.
Required changes both satisfied:
1. Call signature confirmed + implemented: `deepen_evidence(client, state)` (2-arg). No 1-arg call anywhere.
2. NEW regression test pins the real adapter call shape so it can't silently drift:
   `test_run_deepener_sync_real_path_uses_2arg_signature_and_closes_client` patches the real
   `evidence_deepener.deepen_evidence` + `OpenRouterClient`, calls `run_deepener_sync(state)` with NO
   injected `deepen_fn`, and asserts (a) a client instance was constructed and passed as arg 1, (b) state
   passed as arg 2, (c) `client.close()` was awaited. A future revert to a 1-arg call fails this test.
3. seed_only confirmed: `run_live_retrieval(seed_only=True)` suppresses Serper/S2 + domain backends ONLY;
   seed-url fetching + `classify_source_tier` + `is_content_starved` + `_build_provenance_quote` still run,
   so the strict_verify chokepoint is preserved (test_seed_only_skips_serper_s2_and_domain_backends +
   test_no_laundering_thin_deepened_content_dropped_by_chokepoint). 8/8 adapter tests pass offline, NO SPEND.
