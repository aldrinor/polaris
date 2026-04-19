# POLARIS full-audit pass 2 — Codex verification brief

You are re-auditing POLARIS after 10 deep-dive rounds (R1-R12) closed
most of the issues you surfaced in pass 1. This pass produces an
independent verdict on the current state.

## What happened since pass 1

Pass 1 verdict (scoping): `PRIORITIZED`, 3 blockers + 8 mediums + 1 minor.

Rounds completed this session (chronological, commit-linked):

| Round | Bug | Disposition | Commit |
|---|---|---|---|
| R1 | B-101 manifest status | CLOSED | `c764ddb` |
| R2 | B-102 UI un-hardened | SCOPED → deferred R2a-R2h (multi-session) | `7ae5fcf` |
| R3 | B-100 scope gate | CLOSED | `95a9709` |
| R4 | M-203 outline collapse | CLOSED | `75b4b55` |
| R5 | M-205 evaluator gate | CLOSED | `96ac2b8` |
| R6 | M-201 tier-balanced selector | CLOSED | `fbdd0fc` |
| R7 | M-202 contradiction coverage | MVP CLOSED, R7b deferred | `6bdd89e` |
| R8+R11 | M-206 + N-301 cost ledger | CLOSED | `f632ee5` |
| R9 | M-207 invariant audit | CLOSED | `3c772a5` |
| R10 | M-204 limitations verifier | CLOSED | `15b8b5d` |
| R12 | M-208 pipeline C retire | DECIDED (staged) | `ddcd1d4` |

Test suite: 305 → 387 passed (+82 regression tests).

## Your mandate

Produce an independent verdict on commit `ddcd1d4` (or latest if
newer). Scope:

### 1. Confirm closed blockers/mediums are truly substantive

For each row in the table above marked CLOSED, open the commit, read
the fix, verify:
- The fix is substantive (not cosmetic)
- The new tests would fail against the pre-fix code
- No escape hatches or silent-failure modes introduced

The claude_response.md for each round is in
`outputs/codex_findings/deep_dive_round_{1,3..10,12}/claude_response.md`.
Do NOT trust them — read the actual diffs.

### 2. Confirm R2 (B-102) deferral is honest

B-102 is NOT closed. Strategy C was accepted (scoping finding
`outputs/codex_findings/deep_dive_round_2/findings.md`). Implementation
was deferred to 8 sub-rounds (R2a-R2h) because the work crosses
`scripts/live_server.py` (214KB UI server), requires a `graph_v4.py`
shim, and needs 8 integration tests + SSE event emission. See
`docs/todo_list.md` for R2a-R2h task breakdown.

Verify:
- `scripts/live_server.py` still dispatches to v1/v2/v3 (not v4).
- The Docker default entry (`serve`) still routes to un-hardened graphs.
- No silent back-porting has happened that would let B-102 be silently
  closed without actually implementing strategy C.

This is explicitly still a release blocker until R2a-R2h lands.

### 3. Confirm R7b deferral is honest

R7 landed a predicate expansion (AF anticoagulation + tech + policy +
DD predicates; domain kwarg on `extract_numeric_claims`). The full
Codex §4 redesign (generic numeric mining, YAML profile loader,
per-row multi-claim emission) is deferred. Verify:
- The expansion is real (count predicates in each domain set)
- AF reproducer claims ARE now extractable (at least for the verb
  patterns that match `_VALUE_PHRASE_VERBS`)

### 4. Look for new defects you didn't surface in pass 1

Specifically probe:
- Any regression in prior R1-R5 invariants (B-1..B-5) caused by
  R1-R12 code changes
- New silent-failure paths introduced by the 13 new taxonomy values
  and the evaluator gate
- The evidence_selector quota-rebalancing math (could it under-fill
  when the pool is tiny?)
- The telemetry-grounded limitations verifier word-boundary regex
  (could a legitimate number like "T-cell count of 500" spuriously
  match a 500 in telemetry that refers to something unrelated?)
- set_current_run_id state leak across concurrent runs (the ambient
  state is module-level; if two run_one_query calls run concurrently
  via asyncio.gather, does one stomp the other's run_id?)

### 5. Final verdict

One of:

- **READY** — everything closable is closed; B-102 and R7b deferrals
  are honestly documented; no new blockers
- **NOT_READY** — B-102 is still a blocker (expected) OR new defects
  surfaced OR R1-R12 fixes were cosmetic
- **CONDITIONAL** — ready for a LIMITED full-run (e.g., only pipeline A
  sweep, not UI production) until R2 lands

## Output

Write to `outputs/codex_findings/full_audit_pass_2/findings.md` with
frontmatter:

```yaml
---
verdict: READY | NOT_READY | CONDITIONAL
pass: 2
commit: ddcd1d4 or latest
closed_confirmed: <list of bug IDs confirmed CLOSED substantively>
deferred_accepted: <list: B-102, R7b>
new_blockers: <int>
new_mediums: <int>
new_minors: <int>
rationale: |
  <2-4 sentence executive summary>
---
```

Followed by sections:
- `## 1. Closed-fix substantivity review` — per-bug verdict
- `## 2. Deferral honesty review` — B-102, R7b
- `## 3. Regression scan` — any old invariant broken by new code
- `## 4. New defects (if any)` — with file:line + reproducer
- `## 5. Final verdict and release guidance`

## Context paths

- Every `outputs/codex_findings/*/findings.md` and `claude_response.md`
  (rounds 1-5, full-audit pass 1, deep-dive rounds 1-12)
- `docs/pipeline_audit_context/` (00-08 files from pass 1 + this brief)
- `docs/todo_list.md` (status view with R2a-R2h breakdown)
- Source code at HEAD
- Full test suite: `python -m pytest tests/polaris_graph/` → 387 passed

## Anti-circle-jerk rules

1. **READY requires zero blockers and ≤2 mediums**. B-102 is still a
   blocker by its own definition; if you declare READY, justify why
   you disagree with the pass-1 severity.
2. **Do not lower B-102 to medium without showing commit/diff evidence.**
3. **If a claude_response.md claims a fix is substantive but the
   code shows a cosmetic rename, re-raise with `severity_reraised: true`.**
4. **If the test suite doesn't actually exercise the claimed invariant
   (e.g., test mocks its own assertion), call it out.**

## Authentication

OAuth (chatgpt). No API-key burn.

## Expected duration

15-25 minutes (larger scope than individual deep-dives).

---

Start by:

```
git log --oneline 55475c8..HEAD | head -20    # commits since pass 1
git diff 55475c8..HEAD --stat | tail -10       # files changed
python -m pytest tests/polaris_graph/          # 387 passed expected
```

Then walk the table above round-by-round.
