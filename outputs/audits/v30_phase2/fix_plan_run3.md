# V30 Phase-2 run-3 fix plan (post-autoloop cross-review)

Claude + Codex both produced independent audits of V30 Phase-2
run-2 (`outputs/codex_findings/v30_phase2_run2_audit/{claude_findings.md,findings.md}`).
Cross-reviewed tally:

| Dimension       | Claude   | Codex    | Reconciled |
|-----------------|----------|----------|------------|
| Citations       | LOSE_ONE | BO       | **BO**     |
| Regulatory      | LB       | LB       | **LB**     |
| Jurisdiction    | LB       | LB       | **LB**     |
| Claim-frames    | BO       | BO       | **BO**     |
| Structure       | BB       | LB       | **LB** (Codex correct — tables malformed, SURPASS-6 missing, zero regulatory subsections) |
| Contradictions  | BB       | BB       | **BB**     |
| Narrative depth | LB       | LB       | **LB**     |

**Reconciled tally: 1 BB + 2 BO + 4 LB** (net ≥BEAT_ONE: 3).
NOT BEAT-BOTH. Iterate.

Compared to V28/V29 ceiling (3 BB + 0 BO + 4 LB):
- GAINED: Contradictions (unique to V30 architecture),
  Claim-frames (run-2 corrected PMIDs recovered SURPASS-2 ETD/CI/P)
- LOST temporarily: Structure (contract-section rendering bug
  drops SURPASS-6, malforms Trial Summary/Timeline tables)
- UNCHANGED: Regulatory, Jurisdiction, Narrative depth — these
  are the primary V30 Phase-2 architectural gaps

## Four blocker categories

### Blocker 1 — SURPASS-6 pass-but-unsection (Structure, -1 BB)

Manifest says `efficacy_surpass_6.status=pass` (M-59 verdict ≥5
required_fields extracted) but report.md has no SURPASS-6
subsection. Both competitors cover SURPASS-6 (Rosenstock JAMA
2023, tirzepatide vs insulin lispro).

**Hypothesis**: `run_contract_section`'s sentence re-grouping
logic drops SURPASS-6 sentences. Two candidate causes:

1. LLM extracted fields have `source_span` values that fail
   strict_verify's content-word overlap check (≥2 words in
   common with the span). Field values like "Eli Lilly and
   Company" or short numeric values may fail this.
2. `sentences_by_slot[efficacy_surpass_6]` ends up empty
   because `entity_to_slot_id[surpass_6_primary]` map is wrong
   (e.g., `tokens[0].evidence_id` resolves to a different
   entity after citation rewrite).

**Fix**: instrument `run_contract_section` with per-slot
sentence counts (added to SectionResult telemetry) so the
drop cause is diagnosable. Loosen the overlap check for
slot-bound `Field: value [id]` sentences where the citation
binding IS the verification contract (content-word overlap was
designed for legacy free-form LLM prose, not contract slots).

### Blocker 2 — Regulatory entities: all 6 fail_min_fields (Regulatory + Jurisdiction, -2 dims)

All 6 regulatory contract entities (FDA Mounjaro label, FDA
Zepbound label, EMA Mounjaro EPAR, NICE TA924, NICE TA1026, HC
Mounjaro monograph) fail with `fail_min_fields`. Root cause:
they have `url_pattern` primary identifier (no DOI/PMID),
producing METADATA_ONLY provenance, empty `direct_quote`, and
therefore M-58 extraction produces all-`not_extractable` → M-59
fails min_fields threshold.

**Fix (M-66)**: extend M-56 with a `url_pattern` fetch path that
resolves the URL through the existing AccessBypass infrastructure
(Crawl4AI + Jina + Firecrawl) used by live_retriever. Acceptable
because the URL_patterns are all stable regulatory landing pages
(fda.gov, ema.europa.eu, nice.org.uk, canada.ca).

Flow:
```
url_pattern → resolve to concrete URL (static mapping in contract)
  → AccessBypass fetch (Crawl4AI/Jina concurrent)
  → direct_quote = trimmed 25K-char extract
  → provenance_class = OPEN_ACCESS (with url pointing at source)
  → M-58 extracts required_fields from that direct_quote
```

