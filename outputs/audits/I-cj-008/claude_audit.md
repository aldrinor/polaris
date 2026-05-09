# Claude Audit — I-cj-008 (Crown Jewel: entailment correctness)

**Author**: Claude Opus 4.7
**Date**: 2026-05-09
**Branch**: `bot/I-cj-008-entailment-binding`
**Files modified**: 1 new test file (zero production code changes)
**Tests**: 9 new + 42 baseline Crown Jewel = 51 passing
**Codex**: APPROVE on brief iter 1 + APPROVE on diff iter 1 (zero P0/P1)

## What this issue does

Adds Crown Jewel I-cj-008 to `tests/crown_jewels/` binding the architectural invariant introduced by I-bug-092: under `PG_STRICT_VERIFY_ENTAILMENT=enforce` and a judge returning NEUTRAL/CONTRADICTED, `verify_sentence` MUST drop with `drop_reason='entailment_failed'`.

Pure-test addition. Zero production code changes. ~230 LOC including realistic M2 fixture and FakeJudge helper.

## Why a Crown Jewel

The audit-revealed gap (M2/C2/C1 fabrications passing the 5 mechanical strict_verify checks) is a Class-1 architectural failure. The 6th check (entailment judge) closed it. If a future edit silently disables that gate (removes the enforce branch, drops the literal from DropReason, breaks synthesis-claim gating), the audit-revealed fabrications start passing again. A Crown Jewel locks gate teeth — `tests/crown_jewels/` is the binding architectural-invariant suite.

## Coverage (9 tests)

1. **enforce + NEUTRAL → entailment_failed** (the audit-derived M2 case verbatim)
2. **enforce + CONTRADICTED → entailment_failed**
3. **enforce + ENTAILED → keeps + judge invoked exactly once** (positive control)
4. **off mode → judge never invoked** (cost-discipline + behavior parity)
5. **unset env → defaults off**
6. **warn mode → judge runs, sentence kept, WARNING line logged with substring `entailment NEUTRAL`** (telemetry-only invariant)
7. **synthesis-with-tokens → still gated** (mirrors cj_003's no-token exemption layer)
8. **synthesis-without-tokens → exempt** (no judge call)
9. **drop_reason propagates through `verify_sentence_to_record`** (visible in VerifiedSentence record + audit bundle)

## Codex P2 advisories (NOT blockers, captured here)

Per Codex iter 1 diff verdict (`convergence_call: accept_remaining`):

1. **Warn-mode log assertion**: Codex confirms my "check for substring `entailment NEUTRAL`" approach is the right binding (per my Q3 in the diff brief). Resolved.
2. **Optional tightening**: Codex suggests also asserting `levelname == 'WARNING'` on the matching record — would strengthen warn-vs-debug distinction. Captured as optional follow-up; not implemented in this PR per "don't pick bone from egg" + Codex's own `accept_remaining` convergence call.
3. **Comment drift**: `test_cj_008_enforce_entailed_keeps_sentence` calls `_M2_SENTENCE` a "conservative paraphrase" in a comment; technically it IS the fabricated M2 sentence, just paired with an ENTAILED judge verdict for the positive-control wiring. Codex flagged this is comment-only, not a behavioral hole. Captured as optional documentation polish; not blocking.

## Hygiene self-audit

| Pattern | This PR | Verdict |
|---|---|---|
| `try: ... except: pass` | None | ✓ |
| `import unittest.mock` in src/ | N/A — test-only PR | ✓ |
| Magic numbers | None — `min_content_overlap=2` is named threshold | ✓ |
| `time.sleep()` | None | ✓ |
| `# TODO`, `# FIXME` | None | ✓ |
| Mocking the live-evidence DB | No — uses real EvidencePool fixture; only the LLM judge is mocked, which is correct for binding the gate WIRING (not model quality) | ✓ |

## LOC accounting (CHARTER §3)

Test-only changes (excluded from §3 200-LOC cap by convention).
Test file: 230 LOC including 9 tests + FakeJudge helper + M2 fixture + docstrings.

## Definition-of-done at PR merge

- [x] 9 new Crown Jewel tests + 42 baseline = 51 passing
- [x] Codex APPROVE on brief iter 1
- [x] Codex APPROVE on diff iter 1 (zero P0/P1)
- [x] Canonical-diff-sha256 trailer = `03afb4665d18de67788743632a118a514ae4f6f8b2603e5913bcd48caa77adb3`
- [ ] CI `polaris/codex-required` gate green
- [ ] Auto-merge fires per Plan §7.B LOCKED B1
