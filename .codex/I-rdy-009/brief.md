# Codex BRIEF review — I-rdy-009 (#505): wire ambiguity_detector into the ask/create-run flow

**Type:** BRIEF review (acceptance-criteria + scope correctness). Phase 3.6 of the
Carney demo execution plan. **iter 5 of 5 (cap iteration).**

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

This is the **iter-5 cap**. Every iter-1..4 finding has been addressed; no finding
has recurred. Please make a final convergence call.

## §0.5 Changes since prior iters

- **iter 1 → 2:** dropped the false `/api/intake` `candidate_snippets` contract;
  adopted Codex option (a) — build a real candidate-snippet source.
- **iter 2 → 3:** explicit Serper fail-loud guard + distinct modal-open state.
- **iter 3 → 4:** `clinicalScanGate` tri-state hard-block so a 503 scan cannot
  fail open into `createRun`.
- **iter 4 → 5 (REQUEST_CHANGES — P1-002 + P2-001, both accepted, both fixed):**
  - **P1-002 — gate not bound to the submitted question (FIXED, §3.3).** Codex
    was right: `clinicalScanGate="ok"` for question A survived an edit to
    question B, so B could be submitted on A's stale scan. Fix: a **single
    invalidate-on-change `useEffect`** keyed on `[question, template, uploads]`
    resets `clinicalScanGate→"not_run"`, `ambiguity→null`,
    `acknowledgedAmbiguity→false`, `disambigModalOpen→false`. Any edit after a
    scan forces `clinicalScanGate ≠ "ok"`, so the `onSubmit` hard-block (§3.3)
    re-engages — `createRun` can never POST a question that lacks its own
    successful `detect_ambiguity` scan. (Chosen over a scan-key comparison
    because it ALSO clears the now-stale ambiguity notice for the edited
    question — correct UX, not just correct gating.)
  - **P2-001 — upload path no longer auto-opens the modal (FIXED, §3.3).** The
    upload-backed `checkAmbiguity` branch now also calls
    `setDisambigModalOpen(true)` when its result is ambiguous, so "ambiguous
    query triggers the modal" holds for the upload path too, not only
    question-only.

Locked Codex rulings carried forward: `modal_location_ruling = import-in-place`,
`loc_disposition = single-pr-cap-exemption`, `search_backend_ruling = serper-ok`,
`label_ruling = truncated-representative-text-ok`.

## §1. Issue + acceptance

GH #505 (I-rdy-009, Phase 3.6): "F2 ambiguity detection runs in the **main
ask/create-run flow**, not only the test harness. **Acceptance: an ambiguous query
triggers the disambiguation modal in the product flow; Codex APPROVE.**" Depends on
I-rdy-003 (done).

The issue title names `ambiguity_detector` — the module
`src/polaris_v6/ambiguity_detector/` → `detect_ambiguity()`, exposed as
`POST /ambiguity` (`src/polaris_v6/api/ambiguity.py`). This brief wires **that**
detector (NOT the slice-001 PICO scope-axes detector — different mechanism, §3.0).

## §2. Grounded current state (all files read)

- **`/dashboard` (`web/app/dashboard/page.tsx`) is the main create-run flow:**
  template + question → "Check scope" (`checkScope` → `POST /scope/check`) →
  "Start run" (`createRun` → `POST /runs` → redirect `/runs/{id}`).
- **The dashboard ALREADY calls the ambiguity detector — but the path is dead for
  question-only queries.** `runScopeCheck` (`page.tsx:138-149`) runs
  `checkAmbiguity` only `if (decision.verdict === "accepted" && uploads.length > 0)`;
  candidates are built **solely from uploaded-document `chunk_preview`s**. A
  question-only query (no uploads — the common demo case) **never reaches
  `detect_ambiguity`**. When it does fire (uploads present) it renders an inline
  ambiguity **card** (`page.tsx:386-434`), not a modal.
