HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-pin-001 brief — reconcile stale CLAUDE.md §3.1 canonical-pin check (#524)

**GH:** #524
**Branch:** `bot/I-pin-001-canonical-pin-reconciliation` (off `polaris` @ `9185035e`)
**This is the brief; a docs-only diff follows after APPROVE.**

## Background — the finding

CLAUDE.md §3.1 step 0 mandates, as a "non-negotiable HARD STOP" boot check, a
SHA-triple verification of 10 files against `docs/canonical_pin.txt`
(pin == working-tree == HEAD). Investigation for this issue established:

1. **The verifier is dead code.** `.claude/hooks/stop_hook_v3.py` (the wired
   Stop hook) reaches an unconditional `sys.exit(0)` at line 429, *before* its
   `_verify_canonical_pin` (line 121). `scripts/autoloop/orchestrator.py`'s
   copy (line 137) is superseded-autoloop code, not run by the issue-driven
   workflow. No live code runs the `canonical_pin.txt` check.
2. **It was deliberately neutralized 2026-05-04.** `stop_hook_v3.py` lines
   402-453 state the check "was firing on benign Windows CRLF/LF line-ending
   conversion, producing false-drift halts," and was replaced by
   `docs/session_pin.txt` + `scripts/verify_cage.py`.
3. **It still false-fires.** §3.1's literal "pin == working-tree == HEAD"
   cannot pass on a Windows checkout (`core.autocrlf=true`, no
   `.gitattributes` — working-tree SHA256 never equals the LF blob SHA256).
   On 2026-05-16 a §3.1 step-0 run HARD-STOPPED the issue loop on exactly this
   false drift (halt marker since removed; a prior
   `state/halt_20260512…_canonical_pin_drift` shows an earlier session hit it
   too).
4. **The real cage is intact.** The live boot-integrity check is the
   `polaris-controls/CHARTER.md` + `PLAN.md` SHA pins (also in §3.1 step 0,
   verified against `state/polaris_restart/charter_sha_pin.txt`) +
   `scripts/verify_cage.py` (33-check end-to-end). Both CHARTER/PLAN pins
   verified OK on 2026-05-16.

CLAUDE.md §3.1 step 0 is therefore **stale**: it mandates a retired, dead,
false-firing check. This issue reconciles the documentation to the actual
post-2026-05-04 cage. Prior Codex consult `.codex/canonical_pin_reconciliation/`
recommended "regenerate pin + fix verifier code" — that verdict was given
before the verifier was found to be neutralized dead code; it is moot.

## Proposed change (doc reconciliation — `CLAUDE.md` only)

1. **CLAUDE.md §3.1 step 0** — rewrite: remove the `canonical_pin.txt` 10-file
   SHA-triple check and its HARD-STOP language. KEEP the `CHARTER.md` +
   `PLAN.md` SHA-pin verification (the live cage). Add: the canonical-integrity
   check is `scripts/verify_cage.py`. State plainly that the `canonical_pin.txt`
   SHA-triple mechanism was retired 2026-05-04 (CRLF false-positives).
2. **Reconcile every other `canonical_pin` reference in CLAUDE.md** — §2.1
   ("verified at every session-resume per §3 Step 0"), §3.1 step 12
   ("canonical_pin SHA256 computed in step 0"), and any §3/§J/§10 mentions.
   Every surviving reference must be accurate post-rewrite.
3. **`docs/canonical_pin.txt`** — KEEP the file (do NOT delete):
   `scripts/verify_cage.py` line 60 lists it in `EXPECTED_CODEOWNERS_PATHS` —
   deleting it would break verify_cage.py and require a CODEOWNERS edit. Add a
   header comment marking it deprecated / non-enforcing.

## Out of scope (deliberate — keep minimal, docs-only, <200 LOC)

- Removing the dead `_verify_canonical_pin` code from `stop_hook_v3.py` /
  `orchestrator.py` — harmless dead code; the hook's own comment slates it for
  `.legacy/` in a dedicated hook-deprecation cleanup. P3 follow-up.
- Stale local halt markers (`state/halt_1777*`, `state/halt_20260512T…
  _canonical_pin_drift.md`) — `state/` is gitignored; removed as local
  housekeeping, not part of the PR diff.

## Files I have ALSO checked and they're clean

- `scripts/verify_cage.py` — references `canonical_pin.txt` only in
  `EXPECTED_CODEOWNERS_PATHS` (governance), not for pin verification → keep
  the file; verify_cage.py is unaffected by a CLAUDE.md edit.
- `docs/session_pin.txt` — exists; the live pin mechanism; unaffected.
- `state/polaris_restart/charter_sha_pin.txt` — the live CHARTER/PLAN pin;
  unaffected.
- `scripts/autoloop/*` readers of `canonical_pin.txt` — superseded autoloop,
  not run by the issue-driven workflow; unaffected by a doc edit.

## Acceptance criteria

- CLAUDE.md §3.1 step 0 no longer mandates the retired `canonical_pin.txt`
  SHA-triple check; it points to the live cage (CHARTER/PLAN pins +
  `verify_cage.py`).
- Every `canonical_pin` reference remaining in CLAUDE.md is accurate.
- `docs/canonical_pin.txt` retained + marked deprecated; `verify_cage.py`
  unbroken.
- No live code path changed; the diff is docs-only.
- Codex APPROVE on brief + diff.

## Direct questions for Codex

1. `canonical_pin.txt`: keep + deprecate (proposed — minimal, lower-risk) or
   full removal + `verify_cage.py`/CODEOWNERS update?
2. Is leaving the dead `_verify_canonical_pin` code as a P3 follow-up correct,
   or in-scope here?
3. Anything else blocking APPROVE.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
