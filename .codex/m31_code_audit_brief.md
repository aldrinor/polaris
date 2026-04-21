You are auditing M-31 (outline JSON decode resilience) as a code
review BEFORE V21 full-scale sweep runs.

## Scope discipline (user mandate, lessons from M-30)

Audit ONLY the observed V19/V20 failure mode and the M-31 diff
(commit `2e12f12`). Do NOT invent new probe patterns that were not
observed in actual generator output. If you believe the fix has a
residual risk, ground it in ACTUAL DeepSeek output patterns from
`logs/v19_sweep.log` or `logs/v20_sweep.log`, not in constructed
test cases.

The M-30 audit loop went 5 passes chasing Codex-invented probes
that never appeared in real content; that's wasted cycles. This
audit should return READY unless you find a real bug in the diff.

## Context

V19 and V20 both hit the same failure mode:

```
polaris_graph.multi_section WARNING outline JSON decode failed:
Expecting ',' delimiter: line 22 column 6 (char 1867)
```

Character positions 1541 and 1867 in a ~2000-char output are
consistent with mid-JSON truncation at `max_tokens=800` (each
token ≈ 2-3 chars, 800 tokens ≈ 1600-2400 chars output).

The outline fallback is catastrophic:
- V18 (clean outline): 5 sections, 2922 words, 35 citations, 12 regulatory.
- V19/V20 (fallback):  3-4 sections, ~780 words, ~12 citations, 0 regulatory.

Regulatory sources were RETRIEVED correctly by M-28 (48 T3 in raw
corpus). But the deterministic fallback outline didn't pick them,
so the final bibliography had 0 regulatory.

## M-31 changes (commit `2e12f12`)

1. `scripts/run_honest_sweep_r3.py`:
   - `outline_max_tokens=800` → `outline_max_tokens=2500`.
   - Matches the M-24 default in `multi_section_generator.py:883`.
   - Comment documents the V19/V20 truncation failure mode.

2. `src/polaris_graph/generator/multi_section_generator.py`:
   - `_parse_outline` now attempts a lenient re-parse when strict
     `json.loads` fails.
   - Lenient cleanup: `re.sub(r",(\s*[}\]])", r"\1", payload)` —
     strip trailing commas before `]` or `}`.
   - If lenient also fails, returns the same `json_decode_error`
     reason code as before (no behavior change for truly malformed
     JSON).
   - Preserves strict-parse fast path (lenient only runs on failure).

3. `tests/polaris_graph/test_m31_outline_resilience.py`:
   - Trailing-comma recovery: ev_ids list + sections list.
   - Non-regression: well-formed JSON still parses cleanly.
   - Truncation case still fails (lenient doesn't over-relax).
   - Semantics preservation on valid input.
   - Static guard: sweep script must pass outline_max_tokens ≥2500.

## Your task

1. Verify the `outline_max_tokens` bump to 2500 matches the
   in-module default and is consistent with `section_max_tokens`
   budgets downstream.
2. Verify the lenient-cleanup regex `",(\s*[}\]])"` is safe:
   - Cannot change the meaning of well-formed JSON.
   - Cannot mask MISSING-comma truncation errors (which must still
     return `json_decode_error`).
3. Verify the static-guard test (`test_sweep_script_uses_adequate_outline_max_tokens`)
   actually reads the sweep script source. If the sweep caller is
   ever changed back to a lower value, this test must fail.
4. Hard-coding / generalization check: the M-31 diff is
   domain-agnostic (JSON syntax + config) — confirm no domain bias.
5. Any ACTUAL DeepSeek output pattern from
   `logs/v19_sweep.log` or `logs/v20_sweep.log` that M-31 does not
   cover? (Truncation at higher token counts? Other malformed JSON
   shapes?)

## Verdict format

Write `outputs/codex_findings/m31_code_audit/findings.md`:

```
# M-31 code audit

VERDICT: READY | NOT_READY

## Blockers (only if grounded in actual log evidence)
- <list or none>

## Mediums
- <list or none>

## Lows / nits
- <list or none>

## Notes
<any other observations>
```

If READY, V21 sweep launches next. If NOT_READY, the blocker MUST
cite a specific log line from the V19 or V20 sweep log as
justification — not a constructed test case.
