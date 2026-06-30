# drb_72 Smoke Quality — Master Fix Plan (I-deepfix-001, #1344)

Single Codex-ready plan synthesized from 4 forensic artifacts + 4 fix designs. Topic under audit: *literature review on AI's restructuring impact on the labor market, English-language journal articles only.* Verdict: heavily contaminated render; root causes are (a) page-furniture/chrome rendered as cited claims at two render seams, (b) off-topic sources cited (not just weight-demoted), (c) invented quantified scalars, (d) cross-surface repetition, (e) two fabrication/provenance defects with NO designed fix yet.

---

## (1) Deduplicated master defect list

Counts after merging the 4 artifacts (same span flagged by multiple auditors collapsed to one row).

### Class A — Chrome / page-furniture rendered as cited claim (20 distinct)
| # | Defect | Cite | Sev |
|---|--------|------|-----|
| A1 | Cookie/consent banner "Opens in a new window … targeted advertising" (Wiley ev_008/ev_024) | [10] | P0 |
| A2 | GDPR "Functional Always active … technical storage or access is strictly necessary" | [23] | P0 |
| A3 | "Without a subpoena, voluntary compliance …" cookie/privacy text | [23] | P0 |
| A4 | "Statistics … used exclusively for statistical purposes" (note "purposes.The" weld) | [23] | P0 |
| A5 | "Necessary cookies are required … Show more" | [24] | P0 |
| A6 | DOI.org "DOI Not Found … WHAT CAN I DO NEXT?" error page as cited claim | [25] | P0 |
| A7 | DOI-Not-Found error page used as a basket **source TITLE** in the corroboration block | [25] | P0 |
| A8 | Russian recycling masthead "Интернет-журнал «Отходы и ресурсы» … Vol." (also off-topic, non-English, truncated, mis-attributed to Acemoglu [5]) | [5][11] | P0 |
| A9 | Russian "Журнал правовых и экономических исследований" welded into DOI-error page + internal marker "(also mirrored)" | [25] | P0 |
| A10 | Wiley cookie-wall pages ev_008/ev_024 are 100% banner+nav+tracking pixel, zero article content — admitted at fetch time | [10] | P0 |
| A11 | Author/date byline "August 30, 2023 **[By Jim Jones]**…" welded to a real claim (Background) | [8] | P1 |
| A12 | Byline "_Written by Jim McGwin, College of Business_…" welded to claim | [14] | P1 |
| A13 | Uncited orphan prose in "verified" rollup ("At the heart of this revolution… 4IR is not driven by any one innovation…"); also off-topic quantum framing | (none) | P1 |
| A14 | Paywall block "Get full access to this article / View all access and purchase options" | [20] | P1 |
| A15 | IZA working-paper cover masthead (series, DP no., author list, IZA disclaimer) | [19] | P1 |
| A16 | PDF footnote/header furniture "14Tate and Yang (2016)… 7 Post-merger restructuring" | [19] | P1 |
| A17 | Footnote-marker weld ".1 1 … 165 million US jobs filling 1,500 roles" (garbled merge) | [17] | P1 |
| A18 | "Box 3.1 … In collaboration with Indeed … workforce.40" report-layout label | [18] | P1 |
| A19 | Dangling cross-reference "(See Exhibit 1.)" (exhibit not in report) | [17] | P2 |
| A20 | Raw internal evidence-id slug "eloundou_gpts_are_gpts" printed where a locator belongs | [7] | P2 |

### Class B — Off-topic / non-journal sources cited (5 distinct)
| # | Defect | Cite | Sev |
|---|--------|------|-----|
| B1 | Supply-chain logistics blogs (inboundlogistics, protolabs) — off-topic + not journals; 2 claims + 2 biblio entries | [22][24] | P0 |
| B2 | Russian cosmetics market paper, off-topic + non-English, **mis-tiered T1 (weight 0.95)** | [26] | P0 |
| B3 | Russian recycling journal, off-topic + non-English | [11] | P1 |
| B4 | Post-merger M&A labor restructuring (plant closures, not AI-driven) + PDF de-hyphenation defect "tar- gets" | [19] | P1 |
| B5 | DOI-404 error page admitted as an off-topic "source" | [25] | P0 |

