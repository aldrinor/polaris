export const meta = {
  name: 'close-last-failopen',
  description: "Close the 2 confirmed holes: planner eligibility (positive first-hand signal required, not absence-of-cue) + judge rubric (dropping a qualifier the span carries is NOT_ENTAILED). Then adversary re-runs Sol's 29 + A03/A12 + destined-family + novel projections.",
  phases: [
    { title: 'Fix', detail: 'planner positive-eligibility (structural) ‖ judge rubric facet-drop strictness (prompt) — different files, parallel' },
    { title: 'Attack', detail: "adversary re-runs Sol's 29 + A03/A12 comparator/contrast-drop + destined/bound/due family + novel projection synonyms; must be 29/29 + the new vectors" },
  ],
}

const ROOT = '/home/polaris/wt/flywheel'

const LAW = `
=== THE ANTI-OVERFIT LAW ===
A LIST MAY ONLY REJECT. Absence of a list hit means UNKNOWN -> route to judge / not-adjudicable, NEVER
admit. ADMISSION REQUIRES POSITIVE PROOF. The last adversary found EXACTLY ONE surviving fail-open where a
list's absence grants admission (planner eligibility) -- fix it structurally, not by extending the list.
The judge is the backstop; its rubric must enforce FACET PRESERVATION (dropping a qualifier the span
carries is NOT_ENTAILED, even if the remainder is technically true). Never weaken a test to pass.
`

phase('Fix')

const fixes = await parallel([
  () => agent(`${LAW}

YOU OWN ${ROOT}/scripts/argument_planner.py. Close the LAST fail-open (adversary-confirmed).

THE HOLE (argument_planner.py:614-621): \`adjudicable\`/\`eligible\` return ADMIT whenever no
secondhand_cues/forecast_cues hit fires -- ABSENCE OF A CUE GRANTS adjudicability. So a projection whose
modal is not on the list slips through:
  'Employment is DESTINED TO fall after adoption.' -> eligible=True, adjudicable=True (a pure projection
  becomes a weighable directional finding that can anchor a FALSE CONFLICT against a measured card).
  Also: 'is bound to', 'is due to', 'is on course to' -- and any future projection phrasing.

DO NOT just add destined|bound|due|on-course to forecast_cues -- that is whack-a-mole; the next synonym
slips. FIX STRUCTURALLY: a span is ADJUDICABLE (a weighable first-hand measured finding) ONLY IF it carries
a POSITIVE first-hand/measured signal -- a reported result with observed direction/quantity grounded in the
span -- NOT merely 'no forecast cue matched'. Absence of a measured signal => NOT adjudicable (route to
UNKNOWN / non-weighable), regardless of the verb. forecast_cues/secondhand_cues remain as cheap REJECT-only
signals, but they no longer DECIDE admit by their absence.

VERIFY (real output): 'Employment is destined to fall after adoption' -> NOT adjudicable; same for
bound/due/on-course + a novel projection ('Employment is slated to crater'); a genuine MEASURED finding
('Employment fell 4 points after adoption') stays adjudicable=True; the anticipated/secondhand cases still
rejected. Canary + test_fabrication_paths green, no test weakened. Do NOT touch report_ast/synthesis/
cohesion. Do NOT commit. Report file:line + real output.`,
    { label: 'planner positive-eligibility', phase: 'Fix' }),

  () => agent(`${LAW}

YOU OWN the ENTAILMENT JUDGE RUBRIC in ${ROOT}/scripts/report_ast.py (_llm_entailment_judge prompt, ~:739).
The finding lane correctly routes everything to the judge and fails closed -- but the REAL judge is LENIENT
on DROPPED qualifiers (independently confirmed):
  A03: claim 'wages rose' over span 'wages rose in treated firms BUT FELL IN CONTROLS' -> judge ENTAILED (a
       mixed result rendered as an unqualified one-direction claim).
  A12: claim 'output was 8% higher' over span 'output was 8% higher THAN PLACEBO' -> judge ENTAILED (drops
       the comparator).
The prompt already says 'SAME SCOPE/COMPARATOR', but the model reads that as 'don't CONTRADICT' rather than
'don't DROP'.

FIX THE RUBRIC (prompt text only -- do NOT add code word-lists): make it explicit and general:
  * 'The CLAIM must not DROP any qualifier the SPAN attaches to the finding. Omitting a scope, population,
    comparator, baseline, contrast, condition, or time restriction that the SPAN states is NOT_ENTAILED,
    EVEN IF the remaining statement is technically true. An unqualified claim is not entailed by a
    qualified or mixed-result span.'
  * 'If the SPAN reports a MIXED or CONTRASTING result (rose here but fell there), a claim asserting only
    one direction without the contrast is NOT_ENTAILED.'
  * Keep the existing direction/magnitude/number/modality strictness.

VERIFY with the REAL judge (this needs a live model call): A03 and A12 now -> NOT_ENTAILED; the positive
controls (the FULL claim 'wages rose in treated firms but fell in controls' ; 'output was 8% higher than
placebo') -> ENTAILED and SHIP. If the live model is unreachable in your env, say so and provide the
rubric diff + a stub-based proof that the fail-closed path holds; flag that a live re-check is required.
Do NOT touch synthesis/planner/cohesion. Do NOT weaken a test. Do NOT commit. Report the prompt diff +
real output.`,
    { label: 'judge rubric: facet-drop strictness', phase: 'Fix' }),
])

phase('Attack')

const attack = await agent(`${LAW}

The two fixes landed:
PLANNER: ${String(fixes[0]).slice(0, 800)}
JUDGE:   ${String(fixes[1]).slice(0, 800)}

FRESH ADVERSARY. Re-run the WHOLE surface against the REAL validators on a bound graph, real output.
 1. ALL of Sol's prior 29 must still HELD (owned/heading/quote/synthesis/planner-secondhand + positive
    controls SHIP). Regression check.
 2. THE 2 FIXED HOLES:
    * planner: 'Employment is destined to fall' / 'is bound to' / 'is due to' / 'is on course to' / novel
      'is slated to crater' -> NOT adjudicable. A MEASURED finding stays adjudicable.
    * judge: A03 'wages rose' over 'rose in treated but fell in controls' -> NOT_ENTAILED; A12 'output was
      8% higher' over '...than placebo' -> NOT_ENTAILED; the FULL qualified claims -> ENTAILED and SHIP.
      (needs a live judge call -- run it; if unreachable, say so.)
 3. HUNT for a new fail-open: any OTHER place a list's ABSENCE grants admission (grep all four files);
    more dropped-qualifier judge escapes (drop a POPULATION 'among diabetics', a BASELINE 'vs 2019', a
    CONDITION 'when adopted with training'); a projection noun ('the projected decline'); a heading that
    is a projection.
 4. git diff on both test files shows NOTHING weakened.
For each: HELD or BROKEN, file:line, exact input. Report the count (X/N). If ANYTHING lands, name it. Do
NOT commit.`,
  { label: 'adversary: re-run 29 + fixed holes + hunt', phase: 'Attack' })

return { fixes: fixes.filter(Boolean).length, attack }
