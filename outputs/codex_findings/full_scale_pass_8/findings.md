---
verdict: CONDITIONAL
pass: full_scale_8_m17f_architecture_audit
commit: a2309f5
pass7_failures_resolved_by_gate: false
architectural_gate_sound: false
new_over_demotion_risks_found: 1
new_under_demotion_risks_found: 1
body_inspector_promotable: false
rationale: |
  I read the M-17f architectural change line-by-line in src/polaris_graph/retrieval/tier_classifier.py lines 725-771 and 1180-1234, and the six M-17f tests in tests/polaris_graph/test_m17_body_article_type.py lines 665-785. The keyword gate is sound for explicit article-type titles: SR/MA, case report/series, guideline/consensus/statement, and perspective/commentary/editorial/narrative titles all suppress R8b body override and log advisory_only before falling through to R9/R10. Non-diagnostic titles still receive the original body override, preserving the truncated-title motivation.

  However, the gate is narrower than the stated safety goal for primary papers with diagnostic titles. It only recognizes article-type diagnostic titles, not primary-study diagnostic titles. Fresh classify_source_tier() integration scenarios showed that "Randomized placebo-controlled trial of tirzepatide" + body GUIDELINE and "SURPASS-9 trial: tirzepatide in adults with obesity" + body GUIDELINE both return T4 via R8b_body_guideline. That is a material over-demotion path for exactly the false-positive body-guideline leakage Pass 7 exposed. It is documented in the tests, but documenting the behavior does not make it architecturally safe.

  I also found one under-demotion / over-grant risk in the advisory path: "Case report: Pancreatitis with tirzepatide" + false SR_MA body signal is advisory, then R9 classifies it as T4 through the narrative-review detector because "report" contains "review" as a substring. The tested case "Pancreatitis with tirzepatide: a case report" only asserts advisory_only and does not assert tier. This is not caused solely by M-17f, but the advisory branch exposes reliance on imperfect title rules after suppressing the body signal.
---

**Verdict**

CONDITIONAL. M-17f is the right architectural direction for stopping regex-tail chasing, but the gate is incomplete. It should also protect strong primary-study diagnostic titles from body-signal false positives before the body inspector is promoted.

**Gate Architecture Review**

`tier_classifier.py` lines 725-732 correctly state the pivot: body inspection cannot reliably distinguish papers citing external guidelines from new guidelines citing prior ones, so title-diagnostic papers should treat body signals as advisory.

Lines 733-755 define `_DIAGNOSTIC_TITLE_ARTICLE_TYPE_KEYWORDS`. It covers the four required article-type families:

- SR/MA: `systematic review`, `meta-analysis`, `network meta-analysis`; also `cochrane review`, `umbrella review`, `scoping review`.
- Case report: `case report`, `case-report`, `case series`; also `case-series`, `a case of `, `report of a case`.
- Guideline/consensus: `clinical practice guideline`, `practice guideline`, `consensus statement`; also `consensus recommendation`, `position statement`, `expert consensus`.
- Perspective/commentary/editorial: `perspective:`, `commentary:`, `editorial:`; also `opinion:`, `viewpoint:`, `letter to the editor`.

Lines 758-771 implement `_title_is_diagnostic_for_article_type()`. Empty titles return `False`. Non-empty titles are lowercased and matched by substring. This is adequate for the intended article-type gate, though it intentionally excludes primary-study terms such as `randomized`, `placebo-controlled`, and named trial markers.

Lines 1188-1196 compute `body_signal` and, for `SR_MA`, `CASE_REPORT`, `PERSPECTIVE`, and `GUIDELINE`, suppress the override when the title is article-type diagnostic. The code logs `R8b_body_signal_advisory_only: body=...` and falls through to R9/R10 without changing tier.

Lines 1197-1234 preserve the original override when title is not diagnostic: `SR_MA` returns T2; `CASE_REPORT`, `GUIDELINE`, and `PERSPECTIVE` return T4. This preserves recall for truncated/generic titles, but also means primary-trial titles without article-type keywords are still vulnerable to false body overrides.

**Integration Scenarios**

All scenarios used `classify_source_tier()` with independent title and `body_article_type` inputs.

