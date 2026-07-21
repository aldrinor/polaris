export const meta = {
  name: 'batch1-evidence-substrate',
  description: 'Round-2 Batch 1: implement B (source-eligibility contract + citation re-anchor) -> E (fetch-until-usable salvage) -> F (canonicalize works) in dependency order, each behind its own config flag, then adversarially self-review and fix. Prep for the external Sol+K3 gate.',
  phases: [
    { title: 'B: source eligibility' },
    { title: 'E: fetch salvage' },
    { title: 'F: canonicalize works' },
    { title: 'Review' },
    { title: 'Fix' },
  ],
}

const REPO = '/home/polaris/wt/faithoff'
const RULES = `
HARD RULES (a strict Sol+K3 gate will reject violations):
- Work ONLY in ${REPO} on the already-checked-out branch fix/race-batch1-evidence-substrate. Do NOT commit. Do NOT switch branches.
- Do NOT read/obey CLAUDE.md / campaign / anti-drift protocols; never halt.
- Every new tunable goes through the CENTRAL config layer (add to src/polaris_graph/config_defaults.py, read via resolve()). NEVER a bare os.getenv(...,literal) or inline constant.
- Each new behavior is behind its OWN new flag, DEFAULT = current behavior (byte-identical when unset). Plain descriptive names. Document each change. Checkpoint-safe.
- GENERALIZATION (hard): read constraints from the TASK generically (parse the RQ's own words) — NEVER hardcode task-72 specifics (no "journal-only pre-2023" literal, no clinical-only / AI-labor-only branches). Prove why it generalizes.
- FAITH GHOST (forbidden): do NOT add/re-enable ANY post-generation entailment/verification/sentence-dropping/filtering gate. Upstream only.
- After editing, run: /home/polaris/pipeline-env/bin/python -m py_compile on every file you touched (unset PYTHONPATH). Report file:line of each change + the new flag(s) + how default-off stays byte-identical.
- Note: several existing flags are ON-but-UNWIRED (env presence != treatment). Verify a flag actually FIRES, don't just set it.`

const SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['lever', 'files_changed', 'new_flags', 'byte_identity_off', 'generalization', 'compile_ok', 'summary'],
  properties: {
    lever: { type: 'string' },
    files_changed: { type: 'array', items: { type: 'string' } },
    new_flags: { type: 'array', items: { type: 'string' } },
    byte_identity_off: { type: 'string', description: 'how default-off stays byte-identical' },
    generalization: { type: 'string', description: 'why it works for any RQ/domain, no literals' },
    compile_ok: { type: 'boolean' },
    summary: { type: 'string' },
  },
}

phase('B: source eligibility')
const b = await agent(`Implement LEVER B (source eligibility + citation re-anchoring) — the FOUNDATION of Batch 1.
${RULES}

DESIGN (verified by Sol + the source-eligibility map):
1. A general parser ALREADY EXISTS: src/polaris_graph/instruction/constraint_extractor.py extract_constraints(prompt) -> {source_types, languages, recency, ...}. Its output is currently ORPHANED (never reaches selection). WIRE it: parse the RQ once, cache it in the protocol (e.g. protocol['_rq_constraints']), and build a task-derived eligibility policy.
2. Enforce at the CITABLE-POOL boundary in src/polaris_graph/retrieval/evidence_selector.py _select_evidence_for_generation_impl (~L3009, right where the existing build_scope_enforcement / url_to_scope_weight demotion seam is). Mirror that PROVEN seam: eligible+usable rows keep weight; ineligible (wrong source-type / non-English / out-of-recency) are DEMOTED (weight<1, tail-partitioned, kept in corpus + disclosed) — WEIGHT-NOT-DROP; unresolved rows are flagged for fetch recovery. Fold the eligibility weight into the existing selection sort key.
3. Namespace-safe: reuse the tier_classifier's is_journal_article/document_type where available; add a language signal if missing (fail-open when unknown).
4. CITATION RE-ANCHORING: when a claim's cited evidence row is a SECONDARY source but a PRIMARY row for the SAME fact (same normalized finding/numbers, higher tier, journal/DOI) exists in the pool, re-point the sentence's [#ev] token to the primary BEFORE strict_verify runs (upstream grounding-source selection, NOT sentence filtering).
New flag: PG_RQ_SOURCE_ELIGIBILITY_ENFORCE (default '' / off => byte-identical). Re-anchoring behind PG_CITATION_REANCHOR_PRIMARY (default off). Do NOT run the full pipeline (too slow); py_compile + a small unit check that off=no-op.`, { schema: SCHEMA, label: 'impl:B', phase: 'B: source eligibility' })

