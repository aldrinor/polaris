# Codex brief — I-rdy-014 (#510): assemble the coherent demo journey

## §0. HARD ITERATION CAP (verbatim, CLAUDE.md §8.3.1)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

**This is iter 4 of 5.** BRIEF review (acceptance-criteria correctness), not a diff review.

## §0.5 Changes since prior iters

- **iter 1** (REQUEST_CHANGES, 2 P1): command-palette `/intake` second entry;
  pin leg disabled. Both folded into the design.
- **iter 2** (REQUEST_CHANGES, 4 P1) — all verified against the codebase this
  fire and addressed:
  - **P1-1 signed bundle:** verified `src/polaris_v6/api/bundle.py:68` —
    `GET /runs/{run_id}/bundle.tar.gz`. The JSON `downloadBundleAsJson` is a
    *different* artifact. §3 now wires a real `.tar.gz` affordance.
  - **P1-2 integrated report:** corrected — the report surface is
    `/inspector/[runId]`, not `/runs/[runId]` (which is status + SSE only).
  - **P1-3 follow-up/compare:** verified `api/followup.py:22`
    `POST /runs/{run_id}/followup` and `api/compare.py:27`
    `GET /runs/{left_run_id}/compare/{right_run_id}` both exist. Compare ≠
    `/benchmark` (benchmark = POLARIS-vs-external). → §3.7 SCOPE FORK.
  - **P1-4 stale specs:** verified — **18** `web/tests/e2e/*.spec.ts` files
    reference `/intake`. §3.6 handles them.
  - P2s (graph link, HomeKeyboardShell header dup, test asserts link
    surface) folded in.
- **iter 3** (REQUEST_CHANGES, 3 P1; Codex **ruled B-split**) — addressed:
  - **P1-1 real-run bundle 404:** verified — `GET /runs/{id}/bundle` only
    serves `_GOLDEN_RUN_INDEX` fixtures; a freshly-created `/dashboard` UUID
    run 404s, so `/inspector/[runId]` has no JSON. → §3.5 the inspector +
    bundle affordances degrade gracefully on 404 (honest "report pending"
    state, never a crash); the real-run EvidenceContract/bundle bridge from
    `run_store.artifact_dir` is carved as **I-rdy-014c** (backend).
  - **P1-2 auth tarball:** verified — non-`/stream` routes require
    `Authorization: Bearer`; a plain `<a href>` cannot carry it. → §3.5
    uses an authenticated `authFetch` blob download → client object URL.
  - **P1-3 graph link:** the graph route resolves only the curated
    `audit_ir` registry, so `/runs/{uuid}/graph` is a dead link for a
    journey run. → the graph link is **dropped** from #510 scope.
  - P2s: I-rdy-014a/b/c filing + acceptance amendment is now an explicit
    §3.8 execution checklist; `GlobalNav` keeps a sign-in/status affordance.

## §1. Issue

**GH #510 — I-rdy-014, Phase 3.11.** Body verbatim:
> Phase 3. Global navigation in `web/app/layout.tsx`; coherent path land -> template -> ask -> live audit -> integrated report -> inspect -> follow-up/compare/pin/memory -> signed bundle. Hide the 17 test-harness routes from the demo.
> Acceptance: the full journey is navigable with no dead ends; harness routes not reachable from the demo; Codex APPROVE.

## §2. Grounded current state (verified this fire)

- **34 `page.tsx` routes.** `web/app/layout.tsx` has **no nav**.
- **17 harness routes** = `charts_test`+4 (5), `sentence_hover_test`+10 (11),
  `(test_harness)/disambiguation_modal_preview` (1) → exactly 17.
- **Incoherence:** `web/app/page.tsx` template cards AND
  `web/app/components/command_palette.tsx` both route to
  `/intake?template=<id>` (slice-001 page), not `/dashboard` (the real
  template+ask+submit → `/runs/<id>`).
- **`/runs/[runId]`** = run status + actions + live SSE events only — NOT a
  report surface. `/inspector/[runId]` is the evidence-inspector / report.
- **Signed bundle** = `GET /api/v6/runs/{run_id}/bundle.tar.gz`
  (`api/bundle.py:68`). `web/lib/api.ts` currently only has JSON bundle
  helpers (`getBundle`, `downloadBundleAsJson`) — no `.tar.gz` affordance.
- **Follow-up** backend: `POST /runs/{run_id}/followup` (`api/followup.py`).
  **Compare** backend: `GET /runs/{left}/compare/{right}` (`api/compare.py`).
  Neither has a product UI. The `runs/[runId]` "Ask follow-up" button is a
  disabled stub.
