export const meta = {
  name: 'verify-fix-safety',
  description: 'Independently verify the compose fix design: are the 50 killed verdicts worth saving, what anti-fabrication guards are sacred, and the orphan-fragment bug cause',
  phases: [
    { title: 'Characterize' },
    { title: 'Synthesize' },
  ],
}

const WT = '/home/polaris/wt/flywheel'

phase('Characterize')

const tasks = [
  {
    label: 'killed-verdicts-worth-saving',
    prompt: `READ-ONLY investigation. cd ${WT}. Do NOT edit any file.
CONTEXT: A deep-research composer dropped 212 sentences during its last render (outputs/drafts/drops.json). 50 of them were 'OWNED_VERDICT_UNCLASSIFIABLE' — cross-source synthesis verdicts (comparisons between two studies) that the synthesis classifier rejected with the reason "the sentence makes no recognised verdict, so no proof can be checked against it." I.e. glm wrote 50 genuine cross-source comparison sentences and they were killed ONLY because they don't map to a named verdict template (SAME_OUTCOME_DIFFERENT_UNIT / CONTRASTS_LEVEL / RECONCILES / etc.).
QUESTION: Are these 50 worth saving (real synthesis wrongly killed by template-rigidity) or are they genuinely vague junk (correctly killed)?
HOW: (1) Read scripts/synthesis_contract.py to understand EXACTLY what makes a verdict 'classifiable' vs 'UNCLASSIFIABLE' — find where OWNED_VERDICT_UNCLASSIFIABLE is raised and the criteria. (2) Read outputs/drafts/glm_reasoning.log (large; grep for the subsection-writing reasoning blocks containing '**COMPARISON' and the owned-verdict prose glm produced) to sample the ACTUAL synthesis sentences glm wrote. (3) Judge: are glm's cross-source verdicts substantive (two real studies, a stated relation, useful for a literature review's insight) or empty? 
DELIVER: a verdict (WORTH_SAVING / MOSTLY_JUNK / MIXED with %), 5-8 concrete example sentences with your classification of each, and the single criterion in synthesis_contract.py that is over-strict (if any).`,
  },
  {
    label: 'sacred-guard-boundary',
    prompt: `READ-ONLY investigation. cd ${WT}. Do NOT edit any file.
CONTEXT: We will RELAX the synthesis classifier to admit more cross-source verdicts, but we MUST NOT weaken attribution/anti-fabrication faithfulness. Your job is to draw the exact safety boundary.
HOW: Read scripts/synthesis_contract.py, scripts/report_ast.py, scripts/argument_planner.py, scripts/publisher.py. Enumerate EVERY guard/check that enforces ATTRIBUTION or ANTI-FABRICATION faithfulness (correct source per claim; no number/unit that isn't in the source span; no smuggled new finding; premises must be already-admitted cards). For each: file:line, what it rejects, and WHY it is load-bearing.
Specifically classify these drop reasons as SACRED (keep) vs GHOST (relaxable): JUDGE_NOT_ENTAILED, NUMBER_OR_UNIT_NOT_IN_SPAN, SOURCE_NAMED_IN_CLAUSE_TEXT, UNPROVED_RIDER_CLAUSE, OWNED_VERDICT_UNCLASSIFIABLE, OWNED_NAMES_A_SOURCE, OWNED_ATTRIBUTES_A_FINDING, SYNTHESIS_REFUSED:premises_share_a_single_source, SYNTHESIS_SMUGGLES_A_FINDING, OWNED_ASSERTS_UNLICENSED_FINDING, SYNTHESIS_REFUSED:new_entity.
Also: find scripts/synthesis_contract.py's --self-test (it must stay GREEN: 9 invalid/0 false admissions, 5 valid/0 false rejections) and describe what the 9 invalid cases are — these define what a safe relaxation must STILL reject.
DELIVER: the SACRED list (must-not-touch, with file:line), the GHOST list (safe-to-relax), and the exact invariant a new 'fallback verdict type' must preserve so the 9 invalid self-test cases stay rejected.`,
  },
  {
    label: 'orphan-fragment-cause',
    prompt: `READ-ONLY investigation. cd ${WT}. Do NOT edit any file.
CONTEXT: Publish failed with: publisher.RefusedToPublish: THE RELEASED FILE WOULD CONTAIN A SENTENCE NO NODE PRODUCED: 'Writing in the Cureus Journal of Business and Economics.' This is an orphan citation-preamble fragment. The guard (scripts/publisher.py ~line 185-192) hashes node-produced sentences into a sidecar, re-splits the rendered markdown with _sentences(), and refuses if a rendered sentence's hash isn't in the sidecar.
QUESTION: Which is the cause — (a) a node/renderer actually EMITS the bare fragment 'Writing in the <Journal>.' as standalone prose, or (b) _sentences() OVER-SPLITS a full sentence like 'Writing in the Cureus Journal of Business and Economics, X found Y.' at the period after 'Economics.' orphaning the first half?
HOW: Read scripts/publisher.py _sentences() and the sidecar-hashing path (are the SAME splitter/normalization used on both the sidecar side and the publish-check side?). Find where Attributed citation nodes render their 'Writing in the <Journal>' text (grep report_ast.py / cellcog_composer.py / argument_planner.py for 'Writing in' and journal/venue rendering). Grep outputs/drafts/glm_reasoning.log for 'Cureus' to see the intended full sentence.
DELIVER: confirmed cause (a) or (b) with file:line evidence, and the exact minimal fix (WITHOUT weakening the anti-fabrication guard) — e.g. protect journal-name/abbrev periods in the splitter, or make the node not emit a claimless fragment, or ensure sidecar and publish-check use identical segmentation.`,
  },
]

