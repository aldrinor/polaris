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

# Q4 batch 7: claims 43-49 (re-run with full direct_quote)
schema_version: tier1_v2
claims:
  - claim_id: Q4-T1-043
    section: "Long-term Outcomes"
    sentence: "Demographic shifts compound these supply challenges, as average U.S. household size has fallen 23.7% since 1965, from 3.37 to 2.57 persons per household, structurally increasing the number of housing units needed for a given population.[5]"
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
          To understand housing supply, we start with building permits—the first step in the construction pipeline that also captures the optimism of real estate developers and households about the future. Looking at permits adjusted for population growth provides a clearer picture of whether construction is keeping pace with a growing nation. (See the first figure.)
          As the figure shows, there are several distinctive periods:
          - The 1970s peak: Permit activity peaked in 1972 at 10.6 permits per 1,000 people. This was no accident—the baby boom generation was entering prime household-formation age, the interstate highway system had opened vast suburban lands for development, and federal policies—from Federal Housing Administration loan guarantees to mortgage interest deductions—actively encouraged homeownership. This confluence of demographic pressure, available land and policy incentives created the high-water mark of postwar housing construction.
          - The 1980s to the 2000s, from volat
          
          [...]
          
          h inflation and interest rates is reflected in the volatility of permits, until the mid-1990s that started a decade and a half of stable growth.
          - The 2008 collapse: The housing crisis triggered a dramatic decline in permits. Total permits fell from 7.3 per 1,000 in 2005 to just 1.9 per 1,000 in 2009—a 74% decline and the lowest level on record since data collection began in 1960.
          - The incomplete recovery: Despite over a decade of recovery, total permits per capita in 2024 stand at 4.3 per 1,000—still 35% below the 1960-2000 average of 6.6 permits per 1,000. The U.S. is building less housing per person than at almost any point in the postwar era.
          Why Has Housing Construction Stayed Low?
          Several factors constrain today’s housing supply:
          - Labor shortages: The construction workforce nev
          
          [...]
          
          Developable land near job centers has become scarcer and more expensive, pushing construction to outlying areas.
          The Multifamily Shift
          One notable trend is the growing share of multifamily construction (5+ units). Multifamily permits have risen from 0.4 per 1,000 in 2011 to 1.3 per 1,000 in 2024, partially offsetting weak single-family activity. Single-family permits remain at 2.9 per 1,000—well below the historical average of 4.1.
          From Permits to Completions: The “Leaky Pipe” of Supply
          A building permit is a statement of intent, not a finished home. By analyzing the growing divergence between permits issued and final completions, we can identify the specific structural bottl
          
          [...]
          
           from flowing to completion.
          The second figure reveals three hurdles to finishing construction:
          - The completion lag: Permits consistently lead completions by several months to a year, reflecting the time required to build. In 2024, permits stood at 4.3 per 1,000 people while completions were 4.8 per 1,000 people—the gap has narrowed as the postpandemic construction pipeline works through.
          - Historical patterns: At the 1972 peak, permits reached 10.6 per 1,000 while completions hit 9.5 per 1,000 the following year. During the 2008 crisis, both series collapsed together, with completions falling to just 2.1 per 1,000 by 2010.
          - Postpandemic divergence: The COVID-19 pandemic period shows notable dynamics—permits surged to 5.2 per 1,000 in 2021 as demand spiked, but completions lagged as builders faced unprecedented supply chain disruptions and labor shortages.
          Housing Stock and Household Size
          Total housing inventory must be measured against the evolving American househol
          
          [...]
          
          2 units per 1,000 people in 1965 to 386 in 1980, 415 in 2000, and 432 in 2024. This represents a 30% increase since 1965—roughly matching the decline in household size.
          - Declining household size: Average household size has fallen dramatically: from 3.37 persons per household in 1965 to 2.81 in 1980, 2.65 in 2000, and 2.57 in 2024. This means family size has declined by nearly a quarter (23.7%) since 1965; as a result, far more housing units are needed to house the same population.
          So, on this back-of-the-envelope calculation, the U.S. doesn’t look obviously “overbuilt” at the national level: Units per person increased by roughly the sam
          
          [...]
          
          ing absorbed quickly, often correlating with rising prices and rents.
          These vacancy rates have shifted dramatically in the past two decades.
          - Postcrisis spike: Vacancy rates spiked after 2008 as foreclosures flooded the market. Rental vacancies hit 10.6% in 2009, while homeowner vacancies reached 2.9% in 2008—both elevated as distressed properties sat empty.
          - The current tightness: Both vacancy rates have fallen to near-historic lows. Rental vacancy stood at 6.8% in 2024—down from the 2009 peak and below the 1960s levels of 7% to 8%. Homeowner vacancy was just 0.95% (2024)—the lowest on record, down from 2.9% in 2008.
          What do low vacancies mean? Low rental vacancies give landlords pricing power and indicate few options for renters seeking affordable units. Low homeowner vacancies signal intense competition among buyers, driving prices higher.
          Supply vs.
          
          [...]
          
          n which the lowest earners are left without a seat.
          This figure shows two distinct changes during the past two decades:
          - The precrisis overshoot: In the years leading up to 2008, housing completions frequently exceeded household formation. In 2004, 1.83 million units were completed while only 1.35 million new households (three-year average) were formed—contributing to the oversupply that precipitated the crash.
          - The postcrisis undershoot: Since 2008, the pattern has been mixed. In several years, household formation outpaced completions. In 2011, only 585,000 units were completed while 1.30 million households (three-year average) formed—a striking imbalance.
          The result of these changes has been a cumulative gap. Various studies estimate a cumulative housing shortfall of 3 million to 5 million units that has built up since 2008, contrib
          
          [...]
          
          es, and homeownership becomes increasingly out of reach for many American families.
          Conclusion: The Supply Imperative
          The data tell a consistent story: The U.S. is not building enough housing to meet demand. Building permits per capita stood at just 4.3 per 1,000 in 2024—35% below the 1960-2000 historical average and 59% below the 1972 peak. Vacancy rates have fallen to historic lows, with rental vacancy at 6.8% and homeowner vacancy below 1%, signaling intense competition for limited housing stock. Various estimates suggest a cumulative shortfall of 3 million to 5 million units has accumulated since 2008.
          Demographic pressures compound these challenges. Average household size has fallen 23.7% since 1965—from 3.37 to 2.57 persons per household in 2024. Yet construction has not kept pace with this structural shift in how Americans live.
          These supply-side constraints are a key driver of the affordability challenges documented in our companion post. When housing supply
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q4-T1-044
    section: "Long-term Outcomes"
    sentence: "This dynamic creates a delicate balance, as the basic rule of supply and demand dictates that increasing demand without increased supply will raise prices, though demand-side interventions are often favored for their more immediate, measurable impact compared to the years-long timeline for new construction.[8]"
    cited_evidence:
      - evidence_id: ev_019
        bibliography_num: 8
        url: "https://finance.yahoo.com/news/why-demand-side-interventions-paired-140000953.html"
        tier: T6
        span: '0-500'
        title: "Why demand-side interventions need to be paired with housing supply"
        span_text: |
          OTTAWA, ON, April 15, 2026 /CNW/ - New analysis from Canada Mortgage and Housing Corporation (CMHC) explores how housing supply and housing demand interventions need to work together to address the housing affordability crisis. Demand-side interventions, which directly support households in attaining a home, are often favoured because of their more immediate impact. The results can be measured more quickly than the creation of new supply, which take years to deliver. It is a delicate balance, since the basic rule of supply and demand dictates that if demand increases without increased supply, prices will rise. In his latest article, CMHC's Chief Economist, Mathieu Laberge highlights new modeling analyzing the tug-of-war between demand-side and supply-side housing interventions. Quote: "Helping more Canadians access homeownership is an important goal, but how we do it matters", said Mathieu Laberge, Chief Economist, CMHC. "Without careful targeting and a matching increase in housing supply, demand-side measures can end up increasing costs for a broader group of households." Read the full article on [CMHC's website](https://edge.prnewswire.com/c/link/?t=0&l=en&o=4664504-1&h=329659968&u=https%3A%2F%2Fwww.cmhc-schl.gc.ca%2Fen%2Fobserver%2F2026%2Fwhy-demand-side-interventions-need-to-be-targeted-and-offset-with-supply&a=CMHC%27s+website) Related links: - [Why Canada's housing supply gap exists and how to fix it | CMHC](https://edge.prnewswire.com/c/link/?t=0&l=en&o=4664504-1&h=211
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q4-T1-045
    section: "Long-term Outcomes"
    sentence: "In Canada, the scale of the challenge is recognized in ambitions to build millions of homes, with one task force focused on building 5.8 million homes within a short period, though concerns exist that such large-scale construction could add 100 megatons of greenhouse gas emissions.[11]"
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

  - claim_id: Q4-T1-046
    section: "Long-term Outcomes"
    sentence: "Historical precedent suggests such efforts are possible, as Canada's postwar national effort created a generation of housing through government and private industry partnership to meet rapid population growth.[10]"
    cited_evidence:
      - evidence_id: ev_011
        bibliography_num: 10
        url: "https://housing-infrastructure.canada.ca/housing-logement/housing-plan-report-rapport-plan-logement-eng.html"
        tier: T3
        span: '0-500'
        title: "Solving the Housing Crisis: Canada's Housing Plan"
        span_text: |
          Solving the Housing Crisis: Canada's Housing Plan On this page - The Housing Crisis of our Past - The Housing Crisis of Today - Solving the Housing Crisis - 1: Building More Homes - 2: Making it Easier to Rent or Own a Home - 3: Helping Canadians Who Can’t Afford a Home - Conclusion - Who's in Charge of What: List of Responsibilities in Housing by Order of Government We need to build more homes in Canada, and we need to build them by the millions. The good news – we can. The proof is in our history. The Housing Crisis of our Past At the end of the Second World War, our country reached a defining crossroads. As soldiers returned home and displaced people began to start their new lives in Canada, we experienced rapid population growth. This had far-reaching impacts, including a spike in inflation and an immense pressure on housing. Canada had a choice between building homes slowly and steadily, or rising to the occasion to build quickly and ensure that everyone who called our growing country home would have a roof over their head. Canada met the moment. Canada chose to build. What followed was a national effort to build homes at a record pace to meet the needs of a new generation of Canadians. Governments and private industry came together and made the investments necessary to get the job done. We overcame what seemed impossible and created a generation of housing that can still be found in our cities today. A generation later, as baby boomers came of age, Canada once again fac
          
          [...]
          
          ration and partnership with Indigenous Peoples through Nation-to-Nation, Inuit-Crown, and Government-to-Government relationships. This has resulted in new, co-developed distinctions-based approaches to Indigenous housing and homelessness, more than $10.7B, which has created almost 22,000 new or repaired homes on-reserve. With federal partnership, Indigenous communities can build the homes and infrastructure needed to meet the needs of their members, families, and youth. That's why Budget 2024 will p
          
          [...]
          
          t housing challenges. They also represent a disproportionately high share of shelter users, 33% in 2022, while only comprising 5% of Canada's population. We recognize the magnitude of the work ahead. The Government of Canada committed an additional $4.3 billion towards the Urban, Rural and Northern Indigenous Housing Strategy that will launch in 2024. With this funding, the strategy is establishing a ‘for Indigenous, by Indigenous' National Housing Centre and will provide additional distinctions-ba
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q4-T1-047
    section: "Long-term Outcomes"
    sentence: "A growing body of empirical research finds that new market-rate housing can affect broader affordability conditions through household moves, while also underscoring that market outcomes alone are insufficient to meet needs at very low incomes.[6]"
    cited_evidence:
      - evidence_id: ev_005
        bibliography_num: 6
        url: "https://www.novoco.com/notes-from-novogradac/how-new-housing-affects-affordability-evidence-limits-and-policy-implications"
        tier: T4
        span: '0-500'
        title: "How New Housing Affects Affordability: Evidence, Limits and Policy ..."
        span_text: |
          How New Housing Affects Affordability: Evidence, Limits and Policy Implications Recent Insights Key Takeaways A growing body of empirical research finds that new market-rate housing can affect broader affordability conditions through household moves, while also underscoring that market outcomes alone are insufficient to meet needs at very low incomes. - New market rate construction expands mobility through vacancy chains, easing rent pressures even in high cost markets by opening more homes. - Filtering and market wide affordability gains occur unevenly, slowing or stalling in tight markets, underscoring the need to preserve existing lower cost homes as new supply comes online. - Supply growth alone can’t reach extremely low income renters. Sustained public subsidy is indispensable. - Lasting affordability requires pairing new construction with preservation, ensuring low-cost homes are not lost faster than supply can relieve pressure on the housing market. Recent housing debates have increasingly focused not just on how much housing is built, but on who occupies newly built homes and how increases in supply may improve affordability across markets. A growing body of empirical research finds that new market-rate housing can affect broader affordability conditions through household moves, while also underscoring that market outcomes alone are insufficient to meet needs at very low incomes, a dynamic recently highlighted in a February article from [The Atlantic](https://www.thea
          
          [...]
          
           argument that housing markets are segmented by income, location and tenure. This distributional lens matters because neighborhood context shapes life outcomes. Evidence from the [Moving to Opportunity experiment](https://pubs.aeaweb.org/doi/pdfplus/10.1257/aer.20150572) shows that children who moved to lower‑poverty neighborhoods at younger ages had better long‑term outcomes, underscoring that where housing is available can matter alongside how much is built. According to [Harvard’s Joint Center for H
          
          [...]
          
          using debate, often described as the housing ‘filtering’ process. Stuart Rosenthal’s estimates from “[Are Private Markets and Filtering a Viable Source of Low-Income Housing? Estimates from a "Repeat Income" Model](https://www.aeaweb.org/articles?id=10.1257/aer.104.2.687)” indicate that filtering is, on average, faster in rental housing than in owner‑occupied housing, but it still takes time. More recently, [analysis summarized](https://nlihc.org/resource/new-study-examines-filtering-dynamics-us-housing-supply)
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q4-T1-048
    section: "Long-term Outcomes"
    sentence: "Vacancy rates are at historic lows, with rental vacancy at 6.8% and homeowner vacancy at just 0.95% in 2024, signaling intense competition for limited stock and giving landlords and sellers significant pricing power.[5]"
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
          To understand housing supply, we start with building permits—the first step in the construction pipeline that also captures the optimism of real estate developers and households about the future. Looking at permits adjusted for population growth provides a clearer picture of whether construction is keeping pace with a growing nation. (See the first figure.)
          As the figure shows, there are several distinctive periods:
          - The 1970s peak: Permit activity peaked in 1972 at 10.6 permits per 1,000 people. This was no accident—the baby boom generation was entering prime household-formation age, the interstate highway system had opened vast suburban lands for development, and federal policies—from Federal Housing Administration loan guarantees to mortgage interest deductions—actively encouraged homeownership. This confluence of demographic pressure, available land and policy incentives created the high-water mark of postwar housing construction.
          - The 1980s to the 2000s, from volat
          
          [...]
          
          h inflation and interest rates is reflected in the volatility of permits, until the mid-1990s that started a decade and a half of stable growth.
          - The 2008 collapse: The housing crisis triggered a dramatic decline in permits. Total permits fell from 7.3 per 1,000 in 2005 to just 1.9 per 1,000 in 2009—a 74% decline and the lowest level on record since data collection began in 1960.
          - The incomplete recovery: Despite over a decade of recovery, total permits per capita in 2024 stand at 4.3 per 1,000—still 35% below the 1960-2000 average of 6.6 permits per 1,000. The U.S. is building less housing per person than at almost any point in the postwar era.
          Why Has Housing Construction Stayed Low?
          Several factors constrain today’s housing supply:
          - Labor shortages: The construction workforce nev
          
          [...]
          
          Developable land near job centers has become scarcer and more expensive, pushing construction to outlying areas.
          The Multifamily Shift
          One notable trend is the growing share of multifamily construction (5+ units). Multifamily permits have risen from 0.4 per 1,000 in 2011 to 1.3 per 1,000 in 2024, partially offsetting weak single-family activity. Single-family permits remain at 2.9 per 1,000—well below the historical average of 4.1.
          From Permits to Completions: The “Leaky Pipe” of Supply
          A building permit is a statement of intent, not a finished home. By analyzing the growing divergence between permits issued and final completions, we can identify the specific structural bottl
          
          [...]
          
           from flowing to completion.
          The second figure reveals three hurdles to finishing construction:
          - The completion lag: Permits consistently lead completions by several months to a year, reflecting the time required to build. In 2024, permits stood at 4.3 per 1,000 people while completions were 4.8 per 1,000 people—the gap has narrowed as the postpandemic construction pipeline works through.
          - Historical patterns: At the 1972 peak, permits reached 10.6 per 1,000 while completions hit 9.5 per 1,000 the following year. During the 2008 crisis, both series collapsed together, with completions falling to just 2.1 per 1,000 by 2010.
          - Postpandemic divergence: The COVID-19 pandemic period shows notable dynamics—permits surged to 5.2 per 1,000 in 2021 as demand spiked, but completions lagged as builders faced unprecedented supply chain disruptions and labor shortages.
          Housing Stock and Household Size
          Total housing inventory must be measured against the evolving American househol
          
          [...]
          
          2 units per 1,000 people in 1965 to 386 in 1980, 415 in 2000, and 432 in 2024. This represents a 30% increase since 1965—roughly matching the decline in household size.
          - Declining household size: Average household size has fallen dramatically: from 3.37 persons per household in 1965 to 2.81 in 1980, 2.65 in 2000, and 2.57 in 2024. This means family size has declined by nearly a quarter (23.7%) since 1965; as a result, far more housing units are needed to house the same population.
          So, on this back-of-the-envelope calculation, the U.S. doesn’t look obviously “overbuilt” at the national level: Units per person increased by roughly the sam
          
          [...]
          
          ing absorbed quickly, often correlating with rising prices and rents.
          These vacancy rates have shifted dramatically in the past two decades.
          - Postcrisis spike: Vacancy rates spiked after 2008 as foreclosures flooded the market. Rental vacancies hit 10.6% in 2009, while homeowner vacancies reached 2.9% in 2008—both elevated as distressed properties sat empty.
          - The current tightness: Both vacancy rates have fallen to near-historic lows. Rental vacancy stood at 6.8% in 2024—down from the 2009 peak and below the 1960s levels of 7% to 8%. Homeowner vacancy was just 0.95% (2024)—the lowest on record, down from 2.9% in 2008.
          What do low vacancies mean? Low rental vacancies give landlords pricing power and indicate few options for renters seeking affordable units. Low homeowner vacancies signal intense competition among buyers, driving prices higher.
          Supply vs.
          
          [...]
          
          n which the lowest earners are left without a seat.
          This figure shows two distinct changes during the past two decades:
          - The precrisis overshoot: In the years leading up to 2008, housing completions frequently exceeded household formation. In 2004, 1.83 million units were completed while only 1.35 million new households (three-year average) were formed—contributing to the oversupply that precipitated the crash.
          - The postcrisis undershoot: Since 2008, the pattern has been mixed. In several years, household formation outpaced completions. In 2011, only 585,000 units were completed while 1.30 million households (three-year average) formed—a striking imbalance.
          The result of these changes has been a cumulative gap. Various studies estimate a cumulative housing shortfall of 3 million to 5 million units that has built up since 2008, contrib
          
          [...]
          
          es, and homeownership becomes increasingly out of reach for many American families.
          Conclusion: The Supply Imperative
          The data tell a consistent story: The U.S. is not building enough housing to meet demand. Building permits per capita stood at just 4.3 per 1,000 in 2024—35% below the 1960-2000 historical average and 59% below the 1972 peak. Vacancy rates have fallen to historic lows, with rental vacancy at 6.8% and homeowner vacancy below 1%, signaling intense competition for limited housing stock. Various estimates suggest a cumulative shortfall of 3 million to 5 million units has accumulated since 2008.
          Demographic pressures compound these challenges. Average household size has fallen 23.7% since 1965—from 3.37 to 2.57 persons per household in 2024. Yet construction has not kept pace with this structural shift in how Americans live.
          These supply-side constraints are a key driver of the affordability challenges documented in our companion post. When housing supply
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q4-T1-049
    section: "Long-term Outcomes"
    sentence: "Without careful targeting and a matching increase in housing supply, demand-side measures can end up increasing costs for a broader group of households.[8]"
    cited_evidence:
      - evidence_id: ev_019
        bibliography_num: 8
        url: "https://finance.yahoo.com/news/why-demand-side-interventions-paired-140000953.html"
        tier: T6
        span: '0-500'
        title: "Why demand-side interventions need to be paired with housing supply"
        span_text: |
          OTTAWA, ON, April 15, 2026 /CNW/ - New analysis from Canada Mortgage and Housing Corporation (CMHC) explores how housing supply and housing demand interventions need to work together to address the housing affordability crisis. Demand-side interventions, which directly support households in attaining a home, are often favoured because of their more immediate impact. The results can be measured more quickly than the creation of new supply, which take years to deliver. It is a delicate balance, since the basic rule of supply and demand dictates that if demand increases without increased supply, prices will rise. In his latest article, CMHC's Chief Economist, Mathieu Laberge highlights new modeling analyzing the tug-of-war between demand-side and supply-side housing interventions. Quote: "Helping more Canadians access homeownership is an important goal, but how we do it matters", said Mathieu Laberge, Chief Economist, CMHC. "Without careful targeting and a matching increase in housing supply, demand-side measures can end up increasing costs for a broader group of households." Read the full article on [CMHC's website](https://edge.prnewswire.com/c/link/?t=0&l=en&o=4664504-1&h=329659968&u=https%3A%2F%2Fwww.cmhc-schl.gc.ca%2Fen%2Fobserver%2F2026%2Fwhy-demand-side-interventions-need-to-be-targeted-and-offset-with-supply&a=CMHC%27s+website) Related links: - [Why Canada's housing supply gap exists and how to fix it | CMHC](https://edge.prnewswire.com/c/link/?t=0&l=en&o=4664504-1&h=211
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
