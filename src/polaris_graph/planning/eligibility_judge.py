"""Kimi §2/§5 — the POST-FETCH, receipt-emitting ELIGIBILITY JUDGE keyed to the
clause ledger. This is the "smart" enforcement layer both prior reviewers missed.

The problem it solves (Kimi §5 "single most important change"): the deterministic
metadata predicates (dates, ontology-mapped kinds, named-source hosts, tier/peer-
review quality) enforce only the CLOSED world. A hard clause the ontology cannot
map — "only news and company press releases", "high-quality journal articles",
"industry white papers" — lands verbatim in ``RetrievalPolicy.opaque_eligibility``
as *disclosed-but-unenforced* (Stage-1 parking lot). This module makes those
clauses BITE without an ontology entry: it READS each fetched source and decides,
per hard clause, ``pass``/``fail``/``unknown`` with a receipt.

Architecture (Kimi §2 "the symmetric design"):

  * DETERMINISTIC owns the high-precision predicates it CAN decide — dates (via
    metadata), languages, named-source host identity — evaluated FIRST, no LLM.
    A clause the ontology already maps is handled by the scope/quality masks
    upstream; only the residue reaches the LLM leg.

  * A SCHEMA-CONSTRAINED LLM JUDGE owns the open world: for each source, ONE
    bounded call scores ALL its still-pending hard clauses at once, reading the
    source metadata + body surface (title, venue, host, type, statement, quote)
    against each clause verbatim. Reasoning-first safe (big ``max_tokens``,
    reasoning captured). Per-clause ``{verdict, basis}`` JSON.

Every decision emits a :class:`~src.polaris_graph.retrieval.quality_eligibility.SourceReceipt`
(reused verbatim — same ``contract_hash``/``term_id``/``source_id``/``stage``/
``verdict``/``basis`` shape) so opaque receipts flow into the SAME
``eligibility_receipts.json`` sink and the SAME ``contract_compliance.audit_contract``
that quality/topicality already use.

AGGREGATION -> citable eligibility (Kimi §2, spec item 2): a source is CITABLE
only if it PASSES every HARD "only/exclude/require" clause it is subject to. A
``fail`` on any hard clause removes it from the citable menu (KEPT in corpus +
diagnostics — §-1.3 disclose-don't-delete). ``unknown`` under a hard OPAQUE clause
is **fail-OPEN** (an opaque deontic clause the judge cannot decide must NOT
silently quarantine — MEMORY's no-silent-fallback + the topicality fail-open
contract), UNLESS the caller marks it fail-closed. SOFT/prefer clauses demote a
rank weight, never exclude.

CRITICAL — entirely UPSTREAM of the frozen verifier. It only decides which rows
are ELIGIBLE to enter the citable menu (``evidence_for_gen``) BEFORE
``strict_verify`` enumerates the pool. It NEVER changes HOW a claim is verified.
``provenance_generator.py`` / ``strict_verify`` stay 0-diff.

The whole module no-ops when there are no opaque hard clauses (byte-identical),
and the LLM leg is only reached when a real ``llm_judge`` callable is injected —
the eval harness injects a deterministic fake, so the offline eval never fetches.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from urllib.parse import urlparse

# Reuse the EXACT receipt + verdict vocabulary quality/topicality already emit, so
# the opaque receipts are indistinguishable at the audit seam except by ``stage``.
from src.polaris_graph.retrieval.quality_eligibility import (
    FAIL,
    PASS,
    SourceReceipt,
    UNKNOWN,
    _row_get,
    _row_text,
    _row_url,
)

# The stage tag routes opaque receipts separately from quality/topicality at the
# compliance audit (Kimi: "keep the opaque stage distinct so audit can route it").
STAGE_OPAQUE = "opaque_eligibility"

# A per-clause verdict from the LLM judge is one of these (schema-constrained).
_LLM_VERDICTS: frozenset[str] = frozenset({PASS, FAIL, UNKNOWN})


# ---------------------------------------------------------------------------
# Clause identity — a stable id per opaque clause (so receipts + audit key on it)
# ---------------------------------------------------------------------------


def _clause_id(clause: str) -> str:
    """A stable, human-legible term id for one verbatim opaque clause.

    ``"only news and company press releases"`` -> ``"opaque:only-news-and-compan"``.
    Deterministic + collision-resistant enough for a per-run receipt key (the full
    clause text travels in the receipt basis, so the id need only disambiguate).
    """
    slug = re.sub(r"[^a-z0-9]+", "-", (clause or "").strip().lower()).strip("-")
    return "opaque:" + (slug[:24] or "clause")


# ---------------------------------------------------------------------------
# DETERMINISTIC predicates (Kimi §2: "high-precision predicates where they exist")
# ---------------------------------------------------------------------------
#
# These fire ONLY when a clause is unambiguously a date/language/named-host
# constraint that carries its own decidable metadata. Anything else is left for
# the LLM leg (returns None here -> "not deterministically decidable").


_NAMED_HOST_RE = re.compile(
    r"\b((?:[a-z0-9-]+\.)+[a-z]{2,})\b", re.IGNORECASE
)


def _host_of(url: str) -> str:
    try:
        return (urlparse(url or "").netloc or "").lower().lstrip("www.")
    except Exception:  # noqa: BLE001
        return ""


def _deterministic_verdict(clause: str, row: Any) -> Optional[tuple[str, str]]:
    """Try to decide ``clause`` for ``row`` with NO LLM. Returns ``(verdict, basis)``
    or ``None`` when the clause is not a deterministically-decidable predicate.

    Only two high-precision classes are handled here (dates + ontology-mapped kinds
    are already enforced by the scope/date masks UPSTREAM of this judge — the
    opaque residue by construction excludes them). This leg handles:

      * a bare **named-host** clause ("use reuters.com", "only from apnews.com") —
        host identity match against the row url. This is high precision: a literal
        domain token in the clause that either matches or does not match the row's
        host.
    """
    low = (clause or "").strip().lower()
    if not low:
        return None

    # Named-host: the clause names a concrete domain (contains a dotted host token).
    hosts_in_clause = [
        h.lower().lstrip("www.")
        for h in _NAMED_HOST_RE.findall(low)
        # ignore accidental "e.g." / "u.s." style tokens (no TLD-ish tail)
        if "." in h and not h.endswith(".")
    ]
    if hosts_in_clause:
        row_host = _host_of(_row_url(row))
        if not row_host:
            return UNKNOWN, "named-host clause but row has no resolvable host"
        # An "only/use X" clause => the row host must be (a suffix of) one named host.
        matched = any(
            row_host == h or row_host.endswith("." + h) or h.endswith("." + row_host)
            for h in hosts_in_clause
        )
        if matched:
            return PASS, f"row host {row_host!r} matches named host in clause"
        return FAIL, (
            f"row host {row_host!r} matches none of the named hosts "
            f"{hosts_in_clause!r} in the clause"
        )

    return None  # not a deterministically-decidable predicate -> LLM leg


# ---------------------------------------------------------------------------
# The LLM judge prompt (schema-constrained; one call per source, all clauses)
# ---------------------------------------------------------------------------


def _source_metadata_view(row: Any) -> dict[str, Any]:
    """The domain-neutral metadata surface the judge READS. Every field is already
    fetched by live retrieval; the body surface mirrors ``quality_eligibility._row_text``
    (statement + direct_quote) — the fetched-body proxy at this seam.
    """
    url = _row_url(row)
    return {
        "url": url,
        "host": _host_of(url),
        "title": str(_row_get(row, "source_title", "") or _row_get(row, "title", "") or ""),
        "venue": str(_row_get(row, "openalex_venue", "") or ""),
        "source_type": str(_row_get(row, "openalex_source_type", "") or ""),
        "is_peer_reviewed": _row_get(row, "is_peer_reviewed", None),
        "tier": str(_row_get(row, "tier", "") or ""),
        "year": _row_get(row, "year", None) or _row_get(row, "publication_year", None),
        "doi": str(_row_get(row, "doi", "") or ""),
        # the fetched-body proxy (bounded) — statement + direct_quote.
        "body_snippet": _row_text(row)[:1200],
    }


def _build_judge_prompt(meta: dict[str, Any], clauses: list[str]) -> str:
    """A schema-constrained per-source judging prompt over ALL pending clauses.

    The model NEVER emits spans/offsets (deterministic owns those — deletes the
    "span must be an object" failure class). It returns ONLY a per-clause verdict +
    a one-line basis. UNKNOWN is a first-class, ENCOURAGED answer when the metadata
    does not decide the clause (so the caller's fail-open contract is honoured
    instead of a fabricated pass/fail).
    """
    numbered = "\n".join(
        f'  {i}. "{c}"' for i, c in enumerate(clauses)
    )
    meta_json = json.dumps(meta, indent=2, sort_keys=True, default=str)
    return (
        "You are a SOURCE-ELIGIBILITY JUDGE for a research pipeline. A user pinned "
        "hard sourcing constraints. Your job: for ONE fetched source, decide whether "
        "it SATISFIES each constraint clause, reading ONLY the metadata below.\n\n"
        "SOURCE METADATA (already fetched — do not assume anything not shown):\n"
        f"{meta_json}\n\n"
        "CONSTRAINT CLAUSES (verbatim from the user; each is a HARD requirement the "
        "source must satisfy to be citable):\n"
        f"{numbered}\n\n"
        "For EACH clause, decide:\n"
        '  - "pass": the source clearly SATISFIES the clause (e.g. the clause says '
        '"only company press releases" and this source IS a company press release; '
        'or "high-quality journal articles" and this is a peer-reviewed journal).\n'
        '  - "fail": the source clearly VIOLATES the clause (e.g. it is a personal '
        "blog when the clause demands news + press releases; or a predatory/OJS-mill "
        "venue when the clause demands high quality).\n"
        '  - "unknown": the metadata genuinely does not let you decide. Prefer this '
        "over guessing. Do NOT fabricate a verdict.\n\n"
        "Judge what the source ACTUALLY IS from title/venue/host/type/body — not what "
        "it is shaped like. A journal-SHAPED predatory venue is NOT high quality. A "
        "corporate newsroom page IS a company press release. A vendor/analyst PDF may "
        "be an industry white paper.\n\n"
        "Return ONLY a JSON object, no prose, of this exact shape:\n"
        '{"verdicts": [{"clause_index": <int>, "verdict": "pass|fail|unknown", '
        '"basis": "<one short sentence>"}, ...]}\n'
        "Include exactly one entry per clause index above."
    )


def _parse_judge_response(
    text: str, clauses: list[str]
) -> dict[int, tuple[str, str]]:
    """Parse the judge's JSON into ``{clause_index: (verdict, basis)}``.

    Robust + per-item (Kimi's malformed-output contract): a missing/garbled entry
    for a clause maps to ``UNKNOWN`` (fail-open at the caller for opaque), NEVER a
    silent pass and never a crash. An out-of-range/unknown verdict token is coerced
    to ``UNKNOWN`` too.
    """
    out: dict[int, tuple[str, str]] = {}
    payload: Any = None
    raw = (text or "").strip()
    if raw:
        try:
            payload = json.loads(raw)
        except Exception:  # noqa: BLE001 — tolerate fenced / trailing-prose wrappers
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                try:
                    payload = json.loads(m.group(0))
                except Exception:  # noqa: BLE001
                    payload = None
    verdicts = []
    if isinstance(payload, dict):
        verdicts = payload.get("verdicts") or []
    if isinstance(verdicts, list):
        for item in verdicts:
            if not isinstance(item, dict):
                continue
            try:
                idx = int(item.get("clause_index"))
            except (TypeError, ValueError):
                continue
            if not (0 <= idx < len(clauses)):
                continue
            v = str(item.get("verdict", "")).strip().lower()
            if v not in _LLM_VERDICTS:
                v = UNKNOWN
            basis = str(item.get("basis", "") or "").strip()[:280]
            out[idx] = (v, basis or "llm judge (no basis given)")
    # Any clause the model omitted -> UNKNOWN (fail-open at the caller for opaque).
    for i in range(len(clauses)):
        out.setdefault(i, (UNKNOWN, "llm judge returned no verdict for this clause"))
    return out


# ---------------------------------------------------------------------------
# judge_source — the per-source entry point (spec item 1)
# ---------------------------------------------------------------------------


# An LLM judge callable: (source_metadata_view, [clauses]) -> raw JSON response str.
LLMJudge = Callable[[dict[str, Any], list[str]], str]


def judge_source(
    source: Any,
    hard_clauses: list[str],
    *,
    llm: Optional[LLMJudge] = None,
    contract_hash: str = "",
) -> list[SourceReceipt]:
    """Judge ONE fetched source against a list of verbatim hard opaque clauses.

    Layered (spec item 1): (a) a DETERMINISTIC predicate per clause first (named-host
    identity), high precision, no LLM; (b) for every clause the deterministic leg
    could NOT decide, ONE bounded schema-constrained LLM call scoring ALL of them at
    once (quality / topicality / opaque kinds).

    Returns one :class:`SourceReceipt` per (source, clause) with
    ``stage=STAGE_OPAQUE``, ``term_id=opaque:<clause slug>``, and the verdict + basis.
    When ``llm`` is ``None`` and a clause needs the LLM leg, that clause resolves to
    ``UNKNOWN`` with a disclosed basis (never a fabricated pass — no-silent-fallback).
    """
    url = _row_url(source)
    receipts: list[SourceReceipt] = []
    clauses = [c for c in (hard_clauses or []) if str(c).strip()]
    if not url or not clauses:
        return receipts

    pending: list[str] = []          # clauses left for the LLM leg
    resolved: dict[str, tuple[str, str]] = {}  # clause -> (verdict, basis)

    # (a) deterministic leg — per clause.
    for clause in clauses:
        det = _deterministic_verdict(clause, source)
        if det is not None:
            resolved[clause] = det
        else:
            pending.append(clause)

    # (b) LLM leg — one call over all still-pending clauses.
    if pending:
        if llm is not None:
            meta = _source_metadata_view(source)
            try:
                raw = llm(meta, pending)
            except Exception as exc:  # noqa: BLE001 — a judge fault is UNKNOWN, never a crash
                raw = ""
                for clause in pending:
                    resolved[clause] = (UNKNOWN, f"llm judge raised: {exc!r} (fail-open)")
            if raw is not None and any(c not in resolved for c in pending):
                parsed = _parse_judge_response(raw, pending)
                for i, clause in enumerate(pending):
                    if clause not in resolved:
                        resolved[clause] = parsed.get(
                            i, (UNKNOWN, "llm judge returned no verdict")
                        )
        else:
            # No judge injected: the clause is honestly undecided here (disclosed).
            for clause in pending:
                resolved[clause] = (
                    UNKNOWN,
                    "no LLM judge available; opaque clause left undecided (disclosed)",
                )

    for clause in clauses:
        verdict, basis = resolved.get(clause, (UNKNOWN, "unresolved"))
        receipts.append(SourceReceipt(
            contract_hash=contract_hash,
            term_id=_clause_id(clause),
            source_id=url,
            stage=STAGE_OPAQUE,
            verdict=verdict,
            basis=f"{basis} | clause={clause!r}",
        ))
    return receipts


# ---------------------------------------------------------------------------
# build_opaque_eligibility — the aggregation into a citable-eligibility plan
# ---------------------------------------------------------------------------


@dataclass
class OpaquePlan:
    """The opaque-eligibility outcome over one billed candidate set.

    Mirrors :class:`~src.polaris_graph.retrieval.quality_eligibility.EligibilityPlan`'s
    fields so the seam merges it with zero new plumbing: an
    ``eligibility_excluded_ids`` set the seam masks out of the citable menu, a demote
    weight map for SOFT clauses, per-source receipts, and a disclosure record list.
    """

    eligibility_excluded_ids: set[str] = field(default_factory=set)
    url_to_weight: dict[str, float] = field(default_factory=dict)
    receipts: list[SourceReceipt] = field(default_factory=list)
    excluded_records: list[dict[str, Any]] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (
            self.eligibility_excluded_ids
            or self.url_to_weight
            or self.receipts
        )


def build_opaque_eligibility(
    policy: Any,
    evidence_rows: "list[Any] | None",
    *,
    llm: Optional[LLMJudge] = None,
    fail_open_on_unknown: bool = True,
) -> OpaquePlan:
    """Apply the contract's OPAQUE hard clauses to a billed candidate set.

    ``policy`` is a :class:`RetrievalPolicy` (duck-typed: reads ``opaque_eligibility``,
    ``predicate_force['opaque_eligibility']``, ``contract_hash``). When no opaque
    clause is present, returns an EMPTY plan (no-op, byte-identical).

    HARD clauses: a source that ``fail``s ANY hard opaque clause is added to
    ``eligibility_excluded_ids`` (removed from the citable menu, KEPT in corpus +
    diagnostics). ``unknown`` under a hard opaque clause is **fail-OPEN** by default
    (``fail_open_on_unknown=True``) — an opaque deontic clause the judge cannot decide
    must NOT silently quarantine a source (no-silent-fallback; matches topicality's
    fail-open). Set ``fail_open_on_unknown=False`` for a strict "only ..." clause the
    operator wants fail-closed. SOFT clauses: never exclude — a ``fail`` only demotes
    ``url_to_weight`` (order-not-drop).
    """
    plan = OpaquePlan()
    clauses = [str(c).strip() for c in (getattr(policy, "opaque_eligibility", None) or []) if str(c).strip()]
    if not clauses:
        return plan  # no opaque predicate -> byte-identical no-op

    force = (getattr(policy, "predicate_force", {}) or {}).get("opaque_eligibility", "hard")
    is_hard = str(force).strip().lower() == "hard"
    contract_hash = str(getattr(policy, "contract_hash", "") or "")

    for row in list(evidence_rows or []):
        url = _row_url(row)
        if not url:
            continue
        receipts = judge_source(
            row, clauses, llm=llm, contract_hash=contract_hash,
        )
        plan.receipts.extend(receipts)
        # Aggregate: a source is CITABLE only if it passes EVERY hard clause.
        row_failed = False
        row_min_weight = 1.0
        fail_basis = ""
        for rec in receipts:
            if rec.verdict == FAIL:
                row_failed = True
                fail_basis = rec.basis
                break
            if rec.verdict == UNKNOWN and not fail_open_on_unknown:
                # fail-closed variant: unknown under a strict "only ..." excludes.
                row_failed = True
                fail_basis = rec.basis
                break
            if rec.verdict == UNKNOWN:
                row_min_weight = min(row_min_weight, 0.5)
        if row_failed:
            if is_hard:
                plan.eligibility_excluded_ids.add(url)
                plan.excluded_records.append({
                    "source_id": url, "stage": STAGE_OPAQUE,
                    "verdict": FAIL, "basis": fail_basis, "force": "hard",
                })
            else:
                plan.url_to_weight[url] = 0.2
        elif row_min_weight < 1.0 and not is_hard:
            plan.url_to_weight[url] = row_min_weight
    return plan
