export const meta = {
  name: 'compose-contract-injection',
  description: 'Wire the compiled contract (deliverable kind/sections/voice/scope) INTO the compose section-writer + outline-agent LLM PROMPTS so the gate generates contract-shaped content natively (not post-hoc block-shuffle). Sol+Fable+K3 design -> Opus consolidate -> build -> verify (offline + metamorphic across deliverable kinds). Faithfulness FROZEN.',
  phases: [
    { title: 'Pack', detail: 'assemble grounded pack: compose/outline prompt plumbing + contract structure + the compose_projection=None gap' },
    { title: 'Design', detail: 'Fable + Codex Sol + Kimi K3 independently design the prompt-injection wiring' },
    { title: 'Consolidate', detail: 'Opus merges into one minimal, faithfulness-safe, general plan + metamorphic tests' },
    { title: 'Build', detail: 'carry kind/sections/voice + thread compose_projection into section-writer + outline prompts' },
    { title: 'Verify', detail: 'offline + metamorphic across deliverable kinds + faithfulness 0-diff + OFF byte-identical' },
    { title: 'Commit', detail: 'commit local on gate-inversion' },
  ],
}
const REV = "/tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/compose_inject"
const PACK = `${REV}/pack.md`
const BRIEF = `You are designing how to make an open-weight deep-research "smart gate" ACTUALLY STEER COMPOSITION. The compiled research CONTRACT (a typed ResearchContract: deliverable spec = kind/format/length, required sections, voice/tone, and scope constraints) currently reaches RETRIEVAL (the "keystone" fix works — contract_sha256 drives scoping), but it NEVER reaches GENERATION. Prep found: the section generator is called with compose_projection=None (multi_section_generator.py); the deliverable allowlist at research_planning_gate.py:490-492 DROPS deliverable.kind (admits only format/length/tone); contract.sections is left empty (required_section_count=0); and report_skeleton.py only REARRANGES already-written blocks AFTER generation (post-hoc block-shuffle), which is cosmetic, not smart. So for ANY prompt the LLM composes blind to the deliverable kind/sections/voice, then blocks get shuffled.

DESIGN THE FIX: wire the contract INTO the compose (section-writer) AND outline-agent LLM PROMPTS so the model GENERATES contract-shaped content natively (correct deliverable kind, the required section plan, the requested voice/tone, scope emphasis) — for ARBITRARY prompts (systematic literature review / decision memo / policy brief / comparison / explainer / market scan), NOT hardcoded to task-72's review.

Answer, grounded in file:function from the PACK:
1. CONTRACT CARRY: what must the contract carry to drive composition (deliverable.kind/document_type, ordered required sections, voice/tone, scope emphasis), and the minimal change to stop dropping it (the research_planning_gate.py:490 allowlist + the fallback constructor that leaves sections empty). Keep it lossless/general.
2. COMPOSE PROJECTION: design the compose_projection object and WHERE it is built + threaded into multi_section_generator's section-writer PROMPT. What exactly goes into the prompt (deliverable-kind framing, the section's role in the plan, voice/tone directive, scope constraints) and how — additive prompt preamble vs restructuring. Show the injection point (file:function) and keep it a prompt-preamble, not a rewrite of the generation contract that would break verification.
3. OUTLINE-AGENT PROMPT: how the same contract shapes the outline agent's plan/gap-search prompt so the outline itself is contract-shaped (right sections for the deliverable kind).
4. report_skeleton BECOMES A SAFETY-NET: once generation is contract-shaped, report_skeleton is a light fallback (default archetype only when the contract is silent), not the primary shaper. Confirm no conflict.
5. FAITHFULNESS-SAFE: this is UPSTREAM of the frozen verifier — the injected prompt guidance must NOT inject claims/citations or relax grounding; verified sentences stay byte-identical output of strict_verify; provenance_generator.py 0-diff. Explain why prompt-steering the STRUCTURE/VOICE cannot corrupt faithfulness.
6. OFF-PATH byte-identical: gate OFF (or contract silent) => the champion generation prompt is byte-identical (compose_projection=None path unchanged).
7. METAMORPHIC TESTS: swap the contract deliverable kind (review/systematic_review/memo/brief/comparison/explainer) and assert the compose_projection + injected prompt preamble ADAPT (memo => BLUF/decision voice + memo sections; brief => exec-summary; review => thematic + Introduction and Scope), and that gate-OFF is byte-identical, and no journal/review LITERAL in control flow (data-driven).

HARD CONSTRAINTS: faithfulness FROZEN (never touch provenance_generator.py / strict_verify / NLI / drop rule / D8); enforce via PROMPT + structure only, upstream; MINIMAL change, flag over-engineering; general across deliverable kinds; Coverage > Insight > Readability. Be blunt and specific; find what a task-72-hardcoded implementation gets WRONG on a memo/brief prompt.`

