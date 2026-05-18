# Codex SCOPE consult — GH #505 (I-rdy-009): what is the actionable scope, given the running system?

This is a **scope-decision consult**, not a brief/diff review. One question:
**given the running system, what does #505 still require — and is it already
satisfied?** Rule on the options in §4. Do NOT produce an implementation
plan.

## 0. Why you are being asked

The autonomous issue loop picked #505 (I-rdy-009, the lowest-numbered open
non-excluded issue after #504 closed). Grounding the running system against
the issue text surfaced a scope ambiguity: the issue says F2 ambiguity
detection runs "only the test harness," but the running code shows the F2
disambiguation modal is ALREADY wired into a real product page. Before
spending a per-issue cycle, #505's true residual must be settled. Scope
ambiguity goes to Codex, not the operator.

## 1. #505 verbatim

> **I-rdy-009 — Phase 3.6: wire ambiguity_detector into the ask/create-run
> flow.** Phase 3. F2 ambiguity detection runs in the main ask/create-run
> flow, not only the test harness. Acceptance: an ambiguous query triggers
> the disambiguation modal in the product flow; Codex APPROVE. Depends on:
> I-rdy-003.

I-rdy-003 (#499) is CLOSED — the dependency is satisfied.

## 2. Grounded map of the running system (read at polaris HEAD f4653974)

POLARIS v6 has **two distinct ask flows** and **three ambiguity detectors**:

**Flow A — `/intake`** (`web/app/intake/page.tsx` — "Clinical scope
discovery", linked from the home page):
- `web/app/intake/components/intake_form.tsx` submit → `runIntake()` →
  `POST /api/intake` → `process_intake()` → clinical PICO ambiguity
  heuristic (`ambiguity_detector_clinical.detect_ambiguity`).
- If candidate snippets exist, `intake_form.tsx:79-89` then calls
  `runDisambiguation()` → `POST /api/disambiguation` (the F2
  embedding-clustering detector, `disambiguation_route.post_disambiguation`)
  and **renders `DisambiguationModal`** (`intake_form.tsx:183-192`).
- **`/intake` is gates-only — it does NOT create a run.** No `createRun()`
  call; intake just classifies + gates the question.

**Flow B — `/dashboard`** (`web/app/dashboard/page.tsx` — "Start a research
run"):
- `dashboard/page.tsx` `onSubmit` → `createRun()` → **`POST /runs`** →
  inserts to run_store + enqueues the Dramatiq actor. **This is the actual
  ask/create-run flow** — the only flow that creates a run.
- Before submit, an optional "Check scope" button → `runScopeCheck()` →
  `checkScope()` + `checkAmbiguity()` (the v6 *light* detector,
  `POST /ambiguity`, `polaris_v6/ambiguity_detector/detect_ambiguity`);
  `onSubmit` blocks if `ambiguity?.is_ambiguous && !acknowledgedAmbiguity`.
- **The dashboard does NOT render `DisambiguationModal`** and does NOT call
  the F2 `POST /api/disambiguation` clustering detector. Its only ambiguity
  surface is the light `checkAmbiguity` + an acknowledge checkbox.

**The `DisambiguationModal` component** (`web/app/intake/components/
disambiguation_modal.tsx`) is a real reusable component. It is rendered in
exactly two places: `intake_form.tsx` (real product page) and
`web/app/(test_harness)/disambiguation_modal_preview/_client.tsx` (the test
harness).

## 3. The ambiguity #505's text vs the running system

- #505 says F2 detection runs "**not only the test harness**" — implying at
  filing time it ran ONLY in the harness. But the running code shows the F2
  `DisambiguationModal` + `POST /api/disambiguation` ARE wired into
  `intake_form.tsx`, a real product page. So the literal acceptance — "an
  ambiguous query triggers the disambiguation modal in the product flow" —
  is **already met by the `/intake` page**.
- HOWEVER: `/intake` is gates-only; it never creates a run. #505's title is
  "wire ambiguity_detector into the **ask/create-run flow**." The flow that
  actually creates a run is `/dashboard` → `POST /runs`, and the dashboard
  does NOT render the F2 disambiguation modal.
- #505 (I-rdy-009, a Phase-3 readiness issue) was filed AFTER the intake
  disambiguation wiring already existed (intake + `DisambiguationModal`
  predate the I-rdy series). So #505's author plausibly knew intake had the
  modal and meant something the intake flow does NOT cover.

## 4. The decision — rule ONE option

- **Option A — #505 is already satisfied; close it.** The acceptance
  ("an ambiguous query triggers the disambiguation modal in the product
  flow") is literally met by `/intake`, a real product page, not the test
  harness. #505 closes with no PR.
- **Option B — the gap is the dashboard create-run flow.** #505's
  "ask/create-run flow" means the run-creating flow (`/dashboard` →
  `POST /runs`). Slice = wire F2 ambiguity detection (the
  `DisambiguationModal` + `POST /api/disambiguation`, or the existing light
  `checkAmbiguity` path elevated to actually render the disambiguation
  modal) into the dashboard so an ambiguous query triggers the modal there
  before `createRun()`. This is a real frontend (+ maybe glue) change.
- **Option C — your alternative**, if A/B mis-frame it (e.g. the real gap
  is that intake and dashboard should be unified, or the dashboard's light
  `checkAmbiguity` is sufficient and only needs the modal rendered).

Constraints for your ruling:
- The loop's operator-set EXCLUSIONS forbid auto-processing #510 (the
  "assemble the coherent demo journey" issue) and its carve-outs
  #542/#543/#544. If #505's honest scope turns out to be "unify the
  intake/dashboard ask flows," that overlaps #510's journey work — flag it.
- Per `feedback_plan_from_running_system` + the `bpei_phantom_completion`
  lesson: "an issue's acceptance criterion is met" only counts if a real
  user, in the deployed product, hits the behavior. If `/intake` genuinely
  shows the disambiguation modal on an ambiguous query, Option A is honest;
  if the modal only fires under a narrow condition users won't hit, it is
  not.

## 5. Output schema

```yaml
verdict: APPROVE            # APPROVE = scope ruling made
chosen_option: A | B | C
i_rdy_009_residual: <one line — exactly what #505 still requires, or "none">
slice_scope: <one line — what to build, or "none — close the issue">
close_505: <"now, already satisfied" | "after the slice merges">
overlaps_510: <yes/no — does the honest scope bleed into #510's journey work?>
rationale: <2-5 lines>
remaining_blockers_for_execution: [...]
```
