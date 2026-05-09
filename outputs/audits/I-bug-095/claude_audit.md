# Claude Audit — I-bug-095 (graduate to enforce default)

**Date**: 2026-05-09
**Branch**: `bot/I-bug-095-graduate-enforce-default`
**Codex**: APPROVE on brief iter 1; APPROVE on diff iter 2 (zero P0/P1/P2 after addressing iter-1 P2).

## What this PR does

Flips `PG_STRICT_VERIFY_ENTAILMENT` default from `"off"` to `"enforce"`. Closes the policy loop on the 2026-05-09 audit-revealed provenance-correctness gap. The architectural fix from I-bug-092 is no longer dormant — production runs now drop M2/C2/C1-style fabrications by default.

## Empirical justification

I-bug-094 ran 4/4 audit-derived test cases against real OpenRouter Gemma 4 31B in 20.5s and confirmed: M2 fabrication → NEUTRAL (drop), C2 specificity inflation → NEUTRAL (drop), C1 unentailed numbers → NEUTRAL (drop), positive control paraphrase → ENTAILED (keep). The prompt + model + wiring all work together end-to-end on the audit patterns.

## Test infrastructure changes (Codex iter-1 P2 → iter-2 hardened)

Added autouse fixtures in `tests/polaris_graph/conftest.py` and `tests/crown_jewels/conftest.py` that **unconditionally** set `PG_STRICT_VERIFY_ENTAILMENT=off` for tests not exercising the entailment gate. This prevents accidental live-OpenRouter dependency in CI even when a developer has the env var set in their shell. Tests that exercise the gate (test_strict_verify_entailment.py, test_cj_008, test_strict_verify_telemetry.py, test_strict_verify_unknown_mode_warning.py) override per-test via `monkeypatch.setenv`.

Codex iter 1 returned APPROVE with 1 P2 advisory: my initial conditional `if not in os.environ` left the door open for an inherited shell env. Iter 2 makes the override unconditional, addressing the P2 cleanly. Iter 2: zero P0/P1/P2.

## Operator-facing behavior change

| Scenario | Before this PR | After this PR |
|---|---|---|
| `PG_STRICT_VERIFY_ENTAILMENT` unset (default) | mode=off, gate skipped, fabrications pass | mode=enforce, gate runs, fabrications dropped |
| `PG_STRICT_VERIFY_ENTAILMENT=off` (explicit) | mode=off | mode=off (unchanged — operator escape hatch preserved) |
| `PG_STRICT_VERIFY_ENTAILMENT=warn` | mode=warn | mode=warn (unchanged) |
| `PG_STRICT_VERIFY_ENTAILMENT=enforce` | mode=enforce | mode=enforce (unchanged) |
| Typo (`=enforced`) | falls back to off, WARNING logged | falls back to **enforce**, WARNING logged |
| Empty (`=`) | off | enforce |

Operator escape hatch (`=off` explicit) is now binding via Crown Jewel `test_cj_008_explicit_off_disables_gate`.

## Tests updated

- `test_entailment_mode_unset_defaults_off` → `_defaults_enforce`
- `test_entailment_mode_env_parsing` parametrized: empty/unknown/typo all expect "enforce" not "off"
- `test_unknown_mode_emits_warning_once_per_process` — return value asserted as "enforce" (warning unchanged)
- `test_empty_env_emits_no_warning` — return value asserted as "enforce"
- `test_unset_env_emits_no_warning` — return value asserted as "enforce"
- `test_unknown_mode_falls_back_to_off` → `_falls_back_to_enforce` (verify_sentence with typo + NEUTRAL judge now drops, was keeps)
- `test_cj_008_unset_mode_defaults_off` → `_defaults_enforce`
- NEW Crown Jewel: `test_cj_008_explicit_off_disables_gate` — pins the operator override path

275 generator2 + crown_jewel tests pass + 49 wider polaris_graph tests pass + 4 live tests skipped.

## Definition-of-done

- [x] Codex APPROVE on brief iter 1
- [x] Codex APPROVE on diff iter 2 (zero P0/P1/P2)
- [x] canonical-diff-sha256 = `5d4a0f9253a137d1fb67b57698c3b0fdd22ffcd1fa5c42c6fcb89452c723013d`
- [x] Test isolation hardened per Codex iter-1 P2
- [x] Operator escape hatch (`=off`) preserved + bound as Crown Jewel
- [ ] CI gate green
- [ ] Auto-merge per Plan §7.B LOCKED B1
