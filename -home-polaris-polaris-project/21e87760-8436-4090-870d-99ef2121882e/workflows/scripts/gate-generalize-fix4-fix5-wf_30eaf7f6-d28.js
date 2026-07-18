export const meta = {
  name: 'gate-generalize-fix4-fix5',
  description: 'Kimi K3 + Fable 5 + Codex Sol independently design how to make Fix 4 (report shape) and Fix 5 (source-kind/quality eligibility) SMART and GENERAL — contract-driven, not journal/task-72 hardcoded — without breaking faithfulness or over-engineering. Opus consolidates into one plan.',
  phases: [
    { title: 'Pack', detail: 'assemble grounded context pack from the real contract/eligibility/report code at 78fe2ca' },
    { title: 'Investigate', detail: 'Fable + Codex Sol + Kimi K3 independently design the generalization' },
    { title: 'Consolidate', detail: 'Opus merges into a single minimal, faithfulness-safe, general plan + metamorphic tests' },
  ],
}
const REV = "/tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/generality"
const PACK = `${REV}/pack.md`

const QUESTION = `You are designing how to make TWO fixes in an open-weight deep-research pipeline SMART and GENERAL — driven by the compiled research CONTRACT, not hardcoded to the current benchmark task (task 72: an academic literature review that wants peer-reviewed English-language journal articles). The pipeline reads ANY prompt -> a typed ResearchContract (a lossless CLAUSE LEDGER with deontic strength + a deliverable_spec + allowed_source_kinds + scope). The SAME contract must correctly steer these two fixes for ARBITRARY prompts, e.g.: a decision memo that must cite news + company press releases; a policy brief that must cite government reports and primary sources; a market scan that wants industry analyst blogs; a systematic literature review that wants peer-reviewed journals; an open exploratory prompt with no stated source scope.

FIX 4 - REPORT SHAPE. Currently proposed as: emit an H1 title + a '## Introduction and Scope' framing section + thematic sections + demote machinery (methods/disclosure/ledgers) below a '## Appendix' boundary. That is ONE deliverable shape (a literature review). GENERALIZE it. The report skeleton (title style, framing section, section ordering, and WHAT counts as 'machinery' to demote) must derive from the contract's deliverable_spec (format / type / audience / tone). 
  (a) What does deliverable_spec actually carry today, and what is missing to drive a skeleton?
  (b) Propose the general model: a small closed set of deliverable ARCHETYPES (e.g. review / memo / brief / comparison / explainer), each with an ordered skeleton, default=review when unstated — versus a fully generative skeleton. State the trade-offs and pick one for THIS operator (who hates over-engineering).
  (c) How do you keep this RENDER-ONLY and faithfulness-safe: verified claim sentences stay byte-identical, provenance_generator.py stays 0-diff, nothing deleted (only re-ordered/relabeled)?
  (d) How do you keep the champion PG_GATE-OFF path BYTE-IDENTICAL?

FIX 5 - SOURCE-KIND + QUALITY ELIGIBILITY. Currently proposed with journal-LITERAL logic: 'journal-PASS before UNKNOWN fail-closed', 'journal-first ordering', 'journal-only = preference not starvation'. GENERALIZE it.
  (a) Source-kind preference / ordering / corpus-adequacy must key off contract.allowed_source_kinds (news, gov, press_release, blog, journal — WHATEVER the contract names). The prefer-vs-require STRENGTH should come from the clause ledger's deontic strength (a hard 'must only cite X' => require; a soft 'prefer X' => prefer). Design the exact mechanism and where it plugs into retrieval_projection / quality_eligibility.
  (b) UNKNOWN-credibility resolution must key off a GENERAL credibility TIER model, not the literal word 'journal'. DOI / peer-review is ONE T1 signal; official government / primary source is another; a reputable-outlet news wire is another tier. Define the tier model and how UNKNOWN resolves to PASS/DEMOTE by tier — such that 'journal => PASS' falls out as one instance, and a gov-report contract gets gov sources PASSing instead.
  (c) Invariants that must hold for EVERY prompt: never re-admit a strict_verify FAIL; never override a contract that EXCLUDES a kind ('do not cite blogs'); evidence-POSITIVE only (only promote, never newly fail); enforce a HARD source-kind scope only behind a corpus-ADEQUACY pre-check (enough in-scope sources exist) — else degrade to prefer + disclose. Show how each invariant is coded.
  (d) The metamorphic CROSS-PROMPT tests that PROVE adaptation: same code, swap the contract (journal / news+press / gov / blogs-allowed / exclude-blogs / open), assert each fix adapts and never hardcodes journal or review.

HARD CONSTRAINTS ('without fucking it up'): (1) Faithfulness is FROZEN — never touch provenance_generator.py / strict_verify / the drop rule / NLI / D8 thresholds; no new verification pass. (2) Enforce scope at RETRIEVAL, never by filtering a frozen corpus — filtering the 997-row unscoped corpus down to journals tanked RACE 0.4447->0.3264 (even Instruction-Following fell). (3) Prefer the MINIMAL change that generalizes; explicitly flag any over-engineering risk. (4) Coverage > Insight > Readability.

Deliverables: for EACH fix give exact file:function edits, the general data model, the faithfulness + OFF-path safety argument, the corpus-adequacy / disclosure fallback, and the metamorphic test list. Be blunt and specific; cite file:function from the pack. Do NOT rubber-stamp — find what a journal-hardcoded implementation would get WRONG on a non-journal prompt.`

