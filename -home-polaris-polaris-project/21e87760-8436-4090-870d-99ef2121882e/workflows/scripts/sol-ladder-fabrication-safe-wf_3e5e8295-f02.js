export const meta = {
  name: 'sol-ladder-fabrication-safe',
  description: "Sol's burn-remediation ladder: hostile tests that CURRENT code must FAIL, replace lexical entailment, close heading/owned/table/connective lanes, proof-carrying verdicts, safe cohesion, per-domain fixtures. Ends with Sol's re-review.",
  phases: [
    { title: 'RedTests', detail: 'write Sol\'s hostile tests; CURRENT code must FAIL every one (proof the holes are real)' },
    { title: 'Entailment', detail: 'replace word-overlap with real entailment: polarity/direction/units/modality/comparator' },
    { title: 'CloseLanes', detail: 'heading, premise-free OWNED, evidence table, connective, venue — every unreceipted prose lane' },
    { title: 'Verify', detail: 'a fresh adversary re-runs ALL hostile tests; current code must now PASS; canary rebuilt to test the real validator' },
  ],
}

const ROOT = '/home/polaris/wt/flywheel'
const REVIEW = `${ROOT}/sota_review/foundation/SOL_BURN_V10.md`

const LAW = `
=== THE LAW ===
ATTRIBUTED sentence -> MUST be ENTAILED by its source's verbatim span (not word-overlap: negation,
direction, units, modality, comparator, scope, and WHOSE finding all matter). OWNED -> reviewer's voice,
names no source, carries NO new particular (no number spelled or digit, no novel named entity). Fabrication
= an ATTRIBUTED sentence its source does not entail, OR an OWNED sentence carrying a particular.

=== WHY WE ARE HERE ===
Sol reviewed the reasoning engine and found SIX live fabrication paths. Our OWN adversarial suites all
passed -- including the release-boundary attack -- WHILE THE REAL VALIDATOR ADMITTED EVERY HOSTILE INPUT.
"The tests prove only that their chosen attacks were blocked." The released abstract ALREADY uses the
premise-free OWNED bypass. THE ARTIFACT IS BURNED.

THE BUILDER CANNOT VERIFY ITSELF, and NEITHER CAN AN OPUS ADVERSARY THAT SHARES THE BUILDER'S IMAGINATION.
The only accepted proof is: (a) CURRENT code FAILS a hostile test, then (b) after the fix, PASSES it, and
(c) Sol re-reviews and approves. Green canary is KNOWN WORTHLESS until it drives the real validator.
`

const BURN = `
=== SOL'S SIX BURNS (read the full review at ${REVIEW} FIRST) ===

1. ENTAILMENT IS WORD-OVERLAP (report_ast.py:434): digits + 25% bag-of-words. ADMITTED:
     SPAN "ratio ROSE by 1.5 points" -> SHIPPED "ratio FELL by 1.5 points".
     Also: "1.5 points"->"1.5 percent" (units unchecked); fabricated "9 percent" (single digits IGNORED
     at :449); fabricated year (year unconditionally exempt).
2. OWNED WITH NO PREMISES IS UNRESTRICTED (report_ast.py:611): Owned("The intervention causes fatal liver
     injury among children.") SHIPPED. The released abstract uses this (composer:387 -> report.md:5).
3. HEADINGS ASSERT ANYTHING (report_ast.py:540); publisher SKIPS them (publisher.py:186).
4. EVIDENCE TABLE PRINTS MODEL PROSE + unvalidated level/method (report_ast.py:624/:670).
5. CONNECTIVES MANUFACTURE RELATIONS (report_ast.py:548): "employment rose ...by contrast... output rose"
     -- the lie sits BETWEEN the clauses.
6. "MODEL NEVER TYPES A JOURNAL NAME" IS FALSE (report_ast.py:235): venues never added; "Science reports
     ..." SHIPPED under an AER card. Sub-4-char author names invisible.

Plus: OWNED VERDICTS CAN BE FALSE (facets are unproved strings, argument_planner.py:599; synthesis
contract does not validate the RELATION; the gate tries every operation and admits if any passes,
report_ast.py:605). COHESION creates false OWNED claims from templates (cohesion_pass.py:201). GENERALITY
is false -- the domain is HARDCODED (composer:212/:324/:382/:933/:827) and the compiled contract is never
passed in; a judicial opinion is refused at render (report_ast.py:356); zero evidence -> composer aborts
(composer:810) so it can never say "the literature does not settle this".

Sol's ladder (do them IN ORDER, do NOT score or stack until each rung clears its own safety checks):
  1. Add the hostile tests; CURRENT code must FAIL them.
  2. Replace lexical entailment.
  3. Close heading / owned-frame / table / connective lanes.
  4. Add proof-carrying verdicts (RelationProof).
  5. Replace cohesion templates; enforce dependency DAG.
  6. Run paired clinical/legal/thin fixtures at each rung.
`

