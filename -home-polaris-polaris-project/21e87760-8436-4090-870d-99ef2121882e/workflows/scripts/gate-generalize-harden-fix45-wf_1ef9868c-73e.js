export const meta = {
  name: 'gate-generalize-harden-fix45',
  description: 'Generalize Fix 4 (report shape -> archetype table) and Fix 5 (source-kind/quality -> credibility-tier + contract-driven eligibility) on top of d44ee36, per the authoritative 3-way plan. Retire the journal_only_filter corpus mask. Wire contract end-to-end. Metamorphic + anti-hardcode + OFF-path-golden tests. Faithfulness FROZEN.',
  phases: [
    { title: 'Setup', detail: 'confirm d44ee36 + read plan + verify anchors + edit-map' },
    { title: 'Fix4', detail: 'archetype table + framing + KF position + D8 relocate + methods-when-required; unwind litreview literals' },
    { title: 'Fix5', detail: 'tier model + kind-driven eligibility + exclusion-wins + adequacy/receipt gate; retire journal_only_filter; DOI-not-alone' },
    { title: 'Wire', detail: 'contract drives both fixes end-to-end; no journal/review literals in control flow' },
    { title: 'Tests', detail: 'M1-M10 metamorphic + anti-hardcode grep + OFF-path golden + faithfulness 0-diff' },
    { title: 'Verify', detail: 'structured verdict: faithfulness/OFF/anti-hardcode/metamorphic/filter-retired' },
    { title: 'Commit', detail: 'commit local on gate-inversion' },
  ],
}
const PLAN = "/home/polaris/polaris_project/GATE_GENERALIZE_FIX45_PLAN.md"
const GUARD = `
AUTHORITATIVE SPEC: ${PLAN} (the 3-way Fable+Kimi+Codex consolidation). Read the relevant section IN FULL before editing. Do NOT improvise beyond it.

HARD GUARDRAILS (a violation fails the run):
- EDIT ONLY /home/polaris/wt/outline_agent, branch gate-inversion, building on the committed HEAD d44ee36. NEVER touch /home/polaris/wt/flywheel.
- FAITHFULNESS FROZEN: NEVER modify src/polaris_graph/generator/provenance_generator.py (incl frozen banner builder build_d8_unadjudicated_banner ~:3212 and evidence-support ~:3124), strict_verify, NLI, D8 thresholds, or the drop rule. No new verification pass, no new faithfulness test. Verify 0-diff at the end vs both d44ee36's provenance_generator.py and champion df4118a.
- EVIDENCE-POSITIVE ONLY, ABSOLUTE: Fix 5 may ONLY move a source UNKNOWN->PASS (via validated tier) or reorder/prefer it. It must NEVER turn any PASS into FAIL, and NEVER relax an existing FAIL. (The plan REJECTED Kimi's FAIL-relaxation guard — do not implement it.) Retraction / predatory-host / explicit is_peer_reviewed=False FAILs stay absolute and first.
- DOI-ALONE IS NOT T1: a bare DOI (preprint/dataset/predatory/content-shell) must NOT auto-PASS. T1 requires validated peer-reviewed OR official-gov/primary evidence. journal=>PASS is ONE T1 instance, not a special case.
- abacademies.org: it is a NEW predatory FAIL, NOT evidence-positive. Add it (if at all) as a clearly-labelled separate denylist line, NOT inside the UNKNOWN->PASS resolver, so the "FAIL behavior untouched" claim stays true.
- RETIRE journal_only_filter.py (filter_to_citeable / assert_no_leak / JournalOnlyAbort + its ~10 call-sites) — it is a hard fail-closed frozen-corpus MASK (violates "enforce scope at RETRIEVAL, never filter a frozen corpus", which tanked RACE 0.4447->0.3264). Replace with the adequacy+acquisition-receipt-gated PG_SOURCE_RESTRICTION_HARD eligibility path per the plan. If any call-site is load-bearing, neutralize to a no-op behind the gate, do not leave a live mask.
- HARD source-kind enforcement arms ONLY behind corpus-adequacy (>= min in-scope-kind rows) AND a matching acquisition receipt (contract_hash). Otherwise degrade to prefer + a disclosure line in the audit appendix. Adequacy counts in-scope-KIND rows, never DOI/journal rows. Exclusions always win and are never adequacy-checked.
- NO journal/review/"Introduction and Scope" LITERALS in control-flow. They live only as DATA in the archetype/tier registries. (An anti-hardcode grep test enforces this.)
- Methods is NOT always machinery: keep it in the body when contract.sections requires it; only internal audit/disclosure/reliability/ledger blocks are demoted to the appendix.
- Do NOT rebuild predicate_force["allowed_source_kinds"] (retrieval_projection.py:695) or the op="prefer" projection (:336) — already general per the plan.
- PG_GATE-OFF and all-flags-default MUST be byte-identical to champion (golden-hash test). New behavior behind default-OFF/None flags, double-guarded by contract-presence.
- REJECTED HAZARDS (do none): PG_REPORT_D8_BANNER=0; editing the frozen banner builder; institution-allowlist hard PASS; prose-rewrite/re-stitch of verified Key-Findings spans; editing vendored clean_article.py; generative/LLM report skeleton; LLM inside score_source_quality.
- Offline only — NO live retrieval/compose (10-min cap). Verify anchors against the live committed code before editing (line numbers may have drifted).
`
phase('Setup')
const setup = await agent(`${GUARD}
Confirm worktree /home/polaris/wt/outline_agent is on gate-inversion at HEAD d44ee36 (clean). Read ${PLAN} IN FULL. Then produce a precise EDIT-MAP: for every item in the plan's unwind-list (§5) and every Fix 4 / Fix 5 edit, give {file, symbol/function, current committed line, what changes, plan section}. Specifically verify these committed anchors exist and report their real line numbers: the litreview-flavored names to unwind (grep for PG_REPORT_LITREVIEW_SHAPE / build_intro_and_scope_md / reshape_report_body_litreview / _is_journal_lead / _has_doi_or_journal_credential / _journal_only_hard_restriction_enabled / PG_SOURCE_RESTRICTION_JOURNAL_ONLY), the journal_only_filter.py module + ALL its call-sites, the report-assembly seam (~:17254), D8 banner prepend (~:20778), quality_eligibility.py score_source_quality/build_quality_eligibility/build_topicality_eligibility, retrieval_projection.py predicate_force(:695)/op=prefer(:336), key_findings.py bullet/preamble, planning_gate_schema.py ResearchContract/ContractTerm/sections. Return the edit-map as a structured list.`, { label: 'setup', phase: 'Setup', effort: 'high' })

