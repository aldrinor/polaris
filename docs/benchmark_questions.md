# POLARIS Benchmark Research Questions

## 10-Question Evaluation Suite

**Purpose:** Demonstrate POLARIS advantages over competitor platforms (Perplexity Max, ChatGPT Pro, Gemini Ultra, Claude Max). Each question is designed to test specific capabilities where POLARIS has structural advantages: source diversity, citation accuracy, multi-perspective analysis, factual verification, and analytical depth.

**Evaluation Protocol:** Run each question through POLARIS (standard depth, 60-minute budget) and through each competitor. Score all outputs blind (remove platform identifiers before evaluation).

**Last Updated:** 2026-02-27

---

## Evaluation Criteria

Each output is scored on 5 dimensions (0-20 points each, 100 total):

| Dimension | Points | Scoring Criteria |
|-----------|--------|------------------|
| **Source Diversity** | 20 | Number of unique source domains; mix of academic, government, industry, and news sources; geographic diversity; no over-reliance on any single source (max 15% from one domain) |
| **Citation Accuracy** | 20 | Percentage of citations that are: (a) real URLs returning HTTP 200, (b) semantically relevant to the claim they support, (c) correctly attributed — claim content matches source content |
| **Multi-Perspective Analysis** | 20 | Number of distinct analytical perspectives represented; presence of conflicting viewpoints acknowledged; stakeholder coverage (scientific, regulatory, economic, public health, industry, historical) |
| **Factual Verification** | 20 | NLI entailment score for atomic claims; absence of fabricated statistics, dates, organizations, or study results; numeric claims traceable to cited sources |
| **Analytical Depth** | 20 | Word count; section structure and hierarchy; quantitative analysis with specific data; historical context; forward-looking implications; actionable conclusions with evidence basis |

### Scoring Rubric

| Score | Label | Description |
|-------|-------|-------------|
| 18-20 | Exceptional | Exceeds professional analyst quality; all sources verifiable; all claims traceable; comprehensive multi-perspective coverage |
| 14-17 | Strong | High quality with minor gaps; most sources verifiable; good perspective coverage |
| 10-13 | Adequate | Meets basic requirements but lacks depth, source quality, or perspective diversity |
| 6-9 | Weak | Significant gaps in sourcing, accuracy, or depth; single-perspective analysis |
| 0-5 | Poor | Major factual errors, fabricated sources, superficial treatment, or no citations |

---

## Question 1: Contradictory Scientific Evidence

**Query:**

> "What is the current scientific consensus on the effectiveness of silver nanoparticle coatings for antimicrobial water filtration, and where do peer-reviewed studies disagree on long-term efficacy, environmental impact, and regulatory safety thresholds?"

**Tests:** Contradiction detection, academic source diversity, multi-perspective analysis

**Why POLARIS Has an Advantage:**
- Phase 6 uses DeBERTa-v3-large-mnli to identify conflicting claims within evidence. Competitors produce single-narrative summaries that may silently ignore contradictions.
- 6-engine federated search includes Semantic Scholar and OpenAlex for deep academic coverage.
- STORM interviews generate Scientific, Regulatory, and Environmental perspectives that produce genuinely different conclusions.

**Expected Evaluation Criteria:**
- Does the output identify at least 3 specific areas of scientific disagreement (e.g., long-term silver ion leaching rates, bioaccumulation in aquatic systems, minimum inhibitory concentration thresholds)?
- Are conflicting study results presented with proper attribution to specific papers (author, year, journal)?
- Are regulatory thresholds cited from actual agency documents (EPA MCL for silver, WHO drinking water guidelines, EU Biocidal Products Regulation)?
- Does the output distinguish between laboratory efficacy data and real-world field deployment results?
- Are environmental impact concerns sourced from environmental toxicology literature, not industry marketing claims?

---

## Question 2: Cross-Jurisdictional Regulatory Comparison

**Query:**

> "Compare the regulatory pathways for antimicrobial surface coatings used in food processing equipment across the FDA (United States), EFSA (European Union), and Health Canada, including specific approval requirements, testing standards, timeline differences, and regulatory changes since 2023."

