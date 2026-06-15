# POLARIS — Master Fix List (consolidated, Codex-verified) — 2026-06-14

Sources merged: forensic bug ledger (state/forensic_bug_list.md), drb_75/drb_78 hang forensics, Marlin/AB-MCTS + SOTA research, and the Codex line-by-line review (CODEX_VERDICT.txt — specs below are the *corrected* ones). Simple English. "QUICK" = surgical, hours–2 days. "V2" = bigger, after the run. All quick fixes are faithfulness-safe (no gate is relaxed).

## TIER 1 — CRITICAL, must fix before any re-run (these killed/degraded runs)

1. **The hang — TWO separate variants, both run-killers. #1 priority.** No LLM call path has a tight TOTAL deadline, so a trickled/dead socket freezes the run. Both transport-only, faithfulness untouched.
   - **(a) F33 — generator path** (`openrouter_client.py:1566`): the streaming read timeout defaults to the full 6500s budget → ~108-min hang. **Killed drb_75.** Fix: add a 120s per-chunk `read=` timeout on the stream call (keep-alives reset it, so slow reasoning is safe); existing retry reopens a fresh socket.
   - **(b) BUG-HANG-J1 — entailment-judge path** (`entailment_judge.py:210`): `httpx.Client(timeout=30.0)` is a bare float = per-read GAP timeout with NO total deadline and NO `asyncio.wait_for` → **truly unbounded** (a 14-min judge call was observed). **Killed drb_78** — strictly worse than F33. Fix: explicit `httpx.Timeout` + a hard per-attempt TOTAL deadline + treat null content as retryable before `json.loads`. Keep GLM + the fail-closed `judge_error` sentinel.
   - **(c) BUG-HANG-J2 [P1]** — the judge client leaks CLOSE_WAIT sockets on the error path (drb_72 had 47 accumulating live); close half-open sockets + cap keepalive.
   - **(d) BUG-22 — generator distill_map/generate calls run 18–32 MINUTES each** (drb_90: 1924s/1645s/1556s/1107s), slow-but-succeeding but a hung one wouldn't be caught for ~1.8h. Add a per-call `asyncio.wait_for` total deadline well below 6500s (≈600–900s) + retry-on-fresh-socket + surface per-call duration. Do (a)+(b)+(c)+(d) as ONE "tight total deadline on every LLM call (generator + every judge)" change.
2b. **BUG-21 — a run can DIE SILENTLY with no terminal artifact (CRITICAL).** drb_76 (one of the three "critical" runs) vanished mid-verification — NO report, NO manifest, NO crash file — leaving run_status frozen at `generation_started` forever; a blind operator never learns it aborted. Likely OOM from 3 concurrent gate_b runs. FIX (faithfulness-neutral): top-level try/finally that ALWAYS writes a terminal manifest (`status=error_*` + exception + phase) on any exit; heartbeat the real sub-phase; **SERIALIZE / cap concurrency** of per-question runs so they don't OOM each other.
2. **BUG-15 — Zyte never fired** despite the key being present (drb_90), so 3 of 4 anchor sections came out empty. FIX: diagnose + fix the Zyte trigger condition so the paid unlock actually runs. QUICK. *(Must fix before BUG-14.)*
3. **BUG-14 — silent loss of top sources.** A broken/empty fetch (a "Loading…" stub) is mislabeled "low relevance" and silently dropped — lost 24 top-tier journals on drb_72. FIX: detect stub/empty fetches, mark them `fetch_failed` (not low-relevance), and route to fail-loud Zyte re-fetch. Depends on BUG-15. QUICK–MED. Restores weight-not-filter.

## TIER 2 — HIGH quick wins (quality, surgical, faithfulness-safe)

4. **BUG-1 — report-writer blind to its own evidence.** Titles ARE fetched but dropped before the evidence row is built, so the planner guesses section placement. FIX: backfill the title onto the evidence row + into the outline digest (`live_retriever.py:4364`). QUICK. (Codex-confirmed source-true.)
5. **BUG-18 — a banned hardcoded "breadth target" stack (a §-1.3 violation).** Bigger than first thought: it's "choose EXACTLY 5 sections," "NEVER emit only 3 when corpus ≥100 rows," "target 12–20 ev_ids," plus a retry that hard-requires 5–6 sections (`multi_section_generator.py:1047/1049/1086-1089/1872-1906`). FIX: rip out / demote the whole count-target stack → evidence-supported sectioning + disclose when evidence is thin; add a regression test that no prompt/retry contains a hard section count. QUICK–MED. Restores DNA.
6. **BUG-7 — completeness gate grades against the wrong subject.** A GLP-1/diabetes-drug checklist is run on gut-microbiota, Parkinson's, and metal-ions/CVD questions → false "fully covered." FIX: decouple the checklist's "clinical-ness" from the raw routing domain; drive critical-contraindication applicability with a real drug/intervention detector (NOT substring matching); fail-closed/disclose on ambiguity. MED. **Clinical-safety caveat:** must regression-test on real drug + non-drug questions (a wrong "non-applicable" would disable a real safety abort).
7. **BUG-19 [now HIGH — STRUCTURAL] — the faithfulness gate cannot reject boilerplate; a verbatim self-substring trivially entails itself.** Smoking gun: an NTSB **"Page not found" 404 page** was verified ENTAILED ("a faithful subset of the span"). 17–34% of ENTAILED verdicts across runs are web chrome / PDF headers / "URL Source:/Markdown Content:/Title:" / cookie text / table fragments / bare DOIs — all counted as "verified claims," inflating the verified count with non-content. FIX (NOT a gate-relaxation — INPUT hygiene): strip crawl chrome + drop non-assertional/table/DOI fragments BEFORE finding-extraction AND before the gate. QUICK–MED. Makes the gate score real prose only.
8. **BUG-20 — faithful reports built on weak sources.** Every sentence matches its source, but the sources are sometimes consumer-health/marketing pages (BGI Genomics, a family-physician blog, myparkinsonsteam.com) because the T1 journals were lost. FIX: mostly solved by fixing BUG-14/BUG-1 (recover the T1s) + surface credibility weight to the generator so it prefers T1 spans (weight, not drop). MED.

