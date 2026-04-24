# V30 Phase-2 run-3 fix plan v2 (post-Codex CONDITIONAL-blockers review)

Revision of `fix_plan_run3.md` addressing Codex pass-1 review at
`outputs/codex_findings/v30_m66_plan_review/findings.md` (verdict
CONDITIONAL-blockers, 2 blockers + 3 mediums + 1 nit).

**Required revisions (Codex)**:
1. Split M-66a into telemetry-first + verifier-relaxation-only-if-needed
2. Rewrite acceptance criteria to prevent false-pass (CVOT scope,
   malformed tables, false 7/7 completeness claim)
3. Split M-66b into `url_pattern_regulatory_fetch` vs
   `oa_pdf_full_text_fetch` with separate tests
4. Plus Medium #4 immediate fix: stale RetrievalAttempt
   constructor shape in M-56 DOI-consistency guard

## Medium #4 already landed (inline fix, not a sub-module)

The V30 Phase-2 run-1 root-cause fix commit (bcedd57) contained a
bug: the DOI-mismatch branch emitted `RetrievalAttempt(method=...,
endpoint=..., status_code=..., error=..., duration_ms=...)` but the
dataclass uses `(source/url/attempt_index/http_status/outcome)`.
If the branch had ever triggered on a production sweep it would
have raised `TypeError` and crashed M-56 instead of rejecting the
wrong paper.

**Landed in this commit**:
- `src/polaris_graph/retrieval/frame_fetcher.py:807-821` now uses
  canonical kwargs
- Added `TestOrchestratorDoiConsistencyGuard` (3 tests):
  mismatch_rejects, match_accepts, no_doi_element_accepts — all
  pass (39/39 M-56 suite green)

## M-66 fix bundle — revised structure

### M-66c (LAND FIRST — cheap, independent, one-line impact)

**Scope**: clinical.yaml Thomas clamp field realignment.

**Change**: required_fields for `thomas_clamp_2022` currently
include `first_phase_insulin_secretion` and
`second_phase_insulin_secretion` which aren't reported in the
Thomas 2022 abstract. Replace with what the abstract actually
reports (verified via Crossref):
- `m_value_pct_increase` (keep — this IS in abstract)
- `insulin_sensitivity_delta` (M-value change vs baseline)
- `half_life_days` (keep)
- `participant_n` (keep)
- `clamp_duration_weeks` (keep)
- Drop: first_phase / second_phase insulin secretion
- `glucagon_suppression_pct` (keep if in abstract; verify)

**Acceptance**: Thomas clamp subsection renders ≥3 of 6 fields as
`extracted` (not `not_extractable`).

### M-66b-R (regulatory url_pattern fetch)

**Scope**: M-56 adds a `url_pattern`-resolution fetch path for
public regulatory entities (FDA, EMA, NICE, HC monograph URLs).

**Change**:
- Add `_fetch_url_pattern(url)` helper in `frame_fetcher.py`
  that invokes existing AccessBypass (Crawl4AI + Jina +
  Firecrawl concurrent) used elsewhere in POLARIS
- Cap `direct_quote` at 25K chars (matches live_retriever cap)
- When `binding.primary_identifier` is `url:...` AND no DOI/PMID,
  fall through to this path
- `provenance_class = OPEN_ACCESS` when fetch succeeds;
  `METADATA_ONLY` when it doesn't

**Acceptance** (separate from M-66b-T):
- A new test `TestOrchestratorRegulatoryUrlFetch` with mocked
  httpx — verifies FDA.gov / EMA.europa.eu / nice.org.uk /
  canada.ca URL patterns produce `OPEN_ACCESS` direct_quote ≥500
  chars
- Frame coverage report entry for each regulatory entity shows
  `status: pass` OR `status: partial` (NOT `fail_min_fields`)
- At least 4 of 6 regulatory entities render in report.md body
  (FDA Mounjaro, FDA Zepbound, EMA Mounjaro EPAR, NICE TA924 —
  the ones with well-known stable landing pages)

**Not accepted**: NICE TA1026 + HC Mounjaro monograph may remain
`fail_min_fields` if their URLs are paywalled or JavaScript-rendered
(M-61 human completion path covers those).

### M-66b-T (OA full-text fetch for primary trials)

**Scope**: M-56 extends the `oa_pdf_url` path to FETCH the PDF
content (not just record the URL).

**Change**:
- When Unpaywall returns `oa_pdf_url`, invoke
  `_fetch_url_pattern(oa_pdf_url)` to extract up to 25K chars
  of full text
- If OA fetch succeeds, use full text as `direct_quote` (not
  abstract); else fall back to abstract (existing behavior)

**Acceptance** (separate from M-66b-R):
- New test `TestOrchestratorOaFullTextFetch` with mocked httpx —
  verifies OA PDF fetch enriches direct_quote from abstract
  (~500 chars) to full text (>2K chars) when available
- Post-run-3: SURPASS-4 and SURPASS-5 render ≥7 of 9 required
  fields as `extracted` (vs ~4/9 in run-2)

### M-66a-T (telemetry only — NO verifier relaxation)

**Scope**: diagnose SURPASS-6 drop by instrumenting
`run_contract_section` with per-slot strict_verify telemetry.

**Change**:
- `SectionResult` gains a new `contract_slot_drop_log` field:
  list of `{slot_id, entity_id, raw_sentences, kept_sentences,
  dropped_count, drop_reasons}` per slot
