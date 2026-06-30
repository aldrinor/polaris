All anchors confirmed (with corrections folded in below). Here is the consolidated plan.

---

# I-deepfix-001 — Consolidated Codex-Ready Fix Plan: drb_72 HARD Defects + Scoreboard Gaps

Scope: the HARD defects (F1 phantom corroborator, F2/F3 quantified provenance/citation binding, B2 credibility mis-tiering, F4 DOI-404 recovery, DEFER-4 residual chrome) plus the structural gaps the scoreboard critic surfaced. The already-designed easy fixes (FIX-1 chrome predicate done+applied, FIX-2 filler, FIX-3 repetition, DEFER-1 off-topic) live in `C:/POLARIS/.codex/I-deepfix-001/MASTER_FIX_PLAN.md` — referenced, not redone here.

All line numbers below were re-verified against the working tree. Two anchors in the source briefs were stale and are corrected here: `weighted_enrichment._contains_forensic_chrome` is **line 999** (brief said 937); the credibility-tiering merge line is **485** (brief said 481).

---

## Part 1 — Each hard fix: file, change, isolated test, severity, decision class

### F1 — Phantom corroborator in the only "multi-source" basket  — **P0** — TRACED_NEUTRAL_FIX_NOW

The report's single "2 verified independent source(s)" claim (basket `clm_8aa6e2783e4fba96`, Acemoglu task-framework) is corroborated by a phantom: `ev_044` (ewadirect ACE-proceedings PDF), whose corroborating span is license chrome ("under the terms of the Creative Commons Attribution License 4.0") and which earns **no** numbered bibliography entry. Remove it and the report has zero genuine multi-source claims.

Root cause (two disagreeing surfaces):
- Inline `[N]` path (`provenance_generator.py`, `resolve`/`build_bibliography_with_baskets`) correctly denied `ev_044` a number — its chrome span fails `corroborator_span_grounds_sentence`, so it is absent from the 26-entry bibliography.
- The per-claim block renderer trusts a pre-bibliography count. `scripts/run_honest_sweep_r3.py:2523` reads `count = int(basket.get("verified_support_origin_count") or 0)`; that field is computed upstream in `synthesis/credibility_pass.py:843` (`verified_support_origin_count = len(verified_origin_ids)`) from each member's **isolated** `span_verdict == "SUPPORTS"` — and chrome self-entails (text == its own span), so `ev_044` counts.

**Fix — `scripts/run_honest_sweep_r3.py`, inside `_basket_corroboration_block(bibliography)` (def at line 2478):**

(a) At function top, derive the cited set from the argument (no new plumbing):
```python
_biblio_eids = {str(b.get("evidence_id") or "") for b in bibliography if str(b.get("evidence_id") or "")}
_biblio_urls = {str(b.get("url") or "") for b in bibliography if str(b.get("url") or "")}
```
(b) Add a LAW-VI default-ON kill-switch + predicate:
```python
def _biblio_present_enabled():
    return os.environ.get("PG_CORROBORATION_BIBLIO_PRESENT", "1").strip().lower() in ("1","true","on","yes","enabled")
def _is_biblio_present(m):
    return str(m.get("evidence_id") or "") in _biblio_eids or str(m.get("source_url") or "") in _biblio_urls
```
(c) Immediately after `verified`/`weak` are built (the `members = basket.get("supporting_members") or []` block at line 2512 and the verified/weak split), when the gate is ON, filter and recompute (replacing the line-2523 trust-the-field read):
```python
if _biblio_present_enabled():
    verified = [m for m in verified if _is_biblio_present(m)]
    count = len({str(m.get("origin_cluster_id") or m.get("evidence_id") or "") for m in verified})
else:
    count = int(basket.get("verified_support_origin_count") or 0)
```
(d) Phantom-only edge: when the gate is ON and `not verified and not weak and not contested`, `continue` (skip the basket header; the sources still live in the numbered Bibliography).

Result: `clm_8aa6e2783e4fba96` renders "1 verified independent source(s)" with only the aeaweb SUPPORT line; `ev_044` drops from the count and the SUPPORT list.

