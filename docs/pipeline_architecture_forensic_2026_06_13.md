# POLARIS Pipeline Architecture Forensic — fetch-all → weight → consolidate → weighted multi-attribution composition

**Document class:** Architecture forensic + target design + migration plan. Operator-approval-gated (no code is written from this doc until the operator signs off on the sequenced migration).
**Author:** Claude (lead architect). **Date:** 2026-06-13.
**Yardstick (the operator's intended architecture — every finding is judged against this):**

1. **Source many URLs** (thousands) → fetch FULL content with EVERY available tool. Do not lose good sources to a weak fetcher / paywall / JS-render failure.
2. A **RELEVANCE gate** → keep on-topic sources.
3. A **WEIGHTING system** → score each kept source by credibility (peer-reviewed? high-reputation journal? gov? institute? working paper? news? social media?). **WEIGHT, do NOT filter-out.** Social media STAYS (low weight; sometimes it reports a real journal).
4. **CONSOLIDATION** → group sources that carry the SAME claim. Repetition is **CORROBORATION**, not waste. Multiple citations per claim is GOOD and expected.
5. **COMPOSITION** → use ALL relevant sources. Each claim is presented as "supported by X, Y, Z, each with a weight." The USER judges. The pipeline does NOT hard-drop a source to hit a number.

**THE ONLY hard gate that stays is the FAITHFULNESS engine** (strict_verify / NLI entailment / 4-role D8 / provenance). A claim must be span-grounded. Everything else should be a WEIGHT or a CONSOLIDATION, not a DROP / CAP / THIN / TARGET.

**Grounding (honesty):** every file:line below was read against the working tree (`evidence_selector.py`, `finding_dedup.py`, `fact_dedup.py`, `multi_section_generator.py`) or taken from the supplied dual-auditor forensic maps (retrieval map, generation map, cap/filter catalog) and the SOTA research packs (architecture, weighting/consolidation). The forensic path was confirmed: on a Gate-B / honest-sweep **drb_72** run, `_use_research_planner` is FALSE (`PG_USE_RESEARCH_PLANNER` unset), so the LEGACY OFF-MODE path executes; all on-mode/planner branches are DEAD on drb_72 and marked so throughout.

---

## 0. The one-sentence thesis

**The pipeline's only claim-consolidation mechanism _drops_ the corroborating sources and keeps a single representative row plus an integer count, while credibility weight is used only to rank-then-drop and to write one corpus-level advisory mean — so there is no per-claim "supported by X, Y, Z, each with weight W" surface anywhere in the running pipeline. Every drop/cap/thin/target knob below is a symptom of that missing surface: each one forces a breadth NUMBER instead of weighting + consolidating + presenting all relevant sources.**

Everything in this document hangs off that sentence.

---

## 1. AS-IS pipeline flow (drb_72 / Gate-B legacy OFF-mode, as it ACTUALLY runs)

### 1.1 The two halves

```
RETRIEVAL half  (run_gate_b.py → run_honest_sweep_r3.py:run_one_query → live_retriever.run_live_retrieval)
  0. Cap resolution        run_honest_sweep_r3.py:3021-3023 + slate run_gate_b.py:444-510
                           main-lane fetch_cap floored to 740; ~1000-URL budget SPLIT across 5 lanes
                           (main 740 + agentic 100 + deepener 60 + R6 40 + STORM 60)
  1. Query compile + STORM  run_honest_sweep_r3.py:3260-3418  (STORM widens QUERIES only; ON via slate)
  2. Search → fetch → extract  live_retriever — domain backends fire (off-mode), trial-DOI seeds inject,
                           R-6 completeness expansion enabled (3724)
  3. Enrich + score        OpenAlex enrich → AuthoritySignals → authority_score (live_retriever:3386-3399);
                           tier T1-T4 (tier_classifier, :3436)
  4. Corpus build + selection  evidence_selector relevance-floor; finding_dedup; legacy domain-keyed
                           adequacy ABORT (run_honest_sweep_r3:4408)
  ── weighted-corpus gate (I-cred-006b #1170, ON): writes ONE corpus-level weighted_credibility_mean,
     ADVISORY, to corpus_credibility_disclosure.json — NOT propagated per-citation

GENERATION half  (run_honest_sweep_r3.py → multi_section_generator + provenance_generator + fact_dedup + finding_dedup)
  1.  Global evidence selection into generation   run_honest_sweep_r3.py:4758,4865-4907
      Gate-B ON: keep every row ≥0.30 relevance (PG_RELEVANCE_FLOOR) → finding-dedup the floored base →
      tier-balanced top-PG_LIVE_MAX_EV_TO_GEN (slate=1500, non-binding; pool < 1500)
  1b. finding_dedup.dedup_by_finding   keeps ONE representative per numeric-finding cluster; DROPS member rows;
      attaches corroboration_count + member_hosts as METADATA
  2.  Scope gates 2+3 (relevance/dedup)   DEFAULT-OFF (PG_SCOPE_* unset = byte-identical no-op)
  3.  Outline / plan   PG_OUTLINE_MAX_EV=150 menu cap into the outline LLM prompt
  4.  Multi-section generation   PG_MAX_EV_PER_SECTION=40 per-prompt binder (the real per-section limiter)
  5.  fact_dedup / finding_dedup   cross-section prose-redundancy collapse + (OFF) span-cite cap
  6.  strict_verify   per-sentence span-grounding — THE hard gate
  7.  citation / bibliography   resolve_provenance_to_citations — renders [N] entries
```

### 1.2 The four AS-IS divergences from the yardstick

**Divergence A — weight is a rank-then-drop key, never a per-claim surface.** The deterministic `authority_score` (from OpenAlex enrich) is used ONLY as (a) a RANK key — `_relevance_floor_selection` sorts by `-(relevance × authority_score)` (`evidence_selector.py:1624-1630`); `finding_dedup` ranks representatives by `authority_score` (`finding_dedup.py:156-162`) — and (b) a single corpus-level ADVISORY mean (`weighted_corpus_gate.py`, written to `corpus_credibility_disclosure.json`). The architecture wants each CLAIM presented as "supported by X, Y, Z each with weight W." The running pipeline instead uses weight to rank, then **drops** everything below the lexical relevance floor, and writes one corpus-wide number. **There is no per-claim multi-source weighted attribution surfaced to the user.** This is the spine divergence.

**Divergence B — the only consolidation mechanism DROPS the corroborating sources.** `finding_dedup.dedup_by_finding` (`finding_dedup.py:121-218`) is the architecture's "repetition = corroboration" idea in spirit, but mechanically it is a DROP: it clusters rows by a conservative numeric finding key, keeps ONE representative (max `authority_score`), and **deletes** every other member row from `deduped_rows` (`finding_dedup.py:196-203`: "A finding-bearing row that is the rep of nothing is REDUNDANT → dropped"). The corroborating members survive ONLY as `corroboration_count` (an integer) + `member_hosts` (strings) stamped on the representative; **nothing downstream re-expands them into citable `[N]` bibliography entries** (confirmed at generation stage 7). So a finding corroborated by 8 independent sources reaches the writer as 1 citable row + `corroboration_count=8`. This is a DROP, not the intended CONSOLIDATION ("group same-claim, keep ALL sources, present supported-by-X,Y,Z").

**Divergence C — the live drop is the relevance floor, not the consolidation.** `PG_RELEVANCE_FLOOR=0.30` (ON in the Gate-B slate) hard-drops every row below 0.30 lexical relevance. The in-file forensic comment (`evidence_selector.py:1316`) records it cut **236 of 589 rows (589 → 353)** on a live run, and a parallel drb_76 trace shows **597 → 53**. A clean median relevance of ~0.50 means a 0.30 floor still kills the on-topic tail. Lexical/embedding relevance is exactly what should DOWN-WEIGHT a source, not delete it. This is the headline live damage on drb_72.

**Divergence D — finding_dedup is INERT-but-architecturally-wrong on drb_72.** Precise statement so the doc does not overstate current harm: `extract_numeric_claims` (reused by finding_dedup) is **clinical-pattern-tuned** — it emits AT MOST one claim per row and returns NOTHING for non-clinical numerics (GDP, emissions, model-accuracy, AI-labor). drb_72 (domain=`workforce`, an economics/AI-labor question) therefore produces ZERO findings; every row is kept as a SAFE SINGLETON; **no member rows are dropped on drb_72.** So for drb_72 specifically the live consolidation loss is near-zero, and the real live damage is **Divergence C (relevance floor) + the per-section cap (§2)**. BUT the moment the extractor goes field-agnostic (the deferred Gap-D ambition), finding_dedup's member-drop will bite — so it is architecturally wrong _now_ and must be fixed _before_ the extractor is generalized, not after.

---

## 2. The full cap / filter / thin / target catalog, classified

**Disposition vocabulary (three-way + one legit class):**

- **REMOVE** — a number-chasing knob that should be deleted outright; breadth must EMERGE from weight+consolidation, not be asserted by a count.
- **→ WEIGHT** — a hard drop that should become a credibility weight in the per-claim presentation (the source STAYS, ranked lower).
- **→ CONSOLIDATION** — a cap on citations/spans-per-claim that should become "present all sources for this claim, each with a weight."
- **KEEP (legit relevance gate / anti-drop / prose-only)** — survives the migration unchanged or lightly tightened.

**Sequencing rule (advisor-directed):** the table is ordered by **what is ACTUALLY ON and biting the drb_72 / Gate-B run first**, then default-OFF/latent knobs, then legit-keeps. A dormant knob is NOT ranked equal to one cutting half the corpus.

### 2.1 ON and biting drb_72 (fix these FIRST)

| Knob | file:line | kind | classification | why |
|---|---|---|---|---|
| **`PG_RELEVANCE_FLOOR`** (=0.30, ON) | `evidence_selector.py:36,1564-1652` | filter/floor | **→ WEIGHT** | Hard-drops every row < 0.30 relevance; forensic at :1316 records 236 of 589 rows cut (589→353). Relevance is the canonical DOWN-WEIGHT signal, not a delete. Provably loses on-topic tail (median ~0.50). This is the headline live drop. |
| **`PG_MAX_EV_PER_SECTION`** (=40, ON) | `multi_section_generator.py:100-108,806-809,1206,1335` | cap | **→ CONSOLIDATION** | Hard per-section cap on rows handed to the section writer. drb_72 forensic (:1336) shows it truncated sections to 1-4 rows while above-floor high-authority sources sat uncited (196 pool → 21 cited). The **real per-prompt binder.** Caps a number instead of presenting all relevant sources weighted. |
| **finding_dedup member-drop** | `finding_dedup.py:196-203` | thin/consolidation | **→ CONSOLIDATION** | The corroboration idea done as a DROP: keeps a representative, deletes members, surfaces only an integer count. INERT on drb_72 (Divergence D) but architecturally wrong; must keep ALL members as weighted citable sources. |
| corpus-level weighted mean only (I-cred-006b #1170, ON) | `weighted_corpus_gate.py` | disclosure-shape | **→ CONSOLIDATION** (extend, don't remove) | Weight is disclosed ONCE corpus-wide and ADVISORY; not propagated per-citation. The weighting *engine* is right; the *surface* is wrong. Extend to per-claim multi-attribution; keep the corpus mean as a summary. |

### 2.2 Number-chasing TARGET / canary knobs — REMOVE outright

| Knob | file:line | kind | classification | why |
|---|---|---|---|---|
| **`PG_BREADTH_CANARY_MIN`** | `multi_section_generator.py:1031,1164-1197` | target/threshold | **REMOVE** | A "breadth canary" minimum that forces the pipeline to hit a source-breadth NUMBER. Operator named this explicitly as a stupid blocker. Breadth must EMERGE from weighting+consolidating all relevant sources. Remove, or convert to pure telemetry that can NEVER gate. |
| **`PG_LEGACY_SECTION_BREADTH_TARGET`** (default 0) | `multi_section_generator.py:5377-5382` | target | **REMOVE** | Legacy per-section breadth target that adds rows on top of the outline LLM's picks to hit a number. Operator named it by hand. Number-chasing; dissolves into use-all-relevant-sources composition. |
| **`PG_SECTION_SOURCE_BREADTH_TARGET`** (default 0) | `multi_section_generator.py:1336-1358` | target (anti-cap widener) | **REMOVE** | A TARGET that ADDS above-floor rows to UNDO the truncation `PG_MAX_EV_PER_SECTION` caused. A number-chasing patch on a number-chasing cap. When the cap dissolves into consolidation, this band-aid dissolves with it. |
| **`PG_BREADTH_AUGMENT_MIN_OVERLAP` / `_REQUIRE_SECTION_OVERLAP` / `_MARQUEE_PRIORITY`** | `multi_section_generator.py:1022-1068` | threshold/target | **REMOVE** | Breadth-augmentation knobs that mechanically re-inject sources to hit the canary. Same class as the two targets above. Fold into weight+consolidation, not overlap-threshold gymnastics. |

### 2.3 Default-OFF / latent drops — convert when touched (not biting today)

| Knob | file:line | kind | classification | why |
|---|---|---|---|---|
| `PG_SCOPE_DENYLIST_DOMAINS` / `_apply_scope_denylist` | `evidence_selector.py:1388-1487` | filter/denylist | **→ WEIGHT** | Drops rows whose netloc matches an operator denylist (suggested: facebook, scribd, wikipedia, reddit, medium…). **Directly contradicts "social media STAYS at low weight" — see §3.** Default-OFF today, but the concept is a hard host-drop; must demote credibility weight, not delete. |
| `PG_SCOPE_PREFER_JOURNAL` / `prefer_journal_over_arxiv` | `evidence_selector.py:1490-1561` | filter/threshold | **→ WEIGHT** | Drops an arXiv preprint when a published twin exists. Preferring the journal is a WEIGHT, not a reason to drop the preprint (which may carry data the journal paywalls). Default-OFF; architecturally a weight. |
| `PG_SPAN_PER_SOURCE_CITE_CAP` (fact_dedup) | `fact_dedup.py:63-98,197,730` | cap | **→ CONSOLIDATION** | Drops "over-concentrated" citations from one source past a per-source cap. Multiple citations per claim is GOOD (corroboration). Default-OFF; when on it caps to a number instead of presenting all spans with weights. |
| `PG_SECTION_PER_SOURCE_SPAN_CAP` | `multi_section_generator.py:895,1314` | cap | **→ CONSOLIDATION** | Per-section per-source span cap (sibling of the fact_dedup span cap). Penalizes corroboration. Should be weight/consolidation, not a hard span number. |
| `PG_LIVE_MAX_EV_TO_GEN` (=1500 slate, non-binding) | `multi_section_generator.py:806` | cap | **→ CONSOLIDATION** | Global cap on rows passed retrieval→generation. A breadth NUMBER on the whole pool — the operator's exact complaint. Non-binding today (pool < 1500) but should be replaced by consolidate-then-present-all-with-weights, not held as a ceiling. |
| `PG_MAX_EVIDENCE_FOR_SYNTHESIS` (default 1000) | `agents/synthesizer.py:1913-1929` | cap | **→ CONSOLIDATION** | Caps rows entering synthesis (top-N by tier/relevance/confidence). Default 1000 rarely bites, but a hard top-N breadth cap that drops the tail to control map-reduce cost. (synthesizer is the pipeline-B/agentic path; convert when that path activates.) |
| `PG_FOCUSED_MAX_SOURCES_PER_SECTION` / `PG_FOCUSED_MAX_EVIDENCE_PER_SECTION` | `agents/synthesizer.py:1374-1375` | cap | **→ CONSOLIDATION** | Focused-mode per-section source/evidence caps (synthesizer path). Same class — consolidate, don't truncate. |

### 2.4 Token-budget cap — KEEP conditionally (do NOT remove; verify the ordering guarantee)

| Knob | file:line | kind | classification | why |
|---|---|---|---|---|
| `PG_OUTLINE_MAX_EV` / 150-menu cap | `multi_section_generator.py:130-134,1450-1452` | cap/thin | **KEEP — conditional** | Caps how many rows are SERIALIZED into the outline-PLANNING LLM prompt to avoid reasoning-token truncation. The code documents it as **menu-only**: `allowed_ev_ids` validation, full-text resolution, primary-anchor injection, and the per-section `PG_MAX_EV_PER_SECTION` selection ALL stay on the FULL pool (:102-110). IF that ordering/menu-only guarantee holds, this is a legit token-budget cap, NOT a breadth limiter. **OPEN:** the comment admits the truncation-fit-at-150 is an unproven hypothesis (150 terse rows ≈ 16-17K menu chars vs the only known-good 53-verbose ≈ 13K datapoint). Verify with a live V4-Pro 1-query canary that per-section selection sees the full pool before trusting it. Do NOT put in REMOVE. |

### 2.5 Legit relevance gates / anti-drop / prose-only — KEEP

| Knob | file:line | kind | classification | why |
|---|---|---|---|---|
| `PG_SCOPE_TOPIC_GATE` (topic_relevance_gate) | `topic_relevance_gate.py:57-61` (whole file) | filter (relevance) | **KEEP (legit RELEVANCE gate)** | LLM ON/OFF semantic topic judgment — the architecture's point-2 RELEVANCE gate. Legit BECAUSE it is fail-open (drops only on confident OFF, exempts marquee anchors). Verify the fail-open contract holds before trusting. Default-OFF today. |
| `PG_RELEVANCE_PRESERVE_ANCHORS` / `_row_is_marquee_anchor` | `evidence_selector.py:1351-1385,1607-1618` | exemption (anti-drop) | **KEEP — turn ON** | NOT a drop — it EXEMPTS marquee/required-entity rows from the relevance floor. Correct direction (preserve sources). Mitigates the `PG_RELEVANCE_FLOOR` hack today; should be ON. |
| `finding_dedup` corroboration-count machinery (the COUNT, not the member-drop) | `finding_dedup.py` (whole module) | consolidation | **KEEP the count; FIX the drop** | The independent-host corroboration_count + member_indices + member_hosts is corroboration done right and is the SEED for per-claim multi-attribution (members are already preserved on the cluster object — `FindingCluster.member_indices`/`member_hosts`). KEEP this; the only fix is to stop DELETING the member rows from the citable pool and instead render them as weighted citations. |
| fact_dedup `dedup_pass` (cross-section prose redundancy) | `fact_dedup.py:730-772`; `multi_section_generator.py:5676` | thin (prose) | **KEEP (prose-only)** | Collapses near-redundant duplicate-fact SENTENCES and re-verifies survivors through strict_verify. Legitimate prose-level consolidation (removes literal repeated padding); SOURCES/evidence rows untouched. Confirm it dedups PROSE not EVIDENCE. |
| `PG_RELEVANCE_HONEST_DROP` (I-pipe-003 #1228, ON) | `evidence_selector.py:1342-1348,1658-1664` | telemetry | **KEEP (telemetry)** | Logs the ACTUAL floor-cut count so `dropped=0` can no longer launder the relevance-floor cut. Telemetry-only; never changes the keep set. Keep — it is the honesty instrument that surfaces Divergence C. |

---

## 3. Process finding — the codebase is STILL accreting drop-knobs (name it)

Two of the knobs above were added **2026-06-12**, one day before this forensic:

- **`PG_SCOPE_DENYLIST_DOMAINS` (I-scope-001 #1244)** — drops facebook.com / scribd.com / en.wikipedia.org as "contamination." This **directly contradicts the yardstick's "social media STAYS (low weight; sometimes it reports a real journal)."** A denylist is a hard host-drop; the architecture wants a credibility DOWN-WEIGHT. It is default-OFF, which limits the harm, but the *direction* is wrong and the suggested default list is a journal-tunnel-vision relapse the operator already rejected (`feedback_credibility_not_journal_only_no_tunnel_vision_2026_06_07`).
- **`PG_RELEVANCE_HONEST_DROP` (I-pipe-003 #1228)** — the GOOD kind: it surfaces the relevance-floor cut honestly. This one is a keeper.

**The pattern:** the pipeline is acquiring new drop/filter knobs (denylist, prefer-journal, scope gates) at the same time the operator wants the existing ones dissolved into weights. The migration in §5 must (a) freeze net-new hard-drop knobs, and (b) require any new "contamination" handling to ship as a WEIGHT, not a denylist — with social media explicitly kept at low weight.

---

## 4. TARGET architecture (grounded in the named SOTA systems)

The target is the yardstick, made concrete and grounded in established systems. **REUSE** = existing POLARIS code re-wired; **BUILD** = genuinely new.

```
fetch-all → RELEVANCE gate → credibility WEIGHTING → claim CONSOLIDATION → distill →
weighted multi-attribution COMPOSITION (ALL relevant sources) → FAITHFULNESS gate (the only hard gate) → user judges
```

### T0. Fetch-all (KEEP — already the design)
Source thousands; fetch FULL content with every tool; ~1000-URL budget across 5 lanes. **SOTA validation:** OpenAI Deep Research reads "hundreds of sources" as normal at the frontier; GPT-Researcher's explicit philosophy is "the more sites we scrape the less chances of incorrect data." Fetch-MANY is the correct floor. Keep the multi-method fetch (chromium/Zyte/etc.) so good sources are not lost to paywall/JS-render failure.

### T1. RELEVANCE gate (KEEP, fail-open only)
Keep `PG_SCOPE_TOPIC_GATE` semantic ON/OFF as the relevance gate (architecture point-2), **provided** it is fail-open (drops only on confident OFF, exempts marquee anchors). **Convert `PG_RELEVANCE_FLOOR` from a hard drop to a WEIGHT** — relevance becomes the first input to the per-source weight, not a delete threshold. The relevance gate is the ONE place a source may leave the pipeline for being off-topic; credibility never removes a source.

### T2. Credibility WEIGHTING (BUILD the surface; the engine largely exists)
Score each kept source by credibility and KEEP it. **SOTA grounding:**
- **Knowledge-Based Trust (Dong et al., VLDB 2015)** — a source is trustworthy if the facts it asserts are correct, not by link-popularity; separate extraction error from source error (do not penalize a good source because OUR parser misread it). Already cited by `authority_model.py` / `corroboration.py`.
- **GRADE (Cochrane / ACIP)** — the canonical WEIGHT-and-downgrade ladder, never a drop: guidelines > systematic reviews > RCTs > observational > definitional, then up/down-graded for risk-of-bias/inconsistency/indirectness/imprecision; **every study disclosed with its certainty rating, reader judges.** This IS the operator's "weight not filter."
- **Domain-conditional** — clinical weights RCT+peer-review; econ/policy (drb_72) weights design-validity over venue (a strong NBER natural experiment must not rank below a weak peer-reviewed cross-section).

REUSE `authority_model.py` signals A–E + `tier_classifier`; the BUILD is **propagating the weight to the per-citation surface** (T6/T7), not a new scorer. **Social media STAYS at low weight** — never denylisted.

### T3. Claim CONSOLIDATION (BUILD field-agnostic; keep the corroboration primitive)
Group sources carrying the SAME claim; keep ALL of them; repetition = corroboration. **SOTA grounding:**
- **Truth-discovery survey (Li et al., KDD Explorations)** + **CRH (SIGMOD 2014)** — claim-aggregation by source reliability; the **multi-truth variant (VLDB 2018)** matters: one object can have several legitimately-true facts — do NOT force single-winner voting; keep all, surface with weights.
- **Source-copy / dependence detection (Dong et al., VLDB 2009/2010)** — discount copied/syndicated sources so syndication counts as ONE origin (shared-error is the strongest copy signal). POLARIS's `independence_collapse.py` + `corroboration.count_independent_hosts` are the engineering analogue.
- **STORM / Co-STORM** mind-map consolidates by OUTLINE SECTION (not by claim) and does NOT weight — adopt its "organize before you write" stage, improve it to consolidate by CLAIM with credibility weights. **Do NOT adopt STORM's dedup-in-polishing** (it thins corroboration).

REUSE `finding_dedup`'s `FindingCluster` (member_indices/member_hosts already preserved) + `corroboration_count`. **The BUILD: stop deleting member rows; make the cluster a "claim → [all member sources, each with weight]" object.** Replace the clinical-only numeric extractor with a field-agnostic atomic-claim extractor so consolidation is EFFECTIVE on econ/AI-labor corpora (drb_72), not inert.

### T4. Distill / map-reduce (KEEP prose-only)
`PG_SECTION_DISTILL` map-reduce distiller (generator lane) + fact_dedup prose `dedup_pass` collapse repeated PROSE, not evidence. **LangChain Open Deep Research lesson:** "compress findings before synthesis" is real for context limits — but compress to a structured finding, never to a lossy per-source summary that discards the source. **LangChain's second lesson:** multi-agent parallel section-writing produced "disjoint" reports, so they write the report in a SINGLE pass — relevant if POLARIS ever parallelizes section generation.

### T5–T7. Weighted multi-attribution COMPOSITION (the BUILD that closes the spine divergence)
Use ALL relevant sources. Each claim rendered as **"supported by X, Y, Z — each with weight W"**; the user judges. **This is the missing surface (Divergence A+B).** Concretely:
- **Aggregate by weight, not count** — replace COUNT aggregation (`plan_sufficiency_gate.py:313` `covered_count >= target`; `journal_only_filter` `DEFAULT_MIN_DISTINCT_JOURNALS=12`) with **origin-cluster weight-mass** (one weight per independent-origin cluster; copied rows cannot inflate mass). *This is exactly L5 of the Codex-APPROVED credibility plan — see §6.*
- **Contested-topic composition** — consensus side at high weight AND minority **attributed** at low weight with explicit forewarning; medical misinfo disclosed as low-weight/fringe; **ABSTAIN over fabricated balance.**
- **Per-claim disclosure render** — each verified sentence carries {span-verdict, credibility_weight, independent_origin_count, certainty_label}; rendered in the bibliography as a "supported-by" list, not a single representative `[N]`.

### T8. FAITHFULNESS gate — THE ONLY HARD GATE THAT STAYS
strict_verify (per-sentence: evidence-pool membership, span bounds, numeric match, ≥2 content-word overlap, trial-name, entailment) + NLI entailment + 4-role D8 + provenance `[#ev:id:start-end]`. **Every weighting/consolidation change above is additive and faithfulness-safe: it can only ADD an already-fetched source to the citable pool or change how it is RANKED/DISPLAYED — strict_verify still gates every emitted sentence, so no unverified claim can be fabricated to fill a breadth gap.** Weight is never an input to the span-grounding verdict. This gate is non-negotiable and unchanged.

---

## 5. Migration plan (sequenced issues, as-is → target)

Ordered by **live impact on drb_72 first**, then latent-knob conversions, then the net-new build. Each issue is a GitHub Issue per §3.0 issue-driven workflow. Faithfulness gates are untouched by every issue; each ships behind a flag, default-OFF byte-identical, fail-loud.

**Wave 1 — stop the live drops (highest impact, smallest change):**
1. **I-arch-floor-001 — convert `PG_RELEVANCE_FLOOR` from a hard drop to a relevance WEIGHT.** Keep every fetched row; map sub-floor relevance to a low weight that ranks it last, not a delete. Turn `PG_RELEVANCE_PRESERVE_ANCHORS` ON as the interim mitigation in the same PR. *Closes Divergence C — the 236/589 live cut.*
2. **I-arch-section-002 — dissolve `PG_MAX_EV_PER_SECTION` into consolidation.** Replace the per-section hard cap with "present all above-relevance sources for each claim, weighted"; the section length comes from distinct CLAIMS, not a row count. *Closes the real per-prompt binder (196→21 truncation).*

**Wave 2 — delete the number-chasing targets (these become dead once Wave 1 lands):**
3. **I-arch-targets-003 — REMOVE `PG_BREADTH_CANARY_MIN`, `PG_LEGACY_SECTION_BREADTH_TARGET`, `PG_SECTION_SOURCE_BREADTH_TARGET`, and the `PG_BREADTH_AUGMENT_*` family.** Breadth now emerges from weight+consolidation; the canary/targets/augmenters are band-aids on the cap they patched. Convert any breadth signal to pure telemetry that can NEVER gate.

**Wave 3 — the consolidation surface (the spine fix; overlaps the credibility plan — see §6):**
4. **I-arch-consol-004 — make finding_dedup's `FindingCluster` a per-claim multi-attribution object; stop deleting member rows.** Members become weighted citable sources; `corroboration_count` stays as the independent-origin summary. *Closes Divergence B.* This is the seed for the credibility plan's L5/L7.
5. **I-arch-extract-005 — field-agnostic atomic-claim extractor** so consolidation is EFFECTIVE on non-clinical corpora (drb_72), not inert (Divergence D). Must NOT over-merge (clinical-lethal); default to "keep separate" on ambiguity, mirroring the existing conservative-singleton rule. *Sequence this AFTER I-arch-consol-004 so the member-drop is already fixed before the extractor starts producing clusters on econ rows.*
6. **I-arch-compose-006 — per-claim weighted multi-attribution render** in the bibliography ("supported by X, Y, Z, each weight W"); replace COUNT aggregation in `plan_sufficiency_gate.py` / `journal_only_filter` with origin-cluster weight-mass. *Closes Divergence A.* **This issue is the same scope as L5+L7 of the Codex-APPROVED `credibility_weighted_sourcing_redesign_plan_2026_06_07.md` — file it as the execution of that plan's L5/L7, not a parallel build.*

**Wave 4 — convert the latent drops when next touched (lower priority, default-OFF today):**
7. **I-arch-denylist-007 — convert `PG_SCOPE_DENYLIST_DOMAINS` and `PG_SCOPE_PREFER_JOURNAL` to WEIGHTS.** Social media and preprints STAY at low weight; never denylisted/dropped. Freeze net-new hard-drop knobs (process finding §3).
8. **I-arch-spancap-008 — convert `PG_SPAN_PER_SOURCE_CITE_CAP` + `PG_SECTION_PER_SOURCE_SPAN_CAP` to consolidation** (present all spans with weights) rather than a per-source span number.
9. **I-arch-globalcap-009 — convert `PG_LIVE_MAX_EV_TO_GEN` / `PG_MAX_EVIDENCE_FOR_SYNTHESIS` / `PG_FOCUSED_MAX_*`** from top-N truncation to consolidate-then-present-all. (Non-binding today; do for correctness so no future pool silently hits the ceiling.)

**Wave 5 — verify the one conditional KEEP:**
10. **I-arch-outline-canary-010 — live V4-Pro 1-query canary** proving per-section selection sees the FULL pool with `PG_OUTLINE_MAX_EV=150` (the menu-only guarantee) and the outline prompt does not truncate. If it truncates, lower toward ~120 or take the Novita no-row-cut route per the in-file note. Do NOT remove the cap blind.

**Cross-cutting guardrail (every wave):** a regression test asserts that for a fixed fetched pool, the count of DISTINCT citable sources reaching composition is **monotonically non-decreasing** as each drop-knob is converted — i.e. the migration never loses a source it used to keep, and strictly recovers the ones the floor/caps used to drop. Faithfulness gate pass/fail on the fixture is byte-identical across the migration.

---

## 6. Relationship to prior work (so the operator does not reconcile two docs)

- **`docs/credibility_weighted_sourcing_redesign_plan_2026_06_07.md` (Codex-APPROVED, 8-layer, per-claim disclosure)** is the **sibling** of this doc. That plan defines the WEIGHT + per-claim DISCLOSURE machinery (the 8 layers L0–L8, calibration, dissent-recall). **This doc** catalogs the DROP/CAP/THIN/TARGET knobs and specifies how each dissolves into weight or consolidation. **They converge:** that plan's L5 ("replace COUNT aggregation with origin-cluster weight-mass") IS this doc's spine thesis. Migration issues §5#4 and §5#6 are the EXECUTION of that plan's L3-collapse / L5-aggregate / L7-disclose layers — file them as such, not as a parallel architecture.
- **The #1194 I-perm-001..009 permanent-fix program (withhold→always-release reframe, architecture LOCKED, Codex APPROVE iter2/iter3 harness)** is the *faithfulness-release* counterpart: it ensures a span-grounded claim is always RELEASED rather than silently withheld. That program governs the T8 gate's release semantics; this doc governs T1–T7 (everything upstream of the gate). No conflict: this doc never touches the faithfulness gate, and that program never relaxes a span-grounding check.
- **Net-new in THIS doc (not in either prior program):** the explicit REMOVE-list of number-chasing target/canary knobs (§2.2, Wave 2) and the conversion of the latent scope/denylist/span/global caps (Wave 4) into weights/consolidation. The breadth-target removals are genuinely net-new; the consolidation+disclosure builds reference the credibility plan.

---

## 7. Explicit faithfulness note (restated for emphasis)

**The faithfulness engine is the ONLY hard gate that stays.** strict_verify, NLI entailment, the 4-role D8 audit, and the `[#ev:id:start-end]` provenance binding are untouched by every issue in §5. Every weighting/consolidation change can only (a) keep a source that the old floor/cap dropped, (b) change its credibility WEIGHT, or (c) change how it is DISPLAYED per claim. None of these is an input to the span-grounding verdict. A claim still cannot appear unless it is span-grounded; the migration only ensures that ALL the sources which support a span-grounded claim are surfaced to the user with their weights, instead of being dropped to hit a breadth number. Weight and consolidation move a source's VISIBILITY and RANK; only faithfulness moves its ADMISSIBILITY.
