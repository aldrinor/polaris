export const meta = {
  name: 'S6-reproducible-build',
  description: 'S6 reproducible build: hash-pinned deps + SBOM + documented reproducible build + two-build hash-match method',
  phases: [
    { title: 'Assess', detail: 'inventory current dep-pinning/lock state + build entrypoints' },
    { title: 'Build', detail: 'add dep hashes/SBOM + reproducible-build doc (no runtime code changes)' },
    { title: 'Verify', detail: 'collection unchanged; SBOM validates; hashes present' },
    { title: 'Codex-Gate', detail: 'codex checks the S6 acceptance (hash-pinned + SBOM + build doc)' },
    { title: 'Record', detail: 'commit + push + PR' },
  ],
}
const PY = '/home/polaris/pipeline-env/bin/python'
const WT = '/home/polaris/wt/phase-s6'

phase('Assess')
const assess = await agent(
  `Set up S6 (reproducible build) for a Python research pipeline.
1. cd /workspace/POLARIS && git worktree remove ${WT} --force 2>/dev/null; git branch -D chore/review-readiness-s6 2>/dev/null; git worktree add ${WT} -b chore/review-readiness-s6 chore/review-readiness-phase1.
2. Inventory the current dependency + build state in ${WT}: requirements.lock / requirements.txt / pyproject.toml / uv.lock / setup.py — which exist, are versions pinned (==), are cryptographic HASHES present (--hash= lines / uv.lock [[package]] hashes)? Count '--hash=' occurrences. Is there an SBOM (any *.cdx.json / *.spdx.json / bom.xml)? Is the build documented (README build section)? Is python version pinned (pyproject requires-python / .python-version)?
3. Check what tooling is available: '${PY} -m pip --version', is pip-tools/uv/cyclonedx-py/pip-audit installed ('${PY} -m pip list 2>/dev/null | grep -iE "uv|cyclonedx|pip-tools|pip-audit"')?
Return: current state (pinned? hashed? sbom? build-doc? python-pinned?), the count of --hash lines, available tooling, and the gaps to close for S6.`,
  { label: 'assess', phase: 'Assess', schema: { type:'object', additionalProperties:false, required:['versions_pinned','hashes_present','hash_count','sbom_present','build_doc_present','python_pinned','tooling','gaps'], properties:{ versions_pinned:{type:'boolean'}, hashes_present:{type:'boolean'}, hash_count:{type:'integer'}, sbom_present:{type:'boolean'}, build_doc_present:{type:'boolean'}, python_pinned:{type:'boolean'}, tooling:{type:'string'}, gaps:{type:'array',items:{type:'string'}} } } })

phase('Build')
const build = await agent(
  `Close the S6 gaps in ${WT}. Current state: ${JSON.stringify(assess)}. Do ONLY build/deps/docs artifacts — NO runtime code changes (nothing under src/ logic).
1. DEPENDENCY HASHES: if hashes are absent and tooling permits, generate a hash-pinned lock. Prefer the existing lock format. If uv is available: 'uv export --format requirements-txt --no-emit-project > requirements.hashed.txt' (or the equivalent that emits --hash lines). If only pip-tools: 'pip-compile --generate-hashes'. If neither tool is available in this env, DO NOT fabricate hashes — instead write a documented, runnable command in the build doc for how to regenerate a hash-pinned lock, and note the current lock is version-pinned but not hash-pinned. Whatever you produce must be REAL (generated), never hand-written hashes.
2. SBOM: if cyclonedx-py or a similar tool is available, generate a CycloneDX SBOM (${WT}/sbom.cdx.json) from the environment/lock. If no SBOM tool is available, write the exact command to generate it in the build doc and note the SBOM is produced by that documented step (do not fabricate an SBOM).
3. BUILD DOC: write ${WT}/docs/review_readiness/reproducible_build.md documenting: the pinned Python version, the locked+hashed deps (or the command to produce them), the exact build/install commands, how to produce the SBOM, and the TWO-BUILD HASH-MATCH method (build twice in clean envs, hash the artifacts, diff — reference the deterministic-oracle byte-diff approach as precedent). Be honest about what is fully automated vs a documented manual step given this env's tooling.
Report what was actually generated (real artifacts) vs documented-as-a-command, files changed, and confirm no src/ runtime code changed.`,
  { label: 'build', phase: 'Build', schema: { type:'object', additionalProperties:false, required:['hashes_generated','sbom_generated','build_doc_written','files_changed','no_runtime_change','notes'], properties:{ hashes_generated:{type:'boolean'}, sbom_generated:{type:'boolean'}, build_doc_written:{type:'boolean'}, files_changed:{type:'array',items:{type:'string'}}, no_runtime_change:{type:'boolean'}, notes:{type:'string'} } } })

