V30 Phase-2 M-66 fix plan v3 review — xhigh reasoning (pass-3).

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your pass-2 review at
`outputs/codex_findings/v30_m66_plan_review/pass2_findings.md`
returned CONDITIONAL-blockers (1 new blocker + 1 new medium +
2 partials). Claude revised at
`outputs/audits/v30_phase2/fix_plan_run3_v3.md`.

## Pass-2 issues + resolution claims

### Pass-2 new Blocker: ship rule inconsistent

**v3 claim**: **STRICT** gate adopted as canonical. Two labels:
- `BEAT_BOTH_SHIP` = ≥5/7 BB/BO AND **zero LB**
- `PHASE2_CHECKPOINT` = ≥4/7 ≥BO AND ≤1 LB AND zero regressions
- "ship with 1 LB" phrasing deleted

Run-3 honest projection (2 BB + 4 BO + 1 LB) explicitly labeled
as `PHASE2_CHECKPOINT`, not ship. Narrative-depth LB triggers
M-67 then run-4 for ship attempt.

**Verify**: Is the strict/checkpoint distinction operationally
unambiguous? Any scenario where a run-3 dimension could be
misread to shortcut to SHIP?

### Pass-2 new Medium: M-66b test seam

**v3 claim**: Mock `_fetch_url_pattern` / AccessBypass result
directly, NOT httpx.MockTransport. httpx mock reserved for
CrossRef/Unpaywall/PubMed branches (existing tests).

`TestOrchestratorRegulatoryUrlFetch` + `TestOrchestratorOaFullTextFetch`
both stub `_fetch_url_pattern` with deterministic return
`(content, final_url)`.

**Verify**: Is this the right seam? Or is there a purer seam
(AccessBypass class init argument) that avoids module-level
monkeypatching?

### Pass-2 Partial: Trial Summary real-content filter

**v3 claim**: Upgraded to concrete negative regression.
`test_trial_summary_rejects_truncated_comparator_fragments` with
specific patterns:
- `.*\sin adults with type\b` (truncated NEJM/Lancet boilerplate)
- endpoint in `{"—", "", None}`
- result contains no digit OR is just `"at week N"`

Validator in `_build_trial_summary` rejects rows matching any.
Acceptance: `≥6 rows AFTER validator`, not nominal.
Telemetry: `trial_summary_rows_rejected` count.

**Verify**: Are these patterns tight enough to reject the
observed bad rows without false-positiving legitimate SURPASS
rows? Specifically:
- "5 and 15 mg vs placebo" — legitimate, has digits ✓
- "open-label trial" — may be a legitimate comparator
  shorthand but has no digits → would be rejected. Is that
  right?

### Pass-2 Partial: Structure projection

**v3 claim**: Demoted to `PROBABLE BO`, not pre-booked BO.
Explicitly acknowledges new-bugs-possible risk.

**Verify**: Is `PROBABLE BO` an operationally-meaningful label?
Or is it still just "BO with asterisk"?

## Your specific pass-3 questions

1. Is the strict ship gate (`BEAT_BOTH_SHIP` = ≥5/7 ≥BO AND zero
   LB) correctly applied to the run-3 honest projection, so
   run-3 gets `PHASE2_CHECKPOINT` not `SHIP`?

2. Does the v3 `_fetch_url_pattern` test seam stub match the
   implementation detail? Should I re-write the seam spec
   before implementation?

3. Are the Trial Summary negative-regression patterns in v3
   both sufficient (reject observed bad rows) AND safe (don't
   false-reject legitimate rows)?

4. `PROBABLE BO` for Structure — is this a useful label or just
   uncertainty-theatre?

5. Any NEW blocker that emerged from v3?

6. Is there any reason NOT to implement v3 right now?

## Output

Write to
`outputs/codex_findings/v30_m66_plan_review/pass3_findings.md`.

```markdown
# V30 M-66 fix plan v3 review (pass 3)

**Verdict**: APPROVED | CONDITIONAL-no-blockers | CONDITIONAL-blockers | REJECT

## Pass-2 issue resolution

1. Ship rule inconsistency (pass-2 Blocker): RESOLVED | PARTIAL | NOT_RESOLVED
2. M-66b test seam (pass-2 Medium): ...
3. Trial Summary real-content filter (pass-2 Partial): ...
4. Structure projection (pass-2 Partial): ...

## Answers

1. Strict ship gate application: ...
2. Test seam spec: ...
3. Trial Summary patterns: ...
4. PROBABLE BO label utility: ...
5. New blockers: ...
6. Reason NOT to implement: ...

## Findings (new only)

## Next

On APPROVED / CONDITIONAL-no-blockers: Claude implements M-66
bundle. Otherwise: plan v4.
```

Under 150 lines. Full xhigh budget. This is the final plan-
review gate; approval unlocks implementation + run-3 launch.
