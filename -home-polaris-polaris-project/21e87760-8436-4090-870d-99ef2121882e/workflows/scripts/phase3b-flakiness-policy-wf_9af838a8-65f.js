export const meta = {
  name: 'phase3b-flakiness-policy',
  description: '3B/S3: N-run flakiness characterization, quarantine flaky NON-governing tests, flakiness-bar doc, add dep-hash+license+secret scanning to CI (report-only, not required)',
  phases: [
    { title: 'Setup', detail: 'worktree + correct oracle harness + inventory current CI/scanning' },
    { title: 'Characterize', detail: 'run the suite N>=3, identify flaky non-governing tests' },
    { title: 'Policy', detail: 'quarantine list + flakiness-bar doc + CI scanning (report-only)' },
    { title: 'Codex-Gate', detail: 'codex checks the policy + that governing tests are never quarantined' },
    { title: 'Record', detail: 'commit + push + PR' },
  ],
}
const PY = '/home/polaris/pipeline-env/bin/python'
const WT = '/home/polaris/wt/phase-3b'

phase('Setup')
const setup = await agent(
  `Set up Plan V4 3B / deliverable S3 (flakiness policy before required CI).
1. cd /workspace/POLARIS && git worktree remove ${WT} --force 2>/dev/null; git branch -D chore/review-readiness-3b 2>/dev/null; git worktree add ${WT} -b chore/review-readiness-3b chore/review-readiness-phase1.
2. Inventory the current CI: read ${WT}/.github/workflows/*.yml — is CI report-only (continue-on-error / || true)? Is there any dependency-hash check, license scan, or secret scan (pip-audit/bandit/gitleaks/detect-secrets)? What's the current test command?
3. Identify the GOVERNING tests that must NEVER be quarantined: the oracle acceptance (tests/oracle/*) and any RACE/faithfulness/strict_verify tests. List them so the policy protects them.
4. Baseline collection: '${PY} -m pytest tests/ --collect-only -q | tail -1' (16738/11).
Return: ci_report_only (bool), existing_scanning (list), test_command, governing_tests (list), baseline.`,
  { label: 'setup', phase: 'Setup', schema: { type:'object', additionalProperties:false, required:['ci_report_only','existing_scanning','test_command','governing_tests','baseline'], properties:{ ci_report_only:{type:'boolean'}, existing_scanning:{type:'array',items:{type:'string'}}, test_command:{type:'string'}, governing_tests:{type:'array',items:{type:'string'}}, baseline:{type:'string'} } } })

phase('Characterize')
const chars = await agent(
  `Characterize test flakiness in ${WT}. Run a BOUNDED, fast subset of the suite MULTIPLE times (N>=3) to find flaky NON-governing tests — do NOT run the whole 16738-test suite 3x (too slow); instead pick the unit + fast integration tests (exclude slow/api/live markers, exclude tests/oracle) and run them 3 times, capturing which tests PASS sometimes and FAIL other times (flaky) vs consistently pass/fail.
Command pattern: for i in 1 2 3; do ${PY} -m pytest tests/unit tests/polaris_graph -q -x=false -p no:cacheprovider -m 'not slow and not api and not live' --tb=no 2>&1 | tail -3; done  (adjust to real markers). Collect the set of tests with non-deterministic outcomes across the 3 runs.
Also note the 11 known pre-existing COLLECTION errors (import/env issues) — these are separate from flaky tests.
Return: the flaky test node-ids found (list, may be empty), consistently-failing non-governing tests, and the run-to-run pass counts. Do NOT quarantine anything governing.`,
  { label: 'characterize', phase: 'Characterize', schema: { type:'object', additionalProperties:false, required:['flaky_tests','consistent_failures','run_pass_counts','notes'], properties:{ flaky_tests:{type:'array',items:{type:'string'}}, consistent_failures:{type:'array',items:{type:'string'}}, run_pass_counts:{type:'string'}, notes:{type:'string'} } } })