phase('Verify')
const verify = await agent(
  `Verify S6 artifacts in ${WT}. 1. Collection unchanged: '${PY} -m pytest tests/ --collect-only -q | tail -1' (16738/11) — proves no runtime code changed. 2. If a hashed requirements file was generated, spot-check it has real --hash=sha256: lines ('grep -c "hash=sha256" <file>'). 3. If an SBOM was generated, validate it is well-formed JSON with components ('${PY} -c "import json,sys; d=json.load(open(sys.argv[1])); print(len(d.get(chr(99)+chr(111)+chr(109)+chr(112)+chr(111)+chr(110)+chr(101)+chr(110)+chr(116)+chr(115),[])))" <sbom>' or simpler: python -c to count components). 4. Confirm git status shows NO changes under src/ (only deps/lock/docs/sbom). Return collection_ok, hashes_valid, sbom_valid, only_build_artifacts_changed.`,
  { label: 'verify', phase: 'Verify', schema: { type:'object', additionalProperties:false, required:['collection_ok','hashes_valid','sbom_valid','only_build_artifacts_changed'], properties:{ collection_ok:{type:'boolean'}, hashes_valid:{type:'boolean'}, sbom_valid:{type:'boolean'}, only_build_artifacts_changed:{type:'boolean'} } } })

phase('Codex-Gate')
const gate = await agent(
  `Run CODEX (GPT-5.6) to gate S6. Write /tmp/s6_gate.md then 'cd /tmp && timeout 200 codex exec --skip-git-repo-check - < /tmp/s6_gate.md 2>&1 | tail -25' (embed inline; medium; no sandbox flags).
S6 acceptance (Plan V4): two independent builds hash-match + hash-pinned deps + locked env + documented build + SBOM. Evidence: assess=${JSON.stringify(assess)}, build=${JSON.stringify(build)}, verify=${JSON.stringify(verify)}. Note: some artifacts may be documented-runnable-commands rather than generated, if this env lacks the tooling — that is acceptable IF honestly labeled and the commands are real.
Ask codex: "Does this satisfy S6 or make defensible progress? Are the dep hashes REAL (not fabricated), is the SBOM well-formed or its generation documented, is the two-build hash-match method sound, and is no runtime code changed? Flag any fabricated/hand-written hashes or SBOM. End with S6-OK or S6-REVISE (+ the gap)."
Return verdict + points.`,
  { label: 'codex-gate', phase: 'Codex-Gate', schema: { type:'object', additionalProperties:false, required:['verdict','codex_points'], properties:{ verdict:{type:'string'}, codex_points:{type:'array',items:{type:'string'}} } } })

phase('Record')
const rec = await agent(
  `Record S6 in ${WT} (branch chore/review-readiness-s6). Only commit if verify passed (collection_ok, only_build_artifacts_changed) and codex=S6-OK (${gate.verdict}); else commit what's defensible + note the gap.
Stage the build/deps/docs/sbom files explicitly (git add of the specific new files + docs/; guard 0 tests/oracle staged; NO src/ runtime changes should be staged). Commit ("S6: reproducible build — hash-pinned deps + SBOM + build doc + two-build hash-match method") with standard trailers. Push -u origin; PR base gate-inversion (title "Code-review readiness: S6 reproducible build", body summarizing what's generated vs documented).
Return {commit_sha, pushed, pr_url, committed_or_blocked}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false, required:['commit_sha','pushed','pr_url','committed_or_blocked'], properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'}, pr_url:{type:'string'}, committed_or_blocked:{type:'string'} } } })

return { assess, build, verify, gate, record: rec }
