---
verdict: CONDITIONAL
pass: 15
cycle: 8
tier_label_hallucinations: 5
specific_domains_to_add: ["pmc.ncbi.nlm.nih.gov", "mdpi.com", "acc.org", "pubmed.ncbi.nlm.nih.gov"]
released_report_clean: mostly
aborts_legitimate: true
rationale: |
  Cycle 8 is materially better than cycle 7 because it produced one releasable thin-corpus report instead of zero releases. The released tirzepatide report has resolving citations and no obvious unsupported numeric claim, but its tier accounting is not clean: bibliography [1] is an R10 false T1, and the live corpus still has a false-T1 MDPI systematic review/meta-analysis. All remaining T1 hallucinations are narrow R10 fallback cases on biomedical aggregator/journal domains or a professional-society PDF, so a targeted M-15 is preferable to restoring the blanket T1 primary-signal requirement that caused the cycle-7 zero-release failure. The seven aborts are honest under the current adequacy contract; correcting the false T1 rows would make the aborted corpora weaker, not releasable.
---

## Verdict

CONDITIONAL.

Do not reinstate the cycle-7 blanket "T1 must have explicit primary signal" rule. It over-demoted legitimate bare-title clinical primaries and made the loop unusable. Cycle 8 should proceed with targeted M-15 follow-ups that demote the specific R10 false-positive patterns below.

## Scope

Audited current cycle-8 artifacts under `outputs/sweep_r3_final`.

| slug | status | release_allowed | notes |
|---|---:|---:|---|
| `clinical_tirzepatide_t2dm` | `partial_thin_corpus` / sweep `ok_thin_corpus` | true | 13 verified sentences, 363 words, Qwen 4 good / 1 needs_revision |
| remaining 7 queries | `abort_corpus_inadequate` | false | refused before synthesis |

Total sweep cost in `sweep_summary.json`: `$0.00129881`.

## Released Report

`clinical_tirzepatide_t2dm` is mostly clean, not fully clean.

Citation markers [1]-[5] all resolve to bibliography entries, rule checks pass 13/13, and strict verification kept 13 sentences while dropping 2 unsupported span-overlap failures. External/source-title spot checks confirm the cited PMC review and PharmacyTimes article contain the reported SURPASS efficacy and GI-safety statements, and the Frontiers article is correctly T2 as a systematic review/meta-analysis.

Remaining problems:

| item | issue | impact |
|---|---|---|
| Bibliography [1] `PMC10115620` | Labelled T1 by R10, but the article is a perspective/review for primary-care providers, not a primary trial report. | Released tier accounting is false. |
| Live corpus `mdpi.com/1424-8247/18/5/668` | Labelled T1 by R10, but full title is "Systematic Review and Meta-Analysis of Randomized Clinical Trials." | False T1 remains after raw-title M-14 partial fix; expected T2. |
| Bibliography [3] and [4] | Same PharmacyTimes URL duplicated as two refs. | Not a hallucination, but noisy bibliography accounting. |
| Comparative section | Uses PharmacyTimes T6 as the source for SURPASS-2 comparative claims. | Grounded enough for a thin report, but weak evidence provenance for clinical production. |
| Completeness | Qwen marks completeness `needs_revision`; missing GLP-1 class risks and drug interactions. | Acceptable only because limitations disclose the gap. |

## T1 Hallucinations

All T1 rows in cycle-8 `live_corpus_dump.json` are R10 fallback promotions; all five are false or insufficiently supported T1 labels.

| slug | source | observed | expected | targeted fix |
|---|---|---:|---:|---|
| `clinical_tirzepatide_t2dm` | `https://pmc.ncbi.nlm.nih.gov/articles/PMC10115620/` | T1 | T4 | Demote PMC articles when title/content/pub-type signals perspective, review, guidance, or clinical overview. |
| `clinical_tirzepatide_t2dm` | `https://www.mdpi.com/1424-8247/18/5/668` | T1 | T2 | If title is truncated or ends with ellipsis, fetch raw page title/`og:title` before R10; systematic-review/meta-analysis signal must override R10. |
| `clinical_afib_anticoagulation` | `https://pmc.ncbi.nlm.nih.gov/articles/PMC12240022/` | T1 | T4 | Add `guideline`, `guidelines`, `guidance`, `practical guidance`, and consensus/practice-guide signals as R10 blockers. |
| `clinical_afib_anticoagulation` | ACC DOAC dosing PDF | T1 | T3/T4 | Demote professional-society PDFs with path/title signals such as `tools`, `practice-support`, `information-graphics`, `dosing`, or `guideline`; never R10-promote `acc.org` PDFs. |
| `policy_medicare_drug_price` | `https://pubmed.ncbi.nlm.nih.gov/38297186/` | T1 | T4 or T2, not T1 | Do not R10-promote PubMed title-only rows without publication-type metadata; PubMed/Nature `Review` or `Perspective` should demote below T1. |

## M-15 Recommendation

Implement a narrow R10 guard, not a blanket primary-signal requirement:

1. Block R10 when title is truncated (`...`) unless raw content title or trusted metadata has been fetched and classified.
2. Add biomedical review/guidance demotion tokens: `systematic review`, `meta-analysis`, `review`, `perspective`, `guideline`, `guidelines`, `guidance`, `practical guidance`, `consensus`, `practice guide`.
3. Treat `pmc.ncbi.nlm.nih.gov` and `pubmed.ncbi.nlm.nih.gov` as aggregators requiring article-type/title/content signals before T1.
4. Treat professional-society PDFs on `acc.org` as T3/T4 unless explicit primary-study metadata is present.
5. Add regression fixtures for the five URLs above and preserve the NEJM/PMC bare-title primary cases that M-14 part 2 broke.

## Abort Legitimacy

The seven aborts are legitimate honest refusals under the current adequacy rules.

| slug | critical failure | assessment |
|---|---|---|
| `clinical_afib_anticoagulation` | `t1_plus_t2`, `t1_plus_t2_plus_t3` | Legitimate. The two T1 rows are false R10 promotions, so correction weakens the corpus. |
| `policy_fda_ai_devices` | `t1_count`, `t1_plus_t2` | Legitimate but conservative. It has FDA T3 material, but no T1/T2 under the current taxonomy. |
| `policy_medicare_drug_price` | `t1_plus_t2` | Legitimate. The lone T1 is at best not a clear T1 primary under PubMed/Nature metadata. |
| `tech_rag_architectures_2024` | `t1_count`, `t1_plus_t2`, `t1_plus_t2_plus_t3` | Legitimate. Corpus is arXiv/preprint plus blogs/vendor/social material. |
| `tech_long_context_transformer` | `t1_count`, `t1_plus_t2`, `t1_plus_t2_plus_t3` | Legitimate. Corpus is mostly arXiv/preprint and web-guide material. |
| `dd_novo_nordisk_obesity_position` | `t1_count`, `t1_plus_t2`, `t1_plus_t2_plus_t3` | Legitimate. Corpus is market research, business/news/social, and industry material. |
| `dd_lilly_tirzepatide_manufacturing` | `t1_count`, `t1_plus_t2`, `t1_plus_t2_plus_t3` | Legitimate. Corpus is news, market research, and company/press material. |

## Conditional Target

Next cycle should target: `tier_label_hallucinations=0` for the five named URLs, `clinical_tirzepatide_t2dm` still releases, and at least one release remains in the 8-query sweep. If M-15 returns to zero releases, prefer keeping cycle-8 behavior plus visible thin-corpus disclosure over the cycle-7 blanket demotion.
