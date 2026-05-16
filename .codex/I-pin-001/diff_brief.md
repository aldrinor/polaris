HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-pin-001 diff review (#524) — CLAUDE.md §3.1 canonical-pin reconciliation

Brief already APPROVE iter 1 (`.codex/I-pin-001/codex_brief_verdict.txt`).
This is the **diff review**. Full brief: `.codex/I-pin-001/brief.md`.
Diff: `.codex/I-pin-001/codex_diff.patch` (canonical-diff-sha256 trailer
`bab956c1882e2c131d5d44a2f47d3dfde1c25081b0c38720affda354fc2d2cff`).

## The diff — docs-only, `CLAUDE.md`, 8 insertions / 9 deletions

Reconciles the stale §3.1 canonical-pin check (verifier retired 2026-05-04 —
dead code below `sys.exit(0)` in `.claude/hooks/stop_hook_v3.py`; false-fired
on Windows CRLF). 9 reconciled references:

- §-1.2 ordering (L51): "canonical-pin verification" → "control-plane pin verification".
- §1.1 (L89): dropped "hash-pinned via `docs/canonical_pin.txt`".
- §2.1 (L144): `canonical_pin.txt` re-described as a legacy manifest;
  enforcement retired 2026-05-04; live check = `verify_cage.py` + CHARTER/PLAN
  pins; file retained (`codex_verdict_check.yml` hashes it).
- §3.0 halt conditions (L188): removed "canonical pin SHA mismatch" (the
  retired check); the CHARTER/PLAN-mismatch halt is kept.
- §3.1 step-0 header (L211): "canonical-pin verification" → "control-plane pin
  verification"; dropped "per Plan v13 §A".
- §3.1 step 0 (L213): rewritten — `canonical_pin.txt` SHA-triple check removed;
  CHARTER/PLAN pin verification kept; `verify_cage.py` added; a RETIRED note
  explains the 2026-05-04 neutralization + the CRLF false-positive.
- §3.1 step 12 (L239): "canonical_pin SHA256 (computed in step 0)" →
  "CHARTER/PLAN pin verification result".
- §3.1 intra-task drift (L241): "canonical-pin + CHARTER + PLAN SHA re-verify"
  → "CHARTER + PLAN pin re-verify + `scripts/verify_cage.py`".
- §8.3.10 halt list (L607): "canonical-pin / CHARTER-pin mismatch" →
  "CHARTER/PLAN-pin mismatch".

## Honoring your iter-1 brief findings

- **iter-1 P2** (retire the SHA-triple *enforcement* only, keep
  `canonical_pin.txt` — `codex_verdict_check.yml` hashes it): `canonical_pin.txt`
  is NOT in this diff (untouched); §2.1 records its retained + deprecated
  status. The brief proposed a deprecation *header comment* on the file — on
  applying your P2, I did NOT modify the file at all (any content change alters
  the bytes `codex_verdict_check.yml` hashes). Scope reduction consistent with
  your P2 — flag if you disagree.
- **iter-1 P3** (verify `rg canonical_pin CLAUDE.md` after the edit): done —
  only the two intentional accurate references remain (§2.1, §3.1 step 0).

## Verify

- `git diff polaris...HEAD` = `CLAUDE.md` only (8+/9−).
- `grep -ni canonical CLAUDE.md` — every remaining reference is accurate.
- No live code / workflow / hook / test changed (docs-only).
- The dead `_verify_canonical_pin` code is left as a P3 follow-up (per your
  iter-1 verdict).

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