phase('Fix4')
const fix4 = await agent(`${GUARD}
Implement the GENERALIZED Fix 4 (report shape) per ${PLAN} §2/§4, on top of d44ee36. Do exactly:
1. NEW pure module (no I/O, no LLM, no provenance import) holding the closed ARCHETYPE registry keyed off normalized deliverable.kind (review [default] / systematic_review / memo / brief / comparison / explainer), each an ordered list of the EXISTING render blocks; + a resolver using the same synonym-table pattern as _resolve_facet_id (unmapped kind -> preserve verbatim as opaque term + assumptions ledger entry, fall back to review) + a pure order_report_blocks(profile, blocks) + build_framing_md (claim-free, citation-free, template-only from objective/scope spans; empty objective -> emit nothing). NO hardcoded "## Introduction and Scope" in control flow.
2. UNWIND the litreview literals from d44ee36: rename PG_REPORT_LITREVIEW_SHAPE->PG_REPORT_SHAPE, build_intro_and_scope_md->build_framing_md, reshape_report_body_litreview->order_report_blocks; Key-Findings position now VARIES by archetype (memo/brief lead with it), not always-after-thematic.
3. Machinery demotion is contract-aware: only internal audit/disclosure/reliability/ledger blocks go below the existing appendix boundary; Methods STAYS in the body when a contract.sections SectionRequirement matches it. Feed reliability into the existing audit slot (compose_report_with_reliability) — no second boundary.
4. Relocate the D8 banner: in contract-shaped mode insert the banner AFTER the H1/title block (or into the audit appendix per the plan), banner STRING byte-identical, builder 0-diff. In legacy/OFF mode keep the current prepend. This is the real fix for "report opens on a blockquote".
5. Keep the committed Key-Findings whole-bullet integrity + one-sentence preamble; make the preamble neutral (not litreview-specific) and header label archetype-driven (review: ## Key Findings; memo: ## Bottom Line) — chrome only, bullets byte-identical.
Everything behind PG_REPORT_SHAPE (default OFF) AND contract-present; OFF -> the exact d44ee36/champion concatenation + banner prepend, byte-identical. Add a render-time assertion that the multiset of blocks is unchanged (permutation only, nothing deleted). Report edits (file:line).
EDIT-MAP:\n${setup}`, { label: 'fix4', phase: 'Fix4', effort: 'high' })

