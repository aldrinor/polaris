export const meta = {
  name: 's1-config-ownership',
  description: 'S1/1A gate: assign owner-role + precedence to every classified config key (by domain category), completing config governance — doc/metadata only, no runtime change',
  phases: [
    { title: 'Assign', detail: 'map each classified key to an owner-role + precedence by category' },
    { title: 'Codex-Gate', detail: 'codex checks 100% classified+owned+precedence, no runtime change' },
    { title: 'Record', detail: 'commit + push + PR' },
  ],
}
const PY = '/home/polaris/pipeline-env/bin/python'
const WT = '/home/polaris/wt/phase-s1'

phase('Assign')
const assign = await agent(
  `Complete Plan V4 1A / deliverable S1 (config governance: 100% classified + OWNED + precedence). The keys are already CLASSIFIED (6 categories) but 0/1044 have an owner or precedence — close that gap. This is DOC/METADATA only, NO runtime code change.
1. cd /workspace/POLARIS && git worktree remove ${WT} --force 2>/dev/null; git branch -D chore/review-readiness-s1 2>/dev/null; git worktree add ${WT} -b chore/review-readiness-s1 chore/review-readiness-phase1.
2. Find the classification data (docs/review_readiness/config_governance.md + any config_keys_classified.json, and src/polaris_graph/config_defaults.py has the 871-key registry + MODEL_KEY_DEFAULTS). Enumerate the keys and their categories (supported/internal/secret/deprecated/experimental, and by DOMAIN prefix: PG_*, OPENROUTER_*, model keys, retrieval keys, generation keys, secret-shaped keys, etc.).
3. Assign an OWNER-ROLE to each key/category using the roles Plan V4 already defines (Approver = project owner; Executor = engineering). Concretely: model-selection + secret + faithfulness/verification keys → OWNER (project owner) accountable; retrieval/generation/internal tuning keys → EXECUTOR (engineering) with owner sign-off. Assign by CATEGORY/DOMAIN (not 1044 individual hand-entries) — a table mapping category → owner-role → precedence.
4. Document PRECEDENCE for each: the resolution order (process-env > .env > registry default; ModelSettings validation_alias for the 12 model keys; case-sensitive). This is already characterized in 1B — reference it.
5. Produce docs/review_readiness/config_ownership.md: a table of {category, example keys, count, owner-role, precedence, notes}, covering ALL categories so every key has an owner+precedence via its category. State the gate is met: 100% classified + owned (by category) + precedence documented.
Return: categories_covered, total_keys_covered, gate_met (bool), notes. Confirm no runtime/src change.`,
  { label: 'assign', phase: 'Assign', schema: { type:'object', additionalProperties:false, required:['categories_covered','total_keys_covered','gate_met','no_runtime_change','notes'], properties:{ categories_covered:{type:'integer'}, total_keys_covered:{type:'integer'}, gate_met:{type:'boolean'}, no_runtime_change:{type:'boolean'}, notes:{type:'string'} } } })

phase('Codex-Gate')
const gate = await agent(
  `Run CODEX (GPT-5.6) to gate S1/1A config-governance ownership. Write /tmp/s1_gate.md then 'cd /tmp && timeout 180 codex exec --skip-git-repo-check - < /tmp/s1_gate.md 2>&1 | tail -20' (embed inline; medium; no sandbox flags).
Plan V4 1A/S1 gate: 100% of config keys classified + OWNED + precedence documented. Evidence: ${JSON.stringify(assign)}.
Ask codex: "Does this ownership+precedence assignment (by category, using the plan's owner/executor roles) cover EVERY config key so the 1A/S1 gate 'classified + owned + precedence' is met, with no runtime code changed? Is category-level ownership acceptable (vs per-key), and is precedence correctly documented (process-env > .env > registry; case-sensitive; model-key validation_alias)? End with S1-OK or S1-REVISE."
Return verdict + points.`,
  { label: 'codex-gate', phase: 'Codex-Gate', schema: { type:'object', additionalProperties:false, required:['verdict','codex_points'], properties:{ verdict:{type:'string'}, codex_points:{type:'array',items:{type:'string'}} } } })

phase('Record')
const rec = await agent(
  `Record S1 in ${WT} (branch chore/review-readiness-s1). Commit if codex=S1-OK (${gate.verdict}) and no_runtime_change. Confirm collection unchanged: '${PY} -m pytest tests/ --collect-only -q | tail -1' (16738/11). Stage explicit: 'git add docs/review_readiness/config_ownership.md' (+ any updated config_governance.md); GUARD 'git diff --cached --name-only | grep -c tests/oracle' == 0; ensure NO src/ staged. Commit ("Phase 1A/S1: config governance ownership + precedence (100% classified+owned by category)") with standard trailers. Push -u origin; PR base gate-inversion.
Return {commit_sha, pushed, pr_url, committed_or_blocked}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false, required:['commit_sha','pushed','pr_url','committed_or_blocked'], properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'}, pr_url:{type:'string'}, committed_or_blocked:{type:'string'} } } })

return { assign, gate, record: rec }
