export const meta = {
  name: 'gate-fix-plan-3llm',
  description: 'Feed the confirmed findings (0.038 was a cache bug; real RACE=0.3568 below champion 0.4447; 3 drags: D8 banner, eligibility over-mask/ghost, dead reranker) to Fable 5 + Codex Sol + Kimi K3 for a deep line-by-line audit + full fix plan each; Opus reviews all line-by-line and consolidates.',
  phases: [
    { title: 'Evidence', detail: 'assemble the findings + current-state pack' },
    { title: 'FixPlans', detail: 'Fable 5 + Codex Sol + Kimi K3 — 3 independent full fix plans' },
    { title: 'Consolidate', detail: 'Opus reviews all plans line-by-line + single consolidated fix plan' },
  ],
}

const PACK = "/tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/reviews/fixplan_findings.md"
const PRIOR = "/tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/reviews/broken_vs_champion_evidence.md"
const REPORT = "/home/polaris/wt/outline_agent/outputs/gate_e2e_final2/workforce/drb_72_ai_labor/draw1/report.md"

const FINDINGS = `CONFIRMED FINDINGS (from a prior 3-LLM forensic + a re-measurement):
- The RACE=0.0384 was a SCORING-CACHE ARTIFACT, NOT a broken pipeline. deepresearch_bench_race.py:250 scores the CLEANED file; utils/clean_article.py:367-371 dedups by task ID (not content), so a poisoned 1090-char 'unsupported_domain' refusal stub (left in cleaned_data/polaris_gate_task72.jsonl by an ABORTED earlier run) was scored instead of the real report. scripts/score_report_race.py never purges the stale cleaned file; --force re-evaluates but does NOT re-clean.
- RE-MEASURED (poisoned cache purged, fresh model-name) the REAL 4653-word gated report: RACE Overall=0.3568 (Comprehensiveness 0.3826, Insight 0.3546, Instruction-Following 0.3682, Readability 0.2812). vs CHAMPION 0.4447 (Comp 0.4569, Insight 0.4293, IF 0.4587, Read 0.4310). The gated run is BELOW champion on EVERY dimension, including Instruction-Following (0.368 vs 0.459) — the exact dimension the gate was built to improve. Biggest drag: Readability -0.150.
- THREE DRAGS identified (all removable): (D1) the D8-UNADJUDICATED BANNER + disclosure scaffolding prepended to report.md — it fired because we set PG_WINNER_FIRING_GATE=0 (bypassed the winner-gate) because the reranker was dead; this scaffolding text is scored and craters Readability/IF. (D2) the FAITHFULNESS GHOST (real, secondary): the eligibility JUDGE masked 50 of 143 citable sources (35%) + chrome-gate basket drops thinned content -> hurts Comprehensiveness/Insight. ALSO journal-only LEAKED: final citations were only ~45% journal / 55% non-journal (OECD, Morgan Stanley, Fed, MIT Sloan, think tanks) despite the mask. (D3) the DEAD RERANKER (Qwen3 CUDA-OOM, full-weight-all, no reranking) degraded selection — but this was TRANSIENT: the GPU is FREE now (0/82 GB used).
- HARD CONSTRAINT: faithfulness (provenance_generator.py / strict_verify) was FROZEN (0-diff) all day and MUST stay frozen. The fix must remove the UPSTREAM over-restriction / scaffolding / measurement bug — NEVER weaken the verifier.

YOUR JOB: a DEEP, LINE-BY-LINE audit and a FULL FIX PLAN (details + rationale, ranked by leverage) to (a) permanently fix the scoring-cache bug, (b) remove the D8-banner/scaffolding drag (get the reranker running so no winner-gate bypass is needed; the GPU is free now — confirm the code path), (c) tame the eligibility over-mask + FIX the journal-only leak WITHOUT weakening strict_verify, (d) actually make the gate IMPROVE Instruction-Following (the goal) — diagnose why IF is currently WORSE and what specifically must change, and (e) a clean re-run protocol with a predicted RACE. For each fix: exact file:function:line, the change, the rationale, the faithfulness-safety argument, and the expected RACE-dimension impact.`

phase('Evidence')
const evidence = await agent(`Assemble a findings + current-state pack for a 3-LLM fix-planning review. Write it to ${PACK}. You are in /home/polaris/wt/outline_agent (branch gate-inversion). Read-only.
Include: (1) the confirmed findings verbatim (below). (2) From the real gated report ${REPORT}: paste the D8 banner / disclosure scaffolding text that got prepended (grep for 'D8', 'unadjudicated', 'disclosed', 'RELEASE', banner), the section structure, and the citation list (classify journal vs non-journal). (3) The eligibility-mask + chrome-gate + reranker code sites: src/polaris_graph/retrieval/quality_eligibility.py (the Phase-C masking), the chrome-gate, the content_relevance reranker load (where CUDA-OOM falls back), and the winner-firing-gate at scripts/run_honest_sweep_r3.py:~12836 (PG_WINNER_FIRING_GATE) + where the D8 banner is prepended. (4) The scoring bug sites: scripts/score_report_race.py (line ~66 write + line 69 article_chars), third_party/deep_research_bench/deepresearch_bench_race.py:250,365, utils/clean_article.py:367-371. Give exact file:line so the 3 analysts can audit precisely.
FINDINGS TO INCLUDE VERBATIM:
${FINDINGS}`, { label: 'evidence', phase: 'Evidence', effort: 'high' })

