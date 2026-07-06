HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

# Wave 2e — Rendered-report ACCEPTANCE HARNESS (I-deepfix-001 #1344)

## 0. What this is / why

`REAL_PLAN_2026.md` names the **"false-fired pipeline"** as the campaign's biggest risk:
the composition + coverage flags turn ON, the writer-path logs look busy, but the **rendered
`report.md` is still shallow or degraded** (empty sections, disclosure-only bodies, glued chrome,
no cross-source analysis). Internal counters cannot catch this — they report the machinery ran,
not that real prose shipped. Wave 2e (`build_validate_plan` item 2e) is the reader that checks the
**actual finished paragraphs**, not counters. It is the real acceptance check.

This is a **NEW standalone script**: `scripts/rendered_report_acceptance_harness.py`. It modifies
no existing module. It is **offline** (reads a `report.md` path + optional `manifest.json`; no LLM,
no network). It is a **triage / acceptance report**, NOT a faithfulness gate: it emits observations
+ an advisory top-level `looks_false_fired` heuristic. It NEVER raises, NEVER aborts, NEVER modifies
anything, and no hardcoded threshold decides anything critical (LAW VI — every threshold is an
env-tunable used ONLY for the advisory flag).

## 1. Independent-detector rationale (I-wire-013 blind-predicate lesson)

Per the I-wire-013 finding (`project_iwire013_blind_predicate_independent_detector_2026_06_26`):
**shared code = shared blind spot.** The production chrome predicate
(`weighted_enrichment.is_render_chrome_or_unrenderable`) and the truncation predicate
(`key_findings.is_truncated_fragment`) are BLIND to mid-prose glued chrome and mid-word span cuts.
A harness that imported them would inherit the exact blindness it exists to catch. So this harness
**imports ZERO production predicates.** Its chrome / truncation / analytical rules are authored
independently in this file (own regexes, own heuristics). Any divergence from the production
predicate is a FEATURE (it surfaces production blindness), never a bug to be resolved by unifying.
The disclosure-label prefixes it recognizes are re-declared here as literal constants (NOT imported)
so the harness stays a clean-room reader of the rendered text.

## 2. The 6 checks (each reports per-check observations; none is a hard gate)

1. **WRITER PROSE SHIPPED per section.** Enumerate every non-scaffolding content section
   (Abstract, analytical `###`/`####` sections, Corroborated Weighted Findings, Conclusion,
   Implications, Limitations, Background; Key Findings handled as a bulleted section). For each,
   classify: `empty` / `disclosure_only` / `single_sentence` / `prose_shipped` (>=2 connected real
   sentences) / `bullets_present` / `bullets_degraded`. Report per-section verdict + the fraction of
   prose-type sections that shipped real multi-sentence prose. Scaffolding sections (Reliability
   header, Methods, Bibliography, disclosures, Source corroboration, References, Appendix) are
   excluded from the required-prose set.

