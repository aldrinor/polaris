Independent Tier-1 audit of 7 Q2 Canada-US CUSMA claims. Output YAML records only.

You are populating Tier-1 audit fields for each claim in the BATCH below.

# Tier-1 schema (per claim)

```yaml
- claim_id: Q2-T1-NNN
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
  - critical = the headline policy-decision number (e.g., CUSMA July-2026 review trigger, USMCA dispute counts, tariff schedules, federal procurement thresholds)
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

# Q2 batch 2: claims 8-14
schema_version: tier1_v2
claims:
  - claim_id: Q2-T1-008
    section: "Comparative"
    sentence: "Past actions during Trump's first administration included tariff surcharges on steel and aluminum imports, which a subsequent WTO panel found contravened U.S. treaty commitments.[5]"
    cited_evidence:
      - evidence_id: ev_013
        bibliography_num: 5
        url: "https://www.cgai.ca/canadas_cusma_conundrum"
        tier: T4
        span: '0-500'
        title: "Canada's CUSMA Conundrum - Canadian Global Affairs Institute"
        span_text: |
          Image credit: Twitter/ @JustinTrudeau by [Lawrence L. Herman](Lawrence_Herman) December 2024 Table of Contents [Introduction](#Introduction)[End of the Special Relationship](#Relationship)[CUSMA Scenarios](#Scenarios)[Can CUSMA Be Kept in Play?](#CUSMA)[Bilateral Trade Outside of CUSMA](#Outside)[Conclusions – Avoiding the Cutting Room Floor](#Conclusions)[End Notes](#Endnotes)[About the Author](#Author)[Canadian Global Affairs Institute](#CGAI) Introduction Donald Trump’s egregious threat to impose 25 percent tariffs on all Canadian and Mexican imports shows the world that his administration 
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q2-T1-009
    section: "Comparative"
    sentence: "This shift to applying tariffs on the full imported value of goods, rather than only the metal content, fundamentally changes tariff exposure for derivative products compared to prior measures.[6]"
    cited_evidence:
      - evidence_id: ev_015
        bibliography_num: 6
        url: "https://www.pwc.com/ca/en/services/tax/publications/tax-insights/us-tariffs-steel-aluminum-copper-imports-2026.html"
        tier: T5
        span: '0-500'
        title: "Tax Insights: US tariffs on steel, aluminum and copper imports from ..."
        span_text: |
          April 22, 2026 Issue 2026-17 On April 2, 2026, US President Donald Trump signed a proclamation1 under section 232 of the US Trade Expansion Act of 1962 to strengthen existing tariffs on steel and aluminum imports into the United States and expand the scope of these measures to include copper articles and derivatives for the first time. Effective April 6, 2026, the proclamation establishes a revised tariff structure that:2 These developments build on prior proclamations, which are discussed in our previously released Tax Insights.3 The April 2, 2026 proclamation significantly increases the cost
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q2-T1-010
    section: "Comparative"
    sentence: "These current actions demonstrate an approach where the U.S. shows \"no intention of complying with U.S. treaty obligations\" under CUSMA, signaling that future policy may not be bound by existing agreements.[5]"
    cited_evidence:
      - evidence_id: ev_013
        bibliography_num: 5
        url: "https://www.cgai.ca/canadas_cusma_conundrum"
        tier: T4
        span: '0-500'
        title: "Canada's CUSMA Conundrum - Canadian Global Affairs Institute"
        span_text: |
          Image credit: Twitter/ @JustinTrudeau by [Lawrence L. Herman](Lawrence_Herman) December 2024 Table of Contents [Introduction](#Introduction)[End of the Special Relationship](#Relationship)[CUSMA Scenarios](#Scenarios)[Can CUSMA Be Kept in Play?](#CUSMA)[Bilateral Trade Outside of CUSMA](#Outside)[Conclusions – Avoiding the Cutting Room Floor](#Conclusions)[End Notes](#Endnotes)[About the Author](#Author)[Canadian Global Affairs Institute](#CGAI) Introduction Donald Trump’s egregious threat to impose 25 percent tariffs on all Canadian and Mexican imports shows the world that his administration 
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q2-T1-011
    section: "Comparative"
    sentence: "This creates maximum leverage heading into the CUSMA review process that starts in 2026 under Article 34.7, a process designed to give the U.S. side maximum leverage to demand concessions.[5]"
    cited_evidence:
      - evidence_id: ev_013
        bibliography_num: 5
        url: "https://www.cgai.ca/canadas_cusma_conundrum"
        tier: T4
        span: '0-500'
        title: "Canada's CUSMA Conundrum - Canadian Global Affairs Institute"
        span_text: |
          Image credit: Twitter/ @JustinTrudeau by [Lawrence L. Herman](Lawrence_Herman) December 2024 Table of Contents [Introduction](#Introduction)[End of the Special Relationship](#Relationship)[CUSMA Scenarios](#Scenarios)[Can CUSMA Be Kept in Play?](#CUSMA)[Bilateral Trade Outside of CUSMA](#Outside)[Conclusions – Avoiding the Cutting Room Floor](#Conclusions)[End Notes](#Endnotes)[About the Author](#Author)[Canadian Global Affairs Institute](#CGAI) Introduction Donald Trump’s egregious threat to impose 25 percent tariffs on all Canadian and Mexican imports shows the world that his administration 
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q2-T1-012
    section: "Comparative"
    sentence: "The review itself does not require a complete renegotiation by July 2026, as the agreement will continue for a further 10 years after that date unless a party withdraws with six months' notice, but the U.S. is expected to use the process to apply maximum pressure.[3][5]"
    cited_evidence:
      - evidence_id: ev_000
        bibliography_num: 3
        url: "https://www.policymagazine.ca/thoughts-on-the-cusma-review-and-negotiating-with-trump/"
        tier: T4
        span: '0-500'
        title: "Thoughts on the CUSMA Review and Negotiating with Trump"
        span_text: |
          Thoughts on the CUSMA Review and Negotiating with Trump
          May 2, 2026
          July 1, 2026, is an important date for the future of the Canada-U.S. Mexico Agreement (CUSMA), but there is considerable confusion as to exactly what is supposed to happen on that date. Some think it is the final deadline for negotiations to save the agreement from termination. Others think it is the starting date for a complete renegotiation of the CUSMA.
          I am not directly involved in the evolving review of the CUSMA, but I do have experience in trade negotiations, including as Canada’s chief negotiator for the original NAFTA
      - evidence_id: ev_013
        bibliography_num: 5
        url: "https://www.cgai.ca/canadas_cusma_conundrum"
        tier: T4
        span: '0-500'
        title: "Canada's CUSMA Conundrum - Canadian Global Affairs Institute"
        span_text: |
          Image credit: Twitter/ @JustinTrudeau by [Lawrence L. Herman](Lawrence_Herman) December 2024 Table of Contents [Introduction](#Introduction)[End of the Special Relationship](#Relationship)[CUSMA Scenarios](#Scenarios)[Can CUSMA Be Kept in Play?](#CUSMA)[Bilateral Trade Outside of CUSMA](#Outside)[Conclusions – Avoiding the Cutting Room Floor](#Conclusions)[End Notes](#Endnotes)[About the Author](#Author)[Canadian Global Affairs Institute](#CGAI) Introduction Donald Trump’s egregious threat to impose 25 percent tariffs on all Canadian and Mexican imports shows the world that his administration 
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q2-T1-013
    section: "Comparative"
    sentence: "Consequently, the current tariff regime is not merely a repeat of past actions but a heightened and more complex tool being used to shape the review negotiations, with the explicit goal of altering industrial production patterns and extracting concessions.[6][7]"
    cited_evidence:
      - evidence_id: ev_015
        bibliography_num: 6
        url: "https://www.pwc.com/ca/en/services/tax/publications/tax-insights/us-tariffs-steel-aluminum-copper-imports-2026.html"
        tier: T5
        span: '0-500'
        title: "Tax Insights: US tariffs on steel, aluminum and copper imports from ..."
        span_text: |
          April 22, 2026 Issue 2026-17 On April 2, 2026, US President Donald Trump signed a proclamation1 under section 232 of the US Trade Expansion Act of 1962 to strengthen existing tariffs on steel and aluminum imports into the United States and expand the scope of these measures to include copper articles and derivatives for the first time. Effective April 6, 2026, the proclamation establishes a revised tariff structure that:2 These developments build on prior proclamations, which are discussed in our previously released Tax Insights.3 The April 2, 2026 proclamation significantly increases the cost
      - evidence_id: ev_019
        bibliography_num: 7
        url: "https://www.cbc.ca/news/politics/american-offer-canadian-aluminum-steel-companies-tariff-relief-9.7176321"
        tier: T4
        span: '0-500'
        title: "Trump offers immediate tariff relief to Canadian aluminum and steel ..."
        span_text: |
          Trump offers immediate tariff relief to Canadian aluminum and steel companies that commit to U.S. expansion Canada trying to resume formal talks with U.S. on sectoral tariff relief The Trump administration is now offering Canadian and Mexican aluminum and steel companies immediate tariff relief if they commit to moving production to the United States in the future. The U.S published the notice on Thursday during a tense week that saw both American and Canadian officials publicly air their grievances. "It’s a very aggressive tactic by the United States," said international trade lawyer William 
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q2-T1-014
    section: "Population Subgroups"
    sentence: "This expansion is expected to affect a broad range of Canadian industries, including mining, electrical equipment manufacturing, construction, and infrastructure.[6]"
    cited_evidence:
      - evidence_id: ev_015
        bibliography_num: 6
        url: "https://www.pwc.com/ca/en/services/tax/publications/tax-insights/us-tariffs-steel-aluminum-copper-imports-2026.html"
        tier: T5
        span: '0-500'
        title: "Tax Insights: US tariffs on steel, aluminum and copper imports from ..."
        span_text: |
          April 22, 2026 Issue 2026-17 On April 2, 2026, US President Donald Trump signed a proclamation1 under section 232 of the US Trade Expansion Act of 1962 to strengthen existing tariffs on steel and aluminum imports into the United States and expand the scope of these measures to include copper articles and derivatives for the first time. Effective April 6, 2026, the proclamation establishes a revised tariff structure that:2 These developments build on prior proclamations, which are discussed in our previously released Tax Insights.3 The April 2, 2026 proclamation significantly increases the cost
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
