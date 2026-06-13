"""I-cred-012 (#1162) — credibility-analysis pass ORCHESTRATOR (the activation chain).

Pure orchestrator that runs the committed P4→P3→P2→P5→P6 redesign chain over the generator's EFFECTIVE
evidence pool and returns the disclosure inputs (``credibility_by_evidence``, ``origin_by_evidence``,
``claims``, ``edges``, ``weight_mass``). The sweep runner calls it under the master slate
``PG_SWEEP_CREDIBILITY_REDESIGN``; OFF ⇒ not invoked ⇒ byte-identical. ADVISORY only: ``strict_verify`` +
the 4-role D8 release policy stay the ONLY binding gates — nothing here keeps/drops a sentence or flips
release.

FAIL-LOUD (the drb_72 silent-downgrade lesson, locked in the I-cred-012 architecture iter-1/4 resolutions):
a dead production judge (P2 ``judge_error``) or a row missing ``evidence_id`` ABORTS the pass
(``CredibilityPassError``) rather than degrading to a false-green advisory. The activation orchestrator
escalates the modules' OFFLINE fail-soft into a hard abort.

Order (locked): P4 copied-annotated rows (fail-loud on missing eid) → P3 supersession → P2 score
(fail-loud on judge_error) → POST-P3 credibility = P2 × P3 multiplier (certainty carried) → P5 claim graph
→ P6 weight-mass over the POST-P3 judgments. P10 dissent + the M-52 effective-pool hoist + the P8
render-site wrapper are the per-hook sub-issues; this module is the chain core they consume.
"""
from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass, field
from typing import Any, Callable

from src.polaris_graph.authority.credibility_skill import score_source_credibility
from src.polaris_graph.authority.supersession import supersession_adjustment
from src.polaris_graph.synthesis.claim_graph import build_claim_graph
from src.polaris_graph.synthesis.independence_collapse import collapse_independent_origins
from src.polaris_graph.synthesis.weight_mass import aggregate_weight_mass

_MASTER_FLAG = "PG_SWEEP_CREDIBILITY_REDESIGN"
_OFF_VALUES = frozenset({"", "0", "false", "off", "no"})


def credibility_redesign_enabled() -> bool:
    """The master activation slate. OFF ⇒ the runner never calls the pass ⇒ byte-identical."""
    return os.environ.get(_MASTER_FLAG, "").strip().lower() not in _OFF_VALUES


class CredibilityPassError(RuntimeError):
    """Activated pass cannot complete faithfully — fail-loud, never a silent false-green advisory."""


@dataclass
class EvidenceCredibility:
    evidence_id: str
    credibility_weight: float       # POST-P3: P2 weight × supersession multiplier, clamped [0,1]
    reliability_score: float
    relevance_score: float
    origin_cluster_id: str
    is_canonical_origin: bool
    certainty_downgrade: bool       # carried explicitly from P3 (supersession), not folded into the number
    soft_warning: str | None


# ─────────────────────────────────────────────────────────────────────────────
# I-arch-002 [8] / Wave-3 design §5/§6 — the per-claim ClaimBasket.
#
# A basket is one claim_cluster_id's whole group of supporting sources. Principle
# 2 (CONSOLIDATE, don't DROP): ``supporting_members`` keeps ALL sources, never a
# representative. Principle 3 (BASKET FAITHFULNESS): the verdict is decided against
# the WHOLE basket, but ``verified_support_origin_count`` is computed by ISOLATED
# per-member verification — each member verified against its OWN single span, never
# a multi-citation union (design §0/§5 FIX-3: a union that passes while a member
# fails alone must count that member UNVERIFIED). ``basket_verdict`` is a LABEL only
# (design §6): it may downgrade / drop / label, but NEVER resurrect a
# strict_verify-dropped sentence.
#
# These are ADVISORY side-outputs assembled under the master flag. strict_verify +
# the 4-role D8 release policy stay the ONLY binding gates — nothing here keeps or
# drops a sentence or flips release.
# ─────────────────────────────────────────────────────────────────────────────

