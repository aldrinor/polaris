export const meta = {
  name: 'gate-e2e-shakeout',
  description: 'Offline shakeout of the gate e2e path: fix live-compiler fatal errors, fix domain=workforce + fail-loud harness, build a network-mocked dry-e2e integration test so the next live run is clean. Faithfulness FROZEN.',
  phases: [
    { title: 'Compiler', detail: 'diagnose+fix the 3 fatal compile errors (full-strength contract w/ coverage)' },
    { title: 'Harness', detail: 'domain=workforce, fail-loud, mocked dry-e2e integration test' },
    { title: 'Verify', detail: 'run dry-e2e, faithfulness check, commit' },
  ],
}

const GUARD = `
HARD GUARDRAILS (violating any = failure):
- EDIT ONLY /home/polaris/wt/outline_agent on branch gate-s0-s5 (latest commit b444ed5). NEVER edit /home/polaris/wt/flywheel.
- FAITHFULNESS FROZEN: never modify src/polaris_graph/generator/provenance_generator.py or strict_verify / citation-verification. READ ONLY.
- Additive/minimal; keep gate behind default-OFF PG_GATE (OFF path byte-identical).
- Do NOT run a full ~35-min live retrieval/compose (shell caps at 10 min). The contract-compiler LLM call is FAST (1-2 calls) and IS allowed for diagnosis. Everything else must be OFFLINE / network-mocked.
CONTEXT: We are proving the Research Planning Gate on DRB v1 task 72 via scripts/run_gate_e2e.py -> scripts/run_honest_sweep_r3.py:run_one_query (the fresh entry with the gate hook at ~line 10436). A live probe just aborted with TWO problems:
 (1) run_one_query's scope_gate rejected domain='labor' — task 72's real domain is 'workforce' (SUPPORTED_DOMAINS in src/polaris_graph/nodes/scope_gate.py:79; champion run_id was SWEEP_workforce_drb_72_ai_labor). The harness set domain='labor' from the slug.
 (2) the live contract compiler logged "contract compile still invalid after retry: 3 fatal errors" -> fell back to the conservative contract (compiler_degraded=True, coverage=0) so the gate ran at HALF strength.
 (3) the harness printed "[gate-e2e] ALL OK" even though the run ABORTED — a false-success reporting bug.
Env to run the gate compiler live: source /home/polaris/wt/outline_agent/.env ; needs PG_PLANNING_GATE_LIVE=1 + OPENROUTER_API_KEY.
`

phase('Compiler')
const compiler = await agent(`${GUARD}
FIX (1) the live contract compiler's 3 FATAL VALIDATION ERRORS.
- Reproduce: source .env, then run the gate compiler LIVE on the task-72 prompt (PG_PLANNING_GATE_LIVE=1) via src/polaris_graph/planning/research_planning_gate.py:run_research_planning_gate(prompt, mode="autonomous") — the task-72 prompt is in third_party/deep_research_bench/data/prompt_data/query.jsonl id 72. Capture the 3 fatal validator errors verbatim.
- Diagnose whether the fault is (a) the compiler SYSTEM PROMPT / output schema producing malformed contracts, or (b) the deterministic VALIDATORS being too strict / mismatched to the schema. Fix the real cause so a valid FULL-STRENGTH contract is produced: coverage requirements populated (>0), sub-questions present, journal-only + English as EXPLICIT hard terms with spans, assumptions recorded for inferred terms — WITHOUT relaxing the no-invention rule (hard term still requires origin==explicit). Keep the fail-soft conservative fallback intact as a last resort, but it must NOT be the normal path for task 72.
- Prove it: after the fix, a live autonomous compile of task 72 returns state=auto_pinned, compiler_degraded=FALSE, coverage>0, >=1 explicit hard term (journal-only), needs_input=false. Add/adjust a fast test (mock or 1 gated live call) asserting compiler_degraded is False and coverage>0 on task 72.
Report: the 3 errors verbatim, the root cause, the exact fix (file:line), and the post-fix live compile summary. Do NOT commit (the Verify phase commits).`, { label: 'compiler:fix-fatal-errors', phase: 'Compiler' })

