export const meta = {
  name: 'race-followups',
  description: 'Fix 2 rename stragglers (codex-gated) + attempt champion-recipe A/B or record blocked (codex-gated)',
  phases: [
    { title: 'Stragglers' },
    { title: 'AB-Test' },
  ],
}

const STRAG_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['diff', 'verify_ok', 'codex_verdict', 'commit_sha', 'pushed', 'notes'],
  properties: {
    diff: { type: 'string', description: 'the git diff of the straggler fix' },
    verify_ok: { type: 'boolean' },
    codex_verdict: { type: 'string', description: 'codex gate token + one line' },
    commit_sha: { type: 'string' },
    pushed: { type: 'boolean' },
    notes: { type: 'string' },
  },
}

const AB_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['browser_fixed', 'ran_paid_ab', 'baseline_score', 'renamed_score', 'delta', 'blocked_reason', 'codex_verdict', 'cost_usd', 'recipe', 'notes'],
  properties: {
    browser_fixed: { type: 'boolean' },
    ran_paid_ab: { type: 'boolean' },
    baseline_score: { type: 'string' },
    renamed_score: { type: 'string' },
    delta: { type: 'string' },
    blocked_reason: { type: 'string' },
    codex_verdict: { type: 'string' },
    cost_usd: { type: 'string' },
    recipe: { type: 'string', description: 'exact reproduction recipe for a working-browser box' },
    notes: { type: 'string' },
  },
}

phase('Stragglers')
const strag = await agent(`Claude-codex workflow DELIVERABLE 1: fix 2 rename stragglers left by the file-rename PR #1394, then codex-gate.

SETUP: create a CLEAN detached worktree at the committed head of the filerename branch (do NOT use the live /home/polaris/wt/phase-file worktree — it has a concurrent bot's uncommitted changes):
  cd /home/polaris/wt/phase0
  SHA=$(git ls-remote origin refs/heads/chore/review-readiness-filerename | cut -f1)
  WT=/tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/strag_wt
  rm -rf "$WT"; git worktree add --detach "$WT" "$SHA"
  cd "$WT"

FIX #1 — scripts/diagnostics/entailment_rotation_behavioral.py: it imports 'benchmark_run_capture' (line 43) but calls 'pathB_capture.set_role_providers(...)' (line 63) and 'pathB_capture.reset_role_providers(...)' (line 68) — pathB_capture is undefined -> NameError. Change those two calls from pathB_capture -> benchmark_run_capture. (Do NOT touch the import; it is already correct.)

FIX #2 — scripts/operational_readiness_preflight.py line 93: '_PATHB_RUNNER = _REPO_ROOT / "src" / "polaris_graph" / "benchmark" / "pathB_runner.py"' points at the OLD filename. Change 'pathB_runner.py' -> 'benchmark_gate_runner.py' (the renamed file). Leave the doc/comment references (lines 26,328,427,454) as-is — those are prose about pathB_runner.gate_around_question, not a live path.

VERIFY: (a) AST-compile both files with /home/polaris/pipeline-env/bin/python -m py_compile; (b) grep to confirm no remaining bare 'pathB_capture.' call and no 'pathB_runner.py' path literal; (c) confirm the new path file exists: src/polaris_graph/benchmark/benchmark_gate_runner.py.

CODEX-GATE (codex cannot read files here — feed it the diff inline): write the 'git diff' to /tmp/strag.diff, then run:
  cd /tmp && printf 'You are codex-sol. Gate this 2-line rename-straggler fix. It changes an undefined pathB_capture.* call to the already-imported benchmark_run_capture, and updates a stale pathB_runner.py path literal to the renamed benchmark_gate_runner.py. No logic change. Confirm behavior-neutral and correct. Emit STRAG-{SAFE|REVISE}.\\n\\nDIFF:\\n' > /tmp/strag_gate.md && cat /tmp/strag.diff >> /tmp/strag_gate.md && timeout 200 codex exec --skip-git-repo-check -c model_reasoning_effort=high - < /tmp/strag_gate.md 2>&1 | tail -15

COMMIT (only if codex STRAG-SAFE): stage ONLY the 2 fixed files explicitly, commit with trailer 'Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>' and 'Claude-Session: https://claude.ai/code/session_01TLpJSqNfJVSP1UGdtk89nA', then push: git push origin HEAD:refs/heads/chore/review-readiness-filerename. If push rejects (non-fast-forward due to concurrent activity), report that in notes and do NOT force.

Return the diff, verify result, codex verdict token, commit sha, whether pushed, and notes.`, { schema: STRAG_SCHEMA, phase: 'Stragglers', label: 'fix-stragglers' })

