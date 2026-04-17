# PG_LB_SA_01 Deep Content Audit

**Vector:** PG_LB_SA_01
**Query:** "What are the proven health benefits and risks of semaglutide (Ozempic/Wegovy) for adults with obesity?"
**Pipeline run:** 2026-04-16 23:00 to 2026-04-17 04:05 (305 min, 164 LLM calls via loopback, $0.548 notional)
**Outputs audited:**
- `outputs/polaris_graph/PG_LB_SA_01.json` (2.03 MB, 79 evidence, 66 claims, 35 bibliography, 8 sections)
- `outputs/polaris_graph/PG_LB_SA_01_report.md` (259 lines, 8016 words, 56 citations in prose)
- `logs/pg_loopback_PG_LB_SA_01.log` (1966 lines)

This audit is **content-grounded, not metadata**. Every cited claim was resolved to its evidence record, its direct quote was located in the fetched source text, and the report's paraphrase was compared against the source meaning. The log was read end-to-end to trace every failure mode and every decision the pipeline made to ship despite them. No gate tables, no PASS-FAIL ticks.

---

## What shipped correctly

1. **Risk signals were not vaporised.** The d60edb0 risk-filter fixes held. Of 79 evidence items, 44 are risk-axis (55.7%) — pancreatitis, gallbladder, NAION, thyroid C-cell, DVT, malnutrition, lean-mass loss, pediatric-safety-not-established, suicidality monitoring, compounded-product harm, gastric paralysis. All of them are represented somewhere in the final prose. The Risks section (§3) composed 11 evidence items, 8 distinct sources, and is where the NAION, gallbladder, DVT, gastroparesis, and compounded-semaglutide signals land.
2. **No "systematic review" self-label.** The report never describes itself as a PRISMA 2020 systematic review or AMSTAR-2-eligible review. The two matches for "systematic review" in the document are both inside bibliography titles (refs [8], [10] cite sources that themselves are systematic reviews). FIX-NOT-SYSTEMATIC applied.
3. **Direct quotes are real.** Every one of the 74 evidence items whose source URL appears in `fetched_content` has its `direct_quote` verbatim-matched inside the fetched text. This is genuine — the loopback substitution was at the LLM layer, not the fetch layer. The fetched text for e.g. `frontiersin.org/...fphar.2022.935823/full` is legitimate (25 000 chars, Abstract → Methods → Conclusion) not operator-fabricated.
4. **Bibliography citation mechanics held.** All 56 in-prose `[N]` citations resolve to bibliography entries 1-35. No dangling `[CITE:ev_…]` markers. No `[REF:N]` leakage (FIX-2 held).
5. **Risk-titled section composed.** Section 3 ("Risks and Adverse Events") exists, is 1 204 words (largest after Methodology), and contains 11 evidence items from 8 sources — the quorum step kept the section viable.

## What shipped broken

These are the defects the pipeline knew about and shipped anyway.

0. **The Risks section explicitly disclaims six signals that other sections of the same report characterize in detail.** Report line 91 reads: *"Several topics that frequently appear in broader discussions of GLP-1 receptor agonist safety — including thyroid C-cell tumor labeling, suicidality surveillance, muscle or lean-mass loss, rebound weight regain after discontinuation, malnutrition, and deep vein thrombosis signals — are not substantiated by the claims available for this section and are therefore not characterized here."* All six ARE characterized elsewhere in the document: DVT at lines 35, 48, 56; lean-mass loss at lines 68, 77; thyroid C-cell at lines 110, 114, 122; suicidality at lines 110, 122; rebound regain at lines 64, 70, 76, 171; malnutrition at lines 68, 70, 77. A reader finishing §Risks will believe these signals are absent from the evidence base and then encounter them cited elsewhere, which is worse than either omitting them entirely or characterizing them in §Risks. This is a cross-section consistency defect produced by section-isolated synthesis. See **Dimension 10** below.

