# POLARIS Q1 Launch Readiness — Capability Audit vs Frontier DR (#941)

Source: Claude Codex Workflow `q1-capability-readiness-audit` (6 grounded investigation agents +
synthesis), 2026-05-29. Pending Codex §-1.1 verification of load-bearing claims.

**OVERALL VERDICT: READY-WITH-GAPS** — POLARIS's audit-grade per-sentence faithfulness wedge is real,
live, and ahead of frontier DR; but the launch path (Pipeline A / `run_honest_sweep_r3.py`) is
disconnected from POLARIS's own frontier-grade depth and memory machinery, capped at ~20 sources, and
its conflict/memory layers are thin or dormant. The differentiator is shippable; the depth-parity story
is an INTEGRATION gap, not a capability gap.

## Concern 1 — Search Depth: GAP
- Flagship tirzepatide fired 41 Serper + 41 S2 searches but `fetch=20`, `corpus.count=20`
  (`manifest.json`). `PG_SWEEP_FETCH_CAP=20` (`run_honest_sweep_r3.py:1591-1593`) collapses everything.
- POLARIS's real depth engines — the 150-cap citation-snowball `evidence_deepener.py` and the
  12-round/~96-query agentic searcher with STORM — are wired ONLY into Pipeline B `graph.py`; grep finds
  zero references in the launch sweep. No clinical backend (`domain_backends.py:377` "clinical: rely on
  generic Serper + S2"; no PubMed/ClinicalTrials.gov/Cochrane).
- vs Frontier: materially behind on raw depth (frontier ingests 50-200+ with iterative deepening) — but
  it's an INTEGRATION gap; the machinery exists, just not on the path that ships.

## Concern 2 — Tool-Usage Tracking: PARTIAL
- `pathB_capture.py:142-151` `record_retrieval_attempt` stores only backend NAME strings in a set
  (presence flag). The 41+41+19 calls are not individually recorded with query/return-count/URLs.
- No per-call `retrieval_trace.jsonl` mirroring the per-call `reasoning_trace.jsonl` LLM roles get.
  Dropped candidates (~424 of 444) + fetch failures are aggregate scalars; kept sources have no backend
  field; per-query terms exist only transiently on stdout.
- vs Frontier: GAP on retrieval transparency; AHEAD on LLM-role provenance. Cannot prove a backend call
  returned the source it cites — a §-1.1 line-by-line gap.

## Concern 3 — Search Credit/Quota: PARTIAL
- Live probe: Serper `/search` 200 (`x-ratelimit-remaining=499/500`, refilling), S2 200. Both
  gate-mandatory backends (`pathB_run_gate.py:34`) live; no required key missing in `.env`.
- No programmatic check of Serper's TOTAL prepaid pool (header is a refilling window counter, not
  lifetime credits). `pg_preflight.py` T03 hard-fails on missing `EXA_API_KEY` though Exa is Pipeline-B-
  only — preflight isn't a faithful mirror of benchmark creds.
- vs Frontier: operational/sustainability difference, not quality. 5-question run ≈ 25-75 Serper calls —
  a non-issue; at scale the finite Serper pool is the one throttle frontier indexes lack. One-time manual
  dashboard check before launch.

## Concern 4 — Surface Source Disagreement: PARTIAL
- `contradiction_detector.py:575-651` is the SOLE conflict surfacer in Pipeline A — runs unconditionally
  (`run_honest_sweep_r3.py:2075-2087`), writes `contradictions.json`, forces both-sides disclosure. Does
  NOT silently collapse to one number.
- Numeric-regex ONLY → qualitative/directional conflicts (contraindication present-vs-absent, interaction
  warnings, eligibility) are structurally invisible. Precision 0/3 on the one real query (all flags were
  endpoint/dose grouping artifacts the report itself apologizes for). The 4-role gate is a per-claim
  grounding gate (off by default), not a conflict surfacer.
- vs Frontier: AHEAD on intent/honesty; undermined by thin, noisy, numeric-only detection blind to the
  qualitative clinical conflicts that hurt patients.

