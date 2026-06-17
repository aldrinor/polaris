# I-arch-007 — The 485→13 Breadth Funnel: Exact file:line Trace

**Slug:** `drb_78_parkinsons_dbs` (Q78). **Snapshot:** `outputs/audits/iarch007_death_forensic/draft_audit/Q78_corpus_snapshot.json`. **Live report:** `outputs/audits/beatboth7/drb_78_parkinsons_dbs/report.md`.

## 0. Empirical ground truth (re-derived from the snapshot, not the brief)

| Metric | Value | How measured |
|---|---|---|
| `evidence_for_gen` substantive sources | **485** | `len(d['evidence_for_gen'])` |
| T1 peer-reviewed | 92 | `tier` startswith `T1` |
| ≥400-char content | 451 | `len(direct_quote or statement) >= 400` |
| stubs (<100 char) | 12 | — |
| **Bound to a contract entity (`v30_entity_id` set)** | **5** | `[e for e in efg if e['v30_entity_id']]` |
| **UNBOUND (no `v30_entity_id`)** | **480** | — |
| └ of those, substantive (≥400 char) | **447** | the dropped breadth |
| └ of those, T1 peer-reviewed | **87** | dropped T1 mass |
| Contract `required_entities` | **5** | `config/scope_templates/clinical.yaml` |
| Contract `rendering_slots` | **4** | — |
| Distinct sources cited in live report.md | **19** ([1]–[19]) | bibliography |
| └ contract-bound | 5 ([1] NEJM RCT, [2] MDS-UPDRS, [3] hardware-complications, [4] FDA-DBS-label, [11] FDA-levodopa) | = the 5 `v30_entity_id` values |
| └ from legacy enrichment sections | 14 ([5]–[10],[12]–[19]) | Long-term Outcomes / Population Subgroups / Safety / Limitations |

The 5 `v30_entity_id` values are EXACTLY the 5 `required_entities` ids:
`dbs_vs_medical_therapy_rct, parkinson_staging_progression, dbs_complications_warning_signs, dbs_device_mri_safety, dopaminergic_withdrawal_caution`.

**The funnel is real and it is structural: 485 weighted/scored/basketed → 5 contract-bound render targets + ~14 LLM-planner-selected enrichment citations. 447 substantive weighted sources (87 T1) are computed then discarded at the render layer.**

## 1. Where `required_entities` is SIZED — the PRIMARY collapse (a)

- **`nodes/report_contract.py:181-498`** `load_report_contract_for_slug`. `required_entities` is read VERBATIM from `per_query_report_contract.<slug>.required_entities` in the scope-template YAML (`:235-379`). **The count is whatever a human authored in the YAML** — for `drb_78_parkinsons_dbs` that is **5**. It is NEVER computed from, capped against, or scaled to the retrieved-source count. There is no cap CODE; the cap is the hand-authored list itself. This is the §-1.3 FILTER-AND-CAP anti-pattern frozen into config.
- **`nodes/contract_outline.py:218-282`** `compose_outline_from_contract`. The outline's render targets are exactly `contract.entities_by_slot()` (`:217,:225`) — i.e. only the 5 entities. No non-contract source can enter a slot here.
- **`nodes/contract_outline.py:347`** `titles[:6]` — **NOT a cap.** It truncates the one-line `focus` STRING for prompt-header readability (`_compose_section_focus`). It does not drop entities from `entity_ids` (those are emitted in full at `:238,:264`). Ruled out as a funnel site.

**This is the dominant funnel: the render universe is fixed at 5 by config, independent of the 485 retrieved.**

## 2. Single-citation render — NOT the collapse (b is already built)

- **`generator/provenance_generator.py:3009-3033`** `resolve_provenance_to_citations` → `:3036` `_with_count`.
- The INLINE multi-citation basket render (B6/B8 keystone) IS implemented: **`provenance_generator.py:3091-3126`** builds the SUPPORTS-by-cluster index, and **`:3246-3251`** appends `[N]` markers for every OTHER independently span-verified (SUPPORTS) basket member of the clusters the sentence already cites.
- So a rendered claim is NOT strictly single-citation. **But its reach is bounded:** `verified_corroborators_for_tokens` (`:2992-3006`) only expands a token that maps to EXACTLY ONE cluster (`:3000` anti-cross-claim) AND only surfaces members of a cluster a contract/enrichment sentence ALREADY cited. It can corroborate the ~5–19 already-cited claims; it cannot reach the 447 unbound sources that no rendered sentence cites.

**(b) is real but secondary: multi-citation exists; it multiplies citations on already-rendered claims, it does not add breadth.**

## 3. Basket wiring — (c) is EMPIRICALLY FALSE; baskets ARE wired