| ID | Title | Body | Result | Advisory? | Rules | Assessment |
|---|---|---:|---:|---:|---|---|
| a | `Systematic review and meta-analysis of GLP-1 agonists` | `GUIDELINE` | T2 | yes | `R9_openalex_sr_or_ma` | Correct: false GUIDELINE body cannot demote SR/MA title. |
| b | `Case report: Pancreatitis with tirzepatide` | `SR_MA` | T4 | yes | `R9_openalex_narrative_review` | Override suppressed, but title path uses narrative detector because `report` contains `review`; correct tier by accident. |
| c | `Tirzepatide` | `GUIDELINE` | T4 | no | `R8b_body_guideline` | Correct: truncated title still gets body override. |
| d | `Tirzepatide` | `SR_MA` | T2 | no | `R8b_body_sr_ma` | Correct: truncated title still gets SR/MA body override. |
| e | `Randomized placebo-controlled trial of tirzepatide` | `GUIDELINE` | T4 | no | `R8b_body_guideline` | Problem: strong primary-trial title is over-demoted by false body signal. |
| f | `SURPASS-9 trial: tirzepatide in adults with obesity` | `GUIDELINE` | T4 | no | `R8b_body_guideline` | Problem: named trial title is over-demoted by false body signal. |
| g | `Expert consensus on tirzepatide prescribing` | `SR_MA` | T4 | yes | `R9_openalex_guideline_explainer` | Correct: consensus title suppresses false SR/MA body signal. |
| h | empty title | `CASE_REPORT` | T4 | no | `R8b_body_case_report` | Correct: no title evidence, body override remains active. |
| i | `Clinical practice guideline for tirzepatide in obesity` | `GUIDELINE` | T4 | yes | `R9_openalex_guideline_explainer` | Correct: agreeing diagnostic title/body becomes advisory, then title path returns T4. |
| j | `Systematic review of tirzepatide safety` | `CASE_REPORT` | T2 | yes | `R9_openalex_sr_or_ma` | Correct if body is false positive; contradictory true body would be ignored. |

The advisory path consistently logs `advisory_only` and does not add an R8b override rule.

**Pass-7 Failure Cases Revisited**

1. `Previous guidelines recommend X. This guideline updates those.` If the title is article-type diagnostic for another family, M-17f suppresses the false GUIDELINE body signal. If the title is a primary-trial title with no article-type keyword, the false GUIDELINE body signal still returns T4. Not fully resolved.

2. `We followed the 2025 ADA guideline for scope. This guideline was developed...` For a legitimate guideline with generic/truncated title, R8b GUIDELINE still returns T4. For a guideline title such as `Clinical practice guideline...`, the body signal becomes advisory and R9/R10 title rules still return T4. Resolved for guideline classification.

3. `In developing this guideline, we followed the 2025 ADA guideline. This guideline provides...` Same as case 2: legitimate guidelines still classify T4 either by body override on non-diagnostic title or by title path on diagnostic title.

**Primary-Trial-Title Concern**

Cases e and f are the blocker. The implementation treats `randomized`, `placebo-controlled`, `trial`, and named trial titles such as `SURPASS-9` as non-diagnostic for the gate, so R8b body GUIDELINE overrides them to T4 before R9 can grant T1. That preserves the body detector's false-positive cost for strong primary-study titles.

My recommendation is not to resume regex-tail chasing in the body detector. Instead, extend the gate concept: if the title has strong primary-study evidence and OpenAlex says peer-reviewed journal article, body article-type signals should be advisory or require conflict-specific handling. At minimum, primary-study title signals should suppress `GUIDELINE` and `PERSPECTIVE` body demotions; I would also consider suppressing `SR_MA` and `CASE_REPORT` when the title contains explicit primary design markers.

**Test Runs**

`python -m pytest -q tests/polaris_graph/test_m17_body_article_type.py`

Result: 64 passed. One warning: pytest could not create `.pytest_cache` under `C:\POLARIS` due to access denied.

**Required Fix**

Before promotion, add a targeted gate for strong primary-study diagnostic titles. The fix should stay architectural: do not rework the body regex. Suggested behavior:

- Detect explicit primary-study title signals such as `randomized`, `randomised`, `placebo-controlled`, `double-blind`, `phase 2`, `phase 3`, named trial plus `trial`, and established trial-program markers.
- When OpenAlex indicates a peer-reviewed journal article and the title is primary-study diagnostic, log `R8b_body_signal_advisory_only` and fall through to R9/R10 instead of applying R8b body override.
- Add tests for the required scenarios e and f expecting T1/advisory, plus a case where a generic/truncated title still allows GUIDELINE and SR_MA body overrides.

Also add a separate title-rule test for `case report` so the title path itself classifies case reports explicitly rather than depending on the accidental `report` contains `review` substring behavior.
