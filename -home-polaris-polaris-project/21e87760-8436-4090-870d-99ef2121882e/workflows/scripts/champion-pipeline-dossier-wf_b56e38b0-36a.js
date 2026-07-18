export const meta = {
  name: 'champion-pipeline-dossier',
  description: 'Document the full 0.4447 champion pipeline end-to-end (query->search->corpus->outline->write->verify->assemble->score) with token cost and wall-clock time',
  phases: [
    { title: 'Investigate' },
    { title: 'Synthesize' },
  ],
}
const WT = '/home/polaris/wt/outline_agent'
const SP = '/tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad'

phase('Investigate')

const stages = [
  { key: 'search', prompt: `READ-ONLY. cd ${WT}. Document STAGE 1-2: QUERY GENERATION + MULTI-SOURCE SEARCH of the champion's corpus-building pipeline. The corpus (data/cp4_corpus_s3gear_329.json) was built by the SWEEP run 'SWEEP_workforce_drb_72_ai_labor' (see the corpus '_provenance'). Read src/agents/planner_agent.py (how it generates sub-queries from the RQ), src/agents/search_agent.py (which sources: Semantic Scholar/PubMed/arXiv/Serper Google; the QueryAmplifier at src/search/query_amplifier.py), src/orchestration/iteration_manager.py (max_iterations=15, convergence/stopping), src/orchestration/dynamic_replanner.py (gap-driven re-query). Document EXACTLY: how a query is generated, which sources are hit and how, how results iterate (the "search and search" loop), the stopping criteria, and any config (max iters, concurrency limits, amplification). Give file:line for each claim. Also find the actual sweep command / entry point (real_corpus_run*.py) and its parameters.` },
  { key: 'corpus', prompt: `READ-ONLY. cd ${WT}. Document STAGE 3: CORPUS CONSOLIDATION. The sweep output (cp3, s3_consolidate) was converted by scripts/cp3_to_cp4_corpus.py into data/cp4_corpus_s3gear_329.json. Read that converter and the corpus. Document: the corpus STRUCTURE (top keys: research_question, domain, evidence[997], finding_clusters[329], same_work_groups, basket_total, _provenance), the per-evidence fields (authors, direct_quote, statement, doi, journal, tier, provenance_class, v30_entity_id), the QUALITY TIER system (T1-T7, UNKNOWN) — what each tier means and how tiers are assigned, and the corpus STATS: 997 evidence items across 841 distinct works, median direct_quote ~2527 chars. Explain how finding_clusters and same_work_groups are computed and used. file:line for each.` },
  { key: 'outline_write', prompt: `READ-ONLY. cd ${WT}. Document STAGE 4-5: OUTLINE AGENT + SECTION WRITING. Entry: generate_multi_section_report (src/polaris_graph/generator/multi_section_generator.py) with PG_OUTLINE_AGENT=1; the outline agent is src/polaris_graph/outline/outline_agent.py (the React loop: build outline, auto-assign/fold evidence to sections, search_more_evidence, checklist gaps, finish_outline / BOUNCED / convergence ~9 turns). Then the parallel SECTION WRITERS that produce FREE PROSE via glm-5.2 (find the write prompt + how evidence baskets map to a section + [CITE:ev_xxx] provenance tokens). Document the exact flow, the convergence mechanism, how free-writing differs from a template renderer, model config (glm-5.2, temperature, max_tokens). file:line + quote the actual write-prompt.` },
  { key: 'verify_assemble', prompt: `READ-ONLY. cd ${WT}. Document STAGE 6-7: strict_verify (POST-HOC FAITHFULNESS) + ASSEMBLY. Read src/polaris_graph/generator/verified_compose.py and the strict_verify path. Document: how each generated sentence is verified against its cited evidence, how [CITE:ev_xxx] tokens resolve to a numbered [N] bibliography, the drop-and-regenerate-on-failure logic (a real run: 86 sentences verified / 96 dropped), the faithfulness audit (0 leaked tokens, all [N] resolve, faithfulness_pass=True). Then ASSEMBLY (scripts/compose_agentic_report_s3gear329.py ~line 249-340): sections + derived title + abstract + methods + bibliography + evidence table -> report.md. Read the actual 0.4447 report docs/step3_insight_lever_ab/control_report.md and characterize its prose quality (flowing, cites, evidence table). file:line.` },
  { key: 'score', prompt: `READ-ONLY. cd ${WT}. Document STAGE 8: RACE SCORING. The scorer is third_party/deep_research_bench/deepresearch_bench_race.py + prompt/criteria_prompt_en.py + score_prompt_en.py. Document: how RACE works (an LLM judge = openai/gpt-5.5 scores BOTH the target report AND a human reference report against per-task weighted criteria; Overall = target/(target+reference)), the 4 dimensions (Comprehensiveness, Insight, Instruction-Following, Readability) and their task-72 weights, what each criterion rewards. Then the ACTUAL 0.4447 result: results/race/polaris_step3_control/race_result.txt (Comp 0.4569, Insight 0.4293, IF 0.4587, Read 0.4310, Overall 0.4447). Note the reference is claude-3-7-sonnet (~0.42). file:line + exact numbers.` },
  { key: 'cost_time', prompt: `READ-ONLY. cd ${WT} and also check /home/polaris/wt/flywheel. Document TOKEN COST + WALL-CLOCK TIME for the whole champion pipeline. Hunt for cost ledgers (logs/pg_cost_ledger.jsonl, PG_COST_LEDGER_PATH, any *cost*.jsonl) and sum input/output/reasoning tokens and $ per stage. For TIME: the corpus SWEEP duration (cp3 run logs / _provenance created_utc vs sweep start), the compose elapsed (outputs/*/compose_summary.json 'elapsed_seconds' — a real run was ~1207s), the RACE score duration (control_race.log timestamps). Produce a per-stage AND total breakdown: (a) total tokens (in/out/reasoning), (b) total USD cost, (c) total wall-clock (mining + compose + score). If exact numbers aren't fully recoverable, give best estimates with the evidence and clearly mark them as estimates. Be concrete with file:line and actual figures.` },
]

