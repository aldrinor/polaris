export const meta = {
  name: 'bank-and-prove-faithfulness',
  description: 'A: clean up the banked 0.4447 RACE win (remove the refuted STEP-3 lever, keep control path). C: prove the real win on DeepTRACE/faithfulness — score POLARIS, honestly characterize whether competitors can even be audited.',
  phases: [
    { title: 'Bank cleanup', detail: 'remove refuted STEP-3 lever code + its 8 tests; verify control path unchanged' },
    { title: 'DeepTRACE', detail: 'score POLARIS 0.4447 report on the 8 faithfulness metrics; assess competitor auditability' },
    { title: 'Verdict', detail: 'Fable: honest faithfulness-axis standing vs competitors', model: 'fable' },
  ],
}

const CTX = `
CONTEXT. POLARIS just banked a HONEST RACE result: 0.4447 overall (Comp 0.457, Insight 0.429,
Instruction 0.459, Readability 0.431), faithfulness PASS, general, reproduced. It beats claude-3-7-sonnet
(0.4218) but is ~0.035 below the ~0.48 frontier — and closing that gap requires RACE length-tuning the
operator FORBADE. So we bank RACE and now prove the axis where POLARIS is structurally SUPERIOR:
DeepTRACE (citation faithfulness — does every cited claim actually get supported by its source).

Worktree: /home/polaris/wt/outline_agent (branch bot/outline-agent-box, HEAD d8547a2, clean).
POLARIS report to score: outputs/step3_control/report.md (the 0.4447 report) and its packed form
third_party/deep_research_bench/data/test_data/raw_data/polaris_step3_control.jsonl.
DeepTRACE tooling: /workspace/POLARIS/scripts/dr_benchmark/deeptrace_scorer.py,
deeptrace_judge_preflight.py, config/benchmark/deeptrace_judge_lock.yaml (signed, judge kimi-k2.6,
self_rescore policy). Competitors: /workspace/POLARIS/competitors/*.md (ChatGPT/Gemini scoped+unscoped).
Source the key: set -a; . /workspace/POLARIS/.env; set +a (never print it).

HONESTY (non-negotiable): report REAL measured DeepTRACE numbers. A KNOWN prior finding: competitor
reports may NOT be scoreable on DeepTRACE because they lack parseable [N] citations + fetched source
content (ChatGPT uses opaque UI tokens, Gemini bare URLs). If that holds, that is itself the finding —
POLARIS is claim-by-claim AUDITABLE and verified; the competitors are largely UN-AUDITABLE. Do NOT
fake a head-to-head number. Never tune the judge. If we can only score ourselves, say so and frame it
honestly (auditability gap), not as a fabricated win.
`

const BANK_SCHEMA = {
  type: 'object', required: ['removed', 'tests_pass', 'control_unchanged'],
  properties: {
    removed: { type: 'array', items: { type: 'string' }, description: 'the refuted STEP-3 lever code sites removed' },
    tests_pass: { type: 'string', description: 'outline suite result after removal (expect ~90/90)' },
    control_unchanged: { type: 'boolean', description: 'is the compose control (0.4447) path byte-identical after removal' },
    commit: { type: 'string' },
    notes: { type: 'string' },
  },
}
const DT_SCHEMA = {
  type: 'object', required: ['polaris_scored', 'polaris_metrics', 'competitors_scoreable'],
  properties: {
    preflight_pass: { type: 'boolean' },
    polaris_scored: { type: 'boolean' },
    polaris_metrics: { type: 'string', description: 'the 8 DeepTRACE metrics for the POLARIS 0.4447 report, REAL numbers' },
    competitors_scoreable: { enum: ['yes', 'no', 'partial'], description: 'can the competitor .md reports be scored on DeepTRACE at all' },
    competitor_finding: { type: 'string', description: 'if not scoreable, WHY (citation structure absent) — the auditability gap, with counts' },
    head_to_head: { type: 'string', description: 'real comparison if possible, or honest statement that competitors are un-auditable' },
    cost_note: { type: 'string' },
  },
}

