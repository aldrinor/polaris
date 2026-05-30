# Claude architect audit — PR5: wire `evidence_deepener` into the launch sweep (I-meta-002-q1d #942-deepener)

**Issue:** #942-deepener (depth-fix queue, Q1 readiness). **Branch:** `bot/I-meta-002-q1d-deepener-wiring`.
**Both Codex gates APPROVE** — brief `codex_brief_verdict.txt` (iter-2 APPROVE, 0 P0/0 P1) and diff
`codex_diff_audit.txt` (iter-4 APPROVE, all P1/P2 resolved; re-gated against the final patch including the
2-arg regression test). **NO SPEND** — every test is offline with a FAKE deepener + FAKE transport.

## What this changes and why

Codex-verified depth gap (#941): POLARIS's frontier-grade citation-snowball `evidence_deepener` (backward +
forward Semantic Scholar citation chase + recommendations + mechanism search, 150-cap) was wired ONLY into
Pipeline B `graph.py` — it never ran on the launch sweep (`run_honest_sweep_r3.py`). Against ChatGPT-DR /
Gemini-DR, the citation snowball is a core differentiator for surfacing the primary-trial layer; leaving it
out of the sweep capped our corpus depth. This PR wires it in **behind a default-OFF flag with a Stop-RAG
value-based trigger** (deepen only a borderline corpus, never an already-sufficient one).

## Architecture decision: Option A (reuse the exact chokepoint) — Codex-confirmed safer

The deepener only DISCOVERS candidate primary-paper URLs. Those URLs are fed back through the EXISTING
`run_live_retrieval(seed_urls=...)` path: fetch → `classify_source_tier` → `is_content_starved` (drops thin)
→ `_build_provenance_quote` → `evidence_rows.append(...)`. A deepened paper therefore earns its tier ONLY
from FETCHED content, and a thin/abstract-only paper is DROPPED fail-closed. **Zero new evidence-row build
logic** that could drift from strict_verify. Codex agreed Option A is materially safer than Option B
(rebuilding rows from the deepener's `full_text`), which would replicate — and risk drifting from — the
live_retriever chokepoint.

## §9.1 invariant audit (the things that could hurt a patient)

- **No tier laundering** — verified by `test_no_laundering_thin_deepened_content_dropped_by_chokepoint`:
  thin deepened content hits `is_content_starved` → dropped; substantive full text survives the starvation
  gate then is tier-classified by the existing chokepoint, never on metadata/abstract alone.
- **strict_verify / provenance_generator / D8 / runtime lock untouched** — this PR adds INPUT evidence only
  through the existing fetch/tier/provenance chokepoint. Verification semantics unchanged.
- **Atomic, fail-open merge** — the deepener pass stages `classified_sources` / `evidence_rows` in local
  copies, dedups by URL (seen-set updated; only accepted-source rows appended → no adequacy inflation),
  renumbers `ev_{base+i:03d}`, recomputes tier-distribution / completeness / adequacy on the staged corpus,
  and commits only on success. The outer `except` fails open — a deepener failure never corrupts or aborts
  the base corpus.
- **`seed_only` is surgical** — `run_live_retrieval(seed_only=True)` suppresses Serper/S2 fan-out and domain
  backends ONLY; seed-url fetching + classification + provenance construction still run. Verified by
  `test_seed_only_skips_serper_s2_and_domain_backends`. Default `False` → existing callers unchanged.

## Cost bound (the money rule)

- Default OFF (`PG_SWEEP_EVIDENCE_DEEPENER` default "0").
- Requires `SEMANTIC_SCHOLAR_API_KEY` present (no-ops without it).
- Fires only on a BORDERLINE corpus: `adequacy.decision != "proceed" OR completeness.total_uncovered > 0`.
  Never on `proceed + 0 uncovered`.
- When ON+triggered: deepener S2 + one LLM mechanism-query call (its own caps + 720s timeout) + ONE bounded
  `run_live_retrieval` seed-only fetch pass; URL cap normalized non-negative; fetch_cap = min(len, url_cap).
- All under `PG_MAX_COST_PER_RUN` via the real `OpenRouterClient` — `BudgetExceededError` still binds and
  fails loud.

## Event-loop safety

`run_deepener_sync` runs `asyncio.run` on the normal sync sweep path; if a loop is already running (async
test harness / embedded caller) it runs the coroutine in an ISOLATED thread so it never raises RuntimeError
mid-sweep. The real path constructs an `OpenRouterClient`, calls the verified 2-arg
`deepen_evidence(client, state)`, and closes the client in `finally`.

## The 2-arg drift guard (brief-gate iter-2 P0)

The brief's GROUNDED FACTS had stated a stale 1-arg `deepen_evidence(state)` signature; the SHIPPED code was
already correct (2-arg). To stop this drifting silently I added
`test_run_deepener_sync_real_path_uses_2arg_signature_and_closes_client`: it patches the REAL
`evidence_deepener.deepen_evidence` + `OpenRouterClient`, calls `run_deepener_sync(state)` with NO injected
`deepen_fn`, and asserts (a) a client instance was constructed and passed as arg 1, (b) state as arg 2,
(c) `client.close()` was awaited. A revert to a 1-arg call fails this test.

## Accepted-remaining (Codex brief-gate P2, non-blocking)

1. "Keep `seed_only` default false + regression-tested" — DONE (default False; covered).
2. "Log skip reasons separately from trigger reasons" — the wiring logs the deepener trigger + the
   `[deepener] +N papers / +M rows` outcome; finer-grained skip-reason logging (flag off / no key / no seed
   evidence / sufficient corpus) is a cosmetic observability nicety, deferred as accept_remaining. Not a
   correctness or safety gap.

## Tests (offline, NO SPEND)

`tests/polaris_graph/test_deepener_sweep_adapter.py` (8) + the `seed_only` case in
`tests/polaris_graph/test_live_retriever_rerank.py`: trigger predicate (flag/key/seed/borderline),
`build_deepener_state` (whitespace-url dropped), `discovered_urls` (dedup + cap + cap<=0 → []),
`run_deepener_sync` (no-loop + inside-running-loop no-raise + real 2-arg path + client close),
no-laundering (is_content_starved drops thin), `seed_only` suppresses Serper/S2/domain. 8/8 pass.

## Verdict

Ships the deepener behind a default-OFF flag + Stop-RAG trigger, routes every deepened paper through the
EXISTING fetch/tier/strict_verify chokepoint (no laundering, thin-drop fail-closed), bounds spend under
`PG_MAX_COST_PER_RUN`, leaves the verified core untouched, and is fully testable offline. Both gates APPROVE.
Ready to queue for operator merge (Option A — no spend, no lock promotion).
