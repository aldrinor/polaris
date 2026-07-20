export const meta = {
  name: 'foundation-audit',
  description: 'Codex-gated audit of 5 foundation items (config, checkpoints, logging, raw-A gates off, clean run script) before improvement work',
  phases: [{ title: 'Audit' }],
}

const SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['item', 'status', 'evidence', 'gaps', 'codex_verdict', 'recommendation'],
  properties: {
    item: { type: 'string' },
    status: { type: 'string', description: 'DONE | PARTIAL | GAP-FOUND | NOT-DONE — the honest state' },
    evidence: { type: 'string', description: 'concrete file:line evidence Claude found' },
    gaps: { type: 'string', description: 'exactly what is missing/broken, or "none"' },
    codex_verdict: { type: 'string', description: 'the token + one line Codex emitted after reading the files line-by-line itself' },
    recommendation: { type: 'string', description: 'what it would take to close the gap (do NOT implement now — just scope it)' },
  },
}

// All audits read the SAME current tree (has config migration + renames + straggler fixes).
const TREE = '/home/polaris/wt/phase-file'
const CODEX = `cd ${TREE} && timeout 300 codex exec --dangerously-bypass-approvals-and-sandbox -c model_reasoning_effort=high - < /tmp/CODEXPROMPT 2>&1 | tail -25`

