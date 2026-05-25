# I-ux-001d — Route ↔ Figma frame map

Ground-truth inventory for the 22 frames the I-ux-001d prototype audit ships before I-ux-001c hero implementation begins. Resolves Codex iter-1 remaining blocker "Publish an exact 11-page route/frame map, including how Transparency is represented" (`.codex/I-ux-001d/sequencing_verdict_iter1.txt`).

## Live route reconciliation

Authoritative source: `web/app/**/page.tsx` (this branch) + `web/lib/nav.ts` (PRIMARY_NAV — auth-aware) + `web/next.config.ts` (rewrites) + `docs/web/route_map.md` (I-cd-004 locked map). Cross-checked against `state/polaris_restart/issue_breakdown.md` P2-seq-13..23 completion records and `docs/stier_experience_plan.md` §1 surfaces.

| # | Page (operator-facing label) | Next.js route | Live today? | Family | Critical path? | Mobile pattern |
|---|---|---|---|---|---|---|
| 1 | Home | `/` | ✅ `web/app/page.tsx` | marketing | **A+** | single-column hero |
| 2 | Intake (a.k.a. Ask) | `/intake` | ✅ `web/app/intake/page.tsx` | edit-mode | **A+** | sheet-on-input |
| 3 | Source Review (visually = step-2-of-Intake preflight per Codex iter-2 P2) | `/source_review` | ✅ `web/app/source_review/page.tsx` | edit-mode | **A+** | table → cards |
| 4 | Plan review | `/plan` | ✅ `web/app/plan/page.tsx` | edit-mode | **A+** | stacked editable list |
| 5 | Run progress | `/runs/[runId]` | ✅ `web/app/runs/[runId]/page.tsx` | monitor-mode | **A+** | top status + collapsing groups |
| 6 | Report / Inspector (Proof Replay) | `/inspector/[runId]` | ✅ `web/app/inspector/[runId]/page.tsx` | **read-mode (anchor)** | **A+** | bottom-sheet (locked v6) |
| 7 | Compare / follow-up | `/compare` | ✅ `web/app/compare/page.tsx` | read-mode | **A+** | stacked two-source cards |
| 8 | Knowledge graph | `/runs/[runId]/graph` | ✅ `web/app/runs/[runId]/graph/page.tsx` | spatial | **A+** | pinch-zoom + bottom node tray |
| 9 | Audit / export | `/runs/[runId]/audit` | ✅ `web/app/runs/[runId]/audit/page.tsx` | read-mode | A (supporting) | stacked compliance cards |
| 10 | Sign-in | `/sign-in` | ✅ `web/app/sign-in/page.tsx` | marketing/auth | A (supporting) | full-screen split |
| 11 | Dashboard / runs monitoring | `/dashboard` | ✅ `web/app/dashboard/page.tsx` | monitor-mode | A (supporting) | stacked status cards |
| 12 | **Transparency & disclosure (NEW: dedicated HTML page)** | `/transparency` (HTML) + `/.well-known/transparency.json` (JSON) | ❌ Today: `next.config.ts` rewrites `/transparency` → FastAPI JSON. Human page does NOT exist. | marketing | A (supporting; regulatory) | single-column long-read |

**Total page-rows: 12. Frame count: 12 desktop (1440×900) + 12 mobile (390×844) = 24 frames.**

## Transparency: dedicated HTML page (Codex iter-2 P1-002 resolution)

**Contract conflict found in iter-1:** my prior version of this doc claimed transparency lives in shell footer only. Codex iter-2 P1-002 grounded that this is wrong:
- `web/next.config.ts:101-106` rewrites `/transparency` → FastAPI `/transparency` JSON (machine endpoint)
- `web/components/site_footer.tsx:35-39` LINKS to `/transparency` → human reader hits the JSON dead-end
- `docs/stier_experience_plan.md` §6 requires intended-use + non-use + model path + data residency + verifier limits + receipt links as a real human-readable disclosure

