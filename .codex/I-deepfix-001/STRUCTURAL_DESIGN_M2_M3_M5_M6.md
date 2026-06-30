# Codex-Ready Design Plan — Structural DRB-II Rebuilds (M2 / M3 / M5 / M6)

Issue family: `I-deepfix-001` follow-on (drb_72 deep-fix). Four structural gaps, all WEIGHT-and-CONSOLIDATE compliant, all behind LAW-VI kill-switches, all leaving the frozen faithfulness engine untouched.

---

## §0. Canonical cap directive (paste verbatim atop every Codex brief generated from this plan)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

---

## §1. Shared design invariants (true for ALL four gaps — Codex verifies once, applies to all)

1. **Faithfulness engine is FROZEN.** None of `strict_verify`, NLI entailment, the 4-role D8 adjudicator, span-grounding, or provenance-token validation is edited by any of M2/M3/M5/M6. Every new path is fetch-layer, classify-layer, selection/routing-layer, or render-layer. M6 *calls* the production `verify_sentence_provenance` per-clause but does not modify it.
2. **No hard-drop / no weight-floor / no cap / no target.** Every source that reaches composition today still reaches it after these changes. M2 re-weights+labels, M3 adds coverage, M5 routes-to-disclosed (kept + re-surfaced), M6 adds analytical sentences on top of keep-all atoms. Nothing is deleted from `evidence_pool`, `classified_sources`, the bibliography, or `corpus_credibility_disclosure.json`.
3. **Default-OFF or default-ON kill-switch on every path** → byte-identical revert. M2/M6-core default-OFF (operator opt-in / canary). M3/M5 default-ON (they fix an active defect) but revert byte-identically when their flag is unset.
4. **Fail-loud canary on every "feature must fire" path** (per the repeated "verify the feature fired in output, not in config" lesson): if the gating flag is active but zero rows/units carry the new field, the run fails loudly rather than silently no-op'ing.
5. **The reversed `journal_only` DROP machinery is never touched.** M2 builds a parallel WEIGHT path; it never calls `journal_only_active`, `is_citeable_journal`'s exclude branch, `JournalOnlyLeakError`, `assert_no_leak`, `prune_contract_plans`, or the `min_distinct_journals` count floor.

---

## §2. M2 — Per-citation document-type WEIGHT-and-DISCLOSE

**Gap (P0 for journal-only template):** drb_72 required "high-quality, English-language journal articles only," but the cited corpus is dominated by on-topic *wrong-genre* sources — arxiv preprints, an Amazon book, WEF/IZA/OECD reports, university news blogs, BCG/McKinsey consultancy, and a predatory `ewadirect` (T7) proceedings venue that *leads* the Corroborated Weighted Findings. There is no per-citation document-TYPE label anywhere; the only existing genre mechanism (`journal_only_filter.py`) is a FILTER-AND-DROP + `min_distinct_journals:12` COUNT-floor that the operator REVERSED on 2026-06-07 and must stay dormant.

**Root cause:** the pipeline has a credibility axis (tier T1–T7, `authority_score`, `source_class`, `predatory_oa`) but NO orthogonal document-TYPE axis. OpenAlex already computes the discriminating signals (`openalex_publication_type`, `openalex_source_type`, `openalex_is_peer_reviewed`, `predatory_oa`) and attaches them to `ClassificationResult`/`AuthorityResult`, but no consumer turns them into a per-citation genre label or genre weight. 2025 OPENBIB/QSS literature confirms OpenAlex over-marks ~99% of works as "article," so the journal-positive test must require `source_type=="journal"` AND peer-reviewed — exactly what the dormant `is_citeable_journal` already encodes.

### Design (surgical, default-OFF, journal-only-template-scoped)

**A) NEW** `src/polaris_graph/retrieval/document_type_classifier.py` — deterministic, offline, no LLM:

```python
class DocumentType(str, Enum):
    JOURNAL_ARTICLE="JOURNAL_ARTICLE"; REVIEW_ARTICLE="REVIEW_ARTICLE"
    PREPRINT="PREPRINT"; CONFERENCE_PAPER="CONFERENCE_PAPER"; WORKING_PAPER="WORKING_PAPER"
    BOOK="BOOK"; REPORT="REPORT"; NEWS="NEWS"; PRESS_RELEASE="PRESS_RELEASE"
    BLOG_COMMENTARY="BLOG_COMMENTARY"; ENCYCLOPEDIA="ENCYCLOPEDIA"; DATASET="DATASET"
    UGC="UGC"; PREDATORY_OA_JOURNAL="PREDATORY_OA_JOURNAL"; UNKNOWN="UNKNOWN"

# domain/url heuristic fallback sets (LAW VI: seedable from config, with defaults)
_PREPRINT_HOSTS={"arxiv.org","ssrn.com","papers.ssrn.com","osf.io","psyarxiv.com","researchgate.net","biorxiv.org","medrxiv.org"}
_REPORT_HOSTS={"weforum.org","oecd.org","ilo.org","imf.org","worldbank.org","mckinsey.com","bcg.com","mercatus.org","brookings.edu","iza.org","ftp.iza.org","docs.iza.org"}
_NEWS_HOSTS={"reuters.com","bloomberg.com","ft.com","nytimes.com","wsj.com","bbc.com","economist.com"}
_BLOG_PLATFORMS={"medium.com","substack.com","wordpress.com","blogspot.com"}
_BOOK_HOSTS={"amazon.com","books.google.com","springer.com/book"}
_ENCYCLOPEDIA_HOSTS={"wikipedia.org","britannica.com"}
_UNI_NEWS_MARKERS=(".edu/20","/news/","/blog/")  # university news/blog surface, not a journal

def classify_document_type(*, openalex_publication_type="", openalex_source_type="",
        openalex_is_peer_reviewed=None, predatory_oa=False, source_class="",
        url="", title="", doi="") -> tuple["DocumentType", str]:
    pt=(openalex_publication_type or "").strip().lower(); st=(openalex_source_type or "").strip().lower()
    host=_host(url)
    # 1) OpenAlex GOLD signal (require source_type==journal — type alone over-marks 99% as article)
    if predatory_oa and pt in ("article","review"): return DocumentType.PREDATORY_OA_JOURNAL, f"oa_predatory:{pt}"
    if st=="journal" and openalex_is_peer_reviewed and pt=="review": return DocumentType.REVIEW_ARTICLE,"oa_journal_review"
    if st=="journal" and openalex_is_peer_reviewed and pt=="article": return DocumentType.JOURNAL_ARTICLE,"oa_journal_article"
    if pt=="preprint" or st=="repository": return DocumentType.PREPRINT,f"oa_preprint:{pt or st}"
    if pt in ("book","book-chapter") or st in ("ebook platform","book series"): return DocumentType.BOOK,f"oa_book:{pt or st}"
    if st=="conference" or pt=="proceedings-article": return DocumentType.CONFERENCE_PAPER,"oa_conference"
    if pt in ("report","working-paper"): return DocumentType.REPORT,f"oa_report:{pt}"
    # 2) source_class secondary (field-agnostic credibility class)
    sc=(source_class or "").strip().upper()
    if sc=="PRESS_RELEASE": return DocumentType.PRESS_RELEASE,"sourceclass_press"
    if sc=="UGC": return DocumentType.UGC,"sourceclass_ugc"
    # 3) deterministic host/url fallback (no OpenAlex genre)
    if any(host==h or host.endswith("."+h) for h in _PREPRINT_HOSTS): return DocumentType.PREPRINT,f"host_preprint:{host}"
    if any(host==h or host.endswith("."+h) for h in _BOOK_HOSTS): return DocumentType.BOOK,f"host_book:{host}"
    if any(host==h or host.endswith("."+h) for h in _ENCYCLOPEDIA_HOSTS): return DocumentType.ENCYCLOPEDIA,f"host_encyclopedia:{host}"
    if any(host==h or host.endswith("."+h) for h in _REPORT_HOSTS): return DocumentType.REPORT,f"host_report:{host}"
    if any(host==h or host.endswith("."+h) for h in _NEWS_HOSTS): return DocumentType.NEWS,f"host_news:{host}"
    if any(host==h or host.endswith("."+h) for h in _BLOG_PLATFORMS) or any(m in url.lower() for m in _UNI_NEWS_MARKERS):
        return DocumentType.BLOG_COMMENTARY,"host_blog_or_uni_news"
    if sc=="PRIMARY_SCHOLARLY": return DocumentType.JOURNAL_ARTICLE,"sourceclass_scholarly_fallback"
    if sc=="COMMENTARY": return DocumentType.BLOG_COMMENTARY,"sourceclass_commentary"
    return DocumentType.UNKNOWN,"unresolved"

_PEER_REVIEWED_JOURNAL={DocumentType.JOURNAL_ARTICLE, DocumentType.REVIEW_ARTICLE}
def is_peer_reviewed_journal_article(dt:"DocumentType")->bool: return dt in _PEER_REVIEWED_JOURNAL

DEFAULT_DOCUMENT_TYPE_WEIGHTS={  # multiplicative, surfaced — NOT a threshold/floor
  "JOURNAL_ARTICLE":1.0,"REVIEW_ARTICLE":1.0,"PREPRINT":0.7,"WORKING_PAPER":0.6,
  "CONFERENCE_PAPER":0.7,"BOOK":0.5,"REPORT":0.5,"NEWS":0.4,"PRESS_RELEASE":0.35,
  "BLOG_COMMENTARY":0.3,"ENCYCLOPEDIA":0.25,"DATASET":0.4,"UGC":0.2,
  "PREDATORY_OA_JOURNAL":0.25,"UNKNOWN":0.5}

JOURNAL_DOC_WEIGHT_FLAG="PG_DOCUMENT_TYPE_WEIGHT"
def document_type_weighting_active(protocol)->bool:
    return os.getenv(JOURNAL_DOC_WEIGHT_FLAG,"0")=="1" and bool(protocol) and \
        str((protocol or {}).get("document_type_preference") or "").strip().lower()=="journal_article"
def resolve_document_type_weight(dt:"DocumentType", protocol)->float:
    overrides=(protocol or {}).get("document_type_weights") or {}
    return float(overrides.get(dt.value, DEFAULT_DOCUMENT_TYPE_WEIGHTS[dt.value]))
```