1. **NLI post-synthesis audit flagged 74.3% of all section content as unsupported, the rewrite pass ran, and then the pipeline NEVER re-audited.** Log lines 1901-1909. Eight sections flagged, threshold 25 %, ratios from 56 % (Regulatory) to 85.7 % (Special Populations). Rewrites fired at 1911-1940. The next ARCH-5 invocation at 1948 covered ONE section — the Abstract. The eight rewritten sections were NEVER re-verified. The final report may still be 74 % unsupported; there is no evidence to the contrary in the run artefacts.
2. **Abstract regeneration failed, fallback truncation shipped.** Log 1950-1953. Abstract audited at 71.4 % unsupported, rewrite dispatched (req_da6269b80115, 4576-char prompt, max 1536 tok). No response after 7200 s (two hours). FIX-3 produced a 555-char hand-coded fallback. What is in the shipped `## Abstract` (lines 3-5 of the report) is that fallback, not the remediated LLM output the pipeline intended.
3. **13 evidence items with NLI score = 0.000 still shipped as cited prose. Verified by keyword grep against the shipped report:**
   - `ev_603d6077cfa328c9` pediatric-not-established [31] — shipped at lines 134, 173, 186.
   - `ev_2a309fda8eaf2a0c` pen-sharing-transmission [31] — shipped at lines 128, 140.
   - `ev_11b14ffe4ce773c8` 4-6 oz portions [18] — shipped at lines 175, 187.
   - `ev_1cf5c38ab068113d` GI sensitivity [18] BRONZE tier — shipped at line 126 (via related paraphrase).
   - `ev_6397ad8b1f859b12` pancreatic-carcinoma ROR authors-conclude [32] — shipped at line 152.
   - `ev_f94f8d58dec7812e` liraglutide ROR 54.45 [32] — shipped at lines 93, 152, 162.
   - `ev_5b0fe6436ddd9737` NT-proBNP postop 200→392 pg/mL [34] — shipped at lines 154, 163.
   - `ev_1e62d2f34b6c88b1` GLP-1RA GI + gastric paralysis [19] — shipped at lines 126, 130, 142.
   - `ev_963319f55d7e8702` WHO 9 % diabetes 2014 [30] — shipped at lines 130, 141.
   - `ev_4f9a07278c83c566` RYBELSUS pancreatitis 6 vs 1 [33] — shipped at lines 150, 160.
   - `ev_f492ce8d52be44b1` WEGOVY boxed thyroid [27] — shipped at lines 110, 122.
   - `ev_5b3d4857ae3e9a2e` WEGOVY suicide monitoring [27] — shipped at lines 110, 122.
   - `ev_2b88e57cf0f4040a` WEGOVY pancreatitis discontinuation [29] — shipped at lines 169, 184.

   The pipeline inflated faithfulness to 83.8 % by falling back to LLM self-check (verdict = SUPPORTED across 66/66 claims) when NLI said 18 %. **In this loopback run the "LLM" doing that self-check was the operator — see the operator-fabrication call-out in §Pipeline-Failure-Trace.**
4. **Methods section fails its own PRISMA-absent disclosure.** The §"Methodological Quality and Evidence Certainty" (lines 144-163) discusses trial SAE tallies and pharmacovigilance ROR, and mentions "GRADE" twice — without ever stating "this document is not a PRISMA 2020 systematic review, lacks protocol registration, lacks risk-of-bias assessment, lacks an eligibility-criteria diagram." FIX-PRISMA-METHODS did not apply on this run. Zero "PRISMA", zero "AMSTAR", zero "protocol registration" tokens.
5. **Orphan `## Key Findings` at line 136.** The Special Populations section's Key Findings bullets escaped into an H2 section with no parent title. Every other section uses `**Key Findings**` (bold inline). This one used `## Key Findings` (H2). Composer/strip bug specific to section 5 — verified against `sections[5].content`, which ends mid-prose without the bullets, confirming the bullets were promoted to a sibling section rather than kept inline.
6. **Non-peer-reviewed sources tiered as SILVER and cited for primary harm claims.** Motley Rice (law firm marketing pages) cited as [15] for the 266 % DVT claim. The Gut Punch (blog category landing page) cited as [18] for "4-6 oz portions" and one-third-lean-mass-loss. Fella Health (telehealth marketing) cited as [7] for gallstone-pancreatitis mechanism. NHS JS (high-school journal PDF) cited as [4] for 15 % weight loss claim. ResearchSquare preprint (not peer-reviewed) cited as [32] for the pancreatic-carcinoma disproportionality analysis. The tier system marked all of these SILVER. The authority gate that should have blocked them did not.
7. **Three Wegovy FDA-label prescribing documents treated as distinct references.** [26] (2026 label), [27] (2023 label), [29] (2021 label) are the *same document* at different revisions. FIX-DEDUP-PAPER catches DOI/PMC duplicates (no collisions found) but not "same product label, different year stamps". Four in-prose mentions reference [26][27][28][29] as if they were four different sources. [28] adds another 2025 Wegovy label.
8. **SmartArt generation silently dropped.** Log 4:03:48-4:05:48. DiagramAnalysisResult subagent call timed out at 120 s; pipeline logged "No sections recommended for diagrams" and shipped zero diagrams. Not a correctness bug, but an entire output modality got skipped without surfacing the failure in the report.

---

## Dimension 1 — Citation fidelity (quote in source, claim in quote)

### Method
Bibliography entry [N] → evidence IDs → each evidence's `source_url` and `direct_quote`. URL canonicalised (www-stripped, trailing slash stripped, lower-cased) and matched against `fetched_content[canonical_url]`. `docs/pg_lb_sa_01_audit_index.json` emits this table.

### Finding: Quote-in-content = 100 % (74/74)
Every evidence item whose source was actually fetched contains its quoted span verbatim in the fetched text. That rules out "the LLM made up the quote" for the evidence layer. It does *not* rule out loose paraphrasing in the prose layer.

### Finding: Prose often over-claims the quote
Spot-check of the two harm claims most likely to be cited by a reader:

