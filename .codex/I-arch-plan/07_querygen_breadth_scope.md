# DESIGN 7 — QUERY-GEN BREADTH + SCOPE become requirement-aware and adjustable

Author: FABLE 5 (architect brain). Date: 2026-07-10. Branch: `bot/I-deepfix-relaunch` (HEAD 0bde6438).
Grounding: operator's three questions on the FS-Researcher query-gen + search stage. Every cite below is from the real tree on this branch.

---

## 1. The operator's three questions — answered from the code

### Q1 — Is the 35-query ceiling HARD or adjustable?

**Adjustable by env var. Not hardcoded — but also not scope-driven. Production runs sit on the default 35 because nothing sets the var.**

- The cap lives in `_max_queries()` — `src/polaris_graph/retrieval/fs_researcher_query_gen.py:48-50`:
  `return int(os.getenv("PG_QGEN_FS_RESEARCHER_MAX_QUERIES", "35"))`.
  35 is the DEFAULT of an env knob, per the equal-budget bake-off that picked FS-Researcher (#1296).
- Round cap is the same shape: `_max_rounds()` = `PG_QGEN_FS_RESEARCHER_MAX_ROUNDS` default 6 (`fs_researcher_query_gen.py:53-55`).
- The spine never overrides it: `run_honest_sweep_r3.py:10436-10439` calls `_run_fs_researcher_retrieval(...)` WITHOUT a `max_queries` kwarg; `run_fs_researcher_retrieval` (`fs_researcher_query_gen.py:1117-1140`) forwards `None`, so `plan_fs_researcher_queries:874` falls back to the env default.
- The Gate-B benchmark slate does NOT pin `PG_QGEN_FS_RESEARCHER_MAX_QUERIES` (grep of `scripts/dr_benchmark/run_gate_b.py`: no hit) — so the official runs use 35. Only tests set it (`tests/polaris_graph/test_cov_c1_r2_recall_ideepfix001.py:79` sets 200, etc.).
- Two lanes RAISE the budget at run time by exactly their added slice: sub-entity expansion (`fs_researcher_query_gen.py:672-674`, `widen_with_sub_entities`) and the landmark-study lane (`:723-725`, `widen_with_landmark_studies`). The stance lane deliberately does NOT raise it (`:789-792`).

**Honest verdict:** a per-run env knob, raisable/lowerable freely. But no code anywhere reads the USER'S ASK to size it — an "exhaustive global review" and a "one-drug narrow question" both get 35.

### Q2 — How many searches run per sub-query?

**All config/env. No hardcoded k. Per generated sub-query, one `run_live_retrieval` call fires three search backends plus a fetch budget:**

Every FS sub-query goes through `_iter_per_query_retrieve` (`scripts/run_honest_sweep_r3.py:10406-10433`) → `run_live_retrieval(... max_serper=_max_serper, max_s2=_max_s2, fetch_cap=_fetch_cap ...)`.

| Knob | Read at | Default | Gate-B slate pins |
|---|---|---|---|
| `PG_SWEEP_MAX_SERPER` (Serper results/query) | `run_honest_sweep_r3.py:9734` | 12 | 100 (`run_gate_b.py:560`) |
| `PG_SERPER_TOTAL_PER_QUERY` (paginated total) + `PG_SERPER_MAX_PAGES` (default 3) | `live_retriever.py:844,848`; provider page max 20 at `:786` | one page | 60 (`run_gate_b.py:565`) |
| `PG_SWEEP_MAX_S2` (Semantic Scholar/query) | `run_honest_sweep_r3.py:9735`; S2 API hard-caps 100/call (`live_retriever.py:932`) | 12 | 100 (`run_gate_b.py:561`) |
| OpenAlex search (reuses `limit=max_s2`) | `live_retriever.py:5835-5841`; cursor paging `PG_OPENALEX_PER_PAGE`/`PG_OPENALEX_MAX_PAGES` (`domain_backends.py:795-800`) | 12, single page | 100+paging |
| `PG_SWEEP_FETCH_CAP` (URLs actually fetched per retrieval call, after dedup) | `run_honest_sweep_r3.py:9736`, doc `:9715-9717` | 200 | 740 (`run_gate_b.py:559`) |

Note: because the FS lane makes ONE `run_live_retrieval` call per sub-query, `PG_SWEEP_FETCH_CAP` acts per-sub-query on this lane. Retriever-side fallback defaults exist too (`PG_LIVE_MAX_SERPER`/`PG_LIVE_MAX_S2` = 20, `live_retriever.py:114-115`) but the spine always passes its own values.

**Honest verdict:** fully env-adjustable, zero hardcoded k. Same caveat as Q1: static per run, never sized by the ask.

### Q3 — How is search SCOPE controlled when the user prompt carries scope?

**The scope IS parsed into structured constraints, and it DOES steer — but the steering is uneven: strong after retrieval, thin at the search backends, and indirect in query generation. It is genuinely dynamic per user ask only for the date window (OpenAlex only) and language.**

1. **The parsers (real, per-question, dynamic).** `src/polaris_graph/retrieval/intake_constraint_extractor.py`:
   - `extract_constraints_regex` (`:225`) → `UserConstraints` (`:137-199`): date window incl. MONTH precision ("before June 2023" → end `2023-06`), relative windows ("last 5 years", `:80`), language (`:114-122`), journal-only (extracted, DORMANT per operator veto, `:124-127`), timeline strictness `weight|hard` ("strictly before", "no sources after" → hard, `:85-112`).
   - `extract_scope_constraints` (`:1035`) → `ScopeConstraints` (`:761-779`): ontology facets over dimensions `source_type | jurisdiction | geography | language` with ops `include|prefer|exclude` and strictness `weight|hard` (`ScopeFacet`, `:713-726`), plus named pin/exclude sources (`NamedSource`, `:740-757`).
   - Both run at the scope gate: `src/polaris_graph/nodes/scope_gate.py:1010-1059` writes `user_constraints` + `scope_constraints` into protocol.json, fills `date_range` only where the template left it None (`:1020-1030`), and promotes an extracted language into `languages` (`:1071-1076`).
   - Flag-gated, DEFAULT OFF in code, pinned ON by the slate: `PG_EXTRACT_USER_CONSTRAINTS` (`run_gate_b.py:5831`), `PG_EXTRACT_SCOPE_CONSTRAINTS` (`run_gate_b.py:619`).

2. **Where it reaches the search backends — ONE filter, one backend.** The parsed date window becomes a native API filter ONLY at OpenAlex: when `PG_OPENALEX_DATE_FILTER` is ON (default OFF, `live_retriever.py:2437-2442`; slate pins 1 at `run_gate_b.py:1745`) and the question states a window, `run_live_retrieval` fires an EXTRA date-scoped lane `openalex_search(q, from_date=…, to_date=…)` (`live_retriever.py:5873-5893`; window extraction `_openalex_date_window` `:2475-2492`; the actual `filter=from_publication_date:..,to_publication_date:..` in `domain_backends.py:774-813`). Strictly additive — the unscoped base lane still runs (union, no drop).
   **Serper receives ZERO scope parameters** — its payload is `{"q", "num", "page"}` only (`live_retriever.py:794`): no date (`tbs`), no geography (`gl`), no language (`hl`). **S2 receives ZERO scope parameters** — params are query/fields/limit only (`live_retriever.py:929-933`); `year` is a returned field, never a filter.

3. **Where it reaches query GENERATION — text-only, not structured.** The scope anchor (`_scope_anchored()`, default ON, `fs_researcher_query_gen.py:369-384`) carries the WHOLE question text into the TOC/facet prompts, so scope words the user wrote tend to land in query wording — implicit, LLM-mediated, unguaranteed. Exactly one lane consumes a PARSED constraint: the landmark expander constrains its study enumeration to `extract_constraints_regex(question).date_end_iso()` (`fs_researcher_query_gen.py:711-717`). Language is handled by the R5 multilingual lane (default ON, `PG_MULTILINGUAL_RETRIEVAL`): detects the task's language and adds native-language queries with a budget reserve (`:604-635`, `_reserve_native_within_budget` `:337-366`). The structured geography / source-type / jurisdiction facets are NEVER injected into query generation.

4. **Where it lands hardest — AFTER retrieval, at selection.** `src/polaris_graph/retrieval/constraint_enforcement.py:1-70` (gated `PG_SCOPE_CONSTRAINT_ENFORCE`, default OFF, slate pins 1 at `run_gate_b.py:618`): per-URL demote weights for out-of-scope/out-of-window rows, HARD grounding masks for restrict-to / "strictly before" (masked from `evidence_for_gen`, KEPT in pool + PRISMA-style disclosure rows), pin boosts for named includes. §-1.3-clean: weight/mask/disclose, never delete.

**Honest verdict:** the audit's claim "scope filters are parsed and steer retrieval" is TRUE for parsing and post-retrieval enforcement, PARTIALLY true at search time (date→OpenAlex extra lane; language→query expansion), and FALSE for Serper/S2 filters and for geography/source-type steering of searches. And none of the breadth knobs (Q1/Q2) listen to scope at all.

---

## 2. The design — requirement-aware, adjustable breadth + scope-through-everything

Surgical (§-1.3): re-wire existing seams; no new hard filters on credible in-scope sources; every scoped search lane is ADDITIVE (union with the base lane, mirroring the proven `PG_OPENALEX_DATE_FILTER` pattern); the faithfulness engine untouched.

### D1 — One breadth resolver, sized by the ask, bounded by env

New pure module `src/polaris_graph/retrieval/breadth_resolver.py`:

`resolve_breadth(question, protocol, facets) -> BreadthPlan{query_budget, serper_k, s2_k, serper_total, fetch_cap, breadth_class, rationale}`

Inputs, in precedence order:
1. **Explicit env overrides win absolutely** (LAW VI, unchanged semantics): if `PG_QGEN_FS_RESEARCHER_MAX_QUERIES` / `PG_SWEEP_MAX_SERPER` / `PG_SWEEP_MAX_S2` / `PG_SERPER_TOTAL_PER_QUERY` / `PG_SWEEP_FETCH_CAP` is EXPLICITLY set (present in env), the resolver passes it through verbatim. Today's behavior is the fallback, byte-identical, when the resolver flag is off.
2. **Explicit user breadth directive** (deterministic lexicon + GLM confirm, same regex-primary/LLM-fallback pattern as `intake_constraint_extractor`): "exhaustive / comprehensive / systematic review / global landscape / all available evidence" → class WIDE; "brief / quick / overview / summary" → class NARROW; else class STANDARD.
3. **Structural width of the ask**: facet count from the expert-facet planner (`plan_expert_facets` already sizes the frontier by the question — `expert_facet_planner.py:330`), multilingual profile (adds the R5 reserve), scope width (a multi-jurisdiction geo list or a >10-year window widens; a single-drug single-outcome PICO narrows).

Output sizing is a lookup table in `config/settings/breadth_classes.yaml` (LAW VI — no magic numbers in code): e.g. NARROW `{query_budget:15, serper_total:20, fetch_cap:120}`, STANDARD `{35, 60, 300}`, WIDE `{80, 100, 740}`, each row env-overridable. The budget stays a compute-safety CEILING sized to the requirement — never a target the loop pads to (§-1.3: issued count still EMERGES from facets + dedup + wall + checklist saturation; the widen lanes still raise it additively).

Wiring: one flag `PG_BREADTH_RESOLVER` (default OFF = byte-identical). Spine seam: `run_honest_sweep_r3.py:9734-9736` consults the resolver for `_max_serper/_max_s2/_fetch_cap`; qgen seam: pass `max_queries=plan.query_budget` into `_run_fs_researcher_retrieval` at `run_honest_sweep_r3.py:10436` (the kwarg already exists end-to-end, `fs_researcher_query_gen.py:1123` — today it is just never used). The plan + rationale is logged and written into the manifest (disclosed, auditable).

### D2 — Scope flows into query generation as STRUCTURED directives

Today qgen sees only raw question text. Change: `plan_fs_researcher_queries` / `_plan_expert_facet_queries` accept an optional `scope: dict` (the protocol's `user_constraints` + `scope_constraints`, already built at `scope_gate.py:1148-1149`; the spine has `_retrieval_protocol` in hand at `run_honest_sweep_r3.py:10422`). Uses:
- A compact "SCOPE DIRECTIVES" block appended to the TOC prompt (`fs_researcher_query_gen.py:905-916`), the facet-planner prompt, and the per-todo query-derivation prompt: date window, geography facets, source-type facets, language, named pins. Generated queries then CARRY the scope ("… randomized trials Europe 2019..2023") instead of hoping the LLM keeps it.
- The landmark-lane pattern (`:711-717`) generalizes: each additive lane receives the parsed window/geo instead of re-parsing or ignoring it.
- New author/named-source support in the extractor: "papers by <Name>" / "according to <Name>" → `NamedSource(include)` (the dataclass already exists, `intake_constraint_extractor.py:740`) driving a dedicated author-search lane (S2 `/author` + OpenAlex `author.id` filter), additive.
Flag `PG_SCOPE_TO_QGEN` (default OFF). Fail-open: any scope-block build error → today's prompts.

### D3 — Scope flows into ALL backend filters (additive scoped lanes)

Extend the proven OpenAlex-date-lane union pattern to the other backends and dimensions — each an EXTRA scoped call alongside the untouched base call, each behind its own kill-switch, each fail-open:
- **Serper**: date window → `tbs=cdr:1,cd_min:…,cd_max:…`; geography facet → `gl=<country>`; language → `hl=<code>` (`_serper_fetch_page` payload seam, `live_retriever.py:794`). Flag `PG_SERPER_SCOPE_FILTER`.
- **S2**: date window → `year=YYYY-YYYY` param; peer-reviewed source-type facet → `publicationTypes=JournalArticle` on the SCOPED lane only (journal-only stays DORMANT as a global drop per operator veto — this only ADDS a scoped discovery lane, drops nothing) (`_s2_bulk_search` params seam, `live_retriever.py:929-933`). Flag `PG_S2_SCOPE_FILTER`.
- **OpenAlex**: date already done; add `language:<code>` and, for named-author lanes, `author` filters (`domain_backends.py:774` signature already extensible). Extend flag `PG_OPENALEX_DATE_FILTER` → `PG_OPENALEX_SCOPE_FILTER` (alias kept).

§-1.3 discipline, stated once and binding for D1-D3: the user's EXPLICIT scope is a user-requested constraint — distinct from credibility weighting. Search-side it may only ADD scoped lanes (more in-scope discovery), never remove the base lane. Post-retrieval it stays exactly the existing weight/mask/disclose enforcement (`constraint_enforcement.py`) — hard masks only for the user's own explicit hard directives, everything kept in pool + disclosed, credible in-scope sources never silently dropped. No lane, resolver, or filter may ever be tuned to hit a breadth NUMBER (the §-1.3 day-waster ban).

### D4 — Max parallelism stays

`PG_QGEN_PARALLEL_QUERIES` (bounded pool, order-stable, `fs_researcher_query_gen.py:58-70,115-199`) is orthogonal and untouched; the slate pins it >1. A wider WIDE-class budget rides the same wall (`PG_RETRIEVAL_QUESTION_WALL_SECONDS`) — time, not cost, is the constraint.

---

## 3. SECTION definition — QUERYGEN-BREADTH-SCOPE

**Checkpoint boundary.** Section input: clean question + protocol.json (scope blocks) + BreadthPlan. Section output artifact: `outputs/<run>/qgen_checkpoint.json` = the resolved BreadthPlan + the full sub-query set (each query stamped: lane of origin, scope directives applied, issued/pending) + the per-query result set (candidate URLs + per-backend counts). On crash/resume: load the checkpoint, re-issue ONLY pending queries (memory rule: resume from closest checkpoint, never re-run fresh).

**Fast hamster loop** (minutes, no full pipeline): run qgen in search-only mode (real Serper/S2/OpenAlex discovery, `fetch_cap=0`-style candidate capture, no content fetch, no generation) over a fixed 6-question probe slate — 2 NARROW, 2 STANDARD, 2 WIDE, incl. one dated ("before June 2023"), one geo-scoped, one non-English. Each loop iteration: change resolver/lane code → rerun slate → read the emitted queries and request logs LINE BY LINE.

**Lock-down bar** (all must pass before the section freezes; §-1.1 line-by-line, not counts-as-quality):
1. Budget resolution: each probe question resolves to its documented class; an explicit env override beats the resolver; flag-OFF is byte-identical to today (35/12/12/200).
2. Scope-in-queries: read EVERY issued query on the scoped probes — each carries the question's subject anchor AND the applicable scope terms; zero queries contradict the window/geo/language.
3. Backend filters fire: request logs show `tbs`/`gl`/`hl` on the scoped Serper lane, `year`/`publicationTypes` on the scoped S2 lane, date/language filters on OpenAlex — AND the unscoped base lanes still fired (union proof).
4. No-drop proof: candidate-set with scoped lanes ON is a superset-or-equal of base-only on the same slate (additive, zero sources lost).
5. Checkpoint + resume: kill the run mid-frontier; resume issues exactly the pending remainder, no re-plan, no duplicate issues.
6. Activation markers: every lane emits its `[activation]` fire/fail-open marker (existing pattern, `fs_researcher_query_gen.py:134-137,679,755,827`) so a dark lane is detectable.

**Effort split:** D1 + spine wiring ~1 day; D2 ~1 day; D3 ~1.5 days (three backends + tests); hamster harness ~0.5 day. Each D is its own dual-gated (Codex + Fable) diff.
