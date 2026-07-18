export const meta = {
  name: 'gate-fix45-doi-t1-and-tests',
  description: 'Close the DOI-alone-is-not-T1 gap via full classifier-confirmed T1 (operator-approved), author the durable M1-M10 metamorphic Fix-5 tests (incl M8 preprint/dataset rejection + recall boundary), re-verify all 8 gates, commit. Faithfulness FROZEN. Builds ON the uncommitted generalization tree.',
  phases: [
    { title: 'Setup', detail: 'confirm dirty tree + locate T1 predicate call-sites + adequacy wiring' },
    { title: 'DOI-T1', detail: 'classifier-confirmed T1; bare/preprint/dataset DOI no longer auto-PASS; update test contract' },
    { title: 'Tests', detail: 'author durable M1-M10 metamorphic suite incl M8 reject + recall boundary' },
    { title: 'Verify', detail: 're-run all 8 gates; DOI-alone-not-T1 now TRUE' },
    { title: 'Commit', detail: 'commit local on gate-inversion iff all_verified' },
  ],
}
const PLAN = "/home/polaris/polaris_project/GATE_GENERALIZE_FIX45_PLAN.md"
const GUARD = `
CONTEXT: The prior hardening workflow left the working tree of /home/polaris/wt/outline_agent (branch gate-inversion, HEAD d44ee36) DIRTY with the Fix4/Fix5 generalization (8 files modified + new src/polaris_graph/generator/report_skeleton.py + tests/generator/). BUILD ON that uncommitted tree — do NOT git reset / git stash / git checkout / discard it. Authoritative design: ${PLAN}.

OPERATOR DECISION (just made, overrides the plan's "reuse DOI predicate as-is"): implement FULL CLASSIFIER-CONFIRMED T1. A bare DOI — including preprint (arXiv 10.48550), dataset (Zenodo 10.5281), working-paper, and content-shell DOIs — must NOT alone qualify as T1. T1-scholarly requires a POSITIVE genre verdict: is_peer_reviewed_journal_article(classify_document_type(...)) == True. journal=>PASS remains one T1 instance, now gated on the classifier, not on "10." prefix.

HARD GUARDRAILS (a violation fails the run):
- EDIT ONLY /home/polaris/wt/outline_agent on gate-inversion. NEVER touch /home/polaris/wt/flywheel.
- FAITHFULNESS FROZEN: NEVER modify provenance_generator.py (incl banner builder :3212 / evidence-support :3124), strict_verify, NLI, D8 thresholds, drop rule. Verify 0-diff vs d44ee36 AND champion df4118a at the end. Do NOT modify the vendored clean_article.py.
- EVIDENCE-POSITIVE ONLY, ABSOLUTE: the change must be STRICTER (remove a promotion path), never relax a FAIL, never turn PASS->FAIL. A row that no longer earns T1 falls through to its EXISTING UNKNOWN path unchanged (under soft: demoted not dropped; under hard: masked ONLY if corpus-adequate). Retraction/predatory/is_peer_reviewed=False/low-tier FAILs stay absolute and first.
- STARVATION BACKSTOP must remain intact: hard source-kind masking arms ONLY behind corpus-adequacy (>= PG_SOURCE_KIND_MIN_ADEQUATE in-scope-KIND rows, counted by the SAME classifier) AND a matching acquisition receipt; otherwise degrade to prefer + disclosure. Confirm this still holds after the change (so metadata-less journals are never starved — either adequacy fails and nothing is masked, or the confirmed-journal corpus is rich).
- The classifier (document_type_classifier.py) and adequacy are UPSTREAM of the frozen verifier — safe to consult, but do NOT weaken any FAIL/predatory branch there.
- NO journal/review/"Introduction and Scope" literals in control flow (anti-hardcode grep must still pass). PG_GATE-OFF + all-flags-default byte-identical to champion.
- REJECTED HAZARDS (do none): PG_REPORT_D8_BANNER=0; banner-builder edit; institution-allowlist hard PASS; prose-rewrite of verified spans; LLM in score_source_quality; generative skeleton; re-introducing a journal_only_filter live mask.
- Offline only — NO live retrieval/compose. Verify anchors against live code before editing.
`
phase('Setup')
const setup = await agent(`${GUARD}
Confirm the dirty generalization tree is present (git status shows report_skeleton.py + the 8 modified files, HEAD d44ee36, NOT committed). Then map precisely: (1) every call-site of _has_doi_or_journal_credential and _positive_signal_tier in src/polaris_graph/retrieval/quality_eligibility.py; (2) how the T1-scholarly row is currently derived (the "10." short-circuit in _has_doi_or_journal_credential step 1) and where classify_document_type / is_peer_reviewed_journal_article live and what inputs they need (openalex_source_type/openalex_is_peer_reviewed/publication_type/host fallback); (3) the existing test that pins the WRONG contract (test_fix5b_doi_row_passes_before_unknown — quote its assertion); (4) confirm the adequacy gate (build_source_kind_eligibility / corpus_kind_adequacy) counts in-scope-KIND rows via the SAME classifier, and where PG_SOURCE_KIND_MIN_ADEQUATE is read. Return a structured edit-map + the exact classifier inputs a row must carry to earn a positive journal verdict (this is the recall boundary to document in tests).`, { label: 'setup', phase: 'Setup', effort: 'high' })

