export const meta = {
  name: 'close-10-scope-hedge',
  description: "Close #10a (trailing scope) + #10b (edge hedge/evidential) in contiguous_window_admit — the poison sets must cover scope on BOTH edges and modality/evidentiality including multi-word forms. Fresh adversary hunts #11.",
  phases: [
    { title: 'Fix', detail: 'poison = direction+contrast+negation+scope(both edges)+modality/hedge(incl multi-word); a shed meaning-changer at either edge -> judge, fail closed' },
    { title: 'Attack', detail: 'fresh adversary: scope w/o listed preposition, multi-word hedge, evidential, + re-run #9/#10 and all 8 burns; hunt #11' },
  ],
}

const ROOT = '/home/polaris/wt/flywheel'

const LAW = `
=== THE LAW ===
An ATTRIBUTED clause must be ENTAILED by its source span. Meaning-flips that DELETION can introduce and
which THE LAW forbids: DIRECTION (rose/fell), CONTRAST (but/while), NEGATION (not), SCOPE (in cities /
among young workers / only in treated villages / worldwide), MODALITY & EVIDENTIALITY (may/might/could/
suggest/appears/likely/the data suggest that/the authors speculate that). Dropping ANY of these at an edge
changes the claim. The deterministic layer may ADMIT only a contiguous window that sheds NONE of them;
everything else -> the judge -> FAIL CLOSED.
`

const FINDING = `
=== #10 (both land through contiguous_window_admit, judge_calls=0, confirmed end-to-end) ===
#10a TRAILING SCOPE: _SCOPE_WORDS is in _LEAD_POISON (report_ast.py:922) but MISSING from _TRAIL_POISON
  (:924); the trail check (:967) never sees a shed scope qualifier.
    span 'the reform boosted local employment in the adopting cities' -> 'the reform boosted local
    employment' ADMITTED. Also 'fell steadily among young workers'->'overall unemployment fell steadily';
    clinical 'reduced tumor size in patients under 40'->'reduced tumor size'.
#10b EDGE HEDGE/EVIDENTIAL: _HEDGE (report_ast.py:585: may/might/could/suggest/appears/likely/speculate)
  is in NEITHER poison set; _modality_residue (:876) is LEGACY, 'nothing depends on the value.'
    span 'the data suggest that wages grew across every affected sector' -> 'wages grew across every
    affected sector' ADMITTED. Also 'the treatment MAY lower patient anxiety'->'lower patient anxiety';
    'the authors speculate that automation displaced routine clerical labour'->'automation displaced...'.

Root cause: ONE class -- poison sets apply scope asymmetrically (lead only) and omit modality/evidentiality
entirely. The adversary WARNS that the naive fix (_TRAIL_POISON |= _SCOPE_WORDS; fold _HEDGE into both)
still lets MULTI-WORD hedges slip ('there is some evidence that') and SCOPE EXPRESSED WITHOUT A LISTED
PREPOSITION. Do not stop at the naive fix.
`

phase('Fix')

const fix = await agent(`${LAW}\n${FINDING}

YOUR TASK: close #10a and #10b in ${ROOT}/scripts/report_ast.py's contiguous_window_admit, ROBUSTLY.

 1. SCOPE ON BOTH EDGES: a shed scope qualifier at the LEAD or the TRAIL edge blocks the deterministic
    admit. _TRAIL_POISON must include scope. But do not rely only on a preposition list -- SCOPE EXPRESSED
    WITHOUT A LISTED PREPOSITION must also block. Safest sound rule: the contiguous window must be a
    PREFIX-OR-WHOLE of its source clause OR a suffix-or-whole, such that no trailing/leading MODIFIER
    PHRASE that narrows the claim is dropped. If the window drops ANY non-trivial run of words at an edge
    that contains a scope/among/only/prepositional-phrase/subordinate marker, it does NOT admit -> judge.
    When in doubt, DO NOT ADMIT (route to judge, fail closed) -- a false reject is safe, a false admit is not.
 2. MODALITY/EVIDENTIALITY, INCLUDING MULTI-WORD: fold hedge/evidential into the poison check for BOTH
    edges, and handle MULTI-WORD forms ('the data suggest that', 'there is some evidence that', 'it appears
    that', 'the authors speculate that', 'studies indicate that'). A dropped hedge/evidential lead or an
    infixed modal ('may', 'might', 'could') that the window steps over blocks admit. Retire the LEGACY
    _modality_residue confusion -- there must be ONE place that decides 'this edge word/phrase changes the
    claim'.
 3. Keep the true-positive: a genuinely contiguous window that sheds ONLY neutral framing ('we find that',
    'in this paper', 'the results show that' -- reporting frames that add no scope/direction/hedge) still
    ADMITS with no judge. If distinguishing a neutral frame from an evidential hedge is hard, prefer to
    route to the judge (fail closed) rather than admit -- correctness over productivity.

VERIFY yourself, judge DOWN and judge=NOT_ENTAILED (identical results expected):
  * #10a all three (cities/young workers/tumor) -> REJECTED.
  * #10b all (data suggest/may lower/speculate) -> REJECTED. Multi-word 'there is some evidence that
    wages grew' -> REJECTED.
  * true contiguous 'computer capital substitutes for workers in routine tasks' (neutral 'we find that'
    frame) -> ADMITTED, judge_calls=0.
  * #9 family still REJECTED; all 8 burns still REJECTED; test_gate_is_wired + test_fabrication_paths
    GREEN; git diff shows NO test weakened.
Do NOT touch other files. Do NOT commit. Report file:line + real output.`,
  { label: 'close scope+hedge robustly', phase: 'Fix' })

phase('Attack')

const attack = await agent(`${LAW}\n${FINDING}

The scope+hedge fix landed:
${String(fix).slice(0, 1300)}

FRESH ADVERSARY. You built none of it. The last two fixes each opened a new hole; assume this one did too.

RUN against the REAL validate_report on bound cards, real output:
 1. Both suites GREEN, git diff shows NOTHING weakened (check specifically that no positive control was
    swapped/loosened to hide a regression -- that trick has appeared before).
 2. #10a scope: trailing 'in cities'/'among young workers'/'only in treated villages'/'for firms over 500
    employees'; AND scope WITHOUT a listed preposition ('urban employment rose' from 'employment rose in
    urban areas'? adjective-scope); clinical 'in patients under 40'. NONE admit.
 3. #10b hedge/evidential: single ('may'/'suggest'/'appears'), multi-word ('the data suggest that',
    'there is some evidence that', 'it is plausible that', 'a growing literature argues that'), infixed
    modal the window steps over. NONE admit.
 4. #9 family (recombination, dropped contrast/scope/subject, sign via -/−/(n)) still REJECT.
 5. All 8 burns + P0 all hops still hold. Judge-liveness: true contiguous ships judge-down (judge_calls=0);
    everything non-contiguous rejects judge-down.
 6. HUNT #11: a window that sheds a COMPARATOR ('more than'/'relative to'), a TEMPORAL scope ('in 2020'/
    'during the recession'), a CONDITION ('when demand is elastic'), a QUANTIFIER-restrictor ('some'/'a
    few'->all). Anything that changes truth by truncation.

For each: HELD or BROKEN, file:line, exact input. If ANYTHING lands, we are not ready for Sol -- name it.
If nothing lands after genuine effort, SAY SO explicitly and list what you tried. Do NOT commit.`,
  { label: 'fresh adversary: hunt #11', phase: 'Attack' })

return { fix: String(fix).slice(0,700), attack }