**B) EDIT** `src/polaris_graph/retrieval/tier_classifier.py` — ADDITIVE `ClassificationResult` fields (default `None` = byte-identical OFF): `document_type: str | None = None`, `is_journal_article: bool | None = None`. Compute in BOTH return paths (authority-model path ~line 2210 and rules path) by calling `classify_document_type` with the OpenAlex signals already in `signals` + `authority_result.source_class.value` + `authority_result.predatory_oa`. Genre lands right next to `authority_score`/`source_class`; no new network/LLM.

**C) Carry genre to disclosure.** In `live_retriever` where tier is attached to each `CorpusSource`/evidence row, also stash `.document_type` (mirror of `.tier`/`.authority_score`). In `scripts/run_honest_sweep_r3.py` ~9803–9812, build `_wc_document_type_by_url` exactly like `_wc_authority_by_url`, and pass `protocol=scope.protocol` + `document_type_by_url=...` into `build_corpus_credibility_disclosure`.

**D) EDIT** `src/polaris_graph/nodes/weighted_corpus_gate.py` — `SourceCredibilityRow` ADDITIVE fields (default `None`): `document_type`, `is_journal_article`, `document_type_weight`, `document_type_adjusted_weight`. `build_corpus_credibility_disclosure` gains params `protocol=None, document_type_by_url=None`. After the existing credibility `weight`/`basis` is computed (line ~320, UNCHANGED — raw credibility axis preserved), when `document_type_weighting_active(protocol)`:

```python
dt_str = getattr(s,"document_type",None) or (document_type_by_url or {}).get(url)
dt = DocumentType(dt_str) if dt_str in DocumentType._value2member_map_ else DocumentType.UNKNOWN
dtw = resolve_document_type_weight(dt, protocol)
row.document_type=dt.value; row.is_journal_article=is_peer_reviewed_journal_article(dt)
row.document_type_weight=round(dtw,4); row.document_type_adjusted_weight=round(weight*dtw,4)
```

Add a SECOND disclosed mean `document_type_adjusted_mean` on `CorpusCredibilityDisclosure` plus a flag `document_type_preference_active: bool`, so a journal-only question honestly shows the corpus is non-journal-heavy — WITHOUT mutating `weighted_credibility_mean` and WITHOUT any gate reading the adjusted value. OFF path: every new field stays `None`, `weighted_credibility_mean` and `per_source` byte-identical.

**E) Per-citation RENDER** (`scripts/run_honest_sweep_r3.py`). When `document_type_preference` active: (1) bibliography render appends a genre tag per entry — ` — [document type: report — not a peer-reviewed journal article]` for non-journal, ` — [peer-reviewed journal article]` for journal; (2) in `_basket_corroboration_block` (~line 2478) order the Corroborated Weighted Findings by `document_type_adjusted_weight` (a WEIGHT re-rank, NOT a drop) so the `ewadirect` predatory venue falls below the JEP/QJE journal articles but STAYS in the list, labelled. All gated by the same `active()` check → OFF byte-identical.

**F) CONFIG** `config/scope_templates/workforce.yaml` — under the drb_72 journal-only profile add NEW non-drop keys (distinct from the dormant reversed `source_restriction: journal_only`):

```yaml
# NEW (M2): WEIGHT-and-DISCLOSE document-type preference. NOT a drop/floor.
# Gated by PG_DOCUMENT_TYPE_WEIGHT=1 AND this field. Default-OFF byte-identical.
document_type_preference: journal_article
document_type_weights:        # LAW VI overridable multipliers (else module defaults)
  journal_article: 1.0
  review_article: 1.0
  preprint: 0.7
  report: 0.5
  book: 0.5
  news: 0.4
  blog_commentary: 0.3
  predatory_oa_journal: 0.25
  unknown: 0.5
```

Activation for a real run is a one-line operator decision: `PG_DOCUMENT_TYPE_WEIGHT=1` for a deliberate journal-only question. Nothing else in the repo changes behavior.

### M2 risk
1. Genre misclassification mislabels a real journal as non-journal (or vice versa). Mitigation: journal-POSITIVE test requires `source_type=="journal"` AND peer-reviewed (not type alone — OpenAlex over-marks 99% as "article"); host heuristics fire only as fallback when OpenAlex genre absent; UNKNOWN carries neutral 0.5 (never punished). Because nothing is dropped, a misclassification is a visible label + softened weight, not a lost source — low blast radius.
2. Over-reach beyond the journal-only template. Mitigated by the double gate (flag AND template field) and a NEW key separate from `source_restriction`. Codex P0: verify no OFF-path field is populated.
3. Adjusted weight accidentally feeding a gate. Mitigated by leaving raw `credibility_weight` untouched and surfacing the adjusted value as a SEPARATE disclosed field/mean that no gate reads. **Codex P0: confirm `document_type_adjusted_weight` is never consumed by an abort/approval path.**
4. Re-rank of Corroborated Weighted Findings misread as "dropping" the predatory venue. Mitigated by keeping it in the list with an explicit label; test asserts it is still present.
5. Render churn could collide with M5/M6 corroboration-block edits in the same file. Mitigated by gating all render changes behind `active()` and landing M2 in one consolidated diff (see §6 sequencing).