### Class C — Invented quantified filler (1 cluster)
| # | Defect | Cite | Sev |
|---|--------|------|-----|
| C1 | "displacement productivity ratio 2.14286 (modeled assumption) / restructuring efficiency 5 / net job shift 1" — unit-free scalars built by dividing unrelated percentages from different studies × a free scaling_factor | [1][2] | P0 |

### Class D — Repetition (7 clusters → 2 roots)
| # | Defect | Sev |
|---|--------|-----|
| D1 | Cross-surface headline duplication: same `ordered[0]` sentence re-lifted into Abstract + Key Findings + Analytical synthesis + body (Acemoglu task-framework ×4; Frey&Osborne Gaussian ×5; AI-exposure/employment ×5; OECD-23-countries ×4; Brynjolfsson population ×3; reshaping-labour ×2) | P2 |
| D2 | Intra-section duplication: Generative-AI section states intervention + "15% productivity" twice in one paragraph (L52) | P2 |

### Class E — Truncation (2 distinct)
| # | Defect | Cite | Sev |
|---|--------|------|-----|
| E1 | "The right to work includes not only access to." — cut mid-clause + welded UDHR heading furniture | [16] | P1 |
| E2 | Masthead "2024, Vol." — truncated mid-value, no volume number (same span as A8) | [5][11] | P1 |

### Class F — Fabrication / provenance (4 distinct — NO designed fix yet)
| # | Defect | Cite | Sev |
|---|--------|------|-----|
| F1 | The report's ONLY "multi-source corroborated" claim rests on a phantom ewadirect ACE-proceedings PDF that appears in NO bibliography entry | [1] | P0 |
| F2 | quantified input `productivity_gain_avg_pct=15%` recorded at literal_span [40,43] = "lfs" (middle of "Brynjolfsson" surname); real 15% is at offset 485 — provenance binding fabricated/misaligned | — | P0 |
| F3 | quantified sentence cites [1][2] (Acemoglu/Autor) but all inputs came from ev_030 + brynjolfsson ([9]/[6]) — citation markers mis-bound | [1][2] | P1 |
| F4 | B02/B04 re-fetch "RECOVERED" the DOI-404 error page (stub 1008→821 chars) and passed it UNCHANGED to strict_verify as an "upgrade"; recovery measured length, not document-vs-error-page | [25] | P1 |

### Class G — Counts / thin sections (3 distinct)
| # | Defect | Sev |
|---|--------|-----|
| G1 | Reliability header: 64 clusters (63 single + 1 multi) vs 26 biblio sources vs ~24 baskets — three counts do not reconcile; the single "multi-source" is F1 phantom → genuine multi-source ≈ 0 | P3 |
| G2 | Eloundou LLM-exposure section is one stub fragment "Research is needed to estimate how jobs may be affected." [7] | P2 |
| G3 | Implications section = single dangling sentence + leading-whitespace artifact, sourced from a Mercatus policy brief (non-journal) [12] | P3 |

**Why everything survives strict_verify:** chrome/off-topic/filler text is trivially verbatim-grounded in its own source span, so span-grounding ("text == its own span") self-entails. The faithfulness engine is span-faithful but not claim-worthiness-aware. That is by design and must NOT be relaxed; the fixes are render/compose-input suppressions and fetch/topicality gates, not faithfulness changes.

---

## (2) Fixes — grouped, with exact file + change + isolated test

### TRACED_NEUTRAL_FIX_NOW (do immediately — faithfulness-neutral, isolated tests already pass)

#### FIX-1 — Chrome predicate: cookie/consent + DOI-error + foreign-masthead + byline
Covers A1–A12 (the P0 cookie/DOI/masthead block + byline P1s). Both leak seams (`abstractive_writer` K-span fallback at `abstractive_writer.py:504-507`, and FIX-K verbatim-span dump at `multi_section_generator.py:4051-4081`) already delegate to the SAME shared predicate `weighted_enrichment.is_render_chrome_or_unrenderable` (`weighted_enrichment.py:1018` → `_is_new_chrome_category:964` → `_contains_forensic_chrome`). The predicate is wired; it just has no rule for these 4 classes (empirically returns `False` on all 11 chrome strings + the byline today). FLAG-not-drop: unit withheld from rollup, source stays in `evidence_pool`.

