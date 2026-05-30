Excellent guidance. The advisor's points are well-grounded and I've verified all the anchors. Let me write the decision document, folding in the Cohere-direct re-opening, the clinical-vs-benchmark Vast.ai split, the "no REFUTED claims" clarity, the recommendation-not-edit posture, and the safety-critical wiring facts.

# POLARIS I-meta-002 — Feasibility Decision: Wiring Mirror / Sentinel / Judge onto Self-Hosted GPUs

**Scope:** Wire Mirror (Cohere Command A+), Sentinel (IBM Granite Guardian 4.1 8B), Judge (Qwen 3.6-35B-A3B) into the 4-role pipeline. Generator (DeepSeek V4 Pro) is already live. This document is a **recommendation** — the runtime lock YAML is operator-signed and is NOT edited here (mutation policy: Codex APPROVE brief + operator commit).

**Verification status:** One adversarial verification ran (Cohere citation/response_format claim) and returned **CONFIRMED**. **No research claim was REFUTED.** No verification overrides apply; every load-bearing claim below stands as researched, with the one minor scoping nuance noted in §1.

---

## 1. SERVING FEASIBILITY PER MODEL

All three are servable. The decisive correction vs. the original premise: **Command A+ is NOT the 111B dense Command A** — it is a **218B-total / 25B-active sparse MoE** (128 experts, 8 active + 1 shared). Sizing the Mirror as a 111B dense model would have under-provisioned it badly.

### 1.1 Mirror — Cohere Command A+

| Path | GPU | Quant | Stack | Citation output |
|---|---|---|---|---|
| **Self-host (vLLM)** | **2 × H100 (160 GB)** | w4a4 (NVFP4) | vLLM ≥ 0.21.0 | inline `<co>…</co: 0:[0]>` spans |
| Self-host bf16 | 8 × H100 / 4 × B200 | none | vLLM | inline `<co>` spans |
| **Cohere-direct (managed API)** | none (hosted, Toronto) | n/a | Cohere Chat API | **JSON `citations` array** |

