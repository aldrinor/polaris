export const meta = {
  name: 'gate-apply-5-fixes',
  description: 'Apply the consolidated 5-fix plan on gate-inversion: (1) scoring-cache purge, (2) KEYSTONE artifact hand-off, (3) D8-adjudicate wiring, (4) report shape, (5) tame mask + journal leak. Offline unit-tested. Faithfulness FROZEN.',
  phases: [
    { title: 'Setup', detail: 'branch + read the plan + verify line numbers' },
    { title: 'Fix1', detail: 'score_report_race cache purge + assertion' },
    { title: 'Fix2+5', detail: 'KEYSTONE artifact hand-off + tame mask/journal leak (coupled)' },
    { title: 'Fix3', detail: 'D8 four-role adjudication wiring' },
    { title: 'Fix4', detail: 'report shape: title/intro/appendix-order/bullet' },
    { title: 'Verify', detail: 'Gate-0 unit tests + faithfulness 0-diff + OFF byte-identical' },
    { title: 'Commit', detail: 'commit local on gate-inversion' },
  ],
}
const SPEC = "AUTHORITATIVE FIX SPEC (read the relevant section IN FULL before editing): /home/polaris/polaris_project/GATE_FIX_PLAN_CONSOLIDATED.md"
const GUARD = `
HARD GUARDRAILS:
- EDIT ONLY /home/polaris/wt/outline_agent on branch gate-inversion (build on commit 78fe2ca). NEVER edit /home/polaris/wt/flywheel.
- FAITHFULNESS FROZEN: NEVER modify src/polaris_graph/generator/provenance_generator.py (incl the D8 banner builder ~:3212 and evidence-support ~:3124) or strict_verify / NLI / D8 thresholds. Verify 0-diff at the end. Fix 3 makes D8 ADJUDICATE (adds verification) — it must NOT edit the frozen builder or set PG_REPORT_D8_BANNER=0.
- Gate behavior is behind PG_GATE; the PG_GATE-OFF path MUST stay byte-identical to champion.
- Every change must match the consolidated plan's file:function:line + rationale + faithfulness-safety. Do NOT improvise beyond the plan. Do NOT do anything in the plan's REJECTED list (PG_REPORT_D8_BANNER=0, institution-allowlist PASS over hard journal scope, prose-rewrite of verbatim Key-Findings spans, loosening chrome-gate, editing vendored clean_article.py).
- Verify line numbers against the live code before editing (the plan's line numbers may have drifted). Do NOT run live retrieval/compose (10-min cap) — offline unit tests only.
${SPEC}
`
phase('Setup')
const setup = await agent(`${GUARD}
Confirm you are in /home/polaris/wt/outline_agent on branch gate-inversion (78fe2ca). Read GATE_FIX_PLAN_CONSOLIDATED.md IN FULL. Then verify the current line numbers for each fix site against the live code and report any drift: score_report_race.py:main (raw write ~:68, subprocess ~:89); run_gate_e2e.py (_run_one_task/_run_fresh_e2e ~:615, _fresh_e2e_env_slate:317); run_honest_sweep_r3.py (_gate_load_or_compile_artifact ~:8846, four-role seam ~:18121/8968, topicality call ~14369, appendix boundary ~6325, banner prepend ~20783); quality_eligibility.py (~:209/222/224/350, _PREDATORY_HOST_PATTERNS); retrieval_projection.py (~:314); key_findings.py (~:1004, bullet emission). Report a table of {fix, file, planned line, actual line}.`, { label: 'setup', phase: 'Setup', effort: 'high' })

phase('Fix1')
const fix1 = await agent(`${GUARD}
Apply FIX 1 (scoring-cache purge) EXACTLY per the plan. In scripts/score_report_race.py:main: after the raw target-jsonl write, before invoking the harness, purge the stale cleaned file (data/test_data/cleaned_data/{args.model_name}.jsonl) if it exists (log it). AND add the scored-artifact assertion after the harness subprocess.run: read the cleaned file, assert exactly one record with id==task id and len(article) >= 0.5*len(report_text); on failure print 'BLOCKED: cleaned/raw divergence' and return 3. Do NOT thread force into the vendored clean_article.py (rejected). Add a unit test (tests/) that a pre-existing stale cleaned file is purged before scoring. Report edits (file:line) + test result.
Setup notes:\n${setup}`, { label: 'fix1', phase: 'Fix1', effort: 'high' })

