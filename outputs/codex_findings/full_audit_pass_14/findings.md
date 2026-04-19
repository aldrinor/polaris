---
verdict: BLOCKED-ON-ISSUE
pass: 14
cycle: 6
m13_doi_lookup_working: true
m13_content_title_working: false
tier_label_hallucinations: 6
aborts_legitimate: true
rationale: |
  Cycle 6 is the 8-query run in outputs/sweep_r3_final: two clinical reports released as partial_thin_corpus with release_allowed=true, and the other six runs aborted before synthesis. The DOI exact-lookup path is working for the Frontiers DOI case, which is now T2 via R9_openalex_sr_or_ma. The MDPI no-DOI URL remains T1 with the old truncated title, so the content-title fallback is not reliably reaching the classifier. Six false T1 labels remain, all from broad domain-presumed-primary fallback behavior rather than verified primary-study metadata. The six aborts are legitimate because correcting the observed false T1s would not satisfy their failed corpus thresholds.
---

## Verdict

BLOCKED-ON-ISSUE.

M-13 fixed the Frontiers DOI path but did not eliminate T1 hallucinations in the live sweep. The named MDPI systematic-review/meta-analysis case is still labelled T1, and several PMC/professional PDF rows still fall through to `R10_journal_domain_presumed_primary`.

## Scope

Audited cycle-6 artifacts under `outputs/sweep_r3_final`.

Released reports:

| slug | manifest status | release_allowed | cost |
|---|---:|---:|---:|
| `clinical_tirzepatide_t2dm` | `partial_thin_corpus` | true | $0.00146191 |
| `clinical_afib_anticoagulation` | `partial_thin_corpus` | true | $0.00191213 |

Aborted runs:

| slug | status |
|---|---|
| `policy_fda_ai_devices` | `abort_corpus_inadequate` |
| `policy_medicare_drug_price` | `abort_corpus_inadequate` |
| `tech_rag_architectures_2024` | `abort_corpus_inadequate` |
| `tech_long_context_transformer` | `abort_corpus_inadequate` |
| `dd_novo_nordisk_obesity_position` | `abort_corpus_inadequate` |
| `dd_lilly_tirzepatide_manufacturing` | `abort_corpus_inadequate` |

The two release costs sum to $0.00337404, matching the reported ~$0.0034 cycle cost.

## Named Cases

| case | observed | assessment |
|---|---:|---|
| Frontiers `10.3389/fphar.2022.1016639` | T2 | Fixed. DOI lookup is firing: `R9_openalex_sr_or_ma`, reason says OpenAlex review plus systematic-review/meta-analysis title signal. |
| MDPI `1424-8247/18/5/668` | T1 | Not fixed. The live title is still truncated as `The Efficacy and Safety of Tirzepatide in Patients with Diabetes and ...`; classifier falls to `R10_journal_domain_presumed_primary`. |
| `pharmacytimes.com` | T6 | Fixed. Classified as news/blog via `R4_news_blog_domain`. |
| UpToDate AFib pages | T4 | Correct. Classified as clinical reference products. |
| Facebook CNBC post | T6 | Correct. Social/aggregator source, not T1. |
| Knobbe | not present | No Knobbe row appears in cycle-6 `sweep_r3_final` live dumps. |

## Remaining T1 Hallucinations

Six remaining false T1 labels were found:

| slug | source | observed | expected |
|---|---|---:|---:|
| `clinical_tirzepatide_t2dm` | `https://pmc.ncbi.nlm.nih.gov/articles/PMC10115620/` | T1 | T4 |
| `clinical_tirzepatide_t2dm` | `https://www.mdpi.com/1424-8247/18/5/668` | T1 | T2 |
| `clinical_afib_anticoagulation` | `https://pmc.ncbi.nlm.nih.gov/articles/PMC12566413/` | T1 | T4 |
| `clinical_afib_anticoagulation` | `https://pmc.ncbi.nlm.nih.gov/articles/PMC6159394/` | T1 | T4 |
| `clinical_afib_anticoagulation` | ACC DOAC dosing PDF | T1 | T3/T4, not primary |
| `policy_fda_ai_devices` | `https://pmc.ncbi.nlm.nih.gov/articles/PMC12577744/` | T1 | T3/T4, not primary |

All six are low-confidence presumed-primary classifications. The recurring failure class is: when DOI/OpenAlex metadata is absent or insufficient and the visible title does not contain explicit review/guideline markers, journal-like domains and even `acc.org` PDFs can still be promoted to T1 by `R10_journal_domain_presumed_primary`.

## Released Reports

`clinical_afib_anticoagulation`:

- Citation markers [1]-[12] all resolve to bibliography entries.
- No malformed citation fragments, placeholder text, `undefined`, `null`, or broken marker patterns were found.
- Qwen passed all five axes as `good`, and rule checks passed 13/13.
- Tier accounting is not trustworthy because bibliography [5], [6], and [12] carry false T1 labels.

`clinical_tirzepatide_t2dm`:

- Citation markers [1]-[3] all resolve to bibliography entries.
- No malformed citation fragments, placeholder text, `undefined`, `null`, or broken marker patterns were found.
- Qwen allowed release despite `completeness=needs_revision`; the report explicitly discloses gaps on GLP-1 class risks and drug interactions.
- Tier accounting is false because bibliography [1] is a narrative/review PMC source labelled T1; the live corpus also still contains the MDPI SR/MA source as T1.

## Abort Legitimacy

The six aborts are legitimate:

| slug | critical failures | assessment |
|---|---|---|
| `policy_fda_ai_devices` | `t1_plus_t2` | Legitimate. The one T1 is itself false; correcting it makes the corpus weaker, not releasable. |
| `policy_medicare_drug_price` | `t1_count`, `t1_plus_t2` | Legitimate. It has CMS/ASPE T3 and lower-tier explainers, but no T1/T2 evidence. |
| `tech_rag_architectures_2024` | `t1_count`, `t1_plus_t2`, `t1_plus_t2_plus_t3` | Legitimate. Corpus is T4/T5/T6/UNKNOWN only. |
| `tech_long_context_transformer` | `t1_count`, `t1_plus_t2`, `t1_plus_t2_plus_t3` | Legitimate. Corpus is T4/T6/UNKNOWN only. |
| `dd_novo_nordisk_obesity_position` | `t1_count`, `t1_plus_t2`, `t1_plus_t2_plus_t3` | Legitimate. Corpus is market/news/industry/social material only. |
| `dd_lilly_tirzepatide_manufacturing` | `t1_count`, `t1_plus_t2`, `t1_plus_t2_plus_t3` | Legitimate. Only one FDA T3 row appears; no T1/T2 evidence. |

## M-13 Assessment

`m13_doi_lookup_working=true`: the Frontiers DOI URL is no longer T1 and is now correctly classified as T2.

`m13_content_title_working=false`: the MDPI no-DOI URL still uses the truncated Serper-style title and falls through to presumed-primary T1. If content-title extraction fired, the systematic-review/meta-analysis wording should have been available and should have produced T2.

The unfixed class is broader than the MDPI case: any DOI-less or metadata-thin item on PMC/journal-like domains can still become T1 on domain reputation alone. This also affects professional PDFs on domains like `acc.org`, where the source is a dosing tool rather than original research.

## Evidence

- Parsed all `outputs/sweep_r3_final/**/live_corpus_dump.json` files.
- Checked the two released `report.md`, `bibliography.json`, `qwen_judge_output.json`, `evaluator_rule_checks.json`, and `corpus_approval.json` artifacts.
- Parsed all six aborted `manifest.json` adequacy decisions and their high-tier corpus rows.
