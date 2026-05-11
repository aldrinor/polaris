Independent Tier-1 audit of 7 Q5 Pharmacare claims. Output YAML records only.

You are populating Tier-1 audit fields for each claim in the BATCH below.

# Tier-1 schema (per claim)

```yaml
- claim_id: Q5-T1-NNN
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
  - critical = the headline policy-decision number (e.g., $11.2B Bill C-64 cost, October 2024 passage date)
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

# Q5 Pharmacare claim enumeration — Tier-1 pilot (GH#420 I-eval-002)
# Total verified-finding claims: 28

schema_version: tier1_v1
report: outputs/I-beat-001_round_q5_retry/policy/carney_pharmacare_bill_c64_evidence/report.md
claims:
  - claim_id: Q5-T1-015
    section: 'Population Subgroups'
    sentence: 'For working-age Quebecers, this translated to an access advantage; as of 2014, 9.2% of Quebecers aged 55 to 64 reported not filling prescriptions due to cost, compared to 13.9% of similarly aged residents in the rest of Canada .'
    cited_evidence:
      - evidence_id: ev_000
        bibliography_num: 4
        url: 'https://pmc.ncbi.nlm.nih.gov/articles/PMC5636629/'
        tier: T4
        span: '2100-2600'
        title: "Evaluating the effects of Quebec's private–public drug insurance ..."
        span_text: |
          s
          
          [...]
          
          th medicines and physicians’ services among the working-age population.[9](https://pmc.ncbi.nlm.nih.gov/articles/PMC5636629/#b9-189e1259) This advantage with respect to insurance for working-aged Quebecers appears to have been sustained: as of 2014, 9.2% of Quebecers aged 55 to 64 reported that they had not filled prescriptions because of cost, whereas 13.9% of similarly aged residents in the rest of Canada reported such access barriers.[10](https://pmc.ncbi.nlm.nih.gov/articles/PMC563
      - evidence_id: ev_019
        bibliography_num: 5
        url: 'https://pmc.ncbi.nlm.nih.gov/articles/PMC5636629/'
        tier: T4
        span: '2100-2600'
        title: "Evaluating the effects of Quebec's private–public drug insurance ..."
        span_text: |
          s
          
          [...]
          
          th medicines and physicians’ services among the working-age population.[9](https://pmc.ncbi.nlm.nih.gov/articles/PMC5636629/#b9-189e1259) This advantage with respect to insurance for working-aged Quebecers appears to have been sustained: as of 2014, 9.2% of Quebecers aged 55 to 64 reported that they had not filled prescriptions because of cost, whereas 13.9% of similarly aged residents in the rest of Canada reported such access barriers.[10](https://pmc.ncbi.nlm.nih.gov/articles/PMC563
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q5-T1-016
    section: 'Population Subgroups'
    sentence: 'However, this advantage did not extend to older adults, as 6.6% of Quebecers aged 65 and older reported cost-related non-adherence, a rate worse than the 4.1% reported by seniors in the rest of Canada .'
    cited_evidence:
      - evidence_id: ev_000
        bibliography_num: 4
        url: 'https://pmc.ncbi.nlm.nih.gov/articles/PMC5636629/'
        tier: T4
        span: '2700-3200'
        title: "Evaluating the effects of Quebec's private–public drug insurance ..."
        span_text: |
          iated with reductio
          
          [...]
          
          ance in 2002 and eliminated those charges in 2007. As a result of remaining user charges under Quebec’s public drug plan, survey data indicate that older Quebecers do not have the same comparative access advantages as working-age Quebecers: in 2014, 6.6% of Quebecers aged 65 and older reported that they had not filled prescriptions owing to cost, whereas 4.1% of similarly aged residents in the rest of Canada reported such access barriers.[10](https://pmc.ncbi.nlm.nih.
      - evidence_id: ev_019
        bibliography_num: 5
        url: 'https://pmc.ncbi.nlm.nih.gov/articles/PMC5636629/'
        tier: T4
        span: '2700-3200'
        title: "Evaluating the effects of Quebec's private–public drug insurance ..."
        span_text: |
          iated with reductio
          
          [...]
          
          ance in 2002 and eliminated those charges in 2007. As a result of remaining user charges under Quebec’s public drug plan, survey data indicate that older Quebecers do not have the same comparative access advantages as working-age Quebecers: in 2014, 6.6% of Quebecers aged 65 and older reported that they had not filled prescriptions owing to cost, whereas 4.1% of similarly aged residents in the rest of Canada reported such access barriers.[10](https://pmc.ncbi.nlm.nih.
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q5-T1-017
    section: 'Population Subgroups'
    sentence: 'The financial burden of the system falls disproportionately on lower-income households .'
    cited_evidence:
      - evidence_id: ev_000
        bibliography_num: 4
        url: 'https://pmc.ncbi.nlm.nih.gov/articles/PMC5636629/'
        tier: T4
        span: '200-700'
        title: "Evaluating the effects of Quebec's private–public drug insurance ..."
        span_text: |
          public system of prescription drug insurance increased access to insurance for working-age residents and increased user charges for beneficiaries of public drug plans._ * _Quebec’s regime increased access to medicines for working-age residents of Quebec; however, access to medicines in Quebec is lower than in comparable countries._ * _The premiums, deductibles and coinsurance under Quebec’s regime represent a greater proportion of income for lower-income households than for high-income ones._ * 
      - evidence_id: ev_019
        bibliography_num: 5
        url: 'https://pmc.ncbi.nlm.nih.gov/articles/PMC5636629/'
        tier: T4
        span: '200-700'
        title: "Evaluating the effects of Quebec's private–public drug insurance ..."
        span_text: |
          public system of prescription drug insurance increased access to insurance for working-age residents and increased user charges for beneficiaries of public drug plans._ * _Quebec’s regime increased access to medicines for working-age residents of Quebec; however, access to medicines in Quebec is lower than in comparable countries._ * _The premiums, deductibles and coinsurance under Quebec’s regime represent a greater proportion of income for lower-income households than for high-income ones._ * 
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q5-T1-018
    section: 'Population Subgroups'
    sentence: 'The mandatory public premium represents more than 3% of household income for couple families earning $40,000, but only 1.6% for those at the $80,000 median income and 0.7% or less for families with incomes over $180,000 .'
    cited_evidence:
      - evidence_id: ev_000
        bibliography_num: 4
        url: 'https://pmc.ncbi.nlm.nih.gov/articles/PMC5636629/'
        tier: T4
        span: '5100-5600'
        title: "Evaluating the effects of Quebec's private–public drug insurance ..."
        span_text: |
          
          mes higher than $39 880 must pay $1334 in annual premiums.[8](https://pmc.ncbi.nlm.nih.gov/articles/PMC5636629/#b8-189e1259) That mandatory public premium represents more than 3% of household income for couple families earning $40 000; it represents 1.6% of income for couple families earning the $80 000 median income of such households; and it represents 0.7% or less of income for the roughly 10% of couple families with incomes higher than $180 000.[18](https://pmc.ncbi.nlm.nih.gov/articles/PMC
      - evidence_id: ev_019
        bibliography_num: 5
        url: 'https://pmc.ncbi.nlm.nih.gov/articles/PMC5636629/'
        tier: T4
        span: '5100-5600'
        title: "Evaluating the effects of Quebec's private–public drug insurance ..."
        span_text: |
          
          mes higher than $39 880 must pay $1334 in annual premiums.[8](https://pmc.ncbi.nlm.nih.gov/articles/PMC5636629/#b8-189e1259) That mandatory public premium represents more than 3% of household income for couple families earning $40 000; it represents 1.6% of income for couple families earning the $80 000 median income of such households; and it represents 0.7% or less of income for the roughly 10% of couple families with incomes higher than $180 000.[18](https://pmc.ncbi.nlm.nih.gov/articles/PMC
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q5-T1-019
    section: 'Population Subgroups'
    sentence: 'Premiums for private insurance in Quebec may be even more regressive .'
    cited_evidence:
      - evidence_id: ev_000
        bibliography_num: 4
        url: 'https://pmc.ncbi.nlm.nih.gov/articles/PMC5636629/'
        tier: T4
        span: '5200-5700'
        title: "Evaluating the effects of Quebec's private–public drug insurance ..."
        span_text: |
          /PMC5636629/#b8-189e1259) That mandatory public premium represents more than 3% of household income for couple families earning $40 000; it represents 1.6% of income for couple families earning the $80 000 median income of such households; and it represents 0.7% or less of income for the roughly 10% of couple families with incomes higher than $180 000.[18](https://pmc.ncbi.nlm.nih.gov/articles/PMC5636629/#b18-189e1259) Premiums for private insurance in Quebec may be even more regressive. This is
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q5-T1-020
    section: 'Population Subgroups'
    sentence: 'For a patient with a low medication burden (approximately $500 in annual drug costs), out-of-pocket expenses ranged from $250 to $2100 for higher-income residents and from $0 to $700 for lower-income residents across provinces .'
    cited_evidence:
      - evidence_id: ev_003
        bibliography_num: 1
        url: 'https://pmc.ncbi.nlm.nih.gov/articles/PMC5741433/'
        tier: T1
        span: '1000-1500'
        title: 'Comparison of Canadian public medication insurance plans and the ...'
        span_text: |
          g is employed across all provinces. Some residents must pay a premium to receive insurance or must pay 100% of their medication costs until they reach a deductible amount, above which government funding covers a portion of medication costs. With the scenario of low medication burden (medication cost about $500), out-of-pocket costs ranged from $250 to $2100 for higher-income residents and from $0 to $700 for lower-income residents. With the scenario of high medication burden (medication cost abo
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q5-T1-021
    section: 'Population Subgroups'
    sentence: 'This would generate economy-wide savings estimated at $1.4 billion in 2024-25, rising to $2.2 billion in 2027-28, while shifting costs from private to public payers .'
    cited_evidence:
      - evidence_id: ev_013
        bibliography_num: 6
        url: 'https://www.pbo-dpb.ca/en/publications/RP-2324-016-S--cost-estimate-single-payer-universal-drug-plan--estimation-couts-un-regime-assurance-medicaments-universel-payeur-unique'
        tier: T2
        span: '2100-2600'
        title: 'Cost Estimate of a Single-payer Universal Drug Plan'
        span_text: |
          s combined) is estimated to be $11.2 billion in 2024-25, increasing to $13.4 billion in 2027-28 (Table S-1). While there are incremental costs to the public sector resulting from the transfer of expenditures currently covered by the private insurance and out-of-pocket outlays, economy-wide spending on the drugs listed on the formulary is estimated to be lower. The economy-wide savings are projected to increase from $1.4 billion in 2024-25 to $2.2 billion in 2027-28, as the expenditure growth rat
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