phase('AB-Test')
const ab = await agent(`Claude-codex workflow DELIVERABLE 2: attempt the champion-recipe A/B to EMPIRICALLY confirm the renames don't move the RACE score. This is PAID and BROWSER-dependent — be strict about cost and honesty.

CONTEXT: champion recipe = scripts/compose_agentic_report_s3gear329.py --corpus data/cp4_corpus_s3gear_329.json --rq-drb-task 72, env PG_OUTLINE_AGENT=1 + GLM 5.2 (all pinned in /workspace/POLARIS/.env), interpreter /home/polaris/pipeline-env/bin/python (torch cu128, drives the GPU). Reranker needs PG_CONTENT_RELEVANCE_SCORE_CHUNK=16 (byte-identical, avoids OOM). The composer does a LIVE agentic gap-fill that needs a working browser. On this box playwright chrome-headless-shell works via a userspace lib fix (LD_LIBRARY_PATH at /tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/browserlibs/LDPATH.txt) BUT the CRAWL4AI fetch backend fails with TargetClosedError -> composes produced no report.

STEP 1 — BROWSER: diagnose why CRAWL4AI's chromium fails (it may launch the FULL chromium, not chrome-headless-shell; run ldd on ~/.cache/ms-playwright/chromium-*/chrome-linux/chrome and check for still-missing libs; try adding them to the userspace lib dir like the existing fix, or set CRAWL4AI to headless/no-sandbox). Prove a fix by launching it and fetching one URL. Time-box this to a reasonable effort.

STEP 2 — GATE THE SPEND: only if STEP 1 makes the browser actually work, proceed. If the browser CANNOT be fixed, DO NOT run any paid compose. Set browser_fixed=false, ran_paid_ab=false, and write blocked_reason + the exact recipe for a working-browser box, and STOP (still run the codex gate on this blocked decision).

STEP 3 — A/B (only if browser works): run the champion recipe on TWO trees with IDENTICAL config, RACE-score both in the SAME batch (judge openai/gpt-5.5, task 72):
  - baseline: /home/polaris/wt/outline_agent (branch gate-inversion, pre-rename)
  - renamed: a clean detached worktree off chore/review-readiness-filerename
  Cap: ONE compose per tree (no retries beyond 1). Report baseline_score, renamed_score, delta, and total cost_usd. The rename is EXONERATED if |delta| <= 0.016 (judge variance).

STEP 4 — CODEX-GATE (feed inline, codex can't read files): summarize the outcome (browser fixed? scores? delta? or blocked+reason) into /tmp/ab_gate.md prefixed with 'You are codex-sol. Gate this A/B methodology and conclusion about whether the file renames moved the RACE score. Is the conclusion sound and honestly scoped? Emit AB-{SOUND|REVISE}.' then: cd /tmp && timeout 220 codex exec --skip-git-repo-check -c model_reasoning_effort=high - < /tmp/ab_gate.md 2>&1 | tail -20

Return all schema fields honestly. Do NOT fabricate scores — if no report was produced, scores are 'N/A' and ran_paid_ab=false.`, { schema: AB_SCHEMA, phase: 'AB-Test', label: 'ab-test' })

return { strag, ab }