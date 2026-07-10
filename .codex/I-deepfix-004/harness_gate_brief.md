You are the CODEX REVIEW GATE for the branch `bot/I-harness-001-fetch-cited-content`
in the POLARIS repo (`C:/POLARIS`). Render a machine-parseable verdict.

================================================================================
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as
  P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd on remaining
  non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it
  now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Compressed restatement (binding): [HARD ITERATION CAP 5. Front-load ALL findings.
Reserve P0/P1 for real execution risks. APPROVE iff zero P0 AND zero P1.]
================================================================================


## 1. WHAT WAS SUPPOSED TO BE BUILT (intended spec — the 5-line summary)

The deliverable is a **parallel fetch cited-content test harness** per the design doc
`.codex/I-deepfix-004/fable_fetch_harness_design.md`. Its defining properties:
1. **22 real, verified cases** (good controls, combined-PDF page-anchor, no-anchor
   multi-work containers, hub/error shells, paywalled, OA wrong-work swap).
2. A **harness-owned oracle that does NOT import the tested production predicate**
   (I-wire-013 independence): the oracle re-implements `squash` / `contains_any` /
   `contains_none` / `front_matter_structural` / collision checks itself, so it can
   never rubber-stamp the production detector it is meant to catch.
3. **Flag-gate refusal that cannot fake a pass**: at startup the harness asserts every
   required flag/key is ON (pdf_cited_work_slice, span_cited_work_screen,
   cited_span_shell_detect, PG_REFETCH_FULL_BODY, ZYTE_API_KEY, PG_DISABLE_ACCESS_BYPASS
   != 1); any off ⇒ print "RESULT VOID — FIX FLAGS OFF", write NO pass, exit 2.
4. **Single-URL isolation**: `--only <case|ev>`, `--url <u> --expect <cls> --contains
   <stem>`, `--rerun-failures`, ThreadPoolExecutor fan-out with per-case timeout.

Per the design doc the harness lives in THREE new files:
- `scripts/fetch_cited_content_harness.py`  (~300 LOC, read-only imports from src/)
- `config/fetch_harness_cases.yaml`          (the 22 labeled cases — data)
- `tests/polaris_graph/test_fetch_harness_oracle.py`  (OFFLINE oracle unit tests, no net)


## 2. WHAT IS ACTUALLY ON THE BRANCH (verify this yourself)

I checked the tree three ways and report it to you so you VERIFY rather than discover.
Please independently confirm with `git ls-files` and `ls`:

- `git ls-files scripts/fetch_cited_content_harness.py` → **EMPTY (file does not exist)**
- `git ls-files config/fetch_harness_cases.yaml`        → **EMPTY (file does not exist)**
- `git ls-files tests/polaris_graph/test_fetch_harness_oracle.py` → **EMPTY (does not exist)**
- `git log --all --oneline -- <those 3 paths>`          → **EMPTY (never committed anywhere)**

**NONE of the three harness files exists** — not committed on this branch, not in the
working tree, not untracked, not on any other branch or worktree.

What the branch DOES contain (5 commits `2e7de779..2ab1c8c4` on top of the I-deepfix-003
tip `63ea46f0`) is the **I-deepfix-004 PR-1 detector code** — the production fix the
harness was meant to TEST, plus a conventional offline pytest for it:

```
 scripts/run_honest_sweep_r3.py                     |   56 +
 src/polaris_graph/retrieval/live_retriever.py      |  127 +-   (step A full-body refetch + A15 wiring)
 src/polaris_graph/retrieval/resume_refetch.py      |   15 +-   (wrong_content_span recover clear)
 src/polaris_graph/retrieval/shell_detector.py      |  231 +    (is_issue_front_matter, identical_span_collision)
 src/tools/access_bypass.py                         |  345 +-   (step B PDF page-slice + DOI redirect anchor)
 tests/fixtures/i_deepfix_004/real_masthead_spans.json |  76 +  (real banked spans, LAW II provenance)
 tests/polaris_graph/test_i_deepfix_004_frontmatter.py | 619 +  (offline unit tests, 24 cases)
```

