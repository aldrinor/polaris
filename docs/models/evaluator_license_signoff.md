# POLARIS evaluator — license sign-off (I-cd-006, GH#638)

**Operator sign-off mode** (this session, AskUserQuestion): "Auto-merge per
Codex." Codex APPROVE on the brief + APPROVE on the diff IS the operator's
legal acceptance. Brief APPROVE'd iter 2 (`.codex/I-cd-006/`).

This doc accepts the licenses below for the **Carney one-shot deployment** as
described in §B. The 8 license-grant clauses + 3 deployment dependencies +
attribution implementation plan in §B/§C are the operator's recorded
sign-off basis.

## §A — Deployment shape (the basis for the sign-off)

- **Operator (licensee) domicile:** Canada (OVH BHS5 Québec deployment, operator
  contact `orchunyin@gmail.com`). The licensee is not EU-domiciled.
- **Compute location:** Currently Canada (OVH BHS5). May relocate to EU GPU
  per the 2026-05-18 procurement relaxation. Hunyuan eligibility is
  CONDITIONAL on this choice (see §B Hunyuan row).
- **MAU:** Single Government-of-Canada Office user + the demo + the
  Codex-vetted pipeline. Comfortably under any 700M (Llama) or 100M (Hunyuan)
  threshold.
- **Use case:** Evidence-faithfulness adjudication for a Canadian deep-research
  pipeline (policy/research). Not military, not targeting individuals, not
  CSAM-related, not weapons-related, not any enumerated AUP prohibition.
