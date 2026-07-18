export const meta = {
  name: 'gate-inversion-B2',
  description: 'Phase B iteration: add the lossless CLAUSE LEDGER so NO stated constraint can silently drop (deontic-driven constraint detection + clause-disposition completeness + OPAQUE preservation + quality/negation/coordination parsers). Offline. Faithfulness FROZEN.',
  phases: [
    { title: 'Recon', detail: 'current clause handling + deontic lexicon + monotonicity validator' },
    { title: 'Build', detail: 'clause ledger + completeness + OPAQUE + parsers' },
    { title: 'Verify', detail: 'all 4 probes pass losslessly + fuzz + faithfulness' },
    { title: 'Commit', detail: 'commit local on gate-inversion' },
  ],
}

const GUARD = `
HARD GUARDRAILS:
- EDIT ONLY /home/polaris/wt/outline_agent on branch gate-inversion (build on commit 11b8fc3). NEVER edit /home/polaris/wt/flywheel.
- FAITHFULNESS FROZEN: never touch src/polaris_graph/generator/provenance_generator.py / strict_verify. READ ONLY.
- Fully behind default-OFF PG_GATE (OFF byte-identical to champion).
- Do NOT run live retrieval/compose (10-min cap). The compiler LLM call is fast (allowed for verify: source .env, PG_PLANNING_GATE_LIVE=1).
CONTEXT: Phase B (commit 11b8fc3) inverted authority so DETERMINISTIC constraints can't be dropped — but the monotonicity guarantee only covers constraints the deterministic layer EXTRACTS. Constraints with no deterministic extractor (quality 'high-quality', 'company press releases' not in ontology, 'do not cite blogs' exclusion) are INVISIBLE to the validator, so the LLM still silently drops them. Verdict verbatim: "the monotonicity validator only checks that DETERMINISTIC candidate ids survived ... constraints with no deterministic extractor are invisible to it, so when the LLM omits them nothing fails."
SPEC: /home/polaris/polaris_project/GATE_REVIEW_VERDICT.md + Sol's clause-ledger design in /tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/reviews/sol_situation_review.md (section 3 'Generality mechanism' — the lossless ledger).
`

phase('Recon')
const recon = await agent(`${GUARD}
RECON (read-only): map what's needed to add a lossless clause ledger to the CURRENT (post-inversion) compiler. Read src/polaris_graph/planning/research_planning_gate.py (the deterministic-authoritative core built in Phase B, the monotonic merge, validate_monotonicity), planning_gate_schema.py (ContractTerm IR incl. normalization_status/operator added in Phase B; is there an OPAQUE status?), candidate_adapter.py (the registry + parsers). Find the DEONTIC/modal lexicon (grep 'restrict_hard', 'only', modal, deontic, config/scope_ontology or a lexicon module) — what marks a phrase as a hard constraint today. Report: (1) exactly where clause segmentation would insert, (2) how the current validator decides 'survived' and why it misses non-extracted constraints, (3) what deterministic cues exist for quality / negation-exclusion / coordination('A and B') / date-hardness-inheritance, (4) whether NORM_OPAQUE exists in the IR. Cite file:line.`, { label: 'recon', phase: 'Recon' })

