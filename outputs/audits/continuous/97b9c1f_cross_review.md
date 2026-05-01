# Cross-review — `97b9c1f` batch (cycle 4)

**Cross-review of:** `outputs/audits/continuous/97b9c1f_audit.md` (P0=0, P1=1, P2=2, P3=4)
**Subagent ID:** `a2faf9ed60ad4b097`. Cost: 122,423 tokens / 78 tool uses / 486s wall.

## Verdict alignment

| | Claude self-assessment | Subagent verdict |
|---|---|---|
| Verdict | (would have said APPROVE — I missed the regression) | **APPROVE_WITH_FIXES** |
| P0 | none | **none** |
| Honesty / no fake-working | OK in spirit, **NOT OK in fact** — the new `test_actors.py` regression is a quiet LAW II violation (silent failure mode masked by isolation testing). | **NOT OK on P1.1** |

**The subagent caught a regression that broke a previously-passing test.** This is the highest-value finding in any of the 4 cycles — a fix that ATTEMPTED root_cause coverage actually shipped a real bug. My local verification ran `pytest tests/v6/test_actors.py -q` (8/8 PASS) but didn't run the full suite alongside the acceptance tests.

The pattern: dramatiq actor decorators bind to whatever broker is current at module-import time. test_actors.py called `get_broker(use_stub=True)` BEFORE importing the actors → actors bound to a StubBroker that the acceptance suite then couldn't reach (because acceptance creates its own fresh StubBroker per fixture).

The subagent's reproduction proof:
- `pytest tests/v6/` → 237 pass + 7 xfail + **1 fail** (the acceptance test)
- `pytest tests/v6/acceptance/test_dramatiq_acceptance.py` (alone) → PASS
- Reproduces in BOTH orderings — not a flake.

## Fix plan with root_cause / guardrail / band_aid tags

Single root_cause fix (F-13) addresses P1.1. Subagent's recommendation: "move the broker initialization into a fixture/conftest with cleanup."

| ID | Source | Fix | Tag |
|---|---|---|---|
| F-13 | P1.1 | New `tests/v6/conftest.py` that calls `get_broker(use_stub=True)` at MODULE IMPORT TIME (not via a fixture) — pytest imports conftest BEFORE test modules, so the actor decorators bind to this StubBroker. test_actors.py drops its module-level `get_broker` call. acceptance fixture uses `dramatiq.get_broker()` (shared) instead of creating a new broker. test_broker.py adds an autouse fixture that saves+restores the broker per test. | **root_cause** — eliminates the binding-mismatch class entirely. |
| Defer | P2.1 | Audit-revision smell: the cycle-3 audit changed in working tree post-commit. HEAD-commit byte-identity was preserved; future cycles get unmodified state. Acceptable. |
| Defer | P2.2 | `3bac322_actors_coverage.md` per-commit brief never committed (chain break). Brief file exists at `.codex/continuous/` — can land in a follow-up. |
| Defer | P3.1 | `test_broker.py` save-restore now in F-13. Closed. |
| Defer | P3.2 | `opentelemetry-exporter-otlp-proto-grpc` was a chromadb transitive — F-9 makes it explicit. Correct. |
| Defer | P3.3 | F-10 server-side `_UPLOAD_TABLE` accumulation — acceptable for stub. |
| Defer | P3.4 | Cycle-3 deferred items unchanged. |

## Locking math (revised)

Cycle-3 cross-review predicted "cycle-4 (target): clean APPROVE" — wrong because the new test_actors.py introduced a fresh regression. Updated:

- Cycle 1: APPROVE_WITH_FIXES (P1=3) → F-1..F-6.
- Cycle 2: APPROVE_WITH_FIXES (P1=1, fresh) → F-7+F-7b+F-8.
- Cycle 3: APPROVE_WITH_FIXES (P1=1, fresh + new P2.3 root_cause) → F-9..F-12.
- Cycle 4: APPROVE_WITH_FIXES (P1=1, fresh — the regression) → **F-13** → cycle 5.
- Cycle 5 (target): clean APPROVE (P1=0).
- Cycle 6 (target): clean APPROVE (P1=0) → **LOCK**.

Each cycle has been ~$1-2 in subagent tokens; total to lock: ~$8-12.

## Lessons from this cycle

1. **Local-isolation passing ≠ suite-wide passing.** I verified `pytest test_actors.py` in isolation (8/8 PASS) and that's what my brief reported. The subagent ran `pytest tests/v6/` and caught the cross-pollution. **Going forward, always run the FULL `tests/v6/` suite as the verification step, not just the new file.**
2. **Module-level side effects are a smell.** test_actors.py originally called `get_broker(use_stub=True)` at module import to satisfy the dramatiq decorator's broker-required contract. The "right" place for that is a session-shared fixture/conftest, not a test file's module top.
3. **The triangle's value scales with adversarial probe quality.** Cycle-4's subagent ran `pytest tests/v6/` (the full suite) AND `pytest tests/v6/acceptance/test_dramatiq_acceptance.py` (in isolation) AND tried both orderings — the kind of differential testing that catches state-leak bugs. Not surface-level checking.

## Closure

F-13 landed (commit `15622b2`). Counter for the post-97b9c1f batch: this is commit 1/5. Cycle-5 fires at 5/5.
