---
name: race-maxing-audit
description: "Three-model (Sol/Fable/K3) line-by-line audit of how to max RACE — diagnosis + 4-gate fix plan, awaiting operator gate"
metadata:
  node_type: memory
  type: project
  originSessionId: 21e87760-8436-4090-870d-99ef2121882e
---

**2026-07-20: three frontier models (Sol=gpt-5.6 via codex --search, Fable=claude-fable-5, K3=kimi-k3 via a file-reading tool loop I built) independently, blind, line-by-line audited the outline/search/fetch/compose code + the faith-off report, for how to MAX RACE.** All converged. Full plan: `scratchpad/CONSOLIDATED_FINDINGS_V2.md` (+ raw: sol_audit.txt, fable_audit.txt, k3_audit.txt).

**THE DIAGNOSIS (all 3 agree):** We are NOT under-citing (report has 111 markers). The "11 citations" was a measurement artifact — our 79KB report OVERFLOWS the FACT extractor (Fable proved it: our 29KB run extracted 110). The real problem is COMPOSITION: the pipeline "renders every evidence basket" into ONE flat ~500-word paragraph per section (no headings/tables/lists), machine-junk leaks in, instructions aren't enforced. **Readability 0.3981 is the weakest RACE dim.** Sol's root cause: we "maximize routed rows" instead of "eligible/usable/independent sources per reader-designed paragraph." ALL fixes are UPSTREAM (outline/search/fetch/compose/render) or config — the faith ghost stays dead; NEVER re-add a post-gen verifier. See [[background-task-lifecycle-rule]], [[baseline-next-step]].

**4-GATE FIX PLAN (awaiting operator gate — nothing starts until approved):**
- Gate 1 (hours, ~0 risk): kill `(also mirrored)` leak (PG_MIRROR_CITE_COLLAPSE=0), turn ON concise mode (PG_ANTI_VERBOSITY), strip `(tier X)` labels, dedup bibliography by URL, drop the "Additional Corroborated Findings" residual dump.
- Gate 2 (big lever): section-level narrative composition with structure (subheadings/tables/short paras) replacing basket-by-basket rendering; outline gains sub-sections + a task-coverage matrix. Readability +0.08-0.14 (Sol).
- Gate 3: thread a source-eligibility + DATE-ceiling contract (task wanted pre-June-2023 English journals; ignored) through all stages, keep-not-delete (Rank12 firewall generalization); fetch-until-usable-target + clean extraction (reject BibTeX/nav, no mid-token spans). IF +0.10-0.18; citations 11→40-80.
- Gate 4: cross-study synthesis via structured comparison records (Insight +0.05-0.10, Sol-unique); fix clinical-only tier classifier (29% UNKNOWN on econ); rewrite self-undermining intro.
Re-score RACE+FACT after each gate vs frozen baseline (0.4486/1.0, tag foundation-faithoff-v1). Sol's deltas are directional, not additive.

**STEP 1 SHIPPED (2026-07-21, branch fix/race-step1-render-cleanups, commit b50f7e3):** 6 render/config changes (mirror-note off, concise mode on, tier-labels off, residual-dump off, glue-collapse, token-repair PG_NO_TOKEN_SENTENCE_REPAIR=0). URL-dedup REVERTED after an evidence-based Sol consultation (fold+M50 sim failed; touched 9 evidence_id consumers). Sol+K3 both APPROVED. Result: **RACE 0.4486→0.4643 (Readability 0.3981→0.4428, +0.045)**, FACT citations 11→20 accuracy 0.85 (the 3 misses = real facts cited to a blog/Polish paper/marketing site + primary DOIs returning scrape-stubs → source-selection + fetch, not fabrication).

**ROUND-2 AUDIT (2026-07-21, Sol+Fable+K3 blind, on post-Step-1 state): FULL CONVERGENCE.** Unified finding: the fixes are ALREADY BUILT but flag-gated OFF / unwired / stripped from the "field-agnostic" (non-clinical) path — next round is ARM+WIRE+enforce, not new engineering. Plan: `scratchpad/ROUND2_PLAN.md`, 7 levers ranked: A structure+tables (wire summary_table.py/presentation_tables.py — RQ asked for a table we render zero of; un-forbid structure in abstractive_writer.py:419) = biggest Readability+IF; B source-eligibility (wire the orphaned constraint_extractor as a task-derived contract + citation re-anchoring) = biggest IF+FACT; C coverage (arm PG_ROUTE_ALL_BASKETS — 600/1076 rows homeless — + fix verified_compose.py:1978 break); D synthesis (cross-study cards + PG_CROSS_SOURCE_SYNTHESIS); E fetch-until-usable (PG_FETCH_MIN_BODY_CHARS floor + frame_fetcher DOI salvage); F canonicalize works (55 same-work groups); G methods/limitations from RunFacts. Recommended next: A then B. Model swap (Inkling/Kimi K3 as generator) is a separate track — Inkling 404s on our request shape + reasoning-token leak, needs an integration pass. New govkit rules this session: [[two-way-iteration-rule]], generalization_rule, background_task_discipline.

**Tools built this session (in scratchpad; foundation FACT runner committed):** `score_report_fact.sh` (committed to gate-inversion 3fcddc9), `ask_k3_agent.py` (kimi tool-loop with read_file/grep/list_dir/web_search + 429 retry), `baseline_triple.sh`.

**CODEX/SOL OPERATING LESSON:** codex halts on the repo's CLAUDE.md anti-drift protocol (must prepend an override forbidding it to read/obey CLAUDE.md/loop_state/canonical_pin/state/.codex). And "review every single line" of 56k LOC makes codex over-read forever (3.3MB, never concludes) — instead tell it to prioritize like a senior auditor AND mandate it finish with the deliverable. With both fixes Sol produced the deepest of the 3 audits.
