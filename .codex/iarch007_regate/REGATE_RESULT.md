# I-arch-007 Re-gate — Consolidated Result

**Generated:** 2026-06-15
**Inputs:** 4 Codex static re-reviews (iter2 fixes) — RELEASE, GEN, FETCH, SWEEP.
**Source-verified:** every NEW/still-open P0 line below was read on disk and matches the verdict; verdicts parsed from the LAST `verdict:` line of each `*_verdict.txt`.

---

## OVERALL VERDICT: REQUEST_CHANGES

Rule: APPROVE iff every unit APPROVE **and** faithfulness_ok **and** wiring_complete. Result:

| Unit | Verdict | faithfulness_ok | wiring_complete |
|---|---|---|---|
| RELEASE | REQUEST_CHANGES | no | no |
| GEN | REQUEST_CHANGES | yes | no |
| FETCH | REQUEST_CHANGES | no | no |
| SWEEP | REQUEST_CHANGES | no | no |

4 of 4 units = REQUEST_CHANGES. 3 of 4 fail faithfulness. 4 of 4 fail wiring. → **REQUEST_CHANGES.**

---

## REMAINING P0s (fix these first — one line each)

1. **RELEASE — `scripts/run_honest_sweep_r3.py:10980`** (prior P0 #3, still open).
   `adjudicated=bool(_rd.get("adjudicated", True)) if _rd else True` defaults missing/malformed adjudication proof to **True**, so a release-asserting manifest with no `release_disclosure` (or a disclosure missing the `adjudicated` key) passes `assert_release_invariant` as adjudicated-by-default. Contradicts the adjacent fail-closed comment (10968-10970). Reachable for B18/B19 `released_with_disclosed_gaps`.
   **Fix:** default that field to `False` (un-proven) — must be explicitly proven.

2. **SWEEP — `scripts/iarch007_release_invariant_check.py:208`** (NEW).
   Clause (4) only flags a `release_allowed=true` contradiction when `status.startswith("abort")`; clause (5) only demands D8/seam proof for `_STRICT_RELEASE_STATUSES`. So `status="partial_saturation" + release_allowed=true + final_verdicts={}` passes with **no D8 adjudication and no proven seam** — silent un-judged release for the whole `partial_*` family.
   **Fix:** require D8 or proven-seam disposition for `partial_*`/`unknown` release-allowed statuses too, not just strict/disclosed.

3. **FETCH — `src/polaris_graph/retrieval/contradiction_detector.py:1486`** (prior A17, still open).
   Still groups only by `(subject, predicate, unit, dose)`; record creation at 1537/1593/1603 has **no same-`evidence_id`/`source_url` guard**, so two numeric claims from the SAME source unit can be emitted as a cross-source contradiction. The iter2 commensurability guard is orthogonal and does NOT address this.
   **Fix:** skip / suppress pairs sharing the same `evidence_id` or `source_url` when forming contradiction records.

4. **GEN — `src/polaris_graph/generator/fact_dedup.py:658 / :666`** (NEW, exposed by making anti-restatement default-ON at `multi_section_generator.py:6648`).
   Rewrite fallbacks `return {... : None ...}` (DROP-redundants) on malformed JSON / shape-mismatch / null-empty rewrite, deleting redundant **cited** sentences and losing corroborating sources — violates §-1.3 CONSOLIDATE-keep-all.
   **Fix:** on rewrite failure, KEEP the redundant cited sentences (consolidate as multi-citation) instead of dropping them.

---

## REMAINING P1s

1. **SWEEP — `tests/polaris_graph/test_iarch007_regression.py:220` (and :257).**
   A11 still has symbol/source-presence proxy assertions — not fully behavioral if the bar is "call real functions" for every regression assertion.

(RELEASE, GEN, FETCH report zero P1s.)

---

## PRIOR P0s — CLOSED vs STILL OPEN

**CLOSED (7):**
- RELEASE #1 — seam `fabrication_screen_ran=None` now WITHHOLDS the body (`release_policy._compute_seam_outcome`, `screen_clean = fabrication_screen_ran is True and not …found_fabrication`). Unknown/False cannot ship.
- RELEASE #2 — runtime seam `ReleaseOutcome` no longer defaults `adjudicated=True`; `build_seam_release_outcome()` constructs `adjudicated=False` and serializes it.
- RELEASE — iter1 "ReleaseInvariantError / assert_release_invariant symbols MISSING" P0: now EXIST on disk and the invariant is called fail-closed on the manifest write path (violations → four_role_held).
- GEN A20 — coherent default-ON across credibility_pass + claim_graph + finding_dedup; no legacy source-DROP on unset env.
- GEN A6 — semantic_v2 relevance is now a WEIGHT / down-weight-keep, not a hard floor filter (even in semantic mode).
- GEN A4 — recovered atoms route THROUGH M-41c + credibility-disclosure, not appended after.
- SWEEP A12 — `--resume` loads both checkpoints as data only (logs/surfaces); gates still rerun, never replays a verdict.
- SWEEP A19 — `--live` shells out to the real sweep and checks produced manifests (not a success-stub).

**STILL OPEN (4) — see P0 list above:**
- RELEASE prior P0 #3 (invariant fail-open default `adjudicated=True`) — `run_honest_sweep_r3.py:10980`.
- FETCH prior A17 (no same-source contradiction guard) — `contradiction_detector.py:1486`.
- SWEEP NEW hole (partial-status un-judged release) — `iarch007_release_invariant_check.py:208`.
- GEN NEW (fact_dedup rewrite-fallback drops cited sentences) — `fact_dedup.py:658/666`.

**PARTIALLY CLOSED (1):**
- SWEEP A11 (skip removal) — drb90 fixture conditional skip gone, but not all regression assertions behavioral (→ the P1 above).

---

## TRANSPARENCY FLAG (does NOT change the verdict — operator judgment)

**SWEEP A21b false-convergence pattern.** The iter1 A21b P0 was the **PRE-report** timeout case (no `report.md` yet → findings-less stub). Codex iter2 marked A21b "closed" but only addressed the **report.md-EXISTS** path (non-empty report preserved) — a different scenario than the one originally flagged, and says nothing about the pre-report path. Codex did NOT re-flag A21b for iter2, so it is not counted as a P0 here — but the original open scenario was not demonstrated closed. Recommend an explicit pre-report-timeout check before trusting A21b as resolved.

---

## PROCESS NOTES (per CLAUDE.md monitoring/hygiene)

- FETCH: first Codex run hit `timeout 540` at xhigh, exited rc=127 with empty verdict; the untracked `FETCH.diff` was accidentally overwritten during regen and reconstructed deterministically via `git diff 37e2b406^ 37e2b406` (all FETCH iter2 fixes A1/A5/A17/A8 committed in 37e2b406, I-arch-007 WIP checkpoint) back to its exact 1172 lines; rerun completed clean (rc=0).
- All four runs: OAuth via `env -u OPENAI_API_KEY`, static review only, verdict parsed from the written file's last `verdict:` line (never an agent self-report).
- SWEEP: orphaned codex PID 20868 killed per §8.4 resource discipline.
- No strict_verify / NLI / 4-role threshold relaxation found in ANY of the four units. A2 token clamp and A21a per-LLM-call watchdog/deadline confirmed present (RELEASE).
