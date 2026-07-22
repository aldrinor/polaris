# Consolidated Gate Fix Plan (3-LLM audit + Opus consolidation)

All verified. The fail-closed UNKNOWN hazard is real at `quality_eligibility.py:222,224` (would arm once Fix 1 lands), and the topicality floor call site is `run_honest_sweep_r3.py:14369-14371`. I have everything needed. Producing the consolidated plan.

---

# CONSOLIDATED FIX PLAN â Polaris gate-inversion run: RACE 0.3568 â target â¥0.4447 champion

**Auditor: Opus. Branch `gate-inversion` @ `78fe2ca`, worktree `/home/polaris/wt/outline_agent`. Every claim below re-verified against live code + run artifacts. Frozen files confirmed 0-diff vs `main`.**

## VERDICT ON THE THREE PLANS (read first)

**Fable 5 is correct and its three corrections (C1/C2/C3) OVERTURN the findings pack and both other planners on the root cause. I confirmed all three against artifacts:**

- **C2 (KEYSTONE) â CONFIRMED with a smoking gun.** The pinned contract never steered the run. `run_gate_e2e.py:542` writes the real contract to `.../draw{N}/planning_gate_artifact.json` (`04c81bd7e68f`, scope `SCOPE-1`, confidence 0.98, HARD journal/high/en). But `_run_fresh_e2e` (`run_gate_e2e.py:615`) calls `runner(q, out_root)` passing only `out_root`; inside `run_one_query`, `run_dir = out_root / q["domain"] / q["slug"]` (task level, verified line ~8985). `_gate_load_or_compile_artifact` (`run_honest_sweep_r3.py:8833`) looks for the pin at that **task-level** dir, finds none, and **recompiles a degenerate contract**. Proof: the emitted `.../drb_72_ai_labor/eligibility_receipts.json` carries `contract_hash=ad7638434434â¦` and the task-level `planning_gate_artifact.json` is also `ad76â¦` â **NOT** the pinned `04c81â¦`. The recompiled contract dropped `source_quality`/journal/en. This single bug explains the journal leak, all-UNKNOWN `contract_compliance`, and the never-armed quality mask.

- **C1 â CONFIRMED.** All 143 receipts are `stage=topicality_eligibility` (93 pass / 50 fail); **zero quality receipts exist**. The findings pack's claim that `quality_eligibility.py` UNKNOWN-fail-closed drove the 50-source mask is **wrong for this run** â the quality mask never armed (downstream of C2). The 50 masked = pure topicality-cosine failures.

- **C3 â CONFIRMED.** The D8 banner is NOT caused by the `PG_WINNER_FIRING_GATE=0` bypass. The four-role seam requires BOTH `PG_FOUR_ROLE_MODE=1` AND an injected `four_role_transport` (`run_honest_sweep_r3.py:18121`). `run_gate_e2e`'s env slate (`_fresh_e2e_env_slate:317`) sets only 3 gate vars and injects no transport â legacy path â `adjudicated=False` â banner. **The banner returns on every re-run until D8 is wired into this entrypoint**, regardless of the reranker.