- `run_contract_section` populates this during the
  re-grouping pass
- M-60 manifest exposes the drop log for operator review

**Acceptance**:
- run-3 manifest.json has per-contract-slot drop telemetry
- If SURPASS-6 still drops despite richer content from M-66b-T,
  the telemetry shows WHY (overlap-check-failure vs
  token-resolution-failure vs LLM-all-not_extractable)

**M-66a-R (verifier relaxation) — DEFERRED to M-67**:
- Only land if M-66b-T + M-66a-T telemetry shows legitimate
  extracted fields being dropped by the content-overlap check
- Not speculative — data-driven decision

## Acceptance criteria (Codex revision #2)

Hard gates for V30 Phase-2 run-3 SHIP:

### Efficacy subsections (exact accounting)

- **7 rendered pass subsections** when CVOT remains paywalled
  (SURPASS-1/2/3/4/5/6 + SURMOUNT-2 — this is 7, not 8)
- **8 rendered pass subsections** only if SURPASS-CVOT is
  completed via M-61 (human/licensed path) — not required for
  Phase-2 ship

### Regulatory subsections

- **4 of 6 regulatory slots with status=pass in
  frame_coverage_report** (FDA Mounjaro, FDA Zepbound, EMA
  Mounjaro EPAR, NICE TA924 mandatory; NICE TA1026 + HC
  monograph may defer)
- **4 rendered regulatory subsections in report.md body** with
  ≥3 extracted fields each

### Table / timeline integrity (Codex Medium #2)

- **Trial Summary table has ≥6 rows with non-empty Comparator +
  Endpoint + Result fields** (not placeholder "—" or
  "at week 18" style junk — Codex pointed out run-2's
  "insulin glargine in adults with type" mis-parsing)
- **Trial Program Timeline has ≥6 entries with non-null Year
  field**

### Completeness claim integrity

- **Report must NOT claim "Completeness checklist: 7/7 topics
  covered" while any regulatory slot is `fail_min_fields`.**
  Add assertion in assembly code: if any contract regulatory
  entity failed, completeness claim is downgraded to
  `<N>/7 covered, regulatory gaps flagged`

### 7-dimension BEAT-BOTH

- **≥5/7 dimensions BB or BO** (net ≥BEAT_ONE: 7)
- **Zero dimensions LB** (Codex was explicit: "no LB")
- Confirmed via autoloop V2 (Claude + Codex independent audits)

## Dimensional impact projection (Codex-revised — honest)

| Dimension        | Run-2 | Honest run-3 | Optimistic (if M-66b full success) |
|------------------|-------|--------------|-----|
| Citations        | BO    | **BB**       | BB |
| Regulatory       | LB    | **BO**       | BB |
| Jurisdiction     | LB    | **BO**       | BB |
| Claim-frames     | BO    | **BB**       | BB |
| Structure        | LB    | **BO**       | BB (with explicit table fix) |
| Contradictions   | BB    | **BB**       | BB |
| Narrative depth  | LB    | **LB**       | BO (needs synthesis work, not source volume) |

**Honest projection: 2 BB + 4 BO + 1 LB** (net ≥BEAT_ONE: 6)
**Optimistic: 5 BB + 2 BO + 0 LB**

Either scenario meets the ≥5/7 ship criterion if LB=1
(narrative depth). If strict "zero LB" rule applies, add M-67
narrative-depth calibration before ship.

## Omitted blockers addressed (Codex #9)

1. **SURPASS-CVOT paywall**: NOT in hard gate. Remains
   fail_min_fields → M-61 human completion path → operator
   provides full text post-ship.
2. **Trial Summary + Timeline malformation**: dedicated check
   added (≥6 rows with real content, no placeholder comparator
   fragments).
3. **False 7/7 completeness**: assembly-time assertion added.

## Risk mitigation (Codex #8)

**Prompt token growth**: when direct_quote jumps from ~500 to
25K chars, section_max_tokens=2400 may become insufficient for
M-58 extraction. Add:
- Slot-aware content windowing: if `direct_quote` > 10K, pass
  only the first 10K to M-58 (NOT a truncation — M-58 extraction
  only needs the abstract-or-early-text section; full PDF
  content is for downstream narrative synthesis)
- Cost regression test: run-3 total cost must remain <$5 (run-2
  was $0.0045; 10× headroom already generous)

## Implementation order

1. **M-66c** (yaml) — 15 min
2. **M-66b-R** (regulatory url_pattern fetch + test) — 60 min
3. **M-66b-T** (OA full-text fetch + test) — 60 min
4. **M-66a-T** (telemetry instrumentation) — 30 min
5. **Acceptance-criteria assertions** (assembly checks + test) — 30 min
6. **Launch V30 Phase-2 run-3** — 2h
7. **Re-audit (autoloop V2)** — 10 min

**Total: ~4-5 hours to ship checkpoint.**

## Ship vs ship-and-continue (Codex #10)

If run-3 hits BB≥5/7 with zero LB: valid **V30 Phase-2 ship**.
Still ship-and-continue — V31/V32 remain for narrative-depth
calibration, CVOT/paywall policy, and Trial Summary/Timeline
semantic fidelity beyond row-count gates.

## Codex pass-2 review ask

Before implementation, Codex at gpt-5.4 xhigh reviews THIS v2 plan
for: resolution of the 2 blockers + 3 mediums + 1 nit, Medium #4
immediate fix already landed with test coverage, and whether the
split acceptance criteria prevent false-pass.
