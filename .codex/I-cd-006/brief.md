HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

DO NOT explore the repository. Everything you need is in this brief.

# Codex brief review — I-cd-006 / GH#638: 400B evaluator license sign-off

Sign-off rule: operator answered AskUserQuestion this session — **"Auto-merge
per Codex"**. Codex APPROVE on this brief + APPROVE on the diff IS the
operator's legal acceptance. Auto-merge flow same as the 6 prior I-cd-NNN.

## §0 — Iter-2 revisions (responding to iter-1 REQUEST_CHANGES)

Iter 1: 2 P1 + 6 P2. All addressed:
- **P1 (Llama 4 EU-no-grant clause)** — Llama 4 AUP §1(a) does not grant
  rights to EU-domiciled licensees. **POLARIS / Carney operator is
  Canada-domiciled** (OVH BHS5 Québec, operator email orchunyin@gmail.com per
  project memory) → the clause does NOT apply, even if compute is later
  rehosted to EU GPU per the 2026-05-18 procurement relaxation (domicile is
  about the LICENSEE legal entity, not the compute location). Llama 4 Maverick
  remains usable. Documented in §B + §C.
- **P1 (Hunyuan EU prohibition)** — Tencent Hunyuan-Large is expressly limited
  to "worldwide territory EXCLUDING the EU" and prohibits use, reproduction,
  modification, distribution, or display of works/outputs OUTSIDE that
  territory. For a Canada-domiciled operator NOT on EU GPU, Hunyuan is OK; for
  an EU-GPU-hosted deployment, Hunyuan is HARD INELIGIBLE. Recorded in §B as
  the strictest territorial constraint of the candidate set.
- **P2 (Llama 4 + 3.1 MAU = 700M, attribution requirements)** — folded into
  §B. "Built with Llama" required prominently on related website / UI / blog /
  about / product docs; NOTICE text required when distributing copies.
- **P2 (Llama 4 vs 3.1 tightening)** — AUP adds multimodal EU no-grant,
  safety-circumvention prohibition, biological/chemical-weapons legal
  references. Recorded in §B's Llama 4 row.
- **P2 (Tulu 3 405B is Llama 3.1 Community, not AI2 ImpACT)** — corrected
  in §B; HF model card says `License: llama3.1`.
- **P2 (Nemotron-4: no Carney failure)** — confirmed in §B; commercial +
  derivatives OK; redistribution requires NOTICE retention.
- **P2 (HF gated-model request/acceptance for Llama 4 + Llama 3.1)** —
  recorded in §C as a deployment-step dependency for I-cd-009: Meta gates
  Llama 4 access at HF (`request access` with full legal name, DOB, full
  organization name); Llama 3.1 fallback is also gated. Community INT4 quant
  repos need separate wrapper-license/notice check.
- **P2 (Hunyuan non-EU also has 100M MAU, no-output-to-improve-other-LLM,
  downstream restriction notice, public machine-generated disclosure)** —
  folded into §B's Hunyuan row; Canada-only Carney clears these IF documented.

## §A — Operator-locked context

- **Primary evaluator pick (I-cd-005, merged `c5e114e2`):**
  `meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8`.
- **Hard fallback:** `meta-llama/Llama-3.1-405B-Instruct`.
- **6 alternatives** for I-cd-011 revisit.
- **Carney deployment shape:** single-org one-shot delivery; operator
  Canada-domiciled (verified above); compute Canada (current OVH BHS5
  deployment) or EU (per 2026-05-18 GPU procurement relaxation); open-weight
  self-hosted; policy/research use-case (non-military, non-targeting-
  individuals, non-CSAM, non-prohibited).
- **MAU scale:** comfortably under any 700M (Llama) or 100M (Hunyuan)
  threshold — single Government-of-Canada Office user + the demo + the
  Codex-vetted pipeline.

## §B — License headline (Codex iter-1 web-verified, folded in)

