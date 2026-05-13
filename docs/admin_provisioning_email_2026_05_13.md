# Admin provisioning email — POLARIS Carney demo (2026-05-13)

Single email to forward to the admin. Three tasks: OVH H200 procurement, Vexxhost orchestrator VM, Canadian DNS. Each task is self-contained; admin should be able to execute without coming back for clarification.

---

**Subject:** POLARIS Carney demo — 3 procurement + provisioning tasks (target: ready by 2026-05-22)

Hi,

We're shipping the POLARIS sovereign Canadian deep research demo to the PM's office during the window **2026-06-05 to 2026-06-09**. To make that work I need three subscriptions / provisioning actions completed by **end of week 2026-05-22**. All three are Canadian-jurisdiction or non-US providers — that's a hard requirement, not a preference.

Please reply when each is done with the artifacts noted at the bottom of each section.

---

## Task 1 — OVH Canada H200 GPU server (procurement)

**What:** Order 1× NVIDIA H200 GPU bare-metal server in OVH's Beauharnois, QC datacenter. This is the LLM inference server.

**How:** Send the email below to OVH Canada sales. Two options:

- **Email:** `salescanada@ovhcloud.com`
- **Web form (faster, recommended):** https://www.ovhcloud.com/en-ca/about-us/contact-sales/ — pick "Bare Metal Cloud" + "Quebec, Canada" region.

Paste the body below into either channel. Fill in the **three bracketed placeholders** before sending (corporate entity, your name+email, your phone).

---

### Email body to send to OVH

> **Subject:** Sovereign Canadian AI inference deployment — H200 GPU server, BHS region
>
> Hello OVH Canada,
>
> I'm procuring a dedicated GPU server for a sovereign Canadian AI demo. Need this provisioned and accessible by **2026-05-22** for a government demo window **2026-06-05 to 2026-06-09**. Month-to-month, no long-term commit.
>
> **Required spec:**
>
> | Component | Requirement |
> |---|---|
> | Region | Beauharnois, QC (BHS) — non-negotiable |
> | GPU | 1× NVIDIA H200 SXM 141 GB HBM3e (preferred). If H200 not in stock: 1× H100 80 GB SXM acceptable as fallback. |
> | CPU | ≥ 32 vCPU (modern AMD EPYC or Intel Xeon Scalable) |
> | RAM | ≥ 256 GB DDR5 ECC |
> | Storage | ≥ 2 TB NVMe SSD |
> | Network | ≥ 1 Gbps unmetered; public IPv4 + IPv6 |
> | OS | Ubuntu 24.04 LTS pre-installed |
> | Bare metal vs Public Cloud | Bare metal preferred (HGX H200 dedicated server) for hardware control + no hypervisor surface |
> | Term | Month-to-month |
>
> **Timeline:**
> - Order placed: this week (2026-05-15)
> - Provisioned + SSH-accessible: by 2026-05-22
> - Used during demo: 2026-06-05 to 2026-06-09
> - Tear-down option after 2026-06-15 (~2 weeks uptime)
>
> **Account:**
> - Single tenant
> - Billing entity: **[your Canadian corporate entity — fill in]**
> - Contact (account + technical + support): **[your name, email, phone — fill in]**
>
> **Sovereignty / compliance — please confirm in writing:**
>
> 1. Server physically located in Beauharnois, QC datacenter (not Strasbourg, not Gravelines, not Roubaix).
> 2. No data replication outside Canada under default configuration.
> 3. OVH Canada (the corporate entity invoicing me) is the data controller, not OVH SAS in France.
> 4. Compliance with PIPEDA + Quebec Law 25 for any operator metadata held.
> 5. SLA on availability + remediation if hardware fails during the demo window (2026-06-05 to 2026-06-09).
>
> **Technical access requirements:**
>
> - SSH key-based root login on day 1
> - Out-of-band IPMI/iDRAC for emergency recovery
> - Console access via OVH Manager
> - Snapshot-to-image capability so we can spin up a second instance fast if the primary fails during demo
>
> **Please reply with:**
>
> a. Availability + ETA for the hardware
> b. Written confirmation of the 5 compliance points above
> c. Order link or invoice
>
> This server runs the LLM inference layer only. The orchestrator runs on a separate Canadian-hosted VM. The two communicate over VPN.
>
> Thanks,
> [your name]

---

### When OVH replies, send me back:

- The invoice number / order ID
- The server's public IPv4 + IPv6 address
- The private network configuration details (so we can peer it with the Vexxhost VM)
- SSH access details (root username, key fingerprint)
- ETA confirmation
- Their written response to the 5 compliance points

---

## Task 2 — Vexxhost orchestrator VM (subscribe + provision)

**What:** Subscribe to Vexxhost and provision one Ubuntu 24.04 VM in Montréal. This is the orchestrator that runs FastAPI + Next.js + Redis + Caddy. It talks to the OVH GPU server (Task 1) over a private network.

