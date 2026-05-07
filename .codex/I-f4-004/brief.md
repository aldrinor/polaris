# Codex Brief Review — I-f4-004 (ITER 2 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg".
- If iter 5 returns REQUEST_CHANGES, force-APPROVE.
- Verdict APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

**Issue:** I-f4-004 — F4 adversarial: 80% fetch fail; strict_verify drops all
**Phase:** 1 / **Feature:** F4
**LOC budget:** 130 net per breakdown. **CHARTER §1 hard cap: 200.**

## Iter-1 verdict consumed

- P1 (`MAX_EVENTS=50` truncation skews derived counts): RESOLVED iter 2 — track cumulative counters as separate state INDEPENDENT of the panel arrays. Add `cumulative: { source_dropped, retrieval_candidate, verify_decision_kept, verify_decision_dropped }` state. Increment on every event (not affected by panel-array slice). Banner conditions use cumulative.
- P2 #1 (negative test must wait for events processed): RESOLVED iter 2 — normal-path test waits for `panel-verify_decision-count` to reach 5 BEFORE asserting banner absence.
- P2 #2 (parser must fail closed): RESOLVED iter 2 — `payload.kept === false` check wraps in `try/catch JSON.parse → false` (treats malformed as "not kept" for safe-default; banner trips conservatively).
- P2 #3 (verify_decision/kept vs verifier_verdict/pass naming): NOTED iter 2 — this Issue's UI/test naming is binding; backend SSE schema is I-f4-002b/I-f4-004a follow-up; mapping documented in this Issue's brief.

## Mission

Per breakdown: UI shows partial-evidence warning; zero-verified abort. Adversarial Playwright tests.

## Substrate (HONEST at HEAD)

- I-f4-001/002/003 ship `/audit_live` route, `SSEClient`, 6 panels, broadcast cancel.
- The "partial-evidence warning" + "zero-verified abort" UI states need to surface from server-emitted events. Per breakdown's adversarial framing: when ≥80% fetches fail (sources_dropped events for most candidates) OR every section drops (verify_decision events all show drop), the UI must surface a banner.

## Approach

**Part 1 — `web/app/audit_live/_panels.tsx`** (EDIT, ~40 LOC):
- Track CUMULATIVE counters in state (independent of MAX_EVENTS=50 panel slice):
  ```ts
  const [cumulative, setCumulative] = useState({
    source_dropped: 0,
    retrieval_candidate: 0,
    verify_decision_kept: 0,
    verify_decision_dropped: 0,
  });
  ```
- In `onEvent`, increment cumulative counters per name. For `verify_decision`, parse payload safely (`try { JSON.parse(data).kept === false } catch { return false }` — fail-closed: malformed treated as not kept).
- Compute derived banner state:
  - `partial_evidence = cumulative.retrieval_candidate >= 5 && cumulative.source_dropped / cumulative.retrieval_candidate >= 0.8`
  - `all_verify_failed = (cumulative.verify_decision_kept + cumulative.verify_decision_dropped) > 0 && cumulative.verify_decision_kept === 0`
- Render `<div data-testid="partial-evidence-warning">` and `<div data-testid="zero-verified-abort">` accordingly.

**Part 2 — `web/tests/e2e/audit_live_adversarial.spec.ts`** (NEW, ~70 LOC):
- Test 1 (partial-evidence): mock SSE emits 10 retrieval_candidate + 8 source_dropped events; navigate; assert `partial-evidence-warning` visible within 1s.
- Test 2 (zero-verified-abort): mock SSE emits 5 verify_decision events all with `{"kept":false}`; assert `zero-verified-abort` visible within 1s.
- Test 3 (no warning when normal): mock emits 10 candidates + 1 dropped + 5 verify_decision with `{"kept":true}`; wait for `panel-verify_decision-count` to read "5 events" first; THEN assert NEITHER banner visible.
- Test 4 (cap-boundary regression): mock emits 100 candidates + 50 dropped (cumulative 50% drop, NOT 80%); assert NO partial-evidence banner — even if panel-array sliced to 50.

## Acceptance criteria (binding)

1. `web/app/audit_live/_panels.tsx` EDIT — derived state + 2 banner data-testids.
2. `web/tests/e2e/audit_live_adversarial.spec.ts` NEW — 3 Playwright tests.

## Planned diff shape

```
web/app/audit_live/_panels.tsx                 EDIT +40
web/tests/e2e/audit_live_adversarial.spec.ts   NEW +90
```

LOC: +130 net. AT breakdown 130 budget. Under CHARTER §1 200-cap by 70.

## Out of scope

- Server emits these adversarial event patterns → backend SSE schema is I-f4-002b/I-f4-004a follow-up.
- Continuing the run after partial-evidence warning → I-f5-001+ inspector flow.

## Risks for Codex Red-Team

1. **Drop-rate threshold (80%).** Module constant; conservative — avoids false positives on small samples (`total_candidates >= 5` floor).
2. **`payload.kept === false` parse path.** `events.verify_decision[i].payload` is the JSON string from SSE `data:`. Test feeds `{"kept":false}` literally.
3. **Banner rendering precedence.** Both banners can show simultaneously if both conditions trigger; intentional.
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap.** 100 net.
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
