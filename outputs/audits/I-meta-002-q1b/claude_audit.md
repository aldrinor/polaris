# Claude architect audit — I-meta-002-q1b (#939): verifier reasoning separation + capture

## What this fixes (Q1 launch blocker #1, no-spend)
The Codex Q1 launch-readiness gate (#938) APPROVE'd the runbook with 4 must-fix-before-spend
blockers. Blocker #1 was the only no-spend code item: the three verifier roles (Mirror / Sentinel /
Judge) did not separate their reasoning from their verdict, and their reasoning was logged nowhere.
This brings the verifiers to the same bar the generator already meets (I-gen-004 reasoning_trace.jsonl):
reasoning kept apart from the verdict ("no soap") and captured for line-by-line review.

## Design (as built, both Codex gates APPROVE)
- `_separate_reasoning` + 4-tuple `_parse_response` in `openai_compatible_transport.py`: prefer a
  separate `reasoning_content` field (content already bare); else split a LEADING `<think>…</think>`
  off `content`; else no reasoning. Unterminated `<think>` → `RoleTransportError` (fail-closed — never
  feed a half-think to a strict verdict parser). A post-split blank guard fires identically across both
  paths (think-only / blank-after-field both raise).
- `_sanitize_raw_for_capture` (added after Codex diff iter-1 P1): the response handed to the Path-B
  capture channel has `reasoning_content` dropped and `content` replaced by the bare verdict, so
  reasoning can never leak into capture regardless of what `build_response_metadata` persists. Served
  identity (`model`/`usage`/`_pathb_served`/`system_fingerprint`) preserved → M4 served==pinned intact.
  Original `raw` not mutated.
- `reasoning` field on `RoleResponse` + `RoleCallRecord`; `RecordingTransport` carries it; the seam
  (`run_four_role_evaluation`) writes `four_role_role_calls.jsonl` per role call with `reasoning` in its
  own field, NEVER concatenated into the verdict.

## Verification (offline, no spend)
- 434 tests PASS across `tests/roles tests/dr_benchmark tests/architecture` (15 new: 3 reasoning shapes
  × 3 roles + unterminated/think-only/blank-field fail-closed + Mirror `<co>` preserved-after-split +
  sanitizer no-leak + seam jsonl separation).
- `verify_lock --consistency` OK; `gate_a_dry_run` OVERALL PASS (verdict parsers still parse the bare
  post-split verdict; Sentinel yes=UNGROUNDED, Judge off-enum raises, Mirror two-pass binds).
- Frozen / untouched: runtime lock NOT promoted; claim_audit_scorer.py, the 5 PR-10 contracts,
  served==pinned (M4), Sentinel polarity, Judge 5-enum, the D8 gate.

## Clinical-safety note (§-1.1)
Fail-closed throughout: an unparseable/half-emitted reasoning block HOLDS rather than guesses, and a
verifier that returns reasoning-only with no verdict raises. No path weakens the D8 release gate or the
S0 exact-source requirements.

## Residual (out of scope — operator-gated Q1 blockers #2-#4)
Runtime-lock promotion to `status: locked` (operator signature), `PG_MAX_COST_PER_RUN` set for Q1, and
serving-time served==pinned confirmation. No spend until those are honored.
