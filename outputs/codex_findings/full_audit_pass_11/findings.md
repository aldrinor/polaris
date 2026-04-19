---
verdict: BLOCKED-ON-ISSUE
pass: 11
cycle: 3
m10_fix_working: true
tier_label_hallucinations: 7
citation_hallucinations: 0
aborts_legitimate: true
partial_thin_corpus_honest: true
rationale: |
  M-10 works for the pass-10 target families: the live cycle-3 corpus dumps no longer label the named UpToDate, Downstate, IHS, Fast Company, KFF, AccessibleMeds, CMS, Commonwealth Fund, JMIR guiding-principles, PMC guideline-title, or Chitika sources as T1. However, the same R9/OpenAlex path still labels other clear non-primary web, trade, checklist, and report sources as T1, including two sources used in the released Medicare report. The released reports have resolving citations and no malformed citation fragments, and the five aborts are directionally legitimate, but the ready bar requires zero tier hallucinations. Full-scale run remains blocked.
---

## Summary Verdict

BLOCKED-ON-ISSUE.

The specific M-10 remediation target set is clean in cycle 3. I grep'd the live `outputs/sweep_r3_final/**/live_corpus_dump.json` files for the pass-10 domain families and title markers named in the brief. None of those target matches are still T1.

The blocker is broader tier-label honesty. Cycle 3 still contains at least seven clear false T1 labels outside the exact M-10 domain list, including false T1s in a released report. This means M-10 fixed the enumerated regressions but did not close the underlying R9/OpenAlex overclassification path.

## M-10 Target Verification

Checked live corpus dump matches:

| source family | observed cycle-3 tier | file |
|---|---:|---|
| `uptodate.com` x2 | T4 | `clinical/clinical_afib_anticoagulation/live_corpus_dump.json` |
| `downstate.edu` DOAC guideline PDF | T4 | `clinical/clinical_afib_anticoagulation/live_corpus_dump.json` |
| `ihs.gov` formulary brief PDF | T3 | `clinical/clinical_afib_anticoagulation/live_corpus_dump.json` |
| PMC "2025 Guidelines for direct oral anticoagulants" | T4 | `clinical/clinical_afib_anticoagulation/live_corpus_dump.json` |
| `fastcompany.com` Wegovy market-share article | T6 | `due_diligence/dd_novo_nordisk_obesity_position/live_corpus_dump.json` |
| `kff.org` key facts explainer | T4 | `policy/policy_medicare_drug_price/live_corpus_dump.json` |
| `accessiblemeds.org` policy/advocacy blog | T4 | `policy/policy_medicare_drug_price/live_corpus_dump.json` |
| `cms.gov` x2 | T3 | `policy/policy_medicare_drug_price/live_corpus_dump.json` |
| `commonwealthfund.org` explainer | T4 | `policy/policy_medicare_drug_price/live_corpus_dump.json` |
| `ai.jmir.org` "Guiding Principles" | T4 | `policy/policy_fda_ai_devices/live_corpus_dump.json` |
| `chitika.com` RAG guide | T6 | `tech/tech_rag_architectures_2024/live_corpus_dump.json` |

No M-10 target-domain or target-title match remained T1.

## Remaining Tier Hallucinations

Clear false T1 labels still present:

| slug | source | observed | why this is not T1 |
|---|---|---:|---|
| `clinical_afib_anticoagulation` | `pmc.ncbi.nlm.nih.gov/articles/PMC12566413/`, "Oral anticoagulation for adults with atrial fibrillation or venous ..." | T1 | Used as broad clinical guidance/review material in the report, not a primary study. |
| `clinical_tirzepatide_t2dm` | `frontiersin.org/.../10.3389/fphar.2022.1016639/full`, "Efficacy and safety of tirzepatide in patients with type 2 diabetes" | T1 | The report itself cites it as a meta-analysis; this should not be T1 primary-study evidence. |
| `policy_medicare_drug_price` | `vizientinc.com/...pricing-trends`, "Early impacts of the IRA's Medicare Drug Price Negotiation Program" | T1 | Industry/consulting insight article, not peer-reviewed primary research. |
| `policy_medicare_drug_price` | `seniorcarepharmacies.org/...SCPC-IRA-Impact-Whitepaper-ATI-final.pdf` | T1 | Trade-association/whitepaper PDF, not peer-reviewed primary research. |
| `policy_medicare_drug_price` | `doi.org/10.1093/haschl/qxaf030`, "Use of real-world evidence ...: A checklist..." | T1 | Checklist/policy guidance title; should be demoted by title/source-type logic, not T1. |
| `dd_lilly_tirzepatide_manufacturing` | `powderbulksolids.com/...lilly-increases-investment...` | T1 | Trade-news/manufacturing article, not primary research. |
| `tech_long_context_transformer` | `emergentmind.com/topics/long-context-optimization` | T1 | Web explainer/guide page, not primary research. |

