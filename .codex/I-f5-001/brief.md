# Codex Brief Review — I-f5-001 (ITER 2 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 2 of 5.**
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg".
- If iter 5 returns REQUEST_CHANGES, force-APPROVE.
- Verdict APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

**Issue:** I-f5-001 — Hover-highlight every claim sentence
**Phase:** 1 / **Feature:** F5
**LOC budget:** 150 net per breakdown. **CHARTER §1 hard cap: 200.**

## Iter-1 verdict consumed

- P1 (production wiring required, not demo-only): RESOLVED iter 2 — wire `useSentenceHover` directly into `web/app/generation/components/verified_report_view.tsx`. Add `data-sentence-id` to each `<li>` (per `SentenceItem`) and apply `bg-yellow-100 dark:bg-yellow-900/40` highlight when hovered. Test asserts on real `/generation` flow OR a minimal harness that mounts VerifiedReportView with a synthetic VerifiedReport prop.
- P2 (deterministic random sentence in test): RESOLVED iter 2 — test uses index 7 (deterministic mid-range) instead of random; comment explains "any non-zero index proves the hook iterates over all sentences."

## Substrate (HONEST at HEAD)

- `web/app/generation/components/verified_report_view.tsx:62-86` `SentenceItem` renders each sentence as `<li>`. Add data-sentence-id + className conditional on hover state.
- `VerifiedReport.sections[*].verified_sentences` is the source for sentence ids; use sentence index per section as the id (e.g. `${section_id}:${idx}`).

## Approach

**Part 1 — `web/lib/sentence_highlight.ts`** (NEW, ~50 LOC):
- `useSentenceHover(opts: { selector?: string; debounceMs?: number; rootRef?: RefObject<HTMLElement> })`
- React hook: ref-attached mouseover/mouseleave + IntersectionObserver tracking visible sentences (rootMargin "0px"); debounces hover updates by `debounceMs` (default 50).
- Returns `{ hovered_id: string | null, root_ref: RefObject<HTMLDivElement> }`.

**Part 2 — `web/app/generation/components/verified_report_view.tsx`** (EDIT, ~25 LOC):
- Wire `useSentenceHover()`; root_ref attached to outermost `<div>`.
- `SentenceItem` receives optional `hovered_id` prop; if `hovered_id === id`, append `bg-yellow-100 dark:bg-yellow-900/40` className.
- Each `<li>` gets `data-sentence-id={`${section.section_id}:${idx}`}`.

**Part 3 — `web/tests/e2e/sentence_hover.spec.ts`** (NEW, ~50 LOC):
- Mount minimal VerifiedReportView via existing `/generation` route OR a new `/sentence_hover_test` harness route that constructs a synthetic VerifiedReport with 10 sentences.
- Hover sentence at index 7 (deterministic); assert it gets `bg-yellow-100` class within 200ms.
- Hover sentence at index 3; assert index 7 loses highlight + index 3 gains it.

## Acceptance criteria (binding)

1. `web/lib/sentence_highlight.ts` NEW.
2. `web/app/generation/components/verified_report_view.tsx` EDIT — wired hook + data-sentence-id + conditional highlight class.
3. `web/tests/e2e/sentence_hover.spec.ts` NEW — 2 hover-transition tests (deterministic index 7, then 3).

## Planned diff shape

```
web/lib/sentence_highlight.ts                 NEW +55
web/app/generation/components/verified_report_view.tsx  EDIT +25
web/tests/e2e/sentence_hover.spec.ts          NEW +60
```

LOC: +140 net. Under breakdown 150 budget by 10; under CHARTER §1 200-cap by 60.

## Out of scope

- Click → Inspector pane → I-f5-002.
- Source span highlighting → I-f5-003.

## Risks for Codex Red-Team

1. **IntersectionObserver browser support** — modern browsers only.
2. **`set-state-in-effect` lint rule** — hover state set in event handlers (mouseover/mouseleave + debounced setState in handler), NOT synchronously in useEffect body. Effect just attaches/detaches listeners + returns cleanup.
3. **Suspense not needed** (no useSearchParams in this component).
4. **Debounce cleanup on unmount** via clearTimeout in effect cleanup.
5. **Test harness route** — minimal `/sentence_hover_test/page.tsx` + `_demo.tsx` Client mounting VerifiedReportView with synthetic 10-sentence report. Avoids needing a real generation run for the test.
6. **§9.4 N/A frontend.**
7. **CHARTER §1 LOC cap.** 140 net.
8. **No new package dep.**

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
