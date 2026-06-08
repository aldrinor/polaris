export const meta = {
  name: 'credibility-redesign-investigate-and-plan',
  description: 'Phase 2: line-by-line investigation of POLARIS pipeline subsystems against the frontier best-practice (6-layer credibility-weighted, independence-aware, both-sides design) -> a full fix/test/verify/iterate PLAN for operator approval',
  phases: [
    { title: 'Investigate', detail: '6 parallel read-only investigations of pipeline subsystems (retrieve / score / independence / aggregate+adequacy / compose / conflict+disclose) mapped to the 6 best-practice layers' },
    { title: 'Plan', detail: 'synthesize the maps + the frontier doc into the complete phased fix/test/verify plan' },
  ],
}

const FRONTIER_DOC = 'docs/frontier_credibility_intelligence_2026_06_07.md'

const MAP_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    subsystem: { type: 'string' },
    files_examined: { type: 'array', items: { type: 'string' } },
    current_behavior: { type: 'string' },
    filters_or_weights_today: { type: 'string' },
    existing_credibility_signals: { type: 'array', items: { type: 'string' } },
    gap_vs_best_practice: { type: 'string' },
    proposed_change: { type: 'string' },
    faithfulness_interactions: { type: 'string' },
    tests_needed: { type: 'array', items: { type: 'string' } },
    risks: { type: 'array', items: { type: 'string' } },
  },
  required: ['subsystem','files_examined','current_behavior','filters_or_weights_today','existing_credibility_signals','gap_vs_best_practice','proposed_change','faithfulness_interactions','tests_needed','risks'],
}

const PREAMBLE = [
  'You are investigating the POLARIS pipeline (repo root C:\\POLARIS, branch bot/I-ready-017-faithfulness) for a REDESIGN: move sourcing from a journal-only FILTER to a weighted CREDIBILITY PRIOR that is independence-aware and discloses per-claim weight + origin-count + certainty, with honest both-sides presentation on contested topics.',
  'FIRST read the frontier best-practice doc: ' + FRONTIER_DOC + ' (especially section 4, the 6 layers: retrieve / score / independence-collapse / aggregate / compose / disclose). Then read YOUR subsystem code line-by-line.',
  'READ-ONLY: do NOT modify any file. The faithfulness gates (strict_verify per-sentence provenance, 4-role D8, two-family segregation, corpus_approval) MUST be preserved and never weakened by any proposed change - call out exactly how your subsystem touches them.',
  'Be concrete: cite file:line. Distinguish what EXISTS today (signals, scores, structures we can reuse) from what is MISSING. Propose changes that are additive/re-wiring where possible, not rewrites.',
].join('\n')

phase('Investigate')
const subsystems = [
  { label: 'L0-retrieve', name: 'Retrieval / source ingestion', files: 'src/polaris_graph/retrieval/live_retriever.py, frame_fetcher.py, src/polaris_graph/agents/searcher.py, src/search/serper_client.py, src/tools/access_bypass.py, src/tools/core_client.py', q: 'How are sources retrieved and ingested? Is there ANY source-type filter or exclusion at the retrieval/ingest stage (vs at adequacy)? Does Serper already give diverse high-quality links? What metadata per source is captured (host, doi, author, venue, date) that a credibility scorer could consume? Map the retrieval->candidate->fetch flow.' },
  { label: 'L1-score', name: 'Credibility / authority scoring', files: 'src/polaris_graph/authority/source_class.py, authority_model.py, clinical_view.py, src/polaris_graph/retrieval/tier_classifier.py, src/quality/bias_detector.py', q: 'What credibility/authority signals EXIST today? Document authority_score (range, how computed), AuthorityConfidence, the tier classifier (T1-T7, signals used), source_class. Is scoring single-axis (venue/tier) or two-axis (reliability x relevance)? Is it domain-conditional (clinical vs econ/policy vs qualitative)? Where does the score get USED vs ignored? This is the core of the redesign - be exhaustive.' },
  { label: 'L2-independence', name: 'Source independence / corroboration / dedup (echo-chamber)', files: 'src/polaris_graph/synthesis/finding_dedup.py, src/utils/citation_registry.py, anything computing corroboration_count or near-duplicate/syndication detection', q: 'Is there ANY source-independence or echo-chamber / near-duplicate / syndication detection today? How is corroboration_count computed - does it count SOURCES or independent ORIGINS? (Frontier finding: nobody collapses 50 copies of one press release to ~1; this is POLARIS biggest lead opportunity.) Identify exactly where an independence-collapse step would insert and what data it needs.' },
  { label: 'L3-aggregate-adequacy', name: 'Evidence selection + corpus adequacy/approval', files: 'src/polaris_graph/retrieval/evidence_selector.py, src/polaris_graph/nodes/corpus_adequacy_gate.py, corpus_approval_gate.py, src/polaris_graph/adequacy/, src/polaris_graph/clinical_retrieval/corpus_adequacy_gate.py', q: 'How is evidence SELECTED and how is the corpus judged ADEQUATE today - by COUNT/tier-floor (filter) or by WEIGHT? Document the adequacy thresholds and whether they exclude credible non-journal sources. How would weight-based adequacy (enough weighted, independence-collapsed evidence to support the claims) replace count/tier floors? This is where drb_72 starved.' },
  { label: 'L4-compose', name: 'Composition / synthesis', files: 'src/polaris_graph/generator/multi_section_generator.py, contract_section_runner.py, analyst_synthesis.py, slot_fill.py, src/polaris_graph/agents/synthesizer.py', q: 'How is the report COMPOSED today? Does source credibility/weight influence prominence, ordering, emphasis, or conflict resolution AT ALL, or is composition weight-blind? Where would a weighted composition step (lead with high-weight evidence; attribute low-weight minority with forewarning) insert? How does composition consume evidence + provenance?' },
  { label: 'L5-conflict-disclose', name: 'Conflict detection + per-claim disclosure', files: 'src/polaris_graph/retrieval/semantic_conflict_detector.py, qualitative_conflict_detector.py, src/polaris_graph/agents/cross_reference.py, src/polaris_graph/generator/provenance_generator.py, src/utils/citation_registry.py', q: 'How are conflicts/contradictions detected and PRESENTED today (both-sides)? What is disclosed PER CLAIM today - the [#ev:id:start-end] token + strict_verify span-verdict only, or also credibility weight / certainty / origin-count? Map exactly how to extend the per-sentence token to carry {span-verdict, credibility weight, independent-origin count, certainty label}. Does conflict detection favor recall (over-detect, fail loud) per the clinical-safety requirement?' },
]
const maps = await parallel(subsystems.map(s => () =>
  agent(PREAMBLE + '\n\nYOUR SUBSYSTEM: ' + s.name + '\nFILES (start here, follow imports/callers): ' + s.files + '\nKEY QUESTIONS: ' + s.q, { label: s.label, phase: 'Investigate', agentType: 'Explore', schema: MAP_SCHEMA })
))

