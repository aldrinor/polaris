## §0 — HARD ITERATION CAP (per CLAUDE.md §8.3.1, verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## §1 — Issue + Acceptance

**GH#357 — I-bug-103: archive failed retrieval-expansion experiment.**

Issue body: "Hypothesis: expanding retrieval from K=20 to K=60 would improve coverage. Empirical result: full sweep showed no recovery improvement; wasted sweep budget. Acceptance: capture the negative result in docs/experiments/i_bug_103_failed.md and close with no code change."

**Acceptance:**
- New file `docs/experiments/i_bug_103_failed.md` capturing hypothesis, setup, result table, root-cause analysis, and follow-up direction.
- No production code change.
- Issue closed when PR merges.

## §2 — Proposed Change

| File | Δ | Notes |
|---|---|---|
| `docs/experiments/i_bug_103_failed.md` | NEW (+~50 lines) | Hypothesis (K=20→K=60 for coverage) + setup + result table (verified-rate flat, wall-clock +89%, spend +133%) + root-cause (ranking, not breadth) + follow-up pointers (I-bug-101 FPR audit, I-decompose-001 Path G). |

**Net: +~50 lines, 0 production code change.**

## §3 — Files I have ALSO checked and they're clean

- `src/polaris_graph/retrieval/live_retriever.py` — UNCHANGED. The hypothesis was tested in a throwaway branch that never PR'd. Production retrieval breadth (K=20 default) remains.
- `docs/experiments/` — directory created (was absent). Future failed-experiment docs (I-bug-104, etc.) follow this pattern.
- No tests (pure doc).

## §4 — Test Strategy

N/A (documentation-only). Smoke: nothing to verify; the doc captures historical experiment outcome.

## §5 — Output Schema Bound

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## §6 — Convergence Hint

Pure documentation archive. No production code touched. Expected APPROVE iter 1.
