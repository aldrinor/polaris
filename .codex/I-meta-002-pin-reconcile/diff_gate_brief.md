HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
- Read ONLY the patch file `.codex/I-meta-002-pin-reconcile/codex_diff.patch`. Emit the YAML verdict block FIRST, then ≤6 sentences.

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

# DIFF gate — I-meta-002 #973: reconcile canonical_pin.txt onto a stable git-normalized LF basis

You APPROVED the brief/design at iter 2 (CRLF→LF-only normalization + bare-CR hard-fail tripwire). Verify
the patch implements EXACTLY that design and nothing else. Patch: 4 files, +262/-7.

## What the patch contains
1. `scripts/verify_canonical_pin.py` (NEW) — `normalized_sha256(path)` reads bytes, `data.replace(b"\r\n", b"\n")`
   ONLY, then `if b"\r" in normalized: raise BareCarriageReturnError` (the iter-1 P1 tripwire), then
   sha256. `verify()` returns problem list (MISSING / BARE-CR / DRIFT); `regenerate()` rewrites the pin from
   current normalized content preserving path set + order, and itself raises on bare CR. `main()` exits 1 on
   any problem. Pure file read + hashlib; no git subprocess; OS-independent.
2. `tests/test_verify_canonical_pin.py` (NEW, 7 tests, all pass) — CRLF==LF hash equality; real content
   change still detected; bare-CR raises; bare-CR surfaces as a verify problem; regenerate preserves
   path set/order; regenerate refuses on bare CR; the committed pin verifies clean.
3. `CLAUDE.md` §3.1 step 0 (1 line) — states the basis is git-normalized LF via the verifier, bare-CR
   rejected; preserves the HARD STOP + halt-marker + CHARTER/PLAN checks; removes a stale "10 files" count.
4. `docs/canonical_pin.txt` — 6 of 14 SHA entries change to the LF basis (regenerated). No paths added/removed.

## Classification of the 6 changed pin entries (verified by Claude main-thread, NO SPEND)
- PURE CRLF→LF REPRESENTATION (file content UNCHANGED; old pin was the CRLF-bytes sha): architecture.md,
  docs/agent_architecture.md, docs/polaris_step_b_full_set_audit_2026_05_27.md.
- THIS PR's edit: CLAUDE.md (the §3.1 wording change above) — new pin = LF sha of edited content.
- GENUINE STALE PIN (old pin matched NEITHER CRLF nor LF basis — content was changed by a prior reviewed
  commit and the pin was never refreshed; regeneration records the already-merged reviewed content):
  - docs/task_acceptance_matrix.yaml — reviewed commit 6ecbcd27 (2026-05-19, "I-cd-010 stale model-ref
    cleanup"); HISTORICAL / decommission-scheduled file per CLAUDE.md §2.1.
  - .codex/REVIEW_BRIEF_FORMAT.md — reviewed commit 2d13e8bc (2026-05-29, "#935 canonical 20-stage pipeline
    doc + pin + Codex reminder").
  Both are called out in the PR body for operator review at merge.

## The real risks to rule on
1. Does the implemented `normalized_sha256` match the APPROVED design EXACTLY — `\r\n`→`\n` only (no bare-`\r`
   replace) and hard-fail on residual `\r`? (Confirm the code, not the prose.)
2. Could `regenerate()` drop or reorder a pinned path, or silently add one? (Claim: it iterates the parsed
   existing entries in order and rewrites only SHAs.)
3. Does `verify()` cleanly catch a real mutation (DRIFT) and a bare CR (BARE-CR) and a missing file (MISSING),
   each as non-zero exit? (Tests b/e/c + missing-path branch.)
4. Does the CLAUDE.md wording now EXACTLY match the verifier's behavior (so the ritual prose can't drift from
   the code), and does it preserve the HARD STOP semantics?
5. Anything in the patch beyond these 4 files / beyond the approved design? (Should be nothing.)

## NOT in scope (locked / out of scope, do not require here)
- A CI canonical-pin gate that calls this verifier — noted as a follow-up in the brief, not this PR.
- The two genuine-stale-pin content deltas are pre-existing reviewed commits, not introduced here.
- No spend; queued for operator-signed merge (CODEOWNERS requires @aldrinor on both changed canonical files).

APPROVE iff the diff implements the iter-2-approved design exactly (CRLF→LF-only + bare-CR hard-fail),
regenerates the pin without adding/removing/reordering paths, keeps the §3.1 hard-stop intact, and contains
nothing beyond the 4 files.
