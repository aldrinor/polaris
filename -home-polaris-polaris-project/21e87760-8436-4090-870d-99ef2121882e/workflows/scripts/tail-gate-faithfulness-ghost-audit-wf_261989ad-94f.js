export const meta = {
  name: 'tail-gate-faithfulness-ghost-audit',
  description: 'READ-ONLY audit: does the tail gate (strict_verify drop rule / NLI / D8 / key_findings refilter / render-seam) KILL high-RACE-value synthesis, insight, and analysis? Map every content-removing stage, quantify from real reports (champion vs gate run), model the Insight(0.32)+Comprehensiveness(0.29) impact, and surface faithfulness-SAFE levers. No code edits; verifier stays frozen.',
  phases: [
    { title: 'Map', detail: 'enumerate every content-removing tail stage; frozen vs adjustable' },
    { title: 'Evidence', detail: 'quantify actual drops in champion + gate reports; mechanism deep-dive' },
    { title: 'Verdict', detail: 'is the ghost real? which layer? RACE impact + SAFE levers' },
  ],
}
const GUARD = `
THIS IS A READ-ONLY AUDIT. Do NOT edit any code, config, or report. Do NOT modify the verifier. Repo: /home/polaris/wt/outline_agent (branch gate-inversion @ b67506a). Champion = bot/outline-agent-box @ df4118a.

FRAMING: The operator suspects the "tail gate" — everything AFTER section-compose that can DROP / REWRITE / REMOVE content on FAITHFULNESS grounds — is destroying high-value SYNTHESIS, INSIGHT, and ANALYSIS, which are the biggest RACE dimensions (Insight 0.32, Comprehensiveness 0.29, Instruction-Following 0.25, Readability 0.14). The classic tension: cross-source synthesis / interpretation / implications may lack a single-source span citation and thus fail per-sentence NLI grounding -> get DROPPED -> the report loses exactly the analysis that scores highest. That is the "faithfulness ghost."

CONSTRAINT: faithfulness is FROZEN — this audit must NOT propose editing provenance_generator.py / strict_verify / NLI / the drop rule / D8 thresholds. Its job is to (a) CHARACTERIZE and QUANTIFY what the tail drops and whether high-value insight is among it, and (b) find faithfulness-SAFE levers (upstream grounding, D8 rescue, ADJUSTABLE non-frozen layers, section routing) that preserve insight WITHOUT touching the verifier. BUT be brutally honest: if the FROZEN verifier itself is the culprit, SAY SO plainly and quantify the cost — the operator needs the truth to decide, even though we won't touch it without their explicit call.
`
phase('Map')
const map = await agent(`${GUARD}
MAP the entire tail gate. Enumerate EVERY stage from the end of section-compose through the final assembled report.md that can DROP, REMOVE, REWRITE, or SUPPRESS content. For EACH stage give: file:function:line; exactly WHAT it removes; the precise CRITERION (e.g. per-sentence NLI entailment threshold, span-grounding requirement, key-findings refilter, chrome/render-seam removal, D8 adjudication drop, drop_disclosure); whether it operates per-SENTENCE or per-block; and CLASSIFY it FROZEN (provenance_generator.py / strict_verify / NLI / D8 thresholds / drop rule) vs ADJUSTABLE (non-frozen render/compose/key_findings/depth layers). CRITICALLY, for each stage judge: can it drop SYNTHESIS / INTERPRETATION / CROSS-SOURCE / ANALYSIS sentences (multi-source or inferential claims) as opposed to only atomic single-source facts? Trace the strict_verify drop condition precisely — does a sentence need a single supporting span, and how are multi-source synthesis sentences handled (dropped? split? attributed to strongest source?). Also: does the D8 four-role adjudication ADD drops or RESCUE claims? Return a structured stage-by-stage table.`, { label: 'map', phase: 'Map', effort: 'high' })

