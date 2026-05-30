HARD ITERATION CAP: 5 per document. This is iter 1 of the item-7 DIFF gate.
- Front-load ALL real findings; reserve P0/P1 for real risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```

# Codex DIFF-gate — I-meta-002 PR-9/item-7: reconcile stale 2-LLM docs/comments to 4-role (DOCS-ONLY)

Codex-ordered no-spend item 7. This is a DOCSTRING/COMMENT/DOC-PROSE reconciliation ONLY — it updates
stale text that described the OLD 2-LLM stack ("DeepSeek V4 Pro + Gemma 4 31B evaluator") to the LOCKED
4-role architecture (Generator deepseek + Mirror cohere + Sentinel ibm-granite + Judge qwen), citing
config/architecture/polaris_runtime_lock.yaml. NO code/behavior/symbol/value change. NO SPEND.

## What to verify
- The 4 edited files change ONLY docstrings/comments/doc prose — confirm via the diff there is NO code,
  symbol, or value change (the build reported +33/-15 across 4 files).
- The two-family generator/evaluator INVARIANT is NOT deleted or weakened anywhere (it still holds; the
  4 roles respect family diversity). The edits must not claim the segregation check is gone.
- NO pinned canonical file was edited (architecture.md, carney_delivery_plan_v6_2.md,
  agent_architecture.md, polaris_pipeline_canonical.md, the runtime lock, etc. were correctly LEFT —
  editing a pinned file would trip the §3.1 step-0 HARD STOP). docs/file_directory.md is non-pinned.
- NO historical/dated record was rewritten (session logs, dated audit docs, memory, .codex verdicts,
  carney_handover deliverables left as-is).
- The lock was NOT promoted (status stays codex_approved_pending_operator_signature).

## Conservatism notes the build surfaced (confirm these were the right calls)
- entailment_judge.py:28 "Gemma 4 31B by default" LEFT — it's a REAL present default for the separate
  PG_ENTAILMENT_MODEL knob (_DEFAULT_ENTAILMENT_MODEL = google/gemma-4-31b-it), never remapped by the
  lock; rewording would assert a false claim.
- carney_demo_runbook.md LEFT — dated deploy-state snapshot; the deployed VM code is ≥4 days stale and
  may genuinely still run the 2-LLM stack, so editing would assert an untraced runtime fact.
- Class-b two-family-invariant references LEFT (not expanded to N-way) to avoid over-edit.

## SMOKE (build agent, this session)
- pytest tests/roles tests/dr_benchmark tests/architecture -q -> 394 passed (no tests added/removed).
- verify_lock --consistency -> exit 0 (code defaults match lock). gate_a_dry_run -> OVERALL PASS.
- imports OK; no pinned/frozen file touched; lock not promoted.

## Edited files: src/polaris_graph/__init__.py, src/polaris_graph/evaluator/__init__.py,
## src/polaris_graph/evaluator/live_judge.py, docs/file_directory.md

## DIFF (follows)
