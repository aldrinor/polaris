HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# ⚠ HARD CONSTRAINTS — NOT CODEX-NEGOTIABLE ⚠

Operator-locked decisions stated verbatim or implied by the merged breakdown
+ this-session re-locks. Codex's role on this issue is **operational
verification only** — confirming SKU availability + datacenter regions for
the locked topology. Codex must NOT propose alternative topologies, GPU
families, or providers.

- **Provider: OVH** (operator-locked; account `ovh-ca`, project
  `446fccde73604cfbb0758c6012dad6d1`, see `state/ovh_infra.md`).
- **Box 1 — Generator**: **8×H200** for DeepSeek V4 Pro 1.6T at FP4
  (operator-locked; ~800 GB FP4 weights fit 1128 GB HBM on 8×H200).
- **Box 2 — Evaluator**: **4×H100** (operator-locked spec per the merged
  Carney breakdown). I-cd-005-followup (merged `37310ddc`) re-locked the
  evaluator MODEL to `google/gemma-4-31B-it` (Apache 2.0, ~16 GB INT4
  weights), which is dramatically smaller than the original Llama 4
  Maverick lock; the 4×H100 spec is now overprovisioned for the evaluator
  role. The 4×H100 spec STAYS per the locked breakdown; any rightsizing is
  a separate operator decision, not this issue's call.
- **Region: non-US**. Originally Canada-only; relaxed 2026-05-18 to EU as
  well (`project_gpu_procurement_2026_05_15`). OVH options: BHS5 Québec
  (Canada) or GRA9/GRA11 / SBG / RBX (France/Europe).
- **Sovereignty: open-weight self-hosted on non-US-vendor compute**
  (`feedback_sovereignty_threat_model_2026_05_13`). OVH is French; both
  Canada and EU OVH regions satisfy.
- **No cost discussion** in the deliverable doc
  (`feedback_no_cost_mentions`). The state/polaris_gpu_cost_2026_05_19.md
  cost record from earlier this session stays informational only.

# Codex brief review — I-cd-008 / GH#640: GPU topology confirm + early OVH capacity probe

Acceptance per breakdown: "topology confirmed (8×H200 FP4 V4 Pro + 4×H100
evaluator); OVH non-US capacity verified NOW."

## §0 — Iter-2 revisions (responding to iter-1 REQUEST_CHANGES + live OVH probe findings)

Iter 1: 1 P1 + 5 P2. **All addressed; the deliverable framing pivots from
"GREEN: verified available" to "RED with named gap: quota=0 + h200-1920
absent, operator-action required."**

Codex iter 1 (293k tokens, included a live `GET /cloud/project/.../flavor`
query) found:
- `h100-1520` in GRA9 and GRA11: `available=false`, **quota=0**.
- `h200-1920`: **ABSENT** from the project flavor list entirely.