phase('Evidence')
const evidence = await parallel([
  () => agent(`${GUARD}
EVIDENCE-A: the CHAMPION (RACE 0.4447). Locate the champion's scored report.md (search outputs/ for the champion run; or git show df4118a for its generator; or the scored artifact under third_party/DeepResearch-Bench results). Characterize its body: how much of it is SYNTHESIS/INSIGHT/ANALYSIS vs atomic cited facts? Does the champion tail DROP synthesis (look for its drop_disclosure / provenance / _drop_disclosure_md)? How many sentences did the champion verifier drop, and of what kind? The champion is the BAR — if it retains lots of insight, the tail is NOT inherently insight-killing and the gate run's problem is elsewhere; if the champion also drops heavily, the ghost is structural. Quantify. Return findings + representative dropped/kept examples.`, { label: 'ev-champion', phase: 'Evidence', effort: 'high' }),
  () => agent(`${GUARD}
EVIDENCE-B: the GATE RUN (RACE 0.3568). Analyze outputs/gate_e2e_final2/workforce/drb_72_ai_labor/ (draw1/report.md + any drop_disclosure / provenance / eligibility_receipts / manifest). Quantify: how many sentences/claims were DROPPED by the tail, and classify each drop as (i) atomic fact vs (ii) SYNTHESIS/INSIGHT/ANALYSIS. Pull 5-10 VERBATIM examples of dropped content and judge whether they were high-RACE-value insight. Compare the report's insight density to the champion's. Is the gate run's lower score explained by tail-dropped insight, or by other factors (corpus, report shape, the degenerate-contract keystone bug that plagued that specific run)? Be careful: that run had the KEYSTONE bug + no reranker — separate tail-drop effects from those confounds. Return quantified findings + verbatim examples.`, { label: 'ev-gaterun', phase: 'Evidence', effort: 'high' }),
  () => agent(`${GUARD}
EVIDENCE-C: MECHANISM. Deep-read the strict_verify drop rule + NLI grounding in provenance_generator.py and the key_findings refilter + depth_layer/synthesis handling + render-seam chrome removal. Answer precisely: (1) Does the drop rule require EVERY body sentence to be NLI-entailed by a single retrieved span? (2) How does it treat a synthesis sentence that integrates 2+ sources or draws an inference not verbatim in any one source — dropped, or attributed/kept? (3) Is there a mechanism that lets well-grounded analysis survive (e.g. attributing to the strongest supporting source, or a synthesis-specific path)? (4) Does the newly-wired D8 four-role adjudication RESCUE strict_verify drops or only add scrutiny? (5) Does key_findings refilter or the render chrome-removal chop insight bullets? Identify the SINGLE stage most responsible if insight is being killed, and whether it is FROZEN or ADJUSTABLE. Return a mechanism verdict with file:line citations.`, { label: 'ev-mechanism', phase: 'Evidence', effort: 'high' }),
])

phase('Verdict')
const verdict = await agent(`${GUARD}
SYNTHESIZE the audit into the operator's answer. Inputs — MAP: ${map} ; EVIDENCE: ${JSON.stringify(evidence)}.
Deliver:
1. GHOST VERDICT: Is the tail gate killing high-RACE-value synthesis/insight/analysis? YES/NO/PARTIAL, with the quantified basis (how many insight sentences dropped in the gate run vs champion; is it structural or run-specific).
2. THE CULPRIT LAYER: name the single stage most responsible (file:function), and whether it is FROZEN (verifier/NLI/D8/drop) or ADJUSTABLE. Be honest if it is the frozen verifier.
3. RACE IMPACT: model the cost to Insight(0.32)+Comprehensiveness(0.29) — roughly how many RACE points is the tail plausibly costing, if any.
4. FAITHFULNESS-SAFE LEVERS (ranked): concrete options that preserve insight WITHOUT touching the frozen verifier — e.g. (a) ground synthesis better at COMPOSE time so it passes NLI (the right fix); (b) use D8 adjudication to rescue; (c) adjust an ADJUSTABLE non-frozen layer (key_findings/depth/render); (d) route synthesis to a rendered section with proper attribution. For each: expected insight recovered, faithfulness risk, effort. Mark which are pure-safe vs which would require the operator to relax the frozen rule (flag those separately as "operator-decision-only, not recommended without sign-off").
5. BOTTOM LINE: is a latency-fixed re-run worth it as-is, or should a safe lever land first? One paragraph.
Return a structured verdict. Write the full audit to /home/polaris/polaris_project/TAIL_GATE_GHOST_AUDIT.md.`, { label: 'verdict', phase: 'Verdict', effort: 'high', schema: {
  type: 'object', additionalProperties: false,
  required: ['ghost_verdict','structural_or_runspecific','culprit_layer','culprit_is_frozen','insight_sentences_dropped_gaterun','champion_also_drops_insight','race_points_at_risk','safe_levers','requires_frozen_relax','rerun_worth_it_asis','headline'],
  properties: {
    ghost_verdict:{type:'string',enum:['YES','NO','PARTIAL']},
    structural_or_runspecific:{type:'string'},
    culprit_layer:{type:'string'},
    culprit_is_frozen:{type:'boolean'},
    insight_sentences_dropped_gaterun:{type:'string'},
    champion_also_drops_insight:{type:'boolean'},
    race_points_at_risk:{type:'string'},
    safe_levers:{type:'array',items:{type:'string'}},
    requires_frozen_relax:{type:'array',items:{type:'string'}},
    rerun_worth_it_asis:{type:'boolean'},
    headline:{type:'string'},
  },
} })

return verdict
