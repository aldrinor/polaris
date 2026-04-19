---
verdict: BLOCKED-ON-ISSUE
pass: full_scale_4_m17b_code_audit
commit: 0f2674a
body_inspector_now_sound: false
pass3_false_positives_resolved: 6
pass3_over_demotions_resolved: 3
new_adversarial_cases_tested: 3
adversarial_results: "requested a='', b='', c=''; additional audit probes found prior Cochrane review -> SR_MA, this guideline -> GUIDELINE, consensus statement from -> GUIDELINE, this meta-analysis by Smith -> SR_MA"
tests_sound: mixed
rationale: |
  I read _detect_article_type_from_body and its regex tables end-to-end; priority ordering is implemented as metadata/JSON-LD first, publisher headers second, and body patterns last. The exact pass-3 false-positive tests and classifier-level regression pass, and the three requested new adversarial bodies all returned empty strings. However, several body regexes are still not sufficiently context-bound: "cochrane (systematic )?review", "this ... meta-analysis", "this ... guideline", and "consensus statement from" can fire on ordinary background citations or methods references. The PRISMA .{0,40} patterns are bounded and did not show catastrophic-backtracking behavior in stress probes. The test file is realistic and covers positives/negatives broadly, but it misses these citation-shaped negative cases, so M-17b should not proceed to max-scale until those guards are tightened.
---

**Findings**

1. **BLOCKING: SR/MA body patterns still accept citation-shaped lone mentions.**
   In [live_retriever.py](C:/POLARIS/src/polaris_graph/retrieval/live_retriever.py:231), `this\s+(systematic review...|meta-analysis)` fires on background text such as "This meta-analysis by Smith et al. shaped the endpoint hierarchy" in a primary randomized trial. In [live_retriever.py](C:/POLARIS/src/polaris_graph/retrieval/live_retriever.py:237), `cochrane (systematic )?review` fires on "A Cochrane review found..." in a primary trial abstract. These are still pass-3-style prior-evidence citations, just with slightly different wording.

   Verified outputs:
   `prior_cochrane_review_citation -> 'SR_MA'`
   `this_meta_analysis_citation -> 'SR_MA'`

   Suggested fix: remove the standalone Cochrane pattern or require explicit current-article declaration such as "this Cochrane review" plus no citation-byline wording, and tighten `this systematic review/meta-analysis` to require a self-descriptive predicate ("aims", "evaluates", "examines", "was conducted") rather than allowing "this meta-analysis by X".

2. **BLOCKING: guideline body patterns still accept background/methods references.**
   In [live_retriever.py](C:/POLARIS/src/polaris_graph/retrieval/live_retriever.py:258), `this\s+(clinical\s+practice\s+)?guideline` allows bare "this guideline" without declarative article framing. In [live_retriever.py](C:/POLARIS/src/polaris_graph/retrieval/live_retriever.py:261), `consensus\s+statement\s+from\s+(the\s+)?` fires on a primary trial that selected endpoints according to an external consensus statement.

   Verified outputs:
   `this_guideline_reference -> 'GUIDELINE'`
   `consensus_statement_reference -> 'GUIDELINE'`

   Suggested fix: require "this clinical practice guideline" exactly, or require verbs that declare the fetched article's purpose ("provides", "recommends", "was developed", "we developed"). For consensus, require "this consensus statement" or "consensus statement ... provides/recommends/was developed", not "according to a consensus statement from".

3. **Requested adversarial probes passed.**
   I constructed the three requested bodies outside the test file and ran `_detect_article_type_from_body` directly:
   `primary trial discussion prior systematic review -> ''`
   `indirect comparison with adapted systematic review methods -> ''`
   `case series with "We describe 5 cases" -> ''`

4. **PRISMA backtracking risk is low.**
   The PRISMA patterns in [live_retriever.py](C:/POLARIS/src/polaris_graph/retrieval/live_retriever.py:234) and [live_retriever.py](C:/POLARIS/src/polaris_graph/retrieval/live_retriever.py:235) use fixed bounded wildcards (`.{0,40}`) over the already bounded lead text in detector use. Stress probes with 500k characters and many repeated near-misses completed quickly; this is not a catastrophic-backtracking shape.

5. **Priority ordering is correct.**
   Direct conflict probes confirmed metadata beats headers and body patterns, and headers beat body patterns:
   `meta Case Report + header Meta-Analysis + body SR -> 'CASE_REPORT'`
   `header Case Report + body SR -> 'CASE_REPORT'`
   `reverse-order meta Guideline + body SR -> 'GUIDELINE'`

**Test Review**

`python -m pytest tests\polaris_graph\test_m17_body_article_type.py -q` collected and passed all 38 tests. The file covers metadata, publisher headers, SR/MA, case report, guideline, perspective, exact pass-3 negatives, bounded scanning, and classifier integration. I mark it `mixed` because it does not include the citation-shaped negatives above, which are realistic and still fail.
