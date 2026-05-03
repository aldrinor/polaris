# Hardware Decision — DeepSeek V4 Pro Sovereign Path

**Status:** LOCKED 2026-05-02 (user-signed canonical reconciliation per Plan v13 §F)
**Path selected:** **Path C — DeepSeek V4 Flash on 8× H200 OVH BHS Canada**
**Plan reference:** `docs/carney_delivery_plan_v6_2.md` (canonical pin: `0d3d75f56daa7b2ea41c1f3c11c3eaeb65437693bd4309065ebff0c8f1420a24`)
**Blocker reference:** `docs/blockers.md §3` (canonical pin: `79217137de963bbd5efa7f9d50a440e8047461c6d63c4441afc9e074de04404d`)
**Acceptance matrix:** `docs/task_acceptance_matrix.yaml task_0_6` (canonical pin: `8671ce715f07d47a4831dbd0075a82372b78aeba179339e6664d7829d1f627be`)
**Owning task:** Phase 0 Task 0.6 (substrate_prep `0_6_hardware_decision_doc`)
**Canonical pin file SHA256 (composite):** `5a5afbbaf12c01a4e04d2a710cdbdefebf4faf3ff709c113b3e172149d8878b2` (sha256 of `docs/canonical_pin.txt` at commit time)

---

## 1. Decision summary

**Single sentence:** POLARIS sovereign cognition runs DeepSeek V4 Flash on **8× NVIDIA H200 GPUs** in **OVH Canada BHS region** (Path C of the three Phase 0.6 path options).

This decision was canonically reconciled in `docs/blockers.md §3` on 2026-05-02 via user-signed reconciliation per Plan v13 §F best-of-best lock semantics. **No silent fallback** is permitted: if Phase 0.7 SGLang/vLLM bakeoff data later contradicts the lock (e.g. V4 Flash quality fails on 2+ template families), the orchestrator halts per Plan v13 §H halt-condition #5 and the user re-signs canonical to switch paths — not a runtime auto-degradation.

---

## 2. Three paths considered

| Path | Hardware | Model variant | Capacity (concurrent sessions) | Selected? |
|---|---|---|---|---|
| **A** | 16× H200 FP8 | V4 Pro full | 5+ | NOT selected |
| **B** | 8× H200 reduced-context | V4 Pro reduced | 2 | NOT selected |
| **C** | 8× H200 (procurement engaged at Phase 4 entry, NOT now) | **V4 Flash only** | 5+ (target) | **SELECTED** |

### 2.1 Path A (16× H200 FP8 V4 Pro full) — NOT SELECTED

- **Pros:** Highest model fidelity. Full V4 Pro capability surface.
- **Cons:** 2× hardware cost vs Path C. Procurement risk (16× H200 capacity in OVH BHS may not be available within Phase 4 timeline). No measured advantage over V4 Flash on the 8 Carney templates per substrate-audit baseline.
- **Selection blocked by:** procurement-availability risk + cost asymmetry without measured quality gain.

### 2.2 Path B (8× H200 reduced V4 Pro) — NOT SELECTED

- **Pros:** Same hardware footprint as Path C. Marginally higher per-call quality on long-context tasks vs V4 Flash.
- **Cons:** Capacity drops to 2 concurrent sessions due to reduced-context KV-cache pressure. **Concurrency below the deployment requirement** (5+ concurrent sessions on Carney handover bar).
- **Selection blocked by:** capacity insufficient. Carney scope explicitly requires multi-evaluator concurrent access; 2 concurrent is incompatible.

### 2.3 Path C (8× H200 V4 Flash only) — SELECTED

- **Pros:** 5+ concurrent sessions (target capacity, to be verified at Phase 4.4 benchmark). Procurement footprint smaller than Path A (lower availability risk; OVH H200 page status `Coming soon` per `docs/blockers.md §9` — actual reservation engagement scheduled for Phase 4 entry, NOT this commit). Lowest cost. Quality differential vs V4 Pro acceptable for Carney scope per substrate audit `docs/substrate_audit_2026-05-01.md`.
- **Cons:** Marginal quality reduction on long-form synthesis tasks vs V4 Pro. Capability gap acknowledged below.
- **Selection rationale:** capacity > marginal quality for sovereign deployment at Carney scope. V4 Flash quality delta is acceptable for the use case.

---

## 3. Capability gap acknowledged (V4 Flash vs V4 Pro)

Per substrate audit `docs/substrate_audit_2026-05-01.md` and Plan v13 §F honesty framing:

- **Long-form synthesis (>200-sentence reports):** V4 Pro produces marginally better discourse coherence on long syntheses. V4 Flash is acceptable but the gap is non-zero and is documented here, not silently tolerated.
- **Multi-jurisdictional comparison (F12, F14):** V4 Pro's larger context window can hold full bibliographic state for cross-jurisdiction comparison; V4 Flash relies more on retrieval pruning. Mitigation: F12/F14 retrieval pipeline already prunes by relevance; quality impact monitored at Phase 3.5 benchmark.
- **Anti-sycophancy edge cases (paired-prompt fixtures):** V4 Pro may resist sycophantic drift on adversarial paired prompts more reliably than V4 Flash. Mitigation: sycophancy CI (task 1.7) runs on every substrate change; if delta exceeds the ELEPHANT methodology bar (<10% rate, <5% paired-stance delta), Path A/B re-evaluation triggers per Plan v13 §H halt-condition #5.