Contract changes: regulatory entities already have `url_pattern`
like `https://www.fda.gov/...`. The `_resolve_url_pattern`
function is new; it either uses a direct URL or a pattern with
template variables (today they're just plain URLs, so resolution
is identity).

### Blocker 3 — SURPASS-4/5/6 field coverage (Claim-frames, -1 BO)

SURPASS-4 currently renders only population + comparator +
sponsor (report.md:19). SURPASS-5 gets population + baseline HbA1c
+ primary endpoint + safety_signal. Both miss the same ETD/CI/P
depth as SURPASS-2 despite having the same contract field list.

**Hypothesis**: LLM marked many fields `not_extractable` because
the fetched `direct_quote` (likely abstract-only) doesn't contain
verbatim values for etd_with_uncertainty, N, baseline_hba1c.

**Fix**: for open_access primary trials, **fetch the full OA PDF
body** (via existing AccessBypass) into `direct_quote` rather than
relying on the Crossref abstract. Abstract-only retrieval is
insufficient for 9-field extraction; full-text is needed.

This is the higher-fidelity variant of blocker 2 — same
infrastructure, applied to the `oa_pdf_url` path of M-56.

### Blocker 4 — Thomas clamp required_fields misalignment (Claim-frames, -partial)

`first_phase_insulin_secretion` + `second_phase_insulin_secretion`
are NOT reported in the Thomas 2022 abstract — the paper reports
M-value (insulin sensitivity), glucose effectiveness, and AIRg
(acute insulin response to arginine). Contract fields don't
match paper content.

**Fix**: update contract field list to match what Thomas actually
reports:
- `m_value_pct_increase` ✓ (already in yaml)
- `insulin_sensitivity_mvalue` (replace first_phase / second_phase
  insulin secretion which aren't extractable from this paper)
- `airg_acute_insulin_response`
- `half_life_days` ✓
- `participant_n` ✓
- `clamp_duration_weeks` ✓

## Fix sequencing

**M-66 (this cycle)**: Blockers 1, 2, 3 bundled

M-66a: SURPASS-6 rendering diagnostic + content-overlap loosening
  for contract slots.
M-66b: M-56 url_pattern + oa_pdf_url full-text fetch via
  AccessBypass (unlocks Regulatory/Jurisdiction dims + enriches
  SURPASS-4/5/6).
M-66c: Thomas clamp contract field realignment (yaml-only).

**M-67 (next cycle)**: if Blocker 1 diagnostic shows the overlap
check is the root cause, redesign strict_verify content-overlap
to be slot-aware (terser format for contract sections).

**Acceptance criteria for V30 Phase-2 run-3**:
- report.md has subsections for SURPASS-1/2/3/4/5/6 + SURMOUNT-2
  + SURPASS-CVOT (7 efficacy subsections, all with ≥5 fields)
- report.md has 4+ regulatory subsections (FDA, EMA, NICE, HC)
- Trial Summary table has ≥6 rows
- Trial Program Timeline has ≥6 entries
- BEAT-BOTH ≥5/7 dimensions in re-run autoloop

## Cost/time estimate

- M-66a: ~30 min (diagnostic + overlap loosening)
- M-66b: ~2-3 hr (M-56 fetch path + contract URL resolution +
  LLM re-extraction tests; needs regression tests)
- M-66c: ~15 min (yaml edit + PubMed verification)
- Re-run sweep: ~2h
- Re-audit: ~10 min

Total: ~5-6 hours through next BEAT-BOTH checkpoint.

## Expected dimensional impact

| Dimension        | Current | After M-66 |
|------------------|---------|-----------|
| Citations        | BO      | BB        |
| Regulatory       | LB      | BB (+2)   |
| Jurisdiction     | LB      | BO (+1)   |
| Claim-frames     | BO      | BB (+1)   |
| Structure        | LB      | BB (+2)   |
| Contradictions   | BB      | BB        |
| Narrative depth  | LB      | BO (+1)   |

**Target after M-66**: 5 BB + 2 BO + 0 LB (net ≥BEAT_ONE: 7) —
BEAT-BOTH SHIP criterion achieved.

## Codex pass-1 review ask

Before implementation, Codex at gpt-5.4 xhigh reviews this plan
for: root-cause-vs-band-aid, fix sequencing, M-66b scope creep,
acceptance criteria strength, and whether expected dimensional
impact is honest or optimistic.
