export const meta = {
  name: 'gate-inversion-C',
  description: 'Phase C: wire the pinned contract into live retrieval (kill from_champion_plan empty-contract seam -> from_artifact + typed RetrievalPolicy), feed the existing enforcement engine, make quality+topicality real eligibility, add receipts. Flips the 2 control-path xfails green. Faithfulness FROZEN (eligibility is UPSTREAM of verify).',
  phases: [
    { title: 'Recon', detail: 'retrieval seam + enforcement + citable-menu + metadata' },
    { title: 'Wire', detail: 'from_artifact seam + RetrievalPolicy threaded into fs/expert/live' },
    { title: 'Enforce', detail: 'contract->protocol bridge + quality/topicality eligibility + receipts' },
    { title: 'Verify', detail: 'control-path tests PASS + eligibility works + faithfulness/OFF' },
    { title: 'Commit', detail: 'commit local on gate-inversion' },
  ],
}

const GUARD = `
HARD GUARDRAILS:
- EDIT ONLY /home/polaris/wt/outline_agent on branch gate-inversion (build on commit a9f6bb2). NEVER edit /home/polaris/wt/flywheel.
- FAITHFULNESS FROZEN: never modify src/polaris_graph/generator/provenance_generator.py / strict_verify, and never change HOW claims are verified or cited. Phase C changes ONLY which evidence rows are ELIGIBLE to enter the citable menu (UPSTREAM of the frozen verifier). A source failing a hard predicate is removed from the citable menu BEFORE strict_verify sees it — it is never a change to verification.
- Fully behind default-OFF PG_GATE: with PG_GATE unset, the retrieval path is byte-identical to champion (from_champion_plan seam unchanged; new params None-default; new eligibility/quality/topicality passes no-op).
- Do NOT run a full ~35-min live retrieval/compose (10-min shell cap). Phase C is buildable + verifiable OFFLINE with MOCKED corpora + the compiler LLM (fast). The real live proof is a monitored job AFTER this workflow.
CONTEXT: Phase A+B (a9f6bb2) made the CONTRACT smart & lossless, but two P0 gaps remain: (P0-A) the contract never reaches live retrieval — scripts/run_honest_sweep_r3.py:run_one_query uses retrieval_projection.from_champion_plan(_research_plan,...) with an EMPTY ResearchContract() at the FS seam (~line 10444); from_artifact() exists but is only used in a telemetry 'wiring proof'. (P0-quality) 'high_quality'/topicality are decorative (project to the literal word 'high'); no venue-quality or topical eligibility. Two tests xfail: tests/planning/test_control_path_contract_reaches_retrieval.py (they must go GREEN in this phase). 
SPEC: /home/polaris/polaris_project/GATE_REVIEW_VERDICT.md (Phase C) + Sol's section 4 'Enforcement' in /tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/reviews/sol_situation_review.md.
`

phase('Recon')
const recon = await parallel([
  () => agent(`${GUARD}
RECON-1 (read-only): the RETRIEVAL SEAM. In scripts/run_honest_sweep_r3.py:run_one_query — the FS/retrieval dispatch (~10430-10470), how _research_plan is built (plan_research), where from_champion_plan is called, what protocol + ResearchFrame get passed to live_retriever.run_live_retrieval, and how the pinned gate artifact could be threaded in (does run_one_query receive it? if not, how — a param, a file path, an env?). Also src/polaris_graph/planning/retrieval_projection.py:from_artifact vs from_champion_plan (signatures + what a RetrievalPolicy would need). And the signatures of fs_researcher_query_gen.plan_fs_researcher_queries, expert_facet_planner.plan_expert_facets, live_retriever.run_live_retrieval — where a typed retrieval_policy param would thread. Cite file:line. Report the minimal wiring to replace the empty-contract seam with from_artifact under PG_GATE.`, { label: 'recon:seam', phase: 'Recon' }),
  () => agent(`${GUARD}
RECON-2 (read-only): ENFORCEMENT + CITABLE MENU + METADATA. src/polaris_graph/retrieval/constraint_enforcement.py:build_scope_enforcement (what protocol keys it reads: scope_constraints/date_range/user_constraints; what it does: weight-demote/mask/named-pin/timeline). The protocol structure (where scope_gate writes protocol['scope_constraints']). WHERE the citable evidence menu / eligible rows are assembled before the frozen strict_verify (trace from live_retriever output -> corpus rows -> what the writer may cite). WHERE OpenAlex/source metadata lands (is_peer_reviewed, venue, tier, retraction) in live_retriever (~1711/1882/7117) + the existing _candidate_relevance_scores/_relevance_threshold_select. Report: (1) how to bridge a gate contract -> protocol['scope_constraints']/['date_range'] so build_scope_enforcement acts on gate terms; (2) the exact upstream point to apply a post-fetch citable-eligibility filter (drop rows failing a hard predicate from the citable menu, keep in diagnostics) that is CLEARLY upstream of strict_verify; (3) what metadata is available for a deterministic quality scorer. Cite file:line.`, { label: 'recon:enforce', phase: 'Recon' }),
]).then(r => r.map(x => x || 'RECON FAILED — re-read files'))
const [reconSeam, reconEnforce] = recon