phase('Fix2+5')
const fix25 = await agent(`${GUARD}
Apply FIX 2 (KEYSTONE artifact hand-off) AND FIX 5 (tame mask + journal leak) TOGETHER (the plan mandates they ship together).
FIX 2: (a) in run_gate_e2e.py before _run_fresh_e2e, write the pinned artifact to the SWEEP task-level dir (out_root/q['domain']/q['slug']/planning_gate_artifact.json) that run_one_query actually reads (overwrite per-draw). (b) fail-loud identity guard after _run_fresh_e2e: read it back, assert its contract_sha256 == d['stages']['gate']['contract_sha256']; on mismatch set d['error']. (c) run_honest_sweep_r3.py:_gate_load_or_compile_artifact — when the compile/recompile branch fires, log WARNING 'RECOMPILED AT SEAM (pinned artifact absent)' + stamp manifest['gate_contract_recompiled_at_seam']=True.
FIX 5: (a) wire PG_CREDIBILITY_LLM_TIERING into the live slate (resolve UNKNOWN tiers). (b) quality_eligibility.py:score_source_quality — BEFORE the UNKNOWN fail-closed (~:222/224), if the row has a DOI or classifies as a peer-reviewed journal article (reuse document_type_classifier.is_peer_reviewed_journal_article), return PASS; EVIDENCE-POSITIVE ONLY — leave all FAIL verdicts (retracted/predatory/is_peer_reviewed=False/low-tier) UNTOUCHED. Add abacademies.org to _PREDATORY_HOST_PATTERNS. (c) two-tier topicality at run_honest_sweep_r3.py:~14369: add PG_TOPICALITY_HARD_FLOOR (default 0.15) — <0.15 hard-quarantine, 0.15-0.30 band through the existing SOFT-demote path (quality_eligibility.py:~350). (d) journal-only = preference+audit not starvation: in retrieval_projection.py (~:314) a HARD allowed_source_kinds=['peer_reviewed_journal'] becomes op=prefer; add selection ordering that puts journal/DOI rows first in the selected menu (nothing dropped); hard journal-only only behind a corpus-adequacy pre-check (>=~25 T1/T2/DOI rows), else disclose 'insufficient journal corpus; prioritized journals'.
All UPSTREAM of the frozen verifier; no FAIL row re-admitted; provenance_generator.py 0-diff. Add unit tests: (i) run_gate_e2e writes -> run_one_query loads the SAME sha (guard trips on mismatch); (ii) quality plan emits receipts with the draw1 artifact; (iii) topicality two-tier split; (iv) journal-DOI row PASSes before UNKNOWN, a FAIL row still fails. Report edits (file:line) + tests.`, { label: 'fix2and5', phase: 'Fix2+5', effort: 'high' })

phase('Fix3')
const fix3 = await agent(`${GUARD}
Apply FIX 3 (remove D8 banner by making D8 ADJUDICATE — NEVER by hiding it). (a) run_gate_e2e.py:_fresh_e2e_env_slate — add 'PG_FOUR_ROLE_MODE':'1' for live runs. (b) run_gate_e2e.py:_run_fresh_e2e — build + inject the D8 four_role_transport + four_role_input_builder mirroring scripts/dr_benchmark/run_gate_b.py:build_gate_b_transport (transport-mode 'openrouter', no self-hosted stack) and pass them to runner(q, out_root, four_role_transport=..., four_role_input_builder=...) (run_one_query already accepts these params). (a) and (b) MUST land together (the fail-closed guard holds the release if mode is set without a transport). Do NOT edit the frozen build_d8_unadjudicated_banner and do NOT set PG_REPORT_D8_BANNER=0. Note in a comment that the reranker is revived by running with PG_WINNER_FIRING_GATE UNSET (default ON) on a free GPU (not a code change). Add a unit test that when adjudicated=True the banner prepend is empty. Report edits (file:line) + test.`, { label: 'fix3', phase: 'Fix3', effort: 'high' })