Isolated test: `C:/POLARIS/.codex/I-deepfix-001/smoke_forensics/f1_phantom_corroborator_test.py` — offline against the real `bibliography.json`. apply_fix False → count 2 `[aeaweb, ewadirect]`; True → count 1 `[aeaweb]`. Over-correction proven two ways: across all 24 baskets / 25 ENTAILMENT_VERIFIED members, exactly one member (`ev_044`) is not bibliography-present and is filtered; only the phantom basket's surface changes — all 23 other baskets byte-identical.

§-1.3: render/provenance-binding only. The faithfulness engine (`strict_verify` / NLI / 4-role D8 / span-grounding / `provenance`) is untouched. The "bibliography-present" set is exactly the set the report cites; a verified member excluded here is exactly one whose span grounded no cited sentence (inline grounding already denied it a `[N]`). It REDUCES an inflated count (2→1), never inflates breadth; no real corroborator is hard-dropped. Reversible byte-for-byte via `PG_CORROBORATION_BIBLIO_PRESENT=0`.

---

### F1-STRUCTURAL (M1 from the critic) — Chrome contaminates the basket/claim-cluster layer, UPSTREAM of consolidation — **P0** — TRACED, FAITHFULNESS-ADJACENT (Codex-gate with extra care; not an operator decision because it only strengthens)

The critic read `bibliography.json` basket [1] directly: the basket earning `verified_support_origin_count: 2` is chrome corroborated by chrome from a **different** paper. `claim_text` is a truncated PDF running-header/DOI fragment (`"i=10.1257/jep.33.2.3 ... Daron Acemoglu and Pascual Restrepo 4 Journal of Economic Perspectives ..."`); member 1's `direct_quote` is the same header chrome; member 2 (`ev_044`) is the CC-license footer. The consolidation engine matched two pieces of page-furniture across two papers and certified them as one claim with two origins.

This is the deeper cause behind F1 and behind A1–A10 (chrome rendered as claims) and A7 (chrome as a basket TITLE). The render-side F1 fix above makes the **rendered** report clean, but the stored artifact and the basket count stay contaminated, and any future report can re-grow a chrome×chrome basket.

**Fix — run the chrome predicate at claim-cluster / basket build, before `verified_support_origin_count` is computed, then recompute the count from survivors.** Concretely: at the point in `synthesis/credibility_pass.py` (around the `verified_origin_ids` build at line 843) where members are admitted to a basket, screen each member's `direct_quote` and the cluster's `claim_text` through the existing shared predicate `weighted_enrichment.is_render_chrome_or_unrenderable` (public wrapper over `_contains_forensic_chrome` at line 999). A member whose span is chrome is excluded from `verified_origin_ids` (kept in the pool + disclosure, never deleted). Gate default-ON via a new `PG_BASKET_CHROME_SCREEN` kill-switch.

Isolated test: replay the real `bibliography.json` clusters offline; assert basket `clm_8aa6e2783e4fba96` recomputes to `verified_support_origin_count == 1` after screening, and assert no non-chrome basket loses a member.

§-1.3 / faithfulness note: this touches the consolidation/credibility layer, so it is faithfulness-ADJACENT, not faithfulness-neutral. It only ever REMOVES a chrome span from a corroboration count — it strengthens faithfulness and cannot relax a gate or inflate breadth. Per the operator rule (HOLD only to relax a gate or override a locked gate), a strengthening basket fix is fix-now, but it needs the extra Codex care a consolidation-layer change always gets, plus a behavioral replay harness proving `collapsed`/count effects appear in real output. **Recommendation: ship the render-side F1 in the required-before-paid set; ship F1-STRUCTURAL in the same diff if the replay harness is green, else as the immediate fast-follow. The two are complementary, not either/or.**

---

### F2 — Quantified provenance span points at non-numeric text — **P0** — TRACED_NEUTRAL_FIX_NOW

`quantified_model.json` records `productivity_gain_avg_pct=15%` at `literal_span [40,43]`, but `brynjolfsson direct_quote[40:43]="lfs"` (mid-word). The real "15%" is at offset 485.

