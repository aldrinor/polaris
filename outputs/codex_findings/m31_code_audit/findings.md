# M-31 code audit

VERDICT: READY

## Blockers (only if grounded in actual log evidence)
- none

## Mediums
- none

## Lows / nits
- none

## Notes
M-31 directly addresses the observed V19/V20 failure mode. `scripts/run_honest_sweep_r3.py` now passes `outline_max_tokens=2500`, matching the in-module default on `generate_multi_section_report`. `_call_outline` reuses that same max token budget for both the initial outline call and the single retry, so the bump covers both failing calls seen in V19/V20.

The downstream sweep still passes `section_max_tokens=1200`, while the module default is 2400. That is not a blocker for M-31: the outline planner and section writers use separate budgets, and the observed catastrophic failure was outline JSON truncation at 800 output tokens before section generation. V19/V20 section calls proceeded after fallback and used the 1200 section cap as before.

The lenient regex is appropriately narrow for this fix. It only runs after strict `json.loads(payload)` fails, so it cannot alter any well-formed JSON fast path. The transformation removes only commas immediately before `]` or `}`. It does not synthesize missing commas between adjacent JSON values or objects, so missing-comma truncation still returns `json_decode_error`; the added truncation test verifies this behavior.

The static guard test reads `scripts/run_honest_sweep_r3.py` source with `path.read_text(encoding="utf-8")`, extracts numeric `outline_max_tokens = <int>` assignments, and fails if any are below 2500. If the sweep caller is changed back to `outline_max_tokens=800`, this test fails.

The diff is domain-agnostic in behavior: the functional changes are a JSON syntax cleanup and a token-budget config change. The clinical/regulatory references are comments/test rationale tied to the incident, not branching logic or domain-specific parsing.

Actual V19/V20 log evidence found only the same 800-token outline decode pattern:
- `logs/v19_sweep.log:8185-8190`: two outline calls completed at `800 out`, then `Expecting ',' delimiter` at chars 1956 and 1922, followed by deterministic fallback.
- `logs/v20_sweep.log:8180-8185`: two outline calls completed at `800 out`, then `Expecting ',' delimiter` at chars 1541 and 1867, followed by deterministic fallback.

No additional actual DeepSeek outline malformed-JSON pattern appears in `logs/v19_sweep.log` or `logs/v20_sweep.log`.

Verification: `python -m pytest -q tests/polaris_graph/test_m31_outline_resilience.py` passed 6/6. Pytest emitted a cache-write permission warning under `.pytest_cache`, unrelated to M-31 behavior.
