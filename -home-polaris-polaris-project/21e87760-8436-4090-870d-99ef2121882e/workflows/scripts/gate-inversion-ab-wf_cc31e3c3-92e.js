export const meta = {
  name: 'gate-inversion-AB',
  description: 'Gate inversion Phase A+B: failing control-path test + rebuild the contract so DETERMINISTIC code owns explicit constraints (generic IR, monotonic merge, LLM additive-only). Offline-testable. Faithfulness FROZEN.',
  phases: [
    { title: 'Setup', detail: 'branch gate-inversion off gate-s0-s5' },
    { title: 'PhaseA', detail: 'failing control-path test (documents the bar)' },
    { title: 'Recon', detail: 'map current schema/compiler/adapter/ontology' },
    { title: 'Build', detail: 'generic IR + deterministic-authoritative core + monotonic merge + validators' },
    { title: 'Verify', detail: 'generality + fuzz + faithfulness/OFF-path' },
  ],
}

const SPEC = `SPEC (read all three FIRST, in full):
- Consolidated verdict + phased plan: /home/polaris/polaris_project/GATE_REVIEW_VERDICT.md
- Sol's diagnosis (deep, code-grounded): /tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/reviews/sol_situation_review.md
- Fable's diagnosis: (in the verdict; the key mechanics are captured there)`

const GUARD = `
HARD GUARDRAILS (violating any = failure):
- EDIT ONLY /home/polaris/wt/outline_agent on branch gate-inversion. NEVER edit /home/polaris/wt/flywheel.
- FAITHFULNESS FROZEN: never modify src/polaris_graph/generator/provenance_generator.py or strict_verify. READ ONLY.
- The gate is fully behind default-OFF PG_GATE: with PG_GATE unset the pipeline MUST be byte-identical to champion. (The gate-ON *behavior* changes — that is the intended rebuild — but OFF must not.)
- This is a REBUILD of the contract-authority core, not additive patches. But do it as clean, well-structured code; reuse the schema/ontology/enforcement/audit shell.
- Do NOT run live retrieval/compose (10-min shell cap). Phase A+B are OFFLINE-testable. The contract compiler's own LLM call is fast (allowed for verify: source .env, PG_PLANNING_GATE_LIVE=1).
- CORE PRINCIPLE (the whole point): explicit user constraints are a MONOTONIC LOSSLESS authority owned by DETERMINISTIC code. The LLM may interpret/normalize/decompose/propose (referencing clause IDs) but may NEVER silently delete, weaken, relocate, or invent an explicit constraint. No per-type hardcoding — a generic constraint IR + registries.
${SPEC}
`

phase('Setup')
const setup = await agent(`${GUARD}
STEP: In /home/polaris/wt/outline_agent (on gate-s0-s5), create+checkout branch gate-inversion. Read the three SPEC docs. Report a 8-line summary confirming you understand: (1) P0-A the contract never reaches retrieval (from_champion_plan empty contract) — NOT fixed in this workflow (that's Phase C, next), only its failing TEST is written here; (2) P0-B the LLM can drop explicit constraints — THIS workflow fixes it by inverting authority; (3) the generic IR; (4) monotonic merge; (5) faithfulness frozen.`, { label: 'setup', phase: 'Setup' })

phase('PhaseA')
const phaseA = await agent(`${GUARD}
PHASE A — write the FAILING control-path test (it documents the behavioral bar; it is EXPECTED TO FAIL on the current code, that's the point — mark it xfail/skip with a clear reason so the suite stays green, but the assertion body must be real).
Create tests/planning/test_control_path_contract_reaches_retrieval.py that asserts (against the REAL seam, mocked network):
1. When PG_GATE=1, the exact pinned PlanningGateArtifact (its contract_hash) reaches scripts/run_honest_sweep_r3.py:run_one_query's retrieval seam — i.e. the projection used is from_artifact(gate_artifact), NOT from_champion_plan with an empty ResearchContract().
2. Two DIFFERENT contracts over the same candidate/corpus fixture (one allowing all sources, one hard-limiting to journal + date>=2024) produce DIFFERENT eligible/citable source sets.
Because the current code fails both (from_champion_plan ships an empty contract), mark them xfail with reason='P0-A: contract not wired to retrieval; fixed in Phase C' so CI is honest. Report the test + confirm it currently fails/xfails for the RIGHT reason (trace from_champion_plan at run_honest_sweep_r3.py).`, { label: 'phaseA:failing-test', phase: 'PhaseA' })

