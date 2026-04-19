---
verdict: CONDITIONAL
pass: full_scale_9_m17g_combined_gate_audit
commit: 10bb23f
combined_gate_sound: true
primary_study_gate_scenarios_passed: "10/10 behavioral scenarios passed; 2 residual edge risks noted"
over_demotion_risks_remaining: 1
under_demotion_risks_remaining: 1
body_inspector_now_promotable: true
rationale: |
  I read the M-17g addition line-by-line. Lines 733-771 define the article-type title gate as a direct lowercase substring match over explicit article-type tokens. This arm is intentionally broad for titles that already name their type: systematic review/meta-analysis, case report/series, clinical practice guideline, consensus/position/expert statements, perspective/commentary/editorial/opinion/viewpoint, conference abstract markers, and narrative/literature review labels.
  Lines 782-824 define the primary-study title gate as a positive marker list plus a simple lowercase substring detector. Strong markers include randomized/randomised, controlled trial, blinding, placebo-controlled, phase markers, named trials such as SURPASS/SURMOUNT/SELECT/LEADER/SUSTAIN/REWIND/PIONEER, cohort/case-control/cross-sectional/prospective/retrospective/observational/registry/longitudinal/post-marketing/real-world study language, first-in-human, and explicit trial phrasing. The weak marker is "effect of"/"effects of".
  Lines 1188-1208 compute body_signal, restrict R8b to SR_MA/CASE_REPORT/PERSPECTIVE/GUIDELINE, then form the union gate: title_has_article_type OR title_is_primary_study. The primary-study arm is correctly bounded by OpenAlex journal/peer-reviewed evidence and publication_type in article/review. Empty source_type only passes if is_peer_reviewed is explicitly True; otherwise it does not gate.
  Lines 1209-1220 suppress the body override and append advisory-only reason text when either gate arm fires. If both arms fire, gate_reason logs "article-type" because that arm has priority in the ternary. Lines 1221-1258 preserve the original body override for non-diagnostic titles.
  The combined gate is structurally sound for the intended M-17g pivot: body detection remains advisory when title-level evidence is stronger, and remains decisive when the title is generic/truncated. The remaining risks are not regex-tail issues, but boundary choices: "effect of" can over-protect an unlabeled non-primary article, and bare primary-paper titles with no positive primary marker remain unprotected from a false body signal.
---

**Verdict**

CONDITIONAL. The M-17g combined gate is sound enough to promote the body inspector path for max-scale audit use, but I would carry two explicit residual risks into V4 monitoring rather than claim the gate is complete for every primary paper shape.

**Combined Gate Review**

Article-type arm: sound. `_title_is_diagnostic_for_article_type` only checks explicit title labels, so a title such as `Clinical practice guideline for X` or `Tirzepatide efficacy: a systematic review and meta-analysis` makes R8b advisory and lets R9/R10 classify from title/OpenAlex. This prevents body false positives from changing one article type into another.

Primary-study arm: mostly sound. It requires both `_detect_primary_study_signal(title)` and OpenAlex journal/peer-reviewed evidence with `publication_type in ("article", "review")`. This is the right architectural bound: a random web page or repository item titled like a trial still lets body override fire.

Union behavior: sound. If both article-type and primary-study arms fire, logging chooses `gate_reason="article-type"`. That is acceptable because article-type title evidence is more specific and R9 then still demotes SR/MA or guideline titles appropriately.

**Integration Scenarios**

