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

# Q2 batch 1: claims 1-7 (re-run with full direct_quote)
schema_version: tier1_v2
claims:
  - claim_id: Q2-T1-001
    section: "Regulatory"
    sentence: "The formal review process for the Canada-United States-Mexico Agreement (CUSMA) is mandated by Article 34.7, which requires the three parties to conduct a joint review at the six-year mark following the agreement's entry into force on July 1, 2020.[1][2]"
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
      - evidence_id: ev_011
        bibliography_num: 2
        url: "https://www.fasken.com/en/knowledge/2025/10/2026-cusma-review-consultation"
        tier: UNKNOWN
        span: '0-500'
        title: "2026 CUSMA Review Consultation | Knowledge - Fasken"
        span_text: |
          In advance of the July 2026 joint review of the Canada-United States-Mexico Agreement (CUSMA) that will be held between Canada, Mexico, and the United States, Canada has opened formal public consultations on the operation of the CUSMA, providing an important opportunity for Canadians to help shape Canada’s negotiating positions. Given the instability in North American free trade under the Trump 2.0 Administration, the joint review has assumed central importance as a means for Canada to restore certainty to its key trade relationships, thus making the consultations all the more critical for Canadian industry. Below, we provide an overview of the joint review and consultation processes. Overview of the CUSMA Joint Review When the CUSMA entered into force on July 1, 2020, it contained a new article (34.7) which included both a “sunset” clause—providing for the termination of the agreement 16 years after its entry into force unless it is otherwise renewed—as well as a provision mandating a “joint review” of the agreement by the parties in July 2026. The stated purpose of the joint review is to enable parties to consider the operation of the agreement, review any recommendations for action submitted by a party, and decide on any actions. During the joint review, parties will be required to confirm whether they wish to extend the CUSMA by an additional 16 years. If parties unanimously agree, then the agreement will be extended until 2052 and joint reviews will take place every six
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q2-T1-002
    section: "Regulatory"
    sentence: "This review, commencing in July 2026, is conducted through the Free Trade Commission to evaluate the agreement\u2019s effectiveness and consider recommendations for action.[1][2]"
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
      - evidence_id: ev_011
        bibliography_num: 2
        url: "https://www.fasken.com/en/knowledge/2025/10/2026-cusma-review-consultation"
        tier: UNKNOWN
        span: '0-500'
        title: "2026 CUSMA Review Consultation | Knowledge - Fasken"
        span_text: |
          In advance of the July 2026 joint review of the Canada-United States-Mexico Agreement (CUSMA) that will be held between Canada, Mexico, and the United States, Canada has opened formal public consultations on the operation of the CUSMA, providing an important opportunity for Canadians to help shape Canada’s negotiating positions. Given the instability in North American free trade under the Trump 2.0 Administration, the joint review has assumed central importance as a means for Canada to restore certainty to its key trade relationships, thus making the consultations all the more critical for Canadian industry. Below, we provide an overview of the joint review and consultation processes. Overview of the CUSMA Joint Review When the CUSMA entered into force on July 1, 2020, it contained a new article (34.7) which included both a “sunset” clause—providing for the termination of the agreement 16 years after its entry into force unless it is otherwise renewed—as well as a provision mandating a “joint review” of the agreement by the parties in July 2026. The stated purpose of the joint review is to enable parties to consider the operation of the agreement, review any recommendations for action submitted by a party, and decide on any actions. During the joint review, parties will be required to confirm whether they wish to extend the CUSMA by an additional 16 years. If parties unanimously agree, then the agreement will be extended until 2052 and joint reviews will take place every six
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q2-T1-003
    section: "Regulatory"
    sentence: "The stated purpose is to enable parties to consider the operation of the agreement, review any recommendations for action submitted by a party, and decide on any actions.[2]"
    cited_evidence:
      - evidence_id: ev_011
        bibliography_num: 2
        url: "https://www.fasken.com/en/knowledge/2025/10/2026-cusma-review-consultation"
        tier: UNKNOWN
        span: '0-500'
        title: "2026 CUSMA Review Consultation | Knowledge - Fasken"
        span_text: |
          In advance of the July 2026 joint review of the Canada-United States-Mexico Agreement (CUSMA) that will be held between Canada, Mexico, and the United States, Canada has opened formal public consultations on the operation of the CUSMA, providing an important opportunity for Canadians to help shape Canada’s negotiating positions. Given the instability in North American free trade under the Trump 2.0 Administration, the joint review has assumed central importance as a means for Canada to restore certainty to its key trade relationships, thus making the consultations all the more critical for Canadian industry. Below, we provide an overview of the joint review and consultation processes. Overview of the CUSMA Joint Review When the CUSMA entered into force on July 1, 2020, it contained a new article (34.7) which included both a “sunset” clause—providing for the termination of the agreement 16 years after its entry into force unless it is otherwise renewed—as well as a provision mandating a “joint review” of the agreement by the parties in July 2026. The stated purpose of the joint review is to enable parties to consider the operation of the agreement, review any recommendations for action submitted by a party, and decide on any actions. During the joint review, parties will be required to confirm whether they wish to extend the CUSMA by an additional 16 years. If parties unanimously agree, then the agreement will be extended until 2052 and joint reviews will take place every six
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q2-T1-004
    section: "Regulatory"
    sentence: "A critical outcome of this review is the requirement for each party to confirm whether they wish to extend CUSMA for a new 16-year term; unanimous agreement is required for an extension, otherwise the agreement is set to terminate on July 1, 2036.[1][3]"
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
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q2-T1-005
    section: "Regulatory"
    sentence: "The legal framework leaves critical procedural gaps, as Article 34.7 does not explicitly establish how the commission will evaluate or prioritize proposals from stakeholders, nor does it specify criteria for deciding which suggestions will be considered or dismissed.[1]"
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

  - claim_id: Q2-T1-006
    section: "Regulatory"
    sentence: "In advance of the joint review, Canada has opened formal public consultations to gather input from stakeholders, including businesses, unions, and provincial governments, to help shape its negotiating positions.[2][4]"
    cited_evidence:
      - evidence_id: ev_011
        bibliography_num: 2
        url: "https://www.fasken.com/en/knowledge/2025/10/2026-cusma-review-consultation"
        tier: UNKNOWN
        span: '0-500'
        title: "2026 CUSMA Review Consultation | Knowledge - Fasken"
        span_text: |
          In advance of the July 2026 joint review of the Canada-United States-Mexico Agreement (CUSMA) that will be held between Canada, Mexico, and the United States, Canada has opened formal public consultations on the operation of the CUSMA, providing an important opportunity for Canadians to help shape Canada’s negotiating positions. Given the instability in North American free trade under the Trump 2.0 Administration, the joint review has assumed central importance as a means for Canada to restore certainty to its key trade relationships, thus making the consultations all the more critical for Canadian industry. Below, we provide an overview of the joint review and consultation processes. Overview of the CUSMA Joint Review When the CUSMA entered into force on July 1, 2020, it contained a new article (34.7) which included both a “sunset” clause—providing for the termination of the agreement 16 years after its entry into force unless it is otherwise renewed—as well as a provision mandating a “joint review” of the agreement by the parties in July 2026. The stated purpose of the joint review is to enable parties to consider the operation of the agreement, review any recommendations for action submitted by a party, and decide on any actions. During the joint review, parties will be required to confirm whether they wish to extend the CUSMA by an additional 16 years. If parties unanimously agree, then the agreement will be extended until 2052 and joint reviews will take place every six
      - evidence_id: ev_012
        bibliography_num: 4
        url: "https://www.blg.com/en/insights/2026/03/2026-cusma-review-enhancing-trade-negotiation-transparency"
        tier: UNKNOWN
        span: '0-500'
        title: "2026 CUSMA review: Enhancing trade negotiation transparency - BLG"
        span_text: |
          Trade negotiations are in the air, everywhere you look around. They are launched, paused, restarted and concluded. Agreements are reached, then rescinded, ignored or revivified. This past year, the public airwaves have featured more mention of tariffs and negotiations and trade deals than the last thirty years combined. Not since 1988, the year when an entire election was fought over free trade with the United States, has “trade” been a headline concern, and in any event, never for so long. Yes, an election was fought over trade relations with the United States four decades ago. Trade and economic management are at the heart of democratic governance; democratic accountability requires transparency. And yet, trade negotiations, diplomatic and commercial exercises rolled into one, are steeped in discretion. In two sentences lies the conundrum at the heart of trade policy in democratic states. The higher the stakes, the more complex the conundrum. And the stakes have never been higher. The four stages of gri-, uh, negotiations But why a “conundrum”? Broadly speaking, trade negotiations comprise four distinct phases: - Planning and preparation, within the government but also including domestic consultation with stakeholders such as provincial governments, companies engaged in trade, industry associations, civil society groups, and unions. - Negotiations between two sovereign states. - Conclusion, parliamentary review, and ratification. - Implementation – usually through an act of
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q2-T1-007
    section: "Regulatory"
    sentence: "Importantly, Article 34.7 clarifies that the agreement will continue for a further 10 years after July 1 regardless of the review's immediate outcome.[3]"
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
