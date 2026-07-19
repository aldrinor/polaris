export const meta = {
  name: 'plan-v4-audit',
  description: 'Codex-gated audit of all committed work against Plan V4: find missed/wrong/skipped items and the correct next step',
  phases: [
    { title: 'Audit', detail: 'one agent per Plan V4 area assesses status vs the actual repo' },
    { title: 'Synthesize', detail: 'consolidate into a status map + the single correct next step' },
    { title: 'Codex-Gate', detail: 'codex adversarially verifies the audit + next-step decision' },
  ],
}

const PLAN = '/home/polaris/wt/phase1/PLAN_V4_REFERENCE.md'
const P0 = '/home/polaris/wt/phase0'   // branch chore/review-readiness-phase0 (PR #1381)
const P1 = '/home/polaris/wt/phase1'   // branch chore/review-readiness-phase1 (PR #1382)

const AREA_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['items', 'area_summary'],
  properties: {
    items: { type: 'array', items: {
      type: 'object', additionalProperties: false,
      required: ['id', 'title', 'status', 'evidence', 'gap'],
      properties: {
        id: { type: 'string' },
        title: { type: 'string' },
        status: { type: 'string', enum: ['DONE', 'PARTIAL', 'MISSING', 'WRONG'] },
        evidence: { type: 'string', description: 'concrete: commit SHAs, file paths, test names, grep counts' },
        gap: { type: 'string', description: 'what is missing/wrong; empty if DONE' },
      } } },
    area_summary: { type: 'string' },
  },
}

const common = `You are auditing a code-review-readiness initiative against its authoritative plan, Plan V4 (read it in full: ${PLAN}).
The ONE inviolable rule of the plan: no change may move the pipeline RACE score or faithfulness behavior; every change must be provably byte-identical/score-safe.
Two git worktrees hold the committed work:
- Phase 0 work: ${P0} (branch chore/review-readiness-phase0, GitHub PR #1381)
- Phase 1 work: ${P1} (branch chore/review-readiness-phase1, GitHub PR #1382)
Be EVIDENCE-BASED: run git log/ls/grep/cat, read tests and docs, and cite concrete SHAs/paths/counts. Do NOT assume something is done because a doc claims it — verify the artifact exists and matches the plan's acceptance wording. Mark PARTIAL when the artifact exists but does not fully meet the plan's stated acceptance. Report ONLY your assigned area.`

phase('Audit')
const areas = [
  { key: '0', label: 'Phase 0 (baseline + zero-risk)', wt: P0, scope:
    `Phase 0 items to assess: 0A-1 secret-safe baseline manifest (baseline/manifest.json with commit SHA, requirements.lock hash, python/OS, model routing, seeds, commands, fixtures; secrets as SHA-256 digest+present flag, NEVER raw); 0A-2 isolated sandbox N-run with per-artifact SHA-256; 0A-3 non-flakiness N>=3 with the GOVERNING RACE/faithfulness measurement statistically characterized (mean+spread+equivalence band) and NEVER quarantined; 0A-4 written comparison protocol (what is regression vs noise); 0A-5 all 3 graph selectors (v1/v2/v3) characterized as replay fixtures; 0B SHA-pin all 28 CI actions, fix third-party attribution, add pyproject.toml + CI in REPORT-ONLY mode, tidy README/architecture. Also note the deterministic oracle work (tests/oracle/cassette.py, llm_cassette.py) and where it maps to 0A.` },
  { key: '1', label: 'Phase 1 (central settings)', wt: P1, scope:
    `Phase 1 items: 1A govern+classify ALL ~923 keys (supported/internal/secret/deprecated/experimental) each with owner+precedence, gate=100% classified+owned; 1B FULL-BEHAVIOR characterization tests for every key across {unset,empty,valid,malformed} x {default/.env/process-env/CLI precedence} x {key-case} x {read-timing lazy vs import-snapshot} x {runtime type str/coerced/SecretStr}; 1C migrate one module at a time, each default=exact current value, env names preserved, SecretStr for secrets with call-sites unwrapped, acceptance harness after each module. CRITICAL: verify what was ACTUALLY done — settings.py, config_defaults.py, the 832-site AST migration (commit dd96ceb), characterization tests test_settings_models.py + test_config_registry.py. Assess: does 1B's matrix actually cover precedence/case/timing/malformed/SecretStr, or only byte-identical default resolution? Did 1C follow 'one module at a time' or a bulk codemod, and is that deviation safe? Are secrets migrated to SecretStr yet? Check git log on the branch.` },
  { key: '2', label: 'Phase 2 (compat gate + renames + checkpoint)', wt: P1, scope:
    `Phase 2 items: 2A public-compatibility inventory (dynamic imports importlib/__import__/getattr, string refs, saved-state refs, external consumers) BEFORE any rename/delete; 2B execute NAME_RENAME_WORKLIST_validated.tsv (210 renames by risk class: 105 SAFE symbol, 12 TEXT-ONLY, 45 FILE-RENAME, 32 NEEDS-ALIAS keep old string via alias, 16 DOMAIN-REVIEW to owner, 135 KEEP documented); 2C turn on generation checkpoint (pre-check data only, write gated behind flag, byte-identical normal runs). Assess whether ANY of this has started; verify the worklist file exists and its row counts; note graph_v2/v3 are deferred to Phase 3.` },
  { key: '3', label: 'Phase 3 (docs + required CI + graph fork)', wt: P1, scope:
    `Phase 3 items: 3A fill ~530 docstrings (contract/API first) + ADRs; 3B flakiness policy BEFORE CI becomes required (N runs over days, quarantine flaky NON-governing tests, define bar, flip report-only->required, add dep hash-pinning + license/secret scanning); 3C the graph.py/graph_v2/graph_v3 fork removal fully gated (per-selector compatibility matrix on 0A-5 fixtures, usage inventory of PG_GRAPH_VERSION, ResearchStateV2 saved-state migration fixtures, repeated replays, rollback+deprecation). Assess whether started.` },
  { key: 'S', label: 'Scheduled deliverables S1-S6', wt: P1, scope:
    `The six reviewer-axis deliverables: S1 config governance (classify+own 923 keys, precedence); S2 public-compat inventory + supported-Python/install/state-migration/rollback doc; S3 test quality/flakiness policy; S4 security/privacy review (threat model: API auth, crawler SSRF, prompt-injection, PII, log redaction, checkpoint retention); S5 operational readiness (timeouts, retries, rate/cost limits, monitoring, runbooks, recovery); S6 reproducible build (two builds hash-match, hash-pinned deps, locked env, SBOM). For each: DONE/PARTIAL/MISSING with evidence.` },
]

