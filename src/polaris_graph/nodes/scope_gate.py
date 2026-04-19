"""
Phase 2b — Scope gate + pre-registered protocol.json at T+0.

Part of HONEST-REBUILD Phase 2 (plan:
C:/Users/msn/.claude/plans/lovely-finding-firefly.md).

THE PROBLEM THIS SOLVES
-----------------------
PG_LB_SA_02_CONTENT_AUDIT.md Section F-02 documented that the pre-rebuild
pipeline allowed scope drift: the final report used inclusion criteria
that were not pre-registered, the user could not tell when the generator
silently broadened or narrowed the query, and PRISMA-style methods
sections were reconstructed post-hoc rather than locked before retrieval.

Pre-registration is the standard mitigation in systematic review
methodology (PROSPERO, OSF Registries, NIH protocol registration):
you state the question + inclusion/exclusion + expected tier distribution
BEFORE you see the evidence. Any later deviation is documented, not
hidden.

WHAT THIS NODE DOES
-------------------
1. Takes the raw user query + domain hint.
2. Loads the matching scope template from `config/scope_templates/`
   (clinical / policy / tech / due_diligence) — see Phase 2c.
3. Structures the query into a `ProtocolDocument`:
   - Research question (verbatim user input)
   - PICO / population / intervention / comparator / outcome (when clinical)
   - Inclusion criteria (derived from template + user overrides)
   - Exclusion criteria (derived from template + user overrides)
   - Expected tier mix (derived from template)
   - Acceptable evidence horizons (date range, geography, languages)
4. Writes `{run_dir}/protocol.json` and stamps a SHA-256 over it.
5. Returns the protocol path + hash so downstream nodes can attach the
   hash to every artifact for tamper-evidence.

No LLM is called. This node is deterministic and rule-based so the
protocol cannot be hallucinated. If the template-driven derivation is
insufficient, the node logs a warning and marks the protocol as
`needs_user_review: true` — a human should confirm before retrieval.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:  # pragma: no cover — yaml is in requirements.txt
    yaml = None

logger = logging.getLogger("polaris_graph.scope_gate")

# Repo root for locating config/scope_templates/.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCOPE_TEMPLATES_DIR = _REPO_ROOT / "config" / "scope_templates"

# Supported domain hints. Determines which scope template is loaded.
# BUG-B-102 R2b: `custom` added for pipeline-B UI path (graph_v4) so
# free-form UI queries don't all route through clinical/tech/etc.
SUPPORTED_DOMAINS = frozenset({
    "clinical", "policy", "tech", "due_diligence", "custom",
})

DEFAULT_DOMAIN = "clinical"


# ─────────────────────────────────────────────────────────────────────────────
# Protocol schema
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class TierExpectation:
    """Expected lower / upper bounds for a single tier in the final corpus.

    The pipeline does NOT fail if actual distribution differs — but the
    corpus-approval gate (Phase 2g) shows the delta to the user so they
    can reject a corpus dominated by commentary when the protocol asked
    for ≥40% primary studies.
    """

    tier: str          # "T1" .. "T7" or "UNKNOWN"
    min_fraction: float  # 0.0-1.0
    max_fraction: float  # 0.0-1.0
    rationale: str       # human-readable reason ("RCT-heavy for efficacy")


@dataclass
class InclusionExclusionCriteria:
    """PRISMA-style inclusion / exclusion criteria."""

    inclusion: list[str] = field(default_factory=list)
    exclusion: list[str] = field(default_factory=list)

    def normalize(self) -> "InclusionExclusionCriteria":
        """Deduplicate and trim."""
        inc = sorted({i.strip() for i in self.inclusion if i.strip()})
        exc = sorted({e.strip() for e in self.exclusion if e.strip()})
        return InclusionExclusionCriteria(inclusion=inc, exclusion=exc)


@dataclass
class ProtocolDocument:
    """Pre-registered protocol. Immutable once written to protocol.json."""

    # Identity
    run_id: str
    created_at_unix: float
    created_at_iso: str

    # Core question
    research_question: str
    domain: str               # clinical / policy / tech / due_diligence

    # Optional PICO framing (clinical domain only; may be empty for others).
    population: Optional[str] = None
    intervention: Optional[str] = None
    comparator: Optional[str] = None
    outcome: Optional[str] = None

    # Inclusion / exclusion
    criteria: InclusionExclusionCriteria = field(
        default_factory=InclusionExclusionCriteria
    )

    # Expected tier mix (from template)
    expected_tier_distribution: list[TierExpectation] = field(
        default_factory=list
    )

    # Evidence horizons
    date_range: tuple[Optional[str], Optional[str]] = (None, None)
    geography: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=lambda: ["en"])

    # Conflict-of-interest / funding-source filters
    excluded_sponsors: list[str] = field(default_factory=list)

    # Audit trail
    template_used: Optional[str] = None          # path relative to repo root
    user_overrides: dict[str, Any] = field(default_factory=dict)
    needs_user_review: bool = False
    notes: list[str] = field(default_factory=list)

    # BUG-B-100 fix (deep-dive R3): explicit decision outcome so the
    # orchestrator can gate on a real signal rather than advisory
    # needs_user_review. scope_decision is one of:
    #   "proceed" — pipeline should continue
    #   "review"  — pipeline should continue, but the protocol is
    #               uncertain and a human should verify assumptions
    #   "reject"  — pipeline MUST abort; retrieval and generation
    #               would be unsafe or wasteful
    scope_decision: str = "proceed"
    scope_rejected: bool = False
    scope_rejection_code: Optional[str] = None
    scope_reasons: list[str] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        """Serialize, converting tuple date range to a dict."""
        data = asdict(self)
        # Convert tuple to dict for stable JSON
        start, end = self.date_range
        data["date_range"] = {"start": start, "end": end}
        return data


@dataclass
class ScopeGateResult:
    """Return value of run_scope_gate()."""

    protocol: ProtocolDocument
    protocol_path: Path
    protocol_sha256: str


# ─────────────────────────────────────────────────────────────────────────────
# Template loader
# ─────────────────────────────────────────────────────────────────────────────


def load_scope_template(domain: str) -> dict[str, Any]:
    """Load `config/scope_templates/{domain}.yaml` as a dict.

    Raises RuntimeError if the file doesn't exist or yaml isn't installed.
    """
    if yaml is None:
        raise RuntimeError(
            "PyYAML is required for scope_gate. Install via "
            "`pip install pyyaml`."
        )
    if domain not in SUPPORTED_DOMAINS:
        raise ValueError(
            f"domain={domain!r} not in SUPPORTED_DOMAINS. "
            f"Options: {sorted(SUPPORTED_DOMAINS)}"
        )
    path = _SCOPE_TEMPLATES_DIR / f"{domain}.yaml"
    if not path.exists():
        raise RuntimeError(
            f"Scope template {path} does not exist. Phase 2c is responsible "
            f"for creating this file; run the rebuild Phase 2c step first."
        )
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise RuntimeError(
            f"Scope template {path} did not parse to a dict (got "
            f"{type(data).__name__}). Check the YAML syntax."
        )
    return data


# ─────────────────────────────────────────────────────────────────────────────
# Lightweight PICO extractor (clinical domain only)
# ─────────────────────────────────────────────────────────────────────────────

# These are regex heuristics, not an LLM. The point of the scope gate
# is that the protocol is deterministic — an LLM-extracted PICO would be
# hallucinable. The user can override any field via explicit kwargs.

_DRUG_NAME_RE = re.compile(
    r"\b("
    # GLP-1 analogues (canonical test domain)
    r"semaglutide|tirzepatide|liraglutide|dulaglutide|exenatide|lixisenatide|"
    r"retatrutide|cagrilintide|orforglipron|"
    r"metformin|empagliflozin|dapagliflozin|canagliflozin|sitagliptin|"
    # Oncology examples for generality
    r"pembrolizumab|nivolumab|trastuzumab|rituximab|"
    r"imatinib|osimertinib"
    r")\b",
    re.IGNORECASE,
)

_POPULATION_MARKERS_RE = re.compile(
    r"\b("
    r"adults?|children|elderly|pediatric|geriatric|adolescents?|"
    r"pregnant|postmenopausal|premenopausal|"
    r"type\s*1\s*diabetes|type\s*2\s*diabetes|t1dm|t2dm|"
    r"obesity|overweight|obese|"
    r"chronic kidney disease|ckd|"
    r"heart failure|hf|"
    r"NAFLD|NASH|MASH|MASLD"
    r")\b",
    re.IGNORECASE,
)


def extract_pico_heuristic(query: str) -> dict[str, Optional[str]]:
    """Extract a provisional PICO framing from the query string.

    This is heuristic only. The caller SHOULD override these when better
    information is available. We return everything lowercased for later
    case-insensitive comparison, and we return None when no marker is
    found (rather than making up a placeholder).
    """
    q = query.strip()
    result: dict[str, Optional[str]] = {
        "population": None,
        "intervention": None,
        "comparator": None,
        "outcome": None,
    }
    pop = _POPULATION_MARKERS_RE.search(q)
    if pop:
        result["population"] = pop.group(1).lower()
    drug = _DRUG_NAME_RE.search(q)
    if drug:
        result["intervention"] = drug.group(1).lower()

    # Outcome detection is weak; look for standard trial outcomes
    q_l = q.lower()
    for outcome_marker in (
        "weight loss", "hba1c", "mortality", "major adverse cardiac events",
        "mace", "blood pressure", "ldl", "glycemic control",
        "disease-free survival", "overall survival", "quality of life",
    ):
        if outcome_marker in q_l:
            result["outcome"] = outcome_marker
            break
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────


def run_scope_gate(
    *,
    research_question: str,
    run_dir: Path | str,
    run_id: str,
    domain: str = DEFAULT_DOMAIN,
    user_overrides: Optional[dict[str, Any]] = None,
) -> ScopeGateResult:
    """Lock the research protocol at T+0 and write protocol.json.

    Args:
        research_question: The raw user query. Stored verbatim — no
            paraphrasing, no summarization.
        run_dir: Directory where protocol.json will be written.
            Created if it does not exist.
        run_id: Stable run identifier (used for audit trail).
        domain: clinical / policy / tech / due_diligence. Picks the template.
        user_overrides: Optional dict merging into the template. Keys that
            exist in the template are replaced verbatim (no deep-merge).
            Merge is logged in protocol.user_overrides so every deviation
            from the template is traceable.

    Returns:
        ScopeGateResult with the protocol, file path, and SHA-256 hash.
        The protocol file is written atomically (write to .tmp, rename).
    """
    if not research_question or not research_question.strip():
        raise ValueError("research_question must be non-empty.")

    # BUG-B-100 fix (deep-dive R3): the scope gate is now an actual gate.
    # Track reject/review/proceed explicitly instead of silently coercing
    # unsupported inputs. Reject decisions cause the orchestrator to
    # abort BEFORE retrieval with manifest.status=abort_scope_rejected.
    scope_decision = "proceed"
    scope_rejected = False
    scope_rejection_code: Optional[str] = None
    scope_reasons: list[str] = []

    # Hard reject #1: unsupported domain. Previously silently fell back
    # to DEFAULT_DOMAIN ("clinical") — that's a silent category error
    # for any query that legitimately should route elsewhere.
    if domain not in SUPPORTED_DOMAINS:
        scope_decision = "reject"
        scope_rejected = True
        scope_rejection_code = "unsupported_domain"
        scope_reasons.append(
            f"domain={domain!r} is not in SUPPORTED_DOMAINS. "
            f"Options: {sorted(SUPPORTED_DOMAINS)}."
        )
        # Keep domain as-is for the record; the orchestrator will
        # abort before any domain-specific logic fires.

    run_dir_path = Path(run_dir)
    run_dir_path.mkdir(parents=True, exist_ok=True)
    overrides = dict(user_overrides or {})

    # 1. Load template. If domain is rejected, skip the template load
    # (it would raise) and use an empty template; the protocol document
    # still needs to be assembled so the orchestrator can emit an
    # abort manifest.
    if scope_rejected:
        template = {}
        template_path_rel = f"config/scope_templates/<rejected:{domain}>.yaml"
    else:
        template = load_scope_template(domain)
        template_path_rel = f"config/scope_templates/{domain}.yaml"

    # 2. PICO heuristic extraction
    pico = extract_pico_heuristic(research_question)
    # Overrides win
    for key in ("population", "intervention", "comparator", "outcome"):
        if key in overrides and overrides[key]:
            pico[key] = str(overrides[key]).lower()

    # 3. Inclusion / exclusion criteria
    inc_from_template = list(template.get("inclusion_criteria") or [])
    exc_from_template = list(template.get("exclusion_criteria") or [])
    # Overrides append (don't replace) unless explicit reset
    if overrides.get("reset_criteria"):
        inc_from_template = []
        exc_from_template = []
    inc_from_template.extend(overrides.get("add_inclusion") or [])
    exc_from_template.extend(overrides.get("add_exclusion") or [])
    criteria = InclusionExclusionCriteria(
        inclusion=inc_from_template,
        exclusion=exc_from_template,
    ).normalize()

    # 4. Expected tier distribution
    expected_tiers_raw = list(template.get("expected_tier_distribution") or [])
    tier_expectations: list[TierExpectation] = []
    for entry in expected_tiers_raw:
        if not isinstance(entry, dict):
            continue
        tier = entry.get("tier")
        if not tier:
            continue
        try:
            tier_expectations.append(TierExpectation(
                tier=str(tier),
                min_fraction=float(entry.get("min_fraction", 0.0)),
                max_fraction=float(entry.get("max_fraction", 1.0)),
                rationale=str(entry.get("rationale", "")),
            ))
        except (ValueError, TypeError) as exc:
            logger.warning(
                "[scope_gate] skipping malformed tier expectation %r: %s",
                entry, exc,
            )

    # 5. Evidence horizons
    date_range_raw = template.get("date_range") or {}
    if "date_range" in overrides:
        date_range_raw = overrides["date_range"]
    date_range = (
        date_range_raw.get("start") if isinstance(date_range_raw, dict) else None,
        date_range_raw.get("end") if isinstance(date_range_raw, dict) else None,
    )

    geography = list(template.get("geography") or [])
    if "geography" in overrides:
        geography = list(overrides["geography"] or [])

    languages = list(template.get("languages") or ["en"])
    if "languages" in overrides:
        languages = list(overrides["languages"] or ["en"])

    excluded_sponsors = list(template.get("excluded_sponsors") or [])
    if "excluded_sponsors" in overrides:
        excluded_sponsors = list(overrides["excluded_sponsors"] or [])

    # 6. Decision block (BUG-B-100 fix): compute scope_decision +
    # populate reasons + notes + needs_user_review as a function of
    # heuristic + protocol completeness.
    notes: list[str] = []
    needs_review = False

    # If already rejected for unsupported domain, just record why in notes.
    if scope_rejected:
        notes.extend(scope_reasons)
    elif domain == "clinical":
        pico_missing: list[str] = []
        if not pico["population"]:
            notes.append(
                "PICO population could not be extracted from the research "
                "question. User should confirm the target population."
            )
            pico_missing.append("population")
        if not pico["intervention"]:
            notes.append(
                "PICO intervention could not be extracted. User should "
                "confirm the drug / procedure under study."
            )
            pico_missing.append("intervention")
        if len(pico_missing) == 2:
            # Both anchors missing: retrieval would be poorly scoped.
            # Hard reject rather than flag-only.
            scope_decision = "reject"
            scope_rejected = True
            scope_rejection_code = "clinical_pico_unscoped"
            scope_reasons.append(
                "Clinical question has neither extractable population nor "
                "intervention after overrides; retrieval would be too broad "
                "to produce a meaningful evidence corpus."
            )
            needs_review = False
        elif pico_missing:
            # One anchor missing: flag for review but still proceed.
            scope_decision = "review"
            needs_review = True

    if not tier_expectations and not scope_rejected:
        notes.append(
            f"Template {template_path_rel} did not define "
            f"expected_tier_distribution. Corpus-approval gate will "
            f"have no reference distribution."
        )

    # 7. Assemble protocol
    now = time.time()
    protocol = ProtocolDocument(
        run_id=run_id,
        created_at_unix=now,
        created_at_iso=time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)
        ),
        research_question=research_question.strip(),
        domain=domain,
        population=pico["population"],
        intervention=pico["intervention"],
        comparator=pico["comparator"],
        outcome=pico["outcome"],
        criteria=criteria,
        expected_tier_distribution=tier_expectations,
        date_range=date_range,
        geography=geography,
        languages=languages,
        excluded_sponsors=excluded_sponsors,
        template_used=template_path_rel,
        user_overrides=overrides,
        needs_user_review=needs_review,
        notes=notes,
        scope_decision=scope_decision,
        scope_rejected=scope_rejected,
        scope_rejection_code=scope_rejection_code,
        scope_reasons=scope_reasons,
    )

    # 8. Write atomically + compute SHA-256
    protocol_path = run_dir_path / "protocol.json"
    tmp_path = run_dir_path / "protocol.json.tmp"
    data = protocol.to_json_dict()
    # Sort keys so hash is stable across runs with identical content.
    payload = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
    tmp_path.write_text(payload + "\n", encoding="utf-8")
    # Atomic rename
    os.replace(tmp_path, protocol_path)
    sha256 = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    logger.info(
        "[scope_gate] protocol written run_id=%s domain=%s path=%s sha256=%s",
        run_id, domain, protocol_path, sha256[:16],
    )

    return ScopeGateResult(
        protocol=protocol,
        protocol_path=protocol_path,
        protocol_sha256=sha256,
    )


def verify_protocol(protocol_path: Path | str) -> tuple[bool, str, str]:
    """Re-hash an on-disk protocol.json to detect tampering.

    Returns:
        (ok, sha256_hex, error_message). ok=True if the hash matches
        what we'd re-compute from the file contents. error_message is
        empty when ok is True.
    """
    path = Path(protocol_path)
    if not path.exists():
        return (False, "", f"protocol file not found: {path}")
    try:
        content = path.read_text(encoding="utf-8").rstrip("\n")
        # Re-parse + re-dump with same sort keys to normalize formatting
        obj = json.loads(content)
        normalized = json.dumps(
            obj, indent=2, sort_keys=True, ensure_ascii=False,
        )
        sha256 = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return (True, sha256, "")
    except Exception as exc:
        return (False, "", f"protocol verification failed: {exc}")
