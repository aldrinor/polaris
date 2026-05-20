HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# ⚠ HARD CONSTRAINTS — NOT CODEX-NEGOTIABLE ⚠

These are operator-locked decisions stated verbatim this session. Codex's role
on this followup is **operational verification only** — confirming HF ids,
license terms, quant availability, attribution requirements for the locked
model. Codex must NOT propose alternative models, alternative families, or
"strong alternatives to consider" — any such P1/P2 is out of scope and will
be rejected, not addressed.

- **Generator: DeepSeek V4 Pro 1.6T** — operator-locked, not in scope here.
- **Evaluator: `google/gemma-4-31B-it`** — operator-locked **2026-05-19 this
  session, iter-2 revision after Codex iter-1 web-verified that Gemma 4 400B
  does not exist as a released HF checkpoint** (highest released Gemma 4 is
  31B dense or 26B-A4B MoE). Operator asked "which one is best as evaluator"
  → Claude judgment: **31B dense** (dense beats MoE at comparable size for
  LLM-as-judge reasoning; 31B active > 4B active for careful faithfulness;
  community AWQ + GGUF/NVFP4 quants verified by Codex iter-1 P2; 31B INT4
  ≈ 16 GB on 4×H100=320GB = massive headroom).

The earlier I-cd-005 brief said "Class: ~400B operator-locked" but never
surfaced the specific evaluator MODEL as a HARD CONSTRAINT — that's the
frame error this followup corrects. The operator's "Gemma 4 400B" lock
this session resolves to **Gemma 4 31B-it** (the largest released Gemma 4
dense) once Codex's web verification revealed no 400B variant exists.
Locking Llama 4 Maverick at I-cd-005 (PR #661) was the drift this
supersedes.

# Codex brief review — I-cd-005-followup / GH#637: re-lock evaluator to Gemma 4 400B

## §0 — Iter-2 revisions (responding to iter-1 REQUEST_CHANGES + operator decision)

Iter 1 (this followup): Codex web-verified that **no released Gemma 4 400B
checkpoint exists** — Google's released Gemma 4 family tops out at 31B
dense + 26B-A4B MoE (sources: huggingface.co/collections/google/gemma-4,
huggingface.co/blog/gemma4, huggingface.co/google/gemma-4-31B-it). Codex
correctly stayed in operational-verification mode and flagged this as the
operator-escalation P1 the brief asked for — did NOT propose alternative
models.

Operator decision (this session, after iter-1 escalation): "Which one is
best as evaluator" → Claude judgment: **`google/gemma-4-31B-it` (dense)**.
Locked. Reasoning:
- Dense > MoE at comparable total size for LLM-as-judge careful-reasoning
  tasks (the evaluator is reasoning-bound, not throughput-bound).
- 31B > 26B + 31B-active > 4B-active = more per-token compute on each step
  of the faithfulness adjudication.
- Codex iter-1 P2 confirmed community 4-bit AWQ + GGUF/NVFP4 quants for
  Gemma 4 31B (`ebircak/gemma-4-31B-it-4bit-W4A16-AWQ`); the 26B-A4B quant
  ecosystem is less verified.
- 31B INT4 ≈ 16 GB on 4×H100 = 320GB → massive headroom for KV-cache +
  parallel evaluator instances.

The compounded failures this followup corrects (background only — both
mine):
1. I never surfaced the locked evaluator MODEL as a HARD CONSTRAINT in the
   I-cd-005 brief — only "Class: ~400B." That left Codex free to propose
   any ~400B candidate. Per
   `feedback_operator_locked_decisions_not_codex_consultable_2026_05_15`:
   locked decisions go at the TOP as HARD CONSTRAINTS; this brief now does
   exactly that.
2. I let Codex's iter-3 "newer + most-deployed 2026 MoE 400B" framing pivot
   the I-cd-005 pick to Llama 4 Maverick without weighing (a) the
   Llama 4 Maverick LMArena-tuning quality controversy or (b) the
   operator's original Gemma 4 reference per `docs/carney_delivery_plan_v6_2.md`.
   Per `feedback_be_skeptical_of_codex_2026_05_13`: Codex-as-planning-
   advisor gets filtered through Claude judgment. I did neither.

This followup **supersedes** I-cd-005's Llama 4 Maverick lock with
**`google/gemma-4-31B-it`**. The docs `docs/models/evaluator_pick.md` and
`docs/models/evaluator_license_signoff.md` are rewritten in this PR.

## §A — Operational verification asks (Codex web search authoritative)

Please verify and report ONLY THE FACTS for the locked model
**`google/gemma-4-31B-it`**. **No alternative-model discussion is in
scope. Any P1/P2 proposing a different model gets rejected.**

Most of these were already answered in your iter-1 response — please confirm
or correct in iter-2:

1. **Locked HF id**: `google/gemma-4-31B-it` (instruct-tuned 31B dense)
   confirmed released and publicly visible per your iter-1 P2
   (`https://huggingface.co/google/gemma-4-31B-it`). Confirm. Any FP8 /
   NVFP4 / quantized sibling repos officially published by Google to be
   aware of for I-cd-009 wiring?
2. **License**: per your iter-1 P2 the official model card + Google
   license page state **Apache 2.0** (cleaner than the Llama-Community
   pattern; the older "Gemma Terms" page is legacy). Confirm Apache 2.0
   is the operative license + report any Gemma-4-specific acceptable-use
   policy that overlays it.
3. **INT4 quant on 4×H100 via vLLM** (engine locked I-cd-007, vLLM):
   `ebircak/gemma-4-31B-it-4bit-W4A16-AWQ` was named in your iter-1 P2 —
   confirm it's the right choice (or name the better-maintained
   alternative). 31B INT4 weight residency ≈ 16 GB → fits 4×H100 trivially.