### M2 test
Isolated offline replay (no spend/GPU) against real artifacts — `tests/polaris_graph/test_document_type_weight_m2.py`:
- `classify_document_type` truth table on real drb_72 offenders by url/title: `arxiv.org/pdf/2011.03044`→PREPRINT; `amazon.com/...Fourth-Industrial-Revolution`→BOOK; `weforum.org`→REPORT; `its.uri.edu`/`etm.wsu.edu`→BLOG_COMMENTARY; `ilo.org` discovery portal→REPORT; `researchgate.net`→PREPRINT; `ewadirect` (`predatory_oa=True`)→PREDATORY_OA_JOURNAL; `aeaweb.org/JEP` + `onlinelibrary.wiley.com` with `source_type=journal`+peer_reviewed→JOURNAL_ARTICLE. Assert `is_peer_reviewed_journal_article` True only for the last two.
- Replay `build_corpus_credibility_disclosure` over the real `corpus_credibility_disclosure.json` `per_source` (64 rows) with a synthetic journal-only protocol + `PG_DOCUMENT_TYPE_WEIGHT=1`: assert (a) `len(per_source)` UNCHANGED == 64 and url set identical (KEEP-not-DROP); (b) every row gained the 4 new fields; (c) journal rows keep `document_type_weight` 1.0, report/blog/predatory carry reduced multiplier; (d) `credibility_weight`/`weight_basis` byte-identical to input; (e) `document_type_adjusted_mean < weighted_credibility_mean`.
- Corroboration re-rank replay over real `bibliography.json`: assert the `ewadirect` basket no longer sorts first under `document_type_adjusted_weight` AND is still present.
- Default-OFF: flag unset → disclosure dict + `per_source` byte-identical to HEAD (all new fields None), bibliography render unchanged.
- `py_compile` + import clean on touched files; run existing `journal_only` + `weighted_corpus_gate` suites to prove no regression to the dormant drop path.
- **Behavioral re-smoke** (the fired-in-output proof): run from a banked `corpus_snapshot` (or next fresh drb_72 back-half) with the flag + workforce journal-only profile; assert in rendered artifacts that `per_source` rows carry the genre fields, bibliography lines carry the genre tag, the Corroborated Weighted Findings no longer leads with `ewadirect`, and `total_sources`/breadth count are UNCHANGED. **Fail-CLOSED canary:** `document_type_preference` active but zero rows carry a `document_type` → fail the run.

---

## §3. M3 — Canonical primary PDFs render empty (locator + abstract-gather)

**Gap (coverage tragedy):** the two canonical PRIMARY PDFs — `[5] acemoglu_restrepo_robots_jobs` (JPE 2020, DOI 10.1086/705716) and `[7] eloundou GPTs-are-GPTs` (Science 2024, DOI 10.1126/science.adj0998) — render as "no resolvable URL/DOI locator (disclosed evidence gap)" with NO body, while cookie-banner/chrome sources rendered full prose. Both are V30 contract-frame rows carrying a valid DOI but EMPTY `source_url`; `robots_jobs` is `provenance_class=metadata_only` with `direct_quote=""`, `eloundou` is `abstract_only` with a 56-char fragment. Neither appears in retrieval/tool trace — they are injected by the V30 frame path.

**Root cause (two distinct defects, confirmed by a live DOI-resolution probe):**