**How:**

1. **Create account** at https://my.vexxhost.com/ (sign up with your Canadian corporate email).
2. **Pick the Montréal region** in the console (region code `ca-ymq-1`).
3. **Provision one VM** with these specs:

| Setting | Value |
|---|---|
| Image | Ubuntu 24.04 LTS (latest cloud image) |
| Compute | At minimum: **8 vCPU, 32 GB RAM, 100 GB SSD**. Larger is fine. |
| Networking | Floating public IPv4 + IPv6 (both required — our egress lockdown is dual-stack) |
| SSH key | Upload your public key; allow root SSH key-based login |
| Region | Montréal (`ca-ymq-1`) |

4. **Open firewall ports** in the Vexxhost security group: TCP 22 (SSH) + TCP 80 (Let's Encrypt) + TCP 443 (HTTPS). Block everything else inbound.
5. **Confirm with Vexxhost** that the VM is in the Montréal datacenter and that they do not replicate to non-Canadian regions by default.

### When Vexxhost is provisioned, send me back:

- The floating public IPv4 address
- The floating public IPv6 address
- The SSH command line that works to log in as root (e.g., `ssh root@<ip>`)
- The Vexxhost project ID and region (`ca-ymq-1`)
- Confirmation of single-region (Montréal) storage

---

## Task 3 — Canadian DNS registrar + A/AAAA record

**What:** Register (or reuse) a .ca domain at a Canadian registrar and create DNS records pointing a subdomain at the Vexxhost VM.

**Pick ONE of these registrars (both are Canadian):**

- **easyDNS** — https://easydns.com/ — full-service Canadian DNS registrar + DNS hosting in one. Recommended for speed.
- **CIRA-accredited .CA registrar** — https://www.cira.ca/en/canadian-domains/find-a-registrar — pick any Canadian-resident-eligible registrar. Slightly more paperwork but stricter sovereignty.

**Either works.** easyDNS is faster to set up.

### Steps

1. **Pick the domain.** Either:
   - Use an existing .ca domain you control (faster), OR
   - Register a new one (allow ~24 hours for activation).
2. **Subscribe to DNS hosting** at the same registrar (easyDNS bundles this; CIRA registrars usually do too).
3. **Pick the subdomain** — recommend `polaris.<your-domain>.ca`. The full hostname the demo will use.
4. **Create DNS records** pointing the subdomain at the Vexxhost VM from Task 2:

| Record type | Name | Value |
|---|---|---|
| A | `polaris.<your-domain>.ca` | Vexxhost VM floating IPv4 from Task 2 |
| AAAA | `polaris.<your-domain>.ca` | Vexxhost VM floating IPv6 from Task 2 |
| CAA | `polaris.<your-domain>.ca` | `0 issue "letsencrypt.org"` (lets Let's Encrypt issue the TLS cert) |

5. **TTL:** 300 seconds (5 minutes) for the A/AAAA so we can re-point fast if needed during demo prep.

### When DNS is live, send me back:

- The full subdomain (`polaris.<your-domain>.ca`)
- The registrar name
- Confirmation that `dig +short polaris.<your-domain>.ca` returns the Vexxhost IPv4
- Confirmation that `dig +short AAAA polaris.<your-domain>.ca` returns the Vexxhost IPv6

---

## Summary — what I expect back when all three are done

A single reply email with:

1. OVH order ID + server IPv4/IPv6 + 5-compliance written confirmation
2. Vexxhost VM IPv4 + IPv6 + region confirmation
3. Domain hostname + registrar name + DNS verification

Once I have all three I can run the provisioning script and have the demo live by **2026-05-25**, leaving ~10 days of buffer before the **2026-06-05** demo window opens.

If anything in the spec is unclear or any provider says "we can't do that," please reply and let me know — do not substitute. Sovereignty constraints are firm.

Thanks,
[your name]

---

# Notes for me (the user — strip from the admin email before sending)

- Serper stays as the search backend per your 2026-05-13 directive ("search provider is OK to stay serper, as I don't need to share confidential information in it"). I will revert the I-carney-008 Serper-deferred edits in a follow-up PR and re-add `google.serper.dev` to the egress allowlist. `/transparency` will disclose Serper as US-jurisdiction with your framing — search queries non-confidential, generated reports sovereign.
- GH#487 (I-carney-009 Serper swap) will be closed as "user-directive-WONTFIX" since you've explicitly accepted Serper.
- OVH H200 is HARD-GATED on this email completing — GH#199 vLLM swap blocks on the H200 actually existing.
- After the admin replies with all three artifacts, the next code Issue is **I-carney-006** (live-submission rehearsal) which I can run once the Vexxhost VM is reachable via the new hostname.
