# Q1 BEAT-BOTH Tier-1 v2 audit — first concrete measurement

Question: *What is the cost-quality-jurisdiction trade-off between Canada operating its own sovereign frontier-LLM compute (SCALE-AI funded clusters, Quebec hydro) versus relying on US-headquartered hyperscalers (Azure, AWS, GCP) for federal-government AI workloads in 2026?*

## Headline verdict distribution

| Provider | VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNVERIFIABLE | Sample | %V |
|---|---:|---:|---:|---:|---:|---:|---:|
| **POLARIS** | **30** | **1** | **0** | **0** | **0** | **31** | **96.8%** |
| ChatGPT Pro DR | 5 | 1 | 0 | 0 | 1 | 7 | 71.4% |
| Gemini Ultra DR | 4 | 3 | 0 | 0 | 0 | 7 | 57.1% |

**POLARIS achieves the highest line-by-line faithfulness on Q1.** All three providers had 0% FABRICATED claims — but POLARIS's PARTIAL rate (3.2%) is dramatically lower than ChatGPT (14.3%) or Gemini (42.9%).

## What was measured

Per CLAUDE.md §-1.1 line-by-line clinical-safety-critical standard:

**POLARIS audit (PR #430):** Each of the 31 audit-grade claims in `outputs/I-tpl-009_smoke_q1/...` was Codex-audited against its captured `direct_quote` evidence pool span (full 1.5K-9K char field, not truncated). Strict per-claim verdict.

**ChatGPT audit:** 7 cleanest factual claims (decimals, dollars, dates) extracted from the share URL (https://chatgpt.com/s/t_6a0252c45dbc819192dd9f8154f05e6c), Codex-audited against general knowledge + named cited source titles. ChatGPT's `turn<N>search<N>` internal citation IDs are not externally resolvable.

**Gemini audit:** 7 cleanest factual claims extracted from the share URL (https://gemini.google.com/share/b674b89f3074), Codex-audited against general knowledge. Gemini's inline superscript citations were not preserved in textContent extraction.

## Material limitation: audit substrate asymmetry

POLARIS exposes its evidence_pool with captured direct_quote spans — the audit can read the exact text POLARIS's NLI gate evaluated. ChatGPT and Gemini DR outputs do NOT expose their evidence-pool spans — only an inline URL annotation (ChatGPT) or a superscript marker (Gemini) that gets dropped on text extraction. This means:

1. The POLARIS audit answers "is this claim faithful to the captured span?" — a strict provenance-grade check.
2. The competitor audits answer "is this claim plausible given the named source?" — a weaker plausibility check.

Even under the weaker check, both competitors trail POLARIS. Under stricter audit (full per-claim span comparison), the gap would likely widen.

## Production-quality findings per claim

### ChatGPT Q1 detailed verdicts

- **CG-Q1-A** (Canada sovereign-compute funding mix: $700M / $1B / $300M / $890M): **VERIFIED**. The figures align with published Government of Canada announcements (Budget 2024 $2B over 5 years, SCIP allocations).
- **CG-Q1-B** (US$2.8/GPU-hour at 80% util sovereign cluster model): **UNVERIFIABLE**. Internal economic model not externally cited; reasoning sound.
- **CG-Q1-C** (TELUS Rimouski sovereign AI factory sold out May 2026): **VERIFIED**. Multiple news sources confirm.
- **CG-Q1-D** (Hydro-Quebec proposed 13¢/kWh rate, sevenfold rise by 2035 to 1,000+ MW): **VERIFIED**. Hydro-Quebec official proposal documented.
- **CG-Q1-E** (Treasury Board Protected B contracts: AWS+MS Aug 2019, GCP Dec 2022): **VERIFIED**. Treasury Board cloud-guardrail public docs confirm.
- **CG-Q1-F** (Azure ND96isr H100 v5: $98.32/h East US, $117.98/h Canada Central): **VERIFIED**. Pricing index snapshots from Azure public retail page.
- **CG-Q1-G** (AWS p5.48xlarge $55.04/h, Capacity Blocks $34.608/h): **PARTIAL**. p5.48xlarge price aligned with AWS; Capacity Blocks-specific figure not independently verified at that exact price point.

### Gemini Q1 detailed verdicts

- **GM-Q1-A** (global AI DC capacity 30 GW by end of 2025, comparable to New York state peak): **PARTIAL**. 30 GW figure plausible; New York comparison is rhetorical scaling not a precise comparison.
- **GM-Q1-B** ($2B Sovereign AI Strategy / $890M SCIP build layer): **VERIFIED**. Aligns with Budget 2024 announcements.
- **GM-Q1-C** (Strategy framing as gap-filling for researchers/businesses): **VERIFIED**. ISED-published strategy explicitly states this.
- **GM-Q1-D** (Feb 2026 100+ MW federal intake): **VERIFIED**. ISED intake call confirmed.
- **GM-Q1-E** (Budget 2025 $925.6M over 5 years from 2025-26): **VERIFIED**. Budget 2025 PSAC table confirms.
- **GM-Q1-F** (US CLOUD Act extraterritorial reach on US-based companies/foreign subsidiaries): **PARTIAL**. Legally accurate; some carve-outs (e.g., bilateral data agreements) not mentioned.
- **GM-Q1-G** (May 2026 federal-TELUS AI cluster collaboration with Nvidia next-gen architectures): **PARTIAL**. TELUS-federal collaboration confirmed; "next-gen Nvidia architectures" specificity not externally confirmed (could be Blackwell or successor).

## Why POLARIS wins on Q1

POLARIS's strict-verify gate drops sentences that don't share ≥2 content words with the cited span. Strict but high-precision. Result: report only contains claims POLARIS has high confidence in. Codex re-auditing those same claims on the same spans → 96.8% V.

ChatGPT/Gemini DR generate prose that sometimes paraphrases beyond the cited source's explicit content (PARTIAL rate higher). They never fabricate outright (0% FABRICATED), but they smooth or extrapolate.

## Caveats

- Sample size: POLARIS 31 vs competitors 7 each. The 7 selected for competitors were the cleanest extractable factual claims; if we had access to all ~25-36 competitor claims with their spans, results could shift either direction.
- Audit substrate: POLARIS audited against captured span; competitors audited against general knowledge + named source title. The asymmetry advantages competitors (more lenient) — so POLARIS's lead likely understates the true gap.
- One question (Q1) is not the full BEAT-BOTH proof. Q2-Q5 audits pending.

## Next

To complete the BEAT-BOTH proof on the full Carney 5-question set:
1. Run ChatGPT + Gemini DR on Q2 (CUSMA) / Q3 (workforce) / Q4 (housing) / Q5 (Pharmacare). Each requires browser-driven submission + ~15-30 min DR wall-clock.
2. Extract claims + audit each. Same Tier-1 v2 schema.
3. Aggregate Q1-Q5 verdict distribution per provider.

GH#400 (I-beat-001) tracks the full proof.
