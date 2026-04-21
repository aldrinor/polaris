You are auditing M-32 (Fix B: primary-study claim-frame prompt rule)
as a code review BEFORE V22 sweep runs. Narrow scope.

## Scope discipline (user mandate, reconfirmed)

Audit ONLY the M-32 diff (commit `2a3a621`). This is a
PROMPT-RULE addition — rule #12 in
`SECTION_SYSTEM_PROMPT_TEMPLATE`. No executable code changes.
No new helpers. No new state.

Do NOT invent probe patterns. If you find a real defect, cite
the specific line(s) you believe are defective with the rule's
actual text.

## Context

Codex DR pass 10 verdict on V21: LOSE_BOTH on "claim frames".
Specifically:

> The check is whether each named trial gives N + baseline HbA1c +
> baseline weight + primary endpoint. V21 gives efficacy numbers
> but not N, baseline HbA1c, baseline weight, and primary endpoint
> for each trial; SURPASS-1/-3/-4/-6 are compressed into one
> efficacy paragraph...

M-32 adds a prompt instruction to fix this.

## Changes

1. `src/polaris_graph/generator/multi_section_generator.py`:
   - New rule #12 after M-29 rule #11 in
     `SECTION_SYSTEM_PROMPT_TEMPLATE`.
   - Content: instructs the generator to emit the FULL FRAME
     (sample size N, baseline outcome value, comparator, primary
     endpoint + timepoint) in the first sentence that introduces
     a primary study.
   - Template example uses placeholder tokens ([STUDY NAME],
     [COMPARATOR], [OUTCOME]) with domain-agnostic examples.
   - References materials, cohort studies, financial filings as
     non-clinical applications.

2. `tests/polaris_graph/test_m32_claim_frame_prompt.py`:
   - 11 tests covering rule presence, required components
     (N/baseline/comparator/endpoint/timepoint), template
     placeholder, generalization (non-clinical domains),
     hard-coding guard (no drug names in rule text).

## Your task

1. Read rule #12 as it appears in the template. Does it clearly
   and completely specify the FULL FRAME components the Codex
   pass-10 verdict called for?
2. Read the example template in the rule. Is it actionable for a
   generator model? Are the placeholders clear?
3. Generalization: confirm the rule reads as domain-agnostic
   (mentions materials, cohort studies, financial filings
   explicitly; no drug names in rule text).
4. Test suite: are the 11 tests adequate? Do they actually verify
   the rule enforces what Codex pass-10 asked for?
5. Non-regression: M-27 rule #10 and M-29 rule #11 must still be
   intact and numbered correctly.

## Out of scope

- Prompt-engineering style preferences (placement, ordering of
  numbered rules).
- Whether M-32 will empirically close the V21 claim-frame gap —
  that's the V22 sweep's job, not this audit's.
- M-33 / Fix C / Fix A — separately scheduled.

## Verdict format

Write `outputs/codex_findings/m32_code_audit/findings.md`:

```
# M-32 code audit

VERDICT: READY | NOT_READY

## Blockers
- <list or none>

## Mediums
- <list or none>

## Lows / nits
- <list or none>

## Notes
<any other observations>
```

If READY, V22 sweep launches. If NOT_READY, the blocker MUST cite
the specific line in rule #12 that is defective and explain why —
no hypothetical regression probes.

## Actual deliverable check

Read the rule text. Is it long enough to convey the instruction
without being so long it pushes other rules out of the model's
effective attention window? (The full SECTION_SYSTEM_PROMPT_TEMPLATE
now has 12 rules; confirm total length is still reasonable.)