phase('Policy')
const policy = await agent(
  `Write the 3B/S3 flakiness policy + CI scanning in ${WT}. Inputs: setup=${JSON.stringify(setup)}, flakiness=${JSON.stringify(chars)}.
1. docs/review_readiness/flakiness_policy.md: define the non-flakiness BAR (e.g. a test must pass K consecutive CI runs to be "stable"; the suite flips report-only→required ONLY after N days green). State the ABSOLUTE rule: the GOVERNING measurement (oracle RACE/faithfulness — ${JSON.stringify(setup.governing_tests)}) is NEVER quarantined; if it is unstable that is a BLOCKING stop. List any flaky NON-governing tests found (${JSON.stringify(chars.flaky_tests)}) as the tracked quarantine list (mark with @pytest.mark.flaky or a documented skip-list — do NOT actually delete them).
2. If flaky tests were found, add a tracked quarantine mechanism (a docs/flaky_quarantine.txt list + optionally a conftest marker) — non-governing only.
3. CI scanning (report-only, do NOT make CI required): add to the CI workflow (or a new report-only job) dependency-hash verification (pip check / pip-audit), a license scan, and a secret scan (detect-secrets or gitleaks) — all as continue-on-error/report-only steps. If the scanning tools aren't installed, add the steps with the install command + note they run in CI where the tools are available; do NOT fabricate scan results.
Keep it honest: no runtime code changes; CI stays report-only.
Return: files_written, quarantine_count, scanning_added (list), ci_still_report_only.`,
  { label: 'policy', phase: 'Policy', schema: { type:'object', additionalProperties:false, required:['files_written','quarantine_count','scanning_added','ci_still_report_only'], properties:{ files_written:{type:'array',items:{type:'string'}}, quarantine_count:{type:'integer'}, scanning_added:{type:'array',items:{type:'string'}}, ci_still_report_only:{type:'boolean'} } } })

phase('Codex-Gate')
const gate = await agent(
  `Run CODEX (GPT-5.6) to gate 3B/S3. Write /tmp/threeb_gate.md then 'cd /tmp && timeout 200 codex exec --skip-git-repo-check - < /tmp/threeb_gate.md 2>&1 | tail -25' (embed inline; medium; no sandbox flags).
Plan V4 3B: flakiness policy BEFORE CI becomes required — N-run stability, quarantine flaky NON-governing tests (governing RACE/faithfulness NEVER quarantined), define the bar, add dep-hash+license+secret scanning, keep CI report-only until provably stable. Evidence: setup=${JSON.stringify(setup)}, flakiness=${JSON.stringify(chars)}, policy=${JSON.stringify(policy)}.
Ask codex: "Does this establish a sound flakiness policy that (a) protects the governing measurement from ever being quarantined, (b) tracks flaky non-governing tests without deleting them, (c) adds dep-hash/license/secret scanning as report-only, and (d) keeps CI report-only (not flipped to required)? Any fabricated scan results or a governing test wrongly quarantined? End with 3B-OK or 3B-REVISE."
Return verdict + points.`,
  { label: 'codex-gate', phase: 'Codex-Gate', schema: { type:'object', additionalProperties:false, required:['verdict','codex_points'], properties:{ verdict:{type:'string'}, codex_points:{type:'array',items:{type:'string'}} } } })

phase('Record')
const rec = await agent(
  `Record 3B in ${WT} (branch chore/review-readiness-3b). Commit only if codex=3B-OK (${gate.verdict}) and ci_still_report_only=${policy.ci_still_report_only}. Stage explicit paths (docs/ + .github/ + any quarantine list + conftest; NOT tests/oracle — guard git diff --cached --name-only | grep -c tests/oracle == 0). No-secret grep. Commit ("Phase 3B/S3: flakiness policy + report-only CI scanning (governing measurement never quarantined)") with standard trailers. Push -u origin; PR base gate-inversion.
Return {commit_sha, pushed, pr_url, committed_or_blocked}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false, required:['commit_sha','pushed','pr_url','committed_or_blocked'], properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'}, pr_url:{type:'string'}, committed_or_blocked:{type:'string'} } } })

return { setup, chars, policy, gate, record: rec }
