# Proper DR head-to-head benchmark — Claude+Codex synthesized design (I-safety-002b)

**Status**: Claude code-investigation + Codex independent design (`codex_proper_benchmark_design.txt`) CONVERGED 2026-05-28. Pending operator go + competitor-source decision, then build (Codex reviews the scorer).
**Supersedes**: the banned/rigged `beat_both_scorer.py` + `dimension_scorers.py` (discard as scorer; keep the runner/loader plumbing).

## Both agree (no disagreement)
The existing BEAT-BOTH 7-dimension scorer is §-1.1-INVALID and rigged toward POLARIS (numeric_grounding auto-1.0, auditability auto-1.0, count/pattern/string-match everywhere). DISCARD the scorer; KEEP the plumbing (`run_polaris_against`, `external_loader`, config, output).

## The proper scorer — TWO LANES, applied IDENTICALLY to all 4 systems (POLARIS judged from scratch, NOT its own verifier_pass)

### Lane 1 — claim faithfulness / citation audit (the core)
1. Normalize each system's output → `SystemReportPackage` {report, citation map, fetched source snapshots, fetch status, run metadata}.
2. Atomize EVERY factual assertion into atomic claims. **No sampling** (if report too long, reduce # questions, not # claims).
3. For each claim, find the citation(s) it attaches. **Uncited factual claim = `UNSUPPORTED_BY_CITATION`** even if independently true.
4. **Fetch + snapshot the cited source; score against the actually-fetched text** (not title/snippet/reputation).
5. Per claim/citation: **VERIFIED / PARTIAL / UNSUPPORTED / FABRICATED / UNREACHABLE** + the exact supporting/refuting span quote.
6. Cross-family judges, **blinded system IDs**, majority/adjudication; clinical disagreements escalate to Codex/Claude.

### Lane 2 — reference/rubric coverage (prevents terse-report gaming — Codex's key add)
- Pre-register a **gold rubric per question from INDEPENDENT primary/regulatory sources** (NOT from POLARIS output).
- Score whether each report covers each required answer element AND that covered elements are themselves citation-supported.
- Stops the "short answer with 3 claims gets 100% faithfulness" failure.

### Secondary lane — RACE report quality (comprehensiveness/depth/instruction-following/readability), cross-family judge. NOT the headline.

### BANNED (do NOT reintroduce): FACT's "effective citation count", any count/density/pattern/string-match, sampling, metadata comparison, POLARIS auto-win, using POLARIS's own verifier as ground truth.

## Fairness (Codex)
- Each system scored on ITS OWN report + ITS OWN citations (a DR product stands behind its chosen sources).
- **`UNREACHABLE` ≠ `FABRICATED`**: unreachable = couldn't verify (paywall); fabricated = fetched span refutes/fails the claim. Never silently forgive unreachable.
- POLARIS's bundle (source snapshots) is an auditability advantage ONLY if the cited span is actually in the bundle + legally checkable; else POLARIS also gets `UNREACHABLE`.
- "Faithful to cited source" ≠ "clinically correct" (a weak/cherry-picked source can be cited faithfully) → that's WHY Lane 2 + evidence-hierarchy matter.
- Preserve competitor citation structure: export **HTML/PDF + clicked-source snapshots**, not plain .txt (`.txt` loses citation anchors).

## Wiring (Codex)
- Keep `run_polaris_against` + config iteration; REPLACE `beat_both_scorer.py` with new `src/polaris_graph/benchmark/claim_audit_scorer.py` → produces an **audit LEDGER** (not a scoreboard).
- POLARIS: prefer the `/runs` bundle path (`live_run_smoke.py`) — bundle has `verified_report.json`, `evidence_pool.json`, source snapshots, provenance tokens. Do NOT treat `verifier_pass` as the benchmark verdict.
- Competitors: extend `external_loader` to per-question dirs: `external_outputs/<tool>/Q##/{report.html,report.txt,sources/*.txt,fetch_manifest.json}`.
- `scripts/run_line_by_line_audit.py` = primitive only (its VERIFIED is mechanical lexical, NOT semantic entailment); the proper scorer needs semantic claim/span judgment on top.

## First run (Codex — pilot, NOT a superiority claim)
- **5 in-scope clinical treatment/drug questions**, no refusal bait, all 4 systems (POLARIS + ChatGPT DR + Gemini DR + Perplexity). Pre-registered from `config/benchmark/clinical_n10.json`: metformin safety, statin mortality, FOLFIRINOX prognosis, warfarin INR monitoring, PD-1 inhibitors in older NSCLC.
- Headline metric: **S2/S3 unsupported-or-worse atomic-claim rate** = (PARTIAL+UNSUPPORTED+FABRICATED+UNREACHABLE material claims) / all S2/S3 factual atoms, every numerator row linked to claim/span evidence.
- Report gold-rubric coverage SEPARATELY. A system "passes" a question iff zero S2/S3 fabricated/refuted claims AND meets the pre-registered coverage threshold.
- 5 Qs = pilot.

## What it needs (honest)
- **From operator (the one dependency)**: competitor reports — either (A) DeepResearch Bench published scores (free, mid-2025 models, public Qs) OR (B) you run ChatGPT/Gemini/Perplexity DR on the 5 clinical Qs + export HTML + snapshot sources (current models, our turf, contamination-free; manual, no API).
- **From Claude+Codex (no operator)**: build `claim_audit_scorer.py` + the cross-family judge + author the 5 gold rubrics (from independent primary sources) + run POLARIS's pipeline + score. Real API cost (fetch every cited source + judge every claim), no competitor fees.

## Next
Build `claim_audit_scorer.py` + 5 gold rubrics → Codex reviews the scorer (gate) → run POLARIS on the 5 Qs → score → (competitor side per operator's A/B choice). Do NOT report "BEAT-BOTH"; report the audit ledger + the two lane numbers honestly.