- **18 e2e specs** reference `/intake`. The `intake*.spec.ts` group tests
  `/intake` directly (`page.goto('/intake')`) and is unaffected; specs that
  reach `/intake` by *clicking a landing card / command-palette entry*
  (`demo_walkthrough`, `landing_template_grid`, `command_palette`,
  `command_palette_suggest`, and others) break once the link is repointed.

## §3. Proposed approach

### 3.1 Corrected canonical journey → routes

| Journey step | Route / affordance |
|---|---|
| land | `/` |
| template + ask | `/dashboard` (reads `?template=` param) |
| live audit | `/runs/[runId]` (SSE) |
| integrated report | `/inspector/[runId]` — the inspector IS the report surface (P1-2) |
| inspect | `/inspector/[runId]` (per-claim inspection within it) |
| pin | `/pin_replay` |
| memory | `/memory` |
| signed bundle | `GET /api/v6/runs/{runId}/bundle.tar.gz` download affordance on run + inspector pages (P1-1) |
| follow-up | `POST /runs/{id}/followup` — backend only, no UI → §3.7 |
| compare | `GET /runs/{left}/compare/{right}` — backend only, no UI → §3.7 |

### 3.2 Global nav — `GlobalNav` + `layout.tsx`

- New `web/app/components/global_nav.tsx` (`"use client"`, `usePathname()`
  active styling). Links: **Home `/` · Start a run `/dashboard` ·
  Workspace memory `/memory` · Pin & replay `/pin_replay`**. Brand → `/`.
  Right-aligned **sign-in/status affordance** (link to `/sign-in`, or a
  signed-in indicator) — preserved from the `HomeKeyboardShell` header that
  §3.2 P2 removes (Codex iter-3 P2).
- Mount in `layout.tsx` above `{children}`.
- Suppress on `/sign-in` + the 17 harnesses via `usePathname()` URL-prefix
  match (`/charts_test`, `/sentence_hover_test`,
  `/disambiguation_modal_preview`) — Codex iter-1 ruling.
- **P2 — landing header dup:** `web/app/page.tsx` renders via
  `HomeKeyboardShell`; mounting `GlobalNav` in layout would stack two
  headers. Resolution: `GlobalNav` is the single header; the landing page
  drops its own brand row (keeps the keyboard-shell behaviour).
- Drop the duplicate brand rows from `dashboard` and `runs/[runId]` headers
  (keep page-local actions) — Codex iter-1 ruling.

### 3.3 Landing incoherence (P1-1 iter-1)

`page.tsx` cards + `command_palette.tsx` active-template action:
`/intake?template=<id>` → `/dashboard?template=<id>`; `dashboard/page.tsx`
reads `?template=` to preselect the radiogroup.

### 3.4 Hide 17 harness routes — Option A (decided)

Nav-only: never linked, `GlobalNav` self-suppresses; routes stay URL-live so
`web/tests/` harness specs keep working. No dir moves.

### 3.5 Integrated report + signed bundle (P1 iter-2 + iter-3)

- `runs/[runId]` gets a prominent **"View report & inspect" →
  `/inspector/[runId]`** link (the "integrated report" + "inspect" steps).
- **Authenticated tarball download (Codex iter-3 P1-2):** new
  `web/lib/api.ts` helper `downloadBundleTarball(runId)` — `authFetch`
  GET `/runs/${runId}/bundle.tar.gz` → `response.blob()` →
  `URL.createObjectURL` → trigger a download → revoke. A plain `<a href>`
  cannot carry the `Authorization: Bearer` the v6 app requires. A
  **"Download signed bundle (.tar.gz)"** button on `runs/[runId]` AND
  `inspector/[runId]` calls it. Existing JSON export stays as secondary.
- **Graceful degradation on 404 (Codex iter-3 P1-1):** a freshly-created
  `/dashboard` run has no bundle yet (`GET /runs/{id}/bundle` serves only
  golden fixtures). Implementation verifies `/inspector/[runId]` and the
  bundle button render an honest **"report / signed bundle not yet
  available for this run"** state on 404 — never a crash, never a blank
  dead end. A navigable page that says "pending" is not a dead end; a crash
  is. The real-run bundle/EvidenceContract bridge is carved as I-rdy-014c.
- **Graph link dropped (Codex iter-3 P1-3):** no graph link is added —
  `/runs/{uuid}/graph` resolves only curated `audit_ir` runs, so it would
  be a dead link for journey runs. `runs/[runId]/graph` stays where it is,
  unreferenced from the journey.

### 3.6 Stale e2e specs (P1-4 iter-2)

