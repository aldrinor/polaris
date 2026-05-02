M-5 v2 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-5 v1 verdict: PARTIAL with 3 issues. All 3 integrated in v2.

## What changed

1. **classifyCoverageStatus(status, entry)** — entry-aware:
   - `fail_min_fields` → `gap` only if `provenance_class` is
     `frame_gap_unrecoverable`/`gap` OR `available_artifacts` is empty
   - Otherwise → `partial`
   - The summary bar and per-row severity now agree.

2. **slot_id surfaced**:
   - Visible chip on every row: `<span class="coverage-row-slot">slot
     {slot_id}</span>`
   - `data-slot-id` attribute on `<li>` for stable selectors
   - `polaris:resolve-gap` CustomEvent detail expanded:
     `{entity_id, slot_id, status, section, subsection_title}`

3. **required vs retrieved chips differentiated**:
   - Visible label column ("required" / "retrieved") in mono, fixed width
   - `.coverage-chip-required` — dashed border, transparent bg
   - `.coverage-chip-retrieved` — filled accent-soft bg, accent text

Tests: 129 → 135 (4 router + 2 browser). Browser test verifies the
full event detail object after click.

## Your job

Quick verification pass. Verdict: GREEN / STILL-PARTIAL / DISAGREE.

Spot-check:
- All 3 fixes integrated?
- Status classifier really distinguishes partial?
- Slot context flows through to the event?
- Visible label differentiation?
- Any new issues?
- M-6 ready?

## Output

Write to `outputs/codex_findings/m5_v2_review/findings.md`:

```markdown
# Codex re-review of M-5 v2

## Verdict
GREEN / STILL-PARTIAL / DISAGREE

## Fix integration
- [x/no] Status classifier distinguishes partial from gap
- [x/no] slot_id surfaced + included in CustomEvent detail
- [x/no] required vs retrieved chips visibly differentiated

## New issues
none / list

## Final word
GREEN to lock M-5 / STILL-PARTIAL with edits.
```

Be terse. Under 100 lines.
