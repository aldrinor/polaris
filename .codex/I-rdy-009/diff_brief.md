# Codex DIFF review — I-rdy-009 (#505): wire ambiguity_detector into the create-run flow

**Type:** DIFF review (code correctness against the APPROVE'd brief). **iter 2 of 5.**

## §0. Iteration cap directive (CLAUDE.md §8.3.1, verbatim, binding)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## §0.5 Change since diff-iter 1 (REQUEST_CHANGES P1-001 — fixed)

diff-iter-1 raised **P1-001**: an in-flight ambiguity scan started for
question A could resolve *after* the user edited to question B and set
`clinicalScanGate="ok"` for the stale question — `invalidateAmbiguityScan`
only reset *completed* scans, not in-flight ones, and `onSubmit` checked
only the gate, not which question was scanned.

**Fixed (commit `cc073bbc`)** via a monotonic generation ref —
`scanGenerationRef` (`web/app/dashboard/page.tsx`):
- `runScopeCheck` claims a generation at start:
  `const myGeneration = (scanGenerationRef.current += 1)`.
- `invalidateAmbiguityScan` (fired on every question / template / upload
  edit) bumps `scanGenerationRef.current`.
- After **each `await`** in `runScopeCheck` (after `checkScope`, after
  `checkAmbiguity`, after `scanAmbiguity`, and in the `catch`), a guard
  `if (scanGenerationRef.current !== myGeneration) return;` discards the
  result. So a scan whose inputs were edited mid-flight applies **no**
  state — it can never set `clinicalScanGate="ok"`.
- The ref bump is synchronous, so the discard is order-independent of when
  the obsolete promise resolves relative to the edit handler.

Result: `clinicalScanGate==="ok"` ⟺ a scan completed for the *current*
question/template/uploads with no intervening edit — Codex diff-iter-1's
`required_fix` ("cancel/ignore obsolete runScopeCheck results"). e2e gains
a 4th test exercising the in-flight race deterministically (600ms-delayed
scan, edit mid-flight, assert "Start run" blocked).

## §1. What to review

The diff for #505 against the brief APPROVE'd at brief-iter 5
(`.codex/I-rdy-009/codex_brief_verdict.txt`). Canonical diff:
`.codex/I-rdy-009/codex_diff.patch`, trailer
`# canonical-diff-sha256: eaa4f74c7bbb4b60e4d960fcaec083308a0d466ea38c1cb1297991072e066150`
= sha256 of `git diff origin/polaris...HEAD -- ':(exclude).codex/I-rdy-009/'
':(exclude)outputs/audits/I-rdy-009/'`.

7 files, commits `2b73a21e` + `cc073bbc`.

## §2. Two deviations from the APPROVE'd brief — flagged loudly

The brief was APPROVE'd, but two of its specifics were not executable as
written. Both were adapted; both achieve the brief's exact invariant.
**Please scrutinise these first.**

### §2.1 Backend search helper: `SerperClient` → direct `httpx` call

Brief §3.1 specified `get_serper_client()` from `src/search/serper_client.py`.
At implement time `src/search/__init__.py` was found **broken**: line 8
`from src.search.engines import (...)` and line 35
`from src.search.fan_out_executor import (...)` both reference modules that
**do not exist** (`src/search/` contains only `__init__.py`,
`query_amplifier.py`, `serper_client.py`). So `import src.search.serper_client`
raises `ModuleNotFoundError: No module named 'src.search.engines'` — confirmed
empirically: my first `__init__.py` import broke the whole
`ambiguity_detector` package.

Adaptation: `candidate_fetcher.py` issues the Serper `/search` POST directly
via `httpx.AsyncClient`, mirroring the proven pattern in
`src/polaris_graph/retrieval2/real_fetcher.py:_fetch_serper` (slice-002's real
Serper fetcher). Same Serper service, same `https://google.serper.dev/search`
endpoint, same fail-loud contract — no dependency on the broken `src.search`
package. This is arguably *cleaner* than the brief: there is no
`SerperClient.search()` error-swallowing (brief-iter-2 P1) to work around;
the fetcher raises directly. `search_backend_ruling = serper-ok` (brief-iter-2)
still holds — same backend, no new sovereignty surface.

(The broken `src/search/__init__.py` is a pre-existing latent defect affecting
only legacy importers — `src/agents/*`, `src/polaris_graph/agents/searcher.py`.
It is NOT introduced or worsened here. Noted in `claude_audit.md` as a
candidate follow-up issue; out of #505 scope.)

### §2.2 Stale-scan invalidation: `useEffect` → event-handler calls + generation ref

Brief §3.3 (brief-iter-5, the P1-002 fix) specified an invalidate-on-change
`useEffect` keyed on `[question, template, uploads]`. ESLint
`react-hooks/set-state-in-effect` (Next 16 / React 19) **rejects** calling
`setState` synchronously in an effect body — `npm run typecheck` + `eslint`
must pass for CI.

Adaptation: a single `invalidateAmbiguityScan()` helper is called from the
three event handlers that mutate those values — the question `<Input
onChange>`, the template select `<button onClick>`, and both `setUploads`
sites (`handleFiles` add, the per-row remove `onClick`). It also bumps
`scanGenerationRef` (§0.5). This is the React "you might not need an effect"
idiom and gives **identical coverage** to the effect (every path that changes
question/template/uploads), with no mount-time fire, plus the in-flight-scan
cancellation the effect could not provide.

## §3. Implementation map (verify against the brief)

**Backend**
- `src/polaris_v6/ambiguity_detector/candidate_fetcher.py` (new) —
  `fetch_candidate_snippets(question)`: fail-loud guard (brief §3.1) — (1)
  `SERPER_API_KEY` unset → `raise CandidateFetchError`; (2) `httpx.HTTPError`
  from the search → `raise CandidateFetchError`; (3) zero mapped snippets →
  `raise CandidateFetchError`. Never returns `[]`. `_fetch_serper_organic`
  is the network seam (tests stub it).
- `src/polaris_v6/ambiguity_detector/__init__.py` — exports
  `CandidateFetchError`, `fetch_candidate_snippets`.
- `src/polaris_v6/api/ambiguity.py` — `POST /ambiguity/scan` (brief §3.2):
  `fetch_candidate_snippets` → `detect_ambiguity` → `AmbiguityCheckResponse`;
  `CandidateFetchError` → `HTTPException(503, code="candidate_fetch_unavailable")`.
  `_to_check_response` helper shared with the existing `/ambiguity` (pure
  refactor — identical behaviour).

**Frontend**
- `web/lib/api.ts` — `scanAmbiguity(question)` → `POST /ambiguity/scan`;
  non-OK throws via `asJsonOrThrow`.
- `web/app/dashboard/page.tsx` — `runScopeCheck`: clinical question-only
  branch calls `scanAmbiguity`, sets `clinicalScanGate="ok"` on success /
  `"failed"` on throw; opens `DisambiguationModal` when ambiguous. Upload
  branch now also opens the modal when ambiguous (brief-iter-5 P2-001).
  `onSubmit`: hard-block when `template==="clinical" && uploads.length===0
  && clinicalScanGate!=="ok"` (brief-iter-4 P1-001-frontend). `scanGenerationRef`
  discards stale in-flight scans (§0.5 — diff-iter-1 P1-001).
  `invalidateAmbiguityScan` (§2.2). Inline notice + `DisambiguationModal`
  replace the old card.
- `web/tests/e2e/dashboard_ambiguity.spec.ts` (new) — 4 specs: modal opens
  on an ambiguous query; a `503` scan blocks "Start run"; a post-scan
  question edit re-blocks "Start run"; an edit during an in-flight scan
  re-blocks "Start run". All assert no `/runs` POST + no navigation.

## §4. Test evidence

- `tests/v6/test_ambiguity_scan.py`: **5 fetcher tests PASS** (no-key raises,
  HTTP-failure raises, zero-snippets raises, all-empty-text raises, happy
  path maps hits). 4 `/ambiguity/scan` endpoint tests **skip** on this host —
  `create_app()` raises `OSError: Unable to run gpg` (gpg binary absent;
  pre-existing — `test_api_bundle.py` / `test_api_ambiguity.py` error
  identically). The endpoint fixture uses the `try/except OSError →
  pytest.skip` pattern so it is clean locally and **runs in CI** (gpg
  present). `tests/v6/test_ambiguity_detector.py` passes — confirms the
  `__init__.py` change did not regress the package.
- `web/`: `npm run typecheck` clean; `eslint` clean on all changed/new
  frontend files.
- `web/tests/e2e/dashboard_ambiguity.spec.ts`: authored, type-checks, lints;
  full Playwright run is CI-verified (a local run needs `next build` — heavy
  per CLAUDE.md §8.4; the brief §3.3 explicitly sanctioned CI-verification
  for the e2e spec).

## §5. Adjacent-file scan — checked, clean

`src/polaris_v6/api/app.py` (mounts the `ambiguity` router; `/ambiguity/scan`
auto-mounts on it — no change needed), `src/polaris_v6/ambiguity_detector/
ambiguity_detector.py` (`detect_ambiguity` unchanged), `web/app/intake/
components/disambiguation_modal.tsx` (props consumed as-is via the adapter),
`tests/v6/test_api_ambiguity.py` (the existing `/ambiguity` endpoint behaviour
is unchanged — `_to_check_response` is a behaviour-preserving refactor),
`tests/v6/conftest.py`.

## §6. Output schema (CLAUDE.md §8.3.9 — bind to this)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
verdict_reasoning: <text>
```
Loose prose without the schema → resubmit.
