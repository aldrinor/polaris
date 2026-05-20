# POLARIS GPU topology — confirm + early OVH capacity probe (I-cd-008, GH#640)

**Topology (operator-locked, designed):**
- **Box 1 — Generator:** 8×H200 (OVH SKU `h200-1920`) for DeepSeek V4 Pro
  1.6T at FP4 (~800 GB FP4 weights fit 1128 GB HBM3e on 8×H200).
- **Box 2 — Evaluator:** 4×H100 (OVH SKU `h100-1520`) for
  `google/gemma-4-31B-it` + community AWQ INT4 quant (locked in
  I-cd-005-followup, merged `37310ddc`). INT4 ≈ 16 GB → 4×80GB = 320 GB =
  massive headroom (P3 rightsizing note in §C).

**Capacity verification (this PR's deliverable):** **NOT OBTAINABLE NOW
from the current OVH project.** Operator-action required — see §B.

## §A — Probe + result (this-session live OVH API)

Probe: `scripts/ovh_gpu_topology_probe.py` (committed for reproducibility
per the operator's `feedback_verify_primary_sources_before_relying_2026_05_15`
directive — "Commit verification script"). Output JSON:
`outputs/audits/I-cd-008/probe_result.json`.

Cross-checked four+ ways per the same memory:

1. **Catalog at CA subsidiary** (`GET /order/catalog/public/cloud?ovhSubsidiary=CA`):
   75 GPU plan rows visible (the catalog DOES list `h200-1920` and
   `h100-1520` at Canada-subsidiary billing).
2. **Catalog at FR subsidiary**: rejected by the `ovh-ca` endpoint
   (`BadParametersError: invalid ovhSubsidiary`) — the `ovh-ca` endpoint
   only accepts `ovhSubsidiary=CA`. A standalone FR-subsidiary API key
   would be needed for an independent FR-billing cross-check; out of
   scope here.
3. **Project flavor list (UNFILTERED, per Codex iter-2 P2 fix)** —
   `GET /cloud/project/{projectId}/flavor`, filter in code by name +
   region:
   - `h100-1520` @ GRA9: `available=False`, `quota=0`.
   - `h100-1520` @ GRA11: `available=False`, `quota=0`.
   - `h200-1920`: **ABSENT FROM THE PROJECT FLAVOR LIST IN ANY REGION**.
4. **Per-region quota** (`GET /cloud/project/{projectId}/region/{region}/quota`):
   probed across all 15 candidate non-US regions in the project (BHS,
   BHS5, DE, DE1, GRA, GRA9, RBX, RBX-A, RBX-ARCHIVE, SBG, SBG5, UK, UK1,
   WAW, WAW1). Per-region quota state recorded in the JSON artifact.
5. **`/cloud/order/rule/availability`** for each target SKU: returned
   `null` (no order-rule entry exposed for the unprivileged read).

**Project regions enumerated** (from `GET /cloud/project/{projectId}/region`):
`BHS, BHS5, CA-EAST-TOR, DE, DE1, EU-SOUTH-MIL, EU-WEST-PAR, GRA, GRA9,
RBX, RBX-A, RBX-ARCHIVE, SBG, SBG5, UK, UK1, WAW, WAW1`. No US regions
appear in the project — sovereignty rule
(`feedback_sovereignty_threat_model_2026_05_13`) is structurally enforced
at the project level. The 2026-05-18 EU GPU relaxation
(`project_gpu_procurement_2026_05_15`) is consistent with the project's
existing EU region access.

## §B — Operator-action required (the literal acceptance deliverable)

**The locked topology is NOT deployable today.** Open an OVH support
ticket against the OVH Canada account (`ovh-ca`, project
`446fccde73604cfbb0758c6012dad6d1`) requesting:

1. **Add `h200-1920` to the project's flavor allowlist for at least one
   non-US region** (preferred: GRA9 or GRA11 France). The SKU is in the
   public catalog but not surfaced to this project's flavor list at all.
2. **Increase per-region quota for `h100-1520` in GRA9 and GRA11** from
   the current `0` to `>= 1` (one 4×H100 instance suffices for the
   evaluator role).

Per OVH support documentation (referenced in Codex's iter-1 P2): quota-
increase requests are "manual and processing times vary." Do not invent
an SLA — file the ticket as soon as practical so the fulfillment window
is known before I-cd-037 (#642, final hold/confirm) and I-cd-038 (#643,
provisioning order).

This probe is intentionally a NON-HOLDING check (I-cd-037 is the final
hold). The Carney breakdown sequenced this issue at Seq 8 specifically
so this gap surfaces NOW, weeks before the demo, with time for the
operator to negotiate quota via OVH support.

## §C — Side findings (P3, non-blocking)

- **Box 2 is overprovisioned for the locked evaluator model.** Gemma 4
  31B-it at INT4 ≈ 16 GB; 4×80GB H100 = 320 GB. One H100 (`h100-380`, 1×H100
  80GB) or one L40S (`l40s-90`, 1×L40S 48GB) would fit the evaluator role
  with abundant headroom. **Locked spec STAYS 4×H100 per the breakdown** —
  this issue does not rightsize. Side-note for the operator's I-cd-037
  rightsizing decision if Carney delivery considerations make smaller
  evaluator hardware preferable.
- **Memory contradiction reconciled.** Prior
  `feedback_verify_primary_sources_before_relying_2026_05_15` claimed
  `h200-1920` doesn't exist as a public SKU; the 2026-05-19 catalog
  probe (signal 1) found it at the CA-subsidiary billing level; this
  probe (signal 3) finds it absent from THIS PROJECT'S flavor list.
  Reconciliation: SKU exists in the catalog; per-project regional
  flavor exposure is a separate gate, controlled by quota allowlist.
  Three distinct signals; the project-level allowlist is the binding
  constraint for I-cd-038 ordering.

## §D — Provisioning gotchas for I-cd-037 + I-cd-038 (from Codex iter-1+2 P2)

- **Billing mode locks at create**: monthly billing CANNOT be switched
  back to hourly after instance creation. I-cd-038 must choose mode
  BEFORE creating instances. (No cost figures recorded here per
  `feedback_no_cost_mentions`; this is an operational flag only.)
- **Per-region quota is the authoritative gate**, not catalog presence.
  I-cd-037 re-runs `scripts/ovh_gpu_topology_probe.py` immediately
  before I-cd-038 to confirm quota >= 1 for both SKUs in the chosen
  region.
- **Public web pages are NOT SKU-region authoritative** — only the
  project-level API is. Don't infer availability from public datacenter
  pages or pricing pages.

## §E — What's NOT in this issue

- Final capacity hold/confirm — **I-cd-037 (#642)**, right before order.
- GPU provisioning order — **I-cd-038 (#643)**, operator-authorized
  [GL gate].
- Engine wiring (vLLM with the new model id) — **I-cd-009 (#624)**.
- FP4 readiness hardware spike — **I-cd-011 (#641, ~$400 GPU)**.

## §F — Verdict

| Item | State |
|---|---|
| Topology designed (8×H200 generator + 4×H100 evaluator) | ✅ LOCKED |
| Sovereignty (non-US compute) | ✅ STRUCTURAL (no US regions in the project) |
| OVH catalog presence (h200-1920, h100-1520) | ✅ confirmed at CA subsidiary |
| OVH project-region availability for the target SKUs | ❌ **NOT AVAILABLE NOW** (operator-action required) |
| `h100-1520` in GRA9 / GRA11 | ❌ `available=False`, `quota=0` |
| `h200-1920` in any project region | ❌ absent from project flavor list |
| I-cd-038 unblocked | ❌ blocked on quota-increase / SKU-allowlist support ticket |

The non-confirmation IS the deliverable — surfaced NOW with the
operator-action path named, exactly as the Seq-8 early-probe was
designed to do.