The complete diff of this branch vs the I-deepfix-003 tip is saved at
`.codex/I-deepfix-004/harness_review.diff` (1703 lines) — **read that file** for the full
code. The design doc is `.codex/I-deepfix-004/fable_fetch_harness_design.md` — **read it**
for the full intended spec.


## 3. THE KEY CORRECTNESS RISKS TO ADJUDICATE

Evaluate each against the DESIGN INTENT and the ACTUAL branch state. Be precise; do not
fabricate a defect where the artifact is simply absent.

(a) **Harness existence (the gate question).** Does the fetch harness described in the
    design doc actually exist on this branch? The deliverable named in the task is the
    HARNESS (22 cases, independent oracle, flag-gate refusal, single-URL isolation) — all
    HARNESS properties, not detector properties. If the harness is absent, there is no
    22-case run, no flag-gate, no single-URL isolation, and no independent oracle to
    verify. Judge whether that absence blocks acceptance of "the fetch harness."

(b) **Oracle independence.** The design requires the HARNESS's OWN checking oracle to be
    an independent re-implementation that does NOT import the production predicate
    (`shell_detector.is_issue_front_matter`), so it cannot rubber-stamp the detector.
    NOTE precisely: the offline test that DOES exist, `test_i_deepfix_004_frontmatter.py`,
    imports `shell_detector` and calls `is_issue_front_matter` directly — but that is a
    NORMAL unit test (a unit test is supposed to import the unit under test); it is NOT
    the design's independent live-harness oracle and must NOT be scored as an
    "independence violation." The correct reading is that the independent oracle is
    ABSENT (there is no `fetch_cited_content_harness.py`), i.e. independence is
    unverifiable / N/A because the artifact does not exist. Confirm or correct this
    reading.

(c) **Precision-first — the 4 good controls must never FAIL.** In the design the four
    good controls (good_arxiv_html, good_feds_note, good_oa_pdf_nber, good_oecd_fullreport)
    must always verdict PASS or the harness itself is broken. Since the harness is absent
    there is no run to check; but you CAN check the underlying detector the harness would
    exercise: does `shell_detector.is_issue_front_matter` (in the diff) stay precision-first
    / fail-open so a real article head, an ISSN-in-prose span, and an incidental "contents"
    mention are NOT flagged? Judge from the code + `test_i_deepfix_004_frontmatter.py`.

(d) **Flag-gate cannot fake a pass.** The design's flag-gate (assert all flags ON, else
    "RESULT VOID", write no pass, exit 2) lives in the absent harness script, so it does
    not exist. Confirm it is absent.

(e) **No network in the oracle unit tests.** The design's offline oracle unit tests
    (`test_fetch_harness_oracle.py`) are absent. The test that exists,
    `test_i_deepfix_004_frontmatter.py`, is offline (mocks aiohttp, builds fitz PDFs in
    memory, reads a committed fixture) — confirm it makes no live network call, as a
    secondary check on the code that IS present.


## 4. YOUR TASK

1. Independently VERIFY §2 (run `git ls-files` on the three harness paths; read the design
   doc and `.codex/I-deepfix-004/harness_review.diff`).
2. Adjudicate §3 (a)–(e) honestly. The PRIMARY gate is (a): is the fetch-harness
   deliverable present and correct? Absence of the deliverable named in the task is an
   execution-blocking defect. Do NOT invent defects in the detector code to reach a
   verdict, and do NOT downgrade the absence just because solid detector code happens to
   be on the branch — the detector code is the thing the harness was meant to test, not
   the harness.
3. If (and only if) you conclude the harness genuinely exists and is correct on this
   branch, APPROVE.

Return EXACTLY this schema as the LAST lines of your output (the CI/gate parser reads the
LAST `verdict:` line):

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
