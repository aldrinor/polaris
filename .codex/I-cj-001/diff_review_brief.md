# Codex Diff Review — I-cj-001 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-cj-001 — Two-family evaluator Crown Jewel test. Brief APPROVE'd iter 2 (P1 import-path + P2 ambient-overrides + P2 wording fixed).
- **Diff under review:** `.codex/I-cj-001/codex_diff.patch` (canonical-diff-sha256 in trailer).
- **Files changed:**
  - NEW `tests/crown_jewels/__init__.py` (empty)
  - NEW `tests/crown_jewels/test_cj_001_two_family_segregation.py` (~70 LOC, 5 tests)
  - NEW `docs/crown_jewels.md` (~13 LOC table)

## Iter-2 brief fixes incorporated in code

- Imports use `from src.polaris_graph...` per existing test convention.
- Every "without override" test passes `generator_override="" evaluator_override=""` explicitly.
- Doc rows for cj-002..007 read `Pending — issued in subsequent CJ Issues` (not "TODO").

## Acceptance criteria (from brief APPROVE iter 2)

1. ✅ 5 tests covering different-family pass / same-family raise / unknown-gen no-override raise / unknown-eval no-override raise / explicit override bypass.
2. ✅ Registry doc maps I-cj-NNN slots to CLAUDE.md §9.1 invariants + test path + bound function.
3. ✅ All 5 tests pass locally.
4. ✅ ~83 LOC under 200.

## Red-team checklist

1. **Test independence from env state** — explicit `="" ""` overrides protect against ambient PG_*_FAMILY_OVERRIDE.
2. **Match patterns** — `r"same training-lineage family"`, `r"generator model.*does not"`, `r"evaluator model.*does not"` align with the actual error strings in `openrouter_client.py:329-337, 314-321, 324-326`.
3. **Substrate-honest framing** — explicit module docstring states this is binding registry of an existing invariant; no new functionality.
4. **§9.4 hygiene** — clean.

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