**File A: `src/polaris_graph/generator/weighted_enrichment.py`** — add 3 containment rules after `_STATS_TABLE_RE` (~line 814):
```python
# I-deepfix-001 (#1344) — cookie/consent banner, DOI-registry error page, mixed-script masthead.
_COOKIE_CONSENT_RE = re.compile(
    r"utiliz\w*\s+technologies\s+such\s+as\s+cookies"
    r"|we\s+use\s+cookies\s+to\s+enhance\s+your\s+browsing"
    r"|we\s+value\s+your\s+privacy"
    r"|analytics,?\s+personali[sz]ation,?\s+and\s+targeted\s+advertising"
    r"|necessary\s+cookies\s+are\s+required"
    r"|the\s+technical\s+storage\s+or\s+access\s+(?:is|that\s+is)\s+(?:strictly\s+necessary|used\s+exclusively)"
    r"|opens\s+(?:in\s+a\s+new\s+window|an\s+external\s+website)"
    r"|store\s+and/or\s+access\s+information\s+on\s+your\s+device"
    r"|error\s*[-–—]\s*cookies\s+turned\s+off"
    r"|cookieabsent"
    r"|press\s+alt\+1\s+for\s+screen-reader\s+mode"
    r"|strictly\s+necessary\s+for\s+the\s+legitimate\s+purpose"
    r"|accept\s+all\s+cookies", re.IGNORECASE)
_DOI_ERROR_RE = re.compile(
    r"DOI\s+Not\s+Found"
    r"|this\s+DOI\s+cannot\s+be\s+found\s+in\s+the\s+DOI\s+System"
    r"|report\s+this\s+error\s+to\s+the\s+responsible\s+DOI\s+Registration\s+Agency"
    r"|the\s+DOI\s+has\s+not\s+been\s+activated\s+yet"
    r"|search\s+again\s+from\s+DOI\.ORG", re.IGNORECASE)
_NONLATIN_MASTHEAD_RUN_RE = re.compile(r"[Ѐ-ԯ؀-ۿ一-鿿぀-ヿ가-힣]{4,}")
_MASTHEAD_VOL_TOKEN_RE = re.compile(r"\b(?:Vol\.?|Volume|Issue|No\.)\b|№|Том\b", re.IGNORECASE)
def _is_foreign_journal_masthead(text: str) -> bool:
    return bool(_NONLATIN_MASTHEAD_RUN_RE.search(text) and _MASTHEAD_VOL_TOKEN_RE.search(text))
```
Then inside `_contains_forensic_chrome`, immediately after the existing `if _NAV_CHROME_RE.search(s) or _LICENSE_CHROME_RE.search(s) or _BIBLIO_CHROME_RE.search(s): return True` (lines 909-910) add:
```python
        if _COOKIE_CONSENT_RE.search(s) or _DOI_ERROR_RE.search(s) or _is_foreign_journal_masthead(s):
            return True
```
(The mixed-script rule requires BOTH a 4+ char non-Latin run AND a Vol/№/Том token, so English prose quoting a short foreign term is safe; the legacy `_NONLATIN_RUN_RE` omitted Cyrillic U+0400–04FF entirely — this adds U+0400–052F.)

**File B: `src/polaris_graph/generator/chrome_furniture_screen.py`** — add a byline rule to the whole-unit-collapse set. After `_COOKIE_RE` (line 94), and append to `_FURNITURE_RES` (line 96):
```python
_BYLINE_RULES = [
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},?\s+\d{4}\s*\**\s*\[?\s*[Bb]y\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\s*\]?(?:\([^)\s]*\))?\s*\**",
    r"_?\b(?:Written|Posted|Reviewed|Edited|Authored|Reported|Compiled)\s+[Bb]y\s+"
    r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}(?:,\s+[A-Z][^_\n]{0,40})?_?",
]
_BYLINE_RE = re.compile("|".join(_BYLINE_RULES))
# _FURNITURE_RES = [_JOURNAL_HTML_RE, _AFFIL_RE, _PAYWALL_RE, _COOKIE_RE, _BYLINE_RE]
```
Byline obeys the over-strip guard (`is_furniture_dominant`, residue < 4 real words at `chrome_furniture_screen.py:99,127`): a **pure** byline line collapses; a byline-prefix welded to a real multi-clause claim is preserved unchanged.

