## §0 — HARD ITERATION CAP

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings.
- "Don't pick bone from egg".
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## §1 — Issue + Acceptance

**GH#358 — I-bug-104: archive failed prompt rewrite experiment.**

Issue body: "Hypothesis: 100-line prompt rewrite emphasizing per-decimal extraction would improve verified-rate. Empirical result: catastrophic regression (verified-rate dropped 15pp). Reverted. Acceptance: capture in docs/experiments/i_bug_104_failed.md and close."

**Acceptance:** new `docs/experiments/i_bug_104_failed.md`. No production code change.

## §2 — Proposed Change

| File | Δ |
|---|---|
| `docs/experiments/i_bug_104_failed.md` | NEW (+~55 lines) |

Hypothesis (per-decimal discipline) + setup + result table (verified-rate −15pp, drop-reason shift no_provenance_token → dominant) + lesson (over-strict prompts shift failure modes laterally) + follow-ups (I-bug-101 FPR audit, I-bug-105/108 already shipped, Path A bakeoff).

## §3 — Files clean

- `src/polaris_graph/generator/multi_section_generator.py` UNCHANGED. The hypothesis was tested in a throwaway branch that never PR'd.
- Pure markdown documentation.

## §4 — Test Strategy

N/A (documentation-only).

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

Expected APPROVE iter 1.