2. **LABELED-FALLBACK-BLOCK RATE.** Fraction of section body that is a labeled disclosure block —
   a paragraph/line starting with one of the re-declared literal prefixes
   `[uncovered supporting evidence for:` / `[verification incomplete:` /
   `[insufficient verified evidence` — OR the section-level curator-gap stub ("did not survive
   strict verification ... curator-actionable gap"). Report the rate (by unit and by char) overall
   and per section, and WHICH sections are disclosure-heavy. High rate = false-fired / repair
   non-convergence.

3. **ANALYTICAL-UNITS-IN-BODY.** Count body sentences that are cross-source analytical / inference
   units: a sentence carrying >=1 analytical connective (comparison / trend / causal / contrast:
   "in contrast", "whereas", "compared", "however", "relative to", "higher/lower than", "because",
   "therefore", "as a result", "driven by", "leads to", "offset", "counterbalanc", "outweigh",
   "correlat", "associated with", ...) AND citing **>=2 DISTINCT `[N]` citations** in the same
   sentence. Contrast against plain single-source lookups (exactly 1 distinct citation, no analytical
   connective). Report both counts + examples.

4. **TWO-SIDED TREATMENT.** Detect debate-style framing (question / section titles carry debate
   keywords: "debate", "controversy", "benefits and risks", "opportunities and challenges",
   "displacement" vs "creation", "for and against", ...). For a debate report, check presence of a
   **supported PRO** (positive-polarity sentence WITH a `[N]` citation) AND a **supported CON**
   (negative-polarity sentence WITH a citation). Report `debate_detected`, supported_pro_count,
   supported_con_count, `two_sided` (True/False/None), and which side is missing (one-sided).

5. **CHROME / JUNK IN BODY** (independent §-1.1-style detector; imports NO production predicate):
   - raw `[#ev:` provenance tokens leaked into the body (must never render),
   - masthead / byline / ToC furniture: ORCID, affiliation middot lists, license/open-access stubs,
     DOI:/ISSN: markers, `>=3` URLs in one unit, numbered ToC tokens, glued inline markdown headers,
     "Download Associated Records" / browser-cache junk, non-Latin scrape blocks,
   - mid-word truncated fragments before a `[N]` citation — evaluated ONLY when a known-word basis is
     available (own `evidence_pool.json` reader in the report's dir); a token that is a strict
     prefix/suffix of a LONGER known corpus word is a span cut. When no basis is present, truncation
     is reported `not_evaluated` (never a silent pass, never a false flag). Report counts + examples.

6. **RUBRIC-FACET COVERAGE PRESENCE.** If a facet/rubric list is available in the manifest
   (`frame_coverage_report.entries[].entity_id`, `completeness.uncovered_topic_ids`, or a `facets`/
   `rubric` key — best-effort across schemas), derive keyword sets per facet and report which
   required facets appear in the rendered body (>= half their content keywords present, or exact
   entity_id present). If no facet list is found, report `facet_list_available: false`. Never raise.

## 3. Advisory `looks_false_fired` heuristic (env-tunable ONLY — LAW VI)

`looks_false_fired = True` iff ANY of (each threshold from env, CLI-overridable, used ONLY here):
- overall labeled-fallback-block rate > `PG_ACCEPT_FALLBACK_RATE_MAX` (default 0.5)
- prose-shipped section fraction < `PG_ACCEPT_MIN_PROSE_SECTION_FRAC` (default 0.5)
- cross-source analytical units < `PG_ACCEPT_MIN_ANALYTICAL_UNITS` (default 1)
- (chrome units + raw-ev tokens) in body > `PG_ACCEPT_CHROME_MAX` (default 5)

Report `looks_false_fired` + a `reasons` list naming which condition(s) fired. This is advisory
triage, NOT a pass/fail gate; the script always exits 0 (the only non-zero exits are argparse's own
`--help`/bad-arg codes). Missing/malformed report or manifest => structured result with
`input_present: false` / degraded fields, NEVER an exception.

## 4. API (for testability)

- `analyze_report(report_text, manifest=None, snapshot_dir=None, thresholds=None) -> dict` — pure,
  deterministic, env-independent (thresholds passed explicitly; defaults are a module constant).
- Helpers: `split_sections`, `classify_section`, `is_disclosure_block`, `body_chrome_flags`,
  `count_analytical_units`, `two_sided_analysis`, `facet_coverage`, `build_known_words`,
  `truncation_flags`.
- `main(argv) -> int` — CLI wrapper: guarded file reads, prints JSON + plain summary, optional
  `--json-out`, always returns 0 on content (argparse handles `--help`).

## 5. Tests (`tests/polaris_graph/test_rendered_report_acceptance_harness_wave2e.py`, offline)

- GOOD synthetic report.md (connected multi-sentence prose, >=2-distinct-citation analytical units,
  low fallback, supported pro + con, no chrome) => `looks_false_fired is False`, analytical count
  high, fallback rate low, `two_sided True`, zero body chrome.
- FALSE-FIRED synthetic report.md (mostly `[verification incomplete: ...]` /
  `[uncovered supporting evidence for: ...]` blocks, a raw `[#ev:` token, one-sided con-only,
  single-source lookups) => `looks_false_fired is True` with reasons flagging high fallback rate,
  zero analytical units, body chrome (raw ev token), and one-sided treatment.
- Never-raises on empty string, malformed manifest (non-dict / bad JSON handled by caller), and
  missing input — returns a structured dict / exit 0.
- Function-level unit tests for the independent chrome rules and the disclosure-block classifier.

## 6. Files I have ALSO checked and they're clean (adjacent scan)

- `scripts/iwire013_sec11_forensic_audit.py` — the independent-detector precedent (style mirror,
  NOT imported).
- `src/polaris_graph/generator/verified_compose.py:1039-1239` — exact disclosure-label prefixes
  (`_INSUFFICIENT_EVIDENCE_DISCLOSURE_PREFIX`, `_DEGRADED_VERIFY_DISCLOSURE_PREFIX`,
  `_UNCOVERED_FACT_DISCLOSURE_PREFIX`) re-declared as literals here (not imported).
- `src/polaris_graph/generator/multi_section_generator.py:5154`, `contract_section_runner.py:113` —
  `[verification incomplete: ...]` producers; consistent with the prefixes above.
- Manifest schema (`frame_coverage_report`, `completeness`) verified against
  `outputs/iarch011_drb78_run5/manifest.json` for the facet-coverage extraction.
- No existing module imports the new script; it is standalone. No production code is modified.
