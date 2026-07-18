export const meta = {
  name: 'gate-eligibility-judge',
  description: "Stage 2: build the post-fetch eligibility JUDGE keyed to the clause ledger (deterministic predicates + schema-constrained LLM judge for quality/topicality/OPAQUE kinds) + a precision/recall eval harness. Upstream of FROZEN verifier. This is the 'smart' enforcement Kimi says is unbuilt.",
  phases: [
    { title: 'Recon', detail: 'citable-eligibility hook + opaque terms + per-source metadata + LLM client' },
    { title: 'Build', detail: 'eligibility judge + receipts + eval harness (labeled fixture corpus)' },
    { title: 'Verify', detail: 'precision/recall on eval corpus + faithfulness/OFF' },
    { title: 'Commit', detail: 'commit local on gate-inversion' },
  ],
}
const GUARD = `
HARD GUARDRAILS:
- EDIT ONLY /home/polaris/wt/outline_agent on branch gate-inversion (build on commit 12a6d5b). NEVER edit /home/polaris/wt/flywheel.
- FAITHFULNESS FROZEN: never modify src/polaris_graph/generator/provenance_generator.py / strict_verify, and never change HOW claims verify. The judge is UPSTREAM: it removes ineligible rows from the citable/evidence list BEFORE strict_verify sees the pool. provenance_generator.py must stay 0-diff.
- Fully behind default-OFF PG_GATE (+ its own flag if useful); OFF byte-identical.
- Do NOT run a full ~35-min live retrieval/compose (10-min cap). The JUDGE's LLM calls are fast and run on a FIXTURE corpus for the eval (no live fetch). Build + eval OFFLINE.
CONTEXT: The gate now UNDERSTANDS constraints correctly (F1-F7 fixed, 12a6d5b) but does NOT ENFORCE the open-world ones. Stage 1 parks OPAQUE hard clauses ('company press releases', 'industry white papers') in RetrievalPolicy.opaque_eligibility as disclosed-but-unenforced. Phase C added deterministic quality/topicality eligibility at the citable seam (run_honest_sweep_r3.py:~14394, upstream of strict_verify). Kimi's core prescription (the 'smart' part): a post-fetch, receipt-emitting eligibility JUDGE keyed to the clause ledger — deterministic metadata predicates where they exist + a schema-constrained LLM judge that READS each fetched source against each HARD clause (incl. opaque) where they don't — so 'only news + company press releases' and 'high-quality journal articles' actually BITE without an ontology entry. PLUS a precision/recall eval harness.
SPEC: Kimi review sections 2 & 5 (/tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/reviews/kimi_gate_review.md) + /home/polaris/polaris_project/GATE_REVIEW_VERDICT.md.
`
phase('Recon')
const recon = await agent(`${GUARD}
RECON (read-only): map the citable-eligibility seam + inputs for the judge. In scripts/run_honest_sweep_r3.py find the Phase-C citable-eligibility point (~14394) where evidence_for_gen is filtered upstream of strict_verify — how it currently applies quality/topicality, and where a per-source judge would slot in. In src/polaris_graph/planning/retrieval_projection.py: RetrievalPolicy.opaque_eligibility + excluded_source_kinds + quality_profile + the hard clause set available. What per-source METADATA is available at that point (from live_retriever: title, venue, is_peer_reviewed, doi, host, abstract/body text, tier)? How is the LLM client obtained for a schema-constrained judge call (the pattern research_planning_gate/_call uses)? Report: (1) exact insertion point + signature for a judge that takes (fetched_source, [hard_clauses]) -> per-clause pass/fail/unknown + receipt; (2) what deterministic predicates can decide without the LLM (date, language, ontology-mapped kind, named-source) vs what NEEDS the LLM (quality, topicality, opaque kinds); (3) where receipts should be persisted. Cite file:line.`, { label: 'recon', phase: 'Recon' })

