Independent Tier-1 audit of 7 Q4 Canadian housing supply claims. Output YAML records only.

You are populating Tier-1 audit fields for each claim in the BATCH below.

# Tier-1 schema (per claim)

```yaml
- claim_id: Q4-T1-NNN
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
  - critical = the headline policy-decision number (e.g., CMHC supply targets, BC/ON municipal upzoning timelines, federal Housing Accelerator Fund dollars, mortgage qualification stress test rates)
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

# Q4 batch 4: claims 22-28
schema_version: tier1_v2
claims:
  - claim_id: Q4-T1-022
    section: "Regulatory"
    sentence: "A specific federal commitment includes an additional $4.3 billion towards an Urban, Rural and Northern Indigenous Housing Strategy launching in 2024, which aims to establish a \u2018for Indigenous, by Indigenous' National Housing Centre.[10]"
    cited_evidence:
      - evidence_id: ev_011
        bibliography_num: 10
        url: "https://housing-infrastructure.canada.ca/housing-logement/housing-plan-report-rapport-plan-logement-eng.html"
        tier: T3
        span: '0-500'
        title: "Solving the Housing Crisis: Canada's Housing Plan"
        span_text: |
          Solving the Housing Crisis: Canada's Housing Plan On this page - The Housing Crisis of our Past - The Housing Crisis of Today - Solving the Housing Crisis - 1: Building More Homes - 2: Making it Easier to Rent or Own a Home - 3: Helping Canadians Who Can’t Afford a Home - Conclusion - Who's in Charge of What: List of Responsibilities in Housing by Order of Government We need to build more homes in Canada, and we need to build them by the millions. The good news – we can. The proof is in our history. The Housing Crisis of our Past At the end of the Second World War, our country reached a defini
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q4-T1-023
    section: "Regulatory"
    sentence: "This builds on previous federal investments, as one source reports that more than $10.7B in co-developed distinctions-based approaches has created almost 22,000 new or repaired homes on-reserve.[10]"
    cited_evidence:
      - evidence_id: ev_011
        bibliography_num: 10
        url: "https://housing-infrastructure.canada.ca/housing-logement/housing-plan-report-rapport-plan-logement-eng.html"
        tier: T3
        span: '0-500'
        title: "Solving the Housing Crisis: Canada's Housing Plan"
        span_text: |
          Solving the Housing Crisis: Canada's Housing Plan On this page - The Housing Crisis of our Past - The Housing Crisis of Today - Solving the Housing Crisis - 1: Building More Homes - 2: Making it Easier to Rent or Own a Home - 3: Helping Canadians Who Can’t Afford a Home - Conclusion - Who's in Charge of What: List of Responsibilities in Housing by Order of Government We need to build more homes in Canada, and we need to build them by the millions. The good news – we can. The proof is in our history. The Housing Crisis of our Past At the end of the Second World War, our country reached a defini
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q4-T1-024
    section: "Regulatory"
    sentence: "Howe Institute, highlights the acute affordability crises in major urban centers and the growing mismatch between supply and population needs.[11]"
    cited_evidence:
      - evidence_id: ev_015
        bibliography_num: 11
        url: "https://cdhowe.org/publication/housing-policy-for-a-growing-canada/"
        tier: T4
        span: '0-500'
        title: "Housing Policy for a Growing Canada - Toronto - C.D. Howe Institute"
        span_text: |
          [Home](https://cdhowe.org/) / [Publications](https://cdhowe.org/publication/) / [Research](https://cdhowe.org/publication-type/public-policy-research/) / Housing Policy for a Growing Canada - [Media Releases](https://cdhowe.org/media-releases/) - Research - | Housing Policy for a Growing Canada Summary: | Citation | . 2025. Housing Policy for a Growing Canada. ###. Toronto: C.D. Howe Institute. | | Page Title: | Housing Policy for a Growing Canada – C.D. Howe Institute | | Article Title: | Housing Policy for a Growing Canada | | URL: | https://cdhowe.org/publication/housing-policy-for-a-growin
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q4-T1-025
    section: "Regulatory"
    sentence: "For comparative context, legislative reform packages in the United States, such as the hybrid 21st Century ROAD to Housing Act passed by the Senate, propose major updates to federal programs like the Home Investment Partnerships Program (HOME) to expand support for workforce households and housing-related infrastructure.[12][13]"
    cited_evidence:
      - evidence_id: ev_006
        bibliography_num: 12
        url: "https://www.naco.org/resource/house-and-senate-housing-reform-packages-side-side"
        tier: T4
        span: '0-500'
        title: "House and Senate Housing Reform Packages: Side-by-Side"
        span_text: |
          House and Senate Housing Reform Packages: Side-by-Side Upcoming Events Related News As Congress considers comprehensive housing legislation, both the House and Senate proposals include major updates to federal housing programs that counties rely on to improve affordability and support infrastructure and community development projects. Jump to Section As Congress considers comprehensive housing legislation, both the House and Senate proposals include major updates to federal housing programs that counties rely on to improve affordability and support infrastructure and community development proj
      - evidence_id: ev_022
        bibliography_num: 13
        url: "https://www.naco.org/resource/house-and-senate-housing-reform-packages-side-side"
        tier: T4
        span: '0-500'
        title: "House and Senate Housing Reform Packages: Side-by-Side"
        span_text: |
          House and Senate Housing Reform Packages: Side-by-Side Upcoming Events Related News As Congress considers comprehensive housing legislation, both the House and Senate proposals include major updates to federal housing programs that counties rely on to improve affordability and support infrastructure and community development projects. Jump to Section As Congress considers comprehensive housing legislation, both the House and Senate proposals include major updates to federal housing programs that counties rely on to improve affordability and support infrastructure and community development proj
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q4-T1-026
    section: "Regulatory"
    sentence: "The international perspective from a World Economic Forum report notes that a common metric for housing affordability is housing expenditure that is less than 30% of household income.[14]"
    cited_evidence:
      - evidence_id: ev_026
        bibliography_num: 14
        url: "https://www3.weforum.org/docs/WEF_Making_Affordable_Housing_A_Reality_In_Cities_report.pdf"
        tier: UNKNOWN
        span: '0-500'
        title: "[PDF] Making Affordable Housing a Reality in Cities | World Economic Forum"
        span_text: |
          Insight Report Cities, Urban Development & Urban Services Platform In Collaboration with PwC Making Affordable Housing a Reality in Cities June 2019 Foreword Executive Summary Chapter 1 – Introduction Chapter 2 – Supply-Side Challenges: Land Acquisition and Securing Title Chapter 3 – Supply-Side Challenges: Land Use – Zoning and Regulations Chapter 4 – Supply-Side Challenges: Funding Affordable Housing Chapter 5 – Supply-Side Challenges: Design Considerations and Construction Costs of Affordable Housing Chapter 6 – Demand-Side Challenges: An Overview Chapter 7 – Recommendations References Ackn
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q4-T1-027
    section: "Regulatory"
    sentence: "The same report cites a 2014 McKinsey estimate that 330 million urban households globally were living in substandard housing or were financially stretched by housing costs, projected to rise to nearly 440 million households by 2025.[14]"
    cited_evidence:
      - evidence_id: ev_026
        bibliography_num: 14
        url: "https://www3.weforum.org/docs/WEF_Making_Affordable_Housing_A_Reality_In_Cities_report.pdf"
        tier: UNKNOWN
        span: '0-500'
        title: "[PDF] Making Affordable Housing a Reality in Cities | World Economic Forum"
        span_text: |
          Insight Report Cities, Urban Development & Urban Services Platform In Collaboration with PwC Making Affordable Housing a Reality in Cities June 2019 Foreword Executive Summary Chapter 1 – Introduction Chapter 2 – Supply-Side Challenges: Land Acquisition and Securing Title Chapter 3 – Supply-Side Challenges: Land Use – Zoning and Regulations Chapter 4 – Supply-Side Challenges: Funding Affordable Housing Chapter 5 – Supply-Side Challenges: Design Considerations and Construction Costs of Affordable Housing Chapter 6 – Demand-Side Challenges: An Overview Chapter 7 – Recommendations References Ackn
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q4-T1-028
    section: "Regulatory"
    sentence: "A major concern was that large-scale construction targets, such as building 5.8 million homes, could add 100 megatons of greenhouse gas emissions, presenting an environmental policy challenge.[11]"
    cited_evidence:
      - evidence_id: ev_015
        bibliography_num: 11
        url: "https://cdhowe.org/publication/housing-policy-for-a-growing-canada/"
        tier: T4
        span: '0-500'
        title: "Housing Policy for a Growing Canada - Toronto - C.D. Howe Institute"
        span_text: |
          [Home](https://cdhowe.org/) / [Publications](https://cdhowe.org/publication/) / [Research](https://cdhowe.org/publication-type/public-policy-research/) / Housing Policy for a Growing Canada - [Media Releases](https://cdhowe.org/media-releases/) - Research - | Housing Policy for a Growing Canada Summary: | Citation | . 2025. Housing Policy for a Growing Canada. ###. Toronto: C.D. Howe Institute. | | Page Title: | Housing Policy for a Growing Canada – C.D. Howe Institute | | Article Title: | Housing Policy for a Growing Canada | | URL: | https://cdhowe.org/publication/housing-policy-for-a-growin
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
