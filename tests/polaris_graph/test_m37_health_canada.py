"""M-37 tests: Health Canada regulatory coverage.

Codex DR pass-11 gap #2 on V23:
> "Add Health Canada specificity alongside FDA, EMA, and NICE,
> including the Canadian product monograph / Summary Basis of
> Decision and any jurisdiction-specific safety communications."

V23 corpus had 7 Health Canada rows (5 T3 canada.ca + 2 T3/T4
pdf.hres.ca) but zero Health Canada entries in the cited
bibliography. Three root causes:

1. **Tier misclassification**: `pdf.hres.ca` was not on the
   REGULATORY_DOMAINS allowlist, so the MOUNJARO Product
   Monograph PDF fell through R2d and hit R9 OpenAlex which
   demoted it to T4 (OpenAlex tagged it "article" but the host
   wasn't on the peer-reviewed allowlist).

2. **Retrieval pressure**: the clinical.yaml only anchored on
   `hres.ca` and `canada.ca`; adding `pdf.hres.ca`,
   `recalls-rappels.canada.ca`, and `health-products.canada.ca`
   increases the Canadian-regulatory volume in the corpus.

3. **Prompt bias**: the per-section generator prompt had rule
   #11 (M-29) on jurisdictional PRECISION (don't say "both
   agencies" without citing both) but no COVERAGE rule — nothing
   forced the generator to actually cite Canadian sources when
   they were in the evidence subset. New rule #11b requires at
   least one citation per jurisdiction present.

Test design:
  - Tier classifier: pdf.hres.ca URLs now route to T3 via R2d.
  - YAML template: new anchor hosts are loaded and unique.
  - Prompt template: rule #11b is present and names Health
    Canada alongside other jurisdictions.
  - Non-regressions: existing rules (#10, #11, #12) still present.
"""
from __future__ import annotations

from src.polaris_graph.retrieval.tier_classifier import (
    REGULATORY_DOMAINS,
    _domain_matches,
)


# ─────────────────────────────────────────────────────────────────────
# Tier classifier fix
# ─────────────────────────────────────────────────────────────────────


class TestTierClassifierRegulatoryDomains:
    """M-37 fix #1: hres.ca (and therefore pdf.hres.ca) must be
    recognized as a regulatory domain for the T3 fast-path."""

    def test_hres_ca_is_in_regulatory_domains(self) -> None:
        assert "hres.ca" in REGULATORY_DOMAINS

    def test_pdf_hres_ca_matches_via_parent(self) -> None:
        """`_domain_matches` walks parent domains, so pdf.hres.ca
        matches the hres.ca entry."""
        assert _domain_matches("pdf.hres.ca", REGULATORY_DOMAINS)

    def test_bare_hres_ca_matches(self) -> None:
        assert _domain_matches("hres.ca", REGULATORY_DOMAINS)

    def test_canada_ca_still_matches(self) -> None:
        """Non-regression: canada.ca entry still matches itself and
        subdomains (health-products.canada.ca, recalls-rappels.canada.ca)."""
        assert _domain_matches("canada.ca", REGULATORY_DOMAINS)
        assert _domain_matches(
            "recalls-rappels.canada.ca", REGULATORY_DOMAINS
        )
        assert _domain_matches(
            "health-products.canada.ca", REGULATORY_DOMAINS
        )

    def test_random_ca_subdomain_does_not_match(self) -> None:
        """Non-regression: only known regulatory *.ca hosts match.
        A random foo.bar.ca should NOT be classified as regulatory."""
        assert not _domain_matches("news.example.ca", REGULATORY_DOMAINS)

    def test_fda_gov_still_matches(self) -> None:
        """Non-regression: adding hres.ca did not break US coverage."""
        assert _domain_matches("accessdata.fda.gov", REGULATORY_DOMAINS)
        assert _domain_matches("fda.gov", REGULATORY_DOMAINS)


# ─────────────────────────────────────────────────────────────────────
# Clinical template YAML
# ─────────────────────────────────────────────────────────────────────


