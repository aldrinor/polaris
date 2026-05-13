# OVH Canada H200 GPU server — procurement spec

**Send to:** OVH Canada sales (https://www.ovhcloud.com/en-ca/about-us/contact-sales/ or salescanada@ovhcloud.com)

**Subject:** Sovereign Canadian AI inference deployment — H200 GPU server, BHS region

---

## Use case

POLARIS sovereign Canadian deep research AI. Self-hosted inference of two open-weight LLMs (DeepSeek V4 Pro + Gemma 4 31B) for a Canadian government demo. Data must remain in Canadian jurisdiction; no US-owned infrastructure anywhere in the stack.

## Required spec

| Component | Requirement | Why |
|---|---|---|
| Region | **Beauharnois, QC (BHS)** | Canadian data residency |
| GPU | **1× NVIDIA H200 SXM 141 GB HBM3e** (or 2× if H200 SXM not in stock — H100 80GB acceptable fallback) | DeepSeek V4 Pro (~120B params) needs ~80 GB; Gemma 4 31B needs ~62 GB at fp16; serving both concurrently with vLLM requires ~140 GB GPU memory |
| CPU | ≥ 32 vCPU (any modern AMD EPYC or Intel Xeon Scalable) | vLLM scheduler + tokenizer parallelism |
| RAM | ≥ 256 GB DDR5 ECC | Model weight staging + KV cache overflow |
| Storage | ≥ 2 TB NVMe SSD | Model weight storage (DeepSeek V4 Pro ~250 GB fp16, Gemma 4 31B ~62 GB fp16) + room for fine-tunes |
| Network | ≥ 1 Gbps unmetered, public IPv4, optional IPv6 | Outbound to evidence sources (FDA, NICE, Health Canada, etc.) |
| OS | Ubuntu 24.04 LTS | Matches docker-compose.v6.yml substrate |
| Bare metal vs Public Cloud | **Bare metal preferred** (HGX H200 dedicated server) for full hardware control + no hypervisor surface | Sovereignty audit story |
| Term | Month-to-month, no long-term commit | Demo window only |

## Timeline

- **Order placed:** by 2026-05-15 (this week)
- **Provisioned + accessible via SSH:** by 2026-05-22 (1 week later)
- **Used during Carney demo:** 2026-06-05 to 2026-06-09
- **Tear-down option:** after 2026-06-15 (2 weeks total uptime)

## Account setup

- Single tenant
- Billing entity: [your Canadian corporate entity]
- Contact: [your name + email + phone]
- Technical contact for support tickets: same

## Compliance / sovereignty asks

Please confirm in writing:

1. Server physically located in Beauharnois, QC datacenter (not Strasbourg, not Gravelines, not Roubaix)
2. No data replication outside Canada under default configuration
3. OVH Canada (the corporate entity invoicing me) is the data controller, not OVH SAS in France
4. Compliance with PIPEDA + Quebec Law 25 for any operator metadata held
5. SLA on availability + remediation if hardware fails during demo window (2026-06-05 to 2026-06-09)

## Technical access asks

- SSH key-based root login on day 1
- Out-of-band IPMI/iDRAC for emergency recovery (if bare metal)
- Console access via OVH Manager
- Snapshot-to-image capability for the model-weight-baked image (so we can spin up a 2nd instance fast if the primary fails during demo)

---

This server runs the sovereign LLM inference layer ONLY. The orchestrator (FastAPI + Next.js + Redis) lives on a separate, smaller VM (Vexxhost in Montréal, Canadian-owned). The two communicate over VPN/private network.

Please reply with: (a) availability + ETA, (b) confirmation of the 5 compliance asks above, (c) order link or invoice.
