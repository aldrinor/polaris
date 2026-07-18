export const meta = {
  name: 'gate-s0-s5-build',
  description: 'Build the Research Planning Gate S0–S5 (code + cheap validation + S5 harness) in the CHAMPION pipeline. Faithfulness FROZEN. Expensive live runs deferred to monitored jobs.',
  phases: [
    { title: 'Setup', detail: 'branch off champion' },
    { title: 'S0', detail: 'port rule-reader + candidate adapter' },
    { title: 'S1', detail: 'contract+plan schema + compiler + stratified audit' },
    { title: 'S2', detail: 'retrieval projection + query-gen telemetry proof' },
    { title: 'S3', detail: 'outline FEED + gap-scope fix + banked replay' },
    { title: 'S4', detail: 'compose/render projections + compliance audit' },
    { title: 'S5-harness', detail: 'end-to-end run/score harness + dry smoke' },
    { title: 'Verify', detail: 'faithfulness/off-path/tests' },
    { title: 'Commit', detail: 'commit locally (push done by main session)' },
  ],
}

const SPEC = `SPEC DOCS (read both FIRST, in full):
- Consolidated design + build sequence: /home/polaris/polaris_project/GATE_DESIGN_CONSOLIDATED.md
- Sol's detailed hook map + schema: /tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/reviews/gate_gate_design.md
- (fallback if that path 404s) /tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/reviews/sol_gate_design.md`

const GUARD = `
HARD GUARDRAILS (violating any = failure):
- EDIT ONLY the champion repo /home/polaris/wt/outline_agent (branch gate-s0-s5). NEVER edit /home/polaris/wt/flywheel (read-only reference).
- FAITHFULNESS FROZEN: never modify src/polaris_graph/generator/provenance_generator.py or any strict_verify / citation-verification logic. READ ONLY. No new verification pass.
- Every new behavior behind a default-OFF flag (or a None-default kwarg) so the OFF path is BYTE-IDENTICAL to today's champion. Follow the repo's existing flag pattern.
- Additive & minimal. Prefer NEW modules over rewriting. Never invent a hard constraint that isn't from explicit prompt text (design rule).
- Scope must reach RETRIEVAL query generation — NEVER a post-fetch filter of a frozen corpus (the 997->131 anti-pattern).
- Do NOT run any full ~35-min live compose or RACE/FACT scoring (a workflow shell caps at 10 min). Use fast unit tests, OFFLINE compiles, BANKED replays, and query-gen TELEMETRY (no fetch) only. If a step needs a live run, BUILD + unit-test it and leave a documented harness; do not execute it.
- If a task needs a frozen/forbidden file, STOP and report instead.
${SPEC}
`

phase('Setup')
const setup = await agent(`${GUARD}
STEP: In /home/polaris/wt/outline_agent (currently on bot/outline-agent-box @ df4118a), create and checkout a new branch gate-s0-s5. Confirm clean base. Do NOT commit yet. Read the two SPEC docs now and report a 6-line summary confirming you understand the thesis (contract -> existing levers; scope-at-retrieval; FEED outline agent; faithfulness frozen).`, { label: 'setup:branch', phase: 'Setup' })

phase('S0')
const s0 = await agent(`${GUARD}
IMPLEMENT S0 — Port + reconcile (no behavior change).
- Port the validated rule-reader from branch round1-if-compiler into the champion tree: bring src/polaris_graph/instruction/constraint_extractor.py + its tests (view via: git show round1-if-compiler:src/polaris_graph/instruction/constraint_extractor.py). Do NOT bring the compose-time filter_eligible wiring or any coverage-to-heading mapping.
- Create ONE candidate adapter (new module, e.g. src/polaris_graph/planning/candidate_adapter.py) that reconciles the rule-reader with the champion intake extractors src/polaris_graph/retrieval/intake_constraint_extractor.py (extract_constraints_regex / extract_instruction_slots / extract_scope_constraints). Deterministic-wins-on-overlap; preserve exact prompt spans. Output: a list of candidate constraints with spans + origin, NOT a pinned contract.
- Unit tests: adapter merges correctly on task-72 prompt (journal-only/English EXPLICIT with spans); no behavior change elsewhere.
Report files added + test results. Nothing wired into the pipeline yet.`, { label: 's0:port-adapter', phase: 'S0' })

