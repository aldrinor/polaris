You are auditing M-40 pass-2 as a code review. Pass-1 verdict was
READY-with-mediums; pass-2 addresses the material medium (title
visibility to the outline LLM). Narrow scope.

## Pass-1 verdict summary

Pass-1 (your prior audit, findings.md):
- READY, zero blockers.
- Medium #1 (addressed in pass-2): rule triggered on "title or
  snippet" but `_call_outline` only sent `statement[:160]` to
  the LLM — under-firing risk when mechanism term lived only in
  title.
- Medium #2 (deferred, noted in commit): 3-row threshold could
  be permissive on large corpora.
- Medium #3 (cosmetic): rule placement wording mismatch in
  commit message.

## Pass-2 diff

1. `_call_outline` summary block (multi_section_generator.py lines
   ~393-414) now includes the title (truncated to 120 chars,
   sanitized), formatted:
     "ev_id [tier] | title: truncated_title | statement[:160]"
   Rows without a title fall back to the pre-pass-2 format.
2. OUTLINE_SYSTEM_PROMPT M-40 rule body reworded:
     old: "evidence rows whose title or snippet mentions ..."
     new: "evidence rows in the summary above ... in either the
           `title:` field or the statement body"
   The rule now references the actual format the LLM sees.
3. Two new tests:
   - `test_outline_prompt_includes_title_when_present` (inspects
     source for title read in summary builder)
   - `test_rule_mentions_title_field`

## Pass-2 smoke test (stricter)

Live DeepSeek V3.2-exp. Evidence subset where mechanism vocabulary
appears ONLY in titles (not statements) — the exact scenario your
pass-1 audit flagged. Result: outline picked
`['Mechanism', 'Efficacy', 'Safety', 'Regulatory']` with Mechanism
first. Confirms the trigger now fires reliably on title-only
content.

## Files to read

```
src/polaris_graph/generator/multi_section_generator.py
  - `_call_outline` summary-building block (lines ~390-416)
  - OUTLINE_SYSTEM_PROMPT M-40 rule (lines ~162-166)
tests/polaris_graph/test_m40_mechanism_section.py
  - `TestM40OutlineSummaryIncludesTitle` class (NEW)
```

## What to verify

1. **Title inclusion is safe**. Adding title to each evidence
   summary row increases prompt size by ~60-150 chars per row.
   For a 325-row corpus that's ~20K extra tokens. Is this within
   DeepSeek V3.2-exp's comfortable context window? (128K limit;
   the outline prompt still fits comfortably.)

2. **Sanitization coverage**. Title is now run through
   `sanitize_evidence_text` same as statement. Is there any
   prompt-injection surface specific to title content (e.g. a
   malicious title containing <<<evidence:...>>> delimiter)? The
   sanitizer should catch delimiter escapes; confirm it's applied
   before the title lands in the summary block.

3. **Rule-source alignment**. Does the reworded rule ("either the
   `title:` field or the statement body") accurately describe
   what the LLM sees? Compare against the new format string
   `"{ev_id} [{tier}] | title: {title_clean} | {stmt_clean}"`.

4. **Backwards compatibility**. Evidence rows without a title
   still work (fall back to pre-pass-2 format). Any consumer of
   `_call_outline` that assumed a specific summary format?
   (Outline is internal to this module; the only caller is
   `generate_multi_section_report`; the LLM prompt is what
   consumes the summary, not downstream code.)

5. **No new format-string hazards**. The summary block uses
   f-strings; any `{}` literal in title/statement content is
   escaped by sanitize_evidence_text? If sanitize doesn't handle
   `{`/`}`, an evidence row with literal braces in its title
   could interfere with `.format()` downstream — but the outline
   system prompt is passed as `system=`, not through `.format()`,
   so this is not a live risk.

## What counts as a blocker vs medium

- **BLOCKER**: prompt-injection via malicious title content that
  bypasses sanitize; sudden prompt-size blowup on a realistic
  325-row corpus that exceeds DeepSeek context; any test that
  fails under pass-2.
- **MEDIUM**: title truncation strategy (120 chars may be too
  aggressive / conservative); title sanitization could be
  lighter-touch for better LLM interpretability.
- **LOW**: style / wording.

## Deliverable

Write `outputs/codex_findings/m40_code_audit_pass2/findings.md`
with:
- Final verdict (READY | BLOCKED | CONDITIONAL)
- Blockers (zero if READY)
- Mediums
- One-sentence note on whether pass-2 closes the pass-1 medium
  #1 as described.