phase('Pack')
const pack = await agent(`Assemble a GROUNDED context pack for an external-model design review, written to ${PACK}. Read from /home/polaris/wt/outline_agent at the STABLE baseline commit 78fe2ca (use \`git show 78fe2ca:<path>\` so the in-progress build on the working tree does not confuse you). Keep the pack UNDER 35,000 words total (hard cap — it feeds Codex which has a token-cost cliff at 272K tokens; stay well under). Include, each clearly delimited with '===== <label> =====':
1. The Fix 4 and Fix 5 sections VERBATIM from /home/polaris/polaris_project/GATE_FIX_PLAN_CONSOLIDATED.md (what is currently proposed).
2. The REAL contract data model: the ResearchContract / clause ledger / deliverable_spec / allowed_source_kinds / scope definitions and the deontic-strength enum. Find them (grep for 'deliverable_spec', 'allowed_source_kinds', 'ResearchContract', 'class .*Contract', 'deontic', clause_ledger.py, planning_gate_schema.py, retrieval_projection.py). Paste the actual class/field definitions and any to_dict.
3. quality_eligibility.py — the relevant functions (score_source_quality, the UNKNOWN fail-closed path, _PREDATORY_HOST_PATTERNS, the soft-demote path) — paste them.
4. The report-assembly seam in scripts/run_honest_sweep_r3.py around the appendix boundary (~:6325), the banner prepend (~:20783), and how the title/sections are currently emitted — paste the relevant spans (trim aggressively, keep signatures + the ordering logic).
5. key_findings.py — the bullet-emission + preamble spans (~:1004).
6. retrieval_projection.py around :314 (how allowed_source_kinds is projected into retrieval today).
7. A 6-line note on the two ABSOLUTE RULES (faithfulness frozen; enforce scope at retrieval not by filtering a frozen corpus) and the operator's over-engineering aversion.
Prefer signatures + the decision logic over full bodies; elide long unrelated code with '... [elided] ...'. After writing, print the word count and the section list.`, { label: 'pack', phase: 'Pack', effort: 'high' })

phase('Investigate')
const investigations = await parallel([
  // Fable 5 — native workflow agent
  () => agent(`You are FABLE 5, an independent senior architect. Read the context pack at ${PACK} IN FULL, then answer the design brief below. Ground every claim in file:function from the pack. Write your full design to ${REV}/fable.md and also return a tight summary (key decisions + the single biggest risk of a journal-hardcoded implementation).\n\n===== DESIGN BRIEF =====\n${QUESTION}`,
    { label: 'fable', phase: 'Investigate', model: 'fable', effort: 'high' }),
  // Codex Sol — GPT-5.6 via CLI
  () => agent(`You are the CODEX-SOL RUNNER. Invoke Codex (GPT-5.6) to independently produce the design, then capture its output.
Steps:
1. Read ${PACK} to confirm it exists and note its size.
2. Write the full prompt (the design brief below, PLUS an instruction to read ${PACK} for all code context) to ${REV}/codex_prompt.txt.
3. Run Codex with a 900s timeout, bypassing sandbox, capturing everything:
   \`cd /home/polaris/wt/outline_agent && timeout 900 codex exec --dangerously-bypass-approvals-and-sandbox "$(cat ${REV}/codex_prompt.txt)" > ${REV}/codex.md 2>${REV}/codex.err\`
4. If it times out or errors, report that honestly and include whatever partial output landed in codex.md. Do NOT fabricate a Codex answer.
5. Return a tight summary of what Codex actually said (or that it failed), plus the path ${REV}/codex.md.
Keep the codex input well under 272K tokens (the pack is <35k words; fine).\n\n===== DESIGN BRIEF (put this in codex_prompt.txt) =====\n${QUESTION}`,
    { label: 'codex-sol', phase: 'Investigate', effort: 'high' }),
  // Kimi K3 — via OpenRouter
  () => agent(`You are the KIMI-K3 RUNNER. Invoke Kimi K3 via OpenRouter to independently produce the design, then capture its output.
Steps:
1. Load the API key: \`export OPENROUTER_API_KEY=$(grep -E '^OPENROUTER_API_KEY=' /home/polaris/wt/outline_agent/.env | cut -d= -f2- | tr -d '"'"'"'"'"' ')\` (strip quotes/whitespace).
2. Read ${PACK}.
3. Write a python script to ${REV}/run_kimi.py modeled on the WORKING pattern at /tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/reviews/run_kimi_review.py — same OpenRouter call to model 'moonshotai/kimi-k3', max_tokens 48000, temperature 0.3, 900s timeout, retry/backoff loop, and CRITICALLY: capture msg.get('content') OR msg.get('reasoning') (Kimi is reasoning-first and often leaves content empty). System message: 'You are Kimi K3, an independent senior architect and skeptical cross-check. Do not rubber-stamp; find what a journal-hardcoded implementation gets WRONG.' User message = the full pack text + the design brief below. Write the answer to ${REV}/kimi.md.
4. Run it: \`python3 ${REV}/run_kimi.py\`. If empty/failed after retries, report honestly with the error; do NOT fabricate.
5. Return a tight summary of what Kimi actually said (or that it failed), plus the path ${REV}/kimi.md.\n\n===== DESIGN BRIEF =====\n${QUESTION}`,
    { label: 'kimi-k3', phase: 'Investigate', effort: 'high' }),
])

