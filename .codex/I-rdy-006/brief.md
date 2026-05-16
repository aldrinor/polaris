HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-rdy-006 brief — align model/config to V4 Pro + Gemma 4 31B (#502)

**GH:** #502
**Branch:** `bot/I-rdy-006-model-config-align` (off `polaris` @ `9185035e`)
**This is the brief; a diff follows after APPROVE.**

## Issue

Phase 3.3: purge stale V4 Flash / qwen / GLM / default-provider references from
code and docs; everything points at DeepSeek V4 Pro generator + Gemma 4 31B
evaluator; transparency endpoint matches. Acceptance: zero stale model
references; transparency endpoint shows the locked pair; Codex APPROVE.

## Discovery — two distinct classes of "qwen reference"

**Class A — FALSE model-identity statements** (a doc or a default CLAIMS the
wrong model is the evaluator/generator). These are the real bug:

- `src/polaris_v6/api/transparency.py:~218` — the `evaluator` field fallback is
  hardcoded `qwen/qwen-2.5-72b-instruct`. The live default
  (`openrouter_client.py:298` `PG_EVALUATOR_MODEL`) is `google/gemma-4-31b-it`.
  With `PG_EVALUATOR_MODEL` unset, `/transparency` misreports the evaluator —
  directly fails the "transparency endpoint shows the locked pair" criterion.
- `docs/transparency.md:29` — same stale default `qwen/qwen-2.5-72b-instruct`.
- `docs/runbook.md:154,160,274` — "Evaluator: `qwen/qwen3-8b`",
  `PG_EVALUATOR_MODEL=qwen/qwen3-8b`, "Qwen3-8B is $0.05…" — stale; the
  evaluator is Gemma 4 31B.
- `src/polaris_graph/evaluator/live_qwen_judge.py:5,10-11,126` — docstring
  states "judge is Qwen3-8B" / "generator is DeepSeek V3.2-Exp" — stale; the
  module's own line 4 says it reads `PG_EVALUATOR_MODEL` (= Gemma 4 31B) and
  the generator is V4 Pro per I-gen-003.
- `src/polaris_graph/llm/openrouter_client.py:4,820` — docstring "Single
  gateway to Qwen 3.5 Plus" — stale; it is a generic OpenRouter gateway
  (generator V4 Pro, evaluator Gemma).
- `evaluator_gate.py` header comments (lines 5,17,21) — narrative "Qwen" —
  comment-level.

**Class B — legacy qwen-NAMED identifiers** (NOT false claims — legacy naming):

- `evaluator_gate.py` — dataclass fields `qwen_critical_axes`,
  `qwen_parse_ok`; status value `partial_qwen_advisory`; emitted reason
  strings `qwen_parse_failed`, `qwen_citation_tightness_needs_revision`,
  `qwen_hedging_tone_needs_revision`, `qwen_completeness_needs_revision`,
  `qwen_multi_axis_needs_revision`; constant `HIGH_RISK_QWEN_AXES`; param
  `qwen_result`.
- `live_qwen_judge.py` — the module filename + logger name
  `polaris_graph.live_qwen_judge`.
- The output artifact filename `qwen_judge_output.json`.

## SCOPE PROPOSAL — and the question for Codex

I propose **#502 fixes Class A only** (the false model-identity statements).
Rationale:

- Class A IS the acceptance criterion ("transparency endpoint shows the locked
  pair"; "everything points at … Gemma 4 31B evaluator").
- Class B is a wide-blast-radius identifier rename. The `qwen_*` fields +
  `partial_qwen_advisory` status + reason strings are an EMITTED DATA CONTRACT
  — they flow into `manifest.json`, the `qwen_judge_output.json` artifact,
  downstream rule checks, tests under `tests/polaris_graph/`, and likely the
  web UI. `evaluator_gate.py:68` explicitly calls them a "stable, greppable
  identifier list." Renaming them is a schema/contract change that (a) very
  likely exceeds the 200-LOC cap and (b) is naming hygiene, not a false claim
  — it belongs with the I-naming-* series (#436-444), not Phase 3.3
  model-config alignment.

**Question for Codex:** is **Class A the correct scope for #502**, with Class B
(the `qwen_*` identifier / field / status / filename rename) carved out as a
separate I-naming-style follow-up issue? Or do you require Class B inside #502
— in which case it needs a 200-LOC-split ruling?

Class A is ~25-30 changed lines across 6 files (docs + docstrings + one
fallback-default string) — well under 200 LOC.

## Files I have ALSO checked

- `openrouter_client.py:46` — `OPENROUTER_DEFAULT_MODEL` default
  `qwen/qwen3.5-plus-02-15` is a config DEFAULT VALUE, not a false claim;
  changing it is a behavior change, out of #502 scope. Left as-is; flagged.
- `external_evaluator.py:29-30` — docstring already CORRECT ("PG_EVALUATOR_MODEL
  default google/gemma-4-31b-it … PG_GENERATOR_MODEL default
  deepseek/deepseek-v4-pro"). No change.
- `evaluator/__init__.py:3` — already correct ("DeepSeek V4 Pro generator +
  Gemma 4 31B"). No change.
- `config/settings/models.yaml` — the Gemini AGENT-framework config
  (`src/agents/`), a separate subsystem from the pipeline-A V4 Pro / Gemma
  generator+evaluator. Not a stale reference to the locked pair. Out of #502
  scope (flag if you disagree).

## Acceptance criteria

- `transparency.py` + `docs/transparency.md` evaluator default →
  `google/gemma-4-31b-it` (the locked pair).
- `docs/runbook.md` evaluator references corrected to Gemma 4 31B.
- Stale docstrings in `live_qwen_judge.py`, `openrouter_client.py`,
  `evaluator_gate.py` header corrected.
- No live behavior change beyond the `transparency.py` fallback default.
- Class B (`qwen_*` identifier rename) carved to a follow-up issue, pending
  the Codex scope ruling.
- Codex APPROVE on brief + diff.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
scope_ruling: class_a_only | class_b_required | other
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