**Hardware facts (self-host):**
- bf16 weights ≈ 438 GB → **8 × H100 floor** (no quad-H100 bf16 option).
- **w4a4 = 2 × H100 (160 GB) minimum, NOT 1 × H100.** NVFP4 quantizes the **MoE experts only**; the attention path (Q/K/V/O, KV cache, attention compute) stays full precision. So footprint is **above** the naive 218B × 0.5 B = ~109 GB floor (working envelope ~110–150 GB) — a single 80 GB H100 fails.
- **A100 is NOT a viable w4a4 target.** NVFP4/FP8 are emulated on Ampere with zero memory/latency benefit; the official GPU table lists only Hopper (H100) and Blackwell (B200). Do not rent A100s expecting a 4-bit speedup.
- Serving deps: `transformers` + `cohere_melody ≥ 0.9.0`, flags `--tool-call-parser cohere_command4 --reasoning-parser cohere_command4 --enable-auto-tool-choice -tp 2`. OpenAI-compatible `/v1/chat/completions`; POLARIS's existing OpenRouterClient HTTP path works with only a `base_url` override.
- **SGLang is lower-confidence** (Cohere2 support traces to open issue #4570; the `cohere_command4`/`cohere_melody` tooling is documented only for vLLM). **Use vLLM.**

**Citation contract (CONFIRMED by verification):** self-hosted weights emit **inline `<co>` text spans, not a JSON array**, and Cohere's hosted API **forbids `response_format` (JSON schema/object) whenever `documents`/`tools` are supplied** ("not supported in RAG mode"). Minor nuance from verification: the canonical Chat API reference enumerates only `documents` and `tools` as incompatible (the broader `connectors`/`tool_results` list is secondary phrasing) — substance holds. **Mirror output contract must be two-pass on either route:** (call 1) grounded answer + citations; (call 2) separate **non-RAG** call emitting the JSON calibration verdict.

**Recommendation — prefer Cohere-direct for the Mirror.** Cohere is Toronto-based; **Canada is sovereign-OK** per project posture. Cohere-direct (a) returns the JSON `citations` array directly (no `<co>`-span parsing), (b) **eliminates the single largest hardware burden in the stack** (2×H100/160 GB self-host), and (c) runs **full precision**, which matters because the Mirror exists *for its calibration* — see the w4a4-calibration risk in §6. Self-host w4a4 on 2×H100 is the fallback if managed-API sovereignty (Canada acceptable) or availability blocks the direct route. **Operator action:** confirm `cohere/command-a-plus` is exposed on Cohere's managed API (§5).

### 1.2 Sentinel — IBM Granite Guardian 4.1 8B

- **Hardware: trivial.** Dense decoder-only transformer (NOT Mamba-2 hybrid → no exotic engine). 8B bf16 ≈ 16 GB weights, ~24–32 GB practical → fits **1×A100 40/80 GB** comfortably; 4-bit (~5 GB GGUF) fits a 24 GB 4090. Apache-2.0.
- **Serving:** vLLM / SGLang / llama.cpp all official. Cleanest for the gate: **vLLM offline `LLM.generate()` with a pre-rendered prompt, `temperature=0.0`, `max_model_len=8192`**. Context window is **8K** (served) — fine for per-claim calls.
- **Output contract: binary `yes`/`no` inside `<score>…</score>`** — NOT JSON, NOT span attribution, no exposed probability/logprob on the 4.1 card. Parse: strip `<think>`, regex `<score>\s*(.*?)\s*</score>`.
- **⚠ POLARITY (lethal if wrong, per §-1.1): for groundedness, `yes` = UNGROUNDED/hallucinated (risk detected), `no` = grounded/faithful.** Map `yes → UNSUPPORTED/FABRICATED candidate`, `no → grounded`. Inverting this lets fabrications pass.
- **Calling convention changed in 4.1 — do NOT copy 3.x cookbooks.** 4.1 **drops `guardian_config={'criteria_id':...}`**; criteria go in a free-text `<guardian>` block (`build_guardian_block(criteria, think=)`) as the **last user message**. Per-claim convention: claim → **assistant** message; cited span → `documents=[{'doc_id':'0','text':<span>}]`; `<guardian>` groundedness block → **user** message. Use `think=False` on the hot path.
- **Granularity: one call per (claim, cited-span) pair** — matches POLARIS's existing per-sentence provenance model; never feed whole corpora.
- Detector metric ≈ 0.76 BAcc → treat `yes` as an **escalation flag**, not an infallible verdict.

### 1.3 Judge — Qwen 3.6-35B-A3B

- **Slug correction (load-bearing):** correct OpenRouter id is **`qwen/qwen3.6-35b-a3b`** (no hyphen before 3.6). The runtime lock line 77 has **`qwen/qwen-3.6-35b-a3b`** (extra hyphen) — confirmed in-file. A `PG_JUDGE_MODEL` call with the typo'd slug fails / the pathB coverage gate cannot observe the role. See §4/§5.
- **Hardware (MoE — all 35B resident, ~3B active):** bf16 ≈ 70 GB → tight/OOM on one 80 GB H100 at 262K context (needs H200 141 GB or TP). **FP8 (`Qwen/Qwen3.6-35B-A3B-FP8`) ≈ 35 GB → fits one H100/H200 cleanly — recommended self-host target.** H100+ has FP8 tensor cores; **A100 lacks them → use INT8 on A100.** INT4 ≈ 21 GB fits a 24 GB GPU.
- **Structured verdict: strongly supported.** The 5-enum `{VERIFIED|PARTIAL|UNSUPPORTED|FABRICATED|UNREACHABLE}` maps directly to vLLM **`guided_choice`** (hard one-of-N guarantee, no fallback). Thinking-mode-by-default; `--reasoning-parser qwen3` separates the trace from the final verdict.
- **Quant choice matters for correctness, not just parsing:** `guided_choice` guarantees a *parseable* enum, **not a correct one**. A degraded quant emits a valid-but-wrong verdict for a terminal clinical arbiter. **Prefer FP8 (near-lossless) over INT4** for the Judge.

---

## 2. VAST.AI VERDICT

**Split by data sensitivity — this is the crux.**

- **For I-meta-002 (this wiring task + the public DRB-EN golden benchmark): VIABLE / ACCEPTABLE.** I-meta-002 runs the **public golden DRB-EN questions** ("public-golden, not unseen" per project memory). **No private clinical data flows.** The sovereignty research's own carve-out applies directly: "benchmark/synthetic prompts only → the US-broker residual is moot." Use **on-demand**, **verified-EU-DC** hosts, the allowlist filter below.
- **For production clinical inference: FORBIDDEN.** That path stays **direct-EU (OVH France / Scaleway / Hetzner)** per `docs/sovereign_gpu_capacity_confirm.md`. Vast.ai is **strictly second-best** for clinical inference and must not carry real clinical queries.

**Why Vast.ai is forbidden for clinical (residual that survives ALL mitigations):** Vast.ai Inc. is **US-incorporated** (CA stock corp / DE parent) running a **privileged management daemon on each host** + the marketplace control plane. During vLLM inference the query is **decrypted into host RAM and GPU VRAM**, where host root can read it (CUDA VRAM not reliably zeroed; encryption-at-rest doesn't cover in-flight inference). A US broker with privileged host access → data within "possession, custody, or control" → **CLOUD Act reachability**. Verified-EU-DC filtering narrows physical/host-security risk toward direct-EU parity, leaving **exactly one irreducible residual: the US broker interposed in the control plane** — precisely what the narrow threat model forbids for clinical data. (SSH proxy-vs-direct is the *weakest* concern; direct SSH + own TLS defeats it but does NOT close the host-root / US-daemon exposure.)

**EU-host filter (allowlist, NOT a US denylist — `notin:['US']` still admits CN/RU):**
```json
{"geolocation": {"in": ["FR","DE","NL","FI","IE","SE"]},
 "verified": {"eq": true}, "datacenter": {"eq": true}, "static_ip": {"eq": true}}
```
**Filter caveat:** `geolocation` pins **machine location (ISO-2), not host-operator nationality** — there is no host-domicile filter, and geolocation is self-attested (hence `verified`+`datacenter` required). A US-domiciled host with an EU machine passes. A Five-Eyes exclusion would be **stricter than POLARIS's own posture** (which is Canada-OK) and would drop the Canada the operator prefers — surface as an operator tradeoff, do not silently apply.

**On-demand vs interruptible: ON-DEMAND only.** On-demand = exclusive GPU for the instance lifetime, cannot be interrupted by other users. Interruptible (spot) is paused by a higher bid OR any on-demand claim ("on-demand always takes precedence") → corrupted/partial benchmark. Mitigate residual host-disconnect risk: filter `reliability > 0.95` + verified DC + add your own health-check and idempotent re-run.

---

## 3. D8 RELEASE POLICY (highest clinical quality)

**Design proposal that EXTENDS the frozen scorer ordering** — it is NOT what the scorer currently does. Confirmed in code: `reconcile.py:20-25` `_VERDICT_ORDER` = VERIFIED(0) < PARTIAL(1) < UNREACHABLE(2) < UNSUPPORTED(3) < **FABRICATED(4)** (conservative-MAX); `claim_audit_scorer.py:91` currently lumps **UNSUPPORTED + FABRICATED into one `hard_fail` bucket**, `_COVERAGE_THRESHOLD = 0.70`, `_MATERIAL_SEVERITIES = (S0,S1,S2)`, `_PARTIAL_WEIGHT = 0.5`, S3 observe-only. The proposal's occurrence-vs-residual split refines that single bucket using the existing `FABRICATED(4) > UNSUPPORTED(3)` ordering.

**Two-axis, verdict-specific table — applies to MATERIAL (S0–S2) claims only; S3 = observe/log-only, never gates:**

| Verdict | Claim-action | `release_allowed` | Manifest status (reuse existing) |
|---|---|---|---|
| **VERIFIED** | keep in body prose as-is | TRUE | `success` / pass |
| **PARTIAL** | KEEP + visible inline marker ("partially supported: …"); rewrite optional | TRUE | `partial_evaluator_advisory` (if material to coverage) else pass |
| **UNREACHABLE** | KEEP + marker stating subtype (paywall/robots/fetch_failure/source_missing) | TRUE | `partial_evaluator_advisory` |
| **UNSUPPORTED** (material) | REWRITE + re-verify **ONE** pass (reuse §9.2 regeneration budget); if still unsupported → **refuse-in-place** + `gaps.json` | **RESIDUAL-gate**: FALSE only if post-removal Lane-2 coverage < **0.70** | `partial_evaluator_advisory` (coverage holds) / `abort_no_verified_sections` (collapses) |
| **FABRICATED** (material) | **refuse-in-place immediately (NO rewrite)** + `gaps.json` recording refuting/absent span | **OCCURRENCE-gate**: FALSE even after removal | `abort_evaluator_critical` |

**Core design decision — the two axes:** **FABRICATED uses OCCURRENCE-gating** (run held because a fabrication *happened*, regardless of cleanup — it's an active falsehood + generator-integrity red flag) while **UNSUPPORTED uses RESIDUAL-gating** (run held only if what *remains* after cleanup is too thin). `source_missing` UNREACHABLE subtype is a citation-fabrication smell → escalate to UNSUPPORTED handling; paywall/robots/fetch_failure stay soft.

**Hard rules:**
- **ZERO-tolerance, NOT count/rate threshold.** Gate on ANY single material FABRICATED, or any material UNSUPPORTED surviving the one rewrite. Never "release_allowed=false after N failures" / "if unsupported_rate > x" — that is §-1.1-banned metadata AND resurrects the BUG-M-205 "after three failures" anti-pattern the code already removed.
- **"Drop" never means silent deletion.** Refuse-in-place (refusal marker per `atom_refusal_validator` precedent) + `gaps.json` sidecar (LAW II fail-loudly). `release_allowed=false` still emits `report.md` as a reviewable verdict artifact (§9.1 invariant 4) — "gated pending human sign-off," not "no output."
- **Reuse existing statuses** (`pass` / `partial_evaluator_advisory` / `abort_evaluator_critical` / `abort_no_verified_sections`) and the existing `release_allowed` boolean — do NOT invent a new status. Layer on top of `evaluator_gate.py`.
- **Differentiator is NOT "we only show verified claims"** (blanket suppression sacrifices transparency + coverage; literature favors verification-over-abstention). It IS: per-claim machine-checkable terminal verdict + typed `gaps.json` + a single material fabrication gates the run for human sign-off. (Frontier DR tools emit fabrication indistinguishable from verified prose — effectively policy "allow, no gate.")

---

## 4. REVISED ARCHITECTURE (for the runtime lock YAML — recommendation, not an edit)

The lock is operator-signed (mutation policy lines 8–12). The following should land via a **lock-mutation Issue (Codex-APPROVE brief + operator commit)**, not a silent edit. **Family check: deepseek / cohere / ibm-granite / qwen are all distinct lineages and all open-weight with no closed fallback — `all_distinct` family policy (lines 103–110) is preserved.**

| Role | Current lock slug | Correction | Serving route (recommended) |
|---|---|---|---|
| Generator | `deepseek/deepseek-v4-pro` | — (live) | (already wired) |
| **Mirror** | `cohere/command-a-plus` | slug OK | **Cohere-direct managed API (Toronto, Canada-OK)** — JSON `citations`, full precision; fallback = self-host w4a4 on 2×H100 via vLLM |
| **Sentinel** | `ibm-granite/granite-guardian-4.1-8b` | slug OK | self-host vLLM offline `generate()`, 1×A100 40/80GB or 4090@4-bit, `temperature=0.0`, `max_model_len=8192` |
| **Judge** | `qwen/qwen-3.6-35b-a3b` | **→ `qwen/qwen3.6-35b-a3b`** (remove extra hyphen) | **self-host FP8 (`Qwen/Qwen3.6-35B-A3B-FP8`) on 1×H100/H200 via vLLM `guided_choice`** (hard enum). If OpenRouter ever used: **set `provider.require_parameters=true`** or it silently falls back to `json_object` (§9.1 violation) |

**Serving-route rationale:**
- **Mirror → Cohere-direct (Canadian managed) primary.** Removes the heaviest hardware burden (2×H100), gives JSON citations natively, preserves full-precision calibration. Self-host w4a4 on 2×H100 is the documented fallback.
- **Judge → self-host FP8**, not OpenRouter, for the integrity argument: vLLM `guided_choice` is a hard guarantee; OpenRouter hosted structured-output can silently degrade to free-form JSON — the exact §9.1 silent-degradation failure for a terminal arbiter.
- **Sentinel → self-host** (tiny model, Apache-2.0, no managed dependency needed).

---

## 5. OPERATOR ACTIONS STILL REQUIRED

1. **Lock-mutation Issue** to fix Judge slug `qwen/qwen-3.6-35b-a3b → qwen/qwen3.6-35b-a3b` and record the per-role serving routes (Codex-APPROVE brief + operator-signed commit; re-run propagation manifest; update `canonical_pin.txt`).
2. **Confirm `cohere/command-a-plus` is exposed on Cohere's managed API** (Toronto) and provision a Cohere API key — gates the recommended Mirror route. If unavailable → fall back to self-host w4a4 (needs the 2×H100 below).
3. **Vast.ai credit load + EU-host selection** for the benchmark/wiring task: on-demand, allowlist filter (§2), `reliability > 0.95`. Decide whether to apply the stricter Five-Eyes exclusion (drops Canada — operator tradeoff).
4. **GPU sizing decision per role:** Judge = 1×H100/H200 (FP8); Sentinel = 1×A100/4090; Mirror = nothing if Cohere-direct, else 2×H100 (w4a4).
5. **Confirm clinical-data boundary:** ratify that production clinical inference stays direct-EU (OVH/Scaleway/Hetzner) and Vast.ai is benchmark-only.

---

## 6. RISKS + UNKNOWNS

1. **w4a4 may degrade the Mirror's reason for existing.** Mirror = "best calibration in pool." Research proved w4a4 *serves*; it did NOT show 4-bit weights+activations preserve **calibration**. Untested — and a second reason to prefer Cohere-direct full-precision. (If self-host w4a4 is forced, calibration should be re-validated before relying on the Mirror verdict.)
2. **Judge quant correctness:** `guided_choice` guarantees a parseable enum, not a correct one; a degraded quant emits valid-but-wrong verdicts. FP8 chosen to minimize this; INT4 carries real risk for a terminal clinical arbiter.
3. **Sentinel polarity is a one-line lethal failure mode** (`yes`=ungrounded). Must have an explicit test asserting the mapping before wiring.
4. **Sentinel 0.76 BAcc** — detector, not oracle; `yes` is an escalation flag, gated by the Judge and §-1.1 audit.
5. **Medium-confidence research items (carry forward):** exact w4a4 GB (109 GB floor; ~110–150 GB working) and **SGLang Cohere2 support (open issue #4570)** — both reasons vLLM is the only safe self-host path for the Mirror.
6. **Vast.ai host-disconnect:** even on-demand can drop if a host disconnects (no built-in SLA) — needs own health-check + idempotent re-run.
7. **`response_format` RAG-mode limit on Cohere-direct** means the Mirror calibration verdict needs a **separate non-RAG call** (two-pass); a one-call grounded-JSON design is impossible on Cohere's stack.
8. **D8 occurrence-vs-residual split is not yet coded** — `claim_audit_scorer.py:91` currently treats UNSUPPORTED and FABRICATED as one `hard_fail` bucket. Implementing the split is a follow-up diff, design-consistent with the frozen `_VERDICT_ORDER` but not yet present.

**Bottom line:** All three models are servable; the stack is feasible. Wire **Judge self-host FP8 (slug-corrected) + Sentinel self-host + Mirror via Cohere-direct (Canadian, primary) / 2×H100 w4a4 self-host (fallback)**. Vast.ai is acceptable for this public-benchmark task (on-demand, EU-verified) but forbidden for production clinical inference. No research claim was refuted; the one verification confirmed the Cohere citation/response_format constraint.