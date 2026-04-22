"""M-48 tests: per-anchor first-author + journal query variants AND
per-anchor population-scope labels.

V27 hit 4/11 primary trials with anchor-only queries. Codex V28 plan
pass-2 APPROVED the M-48 two-part fix:
1. `per_query_primary_trial_variants` adds first-author + journal
   variant queries alongside each anchor, raising primary landing
   probability.
2. `per_query_trial_population_scope` tags evidence rows as direct
   vs indirect_for_t2d so generator doesn't merge obesity-only
   SURMOUNT-1/3/4 weight-loss estimates into T2D efficacy claims.

These tests are pure — no network, no LLM calls. Fixtures only.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.retrieval.primary_trial_expander import (
    _extract_variants,
    expand_primary_trial_queries,
    get_primary_trial_anchors_for_slug,
    get_trial_population_scope_for_slug,
    label_rows_with_population_scope,
)


def _template_with_variants_and_scope() -> dict:
    """Minimal template fixture mirroring clinical.yaml schema
    for the clinical_tirzepatide_t2dm slug."""
    return {
        "per_query_primary_trial_anchors": {
            "clinical_tirzepatide_t2dm": [
                "SURPASS-1",
                "SURPASS-2",
                "SURPASS-CVOT",
                "SURMOUNT-1",
                "SURMOUNT-2",
            ],
        },
        "per_query_primary_trial_variants": {
            "clinical_tirzepatide_t2dm": {
                "SURPASS-1": "Rosenstock Lancet tirzepatide monotherapy",
                "SURPASS-2": "Frías NEJM tirzepatide semaglutide",
                "SURPASS-CVOT": "Nicholls tirzepatide cardiovascular MACE",
                "SURMOUNT-1": "Jastreboff NEJM tirzepatide obesity",
                "SURMOUNT-2": "Garvey Lancet tirzepatide obesity T2D",
            },
        },
        "per_query_trial_population_scope": {
            "clinical_tirzepatide_t2dm": {
                "SURPASS-1": "direct",
                "SURPASS-2": "direct",
                "SURPASS-CVOT": "direct",
                "SURMOUNT-1": "indirect_for_t2d",
                "SURMOUNT-2": "direct",
            },
        },
    }


class TestM48VariantExtraction:
    def test_extracts_variants_for_known_slug(self) -> None:
        tmpl = _template_with_variants_and_scope()
        variants = _extract_variants(tmpl, "clinical_tirzepatide_t2dm")
        assert variants["SURPASS-2"] == "Frías NEJM tirzepatide semaglutide"
        assert variants["SURMOUNT-1"].startswith("Jastreboff")

    def test_missing_slug_returns_empty_dict(self) -> None:
        tmpl = _template_with_variants_and_scope()
        assert _extract_variants(tmpl, "some_other_slug") == {}

    def test_missing_template_returns_empty_dict(self) -> None:
        assert _extract_variants(None, "clinical_tirzepatide_t2dm") == {}

    def test_malformed_variants_key_rejected(self) -> None:
        tmpl = {
            "per_query_primary_trial_variants": "not a dict",
        }
        assert _extract_variants(tmpl, "any") == {}

    def test_variant_with_double_quote_rejected(self) -> None:
        tmpl = {
            "per_query_primary_trial_variants": {
                "s": {"ANCHOR": 'has "inner quote"'},
            },
        }
        assert _extract_variants(tmpl, "s") == {}

    def test_anchor_with_whitespace_rejected(self) -> None:
        tmpl = {
            "per_query_primary_trial_variants": {
                "s": {"BAD ANCHOR": "valid variant text"},
            },
        }
        assert _extract_variants(tmpl, "s") == {}

    def test_empty_variant_rejected(self) -> None:
        tmpl = {
            "per_query_primary_trial_variants": {
                "s": {"GOOD": "", "BETTER": "   "},
            },
        }
        assert _extract_variants(tmpl, "s") == {}


class TestM48ExpandWithVariants:
    def test_variant_query_emitted_alongside_anchor(self) -> None:
        tmpl = _template_with_variants_and_scope()
        qs = expand_primary_trial_queries(
            "What is the efficacy of tirzepatide in T2D?",
            tmpl,
            "clinical_tirzepatide_t2dm",
        )
        # 5 anchors × 2 (anchor + variant) = 10 queries
        assert len(qs) == 10
        # First query is bare anchor form
        assert qs[0].startswith('"SURPASS-1" What is the efficacy')
        # Second query is variant form (contains Rosenstock Lancet)
        assert qs[1].startswith('"SURPASS-1" Rosenstock Lancet tirzepatide')
        assert qs[1].endswith("What is the efficacy of tirzepatide in T2D?")

    def test_anchor_without_variant_emits_only_one_query(self) -> None:
        tmpl = {
            "per_query_primary_trial_anchors": {
                "s": ["A-1", "A-2"],
            },
            "per_query_primary_trial_variants": {
                "s": {"A-1": "first-author journal"},
                # A-2 has no variant
            },
        }
        qs = expand_primary_trial_queries("q", tmpl, "s")
        # A-1 → 2 queries; A-2 → 1 query → total 3
        assert len(qs) == 3
        assert qs[0] == '"A-1" q'
        assert qs[1] == '"A-1" first-author journal q'
        assert qs[2] == '"A-2" q'

    def test_backwards_compatible_when_no_variants_section(self) -> None:
        tmpl = {
            "per_query_primary_trial_anchors": {"s": ["A-1", "A-2", "A-3"]},
            # No per_query_primary_trial_variants at all
        }
        qs = expand_primary_trial_queries("q", tmpl, "s")
        assert qs == ['"A-1" q', '"A-2" q', '"A-3" q']


class TestM48PopulationScope:
    def test_scope_extraction_only_keeps_valid_labels(self) -> None:
        tmpl = _template_with_variants_and_scope()
        scope = get_trial_population_scope_for_slug(
            tmpl, "clinical_tirzepatide_t2dm",
        )
        assert scope["SURMOUNT-1"] == "indirect_for_t2d"
        assert scope["SURMOUNT-2"] == "direct"
        assert scope["SURPASS-2"] == "direct"

    def test_invalid_label_rejected(self) -> None:
        tmpl = {
            "per_query_trial_population_scope": {
                "s": {"ANCHOR": "not-a-real-label"},
            },
        }
        scope = get_trial_population_scope_for_slug(tmpl, "s")
        assert scope == {}

    def test_accepts_case_insensitive_labels(self) -> None:
        tmpl = {
            "per_query_trial_population_scope": {
                "s": {"ANCHOR": "DIRECT", "OTHER": "Indirect_For_T2D"},
            },
        }
        scope = get_trial_population_scope_for_slug(tmpl, "s")
        assert scope["ANCHOR"] == "direct"
        assert scope["OTHER"] == "indirect_for_t2d"

    def test_labels_rows_by_title_match(self) -> None:
        tmpl = _template_with_variants_and_scope()
        rows = [
            {"evidence_id": "ev1",
             "title": "SURMOUNT-1: Tirzepatide for obesity",
             "url": "https://nejm.org/sm1"},
            {"evidence_id": "ev2",
             "title": "SURMOUNT-2: Tirzepatide for T2D + obesity",
             "url": "https://lancet.com/sm2"},
            {"evidence_id": "ev3",
             "title": "SURPASS-2: Tirzepatide vs semaglutide",
             "url": "https://nejm.org/sp2"},
            {"evidence_id": "ev4",
             "title": "Generic review of incretins",
             "url": "https://example.com/review"},
        ]
        out = label_rows_with_population_scope(
            rows, tmpl, "clinical_tirzepatide_t2dm",
        )
        # ev1: SURMOUNT-1 → indirect_for_t2d
        assert out[0]["population_scope"] == "indirect_for_t2d"
        assert out[0]["indirect_for_t2d"] is True
        assert out[0]["_m48_anchor_match"] == "SURMOUNT-1"
        # ev2: SURMOUNT-2 → direct
        assert out[1]["population_scope"] == "direct"
        assert out[1]["indirect_for_t2d"] is False
        # ev3: SURPASS-2 → direct
        assert out[2]["population_scope"] == "direct"
        assert out[2]["indirect_for_t2d"] is False
        # ev4: no anchor match → no scope key
        assert "population_scope" not in out[3]
        assert "indirect_for_t2d" not in out[3]

    def test_labels_case_insensitive_title_match(self) -> None:
        tmpl = _template_with_variants_and_scope()
        rows = [
            {"evidence_id": "ev1",
             "title": "surmount-1 — obesity primary endpoint",
             "url": "https://x/y"},
        ]
        out = label_rows_with_population_scope(
            rows, tmpl, "clinical_tirzepatide_t2dm",
        )
        assert out[0]["indirect_for_t2d"] is True

    def test_empty_rows_list_returned_unchanged(self) -> None:
        tmpl = _template_with_variants_and_scope()
        out = label_rows_with_population_scope(
            [], tmpl, "clinical_tirzepatide_t2dm",
        )
        assert out == []

    def test_no_template_scope_for_slug_is_noop(self) -> None:
        tmpl = {
            "per_query_trial_population_scope": {
                "other_slug": {"SURMOUNT-1": "indirect_for_t2d"},
            },
        }
        rows = [
            {"evidence_id": "ev1",
             "title": "SURMOUNT-1 obesity primary paper",
             "url": "https://x/y"},
        ]
        out = label_rows_with_population_scope(
            rows, tmpl, "clinical_tirzepatide_t2dm",
        )
        assert "population_scope" not in out[0]


class TestM48RealTemplateIntegration:
    """Verify the real clinical.yaml has the M-48 schema populated
    for the tirzepatide slug."""

    def test_clinical_yaml_has_variants_for_11_anchors(self) -> None:
        from src.polaris_graph.nodes.scope_gate import load_scope_template
        tmpl = load_scope_template("clinical")
        slug = "clinical_tirzepatide_t2dm"
        anchors = get_primary_trial_anchors_for_slug(tmpl, slug)
        variants = _extract_variants(tmpl, slug)
        assert len(anchors) == 11, f"expected 11 anchors; got {len(anchors)}"
        # Every anchor must have a variant (M-48 acceptance criterion).
        missing = [a for a in anchors if a not in variants]
        assert not missing, f"anchors missing variants: {missing}"

    def test_clinical_yaml_has_population_scope_labels(self) -> None:
        from src.polaris_graph.nodes.scope_gate import load_scope_template
        tmpl = load_scope_template("clinical")
        slug = "clinical_tirzepatide_t2dm"
        scope = get_trial_population_scope_for_slug(tmpl, slug)
        # SURMOUNT-2 must be direct (T2D+obesity); SURMOUNT-1/3/4
        # must be indirect_for_t2d (obesity-only).
        assert scope.get("SURMOUNT-2") == "direct"
        assert scope.get("SURMOUNT-1") == "indirect_for_t2d"
        assert scope.get("SURMOUNT-3") == "indirect_for_t2d"
        assert scope.get("SURMOUNT-4") == "indirect_for_t2d"
        # All SURPASS trials direct.
        for name in ("SURPASS-1", "SURPASS-2", "SURPASS-3",
                     "SURPASS-4", "SURPASS-5", "SURPASS-6",
                     "SURPASS-CVOT"):
            assert scope.get(name) == "direct", (
                f"{name} scope = {scope.get(name)!r}, expected 'direct'"
            )

    def test_clinical_yaml_query_expansion_doubles_queries(self) -> None:
        """With variants, expanded query list should be ~2x the anchor
        count (11 anchors → 22 queries under M-43 cap=12 → capped at
        12 * 2 = 24 queries max, but anchor cap is applied first)."""
        from src.polaris_graph.nodes.scope_gate import load_scope_template
        tmpl = load_scope_template("clinical")
        qs = expand_primary_trial_queries(
            "What is tirzepatide efficacy?",
            tmpl,
            "clinical_tirzepatide_t2dm",
        )
        # Anchor cap defaults to 15 for primary trials, so 11 anchors
        # fit. Expect exactly 22 queries (11 * 2 = anchor + variant).
        assert len(qs) == 22, (
            f"expected 22 queries (11 anchors × 2); got {len(qs)}"
        )
