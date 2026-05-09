# Codex Diff Review — I-bug-095 (graduate to enforce default) — ITER 2

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings.
- "Don't pick bone from egg".
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
- DO NOT call exec / rg / shell tools.
```

## Iter 2 changes

Iter 1 returned APPROVE + 1 P2 advisory:

> "Test isolation hardening only: ...the current `if not in os.environ` still allows a developer/CI inherited `warn` or `enforce` env to invoke the judge in unrelated tests."

Iter 2 applies this hardening: both `tests/polaris_graph/conftest.py` and `tests/crown_jewels/conftest.py` now `monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")` UNCONDITIONALLY (no `if not in os.environ` guard). Tests that exercise the entailment gate explicitly override via `monkeypatch.setenv` inside the test body. 275 tests still pass, 4 live skipped.

## Pre-flight

- Brief APPROVE'd iter 1 with `recommend_flip_now: yes`, `sufficient_empirical_evidence: yes`, `latency_acceptable_for_carney: yes`.
- Iter 1 diff verdict: APPROVE + 1 P2 (now addressed in iter 2).
- New diff: `.codex/I-bug-095/codex_diff.patch` (canonical-diff-sha256: `5d4a0f9253a137d1fb67b57698c3b0fdd22ffcd1fa5c42c6fcb89452c723013d`)
- 1 src file, 2 conftest files, 3 test files updated.
- 275 generator2 + crown_jewel tests passing + 49 wider polaris_graph tests passing + 4 live tests skipped.

## What changed

### src/polaris_graph/generator2/strict_verify.py
- `_DEFAULT_MODE = "enforce"` module constant
- `_entailment_mode()` reads default from `_DEFAULT_MODE` instead of hardcoded "off"
- Module docstring updated: "off (default)" → "enforce (default)"; off mode explicitly framed as the operator override

### tests/polaris_graph/conftest.py — autouse fixture
Added `_disable_strict_verify_entailment_by_default` matching the existing `_disable_openalex_by_default` pattern:
```python
if "PG_STRICT_VERIFY_ENTAILMENT" not in os.environ:
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
```
This implements your iter-1 directive: "Make tests explicit: cases that are not testing strict verification should set PG_STRICT_VERIFY_ENTAILMENT=off." All other tests in tests/polaris_graph/ that call verify_sentence transitively now run with mode=off and never lazy-construct the OpenRouter judge in CI.

### tests/crown_jewels/conftest.py — same fixture
Crown-jewel tests follow the same pattern. cj-008 explicitly overrides per-test for entailment-mode tests.

### Test updates (entailment tests that previously asserted default-off)
- `test_entailment_mode_unset_defaults_off` → `test_entailment_mode_unset_defaults_enforce` — asserts new default
- Parametrized `test_entailment_mode_env_parsing` — empty/unknown/typo all expect "enforce" not "off"
- `test_unknown_mode_emits_warning_once_per_process` — assert returns "enforce", warning still emitted
- `test_empty_env_emits_no_warning` — assert returns "enforce"
- `test_unset_env_emits_no_warning` — assert returns "enforce"
- `test_unknown_mode_falls_back_to_off` → `test_unknown_mode_falls_back_to_enforce` — verify_sentence with typo + NEUTRAL judge now DROPS (was keeps)
- cj-008 `test_unset_mode_defaults_off` → `test_unset_mode_defaults_enforce` — gate runs + drops on NEUTRAL with no env set
- cj-008 NEW: `test_explicit_off_disables_gate` — pins the operator escape hatch as a Crown Jewel invariant

## Honors your iter-1 directives

- ✅ "set PG_STRICT_VERIFY_ENTAILMENT=off" for tests not exercising strict verification — done via autouse fixture
- ✅ "default-mode tests should assert enforce" — renamed + updated
- ✅ "CI/unit tests mock the judge path" — autouse fixture prevents accidental live-network dependency
- ✅ "Keep operator rollback path documented" — docstring + new cj-008 `test_explicit_off_disables_gate` Crown Jewel pin

## Operator-facing behavior change

**Before this PR**: `PG_STRICT_VERIFY_ENTAILMENT` unset → mode "off" → gate skipped → reports ship with audit-style M2/C2/C1 fabrications passing.
**After this PR**: `PG_STRICT_VERIFY_ENTAILMENT` unset → mode "enforce" → gate runs → fabrications dropped, sentence-level latency +~1.5s/kept-sentence (~50 sentences = +75s/report).

Operators with the rare case where the gate is unwanted (e.g. running an offline migration script that has no API access) set `PG_STRICT_VERIFY_ENTAILMENT=off` explicitly. cj-008's `test_explicit_off_disables_gate` Crown Jewel pins this escape hatch.

## What I want from you

1. **Verdict** APPROVE / REQUEST_CHANGES.
2. **Any P0/P1 you find** — please be exhaustive iter 1.
3. **The autouse fixture pattern**: tests/polaris_graph/conftest.py + tests/crown_jewels/conftest.py both set off-by-default. Sufficient or do you want a top-level tests/conftest.py instead? My read: scoped fixtures are cleaner since they only apply where needed; a top-level fixture would also affect tests/v3/ tests/v6/ which don't touch strict_verify.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
