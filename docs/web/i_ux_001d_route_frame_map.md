# I-ux-001d — Route ↔ Figma frame map

Ground-truth inventory for the 22 frames the I-ux-001d prototype audit ships before I-ux-001c hero implementation begins. Resolves Codex iter-1 remaining blocker "Publish an exact 11-page route/frame map, including how Transparency is represented" (`.codex/I-ux-001d/sequencing_verdict_iter1.txt`).

## Live route reconciliation

Authoritative source: `web/app/**/page.tsx` (this branch). Cross-checked against `state/polaris_restart/issue_breakdown.md` P2-seq-13..23 completion records and `docs/stier_experience_plan.md` §1 surfaces.

| # | Page (operator-facing label) | Next.js route | Live today? | Family | Critical path? | Mobile pattern |
|---|---|---|---|---|---|---|
| 1 | Home | `/` | ✅ `web/app/page.tsx` | marketing | **A+** | single-column hero |
| 2 | Intake | `/intake` | ✅ `web/app/intake/page.tsx` | edit-mode | **A+** | sheet-on-input |
| 3 | Source Review | `/source_review` | ✅ `web/app/source_review/page.tsx` | edit-mode | **A+** (Codex promoted) | table → cards |
| 4 | Plan review | `/plan` | ✅ `web/app/plan/page.tsx` | edit-mode | **A+** | stacked editable list |
| 5 | Run progress | `/runs/[runId]` | ✅ `web/app/runs/[runId]/page.tsx` | monitor-mode | **A+** | top status + collapsing groups |
| 6 | Report / Inspector (Proof Replay) | `/inspector/[runId]` | ✅ `web/app/inspector/[runId]/page.tsx` | **read-mode (anchor)** | **A+** | bottom-sheet (locked v6) |
| 7 | Compare / follow-up | `/compare` | ✅ `web/app/compare/page.tsx` | read-mode | **A+** | stacked two-source cards |
| 8 | Knowledge graph | `/runs/[runId]/graph` | ✅ `web/app/runs/[runId]/graph/page.tsx` | spatial | **A+** | pinch-zoom + bottom node tray |
| 9 | Audit / export | `/runs/[runId]/audit` | ✅ `web/app/runs/[runId]/audit/page.tsx` | read-mode | A (supporting) | stacked compliance cards |
| 10 | Sign-in | `/sign-in` | ✅ `web/app/sign-in/page.tsx` | marketing/auth | A (supporting) | full-screen split |
| 11 | Dashboard / runs monitoring | `/dashboard` | ✅ `web/app/dashboard/page.tsx` | monitor-mode | A (supporting) | stacked status cards |

**Total page-rows: 11. Frame count: 11 desktop (1440×900) + 11 mobile (390×844) = 22 frames.**

## Transparency: NOT a standalone route