- **DEFECT 1 (locator — deterministic, certain):** `provenance_generator.py:_num_for` (lines 4010–4016) copies only `num/evidence_id/url/tier/statement` and DROPS `doi`/`pmid`. So `_bib_entry_has_locator` (`run_honest_sweep_r3.py:1641`) returns False and the renderer (2719–2722) prints "no resolvable URL/DOI locator" — even though the existing `require_locator` doi.org fallback at 2731–2734 would render `https://doi.org/{doi}` if the entry carried the DOI. `PG_BIB_REQUIRE_LOCATOR` is ON in this run. The DOI was in `evidence_pool` the whole time; it was lost at bib build.
- **DEFECT 2 (body/abstract didn't land — robustness):** both papers are paywalled with NO legal OA full text (Unpaywall `is_oa=False`; OpenAlex closed). The honest content ceiling is the abstract. `frame_fetcher._fetch_frame_entity_inner` SHORT-CIRCUITS the abstract gather: the OpenAlex fallback gate (1465–1471) requires `not abstract_crossref and not abstract_pubmed`, so a degenerate first source wins (eloundou's 56-char OpenAlex fragment) and richer sources are never consulted; under concurrency a transient CrossRef/OpenAlex throttle left `robots_jobs` with no abstract and no further fallback → METADATA_ONLY empty (the 688-char OpenAlex abstract exists but didn't land). Empty body then makes `strict_verify` correctly drop the contract slot. There is NO retry diversification beyond a single short-circuited chain.

### Design (surgical, two fixes, each behind a default-ON LAW-VI kill-switch)

**FIX-M3a (locator carry-through)** — `provenance_generator.py:_num_for`, row dict at 4010–4016, add two keys:

```python
row: dict[str, Any] = {
    "num": ev_to_num[ev_id],
    "evidence_id": ev_id,
    "url": ev.get("source_url", ""),
    "doi": ev.get("doi", ""),     # M3: carry DOI so the require_locator doi.org fallback fires
    "pmid": ev.get("pmid", ""),   # M3: PMID locator fallback
    "tier": ev.get("tier", ""),
    "statement": (ev.get("statement") or "")[:300],
}
```

Byte-neutral when `PG_BIB_REQUIRE_LOCATOR` is OFF (extra keys ignored); when ON, `_bib_entry_has_locator` now returns True for `[5]`/`[7]` and the existing else-branch (`run_honest_sweep_r3.py:2730–2734`) renders `https://doi.org/10.1086/705716` and `https://doi.org/10.1126/science.adj0998`. Optionally extend 2731–2734 with a PMID locator (`https://pubmed.ncbi.nlm.nih.gov/{pmid}/`) when url+doi both blank. **Secondary carry-through sites Codex must verify:** `citation_mapper.py:338` (contract path) and `nodes/assemble.py:173` (non-multi-section assemble path) — carry `doi`/`pmid` there too or a contract run via a different path could still drop the locator.

**FIX-M3b (abstract gather robustness)** — `src/polaris_graph/retrieval/frame_fetcher.py`:

1. **Gather-all-then-pick-richest:** change the OpenAlex fallback gate at 1465–1471 — drop the `not abstract_crossref and not abstract_pubmed` short-circuit so OpenAlex is ALWAYS consulted for a DOI (keep the DOI-consistency guard at 1482). Gate behind `PG_FRAME_MULTI_ABSTRACT` (default `"1"`); OFF restores the legacy short-circuit byte-identically.
2. **Add a 3rd deterministic abstract source — Semantic Scholar Graph API.** New `_call_s2(client, doi)` + `_parse_s2_response(data)` mirroring `_call_openalex`/`_parse_openalex_response`:

```python
_S2_WORK_BASE = "https://api.semanticscholar.org/graph/v1/paper/DOI:"
def _call_s2(client, doi):
    headers = {}
    key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    if key: headers["x-api-key"] = key
    url = _S2_WORK_BASE + _urlsafe_doi(doi)
    r, outcome, attempts, timings = _request_with_retry(
        client, "GET", "s2", url,
        params={"fields": "title,abstract,year,venue,externalIds"},
        headers=headers,
    )
    ... # parse abstract/title/year; DOI-consistency guard vs externalIds.DOI
```

Gate `PG_FRAME_S2_ABSTRACT` (default `"1"`). Feed crossref/openalex/pubmed/s2 abstracts into the EXISTING `_pick_richest_abstract` (longest verbatim wins) at 1514–1527. This deterministically fixes eloundou (full abstract beats the 56-char fragment) and makes `robots_jobs` resilient to any single-source transient (688-char OpenAlex abstract or the S2 abstract lands). **NO Sci-Hub, no fabricated full text** — the abstract is the honest reachable ceiling for a closed-access primary.

Once the abstract lands, the previously-empty METADATA_ONLY row becomes ABSTRACT_ONLY with real verbatim text, `strict_verify` has real text to ground against, and the slot renders instead of being dropped. Combined with FIX-M3a the bibliography shows a working `https://doi.org/` locator.

### M3 risk
- The abstract is a thinner grounding surface than full text, so `strict_verify` may still legitimately drop a contract sentence the abstract does not support — that is CORRECT, not a regression (these primaries are genuinely closed-access; the abstract is the honest ceiling; do not add Sci-Hub).
- FIX-M3b adds 1–2 extra HTTP GETs per DOI entity (OpenAlex always-on + S2), cheap and deterministic, rate-limited by the existing `_request_with_retry` 429/5xx backoff; S2 unauthenticated is rate-limited → wire `SEMANTIC_SCHOLAR_API_KEY` (already an env in the codebase) for headroom.
- Richest-abstract selection could pick a wrong-paper abstract — mitigated by the existing DOI-consistency guard (reject when the source's own DOI != bound DOI), which must be replicated in `_parse_s2_response`.
- FIX-M3a adds keys that are byte-neutral when `require_locator` OFF; verify no downstream consumer asserts an exact bib-row key set.
- **Second bib-builder + assemble path:** `citation_mapper.py:338` and `nodes/assemble.py:173` — carry `doi`/`pmid` there too (Codex P1).

### M3 test
- **Offline FIX-M3a:** build a bib row from the real `evidence_pool` `robots_jobs`/`eloundou` rows WITH the doi carry-through, call `_render_bibliography_lines([row], require_locator=True)`; assert output contains `https://doi.org/10.1086/705716` and `https://doi.org/10.1126/science.adj0998` and does NOT contain "no resolvable URL/DOI locator". Control: a genuinely id-less row (no url, no doi, no pmid) still renders the gap line.
- **Offline FIX-M3b:** dependency-injected fake `httpx.Client` returning canned responses — `robots_jobs` CrossRef(no-abstract)/OpenAlex(688-char)/S2(abstract) → assert `FrameRow.provenance_class==ABSTRACT_ONLY` and `direct_quote` == the richest text; `eloundou` CrossRef(full)/OpenAlex(56-char fragment) → assert the FULL abstract wins; DOI-mismatch case → asserted rejected. Kill-switches OFF → byte-identical legacy. `py_compile` + import clean.
- **Live reproduction already run** (proves the data exists): OpenAlex returns 688 chars for `robots_jobs`; S2/CrossRef carry the eloundou abstract.
- **Behavioral re-smoke (fresh front-half on the VM — a banked replay CANNOT validate a fetch-side fix):** `evidence_pool` `robots_jobs.direct_quote` non-empty; bibliography `[5]`/`[7]` carry `https://doi.org/...` locators; the contract slot renders instead of "did not survive strict verification". **Fail-loud canary:** assert no `v30_frame_row` carrying a DOI ends the run with BOTH empty `direct_quote` AND empty `source_url`.

---

## §4. M5 — Near-zero-weight single-origin sources anchoring standalone findings (promotion-eligibility partition)

**Gap:** the "Corroborated Weighted Findings" enrichment section lets near-zero-weight, single-origin, non-journal sources anchor standalone numbered findings. In drb_72: `[21]` cognifit blog (weight 0.03), `[22]` inboundlogistics (0.00), `[23]` procom (0.01), `[24]` protolabs (0.00), plus wsu blog `[8]`/0.06, IZA working paper `[19]`/0.05, predatory DOI 10.5555 (0.00), off-topic Russian DOI (0.00). Each is on-topic enough to span-verify but carries ~0 credibility and is corroborated by nobody, yet earns a top-level cited claim exactly like a corroborated NEJM/AEA source. DEFER-1 only catches OFF-topic sources; the faithfulness engine cannot catch these because the body sentence is verbatim from the source span (self-entails, passes `strict_verify`). The defect is a SURFACE-placement (credibility/corroboration) decision, not a grounding decision — handled at the cite surface, never in the frozen engine. Simulated on the real `bibliography.json`: weight-floor 0.10 + corroboration-floor 2 demotes exactly those 8, leaves every promoted source untouched.

**Root cause:** `weighted_enrichment.diagnose_unbound_supports_selection` surfaces EVERY unbound span-verified SUPPORTS member into the one enrichment section with no eligibility gate on credibility weight or corroboration. After B18 correctly removed the banned `PG_RELEVANCE_FLOOR` hard-drop (keep-all-sort-below-floor-last), the full member list flows to `build_weighted_enrichment_plan`, each becomes a standalone `strict_verify`-gated body sentence, and `strict_verify` passes them because span self-entailment is the only test. Nothing asks "did this source EARN a top-level cited claim?" — promotion is automatic for any span-verified member. `credibility_weight` and basket `verified_support_origin_count` are computed and disclosed but never used as a promotion gate.

### Design (surgical, three files, default-ON gated, byte-revertible)

The lever is a **PROMOTION-ELIGIBILITY PARTITION** of enrichment members into `promoted` (earn a standalone cited claim) vs `disclosed_only` (kept + disclosed, never a standalone claim). It is a ROUTING decision, NOT a drop. A member EARNS promotion if ANY of: corroboration ≥ K distinct verified origins (the CONSOLIDATE leg), OR credibility weight ≥ W (the WEIGHT leg), OR it is a recognized journal venue (over-demotion guard). Single-origin AND below-W AND non-journal → `disclosed_only`.

**FILE 1** — `src/polaris_graph/generator/weighted_enrichment.py`:

(a) New env gate + fail-loud parsers (mirroring `evidence_selector.parse_relevance_floor`):

```python
_ENV_PROMOTION = "PG_CWF_PROMOTION_ELIGIBILITY"            # default ON
_DEFAULT_PROMOTION_MIN_WEIGHT = 0.10
_DEFAULT_PROMOTION_MIN_CORROBORATION = 2

def promotion_eligibility_enabled() -> bool:
    return os.environ.get(_ENV_PROMOTION, "1").strip().lower() in ("1","true","on","yes","enabled")

def _parse_min_weight(raw):
    if raw is None or not str(raw).strip(): value = _DEFAULT_PROMOTION_MIN_WEIGHT
    else:
        try: value = float(str(raw).strip())
        except ValueError as e: raise ValueError(f"PG_CWF_PROMOTION_MIN_WEIGHT must be a float in [0.0,1.0]; got {raw!r}") from e
    if not (0.0 <= value <= 1.0): raise ValueError(f"PG_CWF_PROMOTION_MIN_WEIGHT out of range [0.0,1.0]: {value}")
    return value

def _parse_min_corroboration(raw):
    if raw is None or not str(raw).strip(): return _DEFAULT_PROMOTION_MIN_CORROBORATION
    try: value = int(str(raw).strip())
    except ValueError as e: raise ValueError(f"PG_CWF_PROMOTION_MIN_CORROBORATION must be int >=1; got {raw!r}") from e
    if value < 1: raise ValueError(f"PG_CWF_PROMOTION_MIN_CORROBORATION must be >=1: {value}")
    return value

def _host_is_known_journal(url: str) -> bool:
    """Over-demotion guard: a recognized peer-reviewed journal article is ALWAYS promotion-eligible
    regardless of weight, so a freak-low weight can never demote a real journal."""
    if not url: return False
    try:
        from urllib.parse import urlparse
        from src.polaris_graph.retrieval.tier_classifier import PEER_REVIEWED_JOURNAL_DOMAINS, _domain_matches
        host = (urlparse(url).hostname or "").lower()
        return bool(host) and _domain_matches(host, PEER_REVIEWED_JOURNAL_DOMAINS)
    except Exception:
        return False
```

(b) Inside `diagnose_unbound_supports_selection`, in the existing basket loop, track per-eid (most-favorable-to-promotion so demotion is conservative): `best_weight` (max `credibility_weight`; `None` kept as "unknown"), `max_origin` (max basket `verified_support_origin_count`), `is_journal` (any member url host on journal domains), `best_tier` (for disclosure). `credibility_weight`/`source_tier` come off `BasketMember` (`credibility_pass.py BasketMember` has both); url from `pool.get(eid)["source_url"]`.

(c) After the ordered `ev_ids` list is built, partition (wrapped so any error fails-OPEN to promote-all = byte-identical legacy):

```python
disclosed_only = []
if promotion_eligibility_enabled():
    min_w = _parse_min_weight(os.environ.get("PG_CWF_PROMOTION_MIN_WEIGHT"))
    min_c = _parse_min_corroboration(os.environ.get("PG_CWF_PROMOTION_MIN_CORROBORATION"))
    def _eligible(eid):
        w = best_weight.get(eid)
        if w is None: return True                       # unknown weight => keep-neutral (promote)
        if w >= min_w: return True                      # WEIGHT leg
        if max_origin.get(eid, 0) >= min_c: return True # CONSOLIDATE leg (corroboration rescues)
        if is_journal.get(eid, False): return True      # journal carve-out (over-demotion guard)
        return False
    promoted = [e for e in ev_ids if _eligible(e)]
    disclosed_only = [
        {"evidence_id": e,
         "source_url": str((pool.get(e) or {}).get("source_url") or (pool.get(e) or {}).get("url") or ""),
         "source_tier": best_tier.get(e, ""), "credibility_weight": best_weight.get(e),
         "reason": "single_origin_low_weight_non_journal"}
        for e in ev_ids if not _eligible(e)
    ]
    ev_ids = promoted
```

(d) Add `disclosed_only` as the LAST field of the `UnboundSupportsSelection` NamedTuple (append-only → existing positional consumers unaffected). `select_unbound_supports_by_weight` keeps returning `.ev_ids` (now the promoted subset) so the enrichment body only gets eligible members — signature unchanged.

**FILE 2** — `src/polaris_graph/generator/multi_section_generator.py` (~line 7654 call site). After `_wfe = _diagnose_unbound_supports_selection(...)`, LOG loudly (`enrichment promotion: %d promoted, %d disclosed-only kept` with URLs) and stash `_wfe.disclosed_only` onto the result via the established getattr-safe additive-attribute idiom (same as `MultiSectionResult.reliability_header` at `run_honest_sweep_r3.py:13536/4329`): set `result.cwf_disclosed_sources = _wfe.disclosed_only`.

**FILE 3** — `scripts/run_honest_sweep_r3.py` — render the disclosure surface so keep+disclose is visible in `report.md` (the demoted source already lives in `evidence_pool` + `corpus_credibility_disclosure.json`):

```python
def _cwf_disclosed_block(disclosed):
    rows = [d for d in (disclosed or []) if d.get("source_url") or d.get("evidence_id")]
    if not rows: return ""
    lines = []
    for d in rows:
        w = d.get("credibility_weight"); ws = f"{float(w):.2f}" if isinstance(w,(int,float)) else "n/a"
        lines.append(f"- {d.get('source_url') or d.get('evidence_id')} (tier {d.get('source_tier') or 'n/a'}, weight {ws})")
    return ("\n\n## Disclosed single-origin low-weight sources\n\n"
            f"{len(rows)} on-topic source(s) were KEPT in the corpus and disclosure but NOT promoted "
            "to a standalone numbered finding: each is single-origin (uncorroborated), carries near-zero "
            "credibility weight, and is not a recognized journal venue. They remain in the evidence pool "
            "and the corpus credibility disclosure; they did not EARN a top-level cited claim.\n\n"
            + "\n".join(lines) + "\n")
```

Append right after the `_basket_corroboration_block` append (~line 2740), reading `getattr(multi, "cwf_disclosed_sources", None)`, gated by `_env_flag("PG_CWF_DISCLOSURE_BLOCK", default=True)`. Net disclosure is preserved: the demoted source leaves the per-claim corroboration block only because it is no longer cited, and is re-surfaced in this dedicated block plus `corpus_credibility_disclosure.json`.

Defaults: W=0.10, K=2. Verified on the real `bibliography.json` — demotes exactly the 8 near-zero single-origin sources and zero promoted ones (sagepub 0.18, abacademies 0.14, mercatus 0.32 all stay).

### M5 risk
1. Threshold W could demote a borderline-legitimate source. Mitigated three ways, all keep-not-drop: the corroboration OR-leg rescues any source another agrees with; the journal-venue carve-out rescues any real journal article; demotion is keep+disclose, so even a wrong demotion loses only a standalone claim, never the source. W and K LAW-VI configurable.
2. A demoted source loses its numbered `[N]` bibliography entry because no longer cited → net disclosure could look reduced. Mitigated by the dedicated 'Disclosed single-origin low-weight sources' block plus unchanged `corpus_credibility_disclosure.json`.
3. Cross-module plumbing of `disclosed_only`. Mitigated by the getattr-safe additive-attribute idiom (reliability_header precedent) and an append-only NamedTuple field so existing positional consumers (`excluded_below_floor` at `multi_section_generator.py:6794/6822`) are unaffected.
4. Default W=0.10 leaves a T7 predatory at 0.14 (abacademies) still promoted — this fix targets only the unambiguous near-zero cases; deeper venue-type policy is M2 (separate operator decision), not bolted on here.

### M5 test
Isolated offline harness `f_m5_promotion_eligibility_test.py` against the real `bibliography.json` baskets (build `BasketMember`/`ClaimBasket` from stored dicts + minimal `{eid: {source_url}}` pool):
1. gate OFF → `ev_ids` contains all members incl. the 8, `disclosed_only` empty — byte-identical legacy.
2. gate ON, W=0.10/K=2 → `ev_ids` EXCLUDES exactly the 8 (wsu 0.06, iza 0.05, cognifit 0.03, inbound 0.00, procom 0.01, protolabs 0.00, doi 10.5555 0.00, russian doi 0.00) and `disclosed_only` equals exactly those 8.
3. Over-correction guards: assert every promoted member with weight ≥ 0.10 stays (pmc 0.90, wiley 0.90, abacademies 0.14, mercatus 0.32, sagepub 0.18, arxiv 0.36, bcg 0.27, weforum 0.24, articleone 0.14, uri 0.16, doi 10.15862 0.12); inject a synthetic journal-domain member at weight 0.01 → KEPT via the journal carve-out; inject a member at weight 0.01 with basket `verified_support_origin_count=2` → KEPT via the corroboration leg.
4. Conservation: assert `set(promoted) | set(d['evidence_id'] for d in disclosed_only) == original ev_ids` (nothing vanishes — routed, not dropped).
5. Garbage env values raise ValueError (fail-loud).
- **Behavioral replay (M5 is selection+render-side, NOT fetch-side, so a banked replay CAN validate it):** re-render the back half on the banked `corpus_snapshot`; assert the Corroborated Weighted Findings no longer cites the `[21]`–`[25]`-class near-zero sources as standalone claims; the new disclosure block lists exactly the 8; standalone enrichment claim count drops by 8; `corpus_credibility_disclosure.json` `total_sources` unchanged. Plus `py_compile` + existing enrichment/render-seam regression suites green.

---

## §5. M6 — Verified analytical-synthesis path (the architecture; biggest)

**Gap:** POLARIS has NO verified analytical-synthesis path, so DRB-II analysis (18% weight) scores near-zero and "Comparative Assessment" is a gap stub. Three traced deficits:

1. The verified BODY composer `verified_compose._compose_section_per_basket` (`verified_compose.py:942`) is single-source-lift: one sentence per basket from the highest-credibility member. Its only multi-source path, `compose_basket_multicited_sentence` (line 859, `PG_VERIFIED_COMPOSE_MULTICITED` default-OFF), CONSOLIDATES WITHIN one basket only, joins with a semantically-neutral "; " connective, and its `relational_quantifier_guard` actively STRIPS any relational/aggregate predicate (line 748). It is corroboration, never cross-basket analysis.
2. "Comparative Assessment" renders the `_GAP_STUB_SENTENCE` (`multi_section_generator.py:721`) because comparison is inherently cross-basket and there is no cross-basket producer.
3. `analyst_synthesis.py` (the I-bug-105 two-layer interpretive narrative citing by `[N]`) IS fully built and wired (`run_honest_sweep_r3.py:6661` import, 12183 suppress flag, 12463–12473 render insert) but is DARK in drb_72 — no "## Analyst Synthesis" header, no run_log mention; `multi.analyst_synthesis_text` came back empty. And even when it fires it is UNVERIFIED BY CONTRACT (line 67); its B13 deviation check (`analyst_synthesis_deviation_check.py`) is ADVISORY — LABELS a sentence BUCKET_LOW, never gates/drops. Abstract/Conclusion are verbatim re-lifts by design (`abstract_conclusion.py`: "unsound synthesis machinery is REMOVED. Any future labeled-synthesis feature must build the entailment gate first").

**Root cause:** there has never been a composer that emits a sentence spanning TWO baskets, because the team could not previously verify a synthesized relation and retreated to verbatim re-presentation and within-basket consolidation that STRIPS relations. `strict_verify` checks one span per `[#ev]` token, which the team read as "one source per sentence" — but that is a per-CLAUSE invariant, not a per-sentence-one-source invariant: `compose_multicited_sentence` already proves a sentence may carry N clauses, each with its own `[#ev]` token, each independently strict_verify-passed. The relation gate the abstract_conclusion header asked for is ALREADY PRESENT but unused for composition: `claim_graph.ClaimGraph.edges` (ContradictionEdge from the 3 certified detectors: `semantic_conflict_detector`, `qualitative_conflict_detector`, rules), `both_sides.compose_both_sides`, equivalence clusters, `consolidation_nli`. The relation gate exists; nothing wires it to a body composer.

### The M6 architecture (the core principle)

**An analytical sentence = `[verified clause A][licensed relation connective][verified clause B]`, where:**
1. each clause is an existing `strict_verify`-PASSED unit carrying its OWN `[#ev:<id>:<start>-<end>]` token, and
2. the connective is from a CLOSED set and is LICENSED by an existing cross-basket relation engine.

The synthesis asserts NO new free-standing fact — it asserts a RELATION between two already-verified facts, and that relation is gated by the engine. **`strict_verify` still passes iff both atoms pass (the connective carries no token), so the frozen faithfulness engine remains the only hard gate.** This is the only faithfulness-safe way to add analysis depth: *synthesize the RELATION, verify the ATOMS.* It is the same atomic-claim-verification family as the C2 atomic-entailment near-miss from I-faith-001, applied at composition time.

#### LAYER 1 — verified cross-basket analytical composer (the M6 core)

**NEW** `src/polaris_graph/generator/cross_source_synthesis.py`:

```python
LICENSED_CONNECTIVES = {            # closed set; NO factual content
  "agreement": "; consistent with this, ",
  "conflict":  "; in contrast, ",
  "extension": "; extending this, ",
  "neutral":   "; separately, ",
}
def license_relation(cluster_a_id, cluster_b_id, *, edges, equiv_clusters, agree_map):
    # conflict iff a ContradictionEdge joins the pair (claim_graph.ClaimGraph.edges)
    if _edge_between(edges, cluster_a_id, cluster_b_id): return "conflict"
    # agreement iff consolidation_nli / equivalence-cluster says A entails/equiv B
    if _agree(agree_map, equiv_clusters, cluster_a_id, cluster_b_id): return "agreement"
    return "neutral"   # NEVER fabricate "extension"; default to pure juxtaposition
def compose_cross_source_analytical_units(section_baskets, evidence_pool, *,
        writer_fn, verify_fn, edges, equiv_clusters, agree_map):
    # 1. pair baskets in this section sharing a subject-predicate anchor (reuse claim-cluster keys)
    # 2. for each pair build clause_A, clause_B via the EXISTING _per_basket_verified_clause
    #    (each already strict_verify-PASSED, each keeps its own [#ev] token)
    # 3. rel = license_relation(...); connective = LICENSED_CONNECTIVES[rel]
    # 4. sentence = clause_A + connective + clause_B
    # 5. RE-RUN verify_fn (verify_sentence_provenance) PER CLAUSE exactly as
    #    compose_multicited_sentence does (each token lands in its own basket region)
    # 6. fail-closed: if either clause fails re-verify -> DROP the analytical unit,
    #    keep the two atoms as independent single-source sentences (keep-all)
    return units
```

**EDIT** `verified_compose._compose_section_per_basket` (line 942): after the existing per-basket `out` list is built, when `PG_CROSS_SOURCE_SYNTHESIS` is ON, append `compose_cross_source_analytical_units(...)` results (ADDITIVE — unpaired baskets keep their single-source unit; a paired unit and its two atoms co-exist, the existing idx8 seen-span dedup at 959–965 collapses any true duplicate). This fills "Comparative Assessment", "Evidence and Analysis", and per-section comparative paragraphs with genuine compare/contrast.

**EDIT** `relational_quantifier_guard.py`: add a `licensed_relations: set[str]` param — a connective whose licensing engine fired is allowed; every UNLICENSED relational/aggregate predicate is stripped exactly as today (a wrong "in contrast" can never render).

**EDIT** `multi_section_generator.py` (~4254, the `_compose_section_per_basket` call): thread `edges` (from the already-built ClaimGraph — `run_honest_sweep_r3.py` builds `verified_claim_graph_campaign.db` at 11712/14536), `equiv_clusters`, and the `consolidation_nli` `agree_map` (all already computed in the run) into the composer.

#### LAYER 2 — activate + verify-gate the dark `analyst_synthesis` (narrative depth, DRB-II coverage)

**EDIT** `run_honest_sweep_r3.py`: ensure `PG_SWEEP_ANALYST_SYNTHESIS` is ON for the non-clinical path (module default is `"1"`; the smoke env suppressed it — un-suppress) and confirm `multi.analyst_synthesis_text` non-empty (the reasoning-first truncation guard / empty-omit at `analyst_synthesis.py:545` is the likely dark cause; raise `PG_ANALYST_SYNTHESIS_REASONING_MAX_TOKENS` headroom per the §9.1 token-MAX rule).

**EDIT** `analyst_synthesis_deviation_check.py`: add a PROMOTE mode — a synthesis sentence the Sentinel groundedness judge says IS grounded against its cited `[N]` span loses its hedge (KEEP-and-LABEL becomes KEEP-and-PROMOTE for grounded sentences); ungrounded ones stay hedged/labeled. Never drops a sentence, never drops a source — pure label change.

#### Abstract/Conclusion — no new code

`build_abstract`/`build_conclusion` (`abstract_conclusion.py:217/245`) re-lift verbatim from already-strict_verify-PASSED body sentences; once Layer 1 adds verified analytical sentences to the body, the abstract/conclusion automatically gain a comparative headline for free, still faithful-by-identity. The header's "build the entailment gate first" precondition is met because Layer 1 reuses the EXISTING certified relation engines.

#### Rollout

`PG_CROSS_SOURCE_SYNTHESIS` default-OFF for the first canary run, default-ON after the behavioral replay proves units render and re-verify. Manifest canary `cross_source_analytical_units` count must be > 0 when ≥ 2 same-anchor baskets exist (fail-loud on silent no-op).

### M6 risk
1. **Honest dependency:** cross-source analysis REQUIRES ≥ 2 baskets sharing an anchor. In drb_72 consolidation produced almost all single-origin baskets and the one 2-origin basket was the F1 chrome-phantom — so M6 yield depends on F1-STRUCTURAL (chrome screen at basket build) AND on the consolidation engine actually forming multi-source baskets. If the corpus genuinely has single-source claims, the analytical layer correctly emits FEWER units (it must not fabricate a relation). Correct §-1.3 behavior, but **M6 alone will not move the score unless basket consolidation also improves — they ship together.**
2. Relation false-positive: a wrong "in contrast"/"consistent with" is a faithfulness defect even though both atoms verify. Mitigated by fail-closed defaulting to "neutral" juxtaposition whenever the licensing engine does not fire, and by `relational_quantifier_guard` stripping any unlicensed relational predicate.
3. The neutral "; separately," connective risks reading as filler if over-used; cap analytical pairing to anchored pairs only (subject-predicate match) so juxtaposition is never random.
4. Layer 2 reasoning-first truncation: the analyst writer can burn the whole token budget on reasoning and return empty (the documented #1323 trap); the token-MAX headroom flip mitigates but must be verified in the canary, not assumed.
5. DeepTRACE one-sided metric: surfacing conflicts ("in contrast") HELPS one-sidedness, but only if both sides are real verified baskets — never synthesize a fake counter-position.

### M6 test
Behavioral replay harness on THIS run's banked artifacts (`corpus_snapshot.json` + `evidence_pool.json` + the claim graph) — a compose-side change over already-verified atoms is validly replayable from a corpus_snapshot (unlike fetch/truncation fixes), because the atoms already live in `evidence_pool`:
1. ASSERT ≥ 1 "Comparative Assessment" / "Evidence and Analysis" analytical sentence renders carrying TWO distinct `[#ev:...]` tokens from TWO distinct baskets.
2. ASSERT re-running the production `verify_sentence_provenance` per-clause over each composed analytical sentence PASSES (both atoms verify), and that a sentence whose clause B is mutated to cite a foreign span FAILS (engine still gates).
3. FAIL-CLOSED relation test: feed a pair with NO ContradictionEdge and NO agreement → assert connective is "neutral", never "in contrast"/"consistent with"; flip the conflict detector to report an edge → assert it upgrades to "in contrast"; proves the connective is judge-licensed, not free-form.
4. KEEP-ALL test: assert no source/basket present pre-change is absent post-change (the analytical unit is additive; only true-duplicate idx8 collapses).
5. Layer 2: assert `PG_SWEEP_ANALYST_SYNTHESIS` ON yields a non-empty "## Analyst Synthesis" block, and a Sentinel-grounded sentence loses its hedge while an ungrounded one keeps it (no sentence dropped).
6. **Canary / re-smoke:** manifest `cross_source_analytical_units` > 0 on a corpus with ≥ 2 same-anchor baskets; if force-ON and 0 fire, the run logs LOUD (silent-no-op trap). **Final acceptance is a fresh §-1.1 line-by-line read** of the re-rendered "Comparative Assessment" confirming each analytical sentence is two real verified clauses joined by a licensed relation — green tests + Codex APPROVE are necessary but not sufficient (the I-arch-007 "fired-in-output, not in-the-slate" rule).

---

## §6. Build sequencing — what lands together, what needs its own Codex gate + replay harness

Two independent axes drive sequencing: (a) **which files each change touches** (shared-file changes must land in ONE diff with ONE Codex gate for coherence, per §3.0.1); (b) **what kind of run validates it** (fetch-side → fresh front-half on the VM; selection/render/compose-side → banked `corpus_snapshot` replay).

| Wave | Gaps | Files | Validation surface | Codex gate |
|---|---|---|---|---|
| **Wave A (fetch-side, fix-now)** | M3a + M3b | `provenance_generator.py`, `frame_fetcher.py`, `citation_mapper.py`, `nodes/assemble.py` | **FRESH front-half on the VM** (a banked replay CANNOT validate a fetch-side fix) | One gate (M3a+M3b share the bib/fetch path; coherent) |
| **Wave B (selection + render, replayable)** | M5 + F1-structural chrome screen (M6 prereq) | `weighted_enrichment.py`, `multi_section_generator.py`, `run_honest_sweep_r3.py` | **Banked `corpus_snapshot` replay** | One gate. Note M5 + M2 + M6-render all edit `run_honest_sweep_r3.py` near the corroboration block — see coherence note below |
| **Wave C (classify + disclose, replayable, operator opt-in)** | M2 | NEW `document_type_classifier.py`, `tier_classifier.py`, `live_retriever`, `weighted_corpus_gate.py`, `run_honest_sweep_r3.py`, `workforce.yaml` | Banked replay over `corpus_credibility_disclosure.json` + a flag-ON re-smoke | One gate |
| **Wave D (compose-side, biggest)** | M6 Layer 1 + Layer 2 | NEW `cross_source_synthesis.py`, `verified_compose.py`, `relational_quantifier_guard.py`, `multi_section_generator.py`, `analyst_synthesis*.py`, `run_honest_sweep_r3.py` | Banked `corpus_snapshot` replay, then **fresh §-1.1 read** | One gate (Layers 1+2 are one analytical feature) |

**Shared-file coherence note (critical for the orchestrator):** M2 render (§2-E), M5 render (FILE 3), and M6 render all edit `scripts/run_honest_sweep_r3.py` in the `_basket_corroboration_block` / bibliography region (~2478–2740). If these waves are built in parallel worktrees they WILL conflict. Two safe options:
- **Option 1 (recommended):** land Wave B (M5) first as its own gated diff; rebase Wave C (M2) and Wave D (M6) render edits on top so each sees the prior block. Each wave keeps its own Codex gate and replay harness.
- **Option 2:** if speed demands parallelism, isolate each render addition behind its own `active()`/`_env_flag` guard at a DISTINCT append site (M2 reorders the existing block; M5 appends `_cwf_disclosed_block`; M6 appends analytical sentences inside the body composer, not the render script) and reconcile in one final consolidated `run_honest_sweep_r3.py` diff with a single coherence gate. Per the parallel-Codex correction (2026-06-28), bounded-parallel gates are allowed when changes are isolatable; a SINGLE consolidated diff + ONE gate is correct when they SHARE a file.

**Can land together (one gate each):** M3a+M3b (Wave A). M5 internals (Wave B). M2 internals (Wave C). M6 Layer1+Layer2 (Wave D).

**Must have their OWN replay harness:** every wave. M3 needs a FRESH-fetch harness (its own, because a banked replay is structurally blind to a fetch-side fix — the I-wire-014 lesson). M5/M2/M6 each get a banked `corpus_snapshot` replay (compose/select/render-side fixes ARE replayable). M6 additionally needs the fresh §-1.1 read as final acceptance.

**Hard dependency edges:**
- M6 Layer 1 yield depends on **F1-structural chrome screen** (kills the 2-origin chrome phantom so real multi-source baskets form) AND on basket consolidation forming ≥2-origin baskets. Ship F1 + M6 in adjacent waves; do not declare M6 "done" on a corpus with no multi-origin baskets — that is the honest dependency, not an M6 bug.
- M5 and M2 are independent of each other and of M6 (no logic edge), only the shared render file couples them.

---

## §7. §-1.3 confirmation — NONE bolts a hard-drop / weight-floor / cap / target; NONE relaxes the faithfulness engine

| Gap | Mechanism | Hard-drop? | Weight-floor / cap / target? | Touches strict_verify / NLI / D8 / span / provenance? |
|---|---|---|---|---|
| **M2** | Per-citation document-TYPE multiplicative weight (0,1] + genre label, surfaced. Re-ranks display, never excludes. | NO — every source stays in pool/disclosure/bibliography/corroboration list; predatory venue still cited, just re-ranked + labelled. `len(per_source)` invariant (asserted). | NO threshold below which anything is excluded; `min_distinct_journals:12` count-floor NOT read/touched/re-activated; corpus-adequacy gate unchanged; cannot abort a run. | NO — advisory disclosure, same class as existing `credibility_weight`; no per-claim verdict / release decision / span check consumes it. |
| **M3** | Fetch-layer coverage ADD (empty→abstract, no-locator→doi.org). | NO — adds coverage, drops nothing; the DOI is a real id the row already carried; the abstract is verbatim primary text. | NO filter/cap/thinner/target; no source removed; no tier forced. Richest-abstract is a coverage choice among the SAME work's deterministic sources, DOI-consistency-guarded. | NO — newly-landed abstract flows through the UNCHANGED engine; if the generator over-claims, strict_verify still drops it (correct). No Sci-Hub. |
| **M5** | Promotion-eligibility PARTITION → promoted vs disclosed_only (kept + re-surfaced). Routing, not removal. | NO — demoted source stays in `evidence_pool`, `corpus_credibility_disclosure.json`, and a dedicated report block; conservation asserted (`promoted ∪ disclosed == original`). | NO top-N / breadth number / target; promoted count EMERGES from corroboration+credibility. Keys on `credibility_weight`+`verified_support_origin_count`+journal-venue, NEVER on `selection_relevance`; does NOT re-impose the banned B18 relevance floor (keep-all-sort-below-floor-last untouched). | NO — promoted member goes through UNCHANGED strict_verify; demotion was never a faithfulness decision (weight/corroboration are credibility judgments). The OR-with-corroboration leg IS the CONSOLIDATE principle. |
| **M6** | Adds analytical sentences = two verified atoms + a licensed closed-set connective. | NO — additive on top of keep-all single-source units; never removes a source/basket; unlicensed relation falls back to neutral juxtaposition or the two independent verified sentences (keep-all). | NO breadth number forced; analytical yield BOUNDED by real corroboration/conflict the engines find — "breadth emerges, never forced." | NO — none of those files edited. Composer CALLS the production `verify_sentence_provenance` per-clause; connective carries no token; strict_verify passes iff both atoms pass — engine untouched, still the only hard gate. Decides the relation against the whole pair via the EXISTING certified detectors → STRENGTHENS basket faithfulness. Layer 2 is LABEL→PROMOTE only. |

**All four are operator-locked WEIGHT-and-CONSOLIDATE, not FILTER-and-DROP.** Every one is reversible byte-for-byte via a LAW-VI kill-switch. Codex P0 checklist across all four: (1) confirm no OFF-path field is populated; (2) confirm no new disclosed/adjusted value is read by an abort/approval gate (M2 `document_type_adjusted_weight`, M5 `disclosed_only`); (3) confirm conservation (M5 nothing vanishes; M6 keep-all; M2 `len` invariant); (4) confirm the faithfulness engine files are untouched in the diff.

---

## §8. Honest scope / effort per gap

| Gap | Severity | New files | Edited files | Effort | Validation cost | Confidence |
|---|---|---|---|---|---|---|
| **M2** | P0 *only for a journal-only question*; otherwise dormant (default-OFF). | 1 (`document_type_classifier.py`) | 4 + 1 config | Medium. Deterministic, offline, no LLM/network. Most work is the classify truth-table + 4-field plumbing through tier→retriever→disclosure→render. | Cheap — offline replay over the banked 64-row disclosure + one flag-ON re-smoke. | High — signals already computed by OpenAlex; journal-positive test is the proven `is_citeable_journal` predicate. |
| **M3** | P0 coverage (canonical primaries render empty). Two defects, one deterministic-certain (locator), one robustness (abstract). | 0 | 4 | Low–Medium. M3a is a 2-key dict add (near-trivial, certain). M3b mirrors existing `_call_openalex` for S2 + drops one short-circuit. | **Higher** — needs a FRESH front-half on the VM (paid, GPU) because a banked replay is blind to a fetch-side fix. Offline unit tests with injected fake httpx cover the logic first. | High on M3a (deterministic, DOI was always present). Medium on M3b (depends on live API behavior, mitigated by 3-source richest-pick + DOI guard). Honest ceiling: closed-access primaries → abstract only, never full text. |
| **M5** | P1 — junk-blog standalone findings hurt DeepTRACE citation-accuracy/source-quality (the more-winnable board). | 0 | 3 | Low–Medium. One partition function + fail-loud parsers + a render block. Partition already simulated correct on real data (exactly 8 demoted). | Cheap — banked `corpus_snapshot` replay (selection+render side, fully replayable). | High — simulation on real `bibliography.json` already confirms the exact 8-source partition with zero over-demotion. |
| **M6** | P0 for DRB-II analysis (18%) — the biggest structural lift and the highest-value board mover, but the hardest. | 1 (`cross_source_synthesis.py`) | 5 | **High.** New composer architecture (relation-licensing + per-clause re-verify), guard param, claim-graph threading, plus un-darkening + verify-gating `analyst_synthesis`. Most design risk lives here. | Banked replay validates the mechanism; **final acceptance is a fresh §-1.1 line-by-line read** (green tests insufficient). | Medium. The faithfulness model (synthesize relation, verify atoms) is sound and reuses certified engines. The real uncertainty is YIELD: it is gated on F1-structural + basket consolidation actually forming ≥2-origin baskets. M6 ships WITH F1; declaring it done on a single-origin corpus is the trap to avoid. |

**Recommended order by value-per-risk:** M3a (trivial, certain, P0) → M5 (simulated-certain, P1, cheap) → M3b (robustness, needs fresh fetch) → M2 (dormant unless operator opts in) → M6 (biggest, ship with F1-structural, fresh §-1.1 read as the gate). M3 and M5 are the genuine fix-now set; M2 is operator-gated opt-in; M6 is the structural headliner that must not be declared done on a corpus that cannot exercise it.