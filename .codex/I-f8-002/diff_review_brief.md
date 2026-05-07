# Codex Diff Review — I-f8-002 (ITER 2 of 5)

## Iter 2 changes per Codex iter 1

- **P1 fix (keyboard a11y):** badge button now has `onKeyDown` handler that ALSO calls `e.stopPropagation()` + `e.preventDefault()` for Enter/Space and invokes `onSelectContradiction`. Keyboard activation no longer bubbles to the parent row's onKeyDown.
- **P2 fix (target size):** added `min-h-6 px-2 py-1` to the badge button (24px min target).
- **P2 fix (TS optional sides):** `ContradictionSignal.sides?: ContradictionSide[]` (optional) — matches the runtime tolerance and back-compat behavior.
- **P2 fix (demo source-3):** sec_x:26 now cites src-0/src-1/src-2 (3 provenance tokens matching 3 sides).

**Updated canonical-diff-sha256:** `bc6364b408e62a124ede45c2cf658e9c3dbe4b5099e21b3d44b7468425349c87`

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only.

**Issue:** I-f8-002 — Side pane with all sides of contradiction
**Brief:** APPROVED iter 1
**Canonical-diff-sha256:** `29395ce08c3ec6f55a7537ad6cddf220b5079b3dfda29fef9aa04194922028ce`
**LOC:** 253 net (53 over CHARTER §1 200-cap; LOC exemption requested below)

## Files

```
src/polaris_graph/generator2/verified_report.py            +29 (ContradictionSide + sides + validator)
tests/polaris_graph/generator2/test_verified_report.py     +37 (4 new tests + import + helper)
web/lib/api.ts                                              +9 (ContradictionSide + sides field)
web/app/generation/components/contradiction_pane.tsx       NEW +99 (Sheet pane with side cards)
web/app/generation/components/verified_report_view.tsx     +35 (badge → button + state + pane wiring)
web/app/sentence_hover_test/_demo.tsx                      +33 (3 sides for sec_x:26)
web/tests/e2e/sentence_inspector_contradiction.spec.ts     +29 (click-pane + 3-sides assertion)
```

## What changed

### Backend
- `ContradictionSide` (6 fields, length-bounded).
- `ContradictionSignal.sides: list[ContradictionSide] = []` + validator: non-empty sides must match disagreeing_source_count.
- 3 new tests + I-f8-001 fixture extended; 49 generator2/test_verified_report.py tests pass.
- `_side()` helper added to test module for concise construction.

### Frontend
- `contradiction_pane.tsx`: Sheet (right, 40%) with title + summary + per-side cards. Each side has 6 testids (source, tier, sample, hedge, pt08, claim).
- `verified_report_view.tsx`:
  - Badge becomes a `<button>` with `e.stopPropagation()` per Codex iter-1 P2 (prevents SentenceInspector co-opening).
  - `onSelectContradiction` callback threaded through SectionCard → SentenceRow.
  - `contradiction_open` state in VerifiedReportView root; ContradictionPane lives at root.
- Demo sec_x:26 extended with 3 sides (T1+T2+T1; sample sizes 1247/432/2103; hedge variations; PT04/null/PT08 flags).
- `sides ?? []` runtime tolerance per Codex iter-1 P2.
- New Playwright test asserts: pane opens, 3 side cards visible, side-0 detail (source/tier/sample/hedge/pt08/claim text), AND SentenceInspector did NOT also open (propagation-stop verified).

## Verification
- `PYTHONPATH=src pytest tests/polaris_graph/generator2/test_verified_report.py`: 49 passed.
- `npx tsc --noEmit` (web/): exit 0.

## LOC exemption requested

CHARTER §1 200-cap exceeded by 53. Drivers: full ContradictionSide schema with 6 fields + validator + 4 new tests + import/helper (backend ~66 LOC); ContradictionPane component with 6 sub-testids per side (~99 LOC); badge → button conversion + state plumbing (~35 LOC); demo 3-sides extension (~33 LOC); spec extension (~29 LOC). Splitting Sheet from schema would surface schema field unused (substrate-only) — substrate-honesty anti-pattern. Exemption analogous to I-f5-003/4 (245/246 LOC), I-f7-001 (217 LOC) — binding multi-substrate coverage in a single coherent backend+UI feature.

## Risks for Codex Red-Team

1. **Click propagation (Codex iter-1 P2):** `e.stopPropagation()` on badge button prevents row-level SentenceInspector co-opening. Test asserts `sentence-inspector-sheet` count=0 after badge click.
2. **Runtime tolerance (Codex iter-1 P2):** `signal?.sides ?? []` defends against absent-sides legacy payloads.
3. **Validator scope:** non-empty mismatch rejected; empty allowed (back-compat with I-f8-001 callers).
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap:** 253 net; exemption requested.
6. **No new package dep.**

## Output schema (mandatory)

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