phase('Plan')
const valid = maps.filter(Boolean)
log('subsystem maps returned: ' + valid.length + ' of ' + subsystems.length)
const plan = await agent(
  [
    'You are the lead architect writing the COMPLETE IMPLEMENTATION PLAN for the POLARIS credibility-weighted sourcing redesign. The operator must SEE and APPROVE this plan before ANY code is written.',
    'Inputs: (1) the frontier best-practice doc at ' + FRONTIER_DOC + ' - READ IT IN FULL (the 6 layers in section 4 + the honest gap in section 3). (2) Six structured subsystem maps of our CURRENT pipeline (JSON below).',
    '',
    'Produce a rigorous markdown plan with these sections:',
    '1. GOAL + non-negotiables (faithfulness gates strict_verify/4-role/provenance/two-family preserved; no silent downgrade; domain-aware; sovereign).',
    '2. TARGET ARCHITECTURE: the 6 layers (retrieve / score(two-axis,domain-conditional) / independence-collapse / aggregate-by-weight / compose-with-forewarning / per-claim disclose) mapped onto OUR concrete files - what we REUSE (authority_score, tier_classifier, corroboration_count, conflict detectors, [#ev] token) vs what we BUILD.',
    '3. GAP TABLE: per layer, HAVE vs NEEDED vs the specific file:line change.',
    '4. PHASED DELIVERY: break into PR-sized phases (each <= ~200 LOC where possible), ordered by dependency and risk, each phase a self-contained Codex-gated unit (brief -> diff -> audit). For each phase: scope, files, the change, offline tests (incl. an adversarial volume-vs-weight test where naive count flips to the false majority - the vax case), verification, and the faithfulness-safety argument.',
    '5. TEST + VERIFY STRATEGY: unit + integration + a blinded per-claim faithfulness eval + an AuthorityBench-style adversarial benchmark; how we prove weight beats count and independence-collapse works.',
    '6. RISKS + MITIGATIONS (incl. capture-resistance: no single external rater hardwired; echo-collapse false positives; clinical safety: news must not outweigh absence of clinical evidence).',
    '7. ITERATION-TO-APPROVAL: how each phase iterates with Codex (5-iter cap) to APPROVE, and the overall acceptance bar (beat-both on the 5 golden questions, §-1.1 line-by-line).',
    '8. OPEN DECISIONS for the operator (domain weighting policy, default dissent visibility, where to start).',
    'Be concrete and honest. Prefer additive re-wiring over rewrites. Flag anything that would touch a faithfulness gate. The CURRENT-pipeline maps (JSON):',
    '',
    JSON.stringify(valid, null, 2),
  ].join('\n'),
  { label: 'redesign-plan', phase: 'Plan', agentType: 'general-purpose' }
)
return { plan: plan, maps_returned: valid.length, maps_total: subsystems.length, raw_maps: valid }