phase('Fix5')
const fix5 = await agent(`${GUARD}
Implement the GENERALIZED Fix 5 (source-kind + credibility) per ${PLAN} §3/§4, on top of Fix 4's tree. Do exactly:
1. RETIRE journal_only_filter.py: remove/neutralize filter_to_citeable / assert_no_leak / JournalOnlyAbort and ALL call-sites (the plan lists them). It is the frozen-corpus hard mask that must die. Replace with the eligibility path below. Leave NO live mask; if a call-site is structural, make it a gated no-op.
2. Replace the journal "4.5 second-chance" (_has_doi_or_journal_credential) in score_source_quality with a deterministic signal->(tier,kind) REGISTRY consulted BEFORE the UNKNOWN fail-closed: T1 = validated peer-reviewed journal metadata OR official gov/primary/statute/authenticated-filing -> PASS unconditionally; T2 = reputable newswire/authenticated IR/established analyst w/ author+method -> PASS iff kind in allowed and not excluded; T3/unrated -> stay UNKNOWN/demote. DOI-ALONE is NOT T1. First match wins with a recorded basis; no match -> existing UNKNOWN path unchanged. score_source_quality gains policy=None => byte-identical default. NO LLM in the verdict fn (PG_CREDIBILITY_LLM_TIERING only fills metadata upstream).
3. Kind eligibility + adequacy: add build_source_kind_eligibility(policy, rows, acquisition_receipt): exclusions (NOT_IN) always win first (monotonic union of excluded ids; a PASS/weight can never re-include an excluded kind). Hard allowed_source_kinds arms a nonmatching-mask ONLY if the acquisition receipt.contract_hash matches AND distinct in-scope-kind usable rows >= PG_SOURCE_KIND_MIN_ADEQUATE (default 25); else downgrade hard->soft (prefer), record an Assumption + SourceReceipt basis, and disclose in the audit appendix. Count in-scope-KIND rows, never DOI/journal.
4. Selection ordering: replace _is_journal_lead with _kind_match(row in allowed_source_kinds) stable sort (kind-match desc, quality weight desc, existing rank); empty allowed -> no reorder (byte-identical). S4 audit metric = cited in-scope-kind share (NOT journal share); empty scope -> silent.
5. Topicality: generalize build_topicality_eligibility with optional soft_floor (score<hard 0.15 quarantine; 0.15<=score<0.30 soft-demote even when hard; >=0.30 unchanged); soft_floor=None => byte-identical. Keep fail-OPEN when score_map is None.
6. Rename PG_SOURCE_RESTRICTION_JOURNAL_ONLY -> PG_SOURCE_RESTRICTION_HARD (kind-agnostic). abacademies.org, if added, is a clearly-commented SEPARATE predatory-denylist line (a new FAIL), NOT part of the evidence-positive resolver.
All UPSTREAM of the frozen verifier; provenance_generator.py 0-diff. Report edits (file:line).`, { label: 'fix5', phase: 'Fix5', effort: 'high' })

phase('Wire')
const wire = await agent(`${GUARD}
WIRE + reconcile so ONE contract drives BOTH fixes end-to-end, per ${PLAN}. Verify: (a) the compiled contract's deliverable.kind actually reaches the archetype resolver at the report-assembly seam (trace the path from run_one_query's pinned artifact -> render profile); (b) allowed_source_kinds/excluded/required + deontic force actually reach build_source_kind_eligibility and the tier registry (trace from the pinned contract -> RetrievalPolicy -> quality_eligibility call site ~:14369/:14480); (c) predicate_force(:695)/op=prefer(:336) are reused, not rebuilt; (d) no journal/review/"Introduction and Scope" string literal appears in any control-flow condition (only in the archetype/tier DATA registries). Fix any broken wiring. Byte-compile all modified modules. Report the two end-to-end traces (deliverable.kind -> skeleton; allowed_source_kinds -> eligibility) and confirm no literals leaked into control flow.
Fix4:\n${fix4}\nFix5:\n${fix5}`, { label: 'wire', phase: 'Wire', effort: 'high' })

