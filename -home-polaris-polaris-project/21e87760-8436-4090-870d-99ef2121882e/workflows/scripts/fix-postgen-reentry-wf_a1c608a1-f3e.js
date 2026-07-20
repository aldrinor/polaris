export const meta = {
  name: 'fix-postgen-reentry',
  description: 'Wire the generation-draft checkpoint as a real resume re-entry point (skip regen, still re-run verification), codex-sol(max) gated until CHECKPOINT-FIX-SOUND',
  phases: [{ title: 'Fix' }],
}

const SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['files_changed','diff','verify','faithfulness_preserved','codex_token','codex_reasoning','iterations','not_covered'],
  properties: {
    files_changed: { type: 'string' },
    diff: { type: 'string', description: 'the git diff of the fix' },
    verify: { type: 'string', description: 'py_compile / ast / targeted check results' },
    faithfulness_preserved: { type: 'string', description: 'evidence (file:line) that verification/strict_verify STILL re-runs on the reused drafts — the §-1.3 invariant' },
    codex_token: { type: 'string', description: 'CHECKPOINT-FIX-SOUND on convergence, else the last token' },
    codex_reasoning: { type: 'string' },
    iterations: { type: 'number' },
    not_covered: { type: 'string', description: 'anything not done / risks left' },
  },
}

const TREE = '/home/polaris/wt/gateinv'

phase('Fix')
const result = await agent(`You are a Claude implementer under the govkit spawn contract: ONE shot, trace the WHOLE data path (not the one spot), evidence (real file:line quotes) or it does not count, and put anything you could not cover in not_covered. Tree: ${TREE} (branch gate-inversion). Do NOT commit — return the diff; the caller commits.

TASK — fix the ONE genuine checkpoint gap codex found (CHECKPOINT-NEEDS-FIX): the section-generation drafts are saved to postgen_checkpoint.json but the load is used ONLY for observability, so a resume re-does the whole (expensive, ~\$2.79) report generation instead of reusing the saved drafts.

PRECISE STATE (verify each against the code before changing anything):
- postgen_checkpoint.json is WRITTEN around scripts/run_honest_sweep_r3.py:16172.
- It is LOADED around scripts/run_honest_sweep_r3.py:9506 / 7081 but only surfaced (observability), NOT used as a re-entry point.
- A reuse path exists but is inert in production: PG_RESUME_REUSE_POSTGEN (~15893 / ~8984) and save_generation_snapshot is NEVER called in the production sweep; Gate-B leaves the flag OFF (run_gate_b.py:~1417).

THE ABSOLUTE CONSTRAINT (§-1.3 no-verdict-replay): a resume must RE-RUN every faithfulness gate and can NEVER replay a stored verdict. So the fix MUST reuse the GENERATED DRAFTS (skip regeneration) while strict_verify / verification / the judge STILL run fresh on those reused drafts. Reusing a stored VERDICT is forbidden; reusing a draft and re-verifying it is allowed. Confirm this distinction in fetch_snapshot.py / corpus_snapshot.py / outline_checkpoint.py comments before you rely on it.

DO: wire the postgen draft checkpoint to actually re-enter on --resume — reuse the saved section drafts, skip the regeneration LLM calls, and fall through to the UNCHANGED verification path so every faithfulness gate re-runs. Prefer enabling/using the EXISTING reuse machinery (save_generation_snapshot + the PG_RESUME_REUSE_POSTGEN load path) over inventing a new one. Keep it safe: if the saved drafts are absent/corrupt, fall back to full regeneration (fail-open). Do not change what verification does.

VERIFY: py_compile scripts/run_honest_sweep_r3.py and any module you touch; AST-parse; grep to show the reuse path is now reachable from the --resume path and that strict_verify still runs after it. State exactly how you confirmed faithfulness_preserved.

CODEX GATE (codex-sol, MAX reasoning, reads files itself): write your change summary + the key hunks to /tmp/codex_postgen.md prefixed: 'You are codex-sol. cwd is a git worktree. INDEPENDENTLY read the changed lines in scripts/run_honest_sweep_r3.py (and any helper) and confirm: (1) on --resume the saved generation drafts are REUSED and regeneration is skipped; (2) strict_verify / the faithfulness gates STILL re-run on the reused drafts (no stored verdict is replayed — §-1.3 preserved); (3) fail-open if drafts missing; (4) valid syntax. Cite file:line. Emit CHECKPOINT-FIX-SOUND or CHECKPOINT-FIX-REVISE + the exact fix if REVISE.' then run: cd ${TREE} && timeout 900 codex exec --dangerously-bypass-approvals-and-sandbox -c model_reasoning_effort=max - < /tmp/codex_postgen.md 2>&1 | tail -40
If codex says REVISE, apply its exact fix and re-gate. Loop up to 3 times until CHECKPOINT-FIX-SOUND (or return the last token honestly if it will not converge).

Return the schema. diff = the actual 'git -C ${TREE} diff' output. Do NOT commit.`, { schema: SCHEMA, phase: 'Fix', label: 'fix-postgen' })

return { result }