**Tests:** Source authority, citation accuracy (regulatory documents), geographic source diversity

**Why POLARIS Has an Advantage:**
- 5-signal scoring assigns maximum authority (0.95) to .gov domains (FDA, EFSA, Health Canada).
- Domain blocklist prevents citation of marketing sites and blog summaries instead of primary regulatory documents.
- Regional analysis stages can target North America, Europe, and Canada-specific sources.

**Expected Evaluation Criteria:**
- Are specific regulatory codes cited by their formal identifiers (FDA 21 CFR Part 175/176, EU Regulation 1935/2004, Health Canada Novel Food Regulations)?
- Are approval timelines quantified with actual data from regulatory databases, not estimates?
- Are testing standards referenced by their standard numbers (ISO 22196, ASTM E2149, JIS Z 2801)?
- Does the output distinguish between pre-market notification, registration, and full approval pathways?
- Are 2023-2026 regulatory changes sourced from official federal registers, gazettes, or agency announcements?

---

## Question 3: Quantitative Market Sizing with Verifiable Numbers

**Query:**

> "What is the total addressable market (TAM), serviceable addressable market (SAM), and serviceable obtainable market (SOM) for long-duration antimicrobial coatings in the global household water filtration industry, with breakdowns by region (North America, Europe, Asia-Pacific), application segment, and growth projections through 2030?"

**Tests:** Factual verification (numeric claims), source diversity (market research + government statistics + industry data)

**Why POLARIS Has an Advantage:**
- NLI verification checks every numeric claim against source text. Market size numbers are among the most frequently fabricated claims by LLMs.
- 5-signal scoring preferentially surfaces government statistical agencies and industry association data.
- Cross-source verification can detect inconsistent market numbers from different sources.

**Expected Evaluation Criteria:**
- Are market size figures attributed to specific, named research firms or data sources (not fabricated analyst reports)?
- Are regional breakdowns sourced from region-specific data (e.g., Freedonia, Euromonitor, Asia-Pacific trade associations), not extrapolated from global totals?
- Are growth rate projections sourced from at least 2 independent data providers?
- Does the output clearly distinguish between TAM, SAM, and SOM with explicit methodology?
- Are competitor market shares cited with named companies and specific revenue or unit figures from verifiable sources?

---

## Question 4: Historical Technology Evolution

**Query:**

> "Trace the evolution of biofilm prevention technologies in municipal water treatment systems from 1990 to present, identifying key scientific breakthroughs, failed approaches, commercial adoption rates, and the specific limitations that each generation of technology addressed and introduced."

**Tests:** Analytical depth (historical timeline), source diversity (academic papers spanning 3 decades), multi-perspective (scientific vs. industry vs. municipal utility)

**Why POLARIS Has an Advantage:**
- 8,000-12,000 word report length provides space for genuine chronological analysis. Competitors limited to 500-3,000 words cannot cover 35 years meaningfully.
- STORM interviews include Historical and Methodological perspectives specifically designed for temporal and developmental analysis.
- Semantic Scholar citation graph can traverse reference chains from recent review papers back to foundational 1990s research.

**Expected Evaluation Criteria:**
- Are at least 5 distinct technology generations identified with specific dates and citations to the original research?
- Are "failed approaches" documented with evidence from actual research papers or industry reports (not LLM inference about what might have failed)?
- Are adoption rates quantified (e.g., percentage of US municipal utilities using specific technology, number of installations)?
- Does the output cite primary research papers from each decade (1990s, 2000s, 2010s, 2020s), not just recent review articles?
- Are technology limitations supported by specific experimental data or field study evidence?

---

## Question 5: Emerging Threat Assessment with Clinical Data

**Query:**

> "Assess the emerging threat of antibiotic-resistant biofilm formation in hospital HVAC systems, including current prevalence data from surveillance studies, transmission risk models, documented outbreak cases, economic impact estimates, and the evidence base for proposed mitigation strategies ranked by effectiveness."

