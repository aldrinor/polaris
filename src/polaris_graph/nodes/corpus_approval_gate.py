"""
Phase 2g — Corpus-approval gate.

After retrieval and tier classification, the pipeline stops and shows
the user the final corpus tier distribution alongside the expected
distribution from `protocol.json`. The user must EXPLICITLY approve
before synthesis begins.

ADDRESSES PG_LB_SA_02_CONTENT_AUDIT Section E-05: the pre-rebuild
pipeline went from retrieval directly to synthesis with no user-
visible checkpoint. Users saw the final report but could not see what
corpus produced it. Corpora dominated by T5 industry marketing + T6
blog posts were synthesized into confident-sounding claims.

RUBBER-STAMP RESISTANCE (FX-05 / I-ready-017):
- If actual distribution is >=15 percentage points off the expected
  in any single tier, the gate blocks auto-approve.
- A material-deviation corpus is DENIED by default
  (abort_corpus_approval_denied, no generator tokens billed). A free-text
  note is NOT a sanctioned credential — the R-3 sweep's own 50-char canned
  note defeated the old len>=30 + denylist heuristic and billed a
  material-deviation corpus.
- The ONLY sanctioned auto-approve is a structured operator authorization
  (env/CLI PG_AUTHORIZED_SWEEP_APPROVAL=1), recorded as an audit-logged
  AuthorizedSweep{authorized_by, authorized_at, flag_source}.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("polaris_graph.corpus_approval_gate")

# Deviation threshold (absolute percentage points) — a tier whose
# actual fraction is more than this far from its expected bounds is
# flagged as "material deviation" requiring an explicit opt-in note.
PG_TIER_MATERIAL_DEVIATION_PP = float(
    os.getenv("PG_TIER_MATERIAL_DEVIATION_PP", "15.0")
) / 100.0


@dataclass
class CorpusSource:
    """A single retrieved source after tier classification."""

    url: str
    tier: str          # "T1".."T7" or "UNKNOWN"
    title: str = ""
    domain: str = ""
    tier_confidence: float = 0.0
    tier_rule: str = ""
    tier_reasons: list[str] = field(default_factory=list)


@dataclass
class TierDeviation:
    """Describes how actual fraction compares to expected range."""

    tier: str
    actual_fraction: float
    expected_min: float
    expected_max: float
    deviation_pp: float      # signed: positive = above max, negative = below min
    is_material: bool        # True if |deviation_pp| > threshold


@dataclass
class CorpusDistributionReport:
    """Summary of actual tier mix vs protocol-expected mix."""

    total_sources: int
    tier_counts: dict[str, int]
    tier_fractions: dict[str, float]
    deviations: list[TierDeviation]
    has_material_deviation: bool
    auto_approve_allowed: bool


@dataclass
class AuthorizedSweep:
    """Structured operator authorization to auto-approve a material-deviation
    corpus (FX-05 / I-ready-017).

    This REPLACES the old free-text "why is this corpus acceptable" note as the
    auto-approve credential. A free-text field is defeatable (the R-3 sweep's own
    48-char canned note passed the len>=30 + denylist guard → a material-deviation
    corpus auto-approved and was billed). A credential must be a *positive,
    audit-logged acknowledgement keyed to an explicit flag*, not prose.

    Built only by `authorization_from_env()` when `PG_AUTHORIZED_SWEEP_APPROVAL`
    is set truthy. Persisted as a structured block in `corpus_approval.json`.
    """

    authorized_by: str   # identity/source, e.g. "env:PG_AUTHORIZED_SWEEP_APPROVAL"
    authorized_at: str   # ISO-8601 UTC timestamp the authorization was minted
    flag_source: str     # provenance of the flag: "env" | "cli"


@dataclass
class CorpusApprovalDecision:
    """Persisted once the user approves / rejects the corpus."""

    run_id: str
    decision_at_unix: float
    decision_at_iso: str
    approved: bool
    user_note: str = ""
    approved_source_urls: list[str] = field(default_factory=list)
    rejected_source_urls: list[str] = field(default_factory=list)
    report: Optional[CorpusDistributionReport] = None
    protocol_sha256: str = ""
    # FX-05: the STRUCTURED credential that authorized an auto-approve on a
    # material-deviation corpus (None = no structured authorization; for a
    # material-deviation corpus that means the run was/should be denied).
    authorization: Optional[AuthorizedSweep] = None


def compute_tier_distribution(
    sources: list[CorpusSource],
    protocol: dict[str, Any],
) -> CorpusDistributionReport:
    """Aggregate the corpus tier mix vs the pre-registered protocol.

    Args:
        sources: List of retrieved sources with Phase 2a tier
            assignments already applied.
        protocol: Dict form of protocol.json (must have key
            'expected_tier_distribution' — list of dicts with
            tier / min_fraction / max_fraction).
    """
    total = len(sources)
    counts: dict[str, int] = {}
    for s in sources:
        counts[s.tier] = counts.get(s.tier, 0) + 1

    fractions = {
        k: (v / total if total > 0 else 0.0)
        for k, v in counts.items()
    }

    deviations: list[TierDeviation] = []
    expected_list = list(protocol.get("expected_tier_distribution") or [])
    for entry in expected_list:
        tier = entry.get("tier")
        if not tier:
            continue
        exp_min = float(entry.get("min_fraction", 0.0))
        exp_max = float(entry.get("max_fraction", 1.0))
        actual = fractions.get(tier, 0.0)

        if actual < exp_min:
            dev_pp = actual - exp_min
        elif actual > exp_max:
            dev_pp = actual - exp_max
        else:
            dev_pp = 0.0

        is_material = abs(dev_pp) > PG_TIER_MATERIAL_DEVIATION_PP
        deviations.append(TierDeviation(
            tier=tier,
            actual_fraction=round(actual, 4),
            expected_min=exp_min,
            expected_max=exp_max,
            deviation_pp=round(dev_pp, 4),
            is_material=is_material,
        ))

    any_material = any(d.is_material for d in deviations)

    return CorpusDistributionReport(
        total_sources=total,
        tier_counts=counts,
        tier_fractions={k: round(v, 4) for k, v in fractions.items()},
        deviations=deviations,
        has_material_deviation=any_material,
        auto_approve_allowed=not any_material,
    )


def render_approval_html(
    report: CorpusDistributionReport,
    sources: list[CorpusSource],
    research_question: str,
) -> str:
    """Render a self-contained HTML page for human corpus review.

    Deliberately minimal (no JS) so it works in any text-only
    browser. The actual approve/reject round-trip happens via the
    endpoint; this view is read-only presentation.
    """
    # Escape helper
    import html as _html

    def esc(s: str) -> str:
        return _html.escape(s or "")

    css = """
    body { font-family: -apple-system, 'Segoe UI', sans-serif; max-width: 980px;
           margin: 2em auto; padding: 0 1em; color: #222; line-height: 1.5; }
    h1 { border-bottom: 2px solid #222; padding-bottom: 0.3em; }
    .material { background: #fff3cd; padding: 1em; border-left: 4px solid #e0a800;
                margin: 1em 0; }
    table { border-collapse: collapse; width: 100%; margin: 1em 0; }
    th, td { border: 1px solid #ccc; padding: 0.5em; text-align: left; }
    th { background: #eee; }
    .t1 { color: #0a6b0a; font-weight: bold; }
    .t2 { color: #0a6b0a; }
    .t3 { color: #1a4d8a; font-weight: bold; }
    .t4 { color: #555; }
    .t5 { color: #a05a00; }
    .t6 { color: #a00000; }
    .t7 { color: #b06060; font-style: italic; }
    .unknown { color: #888; font-style: italic; }
    .dev-neg { color: #a00000; }
    .dev-pos { color: #a05a00; }
    .dev-zero { color: #0a6b0a; }
    """

    # Summary row
    rows = []
    for d in report.deviations:
        tier_class = d.tier.lower()
        if d.deviation_pp < 0:
            dev_class = "dev-neg"
            dev_str = f"{d.deviation_pp*100:+.1f}pp (below protocol min)"
        elif d.deviation_pp > 0:
            dev_class = "dev-pos"
            dev_str = f"{d.deviation_pp*100:+.1f}pp (above protocol max)"
        else:
            dev_class = "dev-zero"
            dev_str = "within range"
        rows.append(
            f"<tr>"
            f"<td class='{tier_class}'>{esc(d.tier)}</td>"
            f"<td>{d.actual_fraction*100:.1f}%</td>"
            f"<td>{d.expected_min*100:.0f}% to {d.expected_max*100:.0f}%</td>"
            f"<td class='{dev_class}'>{esc(dev_str)}"
            + (" <strong>(material)</strong>" if d.is_material else "")
            + "</td>"
            f"</tr>"
        )
    tier_table = (
        "<table><thead><tr><th>Tier</th><th>Actual %</th><th>Expected</th>"
        "<th>Deviation</th></tr></thead><tbody>"
        + "\n".join(rows)
        + "</tbody></table>"
    )

    # Per-source table
    source_rows = []
    for s in sources[:500]:  # cap for large corpora
        tier_class = s.tier.lower()
        source_rows.append(
            f"<tr>"
            f"<td class='{tier_class}'>{esc(s.tier)}</td>"
            f"<td>{esc(s.domain)}</td>"
            f"<td><a href='{esc(s.url)}' rel='noopener'>{esc(s.title[:120])}</a></td>"
            f"<td><small>{esc(s.tier_rule)}</small></td>"
            f"</tr>"
        )
    source_table = (
        "<table><thead><tr><th>Tier</th><th>Domain</th><th>Title</th>"
        "<th>Rule</th></tr></thead><tbody>"
        + "\n".join(source_rows)
        + "</tbody></table>"
    )

    material_banner = ""
    if report.has_material_deviation:
        material_banner = (
            "<div class='material'><strong>Material deviation from the "
            "pre-registered protocol.</strong> Auto-approve is disabled and "
            "the run is denied by default (status "
            "<code>abort_corpus_approval_denied</code>, no generator tokens "
            "billed). The ONLY sanctioned override is an explicit operator "
            "authorization — set <code>PG_AUTHORIZED_SWEEP_APPROVAL=1</code> "
            "(recorded as a structured, audit-logged credential). A free-text "
            "note is not a sanctioned credential.</div>"
        )

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>POLARIS — Corpus Approval Gate</title>
<style>{css}</style>
</head>
<body>
<h1>POLARIS corpus-approval gate</h1>
<p><strong>Research question:</strong> {esc(research_question)}</p>
<p><strong>Total sources retrieved:</strong> {report.total_sources}</p>
{material_banner}
<h2>Tier distribution vs protocol</h2>
{tier_table}
<h2>Per-source breakdown</h2>
<p><em>Showing first {min(500, len(sources))} of {len(sources)} sources.</em></p>
{source_table}
<hr>
<p><small>POLARIS honest-rebuild Phase 2g. Approve / reject via endpoint
<code>POST /api/corpus_approval</code>.</small></p>
</body>
</html>
"""
    return html_doc


def save_approval_decision(
    decision: CorpusApprovalDecision,
    run_dir: Path | str,
) -> Path:
    """Persist the approval decision as JSON. Atomic write + SHA-256."""
    run_dir_path = Path(run_dir)
    run_dir_path.mkdir(parents=True, exist_ok=True)
    path = run_dir_path / "corpus_approval.json"
    tmp = run_dir_path / "corpus_approval.json.tmp"
    data = asdict(decision)
    # Convert nested dataclasses are already asdict-able; CorpusDistributionReport
    # with TierDeviation — asdict handles it recursively.
    payload = json.dumps(
        data, indent=2, sort_keys=True, ensure_ascii=False, default=str,
    )
    tmp.write_text(payload + "\n", encoding="utf-8")
    os.replace(tmp, path)
    sha256 = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    logger.info(
        "[corpus_approval] decision persisted approved=%s path=%s sha=%s",
        decision.approved, path, sha256[:16],
    )
    return path


# FX-05 (I-ready-017): the ONE sanctioned auto-approve credential for a
# material-deviation corpus. A free-text note is NOT a credential.
PG_AUTHORIZED_SWEEP_APPROVAL_ENV = "PG_AUTHORIZED_SWEEP_APPROVAL"
# Optional: who/what to record as the authorizing identity (audit only).
PG_AUTHORIZED_SWEEP_APPROVED_BY_ENV = "PG_AUTHORIZED_SWEEP_APPROVED_BY"

_TRUTHY = {"1", "true", "yes", "on"}


def _is_truthy(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in _TRUTHY


def authorization_from_env() -> Optional[AuthorizedSweep]:
    """Build a structured :class:`AuthorizedSweep` iff
    ``PG_AUTHORIZED_SWEEP_APPROVAL`` is set truthy.

    This is the ONLY sanctioned path to auto-approve a material-deviation
    corpus (FX-05). When the flag is absent/falsey this returns ``None`` and
    the gate denies (``abort_corpus_approval_denied``) — default-deny honors
    §9.1 invariant #5 and gates generator spend. LAW VI: the credential comes
    exclusively from configuration, never hard-coded.
    """
    if not _is_truthy(os.getenv(PG_AUTHORIZED_SWEEP_APPROVAL_ENV)):
        return None
    return AuthorizedSweep(
        authorized_by=(
            os.getenv(PG_AUTHORIZED_SWEEP_APPROVED_BY_ENV)
            or f"env:{PG_AUTHORIZED_SWEEP_APPROVAL_ENV}"
        ),
        authorized_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        flag_source="env",
    )


def check_auto_approve_allowed(
    report: CorpusDistributionReport,
    authorization: Optional[AuthorizedSweep] = None,
) -> tuple[bool, str]:
    """Structured-authorization gate (FX-05 / I-ready-017).

    Replaces the defeatable free-text-note heuristic (any prose >=30 chars not
    in a small denylist auto-approved — the R-3 sweep's own canned note slipped
    through and billed a material-deviation corpus).

    Returns ``(ok, error_message)``.
    - No material deviation → auto-approve is fine; no authorization needed.
    - Material deviation → auto-approve ONLY with a complete structured
      :class:`AuthorizedSweep`. A ``None`` authorization, or ANY non-
      ``AuthorizedSweep`` value (e.g. a legacy free-text note), is rejected
      fail-closed. Default-deny gates generator spend (§9.1 #5).
    """
    if not report.has_material_deviation:
        return True, ""

    if authorization is None:
        return False, (
            "Material deviation from the pre-registered protocol detected. "
            "Auto-approve requires a structured operator authorization "
            f"(set {PG_AUTHORIZED_SWEEP_APPROVAL_ENV}=1); a free-text note is "
            "not a sanctioned credential. Denying "
            "(abort_corpus_approval_denied)."
        )

    if not isinstance(authorization, AuthorizedSweep):
        return False, (
            "Material deviation detected and the supplied approval credential "
            f"is not a structured authorization ({type(authorization).__name__}). "
            f"A free-text note alone never auto-approves; set "
            f"{PG_AUTHORIZED_SWEEP_APPROVAL_ENV}=1. Denying "
            "(abort_corpus_approval_denied)."
        )

    if not (
        authorization.authorized_by.strip()
        and authorization.authorized_at.strip()
        and authorization.flag_source.strip()
    ):
        return False, (
            "Material deviation detected and the structured authorization is "
            "incomplete (authorized_by / authorized_at / flag_source all "
            "required). Denying (abort_corpus_approval_denied)."
        )

    return True, ""