I did not count more borderline T1s without enough local evidence to adjudicate them, so seven is a conservative minimum.

## Released Reports

All citation markers in the three released reports resolve to bibliography entries:

| report | marker check | tier distribution check |
|---|---|---|
| `clinical_afib_anticoagulation/report.md` | [1]-[7] all resolve; sampled citations [1], [3], [5], [7] match the cited source topics. | Report says T1=15%, T3=5%, T4=45%, T7=35%, matching the dump. |
| `clinical_tirzepatide_t2dm/report.md` | [1]-[8] all resolve; sampled citations [1], [2], [4], [7] match the cited source topics. | Report says T1=20%, T3=5%, T4=20%, T5=5%, T7=50%, matching the dump. |
| `policy_medicare_drug_price/report.md` | [1]-[9] all resolve; sampled citations [1], [2], [4], [7], [9] match the cited source topics. | Report says T1=20%, T3=15%, T4=25%, T7=35%, UNKNOWN=5%, matching the dump, but T1 is inflated by false T1s. |

No cycle-1/M-8-style malformed citation fragments were found. The released Medicare report is not clean because bibliography items [1] and [2] are false T1s and are used for substantive claims in the Efficacy section.

Section-label alignment remains rough. `policy_medicare_drug_price` uses an "Efficacy" heading for pricing/access impact, and `clinical_afib_anticoagulation` uses "Regulatory" for clinical-guideline recommendations. This is a real polish/ontology issue, though less severe than the tier-label blocker.

## Abort Legitimacy

The five aborts are legitimate under the honest-tier standard:

| slug | adequacy result | assessment |
|---|---|---|
| `policy_fda_ai_devices` | abort; fails `t1_plus_t2` | Legitimate. Live dump has no T1 and is mostly FDA/regulatory, vendor, legal-commentary, and Semantic Scholar stub material. |
| `dd_novo_nordisk_obesity_position` | abort; fails `t1_count`, `t1_plus_t2`, `t1_plus_t2_plus_t3`; low-quality warning | Legitimate. Corpus is mostly T5/T6 plus UNKNOWN and no T1. |
| `dd_lilly_tirzepatide_manufacturing` | abort; fails `t1_plus_t2` | Legitimate. The one recorded T1 is false trade-news (`powderbulksolids.com`), making the true corpus even thinner. |
| `tech_rag_architectures_2024` | abort; fails `t1_count`, `t1_plus_t2`, `t1_plus_t2_plus_t3` | Legitimate. Corpus is T4/T5/T6 only after Chitika demotion. |
| `tech_long_context_transformer` | abort; fails `t1_plus_t2`, `t1_plus_t2_plus_t3` | Legitimate. The one recorded T1 is false web-guide material (`emergentmind.com`), so the true T1/T2/T3 count is lower. |

One artifact consistency issue: `policy_fda_ai_devices/corpus_adequacy.json` reports `T1=1, T3=9` over 27 sources, while the live dump contains 20 sources with no T1 and 4 T3. This does not change the abort disposition, but it should be investigated before relying on adequacy summaries as the sole audit source.

## Partial Thin Corpus

`partial_thin_corpus` with `release=True` is honest for the two clinical reports as a status, assuming downstream consumers see the limitations. Both manifests record `material_deviation=true`, `adequacy.decision=expand`, and `status=partial_thin_corpus`; both reports disclose the thin corpus in the Limitations and Methods sections.

The AFib report says only 15% T1 with T4/T7 dominance, and the tirzepatide report says only 20% T1 with 50% T7 plus a high-severity contradiction disclosure. That is sufficient warning for a partial release. The status is not the blocker; remaining false T1 labels are.

## Required Fix

M-10 should be kept, but full-scale approval needs another R9 hardening pass. At minimum, prevent `R9_openalex_primary_study` from upgrading industry insight pages, trade-association whitepapers, trade-news sites, web explainers, checklist/guidance titles, and meta-analyses/reviews to T1 solely because OpenAlex returns article-like metadata.
