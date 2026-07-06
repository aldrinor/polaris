"""I-wire-013 (#1327) — the grounded DEPTH cross-source SYNTHESIS pass.

The net-new generation feature: turn the weighted multi-source claim BASKETS into ONE consolidated
cross-source finding per high-corroboration basket — the consolidated claim PLUS the surfaced
agreement / tension across that basket's sources — written by the LOCKED generator-role model
(``polaris_runtime_lock.yaml`` generator arm, resolved at call time), then RE-GROUNDED through the
UNCHANGED faithfulness engine so that a synthesized sentence WITHOUT a grounding span is DROPPED,
never shipped. Zero new fabrication is possible: the synthesis output is NOT trusted prose — every
sentence passes the SAME ``strict_verify`` (provenance token + numeric match + >=2 content-word
overlap) every other composer passes, against a BASKET-ID-BOUND verify pool (a token citing another
basket's source is absent from the scoped pool and fails CLOSED).

FAITHFULNESS (FROZEN engine — nothing here relaxes it):
  * The generator only ORGANIZES + PHRASES already-isolated-verified spans; a fabricated LLM draft
    sentence fails ``strict_verify`` and is DROPPED. I-deepfix-001 P3_dead_synthesis FIX-1 (#1344): when
    the LLM draft re-grounds to ZERO survivors, the basket does NOT vanish — it falls back to the
    DETERMINISTIC verbatim multi-cite span-join the BODY composer already emits
    (``verified_compose.compose_basket_multicited_sentence`` with a NULL writer, verbatim K-span clauses
    only). That fallback re-passes the SAME frozen ``strict_verify`` by construction (each clause IS a
    verified span) — so it adds ZERO new fabrication path; it only revives breadth the free-redraft path
    was silently dropping. Default-ON kill-switch ``PG_DEPTH_SYNTHESIS_SPANJOIN_FALLBACK`` (OFF =>
    drop-not-fallback, byte-identical).
  * The verify pool is the basket's own isolated-``SUPPORTS`` members ONLY (``_basket_scoped_pool``),
    so a sentence citing a DIFFERENT basket's source fails closed (the anti-cross-claim contract).
  * Each surviving sentence's ``[#ev:<id>:<a>-<b>]`` token is resolved to the report's EXISTING ``[N]``
    citation number (``bib_num_by_evidence_id``) — never a fresh renumber — and is routed through the
    ONE shared chrome/truncation screen, exactly like the Key-Findings / Abstract / Conclusion bullets.

§-1.3 DNA: the ``>=2 sources`` gate is DEFINITIONAL, not a cap/target/filter — a *cross-source*
finding requires at least two corroborating sources by definition. It is an ADDITIVE render layer: it
drops NO corpus source, touches NO basket, and the existing per-section body composition is untouched.

DEFAULT-OFF: ``synthesize_cross_source_findings`` only runs when a ``synthesizer`` is injected and a
basket clears the ``>=2`` gate; with no synthesizer (the legacy ``build_depth_layer`` call) it never
runs. The cert path injects the live synthesizer below; tests inject a deterministic fake so the
faithfulness backstop (drop-the-ungrounded) is proven OFFLINE with zero spend.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# A resolved provenance token ``[#ev:<evidence_id>:<start>-<end>]`` (the shape strict_verify emits on
# a kept sentence). Captures the evidence_id so it can be mapped to the report's existing ``[N]``.
_EV_TOKEN_FULL_RE = re.compile(r"\[#ev:([A-Za-z0-9_]+):\d+-\d+\]")

# LAW VI: the cross-source corroboration floor is DEFINITIONAL (a cross-source finding needs >=2
# sources), env-overridable, fail-soft floored at 2 so it can never be weakened to a single source.
_ENV_MIN_SOURCES = "PG_DEPTH_SYNTHESIS_MIN_SOURCES"
_DEFAULT_MIN_SOURCES = 2

# Live-call env knobs (LAW VI). I-wire-013 (#1327) iter-2 (Codex P2-1): the synthesis call is a
# GENERATOR-role call (§9.1.8), so its model AND token budget resolve through the SAME central
# runtime-lock path every other composer uses — NOT a parallel ``PG_DEPTH_SYNTHESIS_MODEL`` /
# ``PG_DEPTH_SYNTHESIS_*_TOKENS`` knob (a per-leg override could silently drift depth onto a forbidden
# model or a starved budget). The model is ``PG_GENERATOR_MODEL`` (the lock generator slug); the token
# budget tracks the section composer's knobs. See ``_resolve_model`` / ``_resolve_token_budget`` below.
_ENV_TEMPERATURE = "PG_DEPTH_SYNTHESIS_TEMPERATURE"
_DEFAULT_TEMPERATURE = 0.2
_ENV_CONCURRENCY = "PG_DEPTH_SYNTHESIS_CONCURRENCY"
_DEFAULT_CONCURRENCY = 8
_ENV_CALL_DEADLINE_S = "PG_DEPTH_SYNTHESIS_CALL_DEADLINE_S"
_DEFAULT_CALL_DEADLINE_S = 120.0
_ENV_WALL_DEADLINE_S = "PG_DEPTH_SYNTHESIS_WALL_DEADLINE_S"
_DEFAULT_WALL_DEADLINE_S = 720.0
# §-1.3 DNA: there is NO default cap on how many cross-source findings render — breadth EMERGES from
# how many high-corroboration baskets survive the UNCHANGED strict_verify, never a forced number. The
# default is UNBOUNDED (0); an operator who wants a bounded top-of-report DIGEST can set a positive
# ``PG_DEPTH_SYNTHESIS_MAX_FINDINGS`` (a verbosity preference, never a breadth target). A hardcoded
# count cap here would be the exact filter-and-cap anti-pattern the DNA bans.
_ENV_MAX_FINDINGS = "PG_DEPTH_SYNTHESIS_MAX_FINDINGS"
_DEFAULT_MAX_FINDINGS = 0  # 0 => unbounded (let breadth emerge); >0 => operator verbosity bound

# I-deepfix-001 wave-3 (conclusion true-drop): the master default-ON gate for threading the grounded
# depth cross-source findings through the SAME 4-role D8 seam the body passes. ON => each finding dict
# additionally carries its PRE-resolve ``audit_sentence`` (with ``[#ev:...]`` tokens) + its
# ``ProvenanceToken`` list so the native Gate-B builder can emit one S3/observe-only ``DS-*`` claim per
# finding; a NON-VERIFIED synthesized finding is then DROPPED from report.md (TRUE drop-not-sink). OFF
# => the two extra keys are omitted (finding dict byte-identical: sentence/tier/label only), no DS-*
# claim is built, and the depth layer ships strict_verify-only-gated exactly as before. LAW VI:
# env-overridable. STRENGTHENS faithfulness (adds a D8 pass + a real drop); relaxes nothing.
_ENV_D8_GATE = "PG_DEPTH_SYNTHESIS_D8_GATE"

# I-wire-013 (#1327) iter-3c — TWO-TIER per-basket labels (§-1.3 "don't drop, label weak weak"). The
# cross-source LABEL decision moved from per-SENTENCE (the iter-2 P1, structurally near-unsatisfiable
# because strict_verify grounds each sentence to ONE span) to per-BASKET distinct surviving origins:
#   * a basket whose surviving sources clear the corroboration floor  -> CROSS_SOURCE finding;
#   * the post-verify COLLAPSE case (a >=floor-member basket that re-grounded to ONE origin) ->
#     SINGLE_SOURCE-attributed finding, SURFACED with an explicit ``(single source)`` label, never
#     dropped. Faithfulness is UNCHANGED: each sentence still re-passed strict_verify (>=1 grounding
#     span) or was dropped — only the corroboration LABEL is decided per-basket.
_TIER_CROSS_SOURCE = "cross_source"
_TIER_SINGLE_SOURCE = "single_source"
# I-wire-013 (#1327) iter-3c gate P1: the two-tier cross-source boundary is DEFINITIONAL — exactly
# 2 distinct surviving origins — and must NOT ride the tunable corroboration floor. If the
# `min_corroboration()` knob were ever set >2, a genuine two-origin basket would be filtered before
# synthesis (eligibility) or mislabeled below the cross-source tier. Hard-clamped here.
_CROSS_SOURCE_MIN_ORIGINS = 2
_SINGLE_SOURCE_LABEL = "(single source)"

# ── I-deepfix-001 P3_dead_synthesis FIX-1 (#1344) ────────────────────────────────────────────────────
# THE DEFECT: the ~11 eligible multi-source baskets are synthesized by a LIVE LLM FREE RE-DRAFT whose
# paraphrase is then re-grounded by the FROZEN strict_verify, which drops every sentence that reformats a
# number / moves a [#ev:] token / loses >=2-word overlap — so all ~11 fail and this layer returns [].
# THE FIX: at the point a basket's LLM draft yields ZERO strict_verify survivors (the drop-branch), DO
# NOT drop — fall back to the DETERMINISTIC verified multi-cite span-join the BODY composer already emits
# (``verified_compose.compose_basket_multicited_sentence`` with a NULL writer, so only the verbatim K-span
# clauses fire). That span-join re-passes the SAME frozen ``verify_fn`` by construction (each clause IS a
# verified span), resolves to the report's EXISTING [N], and carries the honest per-basket
# cross_source/single_source label. Default-ON kill-switch; OFF => the pre-fix drop-not-fallback path
# EXACTLY (byte-identical). FAITHFULNESS: STRENGTHENS breadth with zero new fabrication path — the fallback
# is re-grounded by the UNCHANGED engine, never trusted prose; the LLM stays an OPTIONAL smoother.
_ENV_SPANJOIN_FALLBACK = "PG_DEPTH_SYNTHESIS_SPANJOIN_FALLBACK"

# #1335 (open-repetition class): the FIX-1 deterministic span-join reuses the SAME
# ``compose_basket_multicited_sentence`` the BODY composer runs on the SAME baskets, so a DS-* digest can
# be TEXT-IDENTICAL (modulo whitespace/citation markers) to a body line. On collision the DS-* line is
# DROPPED (the body line is KEPT) so the finding is not rendered twice. Production default => silent
# dedup-drop + a WARNING log; the default-OFF hard-assert switch turns the collision into a loud
# RuntimeError for the offline behavioral test / a fresh-run canary.
_ENV_BODY_DUP_HARD_ASSERT = "PG_DEPTH_SYNTHESIS_BODY_DUP_HARD_ASSERT"
_CITATION_MARKER_RE = re.compile(r"\[[^\]]*\]")


def _spanjoin_fallback_enabled() -> bool:
    """Default ON. When ON, a basket whose LLM synthesis draft re-grounds to ZERO strict_verify
    survivors falls back to the deterministic verbatim multi-cite span-join instead of being dropped.
    OFF (``PG_DEPTH_SYNTHESIS_SPANJOIN_FALLBACK=0``) => the pre-fix drop-not-fallback path, byte-identical."""
    return os.getenv(_ENV_SPANJOIN_FALLBACK, "1").strip().lower() not in ("", "0", "false", "off", "no")


def _body_dup_hard_assert_enabled() -> bool:
    """Default OFF. When ON (``PG_DEPTH_SYNTHESIS_BODY_DUP_HARD_ASSERT=1``), a DS-*/body duplicate raises a
    loud RuntimeError (the offline behavioral test + fresh-run canary). OFF => silent dedup-drop + WARNING."""
    return os.getenv(_ENV_BODY_DUP_HARD_ASSERT, "0").strip().lower() in ("1", "true", "on", "yes")


def _normalize_for_body_dedup(sentence: str) -> str:
    """The #1335 dedup key: strip EVERY bracketed citation marker (``[N]`` and ``[#ev:...]``), then collapse
    whitespace + lowercase — so a DS-* span-join and a body composer line built from the SAME basket spans
    compare equal regardless of citation-number rendering."""
    bare = _CITATION_MARKER_RE.sub(" ", sentence or "")
    return re.sub(r"\s+", " ", bare).strip().lower()


def _deterministic_spanjoin_fallback(
    basket: Any, scoped_pool: dict, *, verify_fn: Callable[..., Any]
) -> str:
    """FIX-1: the deterministic verbatim multi-cite span-join the BODY composer already emits, driven with
    a NULL writer so ONLY the faithful-by-construction verbatim K-span clauses fire (no model call —
    offline-deterministic). Returns "" on any import/compose failure (=> the basket keeps the pre-fix drop)."""
    try:
        from src.polaris_graph.generator.verified_compose import (  # noqa: PLC0415
            compose_basket_multicited_sentence,
        )
    except Exception:  # pragma: no cover - verified_compose is stable in-tree
        return ""

    def _null_writer(*_a: Any, **_k: Any) -> str:
        return ""  # force the verbatim K-span path (the relational guard never touches a verbatim span)

    try:
        return str(
            compose_basket_multicited_sentence(
                basket, scoped_pool, writer_fn=_null_writer, verify_fn=verify_fn,
            )
            or ""
        )
    except Exception:  # noqa: BLE001 — a compose failure keeps the pre-fix drop, never crashes the layer
        logger.warning(
            "[depth_synthesis] deterministic span-join fallback raised -> basket dropped", exc_info=True
        )
        return ""


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("[depth_synthesis] %s=%r not an int; using default %d", name, raw, default)
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("[depth_synthesis] %s=%r not a float; using default %s", name, raw, default)
        return default


def min_corroboration() -> int:
    """The cross-source corroboration floor (DEFINITIONAL, floored at 2 — never a single source)."""
    return max(_DEFAULT_MIN_SOURCES, _env_int(_ENV_MIN_SOURCES, _DEFAULT_MIN_SOURCES))


def depth_synthesis_d8_gate_enabled() -> bool:
    """Default ON. When ON, each grounded cross-source finding carries its PRE-resolve audit sentence
    + ``ProvenanceToken`` list so the runner can thread it through the SAME 4-role D8 seam the body
    passes (a non-VERIFIED synthesized finding is DROPPED from report.md — TRUE drop-not-sink). OFF =>
    the finding dict is byte-identical (sentence/tier/label only) and no ``DS-*`` claim is built. The
    ``>=2`` distinct-origin floor + the cross/single two-tier split are UNCHANGED either way — this gate
    only adds a D8 pass + a real drop; it never relaxes the faithfulness engine."""
    return os.getenv(_ENV_D8_GATE, "1").strip().lower() not in ("", "0", "false", "off", "no")


def _resolve_model() -> str:
    """The synthesis model is a GENERATOR-role call (§9.1.8) and resolves through the SAME central
    runtime-lock path every other composer uses: ``PG_GENERATOR_MODEL`` — the lock generator
    ``model_slug`` (``config/architecture/polaris_runtime_lock.yaml``; ``verify_lock`` asserts the lock
    slug == this code default). NO parallel per-leg override knob, NO hardcoded model-specific default.
    Mirrors ``multi_section_generator`` (``gen_model = model or PG_GENERATOR_MODEL``) and
    ``verified_compose`` ("NO new model, NO new slug, NO new resolver")."""
    from src.polaris_graph.llm.openrouter_client import PG_GENERATOR_MODEL  # noqa: PLC0415
    return PG_GENERATOR_MODEL


def _resolve_token_budget() -> tuple[int, int]:
    """``(content_max_tokens, reasoning_max_tokens)`` for the depth generator call, resolved through the
    SAME generator-role knobs the section composer uses (``multi_section_generator`` section-writer leg):
    ``PG_SECTION_REASONING_MAX_TOKENS`` bounds the reasoning pool and CONTENT is floored strictly above
    it (+``PG_SECTION_CONTENT_HEADROOM_TOKENS``) so a reasoning-first generator (GLM-5.2) cannot starve
    content (§9.1.8 "never starve"). No parallel ``PG_DEPTH_SYNTHESIS_*`` token knob, no model-specific
    hardcoded default — the budget tracks the section composer."""
    reasoning = max(0, _env_int("PG_SECTION_REASONING_MAX_TOKENS", 16384))
    content = max(
        _env_int("PG_SECTION_MAX_TOKENS", 64000),
        reasoning + _env_int("PG_SECTION_CONTENT_HEADROOM_TOKENS", 8192),
    )
    return content, reasoning


def bib_num_by_evidence_id(bibliography: Any) -> dict[str, int]:
    """Build ``evidence_id -> [N]`` from the report's EXISTING bibliography (``multi.bibliography``).

    The synthesized sentence cites the SAME sources the body already numbered, so its ``[#ev:...]``
    tokens resolve to the report's existing ``[N]`` — NEVER a fresh local renumber (which would
    mis-cite). A bibliography row is ``{num, evidence_id, ...}``; rows missing either key are skipped.
    """
    out: dict[str, int] = {}
    for row in bibliography or []:
        try:
            eid = str(row.get("evidence_id") or "")
            num = row.get("num")
        except AttributeError:
            continue
        if not eid or num is None:
            continue
        try:
            out[eid] = int(num)
        except (TypeError, ValueError):
            continue
    return out


def _resolve_tokens_to_citations(text: str, bib_map: dict[str, int]) -> Optional[str]:
    """Replace each ``[#ev:<id>:<a>-<b>]`` token with the report's existing ``[N]`` number.

    Returns ``None`` (drop the sentence) if ANY token's evidence_id is absent from ``bib_map`` — a
    finding that cannot be cited consistently with the report's own numbering must not ship a dangling
    or fabricated citation. PURE."""
    missing = False

    def _sub(m: re.Match[str]) -> str:
        nonlocal missing
        num = bib_map.get(m.group(1))
        if num is None:
            missing = True
            return m.group(0)
        return f"[{num}]"

    out = _EV_TOKEN_FULL_RE.sub(_sub, text or "")
    if missing:
        return None
    return out


def _default_chrome_screen(sentence: str) -> bool:
    """The ONE shared render-side chrome/truncation predicate (sentence-form). Fail-conservative:
    on any import error keep the sentence (never silently drop a real finding)."""
    try:
        from src.polaris_graph.generator.weighted_enrichment import (  # noqa: PLC0415
            is_render_chrome_or_unrenderable,
        )
    except Exception:  # pragma: no cover - weighted_enrichment is stable in-tree
        return False
    try:
        return bool(is_render_chrome_or_unrenderable(sentence, require_sentence_form=True))
    except Exception:  # pragma: no cover - the predicate is pure in-tree
        return False


def _distinct_origin_supports(basket: Any) -> list[Any]:
    """The basket's isolated-``SUPPORTS`` members deduped to ONE per distinct origin (reuses the
    verified_compose helper so cross-source counting matches the body composer exactly). Fail-soft on
    an import error: fall back to the raw ``supporting_members`` filtered to SUPPORTS."""
    try:
        from src.polaris_graph.generator.verified_compose import (  # noqa: PLC0415
            _distinct_origin_supports as _vc_distinct,
        )
        return _vc_distinct(basket)
    except Exception:  # pragma: no cover - verified_compose is stable in-tree
        members = list(getattr(basket, "supporting_members", None) or [])
        return [
            m for m in members
            if str(getattr(m, "span_verdict", "") or "").upper() == "SUPPORTS"
        ]


# ── I-deepfix-001 COV-DECHROME-BASKETS (#1344) ───────────────────────────────────────────────────────
# THE COVERAGE DEFECT (coverage forensic reconcile): a basket MEMBER whose claim-local span resolves to
# page furniture (cookie/consent banner, author/affiliation byline, ToC dot-leader, dead-fetch shell)
# still arrives here as an isolated-``SUPPORTS`` member — credibility_pass keeps it (correctly, §-1.3
# no-drop) but only excludes it from the strengthening COUNT, never from ``supporting_members``. The
# cross-source pre-pass then feeds that chrome span into the consolidation prompt / span-join; the
# clause fails ``_first_verified_clause`` / re-ground and the WHOLE basket collapses to zero — SILENTLY
# (the forensic had to reconstruct these drops because nothing logged them; the depth pre-pass went
# 3->0 and the one anchored cross-source pair died on chrome member spans). Screening chrome members
# OUT of the corroboration set BEFORE the eligibility gate keeps the pre-pass working on the basket's
# REAL members. §-1.3: page furniture is NOT a corroborating source, so holding a chrome member out of
# a corroboration count is not a DROP of a real source (the source stays in ``supporting_members`` +
# disclosure) — it is the consolidation layer keeping junk out of a count, never a breadth cap / target
# / thinner. Faithfulness engine (strict_verify / NLI / D8 / provenance / span-grounding) is untouched.
# LAW VI: default-ON kill-switch (OFF => byte-identical legacy member selection).
_ENV_DECHROME_MEMBERS = "PG_DEPTH_DECHROME_MEMBERS"


def _dechrome_members_enabled() -> bool:
    """Default ON. Screen chrome/unrenderable basket members out of the cross-source corroboration set
    before eligibility (LAW VI kill-switch: ``PG_DEPTH_DECHROME_MEMBERS=0`` => byte-identical legacy)."""
    return os.getenv(_ENV_DECHROME_MEMBERS, "1").strip().lower() not in ("", "0", "false", "off", "no")


def _member_span_is_chrome(member: Any) -> bool:
    """True iff this member's claim-local span (``direct_quote``) is page furniture / a dead-fetch shell
    / a truncated fragment. Reads the DURABLE ``span_is_chrome`` flag credibility_pass stamps at basket
    build; falls back to re-screening ``direct_quote`` through the SAME shared render-seam predicate
    (``weighted_enrichment.is_render_chrome_or_unrenderable``) for a member built without the flag —
    called EXACTLY like the basket-build screen (no ``require_sentence_form``) so the flag and the
    re-screen never disagree. Fail-CONSERVATIVE: an empty span or any import/screen fault => not-chrome
    (never silently hold out a real member)."""
    if bool(getattr(member, "span_is_chrome", False)):
        return True
    quote = str(getattr(member, "direct_quote", "") or "")
    if not quote.strip():
        return False
    try:
        from src.polaris_graph.generator.weighted_enrichment import (  # noqa: PLC0415
            is_render_chrome_or_unrenderable,
        )
        return bool(is_render_chrome_or_unrenderable(quote))
    except Exception:  # pragma: no cover - weighted_enrichment is stable in-tree
        return False


def _dechrome_distinct_origin_supports(basket: Any, *, log_drops: bool = True) -> list[Any]:
    """The basket's distinct-origin isolated-``SUPPORTS`` members with chrome/unrenderable members held
    OUT of the cross-source corroboration set (the coverage-forensic root fix). §-1.3: page furniture is
    not a corroborating source — this keeps junk out of the corroboration count, it NEVER drops a real
    source (the source stays in ``supporting_members`` + disclosure) and NEVER caps/targets breadth. Each
    held-out member is logged LOUD per-basket (``log_drops``; the forensic flagged these drops were
    SILENT). ``PG_DEPTH_DECHROME_MEMBERS=0`` => ``_distinct_origin_supports`` unchanged."""
    members = _distinct_origin_supports(basket)
    if not _dechrome_members_enabled():
        return members
    kept: list[Any] = []
    for m in members:
        if _member_span_is_chrome(m):
            if log_drops:
                logger.info(
                    "[depth_synthesis] basket %s: member dropped from corroboration: chrome span "
                    "(eid=%s, url=%s)",
                    str(getattr(basket, "claim_cluster_id", "") or ""),
                    str(getattr(m, "evidence_id", "") or ""),
                    str(getattr(m, "source_url", "") or ""),
                )
            continue
        kept.append(m)
    return kept


def _scoped_pool(basket: Any, evidence_pool: dict) -> dict:
    """The basket-id-bound verify pool (the basket's SUPPORTS members' GLOBAL rows). Reuses the
    verified_compose helper so the anti-cross-claim scoping is byte-identical to the body composer."""
    try:
        from src.polaris_graph.generator.verified_compose import (  # noqa: PLC0415
            _basket_scoped_pool,
        )
        return _basket_scoped_pool(basket, evidence_pool)
    except Exception:  # pragma: no cover - verified_compose is stable in-tree
        own = {str(getattr(m, "evidence_id", "") or "") for m in _distinct_origin_supports(basket)}
        own.discard("")
        return {eid: row for eid, row in (evidence_pool or {}).items() if eid in own}


# ── I-deepfix-001 WS-8 (D4) THIRD headline path — basket-level recency RE-RANK ────────────────────────
# Codex found the depth cross-source SYNTHESIS pass orders/consumes ``credibility_analysis.baskets``
# DIRECTLY (the ``for basket in baskets`` loop below), bypassing the recency-ordered unbound-supports
# selection — so a very-old source can still anchor a TOP Analysis finding. This leg DEMOTES an older
# basket in the SYNTHESIS ORDER so it does not headline: a WEIGHT on ordering ONLY — every basket is KEPT
# and still synthesized (§-1.3 no-drop / no-cap / no-filter). It reuses the SAME env curve
# (``PG_M2_RECENCY_*``: grace 5, decay 0.02, floor 0.25) as the bibliography + composition legs, is gated
# on the SAME journal-class signal (``PG_DOCUMENT_TYPE_WEIGHT``) AND a new default-ON
# ``PG_DEPTH_RECENCY_RERANK`` kill-switch; OFF / non-journal-class / no basket carries a parseable year =>
# the basket order is returned UNCHANGED (byte-identical). The faithfulness engine is untouched.
_DEPTH_RECENCY_RERANK_ENV = "PG_DEPTH_RECENCY_RERANK"
_DS_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")


def _depth_recency_rerank_enabled() -> bool:
    """Journal-class gate: the depth-synthesis recency re-rank fires only when ``PG_DOCUMENT_TYPE_WEIGHT``
    is ON (the journal-class run signal, same gate as the bibliography + composition legs) AND
    ``PG_DEPTH_RECENCY_RERANK`` is not disabled (default-ON kill-switch)."""
    dtw = os.environ.get("PG_DOCUMENT_TYPE_WEIGHT", "").strip().lower() in ("1", "true", "on", "yes")
    rerank = os.environ.get(_DEPTH_RECENCY_RERANK_ENV, "1").strip().lower() not in ("0", "false", "no", "off")
    return dtw and rerank


def _ds_publication_year(entry: "dict | None") -> "int | None":
    """Publication year of a member SOURCE dict (the evidence-pool row): an explicit year field, else the
    first plausible 4-digit year in title/statement/url/doi. None when none found (=> neutral, no penalty).
    Same parse shape as the other WS-8 legs (``weighted_enrichment._we_publication_year``)."""
    if not isinstance(entry, dict):
        return None
    for k in ("year", "publication_year", "pub_year"):
        v = entry.get(k)
        if v is None:
            continue
        try:
            y = int(str(v).strip()[:4])
        except (TypeError, ValueError):
            continue
        if 1500 <= y <= 2100:
            return y
    for k in ("title", "statement", "url", "doi"):
        m = _DS_YEAR_RE.search(str(entry.get(k) or ""))
        if m:
            y = int(m.group(0))
            if 1500 <= y <= 2100:
                return y
    return None


def _basket_newest_year(basket: Any, evidence_pool: dict) -> "int | None":
    """A basket's recency = the NEWEST publication year among its distinct-origin SUPPORTS member sources
    (each member's row looked up in ``evidence_pool`` by ``evidence_id``). None when NO member carries a
    parseable year (=> the basket is neutral and keeps its order)."""
    years: list[int] = []
    for m in _distinct_origin_supports(basket):
        eid = str(getattr(m, "evidence_id", "") or "")
        y = _ds_publication_year((evidence_pool or {}).get(eid))
        if y is not None:
            years.append(y)
    return max(years) if years else None


def _depth_recency_factor(year: "int | None", reference_year: "int | None") -> float:
    """A ``[floor, 1.0]`` ordering multiplier: 1.0 within ``grace`` years of the corpus-newest basket,
    decaying linearly by ``decay`` per year older, FLOORED (an old basket is DEMOTED in the synthesis
    order, never dropped). Same env curve as the bibliography + composition legs (``PG_M2_RECENCY_*``).
    Missing year / missing reference / disabled => 1.0 (byte-identical)."""
    if year is None or reference_year is None or not _depth_recency_rerank_enabled():
        return 1.0
    try:
        grace = int(os.getenv("PG_M2_RECENCY_GRACE_YEARS", "5"))
        decay = float(os.getenv("PG_M2_RECENCY_DECAY_PER_YEAR", "0.02"))
        floor = float(os.getenv("PG_M2_RECENCY_FLOOR", "0.25"))
    except (TypeError, ValueError):
        grace, decay, floor = 5, 0.02, 0.25
    age = max(0, int(reference_year) - int(year) - grace)
    return max(floor, 1.0 - decay * age)


def _order_baskets_by_recency(baskets: Any, evidence_pool: dict) -> list:
    """Re-order the baskets so an OLDER basket is DEMOTED below a NEWER one in the synthesis order (so a
    very-old source does not anchor a top Analysis finding) — a STABLE WEIGHT on ordering ONLY: every
    basket is KEPT (§-1.3 no-drop / no-cap / no-filter) and ties (including every basket when
    disabled/unknown-year) preserve their original relative order => byte-identical. OFF /
    non-journal-class / no basket carries a parseable year => the input order is returned UNCHANGED."""
    baskets_list = list(baskets or [])
    if not baskets_list or not _depth_recency_rerank_enabled():
        return baskets_list
    years = [_basket_newest_year(b, evidence_pool) for b in baskets_list]
    parseable = [y for y in years if y is not None]
    ref_year = max(parseable) if parseable else None
    if ref_year is None:
        return baskets_list  # no parseable year anywhere => byte-identical order
    factors = [_depth_recency_factor(y, ref_year) for y in years]
    # STABLE DESC sort by recency factor: an older basket (lower factor) sinks below a newer one; equal
    # factors (the newest baskets + unknown-year neutral baskets, all 1.0) keep their original relative
    # order (byte-identical). No basket is removed — this only permutes; the loop still visits them all.
    order = sorted(range(len(baskets_list)), key=lambda i: -factors[i])
    return [baskets_list[i] for i in order]


def synthesize_cross_source_findings(
    baskets: Any,
    evidence_pool: dict,
    *,
    synthesizer: Callable[[Any, dict], str],
    verify_fn: Callable[..., Any],
    bib_num_by_evidence_id: Optional[dict[str, int]] = None,
    min_sources: Optional[int] = None,
    max_findings: Optional[int] = None,
    chrome_screen: Optional[Callable[[str], bool]] = None,
    body_sentences: Optional[Any] = None,
) -> list[dict]:
    """The grounded cross-source synthesis CORE (deterministic given ``synthesizer`` + ``verify_fn``).

    For each basket carrying ``>= min_sources`` distinct-origin isolated-``SUPPORTS`` members:
      1. ``synthesizer(basket, evidence_pool)`` drafts ONE consolidated cross-source finding carrying
         ``[#ev:<id>:<a>-<b>]`` provenance tokens (the LOCKED generator on the cert path; an injected
         fake in tests).
      2. ``verify_fn(draft, scoped_pool)`` (= ``strict_verify``) RE-GROUNDS each sentence against the
         basket's OWN members and DROPS any that fail (numeric mismatch / overlap / no provenance /
         cross-claim). FIX-1 (#1344): when the LLM draft re-grounds to ZERO survivors the basket falls
         back to the DETERMINISTIC verbatim span-join (``_deterministic_spanjoin_fallback``) re-verified
         by the SAME ``verify_fn`` — no drop-to-empty (default-ON ``PG_DEPTH_SYNTHESIS_SPANJOIN_FALLBACK``;
         OFF => drop-not-fallback). ``scoped_pool`` is basket-id-bound so a cross-basket
         citation fails CLOSED. Each surviving sentence still carries ``>= 1`` grounding span (the
         UNCHANGED faithfulness floor); its ``[#ev:...]`` tokens resolve to the report's EXISTING
         ``[N]`` (never a renumber) — a raw / unmappable / unresolved token drops the WHOLE sentence;
         a chrome/truncated sentence is dropped.
      3. I-wire-013 (#1327) iter-3c — TWO-TIER, decided PER BASKET, not per sentence (the iter-2 P1 was
         structurally near-unsatisfiable: strict_verify grounds each sentence to ONE span, so a single
         sentence almost never carries ``>=2`` distinct surviving sources -> every finding dropped ->
         depth=0). The cross-source LABEL is now decided on the basket's DISTINCT SURVIVING ORIGINS
         accumulated across its kept+resolved sentences (distinct report ``[N]`` numbers when a
         ``bib_num_by_evidence_id`` map is supplied — two evidence rows for the SAME source share one
         ``[N]`` and read as ONE origin; distinct evidence_ids otherwise):
           * ``>= min_sources`` distinct surviving origins -> ``cross_source`` finding;
           * exactly the COLLAPSE case (a ``>=floor``-member basket whose synthesis re-grounded to ONE
             surviving origin) -> ``single_source`` finding, SURFACED with a ``(single source)`` label,
             never dropped (§-1.3 "don't drop, label weak weak").

    Returns the ordered, de-duplicated list of grounded findings as dicts
    ``{"sentence": <[N]-cited markdown sentence>, "tier": cross_source|single_source, "label": str}``
    (no header — ``build_depth_layer`` renders the two tiers under distinct subheads). FAITHFULNESS is
    the ``verify_fn`` — this orchestrator never relaxes it and never resurrects a dropped sentence.
    """
    # I-wire-013 (#1327) iter-3c gate P1: the cross-source boundary (eligibility AND tier label) is the
    # DEFINITIONAL 2 distinct origins — decoupled from the tunable `min_corroboration()` floor /
    # `min_sources` so the two-tier guarantee holds even if that knob is raised. `min_sources` is
    # accepted for back-compat but never widens the boundary above 2.
    floor = _CROSS_SOURCE_MIN_ORIGINS
    cap = _env_int(_ENV_MAX_FINDINGS, _DEFAULT_MAX_FINDINGS) if max_findings is None else int(max_findings)
    screen = _default_chrome_screen if chrome_screen is None else chrome_screen

    # #1335: the BODY composer's already-rendered sentences, normalized for duplicate detection so a FIX-1
    # span-join digest that is text-identical to a body line is dropped (the body line is kept). None /
    # empty => no dedup (byte-identical to the pre-fix render — the guard is a no-op).
    body_norm: set[str] = {
        _normalize_for_body_dedup(str(s)) for s in (body_sentences or []) if str(s or "").strip()
    }
    body_norm.discard("")

    def _collect(report: Any) -> "tuple[list[tuple[str, str, list]], set[str]]":
        """Process a verify report's ``kept_sentences`` into (rendered/audit/token triples, distinct
        surviving report-``[N]`` origins). SHARED per-sentence resolution + chrome screen used for BOTH
        the LLM draft AND the FIX-1 deterministic span-join fallback, so the fallback re-grounds through
        the EXACT same faithfulness path (token->[N] resolution, origin identity, chrome screen)."""
        out_sentences: list[tuple[str, str, list]] = []
        out_origins: set[str] = set()
        for sv in (getattr(report, "kept_sentences", None) or []):
            # PRE-resolve audit sentence + its provenance tokens (the D8 inputs), captured BEFORE the
            # token->[N] resolution below mutates ``sentence`` into the rendered form.
            audit_sentence = str(getattr(sv, "sentence", "") or "").strip()
            toks = list(getattr(sv, "tokens", None) or [])
            sentence = audit_sentence
            if not sentence:
                continue
            # The DISTINCT evidence_ids whose ``[#ev:...]`` token SURVIVED strict_verify on THIS sentence
            # (a kept sentence carries >=1 grounding span — the UNCHANGED faithfulness floor; a sentence
            # with zero surviving provenance tokens is not grounded and is skipped).
            surviving_ids = {m.group(1) for m in _EV_TOKEN_FULL_RE.finditer(sentence)}
            if not surviving_ids:
                continue
            if bib_num_by_evidence_id is not None:
                # Every surviving token must resolve to the report's EXISTING [N]; a raw / unmatched /
                # unresolved token returns None here -> DROP the whole sentence (no dangling [N]).
                resolved = _resolve_tokens_to_citations(sentence, bib_num_by_evidence_id)
                if resolved is None:
                    continue
                sentence = resolved.strip()
                # Defence-in-depth: no raw ``[#ev:...]`` token may survive resolution.
                if _EV_TOKEN_FULL_RE.search(sentence) or "[#ev:" in sentence:
                    continue
                # Origin identity = the report bibliography NUMBER (distinct SOURCES, not raw evidence
                # rows — two rows for the same source share one [N] and count as ONE origin). This is what
                # keeps the cross-source label honest (§-1.1 misstated corroboration is lethal).
                sentence_origins = {bib_num_by_evidence_id.get(eid) for eid in surviving_ids}
                sentence_origins.discard(None)
                if not sentence_origins:
                    continue
                origin_keys = {str(n) for n in sentence_origins}
            else:
                origin_keys = set(surviving_ids)
            if not sentence or screen(sentence):
                continue
            out_sentences.append((sentence, audit_sentence, toks))
            out_origins |= origin_keys
        return out_sentences, out_origins

    findings: list[dict] = []
    seen: set[str] = set()
    # WS-8 (D4) THIRD headline path: DEMOTE an older basket in the synthesis ORDER so a very-old source
    # does not anchor a top Analysis finding — a WEIGHT on ordering ONLY (every basket kept + still
    # synthesized; §-1.3). OFF / non-journal-class / unknown-year => byte-identical order.
    # WS-8 P0 fix (Codex waveDE gate): reorder ONLY when there is NO synthesis cap (cap<=0, the default).
    # With a POSITIVE cap the loop below drops baskets past the cap line, so reordering by recency BEFORE
    # the cap would turn an old-basket demotion into an actual DROP (§-1.3 violation). When capped, keep
    # the original weight order for INCLUSION (byte-identical which baskets survive the cap); recency
    # reorders only in the uncapped case, where every basket is synthesized so nothing can be dropped.
    ordered_baskets = (
        _order_baskets_by_recency(baskets, evidence_pool) if cap <= 0 else list(baskets or [])
    )
    for basket in ordered_baskets:
        if cap > 0 and len(findings) >= cap:
            break
        # COV-DECHROME-BASKETS (#1344): hold chrome/unrenderable member spans OUT of the corroboration
        # set BEFORE the eligibility count (the coverage-forensic root; loud per-basket log). §-1.3: not
        # a corpus-source filter — the source stays in the basket + disclosure; only its chrome span is
        # kept out of the cross-source count. OFF => byte-identical ``_distinct_origin_supports``.
        members = _dechrome_distinct_origin_supports(basket)
        if len(members) < floor:
            continue  # not a CROSS-source CANDIDATE basket (definitional, not a filter of corpus sources)
        scoped_pool = _scoped_pool(basket, evidence_pool)
        # (1) LLM draft -> re-ground through the UNCHANGED verify_fn. Each collected element is a TRIPLE
        # (rendered_[N]_sentence, audit_sentence_pre-resolve, tokens): the audit sentence carries the
        # ``[#ev:...]`` tokens for the D8 seam; the rendered sentence is the post-resolution [N] form.
        basket_sentences: list[tuple[str, str, list]] = []
        basket_origins: set[str] = set()
        draft = ""
        try:
            draft = str(synthesizer(basket, evidence_pool) or "")
        except Exception:  # noqa: BLE001 — a per-basket synthesizer failure never aborts the layer
            logger.warning("[depth_synthesis] synthesizer raised for a basket", exc_info=True)
        if draft.strip():
            try:
                basket_sentences, basket_origins = _collect(verify_fn(draft, scoped_pool))
            except Exception:  # noqa: BLE001 — a verify failure drops the LLM draft, never ships unverified
                logger.warning("[depth_synthesis] verify_fn raised on the LLM draft", exc_info=True)
        # (2) I-deepfix-001 P3_dead_synthesis FIX-1 (#1344): the LLM draft re-grounded to ZERO
        # strict_verify survivors -> DO NOT drop the basket. Fall back to the DETERMINISTIC verified
        # multi-cite span-join the BODY composer already emits (verbatim K-span clauses, NULL writer),
        # re-grounded by the SAME verify_fn. This revives the ~11 eligible multi-source baskets the
        # free-redraft-then-verify path drops to []. Default-ON kill-switch; OFF => the pre-fix
        # drop-not-fallback path (byte-identical: the fallback never runs).
        if not basket_sentences and _spanjoin_fallback_enabled():
            fallback = _deterministic_spanjoin_fallback(basket, scoped_pool, verify_fn=verify_fn)
            if fallback.strip():
                try:
                    basket_sentences, basket_origins = _collect(verify_fn(fallback, scoped_pool))
                except Exception:  # noqa: BLE001 — a verify failure on the fallback keeps the drop
                    logger.warning(
                        "[depth_synthesis] verify_fn raised on the span-join fallback", exc_info=True
                    )
        if not basket_sentences:
            continue  # neither the LLM draft NOR the deterministic fallback re-grounded -> true drop
        # PER-BASKET two-tier decision: >=floor distinct surviving origins -> cross_source; the collapse
        # case (1 surviving origin) -> single_source-attributed (surfaced + labeled, §-1.3). The FIX-1
        # fallback flows through the SAME decision, so a fallback that re-grounds to ONE origin is
        # honestly labeled "(single source)", never a blanket "corroborated" (§-1.1 lethal-if-misstated).
        tier = _TIER_CROSS_SOURCE if len(basket_origins) >= floor else _TIER_SINGLE_SOURCE
        label = "" if tier == _TIER_CROSS_SOURCE else _SINGLE_SOURCE_LABEL
        carry_d8 = depth_synthesis_d8_gate_enabled()
        for rendered, audit_sentence, toks in basket_sentences:
            # #1335 body-vs-DS duplicate guard: the FIX-1 deterministic span-join reuses the SAME
            # compose_basket_multicited_sentence the BODY composer runs on the SAME basket, so a DS-*
            # digest can be text-identical (modulo citation markers) to a body line. Drop the DS-*
            # duplicate (keep the body line) so the finding is not rendered twice; fail LOUD when the
            # hard-assert canary is on.
            if body_norm:
                bkey = _normalize_for_body_dedup(rendered)
                if bkey and bkey in body_norm:
                    if _body_dup_hard_assert_enabled():
                        raise RuntimeError(
                            "[depth_synthesis] #1335 DS-*/body duplicate: a synthesized digest is "
                            f"text-identical to a body composer sentence: {rendered!r}"
                        )
                    logger.warning(
                        "[depth_synthesis] #1335 DS-*/body duplicate dropped (kept body line): %.160s",
                        rendered,
                    )
                    continue
            key = re.sub(r"\s+", " ", rendered).strip().lower()
            if key in seen:
                continue
            seen.add(key)
            finding: dict = {"sentence": rendered, "tier": tier, "label": label}
            if carry_d8:
                # The PRE-resolve audit sentence (carries [#ev:...] tokens) + its ProvenanceToken list
                # are the D8 seam inputs. ``build_depth_layer`` reads ONLY sentence/tier/label, so these
                # two extra keys are inert to the render; the native Gate-B builder consumes them. Gate
                # OFF => keys omitted => the dict is byte-identical to the pre-change shape.
                finding["audit_sentence"] = audit_sentence
                finding["tokens"] = toks
            findings.append(finding)
            if cap > 0 and len(findings) >= cap:
                break
    return findings


# ── the live LLM synthesizer (cert path) ─────────────────────────────────────────────────────────
_SYNTHESIS_SYSTEM = (
    "You consolidate several already-verified evidence spans that report the SAME finding into ONE "
    "clean, plain, declarative news-style sentence. You state the consolidated finding, then — only "
    "if the spans themselves show it — note where the sources AGREE or where they are in TENSION. You "
    "NEVER add a fact, number, or claim that is not in a provided span. You copy every number "
    "(decimal, percent, integer, dose) exactly as written; never round, never convert units. You end "
    "the sentence with the exact provenance token(s) supplied, copied character-for-character; you "
    "never invent or edit a token. You output EXACTLY one sentence, nothing else — no markdown, no "
    "bullets, no headings, no preamble."
)


def _build_synthesis_prompt(basket: Any, members: list, evidence_pool: dict) -> str:
    """One cross-source prompt: every distinct-origin SUPPORTS member's verified span + the EXACT
    canonical token (``_member_global_span``). Returns "" when no member resolves a global span."""
    from src.polaris_graph.generator.verified_compose import _member_global_span  # noqa: PLC0415

    subject = str(getattr(basket, "claim_text", "") or getattr(basket, "subject", "") or "").strip()
    lines: list[str] = [
        "Consolidate the corroborating evidence spans below into ONE clean, plain, declarative "
        "news-style sentence that states the shared finding and (only if the spans show it) where "
        "the sources agree or are in tension. End the sentence with EVERY provenance token shown "
        "below, each copied character-for-character. Copy every number verbatim. Output one sentence.",
        "",
    ]
    if subject:
        lines.append(f"CLAIM UNDER CORROBORATION: {subject}")
        lines.append("")
    emitted = 0
    for i, m in enumerate(members, start=1):
        eid = str(getattr(m, "evidence_id", "") or "")
        gspan = _member_global_span(m, evidence_pool)
        quote = str(getattr(m, "direct_quote", "") or "").strip()
        if not eid or gspan is None or not quote:
            continue
        token = f"[#ev:{eid}:{gspan[0]}-{gspan[1]}]"
        lines.append(f"SOURCE {i}: {quote}")
        lines.append(f"TOKEN {i} (append verbatim): {token}")
        lines.append("")
        emitted += 1
    if emitted == 0:
        return ""
    return "\n".join(lines)


async def _synthesize_one_basket(
    basket: Any,
    evidence_pool: dict,
    *,
    model: str,
    max_tokens: int,
    reasoning_max_tokens: int,
    temperature: float,
    call_deadline_s: float,
) -> str:
    """ONE live generator call: consolidate a basket's SUPPORTS spans into one cross-source sentence
    carrying the canonical tokens. Returns "" on any error/timeout (the basket is simply absent from
    the synthesis -> the layer omits it; never crashes the run). Chrome members are input-screened
    BEFORE the call (a paraphrase would mangle the multi-word markers, so only an input screen catches
    them)."""
    from src.polaris_graph.generator.verified_compose import _compose_junk_screen  # noqa: PLC0415
    from src.polaris_graph.llm.openrouter_client import OpenRouterClient  # noqa: PLC0415

    # COV-DECHROME-BASKETS (#1344): hold chrome/unrenderable member spans OUT of the SYNTHESIS input
    # BEFORE the prompt is built (the coverage-forensic root: a chrome member span mangles the multi-word
    # markers and collapses the pre-pass). The eligibility gate already logged the per-basket drop, so
    # ``log_drops=False`` here avoids double-logging the same member. The existing ``_compose_junk_screen``
    # allowlist pass is retained as an inner belt-and-suspenders filter (no regression).
    members = [
        m for m in _dechrome_distinct_origin_supports(basket, log_drops=False)
        if not _compose_junk_screen(str(getattr(m, "direct_quote", "") or ""))
    ]
    if len(members) < min_corroboration():
        return ""
    prompt = _build_synthesis_prompt(basket, members, evidence_pool)
    if not prompt:
        return ""
    reasoning_arg = reasoning_max_tokens if reasoning_max_tokens and reasoning_max_tokens > 0 else None
    client = OpenRouterClient(model=model)
    try:
        response = await asyncio.wait_for(
            client.generate(
                prompt=prompt,
                system=_SYNTHESIS_SYSTEM,
                max_tokens=max_tokens,
                temperature=temperature,
                reasoning_max_tokens=reasoning_arg,
            ),
            timeout=call_deadline_s,
        )
        return str(getattr(response, "content", "") or "")
    except Exception:  # noqa: BLE001 — any error/timeout degrades to absent (always-release)
        logger.warning("[depth_synthesis] basket synthesis call failed -> omitted", exc_info=True)
        return ""
    finally:
        try:
            await client.close()
        except Exception:  # noqa: BLE001 — best-effort teardown; never mask the result
            logger.debug("[depth_synthesis] client.close() raised on teardown", exc_info=True)


async def depth_synthesis_pre_pass(
    baskets: Any,
    evidence_pool: dict,
    *,
    min_sources: Optional[int] = None,
) -> dict:
    """ASYNC pre-pass: precompute one cross-source draft per high-corroboration basket, keyed by the
    basket's canonical ``claim_cluster_id``, under a bounded semaphore + a per-call deadline + an OUTER
    wall-deadline. Reuses the PROVEN abstractive-writer teardown-drain (abandon a wall-stuck task; never
    await it — the httpx-teardown hang class). A skipped/failed/abandoned basket is simply absent ->
    the sync synthesizer returns "" -> the layer omits that finding (always-release, fail-open)."""
    from src.polaris_graph.generator.abstractive_writer import (  # noqa: PLC0415
        _DETACHED_WRITER_TASKS,
        _drain_detached_writer_task,
        _force_drop_detached_writer_task,
        install_teardown_drain_hook,
    )

    # I-wire-013 (#1327) iter-3c gate P1: the cross-source boundary (eligibility AND tier label) is the
    # DEFINITIONAL 2 distinct origins — decoupled from the tunable `min_corroboration()` floor /
    # `min_sources` so the two-tier guarantee holds even if that knob is raised. `min_sources` is
    # accepted for back-compat but never widens the boundary above 2.
    floor = _CROSS_SOURCE_MIN_ORIGINS
    model = _resolve_model()
    max_tokens, reasoning_max_tokens = _resolve_token_budget()
    max_tokens = max(1, max_tokens)
    reasoning_max_tokens = max(0, reasoning_max_tokens)
    temperature = _env_float(_ENV_TEMPERATURE, _DEFAULT_TEMPERATURE)
    call_deadline_s = max(1.0, _env_float(_ENV_CALL_DEADLINE_S, _DEFAULT_CALL_DEADLINE_S))
    wall_deadline_s = max(1.0, _env_float(_ENV_WALL_DEADLINE_S, _DEFAULT_WALL_DEADLINE_S))
    concurrency = max(1, _env_int(_ENV_CONCURRENCY, _DEFAULT_CONCURRENCY))

    # COV-DECHROME-BASKETS (#1344): eligibility counts the DECHROMED corroboration set (chrome member
    # spans held out) so a basket whose only "second origin" is page furniture is not falsely eligible.
    # This is also the ONE per-basket LOUD log site for the async path (``log_drops`` default True);
    # ``_synthesize_one_basket`` re-derives with ``log_drops=False`` to avoid double-logging.
    eligible = [
        b for b in (baskets or [])
        if str(getattr(b, "claim_cluster_id", "") or "")
        and len(_dechrome_distinct_origin_supports(b)) >= floor
    ]
    out: dict = {}
    if not eligible:
        logger.info("[depth_synthesis] pre-pass: 0 eligible high-corroboration baskets (model=%s)", model)
        return out

    sem = asyncio.Semaphore(concurrency)

    async def _one(basket: Any) -> None:
        key = str(getattr(basket, "claim_cluster_id", "") or "")
        async with sem:
            draft = await _synthesize_one_basket(
                basket, evidence_pool,
                model=model, max_tokens=max_tokens,
                reasoning_max_tokens=reasoning_max_tokens, temperature=temperature,
                call_deadline_s=call_deadline_s,
            )
        if draft:
            out[key] = draft

    tasks = [asyncio.ensure_future(_one(b)) for b in eligible]
    try:
        install_teardown_drain_hook(asyncio.get_running_loop())
    except Exception:  # noqa: BLE001 — hook install is best-effort
        logger.debug("[depth_synthesis] teardown-drain hook install skipped", exc_info=True)

    done, pending = await asyncio.wait(tasks, timeout=wall_deadline_s)
    if pending:
        logger.warning(
            "[depth_synthesis] pre-pass WALL %.0fs hit: ABANDONING %d/%d pending basket task(s) "
            "(fail-open). %d drafted before the wall.", wall_deadline_s, len(pending), len(tasks), len(out),
        )
        for t in pending:
            _DETACHED_WRITER_TASKS.add(t)
            t.add_done_callback(_drain_detached_writer_task)
            t.cancel()
            _force_drop_detached_writer_task(t)
    for t in done:
        exc = t.exception()
        if exc is not None:
            logger.warning("[depth_synthesis] a pre-pass basket task raised: %r", exc)
    logger.info(
        "[depth_synthesis] pre-pass complete: %d/%d baskets drafted (model=%s, wall=%.0fs, abandoned=%d)",
        len(out), len(eligible), model, wall_deadline_s, len(pending),
    )
    return out


def make_depth_synthesizer(precomputed: dict) -> Callable[[Any, dict], str]:
    """The SYNC ``synthesizer`` ``synthesize_cross_source_findings`` reads: a pure dict lookup keyed by
    the basket's canonical ``claim_cluster_id``. A missing key returns "" -> that basket is omitted
    from the synthesis layer (never a crash). Mirrors ``abstractive_writer.make_abstractive_writer_fn``."""

    def _synth(basket: Any, _pool: dict) -> str:
        return str(precomputed.get(str(getattr(basket, "claim_cluster_id", "") or ""), "") or "")

    return _synth
