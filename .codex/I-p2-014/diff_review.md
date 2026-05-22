# Codex BRIEF+DIFF review — I-p2-014 (#753): intake honest design-polish

HARD ITERATION CAP: 5. iter 1. Canonical-diff-sha256 `12410a393c3bed13cb59ca6035ef8485cbda5205b2eb5646d983a01442b7e116`. web/ only. MERGE AUTHORIZED if mergeable. APPROVE iff zero P0/P1.

## HONEST scope (recorded on #753 after grounding the backend)
The breakdown title says "just-ask + auto-detected domain + source-set control". GROUNDED FINDING: `IntakeScopeDecision` (api.ts:579, the intake's actual response) has NO `intended_source_tiers` (that's only on the separate `ScopeDecision`, api.ts:340, unused by intake). So neither a source-set CONTROL nor tier transparency is backend-backed → building either = fabrication (the #752 overclaim lesson). The intake ALREADY does just-ask + auto-detected clinical scope_class (efficacy/safety/diagnosis/prognosis, shown in scope_decision_view). So the honest, buildable #753 = a design-system polish.

## Diff (intake_form.tsx)
- Replaced the hardcoded-rose error `Card` (border-rose-500/40 bg-rose-500/5 text-rose-700) with the #750 `ErrorState` (design-system --destructive tokens + role=alert + specific message). Kept the just-ask form, sample chips, auto-detected scope display, honest clinical framing.

## Claude visual audit (standalone @1366, sent to operator): clean frontier-minimal intake, honest clinical framing, Canada-red CTA. (Shell nav still carries "no external AI vendor" — pre-existing overclaim tracked for #762, not this issue.)

## Review focus
1. HONESTY: correct NOT to fake a source-set control / tier transparency (no backend field)? Any remaining overclaim?
2. ErrorState swap clean (no unused Card imports left — Card still used by the question card)? a11y (role=alert)?
3. Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
