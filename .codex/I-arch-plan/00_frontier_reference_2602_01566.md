# Frontier reference — arXiv 2602.01566 (FS-Researcher) — what POLARIS should adopt

Date: 2026-07-10. Author: FABLE 5 (architect brain). Branch context: `bot/I-deepfix-relaunch`.
Source paper: **"FS-Researcher: Test-Time Scaling for Long-Horizon Research Tasks with File-System-Based Agents"** (Zhu, Xu, Du, Wang, Wang, Mao, Zhang — arXiv 2602.01566v2). Read via arxiv abs + full HTML (method + results + ablations).
Companion audit: `.codex/I-arch-audit/fable_orchestration_audit.md` (POLARIS current-state, real code, HEAD 0bde6438).

## 0. THE HEADLINE FINDING (read this first)

**arXiv 2602.01566 IS the FS-Researcher paper — the same paper POLARIS already borrowed its query-gen from** (`src/polaris_graph/retrieval/fs_researcher_query_gen.py`, pinned ON via `PG_QGEN_FS_RESEARCHER=1`). But POLARIS adopted ONLY the query-gen slice (todo-queue, one query per todo, 6-item checklist re-plan, 35 queries / 6 rounds). The paper's actual headline innovations — the structured knowledge base, the report-writer review loop, and the persistent file-system workspace — were **never adopted**. Those unadopted pieces map almost one-to-one onto the top gaps in our own orchestration audit (no holistic review, title-starved one-shot outline, global-not-sectioned baskets, thin resume). So "be smarter than FS-Researcher" decomposes into two moves: (a) adopt the rest of the paper we skipped, and (b) go beyond it at its one known weak point (the frozen knowledge base — see R8).

---

## 1. Paper method summary (mechanics, from the paper text)

**Problem:** context-window limits break long-horizon research. **Solution:** use the file system as "durable external memory and a shared coordination medium" across agent sessions. Two agents share one persistent workspace.

### 1.1 Workspace layout (Markdown files, deliverables + control files)

- `index.md` — table of contents: the topic deconstruction AND the knowledge-base hierarchy in one living file. Folder/file names are descriptive, "reflecting the semantic relationships between the deconstructed topics."
- `knowledge_base/` — tree-structured distilled NOTES. "Every statement in the notes of knowledge_base/ comes with a citation that points to a file in the sources/ directory."
- `sources/` — archived raw webpages.
- Control files: **todo file** (items marked `[PENDING] / [IN-PROGRESS] / [COMPLETE]`), **checklists**, **log file** ("all inspection results, review findings, and session plans... accessible to subsequent sessions").

### 1.2 Context Builder agent (the librarian)

ReAct loop per session: inspect workspace → plan → execute. Browses with `search_web` / `read_webpage`, updates `index.md`, distills notes into `knowledge_base/`, archives raw pages into `sources/`. Dynamically edits the todo file (add / remove / reorder / status-change). **End-of-session self-review:** "conducts a review against the checklist, identifying any potential errors, gaps, or conflicts in the knowledge base"; non-compliant items are re-marked `[IN-PROGRESS]` — gaps seed the next session's work.

### 1.3 Report Writer agent

Runs AFTER the builder; "treats the knowledge base built by Context Builder as the only source of facts," web tools removed — **the KB is frozen once writing starts** (their design choice; our exploit point, see R8). Multi-session writing: session 1 creates the outline file, which "also serves as the todo file"; each later session composes exactly ONE section, loading only the relevant KB subtree on demand. **Section-level review:** section is `[COMPLETE]` only when its checklist passes (e.g., "Are there any statements or claims in the report that do not come with citations?"). **Report-level review:** after all sections, an overall review runs against a report-level checklist (reference-list integrity, duplicated citations, cross-section quality); "if flaws are identified, the corresponding sections are marked as [IN-PROGRESS] again" — a real revise loop.

### 1.4 Test-time scaling (the paper's namesake claim)

Scale = number of Context Builder ROUNDS (3 → 5 → 10). Sources grow 21.6 → 33.3 → 38.8; unique URLs 21.3 → 32.1 → 38.0; RACE 51.18 → 52.37 → 53.05; Comprehensiveness 49.72 → 51.96 → 52.31; Insight 52.27 → 53.43 → 54.70. Monotone gains on everything except Readability; diminishing returns after 5 rounds. File I/O overhead of the whole workspace mechanism: "less than 0.03% of total time."

### 1.5 Results + ablation

