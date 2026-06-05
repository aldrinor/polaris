# POLARIS Full-Capability Readiness Audit — Master Plan (DRAFT, pending 3-way agreement)

**Status:** DRAFT. Requires agreement from **Claude + Codex + Operator** before any execution (operator directive 2026-06-05).
**Owner issue:** (to be created) `I-ready-000 — full-capability readiness audit umbrella`.
**Trigger:** operator 2026-06-05 — "the throttle was one bug; exhaustively audit every potential full-cap issue, fix, smoke, audit line-by-line, Codex decides go/fix, 5-iter cap, parallel workflows."

---

## §1. Mission & binding standards

**Mission:** before the live 1000-URL beat-both run, prove POLARIS is *actually* ready at full capability — every tool wired + functional + logged, every cap/timeout/token coherent, and the OUTPUT correct + right-sized + faithful for real users, not just for the 5 locked benchmark questions.

**Binding standards (override convenience):**
1. **Proof, not "trust me"** — nothing is "done" until proven FUNCTIONAL in a live run whose `tool_utilization` + manifest + line-by-line audit are the evidence. (operator `feedback_no_downgrade_without_operator_approval_2026_06_04`, `feedback_audit_capability_in_shipping_path_before_spend_2026_05_29`.)
2. **§-1.1 line-by-line audit** — every end-result is audited claim-by-claim vs the actually-cited source span (VERIFIED / PARTIAL / UNSUPPORTED / FABRICATED / UNREACHABLE), both Claude and Codex in parallel. NO metadata/pattern/string-presence audits (lethal in clinical).
3. **Codex is the only gate** — Codex decides go-or-fix per issue; 5-iteration cap (§8.3.1); force-APPROVE at iter-5 with residuals → follow-up issues.
4. **No silent downgrade** — any cap/feature reduction needs explicit operator approval; default is FULL capability (floor semantics, fail-closed preflight — see I-cap-005).
5. **Faithfulness invariants intact** — provenance tokens + strict_verify + 4-role D8 gate are NEVER weakened by any fix; advisory features stay advisory.
6. **Flag-gated, byte-identical when off** — every change is env-flag-gated so the locked 5-question benchmark stays byte-identical; new behavior activates only on the general/real-user path until verified.

---

## §2. Audit dimensions (the work-list)

Grounded by the 14-scout research pass (current-state cross-check + 2026 best practice per concern). Each row → its own GitHub issue + per-issue lifecycle (§4).

> **FINDINGS TABLE — populated from the scout workflow (current-state, is-wired, 2026 best practice, gap, severity, fix, smoke, §-1.1 audit). See §6.**

