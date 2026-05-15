# Codex consult — sequencing decision: I-gen-003 (#495) vs I-rdy-006 (#502)

## HARD CONSTRAINTS — operator-locked, NOT for you to reopen

These are operator-locked decisions. Do not question, relax, or propose
alternatives. Your job is ONLY the sequencing question in section 3.

1. **DeepSeek V4 Pro is the generator.** Locked — stated 6+ times by the
   operator; named in the GPU procurement spec, `docs/transparency.md`,
   `docs/carney_demo_runbook.md`, and the whole sovereignty narrative.
2. **Gemma 4 31B is the evaluator.** Locked.
3. **Canadian sovereign GPU hosting.** Locked.

Do NOT propose "use V3.2-Exp instead", "drop V4 Pro", or any model
substitution as a path. V4 Pro working is a requirement, not an option.

## This is a one-shot planning consult

Give your complete analysis in ONE response. No drip-feeding across rounds.
Front-load every consideration. Same quality bar as a full review.

## 1. Context

POLARIS is a clinical-grade sovereign research pipeline being prepared for a
demo to the office of the Canadian Prime Minister (Mark Carney). Two open
GitHub issues are candidates for the next unit of work; we must decide the
order. The operator explicitly asked for a Codex cross-check to ensure the
higher-quality choice.

## 2. The two issues — grounded current state (verified via gh + git)

**I-gen-003 (#495) — OPEN, in_progress.**
"Make DeepSeek V4 Pro work as the multi_section generator (CoT re-prompt +
retry handler)."
- Problem: V4 Pro is currently parked. `src/polaris_graph/llm/openrouter_client.py`
  (~lines 255-271, I-bug-091) reverted `PG_GENERATOR_MODEL` from V4 Pro to
  `deepseek-v3.2-exp` because V4 Pro emits CoT-style planning that lacks the
  `[#ev:<evidence_id>:start-end]` provenance tokens that `strict_verify`
  requires, and exhausts max_tokens mid-planning, triggering fail-loud abort
  (I-bug-089).
- Acceptance: the multi_section generator detects the CoT-without-tokens and
  budget-exhausted-mid-planning failure modes, re-prompts V4 Pro with an
  explicit "output cited prose directly, every sentence ends with [#ev:...],
  no planning preamble" instruction + bounded retry; audits existing
  reasoning-first infra (I-bug-088 response-shape recovery, I-bug-089
  token-budget).
- Code state: written on a local branch `bot/I-gen-003-v4pro-cot-handler` but
  NEVER landed. Its commits were tangled into PR #517, which was CLOSED and
  recut into other PRs; I-gen-003's own work never got a standalone PR
  (`gh pr list --head bot/I-gen-003-v4pro-cot-handler` returns empty). So
  I-gen-003 has unmerged WIP commits and is functionally not in `polaris`.
- NET: today, the actual running generator is `deepseek-v3.2-exp`, NOT V4 Pro.

**I-rdy-006 (#502) — OPEN.**
"Phase 3.3: align model/config to V4 Pro + Gemma 4 31B."
- Body verbatim: "Purge stale V4 Flash / qwen / GLM / default-provider
  references from code and docs. Everything points at DeepSeek V4 Pro
  generator + Gemma 4 31B evaluator. Transparency endpoint matches.
  Acceptance: zero stale model references; transparency endpoint shows the
  locked pair; Codex APPROVE. Depends on: I-rdy-003."
- I-rdy-003 is done (in open PR #521, not yet merged).
- NET: I-rdy-006 is a config/docs NAMING-alignment task — it makes the
  codebase and the `/transparency` endpoint DECLARE V4 Pro + Gemma
  everywhere. It does NOT itself make V4 Pro functional.

## 3. The decision

- Option A — I-gen-003 first, then I-rdy-006.
- Option B — I-rdy-006 first, then I-gen-003.

## 4. The quality concern I (Claude) see — verify or refute

If I-rdy-006 lands before I-gen-003: the `/transparency` endpoint and docs
will assert "generator = DeepSeek V4 Pro," but the system will actually be
running `deepseek-v3.2-exp` (the I-bug-091 fallback), because I-gen-003 — the
issue that makes V4 Pro functional — has not landed. For a demo to the PM's
office, a transparency endpoint declaring a model the system is not actually
running is a FALSE claim — a LAW II "no fake working" violation and a
clinical-grade honesty failure. That argues decisively for A.

Counter-considerations to weigh:
- I-rdy-006 "depends on I-rdy-003" (not I-gen-003) per its own body — so there
  is no *code* dependency forcing A.
- The 5 I-rdy PRs (#518/#519/#521/#522/#435) are open and not yet merged;
  I-rdy-006's stated dependency I-rdy-003 is in #521.
- Is there a defensible Option C — do I-rdy-006 first but have it disclose the
  interim honestly (e.g. transparency endpoint shows "generator: V4 Pro —
  activation pending I-gen-003; interim fallback V3.2-Exp")? Assess whether
  that is acceptable, or whether it just smears the honesty problem.

## 5. Your task

Pick A, B, or a specified C, for the HIGHER-QUALITY outcome given the
clinical-grade PM-demo context. Justify specifically against the
transparency-honesty concern. If you think the section 4 reasoning is wrong,
say why and where.

## 6. Output schema (return exactly this)

```yaml
recommendation: A | B | C
reasoning: <text>
transparency_honesty_verdict: <does B or C create a false transparency claim? yes/no + why>
risks_of_chosen_path: [...]
```
