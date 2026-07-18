# 0017. Ship every new layer behind a flag, default-OFF byte-identical, fail-loud

Status: accepted

Date: 2026-06-07

## Context

POLARIS was migrating a large architecture (credibility weighting, consolidation, disclosure) across many phases. A risky rewrite was off the table; the codebase already had a proven pattern for reversible, surgical change (`credibility_weighted_sourcing_redesign_plan_2026_06_07.md` §4; `pipeline_redesign_master_plan.md` §5).

## Decision

Each new layer ships behind a flag. Default-OFF produces byte-identical output and byte-identical rendered artifacts. Each layer fails loud when its inputs are missing. Disclosure SCHEMA ships first as inert plumbing; population lands later.

A cross-cutting guardrail rides along: on a frozen fixture, the count of distinct citable sources reaching composition is monotonically non-decreasing as each drop-knob is converted, and the faithfulness verdict is byte-identical before and after every wave.

## Consequences

- Every phase gets a trivially-true faithfulness-safety argument: OFF means byte-identical, so the phase cannot change grounding. That is a mechanical safety proof per step, not a hope.
- This yields three properties at once: self-contained phases under the 200-LOC review cap (ADR 0023), the "no silent downgrade" guarantee, and reversibility.
- The trade is more scaffolding up front — schema-first inert plumbing, flags, frozen-fixture checks — in exchange for a migration that can be paused, reverted, or shipped one wave at a time.
- The monotonic-source and byte-identical-verdict checks are the mechanical gate that proves a wave did not quietly lose sources; keep them in CI for every wave.