phase('Wire')
const wire = await agent(`${GUARD}
BUILD — WIRE the contract into retrieval (kills P0-A). Recon:\nSEAM:\n${reconSeam}\n
1. Under PG_GATE=1, thread the pinned PlanningGateArtifact (or its path/hash) into scripts/run_honest_sweep_r3.py:run_one_query, and REPLACE the from_champion_plan empty-contract seam at the FS dispatch with retrieval_projection.from_artifact(artifact) — merged additively with the champion plan's sub_queries so we keep breadth but the CONTRACT drives scope. PG_GATE unset => unchanged champion seam (byte-identical).
2. Compile a typed RetrievalPolicy from the pinned contract+plan in retrieval_projection.py: allowed/excluded source kinds, date interval, languages, named inclusions/exclusions, quality profile ref, per-predicate hard/soft, contract_hash. EXCLUSIONS MUST BE NEGATIVE PREDICATES — never appended as positive query text (fix the scope.prohibited->query-text bug).
3. Thread retrieval_policy explicitly (new None-default param => OFF byte-identical) into fs_researcher_query_gen.plan_fs_researcher_queries, expert_facet_planner.plan_expert_facets, live_retriever.run_live_retrieval. Remove raw hard-value query-text suffixing; QueryIntent source-type/language/date fields must survive projection (route dates server-side to OpenAlex from/to_publication_date where available).
4. FLIP THE CONTROL-PATH TESTS GREEN: tests/planning/test_control_path_contract_reaches_retrieval.py must now PASS — assert (mocked network) the exact contract_hash reaches run_one_query's retrieval seam via from_artifact (not from_champion_plan), and that two different contracts over the same mock corpus produce different eligible source sets. Remove the xfail markers.
Report exact edits (file:line). Do NOT run live retrieval; use the mocked control-path test.`, { label: 'wire:from_artifact', phase: 'Wire', effort: 'high' })

