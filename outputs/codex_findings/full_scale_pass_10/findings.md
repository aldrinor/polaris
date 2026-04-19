---
verdict: CONDITIONAL
pass: full_scale_10_m18_classifier_fixes_audit
commit: 8039f8c
m18a_nejm_fix_sound: true
m18b_social_fix_sound: true
over_demotion_risks_found: 0
under_demotion_risks_found: 1
classifier_promotable_for_v5_sweep: true
rationale: |
  I read the patched tier_classifier.py regions line-by-line, not just the diff. Lines 467-482 keep the journal domain allowlist unchanged. Lines 490-515 add exact DOI prefixes, and lines 518-532 only accept URLs containing doi.org/ and an exact first path segment equal to an allowlisted prefix; doi.org/10.9999/... is safely rejected. Lines 674-690 make case reports, post-hoc, pooled, subgroup, and named program-level analyses strong narrative signals. Lines 697-712 make treatment/update/perspective/clinician phrases weak signals. Lines 721-742 first honors generic narrative review markers, then strong markers, then suppresses weak markers whenever any primary-study signal exists. That fixes the NEJM head-to-head RCT but creates one non-blocking under-demotion risk: narrative titles such as "Update on randomized trials..." or "Beyond randomized trials..." can reach T1 if OpenAlex says article+journal and the host/DOI is allowlisted. Lines 945-962 place RP1_social_platform_early before R1_stub_content_length, so Facebook/Twitter/Reddit are T6 by authority before body length is considered. Lines 1438-1440 correctly extend the R9 host allowlist to exact peer-reviewed DOI prefixes.
---

**Verdict**

CONDITIONAL. The M-18 target fixes are sound and the classifier is promotable for the V5 re-sweep, with one tracked under-demotion risk around weak narrative markers deferring to broad primary-study signals. I do not see a blocker for launching V5; this should be fixed or watched because it can over-grant T1 to review/commentary titles that mention randomized trials.

**M-18a Review**

Lines 467-482: existing peer-reviewed journal domains are unchanged and still include NEJM, JAMA, Lancet, NIH literature hosts, diabetesjournals.org, etc.

Lines 490-515: `PEER_REVIEWED_DOI_PREFIXES` covers the intended publisher prefixes, including `10.1056`, `10.1001`, `10.1016`, `10.1038`, `10.1136`, and `10.2337`.

Lines 518-532: `_has_peer_reviewed_doi_prefix` is narrow enough for the stated use. It lowercases the URL, requires `doi.org/`, extracts the first path segment after that, and requires exact membership in the prefix set. `https://doi.org/10.9999/not-real` did not pass the helper or the T1 allowlist.

Lines 674-690: strong narrative markers preserve the important M-16 behavior: case report, post-hoc, pooled, subgroup, and named program analyses still fire even when a title also contains trial language such as `SURPASS-4`.

Lines 697-712 and 721-742: the weak-marker deferral fixes the DR audit's NEJM RCT case, but the deferral is broad. Any primary marker, including generic `randomized`, suppresses weak narrative markers such as `update on`, `the role of`, and `for clinicians`. That is the one under-demotion risk.

Lines 854-890: `_PRIMARY_STUDY_TITLE_MARKERS` now includes `as compared with` and `as compared to`, which correctly handles NEJM-style head-to-head titles and `Effects of ... as compared with placebo ...` titles.

Lines 1438-1440: R9 now treats an allowlisted DOI prefix as equivalent to an allowlisted peer-reviewed host. This is necessary for doi.org URLs and is exact-prefix guarded.

**M-18b Review**

Lines 945-962: `RP1_social_platform_early` runs after retraction exclusion and before `R1_stub_content_length`. This is the correct order: retracted papers remain blocked, then social/general-interest platforms are T6 regardless of body length, then non-social stubs remain T7.

Lines 1006-1020: the older social rule remains as a later backstop. It is now redundant for normal social URLs, but harmless.

