# Codex independent forensic — I-arch-001 (#1245): POLARIS pipeline architecture

You are doing an INDEPENDENT, serious, exhaustive forensic of the POLARIS deep-research pipeline (this repo). Claude is running the same forensic in parallel; we cross-review. Read the ACTUAL code, cite file:line.

## The operator's INTENDED architecture (judge everything against it)
1. Source many URLs (thousands) -> fetch FULL content with EVERY tool (don't lose good sources to a weak fetcher / paywall / JS-render failure).
2. RELEVANCE gate -> keep on-topic.
3. WEIGHTING system -> score each kept source by credibility (peer-reviewed? high-reputation journal? gov? institute? working paper? news? social media?). WEIGHT, do NOT filter out. Social media STAYS at low weight (sometimes it reports a real journal).
4. CONSOLIDATION -> group sources carrying the SAME claim. Repetition = corroboration (the point of consolidate/distill/map-reduce). Multiple citations per claim is GOOD.
5. COMPOSITION -> use ALL relevant sources; each claim = "supported by X,Y,Z with weights"; the USER judges. The pipeline must NOT hard-drop a source to hit a number.

The ONLY hard gate that stays is the FAITHFULNESS engine (strict_verify / NLI entailment / 4-role D8 / provenance) — a claim must be span-grounded. Everything else should be a WEIGHT or a CONSOLIDATION, not a DROP/CAP/THIN/TARGET.

## What went wrong (the thing to find)
The codebase accreted many drop/cap/filter/thin/target knobs that force a breadth NUMBER instead of weighting+consolidating+surfacing — e.g. PG_SPAN_PER_SOURCE_CITE_CAP, PG_LEGACY_SECTION_BREADTH_TARGET, PG_BREADTH_CANARY_MIN, PG_RELEVANCE_FLOOR, PG_MAX_EV_PER_SECTION, PG_LIVE_MAX_EV_TO_GEN, a 150-source outline menu cap, the new PG_SCOPE_* gates, finding_dedup, fact_dedup. Empirically: the relevance signal is so weak it scored Wikipedia 0.583 (above the clean median 0.5) while burying good on-topic papers; the generator over-concentrates citations (one span cited ~30-49x); breadth was forced with caps/targets, then off-topic + low-cred sources leaked in (the result: span-faithful but contaminated, loses to ChatGPT on scope).

## Your deliverable (write to .codex/I-arch-001/codex_forensic.txt as your stdout)
1. MAP the real pipeline end-to-end (search->fetch->extract->relevance->weight->dedup/consolidate->distill->select->compose->strict_verify->cite). Start: scripts/run_honest_sweep_r3.py, scripts/dr_benchmark/run_gate_b.py, src/polaris_graph/retrieval/{live_retriever,evidence_selector}.py, src/polaris_graph/generator/{multi_section_generator,fact_dedup,provenance_generator}.py, src/polaris_graph/synthesis/finding_dedup.py. For each stage: file:line, what, sources-in->out, dropped/capped + why. Does a credibility WEIGHTING exist? Does CONSOLIDATION-by-claim exist?
2. CATALOG exhaustively every drop/cap/filter/thin/target/threshold (env knobs + hardcoded [:N] slices). For each: file:line, kind, and CLASSIFY: legit_faithfulness_gate | legit_relevance_gate | hack_should_become_weight | hack_should_become_consolidation | hack_should_be_removed | unsure, with why.
3. ASSESS against the intended architecture: the single biggest architectural divergences, in priority order.
4. RECOMMEND the migration: what to rip out, what to build (a source weighting system, a claim-consolidation/clustering stage, a weighted multi-attribution composition that uses ALL relevant sources). Reference established systems (STORM, GPT-Researcher, open deep-research, source-credibility scoring, claim clustering) if you know them.

Be exhaustive and concrete. This decides whether POLARIS gets rebuilt correctly or keeps accreting hacks.