phase('Tests')
const tests = await agent(`${GUARD}
Implement + run the METAMORPHIC cross-prompt test suite per ${PLAN} §"metamorphic tests" (M1-M10). One mixed fixture corpus (peer-reviewed journal, official gov report, newswire, company press release, established analyst blog, anonymous blog, DOI preprint, retracted DOI, predatory journal, content shell). Swap ONLY the contract and assert each fix ADAPTS:
- systematic_review+prefer-journals: systematic-review skeleton, Methods in BODY, journals rank first (no hard mask), valid PR journal PASS, DOI-only preprint NOT PASS.
- memo+must-cite-news+press: memo skeleton (Bottom Line first, NO "Introduction and Scope"), news/PR prioritized, journals get no special boost, other kinds still available (REQUIRE != exclusive).
- brief+only-gov: brief skeleton, hard allowlist arms ONLY with matching receipt + adequacy else prefer+disclose, .gov PASS via gov-tier not because "government" appeared.
- market-scan+prefer-blogs: comparison/memo skeleton, credible analyst blogs first, anonymous blogs stay UNKNOWN, NO journal-first.
- exclude-blogs: every blog excluded incl a reputable one and even if another term prefers blogs; exclusion survives adequacy failure.
- open prompt: policy.is_empty -> no filter/reorder; gate-on default review skeleton; gate-OFF byte-identical.
- safety mutations: retracted DOI stays FAIL, predatory stays FAIL, DOI content-shell not PASS, hard allowlist w/o receipt does NOT arm, same contract below/above adequacy flips prefer/disclose vs enforce, every verified payload sentence byte-identical + same occurrence count across archetypes, D8 banner verbatim but not before H1 in contract-shaped mode.
Plus: M7 ANTI-HARDCODE grep test (fails if journal/review/"Introduction and Scope" literal appears in control flow outside the registries); M9 OFF-path GOLDEN (report.md + manifest byte-equal to champion when PG_GATE=0 or flags default); faithfulness 0-diff test (provenance_generator.py + per-section verified_text hashes unchanged pre/post). Run the FULL offline suite too. Report pass/fail counts and any failure detail (distinguish pre-existing from new).
Wire:\n${wire}`, { label: 'tests', phase: 'Tests', effort: 'high' })

phase('Verify')
const verdict = await agent(`${GUARD}
FINAL VERIFY (offline; NO live retrieval) on gate-inversion. Return the structured verdict. Confirm each:
1. provenance_generator.py 0-diff vs d44ee36 AND champion df4118a; strict_verify/NLI/D8/drop untouched; flywheel untouched.
2. journal_only_filter.py hard corpus mask RETIRED (no live filter_to_citeable/assert_no_leak/JournalOnlyAbort path).
3. NO FAIL relaxed, NO PASS->FAIL; DOI-alone does not PASS; abacademies (if present) is a separate labelled denylist not in the resolver.
4. Anti-hardcode grep (M7) PASSES: no journal/review/"Introduction and Scope" literal in control flow.
5. OFF-path + all-flags-default byte-identical to champion (M9 golden).
6. Hard source-kind enforcement only behind adequacy+receipt; exclusion always wins; adequacy counts in-scope-kind rows.
7. Full metamorphic M1-M10 pass; full offline suite pass count (separate pre-existing failures, name them).
8. None of the REJECTED hazards were done.`, { label: 'verify', phase: 'Verify', effort: 'high', schema: {
  type: 'object', additionalProperties: false,
  required: ['faithfulness_0diff','journal_filter_retired','no_fail_relaxed','doi_alone_not_pass','anti_hardcode_grep_pass','off_path_byte_identical','adequacy_receipt_gated','exclusion_wins','metamorphic_pass','metamorphic_fail','suite_passed','suite_failed_new','suite_failed_preexisting','no_rejected_hazards','all_verified','summary','risks'],
  properties: {
    faithfulness_0diff:{type:'boolean'}, journal_filter_retired:{type:'boolean'}, no_fail_relaxed:{type:'boolean'}, doi_alone_not_pass:{type:'boolean'},
    anti_hardcode_grep_pass:{type:'boolean'}, off_path_byte_identical:{type:'boolean'}, adequacy_receipt_gated:{type:'boolean'}, exclusion_wins:{type:'boolean'},
    metamorphic_pass:{type:'integer'}, metamorphic_fail:{type:'integer'}, suite_passed:{type:'integer'}, suite_failed_new:{type:'integer'}, suite_failed_preexisting:{type:'integer'},
    no_rejected_hazards:{type:'boolean'}, all_verified:{type:'boolean'}, summary:{type:'string'}, risks:{type:'array',items:{type:'string'}},
  },
} })

phase('Commit')
const commit = await agent(`${GUARD}
COMMIT (local only, do NOT push) IFF verify.all_verified is true. Verify verdict: all_verified=${verdict && verdict.all_verified}. If true: on gate-inversion, clean __pycache__, git add -A, commit describing the generalization (Fix 4 -> contract-driven archetype table; Fix 5 -> credibility-tier + kind-driven adequacy/receipt-gated eligibility; retire journal_only_filter corpus mask; metamorphic + anti-hardcode + OFF-golden tests; faithfulness 0-diff). Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>. If all_verified is false, do NOT commit — report what blocked. Return commit hash + clean status, or the blocker.`, { label: 'commit', phase: 'Commit' })

return { branch: 'gate-inversion', base: 'd44ee36', verdict, commit: (commit||'').slice(0,200) }