**Tests:** Academic search depth, factual verification (prevalence data, outbreak cases), evidence tiering (clinical studies vs. news reports)

**Why POLARIS Has an Advantage:**
- Semantic Scholar integration with citation chasing can traverse the epidemiological citation network to find surveillance studies and case reports.
- NLI verification catches fabricated prevalence statistics, study names, and outbreak incidents.
- GOLD tier scoring preferentially surfaces peer-reviewed clinical studies over news articles or press releases.
- LettuceDetect post-synthesis audit catches any fabricated clinical details that survive NLI verification.

**Expected Evaluation Criteria:**
- Are prevalence statistics sourced from published epidemiological surveillance studies (CDC, ECDC, WHO) with specific sample sizes and detection methods?
- Are documented outbreak cases real and verifiable (e.g., in CDC MMWR, ProMED, or peer-reviewed case reports)?
- Are economic impact estimates from health economics studies, not back-of-envelope calculations by the LLM?
- Are mitigation strategies ranked with explicit evidence quality levels (RCT, cohort study, case series, expert opinion)?
- Does the output distinguish between laboratory-demonstrated efficacy and clinically-validated interventions?

---

## Question 6: Patent Landscape with Verifiable IP Data

**Query:**

> "Map the patent landscape for antimicrobial coating technologies applied to water filtration systems, identifying the top 20 patent holders by portfolio size, key patent families with publication numbers and expiration dates, white space opportunities for new IP, and recent patent litigation outcomes that affect freedom to operate."

**Tests:** Factual verification (patent numbers, holders, dates must be real), source diversity (patent databases, legal databases, industry analysis)

**Why POLARIS Has an Advantage:**
- NLI verification prevents fabrication of patent numbers, assignee names, and filing dates — a common LLM failure mode.
- 6-engine federated search can access patent-related academic literature (Semantic Scholar) alongside web-accessible patent summaries.
- 15-section report structure supports organized presentation of patent landscape data.

**Expected Evaluation Criteria:**
- Are patent numbers real and verifiable in public patent databases (USPTO, EPO, WIPO)?
- Are patent assignee names correct and current (accounting for acquisitions and name changes)?
- Are expiration dates correctly calculated from priority dates, filing dates, and applicable patent terms?
- Are litigation outcomes sourced from actual court records, PTAB decisions, or legal databases?
- Does white space analysis reference specific CPC/IPC classification codes and identify technology gaps with evidence?

---

## Question 7: Multi-Stakeholder Impact Assessment

**Query:**

> "Analyze the impact of mandatory antimicrobial surface standards for food processing equipment on six stakeholder groups: small food manufacturers (<50 employees), large food corporations, equipment suppliers, regulatory agencies, consumers, and public health systems. Include cost burden estimates, compliance timeline challenges, and documented case studies of similar regulatory transitions in analogous industries."

**Tests:** Multi-perspective analysis (6 stakeholders), source diversity (industry associations, government RIAs, academic policy analysis, small business advocacy), contradiction detection (conflicting stakeholder interests)

**Why POLARIS Has an Advantage:**
- STORM interviews generate distinct perspectives from Industry, Regulatory, Economic, and Public Health viewpoints — each producing different analysis of the same policy.
- Phase 6 contradiction mining identifies tensions between stakeholder interests (e.g., cost burden on small manufacturers vs. public health benefit).
- Source diversity across 6 engines ensures small business perspectives are sourced from different publications than large corporation analysis.

**Expected Evaluation Criteria:**
- Are all 6 stakeholder perspectives addressed with roughly equal analytical depth (not 90% on large corporations and 10% on the rest)?
- Are cost burden estimates sourced from regulatory impact assessments (RIAs), industry surveys, or economic studies?
- Are analogous case study transitions real (with specific industry, regulation, country, and documented outcomes)?
- Does the output explicitly identify where stakeholder interests conflict, with evidence for both sides?
- Are small manufacturer perspectives sourced from small business associations or trade groups, not extrapolated from large corporation data?

---

## Question 8: Clinical Evidence Synthesis

