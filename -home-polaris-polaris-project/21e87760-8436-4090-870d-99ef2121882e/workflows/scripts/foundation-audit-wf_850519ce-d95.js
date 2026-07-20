export const meta = {
  name: 'foundation-audit',
  description: 'Codex-sol(max)-gated audit of 5 foundation items before improvement work',
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
    codex_verdict: { type: 'string', description: 'the token + one line Codex-sol emitted after reading files line-by-line' },
    recommendation: { type: 'string', description: 'what it would take to close the gap (scope only, do NOT implement)' },
  },
}

const TREE = '/home/polaris/wt/phase-file'
// sol model, MAX reasoning, sandbox off (user-approved) so codex reads files line-by-line.
const codexCmd = (key) => `cd ${TREE} && timeout 360 codex exec --dangerously-bypass-approvals-and-sandbox -c model_reasoning_effort=max - < /tmp/codex_${key}.md 2>&1 | tail -25`

const ITEMS = [
  {
    label: 'config-consolidation',
    prompt: `AUDIT ITEM 1 — "All config variables consolidated so any change is easy." Tree: ${TREE}. VERIFY/SCOPE only — do NOT change code. UNIQUE Codex prompt file: /tmp/codex_config.md (use no other path).
INVESTIGATE: (a) count os.getenv/os.environ read-sites still OUTSIDE src/polaris_graph/settings.py across src/, and how many were migrated to resolve()/get_model_settings(); (b) read settings.py + config_defaults.py to see what IS centralized; (c) categorize the remaining tail: secrets (*_KEY/_TOKEN), computed/multiline defaults, conflicting defaults. Is there a single place to change ANY setting, or split across .env + config_defaults.py + hardcoded literals?
CODEX GATE (codex reads files line-by-line): write findings to /tmp/codex_config.md prefixed: 'You are codex-sol. cwd is a git worktree. INDEPENDENTLY read src/polaris_graph/settings.py, src/polaris_graph/config_defaults.py, grep os.getenv across src/polaris_graph. Verify/refute with exact counts + file:line. Is "all variables consolidated, any change in one place" TRUE/PARTIAL/FALSE? Emit CONFIG-{CONSOLIDATED|PARTIAL|NOT}. Findings:' then append findings. Run: ${codexCmd('config')}
Return schema with Codex's exact verdict token.`,
  },
  {
    label: 'checkpoint-coverage',
    prompt: `AUDIT ITEM 2 — "Checkpoint system across ALL connections." Tree: ${TREE}. VERIFY only. UNIQUE Codex prompt file: /tmp/codex_checkpoint.md.
INVESTIGATE: map every checkpoint/resume/snapshot — grep 'checkpoint','snapshot','resume','save_state',SqliteSaver/checkpointer across src/polaris_graph + scripts/run_honest_sweep_r3.py + scripts/compose_agentic_report_s3gear329.py. List which STAGES (retrieval, corpus-approval, outline, section-gen, verification, render) have a checkpoint and which do NOT; does --resume truly resume each stage? Complete or gaps?
CODEX GATE: write findings to /tmp/codex_checkpoint.md prefixed: 'You are codex-sol. cwd is a git worktree. INDEPENDENTLY read the checkpoint/snapshot/resume machinery. Which stages have checkpoints, which lack them? Complete? Emit CHECKPOINT-{COMPLETE|PARTIAL|SPARSE}. Findings:' then append. Run: ${codexCmd('checkpoint')}
Return schema with a stage-by-stage map.`,
  },
  {
    label: 'logging-integrity',
    prompt: `AUDIT ITEM 3 — "All logs/reasoning real-time + stored with NO loss." Tree: ${TREE}. VERIFY. UNIQUE Codex prompt file: /tmp/codex_logging.md. SYMPTOM: reasoning_trace.jsonl came out 0 bytes in a real run.
INVESTIGATE: (a) where reasoning_trace.jsonl / retrieval_trace.jsonl / tool_trace.jsonl are written and WHEN; (b) is reasoning persisted on EVERY LLM call or only some (openrouter_client logs 'Reasoning logged' — persisted or stdout-only?); (c) WHY reasoning_trace can be empty (writer only some paths / flushed at end / lost on abort?); (d) dashboard vs durable persistence. Pinpoint exact file:line where reasoning is lost.
CODEX GATE: write findings to /tmp/codex_logging.md prefixed: 'You are codex-sol. cwd is a git worktree. INDEPENDENTLY find where reasoning/trace jsonl are written; is reasoning from every LLM call durably persisted or can it be lost? Explain the 0-byte trace. Emit LOGGING-{DURABLE|LOSSY}. Findings:' then append. Run: ${codexCmd('logging')}
Return schema; gap names the exact file:line where reasoning can drop.`,
  },
  {
    label: 'checker-entailment-off',
    prompt: `AUDIT ITEM 4 — "In raw-A, checker (evaluator gate) AND entailment (NLI faithfulness) COMPLETELY off." Tree: ${TREE}. VERIFY. UNIQUE Codex prompt file: /tmp/codex_gates.md.
INVESTIGATE: trace scripts/compose_agentic_report_s3gear329.py -> generate_multi_section_report (src/polaris_graph/generator/multi_section_generator.py). Definitively: (a) does it run the external evaluator/evaluator_gate/judge? (b) does it run entailment/NLI (nli_verifier, entailment_judge, strict_verify, span-grounding, faithfulness gate)? Find the PG_* flags gating each + effective values on the raw-A path; is each OFF or partially ON? Quote gating lines.
CODEX GATE: write findings to /tmp/codex_gates.md prefixed: 'You are codex-sol. cwd is a git worktree. INDEPENDENTLY trace compose_agentic_report_s3gear329.py and generate_multi_section_report; do the checker gate and entailment/NLI verification RUN on raw-A or are they disabled? Cite flags/lines. Emit GATES-{FULLY-OFF|PARTIAL|ON}. Findings:' then append. Run: ${codexCmd('gates')}
Return schema; status states clearly for BOTH checker and entailment whether each is off.`,
  },
  {
    label: 'clean-run-command',
    prompt: `DELIVERABLE ITEM 5 — "A single clean reproducible run command." Tree: ${TREE}. CREATES a file. UNIQUE Codex prompt file: /tmp/codex_runscript.md.
CREATE scripts/run_raw_a.sh capturing the PROVEN raw-A recipe as ONE command: (1) LD_LIBRARY_PATH from cat /tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/browserlibs/LDPATH.txt; (2) PG_LOOPBACK_MODE=0 (else hangs); (3) PG_OUTLINE_AGENT=1, PG_CONTENT_RELEVANCE_SCORE_CHUNK=16, PYTORCH_ALLOC_CONF=expandable_segments:True; (4) PG_OUTLINE_MAX_TOKENS=131072, PG_OUTLINE_REASONING_MAX_TOKENS=32768 (prevents deepseek truncation); (5) OPENROUTER_API_KEY/SERPER_API_KEY via python dotenv_values (NEVER bash-source .env — line 304 breaks bash); (6) unset PYTHONPATH; (7) interpreter /home/polaris/pipeline-env/bin/python; (8) flags --corpus/--rq-drb-task/--out-dir with sane defaults. Header comment explains each knob + WHY. bash -n syntax check. Do NOT run a paid compose.
CODEX GATE: write script+rationale to /tmp/codex_runscript.md prefixed: 'You are codex-sol. cwd is a git worktree. INDEPENDENTLY read scripts/run_raw_a.sh line by line: does it capture every required knob with correct values, valid syntax, reproducible? Flag missing/wrong. Emit RUNSCRIPT-{SOUND|REVISE}. Required knobs + script:' then append knob list + script. Run: ${codexCmd('runscript')}
Return schema; evidence = script path + bash -n result; codex_verdict = token.`,
  },
]

phase('Audit')
const results = await parallel(ITEMS.map(it => () =>
  agent(it.prompt, { schema: SCHEMA, phase: 'Audit', label: it.label })
))

return { results: results.filter(Boolean) }