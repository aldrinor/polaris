# Codex M-59 audit

**Verdict**: CONDITIONAL-no-blockers

## Answers

1. Structured consumption: Yes. Completion, gap detection, and payload sanity are driven from `SlotFillPayload` structure, not freeform prose. The `[entity_id]` check is acceptable because it validates a machine-readable render token in final prose, not semantic prose heuristics. `_GAP_MARKER in prose` is acceptable for now, but it is the one remaining template-coupled check and should ideally come from shared render metadata or a shared renderer constant.
2. Per-entity verdict granularity: Sufficient for M-60 as written. `SlotAggregateVerdict.entity_verdicts` already carries the full per-entity detail; `overall` as first failure is enough for gating and summary. Only add richer aggregate fields if M-60 explicitly needs precomputed pass/fail counts instead of deriving them.
3. Gap-slot requirements: Requiring both explicit gap disclosure and `[entity_id]` is correct. The exact `_GAP_MARKER = "was not retrievable"` literal is too coupled to the current renderer wording; keep the requirement, but do not duplicate the English phrase locally long-term.
4. Min-fields resolution layer: Right layer. `ReportContract.RequiredEntity.min_fields_for_completion` is the completion-policy source of truth; `ContractOutline` is structural and does not own thresholds.
5. Check order: Agree. Missing payload, then payload mismatch, then gap/non-gap checks with first-failure short-circuit is appropriate for deterministic gate semantics. Enumerating every failure per entity is unnecessary unless downstream UI needs multi-cause diagnostics.
6. Payload mismatch fail mode: Yes. `FAIL_PAYLOAD_MISMATCH` is the correct defensive verdict for slot/entity cross-wire conditions.
7. Defensive dead code: The `entity is None` branch is likely invariant-defense code, not a normal reachable path under M-57. I would keep it. The broader "contract entity omitted from outline" case is not checked here because iteration is outline-driven; if that invariant is ever in doubt, add an explicit outline-vs-contract completeness check rather than relying on this branch.
8. Entity-type-agnostic: Yes. There is no `entity_type` branching in the validator, and the statute + `dft_primary` tests are enough to show the logic is threshold-driven rather than type-driven.
9. Determinism: Yes. The function is pure and order comes from the outline traversal. `test_same_inputs_yield_same_report` is enough at this layer; add multi-entity ordering tests only if outline ordering has been unstable elsewhere.
10. Anti-fabrication division of concerns: Right division. M-58 should own value/source-span authenticity; M-59 should own completion, payload sanity, and render-coverage checks. Re-validating frame-row consistency here would duplicate upstream logic and widen the validator API for little gain.

## Findings

- Nit — `src/polaris_graph/generator/slot_validator.py:125`, `src/polaris_graph/generator/slot_validator.py:260`: gap validation is hard-coupled to the English fragment `"was not retrievable"`. That is the only remaining non-structured render dependency. If M-60 changes gap wording without updating this constant, valid gap slots will false-fail. Prefer a shared renderer constant/token or structured render metadata.

## Next

Claude proceeds to M-60. Targeted audit test run passed: `python -m pytest tests/polaris_graph/test_m59_slot_validator.py -q` (`18 passed`).
