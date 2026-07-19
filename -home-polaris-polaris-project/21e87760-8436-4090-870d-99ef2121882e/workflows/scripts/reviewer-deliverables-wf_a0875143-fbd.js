export const meta = {
  name: 'reviewer-deliverables',
  description: 'Un-gated Plan V4 reviewer deliverables in parallel: 2A public-compat inventory + S4 security threat model + S5 operational readiness',
  phases: [
    { title: 'Analyze', detail: '3 parallel analysis agents produce reviewer docs from the real code' },
    { title: 'Codex-Gate', detail: 'codex checks each doc for completeness + accuracy' },
    { title: 'Record', detail: 'commit + push + open PR on the deliverables branch' },
  ],
}

const WT = '/home/polaris/wt/deliverables'   // branch chore/review-readiness-deliverables (full code, from phase1)
const DOCS = `${WT}/docs/review_readiness`

const DOC_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['path', 'summary', 'key_findings', 'gaps_or_risks'],
  properties: {
    path: { type: 'string' },
    summary: { type: 'string' },
    key_findings: { type: 'array', items: { type: 'string' } },
    gaps_or_risks: { type: 'array', items: { type: 'string' }, description: 'concrete risks/holes the reviewer would flag' },
  },
}

const common = `You are producing a reviewer-facing deliverable for a code-review-readiness initiative on a Python deep-research pipeline (repo root ${WT}, package src/polaris_graph). The audience is an independent Telus code reviewer. Be EVIDENCE-BASED: cite concrete files, functions, and line numbers you actually read/grepped; do not speculate. Write a clear, well-structured markdown doc. This is analysis + a NEW doc file only — do NOT modify any runtime code.`

phase('Analyze')
const docs = await parallel([
  () => agent(
    `${common}\nDELIVERABLE: Plan V4 item 2A — PUBLIC-COMPATIBILITY INVENTORY, which must run BEFORE any rename/delete. Write ${DOCS}/public_compat_inventory.md.
Inventory everything that could break if a symbol/file/string is renamed:
1. DYNAMIC IMPORTS: grep src/ for importlib, __import__, getattr(<module>, ...), pkgutil, entry_points, plugin registries. List each with file:line and what it dynamically resolves.
2. STRING-BASED REFERENCES: module/class/function names referenced as strings (e.g. in config, dispatch tables, "cls": "Name" serialization).
3. SAVED-STATE REFERENCES: pickled/JSON-serialized class names (e.g. ResearchState / ResearchStateV2), checkpoint schemas, any persisted field/enum literal that a rename would orphan.
4. ENV-VAR / ENUM / PERSISTED STRING literals that are control-surface (these need ALIASes, never naive rename).
5. EXTERNAL CONSUMERS: CLI entry points, API routes, anything a caller outside the repo depends on.
Then cross-reference against the rename worklist if present (find NAME_RENAME_WORKLIST_validated.tsv) and flag which proposed renames touch anything dynamic. Conclusion: which categories of names are SAFE to rename vs which REQUIRE an alias. State clearly that 'zero static importers' is NOT sufficient.`,
    { label: '2A-compat', phase: 'Analyze', schema: DOC_SCHEMA }),
  () => agent(
    `${common}\nDELIVERABLE: Plan V4 item S4 — SECURITY / PRIVACY THREAT MODEL. Write ${DOCS}/threat_model.md.
Analyze the ACTUAL code for each axis and document threat + current mitigation + residual risk:
1. API AUTH: find the API layer (grep for FastAPI/Flask routes, POLARIS_AUTH_SECRET, POLARIS_JWT_SECRET, auth middleware). How are endpoints authenticated? Any unauthenticated routes?
2. CRAWLER SSRF: the pipeline fetches web content (run_live_retrieval, web fetch, Playwright). Is fetched-URL input validated against internal/metadata addresses (169.254.169.254, localhost, private ranges)? Find the fetch code and assess SSRF exposure.
3. PROMPT INJECTION: retrieved web/document content is fed into LLM prompts. What controls exist (delimiters, instruction/hierarchy, output validation)? 
4. PII: is user/query/document PII stored, logged, or sent to providers? Any redaction?
5. LOG REDACTION: grep for logging of secrets/keys/tokens; are API keys ever logged? Check how os.getenv secrets are handled in logs.
6. CHECKPOINT RETENTION: the generation checkpoint stores drafts — retention/cleanup policy? Sensitive data at rest?
Give a findings table with severity (critical/high/med/low). Flag any UNRESOLVED CRITICAL clearly.`,
    { label: 'S4-security', phase: 'Analyze', schema: DOC_SCHEMA }),
  () => agent(
    `${common}\nDELIVERABLE: Plan V4 item S5 — OPERATIONAL READINESS checklist. Write ${DOCS}/operational_readiness.md.
Inventory from the ACTUAL code, with file:line evidence, and mark each Present / Partial / Missing:
1. TIMEOUTS: per-provider and per-stage timeouts (grep timeout=, PG_*_TIMEOUT). Are all external calls bounded?
2. RETRIES: retry/backoff logic on provider + fetch calls (grep retry, backoff, tenacity).
3. RATE / COST LIMITS: rate limiting, concurrency caps, token/cost accounting (grep PG_*_CONCURRENCY, rate, cost, token_accounting).
4. MONITORING / OBSERVABILITY: logging, metrics, tracing, health checks.
5. RUNBOOKS: any operational docs/runbooks for failure recovery.
6. RECOVERY: checkpoint/resume, idempotency, graceful degradation on provider failure.
Produce a readiness checklist table + a prioritized list of the top operational gaps a reviewer would flag before external exposure.`,
    { label: 'S5-ops', phase: 'Analyze', schema: DOC_SCHEMA }),
])
const valid = docs.filter(Boolean)