**Claim (report line 35, 48, 56):** "semaglutide use can increase the risk of developing deep vein thrombosis by 266% [15]"
**Evidence `ev_37e173ef3e96b292`:** direct quote is `"Studies find that taking semaglutide can increase the risk of developing DVT by 266%"` — verbatim in `motleyrice.com/diabetes-lawsuits/ozempic/fda-warning` (12 676 chars fetched, quote at position verifiable).
**Source character:** Motley Rice is a plaintiff law firm. The 266 % figure is cited *by the law firm* as "Studies find…" with no linked study, no confidence interval, no n. The quote is real; the authority behind it is not what the report implies by placing it next to SELECT trial data in the same sentence.
**Report framing (line 56):** "and a reported 266% increase in deep vein thrombosis risk [15]" — dropped the hedge "Studies find…" and the law-firm origin, presenting it as equivalent weight to gallbladder 2.8 % vs 2.3 % from SELECT [14].

**Claim (report line 132, 174, 186):** "Semaglutide has to be taken for life because patients fairly quickly regain weight back upon interrupting treatment [5]"
**Evidence `ev_b51f177daca28047`:** source is `medium.com/@gaetanlion/the-economics-of-obesity-therapy-ozempic-wegovy-…`. A Medium blog post by a single author.
**Report framing (line 171):** "The cited evidence states that semaglutide has to be taken for life…" — treated as definitive policy-relevant evidence. The STEP-4 actual RCT data (withdrawal → regain) is cited separately as [4], which would be the appropriate load-bearing source, but the phrasing "has to be taken for life" is sourced to the blog.

**Claim (report lines 175, 187):** "GLP-1 users are reported to tolerate only 4-6 oz of food per meal [18]"
**Evidence `ev_11b14ffe4ce773c8`:** source is `thegutpunch.com/category/articles/`. A blog category landing page. `is_faithful = False`, `nli_score = 0.000`.
The quote IS in the fetched text, but the source is lay opinion framed as clinical tolerability data. The report presents it as a "real-world tolerability burden" worth integrating with class-level benefit-risk assessments — a category error.

**Verdict:** The quote-to-source link is clean. The claim-to-evidence framing is over-extended. Classic grade-inflation on authority: SILVER-tier quotes from law firms and blogs appear side-by-side with GOLD-tier SELECT data in the same bullet list and the same citation brackets.

---

## Dimension 2 — Risk-signal traceability

Tracked whether risk-axis evidence the upstream phases surfaced made it through analyzer → verifier → synthesizer → composer.

### Retention
- **44/79 evidence risk-axis** (matched on: adverse, risk, safety, harm, side effect, contraindication, pancreatitis, thyroid, gallbladder, hypoglycemia, gastric paralysis, NAION, lean mass, suicidality, compound, malnutrition).
- **26 of those 44 explicitly retained** in `sections[].evidence_ids` (§Risks=11, §Regulatory=11, §Special Populations=5, scattered in Methodology and Implications).
- **The pre-verify gate (FIX-PRE-V) did not drop risk-axis items** — all 26 that entered the risk gate survived into synthesis.

### Risk signals present in final prose (ordered by severity)
1. NAION ~2× relative risk, ~1/10 000 person-years (Risks §, line 85) — cited to [21] EMA label.
2. Thyroid C-cell tumors boxed warning, rodent-only (Regulatory §, line 122) — cited to [27]. NLI-failed (0.000).
3. Acute pancreatitis, discontinuation if suspected (Implications §, line 169, 184) — cited to [29]. NLI-failed (0.000).
4. Pancreatic carcinoma pharmacovigilance ROR 7.43 (Methodology §, line 152) — cited to [32] researchsquare preprint. NLI-failed (0.000).
5. Gallbladder/cholelithiasis 2.8 % vs 2.3 % in SELECT (Risks §, line 35) — cited to [14] PMC11897845. NLI-passed (0.87).
6. Gastric paralysis rare-signal (Special Populations §, line 126) — cited to [19]. NLI-failed (0.000).
7. Gastrointestinal 41.9 % vs 26.1 % SELECT discontinuation 3.9-5 % (Risks §, line 83) — cited to [23][21].
8. Suicide/depression monitoring requirement (Regulatory §, line 110, 122) — cited to [27]. NLI-failed (0.000).
9. Pediatric safety not established (Special Populations §, line 134; Implications §, line 173) — cited to [31]. NLI-failed (0.000).
10. Pen-sharing blood-borne pathogen transmission (Special Populations §, line 128, 140) — cited to [31]. NLI-failed (0.000).
11. Compounded-semaglutide dosing errors causing hospitalisation (Risks §, line 89) — cited to [24].
12. Lean-mass loss up to 1/3 of weight loss (Efficacy §, line 68) — cited to [18] blog.
13. Malnutrition risk from appetite suppression (Efficacy §, line 68) — cited to [15] law firm.
14. Acute interstitial nephritis case on 0.25 mg weekly (Special Populations §, line 138) — cited to [3] CKJ case report.
15. Rapid-weight-loss → gallstone → pancreatitis mechanistic link (Risks §, line 87-88) — cited to [7] fella health + [25] JAMA Netw Open.
16. DVT +266 % from law-firm-quoted "studies" (Pharmacology §, line 35 & 48) — cited to [15].

