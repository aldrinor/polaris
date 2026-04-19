---
verdict: BLOCKED-ON-ISSUE
pass: full_scale_7_m17e_code_audit
commit: 1b66242
all_pass6_failures_resolved: true
new_adversarial_results: "10 pass / 3 fail across 13 direct probes; failures: previous-guidelines anaphora false positive, mixed external-then-self-declarative over-demotion, explicit in-developing-this-guideline over-demotion"
over_demotion_risks_found: 2
body_inspector_now_sound: false
rationale: |
  I read src/polaris_graph/retrieval/live_retriever.py lines 271-310 and 356-448 from the file, not only the diff. Lines 271-291 document the M-17c/M-17d/M-17e guideline tightening, including removal of summarizes/describes for bare "this guideline", sentence-start anchoring for the bare clinical-practice-guideline phrase, and updates? recall restoration. Lines 292-305 define the patched guideline and consensus regexes: the bare clinical-practice-guideline pattern is anchored to start/sentence/newline, the guideline verb list includes provides/recommends/was developed/is intended/presents/outlines/aims/establishes/offers/updates?, and summarizes/describes are absent from that guideline verb pattern. Lines 420-443 define and apply the function-local _ANAPHORIC_GUIDELINE_CITATION guard with a preceding 300-character window. The guard handles followed/following/according to/citing/cited/per/as recommended by/as per/based on/in line with plus optional year/source/clinical practice guideline(s), then skips the guideline match when such a citation appears before it.
  The 58-test M-17 module passes, and the five M-17e tests cover the three pass-6 failures plus the updates positive and ambiguous-verb inversions. However, direct adversarial probes show M-17e remains unsound: it misses the required "Previous guidelines recommend X. This guideline updates those." anaphoric case because "previous guidelines recommend" is not in the guard marker list, and it over-demotes plausible legitimate self-declarative guidelines that cite/follow an earlier guideline within 300 characters before saying "This guideline provides/was developed...".
---

**Verdict**

BLOCKED-ON-ISSUE. M-17e fixes the three named pass-6 regressions in the checked tests, but fresh adversarial bodies still expose one blocking false positive and two over-demotion risks. The body inspector is not ready for max-scale promotion.

**Patched Pattern Review**

I read [live_retriever.py](C:/POLARIS/src/polaris_graph/retrieval/live_retriever.py:271) lines 271-310 line by line.

Lines 271-291 explain the guideline-body tightening history. The important M-17e claims are present in comments: anaphoric prior external-guideline references must reject later "this guideline" matches; ambiguous guideline verbs `summarizes` and `describes` were removed; the bare `this clinical practice guideline` phrase must appear at sentence start; and `updates?` was added.

Lines 292-301 implement the guideline tuple. The bare pattern is:

```python
r'(?:^|[.!?]\s+|\n\s*)this\s+clinical\s+practice\s+guideline\b'
```

That prevents object-position matches like "followed this clinical practice guideline". The second guideline pattern requires `this` plus an unambiguous verb:

```python
provides|recommends|was developed|is intended|presents|outlines|aims?|establishes|offers|updates?
```

`summarizes` and `describes` are absent from the guideline verb list. Lines 302-310 keep consensus statement handling separate; consensus still allows `summarizes`, which is not affected by the guideline anaphora guard.

I also read [live_retriever.py](C:/POLARIS/src/polaris_graph/retrieval/live_retriever.py:356) lines 356-448 line by line.

Lines 386-392 process explicit meta/JSON-LD article-type tags first. Lines 394-402 process publisher headers second. Lines 404-419 run SR/MA and case-report contextual body rules before guidelines. Lines 420-443 define and apply the anaphoric guideline guard:

```python
_ANAPHORIC_GUIDELINE_CITATION = re.compile(
    r'(?:followed|following|according\s+to|citing|cited|per|'
    r'as\s+recommended\s+by|as\s+per|based\s+on|in\s+line\s+with)'
    r'\s+(?:the\s+)?(?:\d{4}\s+)?(?:[a-z]+\s+)?(?:clinical\s+practice\s+)?'
    r'guidelines?\b',
    re.IGNORECASE,
)
```

For each guideline match, line 440 slices the preceding 300 chars, line 441 searches that slice for an external-guideline citation marker, line 442 skips the match if found, and line 443 returns `GUIDELINE` otherwise.

**New Adversarial Bodies**

Direct calls to `_detect_article_type_from_body`:

| Case | Body summary | Expected | Actual | Result |
| --- | --- | --- | --- | --- |
| a | `We followed the 2024 NICE guideline. This guideline updates... Our trial...` | `""` | `""` | PASS |
| b | `Based on the 2025 European guideline. This guideline offers recommendations.` | `""` | `""` | PASS |
| c | `This clinical practice guideline provides evidence-based recommendations...` | `GUIDELINE` | `GUIDELINE` | PASS |
| d | External citation, then 400+ chars filler, then `This guideline provides...` | `GUIDELINE` | `GUIDELINE` | PASS |
| e | `Previous guidelines recommend X. This guideline updates those.` | `""` | `GUIDELINE` | FAIL |
| f | `We followed the 2025 ADA guideline for scope. This guideline was developed...` | `GUIDELINE` | `""` | FAIL |
| g | `In developing this guideline, we followed the 2025 ADA guideline. This guideline provides...` | `GUIDELINE` | `""` | FAIL |
| h | `This consensus statement provides guidance...` | `GUIDELINE` | `GUIDELINE` | PASS |
| i | `This systematic review and meta-analysis pools...` | `SR_MA` | `SR_MA` | PASS |
| j | `Following PRISMA 2020, study selection and data extraction...` | `SR_MA` | `SR_MA` | PASS |
| k | `We followed PRISMA reporting principles generally but this is a single trial.` | `""` | `""` | PASS |
| l | Meta tag says Systematic Review; body says guideline | `SR_MA` | `SR_MA` | PASS |
| m | Publisher header says Case Report; body says guideline | `CASE_REPORT` | `CASE_REPORT` | PASS |

**Over-Demotion Risk**

Two over-demotion risks are real. The 300-character guard treats any prior "followed the 2025 ADA guideline" style phrase as dispositive external anaphora, even when the article is self-declarative as a new guideline. A legitimate guideline can naturally say it followed an older guideline or used it during development before declaring "This guideline provides..." or "This guideline was developed...". The current guard skips those matches and returns empty.

This risk is not theoretical: direct probes f and g both returned `""` despite self-declarative guideline language.

**PRISMA Recheck**

PRISMA contextual behavior remains intact in the direct probes and existing tests. `Following PRISMA 2020` plus `study selection`/`data extraction` returns `SR_MA`. PRISMA without search/selection/extraction/flow context returns empty.

The contextual patterns at lines 240-242 still enforce PRISMA co-occurrence with search/selection/extraction/flow diagram within 40 chars in either order.

**Consensus/SR-MA Collateral Check**

Consensus statement behavior was not collaterally damaged in the checked body path: `This consensus statement provides guidance...` returns `GUIDELINE`.

SR/MA behavior was also not collaterally damaged: `This systematic review and meta-analysis pools...` returns `SR_MA`, and the existing SR/MA tests still pass.

**Priority Recheck**

Priority ordering inside `_detect_article_type_from_body` is still metadata > publisher header > contextual body:

1. Meta/JSON-LD tags are evaluated first at lines 386-392.
2. Publisher article-type headers are evaluated second at lines 394-402.
3. Contextual body patterns are evaluated only after that at lines 404-446.

Direct probes confirmed this. A Systematic Review meta tag beats a guideline body and returns `SR_MA`. A Case Report publisher header beats a guideline body and returns `CASE_REPORT`.

**Test Runs**

Command:

```powershell
python -m pytest -q tests/polaris_graph/test_m17_body_article_type.py
```

Result: 58 passed, 1 warning. The warning was a pytest cache write warning under `C:\POLARIS\.pytest_cache`, not a test failure.

The test file contains 58 tests. The five M-17e tests cover:

1. `summarizes` no longer being accepted as a bare `this guideline` verb, while fully qualified `This clinical practice guideline...` still flags through the anchored bare CPG pattern.
2. `describes` no longer flagging for bare `this guideline`.
3. `updates?` positive recall.
4. External guideline citation followed by anaphoric `This guideline summarizes...`.
5. Object-position `followed this clinical practice guideline...`.
6. NICE citation followed by `This guideline offers...`.

That covers the pass-6 failures plus the updates recall and ambiguous-verb inversions, but it does not cover the remaining "Previous guidelines recommend X. This guideline updates those." false positive or the legitimate self-declarative over-demotion cases.

**Required Fix**

Fix both sides before promotion:

1. Add an anaphoric marker for prior-guidelines recommendation framing, or otherwise handle `Previous/Current guidelines recommend... This guideline updates those` as external/anaphoric when the article is a primary paper.
2. Refine the 300-character guard so it does not suppress explicit self-declarative forms such as `In developing this guideline, we followed the 2025 ADA guideline. This guideline provides...` or `This guideline was developed...`.
3. Add tests for the three failing adversarial cases above, including at least one true guideline that cites/follows a prior guideline during development before self-declaring.
