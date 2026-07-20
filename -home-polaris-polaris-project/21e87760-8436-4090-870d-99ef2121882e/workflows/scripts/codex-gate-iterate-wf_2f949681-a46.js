export const meta = {
  name: 'codex-gate-iterate',
  description: 'Iterate Claude+Codex-sol(max) on the 3 open gates until Codex emits a clean verdict token (logging, checker/entailment, run-script)',
  phases: [{ title: 'Iterate' }],
}

const SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['item', 'codex_token', 'attempts', 'codex_reasoning', 'claude_finding', 'converged'],
  properties: {
    item: { type: 'string' },
    codex_token: { type: 'string', description: 'the exact clean verdict token Codex emitted (or NONE if never converged)' },
    attempts: { type: 'number', description: 'how many Codex runs it took' },
    codex_reasoning: { type: 'string', description: "Codex's one-paragraph justification with file:line" },
    claude_finding: { type: 'string', description: "Claude's own conclusion, and whether Codex agreed" },
    converged: { type: 'boolean', description: 'true only if Codex emitted a clean token' },
  },
}

const TREE = '/home/polaris/wt/phase-file'
// max reasoning, 15-min window per attempt, sandbox off (approved) so codex reads files.
const codexRun = (key) => `cd ${TREE} && timeout 900 codex exec --dangerously-bypass-approvals-and-sandbox -c model_reasoning_effort=max - < /tmp/gate_${key}.md 2>&1 | tail -40`

const ITEMS = [
  {
    label: 'gate-checker-entailment',
    prompt: `ITERATE Codex-sol(max) until it emits a clean GATES-{FULLY-OFF|PARTIAL|ON} token. Tree: ${TREE}.
KNOWN (Claude already traced this — Codex must confirm/refute by reading files): on the raw-A compose path, the external EVALUATOR/CHECKER gate does NOT run (by design — it's an offline scorer; compose imports external_evaluator only for a sentence-boundary helper), and the ENTAILMENT/NLI gate IS ON: PG_STRICT_VERIFY_ENTAILMENT default = "enforce" in src/polaris_graph/clinical_generator/strict_verify.py, and verify_sentence_provenance (src/polaris_graph/generator/provenance_generator.py) drops NEUTRAL/CONTRADICTED sentences under enforce. Expected token: GATES-PARTIAL.
LOOP (up to 4 attempts): write a NARROW prompt to /tmp/gate_checker.md that tells Codex: "Answer in <=12 lines. Do NOT read CLAUDE.md or plan/governance docs. Read ONLY strict_verify.py, provenance_generator.py, compose_agentic_report_s3gear329.py, external_evaluator.py. Q1: is the external evaluator gate RUN on the raw-A compose path? Q2: is PG_STRICT_VERIFY_ENTAILMENT default 'enforce' and does verify_sentence_provenance drop sentences under it? End with exactly one line: GATES-FULLY-OFF or GATES-PARTIAL or GATES-ON." Then run: ${codexRun('checker')}. If the output does NOT contain one of the three GATES- tokens as Codex's OWN answer (not just the enum in the prompt), NARROW further (name exact line numbers, ask stricter yes/no) and retry. Stop when Codex emits a clean token.
Return schema; codex_token = the token Codex actually emitted; converged=true only if it did.`,
  },
  {
    label: 'gate-logging',
    prompt: `ITERATE Codex-sol(max) until it emits a clean LOGGING-{DURABLE|LOSSY} token. Tree: ${TREE}.
CONTEXT: reasoning_trace.jsonl came out 0 bytes in a real run. A prior trace found that in scripts/run_honest_sweep_r3.py::run_one_query the trace sink is wired write-through with an up-front flush (~lines 9384-9398), so for the SWEEP runner reasoning IS durable — meaning the 0-byte trace likely came from the COMPOSE path (scripts/compose_agentic_report_s3gear329.py) which may not wire the sink at all. Confirm the real story.
FIRST briefly verify yourself (grep the reasoning_trace.jsonl writers in scripts/ + src/polaris_graph, and whether compose_agentic_report_s3gear329.py wires any reasoning sink). THEN loop (up to 4 attempts): write a NARROW prompt to /tmp/gate_logging.md: "Answer in <=12 lines. Do NOT read CLAUDE.md/governance. Find every writer of reasoning_trace.jsonl. Is the reasoning from LLM calls durably persisted on the run_honest_sweep_r3 path? Is it persisted on the compose_agentic_report_s3gear329 path? Explain the 0-byte trace with file:line. End with exactly: LOGGING-DURABLE or LOGGING-LOSSY." Then run: ${codexRun('logging')}. Retry (narrowing) until Codex emits a clean LOGGING- token.
Return schema; converged=true only if Codex emitted the token.`,
  },
  {
    label: 'gate-runscript',
    prompt: `ITERATE Claude+Codex-sol(max) until Codex emits RUNSCRIPT-SOUND for scripts/run_raw_a.sh. Tree: ${TREE}.
The script scripts/run_raw_a.sh already exists (created + partly fixed in a prior pass; Codex earlier said RUNSCRIPT-REVISE then fixes were applied). Now: (1) read the CURRENT scripts/run_raw_a.sh; run bash -n on it; (2) loop (up to 4 attempts): write a NARROW prompt to /tmp/gate_runscript.md: "Answer in <=15 lines. Do NOT read CLAUDE.md/governance. Read ONLY scripts/run_raw_a.sh. Verify it captures every required knob with correct values: LD_LIBRARY_PATH from browserlibs/LDPATH.txt, PG_LOOPBACK_MODE=0, PG_OUTLINE_AGENT=1, PG_CONTENT_RELEVANCE_SCORE_CHUNK=16, PYTORCH_ALLOC_CONF=expandable_segments:True, PG_OUTLINE_MAX_TOKENS=131072, PG_OUTLINE_REASONING_MAX_TOKENS=32768, keys via dotenv_values (never bash-source .env), unset PYTHONPATH, interpreter /home/polaris/pipeline-env/bin/python, flags --corpus/--rq-drb-task/--out-dir. Valid bash syntax. End with exactly: RUNSCRIPT-SOUND or RUNSCRIPT-REVISE + the specific fix if REVISE." Then run: ${codexRun('runscript')}. If Codex says RUNSCRIPT-REVISE, APPLY the exact fix it names to scripts/run_raw_a.sh, re-run bash -n, and re-gate. Repeat until Codex emits RUNSCRIPT-SOUND. Do NOT run a paid compose. Do NOT commit.
Return schema; codex_token must be RUNSCRIPT-SOUND on convergence; claude_finding lists any fixes applied.`,
  },
]

phase('Iterate')
const results = await parallel(ITEMS.map(it => () =>
  agent(it.prompt, { schema: SCHEMA, phase: 'Iterate', label: it.label })
))

return { results: results.filter(Boolean) }