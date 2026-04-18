# Apples-to-apples spot-check

_Honest-rebuild generator + evaluator run on the **same corpus** (URLs + evidence rows) as PG_LB_SA_02._

- **Query (both runs):** 'What are the proven health benefits and risks of semaglutide (Ozempic/Wegovy) for adults with obesity?'
- **Corpus size:** 33 URLs / 20 evidence rows.

## Summary table

| Metric | Pre-rebuild | Honest-rebuild |
|---|---|---|
| Report words  | 10485 | 372 |
| Sections      | 10 | 3 (prose / methods / biblio) |
| Citations     | 67 | 7 |
| Self-graded faithfulness | **90.8%** (cooked) | REMOVED |
| Rule-check pass | N/A | 12/12 |
| Contradiction disclosures | 0 | 0 |

## Pre-rebuild report (first 40 lines)

```markdown
# What are the proven health benefits and risks of semaglutide (Ozempic/Wegovy) for adults with obesity?

## Abstract

This evidence review addresses the proven health benefits and risks of semaglutide 2.4 mg once-weekly (Wegovy) for adults with obesity. Semaglutide received FDA approval for obesity management in 2021 under the trade name Wegovy, having previously been approved for diabetes as Ozempic since 2017 [1]. The supporting evidence base includes a systematic review and meta-analysis of 13 randomized controlled trials (RCTs) comprising 5,838 participants [33].

In the STEP 1 trial, semaglutide-treated patients achieved a mean weight reduction of 14.9% at 68 weeks, compared with 2.4% for placebo [13]. Meta-analytic pooling across non-diabetic obese adults yielded a placebo-adjusted mean weight difference of −11.85% (95% CI −12.81 to −10.90; I²=43%) [7]. The SELECT trial evaluated major adverse cardiovascular event prevention in patients with obesity and established cardiovascular disease [3].

The most common adverse events are gastrointestinal — nausea and diarrhea — generally mild-to-moderate and transient [8]. Gastrointestinal adverse events are approximately 1.6-fold more common with semaglutide than placebo [7]. Rodent studies document dose-dependent thyroid C-cell tumors at clinically relevant exposures; human relevance remains unresolved [10]. Long-term evidence beyond a 16-month treatment window is limited [4]. Semaglutide injection products have been in shortage since 2022, restricting real-world access [25].

## Overview and Clinical Context of Semaglutide for Obesity

Semaglutide was first developed under the trade name Ozempic for diabetes treatment beginning in 2017 and received a new FDA approval under the trade name Wegovy for obesity management in 2021 [1]. The approved chronic weight management indication in adults covers patients with a body mass index (BMI) of 30 kg/m² or greater (obesity), or patients with BMI of 27 kg/m² or greater who have at least one weight-related comorbidity [2]. The 2021 Wegovy approval [1] and the BMI-threshold eligibility criteria [2] define the regulatory boundary between a diabetes drug and an obesity drug for the same underlying compound.

The clinical trial program supporting the Wegovy obesity indication is the Semaglutide Treatment Effect in People with Obesity (STEP) program, a collection of phase-3 trials evaluating semaglutide 2.4 mg for obesity [4]. In the STEP trials, semaglutide participants were 15.08 times as likely to achieve at least 20% body weight loss compared with placebo (RR 15.08, 95% CI 9.31 to 24.43) [5]. Higher proportions of semaglutide-treated patients achieved weight-loss thresholds of 10%, 15%, and 20% of initial body weight compared with placebo, with statistically significant differences at each threshold (p<0.01) [6]. The large relative risk for the 20% threshold [5] and the statistically significant threshold-attainment across 10%, 15%, and 20% benchmarks [6] together characterize the responder distribution in the STEP trial population.

The adverse event profile documented in the STEP program is dominated by gastrointestinal events: gastrointestinal adverse events were 1.59-fold more likely with semaglutide than with placebo (RR 1.59, 95% CI 1.34 to 1.88, p<0.00001, I²=81%) [7]. The most common individual adverse events were nausea and diarrhea, and these were generally mild-to-moderate and transient in severity [8]. The pooled GI event risk ratio of 1.59 [7] and the characterization of individual GI events as mild-to-moderate and transient [8] together establish the GI tolerability profile: frequently elevated risk (1.59-fold) but predominantly low-to-moderate clinical severity.

Long-term durability is a recognized limitation of anti-obesity pharmacotherapy. Patient-group survey data indicate that anti-obesity medications including semaglutide lack long-term effectiveness, with many individuals regaining lost weight within five years [3]. The survey-based durability concern [3] represents a patient-experience perspective on weight maintenance extending beyond the STEP trial follow-up windows; the weight-regain pattern within five years [3] is consistent with the post-discontinuation rebound dynamics addressed in the efficacy sections of this review.

**Key Findings**

- Semaglutide (Ozempic) received FDA approval as Wegovy for obesity in 2021, with the indication covering adults with BMI ≥30 or ≥27 with at least one weight-related comorbidity [1][2].
- The STEP program is a collection of phase-3 trials evaluating semaglutide 2.4 mg for obesity [4].
- Semaglutide participants were 15.08 times as likely to achieve ≥20% weight loss versus placebo (RR 15.08, 95% CI 9.31–24.43) [5]; higher proportions also achieved ≥10% and ≥15% thresholds (p<0.01) [6].
- GI adverse events were 1.59-fold more likely than placebo (RR 1.59, 95% CI 1.34–1.88, I²=81%), though most were mild-to-moderate and transient [7][8].
- Patient-group surveys characterize anti-obesity medications including semaglutide as lacking long-term effectiveness, with weight regain within five years common [3].

## Pharmacology, Mechanism of Action, and Dosing

The 2.4 mg once-weekly therapeutic maintenance dose of semaglutide is reached after 16 weeks of dose escalation beginning at 0.25 mg [10].

GLP-1 receptor agonist (GLP-1RA) use is associated with increased risk of gastrointestinal adverse events including nausea, vomiting, diarrhea, and in rare cases paralysis of the stomach (gastroparesis) [9]. The magnitude of associated benefits from GLP-1RA pharmacotherapy is modest — approximately a 10% to 20% risk reduction for most outcomes — suggesting that combination with lifestyle interventions is needed to achieve meaningful therapeutic benefit [9]. GLP-1RA exposure is also associated with reduced risks of seizures and reduced risks of addiction to substances such as alcohol, cannabis, stimulants, and opioids, compared with traditional diabetes drugs [9].

Analysis of the FDA Adverse Event Reporting System (FAERS) identified 17 cases of proteinuria and 1 case of glomerulonephritis specifically associated with semaglutide [12]. These post-marketing FAERS reports [12] represent an adverse renal signal requiring prospective monitoring, distinct from the gastrointestinal adverse event pattern characterized in clinical trials [9].

Compounded GLP-1 receptor agonist oral formulations raise concerns with regulators about safety, stability, and bioavailability, particularly for oral formulations that lack proprietary absorption mechanisms [11]. The 16-week dose-escalation schedule [10] and the safety, stability, and bioavailability concerns associated with compounded oral formulations [11] together establish that the approved pharmacological pathway has specific dosing architecture and quality standards not present in compounded alternatives.

**Key Findings**

```

