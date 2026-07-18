export const meta = {
  name: 'validator-delist-general',
  description: "Sol V11: rebuild the validator's ADMIT logic to be positive-proof-only. report_ast two-lane (quotation vs judge), delist owned/heading/venue/empirical; synthesis typed-proposition proof; planner facet-verdict; cohesion structure-only. Then adversary runs Sol's exact false-admission examples.",
  phases: [
    { title: 'ReportAST', detail: 'two lanes: quotation (neutral render, never shows-that) + finding (all to judge); lists reject-only; delist owned/heading/venue/empirical' },
    { title: 'OtherLanes', detail: 'synthesis every-proposition-proven + drop SAFE_CAPS/LEVEL_CUES overfit; planner facet={value,span,verdict} + judge secondhand/forecast; cohesion structure-only, no reorder' },
    { title: 'Attack', detail: "adversary runs Sol's EXACT false admissions (Cambridge cohort, eradicated disease, hypothesis-as-finding, riding fabrication) + hunts more; all must reject" },
  ],
}

const ROOT = '/home/polaris/wt/flywheel'

const LAW = `
=== THE ANTI-OVERFIT LAW (Sol V11) ===
The validator decides ADMIT by hardcoded WORD LISTS, and every unlisted word is a HOLE. Proven live
(judge forced UNCERTAIN), all ADMITTED today:
  'The Cambridge cohort uncovered that the treatment cured disease.'
  'The treatment eradicated disease.'   heading 'Daily aspirin eradicates disease'
  synthesis 'These studies observe different units, and the intervention eradicates disease.'
THE GENERAL RULE: a LIST MAY ONLY REJECT (cheap fail-safe). ABSENCE OF A LIST HIT MEANS UNKNOWN -> route
to the judge, NEVER admit. ADMISSION REQUIRES POSITIVE PROOF (structural, or a semantic judge verdict with
governing context, fail-closed on UNCERTAIN/unavailable). Even a BYTE-IDENTICAL quotation may not be
UPGRADED into a finding -- the speech act (a hypothesis, a question, someone else's claim) is dropped.
Never weaken a test to pass. \`${ROOT}/scripts/test_gate_is_wired.py\` and test_fabrication_paths.py stay
the source of truth; a green that hides a false admit is the worst outcome.
`

phase('ReportAST')

const rast = await agent(`${LAW}

YOU OWN ${ROOT}/scripts/report_ast.py. Rebuild its ADMIT logic per Sol V11. This is the core.

1. TWO LANES for attributed content (replace the poison-list contiguous_window_admit / entailed_by_span
   deterministic-admit at ~:913/:947):
   a. QUOTATION LANE (deterministic ADMIT allowed): the emitted payload is BYTE-IDENTICAL to the WHOLE
      bound evidence unit -- case, punctuation, signs, quotes, internal whitespace ALL preserved (no
      normalization; case/punctuation are semantic -- genes, math, question marks). Render NEUTRALLY:
      \`<Author> writes: "<exact bytes>"\`. NEVER render as show/find/establish/demonstrate/'the study
      found'. Its only guarantee: 'these bytes occur in this source.'
   b. FINDING/PARAPHRASE LANE (everything else): goes to the semantic judge, which receives claim + FULL
      evidence unit + governing heading/caption/quotation context + source identity, and must verify
      entailment + assertoric status + source ownership + direction + magnitude + scope + population +
      comparator + time + condition + modality + quantifiers. UNCERTAIN/unavailable/malformed/missing
      context -> REJECT.
   Clause-boundary detection may ONLY reject or route -- NEVER authorize admission.
2. DELIST (each currently fail-open -- an unlisted value ADMITS; make each REJECT-only / route-to-judge):
   * _EMPIRICAL_VERB (~:786): today no listed verb => judge NEVER called on a premise-free Owned. FIX:
     judge EVERY premise-free Owned factual sentence (or abolish premise-free assertions). 'The treatment
     eradicated disease' must be judged/rejected regardless of the verb.
   * _REPORTING_VERB / _ATTRIB_PATTERN / _GROUP_WORDS / _COMMON_SUBJECTS: an OWNED sentence that ascribes
     a finding to any actor must be rejected/judged; do NOT infer 'contains no actor' from a failed
     group-noun match. 'The Cambridge cohort uncovered that...' must not pass.
   * _KNOWN_VENUES: no corpus hit means UNKNOWN (judge the ascription), not 'names no source'.
   * heading validator: a heading must be a structurally-generated label OR semantically classified as a
     non-propositional noun phrase. 'Daily aspirin eradicates disease' must be rejected.
   * 'while' as neutral connective: any relational connective requires a relation proof.
   * _MAGNITUDE_ABS/SPELLED_QTY/FORECAST/entity-capital: keep as REJECT-only; unlisted stays UNKNOWN->judge.
3. Keep numeric/unit/direction/sign checks as REJECT-ONLY defenses; survival never = support.

VERIFY (judge DOWN and judge=UNCERTAIN identical): Sol's 3 report_ast false admissions REJECT; the
hypothesis/question quotations are NOT rendered as findings (quotation lane renders neutrally or rejects);
a TRUE finding still ships via the judge when it is UP+ENTAILED; a verbatim quote ships as a quote.
test_gate_is_wired + test_fabrication_paths GREEN, git diff shows NO test weakened. Do NOT touch other
files. Do NOT commit. Report file:line + real output.`,
  { label: 'report_ast two-lane + delist', phase: 'ReportAST' })