# basket_verdict labels (design §5 — NAMED constants, no inline magic strings).
BASKET_VERDICT_FULL = "full"            # every supporting member independently verified on its own span
BASKET_VERDICT_PARTIAL = "partial"      # some but not all members verified
BASKET_VERDICT_CONTESTED = "contested"  # >=1 refuter edge references this cluster (user judges)
BASKET_VERDICT_UNVERIFIED = "unverified"  # no member verified alone


@dataclass
class BasketMember:
    """One source backing a claim basket, carrying its OWN isolated span verdict.

    ``span_verdict`` is the result of verifying this member ALONE against its own
    span (SUPPORTS / UNSUPPORTED). It is never a union verdict — that is the whole
    anti-laundering property (design §5 FIX-3). A member with no verified span is
    kept (Principle 2: never dropped) and shown as UNSUPPORTED.
    """

    evidence_id: str
    source_url: str
    source_tier: str
    origin_cluster_id: str
    credibility_weight: float | None
    authority_score: float
    span: tuple                     # (start, end) of the member's own verified span
    direct_quote: str               # the span text the member was verified against
    # "SUPPORTS" | "UNSUPPORTED" — the BINARY result of isolated per-member
    # verification. Design §5's enum also lists CONTEXT, but that is a RENDER-layer
    # (P5.x) distinction (a span shown as background, not support); isolated
    # strict_verify is pass/fail, so this assembly emits only the two binary values.
    span_verdict: str


@dataclass
class ClaimBasket:
    """A per-claim basket — the group of sources carrying the SAME claim (design §5).

    ``supporting_members`` keeps ALL sources (never dropped). ``refuter_cluster_ids``
    REFERENCE the contradicting clusters (not duplicated). ``total_clustered_origin_count``
    is ADVISORY (the clustered, not-verified origin count from weight_mass) and is
    NEVER rendered as support strength. ``verified_support_origin_count`` —
    the ONLY strengthening count — is the number of DISTINCT origin clusters whose
    member passed ISOLATED per-member verification on its own span. ``basket_verdict``
    is a LABEL derived from those counts + refuter references; it can never upgrade a
    dropped sentence.
    """

    claim_cluster_id: str
    claim_text: str
    subject: str
    predicate: str
    supporting_members: list                 # list[BasketMember] — ALL sources, never dropped
    refuter_cluster_ids: tuple               # REFERENCE only (design §5)
    weight_mass: float                       # authority-only, copy-uninflatable (from weight_mass.py)
    total_clustered_origin_count: int        # ADVISORY ONLY — never rendered as support strength
    verified_support_origin_count: int       # isolated-verified distinct origins (the only strengthening count)
    basket_verdict: str                      # full | partial | contested | unverified (LABEL only)


@dataclass
class CredibilityAnalysis:
    credibility_by_evidence: dict   # evidence_id -> EvidenceCredibility
    origin_by_evidence: dict        # evidence_id -> origin_cluster_id
    claims: list                    # AtomicClaim[] (Phase-5)
    edges: list                     # ContradictionEdge[] (Phase-5)
    weight_mass: list               # ClaimWeightMass[] (Phase-6)
    # I-arch-002 [8] — per-claim baskets + the sentence->claim_cluster_id binding.
    # Defaulted so the empty-rows early-return (and any legacy caller) still builds.
    baskets: list = field(default_factory=list)             # ClaimBasket[]
    cluster_id_by_evidence: dict = field(default_factory=dict)  # evidence_id -> claim_cluster_id[] (binding)


def _require_evidence_id(row: dict, index: int) -> str:
    eid = str((row or {}).get("evidence_id") or "").strip()
    if not eid:
        raise CredibilityPassError(
            f"abort_credibility_pass_error: evidence row {index} has no evidence_id (cannot disclose a "
            f"claim whose source can't be identified)"
        )
    return eid


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


# ── I-arch-002 [8] — ClaimBasket assembly + isolated per-member verification ───