phase('FixPlans')
const plans = await parallel([
  () => agent(`You are Fable 5, ONE of THREE independent fix-planners (others: Codex Sol, Kimi K3 — do NOT coordinate). Read the findings pack ${PACK} + the prior forensic evidence ${PRIOR} + verify against the real code (branch gate-inversion) and report ${REPORT}.
${FINDINGS}
Produce a COMPLETE, LINE-BY-LINE FIX PLAN (markdown): for EACH of (a) scoring-cache bug, (b) D8-banner/reranker, (c) eligibility over-mask + journal-only leak, (d) making the gate improve IF, (e) clean re-run protocol + predicted RACE — give exact file:function:line, the change, rationale, faithfulness-safety argument, and expected RACE-dimension impact. Rank by leverage. Be exhaustive and concrete.`, { label: 'FABLE-5', phase: 'FixPlans', model: 'fable', effort: 'high' }),
  () => agent(`You are orchestrating SOL (GPT-5.6 via codex). Write the prompt to /tmp/sol_fixplan.txt: "You are Sol (GPT-5.6), ONE of THREE independent fix-planners (others: Fable, Kimi — do not coordinate). Read ${PACK} and ${PRIOR} in full, verify against the real code (branch gate-inversion) and report ${REPORT}. ${FINDINGS} Produce a COMPLETE LINE-BY-LINE FIX PLAN: for each of (a) scoring-cache bug, (b) D8-banner/reranker, (c) eligibility over-mask + journal-only leak, (d) making the gate improve IF, (e) clean re-run protocol + predicted RACE — exact file:function:line, change, rationale, faithfulness-safety, expected RACE impact. Rank by leverage."
Then run: cd /home/polaris/wt/outline_agent && timeout 560 codex exec -C /home/polaris/wt/outline_agent --dangerously-bypass-approvals-and-sandbox "$(cat /tmp/sol_fixplan.txt)" 2>&1
Return codex's FULL stdout verbatim. If codex is blocked, unavailable, or times out with no verdict, say so explicitly and provide your OWN full fix plan as fallback (labeled 'SOL-FALLBACK'). Either way return a complete fix plan.`, { label: 'CODEX-SOL', phase: 'FixPlans', effort: 'high' }),
  () => agent(`You are orchestrating KIMI K3 (via OpenRouter). Source env: cd /home/polaris/wt/outline_agent && set -a && . ./.env && set +a.
Write /tmp/kimi_fixplan.py that: reads ${PACK}, the report ${REPORT} (first 9000 chars), and greps the drop/mask/verify/reranker/banner lines from /home/polaris/wt/outline_agent/outputs/gate_e2e_final2.log; builds messages=[system:"You are Kimi K3, an independent fix-planner; be exhaustive, cite file:line", user: <that evidence> + "${FINDINGS}" + "Produce a COMPLETE LINE-BY-LINE FIX PLAN for each of (a) scoring-cache bug, (b) D8-banner/reranker, (c) eligibility over-mask + journal-only leak, (d) making the gate improve IF, (e) clean re-run protocol + predicted RACE — exact file:function:line, change, rationale, faithfulness-safety, expected RACE impact; rank by leverage."]; calls model 'moonshotai/kimi-k3' at https://openrouter.ai/api/v1/chat/completions (Bearer $OPENROUTER_API_KEY) max_tokens 45000 temperature 0.2; captures message.content OR message.reasoning; retry 4x w/ 30s backoff on 429/5xx. Print the plan.
Run it, return Kimi's FULL plan verbatim. If it fails, say so and give your OWN fallback plan labeled 'KIMI-FALLBACK'.`, { label: 'KIMI-K3', phase: 'FixPlans', effort: 'high' }),
]).then(r => r.map((x,i)=> x || `[planner ${i} produced no output]`))
const [fable, sol, kimi] = plans

phase('Consolidate')
const consolidated = await agent(`You are Opus. Review THREE independent fix plans LINE BY LINE and consolidate them into ONE careful, prioritized fix plan for the operator.
${FINDINGS}

=== FABLE 5 FIX PLAN ===
${fable}

=== CODEX SOL FIX PLAN ===
${sol}

=== KIMI K3 FIX PLAN ===
${kimi}

Review each plan critically (read the actual code to adjudicate disagreements; cite file:function:line). Produce the CONSOLIDATED FIX PLAN:
1. Ordered list of fixes (highest leverage first), each with: exact file:function:line, the concrete change, WHY (rationale), the faithfulness-safety argument (must NOT weaken strict_verify), expected RACE-dimension impact, and effort (S/M/L).
2. Explicitly resolve where the three planners DISAGREE, with your verdict + evidence.
3. Flag anything a planner proposed that is WRONG or would weaken faithfulness — reject it and say why.
4. The clean re-run protocol (exact flags/commands) + a predicted RACE for the fixed gate vs champion 0.4447 — and honestly state whether the gate is likely to BEAT champion on Instruction-Following after the fixes, or whether the gate's benefit is still unproven.
Be decisive, honest, and complete. This is the single fix plan the operator will act on.`, { label: 'opus-consolidate', phase: 'Consolidate', effort: 'high' })

return { consolidated_fix_plan: consolidated, fable: (fable||'').slice(0,160), sol: (sol||'').slice(0,160), kimi: (kimi||'').slice(0,160) }
