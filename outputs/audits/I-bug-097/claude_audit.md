# Claude Audit — I-bug-097 (unknown-mode warning)

**Date**: 2026-05-09
**Branch**: `bot/I-bug-097-unknown-mode-warning`
**Files modified**: `src/polaris_graph/generator2/strict_verify.py` (+23) + new test (119 LOC)
**Tests**: 9 new + 61 baseline (cj-008 + entailment + strict_verify) = 70 passing
**Codex**: APPROVE on brief + diff iter 1, zero P0/P1, 2 P2 advisories acknowledged.

## What this fixes

Real failure mode captured by Codex P2 on I-bug-092 diff review: an operator types `PG_STRICT_VERIFY_ENTAILMENT=enforced` (verb form, not in `{off,warn,enforce}`) and the gate silently disables. With this fix the operator sees a single WARNING per typo per process pointing them at the typo + the valid set.

## Hygiene self-audit

- No silent failures — fail-loud per LAW II
- Process-lifetime dedup via module-level `set` (no lock per Codex iter-1 P2 — bounded duplication is acceptable)
- Test isolation via `autouse` fixture that clears the dedup set between tests
- 8 distinct test scenarios + 1 parametrized (3x) = 9 tests cover known/unknown/empty/unset/uppercase paths

## Codex P2 advisories (acknowledged, NOT blockers)

1. Concurrent-call duplicate warnings — bounded log duplication; not adding `threading.Lock` (5 LOC + complexity for a one-time-per-typo race window during process startup).
2. Normalized vs raw env string in warning message — operator can always inspect the actual env var; normalized message is sufficient for operator diagnosis.

## Definition-of-done

- [x] 9 new tests + 61 baseline = 70 passing
- [x] Codex APPROVE on brief + diff (iter 1, zero P0/P1)
- [x] canonical-diff-sha256 = `abd3a438aecd0c836c016db9c75568f3b1d86236af440e56817e8eec9070ab17`
- [ ] CI gate green
- [ ] Auto-merge per Plan §7.B LOCKED B1
