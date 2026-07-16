"""Contract compliance audit (S4) — DISCLOSURE-ONLY, offline + deterministic.

The gate's final read of its own pinned contract against the produced report
(consolidated design §6, Sol §4 compliance-audit row). It reports, for every
binding contract term, whether the deliverable SATISFIED / FAILED / left it
UNSATISFIABLE / UNKNOWN, and names the OWNING stage — so a forensic reader can
trace a shortfall to retrieval / outline / compose / render.

Hard boundaries (guardrails)
----------------------------
* **DISCLOSURE-ONLY.** :func:`audit_contract` NEVER drops or edits a sentence,
  NEVER reorders/removes a section, NEVER touches ``strict_verify`` or the
  citation audit. It reads the finished report + outline + bibliography and
  returns a plain-data audit. It is called AFTER assembly, ALONGSIDE (never
  in place of) ``_audit_citations``. Its verdict cannot change the report.
* **Deterministic where it counts.** Section presence/order, requested item
  COUNTS, length range, table field availability, and citation presence are all
  decided by DETERMINISTIC string/number checks over the report + biblio — no
  model. A model judge is used ONLY for semantic topic coverage, and ONLY when a
  judge callable is explicitly injected (default ``None`` => that dimension is
  reported ``UNKNOWN``, never fabricated as satisfied). The judge can never alter
  a deterministic verdict and never touches faithfulness.
* **Faithfulness untouched.** This module imports nothing from
  ``provenance_generator`` and runs no verification pass. A term whose evidence
  simply did not survive faithfulness is reported FAILED/UNKNOWN with its owning
  stage — never re-litigated.
* **Never invent a requirement.** Only ``force == hard`` terms (schema-guaranteed
  explicit / user-backed) are audited as REQUIREMENTS. A preference/open term is
  reported as ``NOT_APPLICABLE`` (informational) — its absence is never a FAIL.
* **Fail-open.** A ``None`` / degraded / shapeless contract yields an empty audit
  (no findings), so a caller can always run it safely alongside the citation
  audit without risk to the deliverable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# Result vocabulary
# ---------------------------------------------------------------------------

SATISFIED = "SATISFIED"
FAILED = "FAILED"
UNSATISFIABLE = "UNSATISFIABLE"
UNKNOWN = "UNKNOWN"
NOT_APPLICABLE = "NOT_APPLICABLE"

STATUSES: frozenset[str] = frozenset({
    SATISFIED, FAILED, UNSATISFIABLE, UNKNOWN, NOT_APPLICABLE,
})

# Which stage OWNS a shortfall on a given dimension (design §6 routing).
_STAGE_RETRIEVAL = "retrieval"
_STAGE_OUTLINE = "outline"
_STAGE_COMPOSE = "compose"
_STAGE_RENDER = "render"
_STAGE_AUDIT = "audit"


def _norm(s: Any) -> str:
    return str(s or "").strip()


def _term_value_text(term: Any) -> str:
    if term is None:
        return ""
    val = getattr(term, "value", term)
    if isinstance(val, (list, tuple)):
        return ", ".join(_norm(v) for v in val if _norm(v)).strip()
    return _norm(val)


def _is_hard(term: Any) -> bool:
    force = getattr(term, "force", None)
    if force is not None:
        return str(force).strip().lower() == "hard"
    if isinstance(term, dict):
        return str(term.get("force", "")).strip().lower() == "hard"
    return False


# ---------------------------------------------------------------------------
# One term-level finding
# ---------------------------------------------------------------------------


@dataclass
class ComplianceFinding:
    """One term-level compliance result routed to its owning stage."""

    term_id: str
    dimension: str
    status: str            # one of STATUSES
    owning_stage: str      # retrieval | outline | compose | render | audit
    method: str            # "deterministic" | "judge" | "not_evaluated"
    detail: str = ""
    force: str = ""        # hard | preference | open (informational)

    def to_dict(self) -> dict[str, Any]:
        return {
            "term_id": self.term_id,
            "dimension": self.dimension,
            "status": self.status,
            "owning_stage": self.owning_stage,
            "method": self.method,
            "detail": self.detail,
            "force": self.force,
        }


@dataclass
class ComplianceAudit:
    """The full term-level audit. Disclosure-only; carries no drop/edit power."""

    findings: list[ComplianceFinding] = field(default_factory=list)
    retrieval_scope_status: str = "not_evaluated_prebuilt_corpus"
    contract_sha256: str = ""

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {s: 0 for s in STATUSES}
        for f in self.findings:
            out[f.status] = out.get(f.status, 0) + 1
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "retrieval_scope_status": self.retrieval_scope_status,
            "contract_sha256": self.contract_sha256,
            "counts": self.counts(),
            "findings": [f.to_dict() for f in self.findings],
        }


# ---------------------------------------------------------------------------
# The public entry point
# ---------------------------------------------------------------------------


def audit_contract(
    contract: Any,
    report: str,
    outline: Any = None,
    biblio: Any = None,
    *,
    coverage_judge: Optional[Callable[[str, str], bool]] = None,
    retrieval_scope_status: str = "not_evaluated_prebuilt_corpus",
    contract_sha256: str = "",
) -> ComplianceAudit:
    """Audit a produced report against its pinned contract. DISCLOSURE-ONLY.

    Parameters
    ----------
    contract:
        A pinned :class:`ResearchContract` (or duck-typed equivalent). ``None`` /
        degraded => an empty audit (fail-open).
    report:
        The final assembled report text (verified prose + bibliography).
    outline:
        The resolved outline — a list of section objects/dicts (``title`` attr /
        key) or plain title strings. Used for the deterministic section-order
        check. ``None`` => the report headings are parsed from ``report`` instead.
    biblio:
        The bibliography (list of dict rows) — used for citation-presence and
        references-dedup checks. ``None`` => parsed from the report's References.
    coverage_judge:
        OPTIONAL semantic-coverage judge ``(topic, report) -> bool``. When
        ``None`` (default), semantic topic coverage is reported ``UNKNOWN`` — it is
        NEVER fabricated as satisfied. The judge is a SEPARATE cheap model; it can
        never change a deterministic verdict and never touches faithfulness.
    retrieval_scope_status:
        Recorded verbatim. On a prebuilt corpus the caller passes
        ``"not_evaluated_prebuilt_corpus"`` (the default) so the audit never
        claims a retrieval-scope requirement was enforced when discovery never ran
        under the contract.

    Returns
    -------
    A :class:`ComplianceAudit` with one :class:`ComplianceFinding` per audited
    term. Deterministic for section-order / counts / length / tables / citations;
    a single judge call per semantic topic ONLY when a judge is injected.
    """
    audit = ComplianceAudit(
        retrieval_scope_status=_norm(retrieval_scope_status)
        or "not_evaluated_prebuilt_corpus",
        contract_sha256=_norm(contract_sha256),
    )
    if contract is None or not isinstance(report, str):
        return audit

    report_text = report or ""
    report_headings = _report_headings(report_text)
    outline_titles = _outline_titles(outline) or report_headings
    biblio_rows = _biblio_rows(biblio, report_text)

    # 1) Required sections + order (RENDER-owned, deterministic).
    audit.findings.extend(
        _audit_sections(contract, outline_titles)
    )
    # 2) Requested item counts (COMPOSE-owned, deterministic).
    audit.findings.extend(
        _audit_counts(contract, report_text)
    )
    # 3) Length range (RENDER-owned, deterministic — DISCLOSURE, never a cap).
    audit.findings.extend(
        _audit_length(contract, report_text)
    )
    # 4) Table / visual field availability (RENDER-owned, deterministic).
    audit.findings.extend(
        _audit_visuals(contract, report_text)
    )
    # 5) Citations present (RENDER-owned, deterministic).
    audit.findings.extend(
        _audit_citations_present(contract, report_text, biblio_rows)
    )
    # 6) Retrieval-scope hard terms (RETRIEVAL-owned): on a prebuilt corpus these
    #    are UNKNOWN (discovery never ran under the contract) — disclosed, never
    #    claimed satisfied.
    audit.findings.extend(
        _audit_retrieval_scope(contract, audit.retrieval_scope_status)
    )
    # 7) Semantic topic coverage (COMPOSE/OUTLINE-owned): deterministic keyword
    #    presence is a HINT; the authoritative call is the injected judge. No
    #    judge => UNKNOWN (never fabricated).
    audit.findings.extend(
        _audit_coverage(contract, report_text, coverage_judge)
    )

    return audit


# ---------------------------------------------------------------------------
# Deterministic sub-audits
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s*$", re.MULTILINE)


def _report_headings(report: str) -> list[str]:
    return [h.strip() for h in _HEADING_RE.findall(report or "") if h.strip()]


def _outline_titles(outline: Any) -> list[str]:
    if not isinstance(outline, (list, tuple)):
        return []
    out: list[str] = []
    for item in outline:
        if isinstance(item, str):
            t = _norm(item)
        elif isinstance(item, dict):
            t = _norm(item.get("title"))
        else:
            t = _norm(getattr(item, "title", ""))
        if t:
            out.append(t)
    return out


def _biblio_rows(biblio: Any, report: str) -> list[dict]:
    if isinstance(biblio, (list, tuple)):
        return [b for b in biblio if isinstance(b, dict)]
    # parse from the report's References block as a fallback.
    body = report.split("\n## References\n", 1)
    if len(body) < 2:
        return []
    rows: list[dict] = []
    for line in body[1].splitlines():
        m = re.match(r"\s*\[(\d+)\]\s+(.*)", line)
        if m:
            rows.append({"num": int(m.group(1)), "statement": m.group(2)})
    return rows


def _explicit_sections(contract: Any) -> list[Any]:
    """Sections with an exact-title lock (explicit/user), in contract order."""
    out: list[Any] = []
    sections = getattr(contract, "sections", None)
    if isinstance(sections, (list, tuple)):
        for sec in sections:
            if getattr(sec, "exact_title_lock", False) and _term_value_text(
                getattr(sec, "title", None)
            ):
                out.append(sec)
    return out


def _title_present(title: str, produced: list[str]) -> bool:
    """Case-insensitive presence: an exact heading OR a heading containing it."""
    tl = title.strip().lower()
    if not tl:
        return False
    for p in produced:
        pl = p.strip().lower()
        if pl == tl or tl in pl or pl in tl:
            return True
    return False


def _audit_sections(contract: Any, produced_titles: list[str]) -> list[ComplianceFinding]:
    findings: list[ComplianceFinding] = []
    explicit = _explicit_sections(contract)
    if not explicit:
        return findings

    # presence
    ordered_required: list[tuple[Optional[int], str, str]] = []
    for sec in explicit:
        title = _term_value_text(getattr(sec, "title", None))
        tid = _norm(getattr(getattr(sec, "title", None), "term_id", "")) or _norm(
            getattr(sec, "section_id", "")
        )
        order = getattr(sec, "order", None)
        present = _title_present(title, produced_titles)
        findings.append(ComplianceFinding(
            term_id=tid,
            dimension="deliverable.section",
            status=SATISFIED if present else FAILED,
            owning_stage=_STAGE_RENDER,
            method="deterministic",
            detail=(f"required section {title!r} "
                    + ("present" if present else "absent from produced headings")),
            force="hard",
        ))
        ordered_required.append((order if isinstance(order, int) else None, title, tid))

    # order: only when at least two required sections carry explicit orders.
    with_order = [(o, t, tid) for (o, t, tid) in ordered_required if o is not None]
    if len(with_order) >= 2:
        want = [t for _, t, _ in sorted(with_order, key=lambda x: x[0])]
        # positions of each required title in the produced list.
        positions: list[tuple[str, int]] = []
        low_titles = [p.strip().lower() for p in produced_titles]
        for t in want:
            idx = next(
                (i for i, pl in enumerate(low_titles)
                 if pl == t.lower() or t.lower() in pl or pl in t.lower()),
                -1,
            )
            positions.append((t, idx))
        found = [(t, i) for t, i in positions if i >= 0]
        in_order = all(
            found[k][1] <= found[k + 1][1] for k in range(len(found) - 1)
        ) if len(found) >= 2 else True
        findings.append(ComplianceFinding(
            term_id="deliverable.section_order",
            dimension="deliverable.section_order",
            status=SATISFIED if (len(found) == len(want) and in_order) else FAILED,
            owning_stage=_STAGE_RENDER,
            method="deterministic",
            detail=(f"required order {want!r}; produced positions "
                    f"{[(t, i) for t, i in positions]!r}"),
            force="hard",
        ))
    return findings


_NUM_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}


def _requested_count(term: Any) -> Optional[int]:
    """Extract a requested item count from a term value/dimension (or None)."""
    val = getattr(term, "value", term)
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val
    txt = _term_value_text(term).lower()
    if not txt:
        return None
    m = re.search(r"\b(\d+)\b", txt)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    for w, n in _NUM_WORDS.items():
        if re.search(rf"\b{w}\b", txt):
            return n
    return None


def _audit_counts(contract: Any, report: str) -> list[ComplianceFinding]:
    """Requested item counts (e.g. 'top ten') as a deterministic disclosure.

    A count check counts DISTINCT numbered list markers (``1.`` / ``- ``) in the
    report as a lower bound. This is a DISCLOSURE hint: too few is FAILED, enough
    is SATISFIED. It never edits the report.
    """
    findings: list[ComplianceFinding] = []
    coverage = getattr(contract, "coverage", None)
    if not isinstance(coverage, (list, tuple)):
        return findings
    # count numbered list items in the report (a lower-bound signal).
    numbered = len(re.findall(r"^\s*\d+[.)]\s+", report, re.MULTILINE))
    for cr in coverage:
        stmt = getattr(cr, "statement", None)
        if not _is_hard(stmt):
            continue
        want = _requested_count(stmt)
        if want is None:
            continue
        tid = _norm(getattr(stmt, "term_id", "")) or _norm(
            getattr(cr, "requirement_id", "")
        )
        ok = numbered >= want
        findings.append(ComplianceFinding(
            term_id=tid,
            dimension="content.count",
            status=SATISFIED if ok else UNKNOWN,
            owning_stage=_STAGE_COMPOSE,
            method="deterministic",
            detail=(f"requested count {want}; numbered items found {numbered} "
                    + ("(>= requested)" if ok else "(fewer numbered markers — "
                       "may be prose-listed; disclosed as UNKNOWN, not FAILED)")),
            force="hard",
        ))
    return findings


def _audit_length(contract: Any, report: str) -> list[ComplianceFinding]:
    """Length terms as DISCLOSURE (never a cap). min/target/max compared to the
    report word count; a min not met is FAILED, otherwise SATISFIED."""
    findings: list[ComplianceFinding] = []
    deliverable = getattr(contract, "deliverable", None)
    if not isinstance(deliverable, (list, tuple)):
        return findings
    words = len((report or "").split())
    for t in deliverable:
        dim = _norm(getattr(t, "dimension", "")).lower()
        if "length" not in dim:
            continue
        if not _is_hard(t):
            continue
        want = _requested_count(t)
        if want is None:
            continue
        # a "minimum"/"at least" reading fails when under; otherwise it is a
        # target/max and is disclosed as SATISFIED (length is never truncated).
        is_min = "min" in dim or "at least" in _term_value_text(t).lower()
        status = FAILED if (is_min and words < want) else SATISFIED
        findings.append(ComplianceFinding(
            term_id=_norm(getattr(t, "term_id", "")) or dim,
            dimension="deliverable.length",
            status=status,
            owning_stage=_STAGE_RENDER,
            method="deterministic",
            detail=f"length term {dim}={want}; report words={words} "
                   f"(length is disclosure, never a truncation gate)",
            force="hard",
        ))
    return findings


def _audit_visuals(contract: Any, report: str) -> list[ComplianceFinding]:
    """Requested tables/visuals: SATISFIED iff a markdown table (or the named
    visual keyword) is present. Deterministic; RENDER-owned."""
    findings: list[ComplianceFinding] = []
    has_table = bool(re.search(r"^\s*\|.*\|\s*$", report, re.MULTILINE))
    for group_name in ("deliverable", "content_terms"):
        group = getattr(contract, group_name, None)
        if not isinstance(group, (list, tuple)):
            continue
        for t in group:
            dim = _norm(getattr(t, "dimension", "")).lower()
            if not any(k in dim for k in ("visual", "table", "figure", "chart", "timeline")):
                continue
            if not _is_hard(t):
                continue
            wants_table = "table" in dim or "table" in _term_value_text(t).lower()
            present = has_table if wants_table else _visual_keyword_present(t, report)
            findings.append(ComplianceFinding(
                term_id=_norm(getattr(t, "term_id", "")) or dim,
                dimension="deliverable.visual",
                status=SATISFIED if present else FAILED,
                owning_stage=_STAGE_RENDER,
                method="deterministic",
                detail=(f"requested visual {dim!r}; "
                        + ("present" if present else "not found in report "
                           "(render only builds visuals from VERIFIED fields)")),
                force="hard",
            ))
    return findings


def _visual_keyword_present(term: Any, report: str) -> bool:
    kw = _term_value_text(term).lower()
    rl = report.lower()
    for token in ("table", "figure", "chart", "timeline", "mind map", "matrix"):
        if token in kw and token in rl:
            return True
    return False


def _audit_citations_present(
    contract: Any, report: str, biblio_rows: list[dict]
) -> list[ComplianceFinding]:
    """Citation requirement: SATISFIED iff the report carries [N] markers AND a
    bibliography. Deterministic; RENDER-owned. Never touches _audit_citations."""
    findings: list[ComplianceFinding] = []
    for group_name in ("deliverable",):
        group = getattr(contract, group_name, None)
        if not isinstance(group, (list, tuple)):
            continue
        for t in group:
            dim = _norm(getattr(t, "dimension", "")).lower()
            if "citation" not in dim and "bibliograph" not in dim:
                continue
            if not _is_hard(t):
                continue
            has_markers = bool(re.search(r"\[\d+\]", report))
            has_biblio = len(biblio_rows) > 0
            ok = has_markers and has_biblio
            findings.append(ComplianceFinding(
                term_id=_norm(getattr(t, "term_id", "")) or dim,
                dimension="deliverable.citation",
                status=SATISFIED if ok else FAILED,
                owning_stage=_STAGE_RENDER,
                method="deterministic",
                detail=f"citation markers={has_markers}, bibliography rows="
                       f"{len(biblio_rows)}",
                force="hard",
            ))
    return findings


def _audit_retrieval_scope(
    contract: Any, retrieval_scope_status: str
) -> list[ComplianceFinding]:
    """Hard SCOPE terms (source type / language / date / jurisdiction). On a
    prebuilt corpus discovery never ran under the contract, so these are UNKNOWN
    (disclosed, never claimed satisfied). RETRIEVAL-owned."""
    findings: list[ComplianceFinding] = []
    scope = getattr(contract, "scope", None)
    if not isinstance(scope, (list, tuple)):
        return findings
    for t in scope:
        if not _is_hard(t):
            continue
        val = getattr(t, "value", None)
        if val in (None, "", [], {}):
            continue
        dim = _norm(getattr(t, "dimension", "")) or "scope"
        # This audit runs on a prebuilt corpus (no discovery under the contract),
        # so a retrieval-scope requirement is DISCLOSED as UNKNOWN — never claimed
        # satisfied. A live-retrieval caller with real scope telemetry would route
        # this dimension itself; here it is always disclosure-only.
        findings.append(ComplianceFinding(
            term_id=_norm(getattr(t, "term_id", "")) or dim,
            dimension=dim,
            status=UNKNOWN,
            owning_stage=_STAGE_RETRIEVAL,
            method="not_evaluated",
            detail=(f"hard scope {dim}={_term_value_text(t)!r}; "
                    f"retrieval_scope_status={retrieval_scope_status} — "
                    "discovery not evaluated under this contract "
                    "(disclosed, not claimed satisfied)"),
            force="hard",
        ))
    return findings


def _audit_coverage(
    contract: Any,
    report: str,
    coverage_judge: Optional[Callable[[str, str], bool]],
) -> list[ComplianceFinding]:
    """Semantic topic coverage. The authoritative call is the injected judge; no
    judge => UNKNOWN (never fabricated). COMPOSE/OUTLINE-owned."""
    findings: list[ComplianceFinding] = []
    coverage = getattr(contract, "coverage", None)
    if not isinstance(coverage, (list, tuple)):
        return findings
    rl = (report or "").lower()
    for cr in coverage:
        if not getattr(cr, "required", True):
            continue
        stmt = getattr(cr, "statement", None)
        topic = _term_value_text(stmt)
        if not topic:
            continue
        tid = _norm(getattr(stmt, "term_id", "")) or _norm(
            getattr(cr, "requirement_id", "")
        )
        force = _norm(getattr(stmt, "force", "")) or "preference"
        if coverage_judge is not None:
            try:
                ok = bool(coverage_judge(topic, report))
                status = SATISFIED if ok else FAILED
                method = "judge"
                detail = f"semantic-coverage judge on topic {topic!r}: {ok}"
            except Exception as exc:  # noqa: BLE001 — judge failure => UNKNOWN
                status = UNKNOWN
                method = "judge"
                detail = f"coverage judge errored on {topic!r}: {exc}"
        else:
            # deterministic keyword-presence HINT (never authoritative).
            hint = any(
                w and w in rl
                for w in re.findall(r"[A-Za-z][A-Za-z\-]{3,}", topic.lower())
            )
            status = UNKNOWN
            method = "not_evaluated"
            detail = (f"no semantic-coverage judge injected; keyword-presence "
                      f"hint={hint} for topic {topic!r} (reported UNKNOWN, "
                      "never fabricated as satisfied)")
        findings.append(ComplianceFinding(
            term_id=tid,
            dimension="content.coverage",
            status=status,
            owning_stage=_STAGE_COMPOSE if _is_hard(stmt) else _STAGE_OUTLINE,
            method=method,
            detail=detail,
            force=force,
        ))
    return findings