def _row_span_text(row: dict) -> str:
    """The member's own span text (the same field strict_verify reads). Mirrors
    ``provenance_generator``'s ``direct_quote or statement`` resolution so the
    isolated verification runs against the SAME bytes strict_verify would."""
    return str((row or {}).get("direct_quote") or (row or {}).get("statement") or "")


def _verify_member_in_isolation(
    claim_text: str,
    member_row: dict,
    *,
    verify_fn: Callable,
) -> str:
    """Verify ONE member against ITS OWN single span — never a union (design §5 FIX-3).

    Builds a single-provenance-token sentence (``<claim_text> [#ev:<eid>:0-<len>]``)
    so ``verify_sentence_provenance`` has EXACTLY ONE token. The per-token union loop
    inside the verifier (which aggregates decimals/text across MULTIPLE tokens) is the
    laundering path; one token means no union, so a member whose own span lacks the
    claim's number/content fails ALONE — even if a multi-citation union would pass.

    Returns ``"SUPPORTS"`` iff the isolated sentence is verified, else ``"UNSUPPORTED"``.
    The verifier is INJECTED (production ``verify_sentence_provenance`` by default; a
    deterministic fake in tests) and is NEVER re-run as a gate — this is advisory.
    """
    eid = str((member_row or {}).get("evidence_id") or "")
    span = _row_span_text(member_row)
    if not eid or not span:
        return "UNSUPPORTED"
    # Defensive single-token guarantee (the anti-laundering invariant, design §5
    # FIX-3): strip ANY stray provenance / calc token already in the claim text so
    # the appended one is the ONLY token. With exactly one token the verifier's
    # per-token union loop cannot aggregate this member's span with any other — a
    # member whose own span lacks the claim fails ALONE.
    from src.polaris_graph.generator.provenance_generator import (  # noqa: PLC0415
        _CALC_TOKEN_RE,
        _PROVENANCE_TOKEN_RE,
    )
    safe_text = _PROVENANCE_TOKEN_RE.sub(" ", str(claim_text or ""))
    safe_text = _CALC_TOKEN_RE.sub(" ", safe_text).strip()
    # ONE token spanning the member's whole own span.
    sentence = f"{safe_text} [#ev:{eid}:0-{len(span)}]"
    pool = {eid: dict(member_row)}
    try:
        result = verify_fn(sentence, pool)
    except Exception:
        # Advisory path: a verifier failure on one member is conservatively UNSUPPORTED
        # (never resurrects the member, never aborts the basket) — fail-closed for the
        # strengthening count, which can only ever UNDERCOUNT, never inflate.
        return "UNSUPPORTED"
    return "SUPPORTS" if bool(getattr(result, "is_verified", False)) else "UNSUPPORTED"


