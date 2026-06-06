HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Required output schema (YAML, machine-parsed — last `verdict:` line wins)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Loose verdict prose without this schema is rejected — emit the schema.

---

## What this diff does (#1133, I-ready-017, tier_classifier statistical-agency T3)

ADD a `STATISTICAL_AGENCY_DOMAINS` frozenset and a new `R2b_statistical_agency`
rule so national/international statistical & data agencies (BLS, OECD, ILO,
Eurostat, StatCan, World Bank, IMF, Federal Reserve, FRED, Census) are
classified **T3** — the workforce protocol's primary required evidence tier.

**The bug it fixes (drb_72 `abort_corpus_approval_denied`):**
`config/scope_templates/workforce.yaml` requires T3 at 35-65% as the PRIMARY
quantitative tier (StatCan / BLS / OECD / ILO / Eurostat). In the live corpus:
- `bls.gov` congressional-report URL → `R11_openalex_preprint_or_repo` (T4)
  because OpenAlex returned `publication_type=preprint`, `source_type=repository`.
- `bls.gov` MLR article URL → `R9_openalex_narrative_review` (T4) because
  OpenAlex said article+journal and the title tripped a narrative-flavor marker.
- `oecd.org` / `ilo.org` (.org, on no domain set) → `no_rule_matched` (UNKNOWN).
Net: **T3 = 0%** → corpus approval denied. The new rule is placed BEFORE
R9/R10/R11 (the OpenAlex demotion paths) and AFTER the R2a/R2b denylist
demotions, so a denylisted domain can never be laundered up to T3.

It is classified **T3 (government/regulatory/authoritative-data tier)**, NOT T1
primary-research-paper credit. This is the faithfulness-safe choice.

## FAITHFULNESS-RELEVANT (CLAUDE.md §-1.1)

The tier_classifier is **shared across clinical AND non-clinical domains**. A
regression here could mis-tier clinical evidence. This is why the regression
guards below matter.

## KEY REVIEW POINTS — please verify each

(a) **No clinical-domain tiering regression.** Does the new rule change tiering
    for ANY clinical domain? The diff adds a frozenset + one rule that only
    fires on `_domain_matches(domain, STATISTICAL_AGENCY_DOMAINS)`. Confirm none
    of these domains overlaps clinical handling such that clinical sources move
    tier. (Test `test_clinical_regulatory_domains_still_t3` guards fda.gov +
    ema.europa.eu.)

(b) **Precedence correctness.** The rule is placed in `_classify_source_tier_rules`
    AFTER the denylist demotions (R2a/R2b) and BEFORE R9/R10/R11. Verify:
    (i) statistical agencies are NOT demoted by a downstream content/path T4 rule
    (R9/R11) — i.e. the new rule's early `return result` actually pre-empts them;
    (ii) a denylisted domain cannot be laundered up to T3 by this rule (the
    denylist demotions run first and also `return`); (iii) the R1 stub rule
    (<1000 chars → T7) still fires BEFORE the stat-agency rule (test
    `test_stat_agency_stub_still_t7` asserts a 300-char bls.gov page stays T7).

(c) **Domain-set accuracy / no over-broad elevation.** Are all entries genuine
    statistical/data agencies (not generic .org/.gov that would over-elevate)?
    Confirm a generic .org with no other signals does NOT get promoted to T3
    (test `test_generic_org_is_not_forced_to_t3`). Check `_domain_matches`
    semantics — is it exact-or-parent-suffix match (so `bls.gov` matches
    `www.bls.gov` but NOT some unrelated `notbls.gov`)? Flag any entry that is
    too broad (e.g. would `ec.europa.eu` over-match? the comment notes it
    already parent-matches europa.eu in REGULATORY_DOMAINS and is tier-harmless).

(d) **Full existing tier test suite still green.** The change adds a new
    frozenset and an early-returning rule. Confirm nothing in the existing
    `_classify_source_tier_rules` ordering or the existing domain sets is
    mutated (it is purely additive). The new test file exercises the two
    signal-bearing live-dump cases (preprint/repository, article+journal+
    narrative title) to prove the rule fires before R9/R11.

## The diff under review

