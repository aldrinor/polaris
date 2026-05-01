# Audit — `5839f9a` batch (3 commits, F-13 fix + cross-review meta + protocol v2 doc)

**Verdict:** APPROVE
**Findings:** P0=0  P1=0  P2=2  P3=3
**Lens:** CORRECTNESS (cycle 5, v2 protocol)
**Lock note:** Cycle-4 had P1=1 (the broker-binding regression). Cycle-5 cannot lock alone; the soft-lock rule needs cycle-5 AND cycle-6 both all-P2+. Earliest possible lock = cycle-6.

Three-commit window (manually fired sub-K=5 batch): `15622b2` (F-13 root_cause) → `ae631db` (cross-review + brief meta) → `5839f9a` (protocol v2 doc).

## Pre-flight

- **Files read:** `CLAUDE.md` (LAW I-VII + §9 invariants), `.codex/AUDIT_CYCLE_PROTOCOL_v2.md`, cycle-1/2/3/4 audits + cross-reviews, full git diffs of all 3 commits via `git show <sha>`, current state of `tests/v6/{conftest,test_actors,test_broker}.py`, `tests/v6/acceptance/test_dramatiq_acceptance.py`, `src/polaris_v6/queue/broker.py`, `.gitignore`.
- **Tests run live (against 5839f9a HEAD):**
  - Full v6 suite: `git checkout 5839f9a -- tests/v6/ && pytest tests/v6/ -q` → **238 passed + 7 xfailed in 20.06s** (matches commit message claim exactly).
  - Order independence: `pytest tests/v6/test_broker.py tests/v6/test_actors.py tests/v6/acceptance/test_dramatiq_acceptance.py` → 18 passed + 7 xfail. Reverse ordering same. F-13 fix is order-stable.
  - Acceptance alone: `pytest tests/v6/acceptance/test_dramatiq_acceptance.py` → 1 passed + 7 xfail (was the failing test pre-F-13).
  - Wider scope: `pytest tests/v6/ tests/polaris_graph/ --collect-only` → 3667 collected, no errors. v6 conftest does NOT pollute polaris_graph collection.
  - ResourceWarning probe: `python -W error::ResourceWarning -m pytest tests/v6/test_broker.py` → 9 passed, no warnings emitted (RedisBroker leak is latent, not active).
- **Greps:** `grep -rn "pragma: no cover" src/polaris_v6/` → ZERO (F-11 still intact); `git ls-files .codex/continuous/` → confirms 3bac322 brief still missing (cycle-4 P2.2 carryover).

## Per-criterion forced enumeration

- **C-F-13 conftest StubBroker install:** PASS. Module-level `_get_broker(use_stub=True)` fires at conftest import (before test_actors.py collection). `try/except ImportError` correctly catches dramatiq-missing — broker module's `import dramatiq` raises ImportError. StubBroker is in-memory; no other exception class to consider.
- **C-F-13 acceptance fixture session reuse:** PASS. Worker against shared broker; no close on teardown (correct).
- **C-F-13 test_broker.py autouse save+restore:** PASS for global-broker contract. RedisBroker object leakage residual — see P3.1.
- **C-test_actors.py module-level call removed:** PASS. Comment delegates to conftest correctly.
- **C-protocol-v2 doc:** Internal contradiction — see P2.1.
- **C-cross-cycle integrity:** F-11 (no pragma) holds; cycle-3 P3.5 (.gitignore breadth) unchanged — per cycle-4 P3.4 deferred.

## P0

NONE.

## P1

NONE. F-13 cleanly fixes the cycle-4 P1.1 regression; the v6 suite passes deterministically across two orderings; the conftest's module-level side effect is contained to `tests/v6/` (verified: collecting `tests/polaris_graph/` doesn't trigger it).

## P2

**P2.1 — Protocol v2's "soft-lock" rule is logically equivalent to v1's "clean APPROVE", not softer.** The doc at `.codex/AUDIT_CYCLE_PROTOCOL_v2.md:34-38` states:

> Replace "2 consecutive clean APPROVE (P1=0)" with:
> **Lock when 2 consecutive cycles return findings that are ALL P2 or below** (no P0, no P1).
> Rationale: a real codebase always has SOME issues. Holding out for P1=0 is unrealistic...

But "no P0, no P1" is mathematically equivalent to "P0=0 AND P1=0", which is the same condition v1 already required (a "clean APPROVE" already meant P0=0 + P1=0; APPROVE_WITH_FIXES fired any time P1>0 — see cycle-1 audit header `Verdict: APPROVE_WITH_FIXES / P1=3`). The rationale in line 38 says "P1=0 is unrealistic" but the new rule still requires exactly that. This is a doc-vs-rule mismatch in a meta-protocol file: the announced softening doesn't actually relax the bar. If v2's intent was a meaningful softening, the rule should be "≤1 P1 across the 2-cycle window" or "P1s decreasing monotonically" or similar. As-written, v2's lock criterion is identical to v1's — the only effective change in v2 is brief-blinding + rotating lens. Tag: **guardrail** — meta-protocol clarity.

