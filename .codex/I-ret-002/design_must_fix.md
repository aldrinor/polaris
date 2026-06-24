# I-ret-002 retrieval bake-off — design must-fix list (before Codex gate)

Source: 7-layer design Workflow + 2 adversarial §-1.1/§-1.3 critics (both `needs_fixes_material`).
Raw design: `.codex/I-ret-002/bakeoff_design_v1_raw.json`. Every fix below is a SCOPED addition — no
layer needs a redesign.

## Material fixes (both critics agree)

1. **SYSTEMIC GATE-0 GAP — per-candidate LIVENESS canary on EVERY layer (biggest fix).**
   search / fetch / reranker / embedder GATE-0 canaries test only the scorer MATH on synthetic inputs.
   They never assert a LIVE candidate returns real non-stub output. So a keyless Zyte (silent no-op),
   an empty Exa list, or a load-failed reranker scores a believable-LOW number instead of failing
   loud — the drb_72 class. FIX: port the per-candidate liveness smoke (quality_weight already has it)
   to every layer: before scoring, each candidate must return a known-good non-stub result on a fixed
   probe, else the run FAILS LOUD (non-zero exit). Assert keys present (ZYTE_API_KEY etc.) in the env.

2. **Reranker off-topic-DROP is a §-1.3 weight-not-filter breach.** The metric rewards a hard DROP at
   a calibrated threshold; the incumbent only count-cuts. FIX: remove the off-topic-drop facet OR
   recast as pure DEMOTION-weight (off-topic → gain 0, never removed). PROD INVARIANT: the reranker may
   only RE-ORDER, never remove a non-junk source upstream of strict_verify/NLI/4-role.

3. **Search gold = single canonical URL breaks basket-faithfulness.** A valid alternate/mirror source
   scores 0. FIX: gold(f) becomes a per-finding SOURCE SET (canonical DOI + accepted equivalents),
   matched by DOI/identifier, NOT exact URL. The claimed "reuse _normalize_url + DOI-canon" does not
   exist — build a real DOI/PMID matcher (Crossref/Unpaywall).

4. **idx66 gold denominator collapses** — only 3 of 48 info_recall items carry a resolvable title.
   FIX: resolve gold at the CLAIM level, not the title level (judge maps each untitled finding to its
   supporting source), so recall is representative.

5. **Dedup "exhaustive over all C(N,2) pairs" is arithmetically impossible** (500 bodies = 125k pairs
   vs a 0.5-day estimate). FIX: shrink the exhaustively-labeled set to N≈50–80 (≤3,160 pairs), or
   stratified pair sampling with a stated bound.

6. **Ground-truth quality guards.** quality_weight must pair authoritative-vs-spam WITHIN source-type
   (not just within-topic) or it becomes a "source-type = better" proxy. Credibility labels (reranker,
   quality) must be INDEPENDENT of POLARIS's own tier metadata. embedder Axis-A keyword POS/NEG needs
   judge/human confirmation (pattern-presence-as-ground-truth otherwise). content_extraction GATE-0 #3
   (reproduce WebMainBench published per-extractor numbers) is only valid if the OFFICIAL scorer exists
   — confirm first, else it is circular.

## The real long pole: ground-truth fixtures (all 7 layers blocked on one)

But most layers can ride PUBLISHED 2025/2026 benchmarks (legitimate human-annotated ground truth — the
same sets the recency-audit papers used), so we do NOT hand-build all seven:

- **Reuse published (no new fixture):** content_extraction → WebMainBench (7,809 labeled pages + gold
  Markdown + official ROUGE-N scorer); reranker/embedder relevance → MTEB-R / BEIR; late-interaction
  reasoning axis → BRIGHT. These give independent, citable winners.
- **Build small, judge-labelable (POLARIS-specific, parallel judge + sample audit):**
  `drb_gold_sources.jsonl` (search, claim-level via Crossref/OpenAlex + judge), the clinical
  quality-weight fixture, the near-dup pair fixture, the reranker credibility labels.
- **Reuse existing in-repo:** embedder Axis-A `relevance_scorer_bakeoff.py` LABEL_SETS (+ judge confirm).

## Build order (ready-first; cost-no-object parallel)
1. Layers that ride a published benchmark run FIRST (extraction, embedder/late-interaction, reranker
   relevance) — minimal fixture work, immediate GPU bake-off.
2. POLARIS-specific judge-labeled fixtures built in parallel (search gold, quality clinical, dedup
   pairs, reranker credibility), GATE-0'd, then those layers run.
3. All layers: liveness canary + scorer-math canary green BEFORE any candidate score is trusted.

Anchors: #1294 (I-ret-002), design Workflow wk4ksyt2j, landscape docs/retrieval_landscape_2026.md.