phase('RedTests')

const red = await agent(`${LAW}\n${BURN}

YOUR TASK — SOL LADDER RUNG 1: write the hostile tests, and PROVE THE CURRENT CODE FAILS THEM.
This is the most important rung: it converts Sol's prose into executable proof that the holes are real.

Build ${ROOT}/scripts/test_fabrication_paths.py with one test per burn, each driving THE REAL validator
(report_ast.validate_report / the real render / publisher path) — NOT a hand-built dict, NOT a reimplementation:

  T1 negation:      SPAN "ratio rose by 1.5 points"  CLAUSE "ratio fell by 1.5 points"  -> MUST be REJECTED
  T1b units:        "1.5 points" rendered as "1.5 percent"                                -> MUST be REJECTED
  T1c single-digit: fabricated "9 percent" not in span                                   -> MUST be REJECTED
  T1d fake year:    a fabricated number equal to work.year but not a real finding         -> MUST be REJECTED
  T2 owned-fact:    Owned("The intervention causes fatal liver injury among children.")   -> MUST be REJECTED
  T2b owned-number: Owned("The intervention doubled mortality among children.")           -> MUST be REJECTED
  T3 heading:       Heading(2,"Acemoglu proves that 47 percent of jobs will disappear.")  -> MUST be REJECTED
  T4 table:         a table row whose model-claim REVERSES its span, invented level/method-> MUST be REJECTED
  T5 connective:    two positive unrelated findings joined by "by contrast"               -> MUST be REJECTED
  T6 venue:         "Science reports ..." under an AER card                               -> MUST be REJECTED
  T7 owned-verdict: CONVERGES accepting BOTH "point in opposite directions" AND "not contradictory" -> at
                    most ONE may pass; a false reconciliation MUST be REJECTED

RUN IT NOW AGAINST HEAD. Report which tests the CURRENT code FAILS (i.e. the hostile input is wrongly
ADMITTED). Sol predicts ALL of them fail. If any test shows current code already blocking the attack,
your test is too weak — strengthen it until it exercises the real hole. Quote real output.
Do NOT fix the validator yet. Do NOT commit. This rung's deliverable is: the tests exist and current code
demonstrably fails them.`,
  { label: 'rung 1: hostile tests (must FAIL now)', phase: 'RedTests' })

phase('Entailment')

const entail = await agent(`${LAW}\n${BURN}

Rung 1 landed — hostile tests exist and current code fails them:
${String(red).slice(0, 1400)}

YOUR TASK — SOL LADDER RUNG 2: REPLACE LEXICAL ENTAILMENT. This is the core fix.
report_ast.py:434's check (digit presence + 25% bag-of-words) must become a REAL entailment check for an
ATTRIBUTED clause against its span. It must verify, at minimum:
  * POLARITY / DIRECTION: rose vs fell, increased vs decreased, positive vs negative, more vs less. A
    clause asserting the opposite direction of its span is REJECTED. (This is burn #1, the worst one.)
  * NUMBERS: every numeric quantity in the clause (INCLUDING SINGLE DIGITS and spelled numbers) must
    appear in the span with the SAME UNIT. "1.5 points" != "1.5 percent". Remove the single-digit
    exemption (:449) and the unconditional year exemption (:40/:449).
  * MODALITY / HEDGING: "may reduce" vs "reduces" vs "did not reduce" are different claims.
  * COMPARATOR / SCOPE: the population/unit/comparator the clause asserts must be supported by the span.
Prefer an approach that is deterministic where it can be (sign/number/unit extraction) and falls back to a
constrained LLM entailment judge (MATCH / NO_MATCH / UNCERTAIN with the span excerpt that decided it) for
the semantic residue — UNCERTAIN must FAIL CLOSED (reject), never admit. A legal/doctrinal clause has NO
number: absence of a number must NOT auto-pass or auto-fail; it routes to the semantic check.

Re-run scripts/test_fabrication_paths.py: T1/T1b/T1c/T1d MUST now PASS (attack rejected). Do NOT weaken any
test. Do NOT break a TRUE attributed finding that IS entailed by its span — include a positive control that
must still ship. Canary must stay green. Report real output. Do NOT commit.`,
  { label: 'rung 2: real entailment', phase: 'Entailment' })

phase('CloseLanes')

