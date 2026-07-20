export const meta = {
  name: 'faith-fully-off',
  description: 'Make the faithfulness engine + checker TRULY off on the raw-A path (clean default-off master switch), codex-sol(max) verified FAITH-TRULY-OFF',
  phases: [{ title: 'DisableAndVerify' }],
}

const SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['approach','faithfulness_off_how','checker_off_how','byte_identical_when_unset','codex_token','codex_reasoning','iterations','not_covered'],
  properties: {
    approach: { type: 'string' },
    faithfulness_off_how: { type: 'string', description: 'exactly what config/flag/switch makes strict_verify drop NOTHING, with file:line of every drop path it neutralizes' },
    checker_off_how: { type: 'string', description: 'evidence the external evaluator/checker does not run on the raw-A compose path' },
    byte_identical_when_unset: { type: 'string', description: 'proof the switch is default-off so unset = current behavior (other pipelines/bots untouched)' },
    codex_token: { type: 'string', description: 'FAITH-TRULY-OFF or FAITH-STILL-ON on convergence' },
    codex_reasoning: { type: 'string' },
    iterations: { type: 'number' },
    not_covered: { type: 'string' },
  },
}

const TREE = '/home/polaris/wt/faithoff'

phase('DisableAndVerify')
const result = await agent(`You are a Claude implementer under the govkit spawn contract: ONE shot, trace the WHOLE path, evidence (file:line) or it does not count, gaps in not_covered. Tree: ${TREE} (branch bot/faith-off-scoretest, off gate-inversion). Do NOT commit — return the result; the caller commits and runs the score.

GOAL — make the faithfulness engine TRULY off for the raw-A pipeline (scripts/run_raw_a.sh -> compose_agentic_report_s3gear329.py -> generate_multi_section_report), and confirm the CHECKER is off. Currently only entailment is off (PG_STRICT_VERIFY_ENTAILMENT=off in run_raw_a.sh), but strict_verify still DROPS sentences via other layers.

STEP 1 — map EVERY drop path in verify_sentence_provenance (src/polaris_graph/generator/provenance_generator.py) + strict_verify (src/polaris_graph/clinical_generator/strict_verify.py). From the ghost audit these include: entailment_failed (already off), percent_not_in_cited_span, no_integer_overlap_any_cited_span, number_not_in_any_cited_span, binding_qualifier_dropped, no_content_word_overlap, no_provenance_token. Name each with file:line and what makes it drop/mark a sentence unverified.

STEP 2 — implement a CLEAN master kill-switch so the raw-A run drops NOTHING: add PG_STRICT_VERIFY_OFF (read via resolve, default off/0). When set truthy, verify_sentence_provenance returns every sentence as VERIFIED with no drop (short-circuit at the top, before any layer runs), so 100% of composed sentences survive. DEFAULT-OFF => when unset it is BYTE-IDENTICAL to today (other pipelines + concurrent bots on gate-inversion are untouched). Do NOT weaken any layer's logic — only add the top-level bypass gated by the new flag. Keep the compose faithfulness tripwire (_audit_citations) behavior sane (with nothing dropped, there should be no leaked [CITE:] tokens because nothing is unverified — confirm).

STEP 3 — wire scripts/run_raw_a.sh: add PG_STRICT_VERIFY_OFF=1 (alongside the existing PG_STRICT_VERIFY_ENTAILMENT=off) and a header note that faithfulness is FULLY OFF for this scoring experiment. Confirm the CHECKER (external_evaluator) already does NOT run on the raw-A compose path (compose imports it only for a sentence-boundary helper) — cite it.

VERIFY: py_compile the changed modules; AST-parse; show (grep/trace) that with PG_STRICT_VERIFY_OFF=1 the bypass short-circuits BEFORE every drop path; show the flag is default-off (unset => original path). State exact evidence.

CODEX GATE (codex-sol MAX, reads files itself; do NOT let it read CLAUDE.md/campaign docs — tell it so): write summary + hunks to /tmp/codex_faithoff.md prefixed: 'You are codex-sol. cwd is a git worktree. Do NOT read CLAUDE.md, state/, or any campaign/plan file. INDEPENDENTLY confirm on the raw-A path with PG_STRICT_VERIFY_OFF=1: (1) verify_sentence_provenance drops NO sentence (bypass short-circuits before every drop path — entailment, span, numeric, qualifier, provenance-token); (2) the external evaluator/checker does not run; (3) with the flag UNSET the behavior is byte-identical to before (default-off). Cite file:line. Emit FAITH-TRULY-OFF or FAITH-STILL-ON (+what still drops).' then run: cd ${TREE} && timeout 900 codex exec --dangerously-bypass-approvals-and-sandbox -c model_reasoning_effort=max - < /tmp/codex_faithoff.md 2>&1 | tail -40
If FAITH-STILL-ON, fix the missed path and re-gate, up to 3 loops until FAITH-TRULY-OFF.

Return the schema. Do NOT commit, do NOT run a paid compose.`, { schema: SCHEMA, phase: 'DisableAndVerify', label: 'faith-off' })

return { result }