phase('S1')
const s1 = await agent(`${GUARD}
IMPLEMENT S1 — Contract + plan schema + compiler (OFFLINE, no retrieval).
- New module(s) e.g. src/polaris_graph/planning/planning_gate_schema.py: the typed ResearchContract + ResearchExecutionPlan + PlanningGateArtifact per the consolidated design §3 (Sol's typed skeleton + Fable's Tagged provenance: every term has origin[explicit|user|inferred|policy_default], force[hard|prefer|open], spans, enforcement_stages). Use pydantic/dataclass, strict parsing. HARD force invalid unless origin==explicit/user (mechanical no-invention).
- Compiler: src/polaris_graph/planning/research_planning_gate.py with the two structured LLM calls (contract compiler, plan compiler) using the repo's model resolver (small model, e.g. glm-5.2 policy model). System prompts per Sol §3 (forbid inventing constraints; require spans for explicit; open/null for unspecified; decompose compound; record ambiguities/assumptions/conflicts; clause_coverage). Reuse constraint_extractor.parse_constraints_json parser discipline (fence-tolerant, fail-soft). Deterministic validators: quote equality, no inferred-hard, clause coverage, conflicts. Autonomous mode = pure contract->contract, NO I/O, never blocks; interactive mode returns needs_input with <=3 material questions.
- Reuse research_planner.py serialize_plan_canonical / plan_sha256 for hashing.
- Tests (offline; mock the LLM or use a tiny live call gated by a flag): (a) on task-72 prompt the compiled contract has journal-only/English as EXPLICIT hard terms with spans, literature_review deliverable, 4 coverage requirements; (b) an unspecified-recency prompt yields recency force=open (never hard); (c) autonomous mode NEVER returns needs_input (assert no blocking); (d) a hard term with origin=inferred is REJECTED by the validator.
- SMOKE audit (small, in-workflow): compile ~8 stratified DRB prompts (narrow, compound, non-English, source-restricted, format-heavy) in autonomous mode; assert no invented hard constraint and an assumption record for every inferred term. (The FULL 100-prompt audit is deferred to a monitored job — just note it.)
Report files, test results, and the 8-prompt smoke summary.`, { label: 's1:schema-compiler', phase: 'S1' })

phase('S2')
const s2 = await agent(`${GUARD}
IMPLEMENT S2 — Retrieval projection (the no-starvation core). CODE + TELEMETRY PROOF ONLY (no live fetch).
- Add contract.to_research_frame() / to_scope_terms() compile methods (or a RetrievalProjection) mapping source_types->evidence_needs (route scholarly backends), languages->native queries, entities->sub-entity queries, hard scope->query text + backend filter, soft->ranking.
- Wire (behind default-OFF flag PG_GATE=1): thread the retrieval projection into src/polaris_graph/retrieval/fs_researcher_query_gen.py (_plan_expert_facet_queries / plan_fs_researcher_queries) and src/polaris_graph/retrieval/live_retriever.py:run_live_retrieval (populate research_frame/protocol/amplified_queries). In scripts/run_honest_sweep_r3.py:run_one_query FS branch, pass the projection instead of discarding _research_plan.sub_queries.
- PROOF (offline, NO network fetch): a test that runs ONLY query generation for the task-72 contract and asserts the emitted query strings/frontier contain the journal/scholarly routing + English + each mandatory topic BEFORE any fetch. Add a mechanized guard: the gate path must never REDUCE the candidate query/evidence-need count vs the no-gate path (the 997-guard, at planning level).
- Do NOT run live retrieval. Report the exact hooks changed (file:line), flag state, and the telemetry-proof test output.`, { label: 's2:retrieval-projection', phase: 'S2' })

phase('S3')
const s3 = await agent(`${GUARD}
IMPLEMENT S3 — Outline FEED + gap-scope fix (BANKED replay only).
- Refactor src/polaris_graph/outline/outline_agent.py:run_outline_agent_or_legacy into refine_outline_from_seed(seed_outline, contract, retrieval_projection, coverage_matrix, ...) with legacy path: seed = supplied_seed or legacy_call_outline(...). Preserve the legacy adapter (OFF path byte-identical).
- FEED: thread deliverable_spec/scope_spec from the contract; pre-load required_coverage/must_address as PENDING gaps in the gap ledger. Required topics are coverage obligations, NOT automatically headings (do not repeat the round1 coverage-to-heading bug). Explicit headings = exact title+order lock via existing apply_revision_ops(required_titles=...).
- FIX THE BUG (both designers found it): outline_agent.py:_tool_search_more_evidence drops protocol/research_frame -> its gap search runs UNSCOPED. Thread the scope projection + term_ids through OutlineWorkspace into that run_live_retrieval call (it accepts **_ignored today). 
- Extend OutlineWorkspace with contract hash + term ledger; validate update_outline rejects dropping an explicit lock or the last owner of a binding term.
- Tests (BANKED corpora, no live fetch): replay tasks 30/61/76/90 banked evidence through refine_outline_from_seed; assert real refinement happens, locks + term-mappings preserved, and (unit-level) the gap-search call now carries scope. OFF path byte-identical.
Report files, the bug fix location, and replay test results.`, { label: 's3:outline-feed', phase: 'S3' })