phase('DOI-T1')
const doit1 = await agent(`${GUARD}
Implement FULL CLASSIFIER-CONFIRMED T1. Make the T1-scholarly signal in _positive_signal_tier require is_peer_reviewed_journal_article(classify_document_type(row-fields)) == True. Remove reliance on the bare "10." DOI short-circuit for T1: a DOI may be an INPUT to the classifier (helps genre resolution) but is NOT sufficient alone. Concretely: either (a) change _has_doi_or_journal_credential so step-1 no longer returns True on a bare DOI (DOI feeds the classifier; the positive verdict comes only from is_peer_reviewed_journal_article), or (b) bypass that helper in _positive_signal_tier and call the classifier directly — pick whichever is more surgical and does not alter any OTHER call-site's FAIL/PASS behavior (check the call-sites from setup). Keep the fail-open contract (any classifier fault => not-T1 => row stays UNKNOWN, never a rescue-on-error, never a FAIL). 
Then UPDATE the mispinned test test_fix5b_doi_row_passes_before_unknown to the correct contract: a row with a positive journal classification (openalex_source_type=journal + is_peer_reviewed=True, or a known publisher-host) -> PASS(T1); a bare/preprint/dataset DOI with no journal genre (arXiv 10.48550, Zenodo 10.5281, bare 10.1234/abcd with no metadata) -> stays UNKNOWN (NOT T1, NOT FAIL). Fix the now-false code comment in _positive_signal_tier / _has_doi_or_journal_credential to describe the real behavior. Report edits (file:line) + the updated test.
Setup map:\n${setup}`, { label: 'doi-t1', phase: 'DOI-T1', effort: 'high' })

phase('Tests')
const tests = await agent(`${GUARD}
Author the DURABLE M1-M10 metamorphic Fix-5 test suite the prior workflow verified only live (nothing currently guards build_source_kind_eligibility / corpus_kind_adequacy / _positive_signal_tier / acquisition-receipt gate / adequacy boundary). One mixed fixture corpus (peer-reviewed journal WITH openalex metadata, official gov report, newswire, company press release, established analyst blog, anonymous blog, arXiv preprint DOI, Zenodo dataset DOI, retracted DOI, predatory journal, content-shell). Swap ONLY the contract; assert adaptation:
- M1 systematic_review+prefer-journals: journals rank first, no hard mask, valid PR journal PASS, arXiv/Zenodo DOI NOT PASS (stay UNKNOWN).
- M2 memo+must-cite-news+press: news/PR prioritized, journals no special boost, REQUIRE != exclusive.
- M3 brief+only-gov: hard allowlist arms only with matching receipt + adequacy else prefer+disclose; .gov PASS via gov-tier.
- M4 market-scan+prefer-blogs: credible blogs first, anonymous blogs stay UNKNOWN, no journal-first.
- M5 exclude-blogs: every blog excluded incl reputable, survives adequacy failure, exclusion always wins.
- M6 open prompt: policy.is_empty -> no filter/reorder; gate-OFF byte-identical.
- M7 anti-hardcode grep: no journal/review/"Introduction and Scope" literal in control flow.
- M8 SAFETY/RECALL (the one that was missing): retracted DOI stays FAIL; predatory stays FAIL; **arXiv/Zenodo/bare-DOI content-shell do NOT PASS (T1 requires classifier confirmation)**; a real journal WITH openalex_source_type=journal+is_peer_reviewed=True DOES PASS (recall boundary); DOI-alone-not-T1 asserted.
- M9 OFF-path golden: report.md + manifest byte-equal to champion with flags default.
- M10 cross-fix: memo contract yields memo skeleton AND news-first menu AND news-share audit from one contract.
Plus a monotonicity property test (signals only move UNKNOWN->PASS; guard only reorders) and adequacy-boundary test (n=min_adequate +-1 flips prefer/disclose vs enforce). Run the full offline suite. Report pass/fail counts; separate any pre-existing failures (the test_fetch_snapshot_resume_gh1259 trio + test_run_paid_evaluator_scoring collection error are known-pre-existing).
DOI-T1 change:\n${doit1}`, { label: 'tests', phase: 'Tests', effort: 'high' })

