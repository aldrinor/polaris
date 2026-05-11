# Carney Delivery Goldset v1 — 5 questions

**Status:** DRAFT. Authored 2026-05-11 by Claude from publicly-stated Carney priorities (Liberal leadership campaign + cabinet portfolios + 2026 federal election platform). User can override or refine.

**Rationale per CLAUDE.md §-1.1:** these need to be REAL questions Carney's office would ask, not synthetic. Each maps to one of the 3 Carney scope templates we shipped (I-tpl-006/7/8) or to clinical (existing) / due-diligence (existing).

---

## Q1 — AI sovereignty (template: ai_sovereignty)

**What is the cost-quality-jurisdiction trade-off between Canada operating its own sovereign frontier-LLM compute (e.g. SCALE-AI funded clusters, Quebec hydro) versus relying on US-headquartered hyperscalers (Microsoft Azure, AWS, GCP) for federal-government AI workloads in 2026?**

Scope: Canadian federal procurement context. Compares total-cost-of-ownership, jurisdictional risk under CLOUD Act / FISA 702, talent availability, energy-grid impact. Excludes consumer applications. Time horizon 12–36 months.

## Q2 — Canada-US bilateral (template: canada_us)

**How are Canada's CUSMA review preparations (2026 mandatory review under Article 34.7) being shaped by the second Trump administration's tariff threats on Canadian steel, aluminum, and softwood lumber, and what are the realistic negotiating leverage points for the Carney government?**

Scope: post-2025-01-20 inauguration to present. Compares trade-policy positions, supply-chain reroute estimates, Section 232 / Section 301 risk, dairy supply management red lines. Excludes Mexico-specific bilateral issues. Time horizon: 2026 review window.

## Q3 — Workforce / labour (template: workforce)

**What is the projected impact of generative-AI adoption on Canadian white-collar employment in finance, legal, and public-sector knowledge work over 2026–2030, and what active labour-market interventions (CERB-style transitional benefits, EI reform, ESDC retraining) have evidence of effectiveness in analogous past technology shocks?**

Scope: Canadian labour market. Compares displacement vs augmentation estimates, regional concentration (Toronto/Montreal/Vancouver/Ottawa), unionized vs non-unionized exposure. Excludes manufacturing automation. Time horizon: 2026–2030.

## Q4 — Housing (template: policy — fits existing clinical-style template structure)

**What is the evidence base for the effectiveness of supply-side housing interventions (zoning reform, infrastructure-tied federal transfers, modular-construction subsidies, foreign-buyer bans) versus demand-side interventions (mortgage stress-test changes, first-time-buyer incentives, immigration-pacing) on housing affordability in major Canadian metros 2020–2026?**

Scope: Toronto, Vancouver, Montreal, Ottawa, Calgary metro areas. Compares policy outcomes (rental vacancy, price-to-income, starts-per-capita). Excludes Indigenous housing on-reserve (separate policy framework). Time horizon: 5-year retrospective.

## Q5 — Healthcare (clinical template, Carney-relevant)

**What is the evidence base for the effectiveness of pharmacare programs at reducing population-level chronic-disease morbidity and out-of-pocket household drug spending, comparing the implementation experience of Quebec's RPAM, the New Zealand PHARMAC model, and the UK NHS model, with implications for the federal Pharmacare Act (Bill C-64) rollout in Canada?**

Scope: comparative health-policy. T1 sources: peer-reviewed health-economics studies, Canadian Institute for Health Information (CIHI), Conference Board of Canada. Time horizon: 2010-present implementation, 2026-2030 Canadian projection.

---

## Why these 5

- **Q1, Q2, Q3** map directly to the 3 Carney-specific scope templates we shipped.
- **Q4** uses the existing policy template (which the pipeline already handles).
- **Q5** uses the clinical template (well-tested via tirzepatide validation; clinical is POLARIS's strongest demonstrated lane).

Each question is auditable: claims have decimals/percentages/cited sources/jurisdictions where line-by-line verification is meaningful. None of these are pure-opinion questions where every answer is defensible.

## How they will be used

1. Run POLARIS through each question → 5 reports + biblio + pool.
2. Run ChatGPT DR (paid GPT-5/o3 deep research mode) on each → 5 reports with footnotes.
3. Run Gemini DR (paid Gemini 2.5 Deep Research) on each → 5 reports with footnotes.
4. For each report: fetch the cited URLs, build evidence pool, run line-by-line audit harness.
5. Tally per-claim verdicts (VERIFIED / PARTIAL / UNSUPPORTED / FABRICATED / UNREACHABLE) per CLAUDE.md §-1.1.
6. Honest verdict per question: which side wins on faithfulness, on completeness, on regulatory-grade citation discipline.

## What user needs to confirm (before scaling beyond 1 question)

- Q1–Q5 are the right Carney-priority questions. If not, override.
- ChatGPT DR + Gemini DR runs will need either (a) user paid subscriptions OR (b) existing comparative artifacts. We currently have ChatGPT + Gemini outputs only on tirzepatide-T2DM (clinical), not the policy questions.
