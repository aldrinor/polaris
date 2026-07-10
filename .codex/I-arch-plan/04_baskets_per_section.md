# DESIGN 4 — BASKETS-PER-SECTION (section-scoped consolidation and composition)

Author: FABLE 5 (architect brain). Date: 2026-07-10. Branch: `bot/I-deepfix-relaunch`.
Grounding: audit `.codex/I-arch-audit/fable_orchestration_audit.md` stage 6 (line 14) + ranked gap #6 (line 43), with spillover into stage 5 / gap #3 (outline is title-starved). All file:line cites are from the real tree on this branch.

---

## 1. The problem, in one paragraph

Consolidation is corpus-GLOBAL and section membership is ROW-level, and the two only meet through a late lookup. `finding_dedup.dedup_by_finding` clusters the whole generator pool into same-claim groups (`src/polaris_graph/synthesis/finding_dedup.py:1946-2217`, called on the full `evidence_for_gen` at `scripts/run_honest_sweep_r3.py:14662-14665`); the credibility pass builds one global basket per claim cluster (`src/polaris_graph/synthesis/credibility_pass.py:1751,1759,1784`, consuming the finding_dedup grouping under `PG_BASKET_CONSUME_FINDING_DEDUP` — slate-ON at `scripts/dr_benchmark/run_gate_b.py:1352`). Separately, the outline assigns raw ROW ev_ids to sections (`src/polaris_graph/generator/multi_section_generator.py:2140-2355` on-mode; `_call_outline` at `:2547` off-mode over a 150-row title menu, `:730-775`). The only bridge is `_section_baskets_for_compose` (`src/polaris_graph/generator/verified_compose.py:3103-3173`): "a basket belongs to the section if ANY of its member evidence_ids is in the section's assigned ev_ids" (`:3122-3125`). That bridge leaks in both directions: baskets whose members were never outline-assigned are STRANDED (measured drb_72: ~657 baskets → 53 rendered sentences, ~600 stranded — `verified_compose.py:3520-3525`), and baskets whose members straddle sections are pulled into EVERY such section, so the same claim can compose repeatedly (the render-side `cross_section_repetition_guard` exists because of this). The F1 patch (`route_orphan_baskets_to_section_plans`, `verified_compose.py:3598-3668`, slate-ON `run_gate_b.py:1289`) gives orphans a home by MUTATING `plan.ev_ids` via a lexical title-overlap heuristic — a bolt-on that proves the missing primitive: baskets were never first-class citizens of sections.

**The rule this design implements:** dedup/consolidation keeps its GLOBAL identity (same claim is one basket run-wide, corroboration counted once), but every basket is then GROUPED UNDER the outline sections — one designated PRIMARY home plus any number of CORROBORATING memberships — and synthesis composes each section from its basket group, not from raw rows. A rich source (and a rich basket) may serve multiple sections; the full prose treatment of a claim renders exactly once.

---

## 2. As-built map — where baskets and sections live today