phase('OtherLanes')

const others = await parallel([
  () => agent(`${LAW}

YOU OWN ${ROOT}/scripts/synthesis_contract.py. Sol V11: a recognized phrase licenses a proof while an
UNRELATED fabrication rides the SAME sentence. THIS PASSES today and must not:
   'These studies observe different units of analysis, and the intervention eradicates disease.'
(first clause matches _CLAIM_PATTERNS:359; the proof checks the unit relation; NOTHING proves the
eradication claim.)
FIX (general):
 * A synthesis must be an AST of TYPED PROPOSITIONS, not free prose searched for ONE recognized phrase.
   EVERY proposition in the sentence must map to a proof conclusion; an unproved rider clause -> REJECT.
 * The final prose is COMPILED from the proof object via a CLOSED template -- no model-written suffixes
   or conjunctions.
 * Every facet in a proof needs an exact evidence span + semantic binding; unknown/ambiguous facet ->
   UNKNOWN, cannot participate.
 * DELETE THE TASK-72 OVERFIT: SAFE_CAPS contains 'Artificial Intelligence'/'Fourth Industrial Revolution'
   (:82-95 region) -- allowing them premise-free. Remove domain entities; caps-entity handling must be
   general (unknown entity -> judge, not allow-listed).
 * LEVEL_CUES (:164) is economics-specific and polysemous ('plant'=factory|botanical) -- generalize or
   route to judge.
 * method/horizon must be span-bound, not trusted from declared fields; BOUNDARY/COVERAGE_GAP proofs must
   prove the OBJECT of the limitation.
VERIFY: the riding-fabrication synthesis REJECTS; a legitimate 'different units, not directly comparable'
(no rider) still SHIPS; SAFE_CAPS no longer hardcodes AI/4IR. Canary green, no test weakened. Do NOT touch
report_ast/argument_planner/cohesion. Do NOT commit. Report file:line + real output.`,
    { label: 'synthesis: every-proposition-proven, drop task-72 caps', phase: 'OtherLanes' }),

  () => agent(`${LAW}

YOU OWN ${ROOT}/scripts/argument_planner.py AND ${ROOT}/scripts/cohesion_pass.py (separate files, no other
agent touches them).

ARGUMENT_PLANNER (Sol V11): these secondhand/forecast spans are fully eligible today and must NOT be:
   'Brown demonstrated that the drug reduced mortality.' (secondhand -- Brown reporting someone else)
   'The drug is anticipated to reduce mortality.' / 'is poised to improve survival.' (forecast, not result)
FIX: contract vocabularies (outcome/polarity/negator/clause-break, secondhand_cues:256, forecast_cues)
NOMINATE CANDIDATE FACETS ONLY. A semantic facet extractor returns {value, exact supporting span,
confidence/verdict}; only AFFIRMATIVE, UNAMBIGUOUS bindings enter comparisons. Secondhand-ownership and
observed-vs-forecast status must be JUDGED for every candidate span (unlisted 'was anticipated to lower
mortality' -> forecast/unknown, not comparable). Digit presence is NOT an estimate; a sample size / trial
number cannot make a span a quantitative effect. Corpus absence -> 'not represented in this corpus' only.
Note: the default contract (:141, also loaded by report_ast) is task-72-specific -- flag it; a configurable
default does not make the path general.

COHESION_PASS (Sol V11): templates CREATE new factual relations. These PASS today and must not:
   'their agreement carries more weight than either alone.' / '...the answer is not the same one.' /
   'over the long-term horizon the same mechanisms need not hold.'
FIX: a premise-free cohesion node may express ONLY document structure ('The next section considers safety
outcomes.'). ANY statement about evidence/comparability/agreement/strength/limits needs premise IDs + a
relation proof. Generate transitions from PROVED conclusions, not dominant metadata. DISABLE paragraph
reordering unless cross-paragraph anaphora + discourse dependencies are represented and preserved -- safe
default is NO reorder (reorder can change the antecedent of 'this result'/'the former').
VERIFY: the secondhand/forecast planner spans -> not eligible/judged; the 3 cohesion sentences REJECT; a
structural transition ('The next section considers...') SHIPS; reorder is off by default. Canary green, no
test weakened. Do NOT touch report_ast/synthesis_contract. Do NOT commit. Report file:line + real output.`,
    { label: 'planner facet-verdict + cohesion structure-only', phase: 'OtherLanes' }),
])

