# Claude architect audit — #973: canonical_pin.txt git-normalized LF basis reconciliation

**Issue:** #973. **Branch:** `bot/I-meta-002-pin-reconcile` (on the depth-stack tip so it covers the final
14-file pin). **Brief gate:** APPROVE iter 2 (after adopting the iter-1 bare-CR P1). **Diff gate:** pending.
**NO SPEND** — pure git + hashlib + offline pytest.

## Why
The §3.1 boot-ritual pin check was unsatisfiable on Windows (autocrlf=true): working-tree text is CRLF, git
stores LF, and `canonical_pin.txt` itself mixed CRLF-computed and LF-computed sha256 entries across past
reconciliation commits. Net: at the stack tip, 6 of 14 entries mismatch under the LF basis CI uses. The
local pre-commit hook is stubbed, so nothing caught it. This is a documented §3.1 hard-stop (halt marker
`state/halt_20260530T170643Z_canonical_pin_drift.md`).

## The fix
`scripts/verify_canonical_pin.py` computes one stable basis = git text normalization: `\r\n`→`\n` ONLY, then
HARD-FAIL on any residual bare `\r` (the trust-anchor tripwire — a lone CR must stop the ritual, never hash
clean). Because the 14 files are pure-LF blobs, this equals the git blob content sha on every platform.
`--regenerate` reconciled the pin (6 SHAs changed); `verify` returns 0. CLAUDE.md §3.1 step 0 now names the
basis + points to the verifier, preserving every HARD STOP and the CHARTER/PLAN check.

## The 6 reconciled entries — content integrity classification
- **Pure CRLF→LF representation, content UNCHANGED** (old pin = CRLF-bytes sha): architecture.md,
  docs/agent_architecture.md, docs/polaris_step_b_full_set_audit_2026_05_27.md.
- **This PR's edit:** CLAUDE.md (§3.1 wording).
- **Genuine stale pin — old pin matched NEITHER basis; content changed by a prior *reviewed* commit, pin
  never refreshed; regeneration records already-merged content** (called out for operator at merge):
  - docs/task_acceptance_matrix.yaml ← reviewed commit 6ecbcd27 (2026-05-19); HISTORICAL/decommission-scheduled.
  - .codex/REVIEW_BRIEF_FORMAT.md ← reviewed commit 2d13e8bc (2026-05-29).
  No unauthorized mutation anywhere.

## Safety
- Does NOT mask mutation: normalization touches only `\r\n` pairs (= git); any content byte change still
  changes the sha; a bare `\r` hard-fails. Test (b) + bare-CR tests pin this.
- `regenerate()` preserves the pinned path set + order; only SHA values change. No paths added/removed.
- CODEOWNERS requires @aldrinor on both changed canonical files → structurally cannot merge without the
  operator's sign-off (= the "user-signed reconciliation commit" the rule requires).
- Trust anchor not weakened: §3.1 hard-stop semantics intact; basis is now explicit + cross-platform stable.

## Tests (7, NO SPEND)
CRLF==LF hash equality; real content change detected; bare-CR raises; bare-CR surfaces as verify problem;
regenerate preserves path set/order; regenerate refuses on bare CR; committed pin verifies clean. `py_compile` OK.

## Verdict
Resolves the §3.1 hard stop by putting the pin on a stable git-normalized LF basis with a bare-CR tripwire,
without masking real mutation, touching only 4 files, and queued for operator-signed merge. Brief APPROVE
iter 2; diff gate next.
