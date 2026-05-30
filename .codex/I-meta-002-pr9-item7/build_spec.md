# Item-7 build spec — reconcile stale Path-B docs/tests 2-LLM naming -> 4-role (I-meta-002 PR-9/item7) — NO SPEND

Codex-ordered no-spend item 7: update stale Path-B docs/tests that still describe the OLD 2-LLM
architecture ("generator + evaluator", "V4 Pro + Gemma evaluator", "two-family evaluator" as the whole
story) so they reflect the LOCKED 4-role architecture: Generator (deepseek/deepseek-v4-pro, OpenRouter)
+ Mirror (cohere/command-a-plus) + Sentinel (ibm-granite/granite-guardian-4.1-8b) + Judge
(qwen/qwen3.6-35b-a3b), the latter three self-hosted on Vast. Documentation/comment/test-description
reconciliation ONLY — NOT a code-behavior change.

## Locked constraints
- NO SPEND / NO NETWORK. Docs + comments + test docstrings/names only.
- DO NOT change code BEHAVIOR, public symbol names, or config values. Do NOT rename functions/classes
  that are load-bearing (e.g. the legacy two-family evaluator segregation check
  `check_family_segregation` is a REAL invariant per CLAUDE.md §9.1 — keep it; just ensure prose around
  it doesn't imply the 2-LLM stack is the whole verifier story).
- DO NOT touch frozen claim_audit_scorer.py or the runtime lock. Do NOT promote the lock.
- The two-family generator/evaluator INVARIANT (generator and evaluator from different lineages) STILL
  HOLDS and must NOT be deleted — the 4 roles still respect family diversity. Only fix prose that
  WRONGLY presents "generator + single Gemma/400B evaluator" as the current/whole architecture.
- Be CONSERVATIVE: when unsure whether a reference is stale-and-wrong vs. a still-correct invariant,
  LEAVE IT and note it for the diff-gate rather than over-editing.

## Step 1 — identify (grep, report the blast radius)
Grep docs/ + .codex/ (non-frozen) + tests/ + src/polaris_graph comments for stale 2-LLM framing:
patterns like "Gemma 4 31B evaluator", "V4 Pro + Gemma", "two-LLM", "generator and evaluator" (as the
whole pipeline), "400B evaluator" presented as the live evaluator, "evaluator" where it should be
"Mirror/Sentinel/Judge". Produce a list of file:line candidates and classify each: (a) clearly stale →
fix; (b) still-correct invariant (two-family segregation) → leave; (c) historical/dated record (e.g. a
session log, an old audit doc, a memory) → leave (do not rewrite history).

## Step 2 — reconcile (the clearly-stale ones)
Update the (a) set to describe the 4-role architecture (Generator/Mirror/Sentinel/Judge), citing the
runtime lock config/architecture/polaris_runtime_lock.yaml as the source of truth. Keep edits minimal
and factual. Prefer updating: docs that describe the CURRENT pipeline, test docstrings/test names that
assert 4-role behavior but are described as 2-LLM, and misleading code comments. Do NOT rewrite
historical session logs / dated audit records / memory files.

## Step 3 — verify (no behavior change)
python -m pytest tests/roles tests/dr_benchmark tests/architecture -q  (must still pass, same count)
python -m scripts.architecture.verify_lock --consistency  (exit 0)
python -m scripts.dr_benchmark.gate_a_dry_run  (OVERALL PASS)
Confirm: zero code-behavior changes (only docs/comments/test-descriptions); test count unchanged
(no tests added/removed unless a test's DESCRIPTION text changed); no frozen-file or lock drift.

Report: the candidate list with classifications, the files actually edited (absolute paths), what was
left and why, and the verify results. Do NOT commit. Do NOT run codex.