Codex iter-1 flagged "how Transparency is represented." Grounded answer per `web/components/app_shell.tsx` + `web/components/site_footer.tsx` + `web/app/components/home_keyboard_shell.tsx`: the sovereignty / transparency content is integrated into the **global app shell** (footer + sovereignty panel + signed-bundle pill embedded across pages per P2-seq-23 #762). It is NOT a separate page in the live route map.

Implication for #879:
- Transparency does NOT get its own desktop+mobile hero frame
- The transparency content (sovereignty disclosure: OpenRouter-US LLM path + Canadian hosting + data residency + per-sentence proof + offline-verify) appears as a SHELL element across every page; it must be designed as part of the shell template, not as a page hero
- The dedicated `/transparency` URL the plan §1 implies is REJECTED; the footer + the sovereignty proof panel on Inspector satisfy the surface

## Family taxonomy (Codex iter-1 D2 lock)

Per Codex direction "treat families as CONTRACTS, not cloned pages":

| Family | Pages | Shared contract surface |
|---|---|---|
| **Read-mode** (proof surfaces) | Inspector, Compare, Audit | Sealed evidence block; provenance two-band strip; signed-bundle pill; per-claim verdict; two-judgment chip-row |
| **Edit-mode** (decision gates) | Intake, Source Review, Plan review | Just-ask input or editable list; auto-detected domain badge; source-set control; decision rationale strip; gate verdict (proceed / refuse / amend) |
| **Monitor-mode** (system state) | Run progress, Dashboard | Live SSE stream; depth-visible checklist (T1/T2/.../source-count); pipeline-verdict honesty (success / abort_* / partial); reduced-motion equivalent |
| **Spatial** | Knowledge graph | Force-directed graph; focal spotlight; navigator rail; pinch-zoom; node-tray bottom-sheet on mobile |
| **Marketing / auth** | Home, Sign-in | Single-column hero; proof-as-CTA (Home: real verified brief; Sign-in: institutional split) |

Shell-level contracts apply ACROSS all families: app shell + footer + sovereignty proof + signed-bundle pill + signature badge state + per-page nav + reduced-motion compliance.

## Critical-path lock (Codex iter-1 D5)

**A+ bar (8 pages):** Home → Intake → Source Review → Plan review → Run progress → Inspector → Compare → Knowledge graph
**A bar (3 pages):** Audit, Sign-in, Dashboard

Inspector v6 is already at A+ (Codex iter-5 GREENLIGHT precedent). The remaining 7 critical-path pages must hit the same bar before I-ux-001c implementation begins.

## Naming alignment

Page hero frame filenames in `web/p2shots/I-ux-001d/`:
- Desktop: `page_<n>_<route_slug>_desktop_v<N>.png` (1440×900)
- Mobile: `page_<n>_<route_slug>_mobile_v<N>.png` (390×844)

Where `<n>` is the 1-11 ordering above and `<route_slug>` is the route stem without leading slash, with `/` replaced by `_` and `[runId]` stripped. Example: `page_06_inspector_desktop_v1.png`, `page_05_runs_mobile_v1.png`, `page_08_runs_graph_desktop_v1.png`.

## Salvageable behavior from incumbents (Codex iter-1 D6)

Per Codex direction "incumbent-INFORMED, not incumbent-led — salvage behavior only, rebuild visuals greenfield":

| Page | Salvage from live | Rebuild visually |
|---|---|---|
| Inspector | Bundle loader (tri-state signature), GPG verify path, family segregation badge, real-bundle data contract | Visual hierarchy rebuilt per v6 prototype (DONE) |
| Run progress | SSE event types, sub-task instrumentation, pipeline-verdict humanizer | Progress shape, hierarchy, motion |
| Knowledge graph | Force layout, BFS expand, focal selection, PNG/JSON export | Card density, spotlight treatment, mobile pattern |
| Audit | Real manifest fields (8 audit fields), signed bundle pill | Card elevation, compliance-table density |
| Source review | Tier classifier integration, adequacy gate semantics | Decision-rationale strip, T1/.../T7 visual hierarchy |
| Compare | EvidenceContract two-bundle loader, claim-anchor URL params | Two-column / stacked layout choreography |
| Intake | Domain auto-detection, source-set control state | Hero question typography, decision-gate visualization |
| Plan review | Editable plan JSON-schema | Edit-mode hierarchy, accept/amend/refuse affordances |
| Home | Real verified-brief loader (one CTA) | Proof-as-hero teaser per v6 storyboard |
| Dashboard | Run list, status filter | Monitor-only restraint, status pill |
| Sign-in | static_accounts wiring, error states | Institutional split-screen treatment |

## Out-of-scope for #879

These remain in I-ux-001c (#878) code-time gate per plan §14, NOT in this prototype-audit issue:
- Pixel-perfect Tailwind v4 spacing implementation
- Real bundle data binding
- Playwright e2e tests for the implemented pages
- WCAG 2.2 AA axe-measured pass
- Reduced-motion `prefers-reduced-motion` media-query implementation (motion is *specified* in #879 stills + tokens; *enforced* in #878 code)
