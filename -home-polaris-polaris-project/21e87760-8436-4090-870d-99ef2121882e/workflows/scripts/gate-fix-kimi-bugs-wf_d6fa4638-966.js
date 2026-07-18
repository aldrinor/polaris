export const meta = {
  name: 'gate-fix-kimi-bugs',
  description: "Fix Kimi K3's F1-F7 gate bugs (exclusion inversion, opaque->positive-query, unanchored deontic, segmentation, coordinated exclusions, registry drift) + metamorphic tests. Offline. Faithfulness FROZEN.",
  phases: [
    { title: 'Recon', detail: 'read Kimi review + the exact bug sites' },
    { title: 'Fix', detail: 'F1-F7 per Kimi prescriptions' },
    { title: 'Verify', detail: 'metamorphic tests + faithfulness/OFF' },
    { title: 'Commit', detail: 'commit local on gate-inversion' },
  ],
}
const GUARD = `
HARD GUARDRAILS:
- EDIT ONLY /home/polaris/wt/outline_agent on branch gate-inversion (build on commit 23e2121). NEVER edit /home/polaris/wt/flywheel.
- FAITHFULNESS FROZEN: never touch src/polaris_graph/generator/provenance_generator.py / strict_verify.
- Fully behind default-OFF PG_GATE (OFF byte-identical).
- Do NOT run live retrieval/compose (10-min cap). Everything here is OFFLINE unit-testable; the compiler LLM call is fast (allowed for verify).
SPEC = the FULL Kimi K3 review with exact file:function traces + fixes: /tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/reviews/kimi_gate_review.md  (READ IT IN FULL FIRST — it names every bug and the fix).
`
phase('Recon')
const recon = await agent(`${GUARD}
RECON (read-only): Read the Kimi review in full, then confirm each bug site in the CURRENT code (branch gate-inversion). For F1: clause_ledger.parse_exclusions + research_planning_gate._author_deterministic_terms/_merge_deterministic_authority (exclusions -> CoverageRequirement) + candidate_adapter._from_scope_constraints (named excludes -> content.exclusion). F2: clause_ledger.opaque_terms_for_uncovered (scope.opaque/content.opaque, force=hard, value=full clause) + retrieval_projection.from_contract_and_plan (_EXCLUSION_DIMENSIONS, _SCOPE_TEXT_DIMENSIONS, to_amplified_queries, to_retrieval_policy). F3: _deontic_hit._find (substring, no boundaries) + parse_date_bound + oblige-on-questions. F4: _SEGMENT_RE. F5: parse_exclusions _EXCL_TAIL_RE (and|or). F6: CANDIDATE_REGISTRY source.named->scope.named_source vs to_retrieval_policy plural; quality_profile not emitted in to_scope_protocol; languages[0]; hash identity. F7: from|since|after date semantics; merge alias matching. Report exact file:line for each so the Fix phase is precise. Confirm which are still present (some may have shifted after Phase C).`, { label: 'recon', phase: 'Recon' })

