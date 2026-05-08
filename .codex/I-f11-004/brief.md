# Codex Brief Review — I-f11-004 (ITER 2 of 5)

## Iter 2 changes per Codex iter 1

- **P1-I1-001 fix (test phrase tokenization):** `Summarize` ≠ `summary` under naive split-and-lowercase. Adjusted test phrase to contain the exact token. `test_accepts_one_keyword_overlap` now uses `"What about the summary statistics?"` (`summary` shared with `clinical_summary`).
- **P1-I1-002 fix (route inheritance through refusal):** added `compose_with_inheritance_or_refuse` wrapper in `inheritance.py` that delegates to `compose_or_refuse` first; if refused, returns `RefusalDecision`; if not, delegates to `compose_with_inheritance`. New test asserts inheritance path also refuses out-of-scope follow-ups.
- **P2-I1-001 (single-token template over-refusal):** documented in module docstring as MVP calibration debt; not blocking.

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-f11-004 — Refusal handling for out-of-scope follow-ups. Out-of-scope follow-up → refusal-with-explanation. Acceptance: adversarial test. LOC estimate 90.
- **Substrate today:** I-f11-001 + I-f11-002 + I-f11-003 shipped. `FollowUpAgent.compose` raises `ValueError` only on blank input. There is no out-of-scope detection layer.
- **Honest framing per CLAUDE.md §9.4:** ship a deterministic substrate that flags out-of-scope follow-ups via a heuristic (template-name keyword overlap with the question) and returns a typed refusal explanation. NOT an LLM-augmented refusal — that is post-MVP.

## Plan

### `src/polaris_graph/followup/refusal.py` (NEW, ~60 LOC)

1. `@dataclass(frozen=True) class RefusalDecision`: fields `is_refused: bool`, `reason: str | None`, `template_keywords: list[str]`, `question_overlap: list[str]`.
2. `def _tokenize_template(template: str) -> list[str]`: split on `_`, lowercase, drop empty.
3. `def _tokenize_question(question: str) -> list[str]`: lower → strip punctuation via simple regex `[^a-z0-9 ]` → split → drop empty.
4. `def detect_out_of_scope(parent_template: str, follow_up: str, *, min_overlap: int = 1) -> RefusalDecision`:
   - Special-case: `parent_template == "general"` → `is_refused=False`.
   - Compute keyword/question token sets; intersection = `template_keywords ∩ question_words`.
   - If `len(intersection) < min_overlap` → `is_refused=True` with reason describing the missing overlap.
   - Else `is_refused=False`.
5. `def compose_or_refuse(agent: FollowUpAgent, parent: ParentRunContext, follow_up: str) -> ComposedQuery | RefusalDecision`:
   - Calls `detect_out_of_scope(parent.template, follow_up)`.
   - If refused, returns the `RefusalDecision`.
   - Else delegates to `agent.compose(parent, follow_up)`.
6. Module docstring documents MVP calibration debt for single-token templates.

### `src/polaris_graph/followup/inheritance.py` (MODIFY, +20 LOC)

1. New `compose_with_inheritance_or_refuse(agent, parent_contract, follow_up)` wrapper:
   - Builds `ParentRunContext` from `parent_contract` (same as `compose_with_inheritance`).
   - Calls `compose_or_refuse(agent, parent, follow_up)` first.
   - If `RefusalDecision` returned, returns `(refusal, [])` — no inherited spans for refused queries.
   - Else (got a `ComposedQuery`), proceeds with `inherit_evidence_pool` and returns `(composed, inherited_spans)`.

### Tests `tests/polaris_graph/followup/test_refusal.py` (NEW, ~80 LOC, 7 tests)

1. `test_refuses_zero_overlap_specific_template` — template `clinical_summary`, follow-up `"Why is the sky blue?"` → refused.
2. `test_accepts_one_keyword_overlap` — template `clinical_summary`, follow-up `"What about the summary statistics?"` → not refused (`summary` shared exactly).
3. `test_general_template_never_refuses` — template `general`, follow-up `"random topic"` → not refused.
4. `test_compose_or_refuse_returns_composed_when_in_scope` — typical in-scope case → returns `ComposedQuery`.
5. `test_compose_or_refuse_returns_refusal_when_out_of_scope` — out-of-scope → returns `RefusalDecision` with `is_refused=True` and `reason` populated.
6. `test_adversarial_punctuation_and_case` — template `clinical_summary`, follow-up `"WHAT ABOUT THE SUMMARY?!"` → not refused (case lowered, punctuation stripped).
7. `test_compose_with_inheritance_or_refuse_routes_refusal` — out-of-scope follow-up to inheritance path returns RefusalDecision; in-scope returns ComposedQuery + inherited spans.

## Risks for Codex Red-Team

1. **False positive refusals.** Heuristic is exact-token match. Anyone using a single template-keyword (case-insensitive, exact) gets through.
2. **Template-name design coupling.** Documented as MVP calibration debt for single-token templates.
3. **§9.4 hygiene.** No `try/except: pass`, no magic numbers (`min_overlap=1` is a named keyword arg), no `time.sleep`, no TODO.
4. **CHARTER §3 LOC cap.** ~140 LOC net (60 src/refusal + 20 src/inheritance + 80 tests). Under 200.
5. **Adversarial test (issue acceptance):** `test_refuses_zero_overlap_specific_template` + `test_compose_with_inheritance_or_refuse_routes_refusal`.

## Acceptance criteria

1. New `src/polaris_graph/followup/refusal.py` with `detect_out_of_scope` and `compose_or_refuse`.
2. `inheritance.py` extended with `compose_with_inheritance_or_refuse` so the I-f11-003 inheritance path routes through refusal.
3. Refusal returns a typed `RefusalDecision` carrying the explanation reason.
4. 7 tests pass (including 2 adversarial / route-coverage tests).
5. CHARTER §3 LOC cap respected (≤200 net).

**Forced enumeration:** before verdict, write one line per criterion 1-5.
**Completeness check:** list files actually read.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