phase('Bank cleanup')
const bank = await agent(
  `${CTX}\n\nA — BANK CLEANUP. Remove the REFUTED STEP-3 quant-directive lever (commit 31f488e), which
measured WORSE on RACE (-0.04) and was already decided-dropped. In
src/polaris_graph/generator/multi_section_generator.py remove: _SYNTH_QUANT_ENV +
_synthesis_quant_directive_enabled (~lines 912-924), _SYNTHESIS_QUANT_BLOCK (~line 981), and the
enrichment/injection call sites; plus the 8 synthesis-insight tests
(tests/polaris_graph/outline/test_synthesis_insight_directive.py). NOTE: a plain git revert conflicts
with d8547a2's hygiene edit — delete by hand. Then run the outline test suite (expect ~90/90 after the
8 lever tests are gone) and confirm the compose CONTROL path (directive OFF = the 0.4447 path) is
byte-identical / behavior-unchanged. Commit with an honest rationale. Do NOT touch the topic-driven
structure win (1cf3308) — that is the deliverable.`,
  { label: 'faith:bank-cleanup', phase: 'Bank cleanup', schema: BANK_SCHEMA },
)

phase('DeepTRACE')
const dt = await agent(
  `${CTX}\n\nC — PROVE THE FAITHFULNESS WIN. After cleanup:\n${JSON.stringify(bank, null, 2)}
1. Source the key, run deeptrace_judge_preflight.py --check — confirm PASS (it hard-blocked before only
   for a missing key).
2. Score the POLARIS 0.4447 report (outputs/step3_control/report.md, packed polaris_step3_control.jsonl)
   on the 8 DeepTRACE metrics with the signed kimi-k2.6 judge. Report the REAL numbers (one-sided,
   overconfident, relevant-statements, uncited-sources, unsupported-statements, source-necessity,
   citation-accuracy, citation-thoroughness). Watch cost — one report is ~178 support calls; if 429,
   say so and stop.
3. Assess whether the 4 competitor reports (competitors/*.md) can be scored on DeepTRACE at all — parse
   their citation structure (bibliography, [N] markers, fetched sources). If they can't (opaque tokens /
   bare URLs / no fetched source content), that is THE finding: POLARIS is claim-by-claim auditable +
   verified; competitors are un-auditable. Give counts. Do NOT fabricate competitor numbers.`,
  { label: 'faith:deeptrace-score', phase: 'DeepTRACE', schema: DT_SCHEMA },
)

phase('Verdict')
const verdict = await agent(
  `${CTX}\n\nYOU ARE FABLE. Give the honest verdict on the FAITHFULNESS axis.
CLEANUP: ${JSON.stringify(bank, null, 2)}
DEEPTRACE: ${JSON.stringify(dt, null, 2)}
Answer bluntly: (1) What are POLARIS's real DeepTRACE faithfulness numbers, and are they strong
(auditable, high citation-accuracy/thoroughness, low unsupported)? (2) Can we make a genuine head-to-head
claim vs ChatGPT/Gemini on faithfulness, or are they un-auditable — and if un-auditable, is THAT the
honest moat (POLARIS can be verified claim-by-claim; frontier products cannot)? (3) The honest one-line
positioning: on RACE we're competitive-but-length-capped at 0.44; on faithfulness we are ___. (4) Is
the 'we beat everyone on the axis that matters' claim TRUE and defensible, or is it an incomparable we
should state as such? Do not flatter — the operator wants the truth, not a trophy.`,
  { label: 'faith:fable-verdict', phase: 'Verdict', model: 'fable', effort: 'high' },
)

log(`FAITHFULNESS: polaris scored=${dt?.polaris_scored} | competitors scoreable=${dt?.competitors_scoreable}`)
return { bank, dt, verdict }
