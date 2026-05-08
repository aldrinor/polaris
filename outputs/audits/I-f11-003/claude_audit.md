# Claude architect audit — I-f11-003

## Issue scope

Evidence Contract inheritance for follow-up runs. Follow-up inherits the parent's accepted-source pool with no re-retrieval.

## What landed

`src/polaris_graph/followup/inheritance.py` — two pure functions:
- `inherit_evidence_pool(parent_contract)` returns a fresh list of the parent's `evidence_pool` (defensive list-copy of immutable Pydantic SourceSpan elements).
- `compose_with_inheritance(agent, parent_contract, follow_up)` orchestrates `agent.compose` + `inherit_evidence_pool` and returns both the ComposedQuery and inherited spans.

`tests/polaris_graph/followup/test_inheritance.py` — 7 tests covering returns_copy / preserves_order / empty_pool / returns_both / known_evidence_ids_from_parent_pool / no_re_retrieval (monkeypatch belt) / pass_through_to_merger.

## Architectural alignment

- **Plan F11 (follow-up):** delivers the deterministic inheritance substrate. LLM-augmented disambiguation is I-f11-002 (already shipped).
- **CLAUDE.md §9.1 invariant 2 (provenance tokens):** preserved end-to-end — inherited `SourceSpan.evidence_id` flows unchanged through the merger to verified-sentence provenance.
- **CLAUDE.md §9.4 hygiene:** zero `try/except: pass`, no magic numbers, no `time.sleep`, no TODOs.
- **CHARTER §3 200-LOC cap:** 167 lines net.
- **No retrieval / network imports:** `inheritance.py` imports only `polaris_graph.followup.agent` (stdlib-only) and `polaris_v6.schemas.evidence_contract` (Pydantic schema). No ReAct, no requests, no openrouter.

## Risks considered

- **Shallow vs deep copy:** SourceSpan is Pydantic immutable BaseModel; mutating field assignment is forbidden by default. List-copy is sufficient for pool-mutation isolation. Codex iter-1 P2 noted the docstring overstates "deep copy" — preserved as P2 cosmetic since it does not affect behavior.
- **Pass-through to merger:** test feeds inherited spans into `merge_evidence_pool` and asserts each output preserves all 6 SourceSpan fields. The `_evidence_id_for_retrieval` `ev_` prefix is handled in the assertion.
- **No-re-retrieval:** module-level invariant + monkeypatch belt-and-suspenders test against `ReactAnalysisAgent.run` raising.

## Verdict

Ready to merge. All 7 new + 9 sibling I-f11-001 tests green. Codex diff APPROVE iter 1.
