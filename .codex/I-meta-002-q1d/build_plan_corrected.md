# POLARIS Pre-Q1 Build Plan — CORRECTED ORDER (Codex gap-verify p0s adopted)

Codex CONFIRMED the gaps and REQUEST_CHANGES'd the ORDER with 3 p0 corrections (adopted):
(1) step-1 = fetch-cap + fetch-time rerank/per-sub-query reservation together (not cap-alone);
(2) promote analyst-synthesis safety hardening EARLY (clinical-safety, ships in ~70% of report);
(3) table/figure extraction BEFORE relying on clinical numeric provenance.

Each unit = one Codex-gated issue cycle (brief → codex brief gate → build → smoke → codex diff gate),
≤200 LOC, 5-artifact triple. NO SPEND / NO unconditional network in the fix itself unless flagged.

## Build sequence (depth-first, safety promoted early)
1. **PR1 — Retrieval foundation: fetch-cap retune (#943) + fetch-time relevance rerank + per-sub-query
   reservation (#951 q1d-b).** Codex step-1. Raise cap (20→40, serper/s2 8→12, env-overridable, bound by
   PG_MAX_COST_PER_RUN); rerank candidates by cosine(title+snippet vs question) using the already-loaded
   pooled_embedder + round-robin reserve k slots per sub-query BEFORE `candidates[:fetch_cap]`; fix the
   wrong "per-query" cap comment. No-spend (reuses loaded embedder).
2. **PR2 — Query decomposition on the live path (#951... q1d-a, the S0).** No-network decomposition before
   run_live_retrieval feeding amplified_queries (reuse PICO query_planner + clause splitter). Lands on the
   rerank base so sub-queries aren't truncated by arrival order. Highest-leverage depth gap.
3. **PR3 — Analyst-synthesis safety hardening (#953 q1d-c, CLINICAL-SAFETY).** Route evidence through
   sanitize_evidence_text + add a no-network qualitative-negation screen, OR default the layer OFF until
   hardened. Promote BEFORE the deepener/clinical-backend add more evidence volume into the synthesis.
4. **PR4 — Clinical retrieval backend: Europe PMC (#942-clinical) + table/figure structured extraction
   (#954 q1d-d).** Keyless full-text-resolving primary-literature backend (PMC/DOI only) + table-aware
   linearization in _fetch_content so result-table numbers survive into provenance. no_spend but DOES hit
   network (free keyless) — flag to Codex.
5. **PR5 — Wire evidence_deepener into the sweep behind a flag + Stop-RAG conditional trigger
   (#942-deepener).** Default OFF; fire only on borderline corpus; route every deepened paper through the
   identical classify_source_tier/is_content_starved/_build_provenance_quote chokepoint (fail-closed).
   NOT unconditional no-spend (S2+LLM when ON, bound by PG_MAX_COST_PER_RUN). Highest provenance-impedance
   risk → top Codex scrutiny.
6. **PR6 — Qualitative present-vs-absent clinical conflict detection (#944).** High-precision rule-cue
   assertion-status gate (≥2 sources, span dedup); local NLI opt-in annotate-only. Precision is the lever.
7. **PR7 — Citation-leak scrub-or-resolve bare [ev_NNN] (#946).** Every marker resolves to a bibliography
   entry or is scrubbed. Small.
8. **PR8 — Trial-name verifier recall: locality-aware body match (#948).** CiteGuard body-level match in a
   fail-closed local window (≥2 content words + required numerics). Modifies strict_verify — MANDATORY
   SURMOUNT-3→SURMOUNT-1 locked-FAIL regression test. Top Codex scrutiny.
9. **PR9 — Verified-only extractive exec-summary "Key Findings" block (#948 sibling).** Digest of
   already-verified body sentences (verbatim, zero new claims).
10. **PR10 — Per-call retrieval_trace.jsonl observability (#945).** OTel GenAI retrieval-span vocab + drop
    reasons; mirror the I-gen-004 write-through sink. Additive; gate untouched.
11. **PR11 — Verified-claim reuse, lexical-first advisory-only (#949).** Reuse agent-verified facts but
    fail-closed (primed claims earn no provenance; re-grounded by strict_verify or dropped). Campaign-scope
    the KG across the 5 questions.

## S2 follow-ups (after the above; lower priority for THIS benchmark)
- #955 recency tiebreaker, #956 source-diversity/per-domain cap, #957 generalize comparative synthesis,
  #958 corpus-truncation fail-loud gate signal.

## Clinical-safety call-outs (extra Codex scrutiny)
- PR5 deepener: not unconditional no-spend; conversion shim feeds strict_verify (thin-quote risk).
- PR4 Europe PMC: no_spend but hits network (free keyless).
- PR8 trial-name recall: modifies verify_sentence_provenance directly — locked-FAIL regression mandatory.
- PR3 (#950c) + PR6 (#944) + PR11 (#949): clinical-safety; fail-closed regression tests mandatory.

## Bottom line
With PR1+PR2 (foundation + decomposition) + PR4/PR5 (clinical depth) POLARIS can credibly out-depth
frontier on the golden clinical set while keeping faithfulness — every new candidate still passes the same
strict_verify chokepoint. Without the S0 decomposition, depth fixes only enrich a corpus still bottlenecked
by firing a 40-70-word question as one query.
