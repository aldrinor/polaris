export const meta = {
  name: 'finalize-fabrication-safe',
  description: "Fix the fail-closed false-positives (deterministic ADMIT for provably-entailed clauses), close P0 hops 5 & 7, then ONE unified fresh adversary over the whole validator surface. Ends ready for Sol re-review.",
  phases: [
    { title: 'FalsePos', detail: 'deterministic pre-filter ADMITS a provably-entailed clause without the judge; fail-closed only on the semantic residue' },
    { title: 'P0hops', detail: 'hop 7: alignment_census segments the cover sheet; hop 5: event_ledger _ACCEPTED_STAMP matches provenance._AM_MARK' },
    { title: 'UnifiedAttack', detail: 'one fresh adversary: all 8 burns + false-positives + P0 hops 4-7 + hunt #9; canary must be GREEN for the RIGHT reason' },
  ],
}

const ROOT = '/home/polaris/wt/flywheel'

const LAW = `
=== THE LAW ===
ATTRIBUTED sentence -> ENTAILED by its source's verbatim span (direction, number+unit, modality, scope).
OWNED -> reviewer's voice, no source (oblique or direct), no new particular, no bare empirical finding.
An ACCEPTED MANUSCRIPT is never the journal version. Fail closed on uncertainty -- BUT a validator that
rejects TRUE findings when its judge is unreachable is output-dead, not safe.

=== STATE (verified by me, the orchestrator, running the tests myself) ===
* 8/8 fabrication burns are behaviourally CLOSED (synonym/magnitude/scope/modality/table/venue/verdict/
  oblique-source). The real entailment judge is on the path and fails closed. Independently confirmed.
* BUT the canary is RED on 2 FALSE POSITIVES: 'a TRUE finding reaches the page' and 'CROSS-SOURCE SYNTHESIS
  survives'. Cause: the judge fails closed, and in the test env there is no judge stub, so it rejects
  LEGITIMATE entailed findings. This is the turn-1 failure (163 real sentences deleted) resurfacing.
* P0 hops 5 & 7 are OPEN (an accepted manuscript can be ruled the journal at two hops before the final
  citation gate).
`

phase('FalsePos')

const fp = await agent(`${LAW}

YOUR TASK: fix the fail-closed FALSE POSITIVES without weakening any fabrication check.
File: ${ROOT}/scripts/report_ast.py, entailed_by_span + the OWNED empirical judge path.

THE FIX (Sol's exact spec -- deterministic where it can be, judge only for the residue):
 1. The deterministic PRE-FILTER must be able to ADMIT, not only reject. A clause is PROVABLY ENTAILED --
    and admitted WITHOUT calling the judge -- when it is a structural subset of the span:
      * every number in the clause appears in the span with the same unit, AND
      * every direction/polarity word is consistent with the span (no opposition), AND
      * the clause introduces NO entity/scope/modality term absent from the span, AND
      * (strongest, cheapest) the clause's content words are a subset of the span's content words with no
        added qualifier.
    If all hold, ADMIT deterministically. The judge is for the SEMANTIC RESIDUE only -- a clause that
    restates/paraphrases and cannot be proven a subset.
 2. FAIL-CLOSED STILL APPLIES TO THE RESIDUE: a clause that is NOT provably entailed and whose judge is
    unreachable/UNCERTAIN is REJECTED. But a clause the pre-filter can PROVE is entailed must ship even
    with no judge available -- it is not gated on model availability.
 3. Same for the OWNED cross-source-synthesis lane: a legitimate 'different units, not directly comparable'
    verdict that is structurally licensed must ship without a live judge.

VERIFY (run yourself, quote real output):
 * scripts/test_gate_is_wired.py -> the 2 false-positive checks ('TRUE finding reaches the page',
   'CROSS-SOURCE SYNTHESIS survives') must now PASS, WITH NO JUDGE STUB INJECTED (that is the failing
   condition today).
 * ALL fabrication attacks (synonym/magnitude/scope/modality/table/venue/verdict/oblique) still REJECT.
   The synonym attack ('plunged') must STILL be rejected -- it is NOT a subset of the span (opposite
   direction), so it goes to the judge and fails closed. Prove 'plunged' still dies.
 * scripts/test_fabrication_paths.py still all green.
Do NOT weaken a test. Do NOT touch provenance/alignment_census/event_ledger/acquisition/source_router/
routes_*/cellcog_composer. Do NOT commit. Report file:line + real output.`,
  { label: 'fix fail-closed false positives', phase: 'FalsePos' })

phase('P0hops')