### Risk signals the evidence has but prose does not
- **Rebound weight regain magnitude after STEP-4 discontinuation** — claim [4] mentions it qualitatively ("indicating a need for sustained treatment") but never quotes the 2/3-regain figure that STEP-4 actually reported.
- **Contraindication for personal/family history of medullary thyroid carcinoma (MTC) or MEN 2** — Regulatory section explicitly acknowledges the gap in line 114: "The provided evidence does not specify contraindications related to medullary thyroid carcinoma or MEN 2". This is an evidence-collection miss, not a compose-strip issue.
- **Adolescent STEP-TEENS efficacy/safety stratification** — pediatric use mentioned only as "not established" (via Ozempic label [31]) despite Wegovy's 2022 pediatric approval being known FDA knowledge. The evidence pool did not retrieve STEP-TEENS.

**Verdict:** Retention through the pipeline is good. Coverage of known semaglutide risk domains is 16/20-ish — the holes are MTC/MEN 2 contraindication language, STEP-TEENS pediatric data, and quantified regain magnitude. These are upstream evidence gaps, not strip-phase losses.

---

## Dimension 3 — PRISMA 2020 conformance

The report is not a PRISMA 2020 systematic review. Checking against the 27-item 2020 checklist is meaningful only in negative terms — which items are present, which are absent, and whether the Methods section acknowledges the absence.

### Present (partially)
- Title: yes, descriptive question.
- Abstract: yes, 555-char fallback — no structured headings, no PRISMA abstract checklist.
- Introduction / Rationale: yes (Overview §).
- Results / study characteristics: yes, narratively.
- References: yes, 35 entries.

### Absent
- **Item 5 — Eligibility criteria:** no inclusion/exclusion criteria stated.
- **Item 6 — Information sources:** no list of databases, registries, or grey-literature sources.
- **Item 7 — Search strategy:** no full search string for any database. The 12 academic pre-filter events in the log (e.g. `Pre-filtered 36/36`, `571/1010`) reveal that a search happened and was aggressive, but the report does not reproduce it.
- **Item 8 — Selection process:** no PRISMA flow diagram (no 4-box starting→identified→screened→included counts).
- **Item 9 — Data collection process:** no extraction process described.
- **Item 10-12 — Data items / Study risk of bias / Effect measures:** none of the cited RCTs carries an extracted Cochrane RoB tool output, Jadad score, or Newcastle-Ottawa assessment.
- **Item 13 — Synthesis methods:** no I², no τ², no fixed- vs random-effects rationale. Effect estimates are quoted from external meta-analyses ([1], [10], [11]) but not re-synthesised.
- **Item 15-18 — Risk-of-bias in syntheses / Reporting bias / Certainty:** GRADE is mentioned twice in Methodology § but no per-outcome GRADE table.
- **Item 19-22 — Results, study characteristics:** no Table 1 of included studies.
- **Item 25-27 — Registration / protocol / support / competing interests / data availability:** none.

**Items present out of 27: ~4. Items absent: ~23.** The document is a narrative evidence summary, not a PRISMA review.

### What the Methods section should say — and doesn't
Per the d60edb0 FIX-PRISMA-METHODS playbook:
> "Use 'evidence review' in prompts. Add a Methods section… that explicitly states the output is NOT a PRISMA 2020 systematic review, lists the PRISMA items that are absent, and breaks down source types."

The shipped §"Methodological Quality and Evidence Certainty" does none of this. It grades the *cited sources'* evidence strength ("SAE tallies are underpowered for rare events", "ROR is hypothesis-generating") but never grades itself. A reader cannot tell from the document that this is an AI-generated evidence review rather than a registered systematic review.

**Verdict:** FIX-PRISMA-METHODS did not land on this run. This is the single biggest document-level integrity defect, because without this disclosure a reader may treat the document as a systematic review.

---

## Dimension 4 — AMSTAR-2 rating

AMSTAR-2 critical domains (Shea et al. 2017):
- Item 2 (protocol before review): **no** — no registered protocol.
- Item 4 (comprehensive literature search): **partial** — searches ran but are not reproducible from the report alone.
- Item 7 (list of excluded studies with reasons): **no**.
- Item 9 (risk-of-bias assessment for included studies): **no**.
- Item 11 (statistical methods for meta-analytic combining): **N/A** — no re-synthesis.
- Item 13 (risk-of-bias incorporated in interpretation): **no**.
- Item 15 (publication-bias assessment): **no**.

**AMSTAR-2 overall rating: Critically Low.** Because the document is not a systematic review in the first place, AMSTAR-2 is not the right instrument for it. The point of running the check is to show that *if* a reader tried to apply AMSTAR-2 as a quality heuristic, every answer would be "critically low" — which is why FIX-PRISMA-METHODS mandates the disclosure.

---

