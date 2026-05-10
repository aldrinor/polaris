# Codex Brief — I-bug-105 (two-layer report: verified core + labeled analyst synthesis)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings.
- "Don't pick bone from egg".
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
- DO NOT call exec / rg / shell tools. Brief is self-contained.
```

## Context

Per your strategic-review iter 1 verdict, recommended sequence is **D (floor) + B (repair) + A (bakeoff) + G (decomposition)**. This issue starts on **D — two-layer report contract**.

The empirical baseline (post-I-bug-098): POLARIS produces ~14 verified sentences, ~974 words, all per-sentence span-verified. Frontier DR systems produce ~5000 words but without the audit guarantee. The two-layer architecture preserves POLARIS's faithfulness wedge while closing ~50% of the narrative_length gap.

Your iter-1 directive on this path: "Ship a two-layer report contract: verified audit core plus explicitly labeled analyst synthesis."

## What this PR ships

### Architecture

```
Existing pipeline → MultiSectionResult { section prose with [#ev:...] tokens, all per-sentence verified }
                  + Limitations { telemetry-grounded }
                  + Trial Summary { table }
                  + Trial Timeline { table }

NEW (I-bug-105):
                  + Analyst Synthesis { LLM-written narrative, NOT per-sentence verified }
                       └─ takes the verified prose + bibliography + evidence pool as context
                       └─ writes ~1500-3000 words of interpretive synthesis
                       └─ uses [N] bibliography references but NOT [#ev:...] tokens
                       └─ explicitly hedged: "consistent with verified findings...", "these results are typically interpreted as..."
                       └─ rendered in report.md under a clearly labeled section header
```

### Report.md structure (after this PR)

```markdown
# Research Report: <question>

## Verified Findings
*Every claim below is verifiable in its cited span by an independent
two-family LLM judge. 0 fabrications under audit.*

[the existing 14 verified sentences, with [N] citation markers]

## Analyst Synthesis
*Interpretive expert commentary drawing on the verified findings and
cited evidence. Sentences in this section are NOT individually
span-verified; they synthesize, hedge, and contextualize the audit
core for narrative readability.*

[1500-3000 words of analyst-style narrative referencing [N] cite markers]

## Limitations
[existing limitations paragraph]

## Trial Summary
[existing table]
```

The two-layer disclosure is the load-bearing element: readers see EXACTLY what is span-verified vs. interpretive.

## Implementation surface

### New module

`src/polaris_graph/generator/analyst_synthesis.py` — ~150 LOC
- `ANALYST_SYNTHESIS_SYSTEM_PROMPT` — instructs the LLM to write interpretive narrative drawing on the verified prose + evidence pool, NEVER asserting unsupported facts, ALWAYS hedging when going beyond the verified core
- `async def generate_analyst_synthesis(verified_prose, bibliography, evidence_rows, model, max_tokens, temperature) -> tuple[str, int, int]` — single LLM call, returns (text, in_tokens, out_tokens)
- Fallback on error: returns empty string (the report still ships with verified core only)

### Integration points

`src/polaris_graph/generator/multi_section_generator.py`:
- Add `analyst_synthesis_text: str = ""` and `analyst_synthesis_input_tokens: int = 0` and `analyst_synthesis_output_tokens: int = 0` to `MultiSectionResult` dataclass
- After `lim_text` is generated (line ~3500-ish), add a parallel call to `generate_analyst_synthesis()` using the verified prose joined across kept sections
- Populate the new fields in the final `return MultiSectionResult(...)`

`scripts/run_honest_sweep_r3.py`:
- After the report.md is emitted with the verified prose, append a new "## Analyst Synthesis" section with `MultiSectionResult.analyst_synthesis_text` (with the hedged-disclosure preamble)
- Update manifest.json to record `analyst_synthesis_words` and `analyst_synthesis_input_tokens` / `analyst_synthesis_output_tokens`

### What's IMPORTANT to get right

1. **The disclosure preamble** before the synthesis section MUST be explicit: readers should never confuse synthesis prose with span-verified prose. Codex iter-1 "two-layer report contract" hinges on this.

2. **The synthesis prose should NOT carry [#ev:...] tokens** — only [N] bibliography references. This is intentional: [#ev:...] tokens are POLARIS's audit-grade signal; using them in the synthesis would dilute their meaning.

3. **The synthesis should NOT introduce facts NOT supported by the evidence pool** — but it also should NOT be required to be per-sentence verified. The hedge: "these results are typically interpreted as..." / "the literature suggests..." / "in clinical practice, this profile is consistent with...".

4. **The synthesis SHOULD reference the verified findings** by saying things like "the verified data above show X; clinically, this is consistent with..."

5. **Pipeline should still ship a valid report if synthesis fails** — fallback: empty `analyst_synthesis_text`, report.md just omits that section.

## Tests pinned

- `test_analyst_synthesis_called_after_verified_prose` — ensure synthesis fires after multi_section completes
- `test_analyst_synthesis_text_appended_to_report_md` — ensure report.md has the labeled section
- `test_analyst_synthesis_failure_does_not_break_report` — empty synthesis, report.md still ships with verified core
- `test_analyst_synthesis_no_ev_tokens_in_output` — [#ev:...] should NOT appear in synthesis prose (regex check)
- `test_analyst_synthesis_disclosure_preamble_present` — the labeled disclosure header must appear
- `test_manifest_records_analyst_synthesis_word_count`

## What I want from you

1. **Verdict** APPROVE / REQUEST_CHANGES on the design.
2. **Disclosure preamble wording** — is "Interpretive expert commentary drawing on the verified findings and cited evidence. Sentences in this section are NOT individually span-verified; they synthesize, hedge, and contextualize the audit core for narrative readability." sufficient? Too verbose? Missing key disclosure?
3. **Should synthesis use the same generator (DeepSeek V3.2-Exp) or the evaluator (Gemma 4 31B)?** My read: DeepSeek (consistent with verified prose voice; Gemma is the judge, not the writer). But the two-family invariant doesn't apply because synthesis isn't span-verified.
4. **Should synthesis attempt sub-section structure** (e.g., "Mechanism interpretation", "Comparative considerations", "Clinical implications") OR a single flowing narrative? Single flow is simpler; sub-sections may be more readable.
5. **Cost budget**: each synthesis call is ~$0.005-0.010. Acceptable per-run? Or bound it?
6. **Acceptance criteria** for the experiment: when we re-run BEAT-BOTH after this PR, what numbers should we see to call it a success? My target: narrative_length doubles to ~2000-3000, jurisdictional_precision stays stable, 0 BEHIND-BOTH dimensions becomes ≤2 BEHIND-BOTH.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
disclosure_wording: <as-is | suggested rewrite>
synthesis_generator_recommendation: deepseek_v32 | gemma_4_31b | other
sub_section_structure: yes | no
cost_budget_recommendation: <number or "no cap">
acceptance_criteria_target: <description>
extra_concerns: [...]
loc_estimate_ok: yes | no
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
rationale: <2-3 sentences>
```
