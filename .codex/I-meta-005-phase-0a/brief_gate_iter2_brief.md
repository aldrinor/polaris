HARD ITERATION CAP: 5. iter 2 of 5. Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex BRIEF gate iter 2 — Phase 0a, the 4 iter-1 findings addressed

iter 1 = REQUEST_CHANGES (0 P0; 2 P1: missing input-signal bridge + wrong OpenAlex retrieval contract; 2 P2:
incomplete consumer map + institution-type vocab). All addressed in the ADDENDUM at the end of
.codex/I-meta-005-phase-0a/brief.md (READ the addendum C1-C4). Output §8.3.9 YAML verdict FIRST.

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Confirm each iter-1 finding is closed:
- C1 (was P1): additive AuthoritySignals payload wired end-to-end (openalex_client._parse_work → OpenAlexWork →
  live_retriever:1789-1811 → ClassificationSignals additive → score_source_authority), LOW-confidence when
  absent/partial, fixtures capture the payload. Is the bridge now fully specified + backward-compatible?
- C2 (was P1): /works root-only select fieldset + SEPARATE /sources/{id} fetch keyed by primary_location.source.id
  for summary_stats/apc_prices/is_core/is_in_doaj + a real versioned SQLite migration (not CREATE IF NOT EXISTS).
  Is the retrieval+cache contract now correct?
- C3 (was P2): honest_pipeline.py:60,167 added to consumer map (legacy-only reads, wedge-safe). Complete now?
- C4 (was P2): institution-type map handles `archive` + `funder` explicitly. Done?

APPROVE iff all four are correctly closed and no NEW P0/P1. This is the build contract — on APPROVE, build begins.
