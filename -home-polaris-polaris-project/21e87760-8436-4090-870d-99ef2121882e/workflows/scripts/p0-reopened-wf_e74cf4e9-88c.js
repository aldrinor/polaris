export const meta = {
  name: 'p0-reopened',
  description: "The adversary found the accepted-manuscript P0 REOPENED at a 4th hop (alignment_census ruling-ladder order). Close it, then re-run all 11 of Sol's tests, then fire the fetch.",
  phases: [
    { title: 'Close', detail: 'fix the ruling-ladder order + the test that holds only by luck + the 2 unverified' },
    { title: 'Reattack', detail: "re-run Sol's 11 tests from scratch — a DIFFERENT adversary" },
    { title: 'Fetch', detail: 'only if 11/11 hold: launch the detached fetch' },
  ],
}

const ROOT = '/home/polaris/wt/flywheel'

const LAW = `
=== THE LAW ===
An ACCEPTED MANUSCRIPT is NOT the journal version. Peer review changes numbers: Acemoglu's robot effect is
0.37pp in the NBER working paper and 0.2pp in the published JPE. A span may name a journal ONLY if that
exact span is verified in the journal's own bytes. \`${ROOT}/scripts/test_gate_is_wired.py\` must stay GREEN;
NEVER weaken a check to make it pass.

=== WHY THIS IS URGENT ===
We are about to fetch ~5,000 candidates. If an accepted manuscript can be cited as the journal article,
EVERY ONE OF THEM ARRIVES PRE-POISONED and the whole haul must be burned. The fetch is BLOCKED until this
is closed and independently re-verified.
`

const FINDING = `
=== THE ADVERSARY'S VERDICT ON SOL'S 11 TESTS ===
   8 hold
   1 holds ONLY BY LUCK — and the adversary broke it
   2 were verified ONLY via the builder's own suites (i.e. NOT independently verified)

FINDING 1 — THE P0 IS REOPENED:
   "scripts/alignment_census.py:140 — the \`acceptedVersion -> INADMISSIBLE\` branch sits BELOW [an earlier
    branch in the ruling ladder]"
The accepted-manuscript P0 was patched at THREE hops (provenance.py SPAN_PRESERVING, version_align.py:220,
alignment_census.py:140) and IS STILL OPEN AT A FOURTH — the ORDER of the rules in the ruling ladder means
an earlier branch admits the manuscript before the INADMISSIBLE branch is ever reached.

This is the same disease as everything tonight: THE FIX WAS APPLIED AND THE PATH REMAINED OPEN.
Read the full adversary report in the workflow transcript before you touch anything.
`

phase('Close')

const close = await agent(`${LAW}\n${FINDING}

YOUR TASK: CLOSE THE P0 AT THE FOURTH HOP, AND FIX THE OTHER TWO PROBLEMS THE ADVERSARY FOUND.

 1. \`scripts/alignment_census.py\` — THE RULING LADDER. The \`acceptedVersion -> INADMISSIBLE\` branch sits
    BELOW an earlier branch that admits the manuscript first. FIX THE ORDER — and do not merely reorder:
    make the ordering IMPOSSIBLE TO GET WRONG AGAIN. An acceptedVersion / submittedVersion /
    working-paper / preprint manifestation must be INADMISSIBLE under a journal-only policy NO MATTER
    WHICH BRANCH EVALUATES IT FIRST. Prefer a structure where inadmissibility is a PRECONDITION checked
    before any admitting branch can run, not a rule competing in a ladder.
    (Sol's principle: "which edges are inert must be a STATEMENT, not an absence from a tuple." Apply the
     same principle here: which VERSIONS are inadmissible must be a STATEMENT, not an ordering accident.)

 2. THE TEST THAT "HOLDS ONLY BY LUCK" — the adversary broke it. Find it in the transcript, understand why
    it passes only incidentally, and make it hold BY CONSTRUCTION.

 3. THE TWO TESTS VERIFIED ONLY VIA THE BUILDER'S OWN SUITES — they are NOT independently verified. Build
    real, independent checks for them. (A builder's own suite is exactly what has fooled us four times
    tonight: provenance.py passed 18/18 while the P0 it was written to stop ran live on disk.)

 4. AUDIT EVERY OTHER PLACE a version label could grant journal attribution. The P0 has now been found at
    FOUR hops. Assume there is a FIFTH. Grep for every path from a version/expression label to an
    admissibility or attribution decision, and make them all route through ONE reducer that cannot be
    bypassed.

Run \`python scripts/test_gate_is_wired.py\` after every change (must stay green). Report file:line for
every change, and what you RAN to prove the P0 is closed at ALL hops. Do NOT commit.`,
  { label: 'close the P0 (4th hop)', phase: 'Close' })

phase('Reattack')

