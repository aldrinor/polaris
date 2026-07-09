# Consolidated fix review — drb_72 wave-2 (2026-07-08)

## CAMPAIGN STATUS + FLOW (updated 2026-07-08, operator-locked)

**Honest verdict on the rendered drb_72 wave-2 report:** it RENDERED COMPLETE (all 4 aspect sections,
summary table, 6 seminal papers, ~260 sources) but is NOT beat-both / NOT usable as-is. The §-1.1
line-by-line audit (10 agents, 118 findings) rated **7 of 9 sections SEVERE**; only Key Findings is clean.
Critic: "one half is genuinely good, the other half is a chrome dump — same evidence pool, two composition
paths." ZERO fabrication (faithfulness engine held; weak spots are honest gaps/chrome, never faked prose).
The clean Key-Findings half PROVES the pipeline can write SOTA prose from this pool → the fixes below are
the report-killers, not a lack of evidence. Do NOT score this run.

**Operating model — "Claude Codex Fable Workflow" (operator-locked 2026-07-08):**
- **Fable = brain:** deep root-cause investigation + hands Opus a precise build spec + CONSOLIDATES the
  multi-fix plan. (Opus mis-finds root causes — months lost — so Opus never decides the diagnosis or plan.)
- **Opus = hands:** builds/tests/runs exactly Fable's spec.
- **Fable + Codex = gate:** on the diffs and on the VM e2e test results.

**14 solutions total:**
- DONE + committed (e6b6d31f, dual-gate APPROVE): NLI-consolidation pre-bucket (repetition-a), #1373 query-gen status-leak.
- 6 OLD (Fable root-caused): B1 chrome, B2 mineru, B3 resilience, B4 720s-wall, B5 productivity, B6 D8-judge.
- 6 NEW (Fable investigating): N1 junk-dump render blocks, N2 repetition-b (fragment+prose), N3 broken
  summary table, N4 internal-machinery leak, N5 garbled sentences, N6 off-topic surfacing.
- (B7 source-date-scope: DEFERRED per operator — handle year scope in the SEARCH phase, not composition.)

**Flow:** (1) Fable finishes all investigations → specs. (2) Fable consolidates ONE working plan (grouped
by file, overlaps resolved). (3) Opus builds all 12 per spec. (4) Codex+Fable gate on diffs + VM results.
(5) Relaunch from the corpus checkpoint with all fixes wired.

---


Systematic review of the whole landscape from the live line-by-line read.
Every item: STATUS · SYMPTOM · ROOT CAUSE · ❌ band-aid to avoid (time-wall / muting) · ✅ true mechanism-fix.

**Discipline (operator-locked):** no stupid time walls, no muting/suppressing symptoms. Every fix
below repairs the mechanism. Where a time-wall or a drop would "fix" the number, it is named as the
band-aid and REJECTED.

---

## PART A — RESOLVED (proven + gated + in the pipeline)

These are IN the box2 wave-2 run and/or committed dual-gate-APPROVED. Not re-litigated.

| # | Fix | Where | How proven | Status |
|---|-----|-------|-----------|--------|
| A1 | Hang fix — credibility side-judge concurrency=10 (PARALLEL, not a wall) | relaunch env | credibility pass ran 659/659 clean, no stall, ~9 min | ✅ PROVEN LIVE |
| A2 | Topic gate date-blind prompt | code (bd1adbdd) | seminal papers un-buried; 573 junk demoted; small-test GREEN | ✅ |
| A3 | Rescue-False-stamp (re-judge clears stale bad stamps) | code | present + fired in run | ✅ |
| A4 | Relevance-override — code present, flag OFF per Codex P1 | code+env | Codex caught fail-open-label P1; correctly OFF | ✅ (OFF is correct) |
| A5 | dedup refheader-strict | code (2af05f62) | same-span dedup collapsing restatements live | ✅ |
| A6 | chrome render-seam screen | code | render-chrome prose screen dropped 2/7/9 chrome units live | ✅ (render seam) |
| A7 | anti-glue (no unrelated-pair glue) | code (58f329cf) | present in compose | ✅ |
| A8 | disclosed-analyst depth | code (2aa6ea5a) | the real box2 depth lever, gated | ✅ |
| A9 | NLI-consolidation PRE-BUCKET (repetition) | code (e6b6d31f) | Codex+Fable APPROVE; planted near-dups merge, 288 baskets kept | ✅ DUAL-GATE |
| A10 | #1373 query-gen status-leak screen | code (e6b6d31f) | Codex+Fable APPROVE iter-2; corrupt ev_1091 query dropped | ✅ DUAL-GATE |

