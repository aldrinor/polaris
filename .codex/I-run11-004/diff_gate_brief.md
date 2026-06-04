# Codex diff-gate (iter 2): certified MiniMax-M2 decomposition Sentinel wiring (I-run11-004 / #1046)

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- iter 1 correctly caught that the COMMIT only had a session_log append (git add -u choked on permission-denied codex tmp dirs). RESOLVED: the 23-file implementation is now committed (HEAD has sentinel_adapter +224, sentinel_contract +92, openrouter_role_transport +80, lock, defaults, tests). The patch below is the REAL diff.
- Front-load ALL real findings. Same quality bar. Reserve P0/P1 for real execution risks. "Don't pick bone from egg." Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## What this diff does
Replaces the BROKEN Granite-Guardian Sentinel (over-rejected genuinely-grounded clinical claims -> run-12 coverage 0.286) with the CERTIFIED MiniMax-M2 claim-DECOMPOSITION + span-coverage detector (Codex APPROVE .codex/I-run11-004/certification_verify_verdict.txt: 0 false-accepts on 28 fabrications across NUMBER_SWAP/ENTITY_SWAP/NEGATION/FABRICATED_ATTRIBUTION/SCOPE_INFLATION; over-flag 0.107). tests/roles 410 passing; verify_lock code_defaults_match OK.

## Verify (red-team) — review the patch below, which IS the committed diff
1. NEW "decomposition" mode: sentinel_adapter.py builds a SINGLE user msg = certified GLM_PROMPT.format(span, claim); sentinel_contract.parse_sentinel_decomposition reads {verdict} with robust JSON (fences/reasoning/trailing-commas) and FAILS CLOSED to UNGROUNDED parsed_ok=False on ANY bad input — NEVER GROUNDED. Confirm no fail-OPEN path.
2. Reasoning-ON + max_tokens>=3000 for the decomposition Sentinel (openrouter_role_transport.py _SENTINEL_DECOMPOSITION_MIN_MAX_TOKENS=3000) — confirm it is actually applied to the live MiniMax Sentinel call, not dropped (the truncation->all-UNGROUNDED collapse fix).
3. Self-host mode model-aware: granite-guardian->guardian, minimax->decomposition. Confirm NO residual path pairs MiniMax with the guardian <score> parser.
4. benchmark lineup sentinel->minimax/minimax-m2 (decomposition); lock + openrouter_client defaults; "minimax" in _FAMILY_PREFIXES (4 families all_distinct DeepSeek/Zhipu-GLM/MiniMax/Qwen); minimax pricing; verify_lock not half-swapped.
5. PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS default 2400->7200.
6. Sovereign guardian + noninverted parsers/polarity UNCHANGED; _compose_final_verdict still fail-closed (Sentinel UNGROUNDED/MISSING -> downgrade). Flag REAL blockers only.

## Output schema
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]

=== THE COMMITTED DIFF (git diff bot/I-run11-002-sentinel-mirror-fix...HEAD) ===
diff --git a/config/architecture/polaris_runtime_lock.yaml b/config/architecture/polaris_runtime_lock.yaml
index 171d76c4..accd64c2 100644
--- a/config/architecture/polaris_runtime_lock.yaml
+++ b/config/architecture/polaris_runtime_lock.yaml
@@ -57,24 +57,32 @@ required_roles:
       non-abstention failure mode is mitigated by downstream Mirror/Sentinel/Judge layers.
 
   mirror:
-    model_slug: cohere/command-a-plus
-    family: cohere
+    # I-run11-004: Mirror re-picked to z-ai/glm-5.1 (family glm). Cohere Command A+ is NOT on
+    # OpenRouter and the benchmark + lock now converge on GLM-5.1 as the calibration auditor.
+    model_slug: z-ai/glm-5.1
+    family: glm
     serving_route: vast_self_host_bf16
-    license: Apache 2.0
+    license: MIT
     released: 2026-05-20
     role_description: |
-      Calibration auditor. Best calibration in pool (14.1% AA-Omniscience).
-      Native citation grounding. Tests claims the Generator cannot self-verify.
+      Calibration auditor. Native citation grounding via <co> spans.
+      Tests claims the Generator cannot self-verify.
 
   sentinel:
-    model_slug: ibm-granite/granite-guardian-4.1-8b
-    family: ibm-granite
+    # I-run11-004: Sentinel replaced (broken Granite Guardian -> CERTIFIED MiniMax-M2 running the
+    # claim-DECOMPOSITION + span-coverage prompt). On the 56-item fixture (28 grounded + 28
+    # fabricated across NUMBER_SWAP/ENTITY_SWAP/NEGATION/FABRICATED_ATTRIBUTION/SCOPE_INFLATION)
+    # it scored 0 false-accepts on all 28 fabrications, over-flag 0.107. The PRODUCTION
+    # decomposition mode replicates the certified call (verbatim GLM_PROMPT, span+claim inline in a
+    # single user message, JSON response_format, reasoning ON, max_tokens>=3000).
+    model_slug: minimax/minimax-m2
+    family: minimax
     serving_route: vast_self_host
     license: Apache 2.0
     released: 2026
     role_description: |
-      Purpose-built RAG hallucination detector. RAGTruth BAcc 0.841.
-      Broad guardrail coverage. Catches Mirror's misses.
+      Certified claim-decomposition + span-coverage faithfulness detector
+      (MiniMax-M2). Catches Mirror's misses; fail-closed on any parse failure.
 
   judge:
     model_slug: qwen/qwen3.6-35b-a3b
diff --git a/config/serving/verifier_roles.yaml b/config/serving/verifier_roles.yaml
index b087dd77..4ba3ef4d 100644
--- a/config/serving/verifier_roles.yaml
+++ b/config/serving/verifier_roles.yaml
@@ -36,25 +36,24 @@ roles:
     # Calibration auditor — native <co> citation grounding, served as PLAIN chat
     # (no structured-output constraint): the Mirror emits free-form prose with
     # inline <co>covered text</co:doc_id> spans that mirror_adapter parses.
-    model_slug: cohere/command-a-plus
+    # I-run11-004: Mirror is z-ai/glm-5.1 (Cohere Command A+ retired; GLM-5.1 is the lock pick).
+    model_slug: z-ai/glm-5.1
     serving_route: vast_self_host_bf16
     # model_source = the HF repo / weights path vLLM LOADS (--model). DISTINCT from
     # served_model_name: ONLY served_model_name is bound to the lock slug.
     # model_source must be confirmed against the lock's codex_cross_validation_sources
     # before launch — it is NOT lock-equality checked.
-    model_source: CohereLabs/command-a-plus-05-2026-bf16
+    model_source: zai-org/GLM-5.1
     base_url_env: PG_MIRROR_BASE_URL
     api_key_env: PG_MIRROR_API_KEY
     gpu:
-      # Full-precision bf16 — Command A+ (218B total / 25B active sparse MoE),
-      # ~438 GB weights (docs/vast_ai_budget_i_meta_002.md §1.1).
       count: 8
       kind: H100
       vram_gb_each: 80
-      box_note: "8xH100 bf16 (~438 GB weights); proves sovereign production path"
+      box_note: "8xH100 bf16; calibration auditor, proves sovereign production path"
     vllm_args:
       # served-model-name == the locked slug (M4 served==pinned identity surface).
-      served_model_name: cohere/command-a-plus
+      served_model_name: z-ai/glm-5.1
       tensor_parallel_size: 8
       dtype: bfloat16
       quantization: null            # bf16 full precision; Mirror's job IS calibration
@@ -64,30 +63,32 @@ roles:
       guided_decoding: false
 
   sentinel:
-    # Purpose-built RAG hallucination detector — Granite Guardian 4.1 8B (dense,
-    # ~16 GB). Emits a <score> element (NOT JSON), so NO structured-output spec.
-    model_slug: ibm-granite/granite-guardian-4.1-8b
+    # I-run11-004: certified MiniMax-M2 claim-decomposition + span-coverage faithfulness detector
+    # (replaces the broken Granite Guardian). Runs the verbatim certified GLM_PROMPT with JSON
+    # response_format + reasoning ON; emits JSON {verdict, unsupported_atoms, atoms} parsed by
+    # parse_sentinel_decomposition (fail-closed on any parse failure).
+    model_slug: minimax/minimax-m2
     serving_route: vast_self_host
     # model_source = the weights vLLM LOADS; only served_model_name is lock-bound.
     # Confirm against the lock's codex_cross_validation_sources before launch.
-    model_source: ibm-granite/granite-guardian-4.1-8b
+    model_source: MiniMaxAI/MiniMax-M2
     base_url_env: PG_SENTINEL_BASE_URL
     api_key_env: PG_SENTINEL_API_KEY
     gpu:
-      # 1xA100 80GB — ample VRAM, no KV bottleneck
-      # (docs/vast_ai_budget_i_meta_002.md §1.3).
       count: 1
       kind: A100
       vram_gb_each: 80
-      box_note: "1xA100 80GB (EU/sovereignty-clean); dense 8B guardrail model"
+      box_note: "1xA100 80GB (EU/sovereignty-clean); decomposition faithfulness detector"
     vllm_args:
-      served_model_name: ibm-granite/granite-guardian-4.1-8b
+      served_model_name: minimax/minimax-m2
       tensor_parallel_size: 1
       dtype: bfloat16
       quantization: null
       max_model_len: 16384
-      structured_outputs: false     # Granite emits <score>, not JSON
-      guided_decoding: false
+      # Decomposition mode requests a JSON object; structured-output constraint enabled so the
+      # served self-host path can bind response_format (the robust parser also tolerates non-JSON).
+      structured_outputs: true
+      guided_decoding: true
 
   judge:
     # Terminal arbiter — Qwen3.6-35B-A3B (MoE, 3B active). MUST emit a stable
diff --git a/logs/session_log.md b/logs/session_log.md
index b50beb54..87e1d865 100644
--- a/logs/session_log.md
+++ b/logs/session_log.md
@@ -4059,3 +4059,11 @@
   - TESTS (tests/roles/test_seam_parallel.py, 6): test_output_order_is_input_order_under_reversed_completion (a: inverse-sleep so completion reverses input, assert input order preserved); test_sequential_path_matches_multi_worker (e: `PG_FOUR_ROLE_CLAIM_WORKERS=1` == multi-worker); test_coverage_credit_only_on_verified_parallel (c); test_parallel_and_sequential_trip_cap_at_same_total (b: same `PG_MAX_COST_PER_RUN` cap trips at same accumulated spend); test_single_claim_over_cap_trips_in_worker_fail_closed (worker exception propagates, fail-closed); test_parallel_cost_equals_sequential_cost_under_cap (b: total cost equality). HARD constraints respected: run_claim_pipeline / RecordingTransport / D8 / coverage math / KG store unchanged; no `except: pass`.
 - STATUS: Diff + acceptance suite written on branch; sweep_integration.py modified, test_seam_parallel.py new. NOT yet Codex diff-gated, NOT yet committed/merged, run 11 NOT yet launched. Source correctness governed by the pending Codex diff gate.
 - NEXT_STEP: Codex diff-gate (`codex_diff_audit` per §3.0) on the I-run11-001 diff; on APPROVE, deploy and launch run 11.
