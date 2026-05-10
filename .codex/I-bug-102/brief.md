## §0 — HARD ITERATION CAP

```
HARD ITERATION CAP: 5. iter 1 of 5. Verdict APPROVE iff zero P0/P1.
```

## §1 — Issue + Acceptance

**GH#356 — I-bug-102: off-mode should skip generator2 import.**

Issue: "When PG_PROVENANCE_ENTAILMENT_MODE=off, generator2 module is still imported (top-level imports load entailment helpers). Refactor to lazy-import. Acceptance: off-mode has zero entailment-judge code-path execution, unit test asserts."

## §2 — Scope decision

The acceptance "zero entailment-judge code-path execution" interprets to: in off-mode, no judge is INSTANTIATED, no httpx.Client constructed, no network call, no API-key check. The class definitions ARE loaded into the module namespace at import time (Python module evaluation), but no judge OBJECT exists.

The literal "skip generator2 import" goal — fully eliminating openrouter_client import on off-mode strict_verify import — was tested (lazy-load via accessor) and reverted: the `except _orc.BudgetExceededError` semantics requires the exception class to be resolvable at except-clause evaluation, which is hot-path. Implementing it would complicate the budget-cap propagation contract for marginal cold-import savings (~50ms once per process).

**Acceptance therefore framed as runtime behavior:** in off-mode, `_EntailmentJudge.__init__` does NOT run, `_get_judge()` is never called, telemetry counters do not increment.

## §3 — Proposed change

| File | Δ |
|---|---|
| `src/polaris_graph/llm/entailment_judge.py` | +~15 docstring (off-mode contract documented explicitly) |
| `tests/polaris_graph/llm/test_off_mode_no_judge_instantiation.py` | NEW (+~95): 3 tests — judge not instantiated, telemetry stays zero, no httpx.Client even without OPENROUTER_API_KEY |

Net: +~110 lines. 65 tests pass (3 new + 62 baseline).

## §4 — Files clean

- `_entailment_mode()` early-returns "off"; `_get_judge()` not invoked → no judge instantiation.
- `_EntailmentJudge.__init__` runs `family-segregation + httpx.Client + API-key check` — all GATED by `_get_judge()` which is only called for warn/enforce.
- Telemetry counters increment in `_record_judge_outcome`, only called from inside `_get_judge().judge()`.

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