diff --git a/src/polaris_graph/retrieval/tier_classifier.py b/src/polaris_graph/retrieval/tier_classifier.py
index d9446a94..93eac705 100644
--- a/src/polaris_graph/retrieval/tier_classifier.py
+++ b/src/polaris_graph/retrieval/tier_classifier.py
@@ -380,6 +380,44 @@ GOV_AGENCY_DOMAINS = frozenset({
     "hrsa.gov",       # Health Resources & Services Admin
 })
 
+# I-ready-017 (#1133): national + international statistical / data agencies.
+# These produce PRIMARY quantitative evidence (labour-force surveys, national
+# accounts, economic data series) and are the expected T3 backbone for
+# non-clinical domains such as `workforce` (config/scope_templates/workforce.yaml
+# expected_tier_distribution requires T3 at 35-65%, naming StatCan / BLS / OECD
+# / ILO / Eurostat explicitly).
+#
+# RERUN-BUG: bls.gov was demoted to T4 (OpenAlex returned preprint/repository on
+# one congressional-report URL -> R11; article+journal on an MLR URL whose title
+# tripped a narrative-flavor marker -> R9). oecd.org / ilo.org (.org, not on any
+# domain set) fell through to UNKNOWN. Result: T3 = 0% -> abort_corpus_approval_
+# denied on drb_72. These are genuine statistical agencies; T3 is the correct,
+# faithfulness-safe classification (NOT T1 primary-research-paper credit — the
+# clinical T3 = government/regulatory/authoritative-data tier is the right home).
+#
+# Eurostat note: ec.europa.eu already parent-matches `europa.eu` in
+# REGULATORY_DOMAINS, so Eurostat URLs are already T3 via R2d. ec.europa.eu is
+# listed here for explicitness; it is tier-harmless (both paths -> T3).
+STATISTICAL_AGENCY_DOMAINS = frozenset({
+    # US
+    "bls.gov",                 # Bureau of Labor Statistics
+    "census.gov",              # US Census Bureau
+    "federalreserve.gov",      # Federal Reserve Board
+    "stlouisfed.org",          # St. Louis Fed (FRED economic data series)
+    "fred.stlouisfed.org",     # FRED (parent-match also covers this)
+    # Canada
+    "statcan.gc.ca",           # Statistics Canada
+    "www150.statcan.gc.ca",    # StatCan data tables host (parent-match also)
+    # International statistical / data agencies (.org / .int / .europa.eu)
+    "oecd.org",                # OECD (Employment/Skills/Future of Work outlooks)
+    "ilo.org",                 # International Labour Organization (+ ILOSTAT)
+    "ilostat.ilo.org",         # ILOSTAT data host (parent-match also covers this)
+    "ec.europa.eu",            # Eurostat lives under ec.europa.eu/eurostat
+    "worldbank.org",           # World Bank Open Data
+    "data.worldbank.org",      # World Bank data host (parent-match also covers)
+    "imf.org",                 # International Monetary Fund
+})
+
 # Pass-10 addition (BUG-M-10): business / general news that OpenAlex
 # sometimes flags as 'article' in 'journal'. These are T6 news, not
 # primary research.
@@ -1279,6 +1317,32 @@ def _classify_source_tier_rules(
         )
         return result
 
+    # ── Rule 2b-stat-agency (T3, I-ready-017 #1133): national +
+    # international statistical / data agencies (BLS, OECD, ILO, Eurostat,
+    # StatCan, World Bank, IMF, Federal Reserve, FRED, Census). These
+    # produce PRIMARY quantitative evidence and are the expected T3
+    # backbone for non-clinical domains (workforce protocol requires
+    # T3 at 35-65%). Placed adjacent to R2b_gov_agency / R2c / R2d so
+    # statistical agencies earn T3 the same way regulatory domains do,
+    # and crucially BEFORE R9/R10/R11 (the OpenAlex paths that demoted
+    # bls.gov to T4) and AFTER the R2a/R2b denylist demotions (so a
+    # denylisted domain can never be laundered up to T3). It is T3
+    # (government/regulatory/authoritative-data tier), NOT T1 primary-
+    # research-paper credit.
+    if _domain_matches(domain, STATISTICAL_AGENCY_DOMAINS):
+        result.tier = TierLevel.T3
+        result.confidence = 0.95
+        result.matched_rules.append("R2b_statistical_agency")
+        result.reasons.append(
+            f"Domain {domain!r} is a national or international statistical / "
+            f"data agency (e.g. BLS, OECD, ILO, Eurostat, StatCan, World "
+            f"Bank, IMF, Federal Reserve, Census). Authoritative primary "
+            f"quantitative evidence — T3 regardless of OpenAlex metadata "
+            f"(which mis-labelled BLS reports as preprint/repository or "
+            f"narrative review). Not T1 primary-research-paper credit."
+        )
+        return result
+
     # ── Rule 2b-bizness (T6, BUG-M-10): Business / general news.
     # Fast Company, Forbes, etc. When OpenAlex mis-labels them as
     # 'article'/'journal', they should still be T6 news.
