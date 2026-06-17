# I-arch-007 — BREADTH-COLLAPSE FIX DESIGN (§-1.3-faithful)

**Slug under forensic:** `drb_78_parkinsons_dbs` (Q78).
**Snapshot:** `outputs/audits/iarch007_death_forensic/draft_audit/Q78_corpus_snapshot.json`.
**Live report:** `outputs/audits/beatboth7/drb_78_parkinsons_dbs/report.md`.
**Reconciles:** `claude_trace.md` (root-cause = contract-entity count, option a) + `codex_trace.txt` (root-cause = `credibility_analysis=None` degrade chokepoint).

---

## 0. RECONCILIATION — the two traces describe TWO DIFFERENT failures, not one disputed site

The traces appear to disagree on the PRIMARY site only because they are diagnosing **two distinct failure modes** that both end in "few sources rendered." They are complementary; neither is wrong.

| | Claude trace (a) | Codex trace chokepoint |
|---|---|---|
| Failure | **Structural breadth funnel** — even on a FULLY SUCCESSFUL credibility pass, the render universe = 5 contract entities + a handful of LLM-planner enrichment picks. The 437 unbound weighted SUPPORTS sources never surface. | **Runtime degrade** — `multi_section_generator.py:6670-6692` sets `credibility_analysis = None` on credibility-pass timeout/error, collapsing the inline multi-citation render to byte-identical legacy single-citation. |
| When it fires | ALWAYS (it is config + planner structure). | ONLY when the pass times out / errors. |
| Evidence in Q78 | Q78 was a **success-path** run (485 sources were weighted, scored, basketed — the snapshot proves the pass completed). So the 485→~13-19 collapse there is the STRUCTURAL funnel, NOT the degrade. | Did not fire in the measured Q78 artifact (baskets are present in the snapshot). |
| Owner | **THIS fix (breadth).** | **Death/hang fix** — already handled by the I-arch-007 ITEM-1 wall + B5/B7 always-release degrade at `multi_section_generator.py:6642-6698`. |

**Verdict on the root-cause site:** The breadth collapse measured in Q78 is **Claude's (a) — the structural funnel** (confirmed: the snapshot shows a completed pass with 5 `v30_entity_id`-bound + 480 unbound). The Codex chokepoint is a real *precondition* for the multi-citation render (if baskets are absent, item 1 can't reach anything) but it is the **death-fix's domain**, already mitigated by the wall-deadline + always-release degrade I read at `:6670-6698`. **This design fixes the structural funnel and declares "baskets present" as its precondition; it does NOT re-touch the degrade path (that would collide with the death-fix).**

Both traces ALSO agree, against the task brief's stale framing, that the **inline multi-citation render is already built and live on the Gate-B contract path** (`contract_section_runner.py:1364-1372`). Q78's "~14 citation tokens per distinct source" is direct evidence it fires. So item 1 below is **document + prove + harden**, NOT fabricate wiring (fabricating redundant wiring to match a stale assumption would violate LAW II).

---

## 1. ITEM 1 — MULTI-CITATION PER CLAIM (already wired; residual = prove + survive)

### 1.1 Current state (VERIFIED in the live tree — do NOT re-implement)

The whole-basket inline render is LIVE on BOTH paths:

- **Legacy resolver:** `provenance_generator.py:3091-3126` builds the SUPPORTS-by-cluster index; `:3246-3251` appends `[N]` markers for every OTHER independently span-verified (SUPPORTS) member of the clusters the sentence already cites.
- **Gate-B V30 contract path (the keystone that reaches the benchmark):**
  - `contract_section_runner.py:741-758` HOISTS `_baskets`, `_cluster_id_by_evidence`, `_basket_supports_by_cluster` once from `credibility_analysis`.
  - `:1276-1280` threads `baskets=` + `cluster_id_by_evidence=` into `resolve_provenance_to_citations` so corroborators get numbered into `biblio_slice`.
  - `:1364-1372` calls `verified_corroborators_for_tokens(...)` per sentence and appends each corroborator's `[N]` (dedup'd against the sentence's own cites).
- **Shared faithfulness core:** `provenance_generator.py:2961-3006` `verified_corroborators_for_tokens` — SUPPORTS-only, anti-cross-claim (a token mapping to ≠1 cluster is NOT expanded), member must resolve in `evidence_pool`.

