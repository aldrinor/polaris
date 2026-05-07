# Codex Diff Review — I-f8-003 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only.

**Issue:** I-f8-003 — F8 adversarial: same-source self-contradiction
**Brief:** APPROVED iter 1
**Canonical-diff-sha256:** `9861fbaf7d5544b00724c8885d5b27dc19060b9fc690a05a230ee6642df772ae`
**LOC:** 167 net (under CHARTER §1 200-cap)

## Files

```
src/polaris_graph/generator2/verified_report.py            +37 (ContradictionKind + kind field + multi-clause validator)
tests/polaris_graph/generator2/test_verified_report.py     +56 (5 new tests; covers Codex iter-1 P2 zero/one-side gap)
web/lib/api.ts                                              +3 (ContradictionKind + kind?: field)
web/app/generation/components/verified_report_view.tsx     +13 (kind-discriminated badge text per Codex iter-1 P2 — sides.length not count)
web/app/generation/components/contradiction_pane.tsx       +9 (kind-discriminated pane title)
web/app/sentence_hover_test/_demo.tsx                      +35 (sec_x:27 self-contradiction)
web/tests/e2e/sentence_inspector_contradiction.spec.ts     +27 (badge + pane assertion for sec_x:27)
```

## What changed

### Backend
- `ContradictionKind` Literal: `multi_source` (default) | `self_contradiction`.
- `kind: ContradictionKind = "multi_source"` field added.
- Validator replaces simple `len(sides) == count` with kind-discriminated rules:
  - `multi_source`: count≥2, sides-length matches when non-empty.
  - `self_contradiction`: count==1, sides≥2, all sides reference same source_id.
- `disagreeing_source_count` lower-bound relaxed from 2→1 to allow self-contradiction.
- 5 new tests: default kind, valid self-contradiction, count-not-1 rejected, sides-too-few rejected (Codex iter-1 P2 gap), different-sources rejected.
- 54 generator2/test_verified_report.py tests pass.

### Frontend
- `ContradictionKind` type + optional `kind?: ContradictionKind`.
- Badge text: self-contradiction shows "Source self-contradicts (N spans)" using `sides.length` (Codex iter-1 P2: NOT `disagreeing_source_count` which is 1 for self-contradiction).
- Pane title: "Self-contradiction: source contradicts itself across N spans" vs "Contradiction: N sources disagree".
- Demo sec_x:27 with self-contradiction case (src-0 says safe AND dangerous).
- New Playwright test asserts badge text + pane title + both sides reference src-0 + claim text "safe"/"dangerous".

## Verification
- `PYTHONPATH=src pytest tests/polaris_graph/generator2/test_verified_report.py`: 54 passed.
- `npx tsc --noEmit` (web/): exit 0.

## Risks for Codex Red-Team

1. **Validator scope:** kind-discriminated rules; existing I-f8-001/002 fixtures use multi_source → unaffected.
2. **Backward compat:** `kind` defaults to `multi_source` in Pydantic AND TS `?:`; older payloads behave as before.
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** 167 net. Under 200.
5. **No new package dep.**

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
