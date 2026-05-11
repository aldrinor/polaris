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

# Q4 batch 5: claims 29-35
schema_version: tier1_v2
claims:
  - claim_id: Q4-T1-029
    section: "Regulatory"
    sentence: "The analysis also pointed to financial barriers, noting a \"math equation\" for new projects that does not work for developers due to factors like a drop in rents in many areas, stabilized but high construction costs, and high interest rates.[11]"
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

  - claim_id: Q4-T1-030
    section: "Population Subgroups"
    sentence: "Demand-side interventions designed to assist specific households can inadvertently reduce overall affordability if not carefully targeted and paired with supply increases, according to modeling by the Canada Mortgage and Housing Corporation (CMHC).[9][8][7]"
    cited_evidence:
      - evidence_id: ev_001
        bibliography_num: 7
        url: "https://finance.yahoo.com/news/why-demand-side-interventions-paired-140000953.html"
        tier: T6
        span: '0-500'
        title: "Why demand-side interventions need to be paired with housing supply"
        span_text: |
          OTTAWA, ON, April 15, 2026 /CNW/ - New analysis from Canada Mortgage and Housing Corporation (CMHC) explores how housing supply and housing demand interventions need to work together to address the housing affordability crisis. Demand-side interventions, which directly support households in attaining a home, are often favoured because of their more immediate impact. The results can be measured more quickly than the creation of new supply, which take years to deliver. It is a delicate balance, since the basic rule of supply and demand dictates that if demand increases without increased supply, 
      - evidence_id: ev_019
        bibliography_num: 8
        url: "https://finance.yahoo.com/news/why-demand-side-interventions-paired-140000953.html"
        tier: T6
        span: '0-500'
        title: "Why demand-side interventions need to be paired with housing supply"
        span_text: |
          OTTAWA, ON, April 15, 2026 /CNW/ - New analysis from Canada Mortgage and Housing Corporation (CMHC) explores how housing supply and housing demand interventions need to work together to address the housing affordability crisis. Demand-side interventions, which directly support households in attaining a home, are often favoured because of their more immediate impact. The results can be measured more quickly than the creation of new supply, which take years to deliver. It is a delicate balance, since the basic rule of supply and demand dictates that if demand increases without increased supply, 
      - evidence_id: ev_020
        bibliography_num: 9
        url: "https://www.cmhc-schl.gc.ca/observer/2026/why-demand-side-interventions-need-to-be-targeted-and-offset-with-supply"
        tier: T4
        span: '0-500'
        title: "Targeted demand interventions need supply for housing market ..."
        span_text: |
          When addressing a housing affordability crisis, there is always a tug-of-war between demand- and supply-side housing interventions. Demand-side interventions, which directly help households secure housing, are often favoured because of their more immediate impact. The results are easier to see and measure compared to building new homes, which take years to deliver. A basic principle of supply and demand shows that if demand increases without proportionate supply, prices will increase. New modeling by CMHC shows that this dynamic occurs with housing demand-side interventions. Over time, they ma
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q4-T1-031
    section: "Population Subgroups"
    sentence: "The estimated economic cost of such an intervention includes $2.7 billion to $4.3 billion in direct spending for the intervention itself and an additional $1.6 billion in unintended increased costs for all homebuyers not supported by it.[9]"
    cited_evidence:
      - evidence_id: ev_020
        bibliography_num: 9
        url: "https://www.cmhc-schl.gc.ca/observer/2026/why-demand-side-interventions-need-to-be-targeted-and-offset-with-supply"
        tier: T4
        span: '0-500'
        title: "Targeted demand interventions need supply for housing market ..."
        span_text: |
          When addressing a housing affordability crisis, there is always a tug-of-war between demand- and supply-side housing interventions. Demand-side interventions, which directly help households secure housing, are often favoured because of their more immediate impact. The results are easier to see and measure compared to building new homes, which take years to deliver. A basic principle of supply and demand shows that if demand increases without proportionate supply, prices will increase. New modeling by CMHC shows that this dynamic occurs with housing demand-side interventions. Over time, they ma
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q4-T1-032
    section: "Population Subgroups"
    sentence: "This dynamic is particularly critical for first-time buyers and young families, as major urban centers have seen housing costs outpace income growth, pushing homeownership beyond reach for many middle-class Canadians.[11]"
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

  - claim_id: Q4-T1-033
    section: "Population Subgroups"
    sentence: "Howe Institute notes that this has created significant barriers for first-time buyers.[11]"
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

  - claim_id: Q4-T1-034
    section: "Population Subgroups"
    sentence: "When a demand-side intervention, such as increasing household income or reducing housing costs, corrects this suppression, the newly enabled demand can put upward pressure on prices if not met with proportionate new supply.[9]"
    cited_evidence:
      - evidence_id: ev_020
        bibliography_num: 9
        url: "https://www.cmhc-schl.gc.ca/observer/2026/why-demand-side-interventions-need-to-be-targeted-and-offset-with-supply"
        tier: T4
        span: '0-500'
        title: "Targeted demand interventions need supply for housing market ..."
        span_text: |
          When addressing a housing affordability crisis, there is always a tug-of-war between demand- and supply-side housing interventions. Demand-side interventions, which directly help households secure housing, are often favoured because of their more immediate impact. The results are easier to see and measure compared to building new homes, which take years to deliver. A basic principle of supply and demand shows that if demand increases without proportionate supply, prices will increase. New modeling by CMHC shows that this dynamic occurs with housing demand-side interventions. Over time, they ma
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q4-T1-035
    section: "Population Subgroups"
    sentence: "Therefore, CMHC analysis emphasizes that demand-side supports must be targeted and accompanied by sufficient supply to avoid worsening affordability for the broader population.[9][15]"
    cited_evidence:
      - evidence_id: ev_020
        bibliography_num: 9
        url: "https://www.cmhc-schl.gc.ca/observer/2026/why-demand-side-interventions-need-to-be-targeted-and-offset-with-supply"
        tier: T4
        span: '0-500'
        title: "Targeted demand interventions need supply for housing market ..."
        span_text: |
          When addressing a housing affordability crisis, there is always a tug-of-war between demand- and supply-side housing interventions. Demand-side interventions, which directly help households secure housing, are often favoured because of their more immediate impact. The results are easier to see and measure compared to building new homes, which take years to deliver. A basic principle of supply and demand shows that if demand increases without proportionate supply, prices will increase. New modeling by CMHC shows that this dynamic occurs with housing demand-side interventions. Over time, they ma
      - evidence_id: ev_003
        bibliography_num: 15
        url: "https://www.cmhc-schl.gc.ca/observer/2026/why-demand-side-interventions-need-to-be-targeted-and-offset-with-supply"
        tier: T4
        span: '0-500'
        title: "Targeted demand interventions need supply for housing market ..."
        span_text: |
          Title: Good intentions gone rogue: Balancing housing demand & supply URL Source: https://www.cmhc-schl.gc.ca/observer/2026/why-demand-side-interventions-need-to-be-targeted-and-offset-with-supply Markdown Content: # Targeted demand interventions need supply for housing market affordability | CMHC (https://www.cmhc-schl.gc.ca/observer/2026/why-demand-side-interventions-need-to-be-targeted-and-offset-with-supply#maincontent) [![Image 2: CMHC Home](https://assets.cmhc-schl.gc.ca/sites/cmhc/shared/imgs/chevron-en.png?rev=19e0635b-89b7-466b-a1b9-5255bd257bd5&h=142&iar=0&w=300)Canada Mortgage and Ho
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