const GUARD = `
AUTHORITATIVE once written: ${REV}/CONSOLIDATED.md. Repo /home/polaris/wt/outline_agent, branch gate-inversion @ b67506a. NEVER touch /home/polaris/wt/flywheel.
FAITHFULNESS FROZEN: never modify provenance_generator.py / strict_verify / NLI / D8 thresholds / drop rule; no new verification pass/test. The compose-contract injection is UPSTREAM prompt-steering only — it shapes STRUCTURE/VOICE/SCOPE in the generation prompt, never injects claims or citations, never relaxes grounding. Verify 0-diff on the verifier at the end.
OFF byte-identical: gate OFF or contract-silent => compose_projection=None path and the champion generation prompt stay byte-for-byte identical. New behavior behind default-safe gating.
General across deliverable kinds; no journal/review literal in control flow (data registries only). Minimal; no over-engineering. Offline only — no live retrieval/compose.
`
phase('Pack')
const pack = await agent(`Assemble a GROUNDED context pack for an external-model design review, written to ${PACK}. Read the REAL code at /home/polaris/wt/outline_agent @ b67506a (working tree is fine). UNDER 35,000 words (feeds Codex — stay well under). Delimit sections with '===== <label> ====='. Include:
1. The problem statement: the contract reaches retrieval but NOT compose (compose_projection=None); allowlist drops deliverable.kind; sections empty; report_skeleton is post-hoc. (2-3 sentences.)
2. The CONTRACT structure: ResearchContract / deliverable / ContractTerm / sections / voice/tone fields + the deontic/force enum (planning_gate_schema.py). Paste the class/field defs + to_dict.
3. research_planning_gate.py:~490-519 — the deliverable allowlist (what it admits/drops) + the fallback constructor that leaves contract.sections empty. Paste verbatim.
4. multi_section_generator.py — the section-writer entry that receives compose_projection (grep 'compose_projection'), the section-writer PROMPT construction (the function that builds the LLM prompt for a section), and the strict_verify call sites (require_number_match). Paste signatures + the prompt-assembly spans (trim long unrelated code).
5. The OUTLINE-AGENT prompt construction (find the outline agent / gap-search prompt builder). Paste the prompt-assembly.
6. report_skeleton.py — resolve_archetype + how it's applied post-generation (run_honest_sweep_r3.py ~:17600). Paste the key logic.
7. A 5-line note: faithfulness frozen (provenance_generator.py untouchable); enforce via prompt/structure upstream; OFF byte-identical; general across deliverable kinds.
Prefer signatures + decision logic over full bodies; elide with '... [elided] ...'. After writing, print word count + section list.`, { label: 'pack', phase: 'Pack', effort: 'high' })