phase('Codex-Gate')
const gate = await agent(
  `Run CODEX (GPT-5.6) to gate three reviewer deliverables for completeness + accuracy. Write /tmp/deliv_gate.md then run 'cd /tmp && timeout 300 codex exec --skip-git-repo-check - < /tmp/deliv_gate.md 2>&1 | tail -45' (bubblewrap warning fine; no sandbox flags).
Give codex the three docs' summaries + findings + gaps:
${JSON.stringify(valid)}
Ask codex: "These are Plan V4 deliverables 2A (public-compat inventory), S4 (security threat model), S5 (operational readiness) for a deep-research pipeline. For EACH: is it complete enough to hand an independent reviewer, or does it have a material gap/inaccuracy? Name the single most important thing each is missing. Flag any security finding that is understated. End with one line per doc: 2A: OK|REVISE, S4: OK|REVISE, S5: OK|REVISE."
Return codex's per-doc verdicts + its key points.`,
  { label: 'codex-gate', phase: 'Codex-Gate', schema: { type:'object', additionalProperties:false, required:['verdicts','codex_points'], properties:{ verdicts:{type:'string'}, codex_points:{type:'array',items:{type:'string'}} } } })

phase('Record')
const rec = await agent(
  `Record the reviewer deliverables to the branch. Worktree ${WT} (branch chore/review-readiness-deliverables).
1. git add docs/review_readiness/public_compat_inventory.md docs/review_readiness/threat_model.md docs/review_readiness/operational_readiness.md (whichever exist). Grep-check NO plaintext secret in any staged file.
2. Commit (message: "Plan V4 reviewer deliverables: 2A public-compat inventory + S4 threat model + S5 operational readiness") ending with:
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TLpJSqNfJVSP1UGdtk89nA
3. Push: 'cd ${WT} && git push -u origin chore/review-readiness-deliverables'.
4. Open a PR to main via gh: '/home/polaris/.local/bin/gh pr create --repo aldrinor/deep-cove-research --base main --head chore/review-readiness-deliverables --title "Code-review readiness: reviewer deliverables (2A/S4/S5)" --body "Plan V4 un-gated reviewer deliverables: public-compatibility inventory (2A), security/privacy threat model (S4), operational readiness (S5). Analysis-only, no runtime changes.\\n\\n🤖 Generated with [Claude Code](https://claude.com/claude-code)"'. If gh fails, report the error but still confirm the push.
Return {commit_sha, pushed, pr_url}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false, required:['commit_sha','pushed','pr_url'], properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'}, pr_url:{type:'string'} } } })

return { docs: valid, gate, record: rec }
