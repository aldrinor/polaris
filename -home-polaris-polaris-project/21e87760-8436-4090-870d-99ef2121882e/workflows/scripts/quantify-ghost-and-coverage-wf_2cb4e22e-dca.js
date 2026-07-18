export const meta = {
  name: 'quantify-ghost-and-coverage',
  description: 'Empirically classify the attribution drops (over-literal ghost vs legitimate anti-fabrication) and diagnose why 103 papers are unused',
  phases: [
    { title: 'Sample' },
    { title: 'Synthesize' },
  ],
}
const WT = '/home/polaris/wt/flywheel'

phase('Sample')

const tasks = [
  {
    label: 'classify-entailment-drops',
    prompt: `READ-ONLY. cd ${WT}. Do NOT edit files or disturb the running compose.
A deep-research composer dropped ~80 sentences with reason JUDGE_NOT_ENTAILED (the entailment judge rejected the claim vs its attached source span). Classify a SAMPLE of them (aim >=15) into:
 (1) GHOST/over-literal: the span genuinely supports the claim's MEANING but the judge rejected a paraphrase/wording gap or a too-narrow span — the source DOES support it (recoverable insight);
 (2) LEGITIMATE: the claim adds a number/entity/scope/sign the span lacks, or wrong source — correctly killed (must stay killed).
HOW: outputs/drafts/drops.json lists the drops (each entry: 'section :: reason :: truncated-sentence'). The FULL claim-vs-span pairs are in outputs/drafts/glm_reasoning.log — grep the entailment-judge reasoning blocks: they quote SPAN: "..." and CLAIM: "..." and end with an ENTAILED / NOT_ENTAILED verdict plus the judge's reasoning. Match the NOT_ENTAILED ones to the drops and read WHY the judge said no.
DELIVER: the count you sampled, the split (N ghost / N legitimate / %), and 6+ concrete examples each showing SPAN excerpt + CLAIM + your class + one-line why. Be honest — if most are legitimate anti-fabrication, say so.`,
  },
  {
    label: 'classify-number-drops',
    prompt: `READ-ONLY. cd ${WT}. Do NOT edit files.
Same composer dropped ~19 sentences with NUMBER_OR_UNIT_NOT_IN_SPAN / NUMBER_NOT_IN_SPAN (a number or unit in the claim isn't present in the source span) and ~19 with SOURCE_NAMED_IN_CLAUSE_TEXT, ~6 UNPROVED_RIDER_CLAUSE. Classify a sample into GHOST (over-literal — e.g. the span says 'roughly a third' and the claim says '34%', or the unit is phrased differently but present in substance) vs LEGITIMATE (a number the source truly never states — fabrication; or a real source-naming leak).
HOW: read outputs/drafts/drops.json for these reasons, and cross-reference outputs/drafts/glm_reasoning.log for the SPAN/CLAIM text. The number check logic is scripts/report_ast.py:1295-1301 — read it to understand exactly what it compares (digit/unit presence in span).
DELIVER: split (N ghost / N legitimate / %) with 5+ concrete examples (span number vs claim number) and whether the number-guard is too literal (rejecting '34%' when span says 'about a third') or correctly strict.`,
  },
  {
    label: 'diagnose-unused-papers',
    prompt: `READ-ONLY. cd ${WT}. Do NOT edit files.
The curated compose input outputs/compose_inputs/task72_cards_curated.json has 838 cards across 285 papers (works, identified by the 'manif:HASH' prefix of card ids). Only 182 papers (64%) appear in the model's reasoning (outputs/drafts/glm_reasoning.log). ~103 papers are UNUSED. Diagnose WHY.
HOW: (1) Compute the set of 285 work-hashes in the curated json and the set of work-hashes appearing in glm_reasoning.log; the difference is the ~103 unused. (2) For a sample of unused papers, determine why they didn't appear: were all their cards dropped by the faithfulness gate (check drops.json), filtered by a source-eligibility/tier firewall pre-compose (read scripts/cellcog_composer.py source-policy/selection logic), capped by per-work redundancy limits, or simply not selected by the generator? (3) Are the unused papers LOW-VALUE (off-topic, weak) or GOOD papers being needlessly excluded?
DELIVER: the real reason(s) the 103 are unused (with file:line for any filter), whether they are recoverable GOOD sources, and whether raising coverage toward ~90% is safe and worthwhile for the comprehensiveness score.`,
  },
]

const found = await parallel(tasks.map(t => () => agent(t.prompt, { label: t.label, phase: 'Sample' })))

phase('Synthesize')

const SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['entailment_split', 'number_split', 'ghost_material', 'unused_papers_reason', 'coverage_worthwhile', 'recommendation'],
  properties: {
    entailment_split: { type: 'string', description: 'JUDGE_NOT_ENTAILED: % ghost/over-literal vs % legitimate, with the sampled N' },
    number_split: { type: 'string', description: 'NUMBER drops: % ghost vs % legitimate, sampled N' },
    ghost_material: { type: 'string', description: 'Is the over-literal ghost MATERIAL (worth a calibration) or minor? one-line verdict' },
    unused_papers_reason: { type: 'string', description: 'why the ~103 papers are unused (root cause + file:line)' },
    coverage_worthwhile: { type: 'string', description: 'is raising coverage toward 90% safe AND worthwhile? verdict + risk' },
    recommendation: { type: 'string', description: 'ranked: which lever (ghost-calibration vs coverage-expansion) is the bigger, safer score gain, and whether to act now or after A/B scores' },
  },
}

return await agent(
  `Consolidate an empirical study of a deep-research composer's dropped sentences and unused sources. Three read-only investigations follow. Produce the data verdict. Be conservative: recommend relaxing a gate ONLY if the evidence shows it is over-literal AND a calibration can keep every fabrication rejected.

=== ENTAILMENT DROPS ===
${found[0] || '(failed)'}

=== NUMBER/SOURCE DROPS ===
${found[1] || '(failed)'}

=== UNUSED PAPERS ===
${found[2] || '(failed)'}`,
  { label: 'data-verdict', phase: 'Synthesize', schema: SCHEMA, effort: 'high' }
)