phase('Fix4')
const fix4 = await agent(`${GUARD}
Apply FIX 4 (report shape — ship a literature review, not an audit dump; ALL in NON-frozen render assembly). (a) At the sweep report-assembly seam, emit '# {title}' (title already exists) + a short '## Introduction and Scope' claim-free framing paragraph from the contract objective (no findings, no citations). (b) Demote machinery below the appendix boundary (run_honest_sweep_r3.py:~6325): on-disk order Title -> Intro -> thematic ### -> Synthesis -> Limitations -> Bibliography -> '## Appendix (not scored as report claims)' holding methods/disclosure/contradiction-ledger/reliability. POSITION ONLY — delete NOTHING; disclosure stays in the file + manifest. (c) Key-Findings bullet integrity invariant in src/polaris_graph/generator/key_findings.py: every bullet must open with '**' and contain a matched closing '**'; a failing bullet is re-emitted from its stored title + carried sentence (both exist verbatim upstream), NEVER shipped chopped; constrain the render-seam chrome removal to whole-unit granularity in the Key Findings block. (d) shrink the hedge preamble (~:1004) to one sentence + appendix pointer. Every moved block is disclosure/audit text; every kept finding sentence stays byte-identical strict_verify output; do NOT re-compose verified sentences. Add unit tests: report starts with '# ', no 'STRONGEST VERIFIER' before the first thematic section, every Key-Findings bullet has matched '**'. Report edits + tests.`, { label: 'fix4', phase: 'Fix4', effort: 'high' })

phase('Verify')
const verdict = await agent(`${GUARD}
FINAL VERIFY (offline; NO live retrieval). On gate-inversion:
1. FAITHFULNESS: provenance_generator.py 0-diff vs 78fe2ca (and vs champion df4118a); strict_verify/NLI/D8-thresholds untouched; flywheel untouched. Confirm NONE of the REJECTED items were done (no PG_REPORT_D8_BANNER=0, no banner-builder edit, no institution-allowlist hard PASS, no verbatim-span prose rewrite, no vendored clean_article edit).
2. PG_GATE OFF byte-identical (new behavior gated; None-default params).
3. Run the full Gate-0 unit suite from the plan + tests/planning + any affected fast tests. Report pass/fail counts. Specifically confirm: (a) artifact hand-off writes->loads SAME sha + guard trips on mismatch; (b) journal/DOI PASS-before-UNKNOWN while FAIL rows still fail; (c) topicality two-tier split; (d) banner empty when adjudicated=True; (e) report starts '# ' + no machinery-before-thematic; (f) Key-Findings '**' invariant.
Return a structured verdict.`, { label: 'verify', phase: 'Verify', effort: 'high', schema: {
  type: 'object', additionalProperties: false,
  required: ['faithfulness_untouched','off_path_byte_identical','no_rejected_items_done','fix1_done','fix2_keystone_done','fix5_done','fix3_done','fix4_done','tests_passed','tests_failed','summary','risks'],
  properties: {
    faithfulness_untouched:{type:'boolean'}, off_path_byte_identical:{type:'boolean'}, no_rejected_items_done:{type:'boolean'},
    fix1_done:{type:'boolean'}, fix2_keystone_done:{type:'boolean'}, fix5_done:{type:'boolean'}, fix3_done:{type:'boolean'}, fix4_done:{type:'boolean'},
    tests_passed:{type:'integer'}, tests_failed:{type:'integer'}, summary:{type:'string'}, risks:{type:'array',items:{type:'string'}},
  },
} })

phase('Commit')
const commit = await agent(`${GUARD}
COMMIT (local only, do NOT push). On gate-inversion: clean __pycache__, git add -A, commit describing the 5-fix application (Fix1 scoring-cache purge; Fix2 KEYSTONE artifact hand-off + guard; Fix3 D8 adjudication wiring; Fix4 report shape title/intro/appendix/bullet; Fix5 tame mask + journal-leak journal-PASS/two-tier-topicality/prefer). End with:
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Report commit hash + clean status.`, { label: 'commit', phase: 'Commit' })

return { branch: 'gate-inversion', verdict, commit: (commit||'').slice(0,150) }