## Concern 5 — Report Quality: PARTIAL
- `verification_details.json` is a real per-sentence VERIFIED/DROPPED+reason ledger backed by the 6-check
  `provenance_generator.py:896-1290` verifier — no frontier DR ships this; it caught real fabrications.
- Verified core is THIN — 38 verified vs 35 dropped (~48% kept; docstring admits ~73% typical drop).
  Frontier-comparable length (3828 words) carried by the explicitly-UNVERIFIED Analyst Synthesis layer,
  which leaked a dangling `[ev_012]` citation into published `report.md:61` (scrub regex
  `analyst_synthesis.py:107` only matches `[#ev:...]`, not bare `[ev_NNN]`). Verifier over-drops correct
  prose (a fully-framed SURPASS-2 sentence dropped on a literal title-token miss).
- vs Frontier: WINS on auditability, COMPETITIVE on structure, TRAILS on verified-narrative depth.

## Concern 6 — Semantic Memory: GAP
- `verified_claim_graph.py:185-213` `query_related_claims` + `find_contradictions` are referenced ONLY by
  the store + its tests; nothing in `src/` reads the pool back into generation. The KG is WRITE-ONLY —
  zero snowball reuse at runtime. Flat SQLite table, NO edges (relatedness = lexical keyword overlap, not
  embeddings). Only writer is guarded default-OFF, runs only against a fake transport offline. Pipeline A
  imports no memory module. Agent-side: `MEMORY.md` is 40.2KB over a 24.4KB load limit, truncates today.
- vs Frontier: differentiated CONCEPT (frontier is stateless) but UNWIRED — zero runtime edge today.

## ORDERED Pre-Q1 Fix List
### Tier A — No-spend code fixes (convert dormant capability into shipped capability)
1. Wire `evidence_deepener.py` (citation snowball, 150-cap) into the launch path. Highest leverage. (C1)
2. Raise `PG_SWEEP_FETCH_CAP` from 20 to 50-100+ and re-tune MAX_SERPER/MAX_S2. (C1)
3. Add a qualitative/directional conflict path to the detector (`(did not|no|never|absent|without) +
   endpoint vocab → require atom OR escalate to LLM judge`). (C4)
4. Emit per-call `retrieval_trace.jsonl` (per query: backend/text/return-count/URLs; per kept source:
   backend; per drop: URL+reason). (C2)
5. Fix the citation-integrity leak — scrub bare `[ev_NNN]` too, or resolve to bibliography. (C5)
6. Loosen verifier trial-name matching to evidence body/snippet, not just `title`. (C5)
7. Fix preflight T03 honesty — drop Exa from Pipeline-A scope OR wire Exa into `live_retriever.py`. (C3)
8. Wire the KG read path — call `query_related_claims` back into generation. (C6)
9. Trim `MEMORY.md` under the 24.4KB budget. (C6)
10. Add an executive-summary / key-findings-up-front block to the report. (C5)

### Tier B — Operator / spend-gated
1. Manual Serper dashboard check before launch (prepaid pool not header-visible). (C3)
2. Procure/wire a dedicated clinical backend (PubMed E-utilities — `NCBI_API_KEY` already present —
   ClinicalTrials.gov, Cochrane). (C1, C3)
3. Operator-authorize the Gate-B 4-role canary against a live endpoint (so the per-claim gate + KG write
   actually execute in the shipped path). (C4, C6)
4. Validate the entailment judge's precision/recall on a labeled set (18 of 53 drops this run). (C5)
5. (Stretch) Embedding-based KG relatedness + claim edges (ChromaDB `cross_vector.py` is a start). (C6)

**Bottom line:** the wedge that wins Carney — auditable per-sentence faithfulness — is real and ahead of
frontier today. What blocks an unqualified READY is that POLARIS's own best depth/memory machinery is
sitting one import away from the launch path. Tier A 1-3 are the difference between "competitive on
safety, behind on depth" and "beats the frontier on both."
