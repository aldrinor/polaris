# Codex ↔ Claude audit loop protocol

**Status:** autonomous. User has left the computer for ~24 hours. Loop runs until
Codex declares READY or max rounds reached.

## Roles

- **Codex** (CLI, OAuth auth_mode=chatgpt) — independent reviewer. Writes findings
  to `.codex/round_N/findings.md`. Decision-maker on the READY verdict.
- **Claude** (me, Sonnet 4.6 via Claude Code) — addresses Codex findings with real
  code changes + commits. Never softens severity; never marks items addressed
  without a commit SHA AND a verifying test.

## Round structure

Each round has these files under `.codex/round_N/`:
- `brief.md` — the brief Claude gives Codex for this round.
- `findings.md` — Codex's output for this round. **Must start with a YAML
  frontmatter** containing `verdict`, `blocker_count`, `medium_count`,
  `rationale`. Parsed by `scripts/codex_loop_parse.py`.
- `claude_response.md` — Claude's plan: per-finding, either (a) implemented
  with commit SHA + test ref, (b) deferred with reason, (c) disputed with
  specific counter-evidence.
- `commits.txt` — SHAs of commits Claude made this round.
- `verdict.txt` — single word: `READY` / `NOT_READY` / `CONDITIONAL`.

## Verdict semantics

- **READY** (stop condition): `blocker_count == 0` AND `medium_count <= 2` AND
  every medium item has a documented mitigation plan. No silent failures found.
  Claude and Codex agree on the residual risk profile.
- **CONDITIONAL**: zero blockers but >2 mediums, OR blockers that have
  acceptable operational workarounds. Loop continues — Codex re-reviews the
  mediums.
- **NOT_READY**: ≥1 blocker. Loop continues.

## Anti-circle-jerk rules (baked into every round's brief)

Codex MUST:
1. Read the actual code at the referenced commit SHA. Do not trust summaries.
2. If a previous round claimed a finding was fixed, verify the fix in the diff.
3. If a fix is cosmetic (comment added, test name changed, but behavior
   unchanged), RE-RAISE the finding with SEVERITY INCREASED.
4. If Claude disputed a finding, re-evaluate with the counter-evidence but do
   not defer to Claude's framing.
5. NEVER lower a blocker to medium without showing the specific code change
   that justified the severity drop.
6. If two rounds produce the same finding in the same form, note
   "POTENTIAL DEADLOCK" in the next round's findings.

Claude MUST:
1. Address every blocker with a real commit (not a comment or a docstring).
2. Address every medium OR explicitly defer with a reason.
3. For disputes, cite the specific file:line that contradicts Codex's claim.
4. Never mark an item addressed based on a behavioral guess — verify with a test.
5. Keep the suite green every round (the loop aborts if `pytest` exits non-zero).

## Hard stops

Loop terminates on any of:
- `verdict == READY` (success path)
- Round counter reaches `max_rounds` (default 12)
- Same blocker present in 3 consecutive rounds with no status change
- `.codex/STOP` file exists (user-manual halt)
- Budget guard fires (`PG_MAX_COST_PER_RUN` exceeded, or total Codex-round
  count × avg-run-time > 20 hours)
- Test suite goes red (Claude must fix before next round; if they can't fix
  in one pass, loop halts with "deadlock_tests_red")
- Git conflict on `PL-honest-rebuild-phase-1` branch

## State

`.codex/loop_state.json` is updated on every wakeup. Schema:

```json
{
  "current_round": N,
  "max_rounds": 12,
  "status": "awaiting_codex" | "addressing" | "completed_ready" | "completed_deadlock" | "completed_max_rounds" | "completed_tests_red" | "completed_user_stop",
  "history": [
    {
      "round": 1,
      "verdict": "NOT_READY",
      "blocker_count": 3,
      "medium_count": 5,
      "claude_addressed": 3,
      "claude_deferred": 5,
      "claude_disputed": 0,
      "commits": ["sha1", "sha2", "sha3"],
      "started_iso": "...",
      "codex_completed_iso": "...",
      "claude_completed_iso": "..."
    }
  ],
  "verdict_progression": ["NOT_READY", "CONDITIONAL", "READY"],
  "test_suite_state": {"passed": 220, "xfail": 0, "fail": 0}
}
```
