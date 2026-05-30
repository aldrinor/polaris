# I-meta-002 — Revised 4-role wiring design (iter 2) — Codex adversarial review

UNCAPPED iteration (planning/design). Codex is the REAL adversarial gate here: the workflow that produced these findings had 23/24 verifier agents fail to emit structured verdicts, so the "no claim refuted" status is research-grade, NOT adversarially-verified. Attack the load-bearing claims.

## Output schema

```yaml
verdict: APPROVE_DESIGN | REQUEST_DEEPER_DESIGN
confirmed_claims: [...]                 # load-bearing claims Codex independently CONFIRMS
refuted_or_corrected_claims: [...]      # with primary-source correction
novel_concerns: [...]
d8_policy_assessment: ...               # is the two-axis verdict-specific policy right for clinical?
implementation_order: [...]
operator_decisions_blocked_on: [...]
convergence_call: continue | accept_remaining
```

## Context (settled)

- 4-role lock (I-meta-001 #933, PR #934): Generator deepseek/deepseek-v4-pro (live) + Mirror cohere/command-a-plus + Sentinel ibm-granite/granite-guardian-4.1-8b + Judge qwen/qwen-3.6-35b-a3b + Python validators + Codex §-1.1 audit.
- Codex iter-1 on the first design brief flagged: Cohere Command A+ and Granite Guardian NOT on OpenRouter; Qwen slug typo; Granite native <score> output; release-policy must gate content. ALL CONFIRMED.
- Operator decisions: D5 Qwen-slug-fix APPROVED; D6/D7 serving routed to Vast.ai (token valid, balance $0); D8 "which is highest quality?" answered below.

## Load-bearing findings from the feasibility workflow (ATTACK THESE)

### F1. Cohere Command A+ is 218B-total / 25B-active sparse MoE — NOT 111B dense.
- 128 experts, 8 active + 1 shared. bf16 ≈ 438 GB → 8×H100 floor. w4a4 (NVFP4) = **2×H100 (160GB) minimum, NOT 1×H100** (NVFP4 quantizes experts only; attention path stays full-precision; working envelope ~110–150GB). A100 NOT viable for w4a4 (NVFP4 emulated on Ampere, no benefit).
- Codex: verify the param count + the 2×H100 w4a4 floor against the HF model card CohereLabs/command-a-plus-05-2026 + vLLM docs. This is the single most consequential number — if it's wrong, GPU sizing is wrong.

### F2. Mirror recommendation: Cohere-direct managed API (Toronto), NOT Vast self-host.
- Cohere is Toronto-based → Canada sovereign-OK per project posture. Cohere-direct returns JSON `citations` array natively (self-host emits inline `<co>` text spans needing parsing), runs full-precision (matters — Mirror exists FOR calibration; w4a4 calibration is untested).
- Cohere RAG mode forbids `response_format` when `documents`/`tools` supplied → Mirror needs TWO-PASS: (1) grounded answer+citations, (2) separate non-RAG JSON calibration verdict.
- Codex: is "prefer Cohere-direct managed over Vast self-host for Mirror" sound given the operator routed D6 to Vast.ai? This is a genuine re-opening of the operator's D6. Sovereignty: Cohere Toronto = Canada-OK (narrow threat model = no US runtime vendor; Cohere is Canadian). Confirm/refute.

### F3. Sentinel Granite Guardian 4.1 8B — binary yes/no in `<score>` tags, POLARITY-CRITICAL.
- Dense 8B, trivial hardware (1×A100 40/80GB or 4090@4-bit). Output: binary yes/no in `<score>…</score>`, NOT JSON, no span attribution, no exposed probability.
- **LETHAL POLARITY: for groundedness, `yes` = UNGROUNDED/hallucinated (risk), `no` = grounded/faithful.** Inverting lets fabrications pass. Must have an explicit test asserting the mapping.
- 4.1 calling convention CHANGED: drops `guardian_config={'criteria_id'}`, uses free-text `<guardian>` block as last user message. Claim → assistant msg; cited span → documents=[{doc_id,text}]; guardian block → user msg. Detector ≈ 0.76 BAcc → escalation flag, not oracle.
- Codex: verify the polarity (yes=ungrounded) against IBM's official Granite Guardian 4.1 docs. A polarity inversion is a §-1.1-lethal bug.

### F4. Judge Qwen slug fix + self-host FP8 + guided_choice.
- Lock has `qwen/qwen-3.6-35b-a3b` (extra hyphen). Correct OpenRouter id: `qwen/qwen3.6-35b-a3b`. MoE 35B-total/3B-active. FP8 (`Qwen/Qwen3.6-35B-A3B-FP8`) ≈ 35GB fits 1×H100. vLLM `guided_choice` gives hard one-of-N enum guarantee for {VERIFIED|PARTIAL|UNSUPPORTED|FABRICATED|UNREACHABLE}.
- Recommend SELF-HOST (not OpenRouter): OpenRouter hosted structured-output can silently degrade to free-form json_object (the §9.1 silent-degradation failure for a terminal arbiter). If OpenRouter used, MUST set provider.require_parameters=true. FP8 over INT4 (guided_choice guarantees parseable, not correct — degraded quant emits valid-but-wrong verdict).
- Codex: confirm guided_choice is the right hard-enum mechanism + the FP8>INT4 correctness argument.

### F5. Vast.ai verdict — benchmark-OK, clinical-FORBIDDEN.
- VIABLE for I-meta-002 + public DRB-EN golden benchmark (no private clinical data flows — "public-golden"). FORBIDDEN for production clinical inference: Vast.ai Inc. is US-incorporated, runs privileged host daemon; during inference the query decrypts into host RAM/VRAM where host-root + US-broker control plane = CLOUD Act reachability. Production clinical stays direct-EU (OVH/Scaleway/Hetzner).
- EU-host allowlist filter (NOT us-denylist): `{"geolocation":{"in":["FR","DE","NL","FI","IE","SE"]},"verified":true,"datacenter":true,"static_ip":true}`. Caveat: geolocation = machine location not host-operator nationality; self-attested (hence verified+datacenter required). On-demand ONLY (interruptible = corruptible mid-run).
- Codex: is the benchmark-vs-clinical split sound? Is Vast.ai EU-host acceptable for the public-benchmark wiring task?

## D8 — operator's question "which release policy is highest quality?" ANSWER

NOT a single option (a/b/c/d) — VERDICT-SPECIFIC two-axis policy (applies to MATERIAL S0–S2 claims; S3 observe-only):

| Verdict | Claim-action | release_allowed | Manifest status |
|---|---|---|---|
| VERIFIED | keep as-is | TRUE | success/pass |
| PARTIAL | keep + visible inline marker | TRUE | partial_evaluator_advisory (if material) |
| UNREACHABLE | keep + subtype marker (paywall/robots/fetch_failure/source_missing) | TRUE | partial_evaluator_advisory |
| UNSUPPORTED | rewrite+reverify ONE pass; if still unsupported → refuse-in-place + gaps.json | RESIDUAL-gate: FALSE only if post-removal coverage < 0.70 | partial_evaluator_advisory / abort_no_verified_sections |
| FABRICATED | refuse-in-place IMMEDIATELY (no rewrite) + gaps.json | OCCURRENCE-gate: FALSE even after removal | abort_evaluator_critical |

Two axes: **FABRICATED = occurrence-gating** (held because a fabrication happened — active falsehood + generator-integrity red flag), **UNSUPPORTED = residual-gating** (held only if remainder too thin). `source_missing` UNREACHABLE → escalate to UNSUPPORTED (citation-fabrication smell).

Hard rules:
- ZERO-tolerance on material FABRICATED, NOT a count/rate threshold (count thresholds are §-1.1-BANNED metadata + resurrect the removed BUG-M-205 "after-N-failures" anti-pattern).
- "Drop" = refuse-in-place + gaps.json sidecar (LAW II fail-loudly), NOT silent deletion. release_allowed=false still emits report.md as a reviewable verdict artifact (§9.1 invariant 4).
- Reuse existing statuses (pass / partial_evaluator_advisory / abort_evaluator_critical / abort_no_verified_sections) + existing release_allowed boolean; layer on evaluator_gate.py.
- Differentiator is NOT "we only show verified claims" (blanket suppression sacrifices coverage/transparency). It IS: per-claim machine-checkable terminal verdict + typed gaps.json + single material fabrication gates the run for human sign-off.
- Grounded in code: reconcile.py:20-25 _VERDICT_ORDER (VERIFIED<PARTIAL<UNREACHABLE<UNSUPPORTED<FABRICATED); claim_audit_scorer.py:91 currently lumps UNSUPPORTED+FABRICATED into one hard_fail bucket — the occurrence/residual split refines that.

Codex: is this the highest-quality clinical policy? Is the occurrence-vs-residual distinction correct, or should FABRICATED and UNSUPPORTED both be occurrence-gated (stricter)? This is the operator's actual question.

## Revised serving routes (for the lock-mutation Issue — recommendation, not yet edited)

| Role | Slug | Serving route |
|---|---|---|
| Generator | deepseek/deepseek-v4-pro | already wired (OpenRouter) |
| Mirror | cohere/command-a-plus | **Cohere-direct managed (Toronto) primary; 2×H100 w4a4 vLLM fallback** |
| Sentinel | ibm-granite/granite-guardian-4.1-8b | self-host vLLM offline, 1×A100/4090, temp=0, max_len=8192 |
| Judge | **qwen/qwen3.6-35b-a3b** (slug fixed) | self-host FP8 1×H100 vLLM guided_choice |

Family check: deepseek/cohere/ibm-granite/qwen all distinct, all open-weight → all_distinct policy preserved.

## Operator decisions this raises (Codex: confirm these are genuinely operator-only)

1. Lock-mutation Issue (Qwen slug fix + serving routes) — Codex APPROVE brief + operator commit.
2. Cohere managed API: confirm command-a-plus exposed + provision Cohere API key (gates the recommended Mirror route). Sovereignty: Cohere Toronto = Canada-OK?
3. Vast.ai credit load + EU-host selection (on-demand, allowlist). Five-Eyes-stricter exclusion drops Canada — operator tradeoff.
4. GPU sizing: Judge 1×H100 FP8; Sentinel 1×A100/4090; Mirror nothing (Cohere-direct) or 2×H100 (w4a4 fallback).
5. Ratify clinical-data boundary: production clinical = direct-EU; Vast.ai = benchmark-only.

## Required from Codex

A. Independently verify F1–F5 (especially F1 218B-MoE/2×H100, F3 polarity yes=ungrounded). Refute with primary sources where wrong.
B. Assess the D8 two-axis policy for clinical highest-quality (occurrence vs residual gating).
C. Lock the implementation order (sub-PRs) + flag the longest pole.
D. Confirm which decisions are genuinely operator-only vs Claude-executable.

Iterate until convergence. Claude will push back where evidence supports (feedback_be_skeptical_of_codex).