phase('Consolidate')
const consolidated = await agent(`You are OPUS, consolidating three INDEPENDENT external-model designs into ONE minimal, general, faithfulness-safe generalization plan for Fix 4 (report shape) and Fix 5 (source-kind/quality eligibility).
Read: the pack ${PACK}; ${REV}/fable.md; ${REV}/codex.md (may be partial/failed); ${REV}/kimi.md (may be partial/failed); and cross-check every proposed edit against the REAL code at /home/polaris/wt/outline_agent (git show 78fe2ca:<path>) so you do not repeat a claim that does not match the code. Note which models actually returned (some may have failed — say so; do not invent their views).

Your job: produce the SINGLE plan the operator will act on. For EACH of Fix 4 and Fix 5:
- The GENERAL data model (Fix 4: how deliverable_spec drives the skeleton — archetype set vs generative, your pick + why; Fix 5: source-kind preference driven by allowed_source_kinds + deontic strength, and the credibility-TIER UNKNOWN-resolution model where journal=>PASS is just one instance).
- EXACT file:function edits (verified against the code), minimal.
- The faithfulness-safety argument (provenance_generator.py 0-diff; verified sentences byte-identical; upstream of the frozen verifier) and the PG_GATE-OFF byte-identical argument.
- The corpus-adequacy + disclosure fallback (hard scope only when enough in-scope corpus exists; else prefer + disclose) — for ANY kind, not just journals.
- The metamorphic CROSS-PROMPT tests that prove adaptation (list them concretely: contracts to swap in, assertions).
- Where the three models DISAGREED and your adjudication; and an explicit OVER-ENGINEERING watch (what to NOT build).
Also flag anything in the CURRENT running build (the plan-faithful, journal-flavored Fix 4/5) that this generalization must REPLACE or REFACTOR, so the hardening pass knows what to unwind.
Write the full plan to /home/polaris/polaris_project/GATE_GENERALIZE_FIX45_PLAN.md and return the structured summary.`,
  { label: 'consolidate', phase: 'Consolidate', effort: 'high', schema: {
    type: 'object', additionalProperties: false,
    required: ['models_returned','fix4_model','fix5_model','fix4_edits','fix5_edits','metamorphic_tests','faithfulness_safe','over_engineering_watch','disagreements','plan_path','headline'],
    properties: {
      models_returned: { type: 'array', items: { type: 'string' }, description: 'which of fable/codex/kimi actually produced usable output' },
      fix4_model: { type: 'string', description: 'the chosen general model for report shape' },
      fix5_model: { type: 'string', description: 'the chosen general model for source-kind/quality eligibility' },
      fix4_edits: { type: 'array', items: { type: 'string' } },
      fix5_edits: { type: 'array', items: { type: 'string' } },
      metamorphic_tests: { type: 'array', items: { type: 'string' } },
      faithfulness_safe: { type: 'boolean' },
      over_engineering_watch: { type: 'array', items: { type: 'string' } },
      disagreements: { type: 'array', items: { type: 'string' } },
      plan_path: { type: 'string' },
      headline: { type: 'string' },
    },
  } })

return consolidated
