---
verdict: BLOCKED-ON-ISSUE
pass: 10
cycle: 2
m7_tier_fix_working: true
m8_fragment_guard_working: true
tier_label_hallucinations: 13
citation_hallucinations: 0
aborts_legitimate: true
rationale: |
  The increased abort count is mostly the expected result of honest M-7 demotions: the aborted runs fetched enough rows but failed primary/regulatory adequacy after social, market-research, and commentary domains were no longer mislabeled as T1. M-8 also appears effective: the released and partial reports no longer contain the cycle-1 malformed citation fragments. However, the OpenAlex primary-study path still labels clear non-primary or non-peer-reviewed web/institutional sources as T1, including sources used in the single released report. Because the ready bar requires zero tier-label hallucinations in released or partial outputs, this cycle remains blocked.
---

## Summary Verdict

BLOCKED-ON-ISSUE.

M-7 fixed the specific pass-9 domain families: Facebook, Reddit, AOL, DelveInsight, MatrixBCG, Statista, PharmaVoice, PortersFiveForce, and Knobbe are no longer T1 in the checked sweep outputs. The higher abort rate is therefore mostly an honest refusal pattern, not a regression.

The remaining blocker is broader than M-7: `R9_openalex_primary_study` still trusts OpenAlex `article` + `journal` metadata for domains/titles that are plainly not peer-reviewed primary studies. This affects the released report and multiple partial/aborted outputs.

## Tier-Label Honesty

Clear remaining T1 misclassifications found in `live_corpus_dump.json`:

| slug | domain / source | observed | issue |
|---|---|---:|---|
| `clinical_afib_anticoagulation` | `uptodate.com` x2 | T1 | UpToDate clinical reference pages, not primary studies |
| `clinical_afib_anticoagulation` | `downstate.edu` PDF | T1 | institutional DOAC guideline, not primary study |
| `clinical_afib_anticoagulation` | `ihs.gov` PDF | T1 | government/formulary brief, not primary study |
| `clinical_afib_anticoagulation` | `pmc.ncbi.nlm.nih.gov` "2025 Guidelines for direct oral anticoagulants" | T1 | guideline/review content, not primary study |
| `dd_novo_nordisk_obesity_position` | `fastcompany.com` | T1 | business news/article, not primary study |
| `policy_fda_ai_devices` | `ai.jmir.org` / PMC "Predetermined Change Control Plans: Guiding Principles" | T1 | guiding-principles/policy analysis, not primary study |
| `policy_medicare_drug_price` | `kff.org` | T1 | health-policy explainer, not primary study |
| `policy_medicare_drug_price` | `accessiblemeds.org` | T1 | industry/advocacy blog/report, not primary study |
| `policy_medicare_drug_price` | `cms.gov` | T1 | government/regulatory source, should be T3 at most |
| `policy_medicare_drug_price` | `commonwealthfund.org` | T1 | policy explainer, not primary study |
| `tech_rag_architectures_2024` | `chitika.com` | T1 | SEO/web guide, not primary study |

This is at least 13 clear tier-label hallucinations. I did not count borderline cases such as some PMC/PubMed/DOI clinical-review-looking records unless the title/domain made the non-primary classification obvious; the true count may be higher.

All listed false T1 entries were classified through `R9_openalex_primary_study`, so the remaining defect is rule-ordering/domain-guard coverage around OpenAlex, not the new M-7 override sets.

## Released Report Check

Released report checked: `outputs/sweep_r3_final/clinical/clinical_afib_anticoagulation/report.md`.

Citation integrity:

| marker | bibliography URL | check |
|---|---|---|
| [1] | `uptodate.com/...use-of-oral-anticoagulants` | marker resolves to bibliography; citation not fabricated, but tier is falsely T1 |
| [3] | `downstate.edu/...doac-guideline-jan-2026.pdf` | marker resolves to bibliography; citation not fabricated, but tier is falsely T1 |
| [5] | `pmc.ncbi.nlm.nih.gov/articles/PMC12566413/` | marker resolves to bibliography and supports the DOAC/warfarin comparison theme |
| [9] | `thrombosisresearch.com/...AF-ALERT2...pdf` | marker resolves to bibliography and matches the RCT/CDS-alert paragraph |

No fabricated citation markers were found in the released report: report markers [1]-[9] all resolve to bibliography entries, and `verification_details.json` shows strict verification dropped unsupported numeric AF-ALERT sentences before release.

