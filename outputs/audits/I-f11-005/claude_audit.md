# Claude architect audit — I-f11-005

## Issue scope

F11 multi-turn: 5 sequential follow-ups grounded correctly.

## What landed

`src/polaris_graph/followup/multi_turn.py` — `TurnResult` dataclass and `run_multi_turn(agent, parent_contract, follow_ups)` driver. Each turn flows through `compose_with_inheritance_or_refuse`; `TurnResult` carries exactly one of `composed`/`refusal` plus `inherited_spans` (empty for refused turns).

5 tests including the named "5 sequential in-scope follow-ups all grounded" with explicit `parent_run_id` + `inherited_template` + `inherited_evidence_ids` lineage assertion per turn (P2 hardening from brief review).

## Architectural alignment

- **Plan F11:** multi-turn is the final substrate for F11 follow-up support. Combines I-f11-001 (agent), I-f11-003 (inheritance), I-f11-004 (refusal).
- **CLAUDE.md §9.1 invariant 2 (provenance):** every accepted turn pass-through asserts via `merge_evidence_pool` that all 6 SourceSpan fields preserved.
- **§9.4 hygiene:** clean.
- **CHARTER §3 LOC:** 152 net.

## Verdict

Ready to merge. 28/28 followup tests green (23 prior + 5 new). Codex brief APPROVE iter 1; Codex diff APPROVE iter 1.
