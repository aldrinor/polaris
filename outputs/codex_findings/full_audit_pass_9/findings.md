---
verdict: BLOCKED-ON-ISSUE
pass: 9
sweep_commit: 3e4dd03
released_reports_quality: "Mixed: sampled factual citations generally point to real supporting pages, but released reports contain materially misleading tier labels and thin/template-misaligned sections."
partial_qwen_advisory_legitimate: true
tech_long_context_abort_legitimate: true
hallucinations_found: 0
invariant_breaks:
  - tier_taxonomy_misclassification_in_released_outputs
  - misleading_released_tier_mix_and_limitations
rationale: |
  The released reports cannot be approved for full-scale use because multiple shipped bibliographies and methods sections classify ordinary web, social, trade-news, and consulting pages as T1 primary evidence. This violates the T1 definition in src/polaris_graph/retrieval/tier_classifier.py and makes the reported corpus quality materially misleading. Spot checks of adjacent factual citations in the FDA, RAG, Novo, and Lilly reports found many claims grounded to real URLs, but the tier-provenance invariant is broken in released output. The qwen advisory holds on the three partial reports are legitimate, and the long-context transformer abort is an appropriate refusal under the current adequacy gate.
---

## 1. Released Reports

I opened all four released reports:

- `outputs/sweep_r3_final/policy/policy_fda_ai_devices/report.md`
- `outputs/sweep_r3_final/tech/tech_rag_architectures_2024/report.md`
- `outputs/sweep_r3_final/due_diligence/dd_novo_nordisk_obesity_position/report.md`
- `outputs/sweep_r3_final/due_diligence/dd_lilly_tirzepatide_manufacturing/report.md`

### Citation spot checks

I cross-checked more than the required two reports / three citations per report:

- FDA PCCP report: citations [1], [2], [6], [10], and [13] are broadly grounded. The report's line 5 claims about the December 3, 2024 final AI-PCCP guidance, PCCP components, authorization effect, and non-binding guidance status are supported by the bibliography URLs at lines 33-45 and by the corresponding verifier tokens in `verification_details.json`.
- RAG report: citations [1] and [2] at line 5 are supported by the arXiv abstracts for FAIR-RAG and Blended RAG; citation [5] at line 9 supports the high-level RAG architecture taxonomy. However, [3] is a Reddit thread classified as T1 in the report bibliography at `outputs/sweep_r3_final/tech/tech_rag_architectures_2024/report.md:39`, and in the corpus dump at `outputs/sweep_r3_final/tech/tech_rag_architectures_2024/live_corpus_dump.json:25`.
- Novo due-diligence report: citations [1], [2], [3], [6], [7], and [10] mostly support their adjacent market/projection claims, but the report ships with malformed evidence-only fragments (`.[4]`, `Morgan analysts.[12]`, `.[14]`) at `outputs/sweep_r3_final/due_diligence/dd_novo_nordisk_obesity_position/report.md:5`, `:13`, and `:17`.
- Lilly due-diligence report: citations [1], [2], [5], [6], [9], [10], and [11] generally support the manufacturing investment and demand/sales claims, but the section labels are template-misaligned: manufacturing capacity appears under `Regulatory`, demand under `Efficacy`, and market forecast under `Safety` at `outputs/sweep_r3_final/due_diligence/dd_lilly_tirzepatide_manufacturing/report.md:3`, `:7`, and `:11`.

### Blocking issue: released tier mix is not honest

The tier taxonomy says T1 is "Peer-reviewed primary study" in `src/polaris_graph/retrieval/tier_classifier.py`. Released reports repeatedly classify non-primary web sources as T1:

- Novo: `matrixbcg.com` blog is T1 at `outputs/sweep_r3_final/due_diligence/dd_novo_nordisk_obesity_position/live_corpus_dump.json:25`; `aol.com` is T1 at `:36`; `facebook.com` is T1 at `:58`; `pharmavoice.com` is T1 at `:69`; `portersfiveforce.com` is T1 at `:80`.
- Novo report repeats those labels in the shipped bibliography: Facebook as T1 at `outputs/sweep_r3_final/due_diligence/dd_novo_nordisk_obesity_position/report.md:45`, PharmaVoice as T1 at `:46`, PortersFiveForce as T1 at `:47`, and MatrixBCG as T1 at `:50`.
- Lilly: `delveinsight.com` market forecast is T1 at `outputs/sweep_r3_final/due_diligence/dd_lilly_tirzepatide_manufacturing/live_corpus_dump.json:25`; `statista.com` is T1 at `:47`; C&EN trade news is T1 at `:146`. The report then says only 19% of sources are T1 primary studies at `outputs/sweep_r3_final/due_diligence/dd_lilly_tirzepatide_manufacturing/report.md:17` and lists C&EN as T1 at `:34`.
- RAG: `reddit.com` is T1 at `outputs/sweep_r3_final/tech/tech_rag_architectures_2024/live_corpus_dump.json:25`, and the report bibliography repeats Reddit as T1 at `outputs/sweep_r3_final/tech/tech_rag_architectures_2024/report.md:39`.
- FDA: `knobbe.com` law-firm blog is T1 at `outputs/sweep_r3_final/policy/policy_fda_ai_devices/live_corpus_dump.json:36`, and the report bibliography repeats it at `outputs/sweep_r3_final/policy/policy_fda_ai_devices/report.md:34`.