phase('Enforce')
const enforce = await agent(`${GUARD}
BUILD — real ENFORCEMENT (kills P0-quality). Recon:\nENFORCE:\n${reconEnforce}\n
1. contract->protocol BRIDGE: a deterministic to_scope_protocol() mapping canonical scope terms -> protocol['scope_constraints'] + date.recency -> protocol['date_range']+timeline_strictness, so the EXISTING src/polaris_graph/retrieval/constraint_enforcement.py:build_scope_enforcement (weight-demote/mask/named-pin/hard-timeline, PRISMA disclosure) acts on the GATE's terms. Under PG_GATE, feed it the gate policy instead of (or reconciled with) the legacy separate extraction.
2. QUALITY real: a deterministic, domain-neutral source-quality scorer over metadata already fetched (is_peer_reviewed, venue/DOAJ status, tier, retraction, host heuristics for OJS-mill/conference-proceeding/predatory patterns). It emits (a) a ranking weight and (b) for a HARD source_quality/source_type term, a POST-FETCH CITABLE-ELIGIBILITY verdict: a source failing the hard predicate is removed from the CITABLE menu (kept in diagnostics/corpus accounting) BEFORE the frozen strict_verify. 'journal-shaped' != peer-reviewed; conference proceedings != journal unless allowed. Unknown metadata under a hard 'only high-quality' -> fail-closed for citable eligibility (disclosed), never silently relaxed. Soft preference -> reorder only.
3. TOPICALITY real: score fetched body vs the clean objective/owning thread; confirmed off-topic -> quarantined from citable menu; uncertain -> down-rank + mark. Reuse _candidate_relevance_scores as a starting piece but make it a contract-aware eligibility stage, not just prefetch reorder.
4. RECEIPTS: every query/source carries {contract_hash, term_id, source_id, stage, verdict(pass/fail/unknown), basis}; contract_compliance.audit_contract consumes them so a hard term is SATISFIED only with pass-receipts, UNKNOWN stays unknown.
CRITICAL: all of this is UPSTREAM of strict_verify — it changes which rows are eligible to cite, NOT how citations are verified. provenance_generator.py stays 0-diff. All PG_GATE-gated (OFF no-op).
Report exact edits (file:line) + the eligibility insertion point (prove it's upstream of strict_verify).`, { label: 'enforce:quality-topicality', phase: 'Enforce', effort: 'high' })

phase('Verify')
const verdict = await agent(`${GUARD}
VERIFY (offline + mocked corpora + compiler LLM ok; NO full live retrieval). On gate-inversion:
1. FAITHFULNESS: provenance_generator.py 0-diff; flywheel untouched; the eligibility filter is provably UPSTREAM of strict_verify (cite the call order). PG_GATE OFF byte-identical (from_champion_plan seam unchanged when OFF; new params None-default).
2. CONTROL-PATH TESTS GREEN: tests/planning/test_control_path_contract_reaches_retrieval.py PASSES (contract_hash reaches retrieval via from_artifact; two contracts -> different eligible source sets). No longer xfail.
3. ELIGIBILITY WORKS (mock corpus): build a fixture corpus mixing {reputable journal, predatory OJS, conference proceeding, news blog, off-topic journal}. With a task-72-style hard journal+high-quality contract, assert ONLY the reputable on-topic journal rows reach the citable menu; predatory/conference/blog/off-topic are excluded (kept in diagnostics). With an all-source contract, more rows are eligible. Prohibition ('no blogs') removes blogs and never appears as a positive query.
4. RECEIPTS: a hard term reports SATISFIED only with pass-receipts.
5. Run tests/planning (report pass/fail; the 2 control-path tests must now pass).
Return a structured verdict.`, { label: 'verify', phase: 'Verify', effort: 'high', schema: {
  type: 'object', additionalProperties: false,
  required: ['faithfulness_untouched','off_path_byte_identical','contract_reaches_retrieval','control_path_tests_green','eligibility_filters_correctly','exclusion_not_positive_query','receipts_gate_satisfied','tests_passed','tests_failed','summary','risks'],
  properties: {
    faithfulness_untouched: { type: 'boolean' },
    off_path_byte_identical: { type: 'boolean' },
    contract_reaches_retrieval: { type: 'boolean' },
    control_path_tests_green: { type: 'boolean' },
    eligibility_filters_correctly: { type: 'boolean' },
    exclusion_not_positive_query: { type: 'boolean' },
    receipts_gate_satisfied: { type: 'boolean' },
    tests_passed: { type: 'integer' },
    tests_failed: { type: 'integer' },
    summary: { type: 'string' },
    risks: { type: 'array', items: { type: 'string' } },
  },
} })

phase('Commit')
const commit = await agent(`${GUARD}
COMMIT (local only, do NOT push). On gate-inversion: clean __pycache__, git add -A, commit describing Phase C (wire contract into retrieval via from_artifact + typed RetrievalPolicy; contract->protocol bridge feeding build_scope_enforcement; real quality+topicality citable-eligibility upstream of frozen verify; per-source receipts; control-path tests green; exclusions negative). End with:
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Report commit hash + clean status.`, { label: 'commit', phase: 'Commit' })

return { branch: 'gate-inversion', verdict, commit: (commit||'').slice(0,160) }