phase('Harness')
const harness = await agent(`${GUARD}
FIX (2) domain + (3) false-OK, and BUILD the network-mocked dry-e2e integration test. (The compiler fix from the prior phase is already in the tree.)
- DOMAIN: in scripts/run_gate_e2e.py, map each DRB task to the domain run_one_query's scope_gate accepts (src/polaris_graph/nodes/scope_gate.py SUPPORTED_DOMAINS = {ai_sovereignty,canada_us,clinical,custom,due_diligence,policy,tech,workforce}). Task 72 -> 'workforce'. Investigate how the champion maps DRB tasks->domains (grep 'workforce', drb task->domain tables, SWEEP_workforce) and reuse it; if no clean table exists, task 72='workforce' at minimum and a documented default for others. The q dict passed to run_one_query must carry the accepted domain.
- FAIL-LOUD: the harness must NOT print "ALL OK" when run_one_query aborts (e.g. '[ABORT] Scope rejected') or when no report.md is produced. Detect abort / missing report.md / scope reject and exit NON-ZERO with a clear message. A live run that produced no scoreable report is a FAILURE, not OK.
- MOCKED DRY-E2E INTEGRATION TEST (the key deliverable): a test (tests/planning/test_gate_e2e_integration.py) or a --dry-e2e harness mode that drives the FULL harness path against run_one_query's REAL interface with the NETWORK MOCKED (stub FS-Researcher/live retrieval + the compose LLM calls). It must prove, offline: gate -> q dict has an accepted domain + verbatim task-72 question -> run_one_query is invoked with PG_GATE/PG_USE_RESEARCH_PLANNER so the projection threads to the retrieval hook -> a report.md path is produced -> the RACE+FACT scoring stage receives valid inputs. Assert NO wiring mismatch (domain accepted, prompt byte-matches, projection reached, scoring inputs present) and that fail-loud triggers if any stage yields no report. This is what guarantees the next LIVE run completes.
Report: exact edits (file:line), the domain mapping source, and the dry-e2e test output. Do NOT commit.`, { label: 'harness:domain-faill-loud-drye2e', phase: 'Harness' })

phase('Verify')
const verdict = await agent(`${GUARD}
FINAL VERIFY + COMMIT. On branch gate-s0-s5:
1. Confirm provenance_generator.py has a CLEAN diff (0 lines) and nothing under /home/polaris/wt/flywheel changed.
2. Run the full new/affected fast test suite (pytest -q tests/planning + the new integration test); run the mocked dry-e2e integration test and confirm it passes end-to-end. Report pass/fail counts.
3. Confirm: live compiler on task 72 now compiler_degraded=FALSE + coverage>0 (from the Compiler phase); harness domain=workforce; fail-loud works; PG_GATE OFF path byte-identical.
4. Clean __pycache__, git add -A, commit to gate-s0-s5 with a message describing the shakeout (compiler fatal-errors fixed; domain=workforce; fail-loud; mocked dry-e2e integration test). End with:
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Do NOT push. Return a structured verdict.`, { label: 'verify-commit', phase: 'Verify', schema: {
  type: 'object', additionalProperties: false,
  required: ['faithfulness_untouched','compiler_degraded_fixed','domain_fixed','fail_loud_works','dry_e2e_passes','tests_passed','tests_failed','commit_hash','summary','risks'],
  properties: {
    faithfulness_untouched: { type: 'boolean' },
    compiler_degraded_fixed: { type: 'boolean' },
    domain_fixed: { type: 'boolean' },
    fail_loud_works: { type: 'boolean' },
    dry_e2e_passes: { type: 'boolean' },
    tests_passed: { type: 'integer' },
    tests_failed: { type: 'integer' },
    commit_hash: { type: 'string' },
    coverage_on_task72: { type: 'string' },
    summary: { type: 'string' },
    risks: { type: 'array', items: { type: 'string' } },
  },
} })

return { branch: 'gate-s0-s5', verdict }