| Step | Where (file:line) | What it does today | Section-aware? |
|---|---|---|---|
| Same-work fold + claim clustering | `finding_dedup.py:624-722` (same-work), `:1946-2217` (`dedup_by_finding`) | Global clusters with `member_indices` + `member_hosts` + `corroboration_count`; keep-all under `PG_SWEEP_CREDIBILITY_REDESIGN` (`run_gate_b.py:948`) | No |
| Qualitative baskets + NLI unions | `finding_dedup.py:1777-1943` (greedy + 3 NLI passes) | Global; O(n²) pair caps: `PG_FINDING_DEDUP_NLI_MAX_PAIRS`=20000 (`:1004-1005`), nominate cap (`:1048-1049`); over cap ⇒ SKIP/under-merge (`:1500-1511`, `:1635-1644`) | No — and the global n is what trips the cap |
| Basket assembly + isolated verify | `credibility_pass.py:1332+` (`_assemble_baskets`), regroup `:1152-1329` | One `ClaimBasket` per global cluster; per-member isolated verify; `verified_support_origin_count` | No |
| Section membership (rows) | `multi_section_generator.py:2140-2355` (on-mode, provenance-first via `relevant_section_indices` `:2216-2233`), `_call_outline` `:2547` (off-mode), facet outline `:820-844` (slate-ON `run_gate_b.py:1288`) | Outline assigns `ev_ids` per `SectionPlan`; a row may repeat across sections; per-section char budget (`PG_MAX_EV_PER_SECTION`=40, `run_gate_b.py:789`; payload-tracking F2 `:1290`) | Rows only — baskets invisible |
| The bridge | `verified_compose.py:3103-3173` | Intersection lookup, recomputed per section; + B1 debate con-basket augment (`:3126-3159`); + off-topic basket screen (`:3160-3172`) | Derived, incomplete, duplicative |
| The orphan patch | `verified_compose.py:3598-3668`, called at `multi_section_generator.py:9762` (after baskets exist ~`:9465`, before section generation) | Appends orphan baskets' member ev_ids to the best title-overlap plan, else a residual section | Bolt-on; mutates plans |
| Per-section per-basket compose | `verified_compose.py:2754` (`_compose_section_per_basket`), wired `multi_section_generator.py:5444,5490` under `PG_SYNTH_PRIMARY`/`PG_ABSTRACTIVE_WRITER` (`run_gate_b.py:1639,838`) | Composes ONE verified treatment per basket in the section's derived set; basket-scoped verify pool (`verified_compose.py:269`) | Consumes the leaky bridge |
| Depth synthesis | `run_honest_sweep_r3.py:16548-16620`, `depth_synthesis.py:1-77` | Global top-of-report cross-source digest from the SAME global baskets | Global by design (unchanged here) |

Key sequencing fact (verified): baskets are assembled INSIDE `generate_multi_section_report` after the outline plans exist and BEFORE per-section generation — the orphan-routing call at `multi_section_generator.py:9762` is exactly the seam where a basket→section map belongs. The finding_dedup clusters exist even earlier (sweep-level, `run_honest_sweep_r3.py:14662`), i.e. BEFORE the outline call — so an outline that reads consolidated-claim digests is feasible without reordering the pipeline.

### The four measured defects this design removes