## TIER 3 — MED fixes

9. **BUG-8 — retrieval wanders off-topic.** Agentic/secondary queries pull unrelated sources (drugs into a metals corpus; COVID into a Parkinson's corpus). FIX: pre-fetch topical WEIGHT (not drop) + explicit budget disclosure; needs the URL harvester to carry snippets (a contract change) for the screen to work. MED (not the trivial reorder first thought).
10. **BUG-17 / BUG-10 — contradiction detector explodes into noise** (a 30 MB / 22,000-entry file grouping unrelated numbers under "subject=unknown"). FIX: separate "clinical routing" from true drug-subject extraction; gate predicate/subject precision before pairing; treat unknown-subject as possible-mismatch/disclosure — do NOT blanket-skip (could drop a real contradiction). MED. Shared root with BUG-7. Safety caveat.
11. **BUG-2 — one generation call capped reasoning at 1,000 tokens** (below the "reasoning always max" lock). FIX: ensure reasoning is max on that call. QUICK.
12. **BUG-9 — STORM ran out of time → degraded fallback outline.** FIX: a *disclosed* time-budget reservation for outline generation (`agents/storm_interviews.py`), not a coverage target. QUICK.

## TIER 4 — LOW / cleanup

13. **BUG-5 — stale `gate_b_query_crash.json`** makes a healthy run look crashed. FIX: clean it up on a fresh attempt (`run_gate_b.py:2185`). QUICK.
14. **BUG-13 — schema mismatch** (convergence_assessment dict-vs-string, self-recovered). FIX: normalize in `schemas.py:2115`. QUICK.
15. **BUG-6 — a few paywalled PDFs fully lost.** Coverage gap; largely helped by fixing BUG-15 (Zyte).
16. **BUG-23 — a false-alarm benchmark preflight HARD-CRASHES a paid run.** `check_fa2_competitor_outputs_present` aborted drb_72's first attempt because a competitor markdown was missing (a scoring-harness file, not research). FIX: downgrade to a non-fatal warning, or only enforce when scoring is requested. QUICK. (Also crashed my own first GPU fire — recurring.)

## ALREADY FIXED — just verify it's deployed (do NOT re-fix)
- **BUG-3 (status file)** — the heartbeat already passes cost + section/claim counters; only finer-grained generation liveness remains. Mostly done.
- **BUG-12 (DuckDuckGo)** — `ddgs` is already pinned in requirements.txt; just verify the deployed venv has it.

## CUT / REJECTED (Codex)
- **"Demote strict_verify from drop → label" (V2 B3) — CUT.** Changing the hard gate's action from "don't ship unsupported prose" to "ship it labeled" relaxes faithfulness. Only as a separately operator-gated change with proof that labeled-unsupported text can't be read as a report assertion.

## V2 — bigger, after this run (medium–large, not surgical)
- **AB-MCTS-style adaptive wide-vs-deep controller** on the existing agentic-round seam (`agents/searcher.py`) with an on-topic-yield exit criterion (fixes BUG-8 at the root). It's compute-allocation, never source-dropping (honors §-1.3). Reward MUST be coverage-weighted (supported-claims / gap-closure), NEVER strict_verify pass-rate ("if the reward can go up by saying less, it's the wrong reward"). Touches lane caps + STORM/deepener timing + reward plumbing → medium-large. Phase-0 = telemetry-only reward prototype first. Open-weight (TreeQuest, Apache-2.0 — pin + license-verify).
- **Open-weight multi-LLM regeneration** (different open models per attempt) — bake-off on the 5 golden questions before any paid sweep.
- **Question-aware nugget completeness** (telemetry/disclosure only — the old breadth canaries are already retired).
- **Contradiction-feedback-into-search** (only AFTER BUG-17 precision is fixed).

## Build order (locked)
1. **Unified "tight total deadline on every LLM call"** — F33 (generator stream) + HANG-J1/J2 (judge) + BUG-22 (distill_map/generate 18–32 min) in one change. Kills all three run-killers.
2. **BUG-21** — always-write-terminal-manifest + **serialize/cap concurrency** (3 concurrent runs OOM-killed drb_76). Re-run SERIALIZED (or ≤2 at a time).
3. **BUG-15** (Zyte: make it trigger; on fire-and-fail, fall through not gap-disclose) → **BUG-14** (stub-fetch → re-fetch not drop).
4. **BUG-1 / BUG-18 / BUG-19 (structural input hygiene) / BUG-7** → then re-run the held runs (drb_75, drb_78, drb_76, + optionally 72/90) from the pre-generation checkpoint with the fixes.
Each fix Codex-gated; faithfulness never relaxed.

## Run status snapshot (2026-06-15 ~06:11)
- DEAD/held: drb_75 (F33 generator hang), drb_78 (HANG-J1 judge hang), **drb_76 (silent death, BUG-21, likely OOM)** — all 3 pools reserved.
- LIVE: drb_72 (verifying, slow ~28s/sentence, alive), drb_90 (generating, degraded 18–32 min/call, alive). Both on un-fixed code → at risk; if either hangs (0 CPU + ESTABLISHED openrouter socket rx=tx=0) → hold, do not blind-resume.