- **`POST /ambiguity` (`src/polaris_v6/api/ambiguity.py`)** body:
  `{question, candidates: list[{source_id, text}], min_cluster_size,
  similarity_threshold}`. With no candidates `detect_ambiguity([])` returns
  `is_ambiguous=False` — **`/ambiguity` is useless for a bare question without a
  candidate source.**
- **`detect_ambiguity` (`ambiguity_detector.py:108`)** is pure-Python
  (trigram-cosine greedy clustering — no embeddings/LLM/network). Consumes
  `list[CandidateSnippet(source_id, text)]`; ≥2 qualifying clusters ⇒ ambiguous.
  Its docstring + the `/ambiguity` request docstring both name the missing piece:
  *"Phase 1: backend fetches via cheap retrieval before this call."* **That cheap
  candidate-fetcher was never built — that gap IS issue #505.**
- **`SerperClient` (`src/search/serper_client.py`)** — `get_serper_client()`
  singleton; `async search(query, max_results)` → `list[SerperResult]`
  (`.url/.title/.snippet`). `__init__` sets `self.enabled = bool(self.api_key)`
  (`:211-216`); `_request()` raises `SerperError` when `not self.enabled`
  (`:318`); **`search()` swallows `SerperError` per page (`:474`) and returns the
  accumulated list — `[]` on a first-page failure (`:481`)** — so `search()` never
  raises; the fail-loud guard must be explicit (§3.1). Same Serper backend
  slice-002 production retrieval uses (`polaris_graph/retrieval2/real_fetcher.py`).
- **`web/lib/api.ts:184-217`** `checkAmbiguity` → `POST /ambiguity` →
  `AmbiguityResult {is_ambiguous, clusters: [{cluster_id, representative_text,
  member_source_ids}], fallback_used}`.
- **`DisambiguationModal` (`web/app/intake/components/disambiguation_modal.tsx`)** —
  a `@base-ui/react` `Dialog`. Props `{open, clusters: DisambiguationCluster[],
  onSelectCluster(id), onCancel}`; `DisambiguationCluster = {cluster_id, label,
  sample_snippets[]}`. The literal "disambiguation modal."

## §3. The plan — Codex option (a): cheap clinical candidate-snippet source

### §3.0 Why option (a), not option (b)

Option (b) (narrow acceptance to the PICO `AmbiguityModal`) is rejected: the PICO
modal is driven by `ScopeDecision.ambiguity_axes` — the *scope classifier's* PICO
axes, a different mechanism from `detect_ambiguity` (candidate-clustering). Issue
#505 names `ambiguity_detector` = `detect_ambiguity`; option (b) would satisfy the
word "modal" while leaving `ambiguity_detector` unwired. So option (a).

### §3.1 Backend — a cheap candidate-fetcher with an EXPLICIT fail-loud guard

New module `src/polaris_v6/ambiguity_detector/candidate_fetcher.py` (~55 LOC):

```
async def fetch_candidate_snippets(question: str, *, max_results: int = 10)
    -> list[CandidateSnippet]
```

Logic, in order:
1. `client = get_serper_client()`. **If `not client.enabled`** (no
   `SERPER_API_KEY`) → `raise CandidateFetchError("SERPER_API_KEY unset")`
   immediately — do NOT call `search()` (it would swallow the error, return `[]`).
2. `results = await client.search(question, max_results=max_results)`.
3. Map each `SerperResult` → `CandidateSnippet(source_id=r.url,
   text=f"{r.title}. {r.snippet}".strip())`; drop entries with empty text.
4. **If the mapped list is empty** → `raise CandidateFetchError("search returned
   zero candidate snippets")`. Per LAW II, zero results means *search failed*, NOT
   *unambiguous* — never return `[]` to the detector. (`≥1` snippet is valid input;
   `detect_ambiguity` correctly reports a single snippet as non-ambiguous.)

`CandidateFetchError` is a small new exception class in the same module.

### §3.2 Backend — a question-only endpoint with a 503 on fetch failure

New route in `src/polaris_v6/api/ambiguity.py` (~32 LOC), on the **existing**
`APIRouter(prefix="/ambiguity")` (already mounted — the dashboard reaches
`/ambiguity` today, so `/ambiguity/scan` auto-mounts):