phase('Design')
const designs = await parallel([
  () => agent(`You are FABLE 5, independent senior architect. Read ${PACK} IN FULL, then answer the brief. Ground every claim in file:function from the pack. Write your full design to ${REV}/fable.md and return a tight summary (key wiring decisions + the biggest risk of a task-72-hardcoded implementation on a memo/brief prompt).\n\n===== BRIEF =====\n${BRIEF}`,
    { label: 'fable', phase: 'Design', model: 'fable', effort: 'high' }),
  () => agent(`You are the CODEX-SOL RUNNER. Produce Codex (GPT-5.6)'s independent design, captured to a file. Steps:
1. Build ${REV}/combined_prompt.txt = "You are an independent senior architect. ALL code context is embedded below; do NOT read files, cite file:function from it.\\n\\n===== CONTEXT PACK =====\\n" + contents of ${PACK} + "\\n\\n===== DESIGN BRIEF =====\\n" + the brief below.
2. Run: cd /home/polaris/wt/outline_agent && timeout 1500 codex exec --dangerously-bypass-approvals-and-sandbox -c model_reasoning_effort="high" - < ${REV}/combined_prompt.txt > ${REV}/codex.md 2> ${REV}/codex.err ; echo "EXIT $?"
3. If codex.md is empty or it errored/timed out, report honestly with whatever is in codex.md/codex.err; do NOT fabricate. Return a tight summary of what Codex actually said (or that it failed) + the path.\n\n===== DESIGN BRIEF (put in combined_prompt.txt) =====\n${BRIEF}`,
    { label: 'codex-sol', phase: 'Design', effort: 'high' }),
  () => agent(`You are the KIMI-K3 RUNNER. Produce Kimi K3's independent design via OpenRouter, captured to a file. Steps:
1. Write ${REV}/run_kimi.py modeled on the WORKING pattern: read OPENROUTER_API_KEY from /home/polaris/wt/outline_agent/.env (regex ^OPENROUTER_API_KEY=(.+)$, strip quotes); read ${PACK}; POST to https://openrouter.ai/api/v1/chat/completions model "moonshotai/kimi-k3", max_tokens 60000, temperature 0.3, 1500s timeout, retry/backoff x5; system="You are Kimi K3, independent senior architect and skeptical cross-check; find what a task-72-hardcoded compose-injection gets WRONG on a memo/brief"; user = pack text + the brief below; CRITICALLY capture msg.get("content") OR msg.get("reasoning"); write answer to ${REV}/kimi.md.
2. Run: python3 ${REV}/run_kimi.py . If empty/failed after retries, report honestly; do NOT fabricate. Return a tight summary + the path.\n\n===== DESIGN BRIEF =====\n${BRIEF}`,
    { label: 'kimi-k3', phase: 'Design', effort: 'high' }),
])

phase('Consolidate')
const consolidated = await agent(`You are OPUS consolidating the compose-contract-injection design. Read: ${PACK}; ${REV}/fable.md; ${REV}/codex.md (may be partial/failed — say so, attribute nothing false); ${REV}/kimi.md (same). Cross-check EVERY proposed edit against the REAL code at /home/polaris/wt/outline_agent @ b67506a. Note which models actually returned.
Produce ONE minimal, general, faithfulness-safe plan for wiring the contract into the compose + outline-agent PROMPTS: (a) the contract-carry change (unblock deliverable.kind allowlist + populate sections + voice, minimal, lossless); (b) the compose_projection object + exact injection point into the section-writer prompt (file:function) as an ADDITIVE prompt-preamble; (c) the outline-agent prompt injection; (d) report_skeleton demoted to safety-net; (e) faithfulness-safety argument (upstream, no claims/citations injected, provenance_generator.py 0-diff) + OFF byte-identical argument; (f) the metamorphic cross-deliverable-kind tests + anti-hardcode grep. Flag disagreements + your adjudication + an over-engineering watch. Write the full plan to ${REV}/CONSOLIDATED.md AND /home/polaris/polaris_project/COMPOSE_INJECTION_PLAN.md. Return a structured summary.`,
  { label: 'consolidate', phase: 'Consolidate', effort: 'high', schema: {
    type:'object', additionalProperties:false,
    required:['models_returned','carry_change','compose_projection_injection','outline_injection','faithfulness_safe','off_byte_identical','metamorphic_tests','over_engineering_watch','plan_path','headline'],
    properties:{
      models_returned:{type:'array',items:{type:'string'}},
      carry_change:{type:'string'}, compose_projection_injection:{type:'string'}, outline_injection:{type:'string'},
      faithfulness_safe:{type:'boolean'}, off_byte_identical:{type:'boolean'},
      metamorphic_tests:{type:'array',items:{type:'string'}}, over_engineering_watch:{type:'array',items:{type:'string'}},
      plan_path:{type:'string'}, headline:{type:'string'},
    },
  } })