4. **Attribution requirements**: per your iter-1 P2, Apache-style only
   (retain notices, include the license on redistribution, mark modified
   files, NOTICE only if present); **no Gemma-4-specific "Built with
   Gemma" placement requirement** found. Confirm.
5. **HF gating**: per your iter-1 P2, Gemma 4 31B repos are publicly
   visible with no `request access` gate (unlike Llama 4 Maverick). Confirm
   — this is a deployment-step simplification for I-cd-009.
6. **Two-family vs DeepSeek V4 Pro**: confirm
   `openrouter_client.check_family_segregation` treats `google` as a
   family distinct from `deepseek` (it should; just sanity-check the
   prefix list).
7. **NEW**: any concern about Gemma 4 31B's evaluator-role quality vs
   competitors that the operator should know about as we lock? (Codex's
   role is operational verification, not model re-selection — but if
   Gemma 4 31B has a known weakness for LLM-as-judge tasks, surface it
   as a P1 for operator visibility.)

## §B — What this PR ships

- **REWRITE** `docs/models/evaluator_pick.md` — supersedes I-cd-005's Llama 4
  Maverick lock with `google/gemma-4-31B-it` primary; records the
  community AWQ INT4 quant (`ebircak/gemma-4-31B-it-4bit-W4A16-AWQ`) as the
  intended runtime artifact for vLLM on 4×H100; records the I-cd-011
  empirical-verification trigger; records the Llama 3.1 405B + AWQ/GPTQ-INT4
  on vLLM as the model-side proven-deployable hard-fallback (kept from
  I-cd-005 because it remains the most-mature INT4-on-H100 path if Gemma 4
  31B INT4 cannot be made to work on 4×H100 at I-cd-011 — unlikely given the
  16 GB footprint, but documented for completeness).
- **REWRITE** `docs/models/evaluator_license_signoff.md` — supersedes
  I-cd-005's Llama 4 Maverick license sign-off with `google/gemma-4-31B-it`
  Apache 2.0 acceptance for the Carney shape (cleaner license than Llama
  Community — no MAU clause, no Llama-style HF gating, only Apache-style
  attribution); carries the I-cd-006 operator AskUserQuestion "Auto-merge
  per Codex" mode.
- `state/polaris_restart/iteration_trajectory.md` — §8.3.5 log of the
  failure + followup.

**Out of scope (own later issue):**
- Engine wiring with the new model id — I-cd-009 (#624).
- FP4 hardware spike — I-cd-011 (#641); Gemma 4 31B INT4 fits 4×H100
  trivially, so this spike's risk profile for the evaluator drops
  significantly vs the Llama 4 Maverick lock.
- I-cd-008 (GPU topology) is PAUSED on bot/I-cd-008 branch until this
  followup merges. With Gemma 4 31B on Box 2 = 4×H100, the per-token
  compute is much lower than Maverick's 17B-active MoE or 405B-dense, so
  the topology probe's risk profile also relaxes.

## §C — Output schema — return EXACTLY this

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
