export const meta = {
  name: 'zero-drop-general',
  description: "Replace the overfit poison-word-list entailment admit with the general zero-drop rule (deterministic ADMIT only when the clause drops nothing = whole-clause-identical; every truncation -> judge, fail closed). Fresh adversary tries every meaning-flip class including the ones the lists missed.",
  phases: [
    { title: 'Generalize', detail: 'delete _LEAD/_TRAIL_POISON/_UP/_DOWN/_HEDGE reliance; admit deterministically only on zero-drop whole-clause identity; all truncation -> judge fail-closed' },
    { title: 'Attack', detail: 'fresh adversary: scope/hedge/comparator/temporal/condition/quantifier/sign/direction — every truncation must reject; zero-drop true finding ships; hunt for any residual list' },
  ],
}

const ROOT = '/home/polaris/wt/flywheel'

const LAW = `
=== THE LAW & THE ANTI-OVERFIT PRINCIPLE ===
An ATTRIBUTED clause must be ENTAILED by its source span. DELETION is not truth-preserving: dropping a
direction / contrast / negation / scope / hedge / comparator / temporal / condition / quantifier word can
flip the claim. The space of meaning-changing words is OPEN -- you cannot enumerate it. Every fix that
LISTED the dangerous words was defeated by a word not on the list (plunged, -3, trailing scope, 'the data
suggest that'...). THE GENERAL RULE MUST NOT ENUMERATE DANGEROUS WORDS.

THE ZERO-DROP RULE: the deterministic layer admits WITHOUT the judge ONLY when the attributed clause drops
NOTHING -- it is, after whitespace/case/punctuation normalization, IDENTICAL to a complete sentence or a
complete top-level clause of the span (zero words shed at either edge relative to that clause). ANY
truncation -- a proper substring of a source clause -- MIGHT have dropped a meaning-changer, so it goes to
the JUDGE and FAILS CLOSED (unreachable/UNCERTAIN -> REJECT). A false reject is safe; a false admit is
catastrophic.
`

phase('Generalize')

const fix = await agent(`${LAW}

YOUR TASK: replace the overfit poison-list entailment admit in ${ROOT}/scripts/report_ast.py with the
GENERAL ZERO-DROP RULE. The current contiguous_window_admit relies on _LEAD_POISON/_TRAIL_POISON/_UP/_DOWN/
_HEDGE word lists; a fresh adversary broke it on scope (#10a) and hedge (#10b) and predicts more
(comparator/temporal/condition/quantifier). STOP ENUMERATING.

IMPLEMENT:
 1. The deterministic ADMIT fires ONLY when the normalized attributed clause is IDENTICAL to a complete
    source unit -- a full sentence, or a full top-level clause of the span. "Drops nothing at either edge."
    Normalization: whitespace collapse, case fold, strip surrounding punctuation. NO word lists decide
    admit.
 2. If the attributed clause is a PROPER SUBSTRING of any source unit (i.e. it is contiguous but sheds one
    or more words at an edge), DO NOT admit deterministically -> route to the judge -> fail closed. It does
    not matter WHICH words were shed; we do not judge that deterministically anymore.
 3. Keep the REJECT-only deterministic pre-filter (a number/entity/venue in the clause not in the span ->
    reject) -- those are sound rejects and reduce judge load. But NOTHING deterministic may ADMIT except
    zero-drop identity.
 4. CLAUSE-BOUNDARY DETECTION: to find "a complete top-level clause" you may split on strong punctuation
    (. ; : and sentence end) and coordinating/subordinating boundaries. BUT if clause-splitting itself
    would need an open word list, PREFER THE SAFE UNDER-SPLIT: split on LESS, so a "clause" is larger, so
    fewer things count as whole-clause-identical, so MORE goes to the judge. Under-splitting fails safe
    (more judge, never more admit). Over-splitting (treating a fragment as a whole clause) is the hole --
    avoid it. When unsure whether a boundary exists, DO NOT split there.
 5. Retire the now-dead _UP/_DOWN/_LEAD_POISON/_TRAIL_POISON/_HEDGE/_modality_residue machinery from the
    admit path (leave any that other lanes still use, but the ADMIT decision must not consult them).

VERIFY yourself, judge DOWN and judge=NOT_ENTAILED (identical results required):
  * Every truncation REJECTS (deterministic admit does not fire): #9 subsequence, #10a scope
    ('boosted employment in the adopting cities'->'boosted employment'), #10b hedge ('the data suggest
    that wages grew'->'wages grew'), comparator ('rose more than expected'->'rose'), temporal
    ('rose in 2020'->'rose'), condition ('rose when demand is elastic'->'rose'), quantifier
    ('some firms cut jobs'->'firms cut jobs'). ALL reject with the judge down.
  * A ZERO-DROP true finding SHIPS with judge down (judge_calls=0): the attributed clause equals a whole
    source clause verbatim.
  * All 8 burns still REJECT; test_gate_is_wired + test_fabrication_paths GREEN; git diff shows NO test
    weakened (do not swap a positive control to make it pass -- that trick has appeared before).
Report file:line, the general rule as implemented, and real output for every case above. Do NOT commit.`,
  { label: 'zero-drop general admit', phase: 'Generalize' })

phase('Attack')

const attack = await agent(`${LAW}

The zero-drop general admit landed:
${String(fix).slice(0, 1400)}

FRESH ADVERSARY. Three consecutive false-positive fixes have each opened a new hole. Assume this one did
too. Your job: prove the zero-drop rule cannot be truncated into a lie, and find a residual overfit list.

RUN against the REAL validate_report on bound cards, real output:
 1. Both suites GREEN; git diff shows NOTHING weakened (specifically: no positive control swapped/loosened).
 2. EVERY TRUNCATION CLASS must REJECT deterministically (judge down): direction (rose/fell synonym),
    contrast, negation, scope (prepositional AND adjectival 'urban employment'<-'employment in urban
    areas'), hedge (single + multi-word 'there is some evidence that'), comparator ('more than'/'relative
    to'), temporal ('in 2020'/'during the recession'), condition ('when'/'if'/'provided'), quantifier
    ('some'/'a few'/'most'->all), sign ('-3'->'3', unicode minus, accounting '(3)'), unit ('points'->
    'percent').
 3. THE ZERO-DROP ADMIT ITSELF: can a WHOLE-CLAUSE-IDENTICAL admit still lie? Try -- a span clause that is
    itself hedged/scoped so the "whole clause" carries the qualifier (that's fine, it ships WITH the
    qualifier); a clause-splitter FALSE BOUNDARY (make the splitter treat a fragment as a whole clause --
    e.g. a colon, a dash, a coordinating 'and' mid-claim, a semicolon inside a quote); a two-sentence node;
    a clause identical to a source clause that is itself a CITED REFERENCE inside the span, not the finding.
 4. #9 family + all 8 burns + P0 all hops still hold. Judge-liveness correct.
 5. RESIDUAL OVERFIT HUNT (the operator's specific instruction): grep the ADMIT path for any surviving
    hardcoded word list that DECIDES ADMIT. If found, it is a hole -- name it. Confirm every remaining word
    list is REJECT-only / fail-safe (an unlisted word routes to judge, never admits).

For each: HELD or BROKEN, file:line, exact input. If ANYTHING lands we are not ready for Sol. If nothing
lands after genuine effort, say so explicitly. Do NOT commit.`,
  { label: 'fresh adversary: truncation + residual-list hunt', phase: 'Attack' })

return { fix: String(fix).slice(0,700), attack }
