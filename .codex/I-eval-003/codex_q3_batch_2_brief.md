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

# Q3 batch 2: claims 8-14
schema_version: tier1_v2
claims:
  - claim_id: Q3-T1-008
    section: "Efficacy"
    sentence: "One projection estimates that 40 percent of current GDP could be substantially affected by generative AI, with occupations around the 80th percentile of earnings being the most exposed\u2014around half of their work susceptible to automation on average.[4]"
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

  - claim_id: Q3-T1-009
    section: "Efficacy"
    sentence: "Legal occupations have an exposure to AI automation of 47.5% of tasks.[4]"
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

  - claim_id: Q3-T1-010
    section: "Efficacy"
    sentence: "Aggregate labor-market indicators through 2024\u20132025 show limited disruption, with most datasets finding little evidence of economywide job loss.[3]"
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

  - claim_id: Q3-T1-011
    section: "Efficacy"
    sentence: "Job vacancies in occupations potentially more exposed to and less complementary with AI decreased at a similar rate as vacancies in occupations potentially less exposed to AI from the fourth quarter of 2022 to the third quarter of 2025.[1]"
    cited_evidence:
      - evidence_id: ev_000
        bibliography_num: 1
        url: "https://www150.statcan.gc.ca/n1/pub/36-28-0001/2026001/article/00003-eng.htm"
        tier: T4
        span: '0-500'
        title: "Canadian employment trends in the era of generative ..."
        span_text: |
          Economic and Social Reports Canadian employment trends in the era of generative artificial intelligence: Early evidence DOI: https://doi.org/10.25318/36280001202600100003-eng Text begins Abstract Artificial intelligence (AI) holds the potential to transform the nature of work, and its ability to replace human labour remains a central concern. This study highlights recent labour market trends, distinguishing jobs potentially more exposed to and less complementary with AI from other jobs. From November 2022—when generative AI applications started gaining traction following the mass availability 
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q3-T1-012
    section: "Efficacy"
    sentence: "This pattern is observed in coding-intensive professions, where overall job growth was similar to other jobs, but gains were concentrated among workers aged 30 to 49, while the number of coding professionals younger than 30 stagnated.[1]"
    cited_evidence:
      - evidence_id: ev_000
        bibliography_num: 1
        url: "https://www150.statcan.gc.ca/n1/pub/36-28-0001/2026001/article/00003-eng.htm"
        tier: T4
        span: '0-500'
        title: "Canadian employment trends in the era of generative ..."
        span_text: |
          Economic and Social Reports Canadian employment trends in the era of generative artificial intelligence: Early evidence DOI: https://doi.org/10.25318/36280001202600100003-eng Text begins Abstract Artificial intelligence (AI) holds the potential to transform the nature of work, and its ability to replace human labour remains a central concern. This study highlights recent labour market trends, distinguishing jobs potentially more exposed to and less complementary with AI from other jobs. From November 2022—when generative AI applications started gaining traction following the mass availability 
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q3-T1-013
    section: "Mechanism"
    sentence: "One analysis estimates that 40 percent of current GDP could be substantially affected by generative AI, with occupations around the 80th percentile of earnings being the most exposed, as around half of their work is susceptible to automation on average.[4]"
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

  - claim_id: Q3-T1-014
    section: "Mechanism"
    sentence: "Task-level exposure estimates show Office and Administrative Support occupations have 75.5% of tasks exposed to AI automation, while Business and Financial Operations occupations have 68.4% exposure, and Computer and Mathematical occupations have 62.6% exposure.[4]"
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
