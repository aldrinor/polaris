Independent Tier-1 audit of 7 Q1 AI Sovereignty claims. Output YAML records only.

You are populating Tier-1 audit fields for each claim in the BATCH below.

# Tier-1 schema (per claim)

```yaml
- claim_id: Q1-T1-NNN
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
  - critical = the headline policy-decision number (e.g., $2B Budget-2024 over 5y, 100MW data centre threshold, CAD $700M AI Compute Challenge, US CLOUD Act applicability)
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

# Q1 batch 1: claims 1-7 (re-run with full direct_quote)
schema_version: tier1_v2
claims:
  - claim_id: Q1-T1-001
    section: "Regulatory"
    sentence: "The Canadian Sovereign AI Compute Strategy is a national policy framework designed to address a recognized gap in affordable, domestic computing resources for Canadian AI researchers, businesses, and innovators.[1]"
    cited_evidence:
      - evidence_id: ev_013
        bibliography_num: 1
        url: "https://oecd.ai/en/dashboards/policy-initiatives/canadian-sovereign-ai-compute-strategy"
        tier: T4
        span: '0-500'
        title: "Canadian Sovereign AI Compute Strategy - OECD.AI"
        span_text: |
          Initiative overview The Canadian Sovereign AI Compute Strategy responds to a recognised gap in affordable, domestic computing resources for Canadian AI researchers, businesses and innovators. During a public consultation conducted over the summer of 2024, more than 1,000 stakeholders from research, industry and civil society highlighted the high cost of compute resources and the limited availability of domestic capacity as key barriers. The strategy is guided by the findings of this consultation, published in a What We Heard Report, and is designed to safeguard Canadian data and intellectual property while enabling made-in-Canada AI solutions. The strategy comprises three complementary elements. The first, mobilising private sector investment, allocates up to CAD $700 million through the AI Compute Challenge, which seeks proposals from companies, consortiums and academic-industry partnerships to establish commercial AI data-centre solutions in Canada. Projects must build or expand AI-specific data centre capacity, offer flexible and affordable compute, contribute to anchoring Canadian AI companies, and advance sustainable solutions. The second element, building public supercomputing infrastructure, commits up to CAD $1 billion, including a new state-of-the-art AI supercomputing system through the AI Sovereign Compute Infrastructure Program (SCIP), a smaller secure facility led by Shared Services Canada and the National Research Council for government and industry R&D includin
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q1-T1-002
    section: "Regulatory"
    sentence: "The strategy is informed by a public consultation conducted in the summer of 2024, which engaged more than 1,000 stakeholders from research, industry, and civil society who identified high costs and limited domestic capacity as key barriers.[2][1]"
    cited_evidence:
      - evidence_id: ev_013
        bibliography_num: 1
        url: "https://oecd.ai/en/dashboards/policy-initiatives/canadian-sovereign-ai-compute-strategy"
        tier: T4
        span: '0-500'
        title: "Canadian Sovereign AI Compute Strategy - OECD.AI"
        span_text: |
          Initiative overview The Canadian Sovereign AI Compute Strategy responds to a recognised gap in affordable, domestic computing resources for Canadian AI researchers, businesses and innovators. During a public consultation conducted over the summer of 2024, more than 1,000 stakeholders from research, industry and civil society highlighted the high cost of compute resources and the limited availability of domestic capacity as key barriers. The strategy is guided by the findings of this consultation, published in a What We Heard Report, and is designed to safeguard Canadian data and intellectual property while enabling made-in-Canada AI solutions. The strategy comprises three complementary elements. The first, mobilising private sector investment, allocates up to CAD $700 million through the AI Compute Challenge, which seeks proposals from companies, consortiums and academic-industry partnerships to establish commercial AI data-centre solutions in Canada. Projects must build or expand AI-specific data centre capacity, offer flexible and affordable compute, contribute to anchoring Canadian AI companies, and advance sustainable solutions. The second element, building public supercomputing infrastructure, commits up to CAD $1 billion, including a new state-of-the-art AI supercomputing system through the AI Sovereign Compute Infrastructure Program (SCIP), a smaller secure facility led by Shared Services Canada and the National Research Council for government and industry R&D includin
      - evidence_id: ev_010
        bibliography_num: 2
        url: "https://ised-isde.canada.ca/site/ised/en/canadian-sovereign-ai-compute-strategy"
        tier: T3
        span: '0-500'
        title: "Canadian Sovereign AI Compute Strategy"
        span_text: |
          To strengthen Canada's position as a global leader in artificial intelligence (AI), it is essential for Canadian AI industries and researchers to have access to affordable, cutting‑edge compute infrastructure. By boosting access to powerful computing resources right here in Canada, we can drive innovation, create new opportunities and ensure that Canada stays competitive in the global AI race. What is AI compute? AI compute refers to the computational resources required for AI systems to perform tasks, such as processing data, running algorithms and training machine learning models. In other words, AI compute is the technology that powers AI. More compute power means faster and more accurate results. And that means more innovation, more productivity and more opportunity for Canadian AI companies, researchers and talent. That is why the Government of Canada is committed to building a strong and secure AI compute foundation. Budget 2024 announced $2 billion over five years, starting in 2024–25, to launch new initiatives that will give Canadian researchers and AI companies the tools they need to be competitive globally. Over the summer of 2024, the government launched a public consultation to inform the design and implementation of these two initiatives. We heard from more than 1,000 stakeholders from research, industry and civil society across Canada through in‑person and virtual round table discussions and an online survey. Read the [What We Heard Report](/site/ised/en/what-we
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q1-T1-003
    section: "Regulatory"
    sentence: "This program is part of a historic investment framework, with Budget 2024 announcing $2 billion over five years starting in 2024\u201325 to launch new initiatives for competitive AI compute.[2]"
    cited_evidence:
      - evidence_id: ev_010
        bibliography_num: 2
        url: "https://ised-isde.canada.ca/site/ised/en/canadian-sovereign-ai-compute-strategy"
        tier: T3
        span: '0-500'
        title: "Canadian Sovereign AI Compute Strategy"
        span_text: |
          To strengthen Canada's position as a global leader in artificial intelligence (AI), it is essential for Canadian AI industries and researchers to have access to affordable, cutting‑edge compute infrastructure. By boosting access to powerful computing resources right here in Canada, we can drive innovation, create new opportunities and ensure that Canada stays competitive in the global AI race. What is AI compute? AI compute refers to the computational resources required for AI systems to perform tasks, such as processing data, running algorithms and training machine learning models. In other words, AI compute is the technology that powers AI. More compute power means faster and more accurate results. And that means more innovation, more productivity and more opportunity for Canadian AI companies, researchers and talent. That is why the Government of Canada is committed to building a strong and secure AI compute foundation. Budget 2024 announced $2 billion over five years, starting in 2024–25, to launch new initiatives that will give Canadian researchers and AI companies the tools they need to be competitive globally. Over the summer of 2024, the government launched a public consultation to inform the design and implementation of these two initiatives. We heard from more than 1,000 stakeholders from research, industry and civil society across Canada through in‑person and virtual round table discussions and an online survey. Read the [What We Heard Report](/site/ised/en/what-we
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q1-T1-004
    section: "Regulatory"
    sentence: "A separate federal intake process launched in February 2026 aims to identify and advance sovereign, large-scale AI data centre projects exceeding 100 megawatts (MW) in capacity.[3]"
    cited_evidence:
      - evidence_id: ev_014
        bibliography_num: 3
        url: "https://www.dlapiper.com/en/insights/publications/2026/02/government-of-canada-launches-call-for-proposals-for-large-scale-sovereign-ai-data-centres"
        tier: T4
        span: '0-500'
        title: "Government of Canada launches call for proposals ..."
        span_text: |
          5 February 2026 • 4 minute read Government of Canada launches call for proposals for large scale sovereign AI data centres The Government of Canada has launched a national process to identify and advance large‑scale sovereign AI data centre projects, marking a significant step in expanding the country’s AI infrastructure and strengthening its innovation ecosystem. As artificial intelligence becomes increasingly central to economic growth, the federal government aims to ensure that Canadian researchers, businesses, and institutions have access to the computing capacity needed to remain competitive. This initiative aligns with Budget 2025, which proposes $925.6 million over five years starting in 2025–26 to establish a sovereign, large‑scale public AI computing infrastructure. The investment is intended to expand national AI compute availability and ensure secure, sovereign access for both public‑ and private‑sector research, positioning Canada to compete globally. Through this intake, led by the Minister of Artificial Intelligence and Digital Innovation, the federal government is engaging with industry to identify promising projects, explore potential support mechanisms, and coordinate across jurisdictions to enable the development of large‑scale AI infrastructure. Overview of the initiative Canada has launched a one‑month federal intake to identify and advance “sovereign, large‑scale AI data centres” exceeding 100 megawatts (MW), with selected proponents entering memoranda of
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q1-T1-005
    section: "Regulatory"
    sentence: "This regulatory push for data sovereignty and domestic procurement has drawn international trade attention, with the United States Trade Representative flagging Canada's early interest in a sovereign cloud\u2014which would bar foreign governments from accessing data without consent\u2014as a potential trade irritant in its 2026 report on foreign trade barriers.[4]"
    cited_evidence:
      - evidence_id: ev_004
        bibliography_num: 4
        url: "https://thelogic.co/news/cloud-sovereignty-push-trade-irritant/"
        tier: T4
        span: '0-500'
        title: "U.S. cites Canada's cloud sovereignty push as a trade irritant"
        span_text: |
          OTTAWA — The United States has flagged Canada’s early interest in a sovereign cloud that would bar foreign governments from accessing data without consent as a potential trade irritant. U.S. Trade Representative Jamieson Greer [included](https://ustr.gov/sites/default/files/files/Press/Releases/2026/2026%20NTE%20Report%20_%20Final.pdf) it among several procurement issues in the annual report on foreign trade barriers he submitted Tuesday to U.S. Congress and President Donald Trump. Talking Points As always, Canada’s tightly controlled [dairy market](https://thelogic.co/news/dairy-trade-us-canada-tariffs/) got a mention. So did the Online Streaming Act and the Online News Act, which Greer has [flagged](https://thelogic.co/briefing/what-trump-wants-from-canada-dairy-market-access-digital-services-reform/) as priorities for the coming review of the North American trade pact. The federal government’s [Buy Canadian](https://thelogic.co/news/buy-canadian-policy-lets-foreign-owned-firms-qualify-as-canadian-lightbound-says/) policy for contracts over $25 million is a new one this year, as are moves by some provinces to keep U.S. alcohol [out](https://thelogic.co/news/the-big-read/wine-trade-war-canada-united-states/) of liquor stores. The [long wait](https://thelogic.co/briefing/trump-threatens-to-decertify-and-slap-50-tariff-on-canadian-aircraft/) for regulatory approval of aircraft and a proposed change to the disclosure rules regarding fragrance allergens in cosmetics also debuted
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q1-T1-006
    section: "Regulatory"
    sentence: "The U.S. report also cited Canada's \"Buy Canadian\" policy for contracts over $25 million as a new procurement issue.[4]"
    cited_evidence:
      - evidence_id: ev_004
        bibliography_num: 4
        url: "https://thelogic.co/news/cloud-sovereignty-push-trade-irritant/"
        tier: T4
        span: '0-500'
        title: "U.S. cites Canada's cloud sovereignty push as a trade irritant"
        span_text: |
          OTTAWA — The United States has flagged Canada’s early interest in a sovereign cloud that would bar foreign governments from accessing data without consent as a potential trade irritant. U.S. Trade Representative Jamieson Greer [included](https://ustr.gov/sites/default/files/files/Press/Releases/2026/2026%20NTE%20Report%20_%20Final.pdf) it among several procurement issues in the annual report on foreign trade barriers he submitted Tuesday to U.S. Congress and President Donald Trump. Talking Points As always, Canada’s tightly controlled [dairy market](https://thelogic.co/news/dairy-trade-us-canada-tariffs/) got a mention. So did the Online Streaming Act and the Online News Act, which Greer has [flagged](https://thelogic.co/briefing/what-trump-wants-from-canada-dairy-market-access-digital-services-reform/) as priorities for the coming review of the North American trade pact. The federal government’s [Buy Canadian](https://thelogic.co/news/buy-canadian-policy-lets-foreign-owned-firms-qualify-as-canadian-lightbound-says/) policy for contracts over $25 million is a new one this year, as are moves by some provinces to keep U.S. alcohol [out](https://thelogic.co/news/the-big-read/wine-trade-war-canada-united-states/) of liquor stores. The [long wait](https://thelogic.co/briefing/trump-threatens-to-decertify-and-slap-50-tariff-on-canadian-aircraft/) for regulatory approval of aircraft and a proposed change to the disclosure rules regarding fragrance allergens in cosmetics also debuted
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q1-T1-007
    section: "Regulatory"
    sentence: "Budget 2025 proposed $925.6 million over five years starting in 2025\u201326 to establish a sovereign, large-scale public AI computing infrastructure.[3]"
    cited_evidence:
      - evidence_id: ev_014
        bibliography_num: 3
        url: "https://www.dlapiper.com/en/insights/publications/2026/02/government-of-canada-launches-call-for-proposals-for-large-scale-sovereign-ai-data-centres"
        tier: T4
        span: '0-500'
        title: "Government of Canada launches call for proposals ..."
        span_text: |
          5 February 2026 • 4 minute read Government of Canada launches call for proposals for large scale sovereign AI data centres The Government of Canada has launched a national process to identify and advance large‑scale sovereign AI data centre projects, marking a significant step in expanding the country’s AI infrastructure and strengthening its innovation ecosystem. As artificial intelligence becomes increasingly central to economic growth, the federal government aims to ensure that Canadian researchers, businesses, and institutions have access to the computing capacity needed to remain competitive. This initiative aligns with Budget 2025, which proposes $925.6 million over five years starting in 2025–26 to establish a sovereign, large‑scale public AI computing infrastructure. The investment is intended to expand national AI compute availability and ensure secure, sovereign access for both public‑ and private‑sector research, positioning Canada to compete globally. Through this intake, led by the Minister of Artificial Intelligence and Digital Innovation, the federal government is engaging with industry to identify promising projects, explore potential support mechanisms, and coordinate across jurisdictions to enable the development of large‑scale AI infrastructure. Overview of the initiative Canada has launched a one‑month federal intake to identify and advance “sovereign, large‑scale AI data centres” exceeding 100 megawatts (MW), with selected proponents entering memoranda of
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
