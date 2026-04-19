---
verdict: BLOCKED-ON-ISSUE
pass: full_scale_3_m17_code_audit
commit: 029d521a7933893fccc6e1b3fc7a01284885ab97
body_inspector_sound: false
false_positive_risks_found: 6
over_demotion_risks_found: 3
tests_sound: mixed
rationale: |
  I read the M-17 detector, fetch propagation, classifier rule ordering, and all 21 M-17 tests end-to-end. The tuple propagation and R8b-before-R9 ordering are correct, and the scan is mechanically bounded to 8KB for metadata and 4KB for body-pattern rules. The blocker is semantic: the body-pattern phase treats isolated lead mentions of "systematic review", "meta-analysis", "case series", "for clinicians", and similar generic phrases as article-type proof, so legitimate primary papers can be over-demoted. The tests pass, but they only exercise positive detection and prior-regression cases; they do not test the false-positive scenario explicitly called out in the audit brief. M-17 should not proceed to v4 max-scale until the body detector requires stronger contextual evidence or adds negative guards for cited prior literature / methodological background mentions.
---

# M-17 Code Audit Findings

## Verdict

`BLOCKED-ON-ISSUE`.

The implementation is structurally wired correctly, but the detector is not sound enough for max-scale because body-pattern false positives can override OpenAlex `article` + `journal` primary promotion and demote legitimate primary studies.

## Signal Trace

Body detection is called in both fetch paths:

- `src/polaris_graph/retrieval/live_retriever.py:491` detects `body_type` in `_fetch_content_httpx_naive`.
- `src/polaris_graph/retrieval/live_retriever.py:599` detects `body_type` in `_fetch_content`.
- `src/polaris_graph/retrieval/live_retriever.py:884` unpacks the 4-tuple.
- `src/polaris_graph/retrieval/live_retriever.py:927-938` passes `body_article_type` into `ClassificationSignals`.
- `src/polaris_graph/retrieval/tier_classifier.py:1124-1166` applies R8b before R9/R10.

R8b therefore does override OpenAlex R9 primary promotion. That is desirable for true article-type evidence, but unsafe with the current broad body patterns.

## Detector Audit

`_detect_article_type_from_body` is mechanically bounded:

- `head = raw_content[:8000]` at `live_retriever.py:255`.
- metadata regexes search only `head`.
- `lead = head_lower[:4000]` at `live_retriever.py:283`.
- body pattern regexes search only `lead`.

No regex exceeds the intended scan windows. I did not see catastrophic-backtracking patterns.

Priority is correct: explicit article-type metadata is inspected first at `live_retriever.py:258-280`, then lead body patterns at `live_retriever.py:282-295`.

Line-level concerns:

- `live_retriever.py:192-194`: meta tag regexes require the identifying attribute before `content=...`. They miss valid tags where `content` appears first, such as `<meta content="Systematic Review" name="citation_article_type">`. This is recall loss, not an over-demotion risk.
- `live_retriever.py:197`: JSON-LD `@type` is captured but cannot map to any current signal because `ScholarlyArticle`, `MedicalScholarlyArticle`, and `Article` contain none of the downstream keywords. Harmless but functionally dead.
- `live_retriever.py:199-201`: the Frontiers marker includes `BRIEF REPORT article`, but the captured value is not mapped to a return value. Harmless for M-17 goals, but misleading coverage.
- `live_retriever.py:207`: `\bsystematic review\b` fires on cited/background prior evidence, not only on the fetched article type.
- `live_retriever.py:208-209`: `\bmeta[- ]analysis\b` and `\bnetwork meta[- ]analysis\b` fire on background/methodology phrases, including "meta-analysis methodology" or "prior meta-analysis".
- `live_retriever.py:211`: `PRISMA` is treated as SR/MA proof. Usually high-signal, but it can appear in protocol/reporting-method discussions; it needs context such as search/selection/extraction rather than a lone token.
- `live_retriever.py:217-218`: `case report` and `case series` fire on exclusion criteria or prior-literature background, e.g. "we excluded case reports and case series".
- `live_retriever.py:226-227`: `for primary care providers` and `for clinicians` are broad audience phrases; they can appear in primary papers' implications/conclusion text.
- `live_retriever.py:231-237`: guideline terms are plausible high-signal article-type terms, but "practical guidance" and "expert consensus" can also appear as cited comparator/background material.

The actual risk named in the audit brief is real. This primary-study lead would return `SR_MA`:

```text
Abstract
Background: We compared tirzepatide to semaglutide in adults with obesity.
Prior evidence includes the Wilding et al. systematic review for GLP-1 receptor agonists.
Methods: Participants were randomized ...
```

So would:

```text
Abstract
Methods: This randomized trial compared tirzepatide with semaglutide.
We discuss meta-analysis methodology used in prior evidence synthesis.
```

Both would propagate to R8b and become T2, overriding R9 T1.

`we reviewed the literature` does not currently match any pattern by itself. `post hoc analysis` also does not match, so that exact over-demotion example is not triggered.

## 8KB / 4KB Bounds

The bounds are honored exactly in code. The 4KB lead limit is cost-safe and helps avoid late-body false positives, but it is not semantically safe because abstracts and introductions commonly cite prior reviews and guidelines in the first 4KB.

