# LOCKED golden question set — Path-B DR head-to-head (I-safety-002b / #925)

**Status**: LOCKED 2026-05-28 (Claude + Codex, 2 consults). Replaces the rejected homegrown `clinical_n10.json` set (selection-biased per operator). Frozen BEFORE any system output is viewed.

**Source**: DeepResearch Bench v1 — `data/prompt_data/query.jsonl` (the recognized golden long-form deep-research benchmark; RACE report-quality + FACT citation-trust). All 5 are `language == "en"`, expert-designed PhD-level / high-complexity tasks.

**Honest label (Codex — do NOT overclaim)**: *"DRB-EN high-stakes citation-faithfulness stress slice: 3 clinical tasks + 2 source-critical non-clinical tasks."* NOT "the 5 objectively hardest DRB questions" (DRB has no official hardness ranking) and NOT "representative of all DRB-EN." The defensible claim: a pre-registered slice of golden DRB-EN where POLARIS's declared differentiator — per-claim faithfulness under citation-sensitive, high-stakes conditions — should matter most.

**Pre-registered selection rule (bias-free; selection used NO system output)**:
1. Universe = DRB v1 `query.jsonl`, `language=="en"`.
2. Include ALL DRB-EN Health tasks with direct clinical/patient-management consequences; exclude non-clinical psychology/social-science health items → yields #75, #76, #78 (excludes #77 misinformation/psych).
3. Fill remaining slots from DRB-EN tasks whose prompt makes source faithfulness a CENTRAL deliverable + where unsupported authority would materially change validity.
4. Rank remaining by: explicit source/citation/case-law constraint → high-stakes legal/clinical/financial/policy consequence → ascending ID tie-break → picks #72, #90. (Excludes #54 not source-constrained; #81 lower-stakes; #62 off-turf STEM control.)
5. NO POLARIS/ChatGPT/Gemini/Perplexity output used in selection.

---

## The 5 (verbatim golden prompts)

### #75 — Health (clinical) — *primary clinical slice*
"Could therapeutic interventions aimed at modulating plasma metal ion concentrations represent effective preventive or therapeutic strategies against cardiovascular diseases? What types of interventions—such as supplementation—have been proposed, and is there clinical evidence supporting their feasibility and efficacy?"

### #76 — Health (clinical) — *primary clinical slice*
"The significance of the gut microbiota in maintaining normal intestinal function has emerged as a prominent focus in contemporary research, revealing both beneficial and detrimental impacts on the equilibrium of gut health. Disruption of microbial homeostasis can precipitate intestinal inflammation and has been implicated in the pathogenesis of colorectal cancer. Conversely, probiotics have demonstrated the capacity to mitigate inflammation and retard the progression of colorectal cancer. Within this domain, key questions arise: What are the predominant types of gut probiotics? What precisely constitutes prebiotics and their mechanistic role? Which pathogenic bacteria warrant concern, and what toxic metabolites do they produce? How might these findings inform and optimize our daily dietary choices?"

### #78 — Health (clinical) — *primary clinical slice*
"Parkinson's disease has a profound impact on patients. What are the potential health warning signs associated with different stages of the disease? As family members, which specific signs should alert us to intervene or seek medical advice regarding the patient's condition? Furthermore, for patients who have undergone Deep Brain Stimulation (DBS) surgery, what daily life adjustments and support strategies can be implemented to improve their comfort and overall well-being?"

### #72 — Education & Jobs (source-critical) — *citation-faithfulness IS the task*
"Please write a literature review on the restructuring impact of Artificial Intelligence (AI) on the labor market. Focus on how AI, as a key driver of the Fourth Industrial Revolution, is causing significant disruptions and affecting various industries. Ensure the review only cites high-quality, English-language journal articles."

### #90 — Crime & Law (source-critical) — *case-law citation-sensitive, high-stakes*
"Analyze the complex issue of liability allocation in accidents involving vehicles with advanced driver-assistance systems (ADAS) operating in a shared human-machine driving context. Your analysis should integrate technical principles of ADAS, existing legal frameworks, and relevant case law to systematically examine the boundaries of responsibility between the driver and the system. Conclude with proposed regulatory guidelines or recommendations."

---

## Reporting (Codex)
Report the **3-task clinical slice** and the **5-task overall** SEPARATELY. Do NOT average into "POLARIS wins clinical 5/5." Contamination caveat: these are public golden questions → "public-golden, source-grounded evaluation," not "unseen"; judge claims against RETRIEVED sources, never memorized reference reports. #72/#90 evidence a "sovereign DR across high-stakes domains" claim, NOT clinical-safety per se.

## Next
Re-author the 5 gold rubrics against THESE golden questions' real independent sources → Codex §-1.1 re-verify + hash-pin → POLARIS full-power runs (through the gate) + dual line-by-line → operator competitor exports fold in.
