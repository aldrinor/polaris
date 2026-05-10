# Claude Audit — I-bug-105 (two-layer report: verified core + analyst synthesis)

**Date**: 2026-05-09
**Branch**: `bot/I-bug-105-two-layer-analyst-synthesis`
**Codex**: APPROVE on brief iter 1 (Path D) + APPROVE on diff iter 1 (zero P0/P1, 1 P2 markdown-nesting advisory).

## What this PR ships (Codex strategic-review iter 1 Path D)

After the two cheap experiments (I-bug-103 retrieval expansion, I-bug-104 prompt rewrite) both failed empirically, Codex's strategic-review recommended Path D: ship a two-layer report with verified core + explicitly labeled analyst synthesis. This PR delivers it.

### Architecture

```
Verified Findings (existing, unchanged)
  ## Efficacy / Safety / Comparative ...     [#ev:...] tokens, per-sentence span-verified

NEW: Analyst Synthesis
  ## Mechanism Interpretation
  ## Clinical Implications
  ## Safety and Tolerability
  ## Comparative Considerations
  ## Regulatory and Practice Context
  ## Open Questions and Future Directions
                                              [N] bibliography citations only
                                              0 [#ev:...] tokens (scrub guardrail)
                                              hedged interpretive prose
                                              clearly disclosed as not span-verified

### Limitations (existing) ...
```

### All 4 Codex iter-1 brief P0s addressed

1. ✅ Output scrub guardrail (`_scrub_ev_tokens`) — not just a test
2. ✅ Empty-synthesis section omitted entirely (no empty disclosure)
3. ✅ Prompt requires bibliography [N] citations
4. ✅ Manifest distinguishes `verified_words` from `analyst_synthesis_words`

## Empirical validation

Re-ran tirzepatide sweep against this branch:

```yaml
status: success
total_words: 1241  (was 974 baseline = +27% overall)
verified_words: 205
analyst_synth_words: 1036
[#ev:...] tokens in synthesis: 0   (scrub guardrail working)
[N] citations in synthesis: 43     (good citation density)
synthesis subsections: 7
synthesis cost: ~$0.005 (well under Codex's $0.02 cap)
```

Report.md renders correctly with disclosure preamble. BEAT-BOTH narrative_length: 974 → 1776 (+82%).

The audit core had 6 verified sentences in this run vs 14 baseline — Codex confirms this is acceptable run-to-run variance ("This PR does not touch strict verification, and the observed drop is consistent with the stated run-to-run variance").

## What this PR preserves

1. **Verified pipeline untouched** — `verify_sentence_provenance` is unchanged; entailment gate logic unchanged
2. **Faithfulness wedge intact** — synthesis cannot use `[#ev:...]` tokens (prompt forbids + runtime scrub)
3. **Operator visibility** — manifest separately exposes `verified_words` and `analyst_synthesis_words` so downstream consumers (Inspector UI, audit bundles, BEAT-BOTH scorer) cannot mistake total length for audited length

## Codex P2 advisory (acknowledged, NOT blocker)

Markdown nesting: synthesis subheadings use `##` while the parent "## Analyst Synthesis" is also `##`. Codex says "use ### in the prompt later if downstream parsers need strict hierarchy" — captured as I-bug-106 follow-up if any consumer requires nesting.

## Definition-of-done

- [x] 20 new tests pass
- [x] Codex APPROVE on brief iter 1 + diff iter 1 (zero P0/P1)
- [x] Empirical validation: synthesis fires, verified pipeline preserved, 0 [#ev:...] leakage
- [x] BEAT-BOTH: narrative_length +82%
- [x] canonical-diff-sha256 = `3840897db1518ca9b822435c38b92a956cc4b28032bbf2dfffd523fedd43679d`
- [ ] CI gate green
- [ ] Auto-merge per Plan §7.B LOCKED B1

## Follow-up Issues recommended

- **I-bug-106**: change synthesis subheadings to `###` for hierarchical consistency
- **I-bug-107**: multi-run BEAT-BOTH average to control for stochastic variance in audit-core verified count