**Sol (SOL-FALLBACK) is correct on the cache bug and the banner-is-a-drag diagnosis, but WRONG on two root causes** (attributes the banner to the winner-gate bypass â refuted by C3; attributes the over-mask to a journal-only eligibility heuristic that never ran â refuted by C1). Its Rank 4 "convert Key Findings to prose" is directionally right but I down-rank the aggressive rewrite (faithfulness risk â see Rejected #3).

**Kimi K3 produced no plan** (waited for a completion event that never fired). Nothing to adjudicate.

**The measured drag decomposition all three agree on stands:** Readability â0.150 (banner + no title + fragment bullet + machinery-first), IF â0.091, Comp â0.074, Insight â0.074.

---

## ORDERED FIX PLAN (highest leverage first)

### FIX 1 â Scoring-cache purge (measurement integrity) â **do FIRST, zero risk** â Effort S
- **File:fn:line:** `scripts/score_report_race.py:main`, insert immediately after the raw write (after line ~68, before `cmd = [...]`):
  ```python
  cleaned = DRB / "data/test_data/cleaned_data" / f"{args.model_name}.jsonl"
  if cleaned.exists():
      cleaned.unlink()
      print(f"[race] purged stale cleaned cache {cleaned.name} (forces re-clean)")
  ```
- **Plus (Fable 2b) a scored-artifact assertion** after the harness `subprocess.run` (~:89): read the cleaned file, assert exactly one record with `id == task["id"]` and `len(article) >= 0.5 * len(report_text)`; on failure print `BLOCKED: cleaned/raw divergence` and `return 3`. Also catches the `{"id","error"}` failure-record poisoning vector (`clean_article.py` leaves it; `_load_processed_ids` counts it as processed).
- **Why:** VERIFIED â `deepresearch_bench_race.py:250` scores `cleaned_data/{model}.jsonl`; `--force` at `:360` only bypasses the eval-results cache, never the clean cache; `clean_article.py:369` dedups by task-id (`to_process = [i for i in all_items if i.get('id') not in processed_ids]`) so an aborted 1090-char stub under id 72 permanently shadows the real report. The wrapper writes exactly one raw record â purging the whole per-model cleaned file is exact.
- **Faithfulness:** eval tooling only; zero pipeline contact.
- **RACE impact:** none on the true score; permanently kills the 0.0384-class false reading. Precondition for trusting every number below.
- **Reject Sol's belt-and-suspenders** of threading `force` into `clean_article.py:367` â it edits the vendored benchmark, is unnecessary once the unlink lands, and risks drift from upstream. Keep the fix in our wrapper only.

### FIX 2 â Artifact hand-off: make the pinned contract the one the sweep runs (THE KEYSTONE) â Effort M
- **File:fn:line (a):** `scripts/run_gate_e2e.py:_run_one_task`, before the `_run_fresh_e2e` call at :615, write the pin to the SWEEP's run dir (the task-level dir `run_one_query` actually reads):
  ```python
  sweep_dir = out_root / q["domain"] / q["slug"]
  sweep_dir.mkdir(parents=True, exist_ok=True)
  (sweep_dir / "planning_gate_artifact.json").write_text(
      json.dumps(artifact.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
  ```
  (Per-draw: overwrite before each draw's `_run_fresh_e2e`, since draws share the sweep dir.)
- **(b) Fail-loud identity guard** after `_run_fresh_e2e` returns (~:617): read back `sweep_dir/planning_gate_artifact.json`, assert its `contract_sha256` equals `d["stages"]["gate"]["contract_sha256"]`; on mismatch set `d["error"]` so the run is never scored silently.
- **(c)** `run_honest_sweep_r3.py:_gate_load_or_compile_artifact:8846` â when the compile branch fires, `log` at WARNING with `RECOMPILED AT SEAM (pinned artifact absent)` and stamp `manifest["gate_contract_recompiled_at_seam"]=True`. A silently-swapped contract is exactly the class of bug that hid this for a full day.
- **Why:** VERIFIED â the pin was written to `draw1/` (`04c81â¦`) but the seam read the task-level dir and recompiled `ad76â¦`; receipts prove `ad76â¦` steered the run. This fix makes the HARD `peer_reviewed_journal`/`high`/`en` terms reach Phase C, arm the quality mask, and make the S4 audit meaningful (no more all-UNKNOWN).
- **Faithfulness:** pure planning-input wiring, upstream of everything; strict_verify/provenance_generator untouched (0-diff).
- **RACE impact:** prerequisite for every IF gain. **HARD SEQUENCING CONSTRAINT: do NOT ship Fix 2 without Fix 5** â arming the quality mask on a 41%-UNKNOWN corpus would over-mask worse than the current run.

### FIX 3 â Remove the D8 banner by making D8 actually run (never by hiding it) â Effort M
- **(a)** `scripts/run_gate_e2e.py:_fresh_e2e_env_slate:317` â add `"PG_FOUR_ROLE_MODE": "1"` on live runs.
- **(b)** `scripts/run_gate_e2e.py:_run_fresh_e2e:366` â inject the D8 transport + input builder mirroring `scripts/dr_benchmark/run_gate_b.py:build_gate_b_transport` (transport-mode default "openrouter", no self-hosted stack). Call `runner(q, out_root, four_role_transport=transport, four_role_input_builder=builder)` â `run_one_query` already accepts these (params at `run_honest_sweep_r3.py:8968`). **(a) and (b) MUST land together** â the fail-closed guard at `:18121` HOLDS the release if the mode is set without a transport.
- **Result:** D8 adjudicates â `release_disclosure.adjudicated=True` â `build_d8_unadjudicated_banner` (`provenance_generator.py:3233`, FROZEN, VERIFIED it returns `""` when `adjudicated is not False`) emits nothing at the prepend site (`run_honest_sweep_r3.py:20783`).
- **(c) Reranker:** run with `PG_WINNER_FIRING_GATE` **unset** (default ON, `:12855`). W5 content-relevance Qwen3-Reranker-0.6B OOM'd on a contended GPU; **GPU is now free (verified 0/81920 MiB)** so it loads trivially. Optionally set `PG_RERANKER_MODEL=qwen3` to also arm the W7 selection reranker (`evidence_selector.py:2672`). **GPU smoke test before any paid run** (load reranker + embedder, assert headroom).
- **Why:** VERIFIED the banner is the first 560 chars of the scored report.md and self-invalidates the findings ("UNVERIFIED-by-D8"). The banner is honest disclosure â the ONLY legitimate removal is making the disclosed condition false. **Do NOT set `PG_REPORT_D8_BANNER=0`; do NOT edit the frozen builder.**
- **Faithfulness:** D8 is the STRONGEST verifier â this fix ADDS verification. Reranker reorder is a pure permutation, verified downstream regardless of order.
- **RACE impact:** +0.06â0.10 Readability, +0.02â0.04 IF (largest single Readability lever).

### FIX 4 â Report shape: ship a literature review, not an audit dump (direct IF fix) â Effort M/L
Four VERIFIED mechanisms behind IF â0.091 / Readability â0.150 (all in NON-frozen render assembly):
1. **No H1, opens on a blockquote** (verified: report.md line 1 = `> **STRONGEST VERIFIERâ¦`; champion opens `# A literature review onâ¦`).
2. **Machinery-first** â Key Findings + audit blocks precede any thematic section.
3. **Instruction visibly violated + unevaluated** (fixed by Fix 2 + Fix 5).
4. **Malformed bullet** â VERIFIED report.md line 9 = `Job Displacement by AI Technologies.** â¦`; the opening `**` fragment was chopped at the render seam.

Changes:
- **(a) Title + claim-free intro.** At the sweep report-assembly seam, emit `# {title}` (title already exists) + a short `## Introduction and Scope` framing paragraph from the contract objective. Faithfulness-safe: asserts no findings, contains no citations, identical class to the champion's shipped intro.
- **(b) Demote machinery below the appendix boundary** (`run_honest_sweep_r3.py:6325`). On-disk order: Title â Intro â thematic `###` â Synthesis â Limitations â Bibliography â `## Appendix (not scored as report claims)` containing methods/disclosure/contradiction ledgers/reliability. **Position only â nothing deleted; disclosure stays in the shipped file AND manifest.** Per CLAUDE.md Â§-1.3 placement/repetition is QUALITY not faithfulness (precedent: render-only dedup at `:20802`).
- **(c) Key-Findings integrity invariant** in `src/polaris_graph/generator/key_findings.py` bullet emission: every bullet must open with `**` and contain a matched closing `**`; a failing bullet is re-emitted from its stored title + carried sentence (both exist verbatim upstream), never shipped chopped. Constrain the render-seam chrome removal to whole-unit granularity inside the Key Findings block.
- **(d)** Shrink the hedge preamble (report.md line 7) to one sentence + appendix pointer (`key_findings.py` preamble ~:1004).
- **Faithfulness:** every moved block is disclosure/audit text; every kept finding sentence is byte-identical strict_verify output; frozen files 0-diff. Bullet re-emission uses only verbatim verified text.
- **RACE impact:** +0.03â0.06 IF, +0.04â0.07 Readability, +0.01â0.03 Comprehensiveness.

### FIX 5 â Tame the (about-to-arm) mask + fix the journal leak, WITHOUT touching strict_verify â Effort M â **ship WITH Fix 2**
Once Fix 2 lands, `build_quality_eligibility` arms against a 41%-UNKNOWN corpus; the hard branch would mask FAIL+UNKNOWN â 48% â worse than today. Pair these:
- **(a) Resolve UNKNOWN, don't mask it:** `PG_CREDIBILITY_LLM_TIERING=1` (it was OFF; zero tiering lines in log). Collapses the 41% UNKNOWN to real tiers before the mask reads them. Metadata enrichment, faithfulness-neutral.
- **(b) Deterministic second-chance before UNKNOWN** in `quality_eligibility.py:score_source_quality`, insert before the UNKNOWN fail-closed at :222/:224: if the row has a DOI or classifies as a journal article (`document_type_classifier.is_peer_reviewed_journal_article` â the same predicate the scope classifier already trusts), return PASS. **Evidence-POSITIVE only** â the FAIL verdicts (retracted, predatory, `is_peer_reviewed=False` at :209, low tier) are UNTOUCHED. Extend `_PREDATORY_HOST_PATTERNS` with `abacademies.org` (bib [9], predatory-adjacent, shipped).
- **(c) Two-tier topicality (this run's ACTUAL over-mask).** VERIFIED: 50 exclusions, **38 in the 0.15â0.30 band** (on-topic-adjacent), only 12 truly off-topic (<0.15). At the call site `run_honest_sweep_r3.py:14369-14371`: introduce `PG_TOPICALITY_HARD_FLOOR` (default 0.15) for HARD quarantine; pass the 0.15â0.30 band through the existing SOFT-demote path (`quality_eligibility.py:350`). Confirmed junk (<0.15) still hard-quarantines.
- **(d) Journal-only = visible preference + measured compliance, NOT a starvation mask.** With Fix 2, `allowed_source_kinds=['peer_reviewed_journal']` (hard) becomes an `op=prefer` facet (`retrieval_projection.py:314`). Enforcement, in safety order: (1) selection ordering â journal/DOI rows first in the selected menu (bibliography share rises, nothing dropped); (2) S4 audit now scores real journal share instead of UNKNOWN; (3) HARD journal-only (`PG_SOURCE_RESTRICTION_JOURNAL_ONLY=1`) ONLY behind a corpus-adequacy pre-check (â¥~25 T1/T2/DOI rows post-tiering), else disclose "insufficient journal corpus; prioritized journals" rather than starve. **Empirical justification: the champion scored IF 0.4587 while itself citing majority non-journal** â a hard mask on this 9-journal corpus would crater Comprehensiveness.
- **Faithfulness:** all changes shape the citable MENU upstream of the frozen verifier; no FAIL row re-admitted; UNKNOWN handling adds evidence, not leniency; provenance_generator/strict_verify 0-diff.
- **RACE impact:** +0.02â0.04 Comp/Insight (menu 93 â ~120â135 of 143), +0.01â0.03 IF (visible journal compliance + audit SATISFIED rows).

---

## DISAGREEMENTS RESOLVED

| # | Disagreement | Verdict + evidence |
|---|---|---|
| 1 | **Root cause of the over-mask.** Findings pack + Sol: `quality_eligibility.py` UNKNOWN fail-closed / journal-only heuristic. Fable: quality mask never armed; over-mask is pure topicality. | **Fable.** Receipts are 143/143 `topicality_eligibility`, zero quality receipts. Sol/pack are wrong for THIS run. The fail-closed hazard is REAL but only becomes live AFTER Fix 2 â hence Fix 5 pre-empts it. |
| 2 | **Root cause of the banner.** Sol: the `PG_WINNER_FIRING_GATE=0` bypass caused it. Fable: entrypoint-unconditional (no four-role transport). | **Fable.** Four-role seam needs `PG_FOUR_ROLE_MODE=1` + injected transport (`:18121`); `run_gate_e2e` sets neither. Reviving the reranker alone does NOT remove the banner. Fix 3 wires D8 in. |
| 3 | **Keystone bug existence.** Sol/pack: none identified â treated the recompiled contract's outputs as the gate's real behavior. Fable: artifact hand-off broken. | **Fable.** Task-level `planning_gate_artifact.json` = `ad76â¦` (recompiled), draw1 pin = `04c81â¦`; receipts ran under `ad76â¦`. Confirmed. |
| 4 | **Journal-only policy.** Sol: abandon journal-only entirely, make source-type a soft signal. Fable: enforce as preference + measured compliance, hard-only behind corpus-adequacy. | **Fable, mostly.** Sol is right that a hard journal-only mask hurts (champion proves it), but "abandon entirely" throws away the gate's whole purpose. Fable's graduated stack (prefer â audit â hard-behind-adequacy) is the correct middle. |

---

## REJECTED / FAITHFULNESS HAZARDS

1. **`PG_REPORT_D8_BANNER=0` or editing `build_d8_unadjudicated_banner` (any planner tempted).** REJECT. The banner is honest disclosure; suppressing it while `adjudicated=False` ships a report that hides its own unverified status. The only legitimate removal is making D8 actually adjudicate (Fix 3). provenance_generator.py is frozen (verified 0-diff).
2. **Sol's "add an authoritative-institution allowlist tier" that lets OECD/Fed/Morgan Stanley PASS eligibility.** REJECT as written â it risks re-admitting sources the contract's HARD journal scope excludes, and blurs the mask. Correct form is Fix 5d: keep them as a visible non-journal preference tier + disclose share; never a hard PASS that overrides a HARD contract term.
3. **Sol Rank 4: rewrite the "Key Findings verbatim-span list" into "flowing prose that integrates cited spans into sentences."** DOWN-RANK / CONSTRAIN. The Key Findings bullets are byte-identical strict_verify output; re-composing them into new sentences risks re-ordering/merging spans in ways that break span-grounding provenance. Fix 4's move-and-title approach captures most of the IF/Readability gain WITHOUT touching verified sentence text. Prose integration, if attempted later, must preserve each span verbatim and re-run strict_verify â treat as a separate, gated experiment, not part of this run.
4. **Sol's "loosen the chrome-gate basket-drop threshold 35%â15%" and threading `force` into vendored `clean_article.py`.** REJECT both here â the basket-drop rate is downstream of strict_verify's 65.6% drop and is a separate freeze-respecting investigation (see ceiling note); the clean_article edit is unnecessary given Fix 1's unlink.

---

## CLEAN RE-RUN PROTOCOL

**Gate 0 â offline, no spend:** unit tests for (a) artifact hand-off (run_gate_e2e writes â sweep loads SAME sha; guard trips on mismatch), (b) quality plan emits receipts on a fixture with the draw1 artifact, (c) topicality two-tier split, (d) banner absent when `adjudicated=True`, (e) Key-Findings `**` invariant, (f) render section order. Re-run existing planning/outline suites untouched.

**Gate 1 â GPU smoke, no spend:**
```bash
nvidia-smi --query-gpu=memory.used --format=csv   # expect 0 MiB
# load Qwen3-Reranker-0.6B (+4B if W7 armed) alongside the embedder,
# assert a forward pass on 8 pairs + log nvidia-smi headroom. ABORT the paid run if this fails.
```

**Gate 2 â live single draw:**
```bash
cd /home/polaris/wt/outline_agent
PG_GATE=1 PG_GATE_MODE=autonomous PG_USE_RESEARCH_PLANNER=1 \
PG_QGEN_FS_RESEARCHER=1 \
PG_FOUR_ROLE_MODE=1 \
PG_TOPICALITY_ELIGIBILITY=1 PG_TOPICALITY_HARD_FLOOR=0.15 \
PG_CREDIBILITY_LLM_TIERING=1 \
python3 scripts/run_gate_e2e.py --task-id 72 --draws 1 --score-race \
  --model-name polaris_gate_v2_task72
# PG_WINNER_FIRING_GATE unset (ON); PG_REPORT_D8_BANNER unset (ON, should now emit nothing);
# fresh --model-name + Fix 1 purge guarantee no cached shadow.
```

**Score-verification checklist (BEFORE trusting the number):**
- wrapper `article_chars` â cleaned chars (Fix 1b assertion) and > 20000
- `eligibility_receipts.json` contains BOTH `quality_eligibility` AND `topicality_eligibility` stages, and `contract_hash` == the pinned `04c81â¦` (NOT `ad76â¦`)
- `contract_compliance.json` has â¥1 non-UNKNOWN scope term
- report.md line 1 starts `# ` (H1); no `STRONGEST VERIFIER` substring anywhere in report.md
- bibliography â¥ 28 entries, journal share > 60%

**Then 3 draws** (S5 protocol), score each; judge variance documented Â±0.016.

---

## PREDICTED RACE vs CHAMPION 0.4447

From the re-measured **0.3568** base:
- Fix 3 (banner gone) + Fix 4 (title/intro/structure/bullet): Readability 0.281 â ~0.40â0.43, IF 0.368 â ~0.43â0.46
- Fix 2 + Fix 5 (real contract + un-starved menu): Comp 0.383 â ~0.43â0.46, Insight 0.355 â ~0.40â0.43

**Predicted Overall 0.42â0.46 â parity with champion within judge variance, with upside above it** if the bibliography grows toward the champion's 37 refs and the D8-adjudicated depth layer produces cross-source findings (this run had cross=0).

**Honest answer on the gate's core goal (Instruction-Following):** After the fixes IF should reach **~0.43â0.46, i.e., at or just below champion's 0.4587**. **I do NOT predict the gate beats champion on IF with confidence.** The bulk of the projected IF recovery is removing self-inflicted damage (banner, no-title, fragment bullet, visibly-violated instruction) â that gets the gate back to parity, not past it. The gate's *net-positive* contribution to IF (visible journal compliance + SATISFIED audit rows from Fix 5d) is real but small (+0.01â0.03) and unproven until measured. **Verdict: the gate's benefit over champion remains UNPROVEN. This run's job is to prove the gate is not a regression; beating champion on IF is a hypothesis for a later run, not a claim this plan can guarantee.**

**Residual ceiling (deliberately out of scope, freeze-respecting):** the 65.6% strict_verify drop rate (84/128) and ~21 chrome-basket drops bound Comprehensiveness. The champion succeeded at a ~41% drop rate with clean packaging â so packaging (Fixes 3/4) is the right first battle; the drop rate is a separate, later investigation that must NOT touch the verifier.

**Do-not-do list (faithfulness-frozen):** no edits to `provenance_generator.py` (incl. banner builder :3212 and evidence-support block :3124); no strict_verify/NLI/D8 threshold changes; no `PG_REPORT_D8_BANNER=0`; no re-admitting FAIL-verdict sources; no deleting disclosure content (move-only); no re-composing verified Key-Findings sentences.

**Key artifact paths (all under `/home/polaris/wt/outline_agent`):** `scripts/score_report_race.py`, `scripts/run_gate_e2e.py`, `scripts/run_honest_sweep_r3.py`, `src/polaris_graph/retrieval/quality_eligibility.py`, `src/polaris_graph/planning/retrieval_projection.py`, `src/polaris_graph/generator/key_findings.py`, and the evidence `outputs/gate_e2e_final2/workforce/drb_72_ai_labor/{eligibility_receipts.json,planning_gate_artifact.json,draw1/planning_gate_artifact.json,report.md}`.",
    "fable": "All verification complete. Here is the full fix plan.

---

# FIX PLAN â gate-inversion run: from RACE 0.3568 back above the 0.4447 champion
**Auditor:** Fable ",
    "sol": "I have enough grounding to confirm every core claim against the real code. Codex burned its full 560s budget on file inspection without producing a verdict, so ",
    "kimi": "I'll wait for the completion event."
  },
  "workflowProgress": [
    {
      "type": "workflow_phase",
      "index": 1,
      "title": "Evidence"
    },
    {
      "type": "workflow_phase",
      "index": 2,
      "title": "FixPlans"
    },
    {
      "type": "workflow_phase",
      "index": 3,
      "title": "Consolidate"
    },
    {
      "type": "workflow_agent",
      "index": 1,
      "label": "evidence",
      "phaseIndex": 1,
      "phaseTitle": "Evidence",
      "agentId": "aa9bcc38b1344f5d6",
      "model": "claude-opus-4-8",
      "state": "done",
      "startedAt": 1784261703317,
      "queuedAt": 1784261703316,
      "attempt": 1,
      "lastToolName": "Write",
      "lastToolSummary": "/tmp/claude-1000/-home-polaris-polaris-project/21e87760-843â¦",
      "promptPreview": "Assemble a findings + current-state pack for a 3-LLM fix-planning review. Write it to /tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/reviews/fixplan_findings.md. You are in /home/polaris/wt/outline_agent (branch gate-inversion). Read-only.
Include: (1) the confirmed findings verbatim (below). (2) From the real gated report /home/polaris/wt/outline_agâ¦",
      "lastProgressAt": 1784261984023,
      "tokens": 72087,
      "toolCalls": 31,
      "durationMs": 280706,
      "resultPreview": "Pack assembled and written to `/tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/reviews/fixplan_findings.md`.

Contents delivered:

**(1) Confirmed findings** â pasted verbatim, plus the verbatim JOB spec (a-e).

**(2) Real gated report** (`outputs/gate_e2e_final2/workforce/drb_72_ai_labor/draw1/report.md`, 4653 words confirmed):
- D8 banner verbatim (â¦"
    },
    {
      "type": "workflow_agent",
      "index": 2,
      "label": "FABLE-5",
      "phaseIndex": 2,
      "phaseTitle": "FixPlans",
      "agentId": "a316accf128dc8601",
      "model": "claude-fable-5",
      "state": "done",
      "startedAt": 1784261984055,
      "queuedAt": 1784261984053,
      "attempt": 1,
      "lastToolName": "Bash",
      "lastToolSummary": "cd /home/polaris/wt/outline_agent && grep -n "def _fs_reseaâ¦",
      "promptPreview": "You are Fable 5, ONE of THREE independent fix-planners (others: Codex Sol, Kimi K3 â do NOT coordinate). Read the findings pack /tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/reviews/fixplan_findings.md + the prior forensic evidence /tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/reviews/broken_vs_champiâ¦",
      "lastProgressAt": 1784262961662,
      "tokens": 171813,
      "toolCalls": 67,
      "durationMs": 977606,
      "resultPreview": "All verification complete. Here is the full fix plan.

---

# FIX PLAN â gate-inversion run: from RACE 0.3568 back above the 0.4447 champion
**Auditor:** Fable 5 (independent; no coordination). Branch `gate-inversion` @ `78fe2ca`, worktree `/home/polaris/wt/outline_agent`. All line numbers verified against the working tree and the actual run artifacts (`outputs/gate_e2e_final2/â¦`).

## 0. THREE COâ¦"
    },
    {
      "type": "workflow_agent",
      "index": 3,
      "label": "CODEX-SOL",
      "phaseIndex": 2,
      "phaseTitle": "FixPlans",
      "agentId": "a4341c2e25aef6c00",
      "model": "claude-opus-4-8",
      "state": "done",
      "startedAt": 1784261984058,
      "queuedAt": 1784261984054,
      "attempt": 1,
      "lastToolName": "Bash",
      "lastToolSummary": "cd /home/polaris/wt/outline_agent && grep -rln "eligibilityâ¦",
      "promptPreview": "You are orchestrating SOL (GPT-5.6 via codex). Write the prompt to /tmp/sol_fixplan.txt: "You are Sol (GPT-5.6), ONE of THREE independent fix-planners (others: Fable, Kimi â do not coordinate). Read /tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/reviews/fixplan_findings.md and /tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99eâ¦",
      "lastProgressAt": 1784262718604,
      "tokens": 29824,
      "toolCalls": 12,
      "durationMs": 734546,
      "resultPreview": "I have enough grounding to confirm every core claim against the real code. Codex burned its full 560s budget on file inspection without producing a verdict, so I'll deliver the SOL-FALLBACK plan grounded in what I verified.

---

CODEX BLOCKED: Sol (GPT-5.6) ran but timed out at 560s (exit code 124) having only inspected CLAUDE.md and the campaign state files â it never reached the fix plan. No veâ¦"
    },
    {
      "type": "workflow_agent",
      "index": 4,
      "label": "KIMI-K3",
      "phaseIndex": 2,
      "phaseTitle": "FixPlans",
      "agentId": "a7e1dfe1d9e7c6684",
      "model": "claude-opus-4-8",
      "state": "done",
      "startedAt": 1784261984059,
      "queuedAt": 1784261984054,
      "attempt": 1,
      "lastToolName": "Monitor",
      "lastToolSummary": "until [ -f /tmp/kimi_fixplan.err ] && grep -q "EXIT=" /tmp/â¦",
      "promptPreview": "You are orchestrating KIMI K3 (via OpenRouter). Source env: cd /home/polaris/wt/outline_agent && set -a && . ./.env && set +a.
Write /tmp/kimi_fixplan.py that: reads /tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/reviews/fixplan_findings.md, the report /home/polaris/wt/outline_agent/outputs/gate_e2e_final2/workforce/drb_72_ai_labor/draw1/report.md (fâ¦",
      "lastProgressAt": 1784262686994,
      "tokens": 20079,
      "toolCalls": 6,
      "durationMs": 702935,
      "resultPreview": "I'll wait for the completion event."
    },
    {
      "type": "workflow_agent",
      "index": 5,
      "label": "opus-consolidate",
      "phaseIndex": 3,
      "phaseTitle": "Consolidate",
      "agentId": "a2243b00e64aef3c1",
      "model": "claude-opus-4-8",
      "state": "done",
      "startedAt": 1784262961667,
      "queuedAt": 1784262961664,
      "attempt": 1,
      "lastToolName": "Bash",
      "lastToolSummary": "cd /home/polaris/wt/outline_agent; echo "===quality_eligibiâ¦",
      "promptPreview": "You are Opus. Review THREE independent fix plans LINE BY LINE and consolidate them into ONE careful, prioritized fix plan for the operator.
CONFIRMED FINDINGS (from a prior 3-LLM forensic + a re-measurement):
- The RACE=0.0384 was a SCORING-CACHE ARTIFACT, NOT a broken pipeline. deepresearch_bench_race.py:250 scores the CLEANED file; utils/clean_article.py:367-371 dedups by task ID (not content), â¦",
      "lastProgressAt": 1784263242916,
      "tokens": 49103,
      "toolCalls": 23,
      "durationMs": 281248,
      "resultPreview": "All verified. The fail-closed UNKNOWN hazard is real at `quality_eligibility.py:222,224` (would arm once Fix 1 lands), and the topicality floor call site is `run_honest_sweep_r3.py:14369-14371`. I have everything needed. Producing the consolidated plan.

---

# CONSOLIDATED FIX PLAN â Polaris gate-inversion run: RACE 0.3568 â target â¥0.4447 champion

**Auditor: Opus. Branch `gate-inversion` @ `78fâ¦"
    }
  ],
  "totalTokens": 342906,
  "totalToolCalls": 139