**P2.2 — `bb60495_audit.md` working-tree edit still uncommitted.** `git status outputs/audits/continuous/bb60495_audit.md` at 5839f9a HEAD reports `modified`. Cycle-4 audit P2.1 flagged this same edit (P1=2→P1=1 + shortened pre-flight) and recommended "commit-the-edit or leave it alone." The cross-review's "Defer P2.1: ... HEAD-commit byte-identity preserved" rationalizes leaving HEAD intact, which is true — but the working-tree dirty state has now persisted across 3 cycles (4, 5 in scope; will pollute cycle-6 too). Audit-trail at HEAD remains byte-correct, so no integrity break, but the repeated dirty state is a guardrail smell. Tag: **guardrail**.

## P3

**P3.1 — `test_broker.py` 4 tests construct RedisBroker objects that are never closed.** Each `get_broker(redis_url=...)` call builds a RedisBroker + connection_pool. The new autouse `_restore_session_broker` fixture restores only the GLOBAL broker reference; the constructed RedisBroker objects are unreferenced after test exit. `python -W error::ResourceWarning -m pytest tests/v6/test_broker.py` emits no warnings — RedisBroker doesn't connect until a message is sent. Latent flag if RedisBroker ever becomes eager. Tag: **guardrail**.

**P3.2 — Cycle-4 P2.2 still open: `3bac322_actors_coverage.md` brief never committed.** `git ls-files .codex/continuous/` at 5839f9a confirms briefs for `0c49d57`, `466b662`, `97b9c1f`, `15622b2` exist but `3bac322` is still absent. The chain break carries through cycle-5. Tag: **guardrail**.

## Cross-cycle integrity

- Cycle-1 P2.2 (install bloat), P2.4 (cross-platform lockfile): unchanged. F-13 doesn't touch deps.
- Cycle-2 P2.2 (`testIgnore` Linux-only): unchanged.
- Cycle-3 P3.5 (.gitignore exemption breadth): unchanged. Still `!outputs/audits/` (broader than `continuous/` only). Per cycle-4's P3.4 acceptance, defer.
- Cycle-4 P1.1 (broker cross-pollution): **CLOSED by F-13.** Empirically reproduced fix in two orderings.
- Cycle-4 P2.1 (audit working-tree edit): **STILL OPEN.** See P2.2 above — same dirty file, second cycle.
- Cycle-4 P2.2 (3bac322 brief missing): **STILL OPEN.** See P3.2 above.
- Cycle-4 P3.1 (test_broker leakage): partially closed by F-13's autouse fixture (global broker now restored). RedisBroker object leakage is the residual sub-issue (P3.1 above).

## Reviewer independence statement

I read actual diffs (`git show 15622b2 ae631db 5839f9a`), inspected the new conftest.py + modified test files, ran the full v6 suite at-5839f9a HEAD via `git checkout 5839f9a -- tests/v6/` to verify the commit-message claim of "238 passed + 7 xfailed in 19.29s" — got 238 passed + 7 xfailed in 20.06s, confirmed. Re-ran in two orderings to verify F-13 is order-stable (18 passed + 7 xfailed both ways). Mechanically grepped for cross-cycle integrity. Probed the conftest's `try/except ImportError` reach via the broker module's `import dramatiq` line. Computed protocol-v2 lock-rule equivalence by reading line 36 ("no P0, no P1") against cycle-1's APPROVE_WITH_FIXES at P1=3.

**This was the first cycle under v2 brief-blinding** — I did NOT read `.codex/continuous/15622b2_*.md` or any other per-commit author brief. Worked: I caught the protocol-v2 doc inconsistency (P2.1) which an author-brief-reading reviewer would likely have anchor-followed past, since the v2 brief restates the rule as "softer" without showing the equivalence.

AGREE: F-13 is a clean root_cause fix; conftest module-level execution is the correct place for shared-broker setup; v2 protocol's brief-blinding + rotating-lens changes are sound; cycle-4 cross-review's "isolation ≠ suite-wide" lesson is correct.

DISAGREE: v2's "soft-lock" framing oversells the change. The actual lock criterion is unchanged from v1 — only brief-blinding + rotating lens are genuine novel improvements. The lock-rule line should either be reworded ("inputs change, bar unchanged") or actually softened (e.g. "≤1 P1 across the 2-cycle window").

**Verdict: APPROVE.** P0=0, P1=0. Cycle-5 returns the cleanest verdict in the loop's history. **Lock not yet possible** — cycle-4's P1=1 means the 2-consecutive-cycle window starts here. Cycle-6 must also return all-P2+ for soft-lock.