diff --git a/tests/polaris_graph/test_tier_classifier_stat_agency_t3_iready017.py b/tests/polaris_graph/test_tier_classifier_stat_agency_t3_iready017.py
new file mode 100644
index 00000000..b30b8ce6
--- /dev/null
+++ b/tests/polaris_graph/test_tier_classifier_stat_agency_t3_iready017.py
@@ -0,0 +1,169 @@
+"""I-ready-017 (#1133): statistical / data agencies must classify as T3.
+
+RERUN-BUG context (drb_72 workforce run):
+    The workforce protocol (config/scope_templates/workforce.yaml) requires
+    T3 (statistical-agency outputs: StatCan / BLS / OECD / ILO / Eurostat)
+    at 35-65% as the PRIMARY quantitative evidence. In the live corpus dump
+    bls.gov rows were classified T4 and oecd.org UNKNOWN, driving T3 to 0% ->
+    abort_corpus_approval_denied.
+
+Root cause (verified against the live dump):
+    * bls.gov congressional-report URL -> R11_openalex_preprint_or_repo (T4)
+      because OpenAlex returned publication_type="preprint" /
+      source_type="repository".
+    * bls.gov MLR article URL -> R9_openalex_narrative_review (T4) because
+      OpenAlex said article+journal and the title tripped a narrative-flavor
+      marker.
+    * oecd.org / ilo.org (.org, on no domain set) -> no_rule_matched (UNKNOWN).
+
+Fix: STATISTICAL_AGENCY_DOMAINS frozenset + R2b_statistical_agency rule placed
+adjacent to R2b_gov_agency / R2c / R2d (BEFORE R9/R10/R11, AFTER the denylist
+demotions). Always-on correctness fix.
+
+These tests intentionally include the TWO signal-bearing cases from the live
+dump (preprint/repository and article+journal-with-narrative-title) so they
+prove the new rule fires BEFORE R9 / R11 — a bare-domain-only test would pass
+even if the rule were mis-placed at the end of the function.
+"""
+
+from __future__ import annotations
+
+from src.polaris_graph.retrieval.tier_classifier import (
+    ClassificationSignals,
+    TierLevel,
+    classify_source_tier,
+)
+
+
+# ── The two signal-bearing cases reproduced verbatim from the live drb_72
+# corpus dump (LAW II: the case that failed now passes). These are the ones
+# that prove precedence over R9 / R11.
+
+def test_bls_congressional_report_preprint_signal_is_t3_not_r11_t4():
+    """Live-dump row 1: OpenAlex preprint/repository signal previously ->
+    R11_openalex_preprint_or_repo (T4). Must now be T3 via the stat-agency
+    rule, which fires BEFORE R11."""
+    sig = ClassificationSignals(
+        url=(
+            "https://www.bls.gov/bls/congressional-reports/"
+            "assessing-the-impact-of-new-technologies-on-the-labor-market.htm"
+        ),
+        title="Assessing the Impact of New Technologies on the Labor Market",
+        fetched_content_length=8000,
+        openalex_publication_type="preprint",
+        openalex_source_type="repository",
+    )
+    res = classify_source_tier(sig)
+    assert res.tier == TierLevel.T3, res.reasons
+    assert "R2b_statistical_agency" in res.matched_rules
+    assert "R11_openalex_preprint_or_repo" not in res.matched_rules
+
+
+def test_bls_mlr_article_narrative_signal_is_t3_not_r9_t4():
+    """Live-dump row 2: OpenAlex article+journal + narrative-flavor title
+    previously -> R9_openalex_narrative_review (T4). Must now be T3 via the
+    stat-agency rule, which fires BEFORE R9."""
+    sig = ClassificationSignals(
+        url=(
+            "https://www.bls.gov/opub/mlr/2025/article/"
+            "incorporating-ai-impacts-in-bls-employment-projections.htm"
+        ),
+        title="Incorporating AI impacts in BLS employment projections",
+        fetched_content_length=12000,
+        openalex_publication_type="article",
+        openalex_source_type="journal",
+        openalex_is_peer_reviewed=True,
+    )
+    res = classify_source_tier(sig)
+    assert res.tier == TierLevel.T3, res.reasons
+    assert "R2b_statistical_agency" in res.matched_rules
+    assert "R9_openalex_narrative_review" not in res.matched_rules
+
+
+def test_oecd_no_signals_was_unknown_now_t3():
+    """Live-dump oecd.org row: previously no_rule_matched (UNKNOWN). Now T3."""
+    sig = ClassificationSignals(
+        url=(
+            "https://www.oecd.org/en/publications/2021/01/"
+            "the-impact-of-artificial-intelligence-on-the-labour-market_"
+            "a4b9cac2.html"
+        ),
+        title="The impact of Artificial Intelligence on the labour market - OECD",
+        fetched_content_length=15000,
+    )
+    res = classify_source_tier(sig)
+    assert res.tier == TierLevel.T3, res.reasons
+    assert "R2b_statistical_agency" in res.matched_rules
+
+
+# ── Bare-domain coverage for the named protocol agencies + extensions.
+
+def test_named_statistical_agencies_are_t3():
+    urls = [
+        "https://www.bls.gov/news.release/empsit.nr0.htm",
+        "https://www.oecd.org/employment-outlook/",
+        "https://www.ilo.org/global/research/global-reports/weso/lang--en/index.htm",
+        "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1410028701",
+        "https://www.federalreserve.gov/releases/h6/current/",
+        "https://fred.stlouisfed.org/series/UNRATE",
+        "https://data.worldbank.org/indicator/SL.UEM.TOTL.ZS",
+        "https://www.imf.org/en/Publications/WEO",
+        "https://www.census.gov/topics/employment.html",
+    ]
+    for u in urls:
+        res = classify_source_tier(
+            ClassificationSignals(url=u, fetched_content_length=8000)
+        )
+        assert res.tier == TierLevel.T3, (u, res.tier, res.reasons)
+
+
+def test_eurostat_is_t3():
+    """Eurostat is hosted under ec.europa.eu, which already parent-matches
+    europa.eu in REGULATORY_DOMAINS. Assert tier == T3 only (the matched
+    rule may legitimately be R2d_regulatory_domain, not the new rule)."""
+    res = classify_source_tier(
+        ClassificationSignals(
+            url="https://ec.europa.eu/eurostat/web/lfs/data/database",
+            fetched_content_length=8000,
+        )
+    )
+    assert res.tier == TierLevel.T3, res.reasons
+
+
+# ── Regression guards: pre-existing behaviour must be unchanged.
+
+def test_clinical_regulatory_domains_still_t3():
+    """fda.gov and ema.europa.eu must remain T3 (unregressed)."""
+    for u in [
+        "https://www.fda.gov/drugs/drug-approvals-and-databases",
+        "https://www.ema.europa.eu/en/medicines/human/EPAR/example",
+    ]:
+        res = classify_source_tier(
+            ClassificationSignals(url=u, fetched_content_length=8000)
+        )
+        assert res.tier == TierLevel.T3, (u, res.tier, res.reasons)
+
+
+def test_generic_org_is_not_forced_to_t3():
+    """A generic .org with no other signals must NOT be promoted to T3 by the
+    new rule — it stays UNKNOWN (honest no-match)."""
+    res = classify_source_tier(
+        ClassificationSignals(
+            url="https://www.example.org/some-page",
+            fetched_content_length=8000,
+        )
+    )
+    assert res.tier != TierLevel.T3, res.reasons
+    assert "R2b_statistical_agency" not in res.matched_rules
+
+
+def test_stat_agency_stub_still_t7():
+    """A <1000-char stat-agency page must stay T7 (R1 stub fires before the
+    stat-agency rule — consistent with REGULATORY_DOMAINS handling)."""
+    res = classify_source_tier(
+        ClassificationSignals(
+            url="https://www.bls.gov/some-tiny-page.htm",
+            fetched_content_length=300,
+        )
+    )
+    assert res.tier == TierLevel.T7, res.reasons


Ask: anything blocking APPROVE? Emit the YAML schema with the final `verdict:` line.
