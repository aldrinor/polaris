# I-cd-008 — Claude architect audit

**Issue:** GH#640 — GPU topology confirm + early OVH capacity probe.
**Deliverable:** `scripts/ovh_gpu_topology_probe.py` (committed
verification script per the operator's `feedback_verify_primary_sources_
before_relying_2026_05_15` directive) + `docs/models/gpu_topology.md`
recording the verified topology + the named capacity gap + the
operator-action escalation + `outputs/audits/I-cd-008/probe_result.json`
as the raw evidence artifact.

## What this PR ships

- `scripts/ovh_gpu_topology_probe.py` (NEW, 221 LOC) — read-only OVH API
  probe across 5 independent signals. Reads `OVH_*` from `.env`, never
  echoes secret values, writes JSON to `outputs/audits/I-cd-008/`.
- `docs/models/gpu_topology.md` (NEW, 132 LOC) — topology design + the
  honest "NOT OBTAINABLE NOW" verdict + operator-action escalation.
- `outputs/audits/I-cd-008/probe_result.json` (1493 LOC; large because
  it's the raw OVH API output across 18 regions × 5 signals — the
  operator's traceability artifact, not Claude-written).

## The finding (the deliverable IS the not-confirmation)

This-session live probe (UTC 2026-05-20T02:52:43Z, endpoint `ovh-ca`,
project `446fccde73604cfbb0758c6012dad6d1`):

| Signal | Result |
|---|---|
| Catalog @ CA subsidiary | 75 GPU rows including h200-1920 and h100-1520 |
| Catalog @ FR subsidiary | Cross-check rejected (ovh-ca endpoint scope) — out of scope |
| Project flavor list (unfiltered, region-filtered in code) | `h100-1520` @ GRA9 + GRA11: `available=False`, `quota=0`. `h200-1920`: ABSENT |
| Per-region quota (15 candidate non-US regions) | recorded in JSON |
| `/cloud/order/rule/availability` per SKU | `null` for both |

**Verdict:** `target_skus_obtainable_now = False`. Two named blockers in
the JSON `verdict` field. Operator-action: open OVH support ticket
against the `ovh-ca` account to (a) add `h200-1920` to the project flavor
allowlist (GRA9 or GRA11), and (b) increase `h100-1520` per-region quota
from `0` to `≥1` in GRA9/GRA11.

## Codex trajectory

Brief: iter 1 RC (Codex's own live OVH API probe surfaced exactly the
gap this issue exists to find; 5 P2 endpoint + framing corrections) →
iter 2 APPROVE (0 P0 / 0 P1; 4 P2 confirmations + remaining external
operator blocker). The Seq-8 early-probe sequencing did its job: gap
surfaced ~weeks before I-cd-037 hold and I-cd-038 order.

## Risk surface + side-findings

- **External blocker** for I-cd-038 (#643) provisioning order: the OVH
  support ticket is the unblock path.
- **Box-2 overprovisioning P3 side-note**: Gemma 4 31B-it INT4 ~16 GB on
  320 GB 4×H100 — operator may rightsize at I-cd-037. Locked spec stays
  per the breakdown (this issue does NOT rightsize).
- **Reconciled the prior memory contradiction**:
  `feedback_verify_primary_sources_before_relying_2026_05_15` said
  `h200-1920` doesn't exist; the 2026-05-19 catalog probe found it; this
  probe shows it absent from THIS project's flavor allowlist. Three
  distinct signals; the project-level allowlist is the binding gate.

## Scope discipline

This is a verify-and-record issue. It does NOT:
- Open the OVH support ticket (operator action; cannot file from Claude).
- Rightsize the locked 4×H100 evaluator spec.
- Final-hold inventory (I-cd-037).
- Order GPUs (I-cd-038, [GL gate]).
- Wire models (I-cd-009) or run FP4 spike (I-cd-011).