const p0 = await agent(`${LAW}

YOUR TASK: close P0 hops 5 & 7. An accepted manuscript is ruled the journal at two hops before the final
citation gate. Both were found by a fresh adversary, both pinned:

HOP 7 (severest) -- ${ROOT}/scripts/alignment_census.py:111 is_publisher_typeset -- THE COUNTERFEIT TYPESET.
  It rules a doc publisher-typeset on >=3 page-folios inside the declared page range, but NEVER SEGMENTS
  OFF THE REPOSITORY COVER SHEET. A Nature Communications accepted manuscript whose COVER SHEET cites
  '14(1): 1-12' and whose body paginates from 1 is ruled the JOURNAL ARTICLE (folios 1-10 land in [1,12]).
  declared_page_range (:54), folio_numbers (:49), page_top_heads (:73) all scan the WHOLE text including
  the cover sheet. FIX: segment the cover sheet off FIRST (provenance.segment_cover_sheet /
  event_ledger.segment_front_matter already exist -- reuse one), then derive typeset facts from the
  article body only. On the SAME bytes, provenance.derive_expression_kind correctly returns
  accepted_manuscript -- the census must AGREE with it, not overrule it.

HOP 5 -- ${ROOT}/scripts/event_ledger.py:411 _ACCEPTED_STAMP -- DETECTOR DRIFT. Hop 6 widened
  provenance._AM_MARK (:441) to catch the NIH tell ('author manuscript;? *available in pmc',
  '\\bnihms\\s*\\d{3,}'); that clause was NEVER added to event_ledger's _ACCEPTED_STAMP. The two
  accepted-manuscript detectors have DIVERGED. FIX: make them ONE shared detector (import provenance's, or
  a shared module) so they cannot drift again -- 'which stamps mark an accepted manuscript' must be a
  STATEMENT IN ONE PLACE, not duplicated. Prove: an NIH manuscript ('Author manuscript; available in PMC
  2026' + 'NIHMS2075474') -> event_ledger.derive_eligibility gives accepted_manuscript / NOT admissible,
  matching provenance.

VERIFY: build the two failing fixtures (the Nature Comms cover-sheet AM, the NIH AM) and show BOTH lanes
(census AND event_ledger) now rule them accepted_manuscript / inadmissible, agreeing with provenance.
Also confirm a REAL PMC VoR JATS is still ADMISSIBLE (no over-rejection). canary must stay green (or
greener). Do NOT touch report_ast.py (another agent owns it). Do NOT commit. Report file:line + real output.`,
  { label: 'close P0 hops 5 & 7', phase: 'P0hops' })

phase('UnifiedAttack')

const attack = await agent(`${LAW}

Two fixes just landed:
FALSE-POSITIVE FIX: ${String(fp).slice(0, 900)}
P0 HOPS 5&7: ${String(p0).slice(0, 900)}

YOU ARE THE UNIFIED FRESH ADVERSARY. You built none of this. Attack the WHOLE validator surface -- the
fabrication lanes AND the accepted-manuscript P0 -- and hunt for #9. This is the pass that decides whether
it is ready for Sol.

RUN, quoting real output:
 1. scripts/test_gate_is_wired.py AND scripts/test_fabrication_paths.py -> BOTH GREEN, and green FOR THE
    RIGHT REASON: attacks rejected, true findings + synthesis + framing SHIP. git diff on both test files
    must show NOTHING WEAKENED.
 2. ALL 8 fabrication burns, re-derived: synonym sign-flip (plunged/cratered/went south), magnitude
    (doubled), scope (worldwide vs US), modality verb+noun (causes / the collapse of), wrong-quantity,
    number-word, table sign-flip, connective, venue (Science under AER), oblique-source OWNED
    (The Cambridge team found / a Stanford study reported / lone MIT found), bare empirical OWNED.
 3. THE P0, all hops: a repository accepted manuscript (cover sheet cites the journal + from-1 body),
    an NIH manuscript (Author manuscript; NIHMS), a submittedVersion, a CORE record where fullText is the
    AM but downloadUrl is the VoR. NONE may be ruled JOURNAL_ARTICLE/ADMISSIBLE at ANY hop (census,
    event_ledger, resolve_attribution). Provenance/census/ledger must all AGREE it is accepted_manuscript.
 4. THE FALSE-POSITIVE regression: with NO judge stub, a TRUE entailed finding, a legitimate cross-source
    synthesis, and a framing transition ALL SHIP. And a true finding whose judge is UNREACHABLE but which
    the pre-filter can PROVE entailed SHIPS; a paraphrase that needs the judge and can't reach it REJECTS.
 5. HUNT #9: attacks nobody scripted. Try: a fabrication split across a clause boundary; an OWNED sentence
    that frames AND smuggles ('turning to the economy, where the effect reverses'); a number matching the
    span but wrong sign via a symbol; a venue via abbreviation ('AER' vs 'Nature'); a manuscript whose
    cover sheet is >1 page.

For each: HELD or BROKEN, file:line, exact input. If ANYTHING lands, name it -- we are NOT ready for Sol.
If NOTHING lands after a genuine effort, say so explicitly and list what you tried. Do NOT commit.`,
  { label: 'unified adversary: whole surface + #9', phase: 'UnifiedAttack' })

return { fp: String(fp).slice(0,600), p0: String(p0).slice(0,600), attack }