**Isolated test (already run, offline, no LLM/GPU):** `/tmp/test_fix.py` + `/tmp/test_furn2.py`. 11 real drb_72 chrome strings ALL caught; 6 real claims ALL clean (incl. an English "Journal of Economic Perspectives, Vol. 33" citation and a "browser cookies are used by 85% of websites" finding → 0/6 false positives). Byline: pure byline → collapsed; byline+claim → preserved; "Published March 5, 2024 by Reuters, the report found 14%…" → preserved (a greedy-regex over-strip in the first draft was caught and fixed by bounding "By <Name>" to ≤3 capitalized tokens).

#### FIX-2 — Quantified filler suppression
Covers C1 (and incidentally removes the F2/F3 render symptoms for this run, since withholding the section stops the mis-grounded/mis-attributed scalars from rendering).

**File: `src/polaris_graph/generator/quantified_analysis.py`** — add kill-switch + predicate after `_SPEC_PROVIDER_RETRIES`:
```python
_FILLER_SUPPRESS_ENABLED = os.environ.get("PG_QUANTIFIED_FILLER_SUPPRESS","1").strip().lower() not in ("0","false","no","off")
_DIMENSIONLESS_DISPLAY_KINDS = frozenset({"number","ratio"})
_FILLER_MIN_SOURCED_INPUTS = max(2, int(os.environ.get("PG_QUANTIFIED_FILLER_MIN_SOURCED","2")))
def is_low_value_filler_output(field):
    if not _FILLER_SUPPRESS_ENABLED: return False
    if str(field.get("unit") or "").strip(): return False
    if str(field.get("display_kind") or "number") not in _DIMENSIONLESS_DISPLAY_KINDS: return False
    n_sourced = sum(1 for t in (field.get("sourced_tokens") or []) if isinstance(t, dict))
    return n_sourced >= _FILLER_MIN_SOURCED_INPUTS
```
Rule: a plain output is filler iff it is a **unit-free number/ratio scalar relating ≥2 distinct sourced inputs** (counting sourced INPUTS not ev_ids, so "3% − 2%" from the same source is still caught). In `render_decision_matrix_prose` the `for o in spec.outputs` loop `continue`s when `is_low_value_filler_output(result.fields[o.name])` (break-even/sensitivity render on their own exempt branch). In `run_quantified_section`, after `bound = bind_calc_tokens(prose, result)`, if `not bound.strip()` → set `firing_status="suppressed_low_value_quantified"`, `quantified_filler_suppressed=True`, `_stamp_status DECLINED_NO_SPEC`, `return None` (honest withhold, distinct status — not mislabeled as a Regime-C failure).

**Isolated test (run):** `scratchpad/test_filler_suppress.py` builds the 3 real offenders verbatim + 2 controls (a `$6B` USD currency value, a unit-free "6" with only 1 sourced input). Asserts predicate True for all 3 offenders, False for both controls; prose drops the 3, keeps the 2; kill-switch OFF → all 5 render byte-identical. Regression: `test_quantified_tradeoff_phase7 + b4_fire + reasoning_cap + g6_blockers` = **58 passed, 0 failed**.

#### FIX-3 — Cross-surface headline de-duplication (Part 1 only)
Covers D1 (the Analytical-synthesis re-print of the Key-Findings headline). D2 (intra-section) is a different root (abstractive_writer/section composer + `fact_dedup`) — NOT in this lane.

