Independent Tier-1 audit of 7 Q3 GenAI Workforce claims. Output YAML records only.

You are populating Tier-1 audit fields for each claim in the BATCH below.

# Tier-1 schema (per claim)

```yaml
- claim_id: Q3-T1-NNN
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
  - critical = the headline policy-decision number (e.g., GenAI displacement %, white-collar workforce share, productivity multipliers, automation timelines)
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

# Q3 batch 1: claims 1-7 (re-run with full direct_quote)
schema_version: tier1_v2
claims:
  - claim_id: Q3-T1-001
    section: "Efficacy"
    sentence: "Early Canadian evidence from November 2022 to December 2025 shows employment generally grew regardless of an occupation's potential exposure to or complementarity with AI, with no clear sign that jobs more exposed to AI are declining faster than others.[1][2]"
    cited_evidence:
      - evidence_id: ev_000
        bibliography_num: 1
        url: "https://www150.statcan.gc.ca/n1/pub/36-28-0001/2026001/article/00003-eng.htm"
        tier: T4
        span: '0-500'
        title: "Canadian employment trends in the era of generative ..."
        span_text: |
          Economic and Social Reports Canadian employment trends in the era of generative artificial intelligence: Early evidence DOI: https://doi.org/10.25318/36280001202600100003-eng Text begins Abstract Artificial intelligence (AI) holds the potential to transform the nature of work, and its ability to replace human labour remains a central concern. This study highlights recent labour market trends, distinguishing jobs potentially more exposed to and less complementary with AI from other jobs. From November 2022—when generative AI applications started gaining traction following the mass availability of ChatGPT—to December 2025, employment generally grew regardless of potential occupational exposure to and complementarity with AI. However, job growth varied across worker characteristics. Younger employees and those less educated generally saw weaker job growth over this period. Coding-intensive professions (e.g., software engineers and web designers) grew at a similar rate as other jobs. However, gains in coding-intensive jobs were concentrated among workers aged 30 to 49, while the number of coding professionals younger than 30 stagnated. From the fourth quarter of 2022 to the third quarter of 2025, job vacancies in occupations potentially more exposed to and less complementary with AI decreased at a similar rate as vacancies in occupations potentially less exposed to AI. Jobs potentially more exposed to AI regardless of complementarity are more likely to be higher-paying, associate
          
          [...]
          
          mplementarity across all occupations; otherwise, it is considered to have low complementarity. Sources: Statistics Canada, Labour Force Survey, January 2015 to December 2025; and Occupational Information Network. | |||||| | 2015 | |||||| | January | 76.7 | 78.9 | 96.5 | 79.3 | 88.4 | 98.5 | | February | 77.4 | 78.7 | 96.3 | 79.7 | 88.3 | 98.1 | | March | 78.9 | 77.3 | 96.1 | 79.8 | 87.7 | 99.2 | | April | 79.1 | 77.0 | 96.3 | 79.7 | 87.6 | 99.5 | | May | 79.2 | 78.0 | 95.9 | 80.2 | 86.9 | 98.9 | | June | 79.8 | 78.7 | 96.3 | 81.9 | 86.7 | 98.4 | | July | 80.1 | 79.3 | 95.8 | 81.8 | 87.3 | 98.1 | | August | 82.4 | 78.5 | 95.6 | 82.0 | 87.3 | 97.9 | | September | 82.5 | 79.1 | 95.2 | 82.1 | 87.6 | 97.1 | | October | 82.8 | 79.5 | 94.9 | 80.6 | 89.1 | 96.6 | | November | 82.3 | 78.2 | 94.8 | 82.3 | 88.0 | 96.7 | | December | 81.8 | 79.6 | 94.2 | 81.6 | 87.9 | 96.9 | | 2016 | |||||| | January | 81.7 | 79.3 | 94.2 | 81.1 | 87.9 | 99.0 | | February | 81.2 | 80.0 | 94.3 | 80.7 | 88.2 | 98.4 | | March | 81.0 | 81.3 | 93.7 | 80.7 | 88.7 | 98.4 | | April | 81.5 | 81.7 | 93.3 | 81.4 | 88.7 | 98.5 | | May | 82.1 | 81.5 | 93.7 | 81.1 | 89.2 | 98.5 | | June | 82.3 | 80.2 | 93.7 | 81.6 | 88.9 | 98.7 | | July | 82.2 | 80.9 | 93.4 | 81.1 | 88.3 | 100.1 | | August | 81.6 | 81.0 | 94.5 | 81.7 | 89.9 | 97.9 | | September | 81.2 | 80.9 | 95.2 | 81.5 | 90.1 | 98.4 | | October | 80.6 | 80.4 | 95.5 | 81.8 | 90.3 | 98.6 | | November | 80.0 | 81.8 | 96.0 | 81.2 | 90.8 | 98.8 | | December | 81.0 | 81.6 | 96.4 | 81.3 | 90.9 | 98.9 | | 2017 | |||||| | January | 81.9 | 80.6 | 96.8 | 81.6 | 93.0 | 98.7 | | February | 82.3 | 80.7 | 97.1 | 82.1 | 90.8 | 99.4 | | March | 83.6 | 80.4 | 97.4 | 82.3 | 91.1 | 99.0 | | April | 82.2 | 80.7 | 98.1 | 82.3 | 90.6 | 99.5 | | May | 81.4 | 81.4 | 98.3 | 83.1 | 90.7 | 100.4 | | June | 82.0 | 82.5 | 98.1 | 82.3 | 91.5 | 100.8 | | July | 82.7 | 81.8 | 98.0 | 83.1 | 92.2 | 100.7 | | August | 82.9 | 83.9 | 97.6 | 83.1 | 90.4 | 100.6 | | September | 82.9 | 84.0 | 97.3 | 83.3 | 90.3 | 101.2 | | October | 83.2 | 85.1 | 96.4 | 82.9 | 90.3 | 102.0 | | November | 85.3 | 82.3 |
      - evidence_id: ev_001
        bibliography_num: 2
        url: "https://lmic-cimt.ca/future-of-work/canadian-employment-trends-in-the-era-of-generative-artificial-intelligence-early-evidence/"
        tier: T4
        span: '0-500'
        title: "Canadian employment trends in the era of generative ..."
        span_text: |
          Title: Canadian employment trends in the era of generative artificial intelligence: Early evidence — LMIC-CIMT URL Source: https://lmic-cimt.ca/future-of-work/canadian-employment-trends-in-the-era-of-generative-artificial-intelligence-early-evidence/ Markdown Content: # Canadian employment trends in the era of generative artificial intelligence: Early evidence — LMIC-CIMT (https://lmic-cimt.ca/future-of-work/canadian-employment-trends-in-the-era-of-generative-artificial-intelligence-early-evidence/#fl-main-content) [LMIC-CIMT](https://lmic-cimt.ca/) [](https://lmic-cimt.ca/future-of-work/canadian-employment-trends-in-the-era-of-generative-artificial-intelligence-early-evidence/#) * [Publications](https://lmic-cimt.ca/publications-all/) * [Resources](https://lmic-cimt.ca/lmi-resources/) * [LMIC Dashboards](https://dashboards.lmic-cimt.ca/) * [Future of Work](https://lmic-cimt.ca/lmi-resources/future-of-work/) * [Events & Webinars](https://lmic-cimt.ca/lmi-resources/events/) * [Understanding Skills](https://lmic-cimt.ca/lmi-resources/skills/) * [WorkWords](https://lmic-cimt.ca/lmi-resources/workwords/) * [Canadian Job Trends Dashboard](https://lmic-cimt.ca/canadian-job-trends-dashboard/) * [About](https://lmic-cimt.ca/about/) * [About LMIC](https://lmic-cimt.ca/about/) * [Board of Directors](https://lmic-cimt.ca/about/board-of-directors/) * [LMIC Staff](https://lmic-cimt.ca/about/lmic-staff/) * [National Stakeholder Advisory Panel](https://lmic-cimt.ca/about/national-stakeholde
          
          [...]
          
          n trends shaping Canada's labour market. ## Canadian employment trends in the era of generative artificial intelligence: Early evidence January 28, 2026 | BY Mehdi, T., & Frenette, M. READ THE FULL ARTICLE AT THE SOURCE [Web Version](https://doi.org/10.25318/36280001202600100003-eng) Key Takeaway _Despite concerns that AI will lead to declines in the number of available jobs, early Canadian evidence shows no clear sign that jobs more exposed to AI are declining faster than others._ Research from Statist
          
          [...]
          
          The credential boom is here, but which ones actually help workers?](https://lmic-cimt.ca/future-of-work/the-credential-boom-is-here-but-which-ones-actually-help-workers/) February 3, 2026 | Escobari, M., & Seyal, I. Key Takeaway:_There are more than 1.5 million unique credentials now available. This growth has created a crowded, largely unregulated landscape in which workers struggle to distinguish high-value from low-value options._ [View Summary](https://lmic-cimt.ca/future-of-work/the-credential
          
          [...]
          
          ly for work tasks, creating a shadow economy that is outpacing formal organizational AI adoption._ [View Summary](https://lmic-cimt.ca/future-of-work/the-genai-divide-state-of-ai-in-business-2025/) [PDF Version](https://mlq.ai/media/quarterly_decks/v0.1_State_of_AI_in_Business_2025_Report.pdf) [Canadian employment trends in the era of generative artificial intelligence: Early evidence](https://lmic-cimt.ca/future-of-work/canadian-employment-trends-in-the-era-of-generative-artificial-intelligence-ea
          
          [...]
          
           clear sign that jobs more exposed to AI are declining faster than others._ [View Summary](https://lmic-cimt.ca/future-of-work/canadian-employment-trends-in-the-era-of-generative-artificial-intelligence-early-evidence/) [Web Version](https://doi.org/10.25318/36280001202600100003-eng) [How big a threat is AI to entry-level jobs?](https://lmic-cimt.ca/future-of-work/how-big-a-threat-is-ai-to-entry-level-jobs/) January 29, 2026 | The Economist Key Takeaway:_Generative AI may compress the traditional corpor
          
          [...]
          
          94%20LMIC-CIMT&tw_document_href=https%3A%2F%2Flmic-cimt.ca%2Ffuture-of-work%2Fcanadian-employment-trends-in-the-era-of-generative-artificial-intelligence-early-evidence%2F&tw_iframe_status=0&tw_order_quantity=0&tw_pid_src=1&tw_sale_amount=0&twpid=tw.1778497352493.828341044423509813&txn_id=o1i83&type=javascript&version=2.3.53)![Image 3](https://analytics.twitter.com/i/adsct?bci=3&dv=UTC%26en-US%26Google%20Inc.%26Linux%20x86_64%26255%26800%26600%268%2624%26800%26600%260%26na&eci=2&event_id=080996ad-4951-40fe-a95b-a4f9d2b72ec1&events=%5B%5B%22pageview%22%2C%7B%7D%5D%5D&
          
          [...]
          
          94%20LMIC-CIMT&tw_document_href=https%3A%2F%2Flmic-cimt.ca%2Ffuture-of-work%2Fcanadian-employment-trends-in-the-era-of-generative-artificial-intelligence-early-evidence%2F&tw_iframe_status=0&tw_order_quantity=0&tw_pid_src=1&tw_sale_amount=0&twpid=tw.1778497352493.828341044423509813&txn_id=o1i83&type=javascript&version=2.3.53)
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q3-T1-002
    section: "Efficacy"
    sentence: "One review of empirical evidence notes that where effects appear, they are concentrated in entry-level segments of highly exposed occupations, while senior employment remains largely stable.[3]"
    cited_evidence:
      - evidence_id: ev_007
        bibliography_num: 3
        url: "https://laweconcenter.org/resources/ai-productivity-and-labor-markets-a-review-of-the-empirical-evidence/"
        tier: T4
        span: '0-500'
        title: "AI, Productivity, and Labor Markets: A Review of the ..."
        span_text: |
          AI, Productivity, and Labor Markets: A Review of the Empirical Evidence Executive Summary Generative artificial intelligence (AI) has diffused with unusual speed since late 2022. By late 2024, nearly 40% of U.S. adults ages 18–64 reported using AI tools, a pace that exceeds comparable stages for personal computers and the internet. That rapid uptake has sharpened two policy questions: whether AI will generate measurable gains in output and productivity at the aggregate level, and whether the adjustment process will produce labor-market disruption large enough to justify new regulatory intervention. The empirical literature points to a clear pattern. Controlled field experiments and randomized trials document large productivity gains at the task and firm level, often alongside quality improvements. Across writing, customer support, software development, accounting, law, and translation, studies report 15% to more than 50% reductions in task-completion time, meaningful quality gains, and disproportionately large benefits for less-experienced workers, producing “skill compression” within occupations. At the same time, aggregate labor-market indicators through 2024–2025 show limited disruption, despite rapid adoption. Most datasets find little evidence of economywide job loss or wage decline. Where effects appear, they are concentrated in entry-level segments of highly exposed occupations, while senior employment remains largely stable. Adjustment to date has occurred through tas
          
          [...]
          
          annual global GDP over 10 years—roughly $7 trillion—based on broad occupational task exposure. Erkan Erdem and Dileep Birur (2025), using a dynamic computable general equilibrium framework, estimate that rapid adoption could raise U.S. GDP by about $2.48 trillion by 2030.3 Taken together, these forecasts differ less over data than over assumptions. Aggregate effects depend on three factors: diffusion across sectors, whether productivity gains expand output rather than reshuffle rents, and whether organizational redesi
          
          [...]
          
          rative records across 11 exposed occupations and find essentially zero effects on earnings or hours through 2024. U.S.-based evidence points in the same direction. Jonathan S. Hartley, Filip Jolevski, Vitor Melo, and Brendan Moore (2026) report that 35.9% of U.S. workers used generative AI by December 2025 and find small positive wage effects, with no statistically significant declines in job openings or employment in exposed occupations. Bharat Chandar’s (2025) Current Population Survey analysis si
          
          [...]
          
          ng that AI adoption correlates with an 18% increase in weekly client support and a reallocation of roughly 9% of work hours from routine data entry to higher-value tasks, such as client communication. AI use reduced monthly book-closing timelines by 7.5 days and increased ledger detail by 12%, indicating quality improvements alongside time savings. The authors also document complementarity between professional expertise and AI confidence scores: experienced accountants used model outputs to target 
          
          [...]
          
          ixed and that appropriate tool selection and workflow design can mitigate risks without restricting deployment. Software development studies show similarly large effects. Sida Peng et al. (2023) report that GitHub Copilot users complete coding tasks 55.8% faster in controlled settings, with larger gains among less experienced developers. Kevin Zheyuan Cui et al. (2025), studying nearly 5,000 developers across three large field experiments, find a 26.08% increase in weekly task completion, driven by higher adoption and disproportionately larger gains for junior developers. These findings undermine claims that AI primarily benefits top performers and instead show AI reducing frictions for early-care
          
          [...]
          
          mental evidence from translation extends the pattern. Ali Merali (2024) conducts a randomized trial with 300 professional translators and links increased training compute to economic outcomes. A tenfold increase in compute reduced completion time by 12.3%, improved quality by 0.18 standard deviations, and raised earnings per minute by 16.1%. Lower-skilled translators experienced gains roughly four times larger than their higher-skilled counterparts. The magnitude and replication of these effects across contexts suggest that productivity gains arise consistently in specific task catego
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q3-T1-003
    section: "Efficacy"
    sentence: "The projected macroeconomic impact on productivity and output is gradual; one model estimates AI will increase total factor productivity (TFP) and GDP levels by 1.5% by 2035, nearly 3% by 2055, and 3.7% by 2075, with the peak annual boost to TFP growth of around 0.2 percentage points occurring in the early 2030s.[4]"
    cited_evidence:
      - evidence_id: ev_002
        bibliography_num: 4
        url: "https://budgetmodel.wharton.upenn.edu/p/2025-09-08-the-projected-impact-of-generative-ai-on-future-productivity-growth/"
        tier: T4
        span: '0-500'
        title: "The Projected Impact of Generative AI on Future ..."
        span_text: |
          The Projected Impact of Generative AI on Future Productivity Growth
          The Projected Impact of Generative AI on Future Productivity Growth
          We estimate that AI will increase productivity and GDP by 1.5% by 2035, nearly 3% by 2055, and 3.7% by 2075. AI’s boost to annual productivity growth is strongest in the early 2030s but eventually fades, with a permanent effect of less than 0.04 percentage points due to sectoral shifts.
          Key Points
          -
          We estimate that 40 percent of current GDP could be substantially affected by generative AI. Occupations around the 80th percentile of earnings are the most exposed, with around half of their work susceptible to automation by AI, on average. The highest-earning occupations are less exposed, and the lowest-earning occupations are the least exposed.
          -
          AI’s boost to productivity growth is strongest in the early 2030s, with a peak annual contribution of 0.2 percentage points in 2032. After adoption saturates, growth reverts to trend. Because sectors that are more exposed to AI have faster trend TFP growth, sectoral shifts during the AI transition add a lasting 0.04 percentage point boost to aggregate growth.
          -
          Compounded, TFP and GDP levels are 1.5% higher by 2035, nearly 3% by 2055, and 3.7% by 2075, meaning that AI leads to a permanent increase in the level of economic activity.
          -
          Caution is required in interpreting these projections of AI’s impact, which are based on limited data on AI’s initial effects. Future data and developments in AI technolog
          
          [...]
          
          ile available for download provides exposure estimates for 784 detailed occupational categories that are aggregated in Table 1.
          | Occupation Group | Exposure to AI Automation (% of tasks) |
          |---|---|
          | Office and Administrative Support Occupations | 75.5 |
          | Business and Financial Operations Occupations | 68.4 |
          | Computer and Mathematical Occupations | 62.6 |
          | Sales and Related Occupations | 60.1 |
          | Management Occupations | 49.9 |
          | Legal Occupations | 47.5 |
          | Arts, Design, Entertainment, Sports, and Media Occupations | 45.8 |
          | Architecture and Engineering Occupations | 40.7 |
          | Life, Physical, and Social Science Occupations | 31.0 |
          | Educational Instruction and Library Occupations | 29.5 |
          | Community and Social Service Occupations | 27.5 |
          | Healthcare Practitioners and Technical Occupations | 23.1 |
          | Protective Service Occupations | 20.7 |
          | Transportation and Material Moving Occupations | 20.0 |
          | Food Preparation and Serving Related Occupations | 18.1 |
          | Personal Care and Service Occupations | 17.5 |
          | Healthcare Support Occupations | 15.5 |
          | Production Occupations | 14.4 |
          | Installation, Maintenance, and Repair Occupations | 13.1 |
          | Farming, Fishing, and Forestry Occupations | 9.7 |
          | Construction and Extraction Occupations | 8.9 |
          | Building and Grounds Cleaning and Maintenance Occupations | 2.6 |
          Source: PWBM based on estimates from Eloundou et al.’s (2024) and data from the Bureau of Labor Statistics.
          Figure 1 shows the distribution of employment by automation potential based on the categorization of tasks provided by Eloundou et al. (202
          
          [...]
          
          | 14% increase in task completion rate. |
          | Jabarian and Henkel (2025) | Job interviews with a generative AI voice agent. | 17% increase in job starts; 18% increase in retention rate. |
          | Noy and Zhang (2023) | Basic professional writing with ChatGPT-3.5. | 40% increase in speed; 18% increase in output quality. |
          | Peng et al. (2023) | JavaScript programming with GitHub Copilot. | 56% increase in speed. |
          | Cui et al. (2025) | Software development with GitHub Copilot. | 26% increase in task completi
          
          [...]
          
           increase in speed. |
          Sources: See links in the first column.
          AI’s impact on TFP depends on how quickly productivity-enhancing tools are actually adopted. Data on the diffusion of generative AI tools remains limited, but Bick et al. (2025) find that 26.4 percent of workers used generative AI at work in the second half of 2024, while 33.7 percent of adults used it outside of work. Using data from the Real-Time Population Survey (RPS), they show that early adoption patterns of AI for work are broadly similar to the adoption of personal computers (PCs) in the early 1980s.6
          Figure 3 com
          
          [...]
          
          f exposure to AI (based on the Eloundou et al. classification), we find that job growth has stagnated in occupations with most AI automation potential. For jobs that can be performed entirely by generative AI, employment fell sharply in 2024 and was 0.75 percent lower than in 2021 (however, recall from Figure 1 that these jobs make up only around 1 percent of total employment). In occupations with high AI exposure (90 to 99 percent of tasks can be automated) the shift has been less dramatic, but employment growth has slowed significantly since 2022.7
          Combining estimates of exposure, cost savings, and adoption, we project generative AI’s contribution to TFP growth over the next several decades. Figure 5 plots our projections. Despite examples of successful AI adoption such as those described in Table 2, we estimate that AI’s impact on TFP growth remains small today - 0.01 percentage points (pp) in 2025 - as most businesses have yet to deploy and gain experience with AI tools. Over the next decade, AI’s contribution will grow for three reasons:
          -
          Generative AI tools will increasingly be applied to tasks exposed to AI 
          
          [...]
          
          exposed to AI will rise due to long-running sectoral trends, with sectors relatively more exposed to AI (such as software development and professional services) growing faster than the rest of the economy.
          We project that AI will boost TFP growth by 0.09pp in 2027, 0.18pp in 2030, and peak in the early 2030s at around 0.2pp. As new adoption slows in the 2030s due to declining remaining opportunities to employ additional AI tools productively, the impact on TFP growth diminishes to around 0.1pp by end of the decade and continues to shrink thereafter. We project that TFP growth will be persistently higher by a little less than 0.04pp even after adoption saturates and TFP growth returns to trend. This occurs because sectors that were more exposed to AI also have faster trend TFP growth, and those sectors will make up a larger share of the economy as a result of AI-driven productivity gains.
          Source: PWBM
          Because these are growth effects, their cumulative impact – the impact on TFP levels – is what matters for living standards. Cumulating projected growth contributions implies that the level of TFP will be around 1.5% higher by 2035, 3% higher by 2055, and 3.7% higher by 2075 relative to a noAI path. Put differently, AI makes the economy permanently larger, but once adoption saturates, the ongoing growth rate itself returns to trend—aside from the small, persistent lift from sectors that benefit more from
          
          [...]
          
          of work that can be performed by AI. However, Eloundou at al. present another version of the metric in which they assign a numeric score to each category to facilitate comparisons with other quantities. As shown in Table A1, they assign values of 0, 0.25, 0.5, 0.75, and 1 to categories T0 through T4, respectively. This assignment treats each category as an equal increment of 0.25, rather than using the percentages from the original category definitions to quantify them.
          | Automation Category (Task Exposure %) | Eloundou et al. (2024) | Acemoglu (2024) | PWBM Baseline | PWBM Expanded |
          |---|---|---|---|---|
          | T0 (0%) | 0 | 0 | 0 | 0 |
          | T1 (0-50%) | 0.25 | 0 | 0 | 0.25 |
          | T2 (50-90%) | 0.5 | 0 | 0.7 | 0.7 |
          | T3 (90-99%) | 0.75 | 0.75 | 0.95 | 0.95 |
          | T4 (100%) | 1 | 1 | 1 | 1 |
          Acemoglu interprets these scores as reflecting the percentage of work in each category that can be automated by AI and replaces them with values of 0 percent, 25 percent, 50 percent, 75 percent, and 100 percent. As in our approach, he considers a task to be exposed to AI if more than 50 percent of its components could be performed by generative AI. However, he interprets a score of 0.5 on the Eloundou at al. metric (category T2) as a task for which AI could do 50 percent of the work – rather than 50 to 90 percent as in Eloundou at al.’s original definition – and so excludes the T2 category from his definition of exposed tasks. Ace
          
          [...]
          
          ’s original scores directly as weights, we obtain a GDP-weighted share of exposed tasks of about 38 percent – essentially the same as our 40 percent. Alternatively, if we expand our baseline approach and include tasks in category T1 with a weight of 0.25 as shown in the “PWBM Expanded” column of Table A1, our estimate rises to 48 percent (category T1 means AI can perform some of the task but less than 50 percent). This broader definition of exposure to AI implies a somewhat larger estimate of AI’s impact on TFP: an increase of 4.4 percent by 2075, compared with 3.7 percent in our baseline case.
          The sources for the technology adoption series plotted in Figure 3 are as follows:
          -
          PCs and Internet: Current Population Survey, Computer and Internet Use Supplement (CPS CIU) – The CPS is a household survey that has p
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q3-T1-004
    section: "Efficacy"
    sentence: "The adjustment process appears to involve task reallocation rather than outright displacement, with evidence from fields like accounting showing AI use correlates with a reallocation of roughly 9% of work hours from routine data entry to higher-value tasks.[3]"
    cited_evidence:
      - evidence_id: ev_007
        bibliography_num: 3
        url: "https://laweconcenter.org/resources/ai-productivity-and-labor-markets-a-review-of-the-empirical-evidence/"
        tier: T4
        span: '0-500'
        title: "AI, Productivity, and Labor Markets: A Review of the ..."
        span_text: |
          AI, Productivity, and Labor Markets: A Review of the Empirical Evidence Executive Summary Generative artificial intelligence (AI) has diffused with unusual speed since late 2022. By late 2024, nearly 40% of U.S. adults ages 18–64 reported using AI tools, a pace that exceeds comparable stages for personal computers and the internet. That rapid uptake has sharpened two policy questions: whether AI will generate measurable gains in output and productivity at the aggregate level, and whether the adjustment process will produce labor-market disruption large enough to justify new regulatory intervention. The empirical literature points to a clear pattern. Controlled field experiments and randomized trials document large productivity gains at the task and firm level, often alongside quality improvements. Across writing, customer support, software development, accounting, law, and translation, studies report 15% to more than 50% reductions in task-completion time, meaningful quality gains, and disproportionately large benefits for less-experienced workers, producing “skill compression” within occupations. At the same time, aggregate labor-market indicators through 2024–2025 show limited disruption, despite rapid adoption. Most datasets find little evidence of economywide job loss or wage decline. Where effects appear, they are concentrated in entry-level segments of highly exposed occupations, while senior employment remains largely stable. Adjustment to date has occurred through tas
          
          [...]
          
          annual global GDP over 10 years—roughly $7 trillion—based on broad occupational task exposure. Erkan Erdem and Dileep Birur (2025), using a dynamic computable general equilibrium framework, estimate that rapid adoption could raise U.S. GDP by about $2.48 trillion by 2030.3 Taken together, these forecasts differ less over data than over assumptions. Aggregate effects depend on three factors: diffusion across sectors, whether productivity gains expand output rather than reshuffle rents, and whether organizational redesi
          
          [...]
          
          rative records across 11 exposed occupations and find essentially zero effects on earnings or hours through 2024. U.S.-based evidence points in the same direction. Jonathan S. Hartley, Filip Jolevski, Vitor Melo, and Brendan Moore (2026) report that 35.9% of U.S. workers used generative AI by December 2025 and find small positive wage effects, with no statistically significant declines in job openings or employment in exposed occupations. Bharat Chandar’s (2025) Current Population Survey analysis si
          
          [...]
          
          ng that AI adoption correlates with an 18% increase in weekly client support and a reallocation of roughly 9% of work hours from routine data entry to higher-value tasks, such as client communication. AI use reduced monthly book-closing timelines by 7.5 days and increased ledger detail by 12%, indicating quality improvements alongside time savings. The authors also document complementarity between professional expertise and AI confidence scores: experienced accountants used model outputs to target 
          
          [...]
          
          ixed and that appropriate tool selection and workflow design can mitigate risks without restricting deployment. Software development studies show similarly large effects. Sida Peng et al. (2023) report that GitHub Copilot users complete coding tasks 55.8% faster in controlled settings, with larger gains among less experienced developers. Kevin Zheyuan Cui et al. (2025), studying nearly 5,000 developers across three large field experiments, find a 26.08% increase in weekly task completion, driven by higher adoption and disproportionately larger gains for junior developers. These findings undermine claims that AI primarily benefits top performers and instead show AI reducing frictions for early-care
          
          [...]
          
          mental evidence from translation extends the pattern. Ali Merali (2024) conducts a randomized trial with 300 professional translators and links increased training compute to economic outcomes. A tenfold increase in compute reduced completion time by 12.3%, improved quality by 0.18 standard deviations, and raised earnings per minute by 16.1%. Lower-skilled translators experienced gains roughly four times larger than their higher-skilled counterparts. The magnitude and replication of these effects across contexts suggest that productivity gains arise consistently in specific task catego
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q3-T1-005
    section: "Efficacy"
    sentence: "Furthermore, Canadian businesses investing in AI are 5.4 percentage points more likely to invest in employee training than non-adopting businesses, indicating a concurrent investment in human capital.[5]"
    cited_evidence:
      - evidence_id: ev_006
        bibliography_num: 5
        url: "https://www.cfib-fcei.ca/en/research-economic-analysis/ai-adoption"
        tier: T4
        span: '0-500'
        title: "AI Adoption and Workforce Training Investment in Canada"
        span_text: |
          AI is reshaping how firms operate, raising questions about how businesses invest in their workforce as these technologies are adopted. This blog shows that Canadian businesses investing in AI are more likely to invest in employee training, aligning AI adoption with ongoing investment in skills. Summary - AI adoption is rising: Nearly 45% of Canadian businesses use GenAI in their operations, increasing sharply with firm size. - AI is creating additional skill needs: Businesses that invest in AI are 5.4 percentage points more likely to invest in employee training. - People remain the priority: Nearly 8 in 10 businesses plan to maintain or increase training spending in 2026. Artificial intelligence (AI)1 is rapidly reshaping how businesses operate, from production lines to everyday decision-making. Generative AI, for instance, can significantly boost productivity: SMEs using such tools gain more than twice the time they invest each day─an average of 2.05 hours gained versus 0.97 spent.2 Debate over AI’s impact on jobs has intensified. Some warn that AI will replace workers, while others argue that AI is more likely to complement human labour by sparking new roles, enhancing productivity, and driving greater investment in people through reskilling and upskilling. Headlines about job cuts at major companies such as Amazon3 and Dow4 have only intensified the debate over whether AI is displacing workers or reinforcing the value of human expertise. To date, however, evidence points t
          
          [...]
          
           in employee training.7 The analysis accounts for basic differences between businesses—such as size, sector, and location—so the comparison reflects more than just who is bigger or more established. Figure 3 shows that businesses investing in AI are 5.4 percentage points more likely to invest in employee training than businesses that do not. While the findings do not distinguish between types of training, they do indicate that AI adopting businesses tend to rely on developing their workforce to sup
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q3-T1-006
    section: "Efficacy"
    sentence: "The empirical literature from controlled experiments consistently reports large productivity gains at the task level\u2014such as 40% increases in speed for professional writing, 56% faster coding, and 26% increases in software development task completion\u2014which disproportionately benefit less-experienced workers, producing skill compression within occupations.[4][3]"
    cited_evidence:
      - evidence_id: ev_007
        bibliography_num: 3
        url: "https://laweconcenter.org/resources/ai-productivity-and-labor-markets-a-review-of-the-empirical-evidence/"
        tier: T4
        span: '0-500'
        title: "AI, Productivity, and Labor Markets: A Review of the ..."
        span_text: |
          AI, Productivity, and Labor Markets: A Review of the Empirical Evidence Executive Summary Generative artificial intelligence (AI) has diffused with unusual speed since late 2022. By late 2024, nearly 40% of U.S. adults ages 18–64 reported using AI tools, a pace that exceeds comparable stages for personal computers and the internet. That rapid uptake has sharpened two policy questions: whether AI will generate measurable gains in output and productivity at the aggregate level, and whether the adjustment process will produce labor-market disruption large enough to justify new regulatory intervention. The empirical literature points to a clear pattern. Controlled field experiments and randomized trials document large productivity gains at the task and firm level, often alongside quality improvements. Across writing, customer support, software development, accounting, law, and translation, studies report 15% to more than 50% reductions in task-completion time, meaningful quality gains, and disproportionately large benefits for less-experienced workers, producing “skill compression” within occupations. At the same time, aggregate labor-market indicators through 2024–2025 show limited disruption, despite rapid adoption. Most datasets find little evidence of economywide job loss or wage decline. Where effects appear, they are concentrated in entry-level segments of highly exposed occupations, while senior employment remains largely stable. Adjustment to date has occurred through tas
          
          [...]
          
          annual global GDP over 10 years—roughly $7 trillion—based on broad occupational task exposure. Erkan Erdem and Dileep Birur (2025), using a dynamic computable general equilibrium framework, estimate that rapid adoption could raise U.S. GDP by about $2.48 trillion by 2030.3 Taken together, these forecasts differ less over data than over assumptions. Aggregate effects depend on three factors: diffusion across sectors, whether productivity gains expand output rather than reshuffle rents, and whether organizational redesi
          
          [...]
          
          rative records across 11 exposed occupations and find essentially zero effects on earnings or hours through 2024. U.S.-based evidence points in the same direction. Jonathan S. Hartley, Filip Jolevski, Vitor Melo, and Brendan Moore (2026) report that 35.9% of U.S. workers used generative AI by December 2025 and find small positive wage effects, with no statistically significant declines in job openings or employment in exposed occupations. Bharat Chandar’s (2025) Current Population Survey analysis si
          
          [...]
          
          ng that AI adoption correlates with an 18% increase in weekly client support and a reallocation of roughly 9% of work hours from routine data entry to higher-value tasks, such as client communication. AI use reduced monthly book-closing timelines by 7.5 days and increased ledger detail by 12%, indicating quality improvements alongside time savings. The authors also document complementarity between professional expertise and AI confidence scores: experienced accountants used model outputs to target 
          
          [...]
          
          ixed and that appropriate tool selection and workflow design can mitigate risks without restricting deployment. Software development studies show similarly large effects. Sida Peng et al. (2023) report that GitHub Copilot users complete coding tasks 55.8% faster in controlled settings, with larger gains among less experienced developers. Kevin Zheyuan Cui et al. (2025), studying nearly 5,000 developers across three large field experiments, find a 26.08% increase in weekly task completion, driven by higher adoption and disproportionately larger gains for junior developers. These findings undermine claims that AI primarily benefits top performers and instead show AI reducing frictions for early-care
          
          [...]
          
          mental evidence from translation extends the pattern. Ali Merali (2024) conducts a randomized trial with 300 professional translators and links increased training compute to economic outcomes. A tenfold increase in compute reduced completion time by 12.3%, improved quality by 0.18 standard deviations, and raised earnings per minute by 16.1%. Lower-skilled translators experienced gains roughly four times larger than their higher-skilled counterparts. The magnitude and replication of these effects across contexts suggest that productivity gains arise consistently in specific task catego
      - evidence_id: ev_002
        bibliography_num: 4
        url: "https://budgetmodel.wharton.upenn.edu/p/2025-09-08-the-projected-impact-of-generative-ai-on-future-productivity-growth/"
        tier: T4
        span: '0-500'
        title: "The Projected Impact of Generative AI on Future ..."
        span_text: |
          The Projected Impact of Generative AI on Future Productivity Growth
          The Projected Impact of Generative AI on Future Productivity Growth
          We estimate that AI will increase productivity and GDP by 1.5% by 2035, nearly 3% by 2055, and 3.7% by 2075. AI’s boost to annual productivity growth is strongest in the early 2030s but eventually fades, with a permanent effect of less than 0.04 percentage points due to sectoral shifts.
          Key Points
          -
          We estimate that 40 percent of current GDP could be substantially affected by generative AI. Occupations around the 80th percentile of earnings are the most exposed, with around half of their work susceptible to automation by AI, on average. The highest-earning occupations are less exposed, and the lowest-earning occupations are the least exposed.
          -
          AI’s boost to productivity growth is strongest in the early 2030s, with a peak annual contribution of 0.2 percentage points in 2032. After adoption saturates, growth reverts to trend. Because sectors that are more exposed to AI have faster trend TFP growth, sectoral shifts during the AI transition add a lasting 0.04 percentage point boost to aggregate growth.
          -
          Compounded, TFP and GDP levels are 1.5% higher by 2035, nearly 3% by 2055, and 3.7% by 2075, meaning that AI leads to a permanent increase in the level of economic activity.
          -
          Caution is required in interpreting these projections of AI’s impact, which are based on limited data on AI’s initial effects. Future data and developments in AI technolog
          
          [...]
          
          ile available for download provides exposure estimates for 784 detailed occupational categories that are aggregated in Table 1.
          | Occupation Group | Exposure to AI Automation (% of tasks) |
          |---|---|
          | Office and Administrative Support Occupations | 75.5 |
          | Business and Financial Operations Occupations | 68.4 |
          | Computer and Mathematical Occupations | 62.6 |
          | Sales and Related Occupations | 60.1 |
          | Management Occupations | 49.9 |
          | Legal Occupations | 47.5 |
          | Arts, Design, Entertainment, Sports, and Media Occupations | 45.8 |
          | Architecture and Engineering Occupations | 40.7 |
          | Life, Physical, and Social Science Occupations | 31.0 |
          | Educational Instruction and Library Occupations | 29.5 |
          | Community and Social Service Occupations | 27.5 |
          | Healthcare Practitioners and Technical Occupations | 23.1 |
          | Protective Service Occupations | 20.7 |
          | Transportation and Material Moving Occupations | 20.0 |
          | Food Preparation and Serving Related Occupations | 18.1 |
          | Personal Care and Service Occupations | 17.5 |
          | Healthcare Support Occupations | 15.5 |
          | Production Occupations | 14.4 |
          | Installation, Maintenance, and Repair Occupations | 13.1 |
          | Farming, Fishing, and Forestry Occupations | 9.7 |
          | Construction and Extraction Occupations | 8.9 |
          | Building and Grounds Cleaning and Maintenance Occupations | 2.6 |
          Source: PWBM based on estimates from Eloundou et al.’s (2024) and data from the Bureau of Labor Statistics.
          Figure 1 shows the distribution of employment by automation potential based on the categorization of tasks provided by Eloundou et al. (202
          
          [...]
          
          | 14% increase in task completion rate. |
          | Jabarian and Henkel (2025) | Job interviews with a generative AI voice agent. | 17% increase in job starts; 18% increase in retention rate. |
          | Noy and Zhang (2023) | Basic professional writing with ChatGPT-3.5. | 40% increase in speed; 18% increase in output quality. |
          | Peng et al. (2023) | JavaScript programming with GitHub Copilot. | 56% increase in speed. |
          | Cui et al. (2025) | Software development with GitHub Copilot. | 26% increase in task completi
          
          [...]
          
           increase in speed. |
          Sources: See links in the first column.
          AI’s impact on TFP depends on how quickly productivity-enhancing tools are actually adopted. Data on the diffusion of generative AI tools remains limited, but Bick et al. (2025) find that 26.4 percent of workers used generative AI at work in the second half of 2024, while 33.7 percent of adults used it outside of work. Using data from the Real-Time Population Survey (RPS), they show that early adoption patterns of AI for work are broadly similar to the adoption of personal computers (PCs) in the early 1980s.6
          Figure 3 com
          
          [...]
          
          f exposure to AI (based on the Eloundou et al. classification), we find that job growth has stagnated in occupations with most AI automation potential. For jobs that can be performed entirely by generative AI, employment fell sharply in 2024 and was 0.75 percent lower than in 2021 (however, recall from Figure 1 that these jobs make up only around 1 percent of total employment). In occupations with high AI exposure (90 to 99 percent of tasks can be automated) the shift has been less dramatic, but employment growth has slowed significantly since 2022.7
          Combining estimates of exposure, cost savings, and adoption, we project generative AI’s contribution to TFP growth over the next several decades. Figure 5 plots our projections. Despite examples of successful AI adoption such as those described in Table 2, we estimate that AI’s impact on TFP growth remains small today - 0.01 percentage points (pp) in 2025 - as most businesses have yet to deploy and gain experience with AI tools. Over the next decade, AI’s contribution will grow for three reasons:
          -
          Generative AI tools will increasingly be applied to tasks exposed to AI 
          
          [...]
          
          exposed to AI will rise due to long-running sectoral trends, with sectors relatively more exposed to AI (such as software development and professional services) growing faster than the rest of the economy.
          We project that AI will boost TFP growth by 0.09pp in 2027, 0.18pp in 2030, and peak in the early 2030s at around 0.2pp. As new adoption slows in the 2030s due to declining remaining opportunities to employ additional AI tools productively, the impact on TFP growth diminishes to around 0.1pp by end of the decade and continues to shrink thereafter. We project that TFP growth will be persistently higher by a little less than 0.04pp even after adoption saturates and TFP growth returns to trend. This occurs because sectors that were more exposed to AI also have faster trend TFP growth, and those sectors will make up a larger share of the economy as a result of AI-driven productivity gains.
          Source: PWBM
          Because these are growth effects, their cumulative impact – the impact on TFP levels – is what matters for living standards. Cumulating projected growth contributions implies that the level of TFP will be around 1.5% higher by 2035, 3% higher by 2055, and 3.7% higher by 2075 relative to a noAI path. Put differently, AI makes the economy permanently larger, but once adoption saturates, the ongoing growth rate itself returns to trend—aside from the small, persistent lift from sectors that benefit more from
          
          [...]
          
          of work that can be performed by AI. However, Eloundou at al. present another version of the metric in which they assign a numeric score to each category to facilitate comparisons with other quantities. As shown in Table A1, they assign values of 0, 0.25, 0.5, 0.75, and 1 to categories T0 through T4, respectively. This assignment treats each category as an equal increment of 0.25, rather than using the percentages from the original category definitions to quantify them.
          | Automation Category (Task Exposure %) | Eloundou et al. (2024) | Acemoglu (2024) | PWBM Baseline | PWBM Expanded |
          |---|---|---|---|---|
          | T0 (0%) | 0 | 0 | 0 | 0 |
          | T1 (0-50%) | 0.25 | 0 | 0 | 0.25 |
          | T2 (50-90%) | 0.5 | 0 | 0.7 | 0.7 |
          | T3 (90-99%) | 0.75 | 0.75 | 0.95 | 0.95 |
          | T4 (100%) | 1 | 1 | 1 | 1 |
          Acemoglu interprets these scores as reflecting the percentage of work in each category that can be automated by AI and replaces them with values of 0 percent, 25 percent, 50 percent, 75 percent, and 100 percent. As in our approach, he considers a task to be exposed to AI if more than 50 percent of its components could be performed by generative AI. However, he interprets a score of 0.5 on the Eloundou at al. metric (category T2) as a task for which AI could do 50 percent of the work – rather than 50 to 90 percent as in Eloundou at al.’s original definition – and so excludes the T2 category from his definition of exposed tasks. Ace
          
          [...]
          
          ’s original scores directly as weights, we obtain a GDP-weighted share of exposed tasks of about 38 percent – essentially the same as our 40 percent. Alternatively, if we expand our baseline approach and include tasks in category T1 with a weight of 0.25 as shown in the “PWBM Expanded” column of Table A1, our estimate rises to 48 percent (category T1 means AI can perform some of the task but less than 50 percent). This broader definition of exposure to AI implies a somewhat larger estimate of AI’s impact on TFP: an increase of 4.4 percent by 2075, compared with 3.7 percent in our baseline case.
          The sources for the technology adoption series plotted in Figure 3 are as follows:
          -
          PCs and Internet: Current Population Survey, Computer and Internet Use Supplement (CPS CIU) – The CPS is a household survey that has p
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q3-T1-007
    section: "Efficacy"
    sentence: "These micro-level gains have not yet translated into significant aggregate employment declines in Canada, as early evidence through late 2025 indicates job growth continued across exposure categories.[1][2]"
    cited_evidence:
      - evidence_id: ev_000
        bibliography_num: 1
        url: "https://www150.statcan.gc.ca/n1/pub/36-28-0001/2026001/article/00003-eng.htm"
        tier: T4
        span: '0-500'
        title: "Canadian employment trends in the era of generative ..."
        span_text: |
          Economic and Social Reports Canadian employment trends in the era of generative artificial intelligence: Early evidence DOI: https://doi.org/10.25318/36280001202600100003-eng Text begins Abstract Artificial intelligence (AI) holds the potential to transform the nature of work, and its ability to replace human labour remains a central concern. This study highlights recent labour market trends, distinguishing jobs potentially more exposed to and less complementary with AI from other jobs. From November 2022—when generative AI applications started gaining traction following the mass availability of ChatGPT—to December 2025, employment generally grew regardless of potential occupational exposure to and complementarity with AI. However, job growth varied across worker characteristics. Younger employees and those less educated generally saw weaker job growth over this period. Coding-intensive professions (e.g., software engineers and web designers) grew at a similar rate as other jobs. However, gains in coding-intensive jobs were concentrated among workers aged 30 to 49, while the number of coding professionals younger than 30 stagnated. From the fourth quarter of 2022 to the third quarter of 2025, job vacancies in occupations potentially more exposed to and less complementary with AI decreased at a similar rate as vacancies in occupations potentially less exposed to AI. Jobs potentially more exposed to AI regardless of complementarity are more likely to be higher-paying, associate
          
          [...]
          
          mplementarity across all occupations; otherwise, it is considered to have low complementarity. Sources: Statistics Canada, Labour Force Survey, January 2015 to December 2025; and Occupational Information Network. | |||||| | 2015 | |||||| | January | 76.7 | 78.9 | 96.5 | 79.3 | 88.4 | 98.5 | | February | 77.4 | 78.7 | 96.3 | 79.7 | 88.3 | 98.1 | | March | 78.9 | 77.3 | 96.1 | 79.8 | 87.7 | 99.2 | | April | 79.1 | 77.0 | 96.3 | 79.7 | 87.6 | 99.5 | | May | 79.2 | 78.0 | 95.9 | 80.2 | 86.9 | 98.9 | | June | 79.8 | 78.7 | 96.3 | 81.9 | 86.7 | 98.4 | | July | 80.1 | 79.3 | 95.8 | 81.8 | 87.3 | 98.1 | | August | 82.4 | 78.5 | 95.6 | 82.0 | 87.3 | 97.9 | | September | 82.5 | 79.1 | 95.2 | 82.1 | 87.6 | 97.1 | | October | 82.8 | 79.5 | 94.9 | 80.6 | 89.1 | 96.6 | | November | 82.3 | 78.2 | 94.8 | 82.3 | 88.0 | 96.7 | | December | 81.8 | 79.6 | 94.2 | 81.6 | 87.9 | 96.9 | | 2016 | |||||| | January | 81.7 | 79.3 | 94.2 | 81.1 | 87.9 | 99.0 | | February | 81.2 | 80.0 | 94.3 | 80.7 | 88.2 | 98.4 | | March | 81.0 | 81.3 | 93.7 | 80.7 | 88.7 | 98.4 | | April | 81.5 | 81.7 | 93.3 | 81.4 | 88.7 | 98.5 | | May | 82.1 | 81.5 | 93.7 | 81.1 | 89.2 | 98.5 | | June | 82.3 | 80.2 | 93.7 | 81.6 | 88.9 | 98.7 | | July | 82.2 | 80.9 | 93.4 | 81.1 | 88.3 | 100.1 | | August | 81.6 | 81.0 | 94.5 | 81.7 | 89.9 | 97.9 | | September | 81.2 | 80.9 | 95.2 | 81.5 | 90.1 | 98.4 | | October | 80.6 | 80.4 | 95.5 | 81.8 | 90.3 | 98.6 | | November | 80.0 | 81.8 | 96.0 | 81.2 | 90.8 | 98.8 | | December | 81.0 | 81.6 | 96.4 | 81.3 | 90.9 | 98.9 | | 2017 | |||||| | January | 81.9 | 80.6 | 96.8 | 81.6 | 93.0 | 98.7 | | February | 82.3 | 80.7 | 97.1 | 82.1 | 90.8 | 99.4 | | March | 83.6 | 80.4 | 97.4 | 82.3 | 91.1 | 99.0 | | April | 82.2 | 80.7 | 98.1 | 82.3 | 90.6 | 99.5 | | May | 81.4 | 81.4 | 98.3 | 83.1 | 90.7 | 100.4 | | June | 82.0 | 82.5 | 98.1 | 82.3 | 91.5 | 100.8 | | July | 82.7 | 81.8 | 98.0 | 83.1 | 92.2 | 100.7 | | August | 82.9 | 83.9 | 97.6 | 83.1 | 90.4 | 100.6 | | September | 82.9 | 84.0 | 97.3 | 83.3 | 90.3 | 101.2 | | October | 83.2 | 85.1 | 96.4 | 82.9 | 90.3 | 102.0 | | November | 85.3 | 82.3 |
      - evidence_id: ev_001
        bibliography_num: 2
        url: "https://lmic-cimt.ca/future-of-work/canadian-employment-trends-in-the-era-of-generative-artificial-intelligence-early-evidence/"
        tier: T4
        span: '0-500'
        title: "Canadian employment trends in the era of generative ..."
        span_text: |
          Title: Canadian employment trends in the era of generative artificial intelligence: Early evidence — LMIC-CIMT URL Source: https://lmic-cimt.ca/future-of-work/canadian-employment-trends-in-the-era-of-generative-artificial-intelligence-early-evidence/ Markdown Content: # Canadian employment trends in the era of generative artificial intelligence: Early evidence — LMIC-CIMT (https://lmic-cimt.ca/future-of-work/canadian-employment-trends-in-the-era-of-generative-artificial-intelligence-early-evidence/#fl-main-content) [LMIC-CIMT](https://lmic-cimt.ca/) [](https://lmic-cimt.ca/future-of-work/canadian-employment-trends-in-the-era-of-generative-artificial-intelligence-early-evidence/#) * [Publications](https://lmic-cimt.ca/publications-all/) * [Resources](https://lmic-cimt.ca/lmi-resources/) * [LMIC Dashboards](https://dashboards.lmic-cimt.ca/) * [Future of Work](https://lmic-cimt.ca/lmi-resources/future-of-work/) * [Events & Webinars](https://lmic-cimt.ca/lmi-resources/events/) * [Understanding Skills](https://lmic-cimt.ca/lmi-resources/skills/) * [WorkWords](https://lmic-cimt.ca/lmi-resources/workwords/) * [Canadian Job Trends Dashboard](https://lmic-cimt.ca/canadian-job-trends-dashboard/) * [About](https://lmic-cimt.ca/about/) * [About LMIC](https://lmic-cimt.ca/about/) * [Board of Directors](https://lmic-cimt.ca/about/board-of-directors/) * [LMIC Staff](https://lmic-cimt.ca/about/lmic-staff/) * [National Stakeholder Advisory Panel](https://lmic-cimt.ca/about/national-stakeholde
          
          [...]
          
          n trends shaping Canada's labour market. ## Canadian employment trends in the era of generative artificial intelligence: Early evidence January 28, 2026 | BY Mehdi, T., & Frenette, M. READ THE FULL ARTICLE AT THE SOURCE [Web Version](https://doi.org/10.25318/36280001202600100003-eng) Key Takeaway _Despite concerns that AI will lead to declines in the number of available jobs, early Canadian evidence shows no clear sign that jobs more exposed to AI are declining faster than others._ Research from Statist
          
          [...]
          
          The credential boom is here, but which ones actually help workers?](https://lmic-cimt.ca/future-of-work/the-credential-boom-is-here-but-which-ones-actually-help-workers/) February 3, 2026 | Escobari, M., & Seyal, I. Key Takeaway:_There are more than 1.5 million unique credentials now available. This growth has created a crowded, largely unregulated landscape in which workers struggle to distinguish high-value from low-value options._ [View Summary](https://lmic-cimt.ca/future-of-work/the-credential
          
          [...]
          
          ly for work tasks, creating a shadow economy that is outpacing formal organizational AI adoption._ [View Summary](https://lmic-cimt.ca/future-of-work/the-genai-divide-state-of-ai-in-business-2025/) [PDF Version](https://mlq.ai/media/quarterly_decks/v0.1_State_of_AI_in_Business_2025_Report.pdf) [Canadian employment trends in the era of generative artificial intelligence: Early evidence](https://lmic-cimt.ca/future-of-work/canadian-employment-trends-in-the-era-of-generative-artificial-intelligence-ea
          
          [...]
          
           clear sign that jobs more exposed to AI are declining faster than others._ [View Summary](https://lmic-cimt.ca/future-of-work/canadian-employment-trends-in-the-era-of-generative-artificial-intelligence-early-evidence/) [Web Version](https://doi.org/10.25318/36280001202600100003-eng) [How big a threat is AI to entry-level jobs?](https://lmic-cimt.ca/future-of-work/how-big-a-threat-is-ai-to-entry-level-jobs/) January 29, 2026 | The Economist Key Takeaway:_Generative AI may compress the traditional corpor
          
          [...]
          
          94%20LMIC-CIMT&tw_document_href=https%3A%2F%2Flmic-cimt.ca%2Ffuture-of-work%2Fcanadian-employment-trends-in-the-era-of-generative-artificial-intelligence-early-evidence%2F&tw_iframe_status=0&tw_order_quantity=0&tw_pid_src=1&tw_sale_amount=0&twpid=tw.1778497352493.828341044423509813&txn_id=o1i83&type=javascript&version=2.3.53)![Image 3](https://analytics.twitter.com/i/adsct?bci=3&dv=UTC%26en-US%26Google%20Inc.%26Linux%20x86_64%26255%26800%26600%268%2624%26800%26600%260%26na&eci=2&event_id=080996ad-4951-40fe-a95b-a4f9d2b72ec1&events=%5B%5B%22pageview%22%2C%7B%7D%5D%5D&
          
          [...]
          
          94%20LMIC-CIMT&tw_document_href=https%3A%2F%2Flmic-cimt.ca%2Ffuture-of-work%2Fcanadian-employment-trends-in-the-era-of-generative-artificial-intelligence-early-evidence%2F&tw_iframe_status=0&tw_order_quantity=0&tw_pid_src=1&tw_sale_amount=0&twpid=tw.1778497352493.828341044423509813&txn_id=o1i83&type=javascript&version=2.3.53)
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
