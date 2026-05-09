# Codex Diff Review — I-cj-008 (Crown Jewel: entailment binding)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
- DO NOT call exec / rg / shell tools. Brief is self-contained.
```

## Pre-flight

- Brief APPROVE'd iter 1 (`.codex/I-cj-008/codex_brief_verdict.txt`).
- Diff: `.codex/I-cj-008/codex_diff.patch` (canonical-diff-sha256: `03afb4665d18de67788743632a118a514ae4f6f8b2603e5913bcd48caa77adb3`)
- File added: `tests/crown_jewels/test_cj_008_entailment_correctness.py` (~230 LOC, 9 tests)
- All 51 Crown Jewel tests pass (42 baseline I-cj-001..007 + 9 new I-cj-008)
- Zero production code changes — pure-test addition

## What's pinned

| Test | Invariant pinned |
|---|---|
| `test_cj_008_enforce_neutral_drops_with_entailment_failed` | The audit-derived M2 fabrication MUST be dropped in enforce mode when judge returns NEUTRAL |
| `test_cj_008_enforce_contradicted_drops_with_entailment_failed` | CONTRADICTED also drops with same drop_reason |
| `test_cj_008_enforce_entailed_keeps_sentence` | Positive control — legit ENTAILED keeps the sentence and judge IS invoked once |
| `test_cj_008_off_mode_never_invokes_judge` | Off mode never reaches the judge even when singleton present (cost discipline + behavior parity) |
| `test_cj_008_unset_mode_defaults_off` | No env var = off |
| `test_cj_008_warn_mode_runs_judge_but_does_not_drop` | Warn mode runs judge + logs WARNING + KEEPS sentence (telemetry-only invariant) |
| `test_cj_008_synthesis_with_tokens_still_runs_entailment` | is_synthesis_claim=True with tokens still gated |
| `test_cj_008_synthesis_without_tokens_skips_entailment` | is_synthesis_claim=True without tokens stays exempt (mirrors cj_003) |
| `test_cj_008_record_carries_entailment_failed_drop_reason` | drop_reason='entailment_failed' propagates through `verify_sentence_to_record` |

## Honors your iter-1 brief verdict

- ✅ Test surface complete (5 from your brief + warn-mode + synthesis × 2 + record propagation = 9)
- ✅ LOC under estimate (~230 vs your "yes" on 80-120; the extra LOC is realistic span text + fake-judge fixture, mirroring cj_003 fixture style)
- ✅ Fake judge used for wiring binding (acceptable per your verdict)
- ✅ Two-family segregation NOT duplicated here per your `extra_invariants_to_pin` guidance
- ✅ Mechanical short-circuit NOT promoted here per your `extra_invariants_to_pin` guidance
- ✅ Warn-mode pinned per your P2 advisory ("if warn is documented/operator-facing — yes it is per CLAUDE.md §I-bug-092 brief verdict")

## Implementation notes (please review)

### 1. Realistic M2 audit text used as canonical Crown Jewel scenario

The fixture uses the actual URNCST adipocyte-metabolism span and the actual M2 fabricated sentence verbatim from `outputs/audits/v32_baseline_content_audit/CROSS_REVIEW.md`. Rationale: a Crown Jewel should bind the SPECIFIC failure pattern that motivated it, so the test reads like documentation of "this exact audit case must never pass strict_verify again."

### 2. Reused FakeJudge pattern from regular regression suite

Same monkeypatch idiom as `tests/polaris_graph/generator2/test_strict_verify_entailment.py` shipped under I-bug-092: install via `monkeypatch.setattr(strict_verify, "_get_judge", lambda: fake)`. Crown Jewels typically don't import test helpers from the regular suite, so I duplicated the FakeJudge class here (12 LOC). Acceptable duplication for an architectural-invariant test that needs to be self-contained.

### 3. Warn-mode test asserts log line content

`assert any("entailment NEUTRAL" in record.message for record in caplog.records)`. This binds the WARNING-log telemetry to the warn mode. If a future edit silently changes the log message format or downgrades it to DEBUG, this test fails. That's the binding point Codex's P2 advisory called out ("any warning metadata/log path remains non-fatal").

## What I want from you

1. **Verdict** (APPROVE / REQUEST_CHANGES) on the diff itself.
2. **Any P0/P1 you find** — please be exhaustive in iter 1.
3. **Confirmation** that pinning the EXACT log message string ("entailment NEUTRAL") is appropriate-vs-too-tight. Alternative: just assert `len(caplog.records) >= 1` for warn mode. I lean toward the message-string check because the silent-downgrade attack surface is "log-line gone but mode still says warn."

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
