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

# Q3 batch 3: claims 15-21
schema_version: tier1_v2
claims:
  - claim_id: Q3-T1-015
    section: "Mechanism"
    sentence: "For instance, in basic professional writing, one experiment found a 40% increase in speed and an 18% increase in output quality using ChatGPT-3.5.[4]"
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

  - claim_id: Q3-T1-016
    section: "Mechanism"
    sentence: "In software development, GitHub Copilot led to a 56% increase in coding speed in one study and a 26% increase in weekly task completion in another large field experiment.[4][3]"
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

  - claim_id: Q3-T1-017
    section: "Mechanism"
    sentence: "Early labor market data shows job growth has stagnated in occupations with the most AI automation potential, and for jobs that can be performed entirely by generative AI, employment fell by 0.75 percent from 2021 to 2024.[4]"
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

  - claim_id: Q3-T1-018
    section: "Mechanism"
    sentence: "In the U.S., employment is growing at a slower pace in industries where AI usage has ramped up, especially in technology, finance, and professional roles where displacement risk is higher.[6]"
    cited_evidence:
      - evidence_id: ev_003
        bibliography_num: 6
        url: "https://economics.td.com/ca-labour-market-mirroring-americans-ai-impact"
        tier: T4
        span: '0-500'
        title: "Is Canada's Labour Market Mirroring American's AI Impact?"
        span_text: |
          Highlights - AI adoption within U.S. labour markets is broader than in Canada, though the lack of a global standardized definition complicates cross-border comparisons. - Canadian employment in occupations at higher risk of AI displacement is more resilient, but both nations are exhibiting steady job creation in roles complementary to AI usage. - The normalization of Canada’s labour demand is more a function of cyclical factors rather than AI, although some AI related productivity relationships are loosely emerging. - Youth wages in AI-complementary roles in the U.S. and Canada are growing at 
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q3-T1-019
    section: "Mechanism"
    sentence: "Concurrently, businesses adopting AI are more likely to invest in workforce training, with Canadian businesses that invest in AI being 5.4 percentage points more likely to invest in employee training, indicating a complementary mechanism aimed at skill development.[5]"
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

  - claim_id: Q3-T1-020
    section: "Mechanism"
    sentence: "This aligns with evidence that AI adoption is creating additional skill needs and that most adjustments to date have occurred through task restructuring within firms rather than layoffs.[5][3]"
    cited_evidence:
      - evidence_id: ev_007
        bibliography_num: 3
        url: "https://laweconcenter.org/resources/ai-productivity-and-labor-markets-a-review-of-the-empirical-evidence/"
        tier: T4
        span: '0-500'
        title: "AI, Productivity, and Labor Markets: A Review of the ..."
        span_text: |
          AI, Productivity, and Labor Markets: A Review of the Empirical Evidence Executive Summary Generative artificial intelligence (AI) has diffused with unusual speed since late 2022. By late 2024, nearly 40% of U.S. adults ages 18–64 reported using AI tools, a pace that exceeds comparable stages for personal computers and the internet. That rapid uptake has sharpened two policy questions: whether AI will generate measurable gains in output and productivity at the aggregate level, and whether the adjustment process will produce labor-market disruption large enough to justify new regulatory interven
      - evidence_id: ev_006
        bibliography_num: 5
        url: "https://www.cfib-fcei.ca/en/research-economic-analysis/ai-adoption"
        tier: T4
        span: '0-500'
        title: "AI Adoption and Workforce Training Investment in Canada"
        span_text: |
          AI is reshaping how firms operate, raising questions about how businesses invest in their workforce as these technologies are adopted. This blog shows that Canadian businesses investing in AI are more likely to invest in employee training, aligning AI adoption with ongoing investment in skills. Summary - AI adoption is rising: Nearly 45% of Canadian businesses use GenAI in their operations, increasing sharply with firm size. - AI is creating additional skill needs: Businesses that invest in AI are 5.4 percentage points more likely to invest in employee training. - People remain the priority: N
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q3-T1-021
    section: "Mechanism"
    sentence: "The mechanism involves a reallocation of work hours, as AI adoption correlates with a reallocation of roughly 9% of work hours from routine data entry to higher-value tasks, such as client communication.[3]"
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
