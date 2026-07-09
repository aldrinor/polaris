# UNIFIED BUILD PLAN — 12 fixes, one Opus fan-out (Fable brain, 2026-07-08)

Base for every worktree: the current branch `bot/I-wire-001-integration` at HEAD. It already contains the two committed dual-gate fixes (NLI pre-bucket + #1373, commit e6b6d31f). Do not rebuild those two. Do not build B7 (date scope) — the operator deferred it to the search phase.

One ruling that changes the fix count on the ground: **N1-FIX-1 and N6-FIX-A are the SAME change.** Both add an off-topic basket screen to `_section_baskets_for_compose` in verified_compose.py, keyed on `weighted_enrichment._is_confirmed_offtopic`, threaded through the same two call sites in multi_section_generator.py (lines 5179 and 4831). Build it ONCE, under ONE flag: `PG_COMPOSE_OFFTOPIC_BASKET_SCREEN`. Do NOT create N6's second flag name (`PG_COMPOSE_BASKET_OFFTOPIC_WITHHOLD`) — that would be two flags gating one behavior. Withhold rule (union of both specs, precision-first): withhold a basket only when at least one member row resolves in the pool AND every resolvable member row is `_is_confirmed_offtopic`; mixed, protected (escalated_relevant), unjudged, or missing-row baskets are always kept. Both test files (N1's and N6's) must pass against this one implementation.

Second ruling: **the CONSOLIDATED_FIX_REVIEW text for B6 is superseded.** Fable refuted the availability hypothesis. Build B6 only per FABLE_SPEC_D8JUDGE.md (think-leak strip + off-enum provider rotation + observability). Do not swap the judge model. Do not pin providers. Do not apply B3's keepalive work to the role transport as part of B6.

Third ruling: **B5's binding fix also resolves N5's noted follow-up** (the bare `[brynjolfsson_genai_at_work]` marker that never rewrote to a span token — the entity was missing from the pool at rewrite time). The WT-2 builder should treat that as covered by B5, not as a separate issue.

---

## PART 1 — Files touched by more than one fix, with merge order

**verified_compose.py** — touched by N1-FIX-1 and N6-FIX-A, which are merged into one screen (above). One builder, one edit region (`_section_baskets_for_compose`, line 2826, plus the two new helpers). No other fix in this wave edits this file. N1 explicitly owns the `[uncovered supporting evidence]` surface and N6 must not duplicate it — with the merge, this is automatic.

**multi_section_generator.py** — touched by the merged N1/N6 screen (thread `evidence_pool` at the `_vc_baskets` hoist, line 5179, and the no-token repair pass, line 4831) and by N6-FIX-B (outline off-topic strip after `plans = outline_parse.plans`, ~line 8873, gated under the EXISTING `PG_ASPECT_OFFTOPIC_SLOT_GUARD`). Correction to the task framing: N3 does NOT touch this file — its spec forbids touching the facet outline and changes summary_table.py only. So one builder (WT-1) owns all multi_section_generator.py edits. Merge order inside the file: thread the pool kwargs first, then add FIX-B — they sit at distinct line ranges (4831 / 5179 / 8873) and do not interact.

**contract_section_runner.py** — touched by FOUR fixes: N5-FIX-2 (fragment snap), N2 (fragment-prose dedup), N4 (gap-sentence template), B5 (hollow-slot re-anchor to a clean same-DOI sibling). ONE builder (WT-2) owns this file and builds in this order, one commit each:
1. **N5-FIX-2** — fragment-snap gate immediately after the deterministic-stream `_verify_one_stream` return (~lines 1487-1502).
2. **N2** — fragment-prose dedup pass. Call site is AFTER the I-wire-014 consolidation block (~line 1756) and BEFORE `resolve_provenance_to_citations` (~line 1786). Runtime pipeline order inside `run_contract_section` therefore reads: N5 snap → det/narrative merge (1563) → I-wire-014 dedup → N2 dedup → citation resolve. N2 operates on the list it receives; no shared index state with the earlier pass.
3. **N4** — extract the gap sentence into `_contract_gap_sentence` (lines 2041-2057 region).
4. **B5** — re-anchor logic for a hollow contract slot. B5 runs last in the build sequence because it changes which slots are hollow at all, and the builder should re-run the N4 tests after it (N4 is the backstop that fires only when B5's cure still leaves an honest gap).
Also in this file, do not disturb `_kspan_fallback_body` (lines ~412-520) — commits 7027e829 / #1369 recently edited it; N5-FIX-1 REUSES its marker-before-period idiom rather than duplicating it.

**slot_fill.py** — N5-FIX-1 only (`render_slot_prose`, per-sub-sentence citations). N2's spec forbids touching slot_fill renderers; the WT-2 builder does the N5-FIX-1 edit as its very first commit, then never touches the file again. Known interaction to record for the gate: with N5 ON, only the first sub-sentence carries the field label, so N2's fragment classifier (exact label-prefix match) will classify and possibly drop the labeled first sub-sentence and will keep continuation sub-sentences (they carry their own citations and are verbatim). That is correct behavior, not a clobber.

**summary_table.py** — N3 only. No conflicts.

**boundary_conditions.py** — N1-FIX-2 only (quote hygiene V2). This file already carries the #1369 STEP-4 `_quote_is_unrenderable`; V2 extends it behind its own separate flag; do not modify the STEP-4 behavior when the new flag is off.

**access_bypass.py** — B1 (chrome-catch-early: furniture-density screen + re-fetch with a different extractor + selection-time real-content span pick) and B2 (mineru page-scaled timeout + gentler breaker). One builder (WT-4). Build B2 FIRST — the page-scaled timeout and breaker repair make mineru actually available, which is the extractor B1's re-fetch escalation wants to route through. Then B1 on top. B1 will also need shell_detector (extend beyond short-body) and the span-selection site for direct_quote — the builder greps for the selection seam first and lists it in the brief. B1 imports `is_render_chrome_or_unrenderable` from weighted_enrichment READ-ONLY. **weighted_enrichment.py is a no-edit file this entire wave** — every fix that needs `_is_confirmed_offtopic` or the chrome predicate imports it, never forks or edits it.

**openrouter_client.py** — B3 only (httpx.Limits + low keepalive_expiry via env, fresh-connection-before-retry on disconnect). Plus the config edit in `config/settings/openrouter_provider_routing.yaml`: generator `allow_fallbacks: true` / drop the pinned `order` so the compose burst spreads across glm-5.2's 27 endpoints (mirror what was already done for the judge).

**abstractive_writer.py** — B3-writer parts AND B4. One builder (WT-5, same as openrouter_client since B3 spans both). Merge order inside the file: build B4's scaffolding first (bounded concurrency raise, basket-count-scaled wall from the code's own makespan formula at lines 102-107, bounded recovery second pass over still-pending baskets before any K-span), then layer B3's parts into it: wrap `_call_writer` (lines ~445/475) to catch httpx.ConnectTimeout into a clean K-span (kills the "Task exception was never retrieved" leak), and make both the 180s per-call deadline and the wall transport-aware (reconnect/stall time does not count). These two fixes were designed to compose; they must ship as one coherent diff, not two patches.

**openrouter_role_transport.py + judge_adapter.py + role_transport.py** — B6 only (WT-6). Three sub-fixes per the D8 spec: think-leak strip in `_parse_openrouter_response` (~1543-1576), `served_provider` field on RoleResponse + off-enum re-ask rotation via `provider_ignore_extra` merged into the body's provider ignore list, and observability in the two WS-1(b) warnings. Must not regress the #1191 empty-choices and #1026 blank-ladder branches in the same function, and must not touch `parse_judge_verdict`, the enum, or the degrade semantics.

**N4's four cross-file regex alternations** — key_findings.py:47, run_honest_sweep_r3.py:2592, scripts/dr_benchmark/pack_drb2.py:69, scripts/rendered_report_acceptance_harness.py:89. All additive one-line alternations (`|insufficient verified evidence`). They belong to the WT-2 builder (N4 owner). No other fix in this wave edits run_honest_sweep_r3.py (N1 explicitly leaves the pass-3 merge alone; N3 explicitly leaves the wire-point alone), so there is no collision. One caution: B5's entity-binding site is not yet pinned to a file — the WT-2 builder greps `v30_entity_id` first; if the binding stamp lives in run_honest_sweep_r3.py or evidence_selector.py, it lists the site in the brief and keeps the edit disjoint from line 2592.

---

## PART 2 — Build waves (worktree fan-out)

All six worktrees are file-disjoint and run **in PARALLEL** (Wave A). There is no cross-worktree serial dependency — the serialization is entirely INSIDE worktrees that own shared files, as ordered above.

- **WT-1 (compose/off-topic):** verified_compose.py + multi_section_generator.py + boundary_conditions.py. Fixes: merged N1/N6 screen, N6-FIX-B outline strip, N1-FIX-2 boundary hygiene. Internal order: screen + threading → FIX-B → boundary hygiene.
- **WT-2 (contract stream):** slot_fill.py + contract_section_runner.py + N4's four regex files + B5 binding site (grep-located). Fixes in order: N5-FIX-1 → N5-FIX-2 → N2 → N4 (incl. regex alternations) → B5.
- **WT-3 (table):** summary_table.py. Fix: N3.
- **WT-4 (fetch/extraction):** access_bypass.py + shell_detector + span-selection seam. Fixes in order: B2 → B1.
- **WT-5 (generator transport + writer):** openrouter_client.py + openrouter_provider_routing.yaml + abstractive_writer.py. Fixes: B3 + B4 as one coherent diff, B4 scaffolding first.
- **WT-6 (judge transport):** openrouter_role_transport.py + judge_adapter.py + role_transport.py. Fix: B6.

**Wave B (integration, serial):** merge worktrees onto the base in this order — WT-6, WT-5, WT-4, WT-1, WT-2, WT-3 (transport foundations first, render-surface last; order matters only for reviewer readability since files are disjoint). Then run the FULL offline suite (`pytest tests/polaris_graph -q`) with every NEW flag unset — this is the byte-identical default-OFF proof across all twelve fixes at once. Then ONE combined Codex+Fable gate on the assembled diff (the standing assembly rule: never gate the raw parallel diffs separately).

**Wave C (relaunch):** flip the activation env (Part 3), resume from the corpus checkpoint on the VM, gate per Part 4.

---

## PART 3 — Full flag list

Flags fully specified by Fable specs (names are binding):

| Flag | Fix | Default in code | Relaunch env |
|---|---|---|---|
| PG_COMPOSE_OFFTOPIC_BASKET_SCREEN | N1+N6 merged screen | OFF | **1** |
| PG_BOUNDARY_QUOTE_HYGIENE_V2 | N1-FIX-2 | OFF | **1** |
| PG_ASPECT_OFFTOPIC_SLOT_GUARD | N6-FIX-B (existing flag) | existing kill-switch | **1** |
| PG_CONTRACT_FRAGMENT_PROSE_DEDUP | N2 | 0 | **1** |
| PG_SUMMARY_TABLE_ANCHOR_SECTION | N3 | OFF | **1** |
| PG_CONTRACT_GAP_PLAIN_DISCLOSURE | N4 | 0 | **1** |
| PG_SLOT_PROSE_SENTENCE_CITES | N5-FIX-1 | OFF | **1** |
| PG_SLOT_FRAGMENT_SNAP | N5-FIX-2 | OFF | **1** |
| PG_OPENROUTER_THINK_LEAK_STRIP | B6-FIX-1 | **ON** (kill-switch, per spec) | leave ON |
| PG_JUDGE_OFFENUM_PROVIDER_ROTATE | B6-FIX-2 | **ON** (kill-switch, per spec) | leave ON |

B6's two flags are the deliberate exception to the default-OFF convention — the spec sets them default ON as kill-switches.

Flags this plan ASSIGNS for B1-B5 (the specs gave mechanisms, not names — these names are now binding for Opus; all default OFF, all read from env per LAW VI):

| Flag | Fix | Default | Relaunch env |
|---|---|---|---|
| PG_FURNITURE_DENSITY_SCREEN | B1 step 1 (extraction-time screen → mark degraded) | OFF | **1** |
| PG_FURNITURE_REFETCH | B1 step 1 (re-fetch degraded body with different extractor) | OFF | **1** |
| PG_SPAN_SELECT_FURNITURE_AWARE | B1 step 3 (real-content span wins direct_quote) | OFF | **1** |
| PG_MINERU25_TIMEOUT_PER_PAGE_S | B2 (page-scaled timeout; keep PG_MINERU25_TIMEOUT_S as the floor for small PDFs) | unset = legacy flat 75s | set (builder proposes value from run data, ~1.5-3s/page bounded) |
| PG_MINERU25_BREAKER_THRESHOLD / PG_MINERU25_BREAKER_COOLDOWN_S | B2 (gentler breaker) | unset = legacy 3-fail/300s | set per builder proposal |
| PG_OPENROUTER_KEEPALIVE_EXPIRY_S / PG_OPENROUTER_MAX_KEEPALIVE | B3 (httpx.Limits; precedent entailment_judge.py:726-738) | unset = legacy client | set (~1-2s / 8) |
| PG_OPENROUTER_FRESH_CONN_ON_DISCONNECT | B3 (drop idle pool before retry) | OFF | **1** |
| PG_WRITER_DEADLINE_TRANSPORT_AWARE | B3/B4 (stall time not counted) | OFF | **1** |
| PG_WRITER_WALL_BASKET_SCALED | B4 (makespan-formula wall) | OFF | **1** |
| PG_WRITER_KSPAN_RECOVERY_PASS | B4 (bounded second pass before K-span) | OFF | **1** |
| PG_CONTRACT_BIND_DOI_FALLBACK | B5 (bind entity by DOI + title/author) | OFF | **1** |
| PG_CONTRACT_REANCHOR_CLEAN_SIBLING | B5 (hollow slot → same-DOI clean sibling, through unchanged strict_verify) | OFF | **1** |
| PG_AUTHOR_ABSTRACT_HEADER_STRIP | B5 (strip "## Author Listed … ## Abstract" chrome prefix at normalization) | OFF | **1** |

Also in the relaunch env, confirm the two committed base fixes are active: `PG_CONSOLIDATION_NLI_SUBBUCKET=1`, `PG_QUERY_META_STATUS_SCREEN=1`. Plus the existing runtime setting `PG_ABSTRACTIVE_WRITER_CONCURRENCY=24` (B4 — env value change, not a code default; the box already runs verify at 30).

Config (not a flag): openrouter_provider_routing.yaml generator block → `allow_fallbacks: true`, remove the pinned `order` list.

---

## PART 4 — VM gate criteria (relaunch from the corpus checkpoint; each fix must SHOW this)

- **N1:** log carries `[activation] compose_offtopic_basket_screen: withheld=N kept=M` with N > 0. The report's "[uncovered supporting evidence" blocks no longer quote confirmed-off-topic sources (professor bio, transcribeanywhere, jukeboxprint, alistapart, rooseveltinstitute all gone). No Boundary line quotes a markdown-link/URL fragment; no "on however:" / "on entry-:" labels. Tension lines quote only on-topic body prose. Honest on-topic uncovered blocks MAY remain — that is correct.
- **N2:** no contract slot body renders a labeled fragment ("Identification strategy: …") AND a prose restatement of the same value with the same [N]. Log carries `[contract_section] fragment-prose dedup: X -> Y kept` with drops > 0. A field with no covering prose (e.g. a sample-size fragment) still renders once.
- **N3:** the GFM table (`| Research Literature |` header, 5 columns) sits directly under the body heading that names the summary table; NO detached "## Summary table" heading before the Bibliography; canary line carries `anchored=True`; row count is not thinned versus rows built; the section's narrative prose is still present below the table.
- **N4:** grep of report.md finds ZERO of: any entity slug with underscores, "manifest.frame_coverage_report", "human_gap_tasks.json", "curator-actionable", "Contract-bound". Any residual gap renders as the plain "Insufficient verified evidence…" sentence with its [N]. Key Findings does NOT contain that sentence (the regex alternations held).
- **N5:** no standalone subjectless fragment sentences (the "By applying this framework … [N]." class); the "roughly 1.8%" sentence renders BEFORE "this share jumps"; verification_details shows zero `no_provenance_token` drops originating from labeled slot fragments; zero bare orphan "[entity]." fragments.
- **N6:** the confirmed-off-topic body citations are gone from prose (the jobtoday hourly-wage line, Purdue paralegal blog, Yale customer-service blog, Coursera marketing, fiction-writer blog classes); FINDING#5/strip lines appear in the log even on the legacy outline branch; all 565+ demoted rows STILL appear in the bibliography and disclosure surfaces (withhold-and-disclose, never dropped).
- **B1:** log shows furniture-density degradation marks and re-fetch attempts with a different extractor; the previously lost real papers (Felten, DSpace, World Bank class) carry real-content direct_quotes; all-chrome basket count near zero; sections no longer lose 44-82% of baskets to K-span for the chrome reason.
- **B2:** no 300s mineru breaker blackout after a big-PDF stretch; small PDFs keep extracting via mineru while a large report is in flight; log shows scaled timeouts on large page counts; mineru success rate materially up versus wave-2.
- **B3:** "Server disconnected without sending a response" bursts gone (zero or isolated single events with immediate fresh-connection recovery); ZERO "Task exception was never retrieved"; compose call latency back in the 1-10s band; log shows generator calls served by multiple providers, not one pinned host.
- **B4:** ZERO "WALL-DEADLINE … ABANDONING" mass events; drafted-basket counts per section approximately equal to submitted counts (K-span only for genuine per-basket failures, not batch abandonment); recovery-pass log line if any baskets were pending at the wall.
- **B5:** the genai_productivity slot renders verified content — no gap disclosure for Brynjolfsson; log shows the DOI/title binding stamped `v30_entity_id=brynjolfsson_genai_at_work` on the clean copy (ev_915 class); strict_verify keeps > 0 sentences for that slot; frame_coverage no longer marks it pipeline-fault.
- **B6:** the D8 phase completes without the ~50-minute grind; any garbled response either parses clean after the think-leak strip (one POST) or recovers on ONE rotated re-ask with the garbling provider in the ignore list (visible in the WS-1(b) warning with token + served_provider); zero accepted garbled tokens (enum bar intact); `release_allowed=True` with coverage at least the prior 0.833.

---

## PART 5 — Mixed / correct-honest rulings, and follow-ups

- **N2 (mixed):** BUILD fully. The two-tier fragment+prose template is intentional design; the bug is the duplication, and the spec'd consolidation pass IS the fix. Do not touch the template or the narrative prompt.
- **N3 (mixed):** BUILD the anchoring fix only. The table's row building, verification gating, and em-dash gap cells are CORRECT honest behavior — untouched. The polluted claim CELLS are inherited from the composer and get fixed by B1/B3/B4 and the compose-side fixes, never by the table module.
- **N4 (mixed):** BUILD. The gap disclosure itself is correct honest behavior; only the reader-facing register changes. N4 is the backstop; B5 is the cure for the specific Brynjolfsson slot. Build both.
- **B6 (mixed):** BUILD FIX 1-3 per FABLE_SPEC_D8JUDGE.md. The fail-loud exact-enum bar and the fail-closed UNSUPPORTED degrade are correct behavior and stay byte-identical. Do not swap the model, do not pin providers, do not raise retry counts or add time walls.
- **N1, N5, N6, B1, B2, B3, B4, B5 (real bugs):** BUILD fully per spec.
- **B7 (date scope):** SKIP — operator deferred to the search phase.

**Follow-ups — NOT in this build, each needs its own issue:**
1. **The "quantified SILENT NO-OP" canary** (`firing_status=spec_validation_rejected`) — Fable's new side-finding. It is an honest canary firing on a rejected quantified spec, a SEPARATE non-transport issue. Needs its own investigation. Do not silence it, do not bundle it into B6.
2. The verified_compose K-span member-clause glue garble (report line 43, "; in contrast," + PDF header junk) — a different emitter than N5's; B1 reduces its fuel but the glue path itself is unaudited.
3. The remaining "curator-actionable gap" jargon family in report_redactor.py:96 and multi_section_generator's `_GAP_STUB_SENTENCE` (no slug/filename leak, lower severity) — same register class as N4, deliberately out of this diff.

**Standing bans for every builder (verbatim from the specs):** no time walls, no caps, no thinners, no post-render regex-scrubbing of report.md, no lexical-score filters, no hard-drops of demoted rows from pool/bibliography/disclosures, no relaxing or bypassing strict_verify / NLI / D8 / provenance, no fuzzy enum matching, no edits to weighted_enrichment.py. Every new behavior sits behind its flag with flag-OFF byte-identical proof in an offline test, per each spec's test file. Full suite green with all new flags unset is a merge precondition; ONE combined Codex+Fable gate on the assembled diff before relaunch.