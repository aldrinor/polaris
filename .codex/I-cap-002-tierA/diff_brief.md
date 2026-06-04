HARD ITERATION CAP: 5 per document. This is iter 1 of 5. Front-load ALL findings; reserve P0/P1 for real execution risks; APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Output schema (return EXACTLY this, no prose verdict):
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

---

# DIFF gate — I-cap-001 (#1059) Part A: 3-cap Tier-A un-throttle

DIFF gate against the brief (`.codex/I-cap-002-tierA/brief.md`, brief-gate APPROVE iter-1). Patch:
`.codex/I-cap-002-tierA/codex_diff.patch` (branch `bot/I-cap-002-tierA-caps` on `bot/I-cap-002-nli`).
+15 LOC, 2 files.

## The diff
1. `query_decomposer.py`: `+import os`; `DEFAULT_MAX_SUBQUERIES = 6` -> `int(os.getenv("PG_MAX_SUBQUERIES","15"))`.
2. `run_honest_sweep_r3.py` (the `generate_multi_section_report(...)` call): `PG_SECTION_MAX_TOKENS`
   fallback `2400` -> `5000`; ADD `limitations_max_tokens=int(os.environ.get("PG_LIMITATIONS_MAX_TOKENS","1500"))`.

## Red-team checklist — confirm
- **No-downgrade default:** each cap defaults to SOTA (15 / 5000 / 1500); a run with NO env set is at full
  capability (operator's binding no-downgrade directive).
- **LAW VI env-overridable:** each reads its `PG_*` env (verified: default 15, `PG_MAX_SUBQUERIES=9` -> 9).
- **No signature break:** `generate_multi_section_report` accepts `limitations_max_tokens` (param exists);
  the new kwarg is valid; decomposer 24/24 green; py_compile OK.
- **Faithfulness:** these only widen query breadth + raise token budgets; strict_verify + the 4-role seam
  still drop any unsupported sentence (unverifiable extra prose is dropped, not shipped). Any way raising
  these caps could WEAKEN verification? (It cannot — verification runs after generation regardless.)
- **Magic numbers:** only the operator-approved 15/5000/1500; no other constants introduced.
- Is `int(os.getenv(...))` at module-import time (query_decomposer) acceptable, or do you want it read at
  call time? (Module-level matches the existing pattern; the env is set before import in the run.)

## Smoke evidence
- `py_compile` both files OK; decomposer tests 24/24 pass.
- `DEFAULT_MAX_SUBQUERIES == 15` (no env), `== 9` with `PG_MAX_SUBQUERIES=9`.
- call-site greps confirm `"5000"` fallback + `limitations_max_tokens=...1500`.

## Acceptance
Zero P0/P1. The change is a bounded, env-overridable cap un-throttle with SOTA defaults; faithfulness path
untouched. Any residual tuning concern is P2.
