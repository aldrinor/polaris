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

# Q2 batch 2: claims 8-14 (re-run with full direct_quote)
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
          Image credit: Twitter/ @JustinTrudeau by [Lawrence L. Herman](Lawrence_Herman) December 2024 Table of Contents [Introduction](#Introduction)[End of the Special Relationship](#Relationship)[CUSMA Scenarios](#Scenarios)[Can CUSMA Be Kept in Play?](#CUSMA)[Bilateral Trade Outside of CUSMA](#Outside)[Conclusions – Avoiding the Cutting Room Floor](#Conclusions)[End Notes](#Endnotes)[About the Author](#Author)[Canadian Global Affairs Institute](#CGAI) Introduction Donald Trump’s egregious threat to impose 25 percent tariffs on all Canadian and Mexican imports shows the world that his administration has no intention of complying with U.S. treaty obligations. The threatened tariffs contravene U.S. obligations under the Canada-U.S.-Mexico Agreement (CUSMA) as well as the World Trade Organization (WTO) Agreement. It is a signal that shows Canada, Mexico and the world at large that his future government will not be bound by America’s treaty obligations, be they multilateral or bilateral. In other words, there are no rules that the U.S. can be expected to follow in ongoing trade relations. That approach was seen during Trump’s first administration, when tariff surcharges were applied on imports of steel, aluminum, solar panels and other items, which a subsequent WTO panel found had contravened U.S. treaty commitments. While some experts [maintain](https://www.economist.com/united-states/2024/11/27/does-donald-trump-have-unlimited-authority-to-impose-tariffs) that such tariff increases ar
          
          [...]
          
          titutional issues, and while it may seem far-fetched, Trump could threaten do this again with CUSMA, to maximize political leverage.[2](#_ftn2) The U.S. does have the clear right withdraw from the Agreement by giving six months’ notice under Article 34.6. If it did that, even if Canada and Mexico stayed on board, CUSMA would effectively be terminated. While it’s hard to envisage that happening because, as many have commented, it would be hugely disruptive to the U.S. economy itself, it has to be factored in as a possible, even if far-fetched, scenario. What is more plausible would be an array of tough U.S. demands to change CUSMA to its liking in the review process that starts in 2026 under Article 34.7 of the Agreement. The article says that if the three governments don’t agree to extend it, the Agreement will terminate in 2036. Until then, there will be with annual reviews of the Agreement’s operation, a process was designed to give the U.S. side maximum leverage, as former U.S. Trade Representative Robert Lighthizer and Katherine Tai, his successor, have made clear. While it’s difficult to predict how the Article 34.7 review will unfold, the U.S. side will certainly use the process to apply maximum pressure on Canada, for example, by demanding concessions to end the U.S. trade imbalance with Canada (excluding hydrocarbons). It will almost certainly insist on its 
          
          [...]
          
          ources and potential, and cooperation in multilateral fora. It is also an area where Canada has important advantages: “Canada already supplies many of the minerals deemed critical by the United States: in 2020, bilateral mineral trade was valued at $95.6 billion, with 298 Canadian mining companies and a combined $40 billion in Canadian mining assets south of the border.”[3](#_ftn3) The Action Plan is a substantive bilateral effort, outside of the three-way CUSMA arrangements that is compatible with 
          
          [...]
          
          uring the 2017 NAFTA renegotiations, the initial US position was that the new agreement (CUSMA/USMCA) should terminate definitively after six years. In the end, the Americans agreed to the 2036 termination date and the 2026 review process in Article 34.7. [3](#_ftnref3) Ibid. Canada is also a member of the US-led Minerals Security Partnership, which encourages public and private sector coordination on critical minerals investments. [4](#_ftnref4) Defence Production Sharing Agreement (1 October 1956)
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
          April 22, 2026 Issue 2026-17 On April 2, 2026, US President Donald Trump signed a proclamation1 under section 232 of the US Trade Expansion Act of 1962 to strengthen existing tariffs on steel and aluminum imports into the United States and expand the scope of these measures to include copper articles and derivatives for the first time. Effective April 6, 2026, the proclamation establishes a revised tariff structure that:2 These developments build on prior proclamations, which are discussed in our previously released Tax Insights.3 The April 2, 2026 proclamation significantly increases the cost of importing affected goods into the United States and introduces complex, variable tariff outcomes that depend on product classification, origin and participation in government programs (e.g. trade agreements, reduced rate categories). The inclusion of copper under section 232 for the first time represents a material expansion that will affect a broad range of Canadian industries, including mining, electrical equipment manufacturing, construction and infrastructure. For metals importers, the shift to applying tariffs on the full imported value of goods, rather than only the metal content, can fundamentally change the tariff exposure for derivative products. The proclamation includes a reduced list of covered derivative products, but the revised tariff calculation approach means that the remaining derivative products could face significantly higher tariffs than under the prior section 2
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
          Image credit: Twitter/ @JustinTrudeau by [Lawrence L. Herman](Lawrence_Herman) December 2024 Table of Contents [Introduction](#Introduction)[End of the Special Relationship](#Relationship)[CUSMA Scenarios](#Scenarios)[Can CUSMA Be Kept in Play?](#CUSMA)[Bilateral Trade Outside of CUSMA](#Outside)[Conclusions – Avoiding the Cutting Room Floor](#Conclusions)[End Notes](#Endnotes)[About the Author](#Author)[Canadian Global Affairs Institute](#CGAI) Introduction Donald Trump’s egregious threat to impose 25 percent tariffs on all Canadian and Mexican imports shows the world that his administration has no intention of complying with U.S. treaty obligations. The threatened tariffs contravene U.S. obligations under the Canada-U.S.-Mexico Agreement (CUSMA) as well as the World Trade Organization (WTO) Agreement. It is a signal that shows Canada, Mexico and the world at large that his future government will not be bound by America’s treaty obligations, be they multilateral or bilateral. In other words, there are no rules that the U.S. can be expected to follow in ongoing trade relations. That approach was seen during Trump’s first administration, when tariff surcharges were applied on imports of steel, aluminum, solar panels and other items, which a subsequent WTO panel found had contravened U.S. treaty commitments. While some experts [maintain](https://www.economist.com/united-states/2024/11/27/does-donald-trump-have-unlimited-authority-to-impose-tariffs) that such tariff increases ar
          
          [...]
          
          titutional issues, and while it may seem far-fetched, Trump could threaten do this again with CUSMA, to maximize political leverage.[2](#_ftn2) The U.S. does have the clear right withdraw from the Agreement by giving six months’ notice under Article 34.6. If it did that, even if Canada and Mexico stayed on board, CUSMA would effectively be terminated. While it’s hard to envisage that happening because, as many have commented, it would be hugely disruptive to the U.S. economy itself, it has to be factored in as a possible, even if far-fetched, scenario. What is more plausible would be an array of tough U.S. demands to change CUSMA to its liking in the review process that starts in 2026 under Article 34.7 of the Agreement. The article says that if the three governments don’t agree to extend it, the Agreement will terminate in 2036. Until then, there will be with annual reviews of the Agreement’s operation, a process was designed to give the U.S. side maximum leverage, as former U.S. Trade Representative Robert Lighthizer and Katherine Tai, his successor, have made clear. While it’s difficult to predict how the Article 34.7 review will unfold, the U.S. side will certainly use the process to apply maximum pressure on Canada, for example, by demanding concessions to end the U.S. trade imbalance with Canada (excluding hydrocarbons). It will almost certainly insist on its 
          
          [...]
          
          ources and potential, and cooperation in multilateral fora. It is also an area where Canada has important advantages: “Canada already supplies many of the minerals deemed critical by the United States: in 2020, bilateral mineral trade was valued at $95.6 billion, with 298 Canadian mining companies and a combined $40 billion in Canadian mining assets south of the border.”[3](#_ftn3) The Action Plan is a substantive bilateral effort, outside of the three-way CUSMA arrangements that is compatible with 
          
          [...]
          
          uring the 2017 NAFTA renegotiations, the initial US position was that the new agreement (CUSMA/USMCA) should terminate definitively after six years. In the end, the Americans agreed to the 2036 termination date and the 2026 review process in Article 34.7. [3](#_ftnref3) Ibid. Canada is also a member of the US-led Minerals Security Partnership, which encourages public and private sector coordination on critical minerals investments. [4](#_ftnref4) Defence Production Sharing Agreement (1 October 1956)
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
          Image credit: Twitter/ @JustinTrudeau by [Lawrence L. Herman](Lawrence_Herman) December 2024 Table of Contents [Introduction](#Introduction)[End of the Special Relationship](#Relationship)[CUSMA Scenarios](#Scenarios)[Can CUSMA Be Kept in Play?](#CUSMA)[Bilateral Trade Outside of CUSMA](#Outside)[Conclusions – Avoiding the Cutting Room Floor](#Conclusions)[End Notes](#Endnotes)[About the Author](#Author)[Canadian Global Affairs Institute](#CGAI) Introduction Donald Trump’s egregious threat to impose 25 percent tariffs on all Canadian and Mexican imports shows the world that his administration has no intention of complying with U.S. treaty obligations. The threatened tariffs contravene U.S. obligations under the Canada-U.S.-Mexico Agreement (CUSMA) as well as the World Trade Organization (WTO) Agreement. It is a signal that shows Canada, Mexico and the world at large that his future government will not be bound by America’s treaty obligations, be they multilateral or bilateral. In other words, there are no rules that the U.S. can be expected to follow in ongoing trade relations. That approach was seen during Trump’s first administration, when tariff surcharges were applied on imports of steel, aluminum, solar panels and other items, which a subsequent WTO panel found had contravened U.S. treaty commitments. While some experts [maintain](https://www.economist.com/united-states/2024/11/27/does-donald-trump-have-unlimited-authority-to-impose-tariffs) that such tariff increases ar
          
          [...]
          
          titutional issues, and while it may seem far-fetched, Trump could threaten do this again with CUSMA, to maximize political leverage.[2](#_ftn2) The U.S. does have the clear right withdraw from the Agreement by giving six months’ notice under Article 34.6. If it did that, even if Canada and Mexico stayed on board, CUSMA would effectively be terminated. While it’s hard to envisage that happening because, as many have commented, it would be hugely disruptive to the U.S. economy itself, it has to be factored in as a possible, even if far-fetched, scenario. What is more plausible would be an array of tough U.S. demands to change CUSMA to its liking in the review process that starts in 2026 under Article 34.7 of the Agreement. The article says that if the three governments don’t agree to extend it, the Agreement will terminate in 2036. Until then, there will be with annual reviews of the Agreement’s operation, a process was designed to give the U.S. side maximum leverage, as former U.S. Trade Representative Robert Lighthizer and Katherine Tai, his successor, have made clear. While it’s difficult to predict how the Article 34.7 review will unfold, the U.S. side will certainly use the process to apply maximum pressure on Canada, for example, by demanding concessions to end the U.S. trade imbalance with Canada (excluding hydrocarbons). It will almost certainly insist on its 
          
          [...]
          
          ources and potential, and cooperation in multilateral fora. It is also an area where Canada has important advantages: “Canada already supplies many of the minerals deemed critical by the United States: in 2020, bilateral mineral trade was valued at $95.6 billion, with 298 Canadian mining companies and a combined $40 billion in Canadian mining assets south of the border.”[3](#_ftn3) The Action Plan is a substantive bilateral effort, outside of the three-way CUSMA arrangements that is compatible with 
          
          [...]
          
          uring the 2017 NAFTA renegotiations, the initial US position was that the new agreement (CUSMA/USMCA) should terminate definitively after six years. In the end, the Americans agreed to the 2036 termination date and the 2026 review process in Article 34.7. [3](#_ftnref3) Ibid. Canada is also a member of the US-led Minerals Security Partnership, which encourages public and private sector coordination on critical minerals investments. [4](#_ftnref4) Defence Production Sharing Agreement (1 October 1956)
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
          I am not directly involved in the evolving review of the CUSMA, but I do have experience in trade negotiations, including as Canada’s chief negotiator for the original NAFTA negotiations.
          I will not offer comments on the detail of what is going on today. Rather, I will focus on issues relevant to any big negotiation and comment on some matters relating to the review of the CUSMA that are in the public domain.
          The CUSMA Review
          The text of CUSMA itself (Article 34.7: Review and Term Extension) provides the only authoritative description of what will happen on Canada Day.
          “This Agreement shall terminate 16 years after the date of its entry into force (July 1, 2020), unless each Party confirms it wishes to continue this Agreement for a new 16-year term.” In other words, the agreement will continue for a further 10 years after July 1 regardless of what happens on that date, unless one of the parties decides to exercise its right to withdraw from the agreement which is possible at any time with six months written notice.
          Importantly, Article 34:7 provides that th
      - evidence_id: ev_013
        bibliography_num: 5
        url: "https://www.cgai.ca/canadas_cusma_conundrum"
        tier: T4
        span: '0-500'
        title: "Canada's CUSMA Conundrum - Canadian Global Affairs Institute"
        span_text: |
          Image credit: Twitter/ @JustinTrudeau by [Lawrence L. Herman](Lawrence_Herman) December 2024 Table of Contents [Introduction](#Introduction)[End of the Special Relationship](#Relationship)[CUSMA Scenarios](#Scenarios)[Can CUSMA Be Kept in Play?](#CUSMA)[Bilateral Trade Outside of CUSMA](#Outside)[Conclusions – Avoiding the Cutting Room Floor](#Conclusions)[End Notes](#Endnotes)[About the Author](#Author)[Canadian Global Affairs Institute](#CGAI) Introduction Donald Trump’s egregious threat to impose 25 percent tariffs on all Canadian and Mexican imports shows the world that his administration has no intention of complying with U.S. treaty obligations. The threatened tariffs contravene U.S. obligations under the Canada-U.S.-Mexico Agreement (CUSMA) as well as the World Trade Organization (WTO) Agreement. It is a signal that shows Canada, Mexico and the world at large that his future government will not be bound by America’s treaty obligations, be they multilateral or bilateral. In other words, there are no rules that the U.S. can be expected to follow in ongoing trade relations. That approach was seen during Trump’s first administration, when tariff surcharges were applied on imports of steel, aluminum, solar panels and other items, which a subsequent WTO panel found had contravened U.S. treaty commitments. While some experts [maintain](https://www.economist.com/united-states/2024/11/27/does-donald-trump-have-unlimited-authority-to-impose-tariffs) that such tariff increases ar
          
          [...]
          
          titutional issues, and while it may seem far-fetched, Trump could threaten do this again with CUSMA, to maximize political leverage.[2](#_ftn2) The U.S. does have the clear right withdraw from the Agreement by giving six months’ notice under Article 34.6. If it did that, even if Canada and Mexico stayed on board, CUSMA would effectively be terminated. While it’s hard to envisage that happening because, as many have commented, it would be hugely disruptive to the U.S. economy itself, it has to be factored in as a possible, even if far-fetched, scenario. What is more plausible would be an array of tough U.S. demands to change CUSMA to its liking in the review process that starts in 2026 under Article 34.7 of the Agreement. The article says that if the three governments don’t agree to extend it, the Agreement will terminate in 2036. Until then, there will be with annual reviews of the Agreement’s operation, a process was designed to give the U.S. side maximum leverage, as former U.S. Trade Representative Robert Lighthizer and Katherine Tai, his successor, have made clear. While it’s difficult to predict how the Article 34.7 review will unfold, the U.S. side will certainly use the process to apply maximum pressure on Canada, for example, by demanding concessions to end the U.S. trade imbalance with Canada (excluding hydrocarbons). It will almost certainly insist on its 
          
          [...]
          
          ources and potential, and cooperation in multilateral fora. It is also an area where Canada has important advantages: “Canada already supplies many of the minerals deemed critical by the United States: in 2020, bilateral mineral trade was valued at $95.6 billion, with 298 Canadian mining companies and a combined $40 billion in Canadian mining assets south of the border.”[3](#_ftn3) The Action Plan is a substantive bilateral effort, outside of the three-way CUSMA arrangements that is compatible with 
          
          [...]
          
          uring the 2017 NAFTA renegotiations, the initial US position was that the new agreement (CUSMA/USMCA) should terminate definitively after six years. In the end, the Americans agreed to the 2036 termination date and the 2026 review process in Article 34.7. [3](#_ftnref3) Ibid. Canada is also a member of the US-led Minerals Security Partnership, which encourages public and private sector coordination on critical minerals investments. [4](#_ftnref4) Defence Production Sharing Agreement (1 October 1956)
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
          April 22, 2026 Issue 2026-17 On April 2, 2026, US President Donald Trump signed a proclamation1 under section 232 of the US Trade Expansion Act of 1962 to strengthen existing tariffs on steel and aluminum imports into the United States and expand the scope of these measures to include copper articles and derivatives for the first time. Effective April 6, 2026, the proclamation establishes a revised tariff structure that:2 These developments build on prior proclamations, which are discussed in our previously released Tax Insights.3 The April 2, 2026 proclamation significantly increases the cost of importing affected goods into the United States and introduces complex, variable tariff outcomes that depend on product classification, origin and participation in government programs (e.g. trade agreements, reduced rate categories). The inclusion of copper under section 232 for the first time represents a material expansion that will affect a broad range of Canadian industries, including mining, electrical equipment manufacturing, construction and infrastructure. For metals importers, the shift to applying tariffs on the full imported value of goods, rather than only the metal content, can fundamentally change the tariff exposure for derivative products. The proclamation includes a reduced list of covered derivative products, but the revised tariff calculation approach means that the remaining derivative products could face significantly higher tariffs than under the prior section 2
      - evidence_id: ev_019
        bibliography_num: 7
        url: "https://www.cbc.ca/news/politics/american-offer-canadian-aluminum-steel-companies-tariff-relief-9.7176321"
        tier: T4
        span: '0-500'
        title: "Trump offers immediate tariff relief to Canadian aluminum and steel ..."
        span_text: |
          Trump offers immediate tariff relief to Canadian aluminum and steel companies that commit to U.S. expansion Canada trying to resume formal talks with U.S. on sectoral tariff relief The Trump administration is now offering Canadian and Mexican aluminum and steel companies immediate tariff relief if they commit to moving production to the United States in the future. The U.S published the notice on Thursday during a tense week that saw both American and Canadian officials publicly air their grievances. "It’s a very aggressive tactic by the United States," said international trade lawyer William Pellerin. "This really reinforces the approach that we’ve seen from the United States for a while now, which is simply: We win if you lose." U.S. President Donald Trump’s trade policy is focused on using steep tariffs to try to push foreign companies of all kinds to move production to the U.S. As part of that strategy, the administration has been clobbering Canada’s aluminum and steel sectors with tariffs for more than a year, escalating to 50 per cent. Earlier this month, the U.S. also changed how it applies metal duties to manufactured goods, hitting Canadian companies hard. "Many of our clients are laying off employees, closing facilities," said Pellerin, whose firm McMillan LLP represents companies facing American tariffs. "It is really painful to see these massive layoffs happen in Canada." - Cross Country Checkup is asking: How are Donald Trump’s trade threats affecting your job, y
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
          April 22, 2026 Issue 2026-17 On April 2, 2026, US President Donald Trump signed a proclamation1 under section 232 of the US Trade Expansion Act of 1962 to strengthen existing tariffs on steel and aluminum imports into the United States and expand the scope of these measures to include copper articles and derivatives for the first time. Effective April 6, 2026, the proclamation establishes a revised tariff structure that:2 These developments build on prior proclamations, which are discussed in our previously released Tax Insights.3 The April 2, 2026 proclamation significantly increases the cost of importing affected goods into the United States and introduces complex, variable tariff outcomes that depend on product classification, origin and participation in government programs (e.g. trade agreements, reduced rate categories). The inclusion of copper under section 232 for the first time represents a material expansion that will affect a broad range of Canadian industries, including mining, electrical equipment manufacturing, construction and infrastructure. For metals importers, the shift to applying tariffs on the full imported value of goods, rather than only the metal content, can fundamentally change the tariff exposure for derivative products. The proclamation includes a reduced list of covered derivative products, but the revised tariff calculation approach means that the remaining derivative products could face significantly higher tariffs than under the prior section 2
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
