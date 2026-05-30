I have enough grounding from the inputs plus the advisor's confirmation. Writing the plan now.

# POLARIS Pre-Q1 Build Plan â€” Beat-Frontier-on-Depth, Keep-Faithfulness-Edge

## 1. Ordered build sequence (depth â†’ conflict â†’ rest)

Each unit is one issue-sized PR (â‰¤200 LOC, 5-artifact triple, Codex twice). Effort is right-sized per the input split, not uniform.

**DEPTH (build first â€” close the evidence-depth gap to Gemini 3.1 Pro DR / ChatGPT 5.5 Pro DR):**

1. **#943 â€” fetch-cap retune + doc fix.** `S`. Adopt: test-time breadth/depth tradeoff â€” raise the cap (20â†’40, serper/s2 8â†’12, env-overridable) but let `PG_MAX_COST_PER_RUN` be the hard ceiling; fix the wrong "per-query" comment to "total after dedup." Cheap enabler; do this first so the deepener and decomposition snowball onto a wider base.
2. **#942-clinical â€” Europe PMC clinical backend.** `M`. Adopt: keyless, full-text-resolving primary-literature backend (PMC/DOI only, never `europepmc.org` landing pages); fail-open, branch/flag-gated. Broadens the clinical corpus the deepener will then chase. Defer CT.gov (runtime 403) + openFDA/DailyMed (allowlist change) as named fast-follows.
3. **#942-deepener â€” wire `evidence_deepener` into the sweep behind a flag + conditional trigger.** `M`. Adopt: agentic iterateâ†’reformulate citation-snowball, but with Stop-RAG value-based stopping â€” fire only when corpus is borderline (default OFF). Reuse the R-6 merge path; route every deepened paper through the identical `classify_source_tier`/`is_content_starved`/`_build_provenance_quote` chokepoint (fail-closed drops).

**CONFLICT (build second):**

4. **#944 â€” qualitative present-vs-absent clinical conflict detection.** `M`. Adopt: high-precision rule-cue assertion-status (NegEx-style, present-vs-absent only, â‰¥2 distinct sources, span dedup) as the gate; local NLI is opt-in annotate-only, never a suppressor. Precision is the competitive lever â€” the numeric detector scored 0/3 on the real corpus.

**THE REST:**

5. **#946 â€” bare `[ev_NNN]` citation-leak scrub-or-resolve.** `S`. Adopt: every in-text marker must resolve to a bibliography entry or be scrubbed (canonicalize all marker forms in published text + synthesis).
6. **#948 â€” trial-name verifier recall (locality-aware body match).** `M`. Adopt: CiteGuard body-level match within a fail-closed local window (â‰¥2 content words + required numerics), restoring recall without re-opening the SURMOUNT-3â†’SURMOUNT-1 precision hole.
7. **exec-summary â€” verified-only extractive "Key Findings" block.** `S`. Adopt: executive summary is a digest of already-verified body sentences (verbatim, zero new claims), inserted between title and first section.
8. **#945 â€” per-call `retrieval_trace.jsonl` observability.** `M`. Adopt: OpenTelemetry GenAI retrieval-span vocab + a drop-reason extension; mirror the proven I-gen-004 write-through sink. Additive; gate untouched.
9. **#949 â€” verified-claim reuse (lexical-first, advisory-only).** `M`. Adopt: reuse agent-verified facts as first-class memory, but fail-closed â€” primed claims earn no provenance and must be re-grounded by strict_verify or dropped. Campaign-scope the KG across the 5 questions; embeddings/temporal edges are explicit stretch.

## 2. New gaps from the hunt that deserve their own issues (by severity)

**S0 â€” promote into the build, do NOT leave observe-only:**
- **#950a â€” query decomposition on the live path.** The 40â€“70-word golden questions fire as ONE Serper/S2 query (multi-part Q76 = ~5 sub-questions). No-network decomposition feeding `amplified_queries` (reuse the unwired PICO `query_planner` + a clause-splitter). This is the single highest-leverage depth gap.

**S1:**
- **#950b â€” fetch-time relevance rerank** before `candidates[:fetch_cap]` (local embedding cosine on title+snippet; round-robin across sub-queries). Today candidates are truncated by arrival order.
- **#950c â€” analyst-synthesis is unverified AND un-sanitized.** ~70% of the shipped report is built from raw `<<<evidence>>>` blocks with no `sanitize_evidence_text` and no entailment/negation screen. Route through sanitizer + add a no-network qualitative-negation screen. (Clinical-safety hole hiding in plain sight.)
- **#950d â€” table/figure structured-results extraction.** Result-table numbers (per-arm efficacy/safety, integer counts, `%` without decimals) are flattened before provenance windows form, so strict_verify can't verify them.

**S2 (legitimate, lower priority for THIS benchmark):**
- **#950e â€” recency/publication-date tiebreaker** (fetched `year` is never used to rank; freshness detector is a stub).
- **#950f â€” source-diversity / per-domain cap + per-sub-query reservation** (tier quota â‰  topical diversity; one sub-topic can monopolize the cap).
- **#950g â€” generalize cross-source comparative synthesis** beyond the tirzepatide/SURPASS slot contract to a domain-agnostic entityâ†’attributes frame.
- **#950h â€” corpus-truncation as a fail-loud gate signal** (the 900s post-fetch budget can `break` mid-corpus yet still emit `success`; record `corpus_truncated` and treat it as partial/invalid in the Path-B gate).

## 3. Not-no-spend / clinical-safety call-outs needing extra Codex scrutiny

- **#942-deepener is NOT unconditional no-spend.** When the flag is ON it makes S2 + LLM calls (bounded by `PG_MAX_COST_PER_RUN`). Frame as "no *unconditional* spend." Its conversion shim feeds strict_verify â€” extra scrutiny on thin-quote / abstract-only papers slipping the gate. **Highest provenance-impedance risk.**
- **Europe PMC (#942-clinical) is no-spend but DOES hit the network** (free keyless). "no_spend" â‰  "no-network" â€” say so to Codex explicitly.
- **#948 trial-name recall modifies the verification logic itself** (`provenance_generator.verify_sentence_provenance`) â€” the most direct strict_verify touch in the whole program. The SURMOUNT-3â†’SURMOUNT-1 **locked-FAIL regression test is mandatory.** Top Codex scrutiny.
- **#944 and #949 are clinical-safety-critical even though both claim the gate is untouched.** #944 adds a new clinical-conflict surface to the shipped report; #949 opens a potential contamination path (a primed prior-question claim biasing a sentence past strict_verify). Both need the fail-closed regression tests called out in their plans.
- **#950c (analyst-synthesis unverified+unsanitized)** ships ~70% of the report under an evidence-grounding disclosure with no entailment/negation check and no delimiter sanitization (Invariant Â§9.1.7 bypass) â€” the exact lethal-Â§-1.1 negation class already caught on a real smoke. Treat as clinical-safety, not cleanup.
- All others (#943, #945, #946, exec-summary) are genuinely additive / no-network and do not touch strict_verify or D8.

## 4. Bottom line

**Conditional yes:** with the concern-1 depth fixes (#943 cap + Europe PMC + deepener) **AND the S0 query-decomposition gap (#950a) promoted into the build**, POLARIS can credibly out-depth frontier DR on the golden clinical set while keeping its faithfulness wedge â€” because every new candidate still passes the same strict_verify chokepoint. **Without #950a, the depth fixes only enrich a corpus that is still bottlenecked by firing a 40â€“70-word golden question as a single query, and POLARIS can lose a golden question on lane-2 coverage even at 100% faithfulness.**