const ITEMS = [
  {
    key: 'config',
    label: 'config-consolidation',
    prompt: `AUDIT ITEM 1 — "All config variables consolidated so any change is easy." Tree: ${TREE}. This is a VERIFY/SCOPE task — do NOT change code.
INVESTIGATE: (a) count os.getenv/os.environ read-sites still OUTSIDE src/polaris_graph/settings.py across src/ (grep -rn 'os.getenv\\|os.environ' src/polaris_graph | wc -l) and how many were migrated to resolve()/get_model_settings(); (b) read settings.py + config_defaults.py to see what IS centralized (model keys + registry); (c) categorize the remaining tail: secrets (*_KEY/_TOKEN), computed/multiline defaults, conflicting defaults. Is there a single place where an operator can change ANY setting? Or is it split across .env + config_defaults.py + hardcoded literals?
CODEX GATE (Codex reads the files itself, line by line): write your findings to /tmp/CODEXPROMPT prefixed with: 'You are codex-sol. cwd is a git worktree. INDEPENDENTLY read src/polaris_graph/settings.py, src/polaris_graph/config_defaults.py, and grep os.getenv across src/polaris_graph. Verify or refute this claim about how consolidated the config is, with exact counts and file:line. Is the claim "all variables consolidated, any change made in one place" TRUE, PARTIAL, or FALSE? Emit CONFIG-{CONSOLIDATED|PARTIAL|NOT}. Findings to verify:' then append your findings. Run: ${CODEX}
Return the schema with Codex's exact verdict token.`,
  },
  {
    key: 'checkpoint',
    label: 'checkpoint-coverage',
    prompt: `AUDIT ITEM 2 — "Checkpoint system in place across ALL connections." Tree: ${TREE}. VERIFY only, no code change.
INVESTIGATE: map every checkpoint/resume/snapshot in the pipeline — grep for 'checkpoint', 'snapshot', 'resume', 'save_state', '.json' writes, SqliteSaver/checkpointer, across src/polaris_graph and scripts/run_honest_sweep_r3.py + compose_agentic_report_s3gear329.py. List which pipeline STAGES (retrieval, corpus-approval, outline, section-gen, verification, render) have a checkpoint and which do NOT. Identify whether --resume actually resumes each stage or re-runs. "In all connections" — is coverage complete or are there stages with no checkpoint?
CODEX GATE: write findings to /tmp/CODEXPROMPT prefixed: 'You are codex-sol. cwd is a git worktree. INDEPENDENTLY grep and read the checkpoint/snapshot/resume machinery in src/polaris_graph and the two runner scripts. Verify which pipeline stages have checkpoints and which lack them. Is checkpoint coverage COMPLETE across all stages? Emit CHECKPOINT-{COMPLETE|PARTIAL|SPARSE}. Findings:' then append. Run: ${CODEX}
Return schema with a stage-by-stage checkpoint map in evidence/gaps.`,
  },
  {
    key: 'logging',
    label: 'logging-integrity',
    prompt: `AUDIT ITEM 3 — "All logs/reasoning visualized real-time + stored with NO loss." Tree: ${TREE}. VERIFY, no code change. KNOWN SYMPTOM: in a real run, reasoning_trace.jsonl came out 0 bytes (empty) — reasoning was lost.
INVESTIGATE: (a) where are reasoning_trace.jsonl / retrieval_trace.jsonl / tool_trace.jsonl written and WHEN (find the writers); (b) is reasoning captured on EVERY LLM call or only some? (the openrouter_client logs 'Reasoning logged' — is it also persisted to the trace file, or only to stdout?); (c) WHY can reasoning_trace.jsonl be empty — is the writer only called on certain paths / flushed at the end / lost on early abort? (d) the real-time dashboard (enable_dashboard) — what does it show and is trace persistence independent of it? Pinpoint the exact gap where reasoning is lost.
CODEX GATE: write findings to /tmp/CODEXPROMPT prefixed: 'You are codex-sol. cwd is a git worktree. INDEPENDENTLY find where reasoning/trace jsonl files are written and confirm whether reasoning from every LLM call is durably persisted or can be lost (e.g. only flushed at end, skipped on abort, dashboard-only). Explain the 0-byte reasoning_trace.jsonl. Emit LOGGING-{DURABLE|LOSSY}. Findings:' then append. Run: ${CODEX}
Return schema; the gap must name the exact file:line where reasoning can be dropped.`,
  },
  {
    key: 'gates_off',
    label: 'checker-entailment-off',
    prompt: `AUDIT ITEM 4 — "In raw-A, the checker (evaluator gate) AND entailment (NLI faithfulness) are COMPLETELY off." Tree: ${TREE}. VERIFY, no code change.
INVESTIGATE: trace the raw-A path scripts/compose_agentic_report_s3gear329.py -> generate_multi_section_report (src/polaris_graph/generator/multi_section_generator.py). Determine definitively: (a) Does it run the external evaluator / evaluator_gate / judge? (b) Does it run entailment/NLI verification (nli_verifier, entailment_judge, strict_verify, span-grounding, faithfulness gate)? Find the flags that gate each (PG_* env) and their effective values on the raw-A path. Confirm whether each is OFF, or partially ON. Quote the exact gating lines.
CODEX GATE: write findings to /tmp/CODEXPROMPT prefixed: 'You are codex-sol. cwd is a git worktree. INDEPENDENTLY trace compose_agentic_report_s3gear329.py and generate_multi_section_report and confirm whether the evaluator/checker gate and the entailment/NLI faithfulness verification actually RUN on the raw-A compose path, or are disabled. Cite the gating flags/lines. Emit GATES-{FULLY-OFF|PARTIAL|ON}. Findings:' then append. Run: ${CODEX}
Return schema; status must state clearly for BOTH checker and entailment whether each is off.`,
  },
  {
    key: 'runscript',
    label: 'clean-run-command',
    prompt: `DELIVERABLE ITEM 5 — "A single clean, reproducible run command." Tree: ${TREE}. This one CREATES a file.
CREATE scripts/run_raw_a.sh in ${TREE} that encapsulates the PROVEN raw-A recipe as ONE command, capturing every fragile env trick so a run is never a coin flip: (1) LD_LIBRARY_PATH from the userspace browser libs; (2) PG_LOOPBACK_MODE=0 (else hangs — .env pins =1); (3) PG_OUTLINE_AGENT=1, PG_CONTENT_RELEVANCE_SCORE_CHUNK=16, PYTORCH_ALLOC_CONF=expandable_segments:True; (4) PG_OUTLINE_MAX_TOKENS=131072, PG_OUTLINE_REASONING_MAX_TOKENS=32768 (prevents the deepseek truncation crash); (5) OPENROUTER_API_KEY/SERPER_API_KEY via python dotenv_values (NEVER bash-source .env — line 304 breaks bash); (6) unset PYTHONPATH; (7) interpreter /home/polaris/pipeline-env/bin/python; (8) args --corpus <path> --rq-drb-task <task> --out-dir <dir>. Make corpus/task/out configurable via flags with sane defaults. Add a header comment explaining each knob and WHY. Do a py/bash syntax check (bash -n). Do NOT execute a paid compose.
CODEX GATE: write the script + rationale to /tmp/CODEXPROMPT prefixed: 'You are codex-sol. cwd is a git worktree. INDEPENDENTLY read the new scripts/run_raw_a.sh line by line and verify it faithfully captures every required env knob (list below) with correct values, is syntactically valid, and would reproduce a raw-A run deterministically-as-possible. Flag any missing/wrong knob. Emit RUNSCRIPT-{SOUND|REVISE}. Required knobs and the script:' then append the knob list + the script. Run: ${CODEX}
Return schema; evidence = the script path + bash -n result; codex_verdict = the token.`,
  },
]

phase('Audit')
const results = await parallel(ITEMS.map(it => () =>
  agent(it.prompt, { schema: SCHEMA, phase: 'Audit', label: it.label })
))

return { results: results.filter(Boolean) }