phase('S4')
const s4 = await agent(`${GUARD}
IMPLEMENT S4 — Compose/render projections + compliance audit (BANKED/offline only).
- Compose: thread tone/audience/pov (from contract voice) into the section advisory-prose slot in src/polaris_graph/generator/multi_section_generator.py (_call_section / _select_section_system_prompt) — PROSE guidance only, no routing/verification change. document_type selects skeleton. Length = planning context, NEVER a truncation gate.
- Render: in scripts/compose_agentic_report_s3gear329.py:main thread deliverable_spec/scope_spec; contract-aware assembly (required sections/order, references dedup by work, tables from VERIFIED fields only). KEEP _audit_citations untouched. Record retrieval_scope_status='not_evaluated_prebuilt_corpus' when run on a prebuilt corpus.
- Compliance audit: new src/polaris_graph/planning/contract_compliance.py:audit_contract(contract, report, outline, biblio) -> term-level SATISFIED/FAILED/UNSATISFIABLE/UNKNOWN + owning stage. Deterministic for counts/headings/length/tables/citations; a SEPARATE cheap judge only for semantic coverage. DISCLOSURE-ONLY — it must NEVER drop/edit content and NEVER touch strict_verify. Call it AFTER assembly, ALONGSIDE _audit_citations.
- Tests (offline/banked): audit_contract on a saved report produces a term-level report; required-section/order check is deterministic; faithfulness path untouched. OFF path byte-identical.
Report files + test results.`, { label: 's4:compose-render-audit', phase: 'S4' })

phase('S5-harness')
const s5h = await agent(`${GUARD}
IMPLEMENT S5-HARNESS — build (do NOT run) the end-to-end fresh autonomous run + score harness.
- A script scripts/run_gate_e2e.py that, given a DRB task id, runs the FULL fresh pipeline with PG_GATE=1 autonomous (gate -> FS-Researcher fresh retrieval -> outline FEED -> compose -> render -> compliance audit) and writes report.md + planning_gate_artifact.json + contract_compliance.json + telemetry. It should also support scoring via the existing scripts/score_report_race.py and the FACT utils pipeline, and support N draws.
- A DRY SMOKE only: run the harness in a --dry mode that exercises the gate + planning + wiring WITHOUT live retrieval/compose (mock or --plan-only), proving the harness assembles the full pipeline call for tasks {4,30,61,72,76,90}. Do NOT execute a real compose (>10 min / costs money).
- Document at the top of the script the EXACT commands to run the real S5 (fresh e2e + RACE + FACT, 3 draws) so the main session can execute+monitor them.
Report the harness path, the dry-smoke output, and the documented real-run commands.`, { label: 's5:harness', phase: 'S5-harness' })

phase('Verify')
const verdict = await agent(`${GUARD}
FINAL VERIFY (read + run tests only; no new feature edits). On branch gate-s0-s5:
1. Confirm src/polaris_graph/generator/provenance_generator.py is UNMODIFIED (git diff --stat must show it untouched). Confirm nothing under /home/polaris/wt/flywheel changed.
2. Confirm every new behavior is behind a default-OFF flag / None-default kwarg and the diff is additive. Report the diffstat.
3. Run the full new unit-test suite + any fast existing outline/generator/planning tests that could be affected (pytest -q; run fast ones, NOT live-scoring/network suites). Report pass/fail counts.
4. Summarize what S0-S5 built, what passed, the S1 8-prompt smoke result, the S2 telemetry-proof result, the S3 gap-fix, and any TODO/risk. Explicitly state whether faithfulness was left untouched and whether the OFF path is byte-identical.
Return a structured verdict.`, { label: 'verify', phase: 'Verify', schema: {
  type: 'object', additionalProperties: false,
  required: ['faithfulness_untouched','flywheel_untouched','off_path_byte_identical','tests_passed','tests_failed','summary','risks'],
  properties: {
    faithfulness_untouched: { type: 'boolean' },
    flywheel_untouched: { type: 'boolean' },
    off_path_byte_identical: { type: 'boolean' },
    tests_passed: { type: 'integer' },
    tests_failed: { type: 'integer' },
    s1_smoke: { type: 'string' },
    s2_telemetry_proof: { type: 'string' },
    s3_gap_fix: { type: 'string' },
    diffstat: { type: 'string' },
    summary: { type: 'string' },
    risks: { type: 'array', items: { type: 'string' } },
  },
} })

phase('Commit')
const commit = await agent(`${GUARD}
COMMIT (local only — do NOT push; the main session pushes to GitHub).
- In /home/polaris/wt/outline_agent on branch gate-s0-s5: remove any __pycache__, then git add -A and git commit with a clear message describing S0-S5 (Research Planning Gate: contract compiler + retrieval projection + outline FEED + compose/render + compliance audit; faithfulness frozen; all flag-gated OFF by default; expensive live S2/S5 runs deferred). End the message with:
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
- Do NOT push. Report the commit hash and 'git status' clean state.`, { label: 'commit', phase: 'Commit' })

return { branch: 'gate-s0-s5', verdict, commit: (commit||'').slice(0,200) }
