export const meta = {
  name: 'fix-2A-enumeration',
  description: 'Close codex 2A REVISE: exact per-row disposition table of all 210 rename rows summing cleanly to 210',
  phases: [
    { title: 'Enumerate', detail: 'exact one-row/one-class table for all 210 RENAME rows' },
    { title: 'Codex-Gate', detail: 'codex confirms 2A now OK' },
    { title: 'Record', detail: 'commit + push (updates PR #1383)' },
  ],
}
const WT = '/home/polaris/wt/deliverables'
const DOC = `${WT}/docs/review_readiness/public_compat_inventory.md`
const WORKLIST = '/home/polaris/polaris_project/NAME_RENAME_WORKLIST_validated.tsv'

phase('Enumerate')
const enu = await agent(
  `Close a narrow completeness defect in ${DOC} (Plan V4 2A). Codex accepted all the ANALYSIS but rejected §6.5 because its disposition is GROUPED with tilde-approximated counts that sum to ~199, not an EXACT per-row disposition of all 210 RENAME rows.
Do exactly this, no more:
1. Read the FULL worklist ${WORKLIST}. Filter to the RENAME rows (SAFETY column indicates the risk class; per the existing doc the 210 RENAME rows break down as 105 SAFE + 12 TEXT-ONLY + 45 FILE-RENAME + 32 NEEDS-ALIAS + 16 DOMAIN-REVIEW = 210).
2. Replace §6.5's grouped/approximate content with an EXACT per-row table: one row per rename with columns [# | old_name | new_name | location | class | 1-line reason], where class is one of {SAFE-static, TEXT-ONLY, FILE-RENAME, NEEDS-ALIAS, DYNAMIC-HAZARD, DOMAIN-REVIEW}. Preserve the analytical corrections already made (ResearchStateV2/HonestSweepJobRunner/V3State/V30SweepResult and is_row_content_junk/content_integrity_junk are NEEDS-ALIAS/DYNAMIC-HAZARD, NOT SAFE).
3. End with a roll-up table of EXACT integer counts per class that sums to PRECISELY 210 (no '~'). Show the arithmetic (e.g. 100+12+45+... = 210).
4. If the worklist has fewer/more than 210 RENAME rows, state the exact number found and reconcile to it explicitly rather than asserting 210.
Do NOT rewrite other sections. Return the exact class counts and confirm they sum to the stated total.`,
  { label: '2A-enumerate', phase: 'Enumerate', schema: { type:'object', additionalProperties:false, required:['total_rename_rows','class_counts','sums_cleanly'], properties:{ total_rename_rows:{type:'integer'}, class_counts:{type:'string'}, sums_cleanly:{type:'boolean'} } } })

phase('Codex-Gate')
const gate = await agent(
  `Run CODEX (GPT-5.6) to confirm the 2A doc's enumeration defect is fixed. Write /tmp/twoA_gate.md then run 'cd /tmp && timeout 240 codex exec --skip-git-repo-check - < /tmp/twoA_gate.md 2>&1 | tail -30' (bubblewrap warning fine; no sandbox flags).
Context: codex previously REVISE'd 2A ONLY because §6.5 lacked an exact per-row disposition of all 210 RENAME rows and its roll-up summed to ~199 via tilde-approximations. The analysis was otherwise accepted (S4/S5 already OK). The reviser now reports: ${JSON.stringify(enu)}.
Have codex 'cat ${DOC}' (or at least the §6.5 region) and verify: is there now an exact per-row table for every RENAME row, with integer class counts that sum precisely to the stated total? End with exactly: 2A: OK or 2A: REVISE (and if REVISE, the one remaining item).
Return codex's verdict + key points.`,
  { label: 'codex-gate', phase: 'Codex-Gate', schema: { type:'object', additionalProperties:false, required:['verdict','codex_points'], properties:{ verdict:{type:'string'}, codex_points:{type:'array',items:{type:'string'}} } } })

phase('Record')
const rec = await agent(
  `Record the 2A enumeration fix. Worktree ${WT} (branch chore/review-readiness-deliverables).
1. git add docs/review_readiness/public_compat_inventory.md (grep-check no plaintext secret).
2. Commit: "2A: exact per-row disposition of all 210 rename rows (codex enumeration fix)" with trailers:
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TLpJSqNfJVSP1UGdtk89nA
3. Push (updates PR #1383): 'cd ${WT} && git push'.
Return {commit_sha, pushed}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false, required:['commit_sha','pushed'], properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'} } } })

return { enu, gate, record: rec }
