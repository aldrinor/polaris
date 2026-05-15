# Codex planning consult — Carney demo action-items cross-check

**Type:** PLANNING CONSULT (advisor, not gate). Single round. No diff, no merge gate. Goal: find what's missing from my action-item list. Push hard. If I'm fooling myself about what "ready" means, name it.

**Operator prompts to me (verbatim, in order during this conversation):**
1. "Could you pls go through with codex, and cross check the action items, I am afraid we miss something."
2. (1 minute later, while I was drafting this brief): **"I want to start running the whole thing with frontend and backend with GPU ASAP."**

**The second message changes the priority order.** The operator is no longer in "what do we do while we wait" mode — they want the full sovereign stack (frontend + backend + GPU) online ASAP. So the question is no longer "wait-window action items"; it is "what is the fastest path to a working sovereign-GPU stack, and what must we pre-stage on the orchestrator NOW so the GPU box is plug-and-play the moment it lands?"

The original action-item cross-check is still in scope, but it is subordinate to the GPU-online-ASAP directive.

---

## §0. Iteration cap directive (per CLAUDE.md §8.3.1, applied even for single-round planning)

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

(For this planning consult: APPROVE means "the action-item list is complete enough to execute, no critical gap I missed." REQUEST_CHANGES means "Claude is missing at least one P0 or P1 item.")

---

## §1. Hard physics — what's true on the ground RIGHT NOW

### 1.1 Demo timeline
- **Demo window:** 2026-06-05 to 2026-06-09 (5 days). Plus rehearsals. **22 days from today (2026-05-15).**
- **Audience:** PM Mark Carney's office, single venue.

### 1.2 What is LIVE and verified (2026-05-15 ~02:42 UTC)

OVH Public Cloud, **BHS5 (Beauharnois, Québec, Canada)**, project `446fccde73604cfbb0758c6012dad6d1`.

Orchestrator: instance `polaris-orchestrator`, flavor `b3-16` (4 vCPU / 16 GB / 100 GB), IPv4 `51.79.90.35`, IPv6 `2607:5300:205:300::25c7`, Ubuntu 24.04, Docker CE 29.5.0 + Compose v5.1.3. SSH via `~/.ssh/polaris_orchestrator_key`.

`docker compose -f docker-compose.v6.yml` containers all healthy:
- `polaris-redis-1` (broker)
- `polaris-api-1` (FastAPI v6.2.0, :8000) — `verify_app_startup()` passes
- `polaris-worker-1` (Dramatiq consumer, healthy via redis-reachability override)
- `polaris-webui-1` (Next.js 16.2.4 standalone, :3000, healthy via 127.0.0.1 override)

