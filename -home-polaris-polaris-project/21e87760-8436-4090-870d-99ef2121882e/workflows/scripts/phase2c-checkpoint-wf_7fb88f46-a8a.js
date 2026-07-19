export const meta = {
  name: 'phase2c-checkpoint',
  description: 'Turn on the generation checkpoint (2C): save pre-check data only, gate write behind PG_CHECKPOINT_ENABLED so flag-off runs stay byte-identical, reload re-verifies from scratch',
  phases: [
    { title: 'Setup', detail: 'worktree + study checkpoint_manager.py + the generation loop' },
    { title: 'Wire', detail: 'save pre-check data (gated by flag) + reload path (re-verify from scratch)' },
    { title: 'Validate', detail: 'flag-off oracle byte-identical + collection unchanged + flag-on save/reload roundtrip test' },
    { title: 'Codex-Gate', detail: 'codex confirms flag-off byte-identical + no verdict persisted' },
    { title: 'Record', detail: 'commit + push + PR' },
  ],
}
const PY = '/home/polaris/pipeline-env/bin/python'
const GOLDEN = '9c0a3d438da943242c98e2fe714494c342d42d02102202d75a61a4554339db98'
const WT = '/home/polaris/wt/phase2c'

phase('Setup')
const setup = await agent(
  `Set up to wire the generation checkpoint (Plan V4 item 2C) in a research pipeline.
1. cd /workspace/POLARIS && git worktree remove ${WT} --force 2>/dev/null; git branch -D chore/review-readiness-phase2c 2>/dev/null; git worktree add ${WT} -b chore/review-readiness-phase2c chore/review-readiness-phase1.
2. Overlay the pinned oracle for validation: cd ${WT} && git checkout chore/review-readiness-phase0 -- tests/oracle/ 2>/dev/null; cp -n /home/polaris/wt/phase0/tests/oracle/cassettes/*.jsonl /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_golden.json ${WT}/tests/oracle/cassettes/ 2>/dev/null; ls ${WT}/tests/oracle/cassettes/.
3. STUDY the checkpoint mechanism: read src/polaris_graph/**/checkpoint_manager.py fully (find it). Understand: what does it save/load, what is PG_CHECKPOINT_ENABLED (default '0'), is the save/reload actually WIRED into the generation loop or is it a dormant module?
4. Find the GENERATION LOOP where a checkpoint should save (after drafts/outline are produced but BEFORE the faithfulness/strict_verify check — 'pre-check data only, never a verdict') and where it should reload (on restart, re-verify from scratch). Identify the exact functions/files + the current wiring state.
5. Baseline: 'cd ${WT} && timeout 200 ${PY} -m pytest tests/ --collect-only -q 2>&1 | tail -1' (expect 16738/11).
Return: checkpoint_manager location + capabilities, whether save/reload is already wired or dormant, the exact save-point and reload-point in the generation loop, and the baseline.`,
  { label: 'setup', phase: 'Setup', schema: { type:'object', additionalProperties:false, required:['checkpoint_manager','wiring_state','save_point','reload_point','baseline'], properties:{ checkpoint_manager:{type:'string'}, wiring_state:{type:'string'}, save_point:{type:'string'}, reload_point:{type:'string'}, baseline:{type:'string'} } } })

phase('Wire')
const wire = await agent(
  `Wire the generation checkpoint in ${WT} per Plan V4 2C + the safety rules. Context from setup: checkpoint_manager=${JSON.stringify(setup.checkpoint_manager)}; wiring_state=${JSON.stringify(setup.wiring_state)}; save_point=${JSON.stringify(setup.save_point)}; reload_point=${JSON.stringify(setup.reload_point)}.
REQUIREMENTS (hard):
1. SAVE PRE-CHECK DATA ONLY — drafts + outline + retrieved-evidence needed to resume, NEVER a faithfulness/strict_verify VERDICT (a resumed run must re-verify from scratch, so a poisoned/partial verdict can never be trusted from disk).
2. The WRITE must be gated behind PG_CHECKPOINT_ENABLED (default '0'/off). When the flag is OFF, the generation path must be BYTE-IDENTICAL to today — no checkpoint file written, no new branch taken, no changed ordering. Use the config accessor already in the codebase (resolve('PG_CHECKPOINT_ENABLED') or os.getenv) — do NOT change its default.
3. The RELOAD path (on restart with the flag on + a checkpoint present): load the pre-check drafts/outline, then RUN THE FAITHFULNESS/STRICT_VERIFY CHECK AGAIN from scratch (never trust a saved verdict).
4. If checkpoint_manager already implements save/load correctly, you may only need to WIRE the call sites (guarded by the flag); reuse it, don't rewrite.
Keep the change minimal and localized. py_compile all changed files. After wiring, confirm collection stays at baseline (${setup.baseline}).
Return: files changed, exactly where the flag-gated save + reload were added, and confirmation that flag-OFF takes no new code path (the guard wraps the entire checkpoint write).`,
  { label: 'wire', phase: 'Wire', schema: { type:'object', additionalProperties:false, required:['files_changed','save_wiring','reload_wiring','flag_off_is_noop','collection_after'], properties:{ files_changed:{type:'array',items:{type:'string'}}, save_wiring:{type:'string'}, reload_wiring:{type:'string'}, flag_off_is_noop:{type:'boolean'}, collection_after:{type:'string'} } } })

