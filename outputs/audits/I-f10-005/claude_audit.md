# Claude architect audit — I-f10-005

**Issue:** Chart provenance schema
**Branch:** bot/I-f10-005
**Canonical-diff-sha256:** 19d7ae9127f58a3e7c4c72268c073739698e51438e39138b182e967a0280bae6
**Brief verdict:** APPROVE iter 1 (0/0/0/3 — all 3 P2 fixes applied in diff)
**Diff verdict:** APPROVE iter 1 (0/0/0/0, accept_remaining)

## Substrate honesty
- New `ChartProvenance` Pydantic model formalizes the contract that `spec_builder.build_*` already emits as dicts. Consumer-side schema; no builder changes needed.
- Codex iter-1 P2 fixes applied: `extra="forbid"` (strict schema lock), `field_validator` rejects blank evidence_id strings, `validate_chart_provenance` rejects non-dict containers with clean error message.
- Cross-field validator: timeline ⇔ period_kind locks existing builder behavior.
- 11 tests cover 3 valid round-trips + 8 adversarial cases. All pass locally (1.39s).
- LAW II honest fallback: every error path raises with descriptive message.

## §9.4 N/A backend.

## CHARTER §1 LOC cap
- 175 net. Under 200.

## Verdict
APPROVE.