```
POST /ambiguity/scan   body {question: str (min_length=4, max_length=2000)}
                       -> AmbiguityCheckResponse
```

`try: snippets = await fetch_candidate_snippets(question)` →
`detect_ambiguity(snippets)` → return the **same `AmbiguityCheckResponse` shape**
`/ambiguity` already returns. `except CandidateFetchError as exc:` →
`raise HTTPException(503, {"error": True, "code": "candidate_fetch_unavailable",
"message": str(exc)})` — mirroring the `/api/disambiguation`
`label_client_unavailable` 503 precedent (`disambiguation_route.py:89-92`).

### §3.3 Frontend — dashboard wiring, modal, hard scan-gate, stale-scan invalidation

`web/lib/api.ts`: add `scanAmbiguity(question) -> AmbiguityResult` →
`POST /ambiguity/scan` (~14 LOC); a non-OK response throws via the existing
`asJsonOrThrow` helper.

`web/app/dashboard/page.tsx` — **four distinct state values:**
- `ambiguity: AmbiguityResult | null` — scan result; read by the createRun gate.
- `acknowledgedAmbiguity: boolean` — gate flag; set true ONLY by `onSelectCluster`.
- `disambigModalOpen: boolean` — **new** — drives the dialog only.
- `clinicalScanGate: "not_run" | "ok" | "failed"` — **new** — whether the
  mandatory clinical question-only ambiguity scan has *successfully completed*.

