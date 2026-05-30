# Vast.ai Budget — POLARIS I-meta-002 (Mirror + Sentinel + Judge wiring + 5-question DRB-EN benchmark)

**Date:** 2026-05-28
**Question answered:** "How much do I pay Vast.ai?"
**Posture:** Highest quality, more GPU is fine, cost is not the constraint — but the operator asked for an honest, complete, itemized number, so every dollar is shown with its arithmetic and its assumption.

---

## 0. Read-this-first framing (four load-bearing decisions baked into every number below)

These four facts move the grand total more than any per-GPU rate. They are stated up front so the arithmetic is honest, not buried.

### 0.1 The Generator (DeepSeek V4 Pro) is NOT on Vast in any scenario
I-meta-002 wires **three** new roles: Mirror, Sentinel, Judge. The Generator (DeepSeek V4 Pro, ~8×H200, the largest model in the stack, 1M context) is **already running on OpenRouter API** in the current benchmark code (`pathB_run_gate.py` pins `OPENROUTER_PROVIDER_ORDER`, single provider e.g. `deepinfra`; the 16 smoke runs on 2026-05-28 used the API path). There is **no supplied Vast price for a V4-Pro-capable box**, and folding an 8×H100 generator into a scenario would silently dominate every total. So:

> **Generator stays on OpenRouter API across ALL THREE benchmark scenarios.** Its cost is a small token line, not a Vast GPU line. The *sovereign self-hosted* generator (8×H200) belongs to **production line #4** (Phase-4-gated OVH-Canada/EU tranche per `docs/blockers.md`), NOT to this Vast benchmark budget.

### 0.2 Vast prices are PER-BOX, not per-GPU
$30/hr buys the **whole** 8×H100 box; $7.47/hr buys the **whole** 2×H100 box; $4.13/hr is one H100. Every line below is `box-hours-held × box-rate`. The research's aggregate "≈355 GPU-hours" figure is a *per-GPU* unit and is **deliberately not reused here** — mixing it with a single $/hr would double-convert. We build bottom-up, per box, per the task's own (config / $/hr / dev-hours / benchmark-hours / subtotal) structure.

### 0.3 Dev-phase HOLD-HOURS are the actual bill — 10×–40× more sensitive than benchmark or rate
The benchmark itself is cold-start-dominated and cheap (compute < 2 min). The real "how much do I pay Vast" answer is **how many hours you leave the boxes UP while debugging**. Same Mirror 8×H100 @ $30/hr:

| Discipline | Held hours | Cost |
|---|---|---|
| Disciplined: destroy between sessions (§8.4), ~9 active debug hrs | 9 hr | **$270** |
| Loose: left up 8 hr/day × 10 days | 80 hr | **$2,400** |
| Worst: 24/7 × 2 weeks | 336 hr | **$10,080** |

A **40× spread on identical work.** So dev is never a single number below — it is modeled as explicit held-box-hours with the §8.4 disciplined-teardown assumption, plus the loose sensitivity.

