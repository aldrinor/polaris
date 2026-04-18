# Clinical/Medical Systematic Review Automation, April 2026

Prepared 2026-04-17. Primary sources preferred; numbered references below.

## 1. Cochrane's position

Cochrane (with Campbell, JBI, Collaboration for Environmental Evidence) published a joint position statement on 31 October 2025 endorsing the **RAISE** framework (Responsible use of AI in evidence SynthEsis) [1][2]. Six binding principles: author accountability, conditional approval (AI permissible only when methodological integrity preserved), *explicit* human oversight requirement, transparent reporting of any AI-suggested judgement, developer transparency, ethical compliance [1]. Cochrane additionally announced a platform study (2025–2026) piloting **Laser AI** and **Nested Knowledge** with Cochrane review author teams under training and supervised protocols [3]. In March 2026 Cochrane Rapid Reviews Methods Group issued a separate position statement on AI in rapid reviews [4]. There is **no Cochrane endorsement of any fully-automated SR tool**. Human oversight is mandatory.

## 2. Tooling landscape (Covidence, DistillerSR, EPPI, Rayyan, RobotReviewer)

**Covidence** (April 2026): assistive only — RCT Classifier, active-learning screening (EPPI-Centre model), sponsorship-source extraction where "the reviewer must actively decide to accept or reject each suggestion"; framed as "responsible automation" [5]. **DistillerSR** launched Smart Evidence Extraction (SEE) on 8 April 2026 with GenAI end-to-end extraction, but documentation retains "full auditability and human governance over AI-generated outputs"; adopted NIST AI Risk Management Framework [6]. September 2025 DistillerSR Agentic AI release also preserves human curation [6]. **EPPI-Reviewer**: active-learning ML integrated; LLM integration under evaluation [7]. **Rayyan**: ML-assisted screening; no fully-autonomous clinical SR mode [7]. **RobotReviewer**: the only dedicated RoB automation tool; 2022 BMC Medical Research Methodology evaluation reported **72% mean agreement** with dual humans, moderate reliability on randomisation/allocation, only slight reliability on incomplete outcome data and selective reporting [8]. No Cochrane review uses RobotReviewer as sole assessor.

## 3. Dedicated clinical-review AI (FutureHouse, Elicit, Undermind, etc.)

**PaperQA2** (FutureHouse): SOTA on RAG-QA-Arena science (+12.4%), validated on the 200-question **LitQA2** [9]; added clinicaltrials.gov search in 2025 [10]. Not validated for PRISMA-compliant SR output. **WikiCrow**: biology Wikipedia articles, not SRs. **Elicit Systematic Review** (Bernard et al., *BMC Med Res Methodol* 2025): found only **3/17 (17.6%)** of included studies from an umbrella review, though it surfaced additional eligible studies [11][12]; *adjunct only*. **Undermind**: no benchmarking vs. humans; "never designed for formal systematic review or evidence synthesis" [13]. **Silatus**, **Systematic.com**, **SakanaAI**: no peer-reviewed clinical SR validation located.

## 4. Regulatory context (FDA, EMA, NICE)

**EMA + FDA joint "Guiding Principles of Good AI Practice in Drug Development"** — released 16 January 2026 — 10 high-level principles including human-centric design, risk-based validation, data governance [14][15]. Not formal industry guidance yet. **FDA draft guidance** (January 2025) on AI in regulatory decision-making for drugs/biologics requires a 7-step credibility framework and life-cycle validation [14]. **NICE Position Statement on AI in Evidence Generation** (August 2024, current through April 2026): explicitly permits AI for search strategy generation, classification, screening, but states "AI should augment, not replace, human judgment, ensuring that a capable and informed human remains in the loop." Submissions "should not lead with AI-generated data where there are alternatives" [16][17]. No regulator accepts an AI-authored SR as a standalone submission.

## 5. Academic critical assessments

Sung, Altahsh, Garrison (2026, *JMIR Formative Research*): benchmarked GPT-5 and fine-tuned **ASReviewLab** against 25 recent Cochrane SRs (144,120 abstracts, 1,123 included studies). GPT-5 placed **79.4%** of main-results publications in top 15%; some included studies required reviewing **up to 96% of abstracts**. ASReviewLab: **89%** in top 500; **11% (46 studies) missed entirely**. Verbatim: tools "are not yet sufficiently reliable … [that] lower-ranking studies do not require evaluation by a human reviewer" [18]. A 2025 *Syst Rev* scoping review (Landschaft et al.) concluded LLMs are "on the rise, but not yet ready for use" in SRs [19]. A 2025 JMIR network meta-analysis found humans remain more accurate on clinical research questions [20]. Optimised GPT-4o and Claude-3.5 reached ~98% sensitivity/specificity on *title/abstract screening* in narrow domains [21] — screening only, not extraction or synthesis.

## 6. Reporting standards

**TRIPOD-LLM** (Nature Medicine, Jan 2025, Gallifant et al.): 19 main items, 50 subitems; mandates transparency, human oversight, task-specific performance reporting [22]. **PRISMA-trAIce** (JMIR AI, 2025): PRISMA 2020 extension for SRs using AI as a methodological tool; transparent reporting of all AI steps [23]. Both are now the *de facto* reporting standards for any SR that touches AI.

## 7. Benchmarks for clinical SR quality

**LitQA2** (FutureHouse, 200 expert-authored multiple-choice) is the closest public benchmark; not a PRISMA-compliance metric [9]. MedQA and PubMedQA address clinical QA, not SR methodology. No public 2025–2026 benchmark directly scores PRISMA 2020 / AMSTAR 2 / GRADE / RoB 2 compliance of AI-generated SRs. This is a real gap.

