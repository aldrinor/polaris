export const meta = {
  name: 'retro-validate-phase1',
  description: 'Retro-validate the 832-site Phase 1 config migration against the pinned oracle: replay the cassette on the migrated code, confirm golden SHA 9c0a3d43',
  phases: [
    { title: 'Replay', detail: 'overlay pinned oracle onto Phase 1 code, run --replay, capture artifact SHA' },
    { title: 'Codex-Gate', detail: 'codex judges whether the result validates the migration byte-identical' },
    { title: 'Record', detail: 'write retro-validation evidence + set band=0, commit to phase0 branch' },
  ],
}

const PY = '/home/polaris/pipeline-env/bin/python'
const GOLDEN = '9c0a3d438da943242c98e2fe714494c342d42d02102202d75a61a4554339db98'
const SCRATCH = '/home/polaris/wt/retrovalidate'

phase('Replay')
const replay = await agent(
  `Retro-validate a config migration against a pinned deterministic oracle. GOAL: prove (or disprove) that the Phase 1 832-site os.getenv->resolve() migration (commit dd96ceb on branch chore/review-readiness-phase1) is byte-identical on the oracle's covered path.
Setup an INTEGRATION scratch worktree combining the migrated code + the pinned oracle:
1. cd /workspace/POLARIS && git worktree remove ${SCRATCH} --force 2>/dev/null; git worktree add ${SCRATCH} -b retro-validate-scratch chore/review-readiness-phase1   (this gives the Phase 1 migrated src/).
2. Overlay the pinned oracle tooling + cassettes FROM the phase0 branch/worktree:
   cd ${SCRATCH} && git checkout chore/review-readiness-phase0 -- tests/oracle/
   Then ensure the cassette + golden files are present (they may be git-ignored): copy them from the phase0 worktree filesystem if missing:
   cp -n /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_llm.jsonl /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_retrieval.jsonl /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_golden.json ${SCRATCH}/tests/oracle/cassettes/ 2>/dev/null
   Verify all three cassette/golden files exist in ${SCRATCH}/tests/oracle/cassettes/.
3. Confirm the migrated code is present: 'cd ${SCRATCH} && git log --oneline -1' should be at/after dd96ceb, and 'grep -rl "from src.polaris_graph.settings import resolve" src/polaris_graph | head' should show migrated modules.
4. Run the oracle in REPLAY mode against the migrated code (frozen LLM + frozen retrieval, no network):
   cd ${SCRATCH} && PG_OUTLINE_AGENT_MAX_TURNS=3 ${PY} tests/oracle/acceptance_portable.py --replay 2>&1 | tail -40
5. Capture the resulting golden/artifact SHA-256 the harness computes and compare to the pinned golden ${GOLDEN}.
   - If the harness prints its own SHA + PASS, use that. Otherwise sha256sum the canonical artifact it writes.
6. Report: did replay run to completion with NO cassette MISS? Does the artifact SHA EQUAL ${GOLDEN}? Do both controls pass? If there is a MISS or SHA mismatch, capture the EXACT divergence (which call/field differed) — that would be a real behavior change from the migration.
Be honest: a mismatch is a genuine finding (migration moved behavior on the covered path), not something to hide.`,
  { label: 'replay', phase: 'Replay', schema: { type:'object', additionalProperties:false,
    required:['replay_completed','artifact_sha','sha_matches_golden','positive_control_pass','negative_control_pass','divergence_detail'],
    properties:{ replay_completed:{type:'boolean'}, artifact_sha:{type:'string'}, sha_matches_golden:{type:'boolean'}, positive_control_pass:{type:'boolean'}, negative_control_pass:{type:'boolean'}, divergence_detail:{type:'string'} } } })

phase('Codex-Gate')
const gate = await agent(
  `Run CODEX (GPT-5.6) to gate a retro-validation result. Write /tmp/retro_gate.md then run 'cd /tmp && timeout 240 codex exec --skip-git-repo-check - < /tmp/retro_gate.md 2>&1 | tail -30' (bubblewrap warning fine; if codex cannot read files, embed everything inline; no sandbox flags; use medium effort).
Context: A deterministic oracle (golden SHA ${GOLDEN}, byte-identical across seed+3 replays, controls pass) governs the THIN+SATURATED outline-agent paths. We replayed it against the Phase 1 code which contains an 832-site os.getenv->resolve() migration (dd96ceb). Result: ${JSON.stringify(replay)}.
Ask codex: "Given the replay result, is the 832-site migration proven byte-identical on the oracle's covered path? If the artifact SHA equals the golden and both controls pass with no cassette MISS, that is empirical proof the migration did not change behavior on the covered THIN+SATURATED paths. State clearly what this DOES and DOES NOT prove (coverage caveat: only the exercised outline-agent path + config keys it reads, not the ~830 sites on unexercised paths). End with: MIGRATION-VALIDATED-ON-COVERED-PATH or MIGRATION-DIVERGENCE-FOUND."
Return codex's verdict + points.`,
  { label: 'codex-gate', phase: 'Codex-Gate', schema: { type:'object', additionalProperties:false, required:['verdict','codex_points'], properties:{ verdict:{type:'string'}, codex_points:{type:'array',items:{type:'string'}} } } })

phase('Record')
const rec = await agent(
  `Record the retro-validation evidence to the phase0 branch (where the oracle + comparison protocol live). Worktree /home/polaris/wt/phase0 (branch chore/review-readiness-phase0).
1. Write /home/polaris/wt/phase0/docs/review_readiness/retro_validation_phase1.md: state that the pinned oracle (golden SHA ${GOLDEN}) was replayed against the Phase 1 migrated code (dd96ceb, 832 sites). Record the replay result: ${JSON.stringify(replay)}. Record codex's verdict: ${JSON.stringify(gate.verdict)}. Be explicit about coverage (THIN+SATURATED outline paths only). If SHA matched -> the migration is byte-identical on the covered path (the empirical proof Plan V4 safety-rule-1 demanded). If not -> document the divergence as a finding.
2. Update /home/polaris/wt/phase0/docs/review_readiness/comparison_protocol.md: replace the equivalence-band TODO with: "Equivalence band = 0 (byte-exact): the oracle is a deterministic cassette replay; 'same' means the canonical artifact SHA-256 equals the golden ${GOLDEN} exactly, and both controls (THIN positive, SATURATED negative) pass. Any SHA mismatch or cassette MISS is a regression."
3. Also verify the oracle commit is pushed: 'cd /home/polaris/wt/phase0 && git push' (pushes 8eec65c + the new docs). 
4. git add docs/review_readiness/retro_validation_phase1.md docs/review_readiness/comparison_protocol.md; commit ("Phase 0-A: retro-validate Phase 1 migration against pinned oracle (band=0)") with trailers:
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TLpJSqNfJVSP1UGdtk89nA
5. Push. Also clean up the scratch worktree: 'cd /workspace/POLARIS && git worktree remove ${SCRATCH} --force 2>/dev/null; git branch -D retro-validate-scratch 2>/dev/null'.
Return {commit_sha, pushed, oracle_pushed}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false, required:['commit_sha','pushed','oracle_pushed'], properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'}, oracle_pushed:{type:'boolean'} } } })

return { replay, gate, record: rec }
