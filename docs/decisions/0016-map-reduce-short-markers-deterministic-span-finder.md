# 0016. In map-reduce distillation, emit short markers and let a deterministic span-finder compute offsets

Status: accepted

Date: 2026-06-17

## Context

The map-reduce distiller made every section EMPTY on the real model — `drop_rate` 1.00, a multi-week collapse (`keystone_collapse_forensic_consolidated.md`, #1217, committed 8d74d1bb). Root cause: the REDUCE step told the LLM to transcribe the final machine provenance token, including span offsets. The model's hand-typed offsets are then frozen and never re-fit, so they almost never match, and every sentence is dropped. The implementation had drifted from its own docstring, which already specified short markers.

Map-reduce is NOT incompatible with `strict_verify`. Only emitting the final `[#ev:id:start-end]` machine token FROM the LLM is incompatible — for the same reason as ADR 0001, a token-prediction model cannot be trusted to hand-type exact offsets.

## Decision

In the REDUCE step, cite each sentence with a short `[ev_XXX]` marker (the legacy contract) and drop span offsets from the ledger lines. Then the unchanged deterministic `_rewrite_draft_with_spans` / `_find_best_span_for_sentence` re-fits a prose-matched span designed to pass `strict_verify`.

The full machine token starts with `#`, which the marker regex ignores, so a hand-typed token would pass through unchanged with its frozen (wrong) offsets and gate off every rescue. The short marker avoids that trap.

## Consequences

- The span offset is computed deterministically after generation, never typed by the model, so it actually matches the source and the sentence survives verification.
- This restored non-empty sections and unblocked map-reduce distillation, which is what enables section-scale composition.
- General rule (shared with ADR 0001): whenever an exact machine token must survive a generation step, compute it deterministically; a distinctive `#`-prefixed token in the prompt is a landmine because the model will copy it and freeze bad offsets.
- Keep implementation and docstring in sync — the drift between them is what hid this bug for weeks.
