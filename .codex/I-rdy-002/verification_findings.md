# I-rdy-002 (#498) — Phase 1 gap verification against the live system

**Status:** verification complete (v2, post Codex iter-1). Verified against the
live orchestrator (OVH BHS5) + static code inspection of the repo.

## Verified results

| Gap | Verified status | Evidence |
|---|---|---|
| **Auth** | **CONFIRMED-BROKEN** | `web/app/sign-in/page.tsx` is a disabled placeholder — all inputs `disabled`, copy "Authentication is a placeholder for Phase 0", no form/onSubmit/login call. `web/lib/api.ts` — every `fetch()` sends only `content-type`, zero `Authorization` headers. UI cannot operate with auth on. → I-rdy-004 (#500). |
| **Rich UI fixture-bound** (F5-F15: bundle, charts, follow-up, compare) | **CONFIRMED-BROKEN** | `src/polaris_v6/api/bundle.py:45-64` — `_GOLDEN_RUN_INDEX` dict; `bundle.py:58` does `_GOLDEN_RUN_INDEX.get(run_id)` → 404 for any non-golden run. `charts.py:9,22`, `followup.py:10,24`, `compare.py:10,18` all import `_GOLDEN_RUN_INDEX` and do the same. A real completed run ID will always 404 — fixture-only. No LLM needed to confirm. → I-rdy-008 (#504). |
| **Canonical templates** | **CONFIRMED-BROKEN** | `web/app/page.tsx` template cards = `clinical, housing, climate, ai_sovereignty, canada_us, defense, trade, workforce`. Canonical 8 (`docs/polaris_locked_scope.md` §2) = `clinical, policy, tech, due_diligence, ai_sovereignty, canada_us, workforce, custom`. `housing/climate/defense/trade` are non-canonical; `policy/tech/due_diligence/custom` are missing. → I-rdy-005 (#501). |
| **Worker document_ids** | **CONFIRMED-BROKEN** | `POST /runs` sends `payload.model_dump()` to the actor so `document_ids` reaches `request_payload`, but `src/polaris_v6/queue/actors.py` builds the query object `q` for `run_one_query` WITHOUT `document_ids` — uploaded docs never reach the pipeline. → I-rdy-010 (#506). |
| Model/env alignment | **CONFIRMED — stale refs present** | stale DeepSeek V4 Flash / qwen references are repo-visible (architecture.md, hardware_decision.md, transparency defaults). Fix tracked in I-rdy-006 (#502). |
| Coherent product journey | **CONFIRMED-BROKEN** | `web/app/layout.tsx` has no global nav; 17/33 routes are harness pages; no single land→run→report→inspect journey. → I-rdy-014 (#510). |
| Run create (`POST /runs`) | **WORKS** | returns a real `run_id`, `lifecycle_status: queued`. |
| Run status (`GET /runs/{id}`) | **WORKS** with a live run ID | 200 for the real run `54f42c11…`. |
| cancel/resume | **PARTIAL** | `cancel_research_run` actor exists (`actors.py:214`) but records the request only ("real cancellation via Worker.send_signal"); no cancel endpoint on the API; resume unverified. → I-rdy-011 (#507). |
| F14 memory durability | **CONFIRMED in-memory** | `src/polaris_v6/api/memory.py:18,22` — live path uses `WorkspaceMemoryStore()` (in-memory `store.py`). `chroma_store.py` exists but is NOT the wired backend; comment says "the storage backend [will move] to Chroma". Not durable. → I-rdy-012 (#508). |
| GPG bundle signing | **PARTIAL** | `gpg_signer.py` exists; `/runs/{id}/bundle.tar.gz` appears to have live run-store/artifact-dir signing wiring; clean-machine verification not proven. → tracked in Workstream L (I-rdy-017). |
| Canadian sovereign GPU + sovereign dress rehearsal | **BLOCKED — external** | Not securable by Claude. Vexxhost + ISAIC outreach sent 2026-05-15; OVH Canada has no Hopper GPU. Decision gate 2026-05-24. → Phase 6 (#90 + operator); dress rehearsal Phase 8 (G1). |
| F13 pin replay | **CONFIRMED demo-data-bound** | `web/app/pin_replay/` uses `DEMO_PIN_REGISTRY`; production `/runs/{id}/pins/{date}` fetch is deferred. → wired in I-rdy-008 (#504). |
| 22-type test matrix on the product journey | **NOT DONE** | the ~75 existing Playwright specs target harness/fixture pages, not the coherent product journey. → I-rdy-019/020 (#515-516). |
| Sovereignty / log-redaction enforcement at external call sites | **NOT VERIFIED** | `sovereignty/classification.py` + `audit_bundle/sovereignty_guard.py` exist; per-call-site enforcement proof is absent. → Phase 5/7. |
| UI hardening states (loading / empty / error / network / a11y / performance) | **NOT VERIFIED** | not proven across the real journey. → Phase 5. |
| Demo logistics (fallback recordings, T-1 laptop drill, venue test, source cache, legal notice) | **NOT STARTED** | → Workstream L (#511-513) + G-series (G1/G5-G18) + #473. |
| (P2) Visual design system + route consistency | **NOT STARTED** | only 7 shadcn UI components; no shared design system; route-level consistency not polished. → P2 polish, post-integration (after I-rdy-014). |
| (P2) Scaffold / demo-data copy on user-visible pages | **CONFIRMED PRESENT** | user-visible pages carry scaffold/demo copy — e.g. `sign-in/page.tsx` "Phase 0 scaffold" / "placeholder for Phase 0", `pin_replay` `DEMO_PIN_REGISTRY`. → removed in I-rdy-014 (#510) journey assembly + P2 cleanup. |

## Conclusion

Phase 1 verification covers **every gap in the register**
(`state/carney_readiness_gaps_2026_05_15.md`) — each P0/P1/P2 row now has a
status.

- **5 P0 CONFIRMED-BROKEN** (real builds): auth, rich-UI fixture-bound,
  canonical templates, worker document_ids, coherent journey.
- **P0 BLOCKED-external:** Canadian GPU acquisition + dress rehearsal.
- **PARTIAL:** cancel/resume, F14 memory (confirmed in-memory), GPG signing,
  F13 pin replay (demo-data-bound), model/env (stale refs confirmed present).
- **NOT DONE / NOT VERIFIED / NOT STARTED:** 22-type product test matrix,
  sovereignty call-site proof, UI hardening states, demo logistics.
- **WORKS:** run create, run status.

No gap required a completed run to verify — the rich-UI endpoints are provably
fixture-bound by code (`_GOLDEN_RUN_INDEX`).

Feeds Phase 0B (I-rdy-003, #499): the lock doc's provisional feature statuses
can now be set to these verified statuses.