**File: `src/polaris_graph/generator/key_findings.py`, `build_depth_layer`** — after line 554 (`_cap = _max_key_findings_markers()`) build the registry of headlines the front `## Key Findings` block owns, only when KF is rendered:
```python
front_headlines = set()
if key_findings_enabled():
    for sr in sections or []:
        if getattr(sr, "dropped_due_to_failure", False): continue
        if getattr(sr, "is_gap_stub", False) or getattr(sr, "sentences_verified", 1) == 0: continue
        _vt = _strip_leading_markdown_headers(getattr(sr, "verified_text", "") or "")
        _first = _first_verified_sentences(_vt, 1)
        if _first: front_headlines.add(_first[0])
```
Replace `lines = [f"### {title}", "", f"**Key Findings** {headline}"]` (line 568) with `lines = [f"### {title}", ""]`. After computing challenge+tension (after line 586):
```python
if not challenge and not tension:
    if ordered[0] in front_headlines:
        continue                                  # KF already owns it -> omit, don't duplicate
    lines.append(f"**Key Findings** {headline}")   # KF block off -> headline has no other home
if len(lines) == 2:                                # only "### title" + "" -> no content
    continue
```
Update the section preamble (lines 590-594) to note the headline lives in Key Findings, with only Tension/Challenges here. Net: headline appears once (Key Findings + body); Analytical synthesis carries only the DISTINCT **Tension**/**Challenges** sentences.

**Isolated test (run):** `C:/POLARIS/.codex/I-deepfix-001/smoke_forensics/repetition_dedup_test.py` on the real Acemoglu headline + its distinct "reinstatement effect is the polar opposite" tension + a distinct Autor second-section headline, with `PG_SWEEP_KEY_FINDINGS=1` + `PG_SWEEP_DEPTH_LAYER=1`, running the ACTUAL `build_key_findings` + `build_depth_layer`. Current → headline core occurs 2× (bug reproduced); fixed → 1×; distinct tension still present; distinct Autor claim not over-stripped; front KF block byte-unchanged. ALL pass.

---

### BIGGER_DEFER (designed but higher-risk, or not yet designed)

#### DEFER-1 — Off-topic source cite-suppression (Class B1–B5) — **designed, gated, test passes; this is the single biggest cleanliness lever**
Root cause (verified): the cite-surface (`weighted_enrichment.diagnose_unbound_supports_selection`, `weighted_enrichment.py:193-266`) reads ONLY `selection_relevance` vs `PG_RELEVANCE_FLOOR` and — correctly per the operator-locked §-1.3 / I-arch-011 B18 keep-all-sort-last keystone (lines 223-235) — sorts off-topic last but never excludes; the un-capped I-arch-007 surfacing then renders the full list, so sort-last still emits numbered citations. The lexical query-floor alternative was empirically DISPROVEN: real `_containment` scores the off-topic supply-chain query 0.0000 AND on-topic "AI job displacement" 0.0000 — a lexical floor cannot separate them. Off-topic discrimination is fundamentally SEMANTIC.

Designed fix (3 parts, gated `PG_OFFTOPIC_CITE_SUPPRESS` default-ON, key = SEMANTIC confirmed-off-topic LABEL, NOT the score):
- **A:** flip `topic_relevance_gate.py:60` `PG_SCOPE_TOPIC_GATE` default `"0"→"1"` (already DEMOTE-not-drop, keystone-compatible; keep kill-switch).
- **B:** stamp `content_relevance_label` + carry `topic_offtopic_demoted` onto evidence-pool rows in `evidence_selector.py` (~line 2462, beside `selection_relevance`) and `live_retriever.py` (CorpusSource→row). Pure additive field copy.
- **C:** add `_is_confirmed_offtopic(row)` predicate (`topic_offtopic_demoted is True` OR `content_relevance_label in {"demoted","escalated_demoted"}`) to `weighted_enrichment.py`; in `diagnose_unbound_supports_selection` skip confirmed-off-topic members (append to `offtopic_suppressed`); the bibliography numberer in `multi_section_generator.py` must not assign `[N]`; write the suppressed set to disclosed sidecar `outputs/.../offtopic_excluded_from_citation.json`.

This keys ONLY on the LLM/judge confirmed-OFF verdict, NOT on `selection_relevance < floor` — categorically distinct from the banned B18 drop. **Isolated test (run):** `C:/POLARIS/.codex/I-deepfix-001/smoke_forensics/offtopic_predicate_test.py` — the banned floor suppresses 6 off-topic rows BUT ALSO real on-topic Mercatus [12] (0.22) + Eloundou [7] (0.18) (proves why it's banned); the label predicate suppresses all 6 off-topic, keeps all 3 on-topic. PASS. **Why deferred:** flips a default-OFF gate ON and touches 3 retrieval files; needs careful Codex review, but it is the only lever that stops off-topic *prose* (B4 M&A, B1 supply-chain) that carries no chrome from being cited.

#### DEFER-2 — Abstract↔Key-Findings overlap (Part 2 of repetition)
Not a mechanical bug: `abstract_conclusion.py` docstring (lines 17-29) records that safe non-verbatim Abstract synthesis needs an entailment gate that must be built first; collapsing the honestly-disclaimed verbatim restatement silently would degrade an intended element. Operator design call.

#### DEFER-3 (NEEDS DESIGN — no fix authored) — Fabrication / provenance: F1, F2, F4
- **F1 (P0):** phantom ewadirect corroborator not in any bibliography entry — the report's ONLY multi-source claim. Root: `weighted_enrichment._basket_corroboration_block` + `content_dedup_consolidate.py` basket merge admitting a non-bibliography source. **No designed fix.** Must be designed before claiming a faithfulness-clean re-smoke.
- **F2 (P0):** `quantified_analysis.py` `literal_span` offset computation records a span that does not contain the `raw_literal` it claims ([40,43]="lfs"). FIX-2 hides the *render* of this for drb_72, but the span-binding bug remains for any future quantified output. Needs the span-binding fix lane.
- **F4 (P1):** `live_retriever` B02/B04 re-fetch "recovery" classifies a DOI-404 error page as an upgrade by length, not document-vs-error. FIX-1 stops the error page from *rendering* (A6/A7 `_DOI_ERROR_RE`), but the source still enters the pool as "recovered." Should add a DOI-404/error-page classifier in `shell_detector` / `access_bypass.block_page_detector`.

#### DEFER-4 (lower priority residual chrome NOT covered by FIX-1)
A14 paywall [20] (`_PAYWALL_RE` exists but missed this string), A15 IZA/working-paper English cover masthead [19], A16 PDF footnote/header furniture [19], A17 footnote-marker weld [17], A18 Box-label/footnote-number [18], A19 cross-reference "(See Exhibit 1.)" [17], A20 raw ev-id slug [7], A13 uncited orphan prose, E1 truncation predicate [16]. Same surgical pattern as FIX-1 (precision-first regex at the shared predicate) — extend in a follow-up; cheap but each needs its own real-string + clean-claim probe.

#### DEFER-5 (cosmetic) — G1 reliability-header count reconciliation (`disclosure_population.py`), G2/G3 thin/stub-section handling (mark as curator-actionable gaps). P3/P2.

---

## (3) Fastest path to a clean re-smoke

**Required before the paid re-run (blocks a clean §-1.1 read):**
1. **FIX-1 chrome** — kills all P0 cookie/DOI/foreign-masthead leaks (A1–A10) + byline P1s (A11/A12). Highest visible-contamination removal.
2. **FIX-2 filler** — removes C1 invented scalars and incidentally the F2/F3 render symptoms.
3. **DEFER-1 off-topic cite-suppression** — despite its DEFER label it is **required for cleanliness**: off-topic *prose* sources without chrome (B4 M&A [19], B1 supply-chain blog text) are NOT touched by FIX-1 and will still cite. It is fully designed, gated default-ON, and its isolated test passes. Promote it into this run with one Codex diff gate.

**Strongly recommended before the paid run (else re-smoke still shows chrome/fabrication):**
4. **DEFER-4 residual chrome** — at minimum IZA masthead (A15), PDF footnote furniture (A16/A17), paywall (A14). These are P1 and will visibly survive otherwise. Same one-file pattern as FIX-1.
5. **DEFER-3 F1 phantom corroborator (P0)** — needs a design; a faithfulness-clean claim cannot be made while the only multi-source claim rests on a non-bibliography source. If F1 cannot be designed+gated in time, the re-smoke must explicitly carry F1 as a known open P0, not be called clean.

**Nice-to-have / follow-up (do not block the re-run):** FIX-3 repetition Part 1 (quality, not contamination), DEFER-2 abstract overlap, DEFER-4 minor chrome (A19/A20/A13/E1), DEFER-3 F2 span-binding hardening, DEFER-3 F4 DOI-404 fetch classifier, DEFER-5 counts/thin sections.

**Sequencing for speed (parallel-safe):** FIX-1, FIX-2, FIX-3 touch disjoint files (`weighted_enrichment.py`+`chrome_furniture_screen.py` / `quantified_analysis.py` / `key_findings.py`) → build in parallel, then ONE consolidated Codex diff gate. DEFER-1 touches `evidence_selector.py`+`live_retriever.py`+`topic_relevance_gate.py`+`weighted_enrichment.py` (shares `weighted_enrichment.py` with FIX-1) → keep DEFER-1 in the SAME diff as FIX-1 to avoid a `weighted_enrichment.py` merge conflict and gate them together. Net: 2 worktrees, 1 combined diff, 1 Codex gate, then the fresh back-half re-smoke on the VM (`run_honest_sweep_r3.py` heavy steps run on the VM, never local). A banked replay cannot validate the fetch-side fixes (DEFER-3 F4) or the truncated banked spans — a FRESH front-half run is required to prove FIX-1/DEFER-1.

---

## (4) §-1.3 faithfulness confirmation (FIX_NOW lanes + DEFER-1)

Explicit: none of FIX-1, FIX-2, FIX-3, or DEFER-1 relaxes the faithfulness engine or hard-drops a real corroborator.

- **The only hard gate is untouched.** strict_verify, NLI entailment, 4-role D8, provenance, span-grounding all run UNCHANGED on whatever survives. A fabricated or mis-cited claim still fails exactly as before. None of these fixes promotes a unit.
- **FIX-1 (chrome)** SUPPRESSES render/compose *input* only, FLAG-not-DROP: the unit is withheld from the rendered rollup, but the source row stays in `evidence_pool` + the credibility disclosure. The three containment classes (cookie banner, DOI "Not Found" registry page, foreign-script masthead) are page furniture / dead-fetch shells — never a corroborating source; removing a self-entailing chrome span ("text == its own span") STRENGTHENS faithfulness. The byline rule obeys the operator-mandated over-strip guard (suppresses only when post-strip residue < 4 real words), so a real multi-clause claim with a welded byline prefix is returned unchanged. Verified 0/6 real-claim false positives.
- **FIX-2 (filler)** suppresses a SYNTHESIZED scalar the pipeline invented by combining sources; the sourced inputs themselves (the 30%, the 14%, the 15%) remain cited in their own baskets — nothing real is dropped. Dimensioned results (currency/percent/count, or a transform of a single sourced number) pass through. No faithfulness validator changed.
- **FIX-3 (repetition Part 1)** suppresses a duplicate LABEL line in a post-verify render rollup; the headline still renders once in Key Findings + the body, and the distinct Tension/Challenges sentences still surface — consolidation of a verbatim restatement, not a hard-drop. Nothing leaves the corpus, bibliography, or body.
- **DEFER-1 (off-topic)** keys ONLY on the SEMANTIC confirmed-OFF judge verdict ("this is about cosmetics/supply-chain, not AI labor"), which by definition is not a corroborator of an AI-labor claim. It deliberately does NOT re-impose the keystone-banned `selection_relevance < PG_RELEVANCE_FLOOR` drop (that drop suppressed real on-topic Mercatus [12] + Eloundou [7] in the test). The source STAYS in the pool and is disclosed in a sidecar — kept+disclosed, not hard-dropped. A low-credibility but ON-topic source (label "relevant") is untouched and still cited.

All four are gated by env kill-switches (`PG_QUANTIFIED_FILLER_SUPPRESS`, `PG_OFFTOPIC_CITE_SUPPRESS`, plus the existing `PG_SCOPE_TOPIC_GATE`) for byte-identical revert, per LAW VI.

---

Relevant artifact paths (all absolute):
- Report under audit: `C:\POLARIS\.codex\I-deepfix-001\smoke_forensics\outputs\deepfix_safety_smoke\workforce\drb_72_ai_labor\report.md`
- Isolated-test scripts already run: `C:\POLARIS\.codex\I-deepfix-001\smoke_forensics\offtopic_predicate_test.py`, `C:\POLARIS\.codex\I-deepfix-001\smoke_forensics\repetition_dedup_test.py`, `scratchpad\test_filler_suppress.py`, `/tmp/test_fix.py`, `/tmp/test_furn2.py`
- Files to edit (FIX_NOW + DEFER-1): `src\polaris_graph\generator\weighted_enrichment.py`, `src\polaris_graph\generator\chrome_furniture_screen.py`, `src\polaris_graph\generator\quantified_analysis.py`, `src\polaris_graph\generator\key_findings.py`, `src\polaris_graph\generator\multi_section_generator.py`, `src\polaris_graph\retrieval\topic_relevance_gate.py`, `src\polaris_graph\retrieval\evidence_selector.py`, `src\polaris_graph\retrieval\live_retriever.py`