phase('Recon')
const recon = await parallel([
  () => agent(`${GUARD}
RECON-1 (read-only): map the CURRENT contract authority to be inverted. In src/polaris_graph/planning/: research_planning_gate.py (_contract_user_prompt — the 'represent or reject' instruction; _compile_contract; _promote_source_scope; _conservative_contract; the _call/_loads LLM path; run_research_planning_gate flow), planning_gate_schema.py (ContractTerm.from_dict/to_dict fields; PromptSpan.from_dict string-span raise; _norm_enum silent-coerce; validate_contract; reanchor). Report exact fields + the precise points where an explicit constraint can be dropped/mangled, and where the promoter/fallback speak non-canonical dimensions. Cite file:line.`, { label: 'recon:compiler', phase: 'Recon' }),
  () => agent(`${GUARD}
RECON-2 (read-only): map the deterministic extraction + registries to make authoritative. src/polaris_graph/planning/candidate_adapter.py (reconcile_candidates, _from_user_constraints, _from_scope_constraints, _from_rule_reader, _merge_pair — and the span-loss bug where it locates canonicalized tokens not raw phrases). The ontology config/scope_ontology/source_types.yaml (facet ids, synonyms, the 'dimension' field) + the deontic/modal lexicon (restrict_hard etc.). src/polaris_graph/instruction/constraint_extractor.py (Constraints fields; note it's an LLM call w/o spans). src/polaris_graph/retrieval/intake_constraint_extractor.py (regex extractors). Report: what constraint families are deterministically extractable today (source-type/quality/language/recency/exclusion/format/named), where spans are lost, and how to make the ontology facet 'dimension' drive a GENERIC candidate->canonical registry (no substring 'journal' branches). Cite file:line.`, { label: 'recon:extractors', phase: 'Recon' }),
]).then(r => r.map(x => x || 'RECON FAILED — re-read the files yourself'))
const [reconCompiler, reconExtractors] = recon

phase('Build')
const build = await agent(`${GUARD}
BUILD — the contract-authority INVERSION (the core of the rebuild). This is one coherent module change; do it carefully and cohesively.
Using the recon maps:
COMPILER MAP:\n${reconCompiler}\n
EXTRACTOR MAP:\n${reconExtractors}\n

Implement, in src/polaris_graph/planning/ (planning_gate_schema.py, candidate_adapter.py, research_planning_gate.py):
1. GENERIC CONSTRAINT IR (extend ContractTerm additively; keep existing to_dict/from_dict back-compat): add typed fields subject, attribute, operator (IN|NOT_IN|EQ|GTE|LTE|BETWEEN|REQUIRE|PREFER), value_set, boolean_group, stage_owner (retrieval|ranking|eligibility|compose|render), capability_id, normalization_status (exact|proposed|opaque). Existing dimension/value stay for back-compat.
2. GENERIC candidate->canonical REGISTRY (data-driven, ~10 rows, NOT per-type if-branches): candidate_dimension -> canonical dimension + value normalizer + span policy + force policy + stage_owner + projection semantics. Drive source-type facets from the ontology facet's OWN 'dimension' field, not substring 'journal'/'peer' matching. Cover: source.types, source.quality, source.language, date.recency (operator GTE/BETWEEN), source.jurisdiction, source.named, content.exclusion (operator NOT_IN), content.coverage/comparison, deliverable.format/length, rhetoric.tone. Unknown kind -> first-class OPAQUE value, never dropped.
3. FIX SPAN LOSS: candidate_adapter must locate the RAW trigger phrase the user wrote (e.g. 'news articles', 'company press releases'), not the canonicalized token. Carry raw trigger spans through constraint_extractor.Constraints (add a raw-trigger/raw_spans field) and give the journal_only/regex candidates their match-object span. So every explicit candidate carries a real span and is promotable/hard.
4. DETERMINISTIC-AUTHORITATIVE CORE (run ALWAYS, not a fallback): build the authoritative explicit-constraint contract deterministically from candidates via the registry — this is _conservative_contract's logic done right and promoted to the primary path. Delete _promote_source_scope entirely (subsumed by the registry).
5. LLM ADDITIVE-ONLY + MONOTONIC MERGE: the LLM call no longer authors explicit constraints. It classifies unseen phrasings + decomposes (threads/coverage/inference), referencing candidate/clause IDs. Merge rule: LLM may ADD terms/metadata or enrich; it may NEVER delete, downgrade, or re-dimension a deterministic explicit term. Overlap: deterministic wins. Parse the LLM output PER-ITEM (one bad item is skipped+logged, never nukes the batch). PromptSpan.from_dict accepts a bare quote-string (reanchor supplies offsets); stop asking the model for offsets. Do NOT silently coerce bad enums (_norm_enum) — surface them.
6. LOSSLESS FALLBACK + honest states: on LLM failure, emit a contract with ALL deterministic/opaque explicit terms + a deterministic breadth plan; 'degraded' means enrichment is thin, NEVER that explicit constraints vanished. States: pinned_executable | degraded_lossless | blocked_unsupported.
7. VALIDATORS: add invariants — every explicit deterministic candidate survives into the contract (monotonicity), no unanchored explicit hard term, no invented hard term (hard requires span-verified deterministic origin), operator/value schema valid. (Capability-binding validation is Phase D; add a TODO stub, don't block on it here.)

Keep everything behind PG_GATE (OFF byte-identical). Report exact edits (file:line) + which pieces were deleted vs added. Add unit tests as you go.`, { label: 'build:inversion-core', phase: 'Build', effort: 'high' })