Same PR updates every spec that reaches `/intake` via a landing/palette
*click* to expect `/dashboard` instead (`demo_walkthrough`,
`landing_template_grid`, `command_palette`, `command_palette_suggest`, and
any other click-path spec found by `grep`). Specs that `goto('/intake')`
directly are left (route still exists). New
`web/tests/e2e/demo_journey.spec.ts` asserts the full journey AND the
rendered journey-page link surface (so `/benchmark → /generation`-type
regressions are caught — P2 iter-2).

### 3.7 B-split (Codex iter-3 ruling) + carved issues

Codex iter-3 **ruled B-split**, not C-inline. #510 ships the **navigation +
journey skeleton** (§3.2–§3.6). Three carved issues are filed (see the §3.8
checklist) and #510's acceptance is formally amended:

- **I-rdy-014a — follow-up answer UI** (frontend; backend `POST
  /runs/{id}/followup` exists).
- **I-rdy-014b — run-compare view** (frontend; backend `GET
  /runs/{l}/compare/{r}` exists).
- **I-rdy-014c — real-run bundle / EvidenceContract bridge** (backend; make
  `GET /runs/{id}/bundle` serve a freshly-created `run_store` run from its
  `artifact_dir`, not only `_GOLDEN_RUN_INDEX` fixtures).

**Amended #510 acceptance:** the `land → template → ask → live-audit →
report/inspect → pin → memory → signed-bundle` journey is navigable from
`GlobalNav` + contextual links with **no crash and no dead end** — every
link resolves to a real page, and surfaces with not-yet-populated data
(a brand-new run's report/bundle) render an honest pending state, not an
error; the 17 harness routes are unreachable from the demo. Follow-up,
run-compare, and real-run bundle *content* are tracked in I-rdy-014a/b/c.

### 3.8 Execution checklist (Codex iter-3 P2)

Order of operations once this brief is APPROVE'd:
1. `gh issue create` for I-rdy-014a, I-rdy-014b, I-rdy-014c (titles +
   acceptance criteria), sequenced after #510 in the queue.
2. `gh issue comment 510` recording the amended acceptance (§3.7) and the
   three carved issue numbers.
3. Implement #510 per §3.2–§3.6 + §4.

## §4. Deliverables + LOC (B-split — Codex-ruled scope)

| File | Change | ~LOC |
|---|---|---|
| `web/app/components/global_nav.tsx` | NEW — nav + active-link + URL-prefix suppression + sign-in affordance | +100 |
| `web/app/layout.tsx` | mount `GlobalNav` | +4 |
| `web/app/page.tsx` | card link `/intake`→`/dashboard`; drop brand row | ~12 |
| `web/app/components/command_palette.tsx` | active-template route repair | ~6 |
| `web/app/dashboard/page.tsx` | `?template=` param; drop brand row | ~22 |
| `web/app/runs/[runId]/page.tsx` | drop brand row; report-&-inspect link; authenticated `.tar.gz` button | ~26 |
| `web/app/inspector/[runId]/page.tsx` | authenticated `.tar.gz` button; graceful bundle-404 pending state | ~22 |
| `web/lib/api.ts` | `downloadBundleTarball(runId)` authenticated blob helper | ~18 |
| `web/app/benchmark/page.tsx` | unlink `→ /generation` | ~6 |
| stale e2e specs (`grep`-found click-path set) | repoint `/intake`→`/dashboard` | ~40 |
| `web/tests/e2e/demo_journey.spec.ts` | NEW — journey + nav reachability + no-harness-link asserts | +100 |

**Total ≈ 355 LOC, frontend-only, ~140 test/spec, production frontend ≈ 215.**
Over the 200-LOC cap; Codex iter-1 granted the test-LOC exemption and iter-3
confirmed it holds in principle. The graph link is dropped (iter-3 P1-3);
no backend change (the bundle bridge is carved to I-rdy-014c).

## §5. Files I have ALSO checked and they are clean

- `src/polaris_v6/api/{bundle,followup,compare}.py` — endpoints verified
  (§2); no backend change in #510.
- `web/components/ui/` — shadcn primitives only; `GlobalNav` is new.
- `web/app/components/{home_keyboard_shell,command_palette}.tsx` — both on
  the landing path; `command_palette` is repaired (§3.3).
- All 18 `/intake`-referencing specs enumerated; click-path subset is the
  §3.6 work set.

## §6. Output schema (CLAUDE.md §8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

All iter-1/2/3 decisions resolved: Option A nav-only hiding; B-split (#510 =
journey skeleton; follow-up/compare/real-run-bundle carved to I-rdy-014a/b/c);
authenticated tarball download; graph link dropped; LOC-cap exemption.
No open decisions — iter 4 verifies the three iter-3 P1 fixes landed and the
amended acceptance + execution checklist (§3.7/§3.8) are sound.
