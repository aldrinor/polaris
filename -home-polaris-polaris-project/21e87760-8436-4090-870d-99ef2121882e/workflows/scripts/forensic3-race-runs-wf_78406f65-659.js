export const meta = {
  name: 'forensic3-race-runs',
  description: 'Sol + Fable + K3 independently forensically audit 4 task-72 reports (A gate/faith-off 0.399, B gate/faith-on 0.361, champ_ourcorpus 0.367, step3 best-champion 0.429) LINE BY LINE to explain the RACE gap; Opus consolidates.',
  phases: [
    { title: 'Audit', detail: 'Fable + Codex Sol + Kimi K3 independently audit the 4 scored texts line-by-line' },
    { title: 'Consolidate', detail: 'Opus merges into one forensic answer, line by line' },
  ],
}
const REV = "/tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/forensic3"
const PACK = `${REV}/pack.md`
const BRIEF = `You are forensically auditing FOUR task-72 deep-research literature-review reports to explain their RACE scores. The prompt: "a literature review on the restructuring impact of AI on the labor market." RACE dimension WEIGHTS: Insight 0.32, Comprehensiveness 0.29, Instruction-Following 0.25, Readability 0.14. The four SCORED texts (verbatim, as the GPT judge saw them) + the score table + verified confounds are ALL in the CONTEXT PACK. The judge's own reasoning was NOT saved — you must audit the TEXTS themselves.

Scores: A (our gate, faithfulness OFF) 0.3992 | B (our gate, faithfulness ON) 0.3610 | champ_ourcorpus (champion pipeline on OUR corpus) 0.3671 | step3_rescore_r2 (BEST available champion) 0.4291.

Do a LINE-BY-LINE forensic audit — QUOTE specific passages/sentences from the pack for every claim. Answer:

1. WHY does STEP3 (best champion, 0.429, 3372 words) beat A (our best, 0.399, 5201 words), dimension by dimension — especially Insight (0.414 vs 0.384) and Readability (0.426 vs 0.348)? Quote concrete differences: the TITLE, the OPENING paragraph, section structure, paragraph shape, how each SYNTHESIZES across sources vs lists facts, citation style, and CONCISENESS (step3 is 1830 words SHORTER yet scores higher). What specifically does step3 DO that A does not?

2. Is A>B (0.399 vs 0.361) actually the FAITHFULNESS GHOST, or the confounds (A and B had different corpora/contracts/length + both carry the D8 banner)? Read A and B line-by-line: what did B's faithfulness-ON verification visibly REMOVE, hedge, or gap-state that A kept? Is B thinner in insight/more hedged, or just a different draft? Is the 0.038 delta credibly the ghost, or noise? Be honest about attribution.

3. Our gate (A) BEATS champ_ourcorpus (0.399 vs 0.367) on the SAME corpus — what does our gate composition do RIGHT? And champ_ourcorpus (champion, 2563 words) scores far below step3 (champion, 3372 words) — is that a CORPUS-quality gap or a COMPOSITION gap?

4. THE CHROME DRAGS — quantify the plausible RACE cost of: (a) our title being the RAW PROMPT ("# Research report: Please write a literature review on...") vs champion's clean "# A literature review on..."; (b) the D8 "UNVERIFIED-by-D8" BANNER present in our scored text; (c) length bloat (5201/4549 vs 3372/2563). Would fixing just these plausibly close the gap to step3?

5. RANK the concrete fixes by RACE leverage (expected points per unit effort). Name the SINGLE highest-leverage change.

Be brutally specific; quote the text. This is forensics, not a summary. Find what a superficial reading would MISS.`

