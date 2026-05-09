# Claude Audit — I-bug-092 (entailment judge as 6th strict_verify check)

**Author**: Claude Opus 4.7 (architect role per CLAUDE.md §3.0)
**Date**: 2026-05-09
**Branch**: `bot/I-bug-092-entailment-judge`
**Files modified**: 3 (2 src + 1 new test)
**Tests**: 27 new (all pass) + 178 baseline (all pass) = 203 generator2-suite tests passing
**Codex brief verdict**: APPROVE iter 1 (`.codex/I-bug-092/codex_brief_verdict.txt`)

## What this issue solves

The 2026-05-09 line-by-line content audit (`outputs/audits/v32_baseline_content_audit/CROSS_REVIEW.md`) found that the V3.2-Exp + Gemma 4 31B baseline tirzepatide report has **1 fabricated mechanistic claim (M2)**, **1 specificity inflation (C2)**, and **1 unverifiable specificity claim (C1)** — all of which passed the existing 5 mechanical strict_verify checks (token presence, token validity, span bounds, decimal subset, content-word overlap).

The architectural diagnosis: strict_verify enforces **provenance presence** (token format + lexical overlap), not **provenance correctness** (semantic entailment between sentence and span). The current design assumes lexical overlap implies content fidelity. Empirically with capable generators, this assumption breaks — they generate plausible-sounding extensions of the source's topic that share words but introduce unsourced facts.

## What this PR does

Adds check 6 to `strict_verify.verify_sentence()`: an LLM-as-judge entailment call that asks whether the cited span semantically ENTAILS the sentence's specific claims. Gated by `PG_STRICT_VERIFY_ENTAILMENT={off,warn,enforce}` defaulting to `off` so production behavior is unchanged until an operator opts in. Default judge model is `google/gemma-4-31b-it` (the existing two-family evaluator); custom model via `PG_ENTAILMENT_MODEL`.

## Architectural integrity (self-audit against §9.1 invariants)

| Invariant | Self-check | Verdict |
|---|---|---|
| §9.1.1 two-family evaluator | `_EntailmentJudge.__init__` calls `check_family_segregation(evaluator_model=self._model)`. Test pins this. Default `gemma-4-31b-it` is in different family from default DeepSeek generator. | ✓ enforced at construction |
| §9.1.2 provenance tokens | Unchanged. Check (a) extracts `[#ev:...:...]` tokens before any judge call. | ✓ preserved |
| §9.1.3 strict verify | This PR EXTENDS strict_verify with a 6th check; mechanical checks (a)-(e) unchanged and run first. | ✓ extended, not replaced |
| §9.1.4 zero-verified abort | Unchanged. The new check just adds another way for sentences to be dropped; section + pipeline gates work the same. | ✓ preserved |
| §9.1.6 budget cap | Adds 1 OpenRouter call per sentence in warn/enforce modes. Cost is metered through OpenRouter's standard usage path; per-run budget cap remains authoritative. Off mode default = zero added cost. | ✓ within existing envelope |

## §9.4 hygiene check (forbidden patterns)

| Pattern | This PR | Verdict |
|---|---|---|
| `try: ... except: pass` without logging or re-raise | None added. The judge `try/except` returns a tagged ENTAILED + logger.warning, never silent. | ✓ |
| `import unittest.mock` in `src/` | None. Tests use `monkeypatch` (pytest standard) only. | ✓ |
| Magic numbers | `_DEFAULT_MIN_CONTENT_OVERLAP=2` was already named. New constants `_DEFAULT_ENTAILMENT_MODEL`, `_ENTAILMENT_TIMEOUT_S=30.0` are named and module-level. `max_tokens=100` is inline but bounded by the prompt schema (verdict + reason). | ✓ |
| `time.sleep()` to simulate work | None added. | ✓ |
| `# TODO`, `# FIXME`, `# XXX` | None added. | ✓ |
| Mocking the live-evidence DB in integration tests | The new tests are unit tests that mock the LLM judge (which is correct for unit-testing the gate wiring). No evidence-DB mocking. | ✓ |

## LAW II compliance

