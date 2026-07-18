export const meta = {
  name: 'broken-vs-champion-forensics',
  description: 'Max-ultracode 3-LLM forensic: why did the gate e2e run score RACE 0.038 vs champion 0.4447? Fable 5 + Codex Sol + Kimi K3 independently compare broken(gate-inversion) vs champion(df4118a) code+logs+flow, hunt the faithfulness-ghost, name root cause + root fix. Opus consolidates.',
  phases: [
    { title: 'Evidence', detail: 'assemble the full evidence pack (diff, broken-run stats, scored report, champion baseline)' },
    { title: 'Analyze', detail: 'Fable 5 + Codex Sol + Kimi K3 — 3 independent deep forensics' },
    { title: 'Consolidate', detail: 'Opus: single root cause + root fix' },
  ],
}

const EV = "/tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/reviews/broken_vs_champion_evidence.md"
const REPORT = "/home/polaris/wt/outline_agent/outputs/gate_e2e_final2/workforce/drb_72_ai_labor/draw1/report.md"
const LOG = "/home/polaris/wt/outline_agent/outputs/gate_e2e_final2.log"

const CENTRAL = `CENTRAL QUESTION: The champion pipeline (branch bot/outline-agent-box @ df4118a) scores RACE 0.4447 / FACT 90.3% on DeepResearch-Bench task 72. After a day of building a 'Research Planning Gate' (branch gate-inversion @ ~78fe2ca) to improve instruction-following, the live gated end-to-end run scored RACE=0.0384 (Comprehensiveness 0.0000, Insight 0.0088, Instruction 0.0231, Readability 0.1822) — near-zero/broken. The gate is behind PG_GATE (OFF => byte-identical to champion, verified). The run used: PG_GATE=1 PG_PLANNING_GATE_LIVE=1 PG_TOPICALITY_ELIGIBILITY=1 PG_OPAQUE_ELIGIBILITY=1 PG_AUTHORIZED_SWEEP_APPROVAL=1 PG_WINNER_FIRING_GATE=0. Known facts from the broken run: gate compiled 22 terms/13 hard; corpus_approval passed; the ELIGIBILITY JUDGE masked 50 of 143 citable sources -> 93; report=4653 words BUT verified=44 / DROPPED=84 sentences; chrome-gate canary dropped baskets to 'insufficient-evidence disclosure'; strict_verify dropped 9/9 fact-dedup rewrites; a D8-unadjudicated banner was prepended; status=released_with_disclosed_gaps; AND the W5 content-relevance reranker was DEAD (Qwen3-Reranker CUDA OOM — GPU full, fell back to full-weight-for-all, no reranking). Final citations were only ~45% journal / 55% non-journal (OECD, Morgan Stanley, Fed, MIT Sloan, think tanks).
YOUR JOB: forensically determine the ROOT CAUSE of RACE=0.0384 and the single ROOT FIX. Explicitly adjudicate these hypotheses, with evidence:
 (H1) FAITHFULNESS GHOST / STARVATION: over-aggressive verification/dropping/eligibility-masking gutted the report substance (84 dropped, chrome-gate drops, insufficient-evidence disclosures, D8 banner) leaving a hedge/disclosure shell the RACE judge rates ~0. NOTE: provenance_generator.py/strict_verify were FROZEN (0-diff) — so if the ghost is real it entered via UPSTREAM restriction (eligibility masking, scope, topic-gate, or a gate-flag), not by editing the verifier. NAME the exact file/flag/line where the over-restriction enters.
 (H2) DEAD RERANKER (ENVIRONMENT): the GPU-OOM reranker (full-weight-all, no demotion) produced bad selection -> the report is off-topic/thin -> RACE ~0. Is this the champion's problem too (would a PG_GATE=0 champion run in THIS env also score ~0)? i.e. is the regression the GATE or the BOX?
 (H3) SCORING ARTIFACT: RACE Comprehensiveness=EXACTLY 0.0000 is suspicious — is report.md real substance, or dominated by the D8 banner / disclosure text / a wrong-file / prompt-mismatch so the judge scored a non-report?
 (H4) something else — name it.
Be concrete: cite file:function:line. The operator's ruling is that faithfulness (strict_verify) STAYS FROZEN; the fix must NOT weaken it — it must remove the UPSTREAM over-restriction that starves the report. Deliver: ROOT CAUSE (one paragraph, ranked hypotheses with evidence) + ROOT FIX (the single highest-leverage change, file:function) + a cheap DIAGNOSTIC to confirm (e.g. does a champion PG_GATE=0 run in this env also break?).`

