# Sovereign GPU capacity confirm/hold — operator runbook

**Issue:** I-cd-037 (#642) — Final OVH capacity hold/confirmation for both demo boxes.
**Acceptance:** Written availability/hold confirmed immediately before provisioning.
**Sent immediately before:** Seq 38 (#643) provisioning order.

---

## §1. Scope (revised per operator directive 2026-05-18)

The original sovereignty constraint required **Canada-only** GPU hosting (`docs/ovh_h200_procurement_spec.md`). Per operator directive 2026-05-18:

> "Canada GPU procurement was too hard/expensive/slow; EU GPU allowed at demo stage. Sovereignty still non-US-OK; OVH France/Scaleway/Hetzner back in scope; Carney 'Canadian-hosted' framing + transparency.md must be reconciled."

So the capacity confirm now polls **three vendors in parallel**, pick whichever returns the fastest "yes, hold confirmed":

| Vendor | Region | SKU candidate | Sovereignty story |
|---|---|---|---|
| **OVH Canada** (preferred for "Canadian-hosted" narrative) | Beauharnois, QC (BHS) | HGX H200 bare-metal, or 1×H100 bare-metal as fallback | Canada-resident; OVH Canada is the controller |
| **OVH France** | Gravelines (GRA9/GRA11) or Roubaix (RBX) | HGX H200 Public Cloud or bare-metal | Non-US (French jurisdiction); EU GDPR |
| **Scaleway** | Paris (PAR1/PAR2) or Amsterdam (AMS1) | H100 NVL or H100 SXM | Non-US; French jurisdiction; GDPR |
| **Hetzner** | Falkenstein (FSN1) or Helsinki (HEL1) | Dedicated GPU H100 (GEX series) | Non-US (German/Finnish jurisdiction); GDPR |

The Carney narration must explicitly disclose if the GPU lands in EU rather than Canada — see `docs/transparency.md` for reconciliation pattern.

---

## §2. Demo window dates (revised 2026-05-20)

- **Demo target window:** 2026-08-31 to 2026-09-06 (per `docs/carney_delivery_plan_v6_2.md` Phase 5).
- **GPU online by:** 2026-08-24 (T-7 before demo).
- **Capacity confirm sent:** 2026-08-22 (T-2 before provisioning).
- **Provisioning order placed (Seq 38 / #643):** 2026-08-22 immediately after capacity-confirm reply.

Earlier-stage spike (Seq 11 / #641 FP4 readiness on ~$400 spot GPU) is independent and can happen anytime in May-July to de-risk the vLLM/SGLang serving stack before demo provisioning.

---

## §3. Capacity-confirm email template (for each vendor in parallel)

Send to all three on the same day (2026-08-22 ±1). Pick the first written-yes reply.

```
Subject: Capacity hold for H100/H200 GPU server — provision in 48 hours, demo window
         starts 2026-08-31

To: <vendor sales contact>

Hi,

Following up on the earlier procurement spec sent <date of original RFQ>.

We need a WRITTEN capacity confirmation for:
- 1× NVIDIA H200 (preferred) or 1× H100 SXM 80GB (acceptable fallback)
- Region: <BHS / GRA / PAR / FSN — pick per vendor>
- Bare metal preferred; Public Cloud acceptable for H200 PCIe SKUs
- Ubuntu 24.04 LTS image
- Provisioned by: 2026-08-24
- Used during: 2026-08-31 to 2026-09-06 (Carney demo)
- Term: month-to-month, no long-term commit

Please reply with:
(a) Confirmed in-stock + provisioning ETA <= 48h from order
(b) Quoted monthly price (CAD or EUR; we are not price-sensitive)
(c) Order link / invoice contact for immediate purchase

Compliance asks (please confirm in writing):
1. Server physically located in <region> datacenter (not US, not Asia)
2. No data replication outside <jurisdiction> under default config
3. <Vendor> is the data controller for any operator metadata held
4. GDPR (EU) or PIPEDA (Canada) compliant
5. SLA on availability during demo window 2026-08-31 to 2026-09-06

This is the immediately-pre-provisioning confirm. The order goes in within 48h
of your written reply. Thank you for the fast turnaround.

— <operator name>
```

---

## §4. Operator action checklist

1. [ ] Customize the three emails (vendor-specific SKU + region).
2. [ ] Send all three on 2026-08-22 (T-9 before demo).
3. [ ] Track replies in `state/sovereign_gpu_capacity_replies/<vendor>_<date>.md`.
4. [ ] Acceptance for I-cd-037 (#642) met when ANY vendor returns: (a) written in-stock confirm, (b) quoted price, (c) order link or invoice contact.
5. [ ] Promote winning vendor reply to "approved" → trigger Seq 38 (#643) provisioning order placement.
6. [ ] If ALL three return "out of stock" → escalate: try AWS Capacity Blocks (US, falls sovereignty but acceptable for "demo dry-run" only), OR push demo window 1 week later.

---

## §5. Why this matters

Per Seq 38 (#643) acceptance "operator-authorized provisioning order placed", we CANNOT order without written capacity confirm. The GPU spend is significant ($1-3k for the demo window) and an "ordered but provisioning delayed by 2 weeks" outcome would miss the demo. The capacity-confirm step is the explicit gate that protects against this.

The 3-vendor parallel polling is a hedge: each vendor's "in stock" status fluctuates daily, especially H200 which remains supply-constrained globally as of 2026-Q2. Sending one and waiting wastes 1-2 days of demo-window slack.

---

## §6. References

- `docs/ovh_h200_procurement_spec.md` — original RFQ template (Canada-only scope; superseded by §3 above for EU-relax)
- `docs/carney_demo_runbook.md` — demo runbook (production deploy state)
- `docs/transparency.md` — sovereignty disclosure pattern (Canadian vs EU framing)
- `project_polaris_already_deployed` memory — current OVH BHS5 orchestrator state
- `project_gpu_procurement_2026_05_15` memory — EU-relax operator directive
