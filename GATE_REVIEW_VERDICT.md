# Research Planning Gate — Consolidated Verdict (Opus, from Sol + Fable)

**Date:** 2026-07-16 · **Reviewers:** Sol (GPT-5.6) + Fable 5, independent, blind to each other.
**Operator verdict (confirmed):** "a very stupid gate, not a smart LLM gate." Both reviewers agree, and now we know *precisely* why.

## The two decisive findings (both reviewers, independently, same code paths)

### P0-A — The contract was NEVER wired into live retrieval. It's a shadow artifact.
`run_one_query` (the live path) builds retrieval from `retrieval_projection.from_champion_plan(_research_plan, ...)` — which passes an **empty `ResearchContract()`**. The real `from_artifact(...)` projection is computed only in a **telemetry "wiring proof"** (`run_gate_e2e.py:_retrieval_wiring_proof`) — it counts lanes and throws them in a dict; it does not steer anything. So on the live task-72 run, retrieval was shaped by the *champion* planner + generic scholarly routing, and by **nothing in the gate's contract**. The compliance audit then graded a report the contract never controlled. **This alone explains "journal-shaped but predatory/off-topic."**

### P0-B — The LLM is allowed to erase the deterministic reader's findings.
The compiler tells the LLM each candidate is its "decision to represent or reject," and **no invariant checks that stated constraints survived**. So the LLM dropped journal-only on task 72; nothing failed. `_promote_source_scope()` was bolted on to re-inject *journal-flavored* candidates — a task-shaped whitelist that (a) misses everything else (news, press-releases, recency, exclusions, jurisdiction) and (b) can *invent* constraints (a "peer" facet → a `high` quality term the user never stated).

### Supporting causes (both agree)
- **Enforcement is decorative.** `source_quality=high` projects to the literal word "high" in a query string. No venue-quality scoring — even though OpenAlex already fetches `is_peer_reviewed`. Exclusions (`no blogs`) get appended as *positive* query text. Dates never become a date window.
- **Parsing is all-or-nothing.** One string-shaped span nukes the entire contract parse ("6 fatal errors"); the conservative fallback speaks a dimension vocabulary the projection can't read → "validates clean, projects to nothing."
- **The 73 tests validated the validators, not intelligence.** The offline stub was itself a deterministic echo-compiler; the real LLM failure modes and real live behavior were never tested. "73 green" measured a closed loop.

## The verdict: INVERT THE AUTHORITY (keep the shell, rebuild the core)

Both reviewers independently reached the same target. The outer shape is right and survives: pinned contract → separate adaptive plan → typed projections → compliance audit → (frozen) faithfulness. **What's wrong is the authority boundary inside the compiler.** Fix:

> **Explicit user constraints are a monotonic, lossless authority owned by DETERMINISTIC code. The LLM may interpret, normalize, decompose, and propose inferred constraints — referencing stable clause IDs — but it may NEVER silently delete, weaken, relocate, or invent an explicit constraint.**

Concretely, five changes:

1. **A generic constraint IR** (not per-type patches): `{term_id, clause_ids/spans, subject, attribute, operator(IN/NOT_IN/GTE/BETWEEN/REQUIRE/PREFER), value_set, boolean_group, force, origin, stage_owner, capability_id}`. So "only news + company press releases from 2024 onward" is expressible **generically** — allowed-kind set `IN {news, press_release}` + `published_at GTE 2024`, both hard. Source kinds/languages/quality live in versioned registries/ontologies, not `if "journal"` branches. An unknown kind stays a first-class **opaque** value — never dropped.
2. **Deterministic-authoritative, monotonic merge.** Deterministic extraction + registries author the explicit constraints (the current `_conservative_contract` logic, done right, run ALWAYS — not as a shameful fallback). The LLM call becomes **additive-only**: it classifies unseen phrasings and decomposes into threads/coverage, and it can *add* but never *remove or downgrade* a deterministic term. Delete `_promote_source_scope`.
3. **Wire the contract into retrieval for real.** Replace `from_champion_plan` at the live seam with `from_artifact(...)`; pass a typed `RetrievalPolicy` (hash-stamped) explicitly into FS query-gen, expert-facet planning, and live retrieval — not prose suffixes. **Feed the enforcement engine that already exists** (`constraint_enforcement.build_scope_enforcement`: weight-demote / mask / named-pin / hard-timeline, with PRISMA disclosure) instead of the parallel legacy truth source.
4. **Make quality + topicality executable** (upstream of frozen faithfulness — it changes which rows are *eligible to cite*, not how claims are verified). `high_quality` selects a domain-neutral **quality profile** over metadata already fetched (peer-review status, venue/DOAJ, tier, retraction, OJS-mill host heuristics) → a ranking weight + a **post-fetch citable-eligibility** verdict (a source failing a hard predicate stays in diagnostics, not in the citable menu). Topicality: score fetched body vs the objective/thread; off-topic is quarantined from citations. Both are weights/eligibility in existing seams — faithfulness untouched.
5. **Remove the LLM from the failure-critical path + robustness.** Schema-constrained (tool) output; **never ask the model for character offsets** (deterministic owns spans; the model references clause IDs — this deletes the "span must be an object" failure class); per-item parsing (one bad item never nukes the batch); a **lossless** fallback (explicit constraints always survive; "degraded" means *enrichment* thinner, never constraints vanished). Add the invariant validators + **capability check before pinning** (a hard term with no executable enforcer = `blocked_unsupported`, never silent success).

## Keep / Fix / Throw away
- **Keep:** contract-before-plan split, pinned hashed artifact, origin/force provenance, ambiguity/disclosure concepts, projection-as-concept, the schema + `reanchor_span`, ontology + deontic lexicon, `build_scope_enforcement` logic, existing metadata/tier/relevance components, compliance-as-a-stage, **all frozen faithfulness code**.
- **Fix/rebuild:** the term IR, candidate reconciliation, validators, retrieval projection, FS/expert-planner signatures, live-retrieval policy execution, quality/topicality classification, the live gate-on seam, the tests.
- **Throw away:** LLM-as-authority over explicit constraints, `_promote_source_scope`, raw hard-value query suffixes, positive rendering of exclusions, silent `[]` fallbacks, the `from_champion_plan` gate-on seam, canned task-72 fixtures as "generality" evidence.

## Phased plan (both reviewers align)
- **Phase A — a REAL failing control-path test first.** Assert the exact artifact hash reaches `run_one_query` → FS records → source receipts → compliance; and that two different contracts over the same corpus yield **different eligible source sets**. This must FAIL on the current branch (proving P0-A).
- **Phase B — replace contract authority + schema:** clause ledger + generic IR + deterministic monotonic merge; delete `_promote_source_scope`; conservative-fallback → lossless core; invariant validators.
- **Phase C — single retrieval truth:** compile `RetrievalPolicy` from the artifact, pass it explicitly; remove `from_champion_plan` seam + legacy re-extraction; backend filters + prefetch ranking + post-fetch hard eligibility + per-source receipts.
- **Phase D — executable compliance:** every hard term → a named capability; SATISFIED only with pass-receipts; unknown stays unknown.
- **Phase E — behavioral tests:** 100 DRB prompts + a stratified set with a gold clause-ledger; metamorphic tests (swap source nouns/languages/dates/negation/exclusions — no code change); malformed-output fuzzing (explicit constraints must survive every case); end-to-end assertions over the *citable source set*, not projection strings.

**Release gates (non-tautological):** 100% of prompt clauses dispositioned; 100% of explicit candidates survive or are visibly unresolved; 0 invented hard constraints; 100% of hard terms have an execution path; 100% contract/policy hash identity across compiler→retrieval→audit; the news/press/2024 probe changes actual eligible sources.

## Honest scope
This is a **core rebuild** (the compiler authority, the IR, the retrieval-policy seam, real enforcement, real tests) — not a patch. But most of the **outer shell survives**, and **faithfulness is never touched**. It is bounded and mechanical, not open-ended research. The current `gate-s0-s5` branch's contract-compiler core and the `_promote_source_scope`/`from_champion_plan` seams are replaced; the schema, ontology, enforcement engine, and audit are reused.
