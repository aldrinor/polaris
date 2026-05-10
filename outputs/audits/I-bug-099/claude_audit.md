# I-bug-099 Claude architect audit

## Issue
GH#353 — Extract entailment-judge helpers to shared module.

## Codex review trajectory
- Brief iter-1: REQUEST_CHANGES, 1 P1 (production verifier import path would break test patch propagation), 1 P2 (UNKNOWN_MODE_WARNED rebind issue).
- Brief iter-2: APPROVE, 0 P0/P1, 2 P2 cosmetic, `accept_remaining`. Path scoped: judge class + telemetry → llm/entailment_judge.py; mode resolver + WARNED set → STAY in strict_verify.py; provenance_generator.py UNCHANGED.
- Diff iter-1: APPROVE, 0 P0/P1/P2, `accept_remaining`. Codex independently verified `pytest` 66/66 pass.

Total iters: 3 (within 5-cap). Goal of 1-2 was achieved on diff after the iter-2 brief refinement.

## Architectural review

**Single-import-path goal.** Achieved at the canonical-definition level: future call sites can `from polaris_graph.llm.entailment_judge import _EntailmentJudge, _get_judge, get_judge_telemetry, …` without going through generator2/. Mode resolver is generator2-internal anyway and rarely used by external code.

**Backwards compat with existing test pattern.** Re-exports preserve the `monkeypatch.setattr(strict_verify, …)` pattern. 66/66 tests pass without modification.

**Off-mode behavior.** Eager-import of `polaris_graph.llm` triggers `OpenRouterClient` class import via package __init__.py, but this is pure-Python class definition — no API call, no env-var read at import time. Off-mode runtime path (`_entailment_mode() == "off"` short-circuit in `verify_sentence`) is unchanged. P2-1 acknowledged; hardening `llm/__init__.py` to lazy-load is filed as I-bug-102.

**Family segregation invariant (§9.1.1).** Preserved: `_EntailmentJudge.__init__` still calls `check_family_segregation(evaluator_model=...)` at construction. Two-family invariant unchanged.

## Tests
66/66 entailment-judge tests pass on the post-refactor diff (verified twice: once by me, once by Codex).

## Verdict
**SHIP.**
