HARD ITERATION CAP: 5. iter 3 of 5. Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex BRIEF re-gate iter 3 — Phase 0b (#984): Delta 3 made executable (additive judge_error flag)

iter 2 = REQUEST_CHANGES, ONE continuing P1: Delta-3 judge-error DROP not executable (verifier marks
("ENTAILED","judge_error:...") as is_verified=True, reason discarded; wrapper returns base before the lane runs).
Addressed in the ADDENDUM at the end of .codex/I-meta-005-phase-0b/brief.md (READ it). Deltas 1+2 already CONFIRMED
real+distinct by Codex iter-2. Output §8.3.9 YAML verdict FIRST.

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Confirm Delta 3 is now executable + OFF stays byte-identical:
The corrected design: (1) additive `judge_error: bool=False` on SentenceVerification (:398-407, default False → OFF
behavior + existing fields UNCHANGED byte-identical); base verifier sets judge_error=True when the judge returns
ENTAILED + reason.startswith("judge_error:") at :1200-1204 (still is_verified=True in OFF — pre-existing fail-open NOT
changed in OFF). (2) ON-mode router: `if base.judge_error: DROP` fail-closed REGARDLESS of base.is_verified. (3) Smoke
asserts OFF → is_verified=True + judge_error=True (byte-identical pass, flag inert); ON → DROPPED. (4) OFF fail-open
filed as a separate pre-existing safety issue.
RULE: (a) is the additive flag genuinely OFF-byte-identical (no existing field/behavior changes; the new flag is inert
in OFF)? (b) does ON-mode `if base.judge_error: DROP` actually fail-closed now (the info is available)? (c) is filing
the OFF fail-open as a separate gated issue the right scope call (vs fixing OFF here and breaking byte-identity)?

APPROVE iff Delta 3 is now executable, the additive flag keeps OFF byte-identical, and the OFF-fail-open deferral is
correctly scoped. This is the build contract; on APPROVE the build begins.
