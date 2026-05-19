# I-cd-006 — Claude architect audit

**Issue:** GH#638 — 400B evaluator license sign-off, operator-gated.
**Deliverable:** `docs/models/evaluator_license_signoff.md` — per-license
headline terms + Carney-fit clearance for the I-cd-005 pick set + deployment
dependencies + attribution plan.

## Operator sign-off mode

This session, AskUserQuestion: **"Auto-merge per Codex"** — the operator
explicitly re-classified C-06-style license-acceptance issues as
auto-merge-per-Codex-APPROVE rather than explicit-operator-merge. Codex
APPROVE on the brief (iter 2) + APPROVE on the diff IS the operator's legal
acceptance.

## What this ships

- `docs/models/evaluator_license_signoff.md` (NEW, 122 LOC) — the recorded
  sign-off.

## Codex trajectory

Brief: iter 1 RC (2 P1 — Llama 4 EU-no-grant clause + Hunyuan EU
prohibition, plus 6 P2 license-fact corrections) → iter 2 APPROVE (3 P2
folded into the deliverable doc).

iter 1 was Codex's web-verified deep-read of the actual license texts
(github.com/meta-llama/.../LICENSE + USE_POLICY, HF model cards,
nvidia.com Nemotron PDF, Tencent HF LICENSE.txt). It surfaced:
- Llama 4 AUP §1(a) EU-no-grant — doesn't apply (POLARIS licensee
  Canada-domiciled).
- Hunyuan worldwide-EXCLUDING-EU — hard ineligible if Carney compute
  moves to EU GPU.
- Tulu 3 405B is Llama 3.1 Community License (not AI2 ImpACT as I
  initially assumed).
- HF gated access for Meta models — deployment dep for I-cd-009.
- MAU + Built-with-Llama + non-Llama-LLM-output restrictions — all
  recorded in §B.

## Carney clearance recorded

- Llama 4 Maverick (primary): ACCEPTED.
- Llama 3.1 405B (fallback): ACCEPTED.
- Tulu 3 / Nemotron-4 / Qwen3.5 / MiniMax-M1 / GLM-4.5 / Arcee Trinity /
  ERNIE-4.5-VL: ACCEPTED.
- Hunyuan-Large: CONDITIONAL (eligibility depends on whether Carney compute
  stays outside the EU).

## Risk surface

Doc-only ship; no runtime change. Downstream implementations:
- I-cd-009 (#624) wires the chosen model AFTER (1) Meta HF gated-access
  request completes and (2) the community INT4 quant wrapper-license check
  completes.
- I-cd-022 (#612, /home rebuild) carries the "Built with Llama" UI
  attribution (or sooner if a public demo precedes I-cd-022).
- I-cd-011 (#641, FP4 hardware spike) revisit drops Hunyuan from the
  candidate set if EU GPU is chosen.

## Sign-off declaration in the deliverable

The doc carries an explicit §E sign-off declaration that the licenses are
accepted for the Carney one-shot deployment shape, and that the sign-off
does NOT extend to a materially-different deployment shape (different
domicile, different MAU, different output-use) — those require a
follow-up I-cd-006-followup.