const reattack = await agent(`${LAW}\n${FINDING}

An agent just closed the P0 at the fourth hop and fixed the weak tests:
${String(close).slice(0, 2000)}

YOU ARE A FRESH ADVERSARY. You did not build this and you did not run the previous attack. RE-RUN ALL
ELEVEN OF SOL'S REQUIRED TESTS FROM SCRATCH. Do not trust the previous adversary's 8/11 — re-derive
every one yourself.

  1.  A PMC VoR JATS becomes ADMISSIBLE.
  2.  An NIH / ACCEPTED MANUSCRIPT REMAINS NON-VoR.  ** THIS IS THE P0. It has now been found REOPENED
      at a FOURTH hop after being patched at three. ASSUME THERE IS A FIFTH. Attack it from every
      direction: a repository saying acceptedVersion; a submittedVersion; a manifestation whose bytes are
      an accepted manuscript but whose METADATA claims the journal; an OAI record with a misleading
      version field; a CORE record whose fullText is the AM but whose downloadUrl points at the VoR. **
  3.  The Parry / Yang-Hui He WRONG-WORK case is QUARANTINED (a theorem-proving arXiv paper was once filed
      under an HR journal article by title match).
  4.  The Acemoglu 0.37 / 0.2 mismatch CANNOT ALIGN (WP says 0.37pp, JPE says 0.2pp — a SpanCorrespondence
      between them must FAIL).
  5.  An independently matching VoR span CAN be rebound to the VoR manifestation.
  6.  A SHORT LEGAL JUDGMENT is recognised as COMPLETE (no word floor).
  7.  A complete REGISTRY RECORD does not need article-length prose.
  8.  A 429 NEVER becomes SEARCHED_NONE / "no OA copy exists".
  9.  ONE ROUTE CANNOT INHERIT ANOTHER ROUTE'S MANIFESTATION.
  10. MULTIPLE WORKER PROCESSES stay inside the host budget (the scheduler uses a flock'd file — prove it
      with 2+ real concurrent processes).
  11. TRUNCATED or HTML-ERROR downloads CANNOT ENTER SYNTHESIS.

For each: state HOLDS or BROKEN. If BROKEN, name file:line and the exact failing input.
Then \`python scripts/test_gate_is_wired.py\` must be GREEN, and \`git diff\` on the verifier files must show
NOTHING deleted or loosened — if a check was weakened to pass, that is the WORST outcome; say so loudly.

Report ONLY what you executed. Quote real output. ** The fetch does not run unless you report 11/11. **`,
  { label: 'fresh adversary: 11 tests', phase: 'Reattack' })

phase('Fetch')

const fetch = await agent(`${LAW}

The P0 was closed and a fresh adversary re-ran all 11 tests:
${String(reattack).slice(0, 2500)}

** IF THE ADVERSARY DID NOT REPORT 11/11, STOP. Do not fetch. Report what is still broken and return. **

If 11/11 HOLD: LAUNCH THE FETCH. This is the corpus that decides whether we hit SOTA.

Our corpus is TEN journal works. The #1 system has ~98. The argument planner found ZERO genuine
cross-source conflicts in 10 papers — it is STARVED, and it is our biggest score lever (w=0.0800).

QUEUE (already warm — a resolver has been running):
  outputs/acquisition_campaign/resolved_locations.json  — ~500 works already resolved to OA locations
                                                          (99.2% hit rate; only 4 genuine no-OA; 0 throttled)
  outputs/acquisition_campaign/citation_graph_candidates.json  — a recovery agent is writing ~4,656 more
  outputs/acquisition_campaign/canon_and_contrasts.json        — + the canon (incl. Acemoglu-Restrepo's
                                                                  REAL JPE article, which we lack)
  RE-GLOB THE DIRECTORY each pass so late-arriving files are picked up automatically.

THE RUNNER MUST:
 * LAUNCH DETACHED — \`setsid nohup python <runner> > outputs/acquisition_campaign/fulltext_run.log 2>&1 &\`
   ** TWO PREVIOUS FETCHERS DIED SILENTLY AT ~63 SECONDS because they ran inside an agent turn. **
   Confirm it is alive and blobs are appearing, then RETURN. Do NOT block your turn.
 * CHECKPOINT every outcome immediately (resumable; on restart skip units already terminal).
 * WAVE ORDER: (1) re-derive identity/completeness for bytes we already hold; (2) cheap exact-ID —
   PMC/EuropePMC/DOAJ/Unpaywall/OpenAlex/S2; (3) CORE, OpenAIRE, Zenodo; (4) targeted OAI-PMH from the
   OAI ids those return; (5) title+author ONLY after exact identifiers fail.
 * FETCH ORDER per candidate: PMC JATS / official structured full text > publisher OA VoR > repository
   bytes whose OWN FRONT MATTER proves they are the VoR > accepted manuscript > preprint.
 * A PUBLISHER URL GETS ONE ATTEMPT. A 403 ends that URL and ADVANCES TO REPOSITORIES. (Last run burned
   its whole budget on 403 walls: zero 429s, twenty-four 403s.)
 * STOP RULE: once a complete, identity-confirmed, policy-admissible manifestation is obtained, cancel the
   remaining lower-priority work for that candidate.
 * PRIORITISE the EMPTY CELLS (manufacturing/retail/finance/education/agriculture/transport — 0 papers
   each) and the 2023-2025 frontier, then by weighting.py quality.
 * HONEST OUTCOMES: 429 -> THROTTLED (retriable) | 401 -> AUTH_FAILED | 403 -> ACCESS_DENIED (that URL) |
   timeout/5xx -> BACKEND_FAILED. ** NONE may reduce to "no OA copy exists." **

Report: the launch command, PROOF it is running (tail the log, show blobs appearing), the streaming
outcome histogram, and the current STRICT JOURNAL-ATTRIBUTABLE count. Do NOT commit.`,
  { label: 'launch the fetch', phase: 'Fetch' })

return { close: String(close).slice(0, 800), reattack, fetch: String(fetch).slice(0, 1500) }