1. Both arms: `Randomized trial: a systematic review of tirzepatide efficacy`, body `GUIDELINE`, journal article. Result `T2`, rule `R9_openalex_sr_or_ma`, advisory reason logs `article-type`. Pass.
2. Neither arm: `Tirzepatide efficacy in adults`, body `GUIDELINE`, journal article. Result `T4`, rule `R8b_body_guideline`. Pass.
3. Primary signal but empty source type and not peer-reviewed: `Randomized placebo-controlled trial of tirzepatide`, body `GUIDELINE`, `source_type=""`, `is_peer_reviewed=False`. Result `T4`, rule `R8b_body_guideline`. Pass.
4. Primary signal plus journal plus `pub_type=review`: same randomized title, body `GUIDELINE`. Gate fires, body advisory; R9 returns `T4` via `R9_openalex_pubtype_review`. Pass for gate behavior; metadata conflict remains outside R8b.
5. Weak marker: `Effect of tirzepatide on beta-cell function`, body `CASE_REPORT`, journal article. Gate fires, result `T1`. This is the main over-protection risk if the body signal is legitimate rather than false.
6. Named trial: `SURMOUNT-5 trial of tirzepatide in obesity`, body `SR_MA`, journal article. Gate fires, result `T1`. Pass.
7. Observational title: `Prospective cohort study of tirzepatide adherence`, body `PERSPECTIVE`, journal article. Gate fires, result `T1`. Pass.
8. Preprint/repository: `Randomized placebo-controlled trial of tirzepatide`, body `GUIDELINE`, `pub_type=preprint`, `source_type=repository`. R7 preprint returns `T4` before R8b/R9. Pass.
9. Legit guideline title with false SR/MA body: `Clinical practice guideline for tirzepatide in obesity`, body `SR_MA`, journal article. Gate logs `article-type`; R9 returns `T4` via guideline/explainer title. Pass.
10. Primary trial title plus false guideline body: `Randomized trial of tirzepatide in adults with obesity`, body `GUIDELINE`, journal article. Gate logs `primary-study`; R9 returns `T1`. Pass.

**Pass-7 Failure Cases Final Check**

Detector behavior remains imperfect as expected: `Previous guidelines recommend lifestyle intervention. This guideline updates those...` still returns `GUIDELINE`.

With a primary-trial title that triggers M-17g, `Randomized trial of tirzepatide in adults with obesity` plus that false body signal classifies `T1` through `R9_openalex_primary_study`, with body advisory. This is the architectural win.

With a generic actual-guideline title, `Tirzepatide` plus body `GUIDELINE` still classifies `T4` through `R8b_body_guideline`. This preserves the original M-17 motivating behavior.

With an explicit guideline title, `Clinical practice guideline for tirzepatide` plus false body `SR_MA` logs body advisory and classifies `T4` through `R9_openalex_guideline_explainer`. This fixes the SR/MA false-demotion case for legitimate guidelines.

One non-R8b nuance: a title like `Randomized trial of tirzepatide after previous guidelines recommend lifestyle intervention` triggers the primary-study advisory gate, but R9 later demotes to `T4` because `_detect_guideline_or_explainer_title` matches `guidelines`. That is a separate title-heuristic interaction, not a failure of the R8b union gate.

**Over-Demotion Risk**

One residual over-protection risk remains. The primary-study marker `effect of` / `effects of` is broad. In the scenario `Effect of tirzepatide on beta-cell function` with a legitimate `CASE_REPORT` body signal and OpenAlex journal article metadata, R8b suppresses the body demotion and R9 returns `T1`. Most legitimate case reports, systematic reviews, and guidelines should carry title labels caught by the article-type arm or R9 title demoters, so this is non-blocking but should be monitored.

**Under-Demotion Risk**

One residual under-protection risk remains by design: primary journal papers with bare titles and no positive primary marker are not protected from false body signals. Example: a true primary paper titled only `Tirzepatide in type 2 diabetes` would not satisfy the primary-study arm; if the detector emits `GUIDELINE`, R8b still demotes to `T4`. This is the cost of keeping the gate conservative and avoiding over-trusting OpenAlex article+journal alone.

**Test Runs**

`python -m pytest -q tests/polaris_graph/test_m17_body_article_type.py`

Result: 67 passed. One warning only: pytest could not create `.pytest_cache` due Windows access denial.

**Required Fix**

No blocking fix required before V4 max-scale content audit. Recommended non-blocking monitoring/follow-up:

1. Track suppressed body signals where the only primary-study marker is `effect of` or `effects of`.
2. Track R8b demotions for allowlisted journal articles whose titles lack primary markers but whose journals/URLs look like primary literature.
3. Consider later narrowing R9 guideline-title demotion so incidental `guidelines` mentions in otherwise primary-trial titles do not demote.
