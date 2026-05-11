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

# Q4 batch 5: claims 29-35 (re-run with full direct_quote)
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
          [Home](https://cdhowe.org/) / [Publications](https://cdhowe.org/publication/) / [Research](https://cdhowe.org/publication-type/public-policy-research/) / Housing Policy for a Growing Canada - [Media Releases](https://cdhowe.org/media-releases/) - Research - | Housing Policy for a Growing Canada Summary: | Citation | . 2025. Housing Policy for a Growing Canada. ###. Toronto: C.D. Howe Institute. | | Page Title: | Housing Policy for a Growing Canada – C.D. Howe Institute | | Article Title: | Housing Policy for a Growing Canada | | URL: | https://cdhowe.org/publication/housing-policy-for-a-growing-canada/ | | Published Date: | February 4, 2025 | | Accessed Date: | May 11, 2026 | Outline Outline Related Topics For all media inquiries, including requests for reports or interviews: Introduction and Overview Canada’s housing sector faces unprecedented challenges, with skyrocketing prices, acute affordability crises, and a growing mismatch between housing supply and population needs. Major urban centers like Toronto and Vancouver have been particularly hard-hit, with housing costs outpacing income growth. This has pushed homeownership beyond the reach of many middle-class Canadians and created significant barriers for first-time buyers and young families. On November 14, 2024, against this complex backdrop, the C.D. Howe Institute – with the support of sponsors CREA-ACI, FRPO, and Fitzrovia – convened a conference on “Housing Policy for a Growing Canada.” The sessions brought togethe
          
          [...]
          
          f new projects – a “math equation” that currently doesn’t work for developers. The speaker detailed several compounding factors that have created a perfect storm for stagnation in housing supply. On one hand, rents have dropped by approximately 8 to 8.5 percent in many areas, reducing expected revenues. The speaker mentioned that while construction costs have stabilized, significant back-end expenses, such as mechanical systems, continue to climb. Combined with high interest rates and squeezed prof
          
          [...]
          
          ing, like California’s Accessory Dwelling Units (ADUs),[10](javascript:void(0))An ADU is accessory to a primary residence with complete independent living facilities that does not require new land or costly infrastructure. In Government Code Section 65852.150, the California Legislature found and declared that, among other things, allowing ADUs in zones that allow single-family and multifamily uses provides additional rental housing and is an essential component in addressing California’s housing needs. 
          
          [...]
          
          sing Canada’s housing challenges called the Blueprint for More and Better Housing. The task force includes representatives from developers, former government officials, academics, and industry professionals. It is focused on the urgent need to build 5.8 million homes within a short period. A major concern was that this large-scale construction could add 100 megatons of greenhouse gas emissions, further burdening industries already striving to lower their environmental impact. The speaker emphasized
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
          OTTAWA, ON, April 15, 2026 /CNW/ - New analysis from Canada Mortgage and Housing Corporation (CMHC) explores how housing supply and housing demand interventions need to work together to address the housing affordability crisis. Demand-side interventions, which directly support households in attaining a home, are often favoured because of their more immediate impact. The results can be measured more quickly than the creation of new supply, which take years to deliver. It is a delicate balance, since the basic rule of supply and demand dictates that if demand increases without increased supply, prices will rise. In his latest article, CMHC's Chief Economist, Mathieu Laberge highlights new modeling analyzing the tug-of-war between demand-side and supply-side housing interventions. Quote: "Helping more Canadians access homeownership is an important goal, but how we do it matters", said Mathieu Laberge, Chief Economist, CMHC. "Without careful targeting and a matching increase in housing supply, demand-side measures can end up increasing costs for a broader group of households." Read the full article on [CMHC's website](https://edge.prnewswire.com/c/link/?t=0&l=en&o=4664504-1&h=329659968&u=https%3A%2F%2Fwww.cmhc-schl.gc.ca%2Fen%2Fobserver%2F2026%2Fwhy-demand-side-interventions-need-to-be-targeted-and-offset-with-supply&a=CMHC%27s+website) Related links: - [Why Canada's housing supply gap exists and how to fix it | CMHC](https://edge.prnewswire.com/c/link/?t=0&l=en&o=4664504-1&h=211
      - evidence_id: ev_019
        bibliography_num: 8
        url: "https://finance.yahoo.com/news/why-demand-side-interventions-paired-140000953.html"
        tier: T6
        span: '0-500'
        title: "Why demand-side interventions need to be paired with housing supply"
        span_text: |
          OTTAWA, ON, April 15, 2026 /CNW/ - New analysis from Canada Mortgage and Housing Corporation (CMHC) explores how housing supply and housing demand interventions need to work together to address the housing affordability crisis. Demand-side interventions, which directly support households in attaining a home, are often favoured because of their more immediate impact. The results can be measured more quickly than the creation of new supply, which take years to deliver. It is a delicate balance, since the basic rule of supply and demand dictates that if demand increases without increased supply, prices will rise. In his latest article, CMHC's Chief Economist, Mathieu Laberge highlights new modeling analyzing the tug-of-war between demand-side and supply-side housing interventions. Quote: "Helping more Canadians access homeownership is an important goal, but how we do it matters", said Mathieu Laberge, Chief Economist, CMHC. "Without careful targeting and a matching increase in housing supply, demand-side measures can end up increasing costs for a broader group of households." Read the full article on [CMHC's website](https://edge.prnewswire.com/c/link/?t=0&l=en&o=4664504-1&h=329659968&u=https%3A%2F%2Fwww.cmhc-schl.gc.ca%2Fen%2Fobserver%2F2026%2Fwhy-demand-side-interventions-need-to-be-targeted-and-offset-with-supply&a=CMHC%27s+website) Related links: - [Why Canada's housing supply gap exists and how to fix it | CMHC](https://edge.prnewswire.com/c/link/?t=0&l=en&o=4664504-1&h=211
      - evidence_id: ev_020
        bibliography_num: 9
        url: "https://www.cmhc-schl.gc.ca/observer/2026/why-demand-side-interventions-need-to-be-targeted-and-offset-with-supply"
        tier: T4
        span: '0-500'
        title: "Targeted demand interventions need supply for housing market ..."
        span_text: |
          When addressing a housing affordability crisis, there is always a tug-of-war between demand- and supply-side housing interventions. Demand-side interventions, which directly help households secure housing, are often favoured because of their more immediate impact. The results are easier to see and measure compared to building new homes, which take years to deliver. A basic principle of supply and demand shows that if demand increases without proportionate supply, prices will increase. New modeling by CMHC shows that this dynamic occurs with housing demand-side interventions. Over time, they may worsen housing affordability, instead of improving access to housing. One key learning from this new modeling is that while our ambitions to help Canadians find the right housing must remain a priority, the means to achieve them must be balanced: Demand-side supports must be targeted and accompanied by sufficient supply. How can direct support to aspiring homebuyers reduce affordability? Well-intentioned demand-side interventions can make housing less affordable due to pent-up demand (what economists call induced demand). High housing prices can delay household formation — we all know of young people staying longer at their parents’ home or friends extending apartment-sharing arrangements because they can’t afford housing on their own. In a more favourable housing market, these people would form their own households, but with high housing prices, they simply can’t afford to. This is ca
          
          [...]
          
          ces, they simply can’t afford to. This is called household suppression — the basis of pent-up demand. This is a well-documented phenomenon in academic literature and is also [considered by other Canadian housing](https://institute.smartprosperity.ca/1.5MillionMoreHomes) researchers. A demand-side intervention would try to correct this issue by either increasing household income or reducing housing costs, enabling people to afford housing of their own. Naturally, these people would start looking for
          
          [...]
          
          e over time as additional demand from new homebuyers would put upward pressure on prices. CMHC’s modeling shows the increase in demand from the new homeowners benefitting the intervention means every other homebuyer that doesn't qualify would face a 0.6% increase in house prices. The estimated economic cost of this intervention would be $2.7 billion to $4.3 billion in direct spending for the intervention itself and $1.6 billion in unintended increased costs for all homebuyers that are not supported by the new intervention.
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
          When addressing a housing affordability crisis, there is always a tug-of-war between demand- and supply-side housing interventions. Demand-side interventions, which directly help households secure housing, are often favoured because of their more immediate impact. The results are easier to see and measure compared to building new homes, which take years to deliver. A basic principle of supply and demand shows that if demand increases without proportionate supply, prices will increase. New modeling by CMHC shows that this dynamic occurs with housing demand-side interventions. Over time, they may worsen housing affordability, instead of improving access to housing. One key learning from this new modeling is that while our ambitions to help Canadians find the right housing must remain a priority, the means to achieve them must be balanced: Demand-side supports must be targeted and accompanied by sufficient supply. How can direct support to aspiring homebuyers reduce affordability? Well-intentioned demand-side interventions can make housing less affordable due to pent-up demand (what economists call induced demand). High housing prices can delay household formation — we all know of young people staying longer at their parents’ home or friends extending apartment-sharing arrangements because they can’t afford housing on their own. In a more favourable housing market, these people would form their own households, but with high housing prices, they simply can’t afford to. This is ca
          
          [...]
          
          ces, they simply can’t afford to. This is called household suppression — the basis of pent-up demand. This is a well-documented phenomenon in academic literature and is also [considered by other Canadian housing](https://institute.smartprosperity.ca/1.5MillionMoreHomes) researchers. A demand-side intervention would try to correct this issue by either increasing household income or reducing housing costs, enabling people to afford housing of their own. Naturally, these people would start looking for
          
          [...]
          
          e over time as additional demand from new homebuyers would put upward pressure on prices. CMHC’s modeling shows the increase in demand from the new homeowners benefitting the intervention means every other homebuyer that doesn't qualify would face a 0.6% increase in house prices. The estimated economic cost of this intervention would be $2.7 billion to $4.3 billion in direct spending for the intervention itself and $1.6 billion in unintended increased costs for all homebuyers that are not supported by the new intervention.
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
          [Home](https://cdhowe.org/) / [Publications](https://cdhowe.org/publication/) / [Research](https://cdhowe.org/publication-type/public-policy-research/) / Housing Policy for a Growing Canada - [Media Releases](https://cdhowe.org/media-releases/) - Research - | Housing Policy for a Growing Canada Summary: | Citation | . 2025. Housing Policy for a Growing Canada. ###. Toronto: C.D. Howe Institute. | | Page Title: | Housing Policy for a Growing Canada – C.D. Howe Institute | | Article Title: | Housing Policy for a Growing Canada | | URL: | https://cdhowe.org/publication/housing-policy-for-a-growing-canada/ | | Published Date: | February 4, 2025 | | Accessed Date: | May 11, 2026 | Outline Outline Related Topics For all media inquiries, including requests for reports or interviews: Introduction and Overview Canada’s housing sector faces unprecedented challenges, with skyrocketing prices, acute affordability crises, and a growing mismatch between housing supply and population needs. Major urban centers like Toronto and Vancouver have been particularly hard-hit, with housing costs outpacing income growth. This has pushed homeownership beyond the reach of many middle-class Canadians and created significant barriers for first-time buyers and young families. On November 14, 2024, against this complex backdrop, the C.D. Howe Institute – with the support of sponsors CREA-ACI, FRPO, and Fitzrovia – convened a conference on “Housing Policy for a Growing Canada.” The sessions brought togethe
          
          [...]
          
          f new projects – a “math equation” that currently doesn’t work for developers. The speaker detailed several compounding factors that have created a perfect storm for stagnation in housing supply. On one hand, rents have dropped by approximately 8 to 8.5 percent in many areas, reducing expected revenues. The speaker mentioned that while construction costs have stabilized, significant back-end expenses, such as mechanical systems, continue to climb. Combined with high interest rates and squeezed prof
          
          [...]
          
          ing, like California’s Accessory Dwelling Units (ADUs),[10](javascript:void(0))An ADU is accessory to a primary residence with complete independent living facilities that does not require new land or costly infrastructure. In Government Code Section 65852.150, the California Legislature found and declared that, among other things, allowing ADUs in zones that allow single-family and multifamily uses provides additional rental housing and is an essential component in addressing California’s housing needs. 
          
          [...]
          
          sing Canada’s housing challenges called the Blueprint for More and Better Housing. The task force includes representatives from developers, former government officials, academics, and industry professionals. It is focused on the urgent need to build 5.8 million homes within a short period. A major concern was that this large-scale construction could add 100 megatons of greenhouse gas emissions, further burdening industries already striving to lower their environmental impact. The speaker emphasized
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
          [Home](https://cdhowe.org/) / [Publications](https://cdhowe.org/publication/) / [Research](https://cdhowe.org/publication-type/public-policy-research/) / Housing Policy for a Growing Canada - [Media Releases](https://cdhowe.org/media-releases/) - Research - | Housing Policy for a Growing Canada Summary: | Citation | . 2025. Housing Policy for a Growing Canada. ###. Toronto: C.D. Howe Institute. | | Page Title: | Housing Policy for a Growing Canada – C.D. Howe Institute | | Article Title: | Housing Policy for a Growing Canada | | URL: | https://cdhowe.org/publication/housing-policy-for-a-growing-canada/ | | Published Date: | February 4, 2025 | | Accessed Date: | May 11, 2026 | Outline Outline Related Topics For all media inquiries, including requests for reports or interviews: Introduction and Overview Canada’s housing sector faces unprecedented challenges, with skyrocketing prices, acute affordability crises, and a growing mismatch between housing supply and population needs. Major urban centers like Toronto and Vancouver have been particularly hard-hit, with housing costs outpacing income growth. This has pushed homeownership beyond the reach of many middle-class Canadians and created significant barriers for first-time buyers and young families. On November 14, 2024, against this complex backdrop, the C.D. Howe Institute – with the support of sponsors CREA-ACI, FRPO, and Fitzrovia – convened a conference on “Housing Policy for a Growing Canada.” The sessions brought togethe
          
          [...]
          
          f new projects – a “math equation” that currently doesn’t work for developers. The speaker detailed several compounding factors that have created a perfect storm for stagnation in housing supply. On one hand, rents have dropped by approximately 8 to 8.5 percent in many areas, reducing expected revenues. The speaker mentioned that while construction costs have stabilized, significant back-end expenses, such as mechanical systems, continue to climb. Combined with high interest rates and squeezed prof
          
          [...]
          
          ing, like California’s Accessory Dwelling Units (ADUs),[10](javascript:void(0))An ADU is accessory to a primary residence with complete independent living facilities that does not require new land or costly infrastructure. In Government Code Section 65852.150, the California Legislature found and declared that, among other things, allowing ADUs in zones that allow single-family and multifamily uses provides additional rental housing and is an essential component in addressing California’s housing needs. 
          
          [...]
          
          sing Canada’s housing challenges called the Blueprint for More and Better Housing. The task force includes representatives from developers, former government officials, academics, and industry professionals. It is focused on the urgent need to build 5.8 million homes within a short period. A major concern was that this large-scale construction could add 100 megatons of greenhouse gas emissions, further burdening industries already striving to lower their environmental impact. The speaker emphasized
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
          When addressing a housing affordability crisis, there is always a tug-of-war between demand- and supply-side housing interventions. Demand-side interventions, which directly help households secure housing, are often favoured because of their more immediate impact. The results are easier to see and measure compared to building new homes, which take years to deliver. A basic principle of supply and demand shows that if demand increases without proportionate supply, prices will increase. New modeling by CMHC shows that this dynamic occurs with housing demand-side interventions. Over time, they may worsen housing affordability, instead of improving access to housing. One key learning from this new modeling is that while our ambitions to help Canadians find the right housing must remain a priority, the means to achieve them must be balanced: Demand-side supports must be targeted and accompanied by sufficient supply. How can direct support to aspiring homebuyers reduce affordability? Well-intentioned demand-side interventions can make housing less affordable due to pent-up demand (what economists call induced demand). High housing prices can delay household formation — we all know of young people staying longer at their parents’ home or friends extending apartment-sharing arrangements because they can’t afford housing on their own. In a more favourable housing market, these people would form their own households, but with high housing prices, they simply can’t afford to. This is ca
          
          [...]
          
          ces, they simply can’t afford to. This is called household suppression — the basis of pent-up demand. This is a well-documented phenomenon in academic literature and is also [considered by other Canadian housing](https://institute.smartprosperity.ca/1.5MillionMoreHomes) researchers. A demand-side intervention would try to correct this issue by either increasing household income or reducing housing costs, enabling people to afford housing of their own. Naturally, these people would start looking for
          
          [...]
          
          e over time as additional demand from new homebuyers would put upward pressure on prices. CMHC’s modeling shows the increase in demand from the new homeowners benefitting the intervention means every other homebuyer that doesn't qualify would face a 0.6% increase in house prices. The estimated economic cost of this intervention would be $2.7 billion to $4.3 billion in direct spending for the intervention itself and $1.6 billion in unintended increased costs for all homebuyers that are not supported by the new intervention.
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
          When addressing a housing affordability crisis, there is always a tug-of-war between demand- and supply-side housing interventions. Demand-side interventions, which directly help households secure housing, are often favoured because of their more immediate impact. The results are easier to see and measure compared to building new homes, which take years to deliver. A basic principle of supply and demand shows that if demand increases without proportionate supply, prices will increase. New modeling by CMHC shows that this dynamic occurs with housing demand-side interventions. Over time, they may worsen housing affordability, instead of improving access to housing. One key learning from this new modeling is that while our ambitions to help Canadians find the right housing must remain a priority, the means to achieve them must be balanced: Demand-side supports must be targeted and accompanied by sufficient supply. How can direct support to aspiring homebuyers reduce affordability? Well-intentioned demand-side interventions can make housing less affordable due to pent-up demand (what economists call induced demand). High housing prices can delay household formation — we all know of young people staying longer at their parents’ home or friends extending apartment-sharing arrangements because they can’t afford housing on their own. In a more favourable housing market, these people would form their own households, but with high housing prices, they simply can’t afford to. This is ca
          
          [...]
          
          ces, they simply can’t afford to. This is called household suppression — the basis of pent-up demand. This is a well-documented phenomenon in academic literature and is also [considered by other Canadian housing](https://institute.smartprosperity.ca/1.5MillionMoreHomes) researchers. A demand-side intervention would try to correct this issue by either increasing household income or reducing housing costs, enabling people to afford housing of their own. Naturally, these people would start looking for
          
          [...]
          
          e over time as additional demand from new homebuyers would put upward pressure on prices. CMHC’s modeling shows the increase in demand from the new homeowners benefitting the intervention means every other homebuyer that doesn't qualify would face a 0.6% increase in house prices. The estimated economic cost of this intervention would be $2.7 billion to $4.3 billion in direct spending for the intervention itself and $1.6 billion in unintended increased costs for all homebuyers that are not supported by the new intervention.
      - evidence_id: ev_003
        bibliography_num: 15
        url: "https://www.cmhc-schl.gc.ca/observer/2026/why-demand-side-interventions-need-to-be-targeted-and-offset-with-supply"
        tier: T4
        span: '0-500'
        title: "Targeted demand interventions need supply for housing market ..."
        span_text: |
          Title: Good intentions gone rogue: Balancing housing demand & supply URL Source: https://www.cmhc-schl.gc.ca/observer/2026/why-demand-side-interventions-need-to-be-targeted-and-offset-with-supply Markdown Content: # Targeted demand interventions need supply for housing market affordability | CMHC (https://www.cmhc-schl.gc.ca/observer/2026/why-demand-side-interventions-need-to-be-targeted-and-offset-with-supply#maincontent) [![Image 2: CMHC Home](https://assets.cmhc-schl.gc.ca/sites/cmhc/shared/imgs/chevron-en.png?rev=19e0635b-89b7-466b-a1b9-5255bd257bd5&h=142&iar=0&w=300)Canada Mortgage and Housing Corporation](https://www.cmhc-schl.gc.ca/en) * [Sign In](https://www.cmhc-schl.gc.ca/api/sitecore/B2CAuthentication/SignIn) or [Register](https://www.cmhc-schl.gc.ca/cmhc-registration) * [Français](https://www.cmhc-schl.gc.ca/observateur-logement/2026/pourquoi-les-mesures-axees-sur-la-demande-doivent-etre-ciblees-et-saccompagner-dune-hausse-de-loffre) * [![Image 3](https://assets.cmhc-schl.gc.ca/sf/project/cmhc/home/hamburger.png?rev=209c76e3-4bb0-457a-9f8f-4452da7a80f9&h=15&iar=0&w=19) MENU](https://www.cmhc-schl.gc.ca/observer/2026/why-demand-side-interventions-need-to-be-targeted-and-offset-with-supply) [](https://www.cmhc-schl.gc.ca/observer/2026/why-demand-side-interventions-need-to-be-targeted-and-offset-with-supply) [![Image 4](https://assets.cmhc-schl.gc.ca/sf/project/cmhc/home/hamburger.png?rev=209c76e3-4bb0-457a-9f8f-4452da7a80f9&h=15&iar=0&w=19)MENU](https://www.cmhc-sch
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