1. **Stranded baskets** — ~600 of 657 verified baskets never rendered (`verified_compose.py:3520-3525`); F1 patches it lexically.
2. **Cross-section claim duplication** — the ANY-member intersection (`:3122-3125`) composes one basket in every section any member touches; repetition is then patched at render (audit stage 8).
3. **Outline never sees consolidation** — it plans over ≤150 raw-row titles (`multi_section_generator.py:730-775`), blind to corroboration structure (audit gap #3): two sections can be planned around what is actually ONE consolidated claim.
4. **Global O(n²) NLI recall loss** — the qualitative keystone/nominate passes SKIP whole-corpus over 20000 pairs (`finding_dedup.py:1500-1511,1635-1644`) — the drb_72 large-corpus under-merge. Grouped under sections, n per group is 10-60 baskets ⇒ pairs ≤ ~1800 ⇒ the cap never trips.

---

## 3. The design

The inversion, in one line: **consolidate globally (unchanged identity) → outline over basket digests → assign BASKETS to sections with roles → compose per-section basket groups.** Today's order is outline(rows) → baskets(global) → intersect.

### D1 — New pure module: `src/polaris_graph/synthesis/section_basket_map.py`

One responsibility (LAW V): build the deterministic basket→section map. No LLM, no network, pure functions.

```python
@dataclass
class SectionBasketView:
    claim_cluster_id: str          # the GLOBAL basket id — never a second identity system
    role: str                      # "primary" | "corroborating"
    section_member_ev_ids: list[str]  # the members that matched THIS section (the facet)
    match_signals: dict            # {"provenance": n, "subquery": n, "topical": n} — audit trail

@dataclass
class SectionBasketMap:
    views_by_section: dict[int, list[SectionBasketView]]   # section index → views
    primary_section_by_cluster: dict[str, int]             # exactly ONE home per basket
    residual_section_index: int | None                     # keep-all residual, if created
    stranded_count: int                                    # MUST be 0 (invariant; disclosed)
```

Inputs: `credibility_analysis.baskets` (the global baskets), the `SectionPlan` list, the evidence pool, and `sub_queries` + per-row `query_origin`/`retrieval_subquery` provenance (the same fields Design 1 formalizes; accessor precedent `evidence_selector.py:1273-1275`).

**Assignment algorithm (deterministic, three signals, §-1.3 weight-not-filter):**

1. **Candidate sections per basket** = union of:
   - (a) *provenance floor*: sections whose `ev_ids` intersect the basket's `supporting_members` ev_ids — byte-for-byte today's `_section_baskets_for_compose` rule (`verified_compose.py:3122-3125`), so no basket is ever LESS reachable than today;
   - (b) *sub-query lineage*: sections whose `sub_query_indices` match a member row's originating sub-query — the SAME mapping the plan-sufficiency gate and on-mode assignment already use (`relevant_section_indices`, `multi_section_generator.py:2216-2233`);
   - (c) *topical overlap*: basket claim/subject/predicate content words vs section title+focus, threshold ≥1 shared word — the F1 heuristic promoted from patch to signal (`verified_compose.py:3563-3580,3640-3648`).
2. **Primary home** = the candidate with the highest weighted score (provenance count × w_p > sub-query matches × w_q > topical overlap × w_t; weights env-tunable, LAW VI). Tie → lowest section index. This is the keep-first deterministic pattern finding_dedup already locks (`finding_dedup.py:1322-1341`).
3. **Corroborating memberships** = every other candidate section, each view carrying ONLY the `section_member_ev_ids` that matched that section — the per-section FACET of a rich basket.
4. **No candidate at all** → the basket goes primary into ONE appended residual section (`"Additional Corroborated Findings"`, reusing `_RESIDUAL_COVERAGE_TITLE`, `verified_compose.py:3540`). Keep-all: `stranded_count` is structurally 0.

Nothing is dropped, capped, or targeted: the map is pure placement + roles. Global `corroboration_count` / `verified_support_origin_count` / `member_hosts` are read-only pass-throughs — corroboration is NEVER split per section.

### D2 — Compose consumes the map (roles kill duplication at the source)

`_section_baskets_for_compose` (`verified_compose.py:3103`) gains a precomputed-map fast path: when a `SectionBasketMap` is attached (threaded through `generate_multi_section_report` alongside `credibility_analysis`), return the section's views instead of recomputing the intersection. Role policy:

- **primary** view → the full per-basket verified treatment via the UNCHANGED `_compose_section_per_basket` (`verified_compose.py:2754`) — exactly today's path, now guaranteed to fire exactly once per basket run-wide.
- **corroborating** view → the basket is SUBMITTED to the section writer restricted to its `section_member_ev_ids` facet: it feeds the multicited corroboration sentence (`compose_basket_multicited_sentence`, `verified_compose.py:2229`, slate-ON `PG_VERIFIED_COMPOSE_MULTICITED` `run_gate_b.py:1317`), the numeric comparator, and the B1 debate/refuter seams (`verified_compose.py:3126-3159`) — but does NOT re-emit the full claim narrative. The claim's prose home is its primary section; other sections cite its facet.

Faithfulness lock: the basket-scoped verify pool (`_basket_scoped_pool`, `verified_compose.py:269`) still sees the basket's FULL isolated-SUPPORTS member set in both roles — restricting the writer's facet never shrinks the verify pool, so no sentence can newly pass or fail. strict_verify / NLI-enforce / 4-role D8 / provenance are byte-untouched.

The B1 con-basket augment and the off-topic basket screen (`verified_compose.py:3126-3172`) run on the returned view list unchanged — they are orthogonal verdict-keyed passes.

### D3 — Outline plans over basket digests (fixes gap #3 at the same seam)

The off-mode `_call_outline` menu (≤150 raw-row `ev_id + tier + title` lines, `multi_section_generator.py:730-775`) is replaced — under its own flag — by CONSOLIDATED-CLAIM digests derived from the sweep-level `dedup_by_finding` result that already exists BEFORE the outline (`run_honest_sweep_r3.py:14662-14697`; clusters carry `finding_key`, `corroboration_count`, `member_hosts`): one line per cluster = representative claim text (≤160 chars) + corroboration_count + best tier + member count, ordered by corroboration×weight, with each digest listing its member ev_ids so the outline's `ev_ids` assignment stays row-compatible downstream. The planner now sees the CLAIM STRUCTURE of the corpus, not row titles — so it cannot plan two sections around one consolidated claim, and a 40-source claim is visible as one heavy item instead of 40 menu rows (the menu-size truncation-risk noted at `:763-774` also shrinks). Identity alignment is by construction: the basket consolidator consumes the same finding_dedup grouping (`credibility_pass.py:1152-1329`, `PG_BASKET_CONSUME_FINDING_DEDUP=1` `run_gate_b.py:1352`), so outline-time clusters and compose-time baskets are the same partition (modulo the pass's own merge-only refinements).