The existing bound test puts `meta-analysis` after 10KB, which proves the bound. It does not prove that the first 4KB is high precision.

## R8b Ordering

R8b fires at `tier_classifier.py:1124-1166`, before R9 starts at `tier_classifier.py:1168`. A non-empty valid body signal wins over OpenAlex `article` + `journal` and over R10 journal-domain presumed primary.

This satisfies the intended override, but it amplifies the detector false positives into final-tier regressions.

## 4-Tuple Propagation

`rg` over `src` and `tests` found the live retriever production caller updated:

- `live_retriever.py:884`: `content, ok, content_title_from_fetch, body_article_type = _fetch_content(...)`

The updated tests unpack four values in `test_fetch_access_bypass_wiring.py`.

No unupdated production call to `src.polaris_graph.retrieval.live_retriever._fetch_content` was found. `src/agents/analyst_agent.py` has a separate method named `_fetch_content`; it is unrelated.

## Test Audit

All targeted tests pass:

```text
python -m pytest -q tests/polaris_graph/test_m17_body_article_type.py tests/polaris_graph/test_fetch_access_bypass_wiring.py
27 passed, 1 warning
```

The warning was only a `.pytest_cache` write-permission warning.

Per-test read:

- `test_frontiers_systematic_review_article_header`: name matches assertion. Realistic for Frontiers. Positive only, no regression.
- `test_meta_citation_article_type_systematic_review`: name matches. Realistic but minimal. Positive only.
- `test_meta_citation_article_type_case_report`: name matches. Realistic but minimal. Positive only.
- `test_prisma_reference_in_body_signals_sr_ma`: name matches what code does, but content is toy-like and could normalize an unsafe false-positive pattern. Positive only.
- `test_we_report_a_case_pattern_signals_case_report`: name matches. Realistic for case report abstract. Positive only.
- `test_a_62_year_old_patient_signals_case_report`: name matches. Realistic for a case report, but also broad enough to appear in clinical vignettes. Positive only.
- `test_perspective_for_signals_perspective`: name matches. Realistic headline. Positive only.
- `test_clinical_practice_guideline_signals_guideline`: name matches. Realistic. Positive only.
- `test_consensus_statement_signals_guideline`: name matches. Realistic but toy-length. Positive only.
- `test_nature_article_type_header_meta_analysis`: name matches. Realistic enough for publisher header. Positive only.
- `test_meta_analysis_in_abstract_lead`: name matches. It asserts broad lead detection, but does not distinguish an actual article type from a primary paper mentioning meta-analysis. Positive only.
- `test_bounded_scan_ignores_late_false_signals`: name matches. It verifies late body-pattern suppression after 8KB, but not the 4KB boundary or metadata-only 8KB behavior.
- `test_empty_content_returns_empty`: name matches. Also passes `None` despite the function annotation being `str`; useful robustness check.
- `test_pmc_truncated_title_body_case_report_goes_to_t4`: name matches. It tests classifier behavior from a pre-supplied body signal, not detector-to-classifier integration. Regression for prior false T1.
- `test_pmc_truncated_title_body_perspective_goes_to_t4`: name matches. Same limitation: classifier-only, not detector integration. Regression for prior false T1.
- `test_oxford_non_diagnostic_title_body_sr_ma_goes_to_t2`: name matches. Classifier-only body signal override. Regression for prior false T1.
- `test_body_empty_signal_falls_through_to_title_rules`: name matches. This confirms bare NEJM primary remains T1 when body signal is empty.
- `test_body_signal_overrides_even_strong_openalex_primary`: name matches. Confirms R8b beats R9.
- `test_body_guideline_overrides_title`: name matches. Positive R8b rule coverage.
- `test_regression_m7_facebook_still_t6`: name matches. Good prior-regression guard; unrelated to M-17 detector precision.
- `test_regression_sr_ma_title_still_t2_without_body`: name matches. Good R9/R10 title-regression guard.

Overall: tests are mixed. They cover positives, R8b ordering, and some regressions, but they do not test the central false-positive risk from primary abstracts mentioning prior systematic reviews/meta-analyses/guidelines/case series.

## Required Fixes Before Re-Audit

1. Add negative tests for primary articles whose lead mentions prior reviews:
   - "Wilding et al. systematic review for prior evidence" should return `""`.
   - "meta-analysis methodology" should return `""`.
   - "we excluded case reports and case series" should return `""`.
   - "guidelines recommend background therapy" should return `""`.

2. Tighten SR/MA body detection to require article-type context, not a lone keyword. Examples of safer positive context:
   - explicit metadata/header says systematic review/meta-analysis;
   - abstract objective says "to conduct/perform a systematic review/meta-analysis";
   - methods mention database search + study selection/extraction + pooled estimates;
   - PRISMA appears with flow diagram/search/selection/extraction context.

3. Tighten perspective/guideline detection similarly:
   - prefer explicit article-type metadata/header;
   - avoid classifying solely on audience phrases like "for clinicians";
   - distinguish cited guideline background from the fetched article being a guideline.

4. Add a classifier-level regression proving a false detector signal would over-demote a primary OpenAlex journal article, then prevent that signal from being emitted by the detector.