phase('Fix')
const fix = await agent(`${GUARD}
FIX all of Kimi's bugs. Recon:\n${recon}\n
F1 (CRITICAL): exclusions ('do not cite blogs', 'don't use Reuters') must become NEGATIVE source predicates -> scope.excluded_source_kinds / a scope-level exclusion dimension that retrieval_projection routes to RetrievalPolicy.excluded_source_kinds + to_scope_protocol emits an exclude facet. They must NEVER become a required CoverageRequirement or a mandatory query intent. Fix the dimension routing in _author_deterministic_terms/_merge_deterministic_authority and candidate_adapter so exclusions live in scope, not content.
F2 (CRITICAL): scope.opaque/content.opaque terms must NEVER be suffixed into positive query text. Add scope.opaque/content.opaque to the exclusion-aware routing: a hard OPAQUE term with a restrict/exclude cue -> negative predicate or held out of query text entirely; never appended positively in to_amplified_queries. to_retrieval_policy must handle opaque (as a hard eligibility predicate to be judged later, not a query string).
F3 (HIGH): _deontic_hit must use WORD-BOUNDARY matching (regex \\b, not substring) so 'commonly'!='only', 'avoidance'!='avoid'. Add an instruction-vs-world-statement guard: a clause that is a QUESTION or describes the world ('What must companies disclose', 'X is commonly used') must NOT fire a deontic constraint. parse_exclusions strong cues need a source-noun guard.
F4 (HIGH): _SEGMENT_RE must not split on abbreviation dots (U.S., e.g., i.e., version numbers) or decimals — use a smarter sentence segmenter so restriction scopes stay attached to their nouns.
F5 (HIGH): parse_exclusions must capture ALL coordinated members ('no blogs or forums' -> exclude {blogs, forums}); the completeness _covered check must not pass on partial any-overlap.
F6 (MEDIUM): fix registry/projection drift: source.named dimension name must match between CANDIDATE_REGISTRY and to_retrieval_policy (singular vs plural); EMIT quality_profile in to_scope_protocol (so quality isn't decorative); emit ALL hard languages not just languages[0]; assert contract/policy HASH identity on persisted-vs-compiled bytes.
F7 (MEDIUM): parse_date_bound: 'after YYYY' -> GTE (YYYY+1)-01-01 (distinct from 'since/from YYYY' -> GTE YYYY-01-01); merge alias matching so 'news articles' vs facet 'news_article' dedupe instead of double-surviving; give blocked_unsupported at least a logged/disclosed reader.
Add metamorphic UNIT TESTS (tests/planning/test_kimi_metamorphic.py) for every class Kimi named: 'X is commonly used since 2018' (no hard constraint, no invented date), 'the avoidance of bias' (no exclusion), 'What must companies disclose under CSRD?' (no oblige-block), 'no blogs or forums' (both excluded, negative predicate), 'Use Reuters and AP.' (named includes), 'do not cite blogs' (scope exclusion routed to RetrievalPolicy.excluded_source_kinds AND absent from query text AND not a coverage requirement), and a French prompt (documented as a known gap if not handled). 
Report exact edits (file:line) + which bugs fixed. Keep behind PG_GATE.`, { label: 'fix', phase: 'Fix', effort: 'high' })

phase('Verify')
const verdict = await agent(`${GUARD}
VERIFY (offline + compiler LLM ok; NO live retrieval). On gate-inversion:
1. FAITHFULNESS: provenance_generator.py 0-diff; flywheel untouched; PG_GATE OFF byte-identical.
2. THE METAMORPHIC PROOF (all must pass): (a) 'do not cite blogs' -> a NEGATIVE source predicate in RetrievalPolicy.excluded_source_kinds; NOT a CoverageRequirement; NOT in any query text/amplified query. (b) 'no blogs or forums' -> BOTH excluded. (c) 'X is commonly used since 2018' -> NO hard restriction, NO invented hard date. (d) 'the avoidance of bias' -> NO exclusion term. (e) 'What must companies disclose under CSRD?' -> compiles, NOT blocked_unsupported from a spurious oblige. (f) opaque hard term -> NEVER appears as positive query text. (g) task-72 journal/quality/English still hard (no regression). (h) quality_profile IS emitted in to_scope_protocol.
3. Run tests/planning (report pass/fail). 
Return a structured verdict.`, { label: 'verify', phase: 'Verify', effort: 'high', schema: {
  type: 'object', additionalProperties: false,
  required: ['faithfulness_untouched','off_path_byte_identical','f1_exclusion_negative_predicate','f2_opaque_not_positive_query','f3_word_boundary_no_fabrication','f5_coordinated_exclusions','f6_quality_profile_emitted','task72_no_regression','tests_passed','tests_failed','summary','risks'],
  properties: {
    faithfulness_untouched: { type: 'boolean' },
    off_path_byte_identical: { type: 'boolean' },
    f1_exclusion_negative_predicate: { type: 'boolean' },
    f2_opaque_not_positive_query: { type: 'boolean' },
    f3_word_boundary_no_fabrication: { type: 'boolean' },
    f5_coordinated_exclusions: { type: 'boolean' },
    f6_quality_profile_emitted: { type: 'boolean' },
    task72_no_regression: { type: 'boolean' },
    tests_passed: { type: 'integer' },
    tests_failed: { type: 'integer' },
    summary: { type: 'string' },
    risks: { type: 'array', items: { type: 'string' } },
  },
} })

phase('Commit')
const commit = await agent(`${GUARD}
COMMIT (local only, do NOT push). On gate-inversion: clean __pycache__, git add -A, commit describing the Kimi bug fixes (F1 exclusion->negative predicate; F2 opaque never positive query; F3 word-boundary deontic + instruction guard; F4 abbreviation-safe segmentation; F5 coordinated exclusions; F6 registry/projection drift + quality_profile emitted + hash identity; F7 date semantics + alias merge) + metamorphic tests. End with:
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Report commit hash + clean status.`, { label: 'commit', phase: 'Commit' })

return { branch: 'gate-inversion', verdict, commit: (commit||'').slice(0,150) }