## Honest-rebuild report (full)

```markdown
# Research report: What are the proven health benefits and risks of semaglutide (Ozempic/Wegovy) for adults with obesity?

Semaglutide 2.4 mg produces significant weight loss in adults with obesity, with one trial showing 86.6% of participants achieving at least 5% body-weight loss at week 68 compared to 47.6% with placebo.[1] Participants are 2.37 times as likely to achieve ≥5% weight loss and 15.08 times as likely to achieve ≥20% weight loss with semaglutide.[2][3] Beyond weight loss, semaglutide improves waist circumference, fasting plasma glucose, and lipid profiles compared to placebo  and is FDA-approved to reduce the risk of major adverse cardiovascular events in adults with established cardiovascular disease and obesity or overweight.[4][5] The most common adverse events are gastrointestinal, such as nausea and diarrhea, which are generally mild-to-moderate and transient.[6] One real-world analysis noted that tirzepatide was associated with a lower risk of cardiovascular events, especially incident heart failure, compared with semaglutide.[7]

## Methods
Pre-registered protocol.json (SHA-256 249393f7a9ddde1f...).
Corpus: PG_LB_SA_02 pre-rebuild retrieval (apples-to-apples).
Generator model: deepseek/deepseek-v3.2-exp. Evaluator model: qwen/qwen3-8b (different family).
Sources classified using T1-T7 tier taxonomy.
Inclusion / exclusion per clinical template. Sponsor / conflict-of-interest review per source.
Prompt-injection sanitization enabled. Retrieved 2026-04-18 (honest-rebuild re-tier run).
Expected tier distribution: T1 30-60%, T2 15-40%, T3 5-25%. Actual: T1=9%, T2=21%, T3=15%, T4=15%, T5=15%, T6=18%, T7=6%.


## Bibliography
[1] 86.6% of semaglutide participants vs 47.6% of placebo achieved at least 5% body-weight loss at week 68. — https://jamanetwork.com/journals/jama/articlepdf/2777025/jama_wadden_2021_oi_210014_1618250237.04792.pdf (tier T1)
[2] Semaglutide participants were 2.37 times as likely to achieve ≥5% weight loss (RR 2.37, 95% CI 1.67 to 3.36). — https://www.ajconline.org/article/S00029149(24)00319-9/fulltext (tier UNKNOWN)
[3] Semaglutide participants were 15.08 times as likely to achieve ≥20% weight loss (RR 15.08, 95% CI 9.31 to 24.43). — https://www.ajconline.org/article/S00029149(24)00319-9/fulltext (tier UNKNOWN)
[4] Semaglutide improved waist circumference, fasting plasma glucose, and lipid profiles compared to placebo (p<0.01). — https://diabetesjournals.org/diabetes/article/74/Supplement_1/1745-P/160264/1745-P-Long-Term-Safety-and-Efficacy-of-Once (tier T7)
[5] Wegovy is FDA approved to reduce MACE risk in adults with established CVD and obesity or overweight. — https://www.novomedlink.com/multiple-indications/wegovy-gateway.html (tier UNKNOWN)
[6] The most common adverse events with semaglutide were gastrointestinal (nausea, diarrhea), generally mild-to-moderate and transient. — https://pmc.ncbi.nlm.nih.gov/articles/PMC9769143/ (tier UNKNOWN)
[7] A referenced real-world analysis found tirzepatide had lower cardiovascular-event risk than semaglutide in non-diabetic adults with obesity, especially incident heart failure. — https://www.jomes.org/journal/download_pdf.php?doi=10.7570/jomes22012 (tier UNKNOWN)
```