### 0.4 The cost FLOOR is ~$0 on Vast (API path); self-host is the sovereign-proof UPPER bound
Command A+, Granite Guardian 4.1 8B, and Qwen 3.6-35B-A3B are all servable on OpenRouter/deepinfra (the gate's pinned provider). If dev + benchmark run through the API, **Vast spend is $0** and you pay only API tokens (≈ single-digit dollars — see §1.4). The self-host scenarios below are the **sovereign-self-host upper bound**: what it costs to prove the production cluster path on Vast public GPUs (acceptable because the benchmark uses PUBLIC DRB-EN data, no clinical data — see §5).

---

## 1. Itemized per-role GPU cost (the building blocks)

Workload anchors (from research + `smoke.md` + `polaris_runtime_lock.yaml`):
- **5 questions × ~108 claims = ~540 verifier calls per role** (Mirror, Sentinel, Judge each).
- A **benchmark session** = 1 cold-start + all 5 questions back-to-back on warm boxes. Cold-start is paid **once per session, not per question** (steady-state compute for 540 calls is < 2 min on any config).
- Vast bills **per-second**; partial hours pro-rated. No minimum rental, no setup/reservation fee.

### 1.1 Mirror — Cohere Command A+ (218B total / 25B active sparse MoE)

| Path | Config | Box rate | Cold-start (1 session) | Benchmark session cost | Notes |
|---|---|---|---|---|---|
| **Self-host bf16** | 8×H100 (438 GB weights) | $30.00/hr | 1.6–2.6 hr | **$48–$77** | Full precision. Proves sovereign production path. US-only inventory. |
| **Self-host W4A4** | 2×H100 (110 GB weights) | $7.47/hr | 0.75–1.0 hr | **$5.7–$7.5** | NVFP4 on MoE experts. **Calibration quality UNTESTED** (Mirror's whole job is calibration). |
| **Cohere-managed API** | — (full precision) | $0 GPU | none | **$3.78** total (all 540 calls) | $2.50/1M in + $10/1M out × (1.08M in + 0.108M out). Instant, zero infra. |

Mirror dev hold-hours (self-host paths only — API dev = $0): see §2 scenario tables. The 8×H100 box is what makes Mirror the dominant dev cost lever.

### 1.2 Judge — Qwen 3.6-35B-A3B (MoE, 3B active)

| Config | Box rate | Cold-start | Benchmark session (540 calls warm ≈ 1–2 min) | Recommendation |
|---|---|---|---|---|
| bf16 ~70 GB | 1×H200 $3.56/hr | 3–12 min | run+cold ≈ $0.20–$0.80 | highest quality |
| **FP8 ~35 GB** | 1×H100 $4.13/hr | 2–7 min | run+cold ≈ $0.15–$0.55 | **recommended** — near-lossless, half the download, faster time-to-result |

### 1.3 Sentinel — IBM Granite Guardian 4.1 8B (dense, ~16 GB)

| Config | Box rate | Cold-start | Benchmark session (540 calls warm ≈ 1–3 min) | Recommendation |
|---|---|---|---|---|
| **A100 80GB (EU/Czechia)** | $0.857/hr | 1.5–5 min | run+cold ≈ $0.05–$0.10 | **recommended** — ample VRAM, no KV bottleneck |
| RTX 4090 24GB (EU/NL) | $1.074/hr | 1.5–5 min | run+cold ≈ $0.06–$0.13 | VRAM-tight; FP8 relieves but A100 is cleaner |

### 1.4 Generator (all scenarios) + verifier API floor — OpenRouter token line

The Generator runs on OpenRouter API in every benchmark scenario. The 5-run benchmark is capped at `PG_MAX_COST_PER_RUN=40` per run in `smoke.md`; observed 2-LLM smokes ran well under that. Realistic full-4-role benchmark API token spend (Generator + any API-served verifiers) is bounded by **5 runs × ≤$40 = ≤$200 worst case**, typically **$30–$80** for a clean 5-question pass. **This is paid regardless of scenario** (it is the Generator), so it is held constant and excluded from the Vast-vs-Vast comparison below, then added back in §5/§6.

---

## 2. Three scenarios

**Common to all three:** Generator on OpenRouter API; Judge self-host FP8 1×H100; Sentinel self-host A100 80GB EU. Scenarios differ **only in how Mirror is served** — exactly the real decision I-meta-002 faces.

Dev-hold-hour model (per §0.3, §8.4 disciplined teardown): each self-hosted role gets **~3 debug sessions × ~3 active hrs = ~9 active box-hours**, destroyed between sessions. Integration phase adds **~6 hrs with all self-hosted roles up at once**. Loose-discipline sensitivity (8 hr/day × 10 days held) shown as a flagged upper bound.

Benchmark-related sessions per §0.5/§5 interpretation: **1 clean session + 2 rerun-buffer sessions = 3 sessions total** (the rerun buffer IS the ×2, made explicit so the operator sees the count).

---

### Scenario A — MAX-QUALITY-FULL-SOVEREIGN-SELF-HOST
*Everything self-hosted, including Mirror bf16 on 8×H100. Proves the sovereign production path end-to-end on Vast public GPUs. Highest cost.*

| Role | Config | Box $/hr | Dev hrs (disciplined) | Dev cost | Benchmark: 3 sessions | Bench cost |
|---|---|---|---|---|---|---|
| Mirror | 8×H100 bf16 | $30.00 | 9 | $270 | 3 × ($48–77) | $144–$231 |
| Judge | 1×H100 FP8 | $4.13 | 9 | $37 | 3 × ~$0.4 | $1.20 |
| Sentinel | 1×A100 EU | $0.857 | 9 | $7.71 | 3 × ~$0.08 | $0.24 |
| Integration | all 3 up (Mirror dominates) | ~$35/hr | 6 | $210 | (covered above) | — |
| **Dev subtotal** | | | | **$524.71** | | |
| **Benchmark subtotal (3 sessions)** | | | | | | **$145.64–$232.44** |

- **Storage** (Mirror 438 GB → ~500 GB allocated, held ~2 wk, billed even when stopped, only DESTROY halts): $33–$66 at $0.15–$0.30/GB-mo. Judge/Sentinel storage negligible (~$5). → **$38–$71**
- **Bandwidth/egress**: inbound weight download usually $0 on Vast (`inet_down_cost`=$0 common; verify per offer). Cost of re-download is TIME, not dollars. → **~$0** (budget $10 contingency for a non-zero host).
- **2×-rerun buffer**: already embedded as the 2 extra benchmark sessions above (sessions 2 & 3). No separate line.

> **Scenario A GRAND TOTAL (Vast only):**
> Dev $525 + Benchmark $146–$232 + Storage $38–$71 + Egress contingency $10
> = **≈ $719 – $838** (disciplined dev)
> **Loose-dev sensitivity** (Mirror 8×H100 left up 8hr/day×10d = $2,400 instead of $270): **≈ $2,850 – $2,970**.
> Plus Generator API token line (§1.4): **+ $30–$80** (constant across scenarios).

---

### Scenario B — SMART-QUALITY  *(best quality-per-dollar)*
*Mirror via Cohere-managed API (FULL precision — sovereignty-OK for the benchmark because data is public DRB-EN). Judge + Sentinel self-hosted. Zero Mirror cold-start, zero Mirror infra.*

| Role | Config | Box $/hr | Dev hrs (disciplined) | Dev cost | Benchmark: 3 sessions | Bench cost |
|---|---|---|---|---|---|---|
| Mirror | Cohere API (full precision) | $0 GPU | (API, $0 GPU) | $0 | 3 × $3.78 | $11.34 |
| Judge | 1×H100 FP8 | $4.13 | 9 | $37 | 3 × ~$0.4 | $1.20 |
| Sentinel | 1×A100 EU | $0.857 | 9 | $7.71 | 3 × ~$0.08 | $0.24 |
| Integration | Judge + Sentinel up (Mirror is API) | ~$5/hr | 6 | $30 | (covered above) | — |
| **Dev subtotal (Vast)** | | | | **$74.71** | | |
| **Benchmark subtotal (3 sessions)** | | | | | | **$12.78** |

- **Mirror API dev calls** during debugging (say ~20× the benchmark volume across iteration): ~20 × $3.78 ≈ **$76** of Cohere spend (not Vast — Cohere bill).
- **Storage**: only Judge (~35 GB) + Sentinel (~16 GB) ≈ 100 GB allocated, 2 wk → **~$5–$15**.
- **Bandwidth**: ~$0.
- **2×-rerun buffer**: embedded as sessions 2 & 3 above.

> **Scenario B GRAND TOTAL:**
> Vast: Dev $75 + Benchmark $13 + Storage $5–$15 ≈ **$93 – $103**
> Cohere API (Mirror dev + bench): **≈ $87** (≈$76 dev + $11 bench)
> Generator API token line: **+ $30–$80**
> **Combined ≈ $210 – $270.**
> **Loose-dev sensitivity** (Judge+Sentinel left up — cheap boxes, so impact is small): +$300–$400 worst case → ≈ $510–$670.

---

### Scenario C — ECONOMY-SELF-HOST  *(cheapest full-self-host; quality risk on Mirror)*
*Mirror W4A4 on 2×H100, Judge FP8, Sentinel A100. Everything self-hosted but Mirror runs quantized.*

| Role | Config | Box $/hr | Dev hrs (disciplined) | Dev cost | Benchmark: 3 sessions | Bench cost |
|---|---|---|---|---|---|---|
| Mirror | 2×H100 W4A4 | $7.47 | 9 | $67.23 | 3 × ($5.7–7.5) | $17.10–$22.50 |
| Judge | 1×H100 FP8 | $4.13 | 9 | $37 | 3 × ~$0.4 | $1.20 |
| Sentinel | 1×A100 EU | $0.857 | 9 | $7.71 | 3 × ~$0.08 | $0.24 |
| Integration | all 3 up (Mirror 2×H100 dominates) | ~$12.46/hr | 6 | $74.76 | (covered above) | — |
| **Dev subtotal** | | | | **$186.70** | | |
| **Benchmark subtotal (3 sessions)** | | | | | | **$18.54–$23.94** |

- **Storage**: Mirror W4A4 110 GB → ~128 GB allocated + Judge/Sentinel ≈ 180 GB total, 2 wk → **$14–$28**.
- **Bandwidth**: ~$0.
- **2×-rerun buffer**: embedded as sessions 2 & 3.

> **Scenario C GRAND TOTAL (Vast only):**
> Dev $187 + Benchmark $19–$24 + Storage $14–$28 ≈ **$220 – $239** (disciplined dev)
> **Loose-dev sensitivity** (Mirror 2×H100 left up 8hr/day×10d = $598 vs $67): **≈ $750 – $770**.
> Plus Generator API token line: **+ $30–$80**.
>
> **⚠ QUALITY FLAG:** W4A4 calibration quality is **UNTESTED** for Command A+. Mirror's entire job is calibration auditing — running it quantized risks the one thing it exists to do. Cheapest in dollars, but the quality risk lands on the exact role you cannot afford to degrade. **Not recommended for a quality-no-object posture.**

---

## 3. Scenario comparison (bottom line, disciplined-dev)

| Scenario | Mirror precision | Vast grand total (disciplined) | + Generator API | All-in | Quality | Strategic value |
|---|---|---|---|---|---|---|
| **A** Full self-host bf16 | **Full** | $719–$838 | +$30–$80 | **≈ $750–$920** | Highest | Proves sovereign production path on real GPUs |
| **B** Cohere-managed Mirror | **Full** | $93–$103 Vast + ~$87 Cohere | +$30–$80 | **≈ $210–$270** | Highest (equal to A) | Best $/quality; zero Mirror cold-start/risk |
| **C** Self-host W4A4 | **Quantized (risk)** | $220–$239 | +$30–$80 | **≈ $250–$320** | **Compromised on Mirror** | Cheapest full-self-host, but degrades the calibration role |

**Key insight (the discriminator is precision + strategy, NOT a "self-host = better quality" premise):** A and B both serve Mirror at **full precision**, so they are **quality-equivalent** for the benchmark. C is the only one that compromises quality (W4A4 on the calibration role). So "highest quality" does **not** force A over B. The *only* thing A buys over B is the **sovereign-self-host demonstration** — which the benchmark, on public data with sovereignty explicitly relaxed, does not require.

---

## 4. Production clinical serving (SEPARATE decision — NOT Vast)

Flagged separately per the operator constraint: **production clinical = direct-EU procurement (OVH / Scaleway / Hetzner), NOT Vast.ai.** Clinical patient-facing data carries the no-US-runtime sovereignty constraint; Vast's verified H100/H200 inventory is US-only and therefore **disqualified for production**. This line is order-of-magnitude only.

The sovereign production cluster (per `docs/blockers.md` Path-C, Phase-4-gated AFTER this benchmark APPROVEs) hosts **all four roles self-hosted**, including the Generator (8×H200):

Rough monthly arithmetic (EU direct, 24/7, illustrative GPU-hr rates — **verify with live OVH/Scaleway/Hetzner quotes**):
- Generator V4 Pro 8×H200 + Mirror 4–8×H100 + Judge 1×H200 + Sentinel 1×A100 ≈ **~18–25 GPU equivalents held 24/7**.
- At an illustrative ~$2–$4 / GPU-hr (EU direct, reserved): `~20 GPU × ~$3/GPU-hr × 730 hr/mo` ≈ **$30,000–$45,000 / month** for the full sovereign 4-role cluster held continuously.
- Reserved/committed EU contracts typically cut this materially below on-demand; a right-sized, autoscaled deployment (verifiers not held 24/7) is lower still.

> **This is a separate procurement decision, not part of the Vast benchmark spend.** Do not load this onto Vast.ai. Numbers here are for planning scale only and must be replaced by real EU vendor quotes.

---

## 5. Bottom-line recommendation — "highest quality, cost-no-object"

**Recommended: Scenario B (Cohere-managed Mirror + self-hosted Judge/Sentinel).** All-in ≈ **$210–$270**.

Reasoning, on the real merits (not a false "self-host = higher quality"):
1. **Quality:** B serves Mirror at **full precision** — identical benchmark quality to A, strictly better than C. The calibration role (Mirror's whole purpose) runs untouched.
2. **Risk:** Zero Mirror cold-start, zero 438 GB download, zero risk of losing a stopped Vast instance's weights (the research's data-persistence warning). Cohere is a Canadian vendor — favorable on sovereignty even though the benchmark uses public data.
3. **Cost-no-object doesn't mean "spend for spend's sake":** B is both the highest-quality AND the cheapest full-quality option. Spending 3–4× more on A buys *no extra benchmark quality* — only a sovereign-self-host demonstration the public-data benchmark doesn't need.

**However — if the operator wants this benchmark to ALSO prove the sovereign production path on real GPUs now**, then **Scenario A** is the correct cost-no-object choice. Pick A *for the strategic proof*, not for quality (A and B are quality-equal). A's honest number: **≈ $750–$920 all-in, disciplined dev** (or up to ~$3,000 if Mirror's 8×H100 box is left running loosely — so enforce §8.4 teardown).

**Do NOT pick C** under a quality-no-object posture: W4A4 degrades the exact role you cannot compromise.

### The honest number to load onto Vast.ai

| If you choose | Load onto Vast | Plus other bills |
|---|---|---|
| **B (recommended)** | **$150** Vast credit | + ~$87 Cohere + $30–$80 OpenRouter (Generator) |
| **A (sovereign proof)** | **$1,000** Vast credit (covers disciplined dev + headroom for one loose stretch) | + $30–$80 OpenRouter (Generator) |
| **C (not recommended)** | **$400** Vast credit | + $30–$80 OpenRouter (Generator) |

**Single recommendation:** Load **$150 on Vast** and run **Scenario B**. It is the highest-quality, lowest-risk, lowest-cost path for the public-data DRB-EN benchmark. Reserve the sovereign-self-host proof (Scenario A, ~$1,000) for when you explicitly want to validate the production cluster — which is properly Phase-4 (§4), on direct-EU hardware, not Vast.

---

## Appendix — assumptions & confidence

- **Per-role GPU allocations, throughput, cold-start** are first-principles engineering estimates (research confidence: medium / low-medium). No published Command A+ / Qwen-3.6-A3B / Granite-4.1 vLLM throughput benchmark exists as of 2026-05-28. Benchmark wall-time is cold-start-dominated regardless, so throughput uncertainty barely moves the dollar figures.
- **Cohere Command A+ price ($2.50/$10 per 1M)** is aggregator-sourced (3 aggregators), NOT on Cohere's own pricing page. **Verify directly with Cohere before committing to Scenario B's API line.** Even at 2× this rate, B's Cohere line is ~$170 — still cheapest full-quality.
- **Vast storage $/GB-mo and egress $/GB are host-set marketplace values.** Read live `storage_cost`, `inet_down_cost`, `inet_up_cost`, `min_bid` per offer before renting. Storage bills even when STOPPED — only DESTROY halts it (research, high confidence on mechanism).
- **Sovereignty:** Vast H100/H200 inventory is US-only — acceptable for THIS benchmark (public DRB-EN data, no clinical data) but **disqualified for production clinical** (§4). EU A100/4090 are sovereignty-clean but cannot hold the 218B Mirror.
- **Dev hold-hours** are the dominant and most uncertain line (§0.3). POLARIS history (16 smoke runs in one ~4.5 hr session) means actual iteration count could push dev higher; the §8.4 destroy-between-sessions discipline is the single biggest cost lever — far more than any scenario choice.
- **Generator API token line ($30–$80)** is constant across all scenarios and is bounded above by `PG_MAX_COST_PER_RUN=40` × 5 runs = $200 worst case.