phase('Evidence')
const evidence = await agent(`Assemble a complete EVIDENCE PACK for a forensic comparison of a BROKEN gated pipeline run vs the CHAMPION pipeline. Write it to ${EV}. You are in /home/polaris/wt/outline_agent. Read-only.
Gather and write into the evidence file:
1. CODE DIFF: git diff --stat df4118a..gate-inversion (the full changed-file list) + for the ~10 most important gate files a 2-line summary of what each does. Focus on anything that can REMOVE/DROP/MASK evidence or sentences (eligibility, scope, topic-gate, verification wiring). Grep the diff for anything touching sentence-dropping, evidence masking, char/word budgets, disclosure, chrome-gate.
2. BROKEN-RUN STATS from ${LOG}: extract EVERY line about dropping/masking/verification/gates/disclosure/reranker — quality_eligibility masked N, strict_verify verified/dropped counts, chrome-gate drops, gen-budget tail-drops, topic_gate DEMOTED, content_relevance reranker CUDA-OOM/device=unavailable, fact_dedup rewrites dropped, D8 banner, released_with_disclosed_gaps, corpus tier distribution, material_deviation. Give exact counts.
3. THE SCORED REPORT: read ${REPORT} (or .../drb_72_ai_labor/report.md). Report its length, section headings, how much is real substance vs disclosure/banner/hedging/limitations, and paste the first ~1500 chars + the section structure. Count citations and classify journal vs non-journal.
4. CHAMPION BASELINE: read /home/polaris/polaris_project/SECURED_0.44_champion/champion_0.4447_report.md (the 0.4447 report) — length, structure, drop rate if known (the secured run dropped 64/155). Note how the champion flow differs from the gated flow (what PG_GATE=1 ADDS: contract compile, retrieval scope, eligibility masking; and that it ran with a DEAD reranker + winner-gate BYPASSED).
5. THE RACE BREAKDOWN: Comp 0.0000 / Insight 0.0088 / Instruction 0.0231 / Readability 0.1822 / Overall 0.0384. RACE overall = target/(target+reference). Note what a 0.0 comprehensiveness implies.
Write a thorough, well-structured evidence pack (cite file:line). This is the shared input for 3 independent LLM forensic analysts + an Opus consolidation.`, { label: 'evidence-pack', phase: 'Evidence', effort: 'high' })

