# Claude architect audit — I-f11-004

## Issue scope

Refusal handling for out-of-scope follow-ups. Acceptance: adversarial test demonstrating refusal-with-explanation.

## What landed

- `src/polaris_graph/followup/refusal.py` — `RefusalDecision` dataclass, `detect_out_of_scope` (template `_`-keyword overlap heuristic), `compose_or_refuse` orchestrator.
- `src/polaris_graph/followup/inheritance.py` — new `compose_with_inheritance_or_refuse` routes inheritance (I-f11-003) through refusal first; preserves backward-compat `compose_with_inheritance`.
- `tests/polaris_graph/followup/test_refusal.py` — 7 tests including adversarial "sky blue", case/punctuation, `general`-template bypass, inheritance route.

## Architectural alignment

- **Plan F11:** out-of-scope detection is the next step after deterministic inheritance (I-f11-003). LLM-augmented intent matching is post-MVP per docstring.
- **CLAUDE.md §9.4 hygiene:** zero `try/except: pass`, no magic numbers (`min_overlap=1` is named keyword arg), no `time.sleep`, no TODO.
- **CHARTER §3 200-LOC cap:** 178 net.
- **No retrieval / network imports:** `refusal.py` imports only stdlib (`re`, `dataclasses`) + `polaris_graph.followup.agent`.

## Risks considered

- **Heuristic over-refusal** for single-token templates documented as MVP debt; production templates use multi-token slugs.
- **Backward compat:** `compose_with_inheritance` (I-f11-003) preserved unchanged; `compose_with_inheritance_or_refuse` is opt-in.

## Verdict

Ready to merge. 23/23 followup tests green (16 prior + 7 new). Codex brief APPROVE iter 2; Codex diff APPROVE iter 1.
