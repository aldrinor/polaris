Independent Tier-1 audit of 7 Q3 GenAI Workforce claims. Output YAML records only.

You are populating Tier-1 audit fields for each claim in the BATCH below.

# Tier-1 schema (per claim)

```yaml
- claim_id: Q3-T1-NNN
  claim_type: efficacy | safety | diagnostic | dosing | regulatory | mechanism | epidemiology | economic | guideline | background
  materiality: critical | major | minor | background
  citation_context_match: yes | partial | no
  verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
  rationale: "one sentence quoting or paraphrasing the span_text"
  reviewer_confidence: 0.0 - 1.0
```

# Decision rules

- **citation_context_match: yes** iff the decimal/year/range/figure in the claim is EXPLICITLY present in the cited span_text. **partial** if the span is on-topic and broadly consistent but the specific decimal is not in the visible span. **no** if the span is about a different topic.
- **materiality**:
  - critical = the headline policy-decision number (e.g., GenAI displacement %, white-collar workforce share, productivity multipliers, automation timelines)
  - major = supporting policy-decision-grade decimal
  - minor = supporting context decimal that policy decision would not turn on; ALSO repeated facts already cited elsewhere
  - background = pure framing
- **verdict**: VERIFIED requires citation_context_match=yes AND the claim is consistent with the span. PARTIAL covers framing/attribution issues even when decimals match. UNSUPPORTED covers cases where the span doesn't support the claim.
- **reviewer_confidence < 0.7 → flag for human deferral**.

# Banned shortcuts

- Do NOT skip a claim. ALL 7 must have records.
- Do NOT auto-VERIFIED just because a span exists. Read the span_text and confirm the decimal is there.
- Do NOT exceed one paragraph of rationale per claim.

# Batch (the claims to audit are below; each has cited_evidence with span_text inline)