- `credibility_pass.py:357-492` `_assemble_baskets` builds one `ClaimBasket` per cluster with `supporting_members` = ALL members + `verified_support_origin_count` (isolated-span-verified). `:676-684` builds `cluster_id_by_evidence`. These ARE returned on `CredibilityAnalysis` (`:686-694`).
- They ARE threaded into the LIVE contract render: **`contract_section_runner.py:1276-1280`** calls `resolve_provenance_to_citations(... baskets=_baskets, cluster_id_by_evidence=_cluster_id_by_evidence)`, and **`:1364-1372`** runs the inline corroborator expansion on the V30 contract path (Gate-B forces `PG_V30_PHASE2_ENABLED=1`, `:1257`).
- The A1 basket fallback (`contract_section_runner.py:363-465`, fired `:929-1008`) ALSO already synthesizes a frame row for a non-contract same-claim corroborator and routes it through the UNCHANGED `_fill_one_slot → slot-fill → strict_verify` path — **but only for a SHELL slot** (`:939-950`: `not _slot_has_real_prose and _slot_frame_rows_all_shell`) and only for a corroborator that shares a SINGLE cluster with one of the slot's 5 bound entities.

**Proof (c) is false:** the report cites 19 sources but only 5 are contract-bound. The other 14 came from machinery downstream of the contract (enrichment sections), so "basket-not-wired" contradicts the evidence. The honest finding: baskets are wired at `:1276`/`:1364`; the limit is REACH, not WIRING.

## 4. The enrichment path EXISTS — and is the SECOND, smaller funnel

The task asked whether non-contract sources can surface. They can, via the legacy enrichment sections — but that path is itself bounded:

- **`multi_section_generator.py:6482-6492`** assembles `plans = v30_contract_plans + _enrichment_plans` (enrichment = any LLM-outline section whose title is not a contract title — Long-term Outcomes, Population Subgroups, Limitations, Contradictions). The report's [5]–[10],[12]–[19] live in exactly these sections.
- Enrichment sections run via **`multi_section_generator.py:3544`** `_run_section`, whose evidence subset is **`:3577-3580`** `ev_subset = [evidence_pool[id] for id in section.ev_ids]` — i.e. ONLY the handful of `ev_ids` the **LLM outline planner** assigned to that section, NOT the weighted basket pool. The planner selects a small set per section, so enrichment adds ~14 sources, not 447.
- The honest breadth augmenter that once existed here was DELETED as a banned bolt-on (`:6507-6512`, `_augment_legacy_section_breadth` / `PG_LEGACY_SECTION_BREADTH_TARGET`). So today nothing surfaces the weighted pool into enrichment sections either.

## 5. Conclusion — which of (a)/(b)/(c)

- **PRIMARY = (a) contract-entity-count.** The render universe is hard-fixed at 5 by the hand-authored `required_entities` YAML (`report_contract.py:235-379`; `contract_outline.py:217-282`). 480/485 sources are unbound and can never enter a contract slot. This is ~97% of the funnel.
- **(b) single-citation = PARTIAL/already-built.** Multi-citation basket render exists (`provenance_generator.py:3091-3126,:3246-3251`; contract path `contract_section_runner.py:1276-1280,:1364-1372`). It multiplies citations on the ~5–19 rendered claims; it does not add breadth. Reach-capped by (a).
- **(c) basket-not-wired = FALSE.** Baskets and `cluster_id_by_evidence` are threaded into the live contract resolve and the A1 fallback. The limit is reach (single-cluster, already-cited, or shell-slot-only), not absence of wiring.
- **Second funnel:** even the legacy enrichment path (`multi_section_generator.py:3577-3580`) is bounded by the LLM planner's per-section `ev_ids`, not the weighted pool.

## 6. Proposed fix (SURGICAL, §-1.3-aligned — surface the already-computed baskets; do NOT enlarge the YAML)

**Do NOT add `required_entities` to `clinical.yaml`** — that is the banned filter-and-cap pattern (breadth must EMERGE from weighted baskets, not a longer hand-list).

Generalize the A1 basket-fallback mechanism — which already synthesizes a frame row for a non-contract corroborator and routes it through the UNCHANGED `_fill_one_slot → slot-fill → strict_verify` path — from "shell-slot rescue ONLY" to "surface every HIGH-WEIGHT non-contract basket the credibility pass already verified."

**Insertion point:** `generator/contract_section_runner.py` — after the contract slot loop (~`:1010`), add an enrichment-from-baskets pass that iterates the credibility pass's high-`weight_mass` baskets whose members are NOT already bound to a contract slot, synthesizes frame rows via the existing `_synth_frame_row_for_corroborator` (`:428-465`), and routes them through the SAME `_fill_one_slot → _verify_one_stream` path into a new "Corroborated weighted findings" enrichment section. Equivalently, lift the `section.ev_ids` selection in `multi_section_generator._run_section` (`:3577`) so enrichment sections draw the high-`weight_mass` basket members rather than only the LLM planner's picks.

**Faithfulness:** the 447 unbound substantive sources are ALREADY weighted (tier/authority), clustered (`origin_cluster_id`), and isolated-span-verified (`span_verdict == "SUPPORTS"`) by the credibility pass. Surfacing them re-uses the UNCHANGED strict_verify / span-grounding / NLI / 4-role gates — only SUPPORTS members with a real ≥`_MIN_VERIFIABLE_SPAN_CHARS` span render, exactly as A1 already does. No gate is relaxed, no citation invented, no padding: a basket member ships iff it independently entails its own span. Breadth EMERGES from the honest weighted baskets, satisfying §-1.3.
