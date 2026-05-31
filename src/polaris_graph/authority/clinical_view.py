"""Clinical VIEW renderer — AuthorityResult primitives -> legacy TierLevel.

Phase 0a (GH #983). Data-driven (LAW VI) via config/authority/clinical_view.yaml.

This renders the seven-tier clinical VIEW (primitives -> tiers, NOT hosts ->
tiers) so the computed authority model can run as a drop-in behind
PG_USE_AUTHORITY_MODEL and reproduce the existing clinical T1-T7 distribution
(>=95%, smoke S2). Rule ordering mirrors the legacy classifier's priority order.

It consumes the structural primitives the authority model carried through
(publication_type, source_type, is_retracted, content_length, title markers)
PLUS the computed AuthorityResult.source_class / junk_class / predatory_oa.

Diff-gate P1-B (SIGNAL-DRIVEN demotion, NO host list):
  - junk_demote: when junk_detection flags a structural junk-class (press
    release / self-published blog / login-wall / self-interest), the source is
    demoted to junk_class_tier (T5 for self-interest = legacy industry-marketing
    R3; T6 for press/blog/social = legacy news/blog R4) EVEN IF OpenAlex matched
    an underlying article — so host-wrapped news re-reporting a real paper does
    NOT inherit the paper's T1.
  - predatory_no_t1: a scholarly source carrying the predatory-OA smell (NOT in
    DOAJ AND high APC, computed by citation_graph from the OpenAlex /sources
    is_in_doaj + apc_prices fields) does NOT earn an auto-T1; it lands T4.

HARD Gate-A PREREQUISITE (offline-honesty boundary, NOT silently waved):
  The predatory-OA demotion depends on the LIVE OpenAlex /sources is_in_doaj +
  apc_prices signals. The frozen offline S2 corpus never recorded these, so the
  predatory low-quality-OA case (e.g. an mdpi primary) CANNOT be demoted offline
  and remains at its scholarly tier in the offline smoke. Closing that residual
  requires a ONE-TIME FREE OpenAlex shadow run (no GPU spend) that must hit
  >=0.95 agreement with ZERO lethal inversions BEFORE PG_USE_AUTHORITY_MODEL is
  ever flipped ON. The host-wrapped-news / industry self-interest cases are
  offline-fixable once the structural junk inputs (fetched_body / JSON-LD /
  claim-vendor token) flow into ClassificationSignals.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.polaris_graph.authority.data_loader import load_authority_data
from src.polaris_graph.authority.source_class import AuthorityResult, SourceClass


@dataclass
class ClinicalViewInput:
    """Structural cues + computed authority result fed to the renderer."""

    publication_type: str
    source_type: str
    is_retracted: bool
    fetched_content_length: int
    title: str
    authority: AuthorityResult


def _title_has_marker(title: str, markers: list[str]) -> bool:
    t = (title or "").lower()
    return any(m in t for m in markers)


def render_clinical_tier(view_in: ClinicalViewInput) -> str:
    """Map primitives -> one of T1..T7 / UNKNOWN (returns the tier string)."""
    data = load_authority_data()
    view = data["clinical_view"]
    markers = view["title_markers"]
    scholarly = view["scholarly_primary_types"]
    repo = view["preprint_repo"]

    pub = (view_in.publication_type or "").lower()
    src = (view_in.source_type or "").lower()
    src_class = view_in.authority.source_class
    # Diff-gate P1-B: SIGNAL-DRIVEN demotion inputs (no host list).
    junk_class = (view_in.authority.junk_class or "").strip()
    junk_tier_map = view["junk_class_tier"]
    predatory_oa = bool(view_in.authority.predatory_oa)
    # "scholarly" = a peer-reviewed journal-shaped source (article OR review).
    is_scholarly = (
        pub in scholarly["publication_type"] and src in scholarly["source_type"]
    ) or src_class == SourceClass.PRIMARY_SCHOLARLY
    # T1 primary is reserved for `article` pub_type (a journal `review` is
    # narrative/secondary -> T4, or T2 when the title signals SR/MA). This
    # mirrors legacy: pub_type 'review' never earns T1.
    is_primary_article = (
        pub in scholarly["publication_type"]
        and pub not in view["review_pubtypes"]
        and src in scholarly["source_type"]
    ) or (src_class == SourceClass.PRIMARY_SCHOLARLY and pub not in view["review_pubtypes"])

    for rule in view["rule_order"]:
        if rule == "retracted_unknown":
            if view_in.is_retracted:
                return "UNKNOWN"
        elif rule == "stub_content_t7":
            clen = view_in.fetched_content_length
            if clen and clen < view["t7_stub_content_chars"]:
                return "T7"
        elif rule == "junk_demote":
            # A structural junk-class fired (press/blog/social/self-interest):
            # demote SIGNAL-DRIVEN to the mapped tier even if OpenAlex matched
            # an underlying article (host-wrapped news must NOT inherit a T1).
            if junk_class and junk_class in junk_tier_map:
                return junk_tier_map[junk_class]
        elif rule == "predatory_no_t1":
            # A scholarly-shaped source carrying the predatory-OA smell does NOT
            # auto-T1 — it lands at the unverified-primary tier. (Pure thin-
            # coverage LOW confidence is NOT demoted here; only the affirmative
            # predatory signal is, so honest thin T1 primaries are preserved.)
            if predatory_oa and is_primary_article:
                return view["predatory_oa_tier"]
        elif rule == "conference_abstract_t7":
            if is_scholarly and _title_has_marker(view_in.title, markers["conference_abstract"]):
                return "T7"
        elif rule == "scholarly_sr_t2":
            if is_scholarly and _title_has_marker(view_in.title, markers["systematic_review"]):
                return "T2"
        elif rule == "scholarly_narrative_t4":
            if is_scholarly and _title_has_marker(view_in.title, markers["narrative_review"]):
                return "T4"
        elif rule == "scholarly_primary_t1":
            if is_primary_article:
                return "T1"
        elif rule == "review_pubtype_t4":
            if pub in view["review_pubtypes"]:
                return "T4"
        elif rule == "secondary_doctype_t4":
            if pub in view["secondary_doc_types"]:
                return "T4"
        elif rule == "preprint_repo_t4":
            if pub in repo["publication_type"] or src in repo["source_type"]:
                return "T4"
        elif rule == "official_t3":
            if src_class == SourceClass.PRIMARY_OFFICIAL:
                return "T3"
        elif rule == "source_class_fallthrough":
            return view["source_class_default_tier"].get(src_class.value, "UNKNOWN")

    return "UNKNOWN"
