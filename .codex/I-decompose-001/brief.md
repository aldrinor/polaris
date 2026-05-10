## §0 — HARD ITERATION CAP

```
HARD ITERATION CAP: 5. iter 1 of 5. Verdict APPROVE iff zero P0/P1.
```

## §1 — Issue + Acceptance

**GH#366 — I-decompose-001: Path G multi-question decomposition.**

Issue body: "Codex strategic review path G: decompose Carney complex questions into N sub-questions, run each through pipeline, synthesize cross-question. Acceptance: src/polaris_graph/decomposer.py + integration test on 'tirzepatide vs semaglutide T2DM' (decomposes to efficacy / safety / cost / availability)."

## §2 — Scope decision

This PR provides the **DECOMPOSER** (deterministic heuristic). Retrieval orchestration across N sub-questions and synthesis aggregation are downstream concerns to be wired separately into graph_v4 — out of scope here.

The decomposer is heuristic (regex-based aspect-list parser), not LLM-driven, in this iter. An LLM-driven decomposer is a follow-up that would invoke openrouter_client. Heuristic-first is the right path because:
1. Fast + deterministic → cheap to test
2. The acceptance example ("considering efficacy, safety, cost, and availability") is exactly the aspect-list shape the heuristic detects
3. LLM-driven decomposition can be A/B'd against the heuristic later

## §3 — Proposed change

| File | Δ |
|---|---|
| `src/polaris_graph/decomposer.py` | NEW (+~125 lines): `DecomposedQuestion` frozen dataclass + `decompose()` entry; aspect markers (considering / including / with respect to / across / in terms of / regarding); regex parses tail into per-aspect list; max_sub cap with 'other considerations' bucket |
| `tests/polaris_graph/test_decomposer.py` | NEW (+~115 lines): 10 tests covering acceptance example exactly + simple-pass-through + multi-aspect + cap-with-other-bucket + 'in terms of' + 'across' + empty + immutability + double-?-prevention + short-aspect filtering |

Net: +~240 lines.

## §4 — Acceptance verification

`pytest tests/polaris_graph/test_decomposer.py -x -q` → 10/10 in 5.13s.

`test_acceptance_canonical_example` exercises issue body example: "Compare tirzepatide vs semaglutide in T2DM, considering efficacy, safety, cost, and availability" → 4 sub-questions [efficacy, safety, cost, availability].

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
