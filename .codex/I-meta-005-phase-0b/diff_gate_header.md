HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex DIFF gate — Phase 0b (#984): verification-mode router (gap-#18 fix)

You are reviewing the CODE DIFF against the APPROVE'd brief. The brief was APPROVE'd at iter 3
(.codex/I-meta-005-phase-0b/brief.md + its ADDENDUM). The exact build contract is
.codex/I-meta-005-phase-0b/build_spec.md (9 edits + a 7-case smoke battery). Output the §8.3.9 YAML
verdict FIRST, then prose.

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## What to verify (clinical-safety-critical — read the actual diff, not the summary):

1. **OFF byte-identity (the regression wall).** With PG_VERIFICATION_MODE unset/off, is `is_verified`
   AND `failure_reasons` provably identical to pre-0b? Every new branch must gate on
   `_verification_mode() in ("shadow","enforce")`. The ONLY off-mode structural change is the additive
   `judge_error` dataclass field (default False). Confirm no off-mode behavior change. Confirm the
   S0b-1 smoke actually asserts this (not a trivially-true assertion).

2. **Delta 3 executability (the iter-2 P1).** Does ON mode (enforce) actually fail-closed on
   `("ENTAILED","judge_error: ...")` even though the base path marks it is_verified=True? Trace:
   judge_error_flag set at BOTH judge calls → enforce appends `entailment_judge_error_fail_closed:` →
   is_verified=False. Confirm `judge_error_flag` is in-scope at the return (no NameError path).
   Confirm OFF keeps is_verified=True + flag=True (S0b-4).

3. **Anti-laundering (LETHAL).** `_find_local_content_window` is BOUNDED (<=400 chars) and fail-closed:
   a fabrication whose content words are SCATTERED >400 chars apart must NOT be rescued. Confirm the
   window logic cannot return a whole-document span, and S0b-5 actually exercises a >400-char-scatter
   case that stays dropped under enforce. A rescue that laundered a fabrication is a P0.

4. **shadow is output-neutral AND spend-neutral.** shadow must not change is_verified and must make NO
   extra judge calls (Delta 2 shadow path must not re-judge). Confirm S0b-3 asserts the fake-judge
   call-count for shadow == off.

5. **Delta 1 + Delta 2 actually fix gap-#18.** Under enforce, the gap-#18 grounded sentence that
   dropped now passes (S0b-7 reproduction), and a genuinely-unsupported sentence still drops.

6. Smoke: all 7 S0b cases present + passing, run serialized. The S0b-1 byte-identity wall and S0b-5
   anti-laundering gate must be real (not relaxed/trivial).

APPROVE iff OFF is byte-identical, Delta 3 fails-closed correctly, the bounded window cannot launder a
fabrication, shadow is neutral, and the smoke is real. This verdict authorizes the MERGE (operator
governance 2026-05-31: Codex decides merge, Claude executes on the written verdict).

--- DIFF + SMOKE RESULTS BELOW ---
