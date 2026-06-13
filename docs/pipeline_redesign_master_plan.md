# POLARIS Pipeline Redesign — Master Plan (consolidated)

**Issue:** I-arch-001 (#1245)
**Consolidates:** Claude forensic (`docs/pipeline_architecture_forensic_2026_06_13.md`) + Codex independent forensic (`C:\POLARIS\I-arch-001_codex_forensic.txt`, 62 KB) + the operator's three principles.
**Status:** DESIGN — confirm before any code. Surgical re-wire, **not** a rewrite.
**DNA source:** CLAUDE.md §-1.3 (operator-locked 2026-06-13). This doc is the single execution plan; both forensics are its evidence base.

---

## 0. The lens (operator-locked — the yardstick for everything)

Three principles. Every decision below is measured against these.

1. **Weight, don't filter** — every relevant source flows through to composition carrying a credibility **weight**; the user judges. Social media stays at low weight (it may still report a real journal).
2. **Consolidate, don't drop** — group sources that carry the same claim into a **basket**; keep them all as corroboration.
3. **Basket faithfulness** — verify each claim against its **whole basket** of sources, not one span; the verdict carries the corroboration (count + weights + agreement).

**The flow:** fetch-all → relevance gate → weight → consolidate into per-claim baskets → distill → verify each claim against its basket → compose with weighted multi-attribution → user judges.

**The one hard floor that never moves:** the span-grounding faithfulness engine (strict_verify / NLI / 4-role D8 / provenance). Everything else is a weight or a consolidation.

---

## 1. The one-line diagnosis (both forensics agree)

**The pipeline drops before it weighs.**

POLARIS has a genuinely strong span-faithfulness engine, and that part is correct. But *before the faithfulness engine ever sees a claim*, the code hard-caps, hard-drops, deduplicates, rebalances, and breadth-forces the corpus in many places. The generator never operates over "all relevant sources, weighted and consolidated by claim." It operates over a thinned subset shaped by retrieval budgets, lexical relevance floors, topic/scope filters, finding dedup, per-section caps, outline menus, breadth augmentation, and post-generation fact/span caps.

The funnel we observed on drb_72 — ~4381 discovered → 740 fetched → 591 scored → 403 selected → 76 cited — is the symptom. The cause is that "weight" and "consolidate" exist only as **fragments, off by default, downstream of the thinning.**

---

## 2. What the two forensics found — and what Codex caught that Claude's missed

### 2.1 Where they agree (the spine)
- The faithfulness engine is the **one correct hard gate** and must not be weakened (`provenance_generator.py:1625-2194`, `:2402-2505`; D8/4-role at `run_honest_sweep_r3.py:7425-7926`). Confirmed: it does **not** fall back to whole-document proof when span recovery fails (`provenance_generator.py:2000-2140`) — no blind spot there.
- `PG_RELEVANCE_FLOOR` is a **hard cut on a weak lexical signal** and is unsafe as a gate (`evidence_selector.py:410-440`, `:1564-1681`). Convert to a weight. (The code's own comments admit the denominator dropped on-topic T1 papers; the topic gate was added because Wikipedia scored 0.583 above a clean 0.500 median — `topic_relevance_gate.py:2-14`.)
- `finding_dedup` is **consolidation done as deletion**: it keeps one representative row and drops the corroborators, and is numeric-only (`finding_dedup.py:29-38`, `:121-218`). Re-wire to keep the basket.
- The breadth targets/canaries (`PG_LEGACY_SECTION_BREADTH_TARGET`, `PG_SECTION_SOURCE_BREADTH_TARGET`, `PG_BREADTH_CANARY_MIN`) **force a number instead of letting coverage emerge** (`multi_section_generator.py:993-1195`, `:5377-5393`; `run_honest_sweep_r3.py:6742-6772`). Delete as quality gates.

### 2.2 The three things Codex's forensic adds — **this is "what we miss"**

**MISS 1 — The weight/consolidate machinery ALREADY EXISTS; it is OFF / advisory / downstream.**
We were about to "build" things that are already in the tree:
- `src/polaris_graph/synthesis/weight_mass.py` — origin-cluster weight mass (the exact "independent-origin support so syndicated copies can't inflate" idea). Advisory (`:1-19`, `:87-180`).
- `src/polaris_graph/synthesis/claim_graph.py` — atomic-claim extraction + equivalence clustering, supports/refutes/supersedes (`:1-16`, `:246-380`). The right component, but optional and attached to the credibility pass, not on the main path.
- `src/polaris_graph/synthesis/credibility_pass.py` — independent origins, supersession, credibility judge, claim graph, weight mass — the correct vocabulary (`:134-202`). Gated by `PG_SWEEP_CREDIBILITY_REDESIGN`, which **Gate-B does not enable** (`run_gate_b.py:653`, `:669-715`).
- `src/polaris_graph/authority/authority_model.py` — credibility scoring (`:84-200`).
- `src/polaris_graph/authority/credibility_skill.py` — the **approved adaptive credibility skill** (L1 of the 2026-06-07 plan; `:1`, `:241`). Already implemented — one adaptive skill, no fixed domain rubrics. **This is the scorer we reuse, not replace.**
- `src/polaris_graph/nodes/weighted_corpus_gate.py` — "proceed + weighted disclosure instead of refusal" (`:1-30`, `:171-249`). Gate-B *does* enable this one, but it is **corpus-level disclosure only**, not the composition contract.
→ **Consequence:** the job is even more surgical than the Claude plan framed it — **turn on + promote to the main path + carry through to composition**, far less "build."

**MISS 2 — The RETRIEVAL caps also break "fetch-all," not just selection/composition.**
The Claude plan concentrated on the selection and composition stages. Codex shows the corpus is thinned *much earlier*:
- `_rerank_and_reserve` enforcing `fetch_cap` is **the earliest and biggest source loss** — it decides which URLs are never fetched by any tool (`live_retriever.py:2596-2670`, `:3033-3049`).
- `PG_SWEEP_FETCH_CAP=740`, `PG_SWEEP_MAX_SERPER=100`, `PG_SWEEP_MAX_S2=100` (`run_gate_b.py:444-446`); the complexity router can silently *reduce* the fetch cap (`run_honest_sweep_r3.py:3025-3069`); STORM/R6/agentic/deepener all have their own URL caps (`:3387-3394`, `:3716-3747`, `:3807-3844`, `:3923-4008`, `:4111-4126`).
- Content itself is truncated (`PG_LIVE_CONTENT_MAX`, `live_retriever.py:1498-1500`, `:2305`) and `direct_quote` is a pre-claim provenance window (`:2450-2508`), so "full content with every tool" is **not yet true.**
→ **Consequence:** the redesign must reach into retrieval too — but as **budgets with a loss ledger**, not as silent quality cuts.

**MISS 3 — Separate operational budgets from evidence validity (loss ledger), and store full source artifacts.**
- Keep real operational caps (fetch budget, provider page limits, timeouts, cost) — but a URL not fetched must remain a `SourceCandidate` with an explicit status (`not_fetched_budget`, `fetch_failed`, `blocked`, `metadata_only`, `fetched_fulltext`), never silently vanish (Codex 4.2, 4.10).
- Change retrieval output from "one evidence row with a capped direct_quote" to **`SourceRecord` (full text + metadata + every fetch attempt) → `SourceVersion` (preprint/journal/PDF/HTML/OA twin) → `SourceSpan` (claim-specific windows derived *later*)** (Codex 4.3). Prompt windows stay small; the stored content is full.

---

## 3. The unified catalog (every knob → one classification, grounded)

Six buckets. This merges Claude's 79-item catalog with Codex's classified catalog (§2 of the Codex forensic). `file:line` is from the forensics.

### 3.1 KEEP — legit faithfulness gates (the hard floor, never weaken)
- Provenance token / evidence-id / span-bounds / numeric-match / content-overlap / trial-name / NLI entailment sentence drops (`provenance_generator.py:1713-2194`).
- `PG_PROVENANCE_MIN_CONTENT_OVERLAP` (`:1000-1009`); bounded reanchor / span resolver (`:1035-1074`); `PG_VERIFICATION_MODE`, `PG_STRICT_VERIFY_ENTAILMENT` (`:1366-1379`).
- `PG_PROVENANCE_TOKEN_HONEST_DROP`, `PG_PROVENANCE_SKIP_EMPTY` (`:2353-2505`) — keep, **with audit-ledger row** for each drop.
- Bounded repair loop (`sentence_repair.py:59-60`, `:240-302`) — failed claims stay dropped.
- D8/four-role release + redaction `PG_FOUR_ROLE_MODE`, `PG_REDACT_HELD_UNSUPPORTED`, `PG_ALWAYS_RELEASE` (`run_honest_sweep_r3.py:7425-7926`).
- Gate-B cited-span checks + `PG_MAX_JUDGE_ERROR_RATE` (`run_gate_b.py:523-572`).
- `is_content_starved` (`live_retriever.py:2406-2447`) — no usable text = can't span-ground; **but the metadata-only source goes to the loss ledger, not the void.**

### 3.2 KEEP NARROW — legit relevance/safety gates (confident-OFF only, fail-open, audited)
- Safety refusal gate + scope rejection abort (`run_honest_sweep_r3.py:2722-2783`, `:2941-3003`).
- LLM topic gate **restricted to confident OFF**, fail-open, every drop audited (`topic_relevance_gate.py:22-35`, `:211-352`). Borderline → low weight, not gone.
- Off-topic spam/malware domain denylist only (`evidence_selector.py:1457-1487`) — everything else is credibility weight.
- Underframed-trial sentence filter for clinical claims (`multi_section_generator.py:2650-2690`) — domain-specific precision gate.

### 3.3 KEEP + LOSS LEDGER — operational budgets (not quality logic)
Every one of these stays as a *budget*, but emits a loss-ledger row so a skipped URL is visible and resumable, never treated as "irrelevant":
- `PG_SWEEP_FETCH_CAP`, `PG_SWEEP_MAX_SERPER`, `PG_SWEEP_MAX_S2` (`run_honest_sweep_r3.py:3011-3023`); Serper page/total/zero-new stops (`live_retriever.py:324-355`); S2 clamp (`:411-425`); OpenAlex page caps; post-fetch loop budget (`:3271-3303`).
- STORM / R6 / agentic / deepener URL & query caps (scheduling boundaries, **not** quality filters) (`:3295-4126`, `run_gate_b.py:492-504`, `:630-638`).
- Query-decompose / `PG_MAX_SUBQUERIES` budget — but log "coverage incomplete," don't treat as adequate.
- **DELETE the complexity router** (`PG_COMPLEXITY_ROUTING`, `PG_SIMPLE_FETCH_CAP`, `run_honest_sweep_r3.py:3025-3069`) — silently *reducing* breadth is the exact under-scope failure we're removing.

### 3.4 RE-WIRE → WEIGHT (stop hard-dropping; surface a credibility/relevance weight)
- `PG_RELEVANCE_FLOOR` hard cut → relevance weight + confident-off exception (`evidence_selector.py:1564-1681`).
- Legacy corpus adequacy abort (tier/count/material-deviation) → weight + disclosure (`run_honest_sweep_r3.py:4384-4494`); the journal-only filter (`:4183-4291`) → credibility class, not a hard source-class drop (except an explicit user "journal-only" mode).
- Prefetch off-topic threshold (`prefetch_offtopic_filter.py:179-219`) and amplifier scope floor (`scope_query_validator.py:197-237`) → weight/diversity, not erase-before-fetch.
- Tier quota / `max_rows` over-allocation trim (`evidence_selector.py:1834-1882`); `PG_LIVE_MAX_EV_TO_GEN` (`:4758`); selection-scale caps (`evidence_selector.py:645-730`); recency tiebreak (`:499-590`); plan-sufficiency authority floor (`plan_sufficiency_gate.py:62-77`); agentic host filter (`run_honest_sweep_r3.py:4037-4050`) — all become weights/scores feeding the basket, not source deletions. Token pressure is handled by clustering + progressive summaries, not by dropping sources.

### 3.5 RE-WIRE → CONSOLIDATION (basket, not deletion)
- `finding_dedup` / `PG_USE_FINDING_DEDUP` / `PG_CAPPED_FINDING_DEDUP` → produce **claim clusters with all support/refutation**, keep every source as attribution (`finding_dedup.py:121-218`; `run_honest_sweep_r3.py:4760-5938`).
- `fact_dedup` sentence rewrite/drop + `PG_SPAN_PER_SOURCE_CITE_CAP` (`fact_dedup.py:40-203`, `:709-779`) → over-concentration is a *symptom* of missing claim consolidation; fix by clustering + diversifying support, not by dropping grounded sentences.
- `PG_SCOPE_PREFER_JOURNAL` arXiv-twin drop (`evidence_selector.py:1490-1561`) → cluster preprint + journal as **versions** of one source/claim (`SourceVersion`), don't hard-drop the twin.
- Subquery reserve / domain cap / constrained-greedy diversity (`evidence_selector.py:605-998`, `:2251-2309`) → per-claim independent-origin accounting + source weights, not hidden source reservation.
- **Promote `claim_graph.py`, `credibility_pass.py`, `weight_mass.py` to the main path** and retire `finding_dedup` *as a source-dropper* (Codex 4.6).

### 3.6 DELETE — number-chasing hacks (breadth/quality emerges, it isn't forced)
- `PG_LEGACY_SECTION_BREADTH_TARGET` + breadth augmenter (`multi_section_generator.py:993-1152`, `:5377-5393`).
- `PG_SECTION_SOURCE_BREADTH_TARGET` (`:1326-1359`).
- `PG_BREADTH_CANARY_MIN` (`run_honest_sweep_r3.py:6742-6772`).
- `PG_SPAN_PER_SOURCE_CITE_CAP` (#1232), the scope hard-filter (#1244, uncommitted) — Claude's own bolt-ons. Over-concentration and breadth both self-correct once composition uses the weighted basket.
- `PG_OUTLINE_MAX_EV=150` (`multi_section_generator.py:89-134`, `:1451-1513`) and `PG_MAX_EV_PER_SECTION` (`:1202-1207`, `:1360-1365`) as *source caps* → outline/section planning operates on **claim/facet clusters + coverage summaries**, with full attribution available for citation. (Per-section token budgets stay, but they select clusters, not first-N rows.)

→ Replace all of the above with **coverage metrics**: % of required facets with ≥1 high-confidence claim cluster; weighted support mass per claim; independent-origin count per claim; unresolved contradictions; low-cred-only claims; unfetched-candidate count (Codex 4.8).

---

## 4. The surgical change list (keep / re-wire / delete / build — through the lens)

**KEEP & re-wire (machinery already exists):**
- Tier classifier (T1–T7) + `authority_score` → **priors/inputs to the approved adaptive credibility skill** (`credibility_skill.py`, already implemented — L1 of the 2026-06-07 plan; one adaptive skill, no fixed domain rubrics). Re-wire to weight + surface per-citation; stop rank-then-drop. **Do NOT fork a second or replacement scorer** — reuse the adaptive skill.
- `finding_dedup` / `fact_dedup` → **consolidation.** Re-wire to group same-claim + keep all sources as a basket; stop deleting.
- STORM + Zyte/crawl4ai + distill → **keep** (fetch breadth + per-cluster summarization).
- Faithfulness engine → **keep**, evolve single-span → basket verification.

**DELETE (the four bolt-on hacks):**
- Span re-cite cap (#1232), breadth target + canary (#1233), scope hard-filter (#1244, uncommitted), complexity router.
- Relevance-floor-as-hard-cut → soften to weight + confident-off gate.

**BUILD/WIRE (mostly connecting + turning on what exists):**
- Turn on `PG_SWEEP_CREDIBILITY_REDESIGN`; promote `claim_graph` + `credibility_pass` + `weight_mass` to the main composition path.
- Surface the source weight all the way into composition.
- Carry the consolidated basket per claim through to verification **and** composition.
- Basket verification + "claim → sources + weights + agreement" presentation.
- Loss ledger + `SourceRecord`/`SourceVersion`/`SourceSpan` storage (full text stored, spans derived per claim).

That's it: **re-wire four, delete four, turn on the existing credibility machinery, evolve faithfulness to the basket, add a loss ledger.** Not a rewrite.

---

## 5. Migration waves (reconciled: Claude's 5-wave + Codex's 4.1–4.10)

**Invariant across every wave:** the faithfulness gate's pass/fail verdict is **byte-identical** on a frozen drb_72 fixture before and after the wave. If a wave changes a faithfulness verdict, it is wrong — stop.

- **Wave 0 — Safety net + shadow-on (no behavior change).**
  Add the audit/loss ledger (Codex 4.10): every non-faithfulness drop writes `{source_id, stage, knob, score, reason, would_keep_as_low_weight, claims_affected}`. Turn the existing credibility machinery on in **shadow mode** (compute weight_mass / claim_graph / credibility_pass, log them, change nothing). This makes the rest of the migration diagnosable and reversible.

- **Wave 1 — Relevance floor → weight (ONLY).** `PG_RELEVANCE_FLOOR` hard drop becomes a `relevance_weight` + a confident-off exception (`evidence_selector.py:1620`). **Nothing else this wave** — section/global source caps are NOT touched here. (Codex iter-1: dissolving `PG_MAX_EV_PER_SECTION` before claim baskets exist would risk prompt-flooding or a hidden replacement cap — the cap is real today at `multi_section_generator.py:797`, `:1206`, `:1334`.) This is the live 236/589 floor cut that buried good sources.

- **Wave 2 — Kill the number-chasers.** Delete breadth targets + canary + span re-cite cap + scope hard-filter + complexity router. Coverage metrics replace them as the run-health signal.

- **Wave 3 — Consolidation = basket + render (keystone).** `finding_dedup` member-drop → per-claim multi-attribution object; **reuse `claim_graph`** as the field-agnostic extractor/clusterer (NOT a new framework); promote `credibility_pass` + `weight_mass` to the main path; weighted-multi-attribution **render** in composition — extend the resolver/bibliography (today it carries only `{num,evidence_id,url,tier,statement}` at `provenance_generator.py:2548`, and disclosure reads only the sentence's cited tokens at `credibility_pass.py:222`, `disclosure_population.py:101`) to carry the whole basket + weights. Compose from claim clusters, not source rows (Codex 4.7). **Full design + adversarial stress test: `docs/consolidation_design_wave3.md`** (the merge key is the sole defense against over-merge — every discriminating slot is sentinel-guarded; 6 mechanical proof tests).

- **Wave 4 — Dissolve source caps + retrieval budgets + full artifacts.** Now that baskets exist, dissolve `PG_MAX_EV_PER_SECTION` / `PG_LIVE_MAX_EV_TO_GEN` / `PG_OUTLINE_MAX_EV` as *source* caps (per-cluster summaries handle the token budget). Retrieval caps become budgets-with-ledger; complexity-router gone; convert denylist → credibility class and prefer-journal → version clustering **here** (Codex iter-1: don't enable these as drops earlier — it would contradict "social media/preprints stay low weight"). Store `SourceRecord`/`SourceVersion`/`SourceSpan` with full text; derive `direct_quote` windows per claim (Codex 4.2/4.3).

- **Wave 5 — Basket faithfulness + credibility model central.** Evolve strict_verify/NLI/4-role to verify each claim against its whole basket (union of spans), carrying corroboration count + weights + agreement, **under the §6 contract**; make credibility a required field on every `SourceRecord`, fed by the approved adaptive credibility skill (Codex 4.4/4.5). STORM/GPT-Researcher stay discovery-only (Codex 4.9).

Each wave = its own Issue, its own brief, Codex the only gate, 200-LOC discipline, faithfulness fixture green.

---

## 6. Faithfulness safety — the one thing that must not regress (lethal if wrong)

Evolving single-span → basket must **strengthen** the hard gate, never relax it.

- **Correct:** every basket member is still **independently span-grounded** by strict_verify (numeric + content-overlap + bounds + NLI). The basket *adds* corroboration metadata (independent-origin count, weight mass, agreement). A claim is verified because ≥1 member span genuinely grounds it **and** the basket shows the support structure — verifying against *more* evidence, not less.
- **FORBIDDEN path (name it so we never build it):** "the claim is supported if *any one* basket member loosely supports it" → accept on weaker evidence than today. This is the one regression that must not happen. Basket verification is an **AND over independent grounding**, never an **OR that lowers the bar**. Origin-cluster weight-mass exists precisely so syndicated copies of one source can't masquerade as independent corroboration.
- **Display contract (Codex iter-1, binding):** every source shown as *supporting* a claim must carry **its own verified span verdict** from strict_verify. If a basket member has no verified span, it is displayed as *context / unverified*, and the basket-level verdict is labelled **partial / contested** — it is never silently rendered as full support. Basket verification may only **downgrade, drop, or label** a claim; it may **never upgrade** a claim that strict_verify would fail. (The render path needs extending in Wave 3 — today disclosure reads only the sentence's cited tokens and the bibliography carries no weights, so the "supported by A, B, C with weights" view cannot yet be produced honestly.)
- The provenance engine's no-whole-document-fallback property (`provenance_generator.py:2000-2140`) is preserved unchanged.
- **CORRECTION (consolidation stress test, `wf_30bf3a8a-5bd`; confirmed by Codex + Claude iter-1 review):** span-grounding **cannot** backstop a *false-merge*. `strict_verify` is per-member (production: `provenance_generator.py:2402-2505` driving `verify_sentence_provenance` `:1625-2194`; clinical twin `clinical_generator/strict_verify.py:204-281`) and never cross-compares basket members — so two distinct claims wrongly fused into one basket each still ground their own span and pass. A false-merge fabricates a corroboration *count*, not a span. **Therefore the consolidation merge key is the SOLE defense against over-merge**, and every discriminating slot that can be empty must be sentinel-guarded so it can never wildcard-merge. Full treatment: `docs/consolidation_design_wave3.md`.

This section is the acceptance criterion for Wave 5. Codex reviews it specifically.

---

## 7. Reconciliation — one plan, not two

This master plan **executes** the prior Codex-APPROVED design, it does not replace it:
- `docs/credibility_weighted_sourcing_redesign_plan_2026_06_07.md` (55 KB, APPROVED) — this plan executes its **L3 (claim consolidation), L5, L7 (weighted composition)** plus the drop/cap re-wiring. It does **NOT** replace **L1 scoring**: the approved plan's binding revision is **one adaptive credibility skill, no fixed domain rubrics** (`:247`), already implemented in `src/polaris_graph/authority/credibility_skill.py` (`:1`, `:241`). The tier classifier + `authority_score` are *priors/inputs* to that adaptive skill — not a competing tier-as-scorer. (Codex iter-1: stating "tier is the weighting system" as the final scorer would fork L1 into a second design — corrected.)
- `docs/credibility_adaptive_weighting_and_bothsides_recs_2026_06_08.md`, `docs/credibility_redesign_architecture_diagram.md`, `docs/frontier_credibility_intelligence_2026_06_07.md` — same family.
- The 2026-06-13 forensics (this issue) **confirmed and grounded** that design in file:line reality + SOTA (STORM/Co-STORM, GPT-Researcher, LangChain ODR, KBT/truth-discovery, source-copy detection, GRADE).

**Honest root cause of the lost day:** the right design existed and was approved on 2026-06-07. Instead of executing it, breadth-hacks were bolted on to chase a citation number. This plan deletes the hacks and executes the approved design.

---

## 8. Anti-overkill guardrails (the operator's explicit warning)

- **No rewrite.** The pipeline has good bones — reuse them.
- **No new framework.** `weight_mass.py` / `claim_graph.py` / `credibility_pass.py` / `authority_model.py` / `weighted_corpus_gate.py` already exist — turn on + promote, don't reinvent.
- **No new breadth knob.** If we find ourselves adding a cap/target/thinner to make a number move, **that is the bug** — stop.
- **Faithfulness is the only hard floor.** Everything else is a weight, a consolidation, or a budget-with-ledger.

---

## 9. Codex plan-review verdict (iter 1) + open items

**Verdict: `PLAN_NEEDS_CHANGES` (iter 1, `bd7wwj8hs`)** — three grounded findings, all applied to this doc:
1. **Basket faithfulness display contract** — pinned in §6 (every displayed support source has a verified span verdict, or the basket is partial/contested; verification may only downgrade/label, never upgrade). Render gap grounded at `provenance_generator.py:2548`, `credibility_pass.py:222`, `disclosure_population.py:101` → fixed in Wave 3.
2. **Wave-order dependency fix** — `PG_MAX_EV_PER_SECTION` dissolution moved out of Wave 1 to Wave 4 (after baskets exist); Wave 1 is relevance-floor → weight only. §5 updated.
3. **L1 reconciliation** — §4 + §7 now state the plan executes L3/L5/L7 + drop/cap re-wiring and **reuses** the approved adaptive credibility skill (`credibility_skill.py`); it does not replace L1 scoring.

Codex confirmed everything else directionally right (Principle 1 relevance-floor→weight correctly targeted; Principle 2 `finding_dedup` drop correctly identified + `claim_graph`/`weight_mass` are the right reuse) and explicitly flagged the over-engineering to avoid: **do not build a second claim extractor or scorer.** `faithfulness_safety: RISK` was raised *only* against an under-specified basket contract — now closed by the §6 display contract (additive, fail-closed).

**Open items:**
- These three changes are direct applications of Codex's own specified fixes (one-round convergence). A second Codex pass is optional, not required — the operator decides whether to re-gate or proceed.
- **BUILD GREEN-LIT (operator, 2026-06-13).** Tracked at **I-arch-002 (#1246)**. Wave 3 consolidation design is dual-APPROVED + LOCKED (`docs/consolidation_design_wave3.md`). The build delivers the operator's acceptance test — *the pipeline exhausts the URLs it fetches instead of dumping them* — which spans the post-fetch drop points: Wave 1 (relevance-floor→weight), Wave 4 (dissolve selection/section/outline source caps), Wave 3 (finding_dedup→basket keep-all), and deletion of the breadth number-chasers + the uncommitted #1244 scope-filter. All behind `PG_SWEEP_CREDIBILITY_REDESIGN`; OFF = byte-identical; faithfulness engine untouched. Codex double-checks every fix is in place; then a limited-STORM no-dumping smoke is the acceptance.