This is correct and faithful as-is. The single-cluster anti-cross-claim guard (`:3000`) is the §-1.1 "citation appropriate for the claim" protection — **KEEP IT UNCHANGED.**

### 1.2 Residual work for item 1

1. **A regression test** that proves a multi-source claim renders ALL its SUPPORTS basket members on the REAL `run_contract_section` path, and that an UNSUPPORTED member does NOT render (see §4). The existing `test_lane_section_arch005_contract_path.py` partially covers this; the new test extends it with the negative control and the broadened-source assertion.
2. **Precondition guard (already satisfied by the death-fix, asserted here):** baskets must survive to render. When `credibility_analysis is None` (degrade path) item 1 is byte-identical legacy single-citation — that is the always-release degrade, NOT a breadth regression to re-fix here. The design records this as a documented graceful-degradation, owned by the death-fix.

**No code change in item 1** beyond the test. The brief's "wire it" is stale; the honest deliverable is "wired at `contract_section_runner.py:1364-1372`, faithful, proven by §4 test."

### 1.3 Faithfulness-neutrality (item 1)

Unchanged. `verified_corroborators_for_tokens` surfaces ONLY members whose OWN isolated `span_verdict == "SUPPORTS"` (computed in `src/polaris_graph/synthesis/credibility_pass.py:442-457`), only for an unambiguous single-cluster token, only when resolvable in `evidence_pool`. No strict_verify / NLI / 4-role / span-grounding / section-floor / sentinel threshold is touched. No new textual claim. No invented citation.

---

## 2. ITEM 2 — BROADEN PAST THE CONTRACT (the 437 unbound high-weight SUPPORTS sources)

### 2.1 Why the A1-generalization route (claude_trace's first proposal) does NOT work — and is REJECTED

`claude_trace.md:71-73` proposed generalizing the A1 fallback in `contract_section_runner.py`. **This is blocked by a hard wall I verified at `contract_section_runner.py:963-966`:**

```python
_primary_eid = slot.entity_ids[0]
_contract_entity = plan.contract_entities_by_id.get(_primary_eid)
if _contract_entity is None:
    continue
```

The A1 fallback re-binds a corroborator to an EXISTING contract slot's claim cluster — it requires the corroborator to share a single cluster with one of the slot's 5 bound entities, and requires a contract entity to inherit the field contract from. The 437 unbound sources are in **DIFFERENT clusters** (that is precisely why they have no `v30_entity_id`). They have no contract entity and nothing to corroborate among the 5. So A1-generalization either hits the `continue` wall or, worse, would need a many-cluster linkage that RELAXES the anti-cross-claim rule (§-1.1 lethal). **A1-generalization is the wrong home for NEW claims from unbound sources.**

### 2.2 The correct home — the enrichment `_run_section` path (field-agnostic + three-stream strict_verify)

The faithful place to surface NEW claims from unbound sources is the **enrichment (legacy) section path**, which already:

- runs under Gate-B (CONFIRMED: `multi_section_generator.py:6902-6929` `_run_legacy_bounded` → `_run_section`; Q78's `[5]-[19]` came from exactly these sections, proving the path renders on the benchmark);
- uses **field-agnostic generation** (`_run_section(..., use_field_agnostic_prompt=...)`) — no contract entity required;
- routes every drafted sentence through the SAME `strict_verify` + rewrite path as contract sections (`_run_section` body), with the three-stream verify the live sweep uses.

The single chokepoint that limits enrichment breadth is the evidence subset:

```python
# multi_section_generator.py:3577-3580
ev_subset = [
    evidence_pool[ev_id] for ev_id in section.ev_ids
    if ev_id in evidence_pool
]
```

`section.ev_ids` for an enrichment section is whatever the **LLM outline planner** assigned — a small hand-picked set. The 437 weighted unbound SUPPORTS members are never offered to any section. That is the second, structural funnel.

### 2.3 The fix — a weight-surfaced enrichment section fed by the unbound SUPPORTS baskets

Add ONE enrichment `SectionPlan` whose `ev_ids` are the **unbound** (not bound to any contract `v30_entity_id`) evidence_ids that are basket SUPPORTS members, ordered by `weight_mass` descending. Route it through the UNCHANGED `_run_section` so EVERY surfaced source must survive `strict_verify` to render.

**Insertion point (exact):** `multi_section_generator.py`, immediately AFTER the contract/enrichment plan assembly at `:6482-6492` and AFTER `evidence_pool` is built at `:6505`, BEFORE the dispatch at `:6866`. Implement the selection in a NEW standalone helper so it does NOT edit the death-fix's lines:

- **New helper file:** `src/polaris_graph/generator/weighted_enrichment.py`
  - `def select_unbound_supports_by_weight(*, evidence_pool, credibility_analysis, contract_plans) -> list[str]`
    - Build `bound_eids = { eid for p in contract_plans for slot in p.slots for eid in slot.entity_ids }` (the contract render universe).
    - From `credibility_analysis.baskets`, take members with `span_verdict == "SUPPORTS"` whose `evidence_id not in bound_eids` and `evidence_id in evidence_pool`.
    - Order by the member's basket `weight_mass` (descending), then `evidence_id` (deterministic tiebreak).
    - Return the FULL ordered list — **no `[:N]`, no cap, no target.** Breadth = whatever survives strict_verify downstream.
    - `credibility_analysis is None` (degrade path) ⇒ return `[]` ⇒ no enrichment section ⇒ byte-identical.
  - `def build_weighted_enrichment_plan(ev_ids, *, section_plan_cls) -> SectionPlan | None`
    - Returns `None` when `ev_ids` is empty (byte-identical OFF/degrade).
    - Title: `"Corroborated Weighted Findings"` (a non-contract title ⇒ `is_contract_section()` is False ⇒ routed to `_run_legacy_bounded` ⇒ field-agnostic `_run_section`).
    - `ev_ids = ev_ids`; focus = a neutral framing string ("Additional independently span-verified findings from the weighted source corpus.").

- **Wiring in `multi_section_generator.py` (new lines, additive, NOT inside the death-fix block):** after `:6492`, behind a default-OFF master flag `PG_BREADTH_ENRICHMENT_ENABLED` (LAW VI; unset ⇒ byte-identical), append the plan:
  ```python
  if v30_contract_plans and not partial_mode and _breadth_enrichment_enabled():
      _wfe_ev_ids = select_unbound_supports_by_weight(
          evidence_pool=evidence_pool,
          credibility_analysis=credibility_analysis,
          contract_plans=list(v30_contract_plans),
      )
      _wfe_plan = build_weighted_enrichment_plan(_wfe_ev_ids, section_plan_cls=SectionPlan)
      if _wfe_plan is not None:
          plans.append(_wfe_plan)
  ```
  (Note: `evidence_pool` and `credibility_analysis` are both in scope by `:6594`; the append must occur after `credibility_analysis` is resolved — i.e. relocate this block to just after the credibility pass completes, ~`:6707`, so the analysis is populated. The selection reads only already-built state; no recompute.)

### 2.4 Why this is NOT the banned `_augment_legacy_section_breadth` bolt-on (§-1.3 landmine)

The deleted `_augment_legacy_section_breadth` / `PG_LEGACY_SECTION_BREADTH_TARGET` (`:6507-6512`) was banned because it forced a **per-section distinct-source TARGET number**. This fix is categorically different:

- **No number to hit.** `select_unbound_supports_by_weight` returns the FULL ordered list; there is no `target`, no `cap`, no `top-N`, no floor.
- **Weight is ORDERING, not a filter.** `weight_mass` decides *priority of consideration*, never inclusion/exclusion — every unbound SUPPORTS member is offered.
- **strict_verify is the only gate that decides what renders.** Breadth EMERGES from how many of the offered sources survive the UNCHANGED three-stream verify. If only 30 of 437 survive, 30 render — honestly. That is the §-1.3 "breadth emerges from honest weighted multi-attribution."
- **Surgical, not rewrite:** one new helper file + one additive append; the contract sizing (`required_entities` YAML) is UNTOUCHED (claude_trace.md:69 was right that enlarging the YAML is the banned filter-and-cap — this fix does NOT do that).

### 2.5 The "expand the required-entity set" alternative — noted and DEFERRED (not banned, but more invasive)

The task suggests "expand the required-entity set from the weighted corpus." Dynamically DERIVING contract entities from weight (vs hand-authoring more YAML) is legitimate §-1.3 (it would be weighting, not a hand-cap) — but it touches contract sizing (`report_contract.py`, `contract_outline.py`) and the slot-fill field contract, a much larger blast radius. **The enrichment route (§2.3) is strictly more surgical and reaches the same 437 sources through field-agnostic generation, so it is the chosen mechanism.** The dynamic-entity route is recorded as a possible future generalization, NOT this fix.

### 2.6 Faithfulness-neutrality (item 2)

Every source surfaced into the weighted-enrichment section is:
- **already weighted** (tier/authority — `credibility_pass` / `weight_mass`);
- **already isolated-span-verified `SUPPORTS`** at the basket-member level (`src/polaris_graph/synthesis/credibility_pass.py:442-457`);
- then routed through the **UNCHANGED** `_run_section` → field-agnostic generation → three-stream `strict_verify` (numeric-match + ≥2 content-word overlap + span-grounding) → section floor (≥40% kept). A drafted sentence that does not entail its own cited span is DROPPED exactly as today.

No gate is relaxed. No citation is invented (the LLM must cite a real pool `ev_id` with a valid `[#ev:]` span, or strict_verify drops it). No padding (an empty enrichment section renders the standard gap stub via the existing `_run_section` no-evidence / section-floor path; it does not fabricate). The master flag defaults OFF ⇒ byte-identical until Gate-B activates it. The degrade path (`credibility_analysis is None`) ⇒ empty ev_ids ⇒ no section ⇒ byte-identical.

---

## 3. FAITHFULNESS-NEUTRALITY SUMMARY (per change)

| Change | Touches a gate? | Why faithful |
|---|---|---|
| Item 1 test (no prod code) | No | Proves existing behavior; negative control proves no relaxation. |
| `weighted_enrichment.py` selection | No | Pure read of already-computed baskets; weight = ordering only; returns full list (no cap/target). |
| Enrichment-plan append in `multi_section_generator.py` | No | Adds candidates; `_run_section`'s UNCHANGED strict_verify + section floor decide what renders. Flag default-OFF ⇒ byte-identical; degrade (analysis None) ⇒ empty ⇒ byte-identical. |

**Invariants explicitly preserved:** strict_verify (per-sentence numeric + ≥2 content-word overlap), NLI entailment, 4-role D8, span-grounding, the ≥40% section floor, and the fail-closed sentinel are ALL unchanged. Every new citation is a real pool source that independently survives the same verify the contract sentences do.

---

## 4. THE TEST THAT PROVES IT (breadth up, faithfulness identical)

**File:** `tests/polaris_graph/generator/test_breadth_enrichment_iarch007.py`
**Harness:** extends `test_lane_section_arch005_contract_path.py` shape — drives the REAL `generate_multi_section_report` (or at minimum REAL `run_contract_section` + REAL `_run_section`) with an INJECTED (fake) LLM but **REAL `strict_verify` + REAL citation rewriter** (the live-sweep components), on a FIXED in-memory corpus. No network, no model spend.

**Fixed corpus (constructed, all real-shaped rows):**
- 5 contract-bound entities (matching `clinical.yaml` Q78 `required_entities`), each with a `v30_entity_id` and a verifiable `direct_quote`.
- A claim cluster C1 with 3 SUPPORTS members (one is a contract-bound source, two are UNBOUND) — proves item-1 multi-citation AND item-2 broadening.
- ~6 additional UNBOUND clusters, each with 1-2 SUPPORTS members carrying a real ≥`_MIN_VERIFIABLE_SPAN_CHARS` span whose claim the injected LLM will draft verbatim (so they survive strict_verify).
- **NEGATIVE CONTROL rows (must NOT render):**
  - one UNBOUND member with `span_verdict == "UNSUPPORTED"` (basket-level non-support);
  - one UNBOUND member whose injected draft sentence asserts a number ABSENT from its span (strict_verify numeric-mismatch drop);
  - one UNBOUND member with a fabricated claim sharing <2 content words with its span (content-overlap drop).

**Assertions:**
1. **Breadth up:** with `PG_BREADTH_ENRICHMENT_ENABLED=1`, the rendered report's distinct cited sources ≫ the OFF-run count (and ≫ the 5 contract entities) — specifically ALL the surviving UNBOUND SUPPORTS members appear in the bibliography and inline.
2. **Item-1 multi-citation:** the C1 claim sentence carries `[N]` markers for all 3 of its SUPPORTS members (whole basket), not 1.
3. **Faithfulness identical — negative control:** NONE of the three negative-control rows appears anywhere in `verified_text` or the bibliography. Zero unsupported, zero numeric-fabricated, zero content-mismatch additions.
4. **Anti-cross-claim preserved:** a member of a DIFFERENT cluster is never attached to C1's sentence.
5. **OFF / degrade byte-identical:** with the flag unset, OR with `credibility_analysis=None`, the rendered `verified_text` is byte-identical to the pre-fix run (same 5+planner sources).

Assertion 1 is the breadth half; assertion 3 (the negative control) is the faithfulness half — together they prove "breadth up, faithfulness identical." A test that only checks assertion 1 would pass even if a gate were accidentally relaxed; the negative control is mandatory.

---

## 5. BUILD ORDER + FILE OVERLAP WITH THE DEATH-FIX

This fix overlaps the death-fix on `multi_section_generator.py` and `credibility_pass.py`. To minimize collision:

**Overlap surface (named precisely):**
- **`multi_section_generator.py`** — death-fix owns the credibility-pass wall + always-release degrade block (`:6642-6707`). This fix ADDS an enrichment-plan append AFTER that block (~`:6707`, once `credibility_analysis` is resolved) and reads `evidence_pool`. **No edit inside the death-fix's lines.** Keep the new selection logic in `weighted_enrichment.py` so the only `multi_section_generator.py` change is a ~6-line additive append guarded by a default-OFF flag.
- **`src/polaris_graph/synthesis/credibility_pass.py`** — this fix is READ-ONLY against it (`baskets`, `supporting_members`, `span_verdict`, `weight_mass` already exist, verified at `:140-184`, `:442-457`). No change needed. The death-fix owns the ITEM-1b bounded-pool changes there.
- **`contract_section_runner.py`** — item 1 is READ-ONLY (already wired at `:1364-1372`); only the test references it. No prod edit.

**Build order:**
1. **AFTER the death-fix build releases `multi_section_generator.py` and `credibility_pass.py`** (per the campaign's serialize-hot-files rule — both are in the 5/7-hot-file set). Rebase onto the death-fix branch first.
2. Create `src/polaris_graph/generator/weighted_enrichment.py` (new file — no collision).
3. Add `_breadth_enrichment_enabled()` env reader (LAW VI; default OFF) + the ~6-line additive append in `multi_section_generator.py` after the credibility-pass resolution (~`:6707`).
4. Write `tests/polaris_graph/generator/test_breadth_enrichment_iarch007.py` (new file — no collision); run it + the existing `test_lane_section_arch005_contract_path.py` (must stay green — OFF path byte-identical).
5. Gate-B slate: add `PG_BREADTH_ENRICHMENT_ENABLED=1` to the run slate (`scripts/run_honest_sweep_r3.py` Gate-B env, alongside `PG_V30_PHASE2_ENABLED=1`) so the benchmark activates it.
6. ONE Codex diff gate (per campaign), iter cap per §8.3.1.
7. Final certification: a fresh Q78 run must cite MANY more distinct verified sources than the beatboth7 baseline (485→ far more than 19), with a §-1.1 line-by-line audit confirming ZERO unsupported/fabricated additions.

**Files touched (total):**
- NEW: `src/polaris_graph/generator/weighted_enrichment.py`
- EDIT (additive, ~8 lines, default-OFF): `src/polaris_graph/generator/multi_section_generator.py`
- EDIT (Gate-B slate): `scripts/run_honest_sweep_r3.py`
- NEW (test): `tests/polaris_graph/generator/test_breadth_enrichment_iarch007.py`
- NO EDIT (read-only / proven): `contract_section_runner.py`, `src/polaris_graph/synthesis/credibility_pass.py`, `provenance_generator.py`, `clinical.yaml`.

---

## 6. §-1.3 COMPLIANCE STATEMENT

- **WEIGHT, DON'T FILTER:** `weight_mass` is surfaced as ORDERING priority; every unbound SUPPORTS source is offered to generation. No source is hard-dropped to hit a number.
- **CONSOLIDATE, DON'T DROP:** item 1 renders the WHOLE basket per claim (all SUPPORTS members), not one. Item 2 surfaces the 437 consolidated-but-dropped sources.
- **BASKET FAITHFULNESS:** verdicts come from the already-computed per-member isolated `span_verdict`; the enrichment generation re-verifies each surfaced source against its OWN span via the unchanged strict_verify.
- **ONLY HARD GATE = faithfulness engine:** strict_verify / NLI / 4-role / span-grounding / section floor / sentinel — ALL unchanged. No cap, target, thinner, or hard-filter is added. Breadth EMERGES from honest weighted multi-attribution surviving the unchanged gates.
