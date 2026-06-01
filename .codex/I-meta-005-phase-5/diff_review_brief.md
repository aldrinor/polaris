REVIEW DISCIPLINE: FOCUSED DIFF REVIEW of `.codex/I-meta-005-phase-5/codex_diff.patch`
vs the APPROVED brief. iter 2: confirm the 2 iter-1 P2 fixes are closed; surface any
NEW real blocker. Open at most the 5 changed files. Pure-CPU.

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings. Same quality bar. Don't pick bone from egg.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## iter-1 was APPROVE (0 P0/P1) with 2 P2 — now FIXED, verify

### P2a — explicit zero authority laundered to 1.0 (evidence_selector)
Was: `-(s[1] * float(s[3].get("authority_score", 1.0) or 1.0))` → an EXPLICIT
authority_score=0.0 became 1.0. FIXED: new `_authority(row)` returns 1.0 ONLY when
the key is absent/None; a genuine 0.0 stays 0.0. New test
`test_p5_explicit_zero_authority_ranks_below_positive` pins it (zero ranks below an
equal-relevance positive row).

### P2b — `max_rows<=0` empty-guard short-circuited before floor mode
Was: `if max_rows <= 0 or not evidence_rows:` returned empty even in floor mode.
FIXED: `if (max_rows <= 0 and relevance_floor is None) or not evidence_rows:` — in
floor mode the cap is replaced by the floor, so max_rows=0 no longer empties the
ON pool; OFF-mode max_rows=0 still empties (unchanged). New test
`test_p5_floor_mode_ignores_zero_max_rows` pins both.

VERIFY: both fixes are correct and complete; OFF byte-identity still holds
(off-mode max_rows=0 still empties; no new key off-mode); nothing else changed.

## Everything else was APPROVE-confirmed at iter 1 (do NOT relitigate unless a NEW defect)
- No-unique-claim-loss (conservative singleton), corroboration via corroboration.py
  (urlparse hosts), pinned floor→inject→gate→dedup→generator order, OFF byte-identity,
  fail-loud floor, primary-anchor floor-exempt, zero spend.
- 3 open items ruled acceptable at iter 1 (larger ON pool, structural P5-10, OFF
  omits selection_relevance).

## Smoke (committed tree)
17 Phase-5 + 29 selector regression = 46 passed.

## Output schema (REQUIRED)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