DeepResearch Bench (100 PhD-level tasks): RACE 53.94 (Claude-Sonnet-4.5 backbone) / 52.76 (GPT-5) / 52.51 (Gemini-2.5-Pro) — beats the strongest baseline RhinoInsight by +3.02, with Comprehensiveness +3.74 and Insight +4.4; baselines include OpenAI Deep Research, Claude-Research, Gemini-2.5-Pro-DeepResearch, LangChain-Open-Deep-Research, WebWeaver, EnterpriseDeepResearch. DeepConsult: 80.00% win rate. BrowseComp subset: 55.0% vs 43.9% official harness. **Ablation:** removing the persistent workspace (control files: todos/checklists/logs) drops RACE 52.76 → 48.69 — the status-tracking + review loop is the load-bearing piece, not any single prompt.

---

## 2. What POLARIS already has vs the paper (honest map)

| Paper mechanism | POLARIS today (audit ref) | Verdict |
|---|---|---|
| Todo-queue query-gen with checklist re-plan | ADOPTED — `fs_researcher_query_gen.py`, coverage-driven 6-item checklist, 35q/6r | Have (partial: re-plan is coverage-driven, not outline/KB-driven) |
| Structured notes / hierarchical KB feeding the outline | Outline sees ≤150 rows, TITLE-only on big pools (audit stage 5) | **Missing** |
| Per-statement citation in notes → archived source | STRONGER at compose time (strict_verify span-grounding); absent at the planning layer | Have (stronger) at compose; missing at plan |
| Outline-as-todo, section statuses, section checklist | One-shot outline, parallel compose, no statuses, no structural checklist (stage 5) | **Missing** |
| Report-level review with re-open + revise | NO holistic review in production; `cross_section_reflector.py` built but wired only into pipeline B (stage 8, gap #1) | **Missing — top audit gap** |
| Per-section on-demand KB subtree | Baskets global; composer gets raw rows, not section baskets (stage 6, gap #6) | **Missing** |
| Persistent workspace / multi-session resume | A15 resume refetches degraded rows only; no resumable todo/outline/review state | Partial |
| Test-time scaling of builder rounds | Hardcoded 35 queries / 6 rounds | Missing (as a governed budget knob) |

---

## 3. RANKED adoption list (each: POLARIS section → concrete design direction)

Ranked by expected report-quality impact, consistent with the audit's gap ranking. All items: faithfulness engine (strict_verify / NLI / D8 / provenance) is UNTOUCHED and remains the only hard gate; nothing below drops/caps/thins sources (§-1.3); knobs are requirement-aware budgets, never number-targets.

**R1 — Report-level review + re-open loop → `holistic-review`** (audit gap #1)
Adopt the paper's overall review: after assembly, review the whole report against a report-level checklist (cross-section contradiction in PROSE, redundancy, tone consistency, depth, coverage vs outline, reference integrity); sections that fail are re-marked in-progress and revised. Machinery exists: `synthesis/cross_section_reflector.py` (MoST Phase R) is built, wired only into pipeline B — wire it (or a fresh reviewer) into `run_honest_sweep_r3.py` post-assembly. **Faithfulness seam: every revised sentence re-runs strict_verify before it can replace the original — revision can never fabricate.** Requirement-aware: checklist items partially derived from the parsed deliverable spec (audit RA-b), not a fixed list. Parallelism: per-section review verdicts run concurrently; only the revise-verify step serializes per section. Paper evidence this loop is load-bearing: workspace ablation −4.07 RACE.

**R2 — Structured KB digests feed the outline planner → `orchestrator-outline`** (audit gap #3)
The paper's writer plans the outline FROM distilled, citation-carrying notes — not from raw page titles. POLARIS analog: feed `_call_outline` the finding-dedup BASKET DIGESTS (consolidated claim text + corroboration count + tier weights + member ev_ids), grouped into a topic tree keyed by `query_origin` (each row already carries it — the todo→note hierarchy exists implicitly). This replaces the 150-row title-starved menu with the semantic equivalent of `index.md` + `knowledge_base/`. Keep facet-emergent titles (no fixed count). Digests MUST carry ev_id + span offsets so downstream composition still cites raw spans, never paraphrased digest text.

**R3 — Outline-as-todo with statuses + section-level structural checklist + outline-refine round → `synthesis` + `orchestrator-outline`**
Adopt the STATUS semantics ([pending]/[in-progress]/[complete] per section) and the section-level checklist (did this section address every basket/todo assigned to it? any assigned high-corroboration basket unused?) — but **NOT the paper's one-section-per-session serialization** (that is a context-window workaround; our parallelism mandate keeps sections composing concurrently). After first drafts, one outline-refine pass may merge/split/re-title sections against what the drafts actually contain (the audit's "no revision after drafts" fix). Citation-presence checking stays with strict_verify (already stronger than the paper's checklist question).

**R4 — Section-scoped baskets = per-section KB subtree → `dedup-baskets`** (audit gap #6)
The paper's writer loads only the relevant KB subtree per section. POLARIS: intersect global basket membership with each section's `ev_ids` and hand the composer its section-scoped baskets (claim + all corroborating members + weights) instead of flat evidence rows. Consolidation semantics unchanged — keep-all-members, multi-citation (§-1.3 principle 2).

**R5 — Outline/KB-gap-driven re-plan + governed round budget → `query-gen`**
Two upgrades to the existing `fs_researcher_query_gen.py`: (a) replace the FIXED 6-item coverage checklist with deficits derived from the evolving basket tree/outline skeleton — which sub-topics have thin, conflicting, or zero baskets — so re-planning serves the eventual REPORT, not just corpus coverage (the audit's stage-2 gap). This matches the paper's own review ("errors, gaps, or conflicts in the knowledge base"), which is KB-structural, not a fixed list. (b) Make rounds/queries a governed, requirement-aware BUDGET (config per question breadth + time budget), replacing hardcoded 35/6. Paper evidence: 3→5 rounds is where most gain lives; diminishing after 5. **§-1.3 guard: the budget is spend, never a quality-number target — no knob may exist to "hit" a breadth score.**

**R6 — Either-anchor off-topic judging → `off-topic`** (audit gap #2 — smallest fix, high protection)
In the paper, every source is archived under a note that belongs to a deconstructed SUB-topic — relevance is intrinsically judged against the sub-topic. POLARIS's topic judge sees only the MAIN question. Fix per the audit: pass the row's `query_origin` sub-query into `topic_relevance_gate`; verdict ON if relevant to EITHER anchor; hard-delete only when off-topic to BOTH (fail-open preserved, §-1.3.1 disclosure preserved). Also reconciles the fetch-side/selection-side anchor inconsistency the audit found.

**R7 — File-system research-state checkpoint → `checkpoint-resume`**
Adopt the control-file pattern: persist per-run workspace state — todo queue + statuses, basket-tree index, outline + section statuses, review log — as run artifacts (JSON/MD under the run's output dir), updated as statuses change. Resume then continues MID-RESEARCH from the closest phase (ground rule 2026-07-01: resume from closest checkpoint, never re-run fresh), instead of today's fetch-only A15 refetch. Paper evidence: whole mechanism costs <0.03% wall-clock.

**R8 — GO BEYOND THE PAPER: bounded writer→builder feedback seam → `query-gen` + `synthesis`**
FS-Researcher FREEZES the KB when writing starts ("web browsing tools removed") — a section that discovers thin evidence at compose time is stuck. POLARIS can be smarter: when a section's basket coverage falls below its structural checklist (R3), emit a TARGETED retrieval todo for that sub-topic (low parallelism, small bounded budget, one loop max), fold new rows through the normal tier/topic/dedup path, recompose the section. This is the one place we outrun the paper rather than catch up to it. Bound is a fixed loop count (config), not a quality target.

---

## 4. Conflicts / flags (sovereignty + faithfulness)

1. **Sovereignty — paper backbones are closed models.** Best results use Claude-Sonnet-4.5 / GPT-5 / Gemini-2.5-Pro. The MECHANISM is model-agnostic; POLARIS implements it on the operator-locked open-weight stack (`config/architecture/polaris_runtime_lock.yaml`: deepseek-v4-pro generator, GLM-5.1 mirror, minimax-m2 sentinel, qwen judge). Adopt the architecture, never the backbones. Expect our absolute scores to differ from the paper's.
2. **Faithfulness — the paper's grounding is WEAKER than ours.** Their guarantee is "every note statement carries a citation to an archived file" plus checklist self-review. That is citation-presence, not span-entailment. POLARIS must NOT let any adopted layer substitute for strict_verify: (a) checklists are STRUCTURAL checks (coverage, statuses, redundancy), never claim-truth gates; (b) every sentence produced or revised by any new loop (R1, R3, R8) re-runs strict_verify; (c) basket digests fed to the planner (R2) carry ev_id + span offsets so composition always grounds on raw spans — never on paraphrased note text (paraphrase-drift is the failure mode of note-based KBs).
3. **Serialization — do not copy the one-section-per-session loop.** It exists to dodge context limits, not because serial is better. Keep parallel section composition (runtime-parallelism mandate); adopt only the status/checklist/re-open semantics.
4. **§-1.3 DNA — no number-chasing knobs.** Round budgets (R5) and feedback-loop bounds (R8) are SPEND budgets from config/requirements. If any implementation grows a knob whose purpose is "make RACE/breadth hit X," that is the banned day-waster pattern — stop.
5. **KB-freeze is the paper's weakness, not a rule.** Do not import it (see R8).

---

## 5. Fold-in note for the master execution plan

R1 and R6 are the cheapest high-impact items (R1: module exists, needs wiring + verify seam; R6: prompt + one plumbed field). R2+R3+R4 form one coherent workstream (basket-tree → outline → section-scoped compose → statuses) and should be planned as a unit. R5 rides on R2's basket tree. R7 is infrastructure that makes every long run safer. R8 lands last — it needs R3's checklist to exist first.