class TestClinicalTemplateHealthCanadaAnchors:
    """M-37 fix #2: new Health Canada hosts are loaded in the
    clinical scope template regulatory_anchors list."""

    def test_clinical_template_has_new_hc_hosts(self) -> None:
        from src.polaris_graph.nodes.scope_gate import load_scope_template
        tmpl = load_scope_template("clinical")
        anchors = tmpl.get("regulatory_anchors", [])
        assert isinstance(anchors, list)
        anchor_set = set(a.strip().lower() for a in anchors)
        # New HC anchors from M-37
        assert "pdf.hres.ca" in anchor_set
        assert "recalls-rappels.canada.ca" in anchor_set
        assert "health-products.canada.ca" in anchor_set
        # Existing HC anchors still present (non-regression)
        assert "hres.ca" in anchor_set
        assert "canada.ca" in anchor_set

    def test_anchors_are_unique(self) -> None:
        """If pdf.hres.ca was already present as a duplicate of
        hres.ca, the expander would deduplicate — but readability
        prefers no YAML-level duplicates."""
        from src.polaris_graph.nodes.scope_gate import load_scope_template
        tmpl = load_scope_template("clinical")
        anchors = [a.strip().lower() for a in tmpl.get("regulatory_anchors", [])]
        assert len(anchors) == len(set(anchors)), (
            f"clinical.yaml regulatory_anchors has duplicates: {anchors}"
        )

    def test_existing_non_hc_anchors_unchanged(self) -> None:
        """Non-regression: US/EU/UK anchors still present."""
        from src.polaris_graph.nodes.scope_gate import load_scope_template
        tmpl = load_scope_template("clinical")
        anchor_set = set(
            a.strip().lower() for a in tmpl.get("regulatory_anchors", [])
        )
        for host in (
            "accessdata.fda.gov", "ema.europa.eu", "fda.gov",
            "who.int", "nice.org.uk",
        ):
            assert host in anchor_set, f"missing {host}"


# ─────────────────────────────────────────────────────────────────────
# Section prompt rule #11b
# ─────────────────────────────────────────────────────────────────────


class TestSectionPromptJurisdictionalCoverage:
    """Compatibility coverage for the generalized authority rule."""

    def test_prompt_has_jurisdictional_coverage_rule(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        assert "Authority precision and coverage" in SECTION_SYSTEM_PROMPT_TEMPLATE
        assert "jurisdictions" in SECTION_SYSTEM_PROMPT_TEMPLATE
        assert "agencies" in SECTION_SYSTEM_PROMPT_TEMPLATE
        assert "standards bodies" in SECTION_SYSTEM_PROMPT_TEMPLATE

    def test_authority_precision_is_preserved(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        body = SECTION_SYSTEM_PROMPT_TEMPLATE.lower()
        assert "attribute each specific assertion" in body
        assert "whose source supports it" in body

    def test_precision_and_coverage_share_one_rule(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        start = SECTION_SYSTEM_PROMPT_TEMPLATE.find(
            "Authority precision and coverage"
        )
        end = SECTION_SYSTEM_PROMPT_TEMPLATE.find("\n12.", start)
        body = SECTION_SYSTEM_PROMPT_TEMPLATE[start:end].lower()
        assert "attribute each specific assertion" in body
        assert "cite at least one source from each authority" in body

    def test_prompt_rule_qualifies_on_presence(self) -> None:
        """Rule #11b must qualify on presence (only fire when evidence
        is actually in the subset) — must NOT require inventing
        coverage that isn't in the evidence."""
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        assert "present in the evidence" in SECTION_SYSTEM_PROMPT_TEMPLATE

    def test_authority_rule_has_no_named_domain_authorities(self) -> None:
        """Authority vocabulary is structural rather than domain-specific."""
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        start = SECTION_SYSTEM_PROMPT_TEMPLATE.find(
            "Authority precision and coverage"
        )
        end = SECTION_SYSTEM_PROMPT_TEMPLATE.find("\n12.", start)
        assert start >= 0 and end > start
        lowered = SECTION_SYSTEM_PROMPT_TEMPLATE[start:end].lower()
        for literal in ("fda", "ema", "nice", "health canada"):
            assert literal not in lowered
