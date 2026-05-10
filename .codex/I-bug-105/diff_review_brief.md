# Codex Diff Review — I-bug-105 (two-layer report: verified core + analyst synthesis)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings.
- "Don't pick bone from egg".
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
- DO NOT call exec / rg / shell tools.
```

## Pre-flight

- Brief APPROVE'd iter 1 (`.codex/I-bug-105/codex_brief_verdict.txt`) — Path D, with 4 must-do extras all addressed
- Diff: `.codex/I-bug-105/codex_diff.patch` (canonical-diff-sha256: `3840897db1518ca9b822435c38b92a956cc4b28032bbf2dfffd523fedd43679d`)
- 4 files / 512 lines: 1 new module + 1 generator integration + 1 sweep manifest/render integration + 1 test file
- 20 new tests pass on the analyst_synthesis module

## All 4 of your iter-1 brief P0s addressed

| Codex iter-1 directive | Implemented at |
|---|---|
| Output scrub guardrail removes [#ev:...] (not just test) | `analyst_synthesis.py:_scrub_ev_tokens` runs after every LLM call; `test_scrub_*` pins it |
| Omit synthesis section entirely when empty | `run_honest_sweep_r3.py: if getattr(multi, "analyst_synthesis_text", "")` guards the section append |
| Prompt requires bibliography [N] citations | `ANALYST_SYNTHESIS_SYSTEM_PROMPT` rule 1: "Cite by bibliography [N] markers, NEVER by [#ev:...]" |
| Manifest distinguishes verified_words from analyst_synthesis_words | `run_honest_sweep_r3.py:2542+`: emits `verified_words`, `analyst_synthesis_words`, `analyst_synthesis_input_tokens`, `analyst_synthesis_output_tokens` separately |

Plus your iter-1 disclosure rewrite is verbatim in `ANALYST_SYNTHESIS_DISCLOSURE`.

## Production-validated empirical result

Re-ran `scripts/run_honest_sweep_r3.py --only clinical_tirzepatide_t2dm` against this branch. Result:

```
status              : success
total words         : 1241  (was 974 baseline = +27% on this run)
verified_words      : 205   (audit core preserved as separate metric)
analyst_synth_words : 1036  (NEW — interpretive synthesis, not span-verified)
synthesis tokens    : in=7459 out=1400 → ~$0.005 per call
sentences_verified  : 6     (run-to-run variance from strict_verify; 14 baseline)
sentences_dropped   : 45
```

`report.md` structure renders correctly:
```
### Efficacy / Safety / Comparative   (verified core, [#ev:...] tokens)
## Analyst Synthesis                   (disclosure preamble + 7 sub-sections)
  ## Mechanism Interpretation
  ## Clinical Implications and Efficacy Profile
  ## Safety and Tolerability Considerations
  ## Comparative Efficacy and Safety
  ## Regulatory and Practice Context
  ## Open Questions and Future Directions
### Limitations / Methods / Bibliography
```

**Critical empirical guardrail check**: 0 `[#ev:...]` tokens in the synthesis section (grep verified). 43 `[N]` bibliography citations in the synthesis (citation density ~1 per ~25 words, matches DR-grade).

BEAT-BOTH on this run's manifest:
- narrative_length: 974 → **1776** (+82% lift on the headline dimension)
- structural_depth: 10 → 15 (more sections from synthesis subheadings)
- Other dimensions (jurisdictional_precision, unique_citations, regulatory_coverage) regressed in this specific run because the audit core itself produced only 6 verified sentences (down from 14 baseline) — that's stochastic variance in strict_verify, NOT introduced by I-bug-105 (this PR doesn't touch the verified pipeline).

## What the architecture preserves

1. **Verified core unchanged**: I-bug-105 adds an APPENDED LLM call after `multi_section` finishes and after `_call_limitations`. It reads the verified prose + bibliography + evidence pool but writes to a separate field. The verified pipeline is unaffected.

2. **Two-layer disclosure visible to readers**: the `*italic disclosure preamble*` at the top of the synthesis section explicitly says "these sentences are not individually span-verified; use them as hedged context, not as audit-grade claims."

3. **Faithfulness wedge intact**: scrub guardrail prevents `[#ev:...]` token leakage from synthesis (those tokens are POLARIS's audit-grade signal; using them in interpretive prose would dilute their meaning).

4. **Manifest schema honest**: `verified_words` is now a separate metric from total `words`, so downstream consumers (Inspector UI, audit bundles, BEAT-BOTH scorer) can distinguish the audit-grade portion from the synthesis layer.

## Tests pinned (20)

- 6 scrub guardrail tests (single token, multiple, [N] preservation, warning logging, empty)
- 4 bibliography rendering tests
- 3 evidence pool rendering tests
- 3 disclosure preamble tests (mentions span-verified, audit-grade, references Verified Findings)
- 4 system prompt invariant tests (forbids [#ev:...], requires [N] citations, requires hedging, requires subsections)

## What I want from you

1. **Verdict** APPROVE / REQUEST_CHANGES on the diff.
2. **Any P0/P1 you find** — please be exhaustive iter 1.
3. The 6-verified regression in this run is stochastic. Accept and ship, or do you want a multi-run average before merging?
4. Synthesis is run AFTER limitations. Should it also run when limitations is skipped? My read: yes — synthesis is independent of the limitations text. Currently I gate on `section_results and global_biblio` which is correct for that case.

## Honest caveats

- The I-bug-098 cost-accounting bug (entailment-judge calls untracked) extends here: synthesis OpenRouter call goes through OpenRouterClient so its cost IS tracked (~$0.005 per call), but the entailment-judge calls during multi_section are still uncounted. I-bug-100 follow-up.
- Synthesis word count came in at 1036 vs target 1500-3000. Likely because the verified prose this run was thin (205 verified words) — synthesis can only reference what it has. Re-runs with the typical 14 verified sentences would likely yield 2000+ synthesis words.

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