This is a release blocker even though many adjacent factual citations are not hallucinated. The outputs make claims such as "only 30% of sources classified as T1 primary studies" in `outputs/sweep_r3_final/due_diligence/dd_novo_nordisk_obesity_position/report.md:21` and "T1=30%" in `:31`, but that T1 pool includes Facebook, AOL, consulting blogs, and trade/news sites. The user-facing limitation therefore underreports low-provenance reliance.

### Usefulness and depth

- `policy_fda_ai_devices` is the strongest report: it directly answers the PCCP question and has reasonable depth, but its tier accounting is contaminated by Knobbe being T1.
- `tech_rag_architectures_2024` is partially useful but thin. It includes 2026 arXiv papers despite the "as of 2024-2025" question and spends a full "Population Subgroups" section on energy-sector knowledge preservation, medical-domain RAG, software registries, and education conference proceedings at `outputs/sweep_r3_final/tech/tech_rag_architectures_2024/report.md:17`, which is not a natural answer to best-practice architecture.
- `dd_novo_nordisk_obesity_position` answers the competitive-position question, but the malformed fragments and T1 misclassifications make it unshippable.
- `dd_lilly_tirzepatide_manufacturing` answers the supply-capacity question at a high level, but the section taxonomy is visibly wrong and the T1 labels are not credible.

## 2. Partial qwen advisory reports

The qwen holds are legitimate:

- `clinical_tirzepatide_t2dm`: qwen flags an irrelevant `ev_011` safety citation to a type 1 diabetes phase 2 trial and inadequate contradiction hedging. The report itself contains a weak Safety section: "The evidence for ev_011 is also inaccessible..." at `outputs/sweep_r3_final/clinical/clinical_tirzepatide_t2dm/report.md`, so release should stay blocked.
- `clinical_afib_anticoagulation`: qwen flags missing/tightness issues around a CDS program trial and hedging around DOAC superiority. The report has a short, oddly isolated `Efficacy` section about AF-ALERT2 that does not answer the core guideline question deeply.
- `policy_medicare_drug_price`: qwen's complaint is narrower but reasonable. The limitations section makes tier and evidence-horizon claims without adjacent citations, and the report uses several UNKNOWN/T7 sources while making policy-impact claims.

## 3. Long-context transformer abort

The abort is legitimate under the current adequacy semantics. `outputs/sweep_r3_final/tech/tech_long_context_transformer/corpus_adequacy.json` reports `decision=abort`, with `t1_plus_t2` observed 1 vs threshold 2 and `t1_plus_t2_plus_t3` observed 1 vs threshold 2. The run log exposes the refusal clearly at `outputs/sweep_r3_final/tech/tech_long_context_transformer/run_log.txt`, including the critical threshold failures and the final "Refusing to ship a misleading short report" message.

I would still tune retrieval before rerun: the corpus has 16/20 T4 sources and only one T1, suggesting retrieval found plenty of relevant preprints/reviews but not enough high-tier or official/primary sources.

## 4. Cost and performance sanity

The reported sweep cost is well below the $0.10/query cap, and every manifest shows `budget_cap_usd: 0.1`. The low cost is plausibly due to short generated reports (530-840 words for released/partial reports) plus inexpensive model calls, not solely because generation was skipped. Strict verification did drop sentences in several runs: 6 each for both clinical partials, 4 for Medicare, 4 for each due-diligence report, and 0 for FDA/RAG.

Wall times are plausible for live retrieval-heavy runs. The 0-cost long-context abort is expected because the generator never ran after the corpus adequacy gate failed.

## 5. Honest-by-construction invariants

Survived:

- Generator/evaluator family segregation is present in reports and evaluator outputs: DeepSeek generator and Qwen evaluator.
- Provenance tokens are present in verifier details for kept sentences.
- Strict verification is not rubber-stamping; unsupported sentences were dropped in multiple runs.
- Budget cap was respected.
- Prompt-injection sanitization is disclosed, and I saw no `<<<evidence:...>>>` leaks in opened reports.

Broken:

- Tier taxonomy/provenance quality is not honest in released outputs. The OpenAlex path is overriding obvious domain quality for Facebook, Reddit, AOL, Knobbe, Statista, DelveInsight, MatrixBCG, PortersFiveForce, PharmaVoice, and C&EN. Because the released reports convert those labels into user-facing limitations and actual tier distributions, this is a release-blocking content defect.

## 6. Verdict and recommended fix

Verdict: `BLOCKED-ON-ISSUE`.

Recommended fix before full-scale run:

1. Add hard domain overrides for social platforms, law-firm blogs, market-research/consulting domains, trade/news domains, and data portals so OpenAlex metadata cannot classify them as T1.
2. Add a report-level invariant: no released report may contain T1 sources whose domain is in known social/news/blog/consulting/vendor classes.
3. Recompute corpus tier distributions and regenerate reports after reclassification, because current limitation sections and actual distribution lines are materially wrong.
4. Add a formatting guard to drop standalone citation-token fragments and incomplete sentences before release.
