# Zero-Cost + Paid Validation Plan (Honest Framing)

**What this plan actually delivers:**
- **Phase 0** closes advisor gap 3 at $0 via focused integration test.
- **Phases 1–6** are a **pre-flight smoke test** of the full pipeline using Claude as LLM substitute. This catches **integration, state, schema, async, and wiring bugs** — not LLM-behavior bugs. It does NOT close advisor gaps 2 or 4.
- **Phase 7** is a **required** paid GLM-5.1 run. It closes advisor gaps 2 (production perspective diversity) and 4 (actual fabrication patterns the detector must face). Loopback cannot substitute for this.
- **Phase 8** is ship decision.

## Fundamental limit (stated upfront, not buried)

I (Claude) produce cleaner outputs than GLM-5.1. Every bug that only surfaces with GLM-5.1-shaped output — malformed JSON, reasoning-token routing, prompt non-compliance (the class of bug `FIX-GLM5-STRUCTURED` / commit `4d967e6` fixed) — **will pass loopback and fail in production.** Loopback tests integration, not LLM-behavior compliance. The paid run is insurance against that class of bug; it is not optional.

Additionally: when loopback auto-serves calls with templates, any downstream code that depends on GLM-5.1-specific output shape will silently pass here. Tier A templates are Pydantic-valid but shape-divergent from real GLM-5.1 output.

## Pattern I broke in this plan

I silently deleted tasks #41 and #43–51 (the 10-vector plan) without surfacing it to the user. Second time in this session after task #60. Surfacing now: **we are explicitly single-vector. Ten-vector validation is deferred until one vector ships successfully.**

---

## Phase 0 — Focused remediation integration test  ($0, 30 min)

**Closes advisor gap 3 cleanly.** No full pipeline needed.