phase('Build')
const build = await agent(`${GUARD}
BUILD the eligibility judge + eval harness. Recon:\n${recon}\n
1. NEW module src/polaris_graph/planning/eligibility_judge.py: judge_source(source, hard_clauses, llm=...) -> list of receipts {clause_id, term_id, verdict(pass|fail|unknown), basis, stage}. Layered: (a) DETERMINISTIC predicates first (date via metadata, language, ontology-mapped source-kind, named-source host match) — high precision, no LLM; (b) a SCHEMA-CONSTRAINED LLM JUDGE for the rest — quality ('high-quality': read venue/peer-review/tier signals + the OJS-mill/predatory/conference host heuristics), topicality (source body vs the CLEAN objective/thread), and OPAQUE kinds (read the source and decide: is THIS a 'company press release' / 'industry white paper' / whatever the clause says?). One bounded call per source scoring ALL its pending clauses at once (schema-constrained JSON: per-clause verdict+basis). Reasoning-first safe (big max_tokens, capture reasoning). 
2. AGGREGATION -> citable eligibility: a source is CITABLE only if it PASSES every HARD 'only/exclude/require' clause. FAIL on any hard predicate -> removed from the citable menu (kept in diagnostics/corpus). UNKNOWN under a hard 'only ...' -> fail-closed (disclosed). Soft/prefer -> rank weight, not exclusion. Wire this at the Phase-C citable-eligibility seam behind PG_GATE (extend, don't replace, the deterministic quality/topicality already there); connect RetrievalPolicy.opaque_eligibility so opaque clauses are now JUDGED (not parked). Persist eligibility_receipts.json. UPSTREAM of strict_verify — provenance_generator.py untouched.
3. EVAL HARNESS scripts/eval_eligibility_judge.py + a LABELED FIXTURE corpus (tests/planning/fixtures/eligibility_corpus.json): ~20-30 sources with gold labels across {reputable peer-reviewed journal, predatory OJS mill, conference proceeding, news article, company press release, industry white paper, blog, government report, off-topic journal}, each with realistic metadata + a short body snippet. Run the judge for several contracts (task-72 journal+high-quality+on-topic; 'only news + company press releases from 2024'; 'no blogs'; open) and compute PRECISION/RECALL of admit/exclude vs gold. This is the eval Kimi said was missing.
Report exact edits (file:line) + new modules. Faithfulness untouched. Behind PG_GATE.`, { label: 'build', phase: 'Build', effort: 'high' })

phase('Verify')
const verdict = await agent(`${GUARD}
VERIFY (offline + judge LLM on the FIXTURE corpus; NO live retrieval). On gate-inversion:
1. FAITHFULNESS: provenance_generator.py 0-diff; flywheel untouched; the judge provably mutates the citable/evidence list UPSTREAM of strict_verify (cite call order). PG_GATE OFF byte-identical.
2. THE EVAL (the whole point): run scripts/eval_eligibility_judge.py and report precision/recall. Assert:
   (a) task-72 (journal + high-quality + on-topic): reputable on-topic journals ADMITTED; predatory OJS / conference / blog / news EXCLUDED on quality/kind; off-topic journal EXCLUDED on topicality. 
   (b) 'only news + company press releases from 2024': news + press releases ADMITTED (the OPAQUE 'company press release' now ENFORCED by reading the source, NOT parked); journals/blogs EXCLUDED; pre-2024 EXCLUDED.
   (c) 'no blogs': blogs EXCLUDED; everything else admitted.
   (d) open contract: nothing excluded on source-type.
   Report precision/recall numbers per contract; target recall(admit-correct) and precision(exclude-correct) both high (state the actual numbers honestly, even if imperfect).
3. Run tests/planning (pass/fail).
Return a structured verdict.`, { label: 'verify', phase: 'Verify', effort: 'high', schema: {
  type: 'object', additionalProperties: false,
  required: ['faithfulness_untouched','off_path_byte_identical','judge_upstream_of_verify','opaque_kinds_now_enforced','task72_predatory_excluded','offtopic_excluded','eval_precision_recall','tests_passed','tests_failed','summary','risks'],
  properties: {
    faithfulness_untouched: { type: 'boolean' },
    off_path_byte_identical: { type: 'boolean' },
    judge_upstream_of_verify: { type: 'boolean' },
    opaque_kinds_now_enforced: { type: 'boolean' },
    task72_predatory_excluded: { type: 'boolean' },
    offtopic_excluded: { type: 'boolean' },
    eval_precision_recall: { type: 'string' },
    tests_passed: { type: 'integer' },
    tests_failed: { type: 'integer' },
    summary: { type: 'string' },
    risks: { type: 'array', items: { type: 'string' } },
  },
} })

phase('Commit')
const commit = await agent(`${GUARD}
COMMIT (local only, do NOT push). On gate-inversion: clean __pycache__, git add -A, commit describing Stage 2 (post-fetch eligibility judge keyed to the clause ledger: deterministic predicates + schema-constrained LLM judge for quality/topicality/opaque kinds; opaque constraints now ENFORCED not parked; receipts; precision/recall eval harness + labeled fixture corpus; upstream of frozen verifier). End with:
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Report commit hash + clean status.`, { label: 'commit', phase: 'Commit' })

return { branch: 'gate-inversion', verdict, commit: (commit||'').slice(0,150) }
