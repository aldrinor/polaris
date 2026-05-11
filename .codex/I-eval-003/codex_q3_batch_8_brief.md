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

# Q3 batch 8: claims 50-56
schema_version: tier1_v2
claims:
  - claim_id: Q3-T1-050
    section: "Long-term Outcomes"
    sentence: "However, job growth varied across worker demographics, with younger employees and those with less education generally seeing weaker job growth over this period.[1]"
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

  - claim_id: Q3-T1-051
    section: "Long-term Outcomes"
    sentence: "Within coding-intensive professions, overall job growth was similar to other jobs, but gains were concentrated among workers aged 30 to 49 while the number of coding professionals younger than 30 stagnated.[1]"
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

  - claim_id: Q3-T1-052
    section: "Long-term Outcomes"
    sentence: "From Q4 2022 to Q3 2025, job vacancies in occupations potentially more exposed to and less complementary with AI decreased at a similar rate as vacancies in occupations potentially less exposed to AI.[1]"
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

  - claim_id: Q3-T1-053
    section: "Long-term Outcomes"
    sentence: "One analysis notes that roughly 60% of the Canadian workforce is potentially highly exposed to AI, but about half of those workers may actually benefit from it.[8]"
    cited_evidence:
      - evidence_id: ev_004
        bibliography_num: 8
        url: "https://www.linkedin.com/posts/marc-frenette-ph-d-19752a224_ai-genai-futureofwork-activity-7422271124887056386-iAAH"
        tier: T4
        span: '0-500'
        title: "AI's Impact on Canada's Labour Market: Early Evidence"
        span_text: |
          Is AI substantially reshaping Canada’s labour market? Our new study says: not yet… The widespread availability of ChatGPT starting in November 2022 — and the rapid adoption of GenAI tools since then — has fuelled both excitement and concern about the future of human labour. Our previous work suggested that roughly 60% of the workforce is potentially highly exposed to AI, but that about half of those workers may actually benefit from AI. However, that earlier study did not examine how employment trends were evolving over time. In a newly released Statistics Canada article authored by [Tahsin Me
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q3-T1-054
    section: "Long-term Outcomes"
    sentence: "At the firm level, Canadian businesses investing in AI are 5.4 percentage points more likely to invest in employee training than businesses that do not.[5]"
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

  - claim_id: Q3-T1-055
    section: "Long-term Outcomes"
    sentence: "Empirical literature reviews indicate controlled field experiments document large productivity gains at the task and firm level, with studies across writing, software development, accounting, and translation reporting 15% to more than 50% reductions in task-completion time alongside quality improvements.[3]"
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

  - claim_id: Q3-T1-056
    section: "Long-term Outcomes"
    sentence: "These gains disproportionately benefit less-experienced workers, producing \"skill compression\" within occupations.[3]"
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