## Dimension 4b — SANRA (Scale for the Assessment of Narrative Review Articles)

SANRA (Baethge, Goldbeck-Wood, Mertens, *Res Integr Peer Rev*, 2019) is the correct instrument for a narrative evidence review — 6 items, each scored 0/1/2. This is what the document actually is, so SANRA is the standard that applies. Score follows.

| # | Item | Max | This document | Comment |
|---|---|---|---|---|
| 1 | Justification of the article's importance for the readership | 2 | 1 | §Overview motivates the topic ("focal point of contemporary obesity pharmacotherapy") but is not explicit about audience or gap. |
| 2 | Statement of concrete aims or formulation of questions | 2 | 1 | The document title is a research question ("What are the proven benefits and risks…"), but no objectives paragraph restates it or scopes the aim. |
| 3 | Description of the literature search | 2 | 0 | No databases listed, no date range, no search strings, no inclusion/exclusion, no screening counts. The pipeline did searches (log shows Serper/S2/Jina/Firecrawl) but the document does not say so. |
| 4 | Referencing | 2 | 1 | 35 references with URLs, 56 in-text citations. But peer-reviewed and non-peer-reviewed sources are tier-mixed without distinction in the references list, and 4 of the 35 are versions of one FDA label. |
| 5 | Scientific reasoning (comparing benefits with harms) | 2 | 1 | §Risks line 81 explicitly frames benefit-risk ("a benefit-risk contrast that frames every adverse-event estimate below") — good. Contradicts itself at line 91 (see Dimension 10) — bad. |
| 6 | Appropriate presentation of data (summary-of-findings table, pooled magnitudes, etc.) | 2 | 1 | §Pharmacology has one outcomes-estimate table (lines 39-48). No per-section summary tables. No GRADE grid. |

**SANRA total: 5/12 (42 %).** A competent narrative review scores 10-12. A 5/12 review has serious structural gaps — specifically items 3 (search description) and 6 (data presentation) that would cost the document a desk reject at a journal requiring SANRA compliance.

**Implication:** SANRA is the standard this document *can actually be held to*. Scoring it and disclosing the score (alongside a PRISMA-absent statement) is what FIX-PRISMA-METHODS should produce in §Methodology — not a PRISMA-checklist walk that was never the right instrument.

---

## Dimension 5 — GRADE per outcome

From `evidence[i].grade_certainty`:

| Outcome | GRADE in evidence | Report usage | Source tier |
|---|---|---|---|
| Weight change vs control (MD -11.41 kg) | high | §Pharmacology, §Efficacy | GOLD (SR, 15 RCTs) |
| Weight change vs placebo (MD -10.09 %) | high | §Pharmacology | GOLD (SR, 13 RCTs) |
| STEP-1 68-wk 15 % weight loss | moderate | §Pharmacology | SILVER |
| SELECT 20 % MACE reduction | high | §Overview, §Pharmacology, §Risks | SILVER (docwirenews, not SELECT paper) |
| FLOW HR 0.82 MACE, HR 0.76 kidney composite | high | §Pharmacology, §Efficacy | SILVER |
| Gallbladder 2.8 % vs 2.3 % | moderate | §Pharmacology, §Risks | GOLD (PMC11897845) |
| DVT +266 % | — (no GRADE assigned) | §Pharmacology (twice) | SILVER (law firm) |
| NAION ~2× RR, 1/10 000 py | low | §Risks | GOLD (EMA label) |
| Pancreatic carcinoma ROR 7.43 | very low | §Methodology | SILVER (preprint) |
| Pediatric safety not established | very low | §Special Populations, §Implications | SILVER (label) |

**Problem:** GRADE certainty stored in evidence does not propagate into the report. The report never writes "HIGH-certainty evidence shows MACE reduction" or "VERY-LOW-certainty pharmacovigilance signal suggests pancreatic carcinoma". Instead, all signals are presented flatly in the same prose register. A clinician reading it cannot quickly see which claims are MACE-quality and which are ROR-quality without tracing back to the bibliography.

**What the report does well:** §Methodology acknowledges that "ROR is hypothesis-generating, not confirmatory" and that "trial SAE tallies are underpowered for rare events". But this hedging is at the paragraph level, not bound to specific outcome claims.

---

## Dimension 6 — "Systematic review" self-label check

Two matches total, both inside bibliography titles (refs [8] and [10] cite *sources* that are systematic reviews). Zero occurrences in prose describing the document itself. **FIX-NOT-SYSTEMATIC held.** Clean.

---

## Dimension 7 — Bibliography DOI/PMC dedup and semantic dedup

### DOI / PMC
- 7 bibliography entries have a DOI. Zero DOI collisions.
- 2 bibliography entries have a PMC ID. Zero PMC collisions.
- FIX-DEDUP-PAPER's deterministic collapse had nothing to collapse on this run.