Root cause — `src/polaris_graph/synthesis/tradeoff_modeler.py:814-817`, `build_quantified_spec`. `located = _locate_unique_literal(ev_text, value)` returns None when "15%" is non-unique in the 25 000-char quote (offsets 485/2071/4602). The fallback `_locate_unique_literal(str(dp.get("context","")), value)` then returns offsets **relative to the ~83-char context window** (40,43), which are stored verbatim as `literal_start/end` but read downstream as offsets into the full `direct_quote`.

**Fix — replace the context fallback (lines 814-817) with a version that translates context-window offsets into the evidence-text frame and fail-closes if it cannot anchor uniquely:**
```python
ev_text = _evidence_text(ev_row)
located = _locate_unique_literal(ev_text, value)
if located is None:
    # F2 (#1344): literal non-unique in full ev_text (e.g. "15%" x3). Disambiguate
    # via the datapoint context window, but TRANSLATE context-relative offsets into
    # the ev_text frame so literal_start/end index the SAME string every consumer reads.
    ctx = str(dp.get("context", ""))
    ctx_located = _locate_unique_literal(ctx, value)
    if ctx_located is not None and ev_text and ctx:
        anchor = ev_text.find(ctx)
        if anchor >= 0 and ev_text.find(ctx, anchor + 1) == -1:   # context unique => unambiguous
            _lit, _cs, _ce = ctx_located
            if ev_text[anchor + _cs: anchor + _ce] == _lit:
                located = (_lit, anchor + _cs, anchor + _ce)
if located is None:
    return _reject(f"no_unique_literal_span:{name}:{ev_id}")
literal, lstart, lend = located
```

Isolated test: `C:/POLARIS/.codex/I-deepfix-001/scratch_f2f3_test.py` — offline on the real `evidence_pool.json`. Asserts current path → (15%,40,43) with `ev_text[40:43]=="lfs"`, fixed path → (15%,485,488) with `ev_text[485:488]=="15%"`; controls 30% (unique) and `ev_030` 14% unchanged. All pass.

§-1.3: pure span-grounding honesty. When context cannot be uniquely anchored it fail-closes to the **existing** `no_unique_literal_span` reject — never fabricates a span, never relaxes a gate. Faithfulness engine untouched.

---

### F3 — Quantified `[N]` citations bound to the wrong sources — **P1** (combined with F2 → P0 surface) — TRACED_NEUTRAL_FIX_NOW

`report.md` line 140 cites `[1][2]` (= Acemoglu/Autor in the global bibliography) for inputs that came from `ev_030` (MIT Sloan) + `brynjolfsson`.

Root cause — the quantified section is assembled outside the multi-section bibliography pipeline. `run_quantified_section` (`synthesis/quantified_analysis.py:642`) builds a fresh section-LOCAL `ev_to_num` starting at 1 and DISCARDS the returned biblio. The caller appends `_q_section_md` straight into `sections_concat` (`scripts/run_honest_sweep_r3.py:12629`) with no remap — unlike normal `SectionResult`s, which pass through `multi_section_generator._remap_section_markers_to_global`. So local `[1][2]` collide with global `[1]=Acemoglu`, `[2]=Autor`; and `ev_030` is absent from the global bibliography entirely.

**Fix — two parts:**

(1) `synthesis/quantified_analysis.py`, `run_quantified_section`: surface the local biblio. After the `rendered, _biblio = ...` call (line ~642) add `telem["section_biblio"] = _biblio` (additive; byte-identical when unused).

(2) `scripts/run_honest_sweep_r3.py`, before the append at line 12629 (`sections_concat += "\n\n" + _q_section_md`), remap local→global and fold any missing input source into `multi.bibliography`:
```python
import re as _re
_ev2g = {b.get("evidence_id"): b.get("num") for b in (multi.bibliography or [])}
_next = (max([b.get("num", 0) for b in (multi.bibliography or [])] or [0]) + 1)
_local = _quantified_telemetry.get("section_biblio") or []
for _e in _local:
    _ev = _e.get("evidence_id")
    if _ev and _ev not in _ev2g:
        _row = _q_ev_pool.get(_ev, {})
        multi.bibliography.append({"num": _next, "evidence_id": _ev,
            "url": _row.get("source_url", ""), "tier": _row.get("tier", ""),
            "statement": _row.get("statement", "")})
        _ev2g[_ev] = _next; _next += 1
_l2g = {_e.get("num"): _ev2g.get(_e.get("evidence_id")) for _e in _local}
def _qrepl(m):
    g = _l2g.get(int(m.group(1)))
    return f"[{g}]" if g else m.group(0)
_q_section_md = _re.sub(r"\[(\d+)\]", _qrepl, _q_section_md)
```
This mirrors `_remap_section_markers_to_global` and runs before `_render_bibliography_lines` so newly-folded sources appear in References.