const lanes = await parallel([
  () => agent(`${LAW}\n${BURN}

Rung 2 (real entailment) landed: ${String(entail).slice(0, 900)}

YOUR TASK — SOL LADDER RUNG 3a: close the OWNED / HEADING lanes. YOU OWN report_ast.py's Owned + Heading
handling and cellcog_composer.py's abstract.
  * OWNED with NO premises must NOT be an unrestricted factual lane (report_ast.py:611). An OWNED sentence
    may carry NO new particular: no digit, no SPELLED number ("doubled", "fatal", "half"), no novel named
    entity not present in its premises. A premise-free OWNED node that makes a factual claim is REJECTED.
    ** The released abstract (composer:387) uses this bypass -- the abstract must now pass through the same
    OWNED/ATTRIBUTED gate as every other sentence, or be built from admitted nodes. **
  * HEADINGS (report_ast.py:540) are currently validated only for non-emptiness and SKIPPED by the
    publisher (publisher.py:186). A heading may carry NO factual assertion / no number / no attribution
    claim — or it must receive a receipt like any other node. Close it: "## Acemoglu proves that 47% ..."
    must be REJECTED.
Re-run test_fabrication_paths.py: T2, T2b, T3 must now PASS. Positive control: a legitimate OWNED synthesis
("these findings concern different units and are not directly comparable") and a normal heading
("Employment effects") must still ship. Canary green. Do NOT commit.`,
    { label: 'rung 3a: owned + heading lanes', phase: 'CloseLanes' }),

  () => agent(`${LAW}\n${BURN}

Rung 2 (real entailment) landed: ${String(entail).slice(0, 900)}

YOUR TASK — SOL LADDER RUNG 3b: close the TABLE / CONNECTIVE / VENUE lanes. YOU OWN report_ast.py's
EvidenceTable, the connective handling, and names_a_source().
  * EVIDENCE TABLE (report_ast.py:624/:670) prints the MODEL-AUTHORED claim and unvalidated level/method.
    Every printed cell must be VALIDATED against the span the same way an attributed clause is (numbers,
    polarity, units), and level/method must either come from a span-verified facet or NOT be printed. A row
    whose claim reverses its span, or whose level/method is invented, is REJECTED. The sidecar must record
    the REAL cells the judge reads, not an opaque TABLE_ROW::<id>.
  * CONNECTIVES (report_ast.py:548): "while/whereas/by contrast/but/yet" assert a RELATION that neither
    span-check tests. Either forbid model-chosen contrastive connectives entirely (the relation must come
    from a proof-carrying planner verdict, not the writer), or verify the asserted relation. Two positive
    unrelated findings joined by "by contrast" is REJECTED.
  * VENUE (report_ast.py:235): names_a_source() adds only authors, never venues. "Science reports ..."
    under an AER card is a fabricated attribution and must be REJECTED. Add venue detection; and handle
    sub-4-char / full-name author matches (a surname alone must not evade the check).
Re-run test_fabrication_paths.py: T4, T5, T6 must now PASS. Positive controls must still ship. Canary
green. Coordinate with rung-3a: you both edit report_ast.py — 3a owns Owned+Heading, you own
EvidenceTable+connective+names_a_source. Do NOT touch each other's functions. Do NOT commit.`,
    { label: 'rung 3b: table + connective + venue', phase: 'CloseLanes' }),
])

phase('Verify')

const verify = await agent(`${LAW}\n${BURN}

The entailment fix + all lane closures are in:
${String(entail).slice(0, 600)}
${lanes.filter(Boolean).map((r,i)=>`--- lane ${i+1} ---\n${String(r).slice(0,600)}`).join('\n')}

YOU ARE A FRESH ADVERSARY. You did not build any of this. Your job is to prove the six burns are CLOSED —
and to find a SEVENTH Sol did not name.

 1. Run scripts/test_fabrication_paths.py — EVERY hostile test (T1..T7) must now REJECT its attack, and
    the positive controls must still SHIP. Quote real output.
 2. Then go BEYOND the written tests (this is the whole lesson: the suite only tests what we imagined).
    Attack the REAL validator directly:
      - a sign flip using SYNONYMS ("climbed" vs "declined", "gains" vs "losses")
      - a spelled-number fabrication ("tripled", "a majority", "most")
      - a scope swap ("in the US" -> "globally") with identical numbers
      - a modality flip ("is associated with" -> "causes")
      - an OWNED sentence naming a source obliquely ("the Cambridge team")
      - a table row with a real number but wrong sign
      - the abstract path specifically (Sol: the released abstract used the bypass)
    For each: HELD or BROKEN, with file:line and the exact input.
 3. Rebuild scripts/test_gate_is_wired.py so it DRIVES THE REAL VALIDATOR on bound fixtures and includes
    the fabrication tests — a green canary must now MEAN something. Confirm nothing was weakened
    (git diff on the test file must ADD checks, never remove).
 4. Verify a TRUE attributed finding, a legitimate OWNED synthesis, and a normal heading still SHIP.

Report ONLY what you executed; quote real output. If ANY attack still lands, name it — we are not done
until a fresh adversary cannot break it AND Sol re-reviews. Do NOT commit.`,
  { label: 'fresh adversary: prove burns closed + find #7', phase: 'Verify' })

return { red: String(red).slice(0,600), entail: String(entail).slice(0,600), lanes: lanes.filter(Boolean).length, verify }