**Integration Scenarios**

1. `Tirzepatide as Compared with Semaglutide for the Treatment of Obesity`; `https://doi.org/10.1056/NEJMoa2416394`; body 8000; expected T1; actual T1 via `R9_openalex_primary_study`.
2. `Post-hoc analysis of SURPASS-4`; `https://www.nejm.org/doi/full/10.1056/foo`; body 8000; expected T4; actual T4 via `R9_openalex_narrative_review`.
3. `Tirzepatide in type 2 diabetes: a pooled analysis`; `https://diabetesjournals.org/...`; body 8000; expected T4; actual T4 via `R9_openalex_narrative_review`.
4. `Tirzepatide for the Treatment of Obesity`; `https://pmc.ncbi.nlm.nih.gov/articles/PMC9999/`; body 8000; expected T4; actual T4 via `R9_openalex_narrative_review`.
5. `Effects of tirzepatide as compared with placebo on HbA1c`; `https://doi.org/10.1001/jama.2024.12345`; body 8000; expected T1; actual T1 via `R9_openalex_primary_study`.
6. Facebook boxed-warning post; body 816; expected T6; actual T6 via `RP1_social_platform_early`.
7. Twitter/X long thread; body 50000; expected T6; actual T6 via `RP1_social_platform_early`.
8. Reddit medical discussion; body 3000; expected T6; actual T6 via `RP1_social_platform_early`.
9. NEJM URL with body 500; expected T7; actual T7 via `R1_stub_content_length`.
10. `https://doi.org/10.9999/not-real`; article+journal metadata; expected T4; actual T4 via `R9_openalex_unverified_host_demoted_to_t4`.
11. `Case report randomized trial phrase`; `https://doi.org/10.1056/foo`; body 8000; expected T4; actual T4 via `R9_openalex_narrative_review`.
12. `Beyond randomized trials: real-world evidence`; `https://doi.org/10.1056/NEJMra999999`; body 8000; expected likely T4 if review/commentary; actual T1 via `R9_openalex_primary_study`.
13. `Update on randomized trials of tirzepatide`; `https://doi.org/10.1056/NEJMra999999`; body 8000; expected likely T4; actual T1 via `R9_openalex_primary_study`.
14. `Randomized trials for clinicians: interpreting tirzepatide evidence`; `https://doi.org/10.1056/NEJMra999999`; body 8000; expected likely T4; actual T1 via `R9_openalex_primary_study`.

**Regression Check**

Post-hoc SURPASS title still narrative: yes. M-16 `test_post_hoc_analysis_title_detects` remains covered and the adversarial `Post-hoc analysis of SURPASS-4` classified T4.

Pooled analysis still narrative: yes. M-16 `test_pooled_analysis_title_detects` remains covered and the adversarial pooled-analysis case classified T4.

Case report still narrative: yes. M-16 case-report tests remain covered, and a title containing both `case report` and `randomized trial` classified T4.

Bare `X for the Treatment of Y` still narrative: yes. The M-18 focused test and adversarial PMC case both classified T4.

**Test Runs**

`python -m pytest -q tests/polaris_graph/test_m18_dr_audit_fixes.py`: 10 passed. Pytest emitted a cache warning because `.pytest_cache` could not be written.

`python -m pytest -q tests/polaris_graph/`: 606 passed, 2 failed, 23 errors out of 631 collected. The failures/errors were environmental permission failures writing under `C:\Users\msn\AppData\Local\Temp` or `.pytest_cache`, not M-18 classifier assertion failures.

**Required Fix**

No blocking M-18 fix is required before V5. Recommended targeted improvement: weak narrative markers should not defer to every primary marker. Either make weak markers win when the primary signal is only generic `randomized` / `trial` plural language, or add strong narrative patterns such as `beyond randomized trials`, `update on randomized trials`, `the role of randomized trials`, and `for clinicians` constructions before the primary-signal suppression.