Isolated test: same `scratch_f2f3_test.py` + the shell simulation on the real `bibliography.json` — `brynjolfsson` local[2]→global[6]; `ev_030` local[1]→new global[27] appended with the real MIT Sloan URL; `"[1][2]"`→`"[27][6]"`.

§-1.3: citation-binding correction. Binds rendered `[N]` to the evidence_ids the inputs actually came from and ADDS a real input source (`ev_030`, already in `evidence_pool`) to the bibliography. Never removes a corroborator, never promotes an unverified unit, no cap/thin/target. Faithfulness engine untouched.

---

### B2 — Off-topic Russian cosmetics paper mis-tiered T1 / weight 0.95 — **P0** — TRACED_NEUTRAL_FIX_NOW

`ev_061` (`doi.org/10.26163/gief.2025.70.51.048`, Cyrillic, off-topic) is tiered T1 at weight 0.95 in `corpus_credibility_disclosure.json`.

Root cause — the W8 GLM credibility tiering produced the T1 (run log: `tiered via GLM ... fallback=0`), NOT a DOI allowlist and NOT the rules-floor. OpenAlex returned empty venue/source_type/pub_type, yet the GLM still returned T1 from a bare DOI + scholarly title. The deterministic rules-floor alone classifies this exact signal as UNKNOWN (host not on `PEER_REVIEWED_JOURNAL_DOMAINS`, prefix `10.26163` not allowlisted, no resolved venue). So the GLM overrode a correct low tier, and `classify_sources_llm_tiering` has no backstop to cap an LLM top-tier verdict that no venue signal supports.

**Fix — `src/polaris_graph/retrieval/credibility_llm_tiering.py`, gated by new `PG_TIER_REQUIRE_VENUE_CORROBORATION` (default "1"):**

(A) Deterministic venue-corroboration backstop. Import `_is_known_scholarly_venue` from `tier_classifier` (already imports `_classify_source_tier_rules`). Add:
```python
_UNCORROBORATED_TOP_TIERS = {TierLevel.T1, TierLevel.T2}
def _cap_uncorroborated_top_tier(llm_res, signals, floor_res):
    if (llm_res is not None and _venue_corroboration_required()
            and llm_res.tier in _UNCORROBORATED_TOP_TIERS
            and not _is_known_scholarly_venue(signals)):
        return floor_res
    return llm_res
```
In the gather loop at **line 485**, replace `out.append(llm_res if llm_res is not None else floor_results[idx])` with:
```python
chosen = _cap_uncorroborated_top_tier(llm_res, signals_list[idx], floor_results[idx])
out.append(chosen)
```
Emit one LOUD log line when a cap fires (GLM tier → floor tier + url) so it is disclosed, not silent.

(B) Prompt hardening in `_PROMPT` (lines 107-123): append "T1 and T2 REQUIRE a NAMED peer-reviewed venue or recognized publisher. Do NOT infer T1/T2 from a DOI, a URL, or an academic-sounding title alone. If venue and source_type are empty, or the venue is unrecognized/obscure, classify as T4 (peer-reviewed but unverified venue) or lower."

