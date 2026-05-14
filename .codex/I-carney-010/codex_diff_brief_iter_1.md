HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-010 diff iter 1 — Serper stays: revert search-provider-deferred edits

Brief review AND diff review combined (brief authored alongside the diff).
The full brief is in this diff at `.codex/I-carney-010/brief.md`.

## Summary

GH#490. Revert the I-carney-008 edits that deferred the web search provider
and removed `google.serper.dev` from the egress allowlist. User directive
2026-05-13: Serper stays — search queries carry no confidential content;
the sovereignty constraint protects the LLM inference path + report-data
jurisdiction. Config + docs ONLY — zero `src/` change (Serper retrieval
code was never removed).

## Diff

`.codex/I-carney-010/codex_diff.patch` — 159 LOC across 5 files (all
config/docs), canonical-diff-sha256 trailer included:
- `config/egress_allowlist.txt` — re-add `google.serper.dev`
- `infra/vexxhost/.env.example` — `SERPER_API_KEY` as active backend
- `docs/transparency.md` §4 — Serper disclosed plainly
- `docs/carney_demo_runbook.md` — stack table + prereqs
- `infra/vexxhost/README.md` — search row + sovereignty audit table

## Verification done

- Grep confirmed zero stale `GH#487` / `DEFERRED` / deferral references
  across the 5 files (one intentional Mojeek/Qwant/Ecosia mention remains
  in transparency.md §4 as reviewer-option disclosure context).
- `src/polaris_graph/retrieval/*` Serper code intact + untouched.
- `transparency.py` reads the allowlist line-by-line; `google.serper.dev`
  is a valid plain entry — no code/schema impact.
- `tests/polaris_v6/api/test_transparency.py` uses a tmp fixture, not the
  real allowlist file — no test change needed.

## Direct questions (also in brief.md)

1. Is the `/transparency` §4 disclosure language honest + complete?
2. Should the search provider's jurisdiction be a machine-readable
   `/transparency` JSON field? (That'd be a `src/` change — flag P2/follow-up
   if warranted, don't block.)
3. Anything else blocking APPROVE?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