phase('Build')
const build = await agent(`${GUARD}
BUILD — the LOSSLESS CLAUSE LEDGER (closes the generality gap). Recon map:\n${recon}\n
Implement in src/polaris_graph/planning/:
1. CLAUSE LEDGER (deterministic): segment the prompt into stable clause/span-IDs (sentence + coordinated-phrase granularity). Every clause gets a disposition: objective | explicit_constraint | deliverable | context | unresolved. Segmentation + IDs are deterministic and owned by code.
2. DEONTIC-DRIVEN CONSTRAINT DETECTION (the key invariant): a clause carrying a modal/deontic cue ('only', 'must', 'ensure', 'do not', 'no ___', 'exclude', 'from YYYY onward', 'at least') is DETERMINISTICALLY marked constraint-bearing. Such a clause MUST yield a ContractTerm (normalized OR opaque). The LLM's disposition can ADD/refine but can NEVER downgrade a deontic-marked constraint clause to 'context'.
3. NORM_OPAQUE preservation: a constraint-bearing clause the deterministic layer cannot normalize into a known dimension becomes an OPAQUE ContractTerm (normalization_status=opaque, force from its deontic cue, the raw clause text + span, stage_owner best-guess or 'unsupported'). Preserved + disclosed, NEVER silence. Add the opaque status to the IR if missing.
4. COMPLETENESS VALIDATOR (replaces/augments the candidate-only monotonicity): assert every deontic-marked constraint clause in the ledger has a corresponding ContractTerm (normalized or opaque). If not -> fail (interactive) / preserve-as-opaque + mark degraded_lossless (autonomous). This is what makes it lossless REGARDLESS of whether a deterministic extractor exists.
5. ADD DETERMINISTIC PARSERS (generic, registry/lexicon-driven, no per-task branches): (a) QUALITY: 'high-quality'/'high quality'/'peer-reviewed'/'top-tier' -> source_quality=high (hard if under a deontic scope). (b) NEGATION/EXCLUSION: 'do not cite/use X', 'no X', 'exclude X', 'avoid X' -> content/source exclusion operator NOT_IN {X} (never a positive query token). (c) COORDINATION: 'A and B'/'A, B, or C' within a source/kind phrase -> value_set IN {A,B,C}. (d) DATE-HARDNESS INHERITANCE: 'only ... from YYYY onward' -> date GTE YYYY with force=HARD (the same 'only'-scope hardness that already works for source-language must extend to date + kind).
6. LLM stays ADDITIVE-ONLY, references clause-IDs (not offsets); per-item fail-soft unchanged.
Keep behind PG_GATE. Report exact edits (file:line) + new modules. Add unit tests for the ledger, completeness, opaque, and each new parser.`, { label: 'build:clause-ledger', phase: 'Build', effort: 'high' })

phase('Verify')
const verdict = await agent(`${GUARD}
VERIFY (compiler LLM allowed live — source .env, PG_PLANNING_GATE_LIVE=1 — NO full retrieval). On gate-inversion:
1. FAITHFULNESS: provenance_generator.py 0-diff; flywheel untouched; PG_GATE OFF byte-identical.
2. THE FULL GENERALITY PROOF — all four must now pass LOSSLESSLY (this is the whole point):
   a. Task 72 -> journal_article HARD + en HARD + **source_quality=high HARD** (previously DROPPED — must now be present), all explicit with spans.
   b. 'Only use news articles and company press releases from 2024 onward.' -> kinds IN {news_article, company_press_release} HARD (press_release previously DROPPED) + date GTE 2024 **HARD** (previously downgraded to preference). NEITHER dropped or downgraded; if company_press_release isn't in the ontology it must appear as an OPAQUE hard term, NOT silence.
   c. 'Broad overview of quantum computing.' -> no invented constraint.
   d. 'Do not cite blogs.' -> exclusion NOT_IN {blog}; never a positive query token; captured even via the live LLM path (deontic detection forces it).
   For each, assert compiler did NOT silently drop (degraded_lossless is OK ONLY if the constraint is preserved as opaque; a dropped constraint with degraded=False is a FAIL).
3. FUZZ: malformed LLM output -> all deontic-marked constraints still survive (as normalized or opaque).
4. Run tests/planning (report pass/fail; the Phase-A control-path test stays xfail).
Return a structured verdict.`, { label: 'verify', phase: 'Verify', effort: 'high', schema: {
  type: 'object', additionalProperties: false,
  required: ['faithfulness_untouched','off_path_byte_identical','task72_quality_hard','news_both_kinds_and_hard_date','exclusion_captured_live','open_no_invention','no_silent_drops','tests_passed','tests_failed','summary','risks'],
  properties: {
    faithfulness_untouched: { type: 'boolean' },
    off_path_byte_identical: { type: 'boolean' },
    task72_quality_hard: { type: 'boolean' },
    news_both_kinds_and_hard_date: { type: 'boolean' },
    exclusion_captured_live: { type: 'boolean' },
    open_no_invention: { type: 'boolean' },
    no_silent_drops: { type: 'boolean' },
    tests_passed: { type: 'integer' },
    tests_failed: { type: 'integer' },
    summary: { type: 'string' },
    risks: { type: 'array', items: { type: 'string' } },
  },
} })

phase('Commit')
const commit = await agent(`${GUARD}
COMMIT (local only, do NOT push). On gate-inversion: clean __pycache__, git add -A, commit describing the clause-ledger iteration (lossless clause ledger + deontic-driven constraint detection + completeness validator + OPAQUE preservation + quality/negation/coordination/date-hardness parsers). End with:
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Report commit hash + clean status.`, { label: 'commit', phase: 'Commit' })

return { branch: 'gate-inversion', verdict, commit: (commit||'').slice(0,160) }
