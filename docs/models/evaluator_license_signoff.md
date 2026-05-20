# POLARIS evaluator — license sign-off (I-cd-005-followup, GH#638 + GH#637)

**Operator sign-off mode** (per I-cd-006 AskUserQuestion, carries through
this followup): "Auto-merge per Codex." Codex APPROVE on the followup brief
+ APPROVE on the diff IS the operator's legal acceptance. Brief APPROVE'd
iter 2 (`.codex/I-cd-005-followup/`).

**Supersedes I-cd-006 (PR #662, merged `e1fa8e24`)** which signed off the
Llama 4 Maverick + 8 alternatives shape. The model is now
`google/gemma-4-31B-it` (Apache 2.0 + Gemma Prohibited Use Policy overlay)
per I-cd-005-followup. This sign-off accepts the Gemma 4 31B-it license shape
for the Carney one-shot deployment described in §A.

## §A — Deployment shape (the basis for the sign-off, unchanged)

- **Operator (licensee) domicile:** Canada (OVH BHS5 Québec deployment,
  operator contact `orchunyin@gmail.com`).
- **Compute location:** Canada (current) or EU (per the 2026-05-18 GPU
  procurement relaxation). Gemma 4 31B-it Apache 2.0 has no territorial
  clause, so both are fine.
- **MAU:** Single GoC Office user + the demo + the Codex-vetted pipeline.
  Apache 2.0 has no MAU threshold.
- **Use case:** Evidence-faithfulness adjudication for a Canadian deep-
  research pipeline. Not military, not targeting individuals, not CSAM-
  related, not weapons-related, not any enumerated PUP prohibition.
- **Output use:** Evaluator outputs are RAG-faithfulness verdicts surfaced
  in generated reports. NOT used to train, distill, or otherwise improve
  any other LLM.
- **Distribution:** No model-weight redistribution planned. If the Carney
  handover bundle ever ships model weights, attach Apache 2.0 LICENSE +
  retain notices.

## §B — Per-license sign-off

### Primary: `google/gemma-4-31B-it` (BF16) + `ebircak/gemma-4-31B-it-4bit-W4A16-AWQ` (community INT4 for vLLM)

License: **Apache 2.0** (per Codex iter-2 P2 verification:
`ai.google.dev/gemma/apache_2`, HF model card label, Google license page).
The operative model license is Apache 2.0; the legacy "Gemma Terms" page is
deprecated for Gemma 4.

**License clauses + Carney clearance:**

| Clause | Clearance |
|---|---|
| Apache 2.0 grant: free for any use (commercial, research, redistribution) | OK — Carney research/policy use. |
| MAU threshold | NONE (vs Llama Community's 700M). |
| HF gating (`request access`) | NONE (vs Llama 4 / Llama 3.1 gating). Codex iter-2 P2: "no `Request access`/gated text found." |
| Attribution requirement | Apache-style only: retain copyright/notices, provide LICENSE on redistribution, mark modified files, include NOTICE only if a NOTICE file is present in the redistribution. NO "Built with Gemma" placement requirement (Codex iter-2 P2). |
| Outputs not used to improve non-Gemma LLMs | Apache 2.0 has no such clause; the Gemma PUP overlay (§B.1 below) also does not restrict output use for non-Gemma LLM improvement. OK. |
| HF gated access | None (Codex iter-2 P2) — no deployment-dep step required for I-cd-009 wiring. |

**ACCEPTED for Carney deployment.**

### §B.1 — Gemma Prohibited Use Policy (PUP) overlay

Per Codex iter-2 P2 (source `ai.google.dev/gemma/prohibited_use_policy`),
Google publishes a Gemma PUP covering Gemma and its derivatives. It is NOT
a MAU/gating/branding requirement (the Apache 2.0 license stands as the
operative grant); it is an acceptable-use overlay. Prohibited use
categories:

| PUP category | Carney clearance |
|---|---|
| Rights-infringing (privacy, IP, defamation) | OK — RAG-faithfulness adjudication on cited evidence is fair-use research; no infringement. |
| Dangerous / illegal / malicious (weapons, malware, exploitation) | OK — policy/research use. |
| Misleading | OK — evaluator's job is to flag misleading content, not produce it. |
| Harmful (violence, harassment, sexual content involving minors) | OK — out-of-scope by design. |
| Sexually explicit | OK — out-of-scope by design. |

**Gemma PUP cleared for Carney deployment.**

### §C — Runtime quant artifact

The intended 4×H100 runtime artifact is the community INT4 AWQ:
`ebircak/gemma-4-31B-it-4bit-W4A16-AWQ`. As a third-party redistribution of
quantized Gemma 4 weights, it is a derivative work under Apache 2.0.
Apache-style attribution (retain notices, include LICENSE on
redistribution) applies. I-cd-009 wiring SHOULD verify the artifact's
NOTICE file (if any) is preserved in the Docker image and runtime
deployment.

NVIDIA's NVFP4 sibling (`nvidia/Gemma-4-31B-IT-NVFP4`) is Blackwell-only
and not the 4×H100 target. If a future Blackwell migration adopts it, its
own NVIDIA-published attribution applies in addition to Apache 2.0.

### §D — Hard fallback (kept from I-cd-005)

`meta-llama/Llama-3.1-405B-Instruct` + AWQ/GPTQ-INT4 — accepted under
Llama 3.1 Community License + Llama 3.1 AUP (per I-cd-005's earlier sign-off
machinery). The sign-off shape stands: Canada-domiciled licensee, <700M
MAU, "Built with Llama" required on related UI before first public use,
HF gated access via Meta `request access`. Only invoked if I-cd-011
cannot make Gemma 4 31B INT4 work on 4×H100 (unlikely).

## §E — Sign-off declaration

Per the operator's I-cd-006 session AskUserQuestion ("Auto-merge per
Codex") and Codex's APPROVE on the I-cd-005-followup brief (iter 2): the
**Apache 2.0 + Gemma PUP** licensing of `google/gemma-4-31B-it` (and the
derivative INT4 AWQ artifact) is **ACCEPTED** for the Carney one-shot
deployment described in §A. The hard fallback (Llama 3.1 405B + AWQ/GPTQ-
INT4 under Llama 3.1 Community + AUP) is **ACCEPTED** as the safety-net
shape.

If the Carney deployment shape changes materially (different operator
domicile, different MAU regime, EU GPU hosting affecting any
territorially-restricted alternative, output use for non-Gemma LLM
training), this sign-off does NOT extend to the new shape — file a
follow-up.

## §F — Deployment dependencies for I-cd-009 (config wiring)

Much simpler than the prior Llama 4 Maverick sign-off carried:

1. **No HF gated access** required for `google/gemma-4-31B-it` or the
   community AWQ artifact `ebircak/gemma-4-31B-it-4bit-W4A16-AWQ` — both
   public. Removes the legal-name/DOB/org gating step that was required
   for the prior Llama 4 lock.
2. **Apache 2.0 notice preservation**: the Docker image / runtime
   deployment should preserve any LICENSE / NOTICE files from the
   upstream HF artifacts.
3. **vLLM load command**: `--quantization compressed-tensors` (NOT
   `--quantization awq`, per Codex iter-2 P2 operational correction).
