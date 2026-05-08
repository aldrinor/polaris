# Codex Diff Review — I-f11-004 (ITER 1 of 5)

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

- **Issue:** I-f11-004 — Refusal handling for out-of-scope follow-ups.
- **Brief APPROVE iter 2.** `.codex/I-f11-004/codex_brief_verdict.txt`.
- **Net LOC:** 178 (under 200).
- **Branch:** `bot/I-f11-004`.

## What changed

1. `src/polaris_graph/followup/refusal.py` (NEW, 56 LOC):
   - `RefusalDecision` frozen dataclass.
   - `detect_out_of_scope(parent_template, follow_up, *, min_overlap=1)` — `general` bypasses; otherwise zero shared keyword tokens triggers refusal.
   - `compose_or_refuse(agent, parent, follow_up)` — routes through `detect_out_of_scope` first.
2. `src/polaris_graph/followup/inheritance.py` (MODIFY, +25 LOC net):
   - New `compose_with_inheritance_or_refuse(agent, parent_contract, follow_up)`. Returns `(RefusalDecision, [])` on out-of-scope; `(ComposedQuery, inherited_spans)` otherwise.
3. `tests/polaris_graph/followup/test_refusal.py` (NEW, 97 LOC, 7 tests):
   - `test_refuses_zero_overlap_specific_template` (adversarial — "sky blue" vs `clinical_summary`)
   - `test_accepts_one_keyword_overlap` (`summary` shared)
   - `test_general_template_never_refuses`
   - `test_compose_or_refuse_returns_composed_when_in_scope`
   - `test_compose_or_refuse_returns_refusal_when_out_of_scope`
   - `test_adversarial_punctuation_and_case` ("WHAT ABOUT THE SUMMARY?!")
   - `test_compose_with_inheritance_or_refuse_routes_refusal` — both refused and accepted inheritance paths.

## Test results

```
$ pytest tests/polaris_graph/followup/ -q
collected 23 items
test_agent.py .........        [ 39%]
test_inheritance.py .......    [ 69%]
test_refusal.py .......        [100%]
============= 23 passed in 2.78s =============
```

## Risks for Codex Red-Team

1. **Heuristic quality.** Exact-token overlap is naive. Single-token templates over-refuse. Documented as MVP debt in module docstring.
2. **`compose_with_inheritance_or_refuse` separate function** preserves `compose_with_inheritance` (I-f11-003) backward-compatible — callers can opt-in to refusal.
3. **§9.4 hygiene.** No `try/except: pass`, no magic numbers (`min_overlap=1` is a named keyword arg with explicit comparison), no `time.sleep`, no TODO, no `unittest.mock` import.
4. **CHARTER §3 LOC cap.** 178 net (under 200).
5. **Adversarial test (issue acceptance)** — `test_refuses_zero_overlap_specific_template` is the explicit named test.

## Acceptance criteria — forced enumeration

1. ✅ `src/polaris_graph/followup/refusal.py` with `detect_out_of_scope` + `compose_or_refuse`.
2. ✅ Inheritance path routed through refusal via `compose_with_inheritance_or_refuse`.
3. ✅ Refusal returns typed `RefusalDecision` with explanation `reason`.
4. ✅ 7 tests pass (1 adversarial + inheritance route).
5. ✅ CHARTER §3 LOC cap (178 ≤ 200).

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

## Diff for review

(Full diff appended below.)