**Query:**

> "Synthesize the clinical evidence for copper-alloy antimicrobial surfaces in reducing healthcare-associated infections (HAIs), including all randomized controlled trials published since 2015, their sample sizes, primary endpoints, effect sizes, hospital settings, pathogen coverage, cost-effectiveness analyses, and the current Cochrane or systematic review conclusions."

**Tests:** Academic search depth (RCT citation network), factual verification (sample sizes, effect sizes, p-values), source authority (PubMed, Cochrane, Lancet)

**Why POLARIS Has an Advantage:**
- Semantic Scholar citation chasing can traverse the RCT reference network from key systematic reviews to individual trials.
- NLI verification catches fabricated sample sizes, effect sizes, confidence intervals, and p-values.
- GOLD tier scoring (Tier 1 authority for PubMed, Nature, Lancet) preferentially surfaces peer-reviewed clinical evidence.
- Evidence tiering naturally maps to clinical evidence hierarchy (RCTs = GOLD, cohort studies = SILVER, case series = BRONZE).

**Expected Evaluation Criteria:**
- Are all cited randomized controlled trials real and verifiable in PubMed or ClinicalTrials.gov?
- Are sample sizes, primary endpoints, and effect sizes accurately extracted from the actual trial publications?
- Are systematic review / meta-analytic conclusions attributed to specific published reviews (Cochrane, etc.) with DOIs?
- Does the output distinguish between single-site and multi-site trials, and between ICU and general ward settings?
- Are cost-effectiveness analyses sourced from health economics literature with specific ICER values?

---

## Question 9: Geopolitical Supply Chain Risk Analysis

**Query:**

> "Evaluate the supply chain risks for antimicrobial coating raw materials (silver, copper, zinc, titanium dioxide) including concentration of mining and refining capacity by country, geopolitical vulnerability assessment, price volatility history from 2020 through 2025, substitute material feasibility, and documented supply disruption precedents with measured impact on downstream manufacturers."

**Tests:** Source diversity (commodity data, geopolitical analysis, materials science, trade policy), factual verification (production figures, price data, country percentages), multi-perspective (economic, geopolitical, scientific, industry)

**Why POLARIS Has an Advantage:**
- 6-engine federated search accesses commodity market research, geological survey data (USGS, BGS), materials science literature, and trade policy analysis.
- NLI verification prevents fabrication of production statistics, market prices, and country concentration percentages.
- STORM perspectives generate Economic, Regional, Scientific, and Industry analyses that each produce different risk assessments.

**Expected Evaluation Criteria:**
- Are production concentration figures sourced from geological surveys (USGS Mineral Commodity Summaries, British Geological Survey)?
- Are price volatility data from actual commodity exchanges (LME, COMEX, Shanghai Futures Exchange)?
- Are supply disruption precedents real events with specific dates, causes, durations, and documented impacts?
- Are substitute material assessments grounded in materials science literature with specific property comparisons?
- Does the output quantify risk levels with specific metrics (HHI concentration index, volatility coefficients, substitution elasticities)?

---

## Question 10: Evidence-Based Policy Recommendation

**Query:**

> "Based on evidence from successful national antimicrobial resistance (AMR) action plans in the UK, Sweden, Australia, and Netherlands, what policy recommendations should Canada adopt for antimicrobial surface regulations in healthcare facilities? For each recommendation, provide the evidence base from comparator countries, expected effectiveness metrics, implementation cost estimates, and realistic timeline."

**Tests:** Multi-perspective analysis (policy, scientific, economic, public health, regional), source authority (government action plans, WHO guidelines, peer-reviewed policy evaluation), analytical depth (recommendation-to-evidence linkage)

**Why POLARIS Has an Advantage:**
- STORM perspectives cover Scientific, Regulatory, Economic, Public Health, and Regional viewpoints — each essential for policy analysis.
- Tier 1 source authority scoring prioritizes government action plans, WHO guidelines, and agency evaluation reports.
- 8,000-12,000 word format supports structured recommendation-by-recommendation analysis with evidence linkage.
- Cross-source verification can check whether claimed effectiveness metrics from comparator countries are consistent across multiple evaluation reports.