phase('Audit')
const audits = await parallel([
  () => agent(`You are FABLE 5, forensic auditor at MAX depth. Read the pack at ${PACK} IN FULL (all four scored texts), then do the line-by-line audit below. Quote specific passages. Write your full audit to ${REV}/fable.md and return a tight summary (your single highest-leverage finding + the honest verdict on whether A>B is the ghost).\n\n===== BRIEF =====\n${BRIEF}`,
    { label: 'fable', phase: 'Audit', model: 'fable', effort: 'high' }),
  () => agent(`You are the CODEX-SOL RUNNER. Get Codex (GPT-5.6) at reasoning-effort HIGH to produce the forensic audit, captured to a file.
1. Build ${REV}/combined_prompt.txt = "You are a forensic auditor at maximum depth. ALL four scored texts + scores + confounds are embedded below; quote them by passage. Do NOT read files.\\n\\n===== CONTEXT PACK =====\\n" + contents of ${PACK} + "\\n\\n===== BRIEF =====\\n" + the brief below.
2. Run: cd /home/polaris/wt/outline_agent && timeout 1500 codex exec --dangerously-bypass-approvals-and-sandbox -c model_reasoning_effort="high" - < ${REV}/combined_prompt.txt > ${REV}/codex.md 2> ${REV}/codex.err ; echo "EXIT $?"
3. If codex.md is empty/errored/timed out, report honestly with whatever landed; do NOT fabricate. Return a tight summary of what Codex actually said (or that it failed) + the path.\n\n===== BRIEF (put in combined_prompt.txt) =====\n${BRIEF}`,
    { label: 'codex-sol', phase: 'Audit', effort: 'high' }),
  () => agent(`You are the KIMI-K3 RUNNER. Get Kimi K3 (via OpenRouter) to produce the forensic audit, captured to a file.
1. Write ${REV}/run_kimi.py: read OPENROUTER_API_KEY from /home/polaris/wt/outline_agent/.env (regex ^OPENROUTER_API_KEY=(.+)$, strip quotes); read ${PACK}; POST to https://openrouter.ai/api/v1/chat/completions model "moonshotai/kimi-k3", max_tokens 60000, temperature 0.3, 1500s timeout, retry x5 backoff; system="You are Kimi K3, a forensic auditor at maximum depth; quote passages; find what a superficial reading misses"; user = pack text + the brief below; capture msg.get("content") OR msg.get("reasoning"); write to ${REV}/kimi.md.
2. Run python3 ${REV}/run_kimi.py . If empty/failed, report honestly; do NOT fabricate. Return a tight summary + path.\n\n===== BRIEF =====\n${BRIEF}`,
    { label: 'kimi-k3', phase: 'Audit', effort: 'high' }),
])

phase('Consolidate')
const verdict = await agent(`You are OPUS consolidating a 3-model forensic audit of 4 task-72 reports into ONE line-by-line answer for the operator. Read: the pack ${PACK}; ${REV}/fable.md; ${REV}/codex.md (may be partial/failed — say so honestly, attribute nothing false); ${REV}/kimi.md (same). Note which models actually returned.
Produce the operator's forensic answer:
1. THE VERDICT on A>B: is it the faithfulness ghost, or confounds? Give the honest, evidence-quoted answer (converge/diverge across models).
2. WHY step3 (0.429) beats our best A (0.399): the concrete, quoted differences (title, opening, structure, synthesis vs listing, conciseness, no-banner). Dimension by dimension.
3. WHY our gate A BEATS champ_ourcorpus (0.367) on the same corpus — what the gate does right.
4. THE CHROME DRAGS quantified: raw-prompt title, D8 banner, length bloat — and whether fixing them closes the gap.
5. RANKED fix list by RACE leverage + the SINGLE highest-leverage change.
6. Where the 3 models DISAGREED and your adjudication.
Quote specific passages throughout. Write the full consolidated audit to /home/polaris/polaris_project/FORENSIC3_AUDIT.md and return a structured summary.`,
  { label: 'consolidate', phase: 'Consolidate', effort: 'high', schema: {
    type:'object', additionalProperties:false,
    required:['models_returned','agtb_verdict','why_step3_beats_A','why_A_beats_champourcorpus','chrome_drags','ranked_fixes','single_highest_leverage','disagreements','plan_path','headline'],
    properties:{
      models_returned:{type:'array',items:{type:'string'}},
      agtb_verdict:{type:'string'}, why_step3_beats_A:{type:'string'}, why_A_beats_champourcorpus:{type:'string'},
      chrome_drags:{type:'string'}, ranked_fixes:{type:'array',items:{type:'string'}}, single_highest_leverage:{type:'string'},
      disagreements:{type:'array',items:{type:'string'}}, plan_path:{type:'string'}, headline:{type:'string'},
    },
  } })

return verdict