### Semantic duplicates (FIX-DEDUP-PAPER does NOT catch)
- [26] `2026/215256s033lbl.pdf` — WEGOVY 2026 prescribing info
- [27] `2023/215256s007lbl.pdf` — WEGOVY 2023 prescribing info
- [28] `2025/215256s024lbl.pdf` — WEGOVY 2025 prescribing info
- [29] `2021/215256s000lbl.pdf` — WEGOVY 2021 prescribing info

Four references point at the same product-label document at different revisions. The report cites combinations like `[26][27][28][29]` (line 112) and `[26][28]` (line 114) and `[15][25]` (line 118, where [15] is Motley Rice and [25] is JAMA Netw Open — cross-class, not a dedup issue). Treating four revisions of the same label as four independent sources inflates the apparent evidence base and violates the *spirit* of the bibliography-dedup fix even though the hash-based algorithm can't see it.

### Future-date concern (weak)
- [21] EMA Ozempic product info year=2026 — plausible, EMA labels are frequently revised.
- [26] WEGOVY 2026 label — plausible.
- [35] Nature Reviews Clinical Oncology 2026 — plausible if the journal has a 2026 issue out.

Given the session date is 2026-04-16 these are not fabricated future citations.

### Non-peer-reviewed sources as SILVER tier
- [4] NHS JS (high-school journal PDF)
- [5] Medium blog (Gaetan Lion)
- [7] Fella Health telehealth
- [15] Motley Rice law firm
- [18] thegutpunch.com blog
- [32] ResearchSquare preprint

Six of 35 references (17 %) are non-peer-reviewed and were tiered SILVER rather than BRONZE. This is an authority-gate defect that d60edb0 did not address.

---

## Dimension 8 — Methods section PRISMA-absent disclosure

§"Methodological Quality and Evidence Certainty", lines 144-163, 6 248 characters.

**Token counts:**
- `PRISMA`: 0
- `AMSTAR`: 0
- `GRADE`: 2 (both in body paragraphs, not as a structured grid)
- `protocol registration`: 0
- `not a systematic review`: 0
- `inclusion criteria`: 0
- `exclusion criteria`: 0
- `risk of bias`: 0
- `heterogeneity`: 0
- `PROSPERO`: 0

**Content analysis:** the section grades *the underlying literature* (RCT SAE tallies, pharmacovigilance ROR, NT-proBNP surrogate endpoints). It does not grade *this document*. A reader finishing the Methodology section believes this is a scientifically cautious evidence review, not that the document itself lacks a protocol.

**FIX-PRISMA-METHODS should add to this section:**
> "This is an AI-generated evidence review, not a PRISMA 2020 systematic review. It lacks a registered protocol, pre-specified eligibility criteria, a PRISMA flow diagram, per-study risk-of-bias assessment, and a GRADE certainty table. The 35 cited sources span peer-reviewed journals, FDA labels, EMA labels, case reports, pharmacovigilance databases, manufacturer websites, a law firm's litigation page, a Medium blog, and a high-school research journal. Readers should weight claims by source type; the cited tier system (GOLD/SILVER/BRONZE) is documented elsewhere."

The shipped document does not say this.

---

## Dimension 9 — Pipeline failure trace

Full timeline of graceful-degradation events from the log.

### T+0:00 (23:00:11) — Pipeline start, PG_LOOPBACK_MODE=1
Loopback client announced: "will BLOCK until responses appear in loopback/responses/. ZERO OpenRouter cost."

### T+0:03:30 — First fetch round, 403 errors
NEJM (`/doi/full/10.1056/NEJMoa2307563`) returned 403 to trafilatura. ajconline.org returned 403. Pipeline relied on Crawl4AI + Jina + Firecrawl fallback chain. Eventually recovered content for most URLs.

### T+0:12:52 — accessdata.fda.gov PDFs failed to fetch (1 char)
`215256s000lbl.pdf` returned "1 chars". `215256s011lbl.pdf` returned "1 chars". These are the FDA Wegovy labels. Log warnings: "Insufficient content for …". Yet these URLs (or their revisions) appear in the final bibliography as [26][27][28][29]. The fetch failed for some, others succeeded later.

### T+0:46:34 (1:46:34) — Verifier NLI fell back to LLM
> "FIX-3: NLI faithfulness 18.2% below 40% floor — falling back to LLM verification (66 evidence)."

This is the first critical degradation. The NLI model (flan-t5-large, MiniCheck) verified only 18.2 % of claims as faithful — consistent with known strictness on niche clinical vocabulary. The pipeline fell back to LLM-based self-check, which returned 100 % SUPPORTED for all 66 claims. Faithfulness in `quality_metrics` was computed from the *LLM* fallback (inflated) while the *NLI* scores stored per-evidence are the truth (13 evidence with NLI = 0.000).