Dimensions (operator's list + Claude additions):
- **D1 context-window / sectioning** — does 1000+ URLs fit the generator/Mirror context; section-by-section generation + cross-section continuity.
- **D2 caps / timeouts / tokens** — every fetch/search cap, per-LLM output+reasoning token budget, every timeout coherent at full cap (extends I-cap-005).
- **D3 tool connectivity / functionality / logging** — every tool reachable + functional + utilization-logged; no silent fail-open.
- **D4 query-complexity routing** — simple questions (e.g. Telus/Bell 20-yr stock, split-adjusted) get a right-sized smart answer, not the heavyweight report. *(scout: P1, classifier built but NOT wired into benchmark path.)*
- **D5 anti-over-complication / writing style** — sharp-reporter grounded prose, no fluff; full info for user judgment.
- **D6 chart / table / artifact generation** — functional, high-quality, no weird artifacts.
- **D7 document ingestion** — arbitrary uploads → MD the LLM can read + cite.
- **D8 deep OCR / graphics** — graphic-heavy docs → OCR + figure understanding → MD.
- **D9 contradiction surfacing** — detect + present source contradictions to the user.
- **D10 safety / refusal** — dangerous/illegal queries refused + redirected.
- **D11 prompt design — generator** — grounded-RAG citation-enforced prompt vs 2026 best practice.
- **D12 prompt design — voters (Mirror/Sentinel/Judge)** — verify/adversarial/arbiter prompts vs 2026 best practice.
- **D13 citation faithfulness at scale** — per-sentence provenance + strict_verify + NLI hold at 1000 URLs.
- **D14 dedup / relevance / ranking** — picks the BEST evidence at 1000 URLs (threshold + rerank + dedup), not the first N.

(Severity + sequencing assigned in §6 from the findings.)

---

## §3. Execution architecture — parallel workflows, paced for API safety

**Goal:** work as many issues in parallel as safe, without API errors, with auto-recovery of stalled agents.

**3.1 Clustering.** Group the 14 dimensions into independent **issue-clusters** (a cluster = issues that touch disjoint code so they can run in parallel without merge conflicts). Tentative clusters (finalized in §6):
- Cluster A (retrieval/scaling): D2, D3, D13, D14.
- Cluster B (generation/output): D1, D5, D6.
- Cluster C (intake/inputs): D4, D7, D8.
- Cluster D (faithfulness/safety): D9, D10.
- Cluster E (prompts): D11, D12.

**3.2 Parallelism + API-rate safety.**
- **≤ 3 execution workflows concurrent** (not all 5 at once) — keeps total in-flight agents well under the workflow concurrency cap (`min(16, cores-2)`) and under OpenRouter/Codex rate limits.
- **Codex is SERIALIZED across all parallel workflows** (§8.4 one-codex-at-a-time). Codex gates form a single queue; a workflow that reaches a Codex gate waits its turn. This is the primary pacing constraint — build/smoke run in parallel, Codex reviews run one-at-a-time.
- **`isolation: 'worktree'`** for any cluster whose agents mutate files in parallel, to avoid working-tree conflicts.
- **Back-off on API error**: an agent that hits a rate-limit/API error retries with exponential back-off; persistent failure → the dimension is parked and surfaced (not silently dropped).

**3.3 The 10-minute wake loop (auto-recovery).** A heartbeat (`ScheduleWakeup` dynamic loop, ~600s — under the 5-min cache window is wasteful; ~600-900s is the right idle cadence) that, on each fire: (a) checks for stalled/paused workflows + parked dimensions, (b) re-launches/resumes them (`resumeFromRunId` returns cached completed agents instantly, re-runs only the failed/new ones), (c) if all clusters are done → stops the loop. This revives the "pausing AI to rework again" the operator described.

**3.4 Honest no-silent-cap.** If parallelism is reduced for API safety, that is logged (not silent). If a dimension is parked after retries, it is surfaced to the operator, not dropped.

---

## §4. Per-issue lifecycle (the polaris_task_cycle, per dimension)

Each dimension issue runs the standard cycle, Codex the only gate, 5-iter cap:

`BOOT → BRIEF → codex-gate(brief) → BUILD (flag-gated, faithfulness-safe) → SMOKE (offline first) → codex-gate(diff) → §-1.1 LINE-BY-LINE AUDIT of the end result (Claude + Codex parallel) → codex go/fix decision → CLOSE`

- **Brief** opens with the §8.3.1 cap directive verbatim; includes the scout's current-state + best-practice + adjacent-file scan so Codex VERIFIES not discovers.
- **Build** is flag-gated + byte-identical-when-off; never weakens provenance/strict_verify/4-role.
- **Smoke** offline unit/integration first; a tracker-on micro-run only where a live signal is required.
- **§-1.1 audit** of the end result is the EVIDENCE that decides go/fix — claim-by-claim vs cited span, both Claude and Codex.
- **Codex go/fix**, 5-iter cap; iter-5 force-APPROVE with residuals → follow-up issues.

---

## §5. Three-way agreement protocol (before execution)

1. **Claude** authors this plan grounded in the scout research (done at §6).
2. **Codex** reviews the plan (brief-gate): scope correctness, sequencing, faithfulness-safety, the parallel/pacing design. APPROVE required.
3. **Operator** reviews the plain-language summary + approves (the merge/spend gate).

Only after all three → execution workflows launch (§3).

---

## §6. Dimension findings + sequencing (POPULATED FROM SCOUTS)

Full per-dimension findings (current_state w/ file:line · is_wired · 2026 best practice · gap+full-cap failure · severity · fix · smoke · §-1.1 audit) are saved in `.codex/I-ready-000/findings/<dim>.md`. Severity tally: **1 P0, 11 P1, 2 P2.**

### 6.1 Findings (severity-sorted)

| # | Dimension | Sev | Wired? | Gap (one line) | Fix direction |
|---|---|---|---|---|---|
| F1 | **context_window_sectioning** | **P0** | yes | Generation sees **20 of 1000+** evidence rows (98% silently dropped): the slate raised retrieval but NOT `PG_LIVE_MAX_EV_TO_GEN` (def 20); 2nd ceiling `max_ev_per_section=30`. Same silent-throttle class as I-cap-005, one stage downstream. | Add `PG_LIVE_MAX_EV_TO_GEN`(120-200)+`PG_USE_FINDING_DEDUP`+`PG_RELEVANCE_FLOOR` to slate + preflight floor; raise per-section cap; **empirical bake-off** 20 vs ~50-reranked vs ~150 (lost-in-the-middle aware) on the locked slice. |
| F2 | citation_faithfulness_at_scale | P1→P0 | yes | The **binding** `strict_verify` entailment gate **fails open** on judge error → at 1000 sentences, transient errors ship unverified clinical claims as "verified," silent in manifest. (I-cap-005 fixed only the advisory path.) | `strict_verify.py:281-289` detect `judge_error:` → drop (fail-closed); surface judge_error_rate to manifest + run-level abort floor; bounded retry + route-up/majority-vote for high-stakes. |
| F3 | caps_timeouts_tokens | P1 | yes | `PG_POST_FETCH_LOOP_BUDGET` is a FIXED 2400s — doesn't scale with `fetch_cap`, so 1000 URLs truncate mid-fetch. | Make loop budget ∝ fetch_cap (`max(900, fetch_cap*per_url)`); thread fetch_cap into the deadline; add to preflight. |
| F4 | dedup_relevance_ranking | P1 | partial | Lexical rerank only; shortlists 1000 / extracts 1500 but feeds ~20 to gen (overlaps F1). | Slate `PG_USE_FINDING_DEDUP=1`+`PG_RELEVANCE_FLOOR` (no-cap relevance mode keeps every row ≥ floor); consider cross-encoder rerank (bake-off). |
| F5 | tool_connectivity_logging | P1 | partial | `manifest['tool_utilization']` covers only **3 of ~9** tools (OpenAlex enrich + agentic backends + crawl4ai untraced) → can't prove utilization at full cap. | Add `_trace_tool` to the untraced network tools w/ distinct tool_name; promote to manifest; assert ≥N tools present. |
| F6 | query_complexity_routing | P1 | no | No complexity router in the run path → simple queries (Telus/Bell 20yr) force the heavyweight pipeline, burn ~1000 URLs + budget, no stock-split awareness, then abort/ungrounded. | Wire `run_scope()` complexity signal into `run_one_query` BEFORE retrieval; `simple`→right-sized 1-section answer + lower fetch cap + split-adjust required-entity; flag-gated, faithfulness unchanged. |
| F7 | safety_refusal | P1 | no | **No harm classifier / refusal** anywhere in the benchmark/launch path. | Pre-scope harm-classifier + refuse-with-redirection in the SHARED path (ahead of `run_scope_gate`, not intake.py which benchmark bypasses); open-weight classifier. |
| F8 | prompt_design_voters | P1 | yes | Judge prompt omits the per-verdict rubric (G-Eval/EvalHack); verdicts under-defined. | Rewrite `judge_adapter.py:39-67` with one-line definition per verdict (VERIFIED/PARTIAL/UNSUPPORTED/...). |
| F9 | prompt_design_generator | P1 | yes | Per-sentence prose contract strong, but section/answer-SHAPE is domain-locked (clinical) — wrong for non-clinical. | Domain-aware shape contract; decouple shape from the clinical default; reference 2026 grounded-RAG prompt practice. |
| F10 | doc_ingestion | P1 | no | At full cap the beat-both Gate-B run **cannot use an uploaded user document** — no benchmark wiring; `DocumentIngester` exists but unconnected. | Add `--document-ids/--upload-file` to `run_gate_b main`; resolve via `DocumentIngester`, chunk into citable evidence on `q["uploaded_documents"]`. |
| F11 | ocr_graphics | P1 | no | Graphic-heavy/scanned uploads return HTTP 400 (only `.md`/`.txt` accepted in the v6 upload path). | Wire a real parser (Docling + Surya/DeepSeek-OCR-2) → Markdown w/ tables + figure captions/OCR. |
| F12 | contradiction_surfacing | P1 | yes | Only numeric-regex / NegEx contradictions surfaced; **no semantic/NLI** conflict layer. | Add an NLI/LLM cross-doc conflict pass (reuse the Qwen Judge) merged into `contradictions.json`, additive/flagged. |
| F13 | anti_overcomplication_writing | P2 | yes | Prompt tells the generator to **match GPT-5.4/Gemini DR length** — imports the verbosity bias the operator wants gone. | Front-loading directive (answer-first sentence) + replace length-maximizing language; inverted-pyramid. |
| F14 | chart_table_artifact | P2 | partial | Markdown tables only — **zero rendered figures**; table-cell numbers not strict_verify-gated. | Run table cells through the strict_verify numeric gate; add deterministic figure gen (faithfulness-gated) as a later add. |

### 6.2 Two-tier framing per issue

Most retrieval/cap findings split into: **(a) immediate throttle fix** (env-only, add to the slate + preflight floor — cheap, low-risk, kills the silent downgrade now) and **(b) architectural fix** (the empirical bake-off / new component — the operator-mandated "research + test candidates, don't guess"). The plan ships (a) fast and gates (b) on the bake-off evidence.

### 6.3 Execution clusters (code-disjoint → parallelizable; ≤3 workflows concurrent, Codex serialized, worktree-isolated)

- **C1 evidence→generation scaling (P0 first):** F1 + F4 + F3 — shared files (slate/preflight/`run_honest_sweep_r3`/evidence_selector). Sequential within; the env-only throttle fix lands first, bake-off second.
- **C2 faithfulness:** F2 (strict_verify fail-closed) + F12 (semantic contradiction).
- **C3 answer-shape:** F6 (complexity router) + F9 + F13 (generator prompt/shape/style).
- **C4 verifier prompts:** F8 (judge rubric).
- **C5 inputs:** F10 (doc wiring) + F11 (OCR).
- **C6 safety:** F7 (refusal hook).
- **C7 observability:** F5 (tool tracing).
- **C8 artifacts:** F14 (table verify + figures).

**Sequencing:** C1 (P0) runs first (it gates the meaningfulness of every downstream §-1.1 audit — a report written from 2% of the corpus can't be fairly audited). Then C2-C8 fan out ≤3 at a time. Each issue runs the §4 lifecycle, Codex go/fix at 5-iter cap, with a live tracker-on micro-run + §-1.1 line-by-line audit as the go/fix evidence.

### 6.4 Operator decisions (LOCKED 2026-06-05)
1. **Scope: ALL 14** (P0 + 11 P1 + 2 P2). No deferral.
2. **Empirical bake-offs: YES** — run the F1 evidence-cap (20 vs ~50-reranked vs ~150, lost-in-the-middle aware) + F4 rerank bake-offs on the locked DRB-EN slice; bounded spend approved (operator `feedback_research_then_empirically_test_candidates`).
3. **New deps: YES** — add the input/OCR stack (Docling + Surya/DeepSeek-OCR-2 for F11) + a charting lib for F14 figures.
4. **Hold the live run: YES** — the 1000-URL beat-both run does NOT fire until C1 (P0, the 98%-drop) + F2 (binding fail-open faithfulness) land. A run today writes from <2% of the corpus and can ship unverified claims; auditing it would be unfair.

**Agreement status:** Claude ✅ (plan authored, grounded) · Operator ✅ (2026-06-05, all 4 decisions above) · Codex ⏳ (plan-gate running, w1s8fzsh8). Execution begins only on Codex APPROVE (or after addressing REQUEST_CHANGES).