phase('Verify')
const verdict = await agent(`${GUARD}
FINAL RE-VERIFY (offline) on gate-inversion. Return the structured verdict. Confirm each:
1. provenance_generator.py 0-diff vs d44ee36 AND champion df4118a; strict_verify/NLI/D8/drop untouched; flywheel untouched.
2. DOI-ALONE-IS-NOT-T1 now TRUE: arXiv/Zenodo/bare-DOI content-shell do NOT earn T1 (stay UNKNOWN); a metadata-confirmed journal still PASSes (recall boundary). No FAIL relaxed, no PASS->FAIL; the change is strictly a removed promotion path.
3. journal_only_filter hard mask still retired; starvation backstop intact (hard mask only behind adequacy+receipt; else prefer+disclose).
4. Anti-hardcode grep (M7) passes; abacademies is a separate labelled denylist not in the resolver.
5. OFF-path + all-flags-default byte-identical to champion (M9 golden).
6. Full M1-M10 + monotonicity + adequacy-boundary tests PASS (durable, in-suite now); full offline suite pass count (name pre-existing failures separately).
7. None of the REJECTED hazards were done.`, { label: 'verify', phase: 'Verify', effort: 'high', schema: {
  type: 'object', additionalProperties: false,
  required: ['faithfulness_0diff','doi_alone_not_t1','journal_recall_preserved','no_fail_relaxed','journal_filter_retired','starvation_backstop_intact','anti_hardcode_grep_pass','off_path_byte_identical','metamorphic_pass','metamorphic_fail','suite_passed','suite_failed_new','suite_failed_preexisting','no_rejected_hazards','all_verified','summary','risks'],
  properties: {
    faithfulness_0diff:{type:'boolean'}, doi_alone_not_t1:{type:'boolean'}, journal_recall_preserved:{type:'boolean'}, no_fail_relaxed:{type:'boolean'},
    journal_filter_retired:{type:'boolean'}, starvation_backstop_intact:{type:'boolean'}, anti_hardcode_grep_pass:{type:'boolean'}, off_path_byte_identical:{type:'boolean'},
    metamorphic_pass:{type:'integer'}, metamorphic_fail:{type:'integer'}, suite_passed:{type:'integer'}, suite_failed_new:{type:'integer'}, suite_failed_preexisting:{type:'integer'},
    no_rejected_hazards:{type:'boolean'}, all_verified:{type:'boolean'}, summary:{type:'string'}, risks:{type:'array',items:{type:'string'}},
  },
} })

phase('Commit')
const commit = await agent(`${GUARD}
COMMIT (local only, do NOT push) IFF verify.all_verified is true (value: ${verdict && verdict.all_verified}). If true: on gate-inversion, clean __pycache__, git add -A, commit the whole generalization + this DOI-T1 fix together, describing: Fix4 contract-driven archetype table; Fix5 credibility-tier + kind-driven adequacy/receipt-gated eligibility; journal_only_filter corpus mask retired; DOI-alone-is-not-T1 (full classifier-confirmed T1); durable M1-M10 metamorphic suite. Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>. If all_verified is false, do NOT commit — report the blocker precisely. Return commit hash + clean status, or the blocker.`, { label: 'commit', phase: 'Commit' })

return { branch: 'gate-inversion', base: 'd44ee36', verdict, commit: (commit||'').slice(0,200) }