phase('Build')
const build = await agent(`${GUARD}
IMPLEMENT the compose-contract injection per ${REV}/CONSOLIDATED.md on branch gate-inversion (build on b67506a). Do exactly what the plan specifies: (1) carry deliverable.kind + required sections + voice/tone in the contract (unblock the research_planning_gate.py:490 allowlist + populate contract.sections in the fallback constructor — minimal, general, lossless); (2) build the compose_projection and thread it into multi_section_generator's section-writer PROMPT as an ADDITIVE preamble (deliverable-kind framing + this section's role in the plan + voice/tone directive + scope emphasis) — do NOT inject claims/citations, do NOT alter the strict_verify contract; (3) inject the contract into the outline-agent prompt so the plan is contract-shaped; (4) leave report_skeleton as the safety-net (default archetype only when contract silent). Everything behind default-safe gating so gate-OFF / contract-silent => compose_projection=None path byte-identical. provenance_generator.py 0-diff. Byte-compile all modules. Report edits (file:line).
Consolidated summary:\n${JSON.stringify(consolidated)}`, { label:'build', phase:'Build', effort:'high' })

phase('Verify')
const verdict = await agent(`${GUARD}
FINAL VERIFY (offline; NO live retrieval) on gate-inversion. Return the structured verdict. Confirm:
1. provenance_generator.py 0-diff vs b67506a AND champion df4118a; strict_verify/NLI/D8/drop untouched; flywheel untouched.
2. Compose contract is NO LONGER degenerate: a compiled contract with deliverable.kind + sections + voice now produces a non-empty compose_projection that reaches multi_section_generator's section-writer prompt (trace it); the deliverable.kind is carried (allowlist unblocked) and contract.sections populated.
3. The injected prompt preamble is ADDITIVE structure/voice/scope only — no claims, no citations, no grounding relaxation.
4. OFF / contract-silent byte-identical: gate OFF or empty deliverable => compose_projection=None + champion generation prompt byte-for-byte identical (golden test).
5. METAMORPHIC across deliverable kinds pass: review/systematic_review/memo/brief/comparison/explainer each produce an adapted compose_projection + injected preamble (memo=BLUF/decision, brief=exec-summary, review=thematic); anti-hardcode grep (no journal/review literal in control flow) passes.
6. Full offline suite pass count (name pre-existing failures separately).`, { label:'verify', phase:'Verify', effort:'high', schema:{
    type:'object', additionalProperties:false,
    required:['faithfulness_0diff','compose_contract_nondegenerate','projection_reaches_prompt','preamble_additive_only','off_byte_identical','metamorphic_pass','metamorphic_fail','anti_hardcode_pass','suite_passed','suite_failed_new','suite_failed_preexisting','all_verified','summary','risks'],
    properties:{
      faithfulness_0diff:{type:'boolean'}, compose_contract_nondegenerate:{type:'boolean'}, projection_reaches_prompt:{type:'boolean'},
      preamble_additive_only:{type:'boolean'}, off_byte_identical:{type:'boolean'},
      metamorphic_pass:{type:'integer'}, metamorphic_fail:{type:'integer'}, anti_hardcode_pass:{type:'boolean'},
      suite_passed:{type:'integer'}, suite_failed_new:{type:'integer'}, suite_failed_preexisting:{type:'integer'},
      all_verified:{type:'boolean'}, summary:{type:'string'}, risks:{type:'array',items:{type:'string'}},
    },
  } })

phase('Commit')
const commit = await agent(`${GUARD}
COMMIT (local only, do NOT push) IFF verify.all_verified is true (value: ${verdict && verdict.all_verified}). If true: on gate-inversion clean __pycache__, git add -A, commit describing the compose-contract injection (contract now steers the section-writer + outline-agent prompts; deliverable kind/sections/voice carried; report_skeleton demoted to safety-net; faithfulness 0-diff; metamorphic across deliverable kinds). Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>. If false, do NOT commit — report the blocker. Return commit hash + clean status, or blocker.`, { label:'commit', phase:'Commit' })

return { branch:'gate-inversion', base:'b67506a', consolidated_headline: consolidated && consolidated.headline, verdict, commit:(commit||'').slice(0,200) }