def _assemble_baskets(
    graph: Any,
    weight_mass: list,
    annotated: list[dict],
    credibility_by_evidence: dict,
    *,
    verify_fn: Callable,
) -> list:
    """Assemble one ClaimBasket per claim cluster (design §5/§6).

    Principle 2: ALL members of a cluster are kept (``supporting_members`` is the full
    group, never a representative). Principle 3: ``verified_support_origin_count`` is the
    count of DISTINCT origin clusters whose member passed ISOLATED per-member verification
    (NOT the raw passing-member count, and NOT ``weight_mass.independent_origin_count`` —
    that is the clustered, not-verified count, surfaced ONLY as the ADVISORY
    ``total_clustered_origin_count``). ``basket_verdict`` is a pure LABEL.
    """
    row_by_eid = {str(r.get("evidence_id", "")): r for r in (annotated or [])}
    wm_by_cluster = {
        str(getattr(w, "claim_cluster_id", "") or ""): w for w in (weight_mass or [])
    }

    # Refuter references (design §5): for each cluster, the OTHER cluster ids it is
    # joined to by a ContradictionEdge. REFERENCE only — never duplicated into the basket.
    refuters_by_cluster: dict[str, set] = {}
    for edge in (getattr(graph, "edges", None) or []):
        ids = [str(c) for c in (getattr(edge, "claim_cluster_ids", ()) or ()) if str(c)]
        for cid in ids:
            for other in ids:
                if other != cid:
                    refuters_by_cluster.setdefault(cid, set()).add(other)

    clusters = getattr(graph, "clusters", None) or {}
    claims = getattr(graph, "claims", None) or []

    baskets: list[ClaimBasket] = []
    for cluster_id in sorted(clusters):
        member_indices = clusters[cluster_id]
        member_claims = [claims[i] for i in member_indices]
        if not member_claims:
            continue
        head = member_claims[0]
        cwm = wm_by_cluster.get(cluster_id)

        members: list[BasketMember] = []
        verified_origin_ids: set[str] = set()
        verified_any = False
        all_verified = True
        for claim in member_claims:
            eid = str(getattr(claim, "evidence_id", "") or "")
            row = row_by_eid.get(eid, {})
            ec = credibility_by_evidence.get(eid)
            origin_id = str(getattr(ec, "origin_cluster_id", "") or "") if ec else ""
            if not origin_id:
                # an unmapped member is its own independent origin (mirrors weight_mass)
                origin_id = f"origin::{eid}"
            span = _row_span_text(row)
            # ISOLATED per-member verification (design §5 FIX-3): the claim's TEXT against
            # THIS member's own single span — never a union of basket spans.
            verdict = _verify_member_in_isolation(
                str(getattr(claim, "text", "") or ""), row, verify_fn=verify_fn,
            )
            if verdict == "SUPPORTS":
                verified_any = True
                verified_origin_ids.add(origin_id)
            else:
                all_verified = False
            members.append(BasketMember(
                evidence_id=eid,
                source_url=str(getattr(claim, "source_url", "") or row.get("source_url", "")),
                source_tier=str(getattr(claim, "source_tier", "") or row.get("tier", "")),
                origin_cluster_id=origin_id,
                credibility_weight=(getattr(ec, "credibility_weight", None) if ec else None),
                authority_score=_clamp01(float(row.get("authority_score", 0.0) or 0.0)),
                span=(0, len(span)),
                direct_quote=span,
                span_verdict=verdict,
            ))

        refuter_ids = tuple(sorted(refuters_by_cluster.get(cluster_id, set())))
        # verified count = DISTINCT verified origin clusters (the only strengthening count).
        verified_support_origin_count = len(verified_origin_ids)
        # advisory clustered count (NOT verified) — sourced from weight_mass, never reused
        # as the strengthening count.
        total_clustered_origin_count = int(
            getattr(cwm, "independent_origin_count", 0) or 0
        ) if cwm is not None else 0

        # basket_verdict is a pure LABEL (design §6): derived from verified counts +
        # refuter references. It NEVER feeds is_verified / strict_verify — a downstream
        # consumer reads it for display, it can never resurrect a dropped sentence.
        if refuter_ids:
            basket_verdict = BASKET_VERDICT_CONTESTED
        elif not verified_any:
            basket_verdict = BASKET_VERDICT_UNVERIFIED
        elif all_verified:
            basket_verdict = BASKET_VERDICT_FULL
        else:
            basket_verdict = BASKET_VERDICT_PARTIAL

        baskets.append(ClaimBasket(
            claim_cluster_id=cluster_id,
            claim_text=str(getattr(head, "text", "") or ""),
            subject=str(getattr(head, "subject", "") or ""),
            predicate=str(getattr(head, "predicate", "") or ""),
            supporting_members=members,
            refuter_cluster_ids=refuter_ids,
            weight_mass=float(getattr(cwm, "weight_mass", 0.0) or 0.0) if cwm is not None else 0.0,
            total_clustered_origin_count=total_clustered_origin_count,
            verified_support_origin_count=verified_support_origin_count,
            basket_verdict=basket_verdict,
        ))
    return baskets