On-mode (research_plan / STORM / facet) outlines are untouched — the map binds to whatever plans exist (see §6).

### D4 — Section-scoped merge refinement (recovers the over-cap recall)

Within each section's view list, run ONE additional merge-only pass over basket HEAD claims: containment nomination + strict bidirectional-NLI confirm + polarity hard-block + direct-edge keep-first — reusing `_apply_qualitative_containment_nli_grouping` verbatim (`finding_dedup.py:1426-1562`; it is already row-shape-agnostic over `[shingles, polarity, [indices]]` triples). Per-section pair counts (10-60 baskets ⇒ ≤ ~1800 pairs) sit far under the 20000 cap that silently skips the GLOBAL pass on large corpora (`:1500-1511`) — this is where the drb_72 under-merge recall comes back. A confirmed merge RELABELS the absorbed basket's views onto the surviving global `claim_cluster_id` (merge-only, keep-all, corroboration rises; the same union semantics as `_regroup_graph_by_finding_dedup`, `credibility_pass.py:1159-1179`) and the relabel is applied GLOBALLY (all sections + edges), never forked per section. Rides the resident local cross-encoder the slate already loads (`PG_CONSOLIDATION_NLI=1` `run_gate_b.py:1527`) — zero new model, zero paid spend.

### D5 — What is absorbed / retired

