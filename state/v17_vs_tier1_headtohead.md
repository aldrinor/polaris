# V17 vs Gemini 3.1 Pro DR vs ChatGPT Deep Research — Head-to-Head

**Query**: "What is the efficacy and safety of tirzepatide for glycemic control and weight loss in adults with type 2 diabetes?"

## Quantitative comparison

| Metric | POLARIS V17 | ChatGPT DR | Gemini 3.1 Pro DR |
|---|---:|---:|---:|
| Total words (report.md / PDF text) | 2,077 | 4,830 | 6,835 |
| Body prose words | 1,098 | ~4,000 | ~6,000 |
| Unique URLs cited | 24 | **21** | 43 |
| Unique domains | ~15 | 14 | 21 |
| Sections | 5 | ~5 + table | ~7 + tables |
| Verified sentences / citation markers | 32 / 68 | — / (dense) | — / (dense) |
| Includes FDA label (accessdata.fda.gov) | **No** | Yes | Yes |
| Includes EMA SmPC | No | Yes | No |
| Includes Health Canada | No | No | Yes |
| Includes trial-comparison tables | No | **Yes** | **Yes** |
| Trial-by-trial sub-sections | No (topic-grouped) | **Yes** (SURPASS-1/-2/-3/-4/-5/-6 rows in table) | **Yes** (named sub-sections per trial) |

## What the empirical comparison reveals

**Myth busted — V17's citation count is NOT the gap.** I had claimed "tier-1 produces 50-100 unique primary sources". Empirical result:
- ChatGPT DR produced **21 unique URLs** (fewer than V17's 24)
- Gemini 3.1 Pro DR produced **43 unique URLs** (1.8x V17)
- V17's 24 is **already competitive with ChatGPT** and **56% of Gemini**

**Real gaps that ARE present:**

1. **Regulatory agency content — V17 has NONE.** 
   - Gemini cites: accessdata.fda.gov, fda.gov, Health Canada (recalls-rappels, dhpp.hpfb-dgpsa, pdf.hres.ca)
   - ChatGPT cites: accessdata.fda.gov (FDA label), ema.europa.eu (EMA SmPC), pi.lilly.com (US prescribing info)
   - V17 cites zero regulatory-agency URLs. Codex flagged this on V13 ("Facebook for FDA boxed warning") — it's a **retrieval gap**, not a selector gap.

2. **Structural depth — V17 is prose-only.**
   - Both competitors use comparison tables (trial × endpoints × results) — this compresses a lot of structured data into skim-able form
   - Both have sub-sections per named trial (Gemini: "Foundational Efficacy: SURPASS-1 Monotherapy", "Establishing Class Superiority: SURPASS-2", etc.)
   - V17 groups by topic (Efficacy/Safety/Comparative/Dose Response/Population Subgroups) — less granular

3. **Length — V17 is 1/4 to 1/3 of competitors.**
   - Reflects narrative depth: competitors' SURPASS-1 alone is ~400+ words with baseline demographics, dose-specific results, post-hoc analysis citations
   - V17's SURPASS-1 coverage is 2-3 sentences

4. **Trial authors/year/methodology context — V17 is sparse.**
   - ChatGPT DR includes "N=478; mean age 54 years; mean diabetes duration 4.7 years; baseline HbA1c about 7.9%" for SURPASS-1
   - V17 jumps straight to efficacy numbers without trial-design framing

**Things V17 already does competitively:**

- Citation faithfulness: Codex pass 8 audited 24/24 citations, 23 FAITHFUL, 0 FABRICATED. Neither Gemini nor ChatGPT had independent live-fetch audit, but the standard set is present.
- Primary RCT anchoring: V17 cites NEJM SURPASS-2, Lancet SURPASS-3, SURPASS-CVOT primary. ChatGPT uses similar mix; Gemini relies more on PMC/MDPI.
- Strict provenance binding: V17's [N] markers resolve to exact sources; competitor markers aren't individually verifiable without PDF inspection.

## Revised gap list (empirical, not speculative)

| Gap | What to fix | Difficulty | Expected impact |
|---|---|---|---|
| **A. Regulatory agency retrieval** | Add `site:accessdata.fda.gov OR site:ema.europa.eu` to amplified queries for clinical; M-28a | Low-medium (retrieval-side) | Closes Codex's pass-6 "Facebook for boxed warning" + adds EMA/FDA label URLs |
| **B. Trial-level sub-sections** | Outline template change: allow named trial sections like "SURPASS-1", "SURPASS-2" as alternatives to topic-grouped sections | Medium (outline prompt + validator) | Doubles structural depth; enables per-trial synthesis |
| **C. Trial-comparison table** | Post-synthesis step: extract trial-level data from verified sentences into a markdown table | Medium (new pipeline stage) | Matches competitor scannability |
| **D. Length 2-3x** | Raise per-section sentence target from 10-18 to 20-35; allow sub-section nesting | Low-medium (prompt) | Approaches competitor depth; risk: strict_verify drop-rate |
| **E. Baseline demographics in trial descriptions** | Prompt rule: for each named trial, include N/baseline HbA1c/diabetes duration from evidence | Low (prompt) | Matches competitor trial-framing pattern |

## Gap that I was wrong about

- **Citation count target "50-100 unique primaries"**: empirically wrong. Gemini does 43, ChatGPT does 21. V17's 24 is on par. Don't tune for more unique citations — tune for the regulatory/structural gaps above.

## Summary

V17 beats ChatGPT DR on total citations (24 vs 21), loses to Gemini (24 vs 43). V17 loses both on:
- Regulatory coverage (0 vs 3-4 FDA/EMA/Health Canada URLs)
- Structural depth (narrative vs tables + trial sub-sections)
- Total length (2x-3x shorter)

The "dominance gap" is not quantity of citations — it's **coverage breadth (regulatory retrieval)** and **structural presentation (tables, trial sub-sections)**.

## Recommended next fixes (if pursuing dominance)

**Stop batching.** Pick one at a time. Advisor-endorsed order:

1. **A (FDA/EMA retrieval)** — addresses a Codex-flagged defect AND a competitor advantage in one fix. Retrieval-side, localized to query amplification. If it lands cleanly, it's a clear win.
2. **D (length via prompt)** — if V18 still feels thin after A, increase target sentence count per section. Prompt-only, low risk.
3. **B (trial sub-sections)** — deeper structural change, only if A and D don't close the gap.
4. **C (tables)** — post-processing; architecturally separate from the synthesis pipeline, can be added last.

Skip E — it's already supported by M-27 (multi-source citation); a prompt nudge can add baseline demographics as part of trial-intro sentences.
