---
verdict: BLOCKED-ON-ISSUE
pass: full_scale_6_m17d_code_audit
commit: 56f54d5
all_pass5_citation_shapes_resolved: true
new_adversarial_results: "15 pass / 3 fail across 18 direct-call probes"
over_demotion_risks_found: 2
body_inspector_now_sound: false
rationale: |
  I read src/polaris_graph/retrieval/live_retriever.py lines 180-310 from the file, then re-read the patched guideline block at lines 271-302 line by line. The M-17d dated and generic external citation shapes are fixed because the guideline verb regex now requires explicit "this" before "(clinical practice )?guideline". The provided 54-test suite passes. However, one user-required positive adversarial body fails: "Previous guidelines recommend... This guideline updates those recommendations" returns empty because "updates" is not in the guideline verb list. I also found two over-demotion risks: an anaphoric external citation using the newly broadened "summarizes" verb returns GUIDELINE, and the bare fully-qualified "this clinical practice guideline" pattern still returns GUIDELINE even when used as an external trial-design reference. Therefore the body inspector is improved but not sound enough for max-scale promotion.
---

**Verdict**

BLOCKED-ON-ISSUE. M-17d fixes the exact pass-5 dated citation leak, but the body inspector is still not sound: it misses the required "updates" guideline recall shape and can still over-demote plausible primary-paper external guideline references.

**Patched Pattern Review**

Read from `src/polaris_graph/retrieval/live_retriever.py`, not just the diff.

Lines 198-207 define trusted metadata patterns for `citation_article_type`, `article:section`, `prism.section`, and JSON-LD `articleType`.

Lines 212-222 define trusted publisher headers: Frontiers-style uppercase article banners and Nature-style `Article type:` banners.

Lines 223-254 define SR/MA body patterns. They require objective/method declarations, `this systematic review/meta-analysis` plus a descriptive predicate, contextual PRISMA within 40 chars of search/selection/extraction/flow diagram, tightened Cochrane self-reference or CD-number metadata, or pooled-estimate plus random/fixed-effects signatures.

Lines 271-283 contain the guideline comments. They correctly document the M-17c citation problem and M-17d's change: the former unanchored guideline-plus-verb shape leaked dated external citations, so explicit `this` is now required before the guideline noun.

Lines 284-308 define guideline/consensus patterns. The patched guideline verb pattern at lines 289-292 is `this\s+(clinical\s+practice\s+)?guideline\s+` followed by `provides|recommends|was developed|is intended|presents|outlines|aims?|establishes|offers|summarizes|describes`. I read the regex and comments character by character. The M-17d `this` prefix is present. The broadened verbs `offers|summarizes|describes` are present. The separate exact pattern `this\s+clinical\s+practice\s+guideline` remains broad and does not require a verb.

Lines 347-418 show priority ordering in `_detect_article_type_from_body`: metadata first, publisher headers second, then body SR/MA, case report, guideline, and perspective patterns. This implements metadata > header > body.

**New Adversarial Bodies**

Direct calls to `_detect_article_type_from_body`:

| Case | Expected | Actual | Result |
|---|---:|---:|---:|
| `A recent clinical practice guideline recommends...` | `""` | `""` | PASS |
| `The current guideline suggests...` | `""` | `""` | PASS |
| `The 2025 guideline recommends... This guideline was developed...` | `GUIDELINE` | `GUIDELINE` | PASS |
| `Previous guidelines recommend... This guideline updates those recommendations...` | `GUIDELINE` | `""` | FAIL |
| `According to clinical practice guidelines, tirzepatide is recommended...` | `""` | `""` | PASS |
| `This guideline offers... The 2025 clinical practice guideline recommends...` | `GUIDELINE` | `GUIDELINE` | PASS |

Additional adversarial over-demotion probes:

| Case | Expected | Actual | Result |
|---|---:|---:|---:|
| `We followed the 2025 ADA guideline... This guideline summarizes standards... our randomized trial...` | `""` | `GUIDELINE` | FAIL |
| `Endpoint definitions followed this clinical practice guideline during trial design.` | `""` | `GUIDELINE` | FAIL |

**Over-Demotion Risk**

The verb-list broadening creates a plausible over-demotion path. `This guideline summarizes...` now fires even when `This guideline` is an anaphoric reference to a named external guideline in the preceding sentence of a primary trial.

There is also a pre-existing but still relevant over-demotion path from `r'this\s+clinical\s+practice\s+guideline'`: it fires without requiring a self-descriptive verb, so a primary paper saying it followed "this clinical practice guideline" for endpoint definitions returns `GUIDELINE`.

No collateral damage found in the SR/MA or consensus probes I ran: external Cochrane and "according to a consensus statement from..." remained empty, while self-declarative meta-analysis and consensus statement shapes still fired.

**PRISMA Recheck**

`PRISMA` alone returned `""`.

`PRISMA` followed by search context returned `SR_MA`.

Search/selection context before `PRISMA` returned `SR_MA`.

This matches the contextual PRISMA requirement in lines 240-242.

**Priority Recheck**

Metadata > header > body passed: a `Case Report` meta tag beat a `SYSTEMATIC REVIEW article` header and guideline body text, returning `CASE_REPORT`.

Header > body passed: `META-ANALYSIS article` beat guideline body text, returning `SR_MA`.

Body-only passed: without metadata or header, `This guideline provides...` returned `GUIDELINE`.

**Test Runs**

`python -m pytest -q tests/polaris_graph/test_m17_body_article_type.py`

Result: 54 passed, 1 pytest cache warning due access denied on `.pytest_cache`.

The 5 M-17d tests are present and cover:

- dated external citation: `The 2025 clinical practice guideline recommends...` -> `""`
- generic external citation: `The guideline recommends...` -> `""`
- positive recall for `offers` -> `GUIDELINE`
- positive recall for `summarizes` -> `GUIDELINE`
- positive recall for `describes` -> `GUIDELINE`

**Required Fix**

1. Add a high-precision positive guideline pattern for `this guideline updates those recommendations` or add `updates?` to the guideline verb list if the false-positive risk is accepted.
2. Reduce over-demotion from anaphoric external citations before max-scale promotion. At minimum, add tests for an external named guideline followed by `This guideline summarizes/describes/offers...` in a primary-trial context.
3. Reconsider the bare `this clinical practice guideline` pattern because it does not require a predicate and still flags external-use phrasing.
