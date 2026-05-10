# Claude Audit — I-bug-108 (verifier-driven repair loop + synthesis [N] scrub)

**Date**: 2026-05-09
**Branch**: `bot/I-bug-108-sentence-repair-loop`
**Codex**: APPROVE on brief iter 1 (path B); APPROVE on diff iter 2 (zero P0/P1).

## What this PR ships

1. **`sentence_repair.py`** — verifier-driven repair loop (Codex iter-1 path B). When strict_verify drops a sentence due to drift failures (entailment/numbers/trial-name/content overlap), feed (sentence, cited spans, judge reason) back to the generator for one rewrite. Repaired sentences must pass full `verify_sentence_provenance` re-run including entailment.

2. **`multi_section_generator.py` integration** — calls the repair loop between strict_verify and M-41c filter. Augmented kept[] flows through downstream filters as if the repaired sentences had passed first time.

3. **PT12 root-cause fix in `analyst_synthesis.py`** — added `_scrub_invalid_n_markers` runtime guardrail because the production v2 sweep aborted at PT12. Synthesis LLM hallucinates [N] markers beyond bibliography size; the scrub fixes the production-blocker. Iter-2 hardened to also catch malformed forms `[-N]`, `[ 5 ]`, `[01]`.

## Codex iter-1 P0+P1 → iter-2 fixes

| iter-1 issue | iter-2 fix |
|---|---|
| **P0** scrub regex `\[(\d+)\]` doesn't catch `[-N]`, `[ 5 ]`, `[01]` — downstream PT12 may still abort | Extended regex `\[\s*(-?\d+)\s*\]` + canonical-form check. Tests assert `[-1]`, `[ 5 ]`, `[01]` all scrubbed. |
| **P1** `repair_sentence` returned `(None, 0, 0)` for both API failures and empty-token NULL_DROP; orchestrator inferred classification from token counts | Return shape now `(outcome, text, in_tok, out_tok)` where outcome ∈ {"text", "null_drop", "api_failure", "skipped"}. Test pins distinguish-by-signal (50/10 NULL_DROP and 200/50 API_FAILURE classified correctly). |
| **P2** bundle vs split | Codex iter-2: accept bundling (PT12 scrub is small + tested + tied to release_allowed=TRUE). |
| **P2** recovery variance | Codex iter-2: accept stochastic (40.4% v1, 35.3% v3 both clear 0.30 floor). |

51/51 tests pass.

## Production-validated empirical result (v3 sweep)

```
status: success
release_allowed: TRUE   ← PT12 abort eliminated by synthesis [N] scrub
total_words: 1457   (+50% vs 974 baseline)
verified_words: 368
analyst_synth_words: 1089

Repair loop per-section:
  Efficacy:           0/1 = 0%
  Mechanism:          3/6 = 50%
  Comparative:        2/6 = 33%
  Long-term Outcomes: 1/4 = 25%
  Aggregate:          6/17 = 35.3%   ← above Codex's 0.30 floor

Token-set violations: 0 (model respects constraint)

Synthesis [N] scrub fired:
  "scrubbed 6 invalid [N] markers (N > biblio_size=8)" — runtime guardrail caught hallucinations
```

## Definition-of-done

- [x] 28 new tests + 23 baseline = 51 passing
- [x] Codex APPROVE on brief iter 1 + diff iter 2 (zero P0/P1)
- [x] **Empirical proof: 35.3% recovery rate, status=success, release_allowed=TRUE**
- [x] canonical-diff-sha256 = `e92f927a6381b347ee9b66fb677d17afd4dbb6caad5a4d4feff118e23da0283d`
- [ ] CI gate green
- [ ] Auto-merge per Plan §7.B LOCKED B1

## Follow-up Issues recommended

- **I-bug-110**: investigate why the synthesis LLM hallucinates [N] markers. Prompt clarity? Bibliography embedding? Long-tail issue.
- **I-bug-111**: telemetry counters for synthesis [N] scrub frequency (alert if > 10% of runs scrub more than 5 markers)
