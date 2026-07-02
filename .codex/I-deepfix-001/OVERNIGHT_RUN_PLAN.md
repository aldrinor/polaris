# I-deepfix-001 OVERNIGHT RUN PLAN — WALL PIN (v2, corrected 2026-07-02)

**AUTHORITATIVE. Survives context compaction. On resume, re-read this + RELAUNCH_GATE_CHECKLIST.md + PREFLIGHT_MATRIX.md + scratchpad/box_ledger.csv, then continue from the first unproven step.**

## THE CORRECTION (operator, 2026-07-02) — DO NOT REVERT TO THE OLD MISTAKE
Offline unit tests are **NOT** a real preflight. The mineru incident proved it: mineru passed every offline check (installed, imports, DOPARSE_OK) and then **HUNG the live pipeline** on the first real PDF. Offline-green proves LOGIC, not LIVE-WIRING.

**The SERIOUS preflight = a SMALL-SCALE REAL RUN that proves each of the 32 fixes' EFFECT actually appears in real output, BEFORE the large paid run.** Prove-in-small-real-run. Never config-only, never offline-only, never silent-fallback, never victory-on-deficient. Prove each fix works small and real before spending big.

## STATE
- 32 fixes committed + Codex-gated + offline product gate 374/0 green — that is LOGIC proven, NOT enough.
- mineru in-process (vlm-transformers) HANGS the pipeline (do_parse pipe-read block) + degrades (0 real extractions -> Docling). Corpora are ~72% PDFs, so this is a hard blocker. FIX = mineru vLLM server on card1 (operator-chosen 2026-07-02).
- BOX-1 = vast instance 43580988, ssh9.vast.ai:20988, 2xA100-80GB (card0 pipeline, card1 mineru server). vLLM installing.
- VEXE=/c/Users/msn/AppData/Roaming/Python/Python313/Scripts/vastai.exe. Python needs Windows paths (C:/Users/...).

## PHASE A — FIX + PROVE MINERU (isolated, no paid run)
A1. Install vLLM on box-1 (in progress). If build fails on torch2.5.1/cu124, pin mineru's required vllm version; if truly infeasible, REPORT to operator (do not silently drop to Docling).
A2. Start mineru-vllm-server on card1: `CUDA_VISIBLE_DEVICES=1 mineru-vllm-server --gpu-memory-utilization 0.4 --port 30000`. Poll for "Application startup complete"; nvidia-smi card1 ~20-40GB.
A3. **PROOF TEST (short, ~1min):** extract ONE real academic PDF via PG_MINERU25_BACKEND=vlm-http-client + PG_MINERU25_SERVER_URL=http://localhost:30000. PROVEN iff chars>500 of coherent prose (not empty/hang/error). REPORT the char count + text sample to the operator.

## PHASE B — SMALL-SCALE REAL 32-FIX PREFLIGHT (the serious one)
B1. Config a100_complete_env.sh: remove any mineru-disable lines; add the vlm-http-client backend + server URL.
B2. Run ONE small cheap REAL run through the whole pipeline: `run_gate_b.py --only drb_72_ai_labor --smoke-scale --out-root outputs/preflight_smoke`.
B3. When it renders, §-1.1 READ the real output and confirm EACH 32-fix EFFECT is present (content, not counts). Build the 32-row PROVEN/NOT-PROVEN table at scratchpad/smoke_32fix_verify.md:
- mineru real-extract chars>0 (U1/U7/U8/U19/U20)
- breadth funnel fetched->tiered->kept->CITED sane (U9/U11/U21/U31)
- tiers T1/T2 mix, no scam/retracted on top, journals flagged (U10/U12/U14)
- consolidation baskets>0 multi-origin (U4)
- prose SYNTHESIZED multi-cite, not span-dump (U5)
- safety sections carry provenance tokens + verified (U3)
- headline subject-anchored, not out-of-context number (U13)
- numeric claims CITED (U24); quantified numbers clean (U27)
- chrome-clean (U6/U18); duplicate sections collapsed (U17)
- CRAG corrective loop fired (U22); completeness recognized interventions (U23)
- scorecard honest (U26); OpenAlex honest (U25); contradiction fail-closed + noise-suppressed (U28/U29)
- U5/U8 canaries armed and did NOT false-fire; status=success
**Any fix NOT firing in the real output = a real gap -> fix + re-gate + re-smoke. That is the whole point.**

## PHASE C — LARGE RUN (only after Phase B proves all 32 fire real)
5 questions, one per 2xA100 box (each with its own proven mineru server): drb_72_ai_labor, drb_75_metal_ions_cvd, drb_76_gut_microbiota_crc, drb_78_parkinsons_dbs, drb_90_adas_liability. Forensic-monitor READING CONTENT every tick (queries on-topic, tiers sensible, extracted text clean, section claim-vs-span §-1.1). On render, §-1.1 line-by-line audit + DeepTRACE + DeepResearch-Bench-II. Honest beat-both-or-gap report. Destroy each box when done+audited.

## STANDING RULES
Cost not a limit; never weaken the frozen faithfulness engine; never re-enable PG_SWEEP_ANALYST_SYNTHESIS; never fake/inflate a metric (§-1.1 lethal clinical); ≤4 codex; resume-from-checkpoint on crash; kill orphans; destroy a box when its run is done+audited; report each step plain (operator blind). Keep GitHub #1344 + these wall docs + memory in sync at every phase.