Result: `ev_061` drops T1/0.95 → UNKNOWN/0.20; a genuine corroborated journal (the corpus's real Wiley T1, `onlinelibrary.wiley.com`) keeps T1/0.95.

Isolated test: `scratchpad/b2_venue_corroboration_test.py` — offline on the real offender signals. (1) offender GLM=T1, corroborated=False, floor=UNKNOWN → capped, weight 0.95→0.20; (2) the genuine Wiley journal keeps T1/0.95 (no over-correction); (3) a GLM low tier (T6) on the same offender passes through unchanged (cap only lowers top tiers, never promotes). All pass.

§-1.3: credibility WEIGHT correction, not a faithfulness change and not a hard-drop. The source stays in `evidence_pool` and the disclosure at the honest lower weight. The backstop only LOWERS an uncorroborated top-tier LLM verdict to the deterministic floor; never raises a tier, never removes a source, never gates release. All three §-1.3 prongs hold (weight-not-filter, consolidate-not-drop, basket-faithfulness untouched). Reversible via the env kill-switch.

---

### F4 — DOI-404 registry error page adopted as upgraded full text — **P1** — TRACED_NEUTRAL_FIX_NOW

The B02/B04 forced-Zyte re-fetch "recovered" a doi.org "DOI Not Found" page (~821 chars of real English) and adopted it unchanged as full text (`ev_057`, DOI `10.5555/2485288`). Recovery measured length only (`is_content_starved`), not document-vs-error-page.

Root cause — `src/polaris_graph/retrieval/live_retriever.py:5651`, `_usable = bool(_refetched) and not is_content_starved(_refetched)`. `is_content_starved` (line 3494) flags only <200 chars / CAPTCHA / PDF-metadata / low-alpha — no rule for a registry "not found" page. None of `is_error_shell_text`, `is_block_page_or_stub`, `classify_block_page` caught it either (verified live).

**Fix — two surgical, gated changes:**

(1) `src/tools/access_bypass.py`: new `is_registry_error_page(text)` + `registry_error_guard_enabled()` (kill-switch `PG_REGISTRY_ERROR_GUARD`, default ON), backed by `_REGISTRY_ERROR_SIGNATURES` = full registry-proxy phrases that never occur in a real article body: `"this doi cannot be found in the doi system"`, `"report this error to the responsible doi registration agency"`, `"the doi has not been activated yet"`, `"doi name not found"`, `"this doi has not been registered"`, `"this handle is not registered"`, `"handle not found"`. Lowercased whole-substring match.

(2) `live_retriever.py`: new `_recovered_content_error_class(text)` that delegates to `is_registry_error_page`, `is_error_shell_text`, `classify_block_page` (per-URL fail-OPEN with a LOUD warning if the screen import fails, never silent). The B02/B04 RECOVERED branch (around line 5651) becomes:
```python
_usable = bool(_refetched) and not is_content_starved(_refetched)
_recovered_error = _recovered_content_error_class(_refetched) if _usable else ""
# adopt the span ONLY if (_usable and not _recovered_error)
```
An error/registry/block page falls into the existing degraded `else` branch (`_starved=True`, row stays a disclosed gap, NOT adopted) with a distinct RECOVERED-ERROR-PAGE warning.

Isolated test (ran offline on the real `ev_057` 821-char page): `is_content_starved=False` (old gate adopted it); `is_registry_error_page=True`; `_recovered_content_error_class=="doi_registry_error"`. Over-correction guard: 10 longest real article bodies → 0 false positives; a synthetic 711-char prose body that repeatedly says "DOI was not found", "Crossref", "handle.net proxy" → False. Kill-switch `PG_REGISTRY_ERROR_GUARD=0` → byte-identical legacy adopt. Both files `py_compile` + import clean. Latest-doc: the doi.org proxy "DOI Name Not Found" page text matches `ev_057` verbatim.

§-1.3: stops a fetch FAILURE from being adopted as grounding; the row keeps the exact disposition an unrecovered row already gets (degraded / disclosed gap, NOT deleted). A registry "not found" page is never a real corroborator, so refusing to adopt it is not a §-1.3 hard-drop. Faithfulness engine untouched. Reversible.

Adjacent note for Codex: the OA-resolver timeout-recovery adopt (`live_retriever.py:3168`, `if _oa_content:`) and the initial fetch path do **not** yet run `is_registry_error_page`. A follow-up could route it through `is_content_starved` itself to close all three at once, but that widens a broadly-used predicate, so it was kept out of this surgical F4.

---

### DEFER-4 — Residual page-furniture rendered as cited claims (A14/A15/A16) — **P1** — TRACED_NEUTRAL_FIX_NOW

`report.md` lines 85-87 render as cited claims: A14 publisher paywall ("Get full access to this article / View all access and purchase options for this article." `[20]`); A15 IZA cover masthead ("DISCUSSION PAPER SERIES IZA DP No. 14409 ... Any opinions expressed in this paper are those of the author(s) and not those of IZA." `[19]`); A16 PDF footnote run ("See OECD (2020), Table 3.3. 14Tate and Yang (2016) analyze ... 7 Post-merger restructuring." `[19]`).

Root cause — the shared render-side predicate `src/polaris_graph/generator/weighted_enrichment.py::_contains_forensic_chrome` (**line 999**, reached via `is_render_chrome_or_unrenderable` at the render-seam chokepoint) had no rule for these three furniture classes, so they self-entail `strict_verify` and render.

**Fix — `weighted_enrichment.py`:**

(1) After `_is_foreign_journal_masthead` (line 848) add three precision regexes + a helper:
```python
_PAYWALL_ACCESS_RE = re.compile(r"\bget\s+full\s+access\s+to\s+this\s+article\b|\bview\s+all\s+access\s+and\s+purchase\s+options\b|\bpurchase\s+options\s+for\s+this\s+article\b", re.IGNORECASE)
_WORKING_PAPER_COVER_RE = re.compile(r"\bdiscussion\s+paper\s+series\b|\bany\s+opinions?\s+expressed\s+in\s+this\s+paper\s+are\s+those\s+of\s+the\b", re.IGNORECASE)
_FOOTNOTE_GLUE_RE = re.compile(r"\b\d{1,2}[A-Z][a-z]{2,}\s+(?:and|et\s+al\.?|\(\d{4}\))|\bSee\s+[A-Z][A-Za-z]+(?:\s+(?:and|&)\s+[A-Z][A-Za-z]+)?\s*\(\d{4}\)\s*,?\s+Table\s+\d")
def _is_residual_chrome_furniture(text):  # True if any of the three search
    ...
```
The `_FOOTNOTE_GLUE` `[A-Z][a-z]{2,}` excludes all-caps ("4IR", "23 OECD") and lowercase ("165million"), so only a footnote digit welded to a Mixed-case surname matches.

(2) Inside `_contains_forensic_chrome` (line 999), immediately after the FIX-1 cookie/DOI/masthead branch:
```python
if _is_residual_chrome_furniture(s):
    return True
```

Isolated test: `scratchpad/test_deepfix_defer4_chrome.py` (pure predicate). MUST_FLAG = the 4 real furniture strings verbatim from `report.md` → all flagged. MUST_KEEP = 8 real clean units from the same report incl. over-strip probes (A17 "10% to 15% of jobs could be eliminated", A18 ChatGPT-3.5 inflection, "extends it to 23 OECD countries", "Researchers were granted full access to administrative records", "As reported in Table 2", "The discussion in this paper builds on...") → all kept. Result: `MUST_FLAG: 4  MUST_KEEP: 8  PASS`. Regression: `pytest test_i_wire_013_render_seam_iter3a.py test_iwire013_sec11_forensic_audit.py test_iwire017_truncation_orphan.py` = 43 passed.

§-1.3: render/compose INPUT hygiene (FLAG-not-DROP) — a flagged unit is withheld from the rollup; the source row stays in `evidence_pool` + disclosure. The three classes are page furniture / dead-fetch shells, never corroborators. CRITICAL over-strip guard: A17/A18/A19/E1 are real findings welded to a small artifact — a whole-unit drop there would delete a real finding (violates the operator-locked over-strip law), so they are deliberately left to the render-seam REPAIR / truncation legs, not this drop predicate. A20 (`eloundou_gpts_are_gpts`) is a bibliography-rendering bug, out of lane. Reversible under the existing `PG_RENDER_CHROME_SCREEN` kill-switch.

---

## Part 2 — REQUIRED-before-paid set for a §-1.1-clean + high-scoreboard re-smoke

A paid re-smoke must not run until these land, because they are the defects a §-1.1 line-by-line read will fail on the surfaces POLARIS most needs to win:

| Order | Fix | Severity | Why it gates the paid run |
|---|---|---|---|
| 1 | **F1 render-side** + **F1-STRUCTURAL** | P0 | The report's ONLY multi-source claim is currently chrome×chrome. Without both, the corroboration block — POLARIS's intended DeepTRACE differentiator — fails a §-1.1 read. F1-STRUCTURAL also cleans the stored artifact and prevents regrowth; ship it in-diff if the replay harness is green, else immediate fast-follow. |
| 2 | **F2** (+**F3**) | P0 | A quantified claim is attributed to the wrong sources with a provenance span pointing at non-numeric text. Fabricated-provenance must be gone before spend. |
| 3 | **B2** | P0 | An off-topic non-English paper at top credibility tier (0.95, equal to NEJM) corrupts the corpus-credibility disclosure and the weighted-mean signal feeding DeepTRACE source-quality/one-sided. |
| 4 | **DEFER-1 off-topic** (already designed/gated/tested in MASTER_FIX_PLAN) + **DEFER-4 residual chrome** | P1 | Cited page-furniture and off-topic prose directly lower DeepTRACE citation-accuracy. DEFER-1 already exists — promote it into this run. |
| 5 | **F4** | P1 | A DOI-404 error page adopted as citable text. Lower volume but it is fabricated grounding. |
| 6 | **FIX-2 filler** (C1 unit-free scalars) | P1 | Already designed; suppress invented `2.14286`/`5`/`1`. |

FIX-1 chrome predicate (done+applied) and FIX-3 repetition are already in the tree per MASTER_FIX_PLAN — verify they are still applied on the branch before the run.

Build discipline: these touch a shared set of files (`run_honest_sweep_r3.py` for F1+F3; `weighted_enrichment.py` for DEFER-4; `tradeoff_modeler.py` for F2; `credibility_llm_tiering.py` for B2; `live_retriever.py`+`access_bypass.py` for F4; `credibility_pass.py` for F1-STRUCTURAL). Group by file-owner, then ONE consolidated Codex diff gate over the combined diff (coherence), per §3.0.1. All on the VM (A100-80GB / ssh), never local, per the heavy-runs-on-VM rule.

---

## Part 3 — §-1.3 faithfulness confirmation (explicit, per fix)

None of these relaxes the faithfulness engine and none hard-drops a real corroborator.

- **F1 (render):** does not edit `strict_verify` / NLI / 4-role D8 / span-grounding / `provenance`. Brings the block into agreement with the inline-citation reality. REDUCES an inflated count 2→1; cannot inflate breadth.
- **F1-STRUCTURAL:** faithfulness-ADJACENT (consolidation layer) but only REMOVES chrome from a corroboration count — strengthens, never relaxes. Extra Codex care + behavioral replay harness required; not an operator decision because it cannot relax a gate.
- **F2:** span-grounding honesty; fail-closes to the existing `no_unique_literal_span` reject. Never fabricates a span.
- **F3:** citation-binding; ADDS a real input source to the bibliography, removes no corroborator, promotes no unverified unit.
- **B2:** credibility WEIGHT only; source stays in pool + disclosure at the honest lower weight; backstop only LOWERS uncorroborated top tiers, never raises, never drops, never gates release. All three §-1.3 prongs hold.
- **F4:** refuses to ADOPT a fetch-failure page as grounding; row keeps the same disclosed-gap disposition; a registry error page is never a corroborator.
- **DEFER-4:** FLAG-not-DROP render hygiene; source row stays in pool; over-strip guard deliberately leaves real-finding-bearing units to the REPAIR/truncation legs.

Every fix is gated by a default-ON LAW-VI kill-switch for byte-identical revert. The only hard gate (the faithfulness engine) is edited by none of them.

---

## Part 4 — Scoreboard-impact ordering (which fixes buy the most DeepTRACE / DRB-II score)

### DeepTRACE (citation faithfulness — the more winnable board), in fix order
1. **Chrome rendered as cited claims (A1–A10 + F1-STRUCTURAL).** Highest volume; a GPT-5 judge reads every cookie-banner/DOI-404/masthead sentence as an unsupported junk citation. Place the chrome predicate UPSTREAM at basket/claim-cluster build (F1-STRUCTURAL), not only at the two render seams. This single placement collapses A1–A10 + the F1 phantom + A7 together and protects the corroboration block.
2. **Fake corroboration basket (F1).** Kills citation-accuracy at the worst spot — the one multi-source claim, exactly POLARIS's differentiator. Same lever as #1; must re-run `verified_support_origin_count` after the screen (F1 render does this at render; F1-STRUCTURAL does it in the artifact).
3. **Off-topic + non-journal cited prose (B1–B5).** Hits source-quality + relevance. DEFER-1 (semantic off-topic label) is the right, already-built lever — promote it.
4. **Invented unit-free scalars (C1).** FIX-2 suppression.
5. **Citation-accuracy residue (C1/F3 mis-binding, no-locator [5]/[7], DOI-404 [25], raw-slug locator A20).** Each is a citation pointing to the wrong or no source.

### DeepResearch-Bench-II (coverage / depth — harder), structural gaps
These are NOT on the 40-item list and are the deepest score losers; they are composition-architecture work, larger than a span fix:
- **M2 — journal-only SCOPE VIOLATION as a first-class class.** The user required English-language journal ARTICLES only; the cited corpus is dominated by blogs, consultancy, university news, WEF/IZA reports, and a predatory open-access venue (T7) that actually LEADS the Corroborated Weighted Findings. Distinct from off-topic (many are on-topic but the wrong document TYPE). Needs a venue-TYPE weight/gate for the journal-only template — design carefully, do NOT bolt a weight floor (§-1.3-sensitive: keep + disclose, never hard-drop). **NEEDS_OPERATOR_DECISION** (template policy + §-1.3 surface).
- **M3 — two canonical primary PDFs ([5] acemoglu_restrepo_robots_jobs, [7] eloundou GPTs-are-GPTs) produced NO content** ("no resolvable URL/DOI locator") while cookie banners rendered full prose. This is the coverage tragedy: the funnel surfaced furniture and dropped the best sources (tier mix T1=16%/T3=3% vs expected T3 35-65%, T7=17%). Track as a fetch/extraction-coverage defect on those two PDFs. **TRACED, fetch-layer — fix-now-eligible** once the specific fetch failure is reproduced.
- **M5 — near-zero-weight on-topic single-origin non-journal sources still emit standalone cited claims** (cognifit blog [21] weight 0.03; several at 0.00). DEFER-1 keys on off-topic only. A cite-surface treatment for single-origin near-zero-weight non-journal sources would lift source-quality but is §-1.3-sensitive (keep + disclose, do NOT hard-drop / do NOT bolt a weight floor). **NEEDS_OPERATOR_DECISION.**
- **M6 — no analytical-synthesis path exists at all** (every body sentence is a verbatim single-source lift; "Comparative Assessment" is an empty stub; Abstract/Conclusion are re-lifts). This is the deepest DRB-II analysis-depth (18% weight) failure and a composition-architecture gap, not a span bug. **NEEDS_OPERATOR_DECISION** (scope of a composition rebuild).

### Net recommendation
Promote one structural fix above all the span patches: **run the chrome predicate UPSTREAM at claim-cluster / basket build and recompute origin counts (F1-STRUCTURAL).** It kills A1–A10 + F1 + A7 together and protects the corroboration block, which is the single surface POLARIS most needs to win on DeepTRACE. Then, in order: DEFER-1 off-topic + the F2/F3 quantified binding + B2 credibility backstop in the required-before-paid diff; then FIX-2 filler; then the citation-accuracy residue. The render-seam-only FIX-1 as currently scoped improves the body but leaves the corroboration block and the basket counts contaminated — a re-smoke would still fail a §-1.1 read on that one surface — which is why F1 render + F1-STRUCTURAL must ship together (or render now, structural as the immediate fast-follow).

The DRB-II coverage gaps (M2/M3/M5/M6) do not gate the paid re-smoke for citation-faithfulness, but M3 (the two dropped canonical PDFs) should be reproduced and fixed before any coverage claim, and M2/M5/M6 each need an operator decision because they touch template policy, the §-1.3 keep-and-disclose surface, or a composition rebuild.