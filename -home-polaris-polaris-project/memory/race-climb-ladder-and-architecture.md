---
name: race-climb-ladder-and-architecture
description: "RACE climb ladder (0.4605->0.5084) + the compose-path architecture that decides which levers apply + the structure render-replay design"
metadata:
  node_type: memory
  type: project
  originSessionId: 21e87760-8436-4090-870d-99ef2121882e
---

**2026-07-21 — RACE climb, all Sol(max)+K3 gated + committed on branch fix/race-batch1-evidence-substrate (GitHub aldrinor/deep-cove-research):**
- GLM-5.2 baseline **0.4605** -> K3 generator **0.4903** (+0.030, commit 1a5b751 scripts/run_k3.sh) -> **K3+B/E/F 0.5084** (+0.018, 3x: 0.5069/0.5070/0.5113, tight). Per-dim K3+B/E/F: Comprehensiveness 0.521, Insight 0.524, Instruction 0.499, **Readability 0.457 (weakest)**. Leaders (old Gemini eval): Tavily 52.44, VeriTrace 55.77; GPT-5.5 board (our eval) still populating.
- Commits this stretch: 57b3d3a Batch-2 structure part-1 (PG_SECTION_STRUCTURE, NO-OP pending render-replay), fa5d52e route-all (PG_ROUTE_ALL_BASKETS registered+resolve), 958bf17 multicited (PG_VERIFIED_COMPOSE_MULTICITED registered).

**CRITICAL ARCHITECTURE FINDING (decides which levers apply):** the champion recipe leaves **PG_VERIFIED_COMPOSE OFF** (`_verified_compose_enabled()` default off), so section prose is composed by the **LEGACY `_call_section` path** (section-writer LLM, prompt = `SECTION_SYSTEM_PROMPT_TEMPLATE_FIELD_AGNOSTIC`, multi_section_generator.py:3708), NOT `_compose_section_per_basket` (the IF branch, verified_compose ON). Consequences:
- **Batch-2 structure (rule 7 flip)** targets the RIGHT writer (_call_section) — but the _call_section output flows through `resolve_provenance_to_citations_with_count` (multi_section_generator.py:1262) which FLATTENS (provenance_generator.py:5121 `" ".join`), so it's a NO-OP until the render-replay lands.
- **route-all** (`route_orphan_baskets_to_section_plans`, called at multi_section_generator.py:11251 regardless of compose path) APPLIES — it appends orphan/singleton ev_ids to the best-topical-overlap section before composition. Relevance-aware (not blind); Sol+K3 approved.
- **verified_compose MULTICITED + subtopic-decomposition + first-failure-break** live INSIDE `_compose_section_per_basket` => **NO-OP on the champion path** (need PG_VERIFIED_COMPOSE on). Registered multicited for infra only. On the _call_section path, cross-source multi-citation is a SECTION-PROMPT rule-10 concern.

**STRUCTURE RENDER-REPLAY DESIGN (Sol max-reasoning spec — the riskiest change, touches the 0.508 seam; do dedicated + replay-validated, DON'T rush):** in `resolve_provenance_to_citations_with_count` (provenance_generator.py ~4594-5125), under `PG_SECTION_STRUCTURE && _resolve_verify_off`: (1) use `sv.sentence` as the LAYOUT template; (2) replace each provenance token IN PLACE with its already-assigned `ev_to_num` number (reuse the finalized map — NEVER a second resolver); (3) at :5121 join structured units with `"\n"` not `" "`; (4) fix `_strip_bogus_ev_markers` (:714 `re.sub(r"\s{2,}"," ")`) to `[^\S\r\n]` so it preserves `\n`. Sol's two gotchas: :5106 currently moves citations to the unit END (detaches table-row markers) — the in-place replace fixes that; and ASSERT (don't silently end-append) when corroborators/mirror-collapse are active (that combo needs block/row-aware rendering). VALIDATE by replaying a SAVED structured draft through old+new renderers (assert OFF byte-identical, ev_to_num/emitted_count identical, whitespace-normalized prose identical, markdown structure present) BEFORE paying for a live run. Long-term correct design = typed blocks/cards (writer emits heading/bullet/table-row blocks, each claim keeps its ev-id, compose renders at compose_agentic_report_s3gear329.py:449) — which also makes D comparison cards lift Insight AND Readability.

**Remaining levers ranked by risk:** route-all result (safe, measuring: outputs/k3_b1_routeall_run) < section-prompt rule-10 multi-cite for FACT (low) < structure render-replay (HIGH, above) < D synthesis cards (typed blocks). See [[k3-generator-race-win]], [[batch1-evidence-substrate-result]], [[race-maxing-audit]].
