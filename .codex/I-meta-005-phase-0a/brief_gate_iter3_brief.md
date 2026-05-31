HARD ITERATION CAP: 5. iter 3 of 5. Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex BRIEF gate iter 3 — Phase 0a, the live-path bridge (C5) added

iter 2 = REQUEST_CHANGES, one remaining P1: C1/C2 routed AuthoritySignals through tools/openalex_client, but the
PRODUCTION path is live_retriever._openalex_enrich (:573/:670/:1751/:1789) which does NOT call that client. Now
addressed in ADDENDUM C5 (READ it). C3/C4 already closed iter 2. Output §8.3.9 YAML verdict FIRST.

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Confirm C5 closes the live-path gap:
C5 mandates the new contract land IN live_retriever._openalex_enrich (or a shared versioned cached client it
delegates to): root /works select + separate /sources/{id} fetch by primary_location.source.id + versioned cache
migration + additive AuthoritySignals payload into the enrich dict carried at :1751->:1789 into ClassificationSignals
+ LOW-confidence on missing; frozen S2 fixtures capture the live-path payload. tools/openalex_client kept consistent
but the production wedge path is the live one.

APPROVE iff C5 closes the primary-path bridge and nothing new surfaces. This is the build contract; build begins on APPROVE.