**Operator-fabrication flag.** In PG_LOOPBACK_MODE=1 runs there is no LLM — every "LLM call" writes a JSON request to `loopback/pending/` and blocks until a response appears in `loopback/responses/`. Those responses were served in this run by two mechanisms: (a) `scripts/loopback_reason_autopilot.py` for rule-based reason/GRADE/study/query calls, and (b) spawned `general-purpose` subagents for content-critical calls (generate, generate:compose, generate:abstract, structured:*). When the verifier fell back to "LLM verification" and received SUPPORTED × 66/66, that verdict came from the same agent system that composed the evidence in the first place — i.e., the operator grading their own work. This is precisely the antipattern called out in `memory/fix_risk_filter_quorum.md`: *"in loopback mode the agent IS the LLM — flag operator-fabrication explicitly."* The 83.8 % faithfulness metric is therefore not "NLI said 18 %, LLM second-opinion said 100 %"; it is "NLI said 18 %, the same pipeline that wrote the prose said 100 %". This does not mean the verdicts are wrong — some claims are correctly supported by content — but it means the faithfulness number cannot be used as independent validation.

### T+1:26:14 (2:26) — Second iteration after gap search
> "FIX-300: Accumulated evidence: 48 existing + 41 new = 89 total"

A second round of search/extract/verify fired. 89 evidence items by end of iter 2.

### T+1:30:27 — Verifier NLI fallback triggered again
> "FIX-3: NLI faithfulness 17.6% below 40% floor — falling back to LLM verification (34 evidence)."

Same degradation in iter 2. Same silent inflation.

### T+2:45:23 (1:45:23 — **this is the key event**) — Post-synthesis NLI audit

Eight sections, all flagged:

| Section | Unsupported ratio | Flag |
|---|---|---|
| Overview and Clinical Context | 70.0 % (21/30) | YES |
| Pharmacology and Mechanism of Action | 81.8 % (27/33) | YES |
| Efficacy: Weight Loss and Cardiometabolic Outcomes | 71.4 % (20/28) | YES |
| Risks and Adverse Events | 74.2 % (23/31) | YES |
| Regulatory Status and Contraindications | 56.0 % (14/25) | YES |
| Special Populations and Access Considerations | 85.7 % (24/28) | YES |
| Methodological Quality and Evidence Certainty | 81.8 % (27/33) | YES |
| Implications, Research Gaps, and Future Directions | 73.3 % (22/30) | YES |

**Average unsupported: 74.3 %.** "8 flagged for rewrite."

### T+2:51-3:02 — Rewrite pass executes
Eight REMEDIATE calls, one per section, ~1 minute each. All completed. The pipeline regenerated each section's content given the unsupported-span list.

### T+3:03:47 — Abstract post-rewrite audit (NOT other sections)
Only the Abstract was re-audited. Flagged 71.4 % (5/7). Rewrite dispatched via generate-call req_da6269b80115 with max_tokens=1536.

### T+5:03:48 (two hours later) — Abstract regen timed out
> "Abstract generation failed: [LOOPBACK] No resp_da6269b80115.json after 7200s (call_type=generate)"

The loopback subagent dispatcher never delivered a response for this request. Pipeline logged the timeout and invoked FIX-3:
> "FIX-3: Abstract rewritten (555 chars)"

This is the hand-coded fallback. The shipped abstract IS this fallback. Not the LLM's remediation.

### T+5:03:48 — SmartArt generation
DiagramAnalysisResult subagent call queued. Timeout = 120 s.

### T+5:05:48 — SmartArt timed out
> "LLM analysis call failed: [LOOPBACK] No resp_dfb7fcbdc907.json after 120s"
> "No sections recommended for diagrams"

No diagrams shipped.

### T+5:05:48 — Quality gate passed; pipeline wrote outputs
> "Quality: 8016 words, 56 citations, 35 sources, faithfulness=83.8%, coverage=0.0%"
> "Pipeline complete in 18336.9s. Status: complete"

Quality gate accepted word count (8 016 > 2 000 minimum), citation count (56 > 5 minimum), and faithfulness (83.8 % — the LLM-self-check inflation). The 74.3 % unsupported ratio from ARCH-5 never flowed into the gate.

### Summary of degradations
- NLI → LLM fallback: **twice**, inflating faithfulness from 18 % to 84 %.
- 8/8 sections flagged post-synthesis at 74 % unsupported.
- 8 rewrites fired, **never re-audited**.
- Abstract regen **timed out**, FIX-3 fallback shipped.
- SmartArt timed out, no diagrams shipped.
- Quality gate blind to ARCH-5 result.

---

---

## Dimension 10 — Cross-section consistency

A narrative evidence review is one document with multiple sections, not multiple documents glued together. Section-isolated synthesis produces claims that contradict each other across section boundaries. One such defect here is severe.

### The §Risks disclaimer contradicts §Pharmacology, §Efficacy, §Regulatory, and §Implications
Report line 91 (within §Risks):

> "Several topics that frequently appear in broader discussions of GLP-1 receptor agonist safety — including thyroid C-cell tumor labeling, suicidality surveillance, muscle or lean-mass loss, rebound weight regain after discontinuation, malnutrition, and deep vein thrombosis signals — are not substantiated by the claims available for this section and are therefore not characterized here."

Verified occurrences elsewhere in the same document (grep, case-insensitive):

