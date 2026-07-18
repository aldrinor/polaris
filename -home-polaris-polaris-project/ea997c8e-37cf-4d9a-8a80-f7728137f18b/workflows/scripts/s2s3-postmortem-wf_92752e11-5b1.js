export const meta = {
  name: 's2s3-postmortem',
  description: 'Root-cause WHY S2/S3 silently lost source metadata (DOI/journal/tier) it plainly had, and design a GENERAL fail-loud invariant + regression test so this class of silent data-loss can never recur on any query.',
  phases: [
    { title: 'Root cause', detail: 'read the real S2/S3 code: where metadata SHOULD be captured and why it was not' },
    { title: 'Prevention', detail: 'design a query-agnostic fail-loud invariant + regression test' },
    { title: 'Gate', detail: 'Fable: is the cause real + is the guard genuinely general, not overfit', model: 'fable' },
  ],
}

const CTX = `
POST-MORTEM. What went wrong (measured, on the real 329-basket corpus): S2/S3 produced a cp3 corpus
where only 3/995 evidence rows had a DOI and 3/995 had a journal name, and 253/995 were tier=UNKNOWN
— even though the metadata was PLAINLY PRESENT in each row's own direct_quote text and source_url
(e.g. Acemoglu-Restrepo's row literally contains "Journal of Economic Perspectives" and DOI
10.1257/jep.33.2.3, yet its doi/journal fields were blank). A trivial downstream deterministic pass
(regex DOI + domain->venue map) recovered doi 3->240, journal 3->294, and cut UNKNOWN 253->145.
So S2/S3 SILENTLY DROPPED metadata it had in hand. Consequences: good peer-reviewed sources got
mislabeled UNKNOWN (looks low-quality), instruction-following on journal-demanding tasks tanked, and
nothing anywhere FAILED or warned — the corpus looked fine.

READ-ONLY: read the S2/S3 code but DO NOT WRITE to /home/polaris/wt/s2s3 (a fix wheel is editing it).
Read from /workspace/POLARIS/src (or the s2s3 worktree) read-only; write any findings to
/home/polaris/polaris_project/s2s3_postmortem.md ONLY. The proven recovery logic is at
/home/polaris/wt/outline_agent/scripts/repair_corpus_metadata.py. Corpus: cp3_basket_snapshot.json
(995 rows). Be concrete: file:line for the failure. Honest — if the extractor was never written vs
written-but-never-called vs silently-excepted, say which.
`

const CAUSE_SCHEMA = {
  type: 'object', required: ['mechanism', 'file_line', 'failure_class'],
  properties: {
    mechanism: { type: 'string', description: 'the ACTUAL reason metadata was lost — at file:line' },
    file_line: { type: 'string' },
    failure_class: { enum: ['never_written', 'written_never_called', 'silently_excepted', 'dropped_in_transform', 'wrong_default', 'other'] },
    was_silent: { type: 'boolean', description: 'did anything fail/warn, or did the bad corpus look fine' },
    other_silent_losses: { type: 'array', items: { type: 'string' }, description: 'other places in S2/S3 that could silently drop data' },
    evidence: { type: 'string' },
  },
}
const PREVENT_SCHEMA = {
  type: 'object', required: ['invariant', 'is_query_agnostic', 'test'],
  properties: {
    invariant: { type: 'string', description: 'the fail-loud check: e.g. post-S3, if direct_quote matches DOI_RE then doi MUST be set; if domain in KNOWN_JOURNALS then tier != UNKNOWN — fail loud with counts' },
    is_query_agnostic: { type: 'boolean', description: 'does it work for ANY topic/query, not just AI-labor' },
    test: { type: 'string', description: 'the regression test that would have caught this, and catches it on any future query' },
    where_it_runs: { type: 'string', description: 'where in the pipeline the invariant is enforced so it triggers on every run' },
    false_positive_risk: { type: 'string' },
  },
}

phase('Root cause')
const cause = await agent(
  `${CTX}\n\nROOT-CAUSE it. Find where S2 stamps/enriches evidence rows and where S3 consolidates them.
Determine EXACTLY why doi/journal stayed blank and tier stayed UNKNOWN when the data was in the row's
own text. Was the extractor never written? written but never called? called but silently swallowed an
exception? populated then dropped in a later transform/serialization? a wrong default? Give the
mechanism at file:line, whether it failed SILENTLY, and list any OTHER spots in S2/S3 that could
silently drop data the same way.`,
  { label: 's2s3:root-cause', phase: 'Root cause', schema: CAUSE_SCHEMA },
)

phase('Prevention')
const prevent = await agent(
  `${CTX}\n\nGiven the root cause:\n${JSON.stringify(cause, null, 2)}
Design the PREVENTION so this class of silent metadata-loss can NEVER recur on ANY query. It must be:
(1) a FAIL-LOUD INVARIANT enforced on every S2/S3 run — e.g. after consolidation, assert that any row
whose direct_quote/url contains a DOI pattern has doi populated, and any row from a known-journal
domain is not tier=UNKNOWN; if violated, FAIL LOUD with the offending counts (not a silent pass).
(2) QUERY-AGNOSTIC — it must hold for a finance query, a medical query, anything, not just AI-labor.
Use structural signals (DOI regex, domain class), never topic keywords.
(3) a REGRESSION TEST that reproduces this exact failure and would have caught it, and keeps catching
it. State WHERE the invariant runs so it fires on every future corpus build. Note false-positive risk
(e.g. a genuine non-journal source correctly having no DOI must not trip it).`,
  { label: 's2s3:prevention', phase: 'Prevention', schema: PREVENT_SCHEMA },
)

phase('Gate')
const gate = await agent(
  `${CTX}\n\nYOU ARE FABLE. Judge the post-mortem.
ROOT CAUSE: ${JSON.stringify(cause, null, 2)}
PREVENTION: ${JSON.stringify(prevent, null, 2)}
Answer: (1) Is the root cause the REAL mechanism (file:line verified), or a plausible guess? (2) Is the
prevention GENUINELY query-agnostic and fail-loud — would it catch this on a finance/medical corpus
too, and would it have failed the original bad run instead of passing it silently? (3) Is there a
BROADER lesson — is silent data-loss-without-failure a pattern elsewhere in the pipeline (the corpus
'looked fine' while being broken)? (4) The single most important guard to add so 'looks fine but is
silently broken' cannot ship again. Be blunt; the operator called this a fatal, stupid mistake and
wants it structurally impossible to repeat.`,
  { label: 's2s3:fable-gate', phase: 'Gate', model: 'fable', effort: 'high' },
)

log(`S2S3 postmortem: class=${cause?.failure_class} silent=${cause?.was_silent} | guard query-agnostic=${prevent?.is_query_agnostic}`)
return { cause, prevent, gate }
