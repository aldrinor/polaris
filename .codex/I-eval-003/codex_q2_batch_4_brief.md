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

# Q2 batch 4: claims 22-28 (re-run with full direct_quote)
schema_version: tier1_v2
claims:
  - claim_id: Q2-T1-022
    section: "Long-term Outcomes"
    sentence: "One analysis notes the range of possible outcomes is wide, from an extension of CUSMA with limited changes for a new 16-year term\u2014the base-case assumption that reduces uncertainty\u2014to significant renegotiation or even member withdrawal.[9]"
    cited_evidence:
      - evidence_id: ev_008
        bibliography_num: 9
        url: "https://www.bankofcanada.ca/publications/mpr/mpr-2026-01-28/in-focus-2/"
        tier: T4
        span: '0-500'
        title: "The review of the Canada\u2013United States\u2013Mexico Agreement"
        span_text: |
          Monetary Policy Report—January 2026—In focus The future of Canada’s trade agreement with the United States and Mexico is unclear. A review of the agreement could lead to many possible outcomes, and these can have a wide range of impacts on the Canadian economy. The Canada-United States-Mexico Agreement (CUSMA) is a trilateral trade deal that came into effect in 2020. The agreement is up for review in 2026.[1](#footnote-if2-1) The outcome of the review is an important risk to the outlook (see the [Risks](https://www.bankofcanada.ca/publications/mpr/mpr-2026-01-28/risks/) section). The range of possible outcomes is wide How CUSMA negotiations will unfold is uncertain. Possible outcomes include the following: - CUSMA is extended, with limited changes, for a new term of 16 years until 2042. The current regime is maintained, which reduces uncertainty for exporters and around integrated supply chains. The extension of CUSMA is the outcome assumed in the base-case projection. - CUSMA is significantly renegotiated. This could make trade more expensive. For example, stricter rules around proving where a product was made (rules of origin) or a smaller discount on CUSMA-compliant goods (reduced tariff preferences) would increase effective trade costs. At the same time, as part of the negotiations, some sectoral tariff rates could be lowered, reducing trade costs. - Members withdraw from CUSMA. This could result in a significant increase in trade barriers. Alternatively, parties could ag
          
          [...]
          
          ial counter-tariffs, supply chain disruptions and a weaker Canadian dollar would push up consumer prices. At the same time, softer demand and the associated excess supply would dampen consumer prices. Endnotes - 1. See Government of Canada, “Article 34.7: Review and Term Extension,” [Canada-United States-Mexico Agreement (CUSMA) – Chapter 34 – Final provisions](https://www.international.gc.ca/trade-commerce/trade-agreements-accords-commerciaux/agr-acc/cusma-aceum/text-texte/34.aspx?lang=eng)(Decembe
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q2-T1-023
    section: "Long-term Outcomes"
    sentence: "A significant renegotiation could make trade more expensive through measures like stricter rules of origin or reduced tariff preferences, increasing effective trade costs, though some sectoral tariff rates could concurrently be lowered.[9]"
    cited_evidence:
      - evidence_id: ev_008
        bibliography_num: 9
        url: "https://www.bankofcanada.ca/publications/mpr/mpr-2026-01-28/in-focus-2/"
        tier: T4
        span: '0-500'
        title: "The review of the Canada\u2013United States\u2013Mexico Agreement"
        span_text: |
          Monetary Policy Report—January 2026—In focus The future of Canada’s trade agreement with the United States and Mexico is unclear. A review of the agreement could lead to many possible outcomes, and these can have a wide range of impacts on the Canadian economy. The Canada-United States-Mexico Agreement (CUSMA) is a trilateral trade deal that came into effect in 2020. The agreement is up for review in 2026.[1](#footnote-if2-1) The outcome of the review is an important risk to the outlook (see the [Risks](https://www.bankofcanada.ca/publications/mpr/mpr-2026-01-28/risks/) section). The range of possible outcomes is wide How CUSMA negotiations will unfold is uncertain. Possible outcomes include the following: - CUSMA is extended, with limited changes, for a new term of 16 years until 2042. The current regime is maintained, which reduces uncertainty for exporters and around integrated supply chains. The extension of CUSMA is the outcome assumed in the base-case projection. - CUSMA is significantly renegotiated. This could make trade more expensive. For example, stricter rules around proving where a product was made (rules of origin) or a smaller discount on CUSMA-compliant goods (reduced tariff preferences) would increase effective trade costs. At the same time, as part of the negotiations, some sectoral tariff rates could be lowered, reducing trade costs. - Members withdraw from CUSMA. This could result in a significant increase in trade barriers. Alternatively, parties could ag
          
          [...]
          
          ial counter-tariffs, supply chain disruptions and a weaker Canadian dollar would push up consumer prices. At the same time, softer demand and the associated excess supply would dampen consumer prices. Endnotes - 1. See Government of Canada, “Article 34.7: Review and Term Extension,” [Canada-United States-Mexico Agreement (CUSMA) – Chapter 34 – Final provisions](https://www.international.gc.ca/trade-commerce/trade-agreements-accords-commerciaux/agr-acc/cusma-aceum/text-texte/34.aspx?lang=eng)(Decembe
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q2-T1-024
    section: "Long-term Outcomes"
    sentence: "The most severe long-term scenario would be a U.S. withdrawal from the agreement, which it has the right to do by giving six months\u2019 notice under Article 34.6, effectively terminating CUSMA even if Canada and Mexico remain.[5]"
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

  - claim_id: Q2-T1-025
    section: "Long-term Outcomes"
    sentence: "Such an outcome could result in a significant increase in trade barriers, with one source noting it would be hugely disruptive to the U.S. economy itself but must be factored in as a possible scenario.[9][5]"
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
      - evidence_id: ev_008
        bibliography_num: 9
        url: "https://www.bankofcanada.ca/publications/mpr/mpr-2026-01-28/in-focus-2/"
        tier: T4
        span: '0-500'
        title: "The review of the Canada\u2013United States\u2013Mexico Agreement"
        span_text: |
          Monetary Policy Report—January 2026—In focus The future of Canada’s trade agreement with the United States and Mexico is unclear. A review of the agreement could lead to many possible outcomes, and these can have a wide range of impacts on the Canadian economy. The Canada-United States-Mexico Agreement (CUSMA) is a trilateral trade deal that came into effect in 2020. The agreement is up for review in 2026.[1](#footnote-if2-1) The outcome of the review is an important risk to the outlook (see the [Risks](https://www.bankofcanada.ca/publications/mpr/mpr-2026-01-28/risks/) section). The range of possible outcomes is wide How CUSMA negotiations will unfold is uncertain. Possible outcomes include the following: - CUSMA is extended, with limited changes, for a new term of 16 years until 2042. The current regime is maintained, which reduces uncertainty for exporters and around integrated supply chains. The extension of CUSMA is the outcome assumed in the base-case projection. - CUSMA is significantly renegotiated. This could make trade more expensive. For example, stricter rules around proving where a product was made (rules of origin) or a smaller discount on CUSMA-compliant goods (reduced tariff preferences) would increase effective trade costs. At the same time, as part of the negotiations, some sectoral tariff rates could be lowered, reducing trade costs. - Members withdraw from CUSMA. This could result in a significant increase in trade barriers. Alternatively, parties could ag
          
          [...]
          
          ial counter-tariffs, supply chain disruptions and a weaker Canadian dollar would push up consumer prices. At the same time, softer demand and the associated excess supply would dampen consumer prices. Endnotes - 1. See Government of Canada, “Article 34.7: Review and Term Extension,” [Canada-United States-Mexico Agreement (CUSMA) – Chapter 34 – Final provisions](https://www.international.gc.ca/trade-commerce/trade-agreements-accords-commerciaux/agr-acc/cusma-aceum/text-texte/34.aspx?lang=eng)(Decembe
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q2-T1-026
    section: "Long-term Outcomes"
    sentence: "Concurrently, the imposition of retaliatory counter-tariffs, supply chain disruptions, and a weaker Canadian dollar would push up consumer prices, though softer demand would dampen them.[9]"
    cited_evidence:
      - evidence_id: ev_008
        bibliography_num: 9
        url: "https://www.bankofcanada.ca/publications/mpr/mpr-2026-01-28/in-focus-2/"
        tier: T4
        span: '0-500'
        title: "The review of the Canada\u2013United States\u2013Mexico Agreement"
        span_text: |
          Monetary Policy Report—January 2026—In focus The future of Canada’s trade agreement with the United States and Mexico is unclear. A review of the agreement could lead to many possible outcomes, and these can have a wide range of impacts on the Canadian economy. The Canada-United States-Mexico Agreement (CUSMA) is a trilateral trade deal that came into effect in 2020. The agreement is up for review in 2026.[1](#footnote-if2-1) The outcome of the review is an important risk to the outlook (see the [Risks](https://www.bankofcanada.ca/publications/mpr/mpr-2026-01-28/risks/) section). The range of possible outcomes is wide How CUSMA negotiations will unfold is uncertain. Possible outcomes include the following: - CUSMA is extended, with limited changes, for a new term of 16 years until 2042. The current regime is maintained, which reduces uncertainty for exporters and around integrated supply chains. The extension of CUSMA is the outcome assumed in the base-case projection. - CUSMA is significantly renegotiated. This could make trade more expensive. For example, stricter rules around proving where a product was made (rules of origin) or a smaller discount on CUSMA-compliant goods (reduced tariff preferences) would increase effective trade costs. At the same time, as part of the negotiations, some sectoral tariff rates could be lowered, reducing trade costs. - Members withdraw from CUSMA. This could result in a significant increase in trade barriers. Alternatively, parties could ag
          
          [...]
          
          ial counter-tariffs, supply chain disruptions and a weaker Canadian dollar would push up consumer prices. At the same time, softer demand and the associated excess supply would dampen consumer prices. Endnotes - 1. See Government of Canada, “Article 34.7: Review and Term Extension,” [Canada-United States-Mexico Agreement (CUSMA) – Chapter 34 – Final provisions](https://www.international.gc.ca/trade-commerce/trade-agreements-accords-commerciaux/agr-acc/cusma-aceum/text-texte/34.aspx?lang=eng)(Decembe
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q2-T1-027
    section: "Long-term Outcomes"
    sentence: "This process, designed to give the U.S. side maximum leverage, could see the agreement used as a platform to address non-trade issues such as migration, drug trafficking, and continental defense, shaping the region\u2019s economic future for decades.[1]"
    cited_evidence:
      - evidence_id: ev_009
        bibliography_num: 1
        url: "https://www.csis.org/analysis/usmca-review-2026"
        tier: T4
        span: '0-500'
        title: "USMCA Review 2026 - CSIS"
        span_text: |
          USMCA Review 2026 Table of Contents - The Issue - Introduction - The USMCA at Five - President Trump’s Reindustrialization Drive Through Tariffs - Understanding the 2026 Review Clause: Pathways, Risks, and Leverage - Mapping Six Possible Pathways for the USMCA - What Will Be on the Table: Disputes, Demands, and Deal-Breakers - Keeping Sights High: Options to Deepen Cooperation Under the USMCA Available Downloads The Issue The United States–Mexico–Canada Agreement (USMCA), the backbone of North America’s competitiveness, will undergo a formal review starting in July 2026. What was once expected to be a routine assessment aimed at improving implementation is now likely to become a high-stakes negotiation. The Trump administration is poised to seek additional concessions from Mexico and Canada on long-standing trade disputes, while also leveraging the review to address non-trade issues such as migration, drug trafficking, and continental defense. Both neighbors, already in talks with Washington over tariff relief, are approaching the process with caution. While the review may become a platform for the United States to secure short-term wins, it also presents a rare opportunity to modernize the agreement and strengthen North America’s shared competitiveness. How the three nations navigate this moment will shape the region’s economic future for decades. Introduction In 2020, the USMCA replaced the North American Free Trade Agreement (NAFTA), which had governed trade between the th
          
          [...]
          
          n people, accounting for 30 percent of global GDP. Since its ratification, significant progress has been made in expanding trade, investment, and jobs across North America. In 2024, goods and services trade within North America totaled an estimated $1.93 trillion, solidifying Mexico and Canada as the United States’ top trading partners. In July 2026, on the sixth anniversary of the USMCA’s implementation, the three countries will hold a joint review to assess the agreement’s performance and determin
          
          [...]
          
          er NAFTA is its state-to-state dispute settlement system. Under NAFTA, disputes often stalled because one party could block the formation of a panel by refusing to appoint panelists or agree on a roster. The USMCA addresses this flaw through Article 31.8, which creates a standing list of preapproved independent trade experts, ensuring that dispute resolution panels could be formed even when one party is uncooperative. NAFTA’s shortcomings are most evident in the decades-long sugar dispute between th
          
          [...]
          
          um has acknowledged drug consumption as a shared challenge and continues to call for bilateral cooperation. Still, her government has delivered results: Since she took office in October 2024, fentanyl seizures have surged, including a record bust of 1.1 metric tons in December 2025. According to President Sheinbaum, fentanyl trafficking at the U.S.-Mexico border is down 50 percent. In addition, in February 2025, the Mexican government transferred 29 high-level criminal suspects to U.S. custody; in 
          
          [...]
          
          point, not a breaking point, for the future of regional integration. Understanding the 2026 Review Clause: Pathways, Risks, and Leverage The USMCA is designed to last 16 years, expiring on July 1, 2036, unless the parties agree to extend it. Article 34.7 of the agreement requires the United States, Mexico, and Canada to conduct a formal review at the six-year mark. This process requires the three governments, through their Free Trade Commission, to evaluate the agreement’s effectiveness, consider ea
          
          [...]
          
          ears or letting the agreement expire in 2036. Each country may gather input from its stakeholders, including businesses, unions, nongovernmental organizations, legislators, and local authorities involved in or affected by the USMCA. However, Article 34.7 leaves critical gaps and does not explicitly establish how the commission will evaluate or prioritize these proposals, nor does it specify criteria for deciding which suggestions will be considered or dismissed. A
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q2-T1-028
    section: "Long-term Outcomes"
    sentence: "The long-term consequence of a confrontational negotiation could be a weakened institutional framework for dispute resolution, though the USMCA\u2019s standing list of preapproved independent trade experts was designed to address the flaws of the old NAFTA system.[1]"
    cited_evidence:
      - evidence_id: ev_009
        bibliography_num: 1
        url: "https://www.csis.org/analysis/usmca-review-2026"
        tier: T4
        span: '0-500'
        title: "USMCA Review 2026 - CSIS"
        span_text: |
          USMCA Review 2026 Table of Contents - The Issue - Introduction - The USMCA at Five - President Trump’s Reindustrialization Drive Through Tariffs - Understanding the 2026 Review Clause: Pathways, Risks, and Leverage - Mapping Six Possible Pathways for the USMCA - What Will Be on the Table: Disputes, Demands, and Deal-Breakers - Keeping Sights High: Options to Deepen Cooperation Under the USMCA Available Downloads The Issue The United States–Mexico–Canada Agreement (USMCA), the backbone of North America’s competitiveness, will undergo a formal review starting in July 2026. What was once expected to be a routine assessment aimed at improving implementation is now likely to become a high-stakes negotiation. The Trump administration is poised to seek additional concessions from Mexico and Canada on long-standing trade disputes, while also leveraging the review to address non-trade issues such as migration, drug trafficking, and continental defense. Both neighbors, already in talks with Washington over tariff relief, are approaching the process with caution. While the review may become a platform for the United States to secure short-term wins, it also presents a rare opportunity to modernize the agreement and strengthen North America’s shared competitiveness. How the three nations navigate this moment will shape the region’s economic future for decades. Introduction In 2020, the USMCA replaced the North American Free Trade Agreement (NAFTA), which had governed trade between the th
          
          [...]
          
          n people, accounting for 30 percent of global GDP. Since its ratification, significant progress has been made in expanding trade, investment, and jobs across North America. In 2024, goods and services trade within North America totaled an estimated $1.93 trillion, solidifying Mexico and Canada as the United States’ top trading partners. In July 2026, on the sixth anniversary of the USMCA’s implementation, the three countries will hold a joint review to assess the agreement’s performance and determin
          
          [...]
          
          er NAFTA is its state-to-state dispute settlement system. Under NAFTA, disputes often stalled because one party could block the formation of a panel by refusing to appoint panelists or agree on a roster. The USMCA addresses this flaw through Article 31.8, which creates a standing list of preapproved independent trade experts, ensuring that dispute resolution panels could be formed even when one party is uncooperative. NAFTA’s shortcomings are most evident in the decades-long sugar dispute between th
          
          [...]
          
          um has acknowledged drug consumption as a shared challenge and continues to call for bilateral cooperation. Still, her government has delivered results: Since she took office in October 2024, fentanyl seizures have surged, including a record bust of 1.1 metric tons in December 2025. According to President Sheinbaum, fentanyl trafficking at the U.S.-Mexico border is down 50 percent. In addition, in February 2025, the Mexican government transferred 29 high-level criminal suspects to U.S. custody; in 
          
          [...]
          
          point, not a breaking point, for the future of regional integration. Understanding the 2026 Review Clause: Pathways, Risks, and Leverage The USMCA is designed to last 16 years, expiring on July 1, 2036, unless the parties agree to extend it. Article 34.7 of the agreement requires the United States, Mexico, and Canada to conduct a formal review at the six-year mark. This process requires the three governments, through their Free Trade Commission, to evaluate the agreement’s effectiveness, consider ea
          
          [...]
          
          ears or letting the agreement expire in 2036. Each country may gather input from its stakeholders, including businesses, unions, nongovernmental organizations, legislators, and local authorities involved in or affected by the USMCA. However, Article 34.7 leaves critical gaps and does not explicitly establish how the commission will evaluate or prioritize these proposals, nor does it specify criteria for deciding which suggestions will be considered or dismissed. A
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