Verified end-to-end:
- `GET http://polarisresearch.ca:8000/health` → 200, `{"status":"ok","version":"6.2.0"}`
- `GET http://polarisresearch.ca:3000/` → 200 (Next.js UI)
- `POST /auth/login` with `carney_office` → valid HS256 JWT (12h); bad password → 401
- `GET /transparency` → `provider: "OVHcloud Public Cloud", region: "BHS5 (Beauharnois, Quebec, Canada)", git_commit: 26d34bcc, signing_key_id: 1CE0E526B61D0E06, sovereignty_filter.cleared_tiers: [T1]`
- Retrieval keys live: SERPER + SEMANTIC_SCHOLAR (operator's keys, in `~/polaris/.env`, mode 600)
- GPG signing key `1CE0E526B61D0E06` in `/home/ubuntu/gpg-polaris`, mounted into containers at `/app/gpg`
- `/etc/polaris/static_accounts.yaml` (640 root:root) holds 2 bcrypt-hashed accounts: `carney_office` (reviewer), `ops` (admin)

Domain: **polarisresearch.ca REGISTERED via GoDaddy** (operator). DNS resolves from authoritative ns55/ns56.domaincontrol.com: `@ A 51.79.90.35`, `@ AAAA 2607:5300:205:300::25c7`, `www A`. Verified via `dig +short`. CAA record empty (GoDaddy AI flagged a format issue on first attempt; deferred).

### 1.3 What is NOT live

- **Sovereign GPU box.** OVH support ticket submitted 2026-05-14 for H100 flavor enablement in BHS5; awaiting response. Fallback if OVH says no: Vexxhost Montréal or ISAIC.
- **Sovereign LLM model decision** unresolved. Prior Codex cost-consult recommended **70B-class open-weight** on 1–2× H100 to fit ~$300/mo demo budget; operator hasn't confirmed which 70B candidate. Generator-evaluator two-family invariant must hold (different lineages).
- **OPENROUTER_API_KEY deliberately ABSENT** in `~/polaris/.env`. Generation route honestly returns `400 completion_backend_unavailable` per LAW II until sovereign GPU is wired. This is intentional — no US-vendor LLM fallback.
- **TLS / HTTPS:** not yet wired. `https://polarisresearch.ca` 404s. Demo URL is currently `http://polarisresearch.ca:3000` which is unprofessional and breaks browsers that auto-upgrade.
- **OVH firewall state:** unknown beyond "ports 8000 + 3000 reachable from public internet right now." Have not inspected security group / network ACLs. SSH on :22 is open (verified).

### 1.4 Repo-vs-box drift (real bugs found tonight, NOT yet in repo)

Build fixes applied directly to the box, will land as one I-bug-113 deploy PR:
1. `requirements.txt`: langchain pins capped (`<0.4.0` / `<3.0.0`) — pip resolver was walking through langchain 1.x for 34 minutes.
2. `requirements-v6.txt`: `pydantic-settings==2.6.1` → `>=2.10.1,<3.0.0` (langchain-community needs 2.10.1+); appended `bcrypt==4.0.1`.
3. `requirements.lock`: uv-generated 282-package pinned lockfile; `bcrypt==4.0.1` (5.0.0 breaks `passlib==1.7.4`).
4. `Dockerfile.v6`: pip step installs from `requirements.lock` (5 min vs 34-min resolver runaway).
5. `scripts/v6_entrypoint.sh`: committed with CRLF line terminators → kernel error `exec /entrypoint.sh: no such file or directory` (it's looking for `/bin/bash\r`). Repo fix: `.gitattributes` `*.sh text eol=lf`.
6. `web/Dockerfile:53` healthcheck uses `localhost` which resolves to IPv6 `::1`, but Next.js standalone binds IPv4 `0.0.0.0` only → connection refused. Repo fix: `localhost` → `127.0.0.1`.
7. `docker-compose.v6.yml` worker inherits the shared `Dockerfile.v6` HEALTHCHECK that probes `:8000/health` — but the worker is a Dramatiq consumer with no HTTP server. Repo fix: per-service healthcheck override.

Box is running off `git archive origin/polaris` commit `26d34bcc` with the patches applied on top. A `git pull` on the box would WIPE the patches. **If anything causes the orchestrator to be rebuilt before I-bug-113 ships, we're back to nothing.**

### 1.5 Resource posture

- Orchestrator: ~1.1 GB / 15 GB RAM, all containers idle <200 MB. Plenty of headroom.
- Billing: ~$0.16 CAD/hr (~$117 CAD/mo) **running 24/7 since 2026-05-14**. Operator said "use it when request is on, kill it immediate after end" — orchestrator is harder to kill (it needs to be reachable when Carney's office hits the URL) but post-demo teardown is a real cost item.
- OVH API token `polaris-ovh-30d` valid until ~2026-06-13 (30 days from 2026-05-14). Demo is 2026-06-05 to 2026-06-09 — **token expires ~4 days after demo end.** That's tight. Token renewal pre-demo or extended to 90d is non-obvious.

---

## §2. The action-item list I'm proposing to execute in the GPU-waiting window

Operator just asked "what can we do between this period of time?" My recommended sequence:

### 2.1 Highest-priority during the wait (operator-facing, non-blocking on GPU)

| # | Item | Memory anchor | Est | Blocks demo if missing? |
|---|---|---|---|---|
| A | **Walk the live system end-to-end as a non-developer** — log in as `carney_office`, run intake, run retrieval, view transparency, view report shell. Click every visible button. Find what 404s, what breaks, what's confusing. | `bpei_phantom_completion_lessons.md`: "code-level done ≠ product-level done" | 1–2 hr | YES — silent UI breakage on demo day = mission fail |
| B | **TLS via Caddy sidecar** → `https://polarisresearch.ca`. Open :80 + :443 on OVH firewall. HTTP-01 challenge. | none | 30–60 min | YES — modern browsers auto-upgrade; some block mixed-content; URL looks unprofessional without it |
| C | **G5 (P0): T-1 fallback laptop full drill.** Document what to do when the venue WiFi dies, when OVH dies, when the GPU dies during the demo. | task #306 | 2–4 hr | YES — Carney demo cannot have "the system is down" as a possibility |
| D | **G7 (P1): Egress lockdown black-box validation.** Confirm the orchestrator actually CAN'T reach US LLM endpoints (sovereignty proof for Carney). | task #308 | 1 hr | NO but operator will ask |
| E | **G8 (P1): T1 source snapshot cache.** Pre-fetch FDA/EMA/Health Canada/NICE source pages so a slow venue WiFi doesn't kill retrieval mid-demo. | task #309 | 2–3 hr | NO but high latency in front of Carney = bad |
| F | **G18 (P1): PIPEDA/Law 25/NDA/AUP notice** on `/transparency` page. | task #319 | 30–60 min | NO but Carney's office WILL care |
| G | **I-bug-113 deploy-reconciliation PR** — turn the 4 box-vs-repo fixes into one PR through Codex review → merge. | task #321 + box drift in §1.4 | 1–2 hr | YES IF the orchestrator ever needs rebuild before demo |

### 2.2 Blocked on GPU box (cannot execute yet)
- G1 (P0): Full sovereign dress rehearsal — needs generator working
- GH#473: Live-submission rehearsal (5 canonical + 5 staff-style §-1.1 audit)
- GH#495 I-gen-003: V4 Pro CoT validation — partially executable in dev (OpenRouter dev path) but the sovereign-validation half waits
- GH#496 I-gen-004: capture V4 Pro reasoning trace separately
- Hard V4 Pro stress test (multi-question sweep)
- G6 (P1): Pre-recorded "known-good" demo runs as disclosed fallback — needs a successful run first
- G11 (P1): Capacity + cold-start timing measurement
- G12 (P1): Real v6 bundle verification proof on clean machine

### 2.3 In-flight on OVH side (operator action, not Claude action)
- OVH support ticket: H100/H200 flavor enablement in BHS5 — awaiting OVH reply

### 2.4 Operator-side action items I think operator already handled
- Domain registration (done via GoDaddy)
- DNS records (done via GoDaddy AI)
- OVH API token creation (done; in .env)
- GPG demo signing key (done; `1CE0E526B61D0E06`)
- Static accounts demo credentials (delivered to operator in-session)

---

## §3. The question for Codex

**GIVEN THE OPERATOR'S "GPU ASAP" DIRECTIVE, the primary question for Codex is:**

### 3.0 (NEW, primary) — Fastest path to sovereign GPU online

A. **OVH BHS5 H100 enablement (current ticket path):** OVH support ticket pending. Historically OVH support reply is 24–72 hours; quota grants on a fresh project can take days. We have no SLA. Is "wait for OVH" actually viable given the 22-day demo timeline, or is it dead on arrival?

B. **Vexxhost Montréal (alternate sovereign Canadian provider):** They publish public-cloud H100 SKUs and have an OpenStack API. Setup: account creation + payment method + key upload + instance spawn. What's the realistic time-to-first-token on Vexxhost vs OVH at this point? What's their per-hour H100 price (the operator's `feedback_no_cost_mentions` is suspended for this turn — operator opened cost discussion already; we need real numbers to make a real recommendation).

C. **ISAIC.ca (Canadian sovereign cloud, public sector adjacent):** I have not researched. What is it, what GPUs do they have, and is it a realistic option in 22 days?

D. **OVH France (BHS-not-available fallback):** If OVH says "H100 yes, but only in Gravelines/Strasbourg," does that break the sovereignty story? Per operator's threat model (`feedback_sovereignty_threat_model`): "no US company anywhere = no runtime US LLM vendor calls + no data in US jurisdiction. NOT about model lineage." France is EU, not US. Is "data in France during demo" a viable sovereignty story for a Canadian-PM demo, or is it the wrong optics?

E. **Pre-staging work on the orchestrator that's independent of which GPU provider wins:** What can we land in the next 2-3 days so that when ANY of A/B/C/D resolves, we can spin up vLLM/SGLang and have generation working same-day? Examples:
- Model selection committed (70B class per prior consult — name the specific weight: Llama-3.3-70B-Instruct, Qwen-2.5-72B-Instruct, DeepSeek-V3-Lite, other?). Two-family-evaluator pairing decided.
- vLLM or SGLang serving config templated for the chosen weight.
- Orchestrator-side OpenAI-compatible client pointed at a configurable `GPU_BASE_URL` so flipping providers is one env-var change.
- Cold-start time budget measured (10-20 min for 70B-class per prior consult).
- Health-probe protocol so the orchestrator knows the GPU is ready before accepting demo traffic.

F. **Sovereignty defensibility of each path.** If we pick Vexxhost and Carney's office asks "is Vexxhost a Canadian company?" — what's our one-sentence answer? Same for ISAIC, OVH-France, OVH-BHS.

### 3.1 Cross-check my action-item list. What is missing? Specifically:

### 3.1 Operational/security risks I might have skipped past
- The orchestrator's `/auth/login` is internet-reachable on `:8000`. Is there meaningful brute-force protection? Anyone with the domain can hit it for as long as they want.
- The `/etc/polaris/static_accounts.yaml` only has 2 passwords. If `carney_office` is shared with multiple staff members, is that a problem (no per-user audit)?
- `:8000` and `:3000` are both directly internet-exposed (no reverse proxy). The webui's Next.js standalone server is the trust boundary for `/api/v6/*` rewrites; is that defensible?
- OVH SSH (`:22`) is wide open to the public internet. SSH key is on the operator's machine. Should we restrict by source IP, or move to a bastion, or accept the risk for 22 days?
- The orchestrator's SQLite (`/app/state/v6_runs.sqlite`) lives in a Docker volume `polaris_shared_state` on the OVH disk. No off-box backup. If the VM disk fails or the volume is `down -v`'d by mistake, all run history vanishes. Is that material for the demo? For post-demo handover?

### 3.2 Demo-day failure modes I might not have planned for
- **Venue network** — venue WiFi might be slow, captive-portal'd, IPv6-only, blocking outbound `:8000`, or just dead. G10 is in the pending list but I haven't planned a "what we actually do" sequence.
- **Cellular hotspot fallback** — if WiFi dies, who has the hotspot? Carrier? Data cap? Is the orchestrator URL reachable through Canadian carrier NAT?
- **Demo-day timing** — Carney's office hour is bounded. If the system takes 90s for one query, that's the whole meeting. Have we timed an actual end-to-end query?
- **What happens if Carney asks a question we haven't pre-tested?** The honest answer is "we run it"; the dishonest answer is "show this canned response." Which one are we ready for?
- **What if the sovereign GPU never arrives in time?** Have we made the demo executable on a CPU-only / smaller-model fallback? Or is the demo cancelled?

### 3.3 Cost / OVH discipline gaps
- **OVH API token expires ~2026-06-13.** Demo is 2026-06-05 to 2026-06-09. If we need to provision/destroy GPU instances during the demo week, that's tight. Should we extend now?
- **OVH-Canada quota state.** We requested a GPU quota increase via support ticket but haven't confirmed it was granted. If they grant a too-small quota at the wrong moment, that's a hard problem.
- **Post-demo teardown.** No documented "scripted teardown" — there's a G13 (secret inventory + rotation/revocation/teardown sheet, marked completed) but I haven't verified the teardown actually works end-to-end. Do we know how to make the OVH bill go to $0 after handover?

### 3.4 Claims we might be making to Carney's office that we can't actually substantiate
- "Sovereign Canadian." We're running on OVH Canada (BHS5), DNS via GoDaddy (US registrar; data plane is GoDaddy CDN/anycast though authoritative servers may be in Canada — I have not verified). Per the user's memory `feedback_sovereignty_threat_model_2026_05_13`: "no US company anywhere = no runtime US LLM vendor calls + no data in US jurisdiction. NOT about ... registrar." So GoDaddy is acceptable per the operator's own threat model — but I should be able to defend that specific framing to Carney's office.
- "Two-family evaluator." The invariant is enforced in code (`openrouter_client.check_family_segregation`) but the generator is not yet selected, so the family-segregation claim is currently empty.
- "Auditable per-sentence." Generator-side strict_verify is in code; the actual audit-bundle GPG signature is configured (`1CE0E526B61D0E06`). Has anyone outside our team verified the signature on a real bundle? Per `g13_secret_inventory` (completed) we have an inventory; we don't have a verified third-party verification.
- "Replayable provenance." Per G17 — narrowed claim. Is the wording on `/transparency` consistent with that narrowing?

### 3.5 Things I haven't even thought of
**This is the most important section.** Codex: enumerate categories I haven't named.

---

## §4. Output schema (per CLAUDE.md §8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [<list of P0 items I MISSED. Each: name, why-it-blocks-demo, recommended action>]
continuing_p0: []   # first iter, nothing to continue
p1: [<list of P1 items I MISSED. Same shape.>]
p2: [<lower priority / nice-to-have>]
p3: [<cosmetic>]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [<things that, if true, mean §2 list is unsafe to execute even with the patches>]
reasoning: <your full reasoning, including: do you agree with my §2 priority order? what would you re-order? am I underestimating any execution time? are there scope items operator has not been told about that they should be told about now, 22 days out?>
```

**Important — what NOT to do:**
- Do NOT propose rewriting the architecture. Demo is 22 days out. No restructure can land.
- Do NOT propose new substrate that hasn't been demanded by Carney's office.
- Do NOT cargo-cult enterprise concerns (full SOC-2, full multi-tenant) — this is a single-venue demo.
- DO push back hard on anything in §2 that looks like busywork vs real demo-readiness.
- DO flag if I'm being optimistic about the GPU box timeline (Vexxhost / ISAIC / OVH France-only — what's the actual contingency tree?).
- DO answer §3.0 first; that is the new top priority per the operator's second message.

## §5. Output structure expectation

Top of your reply: a **§3.0 recommendation block** named `gpu_path_recommendation` with this shape:

```yaml
recommended_provider: ovh-bhs | ovh-france | vexxhost-montreal | isaic | other
recommended_model: <exact HuggingFace path or model name>
recommended_serving_stack: vllm | sglang | other
estimated_time_to_first_token_hours: <number>
estimated_demo_period_cost_cad: <number>
sovereignty_one_liner: <text — what to tell Carney's office>
top_risk: <text>
pre_stage_now: [<list of orchestrator-side changes Claude should land in next 2-3 days that are provider-agnostic>]
contingency_if_recommended_path_dies: <text>
```

Then the standard §4 schema covering the rest of the action items.

