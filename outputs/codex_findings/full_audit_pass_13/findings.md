---
verdict: BLOCKED-ON-ISSUE
pass: 13
cycle: 5
m12_full_title_working: false
m12_narrative_markers_working: true
tier_label_hallucinations: 3
aborts_legitimate: true
rationale: |
  M-12 is only partially effective in the live cycle-5 artifacts. The narrative-marker expansion is working for the PMC perspective/prescribing cases, but the full-title path is not reliably reaching the classifier for the two named SR/MA sources. MDPI 1424-8247/18/5/668 and Frontiers 10.3389/fphar.2022.1016639 remain T1 in live_corpus_dump.json, so the zero-T1-hallucination bar is not met. The seven aborts are legitimate despite one AFib RCT over-demotion, because restoring that one primary would not satisfy the abort thresholds. The tirzepatide partial report has resolving citations and release_allowed=false is produced by the Qwen gate, but the report still contains false tier accounting.
---

## Verdict

BLOCKED-ON-ISSUE.

The classifier-level M-12 regression tests pass, but the live cycle-5 dump does not satisfy the requested "all named cases should now be T4 or T2, not T1" check. Two pass-12 named SR/MA sources are still recorded as T1 in `outputs/sweep_r3_final/clinical/clinical_tirzepatide_t2dm/live_corpus_dump.json`.

## Named Case Check

| case | cycle-5 result | finding |
|---|---:|---|
| `PMC10115620` | T4 | Fixed. Classified by `R9_openalex_narrative_review`; reason includes narrative / perspective detection. |
| `PMC12566413` | T4 | Fixed. Classified by `R9_openalex_narrative_review`; the AFib prescribing/guidance article is no longer T1. |
| `MDPI 1424-8247/18/5/668` | T1 | Still false T1. The row title remains truncated as "The Efficacy and Safety of Tirzepatide in Patients with Diabetes and ..."; reason says title does not signal review. This should be T2. |
| `Frontiers 10.3389/fphar.2022.1016639` | T1 | Still false T1. The row title remains "Efficacy and safety of tirzepatide in patients with type 2 diabetes"; reason says title does not signal review. This should be T2. |

The two remaining T1 hallucinations are:

| slug | URL | observed | expected |
|---|---|---:|---:|
| `clinical_tirzepatide_t2dm` | `https://www.mdpi.com/1424-8247/18/5/668` | T1 | T2 |
| `clinical_tirzepatide_t2dm` | `https://www.frontiersin.org/journals/pharmacology/articles/10.3389/fphar.2022.1016639/full` | T1 | T2 |

## M-12 Behavior

Narrative markers are working. The live dump demotes `PMC10115620` and `PMC12566413` to T4 using `R9_openalex_narrative_review`; the unit tests also cover `perspective for`, `for clinicians`, and `prescribing` and pass with `python -m pytest tests\polaris_graph\test_m12_pass12_primary_study_signal.py -q`.

Full-title routing is not working reliably in the live retrieval path. The classifier can classify full MDPI/Frontiers SR/MA titles as T2 in tests, but the live cycle-5 rows still show truncated titles and `R9_openalex_primary_study` for both named SR/MA URLs.

One additional non-T1 tier hallucination is visible: `https://www.pharmacytimes.com/view/tirzepatide-shows-significant-improvements-in-glycemic-control-weight-loss-among-patients-with-type-2-diabetes` is labelled T2 by OpenAlex SR/MA logic even though the visible source is a PharmacyTimes news article, not the systematic review itself.

## Abort Legitimacy

The seven aborts are legitimate at the release-decision level:

| slug | assessment |
|---|---|
| `clinical_afib_anticoagulation` | Legitimate. Tiers are T3=1, T4=13, T7=6 and it fails `t1_count`, `t1_plus_t2`, and `t1_plus_t2_plus_t3`. One real RCT, AF-ALERT2, is over-demoted to T4, but adding it back as T1 would still leave the corpus below clinical thresholds. |
| `policy_fda_ai_devices` | Legitimate. No T1/T2; corpus is FDA/regulatory, policy/commentary, vendor/legal, and unknown material. |
| `policy_medicare_drug_price` | Legitimate. It has one T1 and three T3, but still fails `t1_plus_t2`; the remaining corpus is explainers, government pages, stubs, and unknowns. |
| `tech_rag_architectures_2024` | Legitimate. No T1/T2/T3; mostly arXiv/preprint material and web guides. |
| `tech_long_context_transformer` | Legitimate. No T1/T2/T3; mostly arXiv/preprint material, web articles, and unknowns. |
| `dd_novo_nordisk_obesity_position` | Legitimate. No T1/T2/T3; mostly market/news/industry/social sources. |
| `dd_lilly_tirzepatide_manufacturing` | Legitimate. No T1/T2/T3; mostly investor, market, trade, and unknown sources. |

## Partial Report

`clinical_tirzepatide_t2dm` has `status=partial_qwen_advisory` and `release_allowed=false` in the manifest. The Qwen gate is real: `qwen_judge_output.json` marks `citation_tightness` and `flow` as `needs_revision`, producing `qwen_citation_tightness_needs_revision` and `qwen_multi_axis_needs_revision`.

The report citations [1]-[9] resolve to bibliography entries and the main factual claims are traceable to the cited source topics. However, bibliography [3] is the Frontiers SR/MA still labelled T1, and bibliography [2] is a PharmacyTimes news URL labelled T2. Therefore release blocking is correct, but the run is not clean enough to approve as "qwen noise only."

## Evidence Commands

- `python -m pytest tests\polaris_graph\test_m12_pass12_primary_study_signal.py -q`: 11 passed.
- Parsed manifests and live dumps under `outputs\sweep_r3_final`.
- Checked `outputs\sweep_r3_final\clinical\clinical_tirzepatide_t2dm\manifest.json`, `qwen_judge_output.json`, `bibliography.json`, and `report.md`.