# Q3 batch 1: claims 1-7
schema_version: tier1_v2
claims:
  - claim_id: Q3-T1-001
    section: "Efficacy"
    sentence: "Early Canadian evidence from November 2022 to December 2025 shows employment generally grew regardless of an occupation's potential exposure to or complementarity with AI, with no clear sign that jobs more exposed to AI are declining faster than others.[1][2]"
    cited_evidence:
      - evidence_id: ev_000
        bibliography_num: 1
        url: "https://www150.statcan.gc.ca/n1/pub/36-28-0001/2026001/article/00003-eng.htm"
        tier: T4
        span: '0-500'
        title: "Canadian employment trends in the era of generative ..."
        span_text: |
          Economic and Social Reports Canadian employment trends in the era of generative artificial intelligence: Early evidence DOI: https://doi.org/10.25318/36280001202600100003-eng Text begins Abstract Artificial intelligence (AI) holds the potential to transform the nature of work, and its ability to replace human labour remains a central concern. This study highlights recent labour market trends, distinguishing jobs potentially more exposed to and less complementary with AI from other jobs. From November 2022—when generative AI applications started gaining traction following the mass availability 
      - evidence_id: ev_001
        bibliography_num: 2
        url: "https://lmic-cimt.ca/future-of-work/canadian-employment-trends-in-the-era-of-generative-artificial-intelligence-early-evidence/"
        tier: T4
        span: '0-500'
        title: "Canadian employment trends in the era of generative ..."
        span_text: |
          Title: Canadian employment trends in the era of generative artificial intelligence: Early evidence — LMIC-CIMT URL Source: https://lmic-cimt.ca/future-of-work/canadian-employment-trends-in-the-era-of-generative-artificial-intelligence-early-evidence/ Markdown Content: # Canadian employment trends in the era of generative artificial intelligence: Early evidence — LMIC-CIMT (https://lmic-cimt.ca/future-of-work/canadian-employment-trends-in-the-era-of-generative-artificial-intelligence-early-evidence/#fl-main-content) [LMIC-CIMT](https://lmic-cimt.ca/) [](https://lmic-cimt.ca/future-of-work/canad
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q3-T1-002
    section: "Efficacy"
    sentence: "One review of empirical evidence notes that where effects appear, they are concentrated in entry-level segments of highly exposed occupations, while senior employment remains largely stable.[3]"
    cited_evidence:
      - evidence_id: ev_007
        bibliography_num: 3
        url: "https://laweconcenter.org/resources/ai-productivity-and-labor-markets-a-review-of-the-empirical-evidence/"
        tier: T4
        span: '0-500'
        title: "AI, Productivity, and Labor Markets: A Review of the ..."
        span_text: |
          AI, Productivity, and Labor Markets: A Review of the Empirical Evidence Executive Summary Generative artificial intelligence (AI) has diffused with unusual speed since late 2022. By late 2024, nearly 40% of U.S. adults ages 18–64 reported using AI tools, a pace that exceeds comparable stages for personal computers and the internet. That rapid uptake has sharpened two policy questions: whether AI will generate measurable gains in output and productivity at the aggregate level, and whether the adjustment process will produce labor-market disruption large enough to justify new regulatory interven
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q3-T1-003
    section: "Efficacy"
    sentence: "The projected macroeconomic impact on productivity and output is gradual; one model estimates AI will increase total factor productivity (TFP) and GDP levels by 1.5% by 2035, nearly 3% by 2055, and 3.7% by 2075, with the peak annual boost to TFP growth of around 0.2 percentage points occurring in the early 2030s.[4]"
    cited_evidence:
      - evidence_id: ev_002
        bibliography_num: 4
        url: "https://budgetmodel.wharton.upenn.edu/p/2025-09-08-the-projected-impact-of-generative-ai-on-future-productivity-growth/"
        tier: T4
        span: '0-500'
        title: "The Projected Impact of Generative AI on Future ..."
        span_text: |
          The Projected Impact of Generative AI on Future Productivity Growth
          The Projected Impact of Generative AI on Future Productivity Growth
          We estimate that AI will increase productivity and GDP by 1.5% by 2035, nearly 3% by 2055, and 3.7% by 2075. AI’s boost to annual productivity growth is strongest in the early 2030s but eventually fades, with a permanent effect of less than 0.04 percentage points due to sectoral shifts.
          Key Points
          -
          We estimate that 40 percent of current GDP could be substantially affected by generative AI. Occupations around the 80th percentile of earnings are the most expose
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q3-T1-004
    section: "Efficacy"
    sentence: "The adjustment process appears to involve task reallocation rather than outright displacement, with evidence from fields like accounting showing AI use correlates with a reallocation of roughly 9% of work hours from routine data entry to higher-value tasks.[3]"
    cited_evidence:
      - evidence_id: ev_007
        bibliography_num: 3
        url: "https://laweconcenter.org/resources/ai-productivity-and-labor-markets-a-review-of-the-empirical-evidence/"
        tier: T4
        span: '0-500'
        title: "AI, Productivity, and Labor Markets: A Review of the ..."
        span_text: |
          AI, Productivity, and Labor Markets: A Review of the Empirical Evidence Executive Summary Generative artificial intelligence (AI) has diffused with unusual speed since late 2022. By late 2024, nearly 40% of U.S. adults ages 18–64 reported using AI tools, a pace that exceeds comparable stages for personal computers and the internet. That rapid uptake has sharpened two policy questions: whether AI will generate measurable gains in output and productivity at the aggregate level, and whether the adjustment process will produce labor-market disruption large enough to justify new regulatory interven
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q3-T1-005
    section: "Efficacy"
    sentence: "Furthermore, Canadian businesses investing in AI are 5.4 percentage points more likely to invest in employee training than non-adopting businesses, indicating a concurrent investment in human capital.[5]"
    cited_evidence:
      - evidence_id: ev_006
        bibliography_num: 5
        url: "https://www.cfib-fcei.ca/en/research-economic-analysis/ai-adoption"
        tier: T4
        span: '0-500'
        title: "AI Adoption and Workforce Training Investment in Canada"
        span_text: |
          AI is reshaping how firms operate, raising questions about how businesses invest in their workforce as these technologies are adopted. This blog shows that Canadian businesses investing in AI are more likely to invest in employee training, aligning AI adoption with ongoing investment in skills. Summary - AI adoption is rising: Nearly 45% of Canadian businesses use GenAI in their operations, increasing sharply with firm size. - AI is creating additional skill needs: Businesses that invest in AI are 5.4 percentage points more likely to invest in employee training. - People remain the priority: N
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q3-T1-006
    section: "Efficacy"
    sentence: "The empirical literature from controlled experiments consistently reports large productivity gains at the task level\u2014such as 40% increases in speed for professional writing, 56% faster coding, and 26% increases in software development task completion\u2014which disproportionately benefit less-experienced workers, producing skill compression within occupations.[4][3]"
    cited_evidence:
      - evidence_id: ev_007
        bibliography_num: 3
        url: "https://laweconcenter.org/resources/ai-productivity-and-labor-markets-a-review-of-the-empirical-evidence/"
        tier: T4
        span: '0-500'
        title: "AI, Productivity, and Labor Markets: A Review of the ..."
        span_text: |
          AI, Productivity, and Labor Markets: A Review of the Empirical Evidence Executive Summary Generative artificial intelligence (AI) has diffused with unusual speed since late 2022. By late 2024, nearly 40% of U.S. adults ages 18–64 reported using AI tools, a pace that exceeds comparable stages for personal computers and the internet. That rapid uptake has sharpened two policy questions: whether AI will generate measurable gains in output and productivity at the aggregate level, and whether the adjustment process will produce labor-market disruption large enough to justify new regulatory interven
      - evidence_id: ev_002
        bibliography_num: 4
        url: "https://budgetmodel.wharton.upenn.edu/p/2025-09-08-the-projected-impact-of-generative-ai-on-future-productivity-growth/"
        tier: T4
        span: '0-500'
        title: "The Projected Impact of Generative AI on Future ..."
        span_text: |
          The Projected Impact of Generative AI on Future Productivity Growth
          The Projected Impact of Generative AI on Future Productivity Growth
          We estimate that AI will increase productivity and GDP by 1.5% by 2035, nearly 3% by 2055, and 3.7% by 2075. AI’s boost to annual productivity growth is strongest in the early 2030s but eventually fades, with a permanent effect of less than 0.04 percentage points due to sectoral shifts.
          Key Points
          -
          We estimate that 40 percent of current GDP could be substantially affected by generative AI. Occupations around the 80th percentile of earnings are the most expose
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q3-T1-007
    section: "Efficacy"
    sentence: "These micro-level gains have not yet translated into significant aggregate employment declines in Canada, as early evidence through late 2025 indicates job growth continued across exposure categories.[1][2]"
    cited_evidence:
      - evidence_id: ev_000
        bibliography_num: 1
        url: "https://www150.statcan.gc.ca/n1/pub/36-28-0001/2026001/article/00003-eng.htm"
        tier: T4
        span: '0-500'
        title: "Canadian employment trends in the era of generative ..."
        span_text: |
          Economic and Social Reports Canadian employment trends in the era of generative artificial intelligence: Early evidence DOI: https://doi.org/10.25318/36280001202600100003-eng Text begins Abstract Artificial intelligence (AI) holds the potential to transform the nature of work, and its ability to replace human labour remains a central concern. This study highlights recent labour market trends, distinguishing jobs potentially more exposed to and less complementary with AI from other jobs. From November 2022—when generative AI applications started gaining traction following the mass availability 
      - evidence_id: ev_001
        bibliography_num: 2
        url: "https://lmic-cimt.ca/future-of-work/canadian-employment-trends-in-the-era-of-generative-artificial-intelligence-early-evidence/"
        tier: T4
        span: '0-500'
        title: "Canadian employment trends in the era of generative ..."
        span_text: |
          Title: Canadian employment trends in the era of generative artificial intelligence: Early evidence — LMIC-CIMT URL Source: https://lmic-cimt.ca/future-of-work/canadian-employment-trends-in-the-era-of-generative-artificial-intelligence-early-evidence/ Markdown Content: # Canadian employment trends in the era of generative artificial intelligence: Early evidence — LMIC-CIMT (https://lmic-cimt.ca/future-of-work/canadian-employment-trends-in-the-era-of-generative-artificial-intelligence-early-evidence/#fl-main-content) [LMIC-CIMT](https://lmic-cimt.ca/) [](https://lmic-cimt.ca/future-of-work/canad
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence



# Output

Single YAML block. List of records in claim_id order. Then a summary:

```yaml
- claim_id: ...
  ...
- claim_id: ...
  ...

batch_summary:
  total: 7
  per_verdict: {VERIFIED: N, PARTIAL: N, UNSUPPORTED: N, FABRICATED: N, UNREACHABLE: N}
  per_context_match: {yes: N, partial: N, no: N}
  notable: ["..."]
```

Output the YAML directly. No commentary outside.
