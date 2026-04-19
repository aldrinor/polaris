---
verdict: BLOCKED-ON-ISSUE
pass: 12
cycle: 4
m11_allowlist_calibrated: mixed
tier_label_hallucinations: 4
over_demoted_genuine_primaries: 1
aborts_legitimate: true
released_report_clean: false
rationale: |
  M-11's host allowlist is not visibly over-strict in the requested sense: I did not find several genuine primary papers demoted solely because their journal host was missing from PEER_REVIEWED_JOURNAL_DOMAINS. However, zero-hallucination tiering is still not met. Four sources remain labelled T1 even though they are narrative/secondary/guidance-style articles rather than primary studies, including two T1 labels in the one released tirzepatide report. The seven aborts remain directionally legitimate because restoring the one clear demoted primary I found would not rescue any aborted corpus, but the released report's tier accounting is materially inflated.
---

## Verdict

BLOCKED-ON-ISSUE.

M-11 fixed the specific pass-11 pattern where unknown/trade/industry hosts were upgraded to T1 solely from OpenAlex article+journal metadata. The cycle-4 abort rate is mostly honest. The blocker is that T1 hallucinations still remain on allowlisted journal/NIH hosts, so the pass does not satisfy "zero T1 hallucinations remain".

## Remaining T1 Hallucinations

| slug | source | observed | finding |
|---|---|---:|---|
| `clinical_tirzepatide_t2dm` | `https://pmc.ncbi.nlm.nih.gov/articles/PMC10115620/` | T1 | Not primary research. The full title is "Efficacy and Safety of Tirzepatide in Adults With Type 2 Diabetes: A Perspective for Primary Care Providers"; it is a perspective/review article supported by Eli Lilly, not an original trial report. |
| `clinical_tirzepatide_t2dm` | `https://www.mdpi.com/1424-8247/18/5/668` | T1 | Not T1. The full title is "The Efficacy and Safety of Tirzepatide in Patients with Diabetes and/or Obesity: Systematic Review and Meta-Analysis of Randomized Clinical Trials"; should be T2. |
| `clinical_tirzepatide_t2dm` | `https://www.frontiersin.org/journals/pharmacology/articles/10.3389/fphar.2022.1016639/full` | T1 | Not T1. Frontiers marks it as a "SYSTEMATIC REVIEW article" and the title is "Efficacy and safety of tirzepatide in patients with type 2 diabetes: A systematic review and meta-analysis"; should be T2. |
| `clinical_afib_anticoagulation` | `https://pmc.ncbi.nlm.nih.gov/articles/PMC12566413/` | T1 | Not primary research. PubMed/Australian Prescriber show this as a short clinical prescribing/guidance article on oral anticoagulation, not an original study. |

Root cause: the corpus stores truncated titles such as "Efficacy and safety of tirzepatide in patients with type 2 diabetes" and "The Efficacy and Safety of Tirzepatide in Patients with Diabetes and ...". Because the `systematic review` / `meta-analysis` suffix is lost, `R9_openalex_primary_study` grants T1 on allowlisted hosts.

## Allowlist Calibration

I did not find a pattern of several genuine peer-reviewed primary papers demoted only because their hosts were absent from the allowlist. The prior bad hosts are now non-T1:

| previous false-positive family | cycle-4 result |
|---|---:|
| Vizient "early impacts/pricing trends" | T5 |
| Powder & Bulk Solids trade news | T6 |
| Emergent Mind web explainer | T6 |
| Medicare checklist DOI | T4 |
| Chitika RAG guide | T6 |
| Fast Company / AOL / Facebook / LinkedIn / C&EN style sources | T6 or non-T1 |

One demoted genuine primary exists: `clinical_afib_anticoagulation` item 17, "Electronic alerts for ambulatory patients with atrial fibrillation not prescribed anticoagulation: A randomized, controlled trial (AF-ALERT2)", is a real randomized controlled trial in *Thrombosis Research* and is present as a T7/stub. That looks like a content/stub or host-normalization issue around `thrombosisresearch.com` / ScienceDirect/PubMed, not evidence that M-11 broadly over-demoted less-common journal hosts. Adding that one item as T1 would still leave the AFib corpus below the clinical abort thresholds.

## Abort Legitimacy

The seven aborts are legitimate at the report-release level:

| slug | assessment |
|---|---|
| `clinical_afib_anticoagulation` | Legitimate. Even counting AF-ALERT2 as a genuine primary would leave the corpus short of `min_t1_count=3`, `min_t1_plus_t2=5`, and `min_t1_plus_t2_plus_t3=6`. The existing T1 is false. |
| `policy_fda_ai_devices` | Legitimate. Corpus is FDA/regulatory, vendor/legal commentary, and Semantic Scholar stubs; no genuine T1/T2 found in the retrieved corpus. |
| `policy_medicare_drug_price` | Legitimate. The former false T1 policy/industry/checklist items are now T4/T5/T7/UNKNOWN; no genuine T1/T2 recovery found. |
| `tech_rag_architectures_2024` | Legitimate. Mostly web guides and arXiv preprints/surveys; no peer-reviewed T1 conference/journal papers in the retrieved corpus. |
| `tech_long_context_transformer` | Legitimate. Mostly arXiv preprints and web material; no T1/T2/T3 by the configured tech taxonomy. |
| `dd_novo_nordisk_obesity_position` | Legitimate. Business/news/industry corpus, no primary peer-reviewed mechanism/technology evidence. |
| `dd_lilly_tirzepatide_manufacturing` | Legitimate. Manufacturing/news/market corpus, no primary peer-reviewed evidence after M-11 demotions. |

## Released Report

`clinical_tirzepatide_t2dm/report.md` is not clean because tier accounting is dishonest:

- The report says T1=20%, matching the manifest, but true T1 is closer to 5% if only the JAMA SURMOUNT-4 primary trial is counted.
- Bibliography `[1]` and `[2]` are labelled T1 in the released report but are not primary studies; `[2]` is explicitly a systematic review/meta-analysis and `[1]` is a perspective/review for primary care.
- Citation markers `[1]` through `[9]` resolve to bibliography entries, and I did not find malformed citation fragments, `#ev` leakage, `undefined`, `NaN`, or invalid marker syntax in the final report.
- Claim grounding is mostly traceable to the cited sources, but the report relies on secondary/narrative sources while presenting them as T1 primary evidence.

## Required Follow-up

M-11 should stay, but R9/R10 need another guard for allowlisted hosts:

- Preserve full source titles from OpenAlex/PubMed/publisher metadata before classification, or run review/meta-analysis detection on OpenAlex abstract/type metadata instead of truncated display titles.
- Treat PMC/PubMed/journal hosts as venue evidence only; do not grant T1 without primary-study signals such as randomized trial, cohort, case-control, registry analysis, or original-results metadata.
- Add a regression for the four false T1s above and for the AF-ALERT2 RCT demotion so the next run can distinguish secondary evidence from genuine primary studies.
