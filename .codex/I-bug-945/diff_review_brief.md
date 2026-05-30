## Codex DIFF review brief — I-bug-945 (GH#931) Path-B gate canonical_slug

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (bound)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Context

You APPROVE'd choice C iter 1 on the brief at `.codex/I-bug-945/brief.md` with 4 P2 items:
1. Use GET /api/v1/models (list, exact-match id) — not /models/<id>
2. Fail closed if slug not found; persist canonical_slug=null if absent
3. Add canonical_slug as trailing/defaulted RolePin field
4. Normalize served model before _role_surrogate to avoid drift on mixed alias/canonical

All 4 are addressed in this diff. Review the implementation against your guidance + §-1.1.

## Diff under review

`.codex/I-bug-945/codex_diff.patch` (61 LOC in `scripts/dr_benchmark/pathB_run_gate.py` + 95 LOC tests in `tests/dr_benchmark/test_pathB_run_gate.py`).

## Test results

29/29 PASS (full suite, including 5 new I-bug-945 regressions). Run:
```
python -m pytest tests/dr_benchmark/test_pathB_run_gate.py -x -q
```

## What the diff does

1. **RolePin dataclass** — adds trailing defaulted `canonical_slug: str | None = None` (P2#3 positional-safe).
2. **`resolve_canonical_slug(model_slug)`** — calls GET /api/v1/models list, exact-match by `id`, returns canonical_slug or None if alias==canonical_slug. Raises GateError if alias not in catalog (P2#2 fail closed).
3. **`preflight()`** — for each role pin, if not offline AND canonical_slug not pre-set, resolves via OpenRouter. Resolution happens BEFORE the role_pins dict is built into the returned pin record (so canonical_slug is captured in `pathB_gate_pin.json` per Codex's persistence observation).
4. **`assert_post_run()`** — accepts served `model` matching EITHER `model_slug` OR `canonical_slug`. Normalizes served `model` to the alias (`model_slug`) before `_role_surrogate` so mixed alias/canonical calls produce a single surrogate (P2#4).

## Files I have ALSO checked and they're clean

- `scripts/dr_benchmark/score_run.py:51` — consumes RolePin via `rp.get("model_slug")`; canonical_slug is additive, no change required.
- `scripts/dr_benchmark/aggregate_systems.py:149,153` — final-report rendering; canonical_slug additive.
- `src/polaris_graph/benchmark/pathB_runner.py:_role_pins()` — constructs RolePin with positional args; canonical_slug stays None until preflight() resolves it. No change required.
- `src/polaris_graph/benchmark/pathB_capture.py` — captures served response_metadata; no compare logic.
- `src/polaris_graph/llm/openrouter_client.py` — records served `model` as-is (canonical_slug); no change required.

## Verification chain

- I-bug-944 (provider case-insensitive) — still tested at `test_post_run_passes_on_provider_case_difference`, still passes.
- Existing `test_post_run_fatal_on_model_drift` updated regex from "served model" to "matches neither" (the error message changed).
- New: `test_post_run_passes_when_served_model_is_canonical_slug` — the exact smoke-#14 scenario in unit form.
- New: `test_post_run_fatal_when_served_matches_neither_alias_nor_canonical` — drift catch still works.
- New: `test_post_run_surrogate_stable_across_mixed_alias_and_canonical` — P2#4 in unit form.
- New: `test_resolve_canonical_slug_returns_dated_snapshot` — happy path resolver.
- New: `test_resolve_canonical_slug_returns_none_when_alias_equals_canonical` — None semantics.
- New: `test_resolve_canonical_slug_fail_closed_on_unknown_alias` — P2#2 in unit form.
- New: `test_preflight_persisted_pin_includes_canonical_slug` — audit anchor proof.

## Required from Codex

Review against §-1.1 (clinical-grade pre-registration integrity) and the 4 P2 items from your iter-1 brief APPROVE.

Hand me APPROVE with `convergence_call: accept_remaining` so I can commit + push + relaunch smoke #15.