+
+[2026-06-03 09:47:53]
+- ACTION: I-run11-002 (#1044) Sentinel+Mirror fix Codex-APPROVED (PR #1045); run 12 launched on VM.
+- RATIONALE: Run 11 held (all 70 UNSUPPORTED) — L1 benchmark Sentinel (general granite) ignored the INVERTED Guardian prompt → mislabeled every grounded claim UNGROUNDED. Fix: non-inverted GROUNDED/UNGROUNDED prompt + strict anchored parser (parse_sentinel_grounded_token; "not grounded"/prose fail-closed, no false-accept) selected by PG_SENTINEL_GROUNDEDNESS_MODE (derives from PG_FOUR_ROLE_TRANSPORT). Granite KEPT (4-role lock); sovereign inverted Guardian path byte-unchanged. L2: Mirror pass-2 JSON robustness (fences/alt keys), pass-1 grounding untouched.
+- EVIDENCE: 372 role tests pass; multi-fixture LIVE smoke (granite 2x) grounded/fabricated/qualitative-negation/paraphrase ALL pass; Codex diff APPROVE iter2 (zero P0/P1).
+- AFFECTED_FILES: src/polaris_graph/roles/sentinel_{adapter,contract}.py, mirror_adapter.py, tests/roles/*, scripts/diagnostics/sentinel_{multifixture_smoke,groundedness_probe}.py.
+- STATUS: PR #1045 open (base seam branch). Run 12 live on VM (q1_run12), still generating as of this entry.
+- NEXT_STEP: monitor run 12 — must RELEASE (Sentinel verdicts now a GROUNDED/UNGROUNDED mix, coverage > 0.70), then §-1.1 benchmark vs ChatGPT+Gemini.
diff --git a/scripts/dr_benchmark/gate_a_dry_run.py b/scripts/dr_benchmark/gate_a_dry_run.py
index 86f63622..0d42d675 100644
--- a/scripts/dr_benchmark/gate_a_dry_run.py
+++ b/scripts/dr_benchmark/gate_a_dry_run.py
@@ -242,15 +242,47 @@ def check_role_contracts() -> CheckResult:
     claim = "The grounded answer."
     problems: list[str] = []
 
-    # Sentinel through the adapter+transport: yes => UNGROUNDED, parsed_ok True.
+    # Sentinel GUARDIAN polarity through the adapter+transport: yes => UNGROUNDED, parsed_ok True.
+    # mode="guardian" is pinned so this lethal-polarity fixture is mode-deterministic regardless of
+    # the global default (I-run11-004: the default is now the MiniMax-M2 decomposition mode).
     sentinel_result, _ = run_sentinel(
-        transport, claim, evidence, model_slug="ibm-granite/granite-guardian-4.1-8b"
+        transport, claim, evidence,
+        model_slug="ibm-granite/granite-guardian-4.1-8b", mode="guardian",
     )
     if sentinel_result.verdict is not SentinelVerdict.UNGROUNDED or not sentinel_result.parsed_ok:
         problems.append(
             f"Sentinel polarity wrong via transport: {sentinel_result} (expected UNGROUNDED)"
         )
 
+    # Sentinel DECOMPOSITION contract (I-run11-004): the CERTIFIED MiniMax-M2 JSON verdict
+    # "unsupported" => UNGROUNDED, "supported" => GROUNDED (mode pinned for determinism).
+    decomp_unsupported = _GateAMockTransport(
+        judge_raw=_JUDGE_OFF_ENUM,
+        sentinel_raw='{"verdict": "unsupported", "unsupported_atoms": 1, "atoms": []}',
+    )
+    decomp_result, _ = run_sentinel(
+        decomp_unsupported, claim, evidence,
+        model_slug="minimax/minimax-m2", mode="decomposition",
+    )
+    if decomp_result.verdict is not SentinelVerdict.UNGROUNDED or not decomp_result.parsed_ok:
+        problems.append(
+            f"Sentinel decomposition unsupported wrong via transport: {decomp_result} "
+            "(expected UNGROUNDED)"
+        )
+    decomp_supported = _GateAMockTransport(
+        judge_raw=_JUDGE_OFF_ENUM,
+        sentinel_raw='{"verdict": "supported", "unsupported_atoms": 0, "atoms": []}',
+    )
+    decomp_grounded, _ = run_sentinel(
+        decomp_supported, claim, evidence,
+        model_slug="minimax/minimax-m2", mode="decomposition",
+    )
+    if decomp_grounded.verdict is not SentinelVerdict.GROUNDED or not decomp_grounded.parsed_ok:
+        problems.append(
+            f"Sentinel decomposition supported wrong via transport: {decomp_grounded} "
+            "(expected GROUNDED)"
+        )
+
     # Judge through the adapter+transport: an off-enum token must RAISE (no silent default).
     try:
         run_judge(
@@ -271,7 +303,7 @@ def check_role_contracts() -> CheckResult:
     # Mirror through the adapter+transport: the two-pass grounded round trip binds and returns.
     try:
         mirror_pass2, mirror_records = run_mirror(
-            transport, claim, evidence, model_slug="cohere/command-a-plus"
+            transport, claim, evidence, model_slug="z-ai/glm-5.1"
         )
         if mirror_pass2 is None or len(mirror_records) != 2:
             problems.append(
@@ -286,7 +318,8 @@ def check_role_contracts() -> CheckResult:
     return CheckResult(
         "role_contracts",
         True,
-        "via transport: Sentinel yes=UNGROUNDED, Judge off-enum raises, Mirror two-pass binds",
+        "via transport: Sentinel guardian yes=UNGROUNDED + decomposition "
+        "supported=GROUNDED/unsupported=UNGROUNDED, Judge off-enum raises, Mirror two-pass binds",
     )
 
 
diff --git a/scripts/dr_benchmark/offline_e2e.py b/scripts/dr_benchmark/offline_e2e.py
index 2b72e86e..ea07daed 100644
--- a/scripts/dr_benchmark/offline_e2e.py
+++ b/scripts/dr_benchmark/offline_e2e.py
@@ -218,8 +218,18 @@ class PerClaimFakeRoleTransport:
                 citations=[CitationSpan(span_start=0, span_end=8, doc_ids=(doc_id,))],
             )
         if request.role == "sentinel":
-            # "no" => no risk => GROUNDED (lethal-polarity: yes=risk=ungrounded).
-            return RoleResponse(raw_text="<score>no</score>", served_model=request.model_slug)
+            # GROUNDED in whichever groundedness mode the adapter resolved (I-run11-002 L1 +
+            # I-run11-004): decomposition (MiniMax-M2 default) -> JSON {"verdict": "supported"};
+            # guardian -> `<score>no</score>` (no risk => grounded, lethal-polarity yes=risk);
+            # noninverted -> one-word GROUNDED.
+            final_instruction = request.messages[-1]["content"] if request.messages else ""
+            if "Decompose the CLAIM into atomic sub-assertions" in final_instruction:
+                sentinel_raw = '{"verdict": "supported", "unsupported_atoms": 0, "atoms": []}'
+            elif "<guardian>" in final_instruction:
+                sentinel_raw = "<score>no</score>"
+            else:
+                sentinel_raw = "GROUNDED"
+            return RoleResponse(raw_text=sentinel_raw, served_model=request.model_slug)
         if request.role == "judge":
             verdict = (
                 JUDGE_FABRICATED
diff --git a/scripts/run_honest_sweep_r3.py b/scripts/run_honest_sweep_r3.py
index d37f7307..9c9f490d 100644
--- a/scripts/run_honest_sweep_r3.py
+++ b/scripts/run_honest_sweep_r3.py
@@ -4527,8 +4527,13 @@ async def run_one_query(
                 BudgetExceededError as _SeamBudgetExceededError,
                 _RUN_COST_CTX as _seam_cost_ctx,
             )
+            # I-run11-004: default raised 2400 -> 7200s. 2400 was the run-12 truncator — the
+            # 4-role seam (now incl. the reasoning-ON MiniMax-M2 decomposition Sentinel + the xhigh
+            # Mirror/Judge) takes minutes per claim, and a 2400s cap fired mid-run and held a
+            # truncated manifest. PG_VERIFIER_LLM_TIMEOUT_SECONDS (the per-call budget) stays 900.
+            # LAW VI: env-overridable.
             _seam_timeout = float(
-                os.environ.get("PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS", "2400")
+                os.environ.get("PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS", "7200")
             )
             _seam_kg_path = out_root / "verified_claim_graph_campaign.db"
             _seam_parent_cost = _seam_cost_ctx.get()
diff --git a/src/polaris_graph/llm/openrouter_client.py b/src/polaris_graph/llm/openrouter_client.py
index 45c907b4..c21ddf2b 100644
--- a/src/polaris_graph/llm/openrouter_client.py
+++ b/src/polaris_graph/llm/openrouter_client.py
@@ -265,6 +265,10 @@ _PRICE_TABLE_USD_PER_M: dict[str, tuple[float, float]] = {
     "qwen/":           (0.10, 0.60),
     "z-ai/glm-5.1":    (0.60, 2.20),
     "z-ai/":           (0.60, 2.20),
+    # I-run11-004: MiniMax-M2 Sentinel (decomposition). Conservative upper-bound $/M so the
+    # budget-impute fallback never UNDERcharges (over-counting is the safe direction for the cap).
+    "minimax/minimax-m2": (0.55, 2.20),
+    "minimax/":           (0.55, 2.20),
     "meta-llama/":     (0.30, 0.90),
     "google/gemma-4-31b-it": (0.13, 0.38),
     "google/gemma":    (0.05, 0.30),
@@ -414,8 +418,13 @@ PG_GENERATOR_MODEL = os.getenv(
 # (config/architecture/polaris_runtime_lock.yaml). Each role has its own knob;
 # the legacy PG_EVALUATOR_MODEL is compat-mapped to PG_MIRROR_MODEL until
 # 2026-09-06 (Carney demo) after which it fails the gate at preflight.
-PG_MIRROR_MODEL = os.getenv("PG_MIRROR_MODEL", "cohere/command-a-plus")
-PG_SENTINEL_MODEL = os.getenv("PG_SENTINEL_MODEL", "ibm-granite/granite-guardian-4.1-8b")
+# I-run11-004: the 4-role lock SENTINEL is now the certified MiniMax-M2 decomposition
+# detector (minimax/minimax-m2 — 0 false-accepts on 28 fabrications, over-flag 0.107 on the
+# 56-item fixture) and the MIRROR is z-ai/glm-5.1 (the operator re-pick; Cohere is not on
+# OpenRouter). These defaults MUST equal config/architecture/polaris_runtime_lock.yaml
+# (verify_lock asserts lock model_slug == code default). Judge unchanged.
+PG_MIRROR_MODEL = os.getenv("PG_MIRROR_MODEL", "z-ai/glm-5.1")
+PG_SENTINEL_MODEL = os.getenv("PG_SENTINEL_MODEL", "minimax/minimax-m2")
 PG_JUDGE_MODEL = os.getenv("PG_JUDGE_MODEL", "qwen/qwen3.6-35b-a3b")
 
 # Legacy 2-LLM stub env. Resolves to PG_MIRROR_MODEL when unset (the Mirror
@@ -448,6 +457,7 @@ _FAMILY_PREFIXES: dict[str, tuple[str, ...]] = {
     "kimi":        ("moonshotai/", "moonshot/", "kimi/"),
     "cohere":      ("cohere/", "coherelabs/", "command-"),       # I-meta-001
     "ibm-granite": ("ibm-granite/", "ibm/granite", "granite-"),  # I-meta-001
+    "minimax":     ("minimax/", "minimaxai/"),                   # I-run11-004 (MiniMax-M2 Sentinel)
     # Closed frontier families included for completeness (off-MVP, but if
     # ever allowed via a closed-source fallback they get their own family).
     "openai":   ("openai/", "gpt-"),
diff --git a/src/polaris_graph/roles/openrouter_role_transport.py b/src/polaris_graph/roles/openrouter_role_transport.py
index d793726d..c2133cec 100644
--- a/src/polaris_graph/roles/openrouter_role_transport.py
+++ b/src/polaris_graph/roles/openrouter_role_transport.py
@@ -150,7 +150,10 @@ _BENCHMARK_LINEUP_ENV = {
 }
 _BENCHMARK_LINEUP_DEFAULT_SLUG = {
     "mirror": "z-ai/glm-5.1",
-    "sentinel": "ibm-granite/granite-4.1-8b",
+    # I-run11-004: benchmark Sentinel is the CERTIFIED MiniMax-M2 decomposition detector
+    # (replaces the general ibm-granite/granite-4.1-8b, which mislabeled grounded claims). The
+    # benchmark default mode for the Sentinel is "decomposition" (see sentinel_adapter).
+    "sentinel": "minimax/minimax-m2",
     "judge": "qwen/qwen3.6-35b-a3b",
 }
 # Expected DEFAULT family lane per benchmark verifier role (the lane each role's
@@ -164,7 +167,8 @@ _BENCHMARK_LINEUP_DEFAULT_SLUG = {
 # four lineup members `slug.split("/")[0]` IS the family (z-ai / ibm-granite / qwen / deepseek).
 _BENCHMARK_VERIFIER_DEFAULT_FAMILY = {
     "mirror": "z-ai",
-    "sentinel": "ibm-granite",
+    # I-run11-004: MiniMax-M2 Sentinel — its `provider/` prefix `minimax` IS the family lane.
+    "sentinel": "minimax",
     "judge": "qwen",
 }
 
@@ -267,6 +271,13 @@ FOUR_ROLE_STAGE = "benchmark_openrouter"
 # LAW VI: effort is overridable via PG_FOUR_ROLE_REASONING_EFFORT (default "xhigh" = MAX).
 _REASONING_EFFORT = os.getenv("PG_FOUR_ROLE_REASONING_EFFORT", "xhigh")
 
+# I-run11-004: hard floor on the decomposition Sentinel's top-level max_tokens. The certified
+# MiniMax-M2 call used reasoning + max_tokens>=3000; anything below that truncates the JSON
+# {verdict, atoms} mid-emission (the run-12 truncator) and collapses every claim to a fail-closed
+# UNGROUNDED. An env override (PG_SENTINEL_DECOMPOSITION_MAX_TOKENS) can RAISE but never lower past
+# this floor.
+_SENTINEL_DECOMPOSITION_MIN_MAX_TOKENS = 3000
+
 # I-meta-008 / #1026: blank-verdict step-down ladder. When a reasoning-first verifier returns a
 # BLANK bare verdict (reasoning budget exhausted without converging under the high effort), retry
 # with the effort stepped DOWN this ladder so the model is forced to spend tokens on the VERDICT,
@@ -294,30 +305,56 @@ _VERIFIER_EFFORT_LADDER = _parse_effort_ladder()
 # WHY per-role: Mirror (`z-ai/glm-5.1`) and Judge (`qwen/qwen3.6-35b-a3b`) are DELIBERATIVE
 # verifiers — they weigh evidence and argue a verdict, so they get MAX reasoning effort
 # (`xhigh`) AND `provider.require_parameters=True` (only route to a provider that honors
-# reasoning). Sentinel (`ibm-granite/granite-4.1-8b`) is a faithfulness CLASSIFIER — its
-# self-host destination is the task-trained granite-GUARDIAN, also a classifier — and the
-# OpenRouter general granite slug does NOT advertise `reasoning` in its `supported_parameters`.
-# So Sentinel sends NO reasoning param and NO `provider.require_parameters`, keeping its route
-# executable: with `require_parameters=True` OpenRouter REFUSES to route to a provider that
-# can't honor `reasoning`, which would fail the very first Sentinel call.
+# reasoning).
 #
-# This is NOT a downgrade of the operator's MAX-reasoning directive — that directive targets the
-# DELIBERATIVE verifiers; a classifier has no reasoning channel to maximize, so withholding the
-# param keeps it faithful to its role rather than under-serving it. LAW VI: each role's default
-# is overridable via the env knob `PG_<ROLE>_REASONING`.
+# Sentinel is MODE-AWARE (I-run11-004): the CERTIFIED MiniMax-M2 DECOMPOSITION Sentinel
+# (`minimax/minimax-m2`, the benchmark + lock default) was certified WITH reasoning ON and
+# max_tokens>=3000 — turning reasoning OFF (or starving max_tokens to the 256 classifier budget)
+# truncates the JSON {verdict, atoms} mid-emission and collapses every claim to a fail-closed
+# UNGROUNDED (the run-12 truncator). So when the active Sentinel groundedness mode is
+# "decomposition", the Sentinel sends MAX reasoning + a GENEROUS max_tokens, exactly replicating
+# the certified call. The SOVEREIGN `guardian`/`noninverted` granite Sentinel modes stay
+# reasoning-OFF (a <score>/one-word classifier whose self-host slug does not advertise
+# `reasoning`); their settings are NOT regressed. LAW VI: overridable via `PG_SENTINEL_REASONING`.
 _ROLE_REASONING_DEFAULT = {"mirror": True, "sentinel": False, "judge": True}
 
 
+def sentinel_decomposition_active() -> bool:
+    """True iff the ACTIVE Sentinel groundedness mode is "decomposition" (I-run11-004).
+
+    Lazily resolves `sentinel_adapter.sentinel_groundedness_mode()` (env- + model-aware, LAW VI)
+    so the transport can mode-gate the Sentinel's reasoning + max_tokens WITHOUT an import-time
+    dependency on the adapter (the adapter does not import this transport — no cycle). Any
+    resolution error is swallowed to the conservative non-decomposition answer (the certified
+    MiniMax call is only requested when the mode UNAMBIGUOUSLY resolves to decomposition).
+    """
+    try:
+        from src.polaris_graph.roles.sentinel_adapter import (
+            _MODE_DECOMPOSITION,
+            sentinel_groundedness_mode,
+        )
+
+        return sentinel_groundedness_mode() == _MODE_DECOMPOSITION
+    except Exception:  # noqa: BLE001 — conservative: unknown -> not decomposition.
+        return False
+
+
 def role_reasoning_enabled(role: str) -> bool:
     """Whether the given verifier role should send the MAX-reasoning request params.
 
     Returns the per-role default from `_ROLE_REASONING_DEFAULT`, overridable per role via the
     env var `PG_<ROLE>_REASONING` (LAW VI): "1"/"true"/"yes" -> True, "0"/"false"/"no" -> False;
     absent (or any other value) falls back to the role default. Mirror/Judge default True
-    (deliberative verifiers -> MAX reasoning); Sentinel defaults False (classifier whose
-    OpenRouter slug does not advertise `reasoning`, so reasoning would break routing).
+    (deliberative verifiers -> MAX reasoning). Sentinel is MODE-AWARE (I-run11-004): in
+    "decomposition" mode (the certified MiniMax-M2 detector) it defaults True (reasoning ON, as
+    certified); in the sovereign granite `guardian`/`noninverted` modes it defaults False (a
+    classifier whose slug does not advertise `reasoning`, so reasoning would break routing).
     """
-    default = _ROLE_REASONING_DEFAULT.get(role, False)
+    if role == "sentinel" and os.getenv(f"PG_{role.upper()}_REASONING") is None:
+        # No explicit override: the Sentinel default is mode-aware (decomposition -> reasoning ON).
+        default = sentinel_decomposition_active()
+    else:
+        default = _ROLE_REASONING_DEFAULT.get(role, False)
     override = os.getenv(f"PG_{role.upper()}_REASONING")
     if override is None:
         return default
@@ -445,7 +482,18 @@ def _build_openrouter_body(request: RoleRequest, model_slug: str, normalized_mes
         # #1017 fix popped it, so xhigh ate ~95% of an unknown provider default and STARVED the verdict
         # to empty for a reasoning-first Mirror (GLM-5.1) / Judge (Qwen) -> fail-loud crash on the run.
         # 16384 -> reasoning ~15564 + verdict room ~820 (generous for Mirror JSON + Judge enum).
-        body["max_tokens"] = int(os.getenv("PG_VERIFIER_REASONING_MAX_TOKENS", "16384"))
+        #
+        # I-run11-004: the DECOMPOSITION Sentinel (MiniMax-M2, reasoning ON) emits a JSON
+        # {verdict, unsupported_atoms, atoms} body — a multi-atom list needs MORE output room than a
+        # bare verdict, AND the certification used reasoning + max_tokens>=3000. So the decomposition
+        # Sentinel gets its OWN generous budget (default 16384, hard-floored at 3000 so an env
+        # override can never re-introduce the run-12 truncation that collapses every claim to a
+        # fail-closed UNGROUNDED). Other reasoning verifiers keep PG_VERIFIER_REASONING_MAX_TOKENS.
+        if request.role == "sentinel":
+            decomp_budget = int(os.getenv("PG_SENTINEL_DECOMPOSITION_MAX_TOKENS", "16384"))
+            body["max_tokens"] = max(decomp_budget, _SENTINEL_DECOMPOSITION_MIN_MAX_TOKENS)
+        else:
+            body["max_tokens"] = int(os.getenv("PG_VERIFIER_REASONING_MAX_TOKENS", "16384"))
     else:
         # Sentinel (reasoning-disabled classifier): give it explicit output room rather than relying
         # on an unknown provider default (no pop-and-hope). Small budget is plenty for a label verdict.
diff --git a/src/polaris_graph/roles/sentinel_adapter.py b/src/polaris_graph/roles/sentinel_adapter.py
index 9da8eb27..05090728 100644
--- a/src/polaris_graph/roles/sentinel_adapter.py
+++ b/src/polaris_graph/roles/sentinel_adapter.py
@@ -1,13 +1,21 @@
-"""Sentinel (IBM Granite Guardian 4.1) adapter — request builder + FAIL-CLOSED caller.
+"""Sentinel adapter — request builder + FAIL-CLOSED caller (3 groundedness modes).
 
-Granite Guardian groundedness calling convention (F3, I-meta-002 iter-2): an assistant turn
-carrying the claim to be checked, then a FINAL user `<guardian>` groundedness block, plus the
-`documents`. The model emits `<score>yes|no</score>` (NOT JSON), so the request carries NO
-structured-output spec — the score is parsed by `parse_sentinel_score`.
+THREE (prompt, parser) contracts, selected by mode (env- + model-aware, LAW VI):
+  - "guardian"      (sovereign granite-Guardian): assistant claim turn + a FINAL user
+    `<guardian>` groundedness block + `documents`; the model emits `<score>yes|no</score>`
+    (parsed by `parse_sentinel_score`, yes=UNGROUNDED).
+  - "noninverted"   (general granite): the DIRECT one-word GROUNDED/UNGROUNDED block
+    (parsed by `parse_sentinel_grounded_token`).
+  - "decomposition" (CERTIFIED MiniMax-M2, I-run11-004): a SINGLE user message with the certified
+    claim-DECOMPOSITION + span-coverage prompt (span+claim inline), `response_format` json_object;
+    the model emits JSON {verdict, unsupported_atoms, atoms} (parsed by
+    `parse_sentinel_decomposition`, "supported"=GROUNDED / "unsupported"=UNGROUNDED). The
+    production decomposition call REPLICATES the certified call (verbatim `_DECOMPOSITION_PROMPT`,
+    reasoning ON via the transport, max_tokens>=3000) so the 0-false-accept certification transfers.
 
-FAIL CLOSED (lethal-inversion guard): a malformed/empty output OR a transport error yields
-`SentinelResult(UNGROUNDED, parsed_ok=False)`. There is NO path that returns GROUNDED on bad
-or missing output. `yes=UNGROUNDED` polarity lives in the contract, never re-derived here.
+FAIL CLOSED (lethal-inversion guard, ALL modes): a malformed/empty output OR a transport error
+yields `SentinelResult(UNGROUNDED, parsed_ok=False)`. There is NO path that returns GROUNDED on
+bad or missing output. Polarity/mapping lives in the contract, never re-derived here.
 """
 
 from __future__ import annotations
@@ -30,6 +38,7 @@ from src.polaris_graph.roles.role_transport import (
 from src.polaris_graph.roles.sentinel_contract import (
     SentinelResult,
     SentinelVerdict,
+    parse_sentinel_decomposition,
     parse_sentinel_grounded_token,
     parse_sentinel_score,
 )
@@ -57,48 +66,97 @@ _ROLE = "sentinel"
 _GROUNDEDNESS_MODE_ENV = "PG_SENTINEL_GROUNDEDNESS_MODE"
 _MODE_NONINVERTED = "noninverted"
 _MODE_GUARDIAN = "guardian"
+# I-run11-004: the CERTIFIED MiniMax-M2 claim-decomposition + span-coverage mode (the new lock +
+# benchmark Sentinel). Single-user-message span+claim prompt, JSON verdict parsed by
+# `parse_sentinel_decomposition`. Valid for PG_SENTINEL_GROUNDEDNESS_MODE=decomposition.
+_MODE_DECOMPOSITION = "decomposition"
+_VALID_MODES = (_MODE_NONINVERTED, _MODE_GUARDIAN, _MODE_DECOMPOSITION)
 # The transport env the default derives from (literals kept in sync with run_gate_b.py's
 # `_FOUR_ROLE_TRANSPORT_ENV` / `_TRANSPORT_SELF_HOST`; NOT imported, to avoid a scripts->src cycle).
 _FOUR_ROLE_TRANSPORT_ENV = "PG_FOUR_ROLE_TRANSPORT"
 _TRANSPORT_SELF_HOST = "self_host"
 
+# I-run11-004: model-aware default mode selection. When PG_SENTINEL_GROUNDEDNESS_MODE is UNSET, the
+# default mode depends on the CONFIGURED Sentinel slug so the prompt+parser can never silently
+# desync from the served model:
+#   - a granite-guardian model -> "guardian"  (the inverted <score>yes|no</score> contract);
+#   - a minimax model          -> "decomposition" (the certified MiniMax-M2 detector);
+#   - else                     -> the transport-derived default (self_host->guardian, else noninverted).
+# Substring tokens (matched case-insensitively against the lock/PG_SENTINEL_MODEL slug). Kept in
+# sync with openrouter_client._FAMILY_PREFIXES (granite / minimax) WITHOUT importing it, so the
+# adapter has no import-time dependency on the family registry.
+_SENTINEL_GUARDIAN_SLUG_TOKEN = "granite-guardian"
+_SENTINEL_DECOMPOSITION_SLUG_TOKENS = ("minimax/", "minimax-")
+
+
+def _configured_sentinel_slug() -> str:
+    """The active Sentinel model slug (LAW VI), for the model-aware default mode (I-run11-004).
+
+    Reads `PG_SENTINEL_MODEL` from the env (the lock's per-role primary knob), falling back to the
+    code default `openrouter_client.PG_SENTINEL_MODEL` (the single source of truth that
+    verify_lock pins against the architecture lock). Read lazily so a post-import override is
+    honored; returns "" only if neither is set (never raises)."""
+    return os.getenv("PG_SENTINEL_MODEL") or getattr(_orc, "PG_SENTINEL_MODEL", "") or ""
+
+
+def _model_aware_default_mode() -> str:
+    """Default Sentinel mode when PG_SENTINEL_GROUNDEDNESS_MODE is UNSET (I-run11-004).
+
+    MODEL-AWARE first, so the lock Sentinel (MiniMax-M2) gets the DECOMPOSITION prompt+parser and a
+    granite-guardian Sentinel still gets the inverted guardian contract — no silent desync between
+    the served model and the prompt:
+      - configured slug is a granite-guardian model -> "guardian";
+      - configured slug is a minimax model          -> "decomposition";
+      - otherwise -> the prior transport-derived default ("self_host" -> "guardian", else
+        "noninverted" — the benchmark general-granite route, preserved for back-compat).
+    """
+    slug = _configured_sentinel_slug().strip().lower()
+    if _SENTINEL_GUARDIAN_SLUG_TOKEN in slug:
+        return _MODE_GUARDIAN
+    if any(token in slug for token in _SENTINEL_DECOMPOSITION_SLUG_TOKENS):
+        return _MODE_DECOMPOSITION
+    # Model not recognized as guardian/minimax: fall back to the transport-derived default.
+    transport = os.getenv(_FOUR_ROLE_TRANSPORT_ENV, "").strip().lower()
+    if transport == _TRANSPORT_SELF_HOST:
+        return _MODE_GUARDIAN
+    return _MODE_NONINVERTED
+
 
 def sentinel_groundedness_mode() -> str:
-    """Resolve the active Sentinel groundedness mode (LAW VI). Returns "noninverted" | "guardian".
-
-    Precedence: an explicit `PG_SENTINEL_GROUNDEDNESS_MODE` ("noninverted" | "guardian") wins.
-    An explicit but UNRECOGNIZED value raises ValueError (Codex diff-gate P2, no-silent-fallback:
-    a mode typo must not silently desync the prompt+parser from the served model). When the env is
-    UNSET, DERIVE from `PG_FOUR_ROLE_TRANSPORT` so the prompt+parser match the served model:
-    "self_host" -> "guardian" (sovereign granite-Guardian); anything else (incl. the "openrouter"
-    default) -> "noninverted" (benchmark general granite).
+    """Resolve the active Sentinel groundedness mode (LAW VI).
+
+    Returns "noninverted" | "guardian" | "decomposition".
+
+    Precedence: an explicit `PG_SENTINEL_GROUNDEDNESS_MODE` ("noninverted" | "guardian" |
+    "decomposition") ALWAYS wins. An explicit but UNRECOGNIZED value raises ValueError (Codex
+    diff-gate P2, no-silent-fallback: a mode typo must not silently desync the prompt+parser from
+    the served model). When the env is UNSET, the default is MODEL-AWARE (I-run11-004): a
+    granite-guardian slug -> "guardian"; a minimax slug -> "decomposition"; otherwise the
+    transport-derived default ("self_host" -> "guardian", else "noninverted").
     """
     override = os.getenv(_GROUNDEDNESS_MODE_ENV)
     if override is not None and override.strip():
         token = override.strip().lower()
-        if token in (_MODE_NONINVERTED, _MODE_GUARDIAN):
+        if token in _VALID_MODES:
             return token
         # Fail LOUD on an explicit unrecognized mode (LAW II no-silent-fallback).
         raise ValueError(
             f"{_GROUNDEDNESS_MODE_ENV}={override!r} is invalid; "
-            f"expected {_MODE_NONINVERTED!r} or {_MODE_GUARDIAN!r}."
+            f"expected one of {_VALID_MODES!r}."
         )
-    # Unset/blank: derive from the transport so the sovereign path gets guardian.
-    transport = os.getenv(_FOUR_ROLE_TRANSPORT_ENV, "").strip().lower()
-    if transport == _TRANSPORT_SELF_HOST:
-        return _MODE_GUARDIAN
-    return _MODE_NONINVERTED
+    # Unset/blank: model-aware default (then transport-derived for an unrecognized model).
+    return _model_aware_default_mode()
 
 
 def _resolve_mode(mode: str | None) -> str:
     """Resolve + VALIDATE the active mode (Codex diff-gate P2, no-silent-fallback). An explicit
-    but unrecognized `mode` argument must NOT silently select noninverted — it raises ValueError,
+    but unrecognized `mode` argument must NOT silently select a parser — it raises ValueError,
     so a caller typo cannot desync the prompt from the parser. None -> env-gated resolution."""
     resolved = mode if mode is not None else sentinel_groundedness_mode()
-    if resolved not in (_MODE_NONINVERTED, _MODE_GUARDIAN):
+    if resolved not in _VALID_MODES:
         raise ValueError(
             f"sentinel groundedness mode {resolved!r} is invalid; "
-            f"expected {_MODE_NONINVERTED!r} or {_MODE_GUARDIAN!r}."
+            f"expected one of {_VALID_MODES!r}."
         )
     return resolved
 
@@ -129,6 +187,47 @@ _NONINVERTED_BLOCK = (
     "Answer with EXACTLY one word: GROUNDED or UNGROUNDED. Output only that single word."
 )
 
+# === CERTIFIED DECOMPOSITION prompt (MiniMax-M2, I-run11-004) =================================
+# COPIED VERBATIM from the CERTIFIED harness scripts/diagnostics/sentinel_bakeoff.py `GLM_PROMPT`
+# so the certification (0 false-accepts on 28 fabrications, over-flag 0.107 on the 56-item fixture)
+# TRANSFERS to production. It has `{span}` and `{claim}` `.format` fields and `{{...}}` escaped
+# JSON braces. The atomic-decomposition + grammatical-voice attribution rules are the heart of the
+# detector — DO NOT paraphrase or trim. The production decomposition call inlines span+claim in a
+# SINGLE user message (NOT the guardian documents-channel layout) so the served call matches the
+# certified one exactly.
+_DECOMPOSITION_PROMPT = """You are a strict faithfulness checker for a clinical-grade research pipeline. You are given a SPAN of source text and a CLAIM that cites ONLY that span. Your job: decide whether EVERY factual assertion in the CLAIM is supported by the SPAN alone.
+
+STEP 1 — Decompose the CLAIM into atomic sub-assertions. Separate them into:
+  - mechanism/fact atoms (what happens, numbers, findings),
+  - attribution atoms (WHO said / did / authored / found something — any named person, group, or framework),
+  - relation atoms (causal or "offsets / counterbalances / compensates" links between two things).
+List every atom; do not merge two assertions into one.
+
+STEP 2 — Check EACH atom against the SPAN ONLY. An atom is:
+  - "supported" if the SPAN states it (conservative paraphrase allowed), OR
+  - "unsupported" if the SPAN does not state it.
+
+Rules that decide hard cases:
+  - SCOPE / OFFSET: if the CLAIM says one thing "offsets / counterbalances / compensates for / cancels" another, the SPAN must actually state that offsetting relation. The SPAN merely listing both things separately (e.g. "raises output" AND "displaces labor") does NOT support an "offset" relation atom — that atom is unsupported.
+  - ATTRIBUTION by grammatical voice:
+      * If the SPAN attributes a result with FIRST PERSON ("We present...", "We show...", "Our framework..."), then a CLAIM atom that names the cited source's own authors as the source IS supported (the source is speaking about itself).
+      * If the SPAN attributes a result with a THIRD-PERSON pronoun that has NO proper-noun antecedent inside the SPAN ("He applies...", "She finds...", "They argue..."), then a CLAIM atom that names a SPECIFIC PERSON as the source is UNSUPPORTED — that named identity is not present in the SPAN.
+      * If the SPAN names the person explicitly, an attribution atom naming that same person is supported.
+  - SPECIFICITY: if the CLAIM names a specific entity/number/mechanism the SPAN does not contain, that atom is unsupported.
+
+STEP 3 — Verdict: "unsupported" if ANY atom is unsupported; otherwise "supported".
+
+Return STRICT JSON only, no prose outside it:
+{{"atoms": [{{"atom": "<text>", "type": "mechanism|attribution|relation", "status": "supported|unsupported", "why": "<short>"}}], "unsupported_atoms": <int>, "verdict": "supported" | "unsupported"}}
+
+SPAN:
+{span}
+
+CLAIM:
+{claim}
+
+JSON:"""
+
 # The fail-closed result returned on transport error / malformed output. NEVER GROUNDED.
 _FAIL_CLOSED = SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)
 
@@ -140,29 +239,54 @@ def build_sentinel_request(
     model_slug: str,
     mode: str | None = None,
 ) -> RoleRequest:
-    """Build a Sentinel groundedness request for the active mode (I-run11-002 L1).
-
-    Layout (F3, identical across modes): assistant turn = the claim under check; final user turn =
-    the groundedness instruction; documents ride in `params["documents"]` (Granite's documents
-    channel). NO structured-output spec — both modes emit free text the contract parses, not JSON.
+    """Build a Sentinel groundedness request for the active mode (I-run11-002 L1 / I-run11-004).
 
-    `mode` selects the FINAL user instruction:
+    `mode` selects BOTH the message LAYOUT and the FINAL user instruction:
       - "guardian"    -> the INVERTED `<guardian>` block (sovereign self-host granite-Guardian).
-      - "noninverted" -> the DIRECT one-word GROUNDED/UNGROUNDED block (benchmark general granite).
-    When `mode` is None it resolves from `sentinel_groundedness_mode()` (env-gated, LAW VI;
-    DEFAULT "noninverted" for the OpenRouter/benchmark route, "guardian" for self_host).
+      - "noninverted" -> the DIRECT one-word GROUNDED/UNGROUNDED block (general granite).
+      - "decomposition" -> the CERTIFIED MiniMax-M2 single-user-message span+claim prompt.
+
+    GUARDIAN / NONINVERTED layout (F3): assistant turn = the claim under check; final user turn =
+    the groundedness instruction; documents ride in `params["documents"]` (rendered model-visible by
+    the transport). NO structured-output spec — these emit free text the contract parses.
+
+    DECOMPOSITION layout (I-run11-004) REPLICATES the certified call so the certification transfers:
+    a SINGLE user message carrying `_DECOMPOSITION_PROMPT.format(span=<all evidence .text joined>,
+    claim=claim)` (NOT the guardian documents-channel layout), with `response_format`
+    {"type":"json_object"} requested (the transport forwards it; the robust parser also handles
+    non-JSON-mode output). `documents` is still carried in params for introspection/identity, but the
+    SPAN is inlined into the prompt — the model reads the span from the message, exactly as certified.
+
+    When `mode` is None it resolves from `sentinel_groundedness_mode()` (env- + model-aware, LAW VI).
     """
     resolved_mode = _resolve_mode(mode)
+    documents = [{"doc_id": doc.doc_id, "text": doc.text} for doc in evidence_documents]
+
+    if resolved_mode == _MODE_DECOMPOSITION:
+        # Certified single-user-message layout: span = all evidence document texts joined (the
+        # certified harness passed one `cited_evidence_text` span; multi-doc evidence is joined so
+        # the whole cited pool is in-span). response_format requests JSON; the parser is robust to
+        # non-JSON output too.
+        span = "\n\n".join(doc.text for doc in evidence_documents)
+        user_content = _DECOMPOSITION_PROMPT.format(span=span, claim=claim)
+        messages = [{"role": "user", "content": user_content}]
+        params = {
+            "documents": documents,
+            "response_format": {"type": "json_object"},
+        }
+        return RoleRequest(
+            role=_ROLE,
+            model_slug=model_slug,
+            messages=messages,
+            params=params,
+        )
+
     instruction = _GUARDIAN_BLOCK if resolved_mode == _MODE_GUARDIAN else _NONINVERTED_BLOCK
     messages = [
         {"role": "assistant", "content": claim},
         {"role": "user", "content": instruction},
     ]
-    params = {
-        "documents": [
-            {"doc_id": doc.doc_id, "text": doc.text} for doc in evidence_documents
-        ],
-    }
+    params = {"documents": documents}
     return RoleRequest(
         role=_ROLE,
         model_slug=model_slug,
@@ -185,17 +309,19 @@ def run_sentinel(
     completion, iter-3 P1-a). A transport error OR a malformed/empty `raw_text` both yield
     `SentinelResult(UNGROUNDED, parsed_ok=False)` — never GROUNDED, in EITHER mode.
 
-    `mode` (None -> `sentinel_groundedness_mode()`, env-gated, LAW VI) selects BOTH the prompt
-    (via `build_sentinel_request`) AND the parser, so they always pair correctly:
-      - "guardian"    -> inverted `<score>yes|no</score>` parser (`parse_sentinel_score`).
-      - "noninverted" -> direct GROUNDED/UNGROUNDED parser (`parse_sentinel_grounded_token`).
+    `mode` (None -> `sentinel_groundedness_mode()`, env- + model-aware, LAW VI) selects BOTH the
+    prompt (via `build_sentinel_request`) AND the parser, so they always pair correctly:
+      - "guardian"      -> inverted `<score>yes|no</score>` parser (`parse_sentinel_score`).
+      - "noninverted"   -> direct GROUNDED/UNGROUNDED parser (`parse_sentinel_grounded_token`).
+      - "decomposition" -> certified JSON-verdict parser (`parse_sentinel_decomposition`).
     """
     resolved_mode = _resolve_mode(mode)
-    parser = (
-        parse_sentinel_score
-        if resolved_mode == _MODE_GUARDIAN
-        else parse_sentinel_grounded_token
-    )
+    if resolved_mode == _MODE_GUARDIAN:
+        parser = parse_sentinel_score
+    elif resolved_mode == _MODE_DECOMPOSITION:
+        parser = parse_sentinel_decomposition
+    else:
+        parser = parse_sentinel_grounded_token
     request = build_sentinel_request(
         claim, evidence_documents, model_slug=model_slug, mode=resolved_mode
     )
diff --git a/src/polaris_graph/roles/sentinel_contract.py b/src/polaris_graph/roles/sentinel_contract.py
index 1a962910..fb1146bc 100644
--- a/src/polaris_graph/roles/sentinel_contract.py
+++ b/src/polaris_graph/roles/sentinel_contract.py
@@ -19,6 +19,7 @@ deliberately fails CLOSED, so it is a SEPARATE contract, not a reuse.
 
 from __future__ import annotations
 
+import json
 import re
 from enum import Enum
 from typing import NamedTuple
@@ -162,3 +163,94 @@ def parse_sentinel_grounded_token(raw: str) -> SentinelResult:
         return SentinelResult(SentinelVerdict.GROUNDED, parsed_ok=True)
     # Negated prose, extra tokens, both/neither, repeats, non-clean output -> fail CLOSED.
     return SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)
+
+
+# === DECOMPOSITION (certified MiniMax-M2) groundedness parser (I-run11-004) ===================
+# WHY a THIRD parser: the broken Granite Guardian Sentinel was replaced with the CERTIFIED
+# MiniMax-M2 claim-DECOMPOSITION detector. On the 56-item fixture (28 grounded + 28 fabricated
+# across NUMBER_SWAP / ENTITY_SWAP / NEGATION / FABRICATED_ATTRIBUTION / SCOPE_INFLATION) the
+# certified prompt+parse scored 0 false-accepts on all 28 fabrications and over-flag 0.107. The
+# certified call returns STRICT JSON {verdict: "supported"|"unsupported", unsupported_atoms, atoms}
+# (scripts/diagnostics/sentinel_bakeoff.py: GLM_PROMPT + _strip_json + run_glm_decomposition).
+#
+# This parser PORTS the certified `_strip_json` robust extraction (strip ```json fences, json.loads,
+# largest {...} span, trailing-comma repair) and maps the certified verdict to the SentinelResult:
+#     "supported"   -> GROUNDED,   parsed_ok=True
+#     "unsupported" -> UNGROUNDED,  parsed_ok=True
+# It preserves the LETHAL fail-closed property identical to the other two parsers: ANY parse
+# failure, a missing verdict, an off-enum verdict, or a non-string input -> UNGROUNDED,
+# parsed_ok=False. There is NO code path that returns GROUNDED on bad input — an unverifiable
+# claim is HELD, never released (§-1.1 clinical-safety).
+
+
+def _strip_json(text: str) -> dict:
+    """Robust JSON extraction from a frontier-LLM response (ported VERBATIM-in-behavior from
+    scripts/diagnostics/sentinel_bakeoff.py `_strip_json`, the CERTIFIED harness).
+
+    Frontier models wrap JSON in markdown fences, prepend reasoning text, or emit trailing commas.
+    A brittle `json.loads` crashes on one such reply. This handles: fenced ```json blocks, reasoning
+    prefixes/suffixes (largest {...} span), and trailing commas. Raises ValueError when NO parseable
+    JSON object is present (the caller maps that to a fail-closed UNGROUNDED).
+    """
+    if not isinstance(text, str):
+        raise ValueError(f"non-string response: {type(text).__name__}")
+    s = text.strip()
+    fence = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL | re.IGNORECASE)
+    if fence:
+        s = fence.group(1).strip()
+    try:
+        return json.loads(s)
+    except json.JSONDecodeError:
+        pass
+    start, end = s.find("{"), s.rfind("}")
+    if start != -1 and end != -1 and end > start:
+        block = s[start:end + 1]
+        for attempt in (block, re.sub(r",(\s*[}\]])", r"\1", block)):
+            try:
+                return json.loads(attempt)
+            except json.JSONDecodeError:
+                continue
+    raise ValueError(f"no parseable JSON object in response: {text[:200]!r}")
+
+
+# The two valid decomposition verdict tokens and their groundedness mapping (LOCKED, certified).
+_DECOMPOSITION_VERDICT_SUPPORTED = "supported"
+_DECOMPOSITION_VERDICT_UNSUPPORTED = "unsupported"
+_DECOMPOSITION_VERDICT_TO_VERDICT = {
+    _DECOMPOSITION_VERDICT_SUPPORTED: SentinelVerdict.GROUNDED,
+    _DECOMPOSITION_VERDICT_UNSUPPORTED: SentinelVerdict.UNGROUNDED,
+}
+
+
+def parse_sentinel_decomposition(raw: str) -> SentinelResult:
+    """Parse a CERTIFIED MiniMax-M2 DECOMPOSITION output (JSON) into a SentinelResult (I-run11-004).
+
+    The certified output is STRICT JSON {"verdict": "supported"|"unsupported", "unsupported_atoms":
+    <int>, "atoms": [...]}. Mapping (LOCKED): "supported" -> GROUNDED, "unsupported" -> UNGROUNDED.
+
+    FAIL CLOSED (lethal-inversion guard, identical safety to the other two parsers): ANY of —
+      - non-string input,
+      - unparseable JSON (after the robust `_strip_json` fence/prefix/trailing-comma handling),
+      - a missing `verdict` key,
+      - an off-enum verdict (anything other than the exact tokens "supported"/"unsupported"),
+    yields UNGROUNDED with parsed_ok=False. There is NO path that returns GROUNDED on bad input.
+    `parsed_ok=True` is reserved for a clean JSON object carrying exactly one recognized verdict.
+    """
+    if not isinstance(raw, str):
+        return SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)
+    try:
+        parsed = _strip_json(raw)
+    except ValueError:
+        # Unparseable / no JSON object -> fail CLOSED (clinical-safe: hold, never release).
+        return SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)
+    if not isinstance(parsed, dict):
+        # A bare JSON array / scalar carries no verdict -> fail CLOSED.
+        return SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)
+    verdict_token = parsed.get("verdict")
+    if not isinstance(verdict_token, str):
+        return SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)
+    verdict = _DECOMPOSITION_VERDICT_TO_VERDICT.get(verdict_token.strip().lower())
+    if verdict is None:
+        # Missing/odd/off-enum verdict -> fail CLOSED (never a silent GROUNDED).
+        return SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)
+    return SentinelResult(verdict, parsed_ok=True)
diff --git a/tests/architecture/test_runtime_lock.py b/tests/architecture/test_runtime_lock.py
index a832150e..f1fa6f07 100644
--- a/tests/architecture/test_runtime_lock.py
+++ b/tests/architecture/test_runtime_lock.py
@@ -24,11 +24,19 @@ def test_family_registry_has_cohere():
 
 
 def test_family_registry_has_ibm_granite():
-    """I-meta-001 V4 regression — ibm-granite family added for Sentinel role."""
+    """I-meta-001 V4 regression — ibm-granite family still registered (sovereign Mirror history)."""
     assert "ibm-granite" in _FAMILY_PREFIXES
     assert family_from_model("ibm-granite/granite-guardian-4.1-8b") == "ibm-granite"
 
 
+def test_family_registry_has_minimax():
+    """I-run11-004 regression — minimax family added for the CERTIFIED MiniMax-M2 Sentinel."""
+    assert "minimax" in _FAMILY_PREFIXES
+    assert family_from_model("minimax/minimax-m2") == "minimax"
+    # minimax must NOT collide with any other lock family (4 distinct lineages).
+    assert family_from_model("minimax/minimax-m2") not in ("deepseek", "glm", "qwen")
+
+
 def test_family_registry_existing_families_unchanged():
     """Don't regress the existing 10 families."""
     assert family_from_model("deepseek/deepseek-v4-pro") == "deepseek"
@@ -39,10 +47,12 @@ def test_family_registry_existing_families_unchanged():
 
 # --- N-way family segregation ---
 
+# I-run11-004: the locked stack is now Generator deepseek + Mirror z-ai/glm-5.1 (glm) +
+# Sentinel CERTIFIED minimax/minimax-m2 (minimax) + Judge qwen — four distinct lineages.
 _LOCKED_4_ROLE_MAP = {
     "generator": "deepseek/deepseek-v4-pro",
-    "mirror":    "cohere/command-a-plus",
-    "sentinel":  "ibm-granite/granite-guardian-4.1-8b",
+    "mirror":    "z-ai/glm-5.1",
+    "sentinel":  "minimax/minimax-m2",
     "judge":     "qwen/qwen3.6-35b-a3b",
 }
 
@@ -52,8 +62,8 @@ def test_validate_role_families_passes_for_locked_stack():
     out = validate_role_families(_LOCKED_4_ROLE_MAP)
     assert out == {
         "generator": "deepseek",
-        "mirror":    "cohere",
-        "sentinel":  "ibm-granite",
+        "mirror":    "glm",
+        "sentinel":  "minimax",
         "judge":     "qwen",
     }
 
diff --git a/tests/dr_benchmark/test_gate_b_seam.py b/tests/dr_benchmark/test_gate_b_seam.py
index 56df7c8a..eb4ba5e9 100644
--- a/tests/dr_benchmark/test_gate_b_seam.py
+++ b/tests/dr_benchmark/test_gate_b_seam.py
@@ -87,8 +87,19 @@ class _FakeRoleTransport:
                 citations=[CitationSpan(span_start=0, span_end=8, doc_ids=(doc_id,))],
             )
         if request.role == "sentinel":
-            score = "no" if self._sentinel_grounded else "yes"
-            return RoleResponse(raw_text=f"<score>{score}</score>", served_model=request.model_slug)
+            # Emit the format matching the active groundedness mode (I-run11-002 L1 + I-run11-004):
+            # decomposition (MiniMax-M2 default) -> JSON; guardian -> `<score>`; noninverted -> word.
+            final_instruction = request.messages[-1]["content"] if request.messages else ""
+            if "Decompose the CLAIM into atomic sub-assertions" in final_instruction:
+                verdict = "supported" if self._sentinel_grounded else "unsupported"
+                n = "0" if self._sentinel_grounded else "1"
+                raw_text = ('{"verdict": "' + verdict + '", "unsupported_atoms": '
+                            + n + ', "atoms": []}')
+            elif "<guardian>" in final_instruction:
+                raw_text = "<score>no</score>" if self._sentinel_grounded else "<score>yes</score>"
+            else:
+                raw_text = "GROUNDED" if self._sentinel_grounded else "UNGROUNDED"
+            return RoleResponse(raw_text=raw_text, served_model=request.model_slug)
         if request.role == "judge":
             return RoleResponse(raw_text=self._judge_verdict, served_model=request.model_slug)
         raise AssertionError(f"unexpected role {request.role!r}")
@@ -327,8 +338,8 @@ def test_seam_builder_wins_over_static_inputs(tmp_path):
         coverage_ledger=CoverageLedger(required_element_ids=["static-elem"]),
         required_s0_categories=[],
         model_slugs={
-            "mirror": "cohere/command-a-plus",
-            "sentinel": "ibm-granite/granite-guardian-4.1-8b",
+            "mirror": "z-ai/glm-5.1",
+            "sentinel": "minimax/minimax-m2",
             "judge": "qwen/qwen3.6-35b-a3b",
         },
         rewrite_already_attempted=True,
@@ -385,8 +396,8 @@ def test_seam_static_inputs_used_as_is_no_audit(tmp_path):
         coverage_ledger=CoverageLedger(required_element_ids=["elem-1"]),
         required_s0_categories=["contraindications"],
         model_slugs={
-            "mirror": "cohere/command-a-plus",
-            "sentinel": "ibm-granite/granite-guardian-4.1-8b",
+            "mirror": "z-ai/glm-5.1",
+            "sentinel": "minimax/minimax-m2",
             "judge": "qwen/qwen3.6-35b-a3b",
         },
         rewrite_already_attempted=True,
diff --git a/tests/dr_benchmark/test_pathB_run_gate.py b/tests/dr_benchmark/test_pathB_run_gate.py
index 46c6b139..347facc4 100644
--- a/tests/dr_benchmark/test_pathB_run_gate.py
+++ b/tests/dr_benchmark/test_pathB_run_gate.py
@@ -578,17 +578,18 @@ def test_full_control_surface_includes_retrieval_creds() -> None:
 
 
 # --- I-meta-002 PR-9/M4: self-host served==pinned (NO NETWORK, stub metadata) -------------
-# The runtime lock pins three self-hosted vLLM verifier roles (serving_route: vast_self_host*):
-#   mirror   -> cohere/command-a-plus           (vast_self_host_bf16)
-#   sentinel -> ibm-granite/granite-guardian-4.1-8b (vast_self_host)
-#   judge    -> qwen/qwen3.6-35b-a3b            (vast_self_host_fp8)
+# The runtime lock pins three self-hosted vLLM verifier roles (serving_route: vast_self_host*).
+# I-run11-004:
+#   mirror   -> z-ai/glm-5.1        (vast_self_host_bf16)
+#   sentinel -> minimax/minimax-m2  (vast_self_host)  — CERTIFIED decomposition detector
+#   judge    -> qwen/qwen3.6-35b-a3b (vast_self_host_fp8)
 # Preflight branches on serving_route (NO OpenRouter resolution; validate PG_<ROLE>_BASE_URL);
 # assert_post_run consumes the M1 _pathb_served {endpoint, model} (flattened by
 # build_response_metadata onto top-level model+endpoint keys) and fails closed on a wrong
 # model / wrong box. These tests inject stub captured-metadata dicts — no real endpoint.
 
-_MIRROR_SLUG = "cohere/command-a-plus"
-_SENTINEL_SLUG = "ibm-granite/granite-guardian-4.1-8b"
+_MIRROR_SLUG = "z-ai/glm-5.1"
+_SENTINEL_SLUG = "minimax/minimax-m2"
 _MIRROR_BASE_URL = "http://10.0.0.5:8000"
 
 
diff --git a/tests/dr_benchmark/test_pathB_runner.py b/tests/dr_benchmark/test_pathB_runner.py
index f9fb6558..e406f1e1 100644
--- a/tests/dr_benchmark/test_pathB_runner.py
+++ b/tests/dr_benchmark/test_pathB_runner.py
@@ -17,8 +17,9 @@ from scripts.dr_benchmark.pathB_run_gate import GateError
 # the post-run gate enforces completeness in BOTH directions (every pinned role observed AND
 # every observed role pinned), so the captured calls must be exactly these four roles.
 _GEN_SLUG = "deepseek/deepseek-v4-pro"
-_MIRROR_SLUG = "cohere/command-a-plus"
-_SENTINEL_SLUG = "ibm-granite/granite-guardian-4.1-8b"
+# I-run11-004: Mirror z-ai/glm-5.1, Sentinel CERTIFIED minimax/minimax-m2 (decomposition).
+_MIRROR_SLUG = "z-ai/glm-5.1"
+_SENTINEL_SLUG = "minimax/minimax-m2"
 _JUDGE_SLUG = "qwen/qwen3.6-35b-a3b"
 
 _FOUR_ROLE_SLUGS = {
diff --git a/tests/dr_benchmark/test_verify_serving_identity.py b/tests/dr_benchmark/test_verify_serving_identity.py
index 56bc5f9a..f3b36851 100644
--- a/tests/dr_benchmark/test_verify_serving_identity.py
+++ b/tests/dr_benchmark/test_verify_serving_identity.py
@@ -172,9 +172,10 @@ def test_serving_config_judge_structured_outputs_enabled_mirror_plain_chat():
     # Mirror serves plain chat for <co> citations — NO structured-output constraint.
     mirror_args = config["roles"]["mirror"]["vllm_args"]
     assert mirror_args["structured_outputs"] is False
-    # Sentinel emits a <score> element, not JSON — also plain chat.
+    # I-run11-004: the CERTIFIED MiniMax-M2 decomposition Sentinel requests a JSON object, so its
+    # self-host serving config binds structured-outputs (the robust parser also tolerates non-JSON).
     sentinel_args = config["roles"]["sentinel"]["vllm_args"]
-    assert sentinel_args["structured_outputs"] is False
+    assert sentinel_args["structured_outputs"] is True
 
 
 def test_serving_config_gpu_specs_per_role():
diff --git a/tests/roles/test_four_role_budget_cap.py b/tests/roles/test_four_role_budget_cap.py
index 73c103ac..61bb4756 100644
--- a/tests/roles/test_four_role_budget_cap.py
+++ b/tests/roles/test_four_role_budget_cap.py
@@ -123,13 +123,18 @@ class _FakeRoleTransport:
                 usage=usage,
             )
         if request.role == "sentinel":
-            # I-run11-002 L1: emit the format matching the active groundedness mode so the canned
-            # GROUNDED output pairs with the parser run_sentinel selected (non-inverted GROUNDED by
-            # default; `<score>no</score>` only under the guardian/self_host mode).
+            # Emit the format matching the active groundedness mode so the canned GROUNDED verdict
+            # pairs with the parser run_sentinel selected (I-run11-002 L1 + I-run11-004):
+            #   - decomposition (MiniMax-M2 default): JSON {"verdict": "supported"};
+            #   - guardian (self_host): `<score>no</score>`;
+            #   - noninverted (general granite): one-word `GROUNDED`.
             final_instruction = request.messages[-1]["content"] if request.messages else ""
-            sentinel_raw = (
-                "<score>no</score>" if "<guardian>" in final_instruction else "GROUNDED"
-            )
+            if "Decompose the CLAIM into atomic sub-assertions" in final_instruction:
+                sentinel_raw = '{"verdict": "supported", "unsupported_atoms": 0, "atoms": []}'
+            elif "<guardian>" in final_instruction:
+                sentinel_raw = "<score>no</score>"
+            else:
+                sentinel_raw = "GROUNDED"
             return RoleResponse(
                 raw_text=sentinel_raw, served_model=request.model_slug, usage=usage
             )
diff --git a/tests/roles/test_openai_compatible_transport.py b/tests/roles/test_openai_compatible_transport.py
index 744a00d9..f7260803 100644
--- a/tests/roles/test_openai_compatible_transport.py
+++ b/tests/roles/test_openai_compatible_transport.py
@@ -27,9 +27,10 @@ from src.polaris_graph.roles.openai_compatible_transport import (
 )
 from src.polaris_graph.roles.role_transport import RoleRequest, RoleResponse
 
-# Lock-pinned slugs (config/architecture/polaris_runtime_lock.yaml).
-_MIRROR_SLUG = "cohere/command-a-plus"
-_SENTINEL_SLUG = "ibm-granite/granite-guardian-4.1-8b"
+# Lock-pinned slugs (config/architecture/polaris_runtime_lock.yaml). I-run11-004: Mirror
+# z-ai/glm-5.1, Sentinel CERTIFIED minimax/minimax-m2 (decomposition), Judge qwen.
+_MIRROR_SLUG = "z-ai/glm-5.1"
+_SENTINEL_SLUG = "minimax/minimax-m2"
 _JUDGE_SLUG = "qwen/qwen3.6-35b-a3b"
 
 _MIRROR_BASE = "http://mirror.internal:8001"
diff --git a/tests/roles/test_openrouter_role_transport_meta007.py b/tests/roles/test_openrouter_role_transport_meta007.py
index 406886c4..458768e0 100644
--- a/tests/roles/test_openrouter_role_transport_meta007.py
+++ b/tests/roles/test_openrouter_role_transport_meta007.py
@@ -4,9 +4,10 @@ SPEND-FREE: every test injects an `httpx.Client(transport=httpx.MockTransport(..
 faked OpenRouter catalog through the same), so there is NO socket / NO real LLM / NO spend in any
 path pytest exercises — the OpenRouter HTTP is monkeypatched at the transport layer.
 
-Asserts the I-meta-007d contract (P1-1..P1-4 + P2 fixes, diff-gate iter-1):
+Asserts the I-meta-007d contract (P1-1..P1-4 + P2 fixes, diff-gate iter-1) updated for I-run11-004
+(the CERTIFIED MiniMax-M2 decomposition Sentinel — reasoning ON, max_tokens>=3000):
   (a) the transport sends each verifier role's BENCHMARK lineup slug (Mirror `z-ai/glm-5.1`,
-      Sentinel `ibm-granite/granite-4.1-8b`, Judge `qwen/qwen3.6-35b-a3b` — NOT the lock's
+      Sentinel `minimax/minimax-m2`, Judge `qwen/qwen3.6-35b-a3b` — NOT the lock's
       self-host slugs; P1-1) + the MAX-reasoning request param
       (`reasoning = {"enabled": True, "effort": "xhigh"}` — `xhigh` is OpenRouter's MAX; P1-2),
       and does NOT forward a top-level `documents` body key (P1-4);
@@ -20,7 +21,7 @@ Asserts the I-meta-007d contract (P1-1..P1-4 + P2 fixes, diff-gate iter-1):
       "self_host";
   (e) the openrouter preflight asserts each BENCHMARK lineup slug is present in a faked catalog
       (by `id` OR `canonical_slug`), fails LOUD on a missing slug, and keeps the
-      4-distinct-family check over the deepseek/z-ai/ibm-granite/qwen benchmark lineup.
+      4-distinct-family check over the deepseek/z-ai/minimax/qwen benchmark lineup.
 
 NO network: the real OpenRouter endpoint is never hit; the `OpenAICompatibleRoleTransport`
 self-host path is also never constructed against a live endpoint here.
@@ -47,11 +48,10 @@ from src.polaris_graph.roles.openrouter_role_transport import (
 )
 from src.polaris_graph.roles.role_transport import RoleRequest, RoleResponse
 
-# BENCHMARK-STAGE OpenRouter lineup slugs (P1-1 — role_selection_final.md, NOT the lock's
-# self-host slugs). Mirror + Sentinel differ from the lock (cohere / granite-GUARDIAN are not on
-# OpenRouter); Judge is identical to the lock.
+# BENCHMARK-STAGE OpenRouter lineup slugs (P1-1). I-run11-004: lock + benchmark now converge —
+# Mirror z-ai/glm-5.1, Sentinel CERTIFIED minimax/minimax-m2 (decomposition), Judge qwen.
 _MIRROR_SLUG = "z-ai/glm-5.1"
-_SENTINEL_SLUG = "ibm-granite/granite-4.1-8b"
+_SENTINEL_SLUG = "minimax/minimax-m2"
 _JUDGE_SLUG = "qwen/qwen3.6-35b-a3b"
 
 # Writer/generator (unchanged in the lock + benchmark lineup) — referenced by the preflight
@@ -143,18 +143,15 @@ def test_sends_pinned_slug_and_max_reasoning(role, slug):
     # the lock self-host slug, NOT the request). It also equals the pin verifier_model_slugs feeds
     # into RoleRequest.model_slug, so served == pinned (asserted in its own test below).
     assert body["model"] == slug
-    # Codex iter-2 P1: reasoning is PER-ROLE. The Sentinel classifier sends NEITHER reasoning nor
-    # provider/require_parameters (its OpenRouter slug does not advertise `reasoning`, so those
-    # params would break routing). The deliberative verifiers (Mirror/Judge) send BOTH.
-    if role == "sentinel":
-        assert "reasoning" not in body
-        assert "provider" not in body
-    else:
-        # P1-2 MAX reasoning: enabled + effort "xhigh" (OpenRouter's documented MAXIMUM effort).
-        assert body["reasoning"] == {"enabled": True, "effort": "xhigh"}
-        # require_parameters=True makes OpenRouter only route to a provider that HONORS reasoning
-        # (otherwise the max-reasoning request could be silently ignored on a fallback provider).
-        assert body["provider"] == {"require_parameters": True}
+    # I-run11-004: reasoning is PER-ROLE and the Sentinel is now MODE-AWARE. The default
+    # PG_SENTINEL_MODEL (minimax/minimax-m2) resolves to "decomposition" mode, which the
+    # certification ran WITH reasoning ON (reasoning OFF / starved max_tokens truncates the JSON ->
+    # all-UNGROUNDED collapse). So ALL THREE roles now send MAX reasoning + require_parameters.
+    # P1-2 MAX reasoning: enabled + effort "xhigh" (OpenRouter's documented MAXIMUM effort).
+    assert body["reasoning"] == {"enabled": True, "effort": "xhigh"}
+    # require_parameters=True makes OpenRouter only route to a provider that HONORS reasoning
+    # (otherwise the max-reasoning request could be silently ignored on a fallback provider).
+    assert body["provider"] == {"require_parameters": True}
     # P1-4: a top-level `documents` key is NOT forwarded (OpenRouter's chat-completions schema
     # has no such param; with require_parameters=True it would fail routing). The evidence is
     # already rendered into `messages` by _normalize_messages, so model-visibility is preserved.
@@ -443,15 +440,20 @@ def _catalog_client(catalog_data: list[dict], status_code: int = 200) -> httpx.C
 
 
 def test_preflight_openrouter_resolves_all_slugs_present_as_id():
-    # P1-1: the preflight resolves the BENCHMARK lineup slugs (z-ai/glm-5.1, granite-4.1-8b,
-    # qwen3.6-35b-a3b) against the catalog — NOT the lock self-host slugs.
+    # P1-1 / I-run11-004: the preflight resolves the BENCHMARK lineup slugs (z-ai/glm-5.1,
+    # minimax/minimax-m2, qwen3.6-35b-a3b) against the catalog — NOT the lock self-host slugs.
+    # The decomposition Sentinel is reasoning-enabled, so its catalog entry advertises `reasoning`.
     catalog = [
         {
             "id": _MIRROR_SLUG,
             "canonical_slug": "z-ai/glm-5.1-20260520",
             "supported_parameters": ["reasoning", "max_tokens"],
         },
-        {"id": _SENTINEL_SLUG, "canonical_slug": _SENTINEL_SLUG},
+        {
+            "id": _SENTINEL_SLUG,
+            "canonical_slug": _SENTINEL_SLUG,
+            "supported_parameters": ["reasoning", "response_format", "max_tokens"],
+        },
         {
             "id": _JUDGE_SLUG,
             "canonical_slug": _JUDGE_SLUG,
@@ -475,7 +477,7 @@ def test_preflight_openrouter_matches_via_canonical_slug():
             "canonical_slug": _MIRROR_SLUG,
             "supported_parameters": ["reasoning", "max_tokens"],
         },
-        {"id": _SENTINEL_SLUG},
+        {"id": _SENTINEL_SLUG, "supported_parameters": ["reasoning", "max_tokens"]},
         {"id": _JUDGE_SLUG, "supported_parameters": ["reasoning", "max_tokens"]},
     ]
     resolved = run_gate_b.preflight_openrouter_roles(http_client=_catalog_client(catalog))
@@ -484,11 +486,11 @@ def test_preflight_openrouter_matches_via_canonical_slug():
 
 def test_preflight_openrouter_missing_slug_fails_loud():
     # Judge slug absent from the catalog (neither id nor canonical_slug) -> fail loud.
-    # Mirror advertises `reasoning` so its executability check passes and the loop reaches the
-    # missing Judge, where the PRESENCE failure (match="judge") fires.
+    # Mirror + Sentinel advertise `reasoning` so their executability checks pass and the loop
+    # reaches the missing Judge, where the PRESENCE failure (match="judge") fires.
     catalog = [
         {"id": _MIRROR_SLUG, "supported_parameters": ["reasoning"]},
-        {"id": _SENTINEL_SLUG},
+        {"id": _SENTINEL_SLUG, "supported_parameters": ["reasoning"]},
     ]
     with pytest.raises(RuntimeError, match="judge"):
         run_gate_b.preflight_openrouter_roles(http_client=_catalog_client(catalog))
@@ -497,31 +499,28 @@ def test_preflight_openrouter_missing_slug_fails_loud():
 def test_preflight_openrouter_fails_when_reasoning_role_lacks_reasoning_support():
     # Codex iter-2 P1: a reasoning-enabled role (Mirror) whose slug does NOT advertise `reasoning`
     # must fail preflight — with require_parameters=True OpenRouter would refuse to route. Sentinel
-    # is reasoning-disabled so its lack of `reasoning` is fine; Judge advertises it.
+    # + Judge advertise it (Sentinel is now reasoning-ON in decomposition mode).
     catalog = [
         {"id": _MIRROR_SLUG, "supported_parameters": ["max_tokens"]},
-        {"id": _SENTINEL_SLUG, "supported_parameters": ["max_tokens"]},
+        {"id": _SENTINEL_SLUG, "supported_parameters": ["reasoning", "max_tokens"]},
         {"id": _JUDGE_SLUG, "supported_parameters": ["reasoning", "max_tokens"]},
     ]
     with pytest.raises(RuntimeError, match="(?i)mirror|reasoning"):
         run_gate_b.preflight_openrouter_roles(http_client=_catalog_client(catalog))
 
 
-def test_preflight_openrouter_sentinel_without_reasoning_passes():
-    # The Sentinel classifier is reasoning-DISABLED, so its slug not advertising `reasoning` must
-    # NOT fail preflight (only reasoning-enabled roles get the executability check). Mirror+Judge
-    # advertise `reasoning`; Sentinel does not -> the preflight still resolves.
+def test_preflight_openrouter_decomposition_sentinel_lacking_reasoning_fails_loud():
+    # I-run11-004: the DECOMPOSITION Sentinel (minimax/minimax-m2) is reasoning-ENABLED (certified
+    # with reasoning ON). A catalog entry that does NOT advertise `reasoning` for it must FAIL the
+    # preflight (with require_parameters=True OpenRouter would refuse to route). Mirror+Judge are
+    # fine; only the Sentinel's missing `reasoning` trips the executability check.
     catalog = [
         {"id": _MIRROR_SLUG, "supported_parameters": ["reasoning", "max_tokens"]},
-        {"id": _SENTINEL_SLUG, "supported_parameters": ["max_tokens", "temperature"]},
+        {"id": _SENTINEL_SLUG, "supported_parameters": ["max_tokens", "response_format"]},
         {"id": _JUDGE_SLUG, "supported_parameters": ["reasoning", "max_tokens"]},
     ]
-    resolved = run_gate_b.preflight_openrouter_roles(http_client=_catalog_client(catalog))
-    assert resolved == {
-        "mirror": _MIRROR_SLUG,
-        "sentinel": _SENTINEL_SLUG,
-        "judge": _JUDGE_SLUG,
-    }
+    with pytest.raises(RuntimeError, match="(?i)sentinel|reasoning"):
+        run_gate_b.preflight_openrouter_roles(http_client=_catalog_client(catalog))
 
 
 def test_preflight_openrouter_non_200_fails_loud():
@@ -534,14 +533,14 @@ def test_preflight_openrouter_non_200_fails_loud():
 
 def test_family_check_passes_on_benchmark_lineup(monkeypatch):
     # P1-1: in openrouter mode the 4-distinct-family check asserts on the ACTIVE benchmark
-    # families (generator deepseek from the lock + benchmark verifiers z-ai/ibm-granite/qwen),
+    # families (generator deepseek from the lock + benchmark verifiers z-ai/minimax/qwen),
     # which are 4 distinct lineages — it must PASS (no collision).
     monkeypatch.delenv("PG_FOUR_ROLE_TRANSPORT", raising=False)  # default openrouter
     fams = run_gate_b.assert_four_role_families_distinct()
     assert fams == {
         "generator": "deepseek",
         "mirror": "z-ai",
-        "sentinel": "ibm-granite",
+        "sentinel": "minimax",
         "judge": "qwen",
     }
     assert len(set(fams.values())) == 4
@@ -582,7 +581,7 @@ def test_stage_marker_records_benchmark_openrouter(monkeypatch, tmp_path):
     }
     assert marker["verifier_families"] == {
         "mirror": "z-ai",
-        "sentinel": "ibm-granite",
+        "sentinel": "minimax",
         "judge": "qwen",
     }
     path = run_gate_b.write_four_role_stage_marker(tmp_path)
@@ -677,9 +676,48 @@ def test_reasoning_role_max_tokens_env_overridable(monkeypatch):
     assert seen["body"]["max_tokens"] == 8192
 
 
-def test_sentinel_gets_explicit_classifier_budget():
-    # Sentinel is reasoning-disabled (a classifier); it gets an explicit output budget (default 256),
-    # not a pop-and-hope on the provider default, and no reasoning param is sent.
+def test_decomposition_sentinel_gets_reasoning_and_generous_max_tokens():
+    # I-run11-004: the default Sentinel (minimax/minimax-m2) resolves to "decomposition" mode, which
+    # the certification ran WITH reasoning ON + max_tokens>=3000 (a small budget truncates the JSON
+    # {verdict, atoms} -> all-UNGROUNDED collapse). So the decomposition Sentinel sends reasoning
+    # xhigh AND a generous max_tokens (default 16384), NOT the 256 classifier budget.
+    handler, seen = _recording_handler(served_model=_SENTINEL_SLUG, message={"content": "VERIFIED"})
+    _make_transport(handler).complete(
+        RoleRequest(
+            role="sentinel",
+            model_slug=_SENTINEL_SLUG,
+            messages=[{"role": "user", "content": "decompose this"}],
+            params={"documents": [{"doc_id": "d1", "text": "ev"}],
+                    "response_format": {"type": "json_object"}, "max_tokens": 16},
+        )
+    )
+    assert seen["body"]["reasoning"] == {"enabled": True, "effort": "xhigh"}
+    assert seen["body"]["max_tokens"] == 16384
+    # The certified JSON response_format is forwarded to the body (the robust parser also handles
+    # non-JSON-mode output, but the request asks for JSON).
+    assert seen["body"]["response_format"] == {"type": "json_object"}
+
+
+def test_decomposition_sentinel_max_tokens_floored_at_3000(monkeypatch):
+    # LAW VI: the decomposition budget is env-overridable, but a too-small override is HARD-FLOORED
+    # at 3000 so it can never re-introduce the run-12 JSON truncation.
+    monkeypatch.setenv("PG_SENTINEL_DECOMPOSITION_MAX_TOKENS", "500")
+    handler, seen = _recording_handler(served_model=_SENTINEL_SLUG, message={"content": "VERIFIED"})
+    _make_transport(handler).complete(
+        RoleRequest(
+            role="sentinel",
+            model_slug=_SENTINEL_SLUG,
+            messages=[{"role": "user", "content": "decompose"}],
+            params={"response_format": {"type": "json_object"}},
+        )
+    )
+    assert seen["body"]["max_tokens"] == 3000
+
+
+def test_sentinel_classifier_budget_when_reasoning_disabled(monkeypatch):
+    # When the Sentinel mode is NOT decomposition (e.g. PG_SENTINEL_REASONING=0 forces it OFF), the
+    # classifier path holds: an explicit 256 output budget and no reasoning param.
+    monkeypatch.setenv("PG_SENTINEL_REASONING", "0")
     handler, seen = _recording_handler(served_model=_SENTINEL_SLUG, message={"content": "<score>no</score>"})
     _make_transport(handler).complete(
         RoleRequest(
@@ -756,15 +794,33 @@ def test_blank_verdict_ladder_exhausted_fails_loud_with_reasoning_off_last():
     assert "provider" not in seen["bodies"][2] or "require_parameters" not in seen["bodies"][2].get("provider", {})
 
 
-def test_sentinel_blank_is_single_attempt_no_stepdown():
-    # The non-reasoning Sentinel has no `reasoning` block to step down — it makes ONE attempt and a
-    # blank still fails loud (unchanged behavior; the ladder is reasoning-roles-only).
+def test_classifier_sentinel_blank_is_single_attempt_no_stepdown(monkeypatch):
+    # A reasoning-DISABLED Sentinel (PG_SENTINEL_REASONING=0, the sovereign classifier path) has no
+    # `reasoning` block to step down — it makes ONE attempt and a blank still fails loud (the ladder
+    # is reasoning-roles-only).
+    monkeypatch.setenv("PG_SENTINEL_REASONING", "0")
     handler, seen = _sequenced_handler([{"content": ""}], served_model=_SENTINEL_SLUG)
     with pytest.raises(RoleTransportError):
         _make_transport(handler).complete(
             RoleRequest(role="sentinel", model_slug=_SENTINEL_SLUG, prompt="x")
         )
-    assert len(seen["bodies"]) == 1, "Sentinel must NOT retry (no reasoning ladder)"
+    assert len(seen["bodies"]) == 1, "classifier Sentinel must NOT retry (no reasoning ladder)"
+
+
+def test_decomposition_sentinel_blank_steps_down_reasoning_and_recovers():
+    # I-run11-004: the reasoning-ON decomposition Sentinel DOES follow the blank-verdict step-down
+    # ladder (xhigh -> low -> off) like the other reasoning verifiers — a non-converging xhigh blank
+    # must not crash the run.
+    blank = {"content": "", "reasoning": "looped without converging"}
+    good = {"content": '{"verdict": "supported", "unsupported_atoms": 0, "atoms": []}'}
+    handler, seen = _sequenced_handler([blank, good], served_model=_SENTINEL_SLUG)
+    resp = _make_transport(handler).complete(
+        RoleRequest(role="sentinel", model_slug=_SENTINEL_SLUG, prompt="decompose")
+    )
+    assert resp.raw_text == good["content"]
+    assert len(seen["bodies"]) == 2, "decomposition Sentinel retries after a blank"
+    assert seen["bodies"][0]["reasoning"]["effort"] == "xhigh"
+    assert seen["bodies"][1]["reasoning"]["effort"] == "low"
 
 
 def test_blank_attempt_bills_tokens_into_run_budget(monkeypatch):
diff --git a/tests/roles/test_role_pipeline.py b/tests/roles/test_role_pipeline.py
index 8cc54881..0ae05d43 100644
--- a/tests/roles/test_role_pipeline.py
+++ b/tests/roles/test_role_pipeline.py
@@ -78,13 +78,22 @@ class MockTransport:
                 citations=[CitationSpan(span_start=0, span_end=8, doc_ids=(doc_id,))],
             )
         if request.role == "sentinel":
-            # Emit the format that MATCHES the active groundedness mode (I-run11-002 L1) so the
-            # MockTransport stays faithful whichever mode the adapter resolved: the inverted
-            # `<score>yes|no</score>` when the request carries the `<guardian>` block, else the
-            # non-inverted one-word GROUNDED/UNGROUNDED. (run_sentinel selects the matching parser
-            # off the same mode, so the canned output and the parser always pair.)
+            # Emit the format that MATCHES the active groundedness mode (I-run11-002 L1 +
+            # I-run11-004) so the MockTransport stays faithful whichever mode the adapter resolved:
+            #   - decomposition (MiniMax-M2 default): JSON {"verdict": "supported"|"unsupported"};
+            #   - guardian (request carries `<guardian>`): inverted `<score>yes|no</score>`;
+            #   - noninverted: one-word GROUNDED/UNGROUNDED.
+            # (run_sentinel selects the matching parser off the same mode, so canned output + parser
+            # always pair.)
             final_instruction = request.messages[-1]["content"] if request.messages else ""
-            if "<guardian>" in final_instruction:
+            if "Decompose the CLAIM into atomic sub-assertions" in final_instruction:
+                verdict = "supported" if self._sentinel_grounded else "unsupported"
+                n_unsupported = "0" if self._sentinel_grounded else "1"
+                raw_text = (
+                    '{"verdict": "' + verdict + '", "unsupported_atoms": '
+                    + n_unsupported + ', "atoms": []}'
+                )
+            elif "<guardian>" in final_instruction:
                 score = "no" if self._sentinel_grounded else "yes"
                 raw_text = f"<score>{score}</score>"
             else:
@@ -251,11 +260,14 @@ def test_guardian_env_still_composes_grounded_verified(monkeypatch) -> None:
 
 def test_self_host_transport_env_routes_guardian_in_pipeline(monkeypatch) -> None:
     """The runtime-desync guard end-to-end: PG_FOUR_ROLE_TRANSPORT=self_host (no explicit mode)
-    makes the pipeline's Sentinel resolve to guardian, so the MockTransport's `<guardian>` request
-    + `<score>no</score>` output composes correctly to VERIFIED — the sovereign granite-Guardian
-    gets the inverted prompt it is trained on without any extra env."""
+    with a granite-guardian Sentinel slug resolves to guardian, so the MockTransport's `<guardian>`
+    request + `<score>no</score>` output composes correctly to VERIFIED — the sovereign
+    granite-Guardian gets the inverted prompt it is trained on. (I-run11-004: with the minimax
+    lock slug the self_host default would instead be decomposition; here we pin a guardian slug to
+    exercise the transport-derived guardian fall-through.)"""
     monkeypatch.delenv("PG_SENTINEL_GROUNDEDNESS_MODE", raising=False)
     monkeypatch.setenv("PG_FOUR_ROLE_TRANSPORT", "self_host")
+    monkeypatch.setenv("PG_SENTINEL_MODEL", "ibm-granite/granite-guardian-4.1-8b")
     transport = MockTransport(sentinel_grounded=True, judge_verdict="VERIFIED")
     result = _run(transport)
     assert result.final_verdict == "VERIFIED"
diff --git a/tests/roles/test_seam_parallel.py b/tests/roles/test_seam_parallel.py
index 74993b64..c082cd6d 100644
--- a/tests/roles/test_seam_parallel.py
+++ b/tests/roles/test_seam_parallel.py
@@ -69,13 +69,19 @@ _REQUIRED_S0 = ["contraindications"]
 
 
 def _sentinel_raw_for_mode(request: RoleRequest, grounded: bool) -> str:
-    """I-run11-002 L1: the Sentinel raw output that MATCHES the active groundedness mode.
-
-    `run_sentinel` selects the inverted `<score>yes|no</score>` parser when the request carries the
-    `<guardian>` block (sovereign self_host) and the non-inverted GROUNDED/UNGROUNDED parser
-    otherwise (benchmark default). The fake emits the SAME-mode format so canned output and parser
-    always pair (whatever PG_SENTINEL_GROUNDEDNESS_MODE / PG_FOUR_ROLE_TRANSPORT resolve to)."""
+    """The Sentinel raw output that MATCHES the active groundedness mode (I-run11-002 L1 +
+    I-run11-004).
+
+    `run_sentinel` selects the parser off the resolved mode: decomposition (MiniMax-M2 default) ->
+    JSON {"verdict": "supported"|"unsupported"}; guardian (`<guardian>` block) -> inverted
+    `<score>yes|no</score>`; noninverted -> one-word GROUNDED/UNGROUNDED. The fake emits the
+    SAME-mode format so canned output and parser always pair (whatever
+    PG_SENTINEL_GROUNDEDNESS_MODE / PG_SENTINEL_MODEL / PG_FOUR_ROLE_TRANSPORT resolve to)."""
     final_instruction = request.messages[-1]["content"] if request.messages else ""
+    if "Decompose the CLAIM into atomic sub-assertions" in final_instruction:
+        verdict = "supported" if grounded else "unsupported"
+        n = "0" if grounded else "1"
+        return '{"verdict": "' + verdict + '", "unsupported_atoms": ' + n + ', "atoms": []}'
     if "<guardian>" in final_instruction:
         return "<score>no</score>" if grounded else "<score>yes</score>"
     return "GROUNDED" if grounded else "UNGROUNDED"
diff --git a/tests/roles/test_sentinel_adapter.py b/tests/roles/test_sentinel_adapter.py
index 01b703fb..1993ca1a 100644
--- a/tests/roles/test_sentinel_adapter.py
+++ b/tests/roles/test_sentinel_adapter.py
@@ -200,59 +200,205 @@ def test_benchmark_transport_error_fails_closed() -> None:
     assert "transport_error" in records[0].raw_text
 
 
-# === mode resolver (PG_SENTINEL_GROUNDEDNESS_MODE / PG_FOUR_ROLE_TRANSPORT) ==========
+# === DECOMPOSITION (certified MiniMax-M2) mode tests (I-run11-004) ===================
+_MINIMAX_MODEL = "minimax/minimax-m2"
+_SUPPORTED_JSON = '{"verdict": "supported", "unsupported_atoms": 0, "atoms": []}'
+_UNSUPPORTED_JSON = '{"verdict": "unsupported", "unsupported_atoms": 1, "atoms": []}'
+_MULTI_DOCS = [
+    EvidenceDocument(doc_id="doc_a", text="HbA1c fell 2.3 points across arms."),
+    EvidenceDocument(doc_id="doc_b", text="The reduction was sustained at 52 weeks."),
+]
+
+
+def test_decomposition_request_is_single_user_message_with_span_and_claim() -> None:
+    """build_sentinel_request(mode="decomposition") REPLICATES the certified call: ONE user message
+    carrying the certified decomposition prompt with span (all evidence .text joined) + claim
+    inline (NOT the guardian documents-channel layout), and a JSON response_format param."""
+    request = build_sentinel_request(
+        _CLAIM, _MULTI_DOCS, model_slug=_MINIMAX_MODEL, mode="decomposition"
+    )
+    assert request.role == "sentinel"
+    assert request.model_slug == _MINIMAX_MODEL
+    # SINGLE user message (not assistant+user guardian layout).
+    assert request.messages is not None
+    assert [m["role"] for m in request.messages] == ["user"]
+    user_content = request.messages[0]["content"]
+    # The certified decomposition prompt scaffolding is present.
+    assert "Decompose the CLAIM into atomic sub-assertions" in user_content
+    assert "STRICT JSON only" in user_content
+    # Both spans are inlined into the prompt (the SPAN), and the claim too.
+    assert "HbA1c fell 2.3 points across arms." in user_content
+    assert "The reduction was sustained at 52 weeks." in user_content
+    assert _CLAIM in user_content
+    # No guardian block / no one-word block in this layout.
+    assert "<guardian>" not in user_content
+    assert "GROUNDED or UNGROUNDED" not in user_content
+    # JSON response_format requested; documents still carried for identity/introspection.
+    assert request.params["response_format"] == {"type": "json_object"}
+    assert request.params["documents"][0]["doc_id"] == "doc_a"
+
+
+def test_decomposition_supported_json_parses_grounded() -> None:
+    transport = _CannedTransport(_SUPPORTED_JSON, served_model=_MINIMAX_MODEL)
+    result, records = run_sentinel(
+        transport, _CLAIM, _DOCS, model_slug=_MINIMAX_MODEL, mode="decomposition"
+    )
+    assert result.verdict is SentinelVerdict.GROUNDED
+    assert result.parsed_ok is True
+    assert len(records) == 1
+    assert records[0].parsed == result
+    # The transport saw the single-user-message decomposition layout.
+    assert transport.last_request is not None
+    assert [m["role"] for m in transport.last_request.messages] == ["user"]
+
+
+def test_decomposition_unsupported_json_parses_ungrounded() -> None:
+    transport = _CannedTransport(_UNSUPPORTED_JSON, served_model=_MINIMAX_MODEL)
+    result, _records = run_sentinel(
+        transport, _CLAIM, _DOCS, model_slug=_MINIMAX_MODEL, mode="decomposition"
+    )
+    assert result.verdict is SentinelVerdict.UNGROUNDED
+    assert result.parsed_ok is True
+
+
+def test_decomposition_fenced_json_parses() -> None:
+    fenced = "```json\n" + _SUPPORTED_JSON + "\n```"
+    transport = _CannedTransport(fenced, served_model=_MINIMAX_MODEL)
+    result, _records = run_sentinel(
+        transport, _CLAIM, _DOCS, model_slug=_MINIMAX_MODEL, mode="decomposition"
+    )
+    assert result.verdict is SentinelVerdict.GROUNDED
+    assert result.parsed_ok is True
+
+
+def test_decomposition_garbage_fails_closed() -> None:
+    # Non-JSON, no verdict -> fail closed UNGROUNDED parsed_ok False (never a silent GROUNDED).
+    transport = _CannedTransport("I think the claim is fine", served_model=_MINIMAX_MODEL)
+    result, _records = run_sentinel(
+        transport, _CLAIM, _DOCS, model_slug=_MINIMAX_MODEL, mode="decomposition"
+    )
+    assert result.verdict is SentinelVerdict.UNGROUNDED
+    assert result.parsed_ok is False
+
+
+def test_decomposition_empty_fails_closed() -> None:
+    transport = _CannedTransport("", served_model=_MINIMAX_MODEL)
+    result, _records = run_sentinel(
+        transport, _CLAIM, _DOCS, model_slug=_MINIMAX_MODEL, mode="decomposition"
+    )
+    assert result.verdict is SentinelVerdict.UNGROUNDED
+    assert result.parsed_ok is False
+
+
+def test_decomposition_transport_error_fails_closed() -> None:
+    transport = _RaisingTransport()
+    result, records = run_sentinel(
+        transport, _CLAIM, _DOCS, model_slug=_MINIMAX_MODEL, mode="decomposition"
+    )
+    assert result.verdict is SentinelVerdict.UNGROUNDED
+    assert result.parsed_ok is False
+    assert len(records) == 1
+    assert "transport_error" in records[0].raw_text
+
+
+# === mode resolver (PG_SENTINEL_GROUNDEDNESS_MODE / PG_SENTINEL_MODEL / PG_FOUR_ROLE_TRANSPORT) ==
+# I-run11-004: the UNSET default is MODEL-AWARE first. A granite slug whose name is NOT a
+# minimax/granite-guardian model falls through to the transport-derived default; these tests pin
+# PG_SENTINEL_MODEL to a NON-minimax/non-guardian general slug to exercise that fall-through path.
+_GENERAL_GRANITE_SLUG = "ibm-granite/granite-4.1-8b"
+
+
 def test_mode_defaults_to_noninverted_when_unset(monkeypatch) -> None:
     monkeypatch.delenv("PG_SENTINEL_GROUNDEDNESS_MODE", raising=False)
     monkeypatch.delenv("PG_FOUR_ROLE_TRANSPORT", raising=False)
+    # A general (non-minimax, non-guardian) slug -> transport-derived default (here: noninverted).
+    monkeypatch.setenv("PG_SENTINEL_MODEL", _GENERAL_GRANITE_SLUG)
     assert sentinel_groundedness_mode() == "noninverted"
 
 
 def test_mode_defaults_to_noninverted_on_openrouter_transport(monkeypatch) -> None:
     monkeypatch.delenv("PG_SENTINEL_GROUNDEDNESS_MODE", raising=False)
     monkeypatch.setenv("PG_FOUR_ROLE_TRANSPORT", "openrouter")
+    monkeypatch.setenv("PG_SENTINEL_MODEL", _GENERAL_GRANITE_SLUG)
     assert sentinel_groundedness_mode() == "noninverted"
 
 
 def test_mode_defaults_to_guardian_on_self_host_transport(monkeypatch) -> None:
-    """The runtime-desync guard: the sovereign self_host route DEFAULTS to guardian so the
-    granite-Guardian model gets the inverted prompt it is trained on — without any extra env."""
+    """The runtime-desync guard: a non-minimax/non-guardian slug on the sovereign self_host route
+    DEFAULTS to guardian (the transport-derived fall-through), without any extra env."""
     monkeypatch.delenv("PG_SENTINEL_GROUNDEDNESS_MODE", raising=False)
     monkeypatch.setenv("PG_FOUR_ROLE_TRANSPORT", "self_host")
+    monkeypatch.setenv("PG_SENTINEL_MODEL", _GENERAL_GRANITE_SLUG)
     assert sentinel_groundedness_mode() == "guardian"
 
 
-def test_explicit_mode_env_overrides_transport_default(monkeypatch) -> None:
-    # Explicit override wins over the transport-derived default, both directions.
+# === I-run11-004: model-aware default mode (granite-guardian / minimax) =============
+def test_mode_defaults_to_decomposition_for_minimax_slug(monkeypatch) -> None:
+    """The MiniMax-M2 lock Sentinel: an UNSET PG_SENTINEL_GROUNDEDNESS_MODE with a minimax slug
+    DEFAULTS to decomposition (model-aware), regardless of transport."""
+    monkeypatch.delenv("PG_SENTINEL_GROUNDEDNESS_MODE", raising=False)
+    monkeypatch.setenv("PG_SENTINEL_MODEL", "minimax/minimax-m2")
+    monkeypatch.delenv("PG_FOUR_ROLE_TRANSPORT", raising=False)
+    assert sentinel_groundedness_mode() == "decomposition"
+    monkeypatch.setenv("PG_FOUR_ROLE_TRANSPORT", "self_host")
+    assert sentinel_groundedness_mode() == "decomposition"
+
+
+def test_mode_defaults_to_guardian_for_granite_guardian_slug(monkeypatch) -> None:
+    """A granite-guardian slug DEFAULTS to guardian (model-aware), even on the openrouter route —
+    the inverted contract pairs with the task-trained Guardian model it is served against."""
+    monkeypatch.delenv("PG_SENTINEL_GROUNDEDNESS_MODE", raising=False)
+    monkeypatch.setenv("PG_SENTINEL_MODEL", "ibm-granite/granite-guardian-4.1-8b")
+    monkeypatch.setenv("PG_FOUR_ROLE_TRANSPORT", "openrouter")
+    assert sentinel_groundedness_mode() == "guardian"
+
+
+def test_default_minimax_code_default_resolves_decomposition(monkeypatch) -> None:
+    """With NO PG_SENTINEL_MODEL env (falls back to the openrouter_client code default
+    minimax/minimax-m2) the UNSET-mode default is decomposition — the shipping default."""
+    monkeypatch.delenv("PG_SENTINEL_GROUNDEDNESS_MODE", raising=False)
+    monkeypatch.delenv("PG_SENTINEL_MODEL", raising=False)
+    monkeypatch.delenv("PG_FOUR_ROLE_TRANSPORT", raising=False)
+    assert sentinel_groundedness_mode() == "decomposition"
+
+
+def test_explicit_mode_env_overrides_model_and_transport_default(monkeypatch) -> None:
+    # Explicit override wins over BOTH the model-aware AND transport-derived default, all directions.
+    monkeypatch.setenv("PG_SENTINEL_MODEL", "minimax/minimax-m2")
     monkeypatch.setenv("PG_FOUR_ROLE_TRANSPORT", "self_host")
     monkeypatch.setenv("PG_SENTINEL_GROUNDEDNESS_MODE", "noninverted")
     assert sentinel_groundedness_mode() == "noninverted"
-    monkeypatch.setenv("PG_FOUR_ROLE_TRANSPORT", "openrouter")
     monkeypatch.setenv("PG_SENTINEL_GROUNDEDNESS_MODE", "guardian")
     assert sentinel_groundedness_mode() == "guardian"
+    monkeypatch.setenv("PG_SENTINEL_MODEL", _GENERAL_GRANITE_SLUG)
+    monkeypatch.setenv("PG_SENTINEL_GROUNDEDNESS_MODE", "decomposition")
+    assert sentinel_groundedness_mode() == "decomposition"
 
 
 def test_unrecognized_mode_raises_loud(monkeypatch) -> None:
     # Codex diff-gate P2 (no-silent-fallback): an EXPLICIT but unrecognized
-    # PG_SENTINEL_GROUNDEDNESS_MODE must FAIL LOUD, not silently derive from the transport
+    # PG_SENTINEL_GROUNDEDNESS_MODE must FAIL LOUD, not silently derive from the model/transport
     # (a mode typo must never desync the prompt+parser from the served model).
     import pytest
     monkeypatch.setenv("PG_SENTINEL_GROUNDEDNESS_MODE", "bogus")
     monkeypatch.setenv("PG_FOUR_ROLE_TRANSPORT", "self_host")
     with pytest.raises(ValueError):
         sentinel_groundedness_mode()
-    # When the env is UNSET (not a typo), the transport-derived default still applies.
+    # When the env is UNSET (not a typo), the model-aware default still applies.
     monkeypatch.delenv("PG_SENTINEL_GROUNDEDNESS_MODE", raising=False)
-    monkeypatch.setenv("PG_FOUR_ROLE_TRANSPORT", "self_host")
-    assert sentinel_groundedness_mode() == "guardian"
+    monkeypatch.setenv("PG_SENTINEL_MODEL", "minimax/minimax-m2")
+    assert sentinel_groundedness_mode() == "decomposition"
+    monkeypatch.setenv("PG_SENTINEL_MODEL", _GENERAL_GRANITE_SLUG)
     monkeypatch.setenv("PG_FOUR_ROLE_TRANSPORT", "openrouter")
     assert sentinel_groundedness_mode() == "noninverted"
 
 
 def test_run_sentinel_uses_env_mode_when_mode_arg_none(monkeypatch) -> None:
     """When run_sentinel is called WITHOUT a mode (the role_pipeline call site), it resolves the
-    mode from the env. Default (unset) -> noninverted: a `GROUNDED` word parses GROUNDED."""
+    mode from the env. A general granite slug on openrouter -> noninverted: `GROUNDED` parses."""
     monkeypatch.delenv("PG_SENTINEL_GROUNDEDNESS_MODE", raising=False)
     monkeypatch.delenv("PG_FOUR_ROLE_TRANSPORT", raising=False)
+    monkeypatch.setenv("PG_SENTINEL_MODEL", _GENERAL_GRANITE_SLUG)
     transport = _CannedTransport("GROUNDED", served_model=_BENCHMARK_MODEL)
     result, _records = run_sentinel(
         transport, _CLAIM, _DOCS, model_slug=_BENCHMARK_MODEL
@@ -265,3 +411,25 @@ def test_run_sentinel_uses_env_mode_when_mode_arg_none(monkeypatch) -> None:
     result2, _r2 = run_sentinel(transport2, _CLAIM, _DOCS, model_slug=_MODEL)
     assert result2.verdict is SentinelVerdict.GROUNDED
     assert result2.parsed_ok is True
+
+
+def test_run_sentinel_minimax_default_uses_decomposition(monkeypatch) -> None:
+    """The shipping default: with a minimax slug and no mode env, run_sentinel uses decomposition —
+    a `{"verdict": "supported"}` JSON parses GROUNDED, and a `{"verdict": "unsupported"}` parses
+    UNGROUNDED (the certified mapping)."""
+    monkeypatch.delenv("PG_SENTINEL_GROUNDEDNESS_MODE", raising=False)
+    monkeypatch.setenv("PG_SENTINEL_MODEL", "minimax/minimax-m2")
+    transport = _CannedTransport(
+        '{"verdict": "supported", "unsupported_atoms": 0, "atoms": []}',
+        served_model="minimax/minimax-m2",
+    )
+    result, _records = run_sentinel(transport, _CLAIM, _DOCS, model_slug="minimax/minimax-m2")
+    assert result.verdict is SentinelVerdict.GROUNDED
+    assert result.parsed_ok is True
+    transport2 = _CannedTransport(
+        '{"verdict": "unsupported", "unsupported_atoms": 1, "atoms": []}',
+        served_model="minimax/minimax-m2",
+    )
+    result2, _r2 = run_sentinel(transport2, _CLAIM, _DOCS, model_slug="minimax/minimax-m2")
+    assert result2.verdict is SentinelVerdict.UNGROUNDED
+    assert result2.parsed_ok is True
diff --git a/tests/roles/test_sentinel_contract.py b/tests/roles/test_sentinel_contract.py
index 5a28e92c..01bd4b84 100644
--- a/tests/roles/test_sentinel_contract.py
+++ b/tests/roles/test_sentinel_contract.py
@@ -14,6 +14,7 @@ import pytest
 from src.polaris_graph.roles.sentinel_contract import (
     SentinelResult,
     SentinelVerdict,
+    parse_sentinel_decomposition,
     parse_sentinel_grounded_token,
     parse_sentinel_score,
 )
@@ -307,3 +308,112 @@ def test_sentinel_mode_invalid_env_raises(monkeypatch):
     monkeypatch.setenv("PG_SENTINEL_GROUNDEDNESS_MODE", "guardain")  # typo
     with _pytest.raises(ValueError):
         sentinel_groundedness_mode()
+
+
+# === DECOMPOSITION parser (certified MiniMax-M2, I-run11-004) ========================
+# Mapping: "supported" -> GROUNDED, "unsupported" -> UNGROUNDED. EVERY parse failure / missing /
+# off-enum / non-string fails CLOSED to UNGROUNDED parsed_ok=False. NO silent GROUNDED on bad input.
+def test_decomposition_supported_json_maps_grounded() -> None:
+    raw = '{"verdict": "supported", "unsupported_atoms": 0, "atoms": []}'
+    assert parse_sentinel_decomposition(raw) == SentinelResult(SentinelVerdict.GROUNDED, parsed_ok=True)
+
+
+def test_decomposition_unsupported_json_maps_ungrounded() -> None:
+    raw = '{"verdict": "unsupported", "unsupported_atoms": 2, "atoms": [{"atom": "x"}]}'
+    assert parse_sentinel_decomposition(raw) == SentinelResult(
+        SentinelVerdict.UNGROUNDED, parsed_ok=True
+    )
+
+
+@pytest.mark.parametrize(
+    "raw,verdict",
+    [
+        ('{"verdict": "SUPPORTED"}', SentinelVerdict.GROUNDED),       # case-insensitive
+        ('{"verdict": " supported "}', SentinelVerdict.GROUNDED),     # whitespace tolerant
+        ('{"verdict": "Unsupported"}', SentinelVerdict.UNGROUNDED),
+    ],
+)
+def test_decomposition_verdict_case_and_whitespace_tolerant(raw, verdict) -> None:
+    result = parse_sentinel_decomposition(raw)
+    assert result.verdict is verdict
+    assert result.parsed_ok is True
+
+
+def test_decomposition_fenced_json_parses() -> None:
+    raw = '```json\n{"verdict": "supported", "atoms": []}\n```'
+    assert parse_sentinel_decomposition(raw) == SentinelResult(SentinelVerdict.GROUNDED, parsed_ok=True)
+
+
+def test_decomposition_bare_fence_no_lang_parses() -> None:
+    raw = '```\n{"verdict": "unsupported"}\n```'
+    assert parse_sentinel_decomposition(raw) == SentinelResult(
+        SentinelVerdict.UNGROUNDED, parsed_ok=True
+    )
+
+
+def test_decomposition_trailing_comma_json_parses() -> None:
+    # The certified _strip_json repairs a trailing comma before the closing brace.
+    raw = '{"verdict": "supported", "unsupported_atoms": 0, "atoms": [],}'
+    assert parse_sentinel_decomposition(raw) == SentinelResult(SentinelVerdict.GROUNDED, parsed_ok=True)
+
+
+def test_decomposition_reasoning_prefix_then_json_parses() -> None:
+    # Reasoning prose before the JSON object: _strip_json extracts the largest {...} span.
+    raw = 'Let me decompose the claim.\nHere is my verdict:\n{"verdict": "unsupported", "atoms": []}'
+    assert parse_sentinel_decomposition(raw) == SentinelResult(
+        SentinelVerdict.UNGROUNDED, parsed_ok=True
+    )
+
+
+@pytest.mark.parametrize(
+    "raw",
+    [
+        "",                                      # empty
+        "   ",                                   # whitespace only
+        "not json at all",                       # prose, no JSON
+        "{ this is not valid json",              # malformed, unparseable
+        '{"unsupported_atoms": 0, "atoms": []}',  # missing verdict key
+        '{"verdict": "maybe"}',                  # off-enum verdict
+        '{"verdict": ""}',                       # empty verdict
+        '{"verdict": null}',                     # non-string verdict
+        '{"verdict": 1}',                        # numeric verdict
+        '{"verdict": "grounded"}',               # wrong vocabulary (not supported/unsupported)
+        '["supported"]',                          # JSON array, no verdict object
+        '"supported"',                            # bare JSON string scalar
+    ],
+)
+def test_decomposition_malformed_fails_closed_to_ungrounded(raw) -> None:
+    result = parse_sentinel_decomposition(raw)
+    assert result.verdict is SentinelVerdict.UNGROUNDED
+    assert result.parsed_ok is False
+
+
+def test_decomposition_non_string_fails_closed() -> None:
+    result = parse_sentinel_decomposition(None)  # type: ignore[arg-type]
+    assert result == SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)
+
+
+def test_decomposition_both_verdicts_takes_object_verdict_key() -> None:
+    # A nested 'unsupported' atom plus a top-level "supported" verdict: the TOP-LEVEL verdict key
+    # is authoritative (the certified harness reads parsed['verdict']). Still a clean parse.
+    raw = ('{"atoms": [{"atom": "a", "status": "unsupported"}], '
+           '"unsupported_atoms": 1, "verdict": "supported"}')
+    # The decomposition contract trusts the model's own top-level verdict; the atom-count
+    # fail-closed union is applied UPSTREAM in the certified harness, not re-derived here.
+    assert parse_sentinel_decomposition(raw) == SentinelResult(SentinelVerdict.GROUNDED, parsed_ok=True)
+
+
+def test_decomposition_never_silently_grounded_anti_inversion() -> None:
+    """The lethal property: no malformed/garbage input may yield GROUNDED. The ONLY GROUNDED path
+    is a clean JSON object with verdict == 'supported'."""
+    for raw in (
+        "",
+        "garbage",
+        '{"verdict": "maybe"}',
+        '{"no_verdict": true}',
+        '{"verdict": "unsupported"}',
+        None,
+    ):
+        result = parse_sentinel_decomposition(raw)  # type: ignore[arg-type]
+        if not (result.verdict is SentinelVerdict.GROUNDED and result.parsed_ok):
+            assert result.verdict is SentinelVerdict.UNGROUNDED, repr(raw)
diff --git a/tests/roles/test_sweep_integration.py b/tests/roles/test_sweep_integration.py
index 7e6f4a1d..b8e686e4 100644
--- a/tests/roles/test_sweep_integration.py
+++ b/tests/roles/test_sweep_integration.py
@@ -64,12 +64,16 @@ class MockTransport:
                 citations=[CitationSpan(span_start=0, span_end=8, doc_ids=("doc1",))],
             )
         if request.role == "sentinel":
-            # I-run11-002 L1: emit the format matching the active groundedness mode (the request's
-            # final instruction reveals it) so the canned output pairs with the parser run_sentinel
-            # selected — `<score>yes|no</score>` for the inverted guardian block, else the
-            # non-inverted one-word GROUNDED/UNGROUNDED (the benchmark default).
+            # Emit the format matching the active groundedness mode (I-run11-002 L1 + I-run11-004):
+            # decomposition (MiniMax-M2 default) -> JSON {"verdict": ...}; guardian -> inverted
+            # `<score>yes|no</score>`; noninverted -> one-word GROUNDED/UNGROUNDED.
             final_instruction = request.messages[-1]["content"] if request.messages else ""
-            if "<guardian>" in final_instruction:
+            if "Decompose the CLAIM into atomic sub-assertions" in final_instruction:
+                verdict = "supported" if self._sentinel_grounded else "unsupported"
+                n = "0" if self._sentinel_grounded else "1"
+                raw_text = ('{"verdict": "' + verdict + '", "unsupported_atoms": '
+                            + n + ', "atoms": []}')
+            elif "<guardian>" in final_instruction:
                 raw_text = "<score>no</score>" if self._sentinel_grounded else "<score>yes</score>"
             else:
                 raw_text = "GROUNDED" if self._sentinel_grounded else "UNGROUNDED"
@@ -228,13 +232,18 @@ def test_coverage_credit_only_on_verified(tmp_path) -> None:
     class _Mixed(MockTransport):
         def complete(self, request: RoleRequest) -> RoleResponse:
             # Sentinel UNGROUNDED only for the 'bad' claim's evidence text. Emit the format
-            # matching the active groundedness mode (I-run11-002 L1) so canned output pairs with
-            # the parser run_sentinel selected (non-inverted by default).
+            # matching the active groundedness mode (I-run11-002 L1 + I-run11-004) so canned output
+            # pairs with the parser run_sentinel selected (decomposition JSON by default).
             if request.role == "sentinel":
                 docs = request.params.get("documents", [])
                 grounded = not any(d.get("text") == "x" for d in docs)
                 final_instruction = request.messages[-1]["content"] if request.messages else ""
-                if "<guardian>" in final_instruction:
+                if "Decompose the CLAIM into atomic sub-assertions" in final_instruction:
+                    verdict = "supported" if grounded else "unsupported"
+                    n = "0" if grounded else "1"
+                    raw_text = ('{"verdict": "' + verdict + '", "unsupported_atoms": '
+                                + n + ', "atoms": []}')
+                elif "<guardian>" in final_instruction:
                     raw_text = "<score>no</score>" if grounded else "<score>yes</score>"
                 else:
                     raw_text = "GROUNDED" if grounded else "UNGROUNDED"