def run_credibility_analysis(
    research_question: str,
    rows: list[dict],
    *,
    gov_suffixes: tuple,
    domain: str | None = None,
    judge: Callable | None = None,
    now_year: int | None = None,
) -> CredibilityAnalysis:
    """Run the P4→P3→P2→P5→P6 chain over the EFFECTIVE evidence pool. Fail-loud on judge_error / missing eid.

    ``rows`` MUST already be the generator's effective pool (post-M-52, post-dissent); ``gov_suffixes`` is
    the PSL gov-suffix tuple the rest of the pipeline uses (dependency-injected, no global). ``judge`` is the
    production credibility judge (injected); None ⇒ priors-only, which the runner forbids under activation.
    """
    if not rows:
        return CredibilityAnalysis({}, {}, [], [], [])
    if judge is None:
        # Codex I-cred-012 iter-5 P1: activation requires the PRODUCTION judge. P2 with judge=None returns
        # priors-only with judge_error=False, so a miswired master-on run would ship a false-green advisory.
        # The orchestrator is only ever called under activation, so a missing judge is fail-closed.
        raise CredibilityPassError(
            "abort_credibility_pass_error: the activated credibility pass requires a callable production "
            "judge; refusing to run priors-only (a false-green advisory). Wire the production judge or "
            "leave PG_SWEEP_CREDIBILITY_REDESIGN off."
        )
    from src.polaris_graph.llm.openrouter_client import BudgetExceededError
    try:
        return _run_chain(
            research_question, rows,
            gov_suffixes=gov_suffixes, domain=domain, judge=judge, now_year=now_year,
        )
    except (CredibilityPassError, BudgetExceededError):
        # CredibilityPassError = fail-loud abort; BudgetExceededError (Codex #012a P1-2) must reach the
        # sweep's budget-abort path cleanly, NOT be masked as a generic credibility-pass error.
        raise
    except Exception as exc:  # ANY OTHER wired-module failure → fail-loud abort, never a silent false-green
        raise CredibilityPassError(
            f"abort_credibility_pass_error: a wired credibility module failed "
            f"({type(exc).__name__}): {exc}"
        ) from exc