**Stale-scan invalidation (P1-002 fix) — a single `useEffect`:**
```
useEffect(() => {
  setClinicalScanGate("not_run");
  setAmbiguity(null);
  setAcknowledgedAmbiguity(false);
  setDisambigModalOpen(false);
}, [question, template, uploads]);
```
Any edit to the question, template, or upload set invalidates a prior scan.
(`runScopeCheck` does not mutate those three deps, so it never races this effect;
the effect's mount-time run is a harmless reset to already-default values.)

**`runScopeCheck`:** after `checkScope` returns `decision`:
- **Upload branch** (`uploads.length > 0 && verdict === "accepted"`) — keeps
  `checkAmbiguity` from upload chunks; now ALSO `if (result.is_ambiguous)
  setDisambigModalOpen(true)` (P2-001 fix). Does not touch `clinicalScanGate`.
- **Clinical question-only branch** — if `template === "clinical" &&
  uploads.length === 0 && decision.verdict !== "rejected"`:
  `try { const r = await scanAmbiguity(question.trim()); setAmbiguity(r);
  setClinicalScanGate("ok"); if (r.is_ambiguous) setDisambigModalOpen(true); }
  catch (e) { setClinicalScanGate("failed"); setError("Ambiguity check is
  unavailable — retry Check scope before starting a run."); }`.

**`onSubmit` createRun gate** — after the existing `rejected` check, BEFORE
`createRun`:
```
if (template === "clinical" && uploads.length === 0 && clinicalScanGate !== "ok") {
  setError(clinicalScanGate === "failed"
    ? "Ambiguity check is unavailable — retry Check scope before starting a run."
    : "Run Check scope first — the ambiguity guard must complete for clinical questions.");
  return;   // hard block — no createRun, no navigation
}
```
A 503, a never-run scan, OR a post-scan edit (invalidated by the effect) all leave
`clinicalScanGate ≠ "ok"` → "Start run" hard-blocked. The existing
`ambiguity?.is_ambiguous && !acknowledgedAmbiguity` gate (`page.tsx:167`) still
blocks the ambiguous-and-unacknowledged case. Both gates coexist.

**Modal + inline notice (replaces the card at `page.tsx:386-434`):**
- Imported `DisambiguationModal` (`import-in-place`), `open={disambigModalOpen}`.
  3-line adapter `AmbiguityCluster[] → DisambiguationCluster[]`:
  `{cluster_id, label: representative_text.slice(0,80), sample_snippets:
  [representative_text]}`.
- `onSelectCluster(id)` → `setAcknowledgedAmbiguity(true)` +
  `setDisambigModalOpen(false)`. `onCancel` → `setDisambigModalOpen(false)` ONLY.
- One-line inline notice shown whenever `ambiguity?.is_ambiguous &&
  !acknowledgedAmbiguity`, with a "Review meanings" button re-opening the modal.

e2e Playwright spec `web/tests/e2e/dashboard_ambiguity.spec.ts`: (1) ambiguous
clinical query → `DisambiguationModal` opens; (2) `/ambiguity/scan` mocked `503`
→ "Start run" stays blocked, no `/runs` POST, no navigation (P1-001 regression);
(3) successful scan on question A, then edit to question B → "Start run" blocked
until B is re-checked (P1-002 regression). Mirrors
`web/tests/e2e/intake_disambiguation.spec.ts`.

**Honest environment note:** `web/` is Next.js 16 (`web/AGENTS.md` — read
`node_modules/next/dist/docs/` before frontend code). `npm run build`/Playwright
may be environment-limited in the autonomous session; if so the diff ships with
the spec authored + lint/type-check run as far as the env allows + a clear note
that the e2e run is CI-verified.

## §4. Deliverable files + LOC estimate

`loc_disposition = single-pr-cap-exemption` (Codex iter-2). Single PR, ~275 LOC.

| File | New/Mod | ~LOC |
|---|---|---|
| `src/polaris_v6/ambiguity_detector/candidate_fetcher.py` | new | 55 |
| `src/polaris_v6/ambiguity_detector/__init__.py` | mod (export `fetch_candidate_snippets`, `CandidateFetchError`) | 4 |
| `src/polaris_v6/api/ambiguity.py` | mod (+`/ambiguity/scan`) | 32 |
| `tests/v6/test_ambiguity_scan.py` | new — fetcher fail-loud (no key → raises; zero snippets → raises; happy path), `/ambiguity/scan` 200 + 503, real `detect_ambiguity`, Serper stubbed at the `get_serper_client` boundary | 75 |
| `web/lib/api.ts` | mod (+`scanAmbiguity`) | 14 |
| `web/app/dashboard/page.tsx` | mod (card→modal, scan call, adapter, `disambigModalOpen` + `clinicalScanGate` state, invalidation effect, createRun scan-gate) | ~100 churn (~50 del + ~50 add) |
| `web/tests/e2e/dashboard_ambiguity.spec.ts` | new (modal-opens + 503-blocks + stale-scan-blocks) | 65 |

New-retrieval code itself ~90 LOC (under the ~120 carve threshold); size is
dominated by the card→modal replacement + e2e. Cap exemption ruled by Codex iter-2.

## §5. Adjacent-file scan — files I have ALSO checked and they're clean

`src/polaris_v6/api/app.py` (router mounting; the new endpoint rides the existing
`ambiguity` router), `src/polaris_v6/api/scope.py`, `src/polaris_v6/api/runs.py`,
`src/polaris_v6/ambiguity_detector/__init__.py`, `src/search/serper_client.py`
(`enabled` `:211-216`; `_request` raise `:318`; `search` swallow `:474`; return
`:481`), `src/polaris_graph/retrieval2/real_fetcher.py`,
`src/polaris_graph/api/intake_route.py`, `src/polaris_graph/scope/scope_decision.py`,
`src/polaris_graph/api/disambiguation_route.py`,
`web/app/intake/components/disambiguation_modal.tsx`,
`web/app/intake/components/intake_form.tsx`, `web/app/dashboard/page.tsx`
(`runScopeCheck` `:129-155`, `onSubmit` gate `:157-187`), `web/lib/api.ts`.

## §6. Questions for Codex

1. Does §3.3's invalidate-on-change `useEffect` fully resolve P1-002 (no stale
   scan can authorize a different question)?
2. Does the upload-branch `setDisambigModalOpen(true)` fully resolve P2-001?
3. Any remaining P0/P1 execution risk.

## §7. Output schema (CLAUDE.md §8.3.9 — bind to this)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
verdict_reasoning: <text>
```
Loose prose without the schema → resubmit.
