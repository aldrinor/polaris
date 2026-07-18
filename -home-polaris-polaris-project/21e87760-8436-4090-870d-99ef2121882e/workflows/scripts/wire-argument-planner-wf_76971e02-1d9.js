export const meta = {
  name: 'wire-argument-planner',
  description: "Wire the argument planner (Sol's +0.0259 lever) into the composer, then an INDEPENDENT adversary tries to break it — the builder does not verify itself",
  phases: [
    { title: 'Wire', detail: 'one agent owns the composer: wire argument_planner + fact_use_ledger + derived outline onto the critical path' },
    { title: 'Attack', detail: 'a SEPARATE adversary attacks the wiring — canary green + boundary held + the planner actually on the path' },
  ],
}

const ROOT = '/home/polaris/wt/flywheel'

const LAW = `
=== THE LAW (violating it burns the artifact regardless of score) ===
Every sentence is ATTRIBUTED (names a source -> MUST be entailed by THAT source's VERBATIM SPAN) or
OWNED (reviewer's voice -> names no source, carries NO new particular, MAY be non-entailed — that is
what INSIGHT IS). THE VERBATIM SPAN IS THE ONLY EVIDENCE; the model-written \`claim\` is a display cache
and nothing is validated against it.

\`${ROOT}/scripts/test_gate_is_wired.py\` must stay GREEN (currently 25/25). NEVER weaken a check to make
it pass — that is the exact failure that let fabrication ship four times tonight. Run it after every change.

=== TONIGHT'S ONE LESSON ===
THE BUILDER CANNOT VERIFY ITSELF. Four times a module self-tested green while fabrication shipped; the
provenance module passed 18/18 while the P0 ran live on disk; the canary went 16/16 while 6 attacks
succeeded ("it certified a lane the fabrication no longer used"). So this wheel SEPARATES the builder
from the verifier: one agent wires, a DIFFERENT agent attacks.
`

const DEFECT = `
=== THE DEFECT — Sol's #1 lever, +0.0259 in score units ===
${ROOT}/scripts/cellcog_composer.py generates ~28 subsections INDEPENDENTLY in a ThreadPoolExecutor
(around :479-524). NOBODY EVER DECIDES WHAT IS COMPARED WITH WHAT, so the report LISTS findings instead
of ADJUDICATING them. "Critical Synthesis" (w=0.0800, the joint-heaviest criterion in the rubric) scores
6.36 vs the leader's 9.60. bodhi beats us by 0.08 with a SEVENTEENTH of our sources — because it argues
and we enumerate. This is worth more than any corpus change.

=== WHAT EXISTS — WIRE IT, DO NOT REBUILD IT ===
${ROOT}/scripts/argument_planner.py (1,657 lines, 42 functions) is BUILT, TESTED, and imported by NOBODY.
It builds COMPARISON BUNDLES before prose: keys cards by (technology × outcome × industry × unit × method
× horizon × direction), finds the bundles that MATTER (same outcome + different unit = "only look
contradictory"; same unit + opposite direction = genuine conflict; a finding with no counterpart = a
boundary), and assigns each subsection a PLAN (claim-first thesis, ≥2 attributed clauses bound BY card_id,
the exact comparison, methodological comparability, an OWNED verdict, a boundary, a bridge).
${ROOT}/scripts/fact_use_ledger.py is also built + unwired — stops the same finding being narrated 8×.

THE COMPOSER WAS REBUILT TONIGHT: it writes DRAFTS and calls publisher.publish(); the model emits CARD
IDs and NEVER types a journal name; attribution is rendered by report_ast. Do NOT reintroduce surname
inference. Do NOT add a write to outputs/release/ (it is 0555; only publisher writes there).

CARDS: ${ROOT}/outputs/evidence_cards_bound.json — 232 bound, honest, post-quarantine. Do NOT re-mine (paid).
`

phase('Wire')

const wired = await agent(`${LAW}\n${DEFECT}

YOU OWN cellcog_composer.py. You are the ONLY agent editing it. Work carefully and sequentially; run the
canary after every change.

READ FIRST, in order: cellcog_composer.py (the NEW post-rebuild structure), argument_planner.py (its API
and what it returns), report_ast.py (the ATTRIBUTED/OWNED node types the composer emits), research_contract.py
(it has derive_outline that the composer currently IGNORES for a hardcoded OUTLINE at :305).

THEN WIRE:
 1. Before writing subsections, the composer builds COMPARISON BUNDLES from the bound cards and hands each
    subsection its PLAN (thesis, the specific card_ids to compare, the comparison being made, the owned
    verdict slot, the boundary, the bridge). The writer FILLS the plan instead of freelancing 28 isolated
    pieces. Voice stays STRUCTURAL: attributed clauses carry card_ids, owned sentences carry premise_ids.
 2. The dedicated Critical Synthesis section must hold SEVERAL named cross-source syntheses spanning
    industries/methods — not a few residual paragraphs. That is the +0.0259.
 3. Wire fact_use_ledger too IF it fits cleanly; if it fights the new structure, report that and leave it.
 4. If the hardcoded OUTLINE should become research_contract.derive_outline() for generality, do it — but
    keep task 72 working.

DO NOT break the publish boundary. DO NOT weaken the gate. VERIFY BY RUNNING: the planner's bundle-building
is deterministic over the cards, so test it OFFLINE without a big paid compose; run test_gate_is_wired.py
(must stay green). Do NOT commit.

Report: exact call sites you changed, the comparison bundles the planner ACTUALLY found in the real 232
cards (quote them), whether fact_use_ledger went in, canary status, and anything unverified or unfinished.`,
  { label: 'wire the planner', phase: 'Wire' })

phase('Attack')

const attack = await agent(`${LAW}

Another agent just wired the argument planner into cellcog_composer.py. It reported:
${String(wired).slice(0, 2500)}

YOU ARE THE ADVERSARY. You did not write this. Your job is to BREAK it, or prove it holds. Assume it is
broken until you cannot make it fail.

RUN, do not read:
 1. \`python scripts/test_gate_is_wired.py\` — must be GREEN, and NOTHING weakened. Check git diff on the
    test file: if any check was deleted or loosened to pass, that is the WORST outcome — say so loudly.
 2. IS THE PLANNER ACTUALLY ON THE CRITICAL PATH, or imported and never called? (This is the exact bug
    that has bitten us all night — provenance.py passed 18/18 while called by nobody.) Prove the composer
    CALLS the planner and that removing the planner CHANGES the output. An AST walk + an ablation.
 3. Does the wiring reintroduce SURNAME INFERENCE or any lane where the model names a source? Grep + test.
 4. Does an owned "verdict" sentence smuggle in a NEW PARTICULAR (a number, a named entity) not in its
    premises? Feed one and confirm it is refused.
 5. Does a comparison bundle ever pair two EXPRESSIONS OF ONE STUDY as if independent (the duplicate-study
    attack)? Test with the Acemoglu NBER-vs-JEP pair if present.
 6. Can the composer still write to outputs/release/ ? It must NOT (0555). Try it.
 7. Do a DRY/OFFLINE bundle build over the real 232 cards and report: how many genuine cross-source
    comparison bundles exist? If the planner finds only 1-2, the +0.0259 is not really available on this
    corpus and you must SAY SO — that is a finding, not a failure.

Report ONLY what you executed. Quote real output. If it is broken, name the file:line and the failing
input. A finding that we are still broken is worth more than a clean report.`,
  { label: 'adversary: planner wiring', phase: 'Attack' })

return { wired: String(wired).slice(0, 1200), attack }
