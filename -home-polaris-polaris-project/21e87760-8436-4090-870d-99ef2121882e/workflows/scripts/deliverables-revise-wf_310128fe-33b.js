export const meta = {
  name: 'deliverables-revise',
  description: 'Address codex REVISE on the 3 reviewer deliverables (2A/S4/S5), re-gate, update PR #1383',
  phases: [
    { title: 'Revise', detail: '3 parallel revisers close each doc\'s codex-flagged scope hole' },
    { title: 'Codex-Gate', detail: 'codex re-checks each revised doc' },
    { title: 'Record', detail: 'commit + push to deliverables branch (updates PR #1383)' },
  ],
}

const WT = '/home/polaris/wt/deliverables'
const DOCS = `${WT}/docs/review_readiness`
const WORKLIST = '/home/polaris/polaris_project/NAME_RENAME_WORKLIST_validated.tsv'

const DOC_SCHEMA = { type:'object', additionalProperties:false, required:['path','revisions_made','residual_gaps'],
  properties:{ path:{type:'string'}, revisions_made:{type:'array',items:{type:'string'}}, residual_gaps:{type:'array',items:{type:'string'}} } }

const common = `You are revising an existing reviewer-facing deliverable to close a specific gap an adversarial reviewer (codex) flagged. Repo root ${WT}, package src/polaris_graph. Be EVIDENCE-BASED with file:line citations. EDIT the existing markdown file in place (keep the good parts, fix/extend the flagged parts). Do NOT modify runtime code.`

phase('Revise')
const revised = await parallel([
  () => agent(
    `${common}\nDOC: ${DOCS}/public_compat_inventory.md (Plan V4 2A). CODEX SAID REVISE. Close these:
1. PRIMARY: Provide a ROW-BY-ROW disposition of the AUTHORITATIVE worklist at ${WORKLIST}. Read the ENTIRE file (it has ~210 RENAME rows + KEEP rows). For EVERY rename row, classify its public-compat risk as one of {SAFE-static, NEEDS-ALIAS (env/enum/persisted string), FILE-RENAME-fix-importers, DYNAMIC-HAZARD (string dispatch/saved-state)} with a one-line reason + the location. Present as a table or grouped lists covering ALL rows — not a sample. If a row's LOCATION line number has drifted vs the current worktree, re-verify and note it.
2. Fix the ResearchStateV2 claim: 'checkpoint-serialization-safe' does NOT imply 'public import-name safe.' Add evidence about whether ResearchStateV2 (and other renamed public classes) are exported/imported by external consumers or the API; if you cannot prove no external importer, recommend a compatibility alias rather than declaring SAFE.
Return the revisions made and any residual gaps.`,
    { label: '2A-revise', phase: 'Revise', schema: DOC_SCHEMA }),
  () => agent(
    `${common}\nDOC: ${DOCS}/threat_model.md (Plan V4 S4). CODEX SAID REVISE. Close these:
1. PRIMARY: Add an END-TO-END REACHABILITY / TRUST-BOUNDARY analysis for the SSRF finding. Trace: which inputs (authenticated API params, unauthenticated routes, LLM-harvested URLs) actually REACH each fetcher (live_retriever.py fetchers, domain_backends.py, access_bypass.py, utils/ingest.py)? Does the served polaris_v6 API expose any path that reaches a fetcher? Assess redirect-following AND DNS-rebinding (a private-IP filter alone does not stop DNS-rebinding — note this explicitly). Can internal responses be observed by the caller (exfiltration)? Does the runtime have network access to internal/metadata addresses?
2. Re-rate SSRF conditionally: Critical IF reachable from an exposed API with internal/metadata access; otherwise High pending deployment validation. State the condition explicitly.
3. Rate the POLARIS_AUTH_DISABLED=1 kill switch at least HIGH if production startup permits it, and SOFTEN the 'production auth sound / fail-loud' characterization accordingly (it is overstated while that switch exists).
4. Expand the PII finding: verbatim PII egress to third-party providers needs provider-data-retention + consent/compliance treatment, not just 'no redaction.'
Update the severity table accordingly. Return revisions + residual gaps.`,
    { label: 'S4-revise', phase: 'Revise', schema: DOC_SCHEMA }),
  () => agent(
    `${common}\nDOC: ${DOCS}/operational_readiness.md (Plan V4 S5). CODEX SAID REVISE. Close these:
1. PRIMARY: Add an END-TO-END operational assessment of the SERVING layer src/polaris_v6 and its deployment boundary. Inspect and document (Present/Partial/Missing + file:line): request admission control, server-level timeouts (uvicorn/gunicorn/FastAPI), backpressure/concurrency limits at the server, graceful shutdown, dependency/readiness checks, SLOs/alerting, and multi-worker behavior (shared state, checkpoint DB contention).
2. Fix the consistency issue: change 'TIMEOUTS = Present' to 'Partial' (grep-based sampling did not exhaustively prove all multiline/dynamic client calls are bounded) and say why.
Keep the existing pipeline-level checklist; ADD the serving-layer section. Return revisions + residual gaps.`,
    { label: 'S5-revise', phase: 'Revise', schema: DOC_SCHEMA }),
])
const valid = revised.filter(Boolean)

phase('Codex-Gate')
const gate = await agent(
  `Run CODEX (GPT-5.6) to RE-GATE three revised reviewer docs. Write /tmp/deliv_regate.md then run 'cd /tmp && timeout 300 codex exec --skip-git-repo-check - < /tmp/deliv_regate.md 2>&1 | tail -45' (bubblewrap warning fine; no sandbox flags).
Prior codex verdict was REVISE on all three for: 2A (needed full 210-row worklist disposition + import-surface fix), S4 (needed trust-boundary/reachability model + conditional SSRF severity + kill-switch rating + PII compliance), S5 (needed polaris_v6 serving-layer assessment + TIMEOUTS->Partial).
Here is what the revisers changed:
${JSON.stringify(valid)}
Also cat the three files so codex can see them: 'cat ${DOCS}/public_compat_inventory.md ${DOCS}/threat_model.md ${DOCS}/operational_readiness.md | head -400' — include enough in your prompt.
Ask codex: "Are the prior REVISE gaps now closed for each doc? End with one line per doc: 2A: OK|REVISE, S4: OK|REVISE, S5: OK|REVISE, and for any remaining REVISE name the one blocking item."
Return codex's per-doc verdicts + key points.`,
  { label: 'codex-regate', phase: 'Codex-Gate', schema: { type:'object', additionalProperties:false, required:['verdicts','codex_points'], properties:{ verdicts:{type:'string'}, codex_points:{type:'array',items:{type:'string'}} } } })

phase('Record')
const rec = await agent(
  `Record the revised deliverables. Worktree ${WT} (branch chore/review-readiness-deliverables).
1. git add docs/review_readiness/public_compat_inventory.md docs/review_readiness/threat_model.md docs/review_readiness/operational_readiness.md. Grep-check NO plaintext secret in staged files.
2. Commit (message: "Revise reviewer deliverables per codex: full 210-row 2A disposition, S4 trust-boundary + conditional SSRF, S5 serving-layer assessment") with the standard trailers:
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TLpJSqNfJVSP1UGdtk89nA
3. Push (updates PR #1383): 'cd ${WT} && git push'.
Return {commit_sha, pushed}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false, required:['commit_sha','pushed'], properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'} } } })

return { revised: valid, gate, record: rec }