**Expected Evaluation Criteria:**
- Are the referenced national AMR action plans real documents verifiable on government websites (UK 5-Year AMR Strategy, Sweden's National Action Plan, etc.)?
- Are effectiveness metrics sourced from published program evaluations (e.g., UK Review on AMR, Swedish monitoring reports)?
- Does the output clearly link each recommendation to specific evidence from specific comparator countries?
- Are cost estimates sourced from health economics analyses, government budget documents, or WHO economic assessments?
- Are implementation timelines realistic and justified by documented precedents from the comparator countries?

---

## Scoring Protocol

### Test Administration

1. **POLARIS**: Standard depth, PG_MAX_EXECUTION_MINUTES=60, PG_NLI_ENABLED=1, PG_STORM_ENABLED=1
2. **Perplexity Max**: Pro Search mode, maximum depth setting
3. **ChatGPT Pro**: Deep Research mode (if available), otherwise standard with explicit "be thorough" instruction
4. **Gemini Ultra**: Standard mode with explicit depth instruction
5. **Claude Max**: Standard mode with explicit "cite sources" instruction
6. **Blind scoring**: Remove all platform identifiers before evaluation. Two independent scorers per output.

### Expected POLARIS Advantages by Question

| Question | Primary POLARIS Advantage | Key Structural Differentiator |
|----------|---------------------------|-------------------------------|
| Q1 (Contradictions) | Contradiction Detection | Phase 6 DeBERTa-v3-large-mnli identifies conflicting claims that competitors silently merge |
| Q2 (Regulatory) | Source Authority | 5-signal Tier 1 scoring ensures citations come from .gov regulatory documents, not blog summaries |
| Q3 (Market Sizing) | Factual Verification | NLI verification catches fabricated market numbers — a known LLM failure mode |
| Q4 (Historical) | Analytical Depth | 8,000-12,000 words enables genuine 35-year chronological analysis impossible in 2,000 words |
| Q5 (Clinical Threats) | Academic Search Depth | Semantic Scholar citation chasing traverses epidemiological literature networks |
| Q6 (Patents) | Factual Verification | NLI catches fabricated patent numbers and assignee names — extremely common in LLM output |
| Q7 (Stakeholders) | Multi-Perspective | 8 STORM personas generate genuinely different analyses for each stakeholder group |
| Q8 (Clinical Evidence) | Source Authority + Academic | Tier 1 scoring for PubMed + citation chasing through RCT reference chains |
| Q9 (Supply Chain) | Source Diversity | 6-engine federated search covers commodity exchanges, geological surveys, materials science, trade policy |
| Q10 (Policy) | Multi-Perspective + Authority | STORM policy perspectives + Tier 1 scoring for government action plans and WHO guidelines |

### Results Template

Record results in `docs/benchmark_results.md`:

```markdown
| Q# | Platform | Source Diversity (/20) | Citation Accuracy (/20) | Multi-Perspective (/20) | Factual Verification (/20) | Analytical Depth (/20) | Total (/100) |
|----|----------|------------------------|-------------------------|-------------------------|----------------------------|------------------------|--------------|
| 1  | POLARIS  |                        |                         |                         |                            |                        |              |
| 1  | Perplexity |                      |                         |                         |                            |                        |              |
| 1  | ChatGPT  |                        |                         |                         |                            |                        |              |
| 1  | Gemini   |                        |                         |                         |                            |                        |              |
| 1  | Claude   |                        |                         |                         |                            |                        |              |
```

**Target:** POLARIS should score >= 75/100 average across all 10 questions, and should outscore every competitor by >= 15 points on average.

---

*These benchmark questions target genuine analytical capabilities where POLARIS structural advantages (NLI verification, multi-engine search, STORM interviews, evidence tiering, iterative refinement, audit trail) should produce measurably superior results. Each question was selected to exercise a specific POLARIS differentiator that no competitor currently offers.*