The released report is not clean because its bibliography labels UpToDate, Downstate, IHS, and a guideline/review PMC item as T1. Its limitations tier accounting mechanically matches the artifact distribution (`T1=40%, T4=25%, T7=35%`), but the T1 fraction is inflated by those misclassifications. The limitations prose also calls T7 "general commentary", which is imprecise for the T7 taxonomy.

## Abort Legitimacy

The four `abort_corpus_inadequate` runs look legitimate under the current adequacy policy:

| slug | critical failures | assessment |
|---|---|---|
| `tech_rag_architectures_2024` | `t1_plus_t2`, `t1_plus_t2_plus_t3` | honest abort; only one T1 remains, and that T1 is actually `chitika.com`, so the true primary count is likely zero |
| `tech_long_context_transformer` | `t1_count`, `t1_plus_t2`, `t1_plus_t2_plus_t3` | honest abort; corpus is mostly T4/preprint/repository material with no T1 |
| `dd_novo_nordisk_obesity_position` | `t1_plus_t2`, `t1_plus_t2_plus_t3`, plus low-quality warning | honest abort; demoted AOL/Facebook/market-research sources expose a low-quality corpus, and the one T1 is Fast Company, which is false |
| `dd_lilly_tirzepatide_manufacturing` | `t1_count`, `t1_plus_t2`, `t1_plus_t2_plus_t3` | honest abort; corpus is dominated by T5/T6/UNKNOWN with only one T3 |

This supports the cycle-2 profile change as an honesty improvement. Longer term, tech and due-diligence domains may need domain-aware thresholds, but this sweep should not be approved while false T1 labels still pass through.

## Partial Qwen Advisory Check

The three partial releases have substantive advisory issues:

| slug | qwen concern | assessment |
|---|---|---|
| `clinical_tirzepatide_t2dm` | uncited contradiction values, overconfident superiority language, missing regulatory status | substantive; report includes a contradiction disclosure with values not adjacent to citations |
| `policy_fda_ai_devices` | missing citations for methods/tier distribution, weak primary/safety evidence | partly noisy on methods citations, but completeness concern is substantive given the corpus is dominated by T3/T7 and contains Knobbe correctly demoted to T6 |
| `policy_medicare_drug_price` | limitations percentages uncited, overconfident "will be modest"/"will not likely result", repeated safety evidence blocks | substantive; the report has duplicated CMS evidence blocks and policy forecasts stated too strongly |

Release blocking for these partials is justified.

## M-7 Check

M-7 is working for the target domains in this sweep:

| domain | observed tier |
|---|---:|
| `reddit.com` | T6 |
| `aol.com` | T6 |
| `facebook.com` | T6 |
| `delveinsight.com` | T5 |
| `matrixbcg.com` | T5 |
| `statista.com` | T5 |
| `pharmavoice.com` | T5 |
| `portersfiveforce.com` | T5 |
| `knobbe.com` | T6 |

No M-7 target-domain T1 classifications remain in the checked `live_corpus_dump.json` files.

## M-8 Check

M-8 appears effective. I checked the released report and the three partial reports for the cycle-1 style degenerate fragments such as bare `.[N]` or very short `word.[N]` sentences; none were found.

The code in `resolve_provenance_to_citations()` now strips provenance first, prunes sentences with fewer than three content words or fewer than 15 prose characters, and assigns bibliography numbers only after that pruning. That matches the observed absence of malformed citation fragments.

## Blocker

Block full-scale run until the remaining T1 overclassification path is fixed. The minimum targeted remediation should prevent `R9_openalex_primary_study` from classifying non-journal domains, government/institutional PDFs, clinical reference products, policy explainers, SEO/web guides, and news/business outlets as T1 solely because OpenAlex returns `article` + `journal`.

Suggested next guard families:

1. Add explicit demotion sets for clinical reference products and institutional guideline hosts, including `uptodate.com`, `downstate.edu`, and similar university/health-system PDF paths.
2. Add policy/think-tank/advocacy/government-domain overrides so `cms.gov` routes to T3 and KFF/Commonwealth Fund/AccessibleMeds route to T4/T5/T6, not T1.
3. Add web-guide/news/business-source demotions for domains such as `fastcompany.com` and `chitika.com`.
4. Tighten `R9_openalex_primary_study` so `article` is not enough: require a recognized peer-reviewed journal host or study-design evidence, and downgrade titles containing guideline, guiding principles, explainer, checklist, key facts, report, or blog-like markers.
