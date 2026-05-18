# Codex SCOPE consult — I-rdy-008 / GH #504: what is the residual scope after slices 1-7c?

This is a **scope-decision consult**, not a brief/diff review. One question:
**given the carve-out issues, what work does #504 still own, and should it
close?** Rule on the options in §5. Do NOT produce an implementation plan.

## 0. Why you are being asked

#504 (I-rdy-008, "Phase 3.5: wire live runs into the rich UI") has had
slices 1-7c merged (PR #590-#598) — the Evidence Inspector is fully
migrated onto the AuditIR data path. The loop is about to start "slice 8",
but grounding the running system against the open GitHub issues surfaced a
**scope overlap**: most of #504's stated surfaces are owned by *separate*
carve-out issues. Before spending slices, #504's true residual must be
settled. Architecture/scope decisions go to Codex, not the operator.

## 1. #504's stated scope (issue body, verbatim)

> Phase 3. Inspector, charts, follow-up, compare, F13 pin replay, F14
> memory, and bundle all accept a real completed run ID, not only golden
> fixtures. Acceptance: a live run is fully inspectable end-to-end through
> every rich surface; Codex APPROVE. Depends on: I-rdy-007.

Seven surfaces: **Inspector, charts, follow-up, compare, pin replay,
memory, bundle.**

## 2. Grounded data-path map (read from the running code at polaris HEAD 869ee795, NOT from issue text)

| Surface | Backend route | Golden-bound? | Frontend |
|---|---|---|---|
| Inspector | `GET /api/inspector/runs/{id}` + `/evidence` | **run_store** (migrated, slices 1-7c) | `web/app/inspector/[runId]/page.tsx` — done |
| Charts | `GET /runs/{id}/charts/{type}` (`charts.py:20`) | **GOLDEN-ONLY** — `charts.py:22` `_GOLDEN_RUN_INDEX.get(run_id)` → 404 | inspector Charts tab via `getChart()` |
| Follow-up | `POST /runs/{id}/followup` (`followup.py:22`) | **GOLDEN-ONLY** — `followup.py:24` `_GOLDEN_RUN_INDEX` | **no frontend page or client exists** (disabled button only) |
| Compare | `GET /runs/{l}/compare/{r}` (`compare.py:27`) | **GOLDEN-ONLY** — `compare.py:18` `_GOLDEN_RUN_INDEX`, both arms | **no frontend page or client exists** |
| Bundle | `GET /runs/{id}/bundle` (JSON, `bundle.py:55`) + `GET /runs/{id}/bundle.tar.gz` (`bundle.py:67`) | **MIXED** — JSON path GOLDEN-ONLY; tar.gz path already run_store. Frontend `getBundle()` calls the JSON (golden) path | `web/app/runs/[runId]/page.tsx` |
| Pin replay | **no v6 backend route exists at all** | n/a | `web/app/pin_replay/page.tsx` — pure `DEMO_PIN_REGISTRY`, no API |
| Memory | `POST/GET/DELETE /workspaces/{ws}/memory/*` (`memory.py:31`) | **run_store-INDEPENDENT** — workspace-scoped, no `run_id` parameter at all; already live-operable | `web/app/memory/page.tsx` |

## 3. The carve-out issues (read from GitHub, verbatim intent)

- **#532 (I-rdy-013, OPEN)** — "F13 pin replay: live run_id → pins backend
  route." Body: **"Carved from I-rdy-008 (#504)"**. Scope: build the
  missing `GET /runs/{run_id}/pins/{date}` route + rewire
  `web/app/pin_replay/`. → **pin replay is carved OUT of #504.**
- **#542 (I-rdy-014a, OPEN)** — "follow-up answer UI." Body: "Carved from
  I-rdy-014 (#510)... Backend substrate exists: `POST /runs/{id}/followup`.
  Depends on: #510." → **follow-up UI is owned by #542, not #504.**
- **#543 (I-rdy-014b, OPEN)** — "run-compare view." Body: "Carved from
  I-rdy-014 (#510)... Backend substrate exists: `GET /runs/{l}/compare/{r}`.
  Depends on: #510." → **compare view is owned by #543, not #504.**
- **#544 (I-rdy-014c, OPEN)** — "real-run bundle / EvidenceContract
  bridge." Body: "Carved from I-rdy-014 (#510)... `GET /runs/{id}/bundle`
  currently serves only `_GOLDEN_RUN_INDEX`... Bridge the bundle endpoint
  to serve a real run from run_store `artifact_dir`." → **the bundle
  golden→run_store migration is owned by #544, not #504.**

## 4. The contradiction Codex must weigh

#532's body asserts: *"I-rdy-008 wired the 4 EvidenceContract-backed
surfaces (bundle/charts/followup/compare); pin replay was explicitly out of
that Pattern-A scope."* — i.e. it describes #504 as having ALREADY wired
bundle/charts/followup/compare.

**The running code contradicts that:** at polaris HEAD, `charts.py` /
`followup.py` / `compare.py` and the `getBundle()` JSON path are all still
`_GOLDEN_RUN_INDEX`-bound (§2). #504's slices 1-7c migrated ONLY the
Inspector, and did so onto a *new* AuditIR route — not by un-golden-ing the
bundle/charts/followup/compare routes. So #532's "I-rdy-008 wired the 4
surfaces" is either (a) a forward-looking description of #504's intended
end-state that was never reached, or (b) evidence those 4 surfaces were
re-assigned to #544 (bundle) and #542/#543 (followup/compare) and an
implicit charts owner.

Also: slices 1-7c migrated `/inspector/[runId]` entirely OFF `getBundle()`,
so #544's stated premise ("`/inspector/[runId]` has no report JSON for a
real run") is now stale — the inspector no longer reads `/bundle` at all;
`getBundle()` survives only in `web/app/runs/[runId]/page.tsx`.

## 5. The decision — rule on ONE option

Per §2/§3: of #504's 7 surfaces — Inspector is **done**; pin replay is
**carved to #532**; follow-up UI to **#542**; compare view to **#543**;
bundle bridge to **#544**; memory is **already run_store-independent**
(works for any workspace, never golden-bound — arguably already satisfies
"accept a real run" vacuously since it is not run-scoped). The only surface
with no separate owner and not yet migrated is **charts** (`charts.py`
golden→run_store).

- **Option A — #504 residual = charts only.** One more slice (slice 8):
  migrate `charts.py` off `_GOLDEN_RUN_INDEX` onto `run_store` →
  `artifact_dir` resolution (mirroring the inspector route), so the
  inspector Charts tab renders for live runs. After that slice merges,
  #504 closes; pin-replay/followup/compare/bundle remain tracked in
  #532/#542/#543/#544; memory needs no work.
- **Option B — #504 is already complete; close it now.** The Inspector is
  the only surface #504 still owned after the carve-outs; charts is
  reassigned to a new dedicated issue (or to #544's bundle family). #504
  closes with no slice 8.
- **Option C — #504 is the umbrella; keep it open.** #504 stays open until
  #532/#542/#543/#544 all merge; "slice 8+" under #504 = none (the work
  lives in the carve-out issues). The loop should stop processing #504 as
  a slice queue and move to the next non-excluded issue.
- **Option D — your alternative**, if the three above mis-frame it.

Note for your ruling: the loop's operator-set EXCLUSIONS forbid
auto-processing #532/#542/#543/#544 (Phase-3 / #510-dependent). So whatever
you pick, #504's loop work cannot legitimately include
pin-replay/followup/compare/bundle — that is operator-locked, not your call
to re-fold into #504.

## 6. Output schema

```yaml
verdict: APPROVE            # APPROVE = you have made the scope ruling
chosen_option: A | B | C | D
polaris_504_residual: <one line — exactly what #504 still owns>
slice_8_scope: <one line — what slice 8 is, or "none">
close_504_after: <slice id, or "now", or "when #532/#542/#543/#544 merge">
charts_owner: <#504 slice 8 | a new issue | #544 family | other>
memory_verdict: <does #504 need any memory work? one line>
rationale: <2-4 lines>
remaining_blockers_for_execution: [...]
```