const findings = await parallel(stages.map(s => () =>
  agent(s.prompt, { label: `doc:${s.key}`, phase: 'Investigate' })
))

phase('Synthesize')

const report = await agent(
  `You are writing the DEFINITIVE technical dossier of the "champion" deep-research pipeline that scored RACE Overall 0.4447 on DeepResearch Bench task 72. Six investigators documented the stages; their findings follow. Produce ONE comprehensive, polished, well-structured markdown report suitable for a technical/executive audience (a Telus AI meeting). 

Structure it as:
1. Executive summary (what the pipeline is, the 0.4447 result, the one-line "why it wins").
2. End-to-end flow diagram in text (Query -> Search -> Corpus -> Outline -> Write -> Verify -> Assemble -> Score) with a one-line description of each stage.
3. Stage-by-stage deep detail (each of the 8 stages: what runs, key files, config, the actual mechanism, concrete numbers).
4. The corpus (997 works, 841 papers, tiers, 2527-char passages) and WHY quality-of-evidence matters.
5. The scoring (RACE mechanics, the 4 dimensions + weights, the 0.4447 breakdown vs the reference).
6. COST & TIME: a clean table of tokens + USD + wall-clock, per stage and total.
7. Why it beats the alternatives (1 sentence on the cellcog contrast: write-freely-verify-after vs template-render).
Be precise, use the real numbers and file references from the findings, use tables where helpful, and write cleanly. Do NOT invent numbers — if a figure was marked an estimate, keep it marked.

=== STAGE 1-2 QUERY+SEARCH ===
${findings[0]||'(failed)'}
=== STAGE 3 CORPUS ===
${findings[1]||'(failed)'}
=== STAGE 4-5 OUTLINE+WRITE ===
${findings[2]||'(failed)'}
=== STAGE 6-7 VERIFY+ASSEMBLE ===
${findings[3]||'(failed)'}
=== STAGE 8 SCORE ===
${findings[4]||'(failed)'}
=== COST+TIME ===
${findings[5]||'(failed)'}`,
  { label: 'synthesize-dossier', phase: 'Synthesize', effort: 'high' }
)

return { report }
