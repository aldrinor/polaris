# THIN scenario: seed evidence vs. question coverage

File: /home/polaris/wt/outline_agent/acceptance_outline_agent.py

## What the THIN seed injects

The THIN seed is NOT a hardcoded, hand-curated evidence set scoped to "efficacy".
It is the raw output of a **live retrieval call** seeded by a single query string:

```
62  seed_rows = _bootstrap_seed(
63      "tirzepatide 15mg HbA1c reduction efficacy SURPASS trial results", max_serper=6,
64  )
```

`_bootstrap_seed` (lines 46-55) just runs `run_live_retrieval(research_question=query, max_serper=6, fetch_cap=10, anchor_seed=True)` and returns `result.evidence_rows`. So the "seed evidence" is whatever the live web/Serper pipeline returns for that efficacy-scoped query on the day the test runs.

Guard (lines 65-67):
```
65  if len(seed_rows) < 3:
66      raise RuntimeError(f"bootstrap seed too thin to test with ({len(seed_rows)} rows) — "
67                          "live retrieval may be degraded; not faking a pass")
```

## The QUESTION (asks for TWO facets)

```
69  question = (
70      "What is the HbA1c-lowering efficacy of tirzepatide 15mg AND what is known about its "
71      "long-term cardiovascular safety (major adverse cardiovascular events, SURMOUNT-MMO "
72      "or equivalent outcome trial data)?"
73  )
```

Then the seed rows are handed to the agent verbatim as the starting evidence pool:
```
74  evidence = list(seed_rows)
75  ev_before = {r.get("evidence_id") for r in evidence if isinstance(r, dict)}
```

The test's stated intent (docstring, lines 5-9): seed covers ONLY efficacy; the question
also asks about long-term CV safety; acceptance = checklist names the gap and
`search_more_evidence` fires a real scoped query.

## Does the seed genuinely cover ONLY efficacy? — NO GUARANTEE

The premise ("seed covers only efficacy, so a real uncovered CV-safety gap exists") is
**asserted by construction of the query string, not verified anywhere in the test**:

1. The seed query is efficacy/SURPASS-scoped, but it is a **live, non-deterministic**
   web retrieval. SURPASS trial coverage and general tirzepatide pages routinely also
   discuss cardiovascular outcomes/MACE. Nothing filters CV-safety content OUT of the
   returned rows. So on any given run the seed may already contain CV-safety evidence,
   in which case the "uncovered gap" the test expects does NOT exist.

2. There is **no assertion** that the seed lacks CV-safety coverage. The guard at
   line 65 only checks `len(seed_rows) < 3` (row COUNT), never row CONTENT. Nothing
   inspects the rows to confirm the CV-safety facet is actually absent.

3. Consequently the test's expected behavior (checklist flags a CV-safety gap →
   `search_more_evidence` fires → outline mutates) is contingent on a gap that the
   harness never establishes. If the live seed already covers CV safety, a correct
   agent would legitimately fire zero searches and the "THIN" acceptance would fail —
   not because of a real bug, but because the premise wasn't actually met that run.

## Conclusion

- Seed injected: live-retrieved rows from the efficacy query
  "tirzepatide 15mg HbA1c reduction efficacy SURPASS trial results" (line 63).
- Question asks two facets: efficacy AND long-term CV safety/MACE (lines 69-73).
- The intended gap (CV safety uncovered) is only assumed from the query wording. The
  test premise is **NOT reliably valid**: because the seed is a live, unfiltered
  retrieval and nothing asserts the CV-safety facet is absent, the "real uncovered gap"
  can silently fail to exist, making THIN non-deterministic / potentially self-defeating.