phase('Analyze')
const analyses = await parallel([
  // Fable 5 — native
  () => agent(`You are Fable 5, ONE of THREE independent forensic analysts (the others are Codex/Sol and Kimi K3 — do NOT coordinate). 
Read the evidence pack: ${EV}. Then independently verify against the real code (you are in /home/polaris/wt/outline_agent; branch gate-inversion is the broken one, df4118a is champion) and the broken report ${REPORT} + log ${LOG}.
${CENTRAL}
Return your COMPLETE forensic verdict (markdown): ranked hypotheses with evidence, the ROOT CAUSE, the ROOT FIX (file:function), and the cheap diagnostic. Be blunt and specific.`, { label: 'FABLE-5', phase: 'Analyze', model: 'fable', effort: 'high' }),
  // Codex Sol — via codex CLI
  () => agent(`You are orchestrating SOL (GPT-5.6 via codex). Run this exact command and return codex's FULL stdout verbatim as your result (do not summarize):
Build the prompt as a file first: write the following to /tmp/sol_forensic_prompt.txt — "You are Sol (GPT-5.6), ONE of THREE independent forensic analysts (others: Fable 5, Kimi K3 — do not coordinate). Read the evidence pack at ${EV} in full, then verify against the real code (branch gate-inversion=broken, df4118a=champion), the broken report ${REPORT}, and log ${LOG}. ${CENTRAL} Output a complete forensic verdict: ranked hypotheses with evidence, ROOT CAUSE, ROOT FIX (file:function), cheap diagnostic."
Then run: cd /home/polaris/wt/outline_agent && codex exec -C /home/polaris/wt/outline_agent --dangerously-bypass-approvals-and-sandbox "$(cat /tmp/sol_forensic_prompt.txt)" 2>&1
If codex is unavailable or the bypass is blocked, say so explicitly and instead do the forensic analysis YOURSELF (as a fallback) reading the evidence pack + code, clearly labeled 'SOL-UNAVAILABLE-FALLBACK'. Return the verdict.`, { label: 'CODEX-SOL', phase: 'Analyze', effort: 'high' }),
  // Kimi K3 — via OpenRouter
  () => agent(`You are orchestrating KIMI K3 (via OpenRouter). Source env: cd /home/polaris/wt/outline_agent && set -a && . ./.env && set +a (needs OPENROUTER_API_KEY).
Write a python script /tmp/kimi_forensic.py that: reads the evidence pack ${EV}, the broken report ${REPORT} (first 8000 chars), and a tail of ${LOG} (grep the drop/mask/verify/reranker lines); builds a prompt = a system msg ("You are Kimi K3, an independent forensic analyst; be blunt, cite specifics") + a user msg containing that evidence + this instruction: "${CENTRAL}"; calls model 'moonshotai/kimi-k3' via https://openrouter.ai/api/v1/chat/completions (Bearer $OPENROUTER_API_KEY) with max_tokens 40000 temperature 0.2; on the response, capture message.content OR message.reasoning (Kimi is reasoning-first — content may be empty, use reasoning); retry up to 4x with 30s backoff on 429/5xx. Print the verdict text.
Run it and return Kimi's FULL verdict verbatim. If it fails after retries, say so and provide your OWN fallback analysis labeled 'KIMI-UNAVAILABLE-FALLBACK'.`, { label: 'KIMI-K3', phase: 'Analyze', effort: 'high' }),
]).then(r => r.map((x,i)=> x || `[analyst ${i} produced no output]`))
const [fable, sol, kimi] = analyses

phase('Consolidate')
const consolidated = await agent(`You are Opus, consolidating THREE independent forensic analyses of why a gated pipeline run scored RACE=0.0384 vs the champion's 0.4447. 
${CENTRAL}

=== FABLE 5 VERDICT ===
${fable}

=== CODEX SOL VERDICT ===
${sol}

=== KIMI K3 VERDICT ===
${kimi}

Consolidate into a SINGLE answer for the operator. Structure:
1. WHERE THE THREE AGREE (the high-confidence root cause).
2. WHERE THEY DIVERGE + your adjudication (read the actual code to break ties; cite file:function:line).
3. THE ROOT CAUSE — one clear paragraph. Explicitly answer: is it the FAITHFULNESS GHOST (upstream over-restriction/starvation gutting the report) and if so WHERE/WHICH flag/change 'silently put it in'? Or the DEAD RERANKER (environment)? Or a scoring artifact? Rank by evidence.
4. THE ROOT FIX — the single highest-leverage change (file:function), that does NOT weaken frozen strict_verify — it must remove the upstream over-restriction, OR if it's the environment/reranker, say so plainly.
5. THE CHEAP DIAGNOSTIC to confirm before any fix (e.g. run champion PG_GATE=0 e2e in THIS same GPU-OOM env — if it ALSO scores ~0, the regression is the BOX not the gate).
Be decisive and honest. This is the single answer the operator asked for.`, { label: 'opus-consolidate', phase: 'Consolidate', effort: 'high' })

return { root_answer: consolidated, fable: (fable||'').slice(0,200), sol: (sol||'').slice(0,200), kimi: (kimi||'').slice(0,200) }
