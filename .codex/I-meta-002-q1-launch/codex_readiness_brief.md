RULE NOW — emit the YAML verdict block FIRST, before any prose. Do NOT explore the repo beyond the
grounded facts below (prior runs explored ~1MB and crashed without a verdict). Rule from the facts here.

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: accept_remaining
remaining_blockers_for_execution: [...]
```

# Codex readiness gate — I-meta-002 Q1 LIVE-RUN LAUNCH (#938). Pre-spend. APPROVE = the FOUR-ROLE pipeline is ready to start the FIRST paid question (Q1) without a "shit show", given the runbook's blockers are honored.

The operator's bar for Q1: (a) reasoning and output/verdict content are CLEANLY SEPARATED everywhere — never mixed into one "soap"; (b) FULL per-call run logging so every model call can be reviewed line-by-line ("alphabet level"); (c) all launch blockers surfaced and correctly ordered; (d) NO spend until Codex APPROVE + operator promotes the lock. Rule on whether the runbook (`.codex/I-meta-002-q1-launch/runbook.md`) correctly captures readiness, and whether the verifier-reasoning gap below is a REAL pre-Q1 blocker (P1) or acceptable.

## GROUNDED FACTS (verified by Claude main-thread; do not re-explore)
1. **Generator reasoning↔output: CLEAN.** I-gen-004 (#496): `openrouter_client.set_reasoning_sink` + a run-scoped `ReasoningTraceCollector` persist generator reasoning to `reasoning_trace.jsonl` (hashed into the audit_bundle; `audit_bundle/conformance.py:68 REASONING_TRACE_FILENAME`). `generate()` returns clean prose (reasoning OFF); `reason()` returns reasoning separately in `reasoning_details`. The shipped `report.md` uses content only. Reasoning is captured SEPARATELY from content (`_capture_reasoning_trace`, content_source = direct|promoted_from_reasoning|extracted_from_reasoning).
2. **Verifier transport (Mirror/Sentinel/Judge) reads ONLY `content`.** `src/polaris_graph/roles/openai_compatible_transport.py:305 content = message.get("content")`; `_parse` returns `(raw_text=content, served_model, usage)`. It does NOT read or persist `reasoning_content`. Consequence (a): the verifiers' reasoning is NOT logged anywhere — you cannot line-by-line review WHY Mirror/Sentinel/Judge ruled. Consequence (b): the Judge parser does an EXACT match against the 5-enum after `.strip()` (`judge_contract.py:45,52`) with NO `<think>` stripping; the Mirror parser strips only its own `<co>…</co:doc_id>` tags (`mirror_contract.py:121,141`). So if the served Qwen Judge emits reasoning INLINE as `<think>…</think>` in `content` (rather than a separate `reasoning_content` field), the Judge verdict won't parse → fail-closed (UNREACHABLE / raise), holding every claim. That is safe (no soap reaches the report) but is a functional Q1 risk.
3. **Runtime lock NOT promoted.** `config/architecture/polaris_runtime_lock.yaml:37 status: codex_approved_pending_operator_signature`. `pathB_run_gate._assert_architecture_coverage` raises while pending → live runs frozen until the operator signs `status: locked`. (Operator-gated, by design.)
4. **Judge slug consistent everywhere:** `qwen/qwen3.6-35b-a3b` in lock:80, `config/serving/verifier_roles.yaml:96,111`, `gate_a_dry_run.py:262`. Generator deepseek/deepseek-v4-pro:50, Mirror cohere/command-a-plus:60, Sentinel ibm-granite/granite-guardian-4.1-8b:70. Gate-A OVERALL PASS rc0.
5. **Traceability (other than verifier reasoning) is strong.** Per-question run_dir writes: manifest.json, report.md, run_log.txt, reasoning_trace.jsonl (generator), four_role_claim_audit.json, judge_output.json, verification_details.json, evidence_pool.json, live_corpus_dump.json, evaluator_rule_checks.json, bibliography.json, contradictions.json, completeness.json, model_pin.json, cost_ledger.jsonl + global pg_cost_ledger.jsonl; audit_bundle hashes all. M4 `pathB_run_gate.assert_post_run` records served model+endpoint per role (served==pinned). M2 `verify_serving_identity` probes served id == locked slug before any generation.
6. **Budget:** canary cap is `PG_MAX_COST_PER_RUN` (must be set for Q1). Vast $300 / OpenRouter $50 Codex-approved for the 1-question canary. Q1 is a clinical question (drb_75); a `four_role_held` (release HELD by S0 exact-source gate) is the SAFE outcome and is NOT a failure — must NOT be weakened to force a release.

## What to rule on
A. Is the runbook's readiness assessment CORRECT and COMPLETE — are any launch blockers MISSING?
B. Is the **verifier-reasoning gap (fact 2)** a real pre-Q1 blocker (P1)? i.e. before Q1 spends, must POLARIS (i) capture each verifier's reasoning SEPARATELY into the run artifacts (so the operator's line-by-line review covers the verifiers, not just the generator), AND (ii) make the verdict parsers robust to served reasoning (configure vLLM Qwen reasoning-parser so reasoning → `reasoning_content` leaving `content` = the bare verdict, OR strip a leading `<think>…</think>` before matching) — confirmed at serving time? Or is it acceptable to launch Q1 without it?
C. Is the blocker ORDER correct (verifier-reasoning fix → lock promotion → cost cap → serving-time served==pinned)?
D. Are the abort conditions sufficient (served≠pinned, cost cap, unparseable Judge verdict)?

APPROVE iff the runbook correctly captures Q1 readiness AND the verifier-reasoning handling is either already adequate OR explicitly listed as a must-fix-before-spend blocker (which it is). REQUEST_CHANGES if a real Q1 launch risk is missing or mis-ordered.
