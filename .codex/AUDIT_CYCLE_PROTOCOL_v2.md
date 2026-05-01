# A+C K=5 Triangle Loop — Protocol v2

**Supersedes:** the implicit cycles 1-4 protocol (per-commit briefs + general-purpose subagent every 5 commits, brief-aware reviewer).

**Why v2:** post-cycle-4 honest assessment (2026-05-01) found 3 design problems with the implicit v1:
1. **Brief-bias contamination** — subagent reads author's per-commit briefs (with self-flagged P0/P1) before reviewing. Confirmation bias dominates over orthogonal findings (~45% novel-finding rate).
2. **Unreachable lock criterion** — "2 consecutive clean APPROVE" pattern may never be met if each fix-cycle introduces new issues at a similar rate (cycle-4 case in point: F-9..F-12 batch shipped a regression in test_actors.py).
3. **Same lens every cycle** — `general-purpose` subagent with adversarial prompt finds the same CLASS of issues. Need rotating probe perspective.

## v2 changes

### Change 1: Brief-blinded reviewer

The cycle-N subagent does NOT receive the author's per-commit briefs in `.codex/continuous/` as input. The subagent receives ONLY:
- The list of N commits in scope (`git show <sha>` for each)
- The project rules (`CLAUDE.md`, `architecture.md`)
- Prior CYCLE-LEVEL audits + cross-reviews (so it sees the loop's history but not the per-commit author prep)
- The protocol doc (this file)

Briefs at `.codex/continuous/<sha>_*.md` continue to exist as the author's planning record + audit trail; they're just not handed to the subagent.

### Change 2: Rotating subagent role

Cycle-N selects ONE of these adversarial lenses (round-robin or threat-driven):
1. **Correctness** (cycles 1, 5, 9, ...) — does the code do what the commit message + tests claim?
2. **Security** (cycles 2, 6, 10, ...) — auth, input validation, injection, data classification leaks.
3. **Performance** (cycles 3, 7, 11, ...) — budget regressions, hot-path complexity, memory.
4. **Accessibility & UX** (cycles 4, 8, 12, ...) — WCAG, keyboard nav, error-state hierarchy.

Each cycle's prompt explicitly scopes the lens. The subagent ignores findings outside its lens (or flags them as P3 "out of scope, observed").

### Change 3: Soft-lock criterion (diminishing-returns)

Replace "2 consecutive clean APPROVE (P1=0)" with:

> **Lock when 2 consecutive cycles return findings that are ALL P2 or below** (no P0, no P1).

Rationale: a real codebase always has SOME issues. Holding out for P1=0 is unrealistic and pushes the loop toward "always finds nits forever." P2-only is the diminishing-returns floor — you've found the things that matter; the rest is gardening.

### Change 4 (optional, future): Pre-commit audit

Not implemented in v2. Adopting it would change cadence from K=5 post-commit to per-commit pre-commit, slowing substrate by ~2-5x. Defer until either:
- Cycle-N catches a P0 production-breaker (we got lucky; should pre-empt next time), OR
- The post-K cadence misses 2 in a row (regression rides through audit window twice).

## Cycle-5 invocation template

```
Subagent role: <lens>
Scope: 5 commits <sha-1> .. <sha-5>
Rules: CLAUDE.md, architecture.md, prior audits + cross-reviews
NOT given: per-commit briefs at .codex/continuous/
Output: outputs/audits/continuous/<sha-5>_audit.md
Verdict: APPROVE | APPROVE_WITH_FIXES | REJECT
Lock check: if your findings are all P2+ AND the previous cycle was also all-P2+, recommend LOCK.
```

## Provenance

This protocol was authored by Claude on 2026-05-01 in response to the user's "Pls think deeply" question. The honest self-assessment is captured in the conversation history; the design choices here are extracted from that.
