# DEEP ROOT-CAUSE PACK — why our gate scores ~0.36-0.40 while champion reaches 0.4447-0.51

OPERATOR THESIS TO TEST: a well-prompted LLM generates clean report prose; a CHAIN OF POST-GENERATION FUNCTIONS mangles it — strict_verify (faithfulness) DROPS true content, render INJECTS chrome the LLM never wrote. The prior audit was SLOPPY (invented a 'deferral-pointer disease' that does NOT exist; retreated to cosmetic strip-fixes instead of the faithfulness ghost). Audit the CODE + DROPS + TEXT line by line, and find the ROOT CAUSE + ROOT FIX to earn back 0.4447+.

HARD FACTS (run B, faithfulness-ON, RACE 0.3610, verified from checkpoints):
- Raw LLM draft = 5823 words / ~145 sentences of dense CITED prose -> Final scored = 4549 words. NET pipeline = -1274 words (-22%).
- strict_verify: 147 sentences DROPPED, 55 verified. Only 2 CONTRADICTED in the whole report.
- drop_reason_counts: entailment_failed(NEUTRAL) 66 | no_integer_overlap 21 | percent_not_in_cited_span 15 | no_content_word_overlap 11 | number_not_in_any_cited_span 9 | binding_qualifier 8 | temporal_scope_mismatch 1.
- INJECTED-BY-RENDER (absent from raw draft, present in final): '# Research report: <raw prompt>' title; 'STRONGEST VERIFIER...UNVERIFIED-by-D8' banner; 'Completeness checklist: 0/0' telemetry.
SCORES: A(faith OFF) 0.3992 | B(faith ON) 0.3610 | champ_ourcorpus 0.3671 | polaris_step3_control(TRUE CHAMPION) 0.4447 | fable5_scoped_calibration 0.5065.

AUDIT QUESTIONS (answer each with quoted evidence):
1. Read the 34 DROPPED sentences below + reasons. Were they GOOD content (true, specific, on-topic, insight-bearing) that strict_verify wrongly killed, or genuinely bad? Quantify how much Insight/Comp the 147 drops cost.
2. Is the number-mismatch class (45 drops: correct number, not in the exact cited byte-span) a FAITHFULNESS win or a self-inflicted wound? 
3. Compare RAW draft (Evidence 2) vs FINAL (Evidence 3): what exactly did verify+render do? Confirm the banner/title/telemetry are render-injected, not LLM.
4. Compare FINAL B vs TRUE CHAMPION (Evidence 4): what does champion's text have that ours lost — is it the corpus, the composition, or the post-processing damage?
5. ROOT CAUSE: name the specific function(s) doing the damage (strict_verify drop rule, render title/banner/appendix, dedup). ROOT FIX: how to let the clean LLM draft survive to the scored text WITHOUT abandoning genuine faithfulness — regenerate-not-drop? fix the number-offset matcher? strip render chrome from the SCORED text? Rank by RACE leverage.
6. Is the operator right that faithfulness is the invisible killer, or is the render chrome the bigger loss? Adjudicate with numbers.

## ===== EVIDENCE 1: 34 actual DROPPED sentences (what the ghost killed) + reasons =====

