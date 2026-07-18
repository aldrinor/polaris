export const meta = {
  name: 'real-entailment-judge',
  description: "Replace the lexical direction/magnitude/scope/modality gate with a constrained LLM entailment judge on the WHOLE clause (fail closed), build Rung-4 RelationProof for verdicts, then a fresh adversary re-runs the synonym/scope/modality attacks + hunts an eighth.",
  phases: [
    { title: 'Judge', detail: 'entailed_by_span calls the constrained judge on the whole clause; deterministic checks are a fast REJECT-only pre-filter, never an ADMIT' },
    { title: 'Verdicts', detail: 'Rung 4: a verdict needs a RelationProof (verified shared/differing facets bound to spans); close T7' },
    { title: 'Attack', detail: 'fresh adversary: synonyms, magnitude, scope, modality, oblique source, table sign-flip, false verdict — and find #8' },
  ],
}

const ROOT = '/home/polaris/wt/flywheel'

const LAW = `
=== THE LAW ===
An ATTRIBUTED sentence MUST be ENTAILED by its source's verbatim span. Entailment means: same direction/
polarity, same numbers WITH units, same modality (associational != causal), same scope/population/
comparator, and the clause asserts nothing the span does not support. An OWNED sentence carries no new
particular. Fabrication = an attributed sentence its source does not entail.

=== WHY WE ARE HERE — THE FIX FAILED, HONESTLY ===
Rung 2 was told to replace lexical entailment. It replaced a 25%-bag-of-words check with a BIGGER
40-WORD DIRECTION LEXICON. A fresh adversary broke it on first contact with SYNONYMS:
    SPAN 'ratio ROSE by 1.5 points' -> RENDERED 'ratio PLUNGED by 1.5 points'  (Sol's Burn #1, verbatim)
plus magnitude ('doubled'), scope ('US'->'worldwide'), modality ('associated with'->'causes'), oblique
source ('The Cambridge team'), and a table sign-flip. The LLM judge EXISTS but is fenced behind a
hedge/negation residue detector that these attacks never trip, so IT IS NEVER CALLED.

THE LESSON, FINAL: a gate built from a list of words only catches the words its author imagined. The fix
is NOT a longer list. The fix is to ASK A JUDGE whether the clause is entailed by the span, on the WHOLE
clause, and to FAIL CLOSED when the judge is unavailable or uncertain.

THE BUILDER CANNOT VERIFY ITSELF, and an Opus adversary that shares the builder's imagination is not
enough either — the finish line is SOL'S RE-REVIEW. Do not declare victory.
`

phase('Judge')

const judge = await agent(`${LAW}

YOUR TASK — REPLACE THE LEXICAL ENTAILMENT GATE WITH A CONSTRAINED JUDGE. File: ${ROOT}/scripts/report_ast.py,
\`entailed_by_span\` and its helpers (the _UP/_DOWN lexicons ~:560/:565, the residue gate ~:692-703/:753,
the magnitude/scope gaps).

THE ARCHITECTURE (this is the design; implement it):
 1. DETERMINISTIC PRE-FILTER — REJECT-ONLY, never ADMIT. Fast structural rejects that need no model:
      * a NUMBER in the clause not present in the span (with unit) -> REJECT
      * a NAMED ENTITY / venue / source in an attributed clause that is not the cited one -> REJECT
    These are cheap and certain. They may only REJECT. They may NEVER conclude ADMIT — passing the
    pre-filter means "not yet rejected", not "entailed".
 2. THE JUDGE — for EVERY attributed clause that survives the pre-filter, call a constrained LLM judge
    on the WHOLE clause vs the WHOLE span (not a residue subset, not conditional on hedge words):
        input:  the span (verbatim) + the clause
        output: ENTAILED | NOT_ENTAILED | UNCERTAIN, plus the span excerpt that decided it
        rubric: the clause may assert ONLY what the span supports -- same direction, same magnitude,
                same modality (associational vs causal), same scope/population/comparator, same polarity.
                'rose' vs 'plunged' = NOT_ENTAILED. 'doubled' when span says '1.5 points' = NOT_ENTAILED.
                'worldwide' when span says 'in the US' = NOT_ENTAILED. 'causes' when span says
                'associated with' = NOT_ENTAILED.
    ** FAIL CLOSED: NOT_ENTAILED and UNCERTAIN both REJECT. Only ENTAILED admits. **
    ** FAIL CLOSED ON UNAVAILABILITY: if the judge model cannot be reached, the clause is REJECTED, never
    admitted. A validator that admits when it cannot check is the whole problem. **
 3. The SAME judge path must cover the ATTRIBUTED lane AND the EVIDENCE TABLE lane (the table used the
    same weak lexical check). The attributed lane must be AT LEAST AS STRONG as the OWNED lane -- the
    adversary noted the wrong asymmetry (the lane that puts words in a scholar's mouth was the weaker one).
 4. DETERMINISM/COST: cache judge results by (span_hash, clause) so a re-run is stable and cheap. The
    deterministic pre-filter handles the obvious rejects so the judge is only asked the semantic residue.
    Use the repo's llm() helper; a low temperature; a tight JSON output.

Then run scripts/test_fabrication_paths.py AND the adversary's own harness at
/tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/adv2.py
(read it first). Attacks A (synonym sign-flip), B (magnitude), C (scope), D (modality), F (table) MUST now
be REJECTED. The positive controls (a TRUE entailed finding) MUST still SHIP. Report REAL output, including
a case where the judge said UNCERTAIN and the clause was correctly rejected. Do NOT weaken any test. Do NOT
commit.`,
  { label: 'constrained entailment judge', phase: 'Judge' })