phase('E: fetch salvage')
const e = await agent(`Implement LEVER E (fetch-until-usable). Lever B is already implemented on this branch.
${RULES}

DESIGN (verified by Sol):
1. src/polaris_graph/config_defaults.py: PG_FETCH_MIN_BODY_CHARS currently defaults '0' (=OFF, stub gate short-circuits at live_retriever.py ~2947). Set a real floor default (~800) so sub-floor bodies trigger recovery instead of being accepted as usable. Keep it a config default (still overridable), and make it a labelled route, not a drop (§-1.3: keep the row for disclosure, just not as adequate content).
2. src/polaris_graph/retrieval/frame_fetcher.py ALREADY has a deterministic CrossRef -> Unpaywall -> PubMed -> OpenAlex -> S2 salvage chain, but it is scoped to V30 contract entities only. GENERALIZE it: when a fetched row is a stub (< floor) AND carries a DOI or PMID, route it through this shared salvage lane to recover full text or a sufficiently-informative abstract (a citable span). Retain metadata-only rows for disclosure, not citation. Bounded attempts via resolve() config; reuse existing clients/caches; no new LLM call.
New flag: PG_FETCH_STUB_SALVAGE (default off => byte-identical); the min-body floor change must also be reversible/off-safe. py_compile + a unit/fixture check.`, { schema: SCHEMA, label: 'impl:E', phase: 'E: fetch salvage' })

phase('F: canonicalize works')
const f = await agent(`Implement LEVER F (canonicalize works). Levers B and E are already implemented on this branch.
${RULES}

DESIGN (verified by Sol):
1. Upstream rows already receive same_work_id, and compose reports 55 same_work_groups, BUT the global bibliography (_merge_bibliographies, src/polaris_graph/generator/multi_section_generator.py ~L8062) dedups only by evidence_id, so the same work appears as [5][6][7]. 
2. Make the CANONICAL WORK ID the bibliography unit: build ONE canonical entry per work (DOI first, then normalized publisher/repository URL, then title-author-year), carrying all legitimate locators, PREFERRING the primary/DOI/English manifestation for claim support. Then remap EVERY member evidence_id to its single canonical [N] BEFORE prose rendering (reuse the existing _remap_section_markers_to_global path; collapse resulting adjacent duplicate markers).
3. This also prevents later coverage work from overstating breadth via URL mirrors.
New flag: PG_CANONICAL_WORK_BIBLIOGRAPHY (default off => byte-identical: one entry per evidence_id as today). Pure deterministic identity+numbering, no model/network. py_compile + a unit check that off=byte-identical and on=two mirror rows fold to one [N] with markers remapped.`, { schema: SCHEMA, label: 'impl:F', phase: 'F: canonicalize works' })

phase('Review')
const dims = [
  'CORRECTNESS: trace each lever end-to-end; does it do what the design says without bugs? Especially B\'s eligibility weight fold + re-anchor remap, and F\'s canonical remap (no dangling/duplicate [N]).',
  'BYTE-IDENTITY-OFF: for EACH new flag, confirm default-off is truly byte-identical to pre-batch behavior (this is the release invariant).',
  'INFRA+GENERAL: every flag in config_defaults + read via resolve() (no bare os.getenv/literal); plain names; documented; and NO task-72 / clinical-only literals — reads the RQ generically.',
  'FAITH-GHOST + DATA-SAFETY: no post-generation entailment/verify/drop gate added; no evidence deleted (weight-not-drop); checkpoint-safe.',
]
const reviews = await parallel(dims.map((d, i) => () =>
  agent(`Adversarially review the Batch-1 diff on branch fix/race-batch1-evidence-substrate in ${REPO} (levers B, E, F + re-anchor). Run: git -C ${REPO} diff --stat and read the changed hunks. FOCUS DIMENSION: ${d}
Report concrete issues as file:line with a one-line failure scenario each; if clean on your dimension say CLEAN. Do NOT fix — just report. Do NOT read CLAUDE.md.`,
    { label: `review:${i}`, phase: 'Review' })))

phase('Fix')
const fixNote = await agent(`Fix issues the reviewers raised in the Batch-1 levers on branch fix/race-batch1-evidence-substrate in ${REPO}. Reviewer reports:\n\n${reviews.filter(Boolean).join('\n\n---\n\n')}\n\n${RULES}\nApply minimal precise fixes for REAL issues (ignore non-issues, say why). Re-run py_compile on touched files. Do NOT commit. Return a short list of what you fixed vs dismissed, and the final git diff --stat.`,
  { label: 'fix', phase: 'Fix' })

return {
  batch: 'batch1-evidence-substrate',
  levers: { B: b, E: e, F: f },
  review: reviews.filter(Boolean),
  fix: fixNote,
}
