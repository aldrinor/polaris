export const meta = {
  name: 'phase0a-baseline',
  description: 'Phase 0-A per codex-corrected order: secret-safe manifest anchored to pre-change commit + comparison protocol + harness repair/diagnosis (no pipeline runs yet)',
  phases: [
    { title: 'Artifacts', detail: 'secret-safe manifest (anchored to b6e8ef5) + comparison protocol' },
    { title: 'Harness', detail: 'portable copy of the acceptance harness + diagnose the broken positive control' },
    { title: 'Codex-Gate', detail: 'codex verifies the artifacts + harness verdict meet 0A acceptance' },
    { title: 'Record', detail: 'commit + push to phase0 branch + audit-findings doc' },
  ],
}

const WT = '/home/polaris/wt/phase0'   // branch chore/review-readiness-phase0, PR #1381
const ANCHOR = 'b6e8ef5'               // parent of 43214a2 = last commit before ANY runtime code change
const PY = '/home/polaris/pipeline-env/bin/python'

phase('Artifacts')
const artifacts = await parallel([
  () => agent(
    `Build the SECRET-SAFE Phase 0-A baseline manifest for a research pipeline, per Plan V4 item 0A-1, in worktree ${WT} (branch chore/review-readiness-phase0).
CRITICAL: the manifest must anchor to commit ${ANCHOR} — the last commit BEFORE any runtime code was changed by this initiative (the review-readiness runtime changes start at 43214a2). Record that SHA as the anchor.
Gather and write a JSON file to ${WT}/docs/review_readiness/baseline_manifest.json containing:
- anchor_commit: ${ANCHOR} (and a one-line note: runtime code here == pre-initiative pipeline state)
- requirements_lock_sha256: compute via 'cd ${WT} && git show ${ANCHOR}:requirements.lock | sha256sum' (the lock AS OF the anchor commit)
- python_version (3.11.10) and OS/platform (uname -a, trimmed)
- provider/model routing config: read the model-selection config (settings.py ModelSettings defaults + any PG_*_MODEL in .env). Record every env var NAME and its NON-SECRET value verbatim.
- FOR EVERY SECRET (any var whose name matches KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL): record ONLY {sha256_of_value_first16 or full sha256, present: true/false} — NEVER the raw value. If a secret is absent/empty, present:false. Read secrets from ${WT}/.env or /workspace/POLARIS/.env if present; if no .env is readable, record present:false with a note.
- seeds: any fixed seeds used by the pipeline/harness (grep for seed= / PYTHONHASHSEED / random.seed); if none, say 'none declared'.
- exact_commands: the command(s) that run the acceptance harness (acceptance_outline_agent.py) and the test suite.
- input_fixtures: list the fixture files the acceptance harness consumes (grep the harness for fixture/json paths).
This file is SECRET-SAFE (only digests) and MUST be committed to the branch as reviewer evidence (durable, not git-ignored) — write it under docs/review_readiness/ which is tracked. Double-check no raw secret value appears anywhere in it (grep your own output).
Return a summary of what you recorded and CONFIRM 'no plaintext secret in manifest'.`,
    { label: 'manifest', phase: 'Artifacts', schema: { type:'object', additionalProperties:false, required:['path','secret_safe_confirmed','summary'], properties:{ path:{type:'string'}, secret_safe_confirmed:{type:'boolean'}, summary:{type:'string'} } } }),
  () => agent(
    `Write the Phase 0-A COMPARISON PROTOCOL doc (Plan V4 item 0A-4) to ${WT}/docs/review_readiness/comparison_protocol.md.
It must declare — BEFORE any change is measured — the precise definition of "the pipeline did not change":
- "same" = the governing RACE score stays within a DECLARED equivalence band over N>=3 repeats, AND the faithfulness verdicts match EXACTLY as PER-FIXTURE-KEYED verdicts (keyed by fixture id — NOT as unordered sets; sets discard fixture identity/ordering/multiplicity, which is insufficient), AND artifact-hash (SHA-256) match for artifacts meant to be deterministic.
- Define what counts as a REGRESSION vs NOISE: regression = RACE outside the band OR any per-fixture faithfulness verdict flip OR a deterministic-artifact hash mismatch; noise = RACE jitter within the band on non-deterministic-but-bounded measures.
- State the governing rule: the RACE score and faithfulness verdicts are NEVER quarantined; if they cannot be characterized within a stable band, that is a BLOCKING STOP (investigate variance), not a proceed.
- Note the equivalence band VALUE is filled in after the N>=3 characterization run (leave a clearly-marked TODO for the measured band).
Return the path and a 3-line summary.`,
    { label: 'protocol', phase: 'Artifacts', schema: { type:'object', additionalProperties:false, required:['path','summary'], properties:{ path:{type:'string'}, summary:{type:'string'} } } }),
])