**Note on A6:** the render-seam chrome screen works, but it fires TOO LATE (at render) — it drops
chrome UNITS from prose but cannot un-form an all-chrome BASKET upstream. That gap is B1 below.

---

## PART B — STILL A PROBLEM (root-caused in the live read; fix designed; needs build + gate + land)

### B1 — Chrome leaks all the way to basket composition (BIGGEST quality issue)
- **SYMPTOM:** ~25 all-chrome baskets → writer skipped → K-span; sections lost 44-82% of baskets to
  raw span; REAL papers lost (Felten "Occupational Heterogeneity", a DSpace paper, AI Review 2024,
  Oeconomia Copernicana, World Bank chrome-prefixed).
- **ROOT CAUSE:** the furniture predicate is only wired at basket-build (as a count-demotion; the member
  is still appended) — there is NO furniture screen upstream. Degraded extraction (mineru timeout →
  docling-skip >40pg → PyMuPDF/HTML) returns masthead/nav/DOI/license furniture as the body; it becomes
  the direct_quote, survives strict_verify via the self-citation hole, forms a basket. All-furniture body
  → all-chrome basket → K-span.
- ❌ **Band-aid (REJECT):** "just drop/mute chrome spans." That is MUTING — it deletes real sources and
  shrinks breadth without recovering the content.
- ✅ **TRUE FIX:** catch chrome EARLY and RECOVER the real content. (1) extraction-time furniture-density
  screen on the full body → mark degraded → re-fetch with a different extractor to get the real article;
  (2) if still furniture, down-weight + disclose (keep in pool, §-1.3, never a sole corroborator);
  (3) selection-time: pick a real-content span over a furniture span for the direct_quote. Content is
  RECOVERED, not muted.

### B2 — mineru circuit-break forces the chrome-producing fallback
- **SYMPTOM:** "mineru25 timed out after 75s → fallback to Docling"; after 3 → breaker OPEN 300s → PyMuPDF
  chrome for the whole PDF-heavy stretch.
- **ROOT CAUSE:** a FLAT page-agnostic 75s timeout applied to both a 4-page article and a 458-page report;
  huge reports genuinely need minutes; 3-consecutive-failure breaker then blacks out mineru for ALL PDFs
  incl the small ones it would extract cleanly.
- ❌ **Band-aid (REJECT):** "raise the flat timeout to 600s." That is a TIME WALL — it stalls every small
  PDF too and blows the per-URL fetch budget.
- ✅ **TRUE FIX:** page-SCALED timeout (small PDFs stay fast, big PDFs get proportional time within budget,
  or route huge PDFs to a page-window extractor) + a less-aggressive breaker so one slow big-PDF batch does
  not blind mineru for the small ones. Availability restored by mechanism, not by waiting longer.

### B3 — Connection resilience: glm-5.2 "Server disconnected" → writer K-span
- **SYMPTOM:** bursts of "Server disconnected without sending a response"; compose calls 1-10s → 51-69s;
  an unhandled asyncio ConnectTimeout leaked from _call_writer ("Task exception was never retrieved").
- **ROOT CAUSE (3, all ours — glm-5.2 has 27 healthy providers, NOT scarcity):** (1) httpx.AsyncClient
  built with no limits=/keepalive tuning → default 5s keepalive → stale-pool reuse → RemoteProtocolError;
  (2) retry `continue`s on the SAME dead pool; (3) generator pinned order:[friendli] allow_fallbacks:false
  → whole compose burst hammers ONE provider, fallbacks to the 26 siblings blocked.
- ❌ **Band-aid (REJECT):** "raise the per-call deadline / retry more on the same pool." TIME WALL + retries
  into the same dead socket.
- ✅ **TRUE FIX:** bounded httpx.Limits + LOW keepalive_expiry (precedent already in entailment_judge.py);
  on disconnect force a FRESH connection before retry; unpin the generator provider routing (allow_fallbacks
  true / drop `order`) so the burst load-balances across the 27 endpoints. Plus wrap _call_writer to catch
  ConnectTimeout → clean K-span (stop the unhandled leak). Transport repaired, not walled.