- `route_orphan_baskets_to_section_plans` (`verified_compose.py:3598-3668`) becomes INERT when the map is on: its coverage guarantee (zero stranded) is a native invariant of D1 step 4. The `plan.ev_ids` in-place mutation (`:3583-3595`) ends. Flag-OFF keeps it byte-identical (it is the legacy path's patch).
- The per-section recomputed intersection in `_section_baskets_for_compose` becomes the flag-OFF fallback only.
- The render-side `cross_section_repetition_guard` STAYS as a backstop — expected fire count drops to ~0 (an acceptance metric, not a removal).

### Flags (LAW VI — all env, read at call time, default-OFF byte-identical)

| Flag | Default | Slate | Governs |
|---|---|---|---|
| `PG_SECTION_BASKET_MAP` | OFF | ON | D1 build + D2 consume + D5 absorb |
| `PG_SECTION_BASKET_MAP_REFINE_NLI` | ON (inert unless master ON) | ON | D4 per-section merge refinement |
| `PG_OUTLINE_BASKET_DIGESTS` | OFF | ON | D3 digest menu (off-mode outline only) |
| `PG_SECTION_BASKET_ROLE_POLICY` | `facet` | `facet` | corroborating-role writer policy (`facet` = facet-scoped members; `full` = legacy full-basket submit, for A/B) |
| weight/threshold knobs | w_p=3, w_q=2, w_t=1, topical ≥1 | — | assignment scoring |

---

## 4. §-1.3 conformance + faithfulness lock (explicit)

- **WEIGHT, don't FILTER:** the map assigns and role-tags; it deletes nothing. Every basket keeps every member; low-weight sources stay in their baskets at their weight.
- **CONSOLIDATE, don't DROP:** D4 is merge-only (corroboration can only rise); D1 step 4 guarantees zero stranded baskets — the design EXISTS to stop the biggest measured drop (600/657).
- **BASKET FAITHFULNESS:** verify pools stay basket-scoped and FULL in both roles; the isolated per-member verify (`credibility_pass.py:1332+`), strict_verify, NLI-enforce, 4-role D8, provenance/span-grounding are byte-untouched. The map changes WHICH baskets a section's writer is submitted and in what role — the same class of decision `_section_baskets_for_compose` already makes today, made complete and deterministic.
- **No number-forcing:** no breadth target, no cap, no thinner. Section basket counts EMERGE from the corpus and the outline.

---

## 5. Parallelism, determinism, performance (box = 128 cores / 2 TB; target MINUTES)

- **Map build (D1):** pure CPU, O(baskets × sections) with precomputed per-section ev_id sets and token sets; drb_72 scale (787 sources, ~657 baskets, ~20-40 sections) ⇒ well under 5 s single-threaded; embarrassingly parallel over baskets if ever needed. Deterministic: sorted inputs, keep-first ties, no wall-clock dependence.
- **D4 refinement:** per-section NLI groups run CONCURRENTLY across sections (bounded pool, `PG_FINDING_DEDUP_NLI_WORKERS` pattern `finding_dedup.py:1094-1107`); within a section the direct-edge keep-first result is worker-count-independent (proven pattern, `:1252-1256`). Wall budget per section mirrors `PG_FINDING_DEDUP_NLI_WALL_SECONDS` (`:1126-1144`) — over-wall degrades to under-merge, never blocks.
- **Compose:** sections already generate concurrently (`_gather_sections_isolated`, `multi_section_generator.py:976-1050`; env `PG_PARALLEL_SECTIONS`, `:9768+` comment). With exclusive primary-basket ownership per section, sections share NO mutable compose state — raise section concurrency into the 32-64 band per the parallelism mandate, LLM-stage bound.
- **Fast subset + full run:** the module runs identically on a 30-basket fixture (seconds, offline) and a banked full-run checkpoint (see §7a).

---

## 6. Requirement-awareness (not hardcoded)

The map is OUTLINE-AGNOSTIC: it reads plans generically (`title`, `focus`, `ev_ids`, `sub_query_indices` — the exact attribute surface `SectionPlan` `multi_section_generator.py:1102` and the planner items already expose) and never hardcodes section names, counts, or domains. Whatever produced the outline — clinical 8-title list (`:784-793`), generic 6 (`:800-807`), facet-emergent (`:820-844`), STORM scaffold (`:2411`), research_plan, or a future user-deliverable-spec outline (Design 5) — baskets group under it unchanged. A user asking for a custom structure/tone gets baskets grouped under THEIR sections with zero code change; the role policy knob bends verbosity (facet vs full) without touching identity. No clinical literal enters the module.

---

## 7. Self-contained section: hamster loop, acceptance bar, checkpoints

### 7a. Fast isolation hamster loop (quick test → read every line → Fable investigate → Opus build → retest, concurrent)

- **Harness:** `scripts/replay_section_basket_map.py` — loads a BANKED run's `corpus_snapshot` + credibility disclosure (baskets with members/verdicts/corroboration) + outline plans from the run dir (all already persisted artifacts: snapshot write `run_honest_sweep_r3.py:15046` area; `manifest['finding_dedup']` `:14675-14697`), builds the map OFFLINE, and emits the full assignment table: one line per basket = `claim_cluster_id | head-claim (80 chars) | primary section | corroborating sections | signals {p,q,t} | member count | corroboration`. Pure + deterministic ⇒ each loop iteration is SECONDS. D4 refinement replays with the local cross-encoder (no paid calls) or a `entail_fn` stub (the injection seam already exists, `finding_dedup.py:1430`).
- **Loop:** run harness → Fable reads EVERY assignment line (§-1.4 forensic read: misplaced homes, wrong facets, suspicious residuals) → Fable states the root cause → Opus edits the module → re-run in seconds. Multiple hypotheses test concurrently (the harness takes `--weights`/`--policy` overrides so A/B maps render side-by-side).
- **Fast subset:** `tests/fixtures/section_basket_map/` — a 30-basket, 5-section miniature distilled from drb_72 (real data, not synthetic; LAW II) exercising every branch: multi-home basket, orphan→residual, tie-break, qualitative basket, refuter pair, captcha-stripped work.
- **Full scale:** the banked drb_72 checkpoint (657 baskets) is the load/recall test — the SAME harness, one flag.

### 7b. Lock-down acceptance bar (all behavioral, line-by-line auditable)

1. **Coverage:** `stranded_count == 0` on the drb_72 replay (vs ~600/657 measured today); every basket appears in ≥1 section's views.
2. **Uniqueness:** exactly one primary home per basket; `len(primary_section_by_cluster) == len(baskets)`.
3. **No duplication:** in a full rendered report, a `claim_cluster_id`'s full prose treatment appears in exactly its primary section; `cross_section_repetition_guard` fire count ~0 (logged, compared before/after).
4. **Determinism:** byte-identical `section_basket_map.json` across 3 repeated builds, any worker count, and any input-order permutation of baskets/plans.
5. **Faithfulness frozen:** zero diffs under `generator/provenance_generator.py`, strict_verify, D8/`roles/*`; every rendered sentence still carries a valid `[#ev:...]` token and passes the UNCHANGED strict_verify; a §-1.1 claim-by-claim line-by-line audit of one full before/after report (cited-span text, PRISMA/GRADE where clinical) shows no new UNSUPPORTED/FABRICATED verdicts.
6. **OFF byte-identity:** `PG_SECTION_BASKET_MAP=0` ⇒ legacy intersection + F1 orphan path, byte-identical (existing tests green untouched).
7. **Recall:** D4 refinement produces ≥1 confirmed merge on the drb_72 replay where the global pass skipped over-cap (the honest eligible-yet-zero rule applies: 0 with a logged `[activation]` marker and no over-cap skip is acceptable; 0 BECAUSE of a skip is a FAIL).
8. **Wall-clock:** map build <5 s at drb_72 scale; D4 <60 s wall per section (degrade = under-merge, logged).

### 7c. Checkpoint at the input/output boundary (crash-resilient resume)

- **Input boundary artifacts** (written BEFORE the map builds, at the `multi_section_generator.py:9762` seam): `checkpoints/baskets_global.json` (basket heads, members, verdicts, corroboration, edges) + `checkpoints/outline_plans.json` (titles, focus, ev_ids, sub_query_indices) + a SHA256 of each.
- **Output boundary artifact:** `checkpoints/section_basket_map.json` (the full `SectionBasketMap` + the input SHAs it was built from + the assignment table for audit).
- **Resume rule:** on restart, if `section_basket_map.json` exists AND its recorded input SHAs match the recomputed ones, the map is LOADED, D1/D4 are skipped, and the pipeline resumes directly at per-section composition — which is already crash-isolated per section (`_gather_sections_isolated`, `multi_section_generator.py:976-1050`); add one per-section composed-draft checkpoint file (`checkpoints/section_<idx>_composed.json`) so a mid-composition crash re-runs ONLY the unfinished sections. SHA mismatch ⇒ rebuild loudly (never silently reuse a stale map — LAW II fail-loud).
- This makes DESIGN 4 a SELF-CONTAINED SECTION of the pipeline: `(baskets_global.json, outline_plans.json) → [section_basket_map] → (section_basket_map.json)`, replayable and resumable in isolation.

---

## 8. Build plan (Opus work packages, each ≤200 LOC PR, dual-gate Codex+Fable)

1. **WP1:** `section_basket_map.py` module + fixture + unit tests (D1; acceptance 1,2,4,6).
2. **WP2:** compose wiring — map threading, `_section_baskets_for_compose` fast path, role policy, F1 absorb (D2+D5; acceptance 3,5,6).
3. **WP3:** outline basket-digest menu, off-mode only (D3; menu-size + truncation canary).
4. **WP4:** per-section merge refinement + global relabel (D4; acceptance 7,8).
5. **WP5:** checkpoints + replay harness + resume rule (7a/7c).

WP1→WP2 are the keystone (they alone retire the stranded-basket leak and the duplication); WP3/WP4 are additive recall/planning wins; WP5 locks the section down. Every WP proves itself on the banked drb_72 replay BEFORE any paid run (offline-tests-are-not-preflight rule: the first paid validation is one small real run, then full).

## 9. Risks and honest residuals

- **Corroborating-role under-render:** a section where the claim's restatement genuinely belongs could lose narrative flow when the prose home is elsewhere. Mitigation: `PG_SECTION_BASKET_ROLE_POLICY=full` A/B on the replay + the multicited facet sentence still cites the claim in-place; judged on the §-1.1 before/after audit, not on intuition.
- **Primary-home misplacement:** a wrong argmax puts prose in a suboptimal section. It is still rendered, verified, and cited (quality-of-placement issue, never a loss); the signals + audit table make every placement inspectable in the hamster loop.
- **Cluster/basket identity drift:** D3 digests key on finding_dedup clusters while compose keys on baskets; alignment holds only under `PG_BASKET_CONSUME_FINDING_DEDUP=1` (slate-ON). The map itself keys ONLY on `claim_cluster_id` (basket-side), so drift can affect D3's menu grouping at worst — disclosed in the harness diff.
- **Depth synthesis stays global** (`run_honest_sweep_r3.py:16548-16620`): unchanged by design (it is a whole-report digest). A later design may let it read the map for section-attributed findings; out of scope here.