Write `scripts/pg_remediation_integration_test.py`:
1. Build minimal `wiki_result` dict with one `sections` entry containing known fabricated text that includes valid `[CITE:ev_1]` tokens pointing to a fake evidence_id.
2. Build minimal `outline` dict with corresponding section.
3. Build `evidence_chain` with one `ev_1` entry whose `source_content` directly contradicts the fabricated text (so detector ratio will exceed 40%).
4. Call `compose_from_wiki(wiki_result, outline, evidence_chain, query)` directly.
5. Capture original `sections[0]["content"]`, let remediation run, capture final `sections[0]["content"]`.
6. Assert:
   - G0a: `hallucination_audit` is non-empty, first entry has `needs_rewrite=True`
   - G0b: Original content contains the planted fabrication span
   - G0c: Final content differs from original (mutation happened)
   - G0d: Final content does NOT contain the flagged span verbatim (remediation injected the span into the prompt's avoid-list and the LLM — me, serving via the loopback mechanism — rewrote around it)
   - G0e: `<50 words → keep original` silent fallback did NOT fire (len(revised_content.split()) >= 50)

**Requires:** Loopback mode wired for the compose call only. I serve exactly one re-compose request manually.

**Exit:** All 5 assertions pass → advisor gap 3 closed at $0.

---

## Phase 1 — Loopback LLM-substitution audit  ($0, 30 min)

**Purpose:** Prove no LLM call bypasses `LoopbackLLMClient`.

1. Read `src/polaris_graph/llm/loopback_client.py` end-to-end. Confirm API-parity with `OpenRouterClient`.
2. Grep `src/polaris_graph/` for direct `httpx`/`requests`/`openai` calls that bypass the client abstraction.
3. Verify `graph.py::build_and_run` and all node constructors honor `PG_LOOPBACK_MODE=1`.
4. Smoke: launch pipeline with `PG_LOOPBACK_MODE=1`, confirm first LLM call appears in `loopback/pending/` within 60s and pipeline blocks there.

**Kill switch — concrete decision rule:**
- If the bypass is in planner/analyzer/verifier/synthesizer/composer (core path): **abort, patch bypass, resume Phase 1**.
- If the bypass is in an auxiliary path (audit, memory, metrics): **document as untested path, continue**.

**Exit:** One pending file within 60s. No "real API" log lines. Decision rule applied to any discovered bypass.

---

## Phase 2 — Tiered dispatcher with shape-drift detection  ($0, 1 hour)

Build `scripts/loopback_dispatcher.py` replacing `loopback_auto_universal.py`.

### Classification (prompt fingerprint)

| Tier | Matcher | Handling | Notes |
|---|---|---|---|
| A1 | "generate search queries" / STORM query gen | Auto: 10-15 query templates per perspective | Low-risk plumbing |
| A2 | "canonicalize URLs" / "dedup bibliography" | Auto: identity pass-through | Low-risk plumbing |
| A3 | "assign perspective to source" | Auto: round-robin over 9 perspectives, seeded | **Known circular w.r.t. gap 2 — flagged for paid-run revalidation** |
| B1 | SourceAnalysisBatch | **Operator** (me) — I read fixture content, extract real quotes | |
| B2 | Verifier LLM fallback (NLI low-confidence) | Operator | |
| C1 | ReportOutline | Operator | |
| C2 | Section compose / abstract | Operator — **include `[CITE:ev_N]` tokens** | Required for downstream routing |
| C3 | Remediation re-compose (contains `unsupported_spans`) | Operator | |

### Required behaviors

- Pydantic-validate every response against the schema the request specifies. Reject invalid → log + leave pending.
- **Shape-drift log:** every Tier A auto-response is written with a `template_fingerprint` metadata field. Post-run, diff this against a GLM-5.1 reference corpus (TBD in Phase 8) to identify silent divergence.
- Atomic response write: `.tmp-{id}` → fsync → rename `{id}.json`.
- On stdout: one-line summary per Tier B/C request — call ID + fingerprint + blocking.
- Graceful SIGINT shutdown.

**Exit:** Empty `loopback/` → dispatcher idle (no busy loop). Synthetic pending file → correct tier classification + valid response.

---

## Phase 3 — Fixture pre-fetch  ($0, 30 min)

Pre-fetch 20–30 real intermittent-fasting sources into `loopback/fixtures/if_sources/`:
- 8 RCTs (Scientific), 2 FDA/EFSA (Regulatory), 2 industry (Industry), 2 meta-analyses (Methodological), 2 cost-effectiveness (Economic), 2 WHO/CDC (Public_Health), 1 preprint (Emerging_Trends), 1 foundational (Historical)

**Rationale:** When Tier B1 calls arrive, dispatcher serves me pre-fetched content instantly instead of live web fetch. Eliminates flakiness.

**Exit:** 20+ fixture files. Spot-check 3 for real content. URL list committed.

---

## Phase 4 — Execution  ($0, 2-4h wall-clock, 60-105 min operator)

**Checkpoint/resume — addressed explicitly:**
The polaris_graph pipeline writes state checkpoints at node boundaries (verified via `state/progress_ledger.jsonl` and `state/last_pointer.json` per CLAUDE.md §2.1). If the run interrupts:
- Re-launch with `PG_RESUME=1` (verify this flag exists in Phase 1; if not, full restart and accept the cost).
- If no durable resume exists: **accept one restart budget**. On second interruption, abort Phase 4 and go to Phase 7.

**Launch:**
1. `PG_LOOPBACK_MODE=1` added to `.env` (not shell — memory note #2).
2. Start dispatcher in background terminal.
3. `python -u -m scripts.pg_loopback_minimal --vector PG_LB_FS_01_health`.
4. Watch `logs/polaris_graph.log`.
5. Serve Tier B/C inline as they surface.

**NO deliberate fabrication injection.** Advisor correctly flagged that planted-known ≠ unknown-unknown — a fabrication test here proves nothing about the real threat model. Deferred to Phase 7.

---

## Phase 5 — (removed — merged into Phase 4)

---

## Phase 6 — Smoke-test audit  ($0, 45 min)

**Framing: these gates verify the pipeline didn't crash and plumbing works. They do NOT close advisor gaps 2 or 4.**

| Check | Criterion | What this proves |
|---|---|---|
| G1 | Pipeline ran to completion, final JSON written | No crash-level bugs |
| G2 | `perspective_entropy` field populated (any value ≥ 0) | FIX-ENTROPY code path executes — **not** that production produces diverse perspectives |
| G3 | `hallucination_audit` is a non-empty array with `hallucination_ratio` fields | Detector wired and runs — **not** that it catches production fabrication |
| G4 | Log contains `[wiki-compose] Hallucination audit:` line | FIX-HALLUC-WIKI-WIRE fires |
| G5 | Log contains `[polaris graph] FIX-ENTROPY: perspective_entropy=` line | Logging wired |
| G6 | Bibliography "Unknown" author count | **<30% = ship OK; 30-50% = fix required pre-ship; >50% = ship-blocker** (not a soft "known gap") |
| G7 | 10 random `[CITE:]` references resolve to real bibliography entries | Citation integrity plumbing |
| G8 | D3: distinct bibliography URLs after canonicalization | URL dedup plumbing holds |

**Evidence content audit (5 random entries):**
- `direct_quote` appears literally in `source_content` (verbatim substring match)
- `statement` is a paraphrase of `direct_quote` (not an extrapolation — measured by Rouge-L or manual)
- `perspective` matches source type

**Exit:** G1 mandatory. G2-G5, G7, G8 should pass. G6 per thresholds above. If G6 > 30% Unknown → **fix analyzer bibliography extraction before Phase 7**.

---

## Phase 7 — Paid GLM-5.1 single-vector run  ($1-5, required, 60-120 min)

**Not optional.** This is the only way to close advisor gaps 2 and 4, and to catch GLM-5.1-specific output bugs.

**Setup:**
1. `PG_LOOPBACK_MODE=0` (or unset) in `.env`.
2. `OPENROUTER_DEFAULT_MODEL=z-ai/glm-5.1` confirmed.
3. `PG_BUDGET_GUARD_USD=10` as safety cap.
4. Same vector: PG_LB_FS_01_health.
5. Launch `pg_loopback_minimal` or the non-loopback equivalent.

**Gates (production gates, not smoke test):**

| Check | Criterion | Advisor gap closed |
|---|---|---|
| P1 | `perspective_entropy > 0.3` after production run | gap 2 (real diversity from STORM + LLM) |
| P2 | Hallucination detector flags ≥1 section OR flags 0 sections with operator-audited final report showing no fabrication | gap 4 (real fabrication pattern exposure) |
| P3 | Operator reads final report cover-to-cover, identifies 0 invented PMIDs / authors / statistics | gap 4 (threat model empirical) |
| P4 | Budget stayed under $5 | cost sanity |
| P5 | No GLM-5.1-specific crashes (JSON malformation, reasoning-token misrouting) | gap 1 (GLM-5.1 compliance) |

**If P3 fails (real fabrication appears in output):**
- Examine whether detector missed it (threshold too loose) or wasn't invoked (wiring bug only exposed by GLM-5.1 output shape).
- This is the single most important signal from the whole plan.

---

## Phase 8 — Ship decision and shape-drift reconciliation  ($0, 1 hour)

1. **Shape-drift diff:** compare Tier A template responses from Phase 4 against GLM-5.1 responses from Phase 7 for the same call types. Any silent divergence → log as loopback-limitation.
2. **Outcome writeup:** `docs/validation_outcome.md` with Phase 0, Phase 6, Phase 7 gate results + shape-drift findings.
3. **Ship decision:**
   - If Phase 0 + Phase 6 G1-G5 + Phase 7 P1-P5 all pass: **ship**.
   - Bibliography (G6) must be <30% Unknown.
   - P3 (no invented content in final report) must pass without caveats.
4. Commit dispatcher, fixtures, integration test, outcome doc.
5. Update `MEMORY.md` with loopback-vs-paid lessons.
6. Delete stale 10-vector tasks (surface this: "10 vectors deferred until 1 ships").

---

## Summary of what's actually closed

| Advisor gap | Closed by | Confidence |
|---|---|---|
| 2: entropy populates in production | Phase 7 P1 | High (real run) |
| 3: remediation mutates final JSON | Phase 0 | High (focused test) |
| 4: detector catches real fabrication | Phase 7 P2+P3 | Medium (one vector sample) |
| 1 (implicit): GLM-5.1 output-shape bugs | Phase 7 P5 | Medium (one vector sample) |

**Loopback's role:** catches integration/schema/async bugs before we spend real money. Not gap closure.

**Paid run's role:** closes the real gaps. Required.

**Total cost:** ~30 min (Phase 0) + ~2-4h wall + ~60-105 min operator (Phases 1-6) + $1-5 + 60-120 min (Phase 7) + 1h (Phase 8).

## Honest failure modes

- Loopback smoke test passes, paid run exposes GLM-5.1 crash → fix in code, re-run paid. Budget for one re-run: $10 total.
- Paid run produces fabrication → fix prompt / thresholds, re-run. Same budget.
- Bibliography still >30% Unknown after Phase 6 → analyzer fix required, one additional day.
- Context exhaustion during Phase 4 → abort, restart, accept cost. If it happens twice, skip to Phase 7 (paid run doesn't need operator context).
