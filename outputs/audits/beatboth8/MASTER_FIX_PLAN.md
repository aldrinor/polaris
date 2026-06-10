# beatboth8 — MASTER FIX PLAN ("kill the cruft" campaign) — 2026-06-10

**Operator directive:** before the NEXT run, fix ALL the bugs via a serious Claude Codex Workflow + a serious BEHAVIORAL smoke that PROVES each "stupid shit" is gone on real data. No more fix→re-run→discover loops.

**Evidence base:** beatboth8 re-run (3/5 done, drb_78/90 finishing) + DRB76_FORENSIC.md (Claude+Codex §-1.1, cross-reviewed) + the funnel diagnosis. ZERO fabrication anywhere — every bug below is over-zealous/buggy gating or cruft, NOT a fabrication.

---

## A. THE COMPLETE BUG LIST (root-caused, file:line, this session)

### Tier 1 — COMPLETENESS-blocking (why EVERY question holds <0.70 coverage)
| # | Bug | Evidence | Root | Fix (faithfulness-safe) |
|---|---|---|---|---|
| B1 | **Evidence-selection cap** — ~500 fetched → only **46 selected** into the pool the generator sees (~90% thrown away pre-generation) | drb_76 manifest `evidence_selection.evidence_selected=46`; fetched 500, success 737/740 | selector/reranker keeps a small fixed-N, does not scale with corpus (#1078) | scale selection with corpus size; feed BEST-ranked evidence, not first-N; raise the pool cap |
| B2 | **False held-gate** — D8 must-cover flags an entity "missing" when its content verified+shipped under a different section/citation | drb_76: `d8_s0_must_cover_missing:contraindications` held, BUT idx13/14 (same evidence_id `probiotic_immunocompromised_contraindication`) VERIFIED + shipped under Safety[3] | must-cover check keys on the dedicated slot binding, ignores the same entity's surviving verified claims elsewhere (#1192) | count an S0 entity SATISFIED if its evidence_id has any surviving VERIFIED claim in the report; bind the slot to that content; STOP emitting a false gap |
| B3 | **Over-drop at strict_verify + 4-role** — coverage 0.33–0.43 vs 0.70 bar → everything holds | drb_72=0.429, drb_76=0.40, drb_75=0.333; drb_76 generator dropped 41/81 sentences | strict_verify + the off-target span problem (B4) reject verifiable claims; selection (B1) starves the generator | recover REAL claims: fix span-resolution (B4), re-anchor improvements, feed more evidence (B1). DO NOT lower the 0.70 bar |

### Tier 2 — FAITHFULNESS (real, minor, no fabrication)
| # | Bug | Evidence | Fix |
|---|---|---|---|
| B4 | **Citation-span mis-binding / off-target spans** — a citation binds to a NON-supporting span (hedged abstract opener, author-affiliation header, altmetric-badge URL) when a supporting span exists in the SAME source | DRB76_FORENSIC idx9 (UNSUPPORTED-as-cited; idx15 from same source supports it); prep flagged idx1→affiliation header, idx10→altmetric URL | re-anchor must re-point the `[#ev]` token to the genuinely-entailing span in the cited row; span extraction must skip boilerplate (affiliation/header/altmetric/nav) |

### Tier 3 — PRESENTATION / cruft ("stupid shits")
| # | Bug | Fix |
|---|---|---|
| B5 | **Curator/human wording** in autonomous output ("curator-actionable gap", `human_gap_tasks.json`, "operator can fix") — no curator exists (#1193) | factual self-contained gap disclosure; relabel internal artifact; no human references |
| B6 | **False "did not survive verification" stub** — the stub lies when the entity DID survive (part of B2) | fix wording; don't emit when content verified |
| B7 | **Key Findings preamble overreach** — claims "verbatim, span-verified" but carries section headers + redaction stubs | fix carry-up logic OR soften the preamble |
| B8 | **Noisy/confusing warnings** (FIX-SCHEMA-5, FIX-QWEN-1, repeated "truncating N→100", crawl4ai EPIPE breaker spam) | downgrade to debug / dedupe / summarize |

---

## B. THE FIX CAMPAIGN (Claude Codex Workflow — Codex the ONLY gate, prove-first)

One GitHub issue per coherent fix unit; each: Claims Ledger (claim→file:line→live/staged) → build → behavioral smoke → Codex diff-gate (5-cap). Order by impact:
1. **B2+B6** (#1192) — the false held-gate + lying stub (biggest single win: unblocks the clinical holds that are FALSE).
2. **B1** (#1078) — selection cap (the dominant completeness lever).
3. **B4** — span-binding / re-anchor (raises coverage + fixes the one real faithfulness defect).
4. **B3** — over-drop recovery (composes with B1+B4; re-measure after).
5. **B5+B7+B8** (#1193 + new) — presentation cruft (low-risk, batch).

NO faithfulness-gate relaxation anywhere. The 0.70 bar STAYS; we raise real coverage to meet it.

---

## C. THE SERIOUS BEHAVIORAL SMOKE (the proof gate — runs BEFORE any re-run)

**Principle (per operator: behavioral, not config-flag):** replay the REAL verification/selection/redaction pipeline on the ALREADY-FETCHED beatboth8 evidence (drb_76/75/72 saved `evidence_pool.json` + report sentences) — offline, fast, cheap — and ASSERT each bug is gone on real data:

| Assert | Proves |
|---|---|
| selection feeds **> 46** sources from the saved 500-source corpus | B1 fixed |
| `probiotic_immunocompromised_contraindication` is marked SATISFIED (its verified idx13/14 content recognized) → **no `d8_s0_must_cover_missing:contraindications` hold** | B2 fixed |
| drb_76 four-role coverage **rises above 0.40** on the same saved evidence | B3 progress |
| idx9's citation re-points to a span that genuinely entails "strongly linked" (or the claim softens) | B4 fixed |
| rendered report contains **ZERO** "curator"/"operator can"/human-task strings | B5/B6 fixed |
| **ZERO fabrication** — every shipped numeric/claim still verbatim in its cited span (the §-1.1 invariant) | safety preserved |

The smoke is a deterministic replay where possible (selection, strict_verify against saved spans, must-cover binding, redaction render); the 4-role re-eval can replay against saved `four_role_role_calls.jsonl` or a cheap slice. **GREEN smoke + Codex APPROVE on every fix = the ONLY gate to the next paid run.**

---

## D. SEQUENCE
1. Let the current run finish (drb_78/90) → run the full 5-Q §-1.1 audit (beatboth8-final) → finalize this bug list (catch anything the last 2 questions add).
2. Build the fix campaign (B1–B8), Codex-gated, each behavioral-smoke-green.
3. Run the full behavioral smoke harness on saved beatboth8 evidence → ALL asserts green + Codex APPROVE.
4. ONLY THEN re-run the 5 questions (the next paid run), expecting releases (or honest holds that are genuinely missing, not false).