### B4 — Writer 720s pre-pass WALL abandons the majority of baskets to K-span
- **SYMPTOM:** "WALL-DEADLINE 720s hit: ABANDONING 78/104 … → K-span"; sections drafted only 9-21 of
  82-113 baskets; the rest fell to raw span.
- **ROOT CAUSE:** the 720s wall was sized in-code for 23 baskets at concurrency 8; drb_72 sections carry
  71-113 baskets at the default concurrency 8; under the B3 slowdown the wall exhausts and abandons ALL
  still-pending baskets at once with no recovery.
- ❌ **Band-aid (REJECT):** "just raise the wall to 3600s." STUPID TIME WALL — the exact operator-flagged
  anti-pattern; it makes the run crawl and still abandons under a worse spell.
- ✅ **TRUE FIX:** (1) raise bounded writer CONCURRENCY 8 → ~24-32 (the box already runs verify at 30) so
  more baskets draft in parallel; (2) basket-count-SCALED wall from the code's own makespan formula, not a
  flat 23-basket budget; (3) transport-aware wall (does not count B3 reconnect-stall time); (4) a bounded
  RECOVERY second-pass over still-pending baskets before any K-span. Throughput fixed, not time-walled.

### B5 — genai_productivity contract slot rendered as a GAP (Brynjolfsson QJE)
- **SYMPTOM:** the productivity contract slot = 0 verified sentences → gap disclosure, though the QJE
  productivity paper is present, full-text, well-weighted.
- **ROOT CAUSE:** contract-entity BINDING miss — no evidence row was stamped
  v30_entity_id='brynjolfsson_genai_at_work' (5/6 entities bound). Its sentences carried an unresolvable
  bare marker → strict_verify dropped all 13 for no_provenance_token. Plus the bound abstract copy was
  chrome-prefixed ("## Author Listed … ## Abstract"); a clean copy (ev_915) and the T1 QJE (ev_013/1017)
  existed but were never bound.
- ❌ **Band-aid (REJECT):** "lower strict_verify for this slot" — that is MUTING the faithfulness gate.
- ✅ **TRUE FIX:** bind the entity by DOI (10.1093/qje/qjae044) + title/author; prefer the CLEAN copy
  ev_915; keep the T1 QJE in the gen pool; chrome-strip the "## Author Listed" prefix; re-anchor a hollow
  contract slot to a same-DOI clean sibling and verify it through the SAME strict_verify. Faithfulness
  strengthened, never relaxed.

### B6 — D8 judge grinds / tears the validity seam (NEW — found in the live D8 read)
- **SYMPTOM:** 40+ min in the D8 verify phase: repeated "judge off-enum token (JudgeEnumError)", "judge
  blank verdict", "sentinel role force-close", "POST exceeded PG_ROLE_TRANSPORT_TOTAL_S"; canary
  quantified_silent_no_op fired. The report rendered; the final validity gate is stuck.
- **ROOT CAUSE:** same transport/provider-availability class as B3 but on the role-transport client — the
  judge/sentinel model returns off-enum/blank under concurrency; the role transport times out and force-
  closes, so the seam never cleanly converges.
- ❌ **Band-aid (REJECT):** "mute the judge errors / accept blank verdicts / lower the enum bar." MUTING the
  faithfulness judge — lethal in clinical framing.
- ✅ **TRUE FIX:** apply the B3 transport resilience to the role-transport client (fresh-connection retry +
  keepalive tuning + provider routing), and/or move the judge/sentinel role to a higher-provider-count open
  model (measure /models/{id}/endpoints). Fix the judge's transport + availability, never its verdict bar.

---

## PART C — honest verdict on the rendered report

- The report RENDERED COMPLETE and structurally correct: all 4 required aspect sections (positive,
  negative, challenges, opportunities), the required 5-column summary table, 6 seminal papers correctly
  attributed in Key Findings (incl Brynjolfsson QJE in Key Findings even though its contract SLOT gapped).
- The degradation is COMPOSITION QUALITY (K-span-heavy prose, some section gaps), driven by B3/B4 (glm-5.2
  provider drag eating the writer budget) and B1/B2 (chrome from degraded extraction). NONE of it is a
  faithfulness failure — strict_verify / D8 held; no fabrication was let through (that is why baskets fell
  to honest K-span or disclosed gaps rather than fabricated prose).
- The §-1.1 line-by-line audit (workflow wh5n9q0b5) is the empirical cross-check on PART A/B — it reads the
  actual rendered claims vs cited spans and will confirm which problems are visible in the OUTPUT vs only in
  the logs. Fold its findings into this review when it lands.