**Resolution:** dedicated human-readable `/transparency` HTML page (this map page #12) + relocate the machine JSON to `/.well-known/transparency.json` (well-known URI per RFC 8615). The footer link retargets at the HTML page. The FastAPI JSON path becomes `/api/v6/transparency` (already exists internally) + the `.well-known` rewrite for external auditors.

This adds 1 page-row to the inventory (originally 11 → now 12; 22 frames → 24 frames).

The shell footer + sovereignty proof panel on Inspector remain as the AMBIENT disclosure layer (per P2-seq-23 #762), but the dedicated `/transparency` page becomes the SOURCE-OF-TRUTH for the disclosure content. Footer + panel link to it.

## Nav cut: 5 routes removed from demo primary nav (Codex iter-2 P1-001 resolution)

**Inventory gap found in iter-1:** `web/lib/nav.ts:25-34` exposes 9 primary nav items including `/upload`, `/benchmark`, `/contracts`, `/pin_replay`, `/memory` (all completed as P2-seq-26..30; routes alive). Plan §1 surfaces target a TIGHTER demo nav. Codex iter-2 P1-001: "either cut and document, or include in scope."

**Resolution: CUT from primary nav for the Carney demo.** Rationale:
- Frontier-bar nav restraint: Linear, Stripe, Perplexity, OpenEvidence have 3-5 primary nav items. 9-item nav reads "internal tool suite" not "premium product."
- Budget reality: 5 more pages × A-bar audit + Figma frames blows the ~11-day demo window per Codex iter-2 budget call.
- Critical-path focus: these 5 routes are operator/reviewer surfaces (Upload = ingest docs; Benchmark = head-to-head; Contracts = signed-bundle list; Pin Replay = reproduce a prior run; Memory = campaign memory). None are on Carney's demo journey (Home → Ask → Source Review → Plan → Run → Report → Compare → Graph).
- Operator framing in #872: "Mark Carney will have a very strong and fresh impact" — that demands focus, not breadth.

**What CUT means concretely:**
- Remove from `web/lib/nav.ts` PRIMARY_NAV at I-ux-001c implementation time (CODE-LEVEL change; not in #879 scope)
- Routes remain reachable via direct URL for operator/reviewer access (no 404)
- Routes do NOT get S-tier Figma frames in #879
- Out-of-demo-scope, in-product-scope label in the audit log

**5 cut routes** (live today, not in #879 frame budget):
| Route | Original role | Post-demo plan |
|---|---|---|
| `/upload` | Document upload | Reachable URL; reviewer/operator only |
| `/benchmark` | BEAT-BOTH benchmark UI | Reachable URL; reviewer only |
| `/contracts` | Signed bundle / contracts | Reachable URL; reviewer only |
| `/pin_replay` | Replay a pinned run | Reachable URL; operator only |
| `/memory` | Campaign memory | Reachable URL; operator only |

Demo primary nav becomes: **Home · Ask · Dashboard · Compare** (4 items, auth-aware) + footer Transparency link. Inspector / Report / Source Review / Plan / Run progress / Audit / Graph all reachable via in-app deep-link from Dashboard or Ask flow.

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

## Per-frame v6 proof-language checklist (Codex iter-2 P2 mitigation)

Every frame produced in #879 — desktop and mobile — must satisfy this checklist before submission to Codex audit. Prevents incumbent-leak (old-page habits surviving the rebuild):

- [ ] **Sealed evidence block** where source text is shown (continuous 2px verified-green left rule + source-card + span text + "matched N of N" verification stamp per v6 hero precedent)
- [ ] **Two-judgment separation** is visually unambiguous: faithfulness (binary check / chip grammar; verified-green / amber / magenta-red) is structurally distinct from evidence-strength (ordinal ladder; slate-blue) — never visually blurred
- [ ] **Tri-state signature pill** (`gpg_verified` / `present_unverified` / `missing`) — only `gpg_verified` may render the green "Signed bundle" affordance
- [ ] **Intended-use / non-use language** visible where the page presents clinical content (per plan §6 + Codex iter-4 D4 lock)
- [ ] **Refusal / abstention** state designed (not just success state) — what does the page look like when the answer is "we cannot answer this safely"?
- [ ] **NO old route-card visual habits** — no generic "card with icon + title + caption" hero unless the proof-language hierarchy demands it
- [ ] **App shell + footer + sovereignty disclosure** wired through (per Transparency page #12 + ambient layer)
- [ ] **Brand red `#c8102e`** used only for brand mark + intentional brand moments (never for verdict/evidence semantics — those use the design-tokens-v2 magenta-red at hue 320 specifically to NOT collide with brand)
- [ ] **Six microstates** (rest / hover / focus-visible / active / disabled / loading / error / empty) specified for primary interactive surfaces on the page
- [ ] **Mobile pattern** matches the family contract (read-mode bottom-sheet / edit-mode sheet-on-input / monitor-mode top-status / spatial pinch-zoom / marketing single-column)

## Budget posture acknowledgment (Codex iter-2 P2)

Per Codex iter-2 specific check `budget_realism`: ~11 calendar days to demo-window start (2026-06-05). 24 frames + motion + audits + I-ux-001c implementation + #871 fix + TLS + dress rehearsal is achievable **only if**:

- Frame inventory is FROZEN as of this iter-2 resolution (no further scope expansion in #879)
- I-ux-001c (#878) implementation begins immediately after Track 1 (hero motion) + Track 2 (family contracts) gates pass, in parallel with Tracks 3-5
- The 5 cut nav routes (upload/benchmark/contracts/pin_replay/memory) stay cut for the demo (no last-minute reinstatement)
- #871 (live-clinical-run blocker) is sequenced as parallel work, not after demo prototype is done
- Codex audits hit one-iter APPROVE on Tracks 1+2 (the precedent precedent is ≥3 iters per visual gate; one-iter APPROVE assumes the foundation is now tight enough)

Risk of slippage: if Tracks 1+2 exceed 3 days combined, the 24-frame mega-audit + per-page critical-path audits + code implementation will not finish before June 3 (the rehearsal cutoff). Slippage mitigation = drop the 4 supporting-page A frames (Audit, Sign-in, Dashboard, Transparency) from the prototype set and design them at code-time only.

## Out-of-scope for #879

These remain in I-ux-001c (#878) code-time gate per plan §14, NOT in this prototype-audit issue:
- Pixel-perfect Tailwind v4 spacing implementation
- Real bundle data binding
- Playwright e2e tests for the implemented pages
- WCAG 2.2 AA axe-measured pass
- Reduced-motion `prefers-reduced-motion` media-query implementation (motion is *specified* in #879 stills + tokens; *enforced* in #878 code)
- The `web/lib/nav.ts` PRIMARY_NAV cut (CODE change at #878, not in #879)
- The `next.config.ts` `/transparency` rewrite relocation to `/.well-known/transparency.json` (CODE change at #878)
