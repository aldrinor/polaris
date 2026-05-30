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

===== ITER-2 NOTE =====
Iter-1 P1 FIXED: src/polaris_graph/__init__.py docstring no longer claims check_family_segregation enforces N-way 4-role segregation. It now distinguishes the legacy PAIRWISE generator/evaluator check (check_family_segregation, two-family invariant) from the 4-role ALL-DISTINCT check validate_role_families (openrouter_client.py:532, policy='all_distinct'). Verify the corrected docstring is accurate and no other doc repeats the old N-way-via-check_family_segregation falsehood.

diff --git a/docs/file_directory.md b/docs/file_directory.md
index 6f5bb8eb..c7a2f1de 100644
--- a/docs/file_directory.md
+++ b/docs/file_directory.md
@@ -247,10 +247,13 @@ point to non-existent paths / deprecated concepts. Treat as stale:
 - `scripts/final_audit.py`, `scripts/run_ragas_v3.py` — referenced
   by `scripts/full_cycle.py` (pipeline C). Do not exist; pipeline C
   is broken until these are either restored or removed.
-- "Kimi K2.5 1T" — historical generator. The locked generator/evaluator
-  for the Carney demo is DeepSeek V4 Pro + Gemma 4 31B (see
-  `docs/polaris_locked_scope.md` §1); earlier pipelines used DeepSeek
-  V3.2-Exp + Qwen3-8B.
+- "Kimi K2.5 1T" — historical generator. The locked architecture for the
+  Carney demo is the 4-role stack in
+  `config/architecture/polaris_runtime_lock.yaml` (I-meta-001 #933):
+  Generator (DeepSeek V4 Pro) + Mirror (Cohere Command A+) + Sentinel (IBM
+  Granite Guardian 4.1 8B) + Judge (Qwen3.6-35B-A3B). The earlier 2-LLM
+  framing (DeepSeek V4 Pro generator + Gemma 4 31B evaluator) is superseded;
+  earlier pipelines used DeepSeek V3.2-Exp + Qwen3-8B.
 - "175 vectors exactly" — old invariant from P0-P12. Not applicable
   to any currently-active pipeline.
 
diff --git a/src/polaris_graph/__init__.py b/src/polaris_graph/__init__.py
index 95779c85..2f8a7f29 100644
--- a/src/polaris_graph/__init__.py
+++ b/src/polaris_graph/__init__.py
@@ -1,10 +1,17 @@
 """
 polaris graph — clean-room research pipeline.
 
-Uses DeepSeek V4 Pro generator + Gemma 4 31B-it evaluator via OpenRouter
-(Carney demo lock per I-cd-009 / GH#624). Two-family segregation enforced
-by `openrouter_client.check_family_segregation` returning ('deepseek',
-'gemma'). Reuses battle-tested search/fetch infrastructure from src/tools/.
+Runs the LOCKED 4-role architecture per
+``config/architecture/polaris_runtime_lock.yaml`` (I-meta-001 #933):
+Generator (DeepSeek V4 Pro, OpenRouter) + Mirror (Cohere Command A+) +
+Sentinel (IBM Granite Guardian 4.1 8B) + Judge (Qwen3.6-35B-A3B), plus the
+deterministic python validators and the §-1.1 Codex audit layer. Family
+segregation is enforced two ways: the legacy pairwise generator/evaluator
+check ``openrouter_client.check_family_segregation`` (the two-family
+invariant of CLAUDE.md §9.1), and the 4-role all-distinct-lineage check
+``validate_role_families`` (Mirror, Sentinel, and Judge must each be a
+distinct family from the Generator and from each other).
+Reuses battle-tested search/fetch infrastructure from src/tools/.
 """
 
 __all__ = [
diff --git a/src/polaris_graph/evaluator/__init__.py b/src/polaris_graph/evaluator/__init__.py
index ab159059..56baa4b4 100644
--- a/src/polaris_graph/evaluator/__init__.py
+++ b/src/polaris_graph/evaluator/__init__.py
@@ -1,7 +1,13 @@
 """POLARIS honest-rebuild external evaluator package (Phase 5).
 
-Non-same-family evaluator (DeepSeek V4 Pro generator + Gemma 4 31B
-evaluator by default; both swappable via PG_GENERATOR_MODEL /
-PG_EVALUATOR_MODEL env vars) plus rule-based PRISMA-trAIce compliance
-checks.
+Non-same-family evaluator: the generator (DeepSeek V4 Pro) and this
+evaluator role MUST be from distinct training lineages (CLAUDE.md §9.1
+two-family invariant). Under the LOCKED 4-role architecture
+(``config/architecture/polaris_runtime_lock.yaml``, I-meta-001 #933) the
+evaluator role maps to Mirror (Cohere Command A+); the legacy
+``PG_EVALUATOR_MODEL`` knob is compat-mapped to ``PG_MIRROR_MODEL`` per the
+lock's ``legacy_compat`` block. Both the generator and evaluator models are
+swappable via ``PG_GENERATOR_MODEL`` / ``PG_MIRROR_MODEL``
+(``PG_EVALUATOR_MODEL`` for back-compat) env vars, plus rule-based
+PRISMA-trAIce compliance checks.
 """
diff --git a/src/polaris_graph/evaluator/live_judge.py b/src/polaris_graph/evaluator/live_judge.py
index abe23dfb..33942f05 100644
--- a/src/polaris_graph/evaluator/live_judge.py
+++ b/src/polaris_graph/evaluator/live_judge.py
@@ -2,9 +2,13 @@
 Live judge — HONEST-REBUILD Phase 5 live wiring.
 
 Calls the REAL evaluator model via OpenRouter (model read from
-PG_EVALUATOR_MODEL at runtime; default Gemma 4 31B as of 2026-05-08
-per I-bug-087, previously Qwen3-8B per HONEST-REBUILD Phase 1c) to
-produce per-axis structured verdicts on a completed report.
+PG_EVALUATOR_MODEL at runtime). Under the LOCKED 4-role architecture
+(config/architecture/polaris_runtime_lock.yaml, I-meta-001 #933) the legacy
+PG_EVALUATOR_MODEL knob resolves to the Mirror role via the lock's
+legacy_compat map (PG_EVALUATOR_MODEL -> PG_MIRROR_MODEL) when unset.
+Historical defaults: Gemma 4 31B as of 2026-05-08 per I-bug-087, previously
+Qwen3-8B per HONEST-REBUILD Phase 1c. Produces per-axis structured verdicts
+on a completed report.
 
 This is the NON-SAME-FAMILY judge: the judge model must be from a
 different training family than the generator. `check_family_segregation()`
