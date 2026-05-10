## §0 — HARD ITERATION CAP

```
HARD ITERATION CAP: 5. iter 1 of 5. Verdict APPROVE iff zero P0/P1.
```

## §1 — Issue + Acceptance

**GH#361 — I-bug-109: synthesis [N] hallucination root-cause investigation.**

Acceptance: `docs/investigation/i_bug_109_root_cause.md` with finding + fix recommendation. The runtime guardrail (PR #351) handles the symptom. This investigation document captures the four likely root-cause hypotheses (H1-H4), tests for each, and recommends I-bug-110 telemetry as the empirical isolation path.

## §2 — Proposed change

| File | Δ |
|---|---|
| `docs/investigation/i_bug_109_root_cause.md` | NEW (+~100 lines) |

No code change. Pure investigation document.

## §3 — Hypotheses

- H1 (HIGH): verified-prose `[N]`-shaped numerics confuse synthesis tokenizer
- H2 (MED): biblio-size mismatch in prompt
- H3 (LOW): context-truncation artifact
- H4 (MED): "concrete evidence" framing ambiguous

Each hypothesis has a concrete test. The recommended next step uses I-bug-110 telemetry (per-run scrub counts) to correlate against evidence_pool_size / prompt_token_count over 5-10 sweeps to isolate H1 vs H3.

## §4 — Files clean

- Production code UNCHANGED. The runtime guardrail at `analyst_synthesis.py:287` (already shipped in I-bug-108 PR #351) continues to handle the symptom.
- No tests required for a pure investigation document.

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
