Independent Tier-1 audit of 2 Q4 Canadian housing supply claims. Output YAML records only.

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

- Do NOT skip a claim. ALL 2 must have records.
- Do NOT auto-VERIFIED just because a span exists. Read the span_text and confirm the decimal is there.
- Do NOT exceed one paragraph of rationale per claim.

# Batch (the claims to audit are below; each has cited_evidence with span_text inline)

# Q4 batch 8: claims 50-51
schema_version: tier1_v2
claims:
  - claim_id: Q4-T1-050
    section: "Long-term Outcomes"
    sentence: "For Indigenous communities in Canada, federal partnership has been critical, with more than $10.7 billion creating almost 22,000 new or repaired homes on-reserve.[10]"
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

  - claim_id: Q4-T1-051
    section: "Long-term Outcomes"
    sentence: "Ultimately, without a sufficient and sustained increase in housing supply, affordability trends will remain under pressure, as low vacancies create a market where competition is intense and the lowest-income households are most vulnerable.[5][6]"
    cited_evidence:
      - evidence_id: ev_002
        bibliography_num: 5
        url: "https://www.stlouisfed.org/on-the-economy/2026/apr/supply-side-of-us-housing-challenge"
        tier: UNKNOWN
        span: '0-500'
        title: "The Supply Side of the U.S. Housing Challenge | St. Louis Fed"
        span_text: |
          America Underbuilt Inc.: The Supply Side of the U.S. Housing Challenge
          In a recent post, we documented how housing prices have dramatically outpaced income growth across most U.S. counties over the past two decades. One of the key drivers identified was inelastic housing supply—the inability of new construction to respond adequately to rising demand. This companion post examines the supply side of the equation: How much housing is the U.S. building, and is it enough?
          Building Permits: A Long-Term Perspective
          To understand housing supply, we start with building permits—the first step in the con
      - evidence_id: ev_005
        bibliography_num: 6
        url: "https://www.novoco.com/notes-from-novogradac/how-new-housing-affects-affordability-evidence-limits-and-policy-implications"
        tier: T4
        span: '0-500'
        title: "How New Housing Affects Affordability: Evidence, Limits and Policy ..."
        span_text: |
          How New Housing Affects Affordability: Evidence, Limits and Policy Implications Recent Insights Key Takeaways A growing body of empirical research finds that new market-rate housing can affect broader affordability conditions through household moves, while also underscoring that market outcomes alone are insufficient to meet needs at very low incomes. - New market rate construction expands mobility through vacancy chains, easing rent pressures even in high cost markets by opening more homes. - Filtering and market wide affordability gains occur unevenly, slowing or stalling in tight markets, u
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence


# Output

Single YAML block. List of records in claim_id order. Then a summary:

```yaml
- claim_id: ...
  ...
- claim_id: ...
  ...

batch_summary:
  total: 2
  per_verdict: {VERIFIED: N, PARTIAL: N, UNSUPPORTED: N, FABRICATED: N, UNREACHABLE: N}
  per_context_match: {yes: N, partial: N, no: N}
  notable: ["..."]
```

Output the YAML directly. No commentary outside.
