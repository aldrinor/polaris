RULE NOW — emit the YAML verdict block FIRST. APPROVE this CONCRETE plan or REQUEST_CHANGES with specifics. Read AT MOST the cited regions. NO SPEND / NO NETWORK / NO LLM in the decomposition.

HARD ITERATION CAP: 5. Iter 1 of 5. Front-load all findings; reserve P0/P1 for real execution risks.

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
p0: [...]
p1: [...]
p2: [...]
required_changes: [...]
convergence_call: accept_remaining
```

# Codex brief-gate (iter 1) — PR2 query decomposition on the live path (#951 q1d-a, the S0). NO SPEND / NO NETWORK / NO LLM.

Codex-verified S0 (#950): 4/5 golden Qs (drb_75/76/78/90) ship with no `amplified` list, so a 40-70-word
multi-clause paragraph fires as ~ONE Serper/S2 query (Q76 ≈ 5 sub-questions in one). Keyword engines
retrieve poorly on long paragraphs → low lane-2 coverage → POLARIS can fail a golden Q at 100%
faithfulness. THE single highest-leverage depth gap. Lands on PR1's rerank+reservation base (#959, merged
or queued) so the new sub-queries are NOT truncated by arrival order.

## GROUNDED FACTS (do not re-explore)
- `scripts/run_honest_sweep_r3.py:1639-1641`: `_amplified_effective = list(q.get("amplified", [])) +
  _reg_queries + _trial_queries`, passed to `run_live_retrieval(research_question=q["question"],
  amplified_queries=_amplified_effective, ...)` (:1656-1666). `run_live_retrieval` seeds queries with
  `[research_question]` then extends with `amplified_queries` (`live_retriever.py:1200-1214`), and
  validates them via `validate_amplified_queries(..., always_keep_anchor=True)` when a protocol is given.
- A `_template` (`load_scope_template(q["domain"])`, :1602-1617) and a `scope`/`protocol` object exist in
  scope. The PICO planner `clinical_retrieval/query_planner.plan_queries(decision: ScopeDecision)` is PURE
  (no I/O/LLM/network) but requires a ScopeDecision carrying PICO interpretations — which the golden-Q
  sweep entries may NOT populate. So a question-text clause splitter is the robust PRIMARY; plan_queries
  is an optional augmentation only when a usable ScopeDecision is present.

## CONCRETE PROPOSAL (APPROVE or correct)
A. **New pure module `src/polaris_graph/retrieval/query_decomposer.py`** with
   `decompose_question(question: str, *, max_subqueries: int = 6) -> list[str]`:
   - Deterministic, NO network/LLM. Split the question paragraph into focused sub-query strings on
     clause/sentence boundaries: sentence terminators (`. `, `? `, `; `), enumerations (`1.`/`2)`/`(a)`),
     and top-level coordinating conjunctions (` and `, ` as well as `, ` versus `) — but only split a
     conjunction when BOTH sides carry >=N content words (avoid shredding "safety and efficacy").
   - Normalize each candidate: strip, collapse whitespace, drop fragments with < MIN_CONTENT_WORDS (e.g.
     3) content tokens (reuse the stopword/content-token notion), dedup (case-insensitive / token-set
     Jaccard like `query_planner._dedupe`).
   - Cap at `max_subqueries`; preserve original order (most-leading clause first). Return [] for a short
     single-clause question (no value) so the caller falls back to today's behavior.
B. **Wire into the sweep** (`run_honest_sweep_r3.py`, right before `_amplified_effective`): flag-gated
   (`PG_SWEEP_QUERY_DECOMPOSE`, default "1", env-overridable). When ON, compute
   `_decomposed = decompose_question(q["question"])` and PREPEND it:
   `_amplified_effective = q.get("amplified", []) + _decomposed + _reg_queries + _trial_queries`, then
   DEDUP the combined list (so a hand-authored amplified query that equals a decomposed clause isn't
   duplicated). The anchor full question is still seeded by run_live_retrieval (never lost). Log
   `[q1d] query_decompose: +N sub-queries`.
C. **Bounded:** the sub-queries fan to Serper+S2 (PR1 cap=40 total after dedup + rerank keeps the corpus
   bounded; cost still under `PG_MAX_COST_PER_RUN`). `max_subqueries=6` keeps the per-question query count
   sane. Sub-queries pass the SAME `validate_amplified_queries` scope gate as hand-authored ones.
D. **Tests (offline, socket blocked):** (1) a real 40-70-word golden-style multi-clause question yields
   multiple focused sub-queries (e.g. Q76's 5 sub-topics each appear); (2) "safety and efficacy" is NOT
   split (conjunction guard); (3) a short single-clause question → [] (fallback); (4) dedup: identical
   clauses collapse; (5) cap respected; (6) determinism: same input → same output; (7) the sweep wiring
   prepends decomposed queries and dedups against an existing amplified list (unit-test the list-build
   helper, not a live run).

## Constraints / frozen
- NO SPEND / NO NETWORK / NO LLM in `decompose_question` (pure string ops). snake_case; explicit imports;
  no except:pass; ≤200 LOC. Untouched: strict_verify / D8 / runtime lock / the 5 PR-10 contracts /
  evidence_selector. This only adds INPUT queries; verification semantics unchanged.
- Must not drop the anchor question (run_live_retrieval seeds it) and must not bypass the scope validator.

## The real risks to rule on
1. Over-splitting risk: could the splitter shred a single clinical concept (e.g. "type 2 diabetes",
   "safety and efficacy", "non-small cell lung cancer") into noise queries? Propose the exact conjunction/
   boundary guard (BOTH sides >= N content words; never split inside a known multiword unit — or accept
   the content-word-count guard as sufficient).
2. Query explosion vs the cap: with decomposition + reg + trial queries, is `max_subqueries=6` + PR1's
   total fetch_cap the right bound, or should the sub-query count be tied to the cap?
3. Should plan_queries (PICO) be attempted when a ScopeDecision is available, or is the clause splitter
   alone sufficient for PR2 (PICO as a later PR)?

APPROVE iff the decomposition is pure/no-spend, robustly splits multi-clause golden Qs WITHOUT shredding
single concepts, dedups + bounds the query set, preserves the anchor + scope gate, leaves strict_verify/D8
untouched, and is test-proven.

---

## REVISED SPEC — Codex brief-gate iter-1 REQUEST_CHANGES adopted (binding for the build)
1. **NO bare-comma split.** Split ONLY on: sentence terminators (`.`, `?`, `;`), explicit enumerators
   (`1.`/`2)`/`(a)`), and top-level conjunction/connective boundaries (` and `, ` as well as `,
   ` versus `, ` vs `). Bare commas and weak coordinators are NEVER split points.
2. **Conjunction/connective + `versus`/`vs` splits require BOTH sides to have ≥4 content words.** This
   preserves protected compounds like "safety and efficacy", "type 2 diabetes", "non-small cell lung
   cancer" BY CONSTRUCTION (each side has <4 content words → not split). Same guard for `versus`/`vs`.
3. **Pure list-builder helper** `build_amplified_query_list(*, hand_authored, decomposed, regulatory,
   trial) -> list[str]`: deterministic prepend order (hand_authored + decomposed + regulatory + trial),
   case-insensitive dedup, so the sweep wiring test asserts prepend order / dedup / cap / anchor
   preservation WITHOUT invoking live retrieval.
4. **Clause-splitter-only for PR2.** PICO `plan_queries` augmentation is deferred to a later PR (not in
   the critical path here).
5. Fragment filter ≥3 content words (drop noise); dedup; cap at max_subqueries=6; `[]` for a short
   single-clause question (caller falls back to today's behavior).
6. Tests additionally cover: `versus`/`vs` compact comparator NOT split unless both sides ≥4 content
   words; the `build_amplified_query_list` helper (prepend order + dedup + anchor not in the amplified
   list since run_live_retrieval seeds it separately).