| Model | License | Key terms after iter-1 verification |
|---|---|---|
| `Llama-4-Maverick-17B-128E-Instruct-FP8` (primary) | Llama 4 Community + AUP | 700M MAU threshold; "Built with Llama" prominent attribution on related website/UI/blog/about/product docs; NOTICE text on distributing copies; multimodal **EU-no-grant** to EU-domiciled licensees (POLARIS is Canada-domiciled → does not apply); safety-circumvention prohibition; bio/chem weapons references; **HF gated — `request access` with legal name + DOB + full organization**. Source: github.com/meta-llama/llama-models LICENSE + USE_POLICY. |
| `Llama-3.1-405B-Instruct` (hard fallback) | Llama 3.1 Community + AUP | 700M MAU; same Built-with-Llama + NOTICE; AUP without the Llama-4 multimodal-EU clause; **HF gated**. Source: github.com/meta-llama/llama-models. |
| `allenai/Llama-3.1-Tulu-3-405B` | **Llama 3.1 Community** (corrected — HF card says `license: llama3.1`; AI2 ImpACT is a separate post-training-data declaration, not the governing model license) | Inherits Llama 3.1 700M MAU + AUP + attribution + HF gating. Source: HF model card. |
| `nvidia/Nemotron-4-340B-Instruct` | NVIDIA Open Model License (2025-12-12) | Commercial + derivatives OK; outputs not claimed by NVIDIA; redistribution requires license copy + retained notices + NOTICE attribution if present; no Carney-failure clause. Source: NVIDIA-Nemotron-Open-Model-License-12-12-25.pdf. |
| `Qwen/Qwen3.5-397B-A17B-FP8` | Apache 2.0 | Most permissive; no MAU; standard Apache attribution. |
| `MiniMaxAI/MiniMax-M1-80k-hf` | Apache 2.0 | Most permissive. |
| `zai-org/GLM-4.5` | MIT | Most permissive. |
| `arcee-ai/Trinity-Large-Thinking` | Apache 2.0 | Most permissive. |
| `tencent/Tencent-Hunyuan-Large` | Tencent License | **Worldwide EXCLUDING EU** (hard territorial limit; EU-GPU-hosted deployment is INELIGIBLE); 100M MAU; no-output-to-improve-other-LLM clause; downstream restriction notice; public machine-generated disclosure. Canada-domiciled, Canada-or-non-EU-GPU clears all of these IF documented. Source: HF LICENSE.txt. |
| `baidu/ERNIE-4.5-VL-424B-A47B-PT` | Apache 2.0 | Most permissive. |

## §C — Carney deployment fit

- **Primary (Llama 4 Maverick) — USABLE.** Canada-domiciled operator clears
  the multimodal EU-no-grant clause; Carney MAU well under 700M; non-military
  policy/research use-case clears the AUP enumerated prohibitions; "Built with
  Llama" attribution will be added to the demo UI footer and
  `docs/transparency.md`.
- **Fallback (Llama 3.1 405B) — USABLE.** Same MAU + attribution; lighter AUP
  than Llama 4.
- **Hunyuan-Large — ELIGIBILITY CONDITIONAL on GPU location.** If the
  final GPU is Canadian (OVH BHS5 current) Hunyuan is in-scope; if the
  final GPU is EU (post-2026-05-18 relaxation), Hunyuan is HARD INELIGIBLE
  (worldwide-excluding-EU territorial bar) and must be removed from the
  I-cd-011 candidate set in that case.
- **All other alternatives** (Qwen3.5 / MiniMax-M1 / GLM-4.5 / Arcee Trinity /
  ERNIE-4.5-VL / Nemotron / Tulu 3) — no Carney-failure clauses.

**Deployment-step dependencies for I-cd-009 (config wiring):**
1. Meta Llama 4 Maverick HF `request access` — full legal name, DOB, full
   organization name. Required BEFORE pulling weights.
2. Meta Llama 3.1 405B (fallback) HF `request access` — same gating.
3. Community INT4 quant repo (the specific Maverick or 405B AWQ/GPTQ quant
   chosen at I-cd-011) — separate wrapper-license + NOTICE check.

**Attribution implementation plan:**
- `docs/transparency.md` (new or updated) — names Llama 4 Maverick (or 3.1
  405B fallback) as the evaluator; "Built with Llama" sentence.
- Demo UI footer — "Built with Llama" string visible on the production
  `polarisresearch.ca/` pages (lands at I-cd-022's home rebuild OR sooner).
- NOTICE files alongside any redistribution (none planned for the Carney
  one-shot; if the handover bundle ships model weights, attach NOTICE).

## §D — Sign-off rule (operator's session re-classification)

Operator answered AskUserQuestion: **"Auto-merge per Codex (Recommended)"**.
Codex APPROVE on this brief + APPROVE on the diff IS the operator's license
acceptance for the primary, fallback, and all 8 alternatives' headline terms
as recorded. Same auto-merge flow as the 6 prior I-cd-NNN issues.

## §E — What this PR ships

Only `docs/models/evaluator_license_signoff.md` (the per-license summary
+ Carney-fit affirmations + deployment-step dependencies for I-cd-009 +
attribution implementation plan) + the §8.3.5 trajectory log.

Out of scope: config wiring (I-cd-009), FP4 hardware spike (I-cd-011),
engine bakeoff (I-cd-007), per-route demo-UI updates (I-cd-022+).

## §F — Questions for Codex

1. Are the Llama 4 + Llama 3.1 AUP headline summaries in §B accurate as
   recorded, after iter-1 corrections?
2. Hunyuan: the "Canada-domiciled, Canada-or-non-EU-GPU clears all 5
   non-EU-territory clauses IF documented" claim — is that the right
   formulation, or are there clauses I am still missing?
3. Tulu 3 license correction (Llama 3.1 Community, not AI2 ImpACT) — confirm?
4. Deployment dependencies for I-cd-009 in §C — anything else (e.g. specific
   community INT4 quant repos that require their own click-through)?
5. Attribution implementation — is "Built with Llama" in `docs/transparency.md`
   + the demo UI footer sufficient for Meta's "prominent" requirement, or are
   there more-specific placement/text requirements?
6. Any further license-acceptance step missing?

## §G — Output schema — return EXACTLY this

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