If Phase 0.7 bakeoff data confirms these gaps materially exceed the Carney scope tolerance, this lock is invalidated and user re-signs canonical to switch paths. Not a silent fallback.

---

## 4. Phase 0 vs Phase 4 separation

**Critical:** This decision document represents **the lock**, not the procurement.

- **Phase 0 (May 1–12, current):** decision document committed. Path C locked. **No physical procurement** during Phase 0–3.
- **Phases 0–3 (May 1 – Aug 9):** POLARIS validates via API service (OpenRouter / DeepSeek API). Build + benchmark vs ChatGPT 5.5 Pro DR + Gemini 3.1 Pro DR runs against API-provided LLM endpoints. **No bare-metal cluster commitment during build.** Per `docs/blockers.md §3` API-first sequencing.
- **Phase 4 entry (~2026-08-10):** physical procurement engages. User signs `.private/ovh_quote_*.pdf` (or backup procurement doc per Task 0.9 fallback paths 1–5). 8× H200 OVH BHS reservation goes live. `tests/hardware/bakeoff_results.json` populated against the live cluster.
- **Phase 4 (Aug 10–23):** sovereign migration executes per Plan v13 phase plan.

This separation is deliberate per user directive 2026-05-02 (`docs/blockers.md §3` reconciliation). It de-risks early procurement: the Carney handover quality bar is validated on API substrate before hardware commitment is made.

---

## 5. Required artifacts (Phase 0.6 GREEN criteria mapping)

Per `docs/task_acceptance_matrix.yaml task_0_6.required_artifacts`:

| Artifact | Phase | Status |
|---|---|---|
| `docs/hardware_decision.md` | 0 | **THIS DOCUMENT** — committed at orchestrator iteration |
| `.private/hardware_quote_*.pdf` (Path A or B only) | n/a | Not required — Path C selected |
| `tests/hardware/bakeoff_results.json` | 4 | **Phase-4-deferred (explicit).** Bakeoff requires live OVH BHS H200 cluster; cannot run in Phase 0 under API-first sequencing per `docs/blockers.md §3`. Will populate at Phase 4.4 benchmark step. |
| `.private/hardware_quote_*.pdf` | 4 | **Phase-4-deferred (explicit).** Procurement quote PDF only generated when user engages OVH Sales for the 8× H200 BHS reservation at Phase 4 entry per `docs/blockers.md §3` API-first sequencing. Not produced in Phase 0; this is by design, NOT a silent fallback. |

The matrix's `green_criteria` items are addressed as follows:

- ✅ "docs/hardware_decision.md committed with Path A/B/C selected" — Path C selected, this document.
- ✅ "If Path C (V4 Flash only): rationale documented + capability gap acknowledged" — §2.3 + §3 above.
- ✅ "Decision artifact signed by user (commit hash)" — the user-signature lock is recorded in `docs/blockers.md §3` reconciliation (commit `9bf7907`, 2026-05-02). This document is the corresponding decision-doc artifact; once committed, its commit SHA + the parent reconciliation commit together constitute the signed decision trail.
- ⏳ "If Path A: hardware quote + bakeoff baseline" — N/A (Path C).
- ⏳ "If Path B: bakeoff data confirms 512K context viable" — N/A (Path C).

The tests/hardware/bakeoff_results.json artifact is **Phase-4-deferred** under the API-first separation. This is documented explicitly here and in the manifest at `outputs/audits/manifests/0_6_hardware_decision_doc.json` to preserve Plan v13 §F honesty framing.

---

## 6. Resolution path if locked decision proves wrong

Per Plan v13 §F (no SILENT fallback) + §H halt-condition #5:

If, during Phases 1–3, evidence accumulates that V4 Flash quality is materially insufficient for the Carney scope (e.g. >2 template families fail Phase 3.5 benchmark vs ChatGPT/Gemini DR with delta attributable to model choice rather than retrieval/synthesis), the orchestrator halts. Resolution requires user-signed canonical reconciliation switching to Path A or B. The orchestrator will NOT auto-degrade or auto-substitute.

A halt resolution at `outputs/audits/halt_resolutions/0_6_path_change_<ts>.md` would record the trigger evidence, the proposed path switch, and the user's signed authorization.

---

## 7. References (canonical, hash-pinned)

| Document | Pin SHA (prefix) | Role |
|---|---|---|
| `docs/carney_delivery_plan_v6_2.md` | `0d3d75f5` | Plan v13 (mission) |
| `docs/blockers.md` | `79217137` | Decision lock (§3 hardware path) |
| `docs/task_acceptance_matrix.yaml` | `8671ce71` | Acceptance criteria (task_0_6) |
| `architecture.md` | `8e8e7e2f` | Current-state baseline |
| `docs/substrate_audit_2026-05-01.md` | `0ba71ca0` | Substrate inventory |
| `CLAUDE.md` | `652da811` | Operational directives |

All pins listed above are validated against `docs/canonical_pin.txt` at commit time via the orchestrator's `_verify_canonical_pin()` step. If any pin drifts between this document's commit and a future read, the next session's startup §3 Step 0 will HALT and require user-signed reconciliation.

---

**Decision attestation:** This document represents the canonical hardware decision for the POLARIS Carney delivery. Path C is locked. Procurement deferred to Phase 4 entry. No silent fallbacks.