## Can any tool produce a PRISMA-compliant SR without humans in the loop? (April 2026)

**No.** The evidence is uniform: Cochrane/Campbell/JBI/CEE (Oct 2025) *mandate* human oversight [1]; FDA/EMA (Jan 2026) require human-centric design [14]; NICE (2024, current) requires human-in-loop [16]; the best 2026 Cochrane-benchmark study shows GPT-5 misses included studies that sit as deep as the 96th percentile of abstract rankings [18]; Elicit finds <18% of umbrella-review studies [11]; RobotReviewer agrees with dual humans only 72% of the time [8]. No tool — including PaperQA2, DistillerSR SEE, Covidence, Elicit Systematic Review, Nested Knowledge — is currently validated to output a PRISMA-2020-compliant clinical SR autonomously. Vendor marketing claiming otherwise contradicts published validation data.

## Where the clinical community is ahead of general LLM research products

Five disciplines general LLM "deep research" products have not adopted: **(a) formal reporting checklists** (PRISMA 2020, TRIPOD-LLM, PRISMA-trAIce) forcing per-step AI-use disclosure [22][23]; **(b) mandatory dual-reviewer protocols** treating AI as at most *one* of two assessors [3][5]; **(c) pre-registered protocols** (PROSPERO) fixing inclusion criteria before search; **(d) validated RoB instruments** (Cochrane RoB 2, AMSTAR 2, GRADE) that general products ignore or fake; **(e) explicit sensitivity thresholds** — clinicians will not accept 80% recall when one missed trial can flip a GRADE rating. The 96th-percentile depth in [18] is why. POLARIS-class pipelines aimed at medical output must adopt all five — AMSTAR 2, GRADE, RoB 2, dual-reviewer, pre-registered protocol — before faithfulness stabilises.

---

## References

1. Position statement on AI use in evidence synthesis across Cochrane, Campbell, JBI, Collaboration for Environmental Evidence. 2025. https://pmc.ncbi.nlm.nih.gov/articles/PMC12577299/ (pub. 31 Oct 2025)
2. RAISE framework. https://osf.io/fwaud/ (updated June 2025)
3. Cochrane AI platform study announcement. https://www.cochrane.org/about-us/news/cochrane-announces-selected-ai-tools-innovative-platform-study (2025)
4. Cochrane Rapid Reviews Methods Group position on AI. https://pmc.ncbi.nlm.nih.gov/articles/PMC12644243/ (March 2026)
5. Covidence responsible automation. https://www.covidence.org/blog/responsible-automation/ (current April 2026)
6. DistillerSR SEE GenAI launch, 8 April 2026. https://www.pharmiweb.com/press-release/2026-04-08/distillersr-launches-the-industrys-most-advanced-genai-capabilities-for-extracting-scientific-liter
7. EPPI-Centre tools survey. https://eppi.ioe.ac.uk/CMS/Portals/0/automation_tools_summary_v2.pdf
8. Arno et al. Automating RoB assessment: human vs ML. *BMC Med Res Methodol* 2022. https://link.springer.com/article/10.1186/s12874-022-01649-y
9. PaperQA2 RAG-QA-Arena SOTA. https://www.futurehouse.org/research-announcements/paperqa2-achieves-sota-performance-on-rag-qa-arena-science-benchmark (2024)
10. PaperQA2 clinical trials. https://futurehouse.gitbook.io/futurehouse-cookbook/paperqa/docs/tutorials/querying_with_clinical_trials (2025)
11. Bernard et al. Elicit for SR. *BMC Med Res Methodol* 2025. https://link.springer.com/article/10.1186/s12874-025-02528-y
12. Elicit evaluation PMC. https://pmc.ncbi.nlm.nih.gov/articles/PMC11921719/ (March 2025)
13. Undermind evaluation notes. https://aarontay.substack.com/p/ai2-paper-finder-and-futurehouse (2025)
14. FDA draft guidance AI in drug development, January 2025; joint FDA/EMA principles, 16 Jan 2026. https://www.ema.europa.eu/en/news/ema-fda-set-common-principles-ai-medicine-development-0
15. RAPS coverage of FDA/EMA principles. https://www.raps.org/news-and-articles/news-articles/2026/1/ema-fda-issue-joint-ai-guiding-principles-for-drug (Jan 2026)
16. NICE Position Statement ECD11 on AI in evidence generation. https://www.nice.org.uk/corporate/ecd11/resources/use-of-ai-in-evidence-generation-nice-position-statement-pdf-40464268944325 (Aug 2024, current Apr 2026)
17. NICE position summary (Lumanity). https://lumanity.com/perspectives/summary-of-nice-position-statement-on-ai-use-in-evidence-generation/
18. Sung, Altahsh, Garrison. AI-Assisted Systematic Review: Humans Still Need to Review All Abstracts. *JMIR Form Res* 2026;10:e82896. https://formative.jmir.org/2026/1/e82896
19. Landschaft et al. LLMs for SRs scoping review. *Syst Rev* 2025. https://pubmed.ncbi.nlm.nih.gov/40021099/
20. Accuracy of LLMs on clinical research questions. *JMIR* 2025. https://www.jmir.org/2025/1/e64486
21. GPT-4o / Claude-3.5 screening performance. JMAI 2025. https://jmai.amegroups.org/article/view/10102/html
22. Gallifant et al. TRIPOD-LLM. *Nat Med* Jan 2025. https://www.nature.com/articles/s41591-024-03425-5
23. PRISMA-trAIce checklist. *JMIR AI* 2025. https://ai.jmir.org/2025/1/e80247