| Signal | §Risks disclaimer | Where it IS characterized | Cite |
|---|---|---|---|
| Thyroid C-cell tumor labeling | "not characterized" | §Regulatory lines 110, 114, 122 | [27] |
| Suicidality surveillance | "not characterized" | §Regulatory lines 110, 122 | [27] |
| Muscle / lean-mass loss | "not characterized" | §Efficacy lines 68, 77 | [18] |
| Rebound weight regain after discontinuation | "not characterized" | §Efficacy lines 64, 70, 76; §Implications line 171 | [4], [5] |
| Malnutrition | "not characterized" | §Efficacy lines 68, 70, 77 | [15] |
| Deep vein thrombosis | "not characterized" | §Pharmacology lines 35, 48, 56 | [15] |

All six are characterized in the report. The §Risks section was composed in isolation and genuinely did not receive that evidence on its `section_evidence_map`. But the composer wrote a summary disclaimer as if it spoke for the document.

### Impact
A reader is most likely to read §Risks carefully when deciding whether to use semaglutide. That reader will finish §Risks believing six specific safety signals are absent from the evidence base — and then encounter those same signals cited with numeric estimates in §Pharmacology, §Efficacy, §Regulatory, and §Implications. The reader's trust in the document collapses. This is worse than omitting the signals entirely (honest gap) and worse than characterizing them in §Risks (correct coverage): it is a false disclaimer.

### Root cause (best hypothesis from log)
`section_evidence_map` in the state JSON assigns evidence to sections by some embedding-or-theme routing. Risk-axis atoms that looked more like "class pharmacology" (DVT, malnutrition) or "regulatory label language" (thyroid, suicidality) or "efficacy durability" (regain, lean-mass) were routed to those sections, not §Risks. FIX-RISK-QUORUM injected 11 items into §Risks but did not include these six. When the §Risks composer wrote its convergence paragraph it looked at its own evidence list, noticed the gaps, and wrote a "not characterized here" disclaimer that was locally correct but globally false.

### Fix required
Cross-section reconciliation pass before composing the convergence paragraph. For any risk-axis signal named in any other section, §Risks must either (a) import the claim and characterize it, or (b) stay silent on it — but must not assert it is absent from the evidence base.

---

## Cross-cutting defects that need fixing

1. **ARCH-5 must re-audit after rewrite, and the quality gate must read the post-rewrite number.** Currently it is quantity-gate only (words, citations). A post-rewrite ARCH-5 pass that shows > 25 % unsupported should block the ship.
2. **LLM-fallback faithfulness must not be reported as the pipeline's faithfulness.** Evidence-level NLI scores are stored. The displayed `faithfulness_score` should reflect them, or should report both NLI and LLM numbers side-by-side.
3. **FIX-PRISMA-METHODS must actually write the Methods disclosure into composed §Methodology on every run.** It did not this run.
4. **Authority gate must demote non-peer-reviewed sources below SILVER.** Law-firm, telehealth-marketing, single-author blog, high-school journal, and preprint-without-review all deserve BRONZE at best. Some (law-firm litigation pages) deserve blocking.
5. **Semantic-duplicate collapse in bibliography.** Four WEGOVY revisions should not be four references.
6. **Composer must emit consistent Key Findings marker style.** One section promoted the bullets to an H2 orphan; the rest used bold inline. Pick one.
7. **Abstract path must not rely on a 2-hour generate timeout.** Either a shorter fallback timeout (5 min), or a guarantee that the initial composed abstract isn't clobbered by a failed regen.

---

## Shipping verdict

The document reads fluently, cites real sources, quotes them verbatim, and covers most of the known semaglutide risk landscape. In that sense the user-visible output is defensible.

Underneath, the pipeline silently ran on an inflated faithfulness number (84 % displayed vs 18 % actual NLI; and in loopback the "LLM second opinion" was the operator grading their own work), shipped a Methods section that should have carried a SANRA score and a PRISMA-absent disclosure and didn't, cited a law firm and a Medium blog inside the same bullet list as SELECT and FLOW, never verified that the section rewrites fixed the 74 % unsupported ratio that triggered them, and contains a §Risks disclaimer that explicitly contradicts six claims made in other sections of the same document.

This is not a failed run — most of the machinery worked. It's a run that would pass any metadata audit and fail an honest content audit. The fix list is concrete and falls inside the existing pipeline surface: post-rewrite ARCH-5 re-audit; quality gate reads NLI not LLM-fallback; cross-section reconciliation pass; authority gate demotes non-peer-reviewed sources; semantic-dedup for same-product-label revisions; FIX-PRISMA-METHODS replaced with FIX-SANRA-METHODS that scores the document against SANRA and discloses the score in §Methodology.

The operator-fabrication concern is separate from all of the above. The only way to disentangle "pipeline correctness" from "agent self-grading" is to re-run this query on a paid LLM path (PG_LOOPBACK_MODE=0, OpenRouter to GLM-5.1) and compare the two reports. Everything above describes what this loopback run produced; a paid run is the only way to know whether the defects are pipeline-level or operator-level.