[DROP 1] sec='AI and the Fourth Industrial Revolutio'
  SENTENCE: The concept of Industry 4.0, which debuted at the 2011 Hannover Fair, encompasses a suite of enabling technologies including cyber-physical systems, cloud computing, robotics, the Internet of Things, big data analytics, and AI, all of which are merging physical, cyber, and biological systems [#ev:ev
  REASON: entailment_failed:ev_225,ev_256:verdict=NEUTRAL:reason=The SENTENCE introduces specific details like the 2011 Hannover Fair, cyber-phys

[DROP 2] sec='AI and the Fourth Industrial Revolutio'
  SENTENCE: The McKinsey Global Institute forecasts that automation could displace 75 to 375 million workers by 2030 [#ev:ev_225:2700-3500], and one analysis cites projections of the disappearance of 800 million jobs by 2030 [#ev:ev_128:600-1400].
  REASON: no_integer_overlap_any_cited_span:ev_128,ev_225:missing=['375']

[DROP 3] sec='AI and the Fourth Industrial Revolutio'
  SENTENCE: Retail sales occupations declined from 7.5% to 5.7% of US employment between 2013 and 2023, a reduction of 25%, while labor productivity growth in retail trade surged to between 4 and 5% in recent years compared to the 2% average across all sectors [#ev:ev_307:8600-9400].
  REASON: binding_qualifier_dropped:ev_307

[DROP 4] sec='AI and the Fourth Industrial Revolutio'
  SENTENCE: More recent evidence from AI-specific exposure measures finds that occupations with higher observed AI exposure are projected by the BLS to grow less through 2034, with BLS growth projections dropping by 0.6 percentage points for every 10 percentage point increase in AI coverage [#ev:ev_312:2300-310
  REASON: entailment_failed:ev_312:verdict=NEUTRAL:reason=The SENTENCE adds specificities not present in the SPAN, such as 'AI-specific ex

[DROP 5] sec='AI and the Fourth Industrial Revolutio'
  SENTENCE: Workers in the most AI-exposed professions are more likely to be older, female, more educated, and higher-paid, earning 47% more on average than less-exposed workers [#ev:ev_312:0-800].
  REASON: no_integer_overlap_any_cited_span:ev_312:missing=['47']

[DROP 6] sec='AI and the Fourth Industrial Revolutio'
  SENTENCE: The post-1987 weakening of wage growth and changing displacement effects are detailed under AI and the Fourth Industrial Revolution: Context for Labor Market Transformation [#ev:ev_001:10000-10800].
  REASON: no_integer_overlap_any_cited_span:ev_001:missing=['-1987']

[DROP 7] sec='How AI Technologies Displace and Creat'
  SENTENCE: AI, as a core area of the fourth industrial revolution, simultaneously displaces and creates jobs through mechanisms that scholars characterize as both "destructive" and "creative" [#ev:ev_241:300-1100][#ev:ev_055:600-1400].
  REASON: entailment_failed:ev_055,ev_241:verdict=NEUTRAL:reason=The SENTENCE introduces specific claims about 'AI' and 'simultaneously displaces

[DROP 8] sec='How AI Technologies Displace and Creat'
  SENTENCE: Acemoglu and Restrepo's task-based framework identifies a displacement effect, whereby capital takes over tasks previously performed by labor, and a reinstatement effect, whereby new technologies generate new labor-demanding tasks [#ev:ev_165:1300-2100][#ev:ev_001:9200-10000].
  REASON: entailment_failed:ev_001,ev_165:verdict=NEUTRAL:reason=The span mentions 'new task generation' but does not explicitly mention the 'rei

[DROP 9] sec='How AI Technologies Displace and Creat'
  SENTENCE: From 1987 to 2017, however, displacement accelerated to 0.7 percent per year while reinstatement slowed to 0.35 percent per year, contributing to weaker wage growth of 1.3 percent per year [#ev:ev_165:0-800][#ev:ev_001:0-800].
  REASON: number_not_in_any_cited_span:ev_001,ev_165:missing=['0.35', '0.7', '1.3']

[DROP 10] sec='How AI Technologies Displace and Creat'
  SENTENCE: One analysis projects that automation could displace between 75 and 375 million workers globally by 2030 [#ev:ev_225:2700-3500], while another estimates the disappearance of 800 million jobs by the same year [#ev:ev_128:600-1400].
  REASON: no_integer_overlap_any_cited_span:ev_128,ev_225:missing=['375']

[DROP 11] sec='How AI Technologies Displace and Creat'
  SENTENCE: In the US retail sector, retail sales occupations declined by 850,000 jobs between 2013 and 2023, with their employment share dropping from 7.5 to 5.7 percent, a reduction of 25 percent [#ev:ev_307:8100-8900].
  REASON: binding_qualifier_dropped:ev_307

[DROP 12] sec='How AI Technologies Displace and Creat'
  SENTENCE: STEM employment grew from 6.5 percent of all jobs in 2010 to nearly 10 percent in 2024, an increase of more than 50 percent, reflecting rising demand for new technical skills [#ev:ev_307:1100-1900].
  REASON: entailment_failed:ev_307:verdict=NEUTRAL:reason=The SENTENCE adds the explanation 'reflecting rising demand for new technical sk

[DROP 13] sec='How AI Technologies Displace and Creat'
  SENTENCE: Occupations with higher observed AI exposure are projected by the BLS to grow less through 2034, with every 10 percentage point increase in AI coverage associated with a 0.6 percentage point drop in projected occupational growth [#ev:ev_312:2300-3100].
  REASON: entailment_failed:ev_312:verdict=NEUTRAL:reason=The sentence adds the specific timeframe 'through 2034' which is not present in 

[DROP 14] sec='How AI Technologies Displace and Creat'
  SENTENCE: Despite this, workers in the most AI-exposed professions earn 47 percent more on average and are more likely to be female, more educated, and higher-paid, and no systematic increase in unemployment has been observed for highly exposed workers since late 2022 [#ev:ev_312:0-800].
  REASON: no_integer_overlap_any_cited_span:ev_312:missing=['47']

[DROP 15] sec='How AI Technologies Displace and Creat'
  SENTENCE: In developing nations, however, the fourth industrial revolution poses additional challenges including lack of trained and skilled workforce, infrastructure deficits, and funding constraints that may limit the job-creation potential of AI [#ev:ev_256:2900-3700].
  REASON: entailment_failed:ev_256:verdict=NEUTRAL:reason=The sentence introduces the concept of 'job-creation potential of AI', which is 

[DROP 16] sec='How AI Technologies Displace and Creat'
  SENTENCE: The increased adoption of new and frontier technologies, at an 86.2 percent rate, is identified as the most affecting macro trend driving business transformation, underscoring the urgency of understanding how AI restructures labor markets across sectors [#ev:ev_225:500-1300].
  REASON: entailment_failed:ev_225:verdict=NEUTRAL:reason=The sentence introduces the specific claim about AI restructuring labor markets 

[DROP 17] sec='How AI Technologies Displace and Creat'
  SENTENCE: The 1947–1987 displacement and reinstatement effects are detailed under AI and the Fourth Industrial Revolution: Context for Labor Market Transformation [#ev:ev_165:4200-5000][#ev:ev_001:9700-10500].
  REASON: entailment_failed:ev_001,ev_165:verdict=NEUTRAL:reason=The SENTENCE introduces a specific context or section title ('AI and the Fourth 

[DROP 18] sec='How AI Technologies Displace and Creat'
  SENTENCE: Manufacturing displacement effects over this later period are detailed under AI and the Fourth Industrial Revolution: Context for Labor Market Transformation [#ev:ev_165:6000-6800].
  REASON: entailment_failed:ev_165:verdict=NEUTRAL:reason=The SENTENCE introduces a specific heading or context ('AI and the Fourth Indust

[DROP 19] sec='How AI Technologies Displace and Creat'
  SENTENCE: The 13-fold surge in global AI business investment through 2023 is detailed under AI and the Fourth Industrial Revolution: Context for Labor Market Transformation [#ev:ev_000:1200-2000].
  REASON: entailment_failed:ev_000:verdict=NEUTRAL:reason=The SENTENCE introduces a specific section title not present in the SPAN.

[DROP 20] sec='Skill Demand and Wage Impacts of AI Ad'
  SENTENCE: AI adoption is fundamentally reshaping the task content of production across occupations, generating both displacement and reinstatement effects that alter skill demand and wages.
  REASON: no_provenance_token

[DROP 21] sec='Skill Demand and Wage Impacts of AI Ad'
  SENTENCE: By contrast, from 1987 to 2017, the displacement effect accelerated to 0.7 percent per year while reinstatement slowed to 0.35 percent per year, and wage growth stagnated at 1.33 percent per year [#ev:ev_165:0-800][#ev:ev_001:0-800].
  REASON: number_not_in_any_cited_span:ev_001,ev_165:missing=['0.35', '0.7', '1.33']

[DROP 22] sec='Skill Demand and Wage Impacts of AI Ad'
  SENTENCE: Skill-biased technological change has driven a widening college wage premium, with the share of hours worked by college-educated workers nearly doubling from 20 percent in 1979 to 39 percent in 2018, and the experience premium rising from roughly 67 percent in 1980 to 91 percent in 2018 [#ev:ev_001:
  REASON: no_integer_overlap_any_cited_span:ev_001:missing=['67', '91']

[DROP 23] sec='Skill Demand and Wage Impacts of AI Ad'
  SENTENCE: Conversely, retail sales occupations declined from 7.5 percent to 5.7 percent of employment between 2013 and 2023, a 25 percent reduction, while labor productivity in retail trade surged to between 4 and 5 percent annually in recent years compared to the 2 percent average across all sectors [#ev:ev_
  REASON: binding_qualifier_dropped:ev_307

[DROP 24] sec='Skill Demand and Wage Impacts of AI Ad'
  SENTENCE: The McKinsey Global Institute forecasts that automation could displace 75 to 375 million workers by 2030, with one source citing a figure of 800 million jobs potentially disappearing by 2030, reflecting the scale of occupational restructuring anticipated across sectors [#ev:ev_225:2700-3500][#ev:ev_
  REASON: no_integer_overlap_any_cited_span:ev_128,ev_225:missing=['375']

[DROP 25] sec='Skill Demand and Wage Impacts of AI Ad'
  SENTENCE: Contradictions around labor replacement, skills gaps, and increasing digital divides have been identified, especially in developing economies, underscoring that the wage and skill impacts of AI adoption vary significantly by occupation and regional context [#ev:ev_279:2400-3200].
  REASON: entailment_failed:ev_279:verdict=NEUTRAL:reason=The sentence introduces specific claims about wage and skill impacts of AI adopt

[DROP 26] sec='Skill Demand and Wage Impacts of AI Ad'
  SENTENCE: Manufacturing displacement effects over this later period are documented under AI and the Fourth Industrial Revolution: Context for Labor Market Transformation [#ev:ev_165:6000-6800].
  REASON: entailment_failed:ev_165:verdict=NEUTRAL:reason=The SENTENCE introduces a specific document or section title not mentioned in th

[DROP 27] sec='Skill Demand and Wage Impacts of AI Ad'
  SENTENCE: The absence of systematic unemployment increases for highly AI-exposed workers is detailed under AI and the Fourth Industrial Revolution: Context for Labor Market Transformation [#ev:ev_312:0-800].
  REASON: entailment_failed:ev_312:verdict=NEUTRAL:reason=The SENTENCE introduces a specific section title or context not present in the S

[DROP 28] sec='Skill Demand and Wage Impacts of AI Ad'
  SENTENCE: The 1947–1987 displacement and reinstatement effects are documented under AI and the Fourth Industrial Revolution: Context for Labor Market Transformation [#ev:ev_165:4200-5000].
  REASON: entailment_failed:ev_165:verdict=NEUTRAL:reason=The sentence introduces a specific context or title, 'AI and the Fourth Industri

[DROP 29] sec='Skill Demand and Wage Impacts of AI Ad'
  SENTENCE: STEM employment growth from 2010 to 2024 is detailed under AI and the Fourth Industrial Revolution: Context for Labor Market Transformation [#ev:ev_307:1200-2000].
  REASON: entailment_failed:ev_307:verdict=NEUTRAL:reason=The SENTENCE introduces a specific section title or context ('AI and the Fourth 

[DROP 30] sec='AI's Labor Market Effects Versus Previ'
  SENTENCE: One analysis forecasts that automation could displace 75 to 375 million workers by 2030, reflecting concerns first articulated by Keynes in 1930 about technological unemployment [#ev:ev_225:2700-3500].
  REASON: no_integer_overlap_any_cited_span:ev_225:missing=['375']

[DROP 31] sec='AI's Labor Market Effects Versus Previ'
  SENTENCE: Nevertheless, significant restructuring is underway: STEM employment grew from 6.5 percent of all jobs in 2010 to nearly 10 percent in 2024, an increase of more than 50 percent, while retail sales occupations declined from 7.5 percent to 5.7 percent of employment between 2013 and 2023 [#ev:ev_307:0-
  REASON: number_not_in_any_cited_span:ev_307:missing=['5.7', '6.5', '7.5']

[DROP 32] sec='AI's Labor Market Effects Versus Previ'
  SENTENCE: Recent measurement efforts using actual AI usage data find that occupations with higher observed AI exposure are projected by the Bureau of Labor Statistics to grow less through 2034, with BLS growth projections dropping by 0.6 percentage points for every 10 percentage point increase in AI coverage 
  REASON: entailment_failed:ev_312:verdict=NEUTRAL:reason=The SENTENCE introduces specificities not present in the SPAN, such as 'actual A

[DROP 33] sec='AI's Labor Market Effects Versus Previ'
  SENTENCE: An emerging body of scholarship further posits that AI has the potential to significantly alter political and economic landscapes within states by reconfiguring labor markets, indicating that the labor market effects of the fourth industrial revolution may extend beyond economics into broader societ
  REASON: entailment_failed:ev_055:verdict=NEUTRAL:reason=The SENTENCE introduces the specific claim that labor market effects of the four

[DROP 34] sec='AI's Labor Market Effects Versus Previ'
  SENTENCE: The four rounds of technological revolution and automation dynamics are detailed under AI and the Fourth Industrial Revolution: Context for Labor Market Transformation [#ev:ev_241:0-800].
  REASON: entailment_failed:ev_241:verdict=NEUTRAL:reason=The SENTENCE introduces a specific section title and the term 'AI' which are not

(34 of 147 shown)

## ===== EVIDENCE 2: RAW LLM DRAFT run B (pre-verify, first ~1800w — CLEAN, no chrome) =====
AI Adoption Rates and Employment Outcomes by Industry

AI and the Fourth Industrial Revolution: Context for Labor Market Transformation

AI's Labor Market Effects Versus Previous Industrial Revolutions

Employer Strategies and Worker Transitions in AI-Driven Workforce Restructuring

Forecasted AI Labor Market Outcomes and the Future of Work

How AI Technologies Displace and Create Jobs Across Sectors

Labor Market Polarization and Inequality from AI Restructuring

Skill Demand and Wage Impacts of AI Adoption by Occupation

Synthesis: AI's Role in Restructuring the Labor Market Within the Fourth Industrial Revolution

## ===== EVIDENCE 3: FINAL SCORED TEXT run B (0.3610) =====
# Research report: Please write a literature review on the restructuring impact of Artificial Intelligence (AI) on the labor market. Focus on how AI, as a key driver of the Fourth Industrial Revolution, is causing significant disruptions and affecting various industries. Ensure the review only cites high-quality, English-language journal articles.

> **STRONGEST VERIFIER (four-role D8) DID NOT RUN for this run — findings are UNVERIFIED-by-D8.**
>
> The four-role D8 adjudication (the strongest faithfulness verifier) did not bind for this run, so the findings below carry only the strict_verify / span-grounding / NLI evidence — NOT the final D8 adjudication. Treat them as UNVERIFIED-by-D8 pending a re-judge. See `manifest.json` (`release_disclosure`) for the per-run disclosure detail.

This report reviews the available evidence on How is Artificial Intelligence restructuring the labor market across various industries? What is the role of AI in driving labor market disruptions as part of the Fourth Industrial Revolution?. It synthesizes the findings that survived span-level verification, organized by theme; each cited claim is carried verbatim from a source span. Methods, source-hygiene disclosures, and the reliability audit are collected in the appendix at the end.

## Introduction and Scope

Scope: this review is bounded to the question of How is Artificial Intelligence restructuring the labor market across various industries? It reports only claims that passed span-level verification; unverified or off-topic material is excluded from the findings and disclosed in the appendix.

### AI and the Fourth Industrial Revolution: Context for Labor Market Transformation

Artificial intelligence is widely identified as a core driver of the Fourth Industrial Revolution, situated alongside the earlier transformations wrought by mechanical, electric power, and information technologies. This convergence is already reshaping production processes and manufacturing systems, transforming firms into smart factories and significantly altering the nature of work and the relationship between employees and employers. The economic stakes are substantial: AI's potential in task automation, process optimization, and decision-making enhancement is expected to generate annual economic value ranging from 3.5 to 5.8 trillion USD across industries. Global business investment in AI increased 13-fold from US$14.57 billion in 2013 to US$189 billion in 2023, with 35% of businesses already using AI in their operations and more than 50% intending to implement AI technologies. The labor market implications of this transformation are framed by longstanding debates over technological unemployment, a concept John Maynard Keynes predicted in 1930. Since the outbreak of the industrial revolution, human society has undergone four rounds of technological revolution, and each technological change can be regarded as the deepening of automation technology, with the conflict and subsequent rebalancing of efficiency and employment constantly repeated in the process of replacing people with machines. Schumpeter's innovation theory captures this duality, positing that technological innovation forms from the unity of positive and negative feedback and the oneness of opposites such as "revolutionary" and "destructive". Negative effects identified in the literature include increasing structural unemployment and inequality, decreasing job opportunities, a lack of skilled people for the changing labor market, and short-term job losses. In the United States between 1947 and 1987, the displacement effect reduced labor demand at about 0.48% per year, but this was offset by an equally strong reinstatement effect of 0.47% per year and productivity growth of 2.4% per year, yielding wage bill growth of 2.5% per year. In manufacturing specifically, the displacement effect reduced labor demand at about 1.1% per year, or about 30% cumulatively over this later period. The pace of structural change in the US labor market has, perhaps surprisingly, slowed over time; the years spanning 1990 to 2017 were less disruptive than any prior period measured going back to 1880. Nevertheless, recent shifts are evident: STEM employment grew from 6.5% of all jobs in 2010 to nearly 10% in 2024, an increase of more than 50%. As of late 2022, there has been no systematic increase in unemployment for highly exposed workers, though there is suggestive evidence that hiring of younger workers has slowed in exposed occupations. The Fourth Industrial Revolution poses particular challenges for developing nations, where adoption is constrained by inadequate infrastructure, a lack of trained and skilled workforce, scalability difficulties, and funding limitations. Research on AI and job displacement is growing globally, with major contributions from China, the United States, and Germany. A systematic literature review covering 2015 to July 2025 identifies three core themes: trends in AI-induced labor displacement including task automation, skill polarization, and industry-specific disruptions in sectors such as healthcare, education, and creative industries; the adverse roles of AI technologies particularly affecting white-collar professionals, gig workers, and freelancers; and existing mitigation strategies including responsible AI guidelines aimed at balancing technological advancement with employment protection. Current measures, however, remain fragmented and insufficient to address the structural risks of workforce displacement. In Mauritius, research examines how rapid technological innovations, particularly AI and digital transformation, affect employees' employability during the Fourth Industrial Revolution, highlighting the complex relationship between technology, employability, and career development in a small island developing economy. An emerging field of scholarship posits that AI has the potential to significantly alter political and economic landscapes within states by reconfiguring labor markets and economies, suggesting that the labor market transformations driven by AI extend beyond purely economic dimensions to encompass broader social and political consequences. A task-based framework developed by Acemoglu and Restrepo describes a displacement effect, whereby capital takes over tasks previously performed by labor, and new task generation.

**Tension** Schumpeter's innovation theory captures this duality, positing that technological innovation forms from the unity of positive and negative feedback and the oneness of opposites such as "revolutionary" and "destructive".

### How AI Technologies Displace and Create Jobs Across Sectors

Sector-specific disruptions are evident: AI-driven automation is reshaping employment in healthcare, education, and creative industries, while also affecting white-collar professionals, gig workers, and freelancers by increasing precarity and skill mismatches. Simultaneously, downstream job creation has occurred: light delivery service truck drivers grew by 29 percent, and "stockers and order fillers" increased from 1.8 million to 2.8 million jobs, a rise of nearly 60 percent, fueled in part by AI-powered e-commerce warehouse operations. The effects of Industry 4.0 on employment are not universally negative; in some cases, technological investments enhance employment rates by creating new professions and job opportunities. Occupations requiring human judgment, decision-making, creativity, and innovation exhibit resilience to technological advancements.

### Skill Demand and Wage Impacts of AI Adoption by Occupation

The BLS corroborates this productivity slowdown, reporting that productivity grew at 2.8 percent annually between 1947 and 1973 but only 1.3 percent from 2007 to 2017. AI simultaneously automates routine tasks and expands employee skills, increasing labor productivity while altering the relative value of different occupational capabilities. New downstream occupations have emerged from AI-powered e-commerce, as light delivery service truck drivers grew by 29 percent and stockers and order fillers increased from 1.8 million to 2.8 million jobs between 2013 and 2023. Occupations requiring human judgment, decision-making, creativity, and innovation exhibit resilience to technological advancements, while automation is leading to a decline in low- and medium-skilled occupations and a widening of the pay gap between middle- and high-skilled workers. Digital technology, artificial intelligence, and robot encounters are helping to train skilled robots and raise their relative wages. A regression at the occupation level weighted by current employment finds that growth projections are somewhat weaker for jobs with more observed exposure, such that for every 10 percentage point increase in coverage, the BLS's growth projection drops by 0.6 percentage points. Workers in the most AI-exposed professions earn 47 percent more on average than those in less exposed occupations, are 16 percentage points more likely to be female, and have higher levels of education, with graduate-degree holders constituting 17.4 percent of the most exposed group versus 4.5 percent of the unexposed group. One analysis notes that in a machine-for-machine employment model, new and currently unrealized job roles will emerge.

### AI's Labor Market Effects Versus Previous Industrial Revolutions

However, this process also involves "creative destruction," where the iterative renewal of new technologies simultaneously creates and destroys employment opportunities. Other projections suggest the disappearance of 800 million jobs by 2030 due to Industry 4.0, alongside increasing structural unemployment and inequality. Notably, workers in the most AI-exposed professions are 16 percentage points more likely to be female and earn 47 percent more on average than less-exposed workers, suggesting that AI's displacement effects may increasingly target higher-skilled, higher-paid occupations, a departure from the historical pattern where automation primarily displaced low- and medium-skilled workers. Artificial intelligence is one of the core areas of the fourth industrial revolution, along with the transformation of mechanical technology, electric power technology, and information technology.

### AI Adoption Rates and Employment Outcomes by Industry

The increased adoption of new and frontier technologies has been identified as the most affecting macro trend in driving business transformation, with a rate of 86.2%. Occupations with more observed exposure are projected by the BLS to grow less, with growth projections dropping by 0.6 percentage points for every 10 percentage point increase in coverage. AI-driven automation is reshaping employment, with algorithms optimizing investment methods in finance while AI-powered robotics improves production efficiency in manufacturing.

### Labor Market Polarization and Inequality from AI Restructuring

The consequence has been a deceleration of wage bill growth to 1.33 percent per year, coupled with weaker productivity growth of 1.54 percent per year compared to 2.4 percent per year in the earlier period. However, contradictions around labor replacement, skills gaps, and an increasing digital divide have been identified, especially in developing economies that lack trained and skilled workforces. Current mitigation strategies remain fragmented and insufficient to address the structural risks of workforce displacement, even as a growing body of policy responses encourages human-AI complementarity. This negative shift has been particularly pronounced in manufacturing, where the displacement effect reduced labor demand at about 1.1 percent per year. Occupations with more observed exposure are projected by the BLS to grow somewhat less, with every 10 percentage point increase in coverage associated with a 0.6 percentage point decline in growth projections.

**Tension** However, contradictions around labor replacement, skills gaps, and an increasing digital divide have been identified, especially in developing economies that lack trained and skilled workforces.

### Employer Strategies and Worker Transitions in AI-Driven Workforce Restructuring

The most affecting macro trend in driving business transformation is the increased adoption of new and frontier technologies, reported at an 86.2% rate according to the Future of Jobs Report 2023. Employers face a lack of skilled people for the changing labor market, with new skills and training requirements emerging as central challenges alongside the need for labor market restructuring towards tertiary sectors. Small and medium-sized enterprises, which represent 99% of registered companies in Europe, face financial and knowledge constraints as key barriers to Industry 4.0 adoption, despite recognizing flexibility, cost reduction, efficiency, quality, and competitive advantage as key benefits. Mitigation strategies proposed in the literature focus on responsib

## ===== EVIDENCE 4: TRUE CHAMPION polaris_step3_control (0.4447) full text =====
# A literature review on the restructuring impact of Artificial Intelligence (AI) on the labor market

This report synthesizes the retrieved research evidence on the question above. It is organized as a coherent review: an introduction that frames the scope, thematic sections that group the evidence by sub-topic, a cross-study synthesis that surfaces where the findings agree and conflict, and a closing discussion of conclusions and open research gaps. Every quantitative claim is span-grounded to a cited source; claims that could not be verified against the underlying evidence were removed rather than paraphrased.

## Introduction and Scope

The Fourth Industrial Revolution, a term popularized by Klaus Schwab in 2016, is characterized by a fusion of technologies that blurs the lines between the physical, digital, and biological spheres, distinguishing it from previous industrial revolutions through its unprecedented velocity, scope, and systems impact. Artificial intelligence sits at the center of this transformation, acting as a key driver that orchestrates technologies such as robotics, automated vehicles, and real-time data analytics to redefine how work is performed across industries. Global business investment in AI increased 13-fold from US$14.57 billion in 2013 to US$189 billion in 2023, with 35% of businesses already using AI in their operations and more than 50% intending to implement AI technologies. This rapid diffusion has prompted predictions that STARA—smart technology, artificial intelligence, robotics, and algorithms—will replace a third of jobs that exist today, with forecasts that by 2025, 85 million jobs may be displaced while 97 million new roles may emerge that are adapted to the new division of labor between humans, machines, and algorithms. Similarly, the World Economic Forum has predicted that AI adoption will make 75 million jobs redundant and create 133 million new ones worldwide by 2022, while economic analyses from PwC, IBM, Deloitte, and Gartner Research project that AI will increase global GDP by 15% by 2030, adding approximately $15.7 trillion. A separate Future of Jobs report projected that 7.1 million jobs will be lost across 15 economic areas from 2015 to 2020, while 2.1 million additional jobs are expected to be created in business, financial operations, management, and computer and mathematical roles during the same period. The net impact on labor demand depends on how these effects weigh against each other, and the authors find that the sharp slowdown of US wage bill growth over the last three decades is a consequence of weaker-than-usual productivity growth combined with significant shifts in the task content of production against labor, with stronger displacement effects and considerably weaker reinstatement effects in recent decades. The scope of this disruption spans multiple sectors, with AI-driven automation reshaping employment through task automation, skill polarization, and industry-specific disruptions in healthcare, education, and creative industries, while also affecting white-collar professionals, gig workers, and freelancers by increasing precarity and skill mismatches. Industrial robots already exceed 4 million units in operation, with installations steadily increasing due to falling costs and enhanced AI capabilities. Acemoglu and Restrepo's task-based framework posits that automation generates a displacement effect, as capital takes over tasks previously performed by labor. These converging trends underscore the need for a comprehensive review of AI's impact on labor markets, examining how automation displaces and reinstates labor, how industries are differentially affected, and what policy and organizational responses are emerging to address the challenges.

## Task-Based Frameworks and Displacement-Reinstatement

In this framework, production requires the completion of a range of tasks, each of which can be allocated to either capital or labor, and the resulting allocation determines what the authors term the "task content of production". Countervailing the displacement effect is the reinstatement effect, which is the polar opposite of displacement and arises when new labor-intensive tasks are created in which labor has a comparative advantage, directly increasing both the labor share and labor demand. Historical examples of reinstatement abound: in the 19th century, technological developments generated employment for line workers, engineers, machinists, repairmen, conductors, managers, and financiers, while during agricultural mechanization, new occupations in factories and clerical work played a pivotal role in generating labor demand. The pattern was particularly pronounced in manufacturing, where the displacement effect reduced labor demand at about 1.1 percent per year, or about 30 percent cumulatively over the period. The authors' baseline estimate of the elasticity of substitution between capital and labor at the industry level is 0.8, based on Oberfield and Raval's work, while firm-level elasticities are estimated to be between 0.4 and 0.7. Complementary research by Autor, using decades of U.S. data from 1940 through 2018, estimates that more than 60 percent of employment in 2018 was found in job titles that did not exist in 1940, reinforcing the view that new work is quantitatively important. Acemoglu and Restrepo's paper, published in the Journal of Economic Perspectives, presents a task-based framework for analyzing how technology displaces and reinstates labor. Automation corresponds to the development and adoption of new technologies that enable capital to be substituted for labor in a range of tasks, generating a displacement effect that shifts the task content of production adversely for labor and reduces the labor share of value added. Simultaneously, automation produces a productivity effect by increasing productivity, which contributes to the demand for labor in non-automated tasks, so that the net impact on labor demand depends on how the displacement and productivity effects weigh against each other. The authors argue that some automation technologies may reduce labor demand because they bring sizable displacement effects but modest productivity gains, contradicting the presumption that all technologies increase aggregate labor demand simply because they raise productivity. Using data from Lin, Acemoglu and Restrepo show that about half of employment growth over the period 1980–2015 took place in occupations in which job titles or tasks performed by workers changed. Their decomposition reveals that between 1947 and 1987, wage bill per capita grew at 2.5 percent per year, largely explained by the productivity effect of 2.4 percent per year, while the displacement effect reduced labor demand at about 0.48 percent per year and the reinstatement effect increased it by 0.47 percent per year, yielding a near balance.

## Occupational Exposure and Susceptibility to AI

One such framework proposes evaluating the potential impact of large language models (LLMs) by considering their relevance to the tasks workers perform, estimating that roughly 1.8% of jobs could have over half their tasks affected by LLMs with simple interfaces and general training. When accounting for current and likely future software developments that complement LLM capabilities, this share jumps to just over 46% of jobs. This analysis reveals that AI's potential impact extends beyond routine tasks to include nonroutine ones such as diagnosing health conditions, programming computers, and tracking flight routes. However, the study finds that some affected occupations are augmented rather than replaced—including neurologists, software engineers, and air traffic controllers—and that affected sectors such as IT, Healthcare, and Transport are experiencing labor shortages. Across OECD countries, AI has made the most progress in non-routine, cognitive tasks, meaning that the occupations most exposed to AI tend to be white-collar roles such as IT professionals, business professionals, managers, and science and engineering professionals. Occupations requiring manual skills and strength—such as cleaners, agricultural forestry and fishery labourers, and food preparation assistants—are the least exposed to AI. Additionally, occupations with higher wages are more likely to be exposed to rapid advances in language modelling, and education and legal service sectors exhibit higher exposure. In Korea, new analysis shows that more "traditional" AI appears to be associated with lower growth in full-time, permanent jobs, concentrated in the manufacturing sector, while no such association was found for generative AI. The adoption of AI also appears to change the skills required of workers, as 32.2% of Korean firms reported that AI increased the kinds of skills required and 38.3% reported an increase in the level of skills required. Recent approaches have replaced coarse-grained matching with more precise deep learning methods to evaluate AI's potential impact on occupational tasks. In a survey of Korean firms, 95.5% reported no workforce changes at the department- or team-level following AI adoption, and 56.5% said AI had replaced specific tasks within existing jobs rather than eliminating positions.

## Empirical Evidence on Employment and Labor Demand

However, in occupations where computer use is high, a one standard deviation increase in AI exposure was associated with 5.7 percentage points higher employment growth over the same period. Conversely, within occupations with low computer use, a one standard deviation increase in AI exposure was linked to a 0.60 percentage point greater drop in usual weekly working hours, equivalent to approximately 13 minutes per week. The share of job postings requiring AI skills remained very low overall, averaging 0.24% in the United States and 0.14% in the United Kingdom in 2019. Instrumental variable estimates reinforced these findings, showing AI increased high-skilled employment by 0.376% and medium-skilled employment by 0.397%, while low-skilled employment declined by 0.003%. Under the assumption that historical patterns of long-run substitution persist, that study estimated AI will reduce 90:10 wage inequality but will not affect the top 1%. Research on generative AI's short-term effects in an online labor market, published in Organization Science, found that it reduced overall demand for workers, suggesting generative AI may diminish the role of human capital within organizations. The same report projected that 30% of current U.S. jobs could be automated by 2030, with 60% of jobs seeing significant task-level modifications due to AI integration. Another analysis observed that AI's impact on labor markets has been modest so far, with little evidence of broad-based job losses, echoing past innovation cycles that displaced some jobs but ultimately expanded overall employment over time. One study characterized AI as having a dual purpose in the labor market, causing unemployment in routine and low-skilled occupations such as manufacturing and retail while simultaneously creating high-skilled employment in IT-related fields. Across 23 countries, employment grew by 10.8% on average across all occupations and countries in the sample between 2012 and 2019. A one-unit increase in AI significantly increased high-skilled employment by 0.063% and medium-skilled employment by 0.001%, while decreasing low-skilled employment by 0.001% in China. Regional heterogeneity analysis across Chinese economic zones showed AI positively affected high-skilled labor employment in the Southern Coastal Economic Zone with a coefficient of 0.568 and in the Northeast Economic Zone with a coefficient of 0.211. One analysis that constructed a patent-based measure of occupational AI exposure found that, in contrast to software and robots, AI is directed at high-skilled tasks. A study found that AI exposure increased the relative importance of routine tasks, while robot exposure reduced the routine task share by 0.9 percentage points, accounting for virtually all of the decline in the routine task share between 2006 and 2018. Jobs for AI and Machine Learning specialists have been rising at a compounding rate of 32% per year between 2016 and 2023.

## Productivity Effects of Generative AI

In a preregistered online experiment, Noy et al. assigned occupation-specific writing tasks to 453 college-educated professionals and randomly exposed half to ChatGPT, finding that average time taken decreased by 40% and output quality rose by 18%. The experiment also reduced inequality between workers, and those exposed to ChatGPT were 2 times as likely to report using it in their real job 2 weeks after the experiment and 1.6 times as likely 2 months after. A systematic review of 194 peer-reviewed articles published between 2011 and 2025 concludes that AI functions as a general-purpose technology capable of enhancing productivity, but its effects are often uneven and highly context-dependent, giving rise to trade-offs such as job displacement and widening inequality. An ILO research brief synthesizing evidence from experiments, firm-level data, platform studies, and representative surveys across Australia, Denmark, Germany, Korea, Kuwait, the United Kingdom, and the United States finds that productivity gains are real albeit often unverified and uneven. Worker-reported time savings of a few per cent of working hours have not yet translated into higher measured output, earnings, or employment. Among workers who used generative AI at least once in the previous month, 31.9% spent an hour or more per workday using it, while another 47.0% used it between 15 and 59 minutes daily. Users reported meaningful time savings: among those who used generative AI in the previous week, 20.5% said it saved them four hours or more, 20.1% reported three hours, 26.4% reported saving two hours, and 33.0% reported an hour or less. The weighted correlation between self-reported time savings and self-reported output changes is low, suggesting that workers save time but do not on average produce more. Productivity effects vary substantially by occupation: workers in the computer and mathematics occupation used generative AI in nearly 12% of their work hours and reported this saved them 2.5% of work time, while workers in personal service occupations used it in only 1.3% of their work hours, saving just 0.4%. Across industries, information services has both the largest share of work hours spent using generative AI at 14.0% and the highest time savings at 2.6%, while leisure, accommodation, and other services has the lowest at 2.3% and 0.6%, respectively. A 10 percentage point increase in the share of time spent using generative AI is associated with a 1.7 percentage point increase in time saved as a share of hours worked. A working paper by Bonney and others found that only 5.4% of firms had formally adopted generative AI as of February 2024, suggesting that worker adoption remains mostly informal. In a working paper, a standard model of aggregate production was used to estimate that self-reported time savings from generative AI translate to a 1.1% increase in aggregate productivity, implying that workers are on average 33% more productive in each hour.

## Wage Inequality, Skill Demand, and Labor Polarization

Empirical evidence indicates that the share of the employed population with AI skills remains small—at most 0.3% of those employed in OECD countries on average—but is growing rapidly, with nearly half the AI workforce situated in the top two deciles of the labour earnings distribution. A one standard deviation increase in exposure to AI is associated with a 0.4 percentage point increase in wage growth, an effect largely driven by occupations requiring a high level of familiarity with software. Higher-income occupations exhibit a strong positive relationship between AI impact and both employment and wages, suggesting that access to complementary skills and technologies plays an important role in determining who benefits from AI adoption. These patterns imply that AI has the potential to exacerbate labor market polarization, as the benefits accrue disproportionately to workers already positioned at the upper end of the skill and income distribution. Consistent with this concern, labor participation of low-skilled workers in the United States has declined by 2.34% and that of medium-skill workers by 2.56%, trends that one analysis links to labor-saving technologies including AI. High-skilled roles such as business professionals, managers, CEOs, and science and engineering professionals are most affected by AI advances, while lower-skilled jobs experience comparatively less impact. Job vacancies for AI roles have increased seven-fold since 2012, and jobs requiring AI skills have grown 3.5 times faster than overall job vacancies, signaling a steep rise in demand for specialized competencies. Automation more broadly has been associated with increased wage disparities and social inequalities, as the growing disparity between automated production needs and current workforce capabilities requires coordinated efforts from industry and government to address the skills gap. Theoretical perspectives on occupations and inequality identify four overarching lenses—skills, tasks, institutions, and culture—through which scholars conceptualize how occupational characteristics shape wage inequality, though some mechanisms linking occupations to wage outcomes remain empirically unclear. Notably, generative AI applications have been shown to benefit the least experienced workers most, with one study finding that less experienced programmers using AI tools completed tasks over 50% faster than those in the control group, suggesting that under certain conditions AI may decrease rather than increase performance inequality in the workplace. AI's impact on wages is theoretically ambiguous, with evidence indicating that positive wage effects are driven primarily by occupations with higher software skill requirements and higher-income occupations. Research using the AI Occupational Impact (AIOI) measure provides evidence that occupations impacted by AI experience a small but positive change in wages and no change in employment, while the positive correlation with wages is driven primarily by occupations with higher software skill requirements. Surveys reveal that men—particularly in finance—were more likely than women to expect a wage increase and less likely to expect a wage decrease due to AI, indicating that AI may put further pressure on currently existing wage inequalities.

## Policy Implications and Frameworks for Managing Disruption

The model features two intermediate sectors—one subject to an automation shock—to capture cross-sector labor flows and enable study of policies supporting sectoral mobility. Sectoral reallocation can be costly because of potential mismatch between the skills of unemployed workers and those required by firms, drawing on Branch, Petrosky-Nadeau, and Rocheteau, Di Pace and Hertweck, and Walsh. Cazzaniga and others assume that AI shocks would reduce the labor share by 5.5 percentage points based on the historical change observed in the United Kingdom between 1980 and 2014. A significantly larger share of total employment is in occupations with high augmentation potential across regions, ranging from 10.2 percent in Sub-Saharan Africa to 16.1 percent in Southeastern Asia and the Pacific. Online platform workers in the US regularly report median earnings of roughly $2 to $3 per hour, well below the federal minimum wage of $7.25, and much of this low-paid work has moved to developing countries.

## Cross-Study Synthesis and Contradictions

The cross-study evidence on AI's labor market impact reveals a field still in its earliest stages, with convergent acknowledgment that current findings are fragmented and preliminary. The question of whether AI exposure measures are valid also produces conflicting signals: while existing measures have been criticized as poorly validated against real-world economic outcomes, Tomlinson et al. found that AI exposure measures from Eloundou et al. have very high correlation with Microsoft Copilot usage from 2025. Earlier labor market disruption research, including Autor, Dorn, and Hanson's analysis of the China shock, demonstrates that disruptions can be especially challenging when geographically concentrated, with localized economic and political effects persisting across local labor markets.

## Conclusions and Research Gaps

The collective evidence suggests that AI is beginning to reshape labor markets, but the research remains in an early stage with substantial unresolved questions. Yet early large-scale evidence is consistent with the hypothesis that the AI revolution is beginning to have a significant and disproportionate impact on entry-level workers in the American labor market. AI also has unclear effects on matching between employers and job candidates: algorithmic writing assistance for resumes has been shown to lead to causal increases in hiring and wages for prospective employees, while AI-assisted interviewing has been found to improve candidate selection. However, AI usage may dilute labor market signals; one study finds that while AI improves cover letters, these subsequently became less informative signals of worker ability, prompting employers to shift toward alternative signals such as past reviews. One analysis finds that the evidence on how AI is affecting the labor market today is inconclusive, and claims about harmful impacts on particular groups of workers are premature. Some research found that a decline in job postings began in 2022, prior to the public release of ChatGPT, corresponding better to the macroeconomic shift of rising interest rates than to the launch of large language models, and Frank et al. found similar results. The uneven adoption of AI across regions raises critical questions about global equity, fairness, and the social contract. Important questions about AI's effects on the labor market remain unanswered, and there is a need for more research and better data.

## Limitations

Limitations: The corpus exhibits significant tier-distribution gaps, with only 6% of sources classified as T1 primary studies and 21% falling into T6, while a further 15% remain UNKNOWN and could not be reliably categorized. No contradictions were detected by the pipeline across any paired sources, so no cross-source disagreement on magnitude, direction, or endpoint is asserted here. The telemetry block does not surface a date range, which limits the ability to characterize the evidence horizon or identify temporal gaps in the underlying corpus.

## ===== EVIDENCE 5: MANGLING FUNCTION SOURCE =====

### render TITLE (run_honest_sweep_r3.py 5945-5960):
) -> str:
    """Codex round 1 B-3: build the pipeline-verdict markdown body used
    when ZERO sections survived strict_verify. Pure function so a
    behavior test can call it without mocking run_one_query."""
    head = (
        f"# Research report: {_strip_injected_instruction_appendix(research_question)}\n\n"
        "## Pipeline verdict\n\n"
        # I-beatboth-011 idx 33 (#1289): name the LIVE generator in the user-facing abort body, not a
        # stale hardcoded model string (the run is all-GLM-5.2).
        f"{os.environ.get('PG_GENERATOR_MODEL') or 'The generator'} generated {len(sections)} "
        "section(s), but EVERY section failed Phase-4 strict_verify: "
        "the cited evidence did not support the claims, or the "
        "generator did not emit provenance tokens.\n\n"
        "### Per-section verdict\n\n"
    )
    rows = "\n".join(

### corpus-ledger AUDIT APPENDIX (4245-4295):
_CORPUS_LEDGER_HEADER = "## Corpus ledger (audit appendix — not cited references)"


def _cited_reference_typing_enabled() -> bool:
    """T2 kill-switch. Default ON; OFF => the conflated single Bibliography (pre-fix)."""
    return os.environ.get(_CITED_REFERENCE_TYPING_ENV, "1").strip().lower() not in (
        "", "0", "false", "no", "off",
    )


def cited_reference_numbers(report_text: str) -> "set[int]":
    """The set of bibliography ``[N]`` numbers the report BODY actually cites. PURE.

    A body citation is any ``[N]`` that is NOT the leading marker of a bibliography ENTRY line
    (``^[N] ...``) — those entry lines are the reference list itself, not a citation OF a source.
    Computing the cited set from the whole report MINUS the entry lines guarantees a source cited
    anywhere in the body (key findings / sections / depth / abstract / conclusion / disclosures) is
    counted, so T2 can never demote a genuinely-cited source to the ledger."""
    cited: set[int] = set()
    for line in (report_text or "").split("\n"):
        if _BIB_ENTRY_LINE_RE.match(line):
            continue  # a reference-list entry line, not a body citation
        for m in _INLINE_CITE_MARKER_RE.finditer(line):
            try:
                cited.add(int(m.group(1)))
            except (TypeError, ValueError):
                continue
    return cited


def s2_cited_bibliography_records(
    bibliography: "list[dict] | None", report_body_text: str
) -> "list[dict]":
    """S2 (I-deepfix-001 #1344): the bibliography rows the report BODY actually CITES (``[N]`` present
    in the body), for the required-entity citation-coverage credit. PURE.

    Codex diff-gate P1 (#1344): the credit must come ONLY from cited evidence of the report's VERIFIED
    claims, NOT from every ``multi.bibliography`` row. The full bibliography can carry retrieved-but-
    UNCITED corpus-ledger rows (T2 types them into a non-reference appendix); an uncited row whose URL
    happens to match a required entity's DOI/url_pattern would then FALSELY mark that entity covered and
    SUPPRESS a real Coverage-gaps disclosure — over-claiming completeness, the lethal direction. Keying
    on ``num in cited_reference_numbers(body)`` restricts the credit to genuinely-cited sources (the
    body ``[N]`` markers live in strict_verify-PASSED prose). When the body is empty/unreadable this
    returns [] — a fail-safe UNDER-credit (disclose the gap) that never suppresses a gap on missing input."""
    cited_nums = cited_reference_numbers(report_body_text)
    if not cited_nums:
        return []
    out: list[dict] = []
    for b in bibliography or []:
        if not isinstance(b, dict):
            continue

### content_dedup_consolidate.py head:
"""I-deepfix-001 (#1344) W9 — content-dedup CONSOLIDATE-KEEP-ALL (body-syndication baskets).

The W9 winner is dedup=ContentDeduplicator. Its native ``deduplicate()`` returns
``unique_items`` — a DROP that sheds corroborators, which VIOLATES §-1.3 (the pipeline
is WEIGHT-and-CONSOLIDATE, never FILTER-and-DROP). So W9 is wired here in the ONLY
§-1.3-legal form: ContentDeduplicator's body-MinHash CLUSTERS are used to GROUP
near-identical-body sources into a corroboration BASKET, and EVERY row is kept.
Nothing is dropped; nothing is merged.

WHAT IT ADDS over the existing finding_dedup same-work consolidation (#7, which keys
on DOI / folded title): finding_dedup catches the SAME work cited under the same
identity. It MISSES different-title near-identical-BODY syndication — the same report
republished at two URLs with different titles and no shared DOI. That is exactly what
ContentDeduplicator's body-MinHash catches. Here it is surfaced as a keep-all
corroboration WEIGHT, never a drop.

FAITHFULNESS POSTURE (the load-bearing safety argument — VERIFY it):
  * KEEP-ALL: every input row is returned, unchanged except for additive annotation
    keys. No row is removed; the output list has the SAME length as the input.
  * MERGE-NOTHING: unlike finding_dedup this NEVER collapses two findings into one
    representative. It only ATTACHES "these N rows share a near-identical body" to
    each member. So it cannot over-merge two distinct clinical findings — the
    clinical-lethal over-merge risk finding_dedup's conservative key guards against is
    not in play here, because no claim is ever dropped, rewritten, or merged.
  * NEAR-IDENTICAL ONLY: grouping fires only at the EXACT/NEAR_DUPLICATE tier
    (MinHash similarity >= ``PG_W9_BODY_SIM``, default 0.85). The loose SIMILAR tier
    (0.70-0.85) is DELIBERATELY excluded (we pin ``similar_threshold`` up to the
    near-dup floor) so merely-topical sources are NOT grouped — only true syndication.
  * GROUNDING-UNTOUCHED: the annotation is metadata. It never changes which rows
    ground prose, never feeds or relaxes strict_verify / NLI / 4-role / span-grounding.
    A corroboration count is a disclosure WEIGHT, not a gate.

Pure leaf: no network, no model, no LLM. Reuses ``src.utils.content_deduplicator``
(MinHash/SimHash, pure python, bounded O(n^2) over the corpus). Env kill-switch
(LAW VI). DEFAULT ON. ROW-level byte-identical when no two rows share a near-identical
body (no multi-member cluster => no row gains an annotation key); the stage still emits
a zeroed telemetry dict + one canary log line as the observability signal (it does NOT
claim an empty/absent result object).
"""
from __future__ import annotations

import logging
import os
from typing import Any

from src.utils.content_deduplicator import (
    ContentDeduplicator,
    DeduplicationConfig,
)

logger = logging.getLogger("polaris_graph.content_dedup_consolidate")

_ENV_FLAG = "PG_CONTENT_DEDUP_CONSOLIDATE"
_OFF_VALUES = frozenset({"0", "fal
...[elided]...