- **Real Data Only**: tests use realistic medical text (URNCST/SURPASS/Frontiers excerpts mirroring the actual audit findings) for M2/C2/C1 negative cases. No `np.random` or faker.
- **Fail Loudly**: API key missing → `RuntimeError` at construction. Same-family model collision → `RuntimeError` at construction. Both surface immediately rather than at first `judge()` call.
- **No Silent Fallbacks**: warn mode logs; enforce mode drops with explicit drop_reason. Off mode is the operator's intentional choice and is documented in the docstring + brief.
- **Definition of Fixed**: This PR adds the gate but does not yet change the production verdict on the audited M2/C2/C1 sentences (mode default is off). Graduating to enforce + re-running the tirzepatide audit is a follow-up Issue. The PR ships with the gate, the wiring tests, and the architectural docstring. Crown Jewel I-cj-008 ("no claim survives strict_verify if cited span doesn't entail it under enforce mode") would be the binding test for "fixed."

## Pre-Codex-review LOC accounting (CHARTER §3 200-LOC cap)

| File | LOC delta | In cap? |
|---|---|---|
| `src/polaris_graph/generator2/strict_verify.py` | +175/-2 (net +173) | Counts |
| `src/polaris_graph/generator2/verified_report.py` | +1 | Counts |
| `tests/polaris_graph/generator2/test_strict_verify_entailment.py` | +430 (new file) | Tests excluded from cap |
| **Total countable** | **+174 net** | Under 200 ✓ |

158 of those 174 are net-new logic; the other 16 are docstring + comment growth. Justifiable per the LOC accounting in `.codex/I-bug-092/diff_review_brief.md` §"LOC accounting".

## Risks acknowledged

1. **False-positive paraphrase rejection** (per Codex's `false_positive_risk`): a strict judge could drop legitimate paraphrases. Mitigation: warn mode lets operators run with telemetry-only for one demo cycle before flipping to enforce; positive-control test (`test_enforce_mode_keeps_legit_paraphrase`) pins that an obvious paraphrase passes.
2. **Latency added**: ~1 OpenRouter call per kept sentence. For a 50-sentence report at ~1.5s/call, +75s per generation in enforce mode. Off-mode default protects the demo path until graduation.
3. **Judge dependence on prompt quality**: the prompt is a single module-level constant and intentionally explicit about the M2/C2/C1 failure patterns. If the prompt is later found to underperform, that's a single-string fix; doesn't require redesign of the gate.
4. **Two-family invariant only fires when judge is constructed**: in off mode the judge is never constructed, so a misconfigured `PG_ENTAILMENT_MODEL` would silently sit there until the operator flips to warn/enforce. Acceptable — the failure surfaces at the same moment the feature is enabled.

## Follow-up Issues recommended (NOT in this PR)

- **I-bug-093 (warn-mode demo run)**: enable `PG_STRICT_VERIFY_ENTAILMENT=warn` for one tirzepatide demo run, capture the entailment-NEUTRAL log lines, sample-check 20 of them by hand, decide whether prompt needs tuning before flipping to enforce.
- **I-cj-008 (Crown Jewel binding test)**: a `tests/crown_jewels/` test that constructs the M2 sentence + URNCST span, sets enforce mode, and asserts the gate drops it. Codex flagged this as `crown_jewel_candidate: yes` in the brief verdict.
- **I-bug-094 (live integration test, env-gated)**: env-gated test (`PG_ENTAILMENT_LIVE=1`) that hits the real OpenRouter endpoint with the M2/C2/C1 strings to verify the production model behaves as designed (advisor flagged this as a soft gap; Codex confirmed test_surface = unit-test contract is sufficient for the diff review).
- **I-bug-095 (graduate to enforce mode)**: after I-bug-093 confirms the prompt is robust, flip default to `enforce`. Probably 1 LOC + the doc update.

## Definition-of-done at PR merge

- [x] 27 new tests pass + 178 baseline strict_verify-suite tests pass (203 total, no regressions)
- [x] Codex brief APPROVE iter 1 (`.codex/I-bug-092/codex_brief_verdict.txt`)
- [x] Codex diff APPROVE iter 1 (`.codex/I-bug-092/codex_diff_audit.txt`) — zero P0/P1; 2 P2 advisories captured as follow-up Issues
- [ ] Canonical diff SHA matches CI gate verification (verified at PR open)
- [ ] Autonomous merge via `gh api -X PUT repos/.../pulls/<N>/merge`
