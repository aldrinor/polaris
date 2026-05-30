# Codex brief-gate — I-meta-002 sub-PR-1: lock mutation + verify_lock consistency mode

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```

## Context
I-meta-002 (#935) wires the 4-role architecture. This is sub-PR-1 of 6 (the rest: contract tests, D8 gate, 3 adapters, orchestration, promotion+dry-run). Operator is blind — keep the verdict crisp. No spend in this PR (pure config + Python). Branch bot/I-meta-002-4role-wiring.

This sub-PR addresses two of YOUR own iter-1 review findings on the I-meta-002 design + the operator-APPROVED D5 slug fix:
- Your finding (f): `verify_lock` currently hardcodes `tests_pass: pending` so it exits 1 — making "Gate-A requires verify_lock exit 0" impossible. Need a `--consistency` mode that checks ONLY code/lock/family/pin consistency (not the propagation `tests_pass`/promotion checkpoints), exiting 0 when the code matches the lock even while status is still `codex_approved_pending_operator_signature`.
- D5 (operator-APPROVED): Judge slug typo in the lock `qwen/qwen-3.6-35b-a3b` → correct OpenRouter id `qwen/qwen3.6-35b-a3b` (verified on OpenRouter /api/v1/models this session).

## Scope of sub-PR-1 (acceptance criteria)
1. `config/architecture/polaris_runtime_lock.yaml`: fix Judge `model_slug` typo → `qwen/qwen3.6-35b-a3b`. Add a `serving_route` field per role: generator=`openrouter`, mirror=`vast_self_host_bf16`, sentinel=`vast_self_host`, judge=`vast_self_host_fp8`. Lock `status` STAYS `codex_approved_pending_operator_signature` (do NOT promote — adapters don't exist yet; promotion is sub-PR-6).
2. `scripts/architecture/verify_lock.py`: add a `--consistency` CLI mode (and a `verify_consistency()` function) that runs ONLY: lock loads + parses, every declared family is in `_FAMILY_PREFIXES`, family_policy `all_distinct` holds, every role's `model_slug` matches the code default (PG_*_MODEL env defaults in openrouter_client.py / pathB_runner.py / entailment_judge.py), and canonical_pin includes the lock. Exit 0 if all consistent — regardless of `status` or `tests_pass`. The existing full `report()` (with propagation/promotion checkpoints) stays as the default mode.
3. Re-pin `docs/canonical_pin.txt`: recompute the lock's SHA256 after the edit (the slug+serving_route change alters it).
4. Tests: extend `tests/architecture/test_runtime_lock.py` — assert `verify_consistency()` exits 0 on the clean tree; assert it FAILS if a role's code default diverges from the lock; assert the Judge slug is the corrected form.

## Files I have ALSO checked and they are clean / relevant
- `src/polaris_graph/llm/openrouter_client.py`: PG_JUDGE_MODEL default is `qwen/qwen-3.6-35b-a3b` (line ~? ) — must be updated to match the corrected slug, else consistency check fails. (This sub-PR fixes both the lock AND the code default together.)
- `src/polaris_graph/benchmark/pathB_runner.py`: `_role_pins()` still only emits generator+evaluator — that's sub-PR-5 (orchestration), NOT this PR. Out of scope here.
- `scripts/architecture/weekly_drift_report.py`: reads the lock; serving_route is additive, no break.
- `.github/workflows/architecture-conformance.yml`: runs `verify_lock`; the new `--consistency` mode is additive.

## Questions for Codex
1. Is the `--consistency` vs default-mode split the right design (consistency = code-matches-lock, default = consistency + promotion checkpoints)?
2. Should the Judge slug fix in the CODE default (PG_JUDGE_MODEL in openrouter_client.py) be in THIS sub-PR or deferred? (Claude's view: same PR — the lock and code default must stay consistent, and consistency-mode would fail otherwise.)
3. Any reason NOT to keep lock status pending here (i.e. is there a hidden need to promote earlier)?
4. serving_route field naming + values — sound, or do you want a stricter enum?

Hand me APPROVE iff the scope + the consistency-mode design are correct.