That is the early-probe's purpose: surface this gap NOW, weeks before
I-cd-037 (#642, final hold) and I-cd-038 (#643, provisioning order). The
gap requires operator action (OVH support ticket for quota increase) which
per OVH support docs takes variable time — exactly why the breakdown
sequenced this issue at Seq 8, not later.

Folded into the brief:
- **P1 (no current capacity)** — `§D` now explicitly records the gap + the
  required operator-action (OVH support ticket). The topology DOC will NOT
  say "verified GREEN"; it records the precise per-region quota state Codex
  measured + the next-step escalation.
- **P2 (use unfiltered `/cloud/project/{serviceName}/flavor`)** — `§B`
  updated. Region-filtered probes hit 404 on aggregate codes; unfiltered
  flavor list + name+region client-side filter is the reliable path.
- **P2 (public web pages not authoritative)** — confirmed; my §A had
  already established API > web > training-knowledge.
- **P2 (add quota checks via `/cloud/project/{serviceName}/region/{regionName}/quota`
  and `/quota/allowed`)** — added to `§B`. Quota probe is essential for
  I-cd-037 + the support-ticket follow-up.
- **P2 (billing mode locks at create; monthly cannot revert to hourly)** —
  recorded as a `§D` gotcha for I-cd-038, NOT a §C cost discussion.
- **P2 (Box-2 overprovisioning → P3 side-note only, do not rightsize)** —
  preserved as P3 side-note in §D, no rightsizing in this issue.

## §0 — Why this issue exists in Seq 8 (the early-probe rationale)

The Carney breakdown's iter-1 P1 (per Codex's breakdown review history)
flagged that OVH capacity should be probed EARLY (before I-cd-038 (#643)
provisioning order) so we discover sold-out / capacity-constrained SKUs in
the demo regions in time to react. This issue is that probe. It does NOT
hold inventory (I-cd-037 (#642) is the final hold/confirm immediately
before I-cd-038's order); it just confirms the topology is OBTAINABLE in a
non-US OVH region as of NOW.

## §A — Prior-art verification anchors (Codex web-cross-check if helpful)

Existing repo state (NOT to be re-derived from training knowledge — these
are facts the operator wants me to ground on):

- `state/ovh_infra.md`: account is OVH Canada subsidiary; current
  orchestrator `polaris-orchestrator` is a `b3-16` (non-GPU) in BHS5 Québec.
- `outputs/audit_2026_05_18/ovh_gpu_pricing.py`: this-session probe via
  `/order/catalog/public/cloud?ovhSubsidiary=CA` confirmed (currency CAD)
  that GPU planCodes including `h200-1920` (8×H200) and `h100-1520`
  (4×H100) EXIST in the OVH catalog at CA-subsidiary billing.
- `state/polaris_gpu_cost_2026_05_19.md`: records the catalog-confirmed
  SKUs + this-session per-hour pricing (informational; no cost in the
  deliverable doc).
- `feedback_verify_primary_sources_before_relying_2026_05_15` (memory):
  "OVH has ZERO GPUs in Canadian datacenters (all in France GRA9/GRA11),
  and h200-1920 doesn't exist as Public Cloud SKU at all." That memory is
  partly contradicted by the 2026-05-19 pricing probe (which DID find
  `h200-1920` in the catalog at CA-subsidiary billing). The contradiction
  is exactly the trap: **catalog presence at a billing subsidiary ≠ regional
  hardware availability**. I-cd-008's probe resolves this by querying
  PER-REGION availability, not just catalog presence.

## §B — The probe (what I-cd-008 actually does)

`scripts/ovh_gpu_topology_probe.py` — read-only OVH API queries (revised per
iter-1 P2):

1. **Catalog SKU set**: `GET /order/catalog/public/cloud?ovhSubsidiary=CA`
   (and `=FR` for cross-check) — enumerates GPU planCodes (filter on
   `h100`/`h200`/`l40`/`l4-`/`a100`/`a10-`/`gpu` substrings). Records each
   plan's regions list.
2. **Project flavor probe (UNFILTERED, then filter in code per iter-1
   P2)**: `GET /cloud/project/{projectId}/flavor` returning ALL flavors
   project-wide; client-side filters by name (`h200-1920`, `h100-1520`)
   AND by region (any of `BHS5`, `GRA9`, `GRA11`, `SBG*`, `RBX*`). Records
   `available`, `quota`, and any per-flavor metadata. The project ID
   `446fccde73604cfbb0758c6012dad6d1` is fixed from `state/ovh_infra.md`.
3. **Project quota probe (NEW per iter-1 P2)**: for each candidate region,
   `GET /cloud/project/{projectId}/region/{regionName}/quota` and
   `GET /cloud/project/{projectId}/quota/allowed` — records the project's
   current quota state per region. Identifies which quotas the operator's
   OVH support ticket needs to lift to `>= 1` for h200-1920 and h100-1520.
4. **Region location mapping**: OVH region codes (BHS Canada, GRA France,
   SBG France, RBX France) — confirms each region matches a non-US
   datacenter per the sovereignty rule (`feedback_sovereignty_threat_model_
   2026_05_13`).
5. **Cross-check 4 ways** per `feedback_verify_primary_sources_before_
   relying_2026_05_15`: (a) catalog at CA subsidiary, (b) catalog at FR
   subsidiary, (c) project flavor (unfiltered) at each candidate region,
   (d) project quota state per region — the four independent signals.

The script reads `OVH_*` credentials from `.env` (existing pattern from
`outputs/audit_2026_05_18/ovh_gpu_pricing.py`). It NEVER ECHOES SECRET
VALUES. It outputs: SKU name, region(s), availability flag, datacenter
geographic location. Writes JSON to `outputs/audits/I-cd-008/probe_result.json`
for traceability; the doc records the human-readable summary.

## §C — What this PR ships

- `scripts/ovh_gpu_topology_probe.py` (NEW) — the verification script.
  Committed for reproducibility (operator's "Commit verification script."
  directive). ~100 LOC.
- `docs/models/gpu_topology.md` (NEW) — confirmed topology + verified
  per-region SKU availability + datacenter location + sovereignty
  clearance. NO cost discussion. ~80 LOC.
- `outputs/audits/I-cd-008/probe_result.json` (NEW) — the raw JSON
  output from running the probe at `<utc-timestamp>`. Traceability artifact.
- `state/polaris_restart/iteration_trajectory.md` — §8.3.5 log.

**Out of scope (own later issue):**
- Final capacity hold/confirm — I-cd-037 (#642), immediately before
  provisioning order. Runs the same probe + records the final pre-order
  inventory state.
- Actual GPU provisioning order — I-cd-038 (#643), operator-authorized
  [GL gate].
- Engine wiring + model deployment — I-cd-009 (#624).
- FP4 hardware spike — I-cd-011 (#641).

## §D — Operator-action required + side-findings + gotchas

**Operator-action required (the headline finding, surfaced honestly in the
deliverable doc):** Per Codex iter-1 live probe (and to be re-confirmed by
this PR's own probe run), the OVH project currently has NO operating
capacity for the locked topology:

- `h100-1520` (4×H100) in GRA9 + GRA11: `available=false`, **quota=0**.
- `h200-1920` (8×H200): **absent from the project flavor list entirely**.

**The operator needs to open an OVH support ticket** requesting quota
increase for `h200-1920` in GRA9/GRA11 (or BHS5 if available) and
`h100-1520` in GRA9/GRA11. Per the OVH support docs (Codex iter-1 P2),
quota increases are "manual/support-mediated and can take variable time"
— hence the early-probe sequencing at Seq 8 vs the I-cd-037 hold and
I-cd-038 order much later in the breakdown.

This is the LITERAL ACCEPTANCE DELIVERABLE for I-cd-008: the
non-confirmation of capacity, surfaced NOW with the operator-action
path named.

**Side-findings (not blockers, in the doc as P3 notes):**
- **Box 2 = 4×H100 is overprovisioned for Gemma 4 31B-it**. INT4 ≈ 16 GB
  on 4×80GB H100 = 320GB. P3 side-note for the operator's I-cd-037
  rightsizing call. The locked spec STAYS 4×H100 per the breakdown — this
  issue does NOT rightsize.
- **Memory contradiction reconciled**: prior `feedback_verify_primary_
  sources_before_relying_2026_05_15` claimed `h200-1920` doesn't exist;
  the 2026-05-19 catalog probe found it at CA-subsidiary billing; the
  iter-1 project-flavor probe shows it's absent from THIS PROJECT'S
  region-availability list. Catalog presence ≠ project-region
  availability ≠ project-quota. The doc records all three signals.

**Provisioning gotchas (per iter-1 P2, for I-cd-038's order step):**
- Monthly billing CANNOT be switched back to hourly after instance
  creation. I-cd-038 must choose billing mode BEFORE creating instances.
  (No cost figures in this issue's deliverable; this is a flag, not a
  cost discussion.)
- Quota-increase requests are support-ticket-mediated with variable
  fulfillment windows — operator should open them ASAP.

## §E — Questions for Codex (post-iter-1 residuals)

1. Re-confirm: is unfiltered `GET /cloud/project/{serviceName}/flavor` +
   client-side name+region filtering the right authoritative path, OR is
   there a better project-region-specific endpoint that doesn't 404 on
   aggregate region codes?
2. Re-confirm: is `GET /cloud/project/{serviceName}/region/{regionName}/quota`
   the right per-region quota endpoint, and does `GET /cloud/project/
   {serviceName}/quota/allowed` give a useful complement (e.g., what
   quota increases the project IS allowed to request without manual
   approval)?
3. Is there an OVH API call OR a documented support-ticket SLA the
   operator should target when filing the quota-increase request, so the
   doc can include "expect N business days" honest framing?
4. Any other OVH API signal worth probing (e.g., expressOrder cart
   creation as a dry-run-availability-check, or `/me/order` to see if any
   prior quota-increase requests are pending)?

## §F — Output schema — return EXACTLY this

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
