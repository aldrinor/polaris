---
verdict: IMPLEMENT-C-BODY-INSPECT
pass: full_scale_2_code_audit
commit: 278e36c
m16_unit_tests_sound: true
recommendation_for_3_unfixed: c
rationale: |
  M-16's conference-ID and narrative-flavor title detectors are narrow, order-safe, and covered by focused regressions; they do not appear to add material false-positive risk when the discriminating phrase is actually present in the resolved title. The remaining three hallucinations are not primarily classifier-rule failures, but evidence-signal availability failures: the live pipeline sends truncated or non-diagnostic titles into a title-only classifier. PubMed E-utilities would likely repair the two PMC title-recovery misses, but it would not address the Oxford case whose title does not identify the article as a meta-analysis. A bounded body-inspection pass over high-signal regions such as fetched title/H1/abstract/article-type/early page text is the smallest fix that can cover all three without spending a v3 sweep on a known residual failure mode.
---

## Findings

1. **M-16 implementation is sound and surgical.**

   The new conference-abstract detector in [tier_classifier.py](../../../src/polaris_graph/retrieval/tier_classifier.py) only matches day-code or OR-style presentation IDs at the start of the title, plus supplement URL patterns already aligned with the existing abstract-only logic. That is a low-risk addition: ordinary trial titles such as "Tirzepatide in type 2 diabetes" do not share that prefix shape, and the tests include a normal-title negative guard.

   The narrative additions are also appropriately narrow for title-level classification. Exact phrases such as `case report`, `post hoc`, `secondary analysis`, `pooled analysis`, and `subgroup analysis` are strong evidence that a peer-reviewed journal item should not be treated as a top-tier primary study in this hierarchy. The main caveat is not false positives inside M-16 itself, but the broader policy choice that some post-hoc or subgroup analyses could still be original analyses; this project has already chosen to demote secondary/narrative-flavored analyses rather than over-promote them to T1.

2. **The tests are useful, but they test complete-title behavior.**

   `python -m pytest tests\polaris_graph\test_m16_full_scale_pass1_fixes.py -q` passes: 16 passed, with only a pytest cache permission warning. The test file covers the new THU/MON/OR detections, case-report/post-hoc/pooled/subgroup narrative markers, the three intended complete-title outcomes, and primary-study regressions.

   These tests do not prove the live pipeline will fix the PMC perspective or PMC case-report misses, because [live_retriever.py](../../../src/polaris_graph/retrieval/live_retriever.py) still resolves the classifier title by taking the longest of OpenAlex title, fetched title, and Serper title. If all available title candidates are truncated or non-diagnostic, the M-16 title detectors cannot fire.

3. **Recommendation: implement option c before v3.**

   Option `b` is attractive for PMC URLs and would be a clean way to recover canonical metadata from PMC/PMID records, but it only addresses cases [1] and [10]. It does not solve case [8], where the Oxford title is non-diagnostic even when complete enough for display.

   Option `c` is the better next fix, with one constraint: do not scan the entire body naively for generic terms. Add a bounded secondary narrative/SR signal extractor that inspects high-signal fetched regions only, such as title/H1/meta citation title, article-type metadata, abstract/methods lead text, and the first content window. Use it only as a demotion/promote-to-T2 signal when title classification would otherwise fall through to presumed T1/T4, and record a distinct matched rule/reason.

4. **Do not run full-scale v3 yet.**

   M-16 should fix THU296 end-to-end, but v3 would knowingly preserve the other three observed failure modes unless the corpus composition changes by chance. Since the stated goal is to minimize wasted full-scale spend, build the bounded body-inspection path first, add unit tests for the three real truncated-title fixtures, then run one v3 sweep to validate M-16 plus the broader signal fix together.
