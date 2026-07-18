export const meta = {
  name: 'pipeline-stall-investigation',
  description: 'In-depth read-only investigation of the stalled compose + audit tracks, synthesized into a findings brief for Sol',
  phases: [
    { title: 'Investigate', detail: 'parallel deep-dive: compose state, audit hang, pipeline readiness' },
    { title: 'Synthesize', detail: 'combine into one findings brief for Sol' },
  ],
}

const SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['area', 'state', 'root_cause', 'evidence', 'recommendation'],
  properties: {
    area: { type: 'string' },
    state: { type: 'string', description: 'stalled/progressing/broken/recoverable — concise' },
    root_cause: { type: 'string' },
    evidence: { type: 'string', description: 'concrete log lines / file states / numbers observed' },
    recommendation: { type: 'string', description: 'what a fix should do (findings, not implementation)' },
    reliable_command: { type: 'string', description: 'the exact command sequence to run this step cleanly, if known' },
  },
}

const AREAS = [
  { id: 'compose', title: 'Investigate', label: 'compose-state',
    prompt: `Investigate READ-ONLY what the compose agent is doing and whether it is stalled. The compose agent (running general-purpose) was told to fix report_ast facet-wiring, run the production composer (cellcog_composer.py) on outputs/evidence_cards_full.json (5,759 cards), and score with score_report_race.py. Symptoms: no report file written; cellcog_composer not always in the process tree; its scratch logs are in /tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/ (dry.log, dry2.log, fab_base.log, fab_mine.log, t.log). Determine: (1) exactly what stage the compose reached; (2) the meaning of "Positive controls: REGRESSED — a legitimate node was rejected" in fab_base/fab_mine.log — is it blocking the render? (3) the bindings re-verification result (dry2.log showed "5294 admitted, 2572 refused" as CARD_IS_UNBOUND corroborators, "279 evidence units available") — is that a data problem that starves the report? (4) whether a full render ever ran and how long cellcog_composer actually takes; (5) the EXACT clean command sequence to compose + score reliably. Read cellcog_composer.py's __main__ args, FLYWHEEL_PROGRESS.md, and recent git log for the last known-good compose+score invocation. Do NOT modify anything or kill any process.` },
  { id: 'audit', title: 'Investigate', label: 'audit-hang',
    prompt: `Investigate READ-ONLY why the glm-5.2 card audit hung. It stopped at 175/5759 and its log (/tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/audit_run.log) is now full of "Task was destroyed but it is pending!". The audit tooling is in scripts/card_audit/ (harness.py, tier0.py, disposition.py, judge_guard.py). It was repointed from claude-p-opus to OpenRouter glm-5.2. Determine: (1) the ROOT CAUSE of the asyncio hang — is it asyncio.run()/async OpenRouterClient called inside ThreadPoolExecutor worker threads (event loop destroyed → pending tasks killed)? Read harness.py's transport and the orchestrator the agent built. (2) Did the audit produce ANYTHING usable before hanging (the earlier report showed 100% quarantine — a separate calibration bug)? (3) Is it checkpoint-resumable from 175? (4) What is the CORRECT transport for glm-5.2 in a threaded worker (a synchronous requests/httpx POST per call, not the async client)? Recommend the fix shape (not implementation). Do NOT modify anything or kill any process.` },
  { id: 'pipeline', title: 'Investigate', label: 'pipeline-readiness',
    prompt: `Investigate READ-ONLY the readiness of the compose->score pipeline for a CLEAN direct run (bypassing the stuck agents). Determine: (1) is outputs/evidence_cards_full.json (5,759 cards) valid and consumable by cellcog_composer.py as-is? (2) the report_ast facet-wiring: is _facet_contract() now using research_contract.compile_contract (the fix), and does report_ast import cleanly? (3) the exact score_report_race.py invocation — read its __main__/docstring: it needs the DRB task prompt/reference/criteria (data/prompt_data/query.jsonl) and judges with gpt-5.5 via OpenRouter; what are the required args and env? (4) the "2572 refused corroborators / 279 units" — does the composer need corroborator bindings, or does it compose fine from the 5294 admitted primary bindings? (5) provenance_graph.json — does it exist and strict-load (the composer re-verifies bindings against it)? Produce the EXACT command sequence + env for a clean compose->score run someone could execute directly. Do NOT modify anything.` },
]

phase('Investigate')
const findings = await parallel(AREAS.map(a => () =>
  agent(a.prompt, { schema: SCHEMA, label: a.label, phase: 'Investigate' })
))
const clean = findings.filter(Boolean)

phase('Synthesize')
const synth = await agent(
  `You are synthesizing a stall-investigation into ONE findings brief for Sol (the design authority) to design the solution. Here are the structured findings from three parallel investigators:\n\n${JSON.stringify(clean, null, 2)}\n\nWrite a concise, decision-ready brief (markdown) covering: (1) COMPOSE — is it recoverable or should we run it clean directly; the exact reliable command; any data/regression blocker. (2) AUDIT — root cause of the asyncio hang and the correct fix shape; whether to fix-and-resume or defer. (3) The RELIABLE PATH to a scored report (the deliverable the operator wants tonight), step by step with exact commands. (4) Open questions Sol must decide. Save it by printing it in full. Be concrete — this goes straight to Sol.`,
  { label: 'synthesize', phase: 'Synthesize' }
)
return { findings: clean, brief: synth }
