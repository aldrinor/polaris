# POLARIS issue breakdown (state/polaris_restart/issue_breakdown.md)

**Authority:** advisory until Codex APPROVE.
**Source:** `state/polaris_restart/plan.md` §4 (Codex-APPROVE'd at iter 4 on 2026-05-05).
**Iter:** 2 (addressing iter-1 P1×6 + P2×3 findings).

This document expands plan §4 into the canonical Issue list. Each Issue has `id`, `title`, `scope`, `acceptance_criteria`, `foundation_refs`, `addBlockedBy`, `phase`, `feature`, plus LOC estimate per CHARTER §3. The `addBlockedBy` chain enforces military-order sequential execution.

Issues are atomic per CHARTER §3 (≤200 LOC PR cap). Multi-PR features decompose to N Issues, each with its own brief→APPROVE→diff→APPROVE→merge cycle.

---

## §1 Issue ID schema (FIXED iter 3 P1-ID-SCHEMA per Codex iter 2)

```
I-<prefix>-<NNN>
```

Where:
- `<prefix>` is alphanumeric (lowercase letters + digits permitted), 2-8 characters, MUST NOT start with `-`. Iter-1 said "alpha only" — Codex iter 2 caught that `phase0` and `2c` violated; fixed iter 3 to "alphanumeric" since Phase 0 and Phase 2C both reference numeric phase identifiers naturally.
- `<NNN>` is exactly three decimal digits zero-padded.
- The full ID matches regex `^I-[a-z0-9]{2,8}-[0-9]{3}$`.

Prefixes:
- `phase0`: Phase 0 outstanding tasks
- `f1` through `f15`: Carney v6.2 user-visible features
- `ecg`: Evidence Contract Gate
- `bug`: Reissued bug fixes (#79/#82/#84)
- `bench`: Benchmark proof package
- `tpl`: Template additions (Phase 3)
- `p2c`: Phase 2C polish (renamed from `2c` to `p2c` for clarity, still alphanumeric)
- `sov`: Phase 4 sovereign migration
- `buf`: Phase 4.5 buffer
- `hand`: Phase 5 Carney handover
- `cj`: Crown jewel preservation
- `anti`: Anti-sycophancy CI

Three-digit zero-padded sequence within prefix. Example: `I-phase0-003` for Vast.ai task.

**Task 0.8 split** (per Codex iter 1 P1-USER-BLOCKED-CONFLICT) becomes two distinct IDs without suffix:
- `I-phase0-008` — Gemma 4 31B technical verification (auto-progressable)
- `I-phase0-010` — Gemma 4 31B license sign-off (user-blocked) — uses ID 010 because 009 is OVH H200

This eliminates the `-tech`/`-license` suffix that violated the schema.

---

## §2 Mandatory pre-execution preconditions (FIXED iter 2 P2-MECHANICAL-GATES)

Before ANY Issue execution begins, all preconditions must be verified:

1. **§10 mechanical gates LIVE** — see plan §10. CODEOWNERS file in place; `polaris-controls/` signed-commits-required protection enabled; `gh pr merge --admin` revoked from Claude; CI workflow `polaris/codex-required.yml` deployed. Verification: `scripts/verify_cage.py` returns "33/33 cage checks pass".
2. **§9.6a session-start hook deployed** — `scripts/hooks/session_start_check.py` (canonical, cross-platform) + `scripts/hooks/session_start_check.sh` (fallback) + `.claude/settings.json` (TRACKED, project-shared) wire the PreToolUse matcher with `python $CLAUDE_PROJECT_DIR/scripts/hooks/session_start_check.py`. Hook verifies BOTH `polaris-controls/CHARTER.md` AND `polaris-controls/PLAN.md` blob hashes against `state/polaris_restart/charter_sha_pin.txt` on every tool call (no same-day-stamp shortcut; stamp is informational only). Verification: any Bash/Edit/Write/MultiEdit call with mismatched or missing pin emits PreToolUse deny payload with reconciliation instructions.
3. **§7.G G2 signed commit on polaris-controls** — operator-approval commit exists with body acknowledging slice 001 goldens + CHARTER + PLAN SHAs.
4. **`pre_restart_2026_05_05` tag created** on `polaris` branch HEAD before reset.
5. **`polaris` branch reset** to `365f334` per plan §7.D ROAD B without cherry-pick.

These are USER actions, not Issues. They are NOT in the Issue list because they are not Codex-executable. Verification reference: plan §10.0 + §11 "What I cannot do".

---

## §3 Issue body template (CHARTER §7 visibility — FIXED iter 2 P1-VISIBILITY-GAP)

Every Issue uses this body when opened on GitHub:

```markdown
## Scope
<one paragraph; what this Issue produces and what it does NOT touch>

## Foundation refs
- CHARTER §<N> (`polaris-controls/CHARTER.md`)
- PLAN §<N> (`polaris-controls/PLAN.md`)
- Carney v6.2 §<F or Phase> (`docs/carney_delivery_plan_v6_2.md`)
- Substrate audit (`docs/substrate_audit_2026-05-01.md` — module path if relevant)
- Slice spec (`polaris-controls/slices/slice_NNN_*.md` — if applicable)

## Acceptance criteria
<bulleted list; each item testable>

## Out of scope
<bulleted list; explicit exclusions>

## Adversarial inputs
<bulleted list>

## LOC estimate
<integer; must be ≤200 per CHARTER §3>

## Per-Issue artifacts required at PR open (CHARTER §7 visibility)

Per CLAUDE.md §3.0 + plan.md §7.A LOCKED A2 + PR-D `codex-required.yml` 5-artifact gate (PR-D iter 3 PRD3-P2-001 fix synchronizes this list with CLAUDE.md/plan.md/codex-required.yml — earlier `decision.md` entry was an iter-pre-PR-D draft superseded by the canonical 5-artifact contract):

- `.codex/<issue_id>/brief.md` (Claude-authored)
- `.codex/<issue_id>/codex_brief_verdict.txt` (Codex APPROVE)
- `.codex/<issue_id>/codex_diff.patch` (Claude-written diff committed under this name; binds to actual PR diff via PR-D `codex-required.yml` content-hash check per PRD3-P1-001 fix)
- `.codex/<issue_id>/codex_diff_audit.txt` (Codex APPROVE — Red-Team checklist on codex_diff.patch)
- `outputs/audits/<issue_id>/claude_audit.md` (Claude architect review — `<issue_id>` is literal Issue ID e.g. `I-f1-001`)

## Blocks
<list of Issue IDs this Issue must complete before>

## Blocked by
<list of Issue IDs that must complete before this can start>
```

CI workflow `polaris/codex-required.yml` checks for ALL FIVE artifacts (the four `.codex/` files + the `outputs/audits/` claude_audit). Missing any → CI fail → cannot merge.

---

## §3a Default metadata inheritance (FIXED iter 3 P1-INCOMPLETE-METADATA)

To avoid repeating identical metadata on every Issue, the following defaults apply to every Issue in this document UNLESS the Issue explicitly overrides:

- **Phase:** inherited from containing section header (deterministic):
  - PHASE0 → Phase 0
  - F1, F2, F3, F15, ECG, BUG-079, BUG-082 → Phase 1
  - F4, F5, F7, F8, F9 → Phase 2A
  - F6, F10, F13, F14 → Phase 2B (F6 is in 2B per Carney v6.2 §"Phase 2B" line; iter 3 PHASE-METADATA-CONFLICT resolved here — F6 belongs ONLY to Phase 2B, not Phase 2A. Iter 2 §3a incorrectly listed F6 in both; corrected.)
  - P2C → Phase 2C polish
  - F11, F12, BENCH, TPL, BUG-084 → Phase 3
  - SOV → Phase 4
  - BUF → Phase 4.5
  - HAND → Phase 5
  - CJ, ANTI → parallel side-tracks (no phase number; flagged as "side-track" in body)
- **Feature:** inherited from prefix. `f1` Issues have feature F1, `f2` have F2, etc. `phase0` Issues have feature `infra`. `cj` have feature `crown-jewel-preservation`. `anti` have feature `anti-sycophancy-CI`. `bug` Issues have feature corresponding to the bug location (079=F1 intake, 082=F15 audit-bundle, 084=F12+benchmark scorer).
- **Foundation refs:** every Issue references (a) `state/polaris_restart/plan.md` §4 (the master breakdown), (b) `polaris-controls/CHARTER.md` §1+§3+§4+§7 (role assignment + LOC cap + immutable tests + visibility), (c) `polaris-controls/PLAN.md` (slice progression context), (d) `docs/carney_delivery_plan_v6_2.md` §<feature or phase>. Issue-specific foundation refs (e.g., specific substrate paths) appear ONLY when the Issue depends on a non-default reference; these are listed inline in the Issue.

When an Issue is opened on GitHub (per §3 body template), the Phase/Feature/Foundation refs lines are FILLED IN by the brief writer using these defaults plus any inline overrides. The body template §3 lists them as required fields; missing them in the GitHub Issue body fails CI.

---

## §4 Phase 0 outstanding Issues (7, FIXED iter 3 count + iter 2 schema + user-blocked split)

7 Issues: I-phase0-003 (Vast.ai), I-phase0-005 (Dramatiq), I-phase0-006 (hardware path decision), I-phase0-007 (SGLang vs vLLM), I-phase0-008 (Gemma tech), I-phase0-009 (OVH H200), I-phase0-010 (Gemma license sign-off).

### I-phase0-003 — Vast.ai US dev cluster operational (Carney Task 0.3)

- **Phase:** 0 / **Feature:** infra
- **Foundation refs:** Carney v6.2 §Phase 0 Task 0.3; existing `scripts/provision_vast_dev_cluster.py` substrate
- **Scope:** stand up Vast.ai account, provision GPU instance per `scripts/provision_vast_dev_cluster.py` config, verify SSH access, install POLARIS dependencies, run smoke test, write `docs/decisions/0_3_vastai_provisioning.md` recording instance ID, region, GPU type, hourly cost
- **Acceptance:** Vast.ai instance reachable; `nvidia-smi` shows expected GPU; POLARIS test-suite-light runs green; verification doc committed
- **LOC estimate:** 80 (verification doc + provisioning script `--apply` path implementation per existing dry-run substrate)
- **User-blocked:** YES (account, billing, payment)
- **Blocked by:** preconditions §2
- **Blocks:** I-phase0-006, I-phase0-007

### I-phase0-005 — Backend modernization + Dramatiq queue (Carney Task 0.5)

- **Phase:** 0 / **Feature:** infra
- **Scope:** install Dramatiq + Redis, write `Job` + `Worker` skeleton, integration test with single job
- **Acceptance:** Dramatiq worker consumes job from queue; result materialized in DB; integration test green
- **Foundation refs:** Carney v6.2 §Phase 0 Task 0.5
- **LOC estimate:** 180
- **User-blocked:** NO
- **Blocked by:** preconditions §2
- **Blocks:** I-f1-001, I-cj-001, I-anti-001

### I-phase0-006 — DeepSeek V4 hardware Path A/B/C decision (Carney Task 0.6)

- **Phase:** 0 / **Feature:** infra
- **Scope:** decision document `docs/decisions/0_6_hardware_path.md` with cost/speed/sovereignty matrix; user signs which path
- **Acceptance:** user-signed commit on polaris-controls naming chosen path
- **Foundation refs:** Carney v6.2 §Phase 0 Task 0.6
- **LOC estimate:** 0 (decision document)
- **User-blocked:** YES (strategic decision)
- **Blocked by:** I-phase0-003
- **Blocks:** I-phase0-007, I-phase0-009

### I-phase0-007 — SGLang vs vLLM bakeoff (Carney Task 0.7)

- **Phase:** 0 / **Feature:** infra
- **Scope:** `scripts/bakeoff_sglang_vllm.py` runs identical workload through both engines on Vast.ai GPU; latency, throughput, token/$ measured
- **Acceptance:** decision document `docs/decisions/0_7_inference_engine.md` with chosen engine + benchmark numbers + Codex APPROVE
- **Foundation refs:** Carney v6.2 §Phase 0 Task 0.7
- **LOC estimate:** 200 (script + decision doc)
- **User-blocked:** NO (after I-phase0-003 done)
- **Blocked by:** I-phase0-003, I-phase0-006
- **Blocks:** I-sov-001

### I-phase0-008 — Gemma 4 31B technical verification (Carney Task 0.8 tech portion — RENAMED iter 3)

- **Phase:** 0 / **Feature:** infra
- **Foundation refs:** Carney v6.2 §Phase 0 Task 0.8; memory `v6_phase_0_errata_otel_gemma`
- **Scope:** download Gemma 4 31B weights; checksum-verify against published; smoke-test with single inference
- **Acceptance:** weights downloaded + checksum verified; smoke test runs
- **LOC estimate:** 80
- **User-blocked:** NO
- **Blocked by:** preconditions §2
- **Blocks:** I-phase0-010

### I-phase0-009 — OVH Canada BHS H200 invoice + provisioning (Carney Task 0.9 — HARD GATE)

- **Phase:** 0 / **Feature:** infra
- **Foundation refs:** Carney v6.2 §Phase 0 Task 0.9
- **Scope:** OVH H200 invoice paid, provisioning script ready, sovereign cluster reachable
- **Acceptance:** OVH H200 SSH-reachable from authorized IPs; nvidia-smi shows H200; user-signed commit recording invoice ID
- **LOC estimate:** 60 (provisioning script + verification doc)
- **User-blocked:** YES (procurement + invoice)
- **Blocked by:** I-phase0-006
- **Blocks:** I-sov-001

### I-phase0-010 — Gemma 4 31B license sign-off (Carney Task 0.8 license portion — RENAMED iter 3 from `008-license`)

- **Phase:** 0 / **Feature:** infra
- **Foundation refs:** Carney v6.2 §Phase 0 Task 0.8
- **Scope:** confirm Gemma 4 31B Apache 2.0 + Gemma Use Policy compliance; user signs `docs/licenses/gemma4.md`
- **Acceptance:** user-signed license document
- **LOC estimate:** 0 (sign-off only)
- **User-blocked:** YES (legal sign-off)
- **Blocked by:** I-phase0-008
- **Blocks:** I-sov-001

---

## §5 F1 — Scope discovery + template browse (6 issues)

### I-f1-001 — Next.js landing page Card grid

- **Scope:** `web/app/page.tsx` Card grid renders 3 active + 5 to-build templates; responsive at 1920/1024/768/375; Tailwind v4
- **Acceptance:** 4 viewport Playwright screenshots clean; axe-core WCAG-AA pass; cards link to `/intake?template=<id>`
- **Foundation refs:** Carney v6.2 §F1; substrate `template_catalog.py`, `template_classifier.py`
- **LOC estimate:** 150
- **Blocked by:** I-phase0-005
- **Blocks:** I-f1-002

### I-f1-002 — Command palette + react-hotkeys-hook keyboard nav

- **Scope:** ⌘K opens command palette; arrow-key navigate; Enter selects template
- **Acceptance:** Playwright keyboard-only test passes; no mouse needed
- **Foundation refs:** Carney v6.2 §F1
- **LOC estimate:** 120
- **Blocked by:** I-f1-001
- **Blocks:** I-f1-003

### I-f1-003 — Live template-suggestion as user types

- **Scope:** input "tirzepatide" → suggest "Clinical drug audit" within 200ms (debounced)
- **Acceptance:** Playwright timing test under 200ms; suggestion overlay positioned correctly; mobile tap-to-show
- **LOC estimate:** 140
- **Blocked by:** I-f1-002
- **Blocks:** I-f1-004

### I-f1-004 — Template adversarial test: "BPEI" → no false-positive

- **Scope:** input "BPEI" must NOT suggest any template
- **Acceptance:** Playwright + AI-agent adversarial test confirms no false-positive across 22-input adversarial corpus
- **LOC estimate:** 100
- **Blocked by:** I-f1-003
- **Blocks:** I-f1-005

### I-f1-005 — F1 axe-core WCAG-AA compliance test

- **Scope:** automated accessibility scan
- **Acceptance:** zero serious/critical violations
- **LOC estimate:** 60
- **Blocked by:** I-f1-004
- **Blocks:** I-f1-006

### I-f1-006 — F1 multi-tab safety test (3 tabs, no state pollution)

- **Scope:** open 3 tabs each with different query; no global-state leakage between tabs
- **Acceptance:** Playwright parallel-context test passes
- **LOC estimate:** 80
- **Blocked by:** I-f1-005
- **Blocks:** I-f2-001

---

## §6 F2 — Query input with disambiguation modal (8 issues)

### I-f2-001 — Backend: HDBSCAN clustering on top-K retrieval candidates

- **Scope:** `src/polaris_graph/intake/disambiguation_clusterer.py`; cluster top-K (default 30) candidate embeddings; HDBSCAN min_cluster_size=2
- **Acceptance:** unit tests with synthetic embedding sets; >1 cluster surfaces ambiguity; single dense cluster does not
- **Foundation:** v6.2 §F2 Diversify-then-Verify
- **LOC estimate:** 180
- **Blocked by:** I-f1-006
- **Blocks:** I-f2-002

### I-f2-002 — Backend: LLM cluster-labeling per primary entity

- **Scope:** `src/polaris_graph/intake/cluster_labeler.py`
- **Acceptance:** "BPEI" clusters → 3 labels: syndrome, institute, chemical
- **LOC estimate:** 130
- **Blocked by:** I-f2-001
- **Blocks:** I-f2-003

### I-f2-003 — Backend: disambiguation API endpoint

- **Scope:** POST `/api/disambiguation` returns clusters
- **Acceptance:** OpenAPI valid; httpx test green
- **LOC estimate:** 120
- **Blocked by:** I-f2-002
- **Blocks:** I-f2-004

### I-f2-004 — Frontend: disambiguation modal (2/3/5 candidate variants)

- **Scope:** `web/app/intake/components/DisambiguationModal.tsx`
- **Acceptance:** Playwright visual test all variants clean
- **LOC estimate:** 160
- **Blocked by:** I-f2-003
- **Blocks:** I-f2-005

### I-f2-005 — F2 functional test: BPEI end-to-end

- **Scope:** Playwright: type → submit → modal → 3 candidates → pick → query proceeds
- **Acceptance:** test passes; latency tooltip-to-modal <500ms
- **LOC estimate:** 100
- **Blocked by:** I-f2-004
- **Blocks:** I-f2-006

### I-f2-006 — F2 adversarial: tirzepatide → no false disambiguation

- **Scope:** single primary entity → no modal
- **Acceptance:** Playwright zero modal renders for unambiguous queries
- **LOC estimate:** 80
- **Blocked by:** I-f2-005
- **Blocks:** I-f2-007

### I-f2-007 — F2 edge: French / PDF drop

- **Scope:** non-English → English-only message; PDF on /intake → routes to /upload
- **Acceptance:** edge tests pass
- **LOC estimate:** 100
- **Blocked by:** I-f2-006
- **Blocks:** I-f2-008

### I-f2-008 — F2 evaluator walkthrough

- **Scope:** product-owner walkthrough; record-screen 3 sessions × 22-input corpus
- **Acceptance:** all 22 handled correctly per recording review
- **LOC estimate:** 0 (walkthrough; no code)
- **Blocked by:** I-f2-007
- **Blocks:** I-bug-079

---

## §7 I-bug-079 — async/sync collision in clinical_classifier (reissued)

- **Phase:** 1 / **Feature:** F1 (intake)
- **Scope:** fix `_default_llm_completion` to drive async `OpenRouterClient.generate` via `asyncio.run`; raise RuntimeError if called from running event loop
- **Acceptance:** smoke test under real key returns `scope_class=clinical_efficacy`; 5 regression tests
- **Foundation refs:** plan §4.9b
- **LOC estimate:** 80
- **Blocked by:** I-f2-008
- **Blocks:** I-f3-001

---

## §8 F3 — Document upload + grounding (10 issues)

### I-f3-001 — Backend: wire document_ids into graph_v4 evidence pool

- **Scope:** `src/polaris_graph/graph_v4.py:149` consume `document_ids`; merge document evidence into pool
- **Acceptance:** integration test: upload PDF → query references content → strict_verify cites span
- **Foundation:** v6.2 §F3 CRITICAL GAP
- **LOC estimate:** 200
- **Blocked by:** I-bug-079
- **Blocks:** I-f3-002

### I-f3-002 — Backend: data classification taxonomy

- **Scope:** `src/polaris_graph/sovereignty/classification.py`; enum `PUBLIC_SYNTHETIC | CAN_REAL | PRIVATE | CLIENT | UNKNOWN`
- **Acceptance:** unit tests; serializable to JSON
- **LOC estimate:** 100
- **Blocked by:** I-f3-001
- **Blocks:** I-f3-003

### I-f3-003 — Backend: sovereignty router

- **Scope:** `src/polaris_graph/sovereignty/router.py`; intercepts CLIENT-tagged docs from external API
- **Acceptance:** unit + integration; CLIENT cannot leak
- **LOC estimate:** 180
- **Blocked by:** I-f3-002
- **Blocks:** I-f3-004

### I-f3-004 — Backend: sovereignty CI test

- **Scope:** `.github/workflows/sovereignty.yml` runs CLIENT-doc-cannot-leak test
- **Acceptance:** CI fails on intentional violation
- **LOC estimate:** 80
- **Blocked by:** I-f3-003
- **Blocks:** I-f3-005

### I-f3-005 — Frontend: drag-drop upload zone

- **Scope:** `web/app/upload/page.tsx`; shadcn dropzone + react-dropzone; 50MB limit
- **Acceptance:** Playwright drag 50MB PDF → progress visible
- **LOC estimate:** 150
- **Blocked by:** I-f3-004
- **Blocks:** I-f3-006

### I-f3-006 — Frontend: per-file parse status

- **Scope:** parsed-chunks list as DocumentIngester progresses
- **Acceptance:** Playwright watches progression
- **LOC estimate:** 120
- **Blocked by:** I-f3-005
- **Blocks:** I-f3-007

### I-f3-007 — Frontend: doc preview with chunk highlights

- **Scope:** PDF.js preview + click chunk → highlight at coordinates
- **Acceptance:** Playwright span/coords accurate
- **LOC estimate:** 180
- **Blocked by:** I-f3-006
- **Blocks:** I-f3-008

### I-f3-008 — Frontend: "use these docs as evidence" toggle

- **Scope:** per-doc toggle gates inclusion in evidence pool
- **Acceptance:** Playwright; backend echoes inclusion
- **LOC estimate:** 100
- **Blocked by:** I-f3-007
- **Blocks:** I-f3-009

### I-f3-009 — F3 adversarial: 8 input types

- **Scope:** 100MB, 0-byte, malformed, password, image-only, Word, txt, EPUB
- **Acceptance:** each handled per spec
- **LOC estimate:** 200
- **Blocked by:** I-f3-008
- **Blocks:** I-f3-010

### I-f3-010 — F3 sovereignty walkthrough

- **Scope:** product-owner upload-and-fact-check walkthrough
- **Acceptance:** recording: CLIENT classification visible, no external API call
- **LOC estimate:** 0 (walkthrough)
- **Blocked by:** I-f3-009
- **Blocks:** I-f15-001

---

## §9 F15 — Audit bundle export (6 issues)

### I-f15-001 — Bundle schema

- **Scope:** `src/polaris_graph/audit_bundle/schema.py`; manifest + 6 component files + reviewer README
- **Acceptance:** Pydantic models; jsonschema validates
- **Foundation:** v6.2 §F15
- **LOC estimate:** 200
- **Blocked by:** I-f3-010
- **Blocks:** I-f15-002

### I-f15-002 — Embed extracted span text ≤500 chars

- **Scope:** truncate spans; preserve UTF-8 boundaries
- **Acceptance:** unit test; multilingual safe
- **LOC estimate:** 80
- **Blocked by:** I-f15-001
- **Blocks:** I-f15-003

### I-f15-003 — Bundle preview pane in report header

- **Scope:** `web/app/generation/components/BundlePreview.tsx`
- **Acceptance:** Playwright preview accurate
- **LOC estimate:** 130
- **Blocked by:** I-f15-002
- **Blocks:** I-f15-004

### I-f15-004 — Standalone-verifiable test

- **Scope:** README explains structure; reviewer-blind test
- **Acceptance:** random claim → span found <5min
- **LOC estimate:** 100
- **Blocked by:** I-f15-003
- **Blocks:** I-f15-005

### I-f15-005 — F15 adversarial: paywalled, 500MB resumable, partial run

- **Scope:** 3 adversarial tests
- **Acceptance:** each handled per spec
- **LOC estimate:** 150
- **Blocked by:** I-f15-004
- **Blocks:** I-f15-006

### I-f15-006 — Sovereignty CI: legal-cleared spans only

- **Scope:** CI rejects bundle with copyrighted span
- **Acceptance:** CI fails on violation
- **LOC estimate:** 100
- **Blocked by:** I-f15-005
- **Blocks:** I-bug-082

---

## §10 I-bug-082 — audit-bundle health endpoint hardcoded sentinel (reissued)

- **Scope:** `/api/audit-bundle/health` uses `Depends(get_sign_fn)`
- **Acceptance:** health test with `POLARIS_GPG_KEY_ID` returns `signing_backend: gpg`
- **Foundation refs:** plan §4.9b
- **LOC estimate:** 60
- **Blocked by:** I-f15-006
- **Blocks:** I-ecg-001

---

## §11 Evidence Contract Gate (4 issues)

### I-ecg-001 — Contract schema
- **Scope:** `src/polaris_graph/evidence_contract/schema.py`; entities, claims, jurisdictions, expected sources
- **Acceptance:** Pydantic schema; tests
- **Foundation:** v6.2 §Phase 1 ECG
- **LOC estimate:** 180
- **Blocked by:** I-bug-082
- **Blocks:** I-ecg-002

### I-ecg-002 — Gate enforcement
- **Scope:** `src/polaris_graph/evidence_contract/gate.py`; raises if generation without contract
- **Acceptance:** integration test
- **LOC estimate:** 130
- **Blocked by:** I-ecg-001
- **Blocks:** I-ecg-003

### I-ecg-003 — Contract editor UI
- **Scope:** `web/app/contracts/page.tsx`
- **Acceptance:** Playwright create/edit/save
- **LOC estimate:** 200
- **Blocked by:** I-ecg-002
- **Blocks:** I-ecg-004

### I-ecg-004 — Contract version migration test
- **Scope:** v1 → v2 schema migration; backward-compat
- **Acceptance:** migration test on fixture v1 contracts
- **LOC estimate:** 100
- **Blocked by:** I-ecg-003
- **Blocks:** I-f4-001

---

## §12 F4 — Live audit run (5 issues)

### I-f4-001 — SSE EventSource consumer with reconnect/backoff
- **Scope:** `web/lib/sse_client.ts`; reconnect on drop with exponential backoff
- **Acceptance:** Playwright force-disconnect → reconnects within 2s
- **LOC estimate:** 150
- **Blocked by:** I-ecg-004
- **Blocks:** I-f4-002

### I-f4-002 — Event-type UI affordances
- **Scope:** 6 event types render as dedicated UI: query reformulations, retrieval candidates, sources dropped, synthesis decisions, contradiction events, per-sentence verify decisions
- **Acceptance:** Playwright full-run recording 5-10min — every event appears within 1s of server emit
- **LOC estimate:** 200
- **Blocked by:** I-f4-001
- **Blocks:** I-f4-003

### I-f4-003 — Multi-tab independent updates
- **Scope:** open same run in 2 tabs; cancel in one cancels both
- **Acceptance:** Playwright parallel-context test
- **LOC estimate:** 120
- **Blocked by:** I-f4-002
- **Blocks:** I-f4-004

### I-f4-004 — Adversarial: 80% fetch fail; strict_verify drops all
- **Scope:** UI shows partial-evidence warning; zero-verified abort
- **Acceptance:** adversarial Playwright tests
- **LOC estimate:** 130
- **Blocked by:** I-f4-003
- **Blocks:** I-f4-005

### I-f4-005 — F4 200-sentence walkthrough
- **Scope:** product-owner recording on 200-sentence run
- **Acceptance:** hover/click latency <1s
- **LOC estimate:** 0 (walkthrough)
- **Blocked by:** I-f4-004
- **Blocks:** I-f5-001

---

## §13 F5 — Report inspection (11 issues)

### I-f5-001 — Hover-highlight every claim sentence
- **Scope:** intersection observer; debounced
- **Acceptance:** Playwright hover at random sentence highlights
- **LOC estimate:** 150
- **Blocked by:** I-f4-005
- **Blocks:** I-f5-002

### I-f5-002 — Click → Inspector pane (Sheet, 40% width)
- **Scope:** shadcn Sheet from right
- **Acceptance:** Playwright click sentence → Sheet opens
- **LOC estimate:** 130
- **Blocked by:** I-f5-001
- **Blocks:** I-f5-003

### I-f5-003 — Inspector: source span + URL + tier + retrieval trace
- **Scope:** highlighted span; tier badge with rationale; retrieval steps
- **Acceptance:** Playwright Inspector content correct
- **LOC estimate:** 180
- **Blocked by:** I-f5-002
- **Blocks:** I-f5-004

### I-f5-004 — Inspector: two-family evaluator agreement signal
- **Scope:** badge showing generator/evaluator agreement
- **Acceptance:** Playwright; backend signal correct
- **LOC estimate:** 100
- **Blocked by:** I-f5-003
- **Blocks:** I-f5-005

### I-f5-005 — Inspector: multi-span support
- **Scope:** claims with N spans show all N
- **Acceptance:** Playwright multi-span test
- **LOC estimate:** 110
- **Blocked by:** I-f5-004
- **Blocks:** I-f5-006

### I-f5-006 — Inspector: synthesis-claim badge
- **Scope:** when no direct span, show synthesis-claim badge
- **Acceptance:** Playwright detection
- **LOC estimate:** 80
- **Blocked by:** I-f5-005
- **Blocks:** I-f5-007

### I-f5-007 — Inspector: retracted-source + stale (>2y) badges
- **Scope:** stale + retracted-source badges
- **Acceptance:** Playwright; backend metadata
- **LOC estimate:** 100
- **Blocked by:** I-f5-006
- **Blocks:** I-f5-008

### I-f5-008 — F5 latency at 50/100/200/500 sentences
- **Scope:** stress test
- **Acceptance:** all under 1s
- **LOC estimate:** 100
- **Blocked by:** I-f5-007
- **Blocks:** I-f5-009

### I-f5-009 — F5 functional: every assertion gated-and-clickable
- **Scope:** prose, table, summary bullet, limitation, caption, heading — all clickable OR marked ungated
- **Acceptance:** Playwright comprehensive
- **LOC estimate:** 150
- **Blocked by:** I-f5-008
- **Blocks:** I-f5-010

### I-f5-010 — F5 adversarial: paywalled span, multi-span claim, T1-vs-T1 conflict
- **Scope:** 3 adversarial cases
- **Acceptance:** each handled
- **LOC estimate:** 120
- **Blocked by:** I-f5-009
- **Blocks:** I-f5-011

### I-f5-011 — F5 AI agent test
- **Scope:** independent agent navigates 10 random sentences
- **Acceptance:** each opens evidence within 1s
- **LOC estimate:** 100
- **Blocked by:** I-f5-010
- **Blocks:** I-f7-001

---

## §14 F7 — Frame coverage (4 issues)

### I-f7-001 — Top-of-report panel
- **Scope:** Alert + Progress component above-the-fold
- **Acceptance:** 14/15 entities → "1 gap: <name>, reason"
- **LOC estimate:** 120
- **Blocked by:** I-f5-011
- **Blocks:** I-f7-002

### I-f7-002 — Gap reason taxonomy frozen as enum
- **Scope:** paywalled / no OA / source-tier ineligible / etc.
- **Acceptance:** enum exhaustive; tests
- **LOC estimate:** 80
- **Blocked by:** I-f7-001
- **Blocks:** I-f7-003

### I-f7-003 — Each gap clickable → unblock action
- **Scope:** click gap → detail panel + documented unblock
- **Acceptance:** Playwright; copy-to-clipboard
- **LOC estimate:** 130
- **Blocked by:** I-f7-002
- **Blocks:** I-f7-004

### I-f7-004 — F7 adversarial: 0/15, 15/15, 1/15
- **Scope:** edge variants
- **Acceptance:** each renders correctly
- **LOC estimate:** 100
- **Blocked by:** I-f7-003
- **Blocks:** I-f8-001

---

## §15 F8 — Contradiction navigation (6 issues)

### I-f8-001 — Inline `⚠ N sources disagree` badge
- **Scope:** badge in body
- **Acceptance:** Playwright detects badge in contradicting prose
- **LOC estimate:** 110
- **Blocked by:** I-f7-004
- **Blocks:** I-f8-002

### I-f8-002 — Side pane with all sides
- **Scope:** Sheet + tiers + sample sizes + hedge language + per-flag PT08
- **Acceptance:** Playwright pane content correct
- **LOC estimate:** 200
- **Blocked by:** I-f8-001
- **Blocks:** I-f8-003

### I-f8-003 — F8 adversarial: contradicting paragraphs same source
- **Scope:** "X is safe" + "X is dangerous" same source → flagged
- **Acceptance:** test detects
- **LOC estimate:** 100
- **Blocked by:** I-f8-002
- **Blocks:** I-f8-004

### I-f8-004 — Non-numeric contradictions
- **Scope:** "is approved" vs "is not approved"
- **Acceptance:** detected
- **LOC estimate:** 90
- **Blocked by:** I-f8-003
- **Blocks:** I-f8-005

### I-f8-005 — Guideline-vs-trial conflict
- **Scope:** distinct conflict type
- **Acceptance:** rendered with type tag
- **LOC estimate:** 80
- **Blocked by:** I-f8-004
- **Blocks:** I-f8-006

### I-f8-006 — Jurisdictional disagreement display
- **Scope:** Canada/US/EU/UK contradictions
- **Acceptance:** jurisdiction tags visible
- **LOC estimate:** 100
- **Blocked by:** I-f8-005
- **Blocks:** I-f9-001

---

## §16 F9 — Two-family disagreement signal (3 issues)

### I-f9-001 — Per-claim badge
- **Scope:** "⚠ Internal evaluator flagged this"
- **Acceptance:** Playwright detects badge
- **LOC estimate:** 100
- **Blocked by:** I-f8-006
- **Blocks:** I-f9-002

### I-f9-002 — Side pane: generator vs evaluator readings
- **Scope:** show both readings + evidence each cited
- **Acceptance:** Playwright pane content
- **LOC estimate:** 150
- **Blocked by:** I-f9-001
- **Blocks:** I-f9-003

### I-f9-003 — F9 edge: no disagreements / all disagreements
- **Scope:** boundary tests
- **Acceptance:** UI handles each
- **LOC estimate:** 80
- **Blocked by:** I-f9-002
- **Blocks:** I-f6-001

---

## §17 F6 — Live citation overlay (5 issues)

### I-f6-001 — Hover-card with debounced rendering
- **Scope:** existing `web/components/ui/evidence-tooltip.tsx` extended
- **Acceptance:** hover percentage → tooltip with quote + tier + timestamp
- **LOC estimate:** 130
- **Blocked by:** I-f9-003
- **Blocks:** I-f6-002

### I-f6-002 — Edge-aware positioning
- **Scope:** near viewport edge → repositions
- **Acceptance:** Playwright edge cases
- **LOC estimate:** 100
- **Blocked by:** I-f6-001
- **Blocks:** I-f6-003

### I-f6-003 — Mobile tap-to-show fallback
- **Scope:** no hover on mobile → tap shows
- **Acceptance:** mobile Playwright
- **LOC estimate:** 90
- **Blocked by:** I-f6-002
- **Blocks:** I-f6-004

### I-f6-004 — Multi-source claim cross-ref panel
- **Scope:** count "5 sources" → click → panel with all 5
- **Acceptance:** Playwright cross-ref
- **LOC estimate:** 130
- **Blocked by:** I-f6-003
- **Blocks:** I-f6-005

### I-f6-005 — F6 perf: 100x hover consistent <100ms
- **Scope:** rendering perf test
- **Acceptance:** consistent under threshold
- **LOC estimate:** 70
- **Blocked by:** I-f6-004
- **Blocks:** I-f10-001

---

## §18 F10 — Inline visual generation (8 issues)

### I-f10-001 — Vega-Lite renderer (react-vega + Vega-Lite v5)
- **Scope:** wire react-vega
- **Acceptance:** sample chart renders
- **LOC estimate:** 120
- **Blocked by:** I-f6-005
- **Blocks:** I-f10-002

### I-f10-002 — Forest plot chart spec
- **Scope:** spec generator + tests
- **Acceptance:** sample meta-analysis renders
- **LOC estimate:** 150
- **Blocked by:** I-f10-001
- **Blocks:** I-f10-003

### I-f10-003 — Comparison table chart spec
- **Scope:** auto-table when comparing N entities
- **Acceptance:** N=2,3,5 render correctly
- **LOC estimate:** 130
- **Blocked by:** I-f10-002
- **Blocks:** I-f10-004

### I-f10-004 — Timeline chart spec
- **Scope:** time-series Vega-Lite
- **Acceptance:** sample timeline renders
- **LOC estimate:** 130
- **Blocked by:** I-f10-003
- **Blocks:** I-f10-005

### I-f10-005 — Chart provenance schema
- **Scope:** every chart cites source data via Evidence Contract spans
- **Acceptance:** schema; tests
- **LOC estimate:** 100
- **Blocked by:** I-f10-004
- **Blocks:** I-f10-006

### I-f10-006 — Click-through-to-source-data
- **Scope:** click chart point → opens Inspector with source span
- **Acceptance:** Playwright click-through
- **LOC estimate:** 110
- **Blocked by:** I-f10-005
- **Blocks:** I-f10-007

### I-f10-007 — Sandboxed Python execution (no-egress, resource-capped)
- **Scope:** existing code_executor.py hardened; egress blocked
- **Acceptance:** sovereignty CI test
- **LOC estimate:** 200
- **Blocked by:** I-f10-006
- **Blocks:** I-f10-008

### I-f10-008 — F10 walkthrough: tirzepatide vs semaglutide
- **Scope:** product-owner recording
- **Acceptance:** auto-table generated with citations
- **LOC estimate:** 0 (walkthrough)
- **Blocked by:** I-f10-007
- **Blocks:** I-f13-001

---

## §19 F13 — Pin replay (4 issues)

### I-f13-001 — Pin replay UI
- **Scope:** same query rerun on different dates
- **Acceptance:** Playwright switch dates
- **LOC estimate:** 150
- **Blocked by:** I-f10-008
- **Blocks:** I-f13-002

### I-f13-002 — Diff visualization
- **Scope:** Vega-Lite time-series; diff side-panel
- **Acceptance:** Playwright diff
- **LOC estimate:** 180
- **Blocked by:** I-f13-001
- **Blocks:** I-f13-003

### I-f13-003 — Regression alerts inline
- **Scope:** alert badges when metric drops >threshold
- **Acceptance:** alert fires on test fixture
- **LOC estimate:** 100
- **Blocked by:** I-f13-002
- **Blocks:** I-f13-004

### I-f13-004 — F13 adversarial: source retraction during replay
- **Scope:** retracted source mid-replay → handled
- **Acceptance:** test
- **LOC estimate:** 90
- **Blocked by:** I-f13-003
- **Blocks:** I-f14-001

---

## §20 F14 — Auditable research memory (5 issues)

### I-f14-001 — Migrate workspace_memory to Chroma semantic
- **Scope:** keyword/Jaccard → ChromaDB embedding-based
- **Acceptance:** semantic recall test
- **LOC estimate:** 200
- **Blocked by:** I-f13-004
- **Blocks:** I-f14-002

### I-f14-002 — Memory page with explicit controls
- **Scope:** save / pin / forget UI
- **Acceptance:** Playwright controls
- **LOC estimate:** 150
- **Blocked by:** I-f14-001
- **Blocks:** I-f14-003

### I-f14-003 — Cross-session surfacing
- **Scope:** "you researched X last week"
- **Acceptance:** test
- **LOC estimate:** 110
- **Blocked by:** I-f14-002
- **Blocks:** I-f14-004

### I-f14-004 — Memory-as-corpus for new queries
- **Scope:** prior runs join evidence pool
- **Acceptance:** integration test
- **LOC estimate:** 130
- **Blocked by:** I-f14-003
- **Blocks:** I-f14-005

### I-f14-005 — Cited recall
- **Scope:** when memory contributes, surface which past run + claim
- **Acceptance:** Playwright shows cite-in-current
- **LOC estimate:** 100
- **Blocked by:** I-f14-004
- **Blocks:** I-p2c-001

---

## §21 Phase 2C polish (5 issues)

### I-p2c-001 — Cross-feature integration testing
- **Scope:** F1→F2→F3→F4→F5 chain
- **Acceptance:** integration suite green
- **LOC estimate:** 180
- **Blocked by:** I-f14-005
- **Blocks:** I-p2c-002

### I-p2c-002 — Visual regression: 60 baselines (4 viewports × 15 features)
- **Scope:** Playwright + percy.io baselines
- **Acceptance:** zero unintended pixel diffs
- **LOC estimate:** 200
- **Blocked by:** I-p2c-001
- **Blocks:** I-p2c-003

### I-p2c-003 — Cross-browser: Chromium / Firefox / WebKit
- **Scope:** Playwright across 3 browsers
- **Acceptance:** all pass
- **LOC estimate:** 130
- **Blocked by:** I-p2c-002
- **Blocks:** I-p2c-004

### I-p2c-004 — Performance: Core Web Vitals green
- **Scope:** Lighthouse + perf test
- **Acceptance:** LCP <2.5s, INP <200ms, hover-latency <100ms
- **LOC estimate:** 150
- **Blocked by:** I-p2c-003
- **Blocks:** I-p2c-005

### I-p2c-005 — Mobile end-to-end
- **Scope:** mobile viewport full flow
- **Acceptance:** Playwright mobile
- **LOC estimate:** 130
- **Blocked by:** I-p2c-004
- **Blocks:** I-f11-001

---

## §22 F11 — Auditable follow-up (5 issues)

### I-f11-001 — Follow-up agent with parent-run-context preservation
- **Scope:** `src/polaris_graph/followup/agent.py`
- **Acceptance:** parent context preserved test
- **LOC estimate:** 200
- **Blocked by:** I-p2c-005
- **Blocks:** I-f11-002

### I-f11-002 — Append-to-existing-report rendering
- **Scope:** UI appends below original with separator
- **Acceptance:** Playwright; clear separator visible
- **LOC estimate:** 110
- **Blocked by:** I-f11-001
- **Blocks:** I-f11-003

### I-f11-003 — Evidence Contract inheritance
- **Scope:** follow-up inherits parent's accepted-source pool
- **Acceptance:** integration; no re-retrieval of parent
- **LOC estimate:** 130
- **Blocked by:** I-f11-002
- **Blocks:** I-f11-004

### I-f11-004 — Refusal handling for out-of-scope follow-ups
- **Scope:** out-of-scope follow-up → refusal-with-explanation
- **Acceptance:** adversarial test
- **LOC estimate:** 90
- **Blocked by:** I-f11-003
- **Blocks:** I-f11-005

### I-f11-005 — F11 multi-turn: 5 sequential follow-ups
- **Scope:** 5 follow-ups grounded correctly
- **Acceptance:** test
- **LOC estimate:** 100
- **Blocked by:** I-f11-004
- **Blocks:** I-f12-001

---

## §23 F12 — Side-by-side compare (4 issues)

### I-f12-001 — Two-run picker UI
- **Scope:** pick any 2 completed runs
- **Acceptance:** Playwright pick
- **LOC estimate:** 110
- **Blocked by:** I-f11-005
- **Blocks:** I-f12-002

### I-f12-002 — Split-screen view (ResizablePanels)
- **Scope:** shadcn ResizablePanels
- **Acceptance:** Playwright split-screen
- **LOC estimate:** 130
- **Blocked by:** I-f12-001
- **Blocks:** I-f12-003

### I-f12-003 — Claim-level diff algorithm
- **Scope:** claims agree/disagree/evidence-pool overlap
- **Acceptance:** diff sample fixtures
- **LOC estimate:** 200
- **Blocked by:** I-f12-002
- **Blocks:** I-f12-004

### I-f12-004 — F12 functional: jurisdictional diff
- **Scope:** same query different jurisdictions
- **Acceptance:** show jurisdictional differences
- **LOC estimate:** 100
- **Blocked by:** I-f12-003
- **Blocks:** I-bug-084

---

## §24 I-bug-084 — coverage scorer keywords (reissued)

- **Scope:** add `expected_pico_keywords` field; scorer prefers keywords when set
- **Acceptance:** aspirin/migraine with keywords scores 1.0; without keywords falls back
- **Foundation refs:** plan §4.9b
- **LOC estimate:** 90
- **Blocked by:** I-f12-004
- **Blocks:** I-bench-001

---

## §25 Benchmark + templates (5 issues)

### I-bench-001 — 50 questions × 4 systems × 6 dimensions
- **Scope:** benchmark harness `scripts/benchmark_proof_package.py`
- **Acceptance:** harness runs end-to-end
- **LOC estimate:** 200
- **Blocked by:** I-bug-084
- **Blocks:** I-bench-002

### I-bench-002 — Paid sample evaluator scoring
- **Scope:** $5-12k procurement; evaluator scores benchmark slice
- **Acceptance:** evaluator delivers scoring report
- **LOC estimate:** 0 (procurement + integration of report)
- **User-blocked:** YES (procurement)
- **Blocked by:** I-bench-001
- **Blocks:** I-tpl-006

### I-tpl-006 — AI sovereignty template
- **Scope:** new template + scope examples
- **Acceptance:** classifier correctly suggests
- **LOC estimate:** 150
- **Blocked by:** I-bench-002
- **Blocks:** I-tpl-007

### I-tpl-007 — Canada-US template
- **Scope:** new template
- **Acceptance:** classifier suggests
- **LOC estimate:** 150
- **Blocked by:** I-tpl-006
- **Blocks:** I-tpl-008

### I-tpl-008 — Workforce template
- **Scope:** new template
- **Acceptance:** classifier suggests
- **LOC estimate:** 150
- **Blocked by:** I-tpl-007
- **Blocks:** I-sov-001

---

## §26 Phase 4 sovereign migration (4 issues)

### I-sov-001 — Replace OpenRouter with sovereign vLLM
- **Scope:** swap LLM client; sovereignty router enforces
- **Acceptance:** integration test on sovereign cluster
- **LOC estimate:** 200
- **Blocked by:** I-tpl-008, I-phase0-007, I-phase0-010, I-phase0-009
- **Blocks:** I-sov-002

### I-sov-002 — Validate quality unchanged
- **Scope:** paired-prompt eval comparing OpenRouter vs sovereign
- **Acceptance:** quality delta within 5%
- **LOC estimate:** 150
- **Blocked by:** I-sov-001
- **Blocks:** I-sov-003

### I-sov-003 — Re-run F-INT regression suite on sovereign topology
- **Scope:** full regression
- **Acceptance:** all green
- **LOC estimate:** 80
- **Blocked by:** I-sov-002
- **Blocks:** I-sov-004

### I-sov-004 — Two-family segregation re-verification
- **Scope:** check_family_segregation passes on sovereign generator + verifier
- **Acceptance:** test green
- **LOC estimate:** 60
- **Blocked by:** I-sov-003
- **Blocks:** I-buf-001

---

## §27 Phase 4.5 buffer (1 issue)

### I-buf-001 — Migration findings + regression fixes
- **Scope:** catch-all for issues found in Phase 4
- **Acceptance:** issues triaged + fixed
- **LOC estimate:** 200 (variable; cap enforces split if needed)
- **Blocked by:** I-sov-004
- **Blocks:** I-hand-001

---

## §28 Phase 5 Carney handover (3 issues)

### I-hand-001 — Final walkthrough + Codex sweep
- **Scope:** product-owner end-to-end walkthrough; Codex full audit
- **Acceptance:** walkthrough recorded; Codex APPROVE
- **LOC estimate:** 0 (walkthrough)
- **Blocked by:** I-buf-001
- **Blocks:** I-hand-002

### I-hand-002 — Handover package
- **Scope:** runbook + demo script + crown-jewel registry + handover.md
- **Acceptance:** package complete
- **LOC estimate:** 200
- **Blocked by:** I-hand-001
- **Blocks:** I-hand-003

### I-hand-003 — Carney office demo
- **Scope:** Sep 6 demo to Carney office
- **Acceptance:** demo completes; deliverable accepted
- **LOC estimate:** 0 (demo)
- **Blocked by:** I-hand-002
- **Blocks:** none (terminal)

---

## §29 Crown jewel preservation (7 issues, parallel side-track — FIXED P1-CJ-GATE-CONFLICT)

These run in parallel after I-phase0-005 (Dramatiq queue live, so test infrastructure works). The earlier reference in iter 1 to "after I-f1-006" was inconsistent; corrected to single rule: `addBlockedBy = I-phase0-005`.

### I-cj-001 — Two-family evaluator test
- **Scope:** test asserts `check_family_segregation` raises on violation
- **Acceptance:** test green; fixture violation triggers raise
- **LOC estimate:** 80
- **Blocked by:** I-phase0-005
- **Blocks:** I-cj-002

### I-cj-002 — Provenance token test
- **Scope:** every generated sentence has `[#ev:source_id:start-end]`
- **Acceptance:** test green
- **LOC estimate:** 70
- **Blocked by:** I-cj-001
- **Blocks:** I-cj-003

### I-cj-003 — Strict-verify test
- **Scope:** per-sentence numeric match + ≥2 content-word overlap
- **Acceptance:** test green; mutation tests verify gate teeth
- **LOC estimate:** 100
- **Blocked by:** I-cj-002
- **Blocks:** I-cj-004

### I-cj-004 — Zero-verified abort test
- **Scope:** assert `abort_no_verified_sections` fires when all sections fail
- **Acceptance:** test
- **LOC estimate:** 80
- **Blocked by:** I-cj-003
- **Blocks:** I-cj-005

### I-cj-005 — Corpus approval enforcement test
- **Scope:** rubber-stamp note + material deviation → `abort_corpus_approval_denied`
- **Acceptance:** test
- **LOC estimate:** 80
- **Blocked by:** I-cj-004
- **Blocks:** I-cj-006

### I-cj-006 — Budget cap test
- **Scope:** `_impute_cost_from_tokens` backstops token-only responses
- **Acceptance:** test
- **LOC estimate:** 70
- **Blocked by:** I-cj-005
- **Blocks:** I-cj-007

### I-cj-007 — Delimiter sanitization test
- **Scope:** NFKD, invisible chars, homoglyph evasions all neutralized
- **Acceptance:** test
- **LOC estimate:** 90
- **Blocked by:** I-cj-006
- **Blocks:** none (terminal in side-track)

---

## §30 Anti-sycophancy CI (4 issues, parallel side-track)

These run in parallel after I-phase0-005 (Dramatiq stack present for nightly job).

### I-anti-001 — Paired-prompt corpus
- **Scope:** neutral / leading / opposite-frame triples for 20 questions
- **Acceptance:** corpus committed
- **LOC estimate:** 100 (mostly data)
- **Blocked by:** I-phase0-005
- **Blocks:** I-anti-002

### I-anti-002 — Stance-delta computation
- **Scope:** `src/polaris_graph/anti_sycophancy/stance_delta.py`
- **Acceptance:** unit tests on fixture corpus
- **LOC estimate:** 130
- **Blocked by:** I-anti-001
- **Blocks:** I-anti-003

### I-anti-003 — CI gate at <5% delta on 20 paired prompts
- **Scope:** `.github/workflows/anti_sycophancy.yml`
- **Acceptance:** CI runs; >5% fails build
- **LOC estimate:** 80
- **Blocked by:** I-anti-002
- **Blocks:** I-anti-004

### I-anti-004 — Nightly full eval
- **Scope:** Dramatiq scheduled task; reports to log
- **Acceptance:** nightly run succeeds
- **LOC estimate:** 100
- **Blocked by:** I-anti-003
- **Blocks:** none (terminal in side-track)

---

## §31 Issue count summary (FIXED iter 2 P1-COUNT-MISMATCH)

| Group | Count | Section |
|---|---|---|
| Phase 0 outstanding | 7 (split 0.8 into tech + license) | §4 |
| F1 | 6 | §5 |
| F2 | 8 | §6 |
| Reissued bug 079 | 1 | §7 |
| F3 | 10 | §8 |
| F15 | 6 | §9 |
| Reissued bug 082 | 1 | §10 |
| Evidence Contract Gate | 4 | §11 |
| F4 | 5 | §12 |
| F5 | 11 | §13 |
| F7 | 4 | §14 |
| F8 | 6 | §15 |
| F9 | 3 | §16 |
| F6 | 5 | §17 |
| F10 | 8 | §18 |
| F13 | 4 | §19 |
| F14 | 5 | §20 |
| Phase 2C polish | 5 | §21 |
| F11 | 5 | §22 |
| F12 | 4 | §23 |
| Reissued bug 084 | 1 | §24 |
| Benchmark + templates | 5 | §25 |
| Phase 4 sovereign | 4 | §26 |
| Phase 4.5 buffer | 1 | §27 |
| Phase 5 handover | 3 | §28 |
| Crown jewels (parallel) | 7 | §29 |
| Anti-sycophancy (parallel) | 4 | §30 |
| **TOTAL** | **133** | |

(Iter-2 P1-COUNT-MISMATCH resolved iter 3: cell-by-cell sum is 7+6+8+1+10+6+1+4+5+11+4+6+3+5+8+4+5+5+5+4+1+5+4+1+3+7+4 = 133. Iter-1 over-counted to 137; iter-2 incorrectly stated 138. Cell totals now reconciled. Phase 0 has 7 Issues since Task 0.8 split into tech (I-phase0-008) + license (I-phase0-010); §3 header says "7" not "6".)

---

## §32 Sequential execution chain (top → bottom)

Main chain (sequential, blocks each next Issue):

```
preconditions §2
  → I-phase0-005
  → I-f1-001 → I-f1-002 → I-f1-003 → I-f1-004 → I-f1-005 → I-f1-006
  → I-f2-001 → I-f2-002 → I-f2-003 → I-f2-004 → I-f2-005 → I-f2-006 → I-f2-007 → I-f2-008
  → I-bug-079
  → I-f3-001 → I-f3-002 → I-f3-003 → I-f3-004 → I-f3-005 → I-f3-006 → I-f3-007 → I-f3-008 → I-f3-009 → I-f3-010
  → I-f15-001 → I-f15-002 → I-f15-003 → I-f15-004 → I-f15-005 → I-f15-006
  → I-bug-082
  → I-ecg-001 → I-ecg-002 → I-ecg-003 → I-ecg-004
  → I-f4-001 → I-f4-002 → I-f4-003 → I-f4-004 → I-f4-005
  → I-f5-001 → ... → I-f5-011
  → I-f7-001 → ... → I-f7-004
  → I-f8-001 → ... → I-f8-006
  → I-f9-001 → I-f9-002 → I-f9-003
  → I-f6-001 → ... → I-f6-005
  → I-f10-001 → ... → I-f10-008
  → I-f13-001 → ... → I-f13-004
  → I-f14-001 → ... → I-f14-005
  → I-p2c-001 → ... → I-p2c-005
  → I-f11-001 → ... → I-f11-005
  → I-f12-001 → ... → I-f12-004
  → I-bug-084
  → I-bench-001 → I-bench-002 (USER-BLOCKED)
  → I-tpl-006 → I-tpl-007 → I-tpl-008
  → I-sov-001 → I-sov-002 → I-sov-003 → I-sov-004
  → I-buf-001
  → I-hand-001 → I-hand-002 → I-hand-003
```

Parallel side-tracks (run alongside main chain after I-phase0-005):
- Crown jewels: I-cj-001 → I-cj-002 → I-cj-003 → I-cj-004 → I-cj-005 → I-cj-006 → I-cj-007
- Anti-sycophancy: I-anti-001 → I-anti-002 → I-anti-003 → I-anti-004

Hardware procurement (user-blocked, parallel to all):
- I-phase0-003 → I-phase0-006 → I-phase0-007 (sequential within hardware track)
- I-phase0-006 → I-phase0-009
- I-phase0-008 → I-phase0-010

These three external prerequisites (I-phase0-007 + I-phase0-010 + I-phase0-009) merge with I-tpl-008 (main-chain prerequisite) as the four total prerequisites for I-sov-001.

---

## §33 User-blocked Issues summary (FIXED iter 2 P1-USER-BLOCKED-CONFLICT)

5 Issues require user procurement / signing / decision and CANNOT be auto-progressed:

- I-phase0-003 (Vast.ai account)
- I-phase0-006 (hardware path A/B/C decision)
- I-phase0-010 (Gemma 4 license sign-off ONLY; tech portion I-phase0-008 is auto-progressable)
- I-phase0-009 (OVH H200 invoice)
- I-bench-002 (paid sample evaluator $5-12k procurement)

These are flagged in TaskCreate as user-blocked. Software work continues in main chain; sovereign migration (Phase 4) is gated on I-phase0-007 + I-phase0-010 + I-phase0-009 completing.

---

## §34 Calendar context (FIXED iter 2 P2-CALENDAR — historical only, NOT commitment)

Carney v6.2 §"Phase plan" gives calendar windows for each phase (Phase 1 May 13-31, etc.). These are historical context from the v6.2 document, not execution commitments. Per CHARTER §3 (200-LOC PR cap) + §5 (reviewer-fatigue halt at >3 PRs/24h) + per-Issue Codex iteration cycles, real velocity will diverge from calendar. Execution rate is measured by Issue throughput per day post-execution-start, not by calendar dates.

---

## §35 Halt conditions (CHARTER §5 + plan §10 — FIXED iter 2 P1-VISIBILITY-GAP)

CI workflow `polaris/codex-required.yml` rejects PR if any of:

- Missing any of 5 mandatory artifacts (`.codex/<issue_id>/{brief.md, codex_brief_verdict.txt, codex_diff.patch, codex_diff_audit.txt}` + `outputs/audits/<issue_id>/claude_audit.md`) — explicit list per CHARTER §7 visibility (was 3 in iter 1; corrected to 5; PR-D iter 4 PRD4-P2-001 fix synchronizes with §3 canonical list — `decision.md` was a draft superseded by `codex_diff.patch`)
- Codex `codex_brief_verdict.txt` does not contain `verdict: APPROVE`
- Codex `codex_diff_audit.txt` does not contain `verdict: APPROVE`
- PR > 200 net additions (per CHARTER §3)
- `state/active_issue.json` shows different Issue in_progress (sequence violation)

Halt emitted to `state/halt_<utc>_<reason>.md` on:

- Sequence violation: any attempt to start I-X-NNN+1 while I-X-NNN is not `completed`
- Codex unavailable >1h: halt; do not bypass
- Reviewer fatigue: >3 PRs queued for user in 24h → halt; user-side surface
- 2-cycle repeated root cause: same P1 finding twice across cycles → halt; investigate harness
- SHA pin drift: polaris-controls/CHARTER.md SHA changes between sessions → halt session-start hook
- 200-LOC overflow: redundant with CI but emit halt for tracking

---

## §36 Codex review request iter 4 (was iter 3)

This iter 4 brief addresses all iter-3 findings (1 P1 + 4 P2):

- **iter3 P1-PHASE-METADATA-CONFLICT** → §3a Phase mapping rewritten as deterministic per-prefix list. F6 explicitly assigned ONLY to Phase 2B (was double-listed in 2A and 2B). Each prefix maps to exactly one phase.
- **iter3 P2-ARTIFACT-PATH-AMBIGUITY** → §3 body template line for `outputs/audits/I-<id>/claude_audit.md` rewritten to `outputs/audits/<issue_id>/claude_audit.md` matching §35/§36.
- **iter3 P2-BLOCKS-RECIPROCITY-CJ** → I-phase0-005 Blocks now lists I-cj-001 and I-anti-001 (and I-f1-001) reciprocally with their Blocked-by entries.
- **iter3 P2-BLOCKS-FIELD-POLLUTION** → I-f1-006 Blocks line cleaned to bare ID list (`I-f2-001`); the parenthetical clarification removed so mechanical ID extraction sees only valid Issue IDs.
- **iter3 P2-SOVEREIGN-GATE-WORDING** → §32 sovereign gate wording corrected: "These three external prerequisites (...) merge with I-tpl-008 (main-chain prerequisite) as the four total prerequisites for I-sov-001."

Earlier iter 1 + iter 2 findings carried through and remain addressed.

Codex: emit structured verdict same format as iter 3. APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

## §36-OBSOLETE iter 3 brief (preserved for audit trail)

This iter 3 brief addresses all iter-2 findings (4 P1 + 4 P2):

- **iter2 P1-ID-SCHEMA** → §1 schema clarified to alphanumeric `[a-z0-9]{2,8}` (was "alpha only" which conflicted with `phase0`/`f1`/`2c`). `I-phase0-008-tech`/`-license` renamed to `I-phase0-008` (tech) + `I-phase0-010` (license sign-off). `I-2c-NNN` renamed to `I-p2c-NNN`.
- **iter2 P1-COUNT-MISMATCH** → §31 cell-by-cell sum now 133 (corrected from iter 2's incorrectly-stated 138). §4 header now "7" not "6".
- **iter2 P1-CJ-GATE-CONFLICT** → I-f1-006 Blocks line corrected; crown jewels blocked-by I-phase0-005 only per §29. §32 chain reflects.
- **iter2 P1-INCOMPLETE-METADATA** → new §3a defines default Phase/Feature/Foundation refs inheritance from prefix + section header; CI body-template check (§3) requires brief author to fill these in per §3a defaults plus inline overrides.
- **iter2 P2-BLOCKS-RECIPROCITY** → I-phase0-003 Blocks now lists I-phase0-006 + I-phase0-007 (reciprocal with each's Blocked-by).
- **iter2 P2-ARTIFACT-PATH-AMBIGUITY** → all `.codex/I-<id>/` and `.codex/I-X/` replaced with `.codex/<issue_id>/`. Same for `outputs/audits/<issue_id>/`.
- **iter2 P2-F4-EVENT-COUNT** → I-f4-002 scope now says "6 event types" matching enumeration.
- **iter2 P2-LOC-ZERO-MISMATCH** → I-phase0-003 LOC raised from 0 to 80.

Iter 1 findings carried through both iterations — no regression.

Codex: emit structured verdict same format as iter 2. APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

```
verdict: APPROVE | REQUEST_CHANGES
novel_p0:
  - <id>: <one-sentence finding>
continuing_p0:
  - <id from prior iter>: <one-sentence finding>
p1:
  - <id>: <one-sentence finding>
p2:
  - <id>: <one-sentence finding>
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: <list any user-blocked items>
```

No exec exploration unless verifying a specific concern. No toothpaste-squeeze. List ALL remaining issues this iteration.