phase('Harness')
const harness = await agent(
  `Diagnose and repair the acceptance harness for a research pipeline so it can serve as the governing oracle (Plan V4 0A-2/0A-3 prerequisite). Worktree: ${WT}.
The harness is ${WT}/acceptance_outline_agent.py. It currently (a) hardcodes non-portable paths and (b) is documented as broken (its THIN positive control fires 0 searches when it should trigger search_more_evidence).
Do this WITHOUT modifying the production pipeline runtime and WITHOUT modifying the original harness file in place:
1. Copy acceptance_outline_agent.py to ${WT}/tests/oracle/acceptance_portable.py. In the COPY, replace the 4 hardcoded paths (line 28 sys.path.insert "/workspace/outline_agent_wt"; line 31 load_dotenv "/workspace/POLARIS/.env"; lines 281-282 output "/workspace/outline_agent_wt/acceptance_result*.json") with repo-relative or env-var-configurable paths that work from ${WT}.
2. Try to run the portable copy: 'cd ${WT} && ${PY} tests/oracle/acceptance_portable.py' (use a short timeout; it may need provider access or a cassette — note what it needs).
3. DIAGNOSE the positive-control-fires-0-searches problem: read the harness to understand what the THIN positive control asserts (it expects search_more_evidence to fire N>0 searches). Determine the ROOT CAUSE — is the harness scenario misconfigured, is search gated off by an env flag, does it need the cassette/offline path, or is the control assertion itself vacuous? Cite the exact code.
4. Return a VERDICT on whether this harness can be pinned as a trustworthy governing oracle, or whether pinning is currently BLOCKED (and why). Be honest — a broken positive control means the oracle is NOT yet trustworthy.
Do NOT run the full pipeline N times here; only enough to diagnose runnability + the positive control.`,
  { label: 'harness-diagnose', phase: 'Harness', schema: { type:'object', additionalProperties:false,
    required:['portable_copy_path','harness_runs','positive_control_valid','root_cause','can_be_pinned','blocking_reason'],
    properties:{ portable_copy_path:{type:'string'}, harness_runs:{type:'boolean'}, positive_control_valid:{type:'boolean'}, root_cause:{type:'string'}, can_be_pinned:{type:'boolean'}, blocking_reason:{type:'string'} } } })

phase('Codex-Gate')
const gate = await agent(
  `Run CODEX (GPT-5.6), the plan's independent adversarial reviewer, to gate Phase 0-A artifacts.
Context to give codex (write to /tmp/p0a_gate.md then run 'cd /tmp && timeout 300 codex exec --skip-git-repo-check - < /tmp/p0a_gate.md 2>&1 | tail -40'; bubblewrap warning is fine, no sandbox flags):
- Plan V4 0A requires: secret-safe manifest anchored to the PRE-runtime-change commit (${ANCHOR}); a comparison protocol with PER-FIXTURE-KEYED faithfulness verdicts + declared equivalence band; the governing oracle statistically characterized or execution BLOCKED.
- Manifest result: ${JSON.stringify(artifacts[0])}
- Protocol result: ${JSON.stringify(artifacts[1])}
- Harness diagnosis: ${JSON.stringify(harness)}
Ask codex: "Do the manifest + comparison protocol meet Plan V4 0A-1/0A-4 acceptance (secret-safe, anchored to the pre-change commit, per-fixture verdicts, durable)? Given the harness diagnosis, is the correct next action to (a) proceed to the N>=3 characterization run, or (b) declare a BLOCKING STOP until the positive control is fixed? Name any gap. End with: P0A-ARTIFACTS-OK or P0A-ARTIFACTS-REVISE, and NEXT: RUN-CHARACTERIZATION or NEXT: FIX-HARNESS-FIRST."
Return codex's verdict + the NEXT directive verbatim.`,
  { label: 'codex-gate', phase: 'Codex-Gate', schema: { type:'object', additionalProperties:false,
    required:['verdict','next_directive','codex_points'],
    properties:{ verdict:{type:'string'}, next_directive:{type:'string'}, codex_points:{type:'array',items:{type:'string'}} } } })

phase('Record')
const rec = await agent(
  `Record Phase 0-A progress to the branch and GitHub. Worktree ${WT} (branch chore/review-readiness-phase0).
1. Write ${WT}/docs/review_readiness/planv4_audit_2026-07-19.md capturing the codex-gated Plan-V4 audit finding: "Phase 0 baseline was skipped; all Phase 1 runtime work stood on an un-pinned oracle (Plan V4 safety rule 1 violation). Corrected order per codex: manifest anchored to ${ANCHOR} -> repair+validate harness -> N>=3 characterization -> comparison protocol -> selector fixtures -> retro-validate every runtime change module-by-module. Status downgrades: 1A/1C-order VIOLATED, 2B NOT-STARTED, S3 MISSING." Keep it concise but concrete.
2. git add the new files under docs/review_readiness/ (baseline_manifest.json, comparison_protocol.md, planv4_audit_2026-07-19.md) and the portable harness copy under tests/oracle/. Do NOT stage any file containing a plaintext secret — grep-check first.
3. Commit with a clear message describing the audit finding + the 0A artifacts, ending with:
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TLpJSqNfJVSP1UGdtk89nA
4. Push: 'cd ${WT} && git push'. Report the commit SHA and push result.
Return {commit_sha, pushed, files_committed}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false,
    required:['commit_sha','pushed','files_committed'],
    properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'}, files_committed:{type:'array',items:{type:'string'}} } } })

return { artifacts, harness, gate, record: rec }