phase('Attack')

const attack = await agent(`${LAW}

The validator ADMIT-logic rebuild landed:
REPORT_AST: ${String(rast).slice(0, 700)}
OTHER: ${others.filter(Boolean).map((r,i)=>`[${i}] ${String(r).slice(0,500)}`).join(' ')}

FRESH ADVERSARY. Run Sol's EXACT false-admission examples against the REAL validate_report on bound cards,
plus your own. EVERY ONE must now REJECT (or, for a verbatim quote, ship ONLY as a neutral quotation, never
as 'shows that'). Judge forced UNCERTAIN AND judge down -- identical results.
  report_ast: 'The Cambridge cohort uncovered that the treatment cured disease.' ; 'The Oxford
    investigators ascertained that the drug was effective.' ; 'The Karolinska cohort detected a survival
    benefit.' ; 'The treatment eradicated disease.' ; 'The intervention prolonged survival.'
  headings: 'Daily aspirin eradicates disease' ; 'The intervention guarantees recovery' ; 'The treatment
    cured cancer'
  quotation-vs-finding: SPAN 'Daily aspirin reduced all-cause mortality?' -> CLAIM 'Daily aspirin reduced
    all-cause mortality.' must NOT render as a finding; SPAN 'Hypothesis: Daily aspirin reduced mortality'
    -> same.
  synthesis: 'These studies observe different units of analysis, and the intervention eradicates disease.'
  planner: 'Brown demonstrated that the drug reduced mortality.' ; 'The drug is anticipated to reduce
    mortality.' ; 'Mortality is destined to fall after adoption.'
  cohesion: 'their agreement carries more weight than either alone.' ; 'the answer is not the same one.'
THEN hunt more with NOVEL synonyms (the whole point -- lists must be gone): 'The lab ascertained...',
'is on track to reduce', 'was shown to eliminate', a heading 'Statins abolish risk'.
CONFIRM POSITIVE CONTROLS still ship: a true entailed finding (judge up), a verbatim neutral quotation, a
legitimate 'different units' synthesis (no rider), a structural transition.
CHECK: git diff on BOTH test files shows NOTHING weakened. Grep the ADMIT paths for any surviving word
list that DECIDES admit -- if found, name it (file:line).
For each: HELD or BROKEN, file:line, exact input. If ANYTHING lands we are not ready for Sol's final
re-review. Do NOT commit.`,
  { label: "adversary: Sol's exact false admissions + novel synonyms", phase: 'Attack' })

return { rast: String(rast).slice(0,500), others: others.filter(Boolean).length, attack }
