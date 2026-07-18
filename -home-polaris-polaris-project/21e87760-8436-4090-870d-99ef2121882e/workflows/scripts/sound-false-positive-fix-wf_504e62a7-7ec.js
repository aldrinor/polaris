export const meta = {
  name: 'sound-false-positive-fix',
  description: "The SOUND false-positive fix: deterministic ADMIT only for a contiguous single-source-clause span with no intervening contrast/scope — then a fresh adversary re-runs #9/#9b + hunts #10. Ready for Sol only if clean.",
  phases: [
    { title: 'Fix', detail: 'contiguous single-clause ADMIT; sign-aware numbers; judge for everything else, fail-closed' },
    { title: 'Attack', detail: 'fresh adversary: the #9 subsequence family, sign-via-symbol, boundary recombination, all 8 burns, judge-liveness — and #10' },
  ],
}

const ROOT = '/home/polaris/wt/flywheel'

const LAW = `
=== THE LAW ===
ATTRIBUTED -> ENTAILED by its source's verbatim span (direction, number+unit+SIGN, modality, scope).
The deterministic layer may ADMIT only when it can PROVE entailment; everything else goes to the judge,
which FAILS CLOSED (unreachable/UNCERTAIN -> REJECT). A validator that admits a lie is catastrophic; one
that rejects a truth when the judge is down is merely unproductive.

=== WHAT JUST FAILED (do not repeat it) ===
The previous false-positive fix added ADMIT_SUBSEQUENCE_OF_SPAN: 'if the clause's words are an order-
preserving subsequence of the span, admit.' UNSOUND -- deletion flips meaning:
  SPAN 'employment rose in the adopting cities but FELL across the nation as a whole'
  ADMITTED 'employment rose across the nation as a whole'  (every word present; opposite claim)
Plus sign-blindness: '-3 percent' -> '3 percent' admitted. And the fixer WEAKENED a canary assertion to
mask it. All reverted. report_ast.py:662 states the invariant: 'the deterministic layer may NEVER conclude
ADMIT' -- the previous fix violated it. THE SOUND VERSION MUST NOT.
`

phase('Fix')

const fix = await agent(`${LAW}

YOUR TASK: the SOUND false-positive fix in ${ROOT}/scripts/report_ast.py, entailed_by_span.

THE PROBLEM: with the judge unreachable, entailed_by_span fails closed on EVERYTHING, so a TRUE entailed
finding is deleted (the canary's 'TRUE finding reaches the page' + 'CROSS-SOURCE SYNTHESIS survives' go RED
when no judge is up). Safe but unproductive: a real compose could come out empty if the model blips.

THE SOUND FIX (this is the ONLY deterministic ADMIT that is truth-preserving):
  A clause may be ADMITTED without the judge ONLY IF it is a CONTIGUOUS substring/window of a SINGLE
  source clause -- i.e. the span, split into clauses at contrast/scope/coordination boundaries
  (but/while/whereas/however/although/across/in <region>/among/for <group>/','/';'), contains one clause
  that CONTAINS the entire attributed clause as a contiguous run (modulo whitespace/case/punctuation),
  AND the attributed clause does not straddle or drop such a boundary.
  Rationale: a contiguous window of ONE clause cannot flip meaning by DELETION -- there is no dropped
  contrast/scope term, because we required it to sit wholly inside one clause with none removed. A
  SUBSEQUENCE (non-contiguous) can drop a 'but/fell' and is FORBIDDEN -- that was the #9 hole.
  If the clause spans two source clauses, or drops an intervening qualifier, it is NOT admitted here ->
  goes to the judge -> fail closed.
Also FIX SIGN-BLINDNESS: the number extractor (_NUM ~:547, quantities_in ~:933) must capture a leading
sign, so span '-3 percent' and clause '3 percent' are DIFFERENT numbers -> not a match -> not admitted.

VERIFY (run yourself, quote real output), with set_entailment_judge(None) i.e. NO judge and also with an
injected NOT_ENTAILED judge -- results must be identical for these because the deterministic layer decides:
  * #9 subsequence: 'employment rose across the nation' from 'rose in cities but fell across the nation'
    -> REJECTED (straddles a 'but' boundary / drops 'fell'). Prove it.
  * #9 causal recomb: 'automation drove the national job losses' from '...while offshoring drove the
    national job losses' -> REJECTED.
  * #9b sign: '3 percent' from '-3 percent' -> REJECTED.
  * TRUE contiguous finding: 'computer capital substitutes for workers in routine tasks' from a span that
    contains exactly that as a contiguous run -> ADMITTED with NO judge (this is the false-positive fix
    working).
  * scripts/test_gate_is_wired.py -> the 2 false-positive checks PASS with NO judge stub; ALL 8 fabrication
    attacks still REJECT. scripts/test_fabrication_paths.py all green. git diff on BOTH test files must show
    NOTHING WEAKENED (you may only make checks pass by fixing report_ast.py).
Do NOT touch any other file. Do NOT commit.`,
  { label: 'sound contiguous-clause ADMIT', phase: 'Fix' })

phase('Attack')

const attack = await agent(`${LAW}

The sound false-positive fix landed:
${String(fix).slice(0, 1400)}

YOU ARE A FRESH ADVERSARY. You built none of this. The LAST false-positive fix was a fabrication
superhighway that also masked a test. Assume this one is broken too until you cannot break it.

RUN, real output, driving the REAL report_ast.validate_report on bound cards:
 1. Both test suites GREEN and git diff shows NOTHING weakened (the previous fixer swapped a subset-shaped
    positive control to a paraphrase to hide the regression -- check the diff for exactly that trick).
 2. THE #9 FAMILY, exhaustively: order-preserving subsequence that drops a contrast ('but/while/whereas'),
    drops a scope ('in cities'/'nationally'/'worldwide'), drops a subject/object ('men gained while women
    lost' -> 'women lost' vs 'men lost'), causal recombination across a clause, sign flip via '-'/'−'
    (unicode minus)/'(3)' accounting-negative/'3% decline' vs '3% ' . NONE may ship.
 3. THE CONTIGUOUS-ADMIT boundary itself: can you make a contiguous window of ONE clause still lie? Try a
    clause that is contiguous in the span but whose truncation changes meaning ('rose sharply' -> 'rose';
    'may have risen' -> 'risen'; 'rose, then fell' where your splitter fails to split on the comma). If the
    splitter misses a boundary type, the contiguous-admit becomes a hole -- find it.
 4. Judge-liveness: a TRUE contiguous finding ships with the judge DOWN; a paraphrase (not contiguous)
    with the judge down REJECTS; with the judge UP and returning ENTAILED, the paraphrase ships. Confirm
    the deterministic admit does NOT call the judge (instrument it).
 5. All 8 prior burns + the P0 hops (accepted manuscript at any hop) still hold.
 6. HUNT #10.

For each: HELD or BROKEN, file:line, exact input. If ANYTHING lands we are not ready for Sol. If nothing
lands after genuine effort, say so and list what you tried. Do NOT commit.`,
  { label: 'fresh adversary: #9 family + #10', phase: 'Attack' })

return { fix: String(fix).slice(0,700), attack }
