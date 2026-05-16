# Claude architect audit — I-rdy-009 (#505): wire ambiguity_detector into the create-run flow

**Issue:** GH #505 — F2 ambiguity detection runs in the main ask/create-run
flow, not only the test harness. Acceptance: an ambiguous query triggers the
disambiguation modal in the product flow.

**Commit:** `2b73a21e` on `bot/I-rdy-009-ambiguity-wiring` (off `polaris` @
`9185035e`). 7 files, +638/-70. Canonical-diff-sha256
`63ac8b4fb717a00b118bb35d5e6d3343d3bb4bb083a4db8a1bd1eed280564118`.

## Acceptance check

The gap #505 names was real and specific: the dashboard already calls the
ambiguity detector (`checkAmbiguity` → `POST /ambiguity`), but only when
`uploads.length > 0` — a question-only query (the common demo case) never
reached `detect_ambiguity` because there was no candidate source for a bare
question. The `ambiguity_detector` / `/ambiguity` docstrings both named the
missing "Phase 1: backend fetches via cheap retrieval" piece; it had never
been built. This PR builds it.

- **Backend candidate source.** `candidate_fetcher.fetch_candidate_snippets`
  does one Serper `/search` call and maps hits → `CandidateSnippet`.
- **Question-only endpoint.** `POST /ambiguity/scan` runs the fetch +
  `detect_ambiguity`, returns the same `AmbiguityCheckResponse` as
  `/ambiguity`.
- **Product flow.** The dashboard `runScopeCheck`, for a clinical
  question-only query, calls `scanAmbiguity`; an ambiguous result opens the
  `DisambiguationModal` — the literal "disambiguation modal" the acceptance
  criterion names. Verified by the e2e spec `dashboard_ambiguity.spec.ts`
  test 1.

Acceptance met for the clinical template (Codex brief-iter-2 `scope_ruling =
option-C`: clinical-only is acceptable for #505; non-clinical question-only
ambiguity is a carved follow-up).

## Fail-loud review (LAW II)

The central safety property: a search/config failure must NOT silently
become a false "not ambiguous". Verified line-by-line:

- `fetch_candidate_snippets` raises `CandidateFetchError` on (1) unset
  `SERPER_API_KEY`, (2) `httpx.HTTPError`, (3) zero usable mapped snippets.
  It never returns `[]`. `detect_ambiguity([])` would return
  `is_ambiguous=False` — the false-negative this guard exists to prevent.
- `POST /ambiguity/scan` maps `CandidateFetchError` → HTTP 503
  `candidate_fetch_unavailable` (mirrors the `/api/disambiguation`
  `label_client_unavailable` precedent).
- The frontend `clinicalScanGate` tri-state hard-blocks "Start run" for a
  clinical question-only run unless the scan succeeded — so a 503, a
  never-run scan, or a post-scan input edit cannot fail open into
  `createRun`. (Codex brief-iter-3 P1-001 + brief-iter-4 P1-002.)

Tests cover all three raise paths + the 503 + the createRun hard-block.

## Two brief deviations (both forced, both sound)

1. **`SerperClient` → direct `httpx`.** `src/search/__init__.py` is broken at
   HEAD (imports non-existent `src.search.engines` / `fan_out_executor`), so
   `SerperClient` is unimportable. `candidate_fetcher` issues the Serper call
   directly, mirroring `real_fetcher._fetch_serper`. Same service/endpoint;
   no new sovereignty surface; fail-loud is cleaner (no `search()`
   error-swallowing to defeat). Detailed in `diff_brief.md` §2.1.
2. **Invalidation `useEffect` → event-handler calls.** ESLint
   `react-hooks/set-state-in-effect` rejects setState-in-effect; the
   invalidation now runs from the question/template/upload handlers via
   `invalidateAmbiguityScan()` — identical coverage, React-idiomatic.
   Detailed in `diff_brief.md` §2.2.

## Residual / follow-up

- **Pre-existing defect (not mine to fix here):** `src/search/__init__.py`
  references two non-existent modules — a latent breakage for legacy
  importers (`src/agents/*`, `polaris_graph/agents/searcher.py`). Candidate
  for a follow-up hygiene issue; out of #505 scope.
- The `/ambiguity/scan` endpoint tests skip on this gpg-less host; they run
  in CI. The fetcher logic (the real new code) is fully unit-tested locally
  (5/5 pass).
- Non-clinical question-only ambiguity remains uncovered — carved follow-up
  per Codex brief-iter-2 `scope_ruling = option-C`.

## Verdict

The diff implements the APPROVE'd brief, both deviations are documented and
sound, fail-loud holds end-to-end, and tests cover every raise + gate path.
Ready for Codex diff review.
