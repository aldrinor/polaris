Independent Tier-1 audit of 5 Q3 GenAI Workforce claims. Output YAML records only.

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

- Do NOT skip a claim. ALL 5 must have records.
- Do NOT auto-VERIFIED just because a span exists. Read the span_text and confirm the decimal is there.
- Do NOT exceed one paragraph of rationale per claim.

# Batch (the claims to audit are below; each has cited_evidence with span_text inline)

# Q3 batch 9: claims 57-61 (re-run with full direct_quote)
schema_version: tier1_v2
claims:
  - claim_id: Q3-T1-057
    section: "Long-term Outcomes"
    sentence: "For instance, in software development, one study found GitHub Copilot users completed coding tasks 55.8% faster in controlled settings, while another field experiment with nearly 5,000 developers reported a 26.08% increase in weekly task completion.[3]"
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

  - claim_id: Q3-T1-058
    section: "Long-term Outcomes"
    sentence: "This projection is based on an estimate that 40 percent of current GDP could be substantially affected by generative AI, with occupations around the 80th percentile of earnings being the most exposed.[4]"
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

  - claim_id: Q3-T1-059
    section: "Long-term Outcomes"
    sentence: "The aggregate labor market adjustment to date has occurred through task reallocation rather than mass job loss, with evidence concentrated in entry-level segments of highly exposed occupations while senior employment remains stable.[3]"
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

  - claim_id: Q3-T1-060
    section: "Long-term Outcomes"
    sentence: "AI use reduced monthly book-closing timelines by 7.5 days and increased ledger detail by 12%.[3]"
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

  - claim_id: Q3-T1-061
    section: "Long-term Outcomes"
    sentence: "Long-term macroeconomic projections estimate AI will increase productivity and GDP, with a peak annual contribution to productivity growth of 0.2 percentage points in the early 2030s before growth reverts to trend, and compounded TFP and GDP levels are 1.5% higher by 2035, nearly 3% by 2055, and 3.7% by 2075.[4]"
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


# Output

Single YAML block. List of records in claim_id order. Then a summary:

```yaml
- claim_id: ...
  ...
- claim_id: ...
  ...

batch_summary:
  total: 5
  per_verdict: {VERIFIED: N, PARTIAL: N, UNSUPPORTED: N, FABRICATED: N, UNREACHABLE: N}
  per_context_match: {yes: N, partial: N, no: N}
  notable: ["..."]
```

Output the YAML directly. No commentary outside.
