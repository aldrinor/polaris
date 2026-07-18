# 0006. Pipeline DNA: WEIGHT-AND-CONSOLIDATE, not FILTER-AND-CAP; faithfulness is the only hard gate

Status: accepted

Date: 2026-06-13

## Context

Operator-locked (2026-06-13, I-arch-001 #1245) after a full day was lost symptom-patching the pipeline with hardcoded caps, targets, and thinners to force a breadth number upward. The right credibility-weighted design already existed and was Codex-approved on 2026-06-07; the waste came from re-building breadth hacks instead of executing it. This is the design genome that overrides other design choices on conflict (`CLAUDE.md` §-1.3).

## Decision

Three binding principles govern every retrieval, selection, and composition decision.

1. WEIGHT, don't FILTER. Every relevant source flows through to composition carrying a credibility WEIGHT. The T1-T7 tier classifier and `authority_score` are a per-citation weight surfaced to the user, never a rank-then-drop hard filter. Social media, preprints, and low-tier sources stay at low weight; they are never hard-dropped to hit a number.
2. CONSOLIDATE, don't DROP. Group same-claim sources into a basket. Repetition is corroboration; multiple citations per claim is good and expected. `finding_dedup`/`fact_dedup` keep ALL sources per claim and operate on qualitative claims too, never numeric-only, never delete-all.
3. BASKET FAITHFULNESS. Judge a claim against its whole basket of supporting sources, never a single URL or span. The verdict carries the corroboration count, weights, and agreement. This STRENGTHENS faithfulness; it never relaxes it.

The faithfulness engine (strict_verify / NLI / 4-role D8 / provenance / span-grounding) is the ONLY hard gate. Everything else is a WEIGHT or a CONSOLIDATION — never a DROP, CAP, THIN, or TARGET. The fix for any breadth or quality shortfall is a SURGICAL re-wire of the machinery that already exists (STORM retrieval, Zyte/crawl4ai/distill, the tier classifier, `finding_dedup`/`fact_dedup`) to the right semantics — never a rewrite, never over-kill.

## Consequences

- Breadth and quality EMERGE from honest weighted multi-attribution; they cannot be forced. If you catch yourself adding a knob to make a metric hit a target, STOP — that knob IS the bug. The named, banned day-waster bolt-ons include `PG_SPAN_PER_SOURCE_CITE_CAP`, `PG_LEGACY_SECTION_BREADTH_TARGET`, `PG_BREADTH_CANARY_MIN`, and scope hard-filters.
- Single-source verification is a known blind spot, so a verdict must carry its basket's corroboration count and weights, not a bare pass/fail.
- Because every upstream change can only add an already-fetched source or re-rank it, every such change is provably faithfulness-safe — it cannot alter admissibility, only visibility.
- Two later decisions bound this genome: ADR 0008 carves out a narrow deletion path for genuine junk, and ADR 0009 gives the "never silently drop" promise its data model.