phase('Verdicts')

const verdicts = await agent(`${LAW}

The entailment gate was just replaced with a constrained judge:
${String(judge).slice(0, 1200)}

YOUR TASK — RUNG 4: PROOF-CARRYING VERDICTS (close T7). The planner's OWNED verdicts are DETERMINISTIC but
can be FALSE. The adversary showed the gate admits BOTH "these point in opposite directions" AND "these are
not contradictory" for the same premises -- a false reconciliation assembled from true particulars.

Per Sol, a verdict needs a PROOF OBJECT, not tags. In ${ROOT}/scripts/argument_planner.py and
${ROOT}/scripts/synthesis_contract.py:
 1. A RelationProof for every planner verdict:
        operation
        premise claim-atom IDs
        verified SHARED dimensions (with the exact facet-supporting span for each)
        verified DIFFERING dimensions (same)
        polarity / modality / comparator for each premise
        the rule whose preconditions were satisfied
        the rendered conclusion template
 2. FACETS MUST BIND TO SPANS. argument_planner.py:599 trusts level/method/horizon as strings off the
    card. A facet used in a verdict must be supported by a verbatim span, or the verdict does not ship.
 3. OPERATION-SPECIFIC SEMANTIC CHECKS. The synthesis contract currently lets CONVERGES / CONTRASTS /
    ESTABLISHES / DOES_NOT_ESTABLISH pass on anchoring alone. Each must verify its OWN preconditions:
      * SAME_OUTCOME_DIFFERENT_UNIT licenses ONLY "these concern different units and are not directly
        comparable." It does NOT license "not contradictory", "what holds at A does not establish B", or
        a causal explanation of the difference.
      * "not contradictory" requires: same construct, compatible population/time/comparator, opposed
        surface results, AND a demonstration both can be simultaneously true because scopes differ. If any
        facet is unproved, NO VERDICT SHIPS.
 4. The gate must stop "try every operation, admit if any passes" (report_ast.py:605). An Owned verdict
    carries its operation and is checked against THAT operation's proof.

Run the tests: T7 (the false-verdict pair) MUST now reject the unproven verdict while still allowing the
proven "different units" one. Do NOT commit.`,
  { label: 'rung 4: proof-carrying verdicts', phase: 'Verdicts' })

phase('Attack')

const attack = await agent(`${LAW}

The entailment judge and proof-carrying verdicts are in:
JUDGE: ${String(judge).slice(0, 700)}
VERDICTS: ${String(verdicts).slice(0, 700)}

YOU ARE A FRESH ADVERSARY. You did not build this. The LAST adversary broke the previous fix on first
contact with synonyms. Your job: prove these attacks are now DEAD, and find the EIGHTH.

RUN, against the REAL validator (report_ast.validate_report / render), quoting real output:
 1. scripts/test_fabrication_paths.py — all T1..T7 must REJECT; positive controls must SHIP.
 2. The previous adversary's harness (scratchpad/adv2.py) — attacks A/B/C/D/E3/F must now be REJECTED.
 3. NEW attacks it did not try:
    - sign flip via RARE synonym or metaphor ("cratered", "went south", "evaporated")
    - a number that IS in the span but attached to the WRONG quantity ("unemployment 3%" when the span's
      3% is the ADOPTION rate)
    - a true clause + a fabricated SECOND sentence in the same node
    - modality via a noun ("the collapse of employment" when span says "a decline")
    - a verdict whose facets are real but whose RULE is misapplied
    - the judge-unavailable path: force the judge to error/timeout and confirm the clause is REJECTED
      (fail-closed), NOT admitted
    - a non-English or number-word attack ("fell by one and a half points" vs "1.5")
 4. Confirm the judge is ACTUALLY CALLED (not fenced behind a residue) — instrument it, show the call.
 5. Rebuild scripts/test_gate_is_wired.py to include these attacks driving the real validator. It must be
    RED if any attack lands, GREEN only when all are closed. Do NOT green it artificially.

For each: HELD or BROKEN, file:line, exact input. If anything lands, we are not done. Report ONLY what you
ran. Do NOT commit.`,
  { label: 'fresh adversary: synonyms + find #8', phase: 'Attack' })

return { judge: String(judge).slice(0, 700), verdicts: String(verdicts).slice(0, 700), attack }
