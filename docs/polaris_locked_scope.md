# POLARIS — Locked Scope (Carney demo)

**Status:** LOCKED 2026-05-15. **Issue:** I-rdy-001 (#497), Phase 0A of the
Carney demo execution plan.

**Purpose:** the single anti-drift source of truth for the Carney demo. The
LLM, the architecture, and the feature scope are frozen here. If a Codex
consult, an advisor, an external doc, or Claude's own reasoning ever proposes
something that contradicts §1, this document wins. Changes to §1 require an
explicit operator-signed reconciliation commit — not a silent edit.

**Pinning:** §1 (constraints) is LOCKED at this commit; its commit SHA is the
pin. §3.1 feature statuses are **VERIFIED** by Phase 1 (I-rdy-002, #498) and
pinned here by Phase 0B (I-rdy-003, #499). §3.2 cross-cutting capabilities
were not part of the Phase 1 pass and remain PROVISIONAL pending their own
verification.

---

## §1. Locked constraints — frozen, do not reopen

### §1.1 LLM
- **Generator: DeepSeek V4 Pro** — 1.6-trillion-parameter MoE (49B active/token), ships FP4 (experts) + FP8 (rest). Operator-locked, stated 6+ times.
- **Evaluator: Gemma 4 31B.**
- **Two-family invariant:** generator (DeepSeek lineage) and evaluator (Google/Gemma lineage) are different training lineages. `openrouter_client.check_family_segregation` enforces this at construction.
- **Concurrency: 1 concurrent session.** Traffic is operator-limited. This does not shrink the GPU requirement (the 1.6T model needs ~880 GB VRAM regardless of concurrency); it only bounds KV-cache headroom.
- Supersedes the prior `docs/hardware_decision.md` "Path C / V4 Flash" — that was overridden by operator directive to V4 Pro.

### §1.2 Hardware / sovereignty
- **Canadian sovereign GPU only.** V4 Pro requires 8× H200 or 12-16× H100 (Hopper-class — V100/A100 lack FP4/FP8 and cannot run it).
- **Not** OVH Canada — its Canadian datacentre (Beauharnois, Québec) has only old V100/V100S GPUs, which lack FP4/FP8 and cannot run V4 Pro; OVH's Hopper-class H100/H200/A100 are France-only (verified via the OVH API). **Not** France. **Not** any US company.
- Canadian sovereign GPU candidates: Vexxhost (Montréal), ISAIC (Edmonton) — both pending physical-location confirmation.
- Sovereignty threat model is NARROW: no runtime US LLM vendor calls + no report data in US jurisdiction. Model lineage, build toolchain, and DNS registrar are out of scope of the threat model.
- The orchestrator (CPU box) stays on OVH BHS5 — that is Canadian and acceptable; only the LLM inference must move to a Canadian GPU.

### §1.3 Architecture
- **The deployed v6 stack** is the architecture: `redis + api (FastAPI v6.2.0) + worker (Dramatiq) + webui (Next.js 16)` via `docker-compose.v6.yml`. **No rewrites.**
- Pipeline B (legacy LangGraph) and Pipeline C (frozen CLI) are **out of demo scope.**
- Frontend stack: Next.js 16 + React 19 + shadcn/ui + Tailwind 4.

### §1.4 Naming
- The legacy name **"BPEI" is banned** in all demo-facing code, docs, and config. Renamed to `ambiguity_detector`. Rename tracked by #434 (I-naming-001) + readiness Phase 2.

### §1.5 Demo
- Single venue, PM Mark Carney's office, flexible date in June 2026.
- Scope = the Carney plan (`docs/carney_delivery_plan_v6_2.md`). **No features beyond it.**

---

## §2. Canonical templates — the 8, frozen

The single source of truth is `config/scope_templates/`. Frontend cards,
frontend TypeScript types, and the v6 backend registry MUST all read from it
(reconciliation tracked by I-rdy-005, #501).

1. `clinical` — clinical drug audit
2. `policy` — public policy
3. `tech` — technology assessment
4. `due_diligence` — due diligence
5. `ai_sovereignty` — AI sovereignty
6. `canada_us` — Canada–US
7. `workforce` — workforce
8. `custom` — operator-defined catch-all

No template is added or removed without an operator-acknowledged change to §2 (per the §5 change protocol).

---

## §3. Feature scope — the 15 + cross-cutting capabilities

**§3.1 status values are VERIFIED 2026-05-15** via Phase 1 (I-rdy-002, #498) —
grounded against the live deployed system + static code inspection. Full
evidence: `.codex/I-rdy-002/verification_findings.md` (Codex-APPROVED iter 4).
§3.2 cross-cutting capabilities are not covered by this pass — see §3.2.

**Binding rule:** *harness-page evidence and golden-fixture tests do NOT count
as feature-complete.* A feature is "complete" only when a live run exercises
it end-to-end in the deployed product.

### §3.1 The 15 user-visible features

| F# | Feature | Verified status (I-rdy-002, 2026-05-15) |
|---|---|---|
| F1 | Scope discovery + template browse | substrate exists; template registry mismatch |
| F2 | Ambiguity-detection disambiguation modal | substrate exists; not wired into main ask flow |
| F3 | Document upload + grounding | UI+API exist; async runs ignore uploaded docs |
| F4 | Live audit run (SSE reasoning visibility) | SSE substrate works; raw event cards, not frontier-grade |
| F5 | Report inspection / click-through audit | components exist; not on the live `/runs` report |
| F6 | Live citation hover overlay | components exist; harness/fixture-bound |
| F7 | Frame coverage panel | components exist; harness/fixture-bound |
| F8 | Contradiction navigation | components exist; harness/fixture-bound |
| F9 | Two-family disagreement signal | components exist; harness/fixture-bound |
| F10 | Inline visual generation (Vega-Lite) | spec builder/API/tests exist; fixture-bound |
| F11 | Report-scoped auditable follow-up | backend exists; disabled on the product run page |
| F12 | Side-by-side compare two reports | backend exists; no product route |
| F13 | Pin replay / "what changed" | page exists; demo-data-bound |
| F14 | Auditable research memory | page+API exist; in-memory demo store, not durable |
| F15 | Audit bundle export | tar.gz backend works; inspector JSON path fixture-only; clean-machine verification not proven |

### §3.2 Cross-cutting capabilities (additional to F1-F15)

- Knowledge snowballing (`evidence_deepener.py`)
- Anti-sycophancy CI (paired-prompt, ELEPHANT methodology)
- Sovereignty enforcement (data classification + provider routing)
- Cross-jurisdiction synthesizer
- Strict-verify per-sentence provenance
- Two-family segregation invariant
- Evidence Contract Gate
- GPG-signed audit bundles

These §3.2 capabilities were NOT individually verified by the Phase 1
(I-rdy-002) pass — that pass covered the §3.1 features. Their statuses remain
PROVISIONAL pending a dedicated verification pass.

---

## §4. Out of scope (frozen)

- No new features beyond §3 / the Carney plan.
- No architecture rewrites (§1.3).
- Pipelines B and C are not demo deliverables.
- Multi-tenant / full SOC-2 / billing are not demo deliverables (single-venue demo).

---

## §5. Change protocol

- §1 (constraints) changes ONLY via an operator-signed reconciliation commit that explicitly states the prior value, the new value, and the reason.
- §2 / §3 / §4 changes require an operator-acknowledged commit.
- A Codex consult, advisor, or Claude reasoning step may *recommend* a change but may NOT enact one — §1 is operator-owned.
- This is the structural defense against the swing pattern (LLM drifting V4 Pro→Flash→Llama; provider drifting Canada→France) seen 2026-05-15.
