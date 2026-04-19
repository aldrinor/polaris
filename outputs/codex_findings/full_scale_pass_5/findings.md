---
verdict: BLOCKED-ON-ISSUE
pass: full_scale_5_m17c_code_audit
commit: c064a0c
all_pass4_citation_shapes_resolved: true
new_adversarial_results: "4/5 passed; external 'The 2025 clinical practice guideline recommends...' citation returned GUIDELINE instead of empty"
over_demotion_risks_found: 5
body_inspector_now_sound: false
rationale: |
  M-17c resolves the four pass-4 citation-byline regressions covered by the existing M-17 file, and the 49-test targeted suite passes. The new adversarial guideline citation still fails because the generic `(clinical practice )?guideline recommends` pattern is not anchored to "this" or another self-description signal. PRISMA contextual patterns still work, and PRISMA alone remains insufficient. Metadata > publisher header > body priority still holds in direct conflict checks. The body inspector is therefore improved but not sound enough for max-scale promotion until the guideline citation false positive is fixed.
---

**Verdict**

BLOCKED-ON-ISSUE. M-17c is close, but one remaining false positive can demote a primary paper when it cites an external clinical practice guideline.

**Patched Pattern Review**

Read line-by-line in `src/polaris_graph/retrieval/live_retriever.py`.

- SR/MA patterns at lines 225-256 are materially safer than pass 4. The `this systematic review...` / `this meta-analysis...` pattern at lines 235-240 rejects byline shapes such as "This meta-analysis by Smith et al." and catches core present-tense self-descriptive forms such as `examines`, `assesses`, `pools`, and `analyzes`.
- The Cochrane declarative pattern at lines 248-250 is narrow enough for citation-byline rejection. The `cochrane (database|library).*CD\d{6}` pattern at line 252 did not fire on the requested "Cochrane review CD012345" background case, but remains worth treating as metadata-like rather than arbitrary body text because a primary article could cite "Cochrane Library CD012345".
- Guideline pattern line 282 intentionally accepts exact `this clinical practice guideline` without a verb. That matches the M-17c spec and passed the no-verb adversarial case.
- Guideline pattern lines 284-286 are the blocking defect. Because the subject is simply `(clinical practice )?guideline`, it fires on external citations such as "The 2025 clinical practice guideline recommends..." even though the paper is not itself a guideline.
- Consensus patterns at lines 288-299 are safer than the generic guideline pattern because `this consensus statement...`, `consensus statement from X <verb>`, and `expert consensus panel/group <verb>` more strongly bind the statement/panel as the article subject.

**New Adversarial Bodies**

1. Primary trial mentioning `Cochrane review CD012345` in background:
   Expected `""`; actual `""`; pass.
2. Meta-analysis abstract saying `This meta-analysis pools SURPASS trial data.`:
   Expected `SR_MA`; actual `SR_MA`; pass.
3. Primary trial discussion saying `An updated systematic review and meta-analysis may further clarify these findings.`:
   Expected `""`; actual `""`; pass.
4. Guideline paper saying `This clinical practice guideline.`:
   Expected `GUIDELINE`; actual `GUIDELINE`; pass.
5. Primary paper saying `The 2025 clinical practice guideline recommends...`:
   Expected `""`; actual `GUIDELINE`; fail.

**Over-Demotion Risk**

Found 5 plausible legitimate declarative forms that currently return empty:

- `This review investigates...` returns `""` because the SR/MA pattern requires `systematic review` or `meta-analysis`, not bare `review`.
- `This review explored...` returns `""` for the same reason and because past tense `explored` is missing.
- `This systematic review and meta-analysis explored...` returns `""` because past tense `explored` is missing, despite `explores?` covering `explore/explores`.
- `This guideline offers recommendations...` returns `""` because `offers` is missing.
- `This guideline summarizes evidence and recommendations...` returns `""` because `summarizes` is only present for consensus statements, not guideline.

These are recall risks rather than the current blocker. I would not broaden them until the citation false-positive guard is fixed, because adding verbs to the unanchored guideline pattern would increase demotion risk.

**PRISMA Recheck**

PRISMA contextual checks still work:

- `Following PRISMA 2020 flow diagram... search...` returned `SR_MA`.
- `search and study selection followed PRISMA 2020` returned `SR_MA`.
- PRISMA without search/selection/extraction/flow-diagram context returned `""`.

**Priority Recheck**

Direct conflict checks confirm priority still holds:

- Metadata beats body: meta `Case Report` plus body `This meta-analysis pools...` returned `CASE_REPORT`.
- Publisher header beats body: `Article type: Meta-Analysis` plus body `We report a case...` returned `SR_MA`.
- Body is used only after metadata/header are absent: `We report a case...` returned `CASE_REPORT`.

**Test Runs**

- `python -m pytest -q tests\polaris_graph\test_m17_body_article_type.py`: 49 passed, 1 cache-permission warning.
- `python -m pytest -q`: blocked during collection by unrelated checkout/environment issues before test execution: missing `src.polaris_graph.wiki.mesh.*`, missing `src.agents.clarification_agent`, missing `src.benchmarks.hle_benchmark`, missing `src.phases`, and a Playwright `[WinError 5] Access is denied`.

**Required Fix**

Tighten the generic guideline self-descriptive pattern so citation subjects do not match. At minimum, require `this guideline <verb>` / `this clinical practice guideline <verb>`, or add a negative guard for dated/external citation subjects such as `the 2025 clinical practice guideline recommends`. After that, add the failed adversarial body as a regression test.