def _run_chain(
    research_question: str,
    rows: list[dict],
    *,
    gov_suffixes: tuple,
    domain: str | None,
    judge: Callable | None,
    now_year: int | None,
) -> CredibilityAnalysis:
    """The P4→P3→P2→P5→P6 chain body; wrapped by run_credibility_analysis for the fail-loud posture."""
    # ── P4: independent-origin collapse → per-row assignment, on COPIED rows (never mutate the caller) ──
    collapse = collapse_independent_origins(rows, gov_suffixes=gov_suffixes)
    if len(collapse.assignments) != len(rows):
        raise CredibilityPassError(
            "abort_independence_annotation_gap: P4 returned "
            f"{len(collapse.assignments)} assignments for {len(rows)} rows"
        )
    annotated: list[dict] = []
    origin_by_evidence: dict = {}
    for i, row in enumerate(rows):
        eid = _require_evidence_id(row, i)
        assignment = collapse.assignments[i]
        new_row = dict(row)  # COPY
        new_row["origin_cluster_id"] = assignment.origin_cluster_id
        new_row["is_canonical_origin"] = assignment.is_canonical_origin
        annotated.append(new_row)
        origin_by_evidence[eid] = assignment.origin_cluster_id

    # ── P3: supersession multiplier per source ──
    supers_by_evidence = {
        _require_evidence_id(row, i): supersession_adjustment(row, now_year=now_year)
        for i, row in enumerate(annotated)
    }

    # ── P2: credibility judgments — FAIL-LOUD on any judge_error under activation ──
    judgments = score_source_credibility(research_question, annotated, domain=domain, judge=judge)
    errored = [j.evidence_id for j in judgments if getattr(j, "judge_error", False)]
    if errored:
        raise CredibilityPassError(
            f"abort_credibility_pass_error: the production credibility judge failed for "
            f"{len(errored)} source(s) (e.g. {errored[:5]}); refusing to ship a priors-only false-green"
        )

    # ── POST-P3 credibility = P2 weight × supersession multiplier (certainty carried, not folded away) ──
    credibility_by_evidence: dict = {}
    for row, judgment in zip(annotated, judgments):
        eid = judgment.evidence_id
        supersession = supers_by_evidence.get(eid)
        multiplier = supersession.multiplier if supersession else 1.0
        credibility_by_evidence[eid] = EvidenceCredibility(
            evidence_id=eid,
            credibility_weight=_clamp01(judgment.credibility_weight * multiplier),
            reliability_score=judgment.reliability_score,
            relevance_score=judgment.relevance_score,
            origin_cluster_id=origin_by_evidence.get(eid, ""),
            is_canonical_origin=bool(row.get("is_canonical_origin")),
            certainty_downgrade=bool(supersession.certainty_downgrade) if supersession else False,
            soft_warning=(supersession.soft_warning if supersession else None),
        )

    # POST-P3 judgments for downstream — P6 disclosure must use the post-P3 credibility, not raw P2.
    adjusted_judgments = [
        dataclasses.replace(j, credibility_weight=credibility_by_evidence[j.evidence_id].credibility_weight)
        for j in judgments
    ]

    # ── P5: claim graph (atomic claims + contradiction edges) ──
    graph = build_claim_graph(annotated, domain=domain)

    # ── P6: origin-cluster weight-mass (mass = authority(canonical) ONLY; credibility disclosed) ──
    weight_mass = aggregate_weight_mass(graph.claims, annotated, adjusted_judgments)

    # ── I-arch-002 [8] — assemble per-claim baskets with ISOLATED per-member verification.
    # The verifier is the PRODUCTION single-sentence callable, lazy-imported here so this
    # module's import graph stays decoupled from the big provenance module (mirrors the
    # local imports at run_credibility_analysis / apply_disclosure_to_svs). It is used
    # ADVISORY only — strict_verify itself is never re-run as a gate.
    from src.polaris_graph.generator.provenance_generator import (  # noqa: PLC0415
        verify_sentence_provenance,
    )
    baskets = _assemble_baskets(
        graph, weight_mass, annotated, credibility_by_evidence,
        verify_fn=verify_sentence_provenance,
    )

    # ── sentence -> claim_cluster_id binding (design §6): evidence_id -> the cluster
    #    id(s) its atomic claim(s) belong to. The resolve sites today carry only cited
    #    tokens (each an evidence_id), so this lets the render layer (P5.x) map a cited
    #    token to the basket whose verified count it should surface. Reference data only.
    cluster_id_by_evidence: dict[str, list[str]] = {}
    for claim in (graph.claims or []):
        eid = str(getattr(claim, "evidence_id", "") or "")
        ccid = str(getattr(claim, "claim_cluster_id", "") or "")
        if not eid or not ccid:
            continue
        bucket = cluster_id_by_evidence.setdefault(eid, [])
        if ccid not in bucket:
            bucket.append(ccid)

    return CredibilityAnalysis(
        credibility_by_evidence=credibility_by_evidence,
        origin_by_evidence=origin_by_evidence,
        claims=graph.claims,
        edges=graph.edges,
        weight_mass=weight_mass,
        baskets=baskets,
        cluster_id_by_evidence=cluster_id_by_evidence,
    )


# ─────────────────────────────────────────────────────────────────────────────
# I-cred-008b (#1162) — the SHARED per-claim disclosure populate+carrier+coverage
# helper, called at ALL FOUR cited-prose resolve sites (legacy _run_section,
# fact-dedup re-resolve, V30 contract runner, quantified-analysis). ONE copy of
# this faithfulness-critical logic so it cannot drift across the four sites.
# ─────────────────────────────────────────────────────────────────────────────

def _cited_evidence_ids_for_coverage(sv: Any) -> list[str]:
    """The cited evidence_ids on a RESOLVER-EMITTED SentenceVerification (its tokens)."""
    out: list[str] = []
    for token in (getattr(sv, "tokens", None) or []):
        eid = str(getattr(token, "evidence_id", "") or "")
        if eid:
            out.append(eid)
    return out


