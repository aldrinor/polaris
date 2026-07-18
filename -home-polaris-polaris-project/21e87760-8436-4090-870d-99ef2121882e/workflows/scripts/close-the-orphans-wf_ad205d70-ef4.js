export const meta = {
  name: 'close-the-orphans',
  description: "Wire the 4 orphaned modules (fact_use_ledger, recency, insight_value, weighting) + build the missing cohesion pass — then an adversary proves each is on the critical path by ABLATION",
  phases: [
    { title: 'Wire', detail: 'composer orphans (fact_use_ledger + cohesion) and acquisition orphans (recency, insight_value, weighting) — different files, parallel' },
    { title: 'Ablate', detail: 'adversary: remove each module, prove the output CHANGES — orphan = not on the path' },
  ],
}

const ROOT = '/home/polaris/wt/flywheel'

const LAW = `
=== THE LAW ===
ATTRIBUTED sentences must be entailed by their source's VERBATIM SPAN; OWNED sentences name no source and
carry no new particular. \`${ROOT}/scripts/test_gate_is_wired.py\` must stay GREEN — NEVER weaken a check.
The composer writes DRAFTS; only publisher.publish() writes outputs/release/ (0555). The model emits CARD
IDs and never types a journal name.

=== THE DISEASE WE ARE CURING, AND IT IS THE ONE THAT HAS COST US EVERY TURN ===
A module that self-tests GREEN and is CALLED BY NOBODY is worthless and actively dangerous — it
manufactures confidence. provenance.py passed 18/18 while the P0 it was written to stop ran live on disk.
The canary went 16/16 while six adversary attacks succeeded ("it certified a lane the fabrication no
longer used"). So: BEING BUILT IS NOT BEING DONE. A module is done when REMOVING IT CHANGES THE OUTPUT.

=== GENERALITY IS THE GOAL, NOT TASK 72 ===
The mission is a system that beats SOTA on ANY question. A fix that only works for AI-and-the-labour-market
is overfitting wearing a win's clothes. Every mechanism must behave correctly on a CLINICAL question, a
LEGAL question, and a THIN-EVIDENCE question (where "the literature does not settle this" is the CORRECT
answer). Domain changes must be DATA edits (a registry row), never CODE edits. No hardcoded topic regex.
`

const STATE = `
=== VERIFIED STATE (audited on disk) ===
PLAN 3: 10/12 done. ORPHAN: fact_use_ledger. UNDONE: the cohesion pass.
PLAN 4: 3/6 wired.  ORPHAN: recency, insight_value, weighting.
MEASUREMENT: the A0/A6/A7 ladder has NEVER RUN. No real score since the rebuild.

Another wheel is LIVE right now building Sol's full-text acquisition lane (it owns: provenance.py,
version_align.py, alignment_census.py, source_router.py, acquisition.py, deep_fetch.py, event_ledger.py,
config/source_routes.yaml, and new routes_*.py). DO NOT TOUCH THOSE FILES. Coordinate by staying out.

Cards: outputs/evidence_cards_bound.json (232 bound, 10 works). Do NOT re-mine (paid).
`

phase('Wire')

