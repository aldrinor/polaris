# Codex Diff Review — I-f7-001 (ITER 2 of 5)

## Iter 2 changes per Codex iter 1

- **P1 fix #1 (Playwright runtime ReferenceError):** dropped `Node.DOCUMENT_POSITION_PRECEDING` reference; ordering check now uses `firstElementChild.getAttribute("data-testid")` inside `page.evaluate`. Asserts the panel is the first-child of `verified-report-view` (stricter above-the-fold semantics per Codex iter-1 P2).
- **P1 fix #2 (scope honesty):** this Issue ships **schema + UI surface ONLY**. The live generator path does NOT yet populate `frame_coverage` — that's the substrate target for a future Issue (I-f7-003 candidate or earlier integration with the heritage `frame_manifest.py` M-60 pipeline). Demo page is the only render path today. Honest framing per CLAUDE.md §9.4 + substrate-honesty memory: schema field exists, UI consumer exists, real-data wiring deferred to next Issue. **No silent overclaim** — `report.frame_coverage ?? null` produces no panel for live reports until populator wires in.
- **P2 fix (degenerate empty case):** total=0 → render null (no misleading amber panel for 0/0/[] coverage).

**Updated canonical-diff-sha256:** `ac10abe9ba388890b9fef61d9f7c3a2bd0812a3385e0f91c1bbe71cc8243c2bb`

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only.

**Issue:** I-f7-001 — Top-of-report frame coverage panel
**Brief:** APPROVED iter 1
**Canonical-diff-sha256:** `d658cd26dc3f58a884692a2ce1237101ca17afc8a441c7f648082d27de4252a7`
**LOC:** 217 net (17 over CHARTER §1 200-cap; LOC exemption requested below)

## Files

```
src/polaris_graph/generator2/verified_report.py             +47 (FrameGap + FrameCoverage + field)
tests/polaris_graph/generator2/test_verified_report.py      +25 (4 new tests)
web/lib/api.ts                                              +12 (FrameGap + FrameCoverage interfaces)
web/app/generation/components/frame_coverage_panel.tsx      NEW +84 (3 visual states + progress + gap list)
web/app/generation/components/verified_report_view.tsx      +2 (panel above report card)
web/app/sentence_hover_test/_demo.tsx                       +12 (frame_coverage 14/15 + 1 gap)
web/tests/e2e/frame_coverage_panel.spec.ts                  NEW +35 (2 tests, ordering check + content)
```

## What changed

### Backend
- `FrameGap`: entity_name + reason (length-bounded).
- `FrameCoverage`: covered + total + gaps; validator rejects covered>total AND covered+len(gaps) != total.
- `VerifiedReport.frame_coverage: FrameCoverage | None = None` — optional; existing fixtures stay valid.
- 4 new schema tests (no-gaps minimal, with-gaps passes, count-mismatch rejected, covered-exceeds-total rejected).
- 40 generator2/test_verified_report.py tests pass.

### Frontend
- `FrameCoveragePanel`: 3 visual states (null = nothing, all-covered = emerald, has-gaps = amber).
- Progress bar with `total>0` guard per Codex iter-1 P2 (no NaN%).
- Gap-count summary `frame-coverage-gap-count` per Codex iter-1 P2 ("1 gap" / "N gaps").
- Each gap row gets `frame-coverage-gap-{idx}` testid with `<entity_name> — <reason>`.
- `verified_report_view.tsx`: renders `<FrameCoveragePanel>` ABOVE the existing report Card.
- Demo: 14 covered / 15 total / 1 gap (Pediatric population, no Cochrane review).
- Playwright: content + DOM-position assertion (panel must NOT come AFTER verified-report-view) per Codex iter-1 P2.

## Verification
- `PYTHONPATH=src pytest tests/polaris_graph/generator2/test_verified_report.py`: 40 passed.
- `npx tsc --noEmit` (web/): exit 0.

## LOC exemption requested

CHARTER §1 200-cap exceeded by 17. Drivers: 3 visual states (success / gaps / null) each requiring discrete styling + testids; backend Pydantic model needs explicit validator with two clauses; 4 backend tests cover validator branches. Splitting Panel from validator across PRs would surface the schema field unused (substrate-only) — exactly the substrate-honesty anti-pattern. Exemption analogous to I-f5-003 (245 LOC granted) and I-f5-004 (246 LOC granted) — binding multi-substrate coverage in a single coherent backend+UI feature.

## Risks for Codex Red-Team

1. **Optional field back-compat:** `frame_coverage?: ... | null` on TS, default None on Pydantic — older payloads render no panel.
2. **Validator exhaustiveness:** rejects both covered > total AND count mismatch; allows degenerate empty (0/0/[]).
3. **DOM ordering test:** `compareDocumentPosition` asserts Panel does NOT come AFTER verified-report-view. Robust to either above-the-fold (siblings, panel first) or panel-nested-inside-rv (FC contained by RV).
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap:** 217 net; exemption requested.
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
