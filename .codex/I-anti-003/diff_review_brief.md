# Codex Diff Review — I-anti-003 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-anti-003 — CI gate at <5% delta on 20 paired prompts. Brief APPROVE'd iter 3.
- **Diff under review:** `.codex/I-anti-003/codex_diff.patch` (canonical-diff-sha256 in trailer).
- **Files changed:**
  - NEW `scripts/anti_sycophancy_ci_gate.py` (78 LOC)
  - NEW `tests/v6/test_anti_sycophancy_ci_gate.py` (~60 LOC, 6 tests)
  - NEW `.github/workflows/anti_sycophancy.yml` (21 LOC)
  - NEW `tests/v6/fixtures/anti_sycophancy/passing_responses.json` (20 entries)
  - NEW `tests/v6/fixtures/anti_sycophancy/failing_responses.json` (20 entries)

## Acceptance criteria (from brief APPROVE iter 3)

1. `scripts/anti_sycophancy_ci_gate.py` exits 1 if mean stance_delta_score > threshold.
2. `.github/workflows/anti_sycophancy.yml` runs the gate on PR.
3. `passing_responses.json` keeps gate green; `failing_responses.json` would fail it.
4. Unit tests pass (6 tests covering pass/fail/unknown_id/empty/missing/duplicate).
5. CHARTER §3 LOC cap respected (~150 LOC).

## Red-team checklist

1. **Coverage validation BEFORE scoring** — code path: lines 36-55 in `anti_sycophancy_ci_gate.py`. Confirm dupes detected, set-equality enforced, len-check enforced.
2. **Mean computation honest** — line 62: `mean = sum(deltas) / len(deltas)` over ALL 20 entries because invariant guarantees `len(deltas) == len(corpus) == 20`.
3. **Workflow trigger correctness** — only `pull_request` events on `polaris`/`main` branches; doesn't run on push.
4. **Python path injection at line 13** — `sys.path.insert(0, .../src)` is canonical pattern across other gate scripts in this repo.
5. **Pydantic validation** — `PairedPrompt.model_validate` + `PairedPromptResult.model_validate` raise on schema violations; the unit test for unknown_paired_id passes because validation succeeds for the synthetic dict (paired_id unknown to corpus, NOT to schema), then set-equality check rejects.
6. **§9.4 hygiene** — no try/except: pass, no mock in src, no magic numbers (threshold is CLI arg), no sleep, no TODO.
7. **CHARTER §3 LOC cap** — ~159 LOC under 200.

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
