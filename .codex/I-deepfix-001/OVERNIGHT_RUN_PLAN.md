# I-deepfix-001 OVERNIGHT RUN PLAN — WALL PIN (operator asleep, authorized 2026-07-02)

**This is the authoritative overnight plan. It survives context compaction. If resumed, re-read this + RELAUNCH_GATE_CHECKLIST.md + PREFLIGHT_MATRIX.md, then continue from the first unchecked step.**

Operator (blind) is asleep. Explicit authorization: after preflight goes full-green, provision 5 dual-GPU boxes (one question each), launch, monitor SERIOUSLY (forensic, not rubber-stamp), and deliver a §-1.1 line-by-line beat-both report. If any report is deficient / a canary fires / it does not clearly beat — DO NOT declare victory: capture the gap, fix→Codex-gate→re-run that box, keep iterating. Wake the operator to either a genuine beat-both with evidence, or an honest "still short + here's the fix in progress."

## Standing rules (binding)
- Cost is NOT a limit (FAST + BEAT-BOTH locked). Spend on boxes freely; kill a box when its run is done + audited.
- NEVER weaken the frozen faithfulness engine (strict_verify / NLI / four_role-D8 / provenance / span-grounding). U29 was the one authorized tightening.
- NEVER re-enable PG_SWEEP_ANALYST_SYNTHESIS.
- NEVER fake or inflate a metric — §-1.1 line-by-line only; metadata/pattern counts are lethal in clinical context.
- §8.4 resource discipline: ≤4 codex in flight, glance Get-Process, kill orphans; heavy/paid GPU work is VM-only.
- Resume-from-closest-checkpoint if a box crashes mid-run — never fresh-restart over a good checkpoint.

## State entering the night
- **32 of 32 issues committed + Codex-gated** (U1–U29 all, U31, U32 code-committed; U16 folded into the U25 commit; U30 accepted; U5/U8 LIVE-CANARY committed). 0 conflict markers. Frozen engine untouched except U29.
- PREFLIGHT_MATRIX.md written (32 rows). Whole offline suite measuring in background.
- All 10 prior vast boxes DESTROYED — the clean run must PROVISION FRESH boxes.

## STEP 1 — Finish preflight (gate before any paid run)
1. Collect the whole-suite run; read N passed / M failed.
2. The 28 collection errors are PRE-EXISTING benchmark-dir import issues (my changed files parse clean) — document non-blocking.
3. Every real FAILURE: clean-HEAD COPY-check (cp file aside; `git checkout HEAD file`; re-run test; restore) → NEW regression = fix+re-gate; stale/pre-existing (D8-transport/sentinel/docstring/b11_b20/generator-byte-identical) = document with proof it fails on HEAD too.
4. Offline single-sentence smoke (PG_ flags, no paid LLM) clean. Re-grep 0 conflict markers (hard gate).
5. Finalize PREFLIGHT_MATRIX.md + RELAUNCH_GATE_CHECKLIST.md + GitHub #1344 comment.

## STEP 2 — Provision 5 fresh dual-GPU boxes
- vastai: 5 boxes, 2× A100-80GB (or A6000) each. On each: mineru vLLM server on card 1 + verify GPU split + mineru live (ssh probe: `nvidia-smi` 2 cards, mineru health). Deploy patched HEAD (`git pull`). Env all-flags-ON incl PG_SYNTHESIS_FIRE_CANARY=1, PG_MINERU_FIRE_CANARY=1, PG_VERIFIED_COMPOSE_MULTICITED=1, U11 recall slate, U31 300k cap.
- Record box→question→pid→outdir in state.

## STEP 3 — Launch 5 questions, 1 per box, FRESH
- drb_72 workforce · drb_75 metal-ions/CVD · drb_76 gut-microbiota/CRC · drb_78 parkinsons/DBS · drb_90 ADAS-liability.

## STEP 4 — SERIOUS forensic 5-min monitor per box (read intermediate output, not rubber-stamp)
- mineru real GPU-VLM-extracted-N-chars count > 0 + CUBLAS-clear.
- breadth funnel: fetched → tiered → kept → CITED (report the CITED count each tick).
- tier T1/T2 mix; consolidation baskets > 0 multi-origin; verify drop-rate.
- composition SYNTHESIZED prose (multi-cite), NOT a span-dump — read sentences, claim-vs-cited-span §-1.1.
- chrome-clean; status=success; U5/U8 canaries did NOT fire-abort (if a canary fires, that run is deficient — capture why).
- watch hang/OOM/429/stall; resume-from-checkpoint on crash.

## STEP 5 — §-1.1 line-by-line audit per rendered report.md
- Per claim → cited span: VERIFIED / PARTIAL / UNSUPPORTED / FABRICATED (with the span quote).
- Breadth cited-source count; synthesized multi-cite sentence count; chrome/truncation clean.
- Score vs DeepTRACE (citation faithfulness — unsupported/citation-accuracy/one-sided) + DeepResearch-Bench-II (coverage recall/analysis/presentation).

## STEP 6 — Honest verdict
- All 5 clean + broad + faithful AND beat competitor baselines → deliver FULL beat-both report (per-question §-1.1 + metrics + the 32-fix summary) + confirm GitHub #1344 synced.
- ANY deficient / canary-fired / not-clearly-beat → NO victory claim: capture gap → issue → fix → Codex-gate → re-run that box → iterate.

Report each box status every ~5 min, plain (box / question / stage / mineru-count / CITED-count / status).