const findings = await parallel(tasks.map(t => () =>
  agent(t.prompt, { label: t.label, phase: 'Characterize' })
))

phase('Synthesize')

const SPEC = {
  type: 'object',
  additionalProperties: false,
  required: ['relax_verdict', 'sacred_keep', 'ghost_relax', 'bug1_cause', 'bug1_fix', 'safety_invariant', 'go_no_go'],
  properties: {
    relax_verdict: { type: 'string', description: 'Are the 50 killed verdicts worth saving? WORTH_SAVING / MOSTLY_JUNK / MIXED, with brief justification' },
    sacred_keep: { type: 'array', items: { type: 'string' }, description: 'Guards that MUST NOT be weakened (file:line + one line each)' },
    ghost_relax: { type: 'array', items: { type: 'string' }, description: 'Drop reasons safe to relax (with the target file:line)' },
    bug1_cause: { type: 'string', description: 'orphan fragment: cause (a) node emits fragment / (b) splitter over-splits — with evidence' },
    bug1_fix: { type: 'string', description: 'exact minimal fix for the orphan fragment bug' },
    safety_invariant: { type: 'string', description: 'the invariant a fallback verdict type must preserve so the 9 self-test invalid cases stay rejected' },
    go_no_go: { type: 'string', description: 'GO if relaxation is safe and worthwhile, NO-GO otherwise, with the one deciding reason' },
  },
}

const spec = await agent(
  `You are consolidating an independent SAFETY verification of a planned fix to a deep-research composer. Three read-only investigations were run; their findings follow. Produce the consolidated go/no-go spec. Be conservative on safety: if relaxing the synthesis classifier could admit ANY fabrication (a smuggled finding, a number not in span, a wrong source), that is NO-GO for that path. The prize is admitting real cross-source synthesis (insight); the hard constraint is zero false admissions.

=== FINDING 1: are the 50 killed verdicts worth saving ===
${findings[0] || '(failed)'}

=== FINDING 2: sacred vs ghost guard boundary ===
${findings[1] || '(failed)'}

=== FINDING 3: orphan-fragment bug cause ===
${findings[2] || '(failed)'}`,
  { label: 'consolidate-spec', phase: 'Synthesize', schema: SPEC, effort: 'high' }
)

return spec