---

## PART D — §-1.1 line-by-line audit result (empirical cross-check, workflow wh5n9q0b5, 10 agents, 118 findings)

**Headline: 7 of 9 sections rated SEVERE. The report is NOT usable / NOT beat-both as-is.**

Per-section quality:
| Section | Quality |
|---|---|
| Key Findings (6 seminal papers) | **minor_issues** (genuinely good) |
| Positive Views / Productivity | **SEVERE** |
| Negative Views / Displacement | **SEVERE** |
| Challenges / Inequality | **SEVERE** |
| Opportunities / New Tasks | **SEVERE** |
| Corroborated Findings blocks | **SEVERE** |
| Analyst Synthesis + Contradictions | material_issues |
| Summary Table (REQUIRED deliverable) | **SEVERE** |
| Bibliography + Source corroboration | **SEVERE** |

Critic verdict (verbatim): *"The report has a sharp split. One half is genuinely good. The other half is a
chrome dump. Same evidence pool, two different composition paths, opposite quality."* — this is the key:
Key Findings PROVES the composer produces clean, on-topic, cited prose from this exact pool; the severe
sections came from the CHROME/K-span path (B1-B4), not from a lack of evidence.

Confirmed in the OUTPUT (worse than the logs alone showed — chrome glued INTO rendered prose, not just K-span):
- **Positive Views body is a chrome chain:** World Bank copyright notice + a graphic-designer bio + a
  truncated Microsoft stat + a social-work poverty stat + an innovation-policy paper's title/author/Abstract
  header — zero on-topic productivity claims. Brynjolfsson 14-15% / Noy-Zhang ABSENT. (= B1 in the output.)
- **Brynjolfsson Key-Findings slot leaks internal machinery text** into the report body: the slug
  'brynjolfsson_genai_at_work', 'Contract-bound content', and internal filenames 'manifest.frame_coverage_report',
  'human_gap_tasks.json'. A reader must never see internal filenames. (= B5 surfacing as visible chrome.)
- **Repetition still present:** the Penn Wharton GDP sentence rendered 4x; within-subsection fact-doubling
  (fragment then prose). The NLI pre-bucket fix (A9) is committed but was NOT in THIS run.
- **Summary Table defect:** the 'Industry Application Cases and Risk Summary Table' section contains NO table —
  a single generic sentence. (The separate 'Summary table' at line 534 exists but rated severe.)
- Correctness where content IS real is strong: every number the auditors checked verbatim-matched its source;
  ZERO fabrication. Weak spots are honest gaps/chrome, never faked prose — the faithfulness engine held.

### B7 (NEW from the audit) — Out-of-scope DATE source cited (integrity)
- **SYMPTOM:** the section's sole real productivity number is sourced to the Penn Wharton brief "Projected
  Impact of Generative AI on Future Productivity Growth" — published 9/8/2025 — in a report whose brief
  demands "academic research published before June 2023." The report contradicts its own stated scope.
- **ROOT CAUSE:** no source-DATE-scope enforcement. #1373 fixed corrupt QUERY text; this is a SOURCE
  publication-date gate — a source dated after the user's cutoff was retrieved, weighted, and cited.
- ❌ **Band-aid (REJECT):** silently drop anything with a 2024/2025 date string (would muzzle legit undated
  or reissued pre-cutoff work).
- ✅ **TRUE FIX:** when the user states a date window, extract it as a constraint (PG_EXTRACT_USER_CONSTRAINTS)
  and WEIGHT sources by publication date — down-weight/disclose out-of-window sources so an out-of-scope 2025
  forecast cannot become a section's headline cited claim. Weight, not blind-drop.

**Bottom line:** the fixes B1-B7 are empirically confirmed as the report-killers. The good Key-Findings half
proves the pipeline can produce SOTA prose from this pool; the chrome path is what wrecks the rest. Do NOT
score this run. Build B1-B7 (chrome-catch-early + re-fetch is #1), gate, relaunch.

## Assembly rule (unchanged)
B3 + B4 both edit abstractive_writer.py; B3 also edits openrouter_client.py. Build B1-B6 on the committed
base (e6b6d31f), resolve the shared-file overlaps by hand, run ONE combined Codex+Fable gate, then relaunch.
Every fix above is a mechanism repair — zero time walls, zero muting.