const areaResults = await parallel(areas.map(a => () =>
  agent(`${common}\n\nYOUR AREA: ${a.label}. Start by: cd ${a.wt} && git log --oneline -25 and ls the tree.\n${a.scope}\n\nReturn every plan item in your area with a status and concrete evidence.`,
    { label: `audit:P${a.key}`, phase: 'Audit', schema: AREA_SCHEMA })
      .then(r => ({ area: a.label, ...r }))
))
const audits = areaResults.filter(Boolean)

phase('Synthesize')
const SYNTH_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['status_map_markdown', 'next_step', 'missed_or_wrong', 'planv4_deviations', 'phase0_blocking'],
  properties: {
    status_map_markdown: { type: 'string', description: 'a markdown table: item | status | evidence | gap' },
    next_step: { type: 'object', additionalProperties: false, required: ['id', 'what', 'why_next', 'execution_outline'],
      properties: { id: {type:'string'}, what: {type:'string'}, why_next: {type:'string'}, execution_outline: {type:'string'} } },
    missed_or_wrong: { type: 'array', items: { type: 'string' } },
    planv4_deviations: { type: 'array', items: { type: 'string' }, description: 'where actual work deviated from Plan V4 wording, and whether the deviation is safe' },
    phase0_blocking: { type: 'string', description: 'per Plan V4 safety rule 1 (baseline first): is any Phase 0 baseline artifact missing such that later phases are running on an un-pinned oracle? state clearly' },
  },
}
const synthesis = await agent(
  `${common}\n\nYou are the SYNTHESIS reviewer. Here are the per-area audit results as JSON:\n${JSON.stringify(audits)}\n\nProduce: (1) a consolidated status_map markdown table across ALL Plan V4 items; (2) the SINGLE correct next step per Plan V4's ordering and safety rules (Phase 0 gaps block everything; then Phase 1; etc.) with a concrete execution_outline; (3) missed_or_wrong: anything the executor skipped, did wrong, or left idle; (4) planv4_deviations: where the actual work diverged from Plan V4's literal wording (e.g. bulk codemod vs 'one module at a time', or 1B matrix coverage) and whether each divergence is score-safe; (5) phase0_blocking: whether later work is standing on an un-pinned baseline. Be rigorous and specific.`,
  { label: 'synthesize', phase: 'Synthesize', schema: SYNTH_SCHEMA })

phase('Codex-Gate')
const gate = await agent(
  `You are running CODEX (GPT-5.6), the plan's independent adversarial reviewer, to gate an audit of a code-review-readiness initiative against Plan V4.
Steps:
1. Read the plan: cat ${PLAN}
2. Write this audit synthesis to /tmp/planv4_synth.json:
${JSON.stringify(synthesis)}
3. Compose a terse prompt file /tmp/codex_planv4.md that gives codex: the plan's phases/safety-rules (summarize from the plan), the synthesis JSON, and asks: "Is this audit's status assessment ACCURATE and is its chosen next_step CORRECT per Plan V4's ordering and safety rules? Attack it: name any item wrongly marked DONE, any missed gap, any Phase-0 baseline hole that makes later work unsafe, or a better next step. Then give a final verdict line: AUDIT-CONFIRMED or AUDIT-REVISE."
4. Run: cd /tmp && timeout 300 codex exec --skip-git-repo-check - < /tmp/codex_planv4.md 2>&1 | tail -40
   (codex may warn about bubblewrap; that is fine, it still runs. Do NOT pass sandbox flags.)
5. Return codex's verdict and its key points verbatim.`,
  { label: 'codex-gate', phase: 'Codex-Gate', schema: {
    type: 'object', additionalProperties: false,
    required: ['verdict', 'codex_points', 'confirmed_next_step'],
    properties: {
      verdict: { type: 'string', enum: ['AUDIT-CONFIRMED', 'AUDIT-REVISE'] },
      codex_points: { type: 'array', items: { type: 'string' } },
      confirmed_next_step: { type: 'string' },
    } } })

return { synthesis, gate }