- **Output use:** Evaluator outputs are RAG-faithfulness verdicts surfaced in
  generated reports. They are NOT used to train, distill, or otherwise improve
  any other LLM (per Codex iter-2 P2, this clears the Llama "non-Llama LLM
  improvement" restriction).
- **Distribution:** No model-weight redistribution planned. If the Carney
  handover bundle ever ships model weights, NOTICE files attach per each
  license.

## §B — Per-license sign-off

### Primary: `meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8`

License: **Llama 4 Community License** + Llama 4 Acceptable Use Policy.
Source: github.com/meta-llama/llama-models/.../llama4/LICENSE + USE_POLICY.md.

Clauses + Carney clearance:

| Clause | Clearance |
|---|---|
| Free for commercial + research use | OK — Carney research use. |
| 700M MAU threshold | OK — well under (single GoC Office, demo). |
| AUP §1(a) **EU-no-grant to EU-domiciled licensees** | OK — POLARIS operator is Canada-domiciled, not EU-domiciled (this applies to the LICENSEE legal entity, not the compute location; EU GPU hosting per 2026-05-18 relaxation does not change licensee domicile). |
| AUP enumerated prohibitions (no military, no targeting individuals, no CSAM, no bio/chem weapons, no safety circumvention) | OK — policy/research use. |
| "Built with Llama" prominent attribution on related website/UI/blog/about/product docs | **PENDING IMPLEMENTATION** — see §C. Codex iter-2 P2: must be visible + legible; dependency before first public Llama-powered use. |
| NOTICE text on distributing copies of Llama materials | OK — no weight redistribution planned; if handover bundle changes, attach NOTICE. |
| Outputs not used to improve non-Llama LLMs | OK — evaluator verdicts are surfaced in reports, not used for training/distillation/model-improvement. |
| HF gated access | DEPLOYMENT DEPENDENCY for I-cd-009 — `request access` with full legal name + DOB + full organization. |

**ACCEPTED for Carney deployment.**

### Hard fallback: `meta-llama/Llama-3.1-405B-Instruct`

License: **Llama 3.1 Community License** + Llama 3.1 AUP.
Source: github.com/meta-llama/llama-models/.../llama3_1/LICENSE.

Headline: same 700M MAU + Built-with-Llama + NOTICE + non-Llama-LLM-output-
restriction as Llama 4. AUP is the Llama 3.1 version (does NOT carry the
Llama 4 multimodal EU-no-grant). HF gated — same `request access` flow as a
deployment dependency for I-cd-009.

**ACCEPTED for Carney deployment.**

### I-cd-011 revisit alternatives

| Model | License | Carney clearance |
|---|---|---|
| `allenai/Llama-3.1-Tulu-3-405B` | **Llama 3.1 Community** (inherits Meta's license; AI2 ImpACT is a separate post-training-data declaration, not the governing model license) | Same Llama 3.1 acceptance as above. ACCEPTED. |
| `nvidia/Nemotron-4-340B-Instruct` | NVIDIA Open Model License (2025-12-12) | Commercial + derivatives OK; outputs not claimed by NVIDIA; redistribution requires license copy + retained notices + NOTICE attribution if present; no Carney-failure clause. ACCEPTED. |
| `Qwen/Qwen3.5-397B-A17B-FP8` | Apache 2.0 | Most permissive; no MAU; standard attribution. ACCEPTED. |
| `MiniMaxAI/MiniMax-M1-80k-hf` | Apache 2.0 | Same. ACCEPTED. |
| `zai-org/GLM-4.5` | MIT | Most permissive. ACCEPTED. |
| `arcee-ai/Trinity-Large-Thinking` | Apache 2.0 | Most permissive. ACCEPTED. |
| `baidu/ERNIE-4.5-VL-424B-A47B-PT` | Apache 2.0 | Most permissive. ACCEPTED. |
| `tencent/Tencent-Hunyuan-Large` | Tencent License (worldwide EXCLUDING EU) | **CONDITIONAL.** Only ACCEPTED if Carney compute stays outside the EU AND all licensed acts (use, reproduction, modification, distribution, display, output access) stay outside EU territory. If post-2026-05-18 procurement relocates to EU GPU, Hunyuan is **HARD INELIGIBLE** and must be removed from the I-cd-011 candidate set. Also clears 100M MAU, no-output-to-improve-other-LLM, downstream-restriction-notice, and public-machine-generated-disclosure for the non-EU Carney shape if documented per §C. |

## §C — Deployment-step dependencies for I-cd-009

I-cd-009 (#624 — `align model/config to V4 Pro + 400B evaluator`) cannot pull
weights until these complete:

1. **Meta Llama 4 Maverick HF access**: `request access` at
   `huggingface.co/meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8` —
   requires the operator's full legal name, DOB, and full organization name.
2. **Meta Llama 3.1 405B Instruct HF access** (fallback path): same
   `request access` with the same identity disclosure.
3. **Community INT4 quant repo for the chosen model** (the specific Maverick
   or 405B AWQ/GPTQ quant chosen at I-cd-011): separate wrapper-license +
   NOTICE check before pulling.

## §D — Attribution implementation plan

Per Llama 4/3.1 Community License "Built with Llama" requirement, prominent
+ visible + legible on related UI/pages, before first public Llama-powered
use:

1. `docs/transparency.md` (new or appended) — names Llama 4 Maverick (primary)
   or Llama 3.1 405B Instruct (fallback) as the evaluator; carries the
   verbatim "Built with Llama" sentence.
2. **Demo UI footer** — visible "Built with Llama" string on the production
   `polarisresearch.ca/` pages. Lands at I-cd-022 (home rebuild) at the
   latest; the I-cd-004 AppShell can be extended sooner if a public demo
   precedes I-cd-022.
3. **NOTICE files** — alongside any redistribution. None planned for the
   Carney one-shot; if the handover bundle ships model weights, attach the
   relevant NOTICE per Meta + each non-Llama license.

## §E — Sign-off declaration

Per the operator's session AskUserQuestion ("Auto-merge per Codex") and
Codex's APPROVE on both the brief (iter 2) and (about to be requested) the
diff: the licenses above are **accepted** for the Carney one-shot deployment
described in §A. The deployment-step dependencies in §C and the attribution
plan in §D are the implementation commitments this acceptance carries.

If the Carney deployment shape changes materially (different operator
domicile, different MAU regime, EU GPU hosting affecting Hunyuan eligibility,
output use for non-Llama LLM training), this sign-off does NOT extend to the
new shape — file a follow-up I-cd-006-followup.
