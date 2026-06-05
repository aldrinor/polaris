# Brief — I-ready-006 (#1082): query-complexity router — right-size simple queries (flag-gated, fail-open)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Finding (`.codex/I-ready-000/findings/query_complexity_routing.md`, P1)
POLARIS applies an IDENTICAL heavyweight deep-research shape to EVERY query — no code path reads a
query-complexity signal between intake and generation. A simple factual query ("Telus and Bell stock
price over 20 years") is forced down the full heavyweight path: the I-cap-005 slate force-ONs
PG_SWEEP_FETCH_CAP=1000, STORM, agentic URL-discovery, the deepener, 4-role per-claim verification,
$25/run — then the clinical adequacy gate (min 8 sources / 2 T1) can't surface peer-reviewed sources
for a stock fact, so it aborts `abort_corpus_inadequate` OR force-fits a 3-6 section clinical-shaped
report whose ungrounded sentences strict_verify drops (`abort_no_verified_sections`). A cost+latency
blowup AND a correctness failure on the easiest class of question.

**Honest scope (not over-claimed):** the LOCKED 5-question DRB-EN benchmark is NOT broken by this (all
5 are heavyweight clinical/policy). The failure surfaces for arbitrary real-user queries via the
general sweep / pipeline-B UI. So this MUST be default-OFF (locked benchmark byte-identical) and
activated on the general/real-user path.

## Current state (verified file:line)
- `run_one_query` scopes every query via the deterministic `run_scope_gate`
  (`run_honest_sweep_r3.py:1674` → `protocol = scope.protocol.to_json_dict()` :1680). No complexity
  classification; nothing varies depth/shape by difficulty.
- `_fetch_cap = int(os.getenv("PG_SWEEP_FETCH_CAP", "40"))` at `:1898`; used by `run_live_retrieval`
  at `:2268`.
- `corpus_adequacy_gate.py:33 AdequacyThresholds` (min_total_sources=8, min_t1_count=2; per-domain
  variants :73/84/92/99/109) — no "simple factual query, a short answer is fine" branch.
- Generator hard-floors >=3 sections (`multi_section_generator.py:517-518 section_count_below_min`).
- A built-but-unwired LLM complexity classifier exists (`nodes/scope.py run_scope()` →
  simple/moderate/complex + estimated_depth) but is LLM-based and wired ONLY to graph_v3 (pipeline-B),
  absent from the benchmark path.

## Proposed scope (route the granularity decisions to you)

**Classifier — DETERMINISTIC, not the LLM run_scope() (DECISION 1 for you):** I propose a cheap
deterministic heuristic (new module `src/polaris_graph/nodes/complexity_router.py`): a query is
`simple` iff it has a price/quantity/factual cue + a named entity + (optional) a temporal range AND
NO comparison/mechanism/causal/synthesis intent; else `complex`; `moderate` between. Returns
`(complexity, confidence, reasons)`. WHY deterministic over run_scope(): (a) §8.4 — run_scope() is an
LLM call; burning an LLM call just to decide a query is simple is self-defeating for a cost-saving
feature; (b) offline-testable, zero spend, deterministic. Your call if you'd prefer run_scope().

**Wiring — flag-gated, fail-open:** call the classifier in `run_one_query` AFTER the scope-gate
(:1680) and BEFORE the fetch-cap read (:1898), gated `PG_COMPLEXITY_ROUTING` (default OFF →
byte-identical). **FAIL-OPEN**: any classifier error OR `confidence < PG_COMPLEXITY_MIN_CONFIDENCE`
OR complexity != "simple" → the FULL heavyweight path (never under-serve a complex/clinical query).
Emit a `complexity_routing` manifest field (complexity, confidence, reasons, applied:bool) — the
routing decision is auditable.

**Right-sizing for `simple` (DECISION 2 for you — scope granularity):** when complexity=="simple"
AND routing ON AND confident:
- (a) lower the fetch cap: `_fetch_cap = int(os.getenv("PG_SIMPLE_FETCH_CAP", "40"))` instead of the
  1000 slate value — fixes the PRIMARY cost/latency blowup. [low risk]
- (b) a "simple" adequacy profile so a short grounded answer is allowed instead of
  `abort_corpus_inadequate` (e.g. min_total_sources=1, min_t1_count=0 for simple). [faithfulness-
  adjacent — but strict_verify + 4-role still drop ungrounded sentences, so a relaxed-adequacy simple
  query can ship ONLY grounded prose or lands at abort_no_verified_sections; faithfulness intact.]
- (c) allow a 1-section direct answer (relax the >=3 section floor for simple). [secondary]
My lean: ship (a)+(b) (the cost fix + the right-sized-answer enabler) in this PR; (c) section-floor
is a smaller follow-up if it bloats the diff past the 200-LOC cap. Your call on whether to include
(c) and on the (b) adequacy-relaxation safety.

**FAITHFULNESS INVARIANT (unchanged):** strict_verify per-sentence provenance + the 4-role D8 binding
gate + provenance-token enforcement are NOT touched. The router only changes WHICH path/thresholds a
classified-simple query takes; every emitted sentence is still verified identically.

**Financial split-adjustment (DECISION 3 — defer?):** the finding wants the simple financial answer
to carry a split-adjustment required-entity. That is a domain-specific answer-contract addition; I
propose DEFERRING it to a follow-up (it needs a financial answer-contract + a stock-split data
source) and keeping #1082 to the general complexity router. Confirm.

## Smoke (offline, no spend)
- Config-invariance: drive a one-line "X stock price over 20 years" vs a multi-hop clinical question
  through the classifier; assert OFF → identical resolution (no complexity read); ON → simple resolves
  to lower cap + relaxed adequacy, complex unchanged.
- Classifier unit: a battery of simple vs complex queries → correct label + confidence; fail-open on
  ambiguous (low confidence → complex).
- Byte-identical-OFF: PG_COMPLEXITY_ROUTING unset → `_fetch_cap` + adequacy thresholds unchanged.
- Manifest: `complexity_routing` field present with the decision.

## Files I have ALSO checked
- The locked benchmark (`run_gate_b.py:723`) feeds only the 5 heavyweight DRB-EN questions → with the
  flag default-OFF the benchmark is byte-identical; Gate-B does NOT set PG_COMPLEXITY_ROUTING.
- strict_verify / provenance_generator / 4-role seam — untouched; the router is pre-retrieval.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
classifier_choice: deterministic_heuristic | run_scope_llm | other
rightsizing_scope: cap_only | cap_plus_adequacy | cap_adequacy_section | other
defer_split_adjustment: yes | no
```