phase('Verify')
const verdict = await agent(`${GUARD}
VERIFY (read + run tests; the compiler LLM call is allowed live for the generality probe — source .env, PG_PLANNING_GATE_LIVE=1 — but NO full retrieval). On branch gate-inversion:
1. provenance_generator.py CLEAN diff (0 lines); nothing under flywheel changed; PG_GATE OFF path byte-identical (spot-check the OFF path is unchanged).
2. THE GENERALITY PROOF (the whole point) — live-compile these prompts and assert:
   a. Task 72 ('...only high-quality English-language journal articles') -> contract has source_types=journal_article HARD + source_quality=high HARD + source_languages=en HARD, all origin=explicit with spans.
   b. 'Write a market analysis of the EV industry in 2025. Only use news articles and company press releases from 2024 onward.' -> contract has source kinds IN {news_article, company_press_release} HARD + date GTE 2024 HARD. NEITHER dropped. compiler NOT degraded-with-loss.
   c. 'Broad overview of quantum computing.' -> NO source/date constraint (no invention).
   d. An exclusion: 'Do not cite blogs.' -> content.exclusion NOT_IN {blog} (never a positive query token).
3. MALFORMED-OUTPUT FUZZ: feed the parser string-shaped spans / missing keys / truncated JSON via a stub client; assert the deterministic explicit constraints SURVIVE every case (per-item fail-soft).
4. Run the full tests/planning suite + the Phase-A xfail test (must still xfail for the right reason). Report pass/fail counts.
Return a structured verdict.`, { label: 'verify', phase: 'Verify', effort: 'high', schema: {
  type: 'object', additionalProperties: false,
  required: ['faithfulness_untouched','off_path_byte_identical','task72_all_hard','news_probe_captured','open_no_invention','exclusion_negative','fuzz_survives','tests_passed','tests_failed','summary','risks'],
  properties: {
    faithfulness_untouched: { type: 'boolean' },
    off_path_byte_identical: { type: 'boolean' },
    task72_all_hard: { type: 'boolean' },
    news_probe_captured: { type: 'boolean' },
    open_no_invention: { type: 'boolean' },
    exclusion_negative: { type: 'boolean' },
    fuzz_survives: { type: 'boolean' },
    tests_passed: { type: 'integer' },
    tests_failed: { type: 'integer' },
    summary: { type: 'string' },
    risks: { type: 'array', items: { type: 'string' } },
  },
} })

phase('Commit')
const commit = await agent(`${GUARD}
COMMIT (local only — do NOT push). On gate-inversion: clean __pycache__, git add -A, commit describing Phase A+B (failing control-path test; contract-authority inversion: generic IR + deterministic-authoritative core + monotonic merge + LLM additive-only + lossless fallback; _promote_source_scope deleted; span-loss fixed). End with:
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Report the commit hash + clean status.`, { label: 'commit', phase: 'Commit' })

return { branch: 'gate-inversion', verdict, commit: (commit||'').slice(0,160) }