def apply_disclosure_to_svs(svs: list, analysis: "CredibilityAnalysis") -> list:
    """Populate the four advisory disclosure fields on each resolver-emitted SV, then carry the
    P3 certainty downgrade — ONE shared implementation for all four cited-prose resolve sites.

    Steps (ADVISORY only — never re-runs strict_verify, never flips ``is_verified``):
      1. COVERAGE ASSERTION (fail-LOUD): every cited token's evidence_id on these SVs MUST have
         credibility + origin coverage in ``analysis`` (both maps are co-built per-row in
         ``_run_chain``). A cited token with none ⇒ ``CredibilityPassError(abort_credibility_coverage_gap)``.
         Scoped to RESOLVER-EMITTED cited SVs (the SVs handed to ``resolve_provenance_to_citations``),
         NOT every ``[N]`` marker in deterministic tables/timelines — those never become SVs at the
         resolve sites, so they are excluded for free (Codex I-cred-012 iter-5 P2-3).
      2. POPULATE: the EvidenceCredibility→float adaptation
         (``{eid: ec.credibility_weight}``) feeds ``populate_disclosure`` (which expects FLOAT weights,
         not the EvidenceCredibility object), populating span_verdict / credibility_weight /
         independent_origin_count / certainty_label.
      3. P3 CERTAINTY CARRIER (Codex I-cred-012 iter-5 P2): ``populate_disclosure`` derives certainty
         from credibility/origins ONLY; it does NOT see the P3 supersession downgrade. So for each
         populated SV whose cited evidence carries ``certainty_downgrade=True``, cap its certainty_label
         (never above "moderate") and surface the source's ``soft_warning`` on the SV's ``soft_warnings``.

    Inputs are NOT mutated; ``populate_disclosure`` returns NEW SVs via ``dataclasses.replace``.
    """
    from src.polaris_graph.synthesis.disclosure_population import populate_disclosure

    cred_by_ev = analysis.credibility_by_evidence or {}
    origin_by_ev = analysis.origin_by_evidence or {}

    # ── Step 1: coverage assertion (fail-loud BEFORE populate) ──
    for sv in (svs or []):
        for eid in _cited_evidence_ids_for_coverage(sv):
            if eid not in cred_by_ev or eid not in origin_by_ev:
                raise CredibilityPassError(
                    "abort_credibility_coverage_gap: a cited evidence_id "
                    f"({eid!r}) emitted by the resolver has no credibility/origin coverage "
                    "in the credibility analysis; refusing to disclose a claim whose source "
                    "the activated pass never scored (fail-loud, never a false-green advisory)"
                )

    # ── Step 2: EvidenceCredibility → FLOAT adaptation, then populate ──
    cred_floats = {
        eid: ec.credibility_weight for eid, ec in cred_by_ev.items()
    }
    populated = populate_disclosure(svs, cred_floats, origin_by_ev)

    # ── Step 3: P3 certainty carrier (downgrade + soft_warning surface) ──
    out: list = []
    for sv in populated:
        downgrade = False
        warnings: list[str] = []
        for eid in _cited_evidence_ids_for_coverage(sv):
            ec = cred_by_ev.get(eid)
            if ec is None:
                continue
            if bool(getattr(ec, "certainty_downgrade", False)):
                downgrade = True
                warn = getattr(ec, "soft_warning", None)
                if warn:
                    warnings.append(str(warn))
        if not downgrade:
            out.append(sv)
            continue
        # Cap certainty at "moderate" (never "high") when any cited source was P3-downgraded.
        new_label = sv.certainty_label
        if new_label == "high":
            new_label = "moderate"
        existing_warnings = list(getattr(sv, "soft_warnings", None) or [])
        for w in warnings:
            if w not in existing_warnings:
                existing_warnings.append(w)
        out.append(dataclasses.replace(
            sv,
            certainty_label=new_label,
            soft_warnings=existing_warnings,
        ))
    return out