phase('Validate')
const validate = await agent(
  `Validate the checkpoint wiring in ${WT} is byte-identical when OFF and functional when ON.
1. FLAG-OFF byte-identical (the critical gate): 'cd ${WT} && PG_OUTLINE_AGENT_MAX_TURNS=3 ${PY} tests/oracle/acceptance_portable.py --replay 2>&1 | tail -12' with PG_CHECKPOINT_ENABLED unset/0 — artifact SHA MUST equal ${GOLDEN}, both controls pass. (Proves normal runs are unchanged.)
2. Collection unchanged: '${PY} -m pytest tests/ --collect-only -q | tail -1' == ${setup.baseline}.
3. Config characterization: '${PY} -m pytest tests/test_config_registry.py tests/test_settings_models.py -q | tail -1'.
4. FLAG-ON roundtrip: write a NEW test (tests/test_checkpoint_roundtrip.py) that, with PG_CHECKPOINT_ENABLED=1, exercises the checkpoint save then reload and asserts: (a) a checkpoint artifact is written containing drafts/outline, (b) it contains NO faithfulness/strict_verify verdict field, (c) the reload path re-runs verification (does not read a verdict from disk). Run it and report pass/fail. Keep the test hermetic (no network — stub/monkeypatch as needed).
Return all gate outcomes + the oracle SHA + whether the new roundtrip test passes + confirmation no verdict is persisted.`,
  { label: 'validate', phase: 'Validate', schema: { type:'object', additionalProperties:false, required:['flag_off_oracle_sha','flag_off_byte_identical','collection_ok','characterization_ok','roundtrip_test_passes','no_verdict_persisted','notes'], properties:{ flag_off_oracle_sha:{type:'string'}, flag_off_byte_identical:{type:'boolean'}, collection_ok:{type:'boolean'}, characterization_ok:{type:'boolean'}, roundtrip_test_passes:{type:'boolean'}, no_verdict_persisted:{type:'boolean'}, notes:{type:'string'} } } })

phase('Codex-Gate')
const gate = await agent(
  `Run CODEX (GPT-5.6) to gate the checkpoint wiring. Write /tmp/ckpt_gate.md then 'cd /tmp && timeout 240 codex exec --skip-git-repo-check - < /tmp/ckpt_gate.md 2>&1 | tail -30' (embed evidence inline; medium effort; no sandbox flags; bubblewrap warning fine).
Context: wired the generation checkpoint. wire=${JSON.stringify(wire)}. validate=${JSON.stringify(validate)}. Requirements: flag-off byte-identical (oracle SHA ${GOLDEN} unchanged), save PRE-CHECK data only (no faithfulness verdict persisted), reload re-verifies from scratch.
Ask codex: "Is the flag-off path provably byte-identical (write fully guarded by PG_CHECKPOINT_ENABLED, default unchanged, oracle SHA unchanged)? Does the checkpoint persist ONLY pre-check data (drafts/outline) and NEVER a faithfulness/strict_verify verdict, so a resumed run cannot trust a stale verdict? Does the reload path re-run verification from scratch? Any way a poisoned/partial checkpoint could corrupt a resumed run's faithfulness? End with: CHECKPOINT-SAFE or CHECKPOINT-REVISE."
Return verdict + points.`,
  { label: 'codex-gate', phase: 'Codex-Gate', schema: { type:'object', additionalProperties:false, required:['verdict','codex_points'], properties:{ verdict:{type:'string'}, codex_points:{type:'array',items:{type:'string'}} } } })

phase('Record')
const rec = await agent(
  `Record the 2C checkpoint wiring. Worktree ${WT} (branch chore/review-readiness-phase2c).
Only commit if validate passed (flag_off_byte_identical=${validate.flag_off_byte_identical}, collection_ok=${validate.collection_ok}, roundtrip_test_passes=${validate.roundtrip_test_passes}, no_verdict_persisted=${validate.no_verdict_persisted}) and codex=CHECKPOINT-SAFE (${gate.verdict}). Else commit nothing, report blocker.
1. Stage src/ + the new tests/test_checkpoint_roundtrip.py (NOT the overlaid tests/oracle/*). Grep-check no secret.
2. Write docs/review_readiness/checkpoint_2c.md: what was wired, the flag-off byte-identical proof (oracle SHA), the pre-check-data-only guarantee, the reload-re-verifies design, codex verdict.
3. Commit ("Phase 2C: wire generation checkpoint (pre-check data only, flag-gated, byte-identical when off)") with trailers:
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TLpJSqNfJVSP1UGdtk89nA
4. Push -u origin chore/review-readiness-phase2c; open PR to base gate-inversion: '/home/polaris/.local/bin/gh pr create --repo aldrinor/deep-cove-research --base gate-inversion --head chore/review-readiness-phase2c --title "Code-review readiness: Phase 2C generation checkpoint (flag-gated, byte-identical off)" --body "Turns on the generation checkpoint: saves pre-check data only (drafts/outline, never a verdict), write gated behind PG_CHECKPOINT_ENABLED (default off = byte-identical, oracle-proven 9c0a3d43), reload re-verifies from scratch. 🤖 Generated with [Claude Code](https://claude.com/claude-code)"'.
Return {commit_sha, pushed, pr_url, committed_or_blocked}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false, required:['commit_sha','pushed','pr_url','committed_or_blocked'], properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'}, pr_url:{type:'string'}, committed_or_blocked:{type:'string'} } } })

return { setup: { wiring_state: setup.wiring_state, save_point: setup.save_point }, wire, validate, gate, record: rec }
