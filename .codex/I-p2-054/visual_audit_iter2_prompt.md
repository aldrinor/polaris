# Codex VISUAL audit — I-p2-054 (#855) Compare, A++/S bar — iter 2 of 5

You have VISION. iter-1 was REQUEST_CHANGES (result_desktop A- / result_mobile A- / picker A- /
empty A). P1: left/right pickers were visually indistinguishable (the fixture's two runs share
template+question and the id was truncated off the end); the result didn't show WHICH runs. P2:
mobile stat cramped.

## Fixes applied (this iter)
- optionLabel now LEADS with the unique run id + completion date: "run-tirzep-001 · May 21 ·
  clinical_efficacy · <question…>" — so two runs sharing a template/question are still
  distinguishable (id never truncates off the end).
- The result headline now shows the compared PAIR explicitly: "run-tirzep-001 ↔ run-tirzep-002"
  (mono) above the % stat.
- Mobile: the "% shared evidence" stat stacks (percent over caption) below sm.

## Attached
1. cmp_result_desktop  2. cmp_result_mobile  3. cmp_picker_desktop  4. cmp_empty_desktop

## Locked / do NOT flag
- Brand #c8102e (Compare button + nav active only). Fixture visual-audit-only. LIVE-populated
  verification DEFERRED. Evidence-id chips + frame names are real fields.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
per_screen_grades: { result_desktop: "", result_mobile: "", picker: "", empty: "" }
novel_p0: [...]
continuing_p0: []
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```
APPROVE iff zero P0/P1 (run identity now unambiguous in picker + result).