const wired = await parallel([
  () => agent(`${LAW}\n${STATE}

YOU OWN cellcog_composer.py. No other agent in this wheel touches it.

TASK A — WIRE fact_use_ledger.py (ORPHAN: built, 1,089 lines, called by nobody).
MEASURED: 222 card slots drawn from 82 cards; one finding narrated EIGHT times; 41 exact repetitions;
~1,500-2,000 words of pure restatement. It keys finding identity on sha1(VERBATIM SPAN), explicitly NOT on
the model-written claim — "identity keyed on model prose is identity the model can forge by rewording."
Wire it so a finding is NARRATED IN FULL ONCE and may be re-used only in a NEW ANALYTICAL ROLE (comparison
/ boundary / method / implication); otherwise the writer must make an OWNED BACKWARD REFERENCE without
restating the fact. Corroborating sources stay in the basket — the ledger governs RHETORICAL reuse, never
evidence retention. Sol explicitly REJECTED hard "one card, one section" partitioning: it would STARVE the
theory and synthesis sections.

TASK B — BUILD THE COHESION PASS (Sol plan 3 item 7). This is UNDONE and it targets S2 Paragraph Cohesion
= 4.90, OUR LOWEST CRITERION. The judge: "fragmented narrative... without adequate transitions."
** DO NOT let a model rewrite the report. ATTRIBUTED CLAUSES ARE FROZEN BYTE-FOR-BYTE. **
The pass may ONLY: add/revise OWNED topic sentences; add OWNED transitions; reorder already-admitted
paragraph objects WITHIN their section; delete redundant OWNED sentences; repair grammar WITHOUT touching
a factual clause. Give it the previous paragraph's summary, the current paragraph's role, and the next
paragraph's role. Transitions must express ANALYTICAL MOVEMENT (level, method, horizon, sector) — never
"Turning now to...". Sol: "a free-form sequential rewrite is NOT safe to stack; the immutability of
attributed objects IS the safety boundary."

Run the canary after every change (must stay green). Prove BOTH are on the critical path — an AST call
check AND a behavioural difference. Do NOT commit. Report file:line + what you RAN.`,
    { label: 'wire fact_use_ledger + cohesion', phase: 'Wire' }),

  () => agent(`${LAW}\n${STATE}

YOU OWN the acquisition-side orphans. Do NOT touch cellcog_composer.py, provenance.py, acquisition.py,
event_ledger.py, source_router.py or config/source_routes.yaml (other wheels own those).

Three modules are BUILT and CALLED BY NOBODY. Wire each into the pipeline that should be using it:

 1. recency.py — THE OPERATOR'S OWN INSIGHT ("just search by date"), and Sol's mechanism for why it is
    right: "backward citation expansion SYSTEMATICALLY MISSES RECENT WORK — recent papers have not
    accumulated references or citations." OUR CORPUS ENDS IN 2023 and the entire generative-AI turn
    (2023-2025) is missing. Two lanes: FOUNDATION (no recency penalty for age) and FRONTIER (explicit
    date windows, SORTED BY DATE, never by citations). Windows live in a RECENCY PROFILE (data), not code.
    Wire it so the candidate pipeline actually USES the frontier lane. Worth +0.006 to +0.015.

 2. insight_value.py — Sol: the acquisition objective is MARGINAL INSIGHT READINESS, not a count.
    "A FIFTH POSITIVE ESTIMATE in the same context usually adds less insight than THE FIRST CREDIBLE NULL,
    a different population, or a design that resolves a disagreement." Wire the marginal-value vector so
    candidate SELECTION actually ranks by it (new-cell coverage + complete tuple + independent
    corroboration + method/population contrast + null/counterevidence + frontier + explains-a-contradiction
    - same-study redundancy). ** This is what unstarves the argument planner: it found ZERO genuine
    cross-source conflicts in our 10 papers. Actively prioritise CONTRASTS AND NULLS. **

 3. weighting.py — 10-dimension field-normalized quality, replacing raw citation count (which "returns
    ResNet and SMOTE — famous, not relevant"). Wire it so candidate PRIORITISATION uses the vector, never
    a bare scalar, and 'high_quality' is never a bare label (it must render as its components with
    provenance).

GENERALITY: all three must behave correctly on clinical / legal / thin questions. A legal question has no
effect sizes — nothing may demand a number. Domain changes are DATA rows.

Prove each is ON THE CRITICAL PATH (not just importable): show the call site AND that removing it changes
the ranking/candidate order. Canary green. Do NOT commit. Report file:line + what you RAN.`,
    { label: 'wire recency + insight_value + weighting', phase: 'Wire' }),
])

phase('Ablate')

const ablate = await agent(`${LAW}\n${STATE}

Two agents just wired the orphans:
${wired.filter(Boolean).map((r, i) => `--- ${i + 1} ---\n${String(r).slice(0, 1100)}`).join('\n\n')}

YOU ARE THE ADVERSARY. You did not build this. THE ONLY QUESTION THAT MATTERS: is each module ACTUALLY ON
THE CRITICAL PATH, or has it merely been imported so the builder could claim it was wired?

We have been fooled by this FOUR TIMES tonight. provenance.py passed 18/18 while the P0 it was built to
stop ran live on disk. So DO NOT accept an import, a call site, or a self-test as proof.

RUN AN ABLATION FOR EACH of the five: fact_use_ledger, the cohesion pass, recency, insight_value, weighting.
   For each: monkeypatch/disable the module, re-run the relevant path, and show that the OUTPUT DIFFERS.
   If output is IDENTICAL with the module removed, IT IS NOT ON THE PATH — say so loudly, name file:line.
   (The argument planner passed this test honestly: "planner ON: 219 bundles -> 16 verdicts placed;
    planner OFF: 0 bundles -> 0 placed." That is the standard. Meet it or fail it.)

THEN attack the two NEW behaviours:
 * COHESION PASS: can it MUTATE an attributed clause? Feed it a draft and try to make it alter a NUMBER or
   move a clause to a different source. Attributed clauses must be FROZEN BYTE-FOR-BYTE. Try to break that.
 * FACT-USE LEDGER: does it STARVE the synthesis section (Sol's explicit warning about hard partitioning)?
   Check the Critical Synthesis section still gets its evidence.
 * Does an OWNED transition smuggle in a NEW PARTICULAR (a number, a named entity)? Feed one; it must be
   refused.
 * GENERALITY: does anything now demand a NUMBER, which would silently discard a legal/doctrinal source?

Finally: \`python scripts/test_gate_is_wired.py\` must be GREEN, and \`git diff\` on the verifier files must
show NOTHING deleted or loosened. If a check was weakened to pass, that is the WORST outcome — say so.

Report ONLY what you executed. Quote real output. A finding that a module is still an orphan is worth more
than a clean report.`,
  { label: 'adversary: ablate all five', phase: 'Ablate' })

return { wired: wired.filter(Boolean).length, ablate }
