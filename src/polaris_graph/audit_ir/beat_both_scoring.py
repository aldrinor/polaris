"""M-D9 phase 2 (Phase D): BEAT-BOTH dimension scoring.

Phase 1 of M-D9 (commit 8abf160) shipped pin + induction
precision + manifest verdict diff. Phase 2 layers
**per-dimension regression detection** on top: the 7 BEAT-BOTH
dimensions from `state/v17_vs_tier1_headtohead.md` get scored
against a manifest, and regressions per dimension trip the CI
gate.

## Why this milestone matters

The user-mandated stop criterion (per
`autoloop_beat_tier1_mandate.md`, locked 2026-04-20) is "V_N
beats both ChatGPT DR + Gemini 3.1 Pro DR on the agreed 7
dimensions". Phase 1 checks pipeline-internal regressions
(precision, taxonomy drift). Phase 2 checks per-dimension
*content-shape* regressions — has citation count dropped, has
narrative length collapsed, has structural depth regressed
since the baseline?

This is the BEAT-BOTH dimension scoring deliverable from
`docs/phase_d_milestones.md` line 88: "BEAT-BOTH dimension
scoring as part of CI". Phase 2 makes the dimension shape
**CI-enforceable**.

## The 7 BEAT-BOTH dimensions

Documented in `state/v17_vs_tier1_headtohead.md` and the locked
memory `autoloop_beat_tier1_mandate.md`:

  1. unique_citations        — distinct URLs cited
  2. regulatory_coverage     — count of FDA/EMA/HC source URLs
  3. jurisdictional_precision — distinct jurisdictions named
  4. claim_frames            — claims with N/baseline/endpoint/CI
  5. structural_depth        — tables + sub-section count
  6. contradiction_handling_grammar — contrast markers tied to claims
  7. narrative_length        — total body prose word count

All 7 ship as default scorers in `BEAT_BOTH_SCORERS`. The API
also accepts custom scorers via the `DimensionScorer` Protocol
so future dimensions land cleanly without forking this module.

## What phase 2 v1 ships

  - `BeatBothDimension` enum — closed taxonomy of the 7
  - `DimensionScore` dataclass — value + direction + rationale
  - `DimensionScorer` Protocol — pluggable scorer contract
  - 7 concrete scorer impls (one per dimension), each defensive
    on missing manifest fields
  - `score_run(manifest, *, scorers)` — pure derivation, no I/O
  - `DimensionRegression` dataclass + `diff_dimension_scores`
  - `BeatBothReport` + `report_to_exit_code` (RED → 1)

## What phase 2 v1 does NOT do

  - No live competitor comparison ("are we beating ChatGPT
    today?"). That's V19+ live-audit territory; phase 2 here
    scores AGAINST a baseline pin only.
  - No dimension-class trend analysis (rolling-window
    regression). Phase 2 v2 may add it.
  - No tolerance auto-calibration. Each dimension ships with a
    default tolerance + env override (LAW VI); calibration
    against run history is phase 2 v2 territory.

See `docs/md9_phase2_threat_model.md` for the full boundaries.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Protocol
from urllib.parse import urlsplit


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class BeatBothScoringError(ValueError):
    """Raised on contract violations — invalid scorer, malformed
    DimensionScore, etc."""


# ---------------------------------------------------------------------------
# Dimension taxonomy
# ---------------------------------------------------------------------------


class BeatBothDimension(str, Enum):
    """The 7 BEAT-BOTH dimensions per
    `state/v17_vs_tier1_headtohead.md` and locked memory
    `autoloop_beat_tier1_mandate.md`. String values match the
    documented dimension names so external consumers (CI logs,
    audit reports) can compare without importing the enum."""

    UNIQUE_CITATIONS = "unique_citations"
    REGULATORY_COVERAGE = "regulatory_coverage"
    JURISDICTIONAL_PRECISION = "jurisdictional_precision"
    CLAIM_FRAMES = "claim_frames"
    STRUCTURAL_DEPTH = "structural_depth"
    CONTRADICTION_HANDLING_GRAMMAR = "contradiction_handling_grammar"
    NARRATIVE_LENGTH = "narrative_length"


# ---------------------------------------------------------------------------
# DimensionScore + Protocol
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DimensionScore:
    """One scorer's verdict for one manifest.

    `dimension` is a string (not enum) so callers can ship
    custom dimensions via the Protocol without extending the
    enum.

    `value` is a numeric score — count or ratio, dimension-
    specific. `higher_is_better` interprets the direction of
    "good": a unique-citation count of 24 is better than 18
    (higher_is_better=True), a hypothetical "duplicate-claim
    count" would be lower=better.

    `rationale` is human-readable text surfaced to operators on
    regression alerts.
    """

    dimension: str
    value: float
    higher_is_better: bool
    rationale: str


class DimensionScorer(Protocol):
    """Pluggable scorer contract.

    Implementers MUST:
      - Be deterministic given the same manifest dict
      - Be defensive on missing fields (return 0.0 with a
        rationale, NOT raise) — manifests vary across pipeline
        revisions
      - Return a `DimensionScore` whose `dimension` matches the
        scorer's `dimension` property

    Implementers MUST NOT:
      - Mutate the manifest
      - Make I/O calls (HTTP, DB, file). Phase 2 is pure
        derivation; live retrieval / fetching is V19+ territory.
    """

    @property
    def dimension(self) -> str:
        ...

    @property
    def higher_is_better(self) -> bool:
        ...

    def score(self, manifest: dict[str, Any]) -> DimensionScore:
        ...


# ---------------------------------------------------------------------------
# Manifest probe helpers (defensive on missing fields)
# ---------------------------------------------------------------------------


_MISSING = object()


def _is_frame_field_populated(value: Any) -> bool:
    """Codex round-2 LOW fix (v3): a frame field counts as
    populated when:
      - it's not the sentinel (key absent from dict)
      - it's not None
      - it's not the empty string

    Numeric 0 / 0.0 (legitimate baseline / endpoint values) DO
    count as populated. This is the round-1 fix preserved.
    """
    if value is _MISSING or value is None:
        return False
    if isinstance(value, str) and value == "":
        return False
    return True


def _coerce_iterable(value: Any) -> tuple[Any, ...]:
    """Best-effort coerce to tuple. None / scalar → empty tuple."""
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(value)
    if isinstance(value, dict):
        return tuple(value.values())
    return ()


def _get(manifest: dict[str, Any], *keys: str) -> Any:
    """Nested dict get; returns None if any key missing."""
    cursor: Any = manifest
    for key in keys:
        if not isinstance(cursor, dict) or key not in cursor:
            return None
        cursor = cursor[key]
    return cursor


# ---------------------------------------------------------------------------
# Concrete scorers (one per BEAT-BOTH dimension)
# ---------------------------------------------------------------------------


# Codex round-1 MED fix (v2): regulatory matching now parses the
# URL host and checks membership in `_REGULATORY_HOSTS`, not a
# regex against the full URL. The v1 regex matched any URL whose
# path or query string contained a regulatory hostname literal,
# e.g. `https://example.com/redirect?u=https://fda.gov/x` falsely
# scored as regulatory coverage. v2 only counts a URL as
# regulatory if its actual host matches.
_REGULATORY_HOSTS: frozenset[str] = frozenset({
    "accessdata.fda.gov",
    "fda.gov",
    "ema.europa.eu",
    "canada.ca",                      # health canada main
    "hc-sc.gc.ca",                    # health canada legacy
    "recalls-rappels.canada.ca",
    "dhpp.hpfb-dgpsa.ca",
    "pdf.hres.ca",
    "pi.lilly.com",                   # lilly prescribing info
    "nice.org.uk",                    # NICE UK
    "cdc.gov",
    "nih.gov",
    "clinicaltrials.gov",
})


# Per-domain → jurisdiction map for the precision dimension.
# Conservative; only domains we KNOW are jurisdiction-tagged.
_JURISDICTION_HOSTS = {
    "accessdata.fda.gov": "US",
    "fda.gov": "US",
    "cdc.gov": "US",
    "nih.gov": "US",
    "clinicaltrials.gov": "US",
    "ema.europa.eu": "EU",
    "canada.ca": "CA",
    "hc-sc.gc.ca": "CA",
    "recalls-rappels.canada.ca": "CA",
    "dhpp.hpfb-dgpsa.ca": "CA",
    "pdf.hres.ca": "CA",
    "nice.org.uk": "UK",
    "pi.lilly.com": "US",
}


def _host_of(url: str) -> str:
    """Parse the canonical lowercase host from a URL.

    Codex round-2 MED fix (v3): strip userinfo (`user:pass@`),
    port (`:443`), query (`?x=1`), and fragment (`#frag`) so
    legitimate regulatory URLs with any of those components
    parse to the bare hostname. v1+v2 used a simple regex that
    only stopped at `/`, so `https://fda.gov:443/x` returned
    `fda.gov:443` and missed the regulatory frozenset check.

    Uses `urllib.parse.urlsplit` for canonical parsing —
    Python's standard URL parser handles the edge cases
    (escaped userinfo, IPv6 brackets, etc.) more robustly than
    regex.
    """
    if not url:
        return ""
    # urlsplit handles missing scheme by treating the whole
    # thing as path; pre-pend `//` if no scheme so it parses
    # the host correctly.
    candidate = url.strip()
    if "://" not in candidate and not candidate.startswith("//"):
        candidate = "//" + candidate
    try:
        parts = urlsplit(candidate)
        host = parts.hostname or ""
    except (ValueError, AttributeError):
        return ""
    # Strip the leading "www." per the v1 convention so
    # www.fda.gov and fda.gov hit the same regulatory entry.
    host_lower = host.lower()
    if host_lower.startswith("www."):
        host_lower = host_lower[4:]
    return host_lower


def _citation_urls(manifest: dict[str, Any]) -> tuple[str, ...]:
    """Pull citation URLs from a manifest. Looks at multiple
    plausible locations: top-level `citations`, `evidence`,
    nested `report.citations`, etc. Returns a deduplicated tuple.
    """
    candidates: list[str] = []
    for path in (
        ("citations",),
        ("evidence",),
        ("report", "citations"),
        ("report", "evidence"),
    ):
        bag = _get(manifest, *path)
        for entry in _coerce_iterable(bag):
            if isinstance(entry, str):
                candidates.append(entry)
            elif isinstance(entry, dict):
                for key in ("url", "source_url", "doi", "pmid"):
                    val = entry.get(key)
                    if isinstance(val, str):
                        candidates.append(val)
                        break
    seen: set[str] = set()
    out: list[str] = []
    for url in candidates:
        normalized = url.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return tuple(out)


@dataclass(frozen=True)
class _UniqueCitationsScorer:
    dimension: str = BeatBothDimension.UNIQUE_CITATIONS.value
    higher_is_better: bool = True

    def score(self, manifest: dict[str, Any]) -> DimensionScore:
        urls = _citation_urls(manifest)
        return DimensionScore(
            dimension=self.dimension,
            value=float(len(urls)),
            higher_is_better=self.higher_is_better,
            rationale=(
                f"{len(urls)} unique citation URLs found in manifest"
                if urls
                else "no citation URLs found in manifest "
                "(checked citations / evidence / report.citations)"
            ),
        )


@dataclass(frozen=True)
class _RegulatoryCoverageScorer:
    dimension: str = BeatBothDimension.REGULATORY_COVERAGE.value
    higher_is_better: bool = True

    def score(self, manifest: dict[str, Any]) -> DimensionScore:
        urls = _citation_urls(manifest)
        regulatory = tuple(
            url for url in urls if _host_of(url) in _REGULATORY_HOSTS
        )
        return DimensionScore(
            dimension=self.dimension,
            value=float(len(regulatory)),
            higher_is_better=self.higher_is_better,
            rationale=(
                f"{len(regulatory)} regulatory-source URLs found "
                f"(FDA / EMA / Health Canada / NICE / etc.) "
                f"out of {len(urls)} total"
            ),
        )


@dataclass(frozen=True)
class _JurisdictionalPrecisionScorer:
    dimension: str = BeatBothDimension.JURISDICTIONAL_PRECISION.value
    higher_is_better: bool = True

    def score(self, manifest: dict[str, Any]) -> DimensionScore:
        urls = _citation_urls(manifest)
        jurisdictions: set[str] = set()
        for url in urls:
            host = _host_of(url)
            if host in _JURISDICTION_HOSTS:
                jurisdictions.add(_JURISDICTION_HOSTS[host])
        return DimensionScore(
            dimension=self.dimension,
            value=float(len(jurisdictions)),
            higher_is_better=self.higher_is_better,
            rationale=(
                f"{len(jurisdictions)} distinct jurisdictions covered: "
                f"{sorted(jurisdictions) or 'none'}"
            ),
        )


@dataclass(frozen=True)
class _ClaimFramesScorer:
    """Counts claims that have ALL FOUR frame fields populated:
    N (sample size), baseline, endpoint, CI (confidence interval).

    Looks in `claims` / `verified_claims` / `report.claims`.
    Each claim is a dict; the four field names are well-known
    from V19+ POLARIS prompts.
    """

    dimension: str = BeatBothDimension.CLAIM_FRAMES.value
    higher_is_better: bool = True
    _FRAME_KEYS: tuple[str, ...] = (
        "n", "baseline", "endpoint", "ci",
    )

    def score(self, manifest: dict[str, Any]) -> DimensionScore:
        claims: list[dict[str, Any]] = []
        for path in (
            ("claims",),
            ("verified_claims",),
            ("report", "claims"),
        ):
            bag = _get(manifest, *path)
            for entry in _coerce_iterable(bag):
                if isinstance(entry, dict):
                    claims.append(entry)
        complete = 0
        # Codex round-1 LOW fix (v2): use explicit "key in claim
        # and value is not None" rather than `all(claim.get(key))`.
        # The truthy check would treat a populated `baseline=0.0`
        # or `endpoint=0.0` (legitimate baseline measurements) as
        # missing.
        # Codex round-2 LOW fix (v3): also reject empty strings.
        # An empty `ci=""` is morally missing — it doesn't carry
        # the [low, high] range the dimension counts. Numeric 0
        # stays present (legitimate measurement value); empty
        # string is not.
        for claim in claims:
            if all(
                _is_frame_field_populated(claim.get(key, _MISSING))
                for key in self._FRAME_KEYS
            ):
                complete += 1
        return DimensionScore(
            dimension=self.dimension,
            value=float(complete),
            higher_is_better=self.higher_is_better,
            rationale=(
                f"{complete} claims with all 4 frame fields "
                f"(N + baseline + endpoint + CI) "
                f"out of {len(claims)} total claims"
            ),
        )


@dataclass(frozen=True)
class _StructuralDepthScorer:
    """Sum of comparison tables + named sub-sections.

    Checks `tables` / `report.tables` for table count and
    `sections` / `report.sections` for sub-section count.
    """

    dimension: str = BeatBothDimension.STRUCTURAL_DEPTH.value
    higher_is_better: bool = True

    def score(self, manifest: dict[str, Any]) -> DimensionScore:
        # Codex round-1 MED fix (v2): probe top-level OR nested,
        # NOT both. v1 summed both paths, double-counting when a
        # manifest mirrored tables/sections at both levels (which
        # contradicted the threat-model "OR" wording). Use the
        # first-non-empty-wins pattern matching `_citation_urls`.
        table_count = 0
        for path in (("tables",), ("report", "tables")):
            bag = _get(manifest, *path)
            entries = _coerce_iterable(bag)
            if entries:
                table_count = len(entries)
                break
        section_count = 0
        for path in (("sections",), ("report", "sections")):
            bag = _get(manifest, *path)
            entries = _coerce_iterable(bag)
            if entries:
                section_count = len(entries)
                break
        depth = table_count + section_count
        return DimensionScore(
            dimension=self.dimension,
            value=float(depth),
            higher_is_better=self.higher_is_better,
            rationale=(
                f"structural depth = {depth} "
                f"({table_count} tables + {section_count} sections)"
            ),
        )


_CONTRADICTION_MARKERS = (
    "however", "but", "in contrast", "conversely", "on the other hand",
    "whereas", "although", "despite", "nonetheless", "yet",
)


@dataclass(frozen=True)
class _ContradictionHandlingScorer:
    """Counts contradiction-grammar markers in the body prose.

    Reads `report.body` or `body` (free-text). Counts case-
    insensitive occurrences of contrast markers like "however",
    "in contrast", "whereas", etc. Approximate proxy for
    contradiction-aware writing.
    """

    dimension: str = BeatBothDimension.CONTRADICTION_HANDLING_GRAMMAR.value
    higher_is_better: bool = True

    def score(self, manifest: dict[str, Any]) -> DimensionScore:
        body = ""
        for path in (("report", "body"), ("body",)):
            value = _get(manifest, *path)
            if isinstance(value, str) and value:
                body = value
                break
        if not body:
            return DimensionScore(
                dimension=self.dimension,
                value=0.0,
                higher_is_better=self.higher_is_better,
                rationale="no body prose found in manifest",
            )
        body_lower = body.lower()
        count = 0
        for marker in _CONTRADICTION_MARKERS:
            count += len(re.findall(rf"\b{re.escape(marker)}\b", body_lower))
        return DimensionScore(
            dimension=self.dimension,
            value=float(count),
            higher_is_better=self.higher_is_better,
            rationale=(
                f"{count} contradiction-grammar markers in body prose "
                f"(however/but/in contrast/whereas/etc.)"
            ),
        )


@dataclass(frozen=True)
class _NarrativeLengthScorer:
    """Total word count of the body prose."""

    dimension: str = BeatBothDimension.NARRATIVE_LENGTH.value
    higher_is_better: bool = True

    def score(self, manifest: dict[str, Any]) -> DimensionScore:
        body = ""
        for path in (("report", "body"), ("body",)):
            value = _get(manifest, *path)
            if isinstance(value, str) and value:
                body = value
                break
        word_count = len(body.split())
        return DimensionScore(
            dimension=self.dimension,
            value=float(word_count),
            higher_is_better=self.higher_is_better,
            rationale=(
                f"{word_count} body-prose words"
                if body
                else "no body prose found in manifest"
            ),
        )


BEAT_BOTH_SCORERS: tuple[DimensionScorer, ...] = (
    _UniqueCitationsScorer(),
    _RegulatoryCoverageScorer(),
    _JurisdictionalPrecisionScorer(),
    _ClaimFramesScorer(),
    _StructuralDepthScorer(),
    _ContradictionHandlingScorer(),
    _NarrativeLengthScorer(),
)


# ---------------------------------------------------------------------------
# Per-dimension tolerances (env-overridable, LAW VI)
# ---------------------------------------------------------------------------


_DEFAULT_TOLERANCES: dict[str, float] = {
    BeatBothDimension.UNIQUE_CITATIONS.value: 2.0,
    BeatBothDimension.REGULATORY_COVERAGE.value: 1.0,
    BeatBothDimension.JURISDICTIONAL_PRECISION.value: 1.0,
    BeatBothDimension.CLAIM_FRAMES.value: 5.0,
    BeatBothDimension.STRUCTURAL_DEPTH.value: 1.0,
    BeatBothDimension.CONTRADICTION_HANDLING_GRAMMAR.value: 2.0,
    BeatBothDimension.NARRATIVE_LENGTH.value: 100.0,
}


def _env_var_for(dimension: str) -> str:
    return f"PG_BEAT_BOTH_{dimension.upper()}_TOLERANCE"


def tolerance_for(dimension: str) -> float:
    """Resolve a per-dimension tolerance.

    Priority (LAW VI): env var > built-in default. Out-of-range
    values clamp to >= 0.0; non-numeric env values fall back to
    the built-in default.

    Custom dimensions (not in `_DEFAULT_TOLERANCES`) default to
    0.0 — any change is a regression unless the caller supplies
    `tolerances=` explicitly to `diff_dimension_scores`.
    """
    raw = os.environ.get(_env_var_for(dimension))
    if raw is not None and raw != "":
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    return _DEFAULT_TOLERANCES.get(dimension, 0.0)


# ---------------------------------------------------------------------------
# Diff machinery
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DimensionRegression:
    """One per-dimension regression entry.

    `delta` is `current.value - baseline.value`. `is_regression`
    is True when the delta moves in the WRONG direction beyond
    `tolerance` (direction interpreted via `higher_is_better`).
    `severity` is "ok" | "minor" | "major".
    """

    dimension: str
    baseline_value: float
    current_value: float
    delta: float
    tolerance: float
    higher_is_better: bool
    is_regression: bool
    severity: str
    rationale: str


@dataclass(frozen=True)
class BeatBothReport:
    """Combined per-dimension regression report."""

    baseline_scores: dict[str, DimensionScore]
    current_scores: dict[str, DimensionScore]
    dimensions: tuple[DimensionRegression, ...]
    verdict: "BeatBothVerdict"


class BeatBothVerdict(Enum):
    """Top-level verdict.

    GREEN: no dimension regressed beyond tolerance.
    YELLOW: at least one dimension moved beyond tolerance but
       all stayed within ±2x tolerance (minor severity).
    RED: at least one dimension regressed beyond 2x tolerance
       (major severity) — CI blocks merge.
    """

    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


def score_run(
    manifest: dict[str, Any],
    *,
    scorers: Iterable[DimensionScorer] = BEAT_BOTH_SCORERS,
) -> dict[str, DimensionScore]:
    """Score a manifest across the requested dimensions.

    Pure derivation — no I/O. Returns a dict keyed by
    `scorer.dimension`. Validates each returned score against
    its scorer's contract.
    """
    if not isinstance(manifest, dict):
        raise BeatBothScoringError(
            f"manifest must be a dict, got {type(manifest).__name__}"
        )
    scores: dict[str, DimensionScore] = {}
    for scorer in scorers:
        result = scorer.score(manifest)
        if not isinstance(result, DimensionScore):
            raise BeatBothScoringError(
                f"scorer {scorer!r} returned "
                f"{type(result).__name__}, expected DimensionScore"
            )
        if result.dimension != scorer.dimension:
            raise BeatBothScoringError(
                f"scorer {scorer!r} returned dimension "
                f"{result.dimension!r}, expected "
                f"{scorer.dimension!r}"
            )
        if result.higher_is_better != scorer.higher_is_better:
            raise BeatBothScoringError(
                f"scorer {scorer!r} returned higher_is_better="
                f"{result.higher_is_better}, expected "
                f"{scorer.higher_is_better}"
            )
        scores[scorer.dimension] = result
    return scores


def diff_dimension_scores(
    baseline_scores: dict[str, DimensionScore],
    current_scores: dict[str, DimensionScore],
    *,
    tolerances: dict[str, float] | None = None,
) -> BeatBothReport:
    """Diff two score dicts; return a BeatBothReport.

    `tolerances` overrides per-dimension defaults. If a dimension
    appears in baseline + current but is missing from
    `tolerances`, `tolerance_for(dim)` resolves the default
    (env > built-in).

    Verdict logic:
      - GREEN: no `is_regression=True` entries
      - RED:   any entry has `severity="major"`
      - YELLOW: `is_regression=True` exists but all are minor
    """
    if not isinstance(baseline_scores, dict) or not isinstance(
        current_scores, dict
    ):
        raise BeatBothScoringError(
            "baseline_scores and current_scores must be dicts"
        )
    overrides = tolerances or {}
    common = sorted(set(baseline_scores) & set(current_scores))
    entries: list[DimensionRegression] = []
    has_major = False
    has_minor = False
    for dim in common:
        baseline = baseline_scores[dim]
        current = current_scores[dim]
        if baseline.higher_is_better != current.higher_is_better:
            raise BeatBothScoringError(
                f"dimension {dim!r}: baseline higher_is_better="
                f"{baseline.higher_is_better} but current="
                f"{current.higher_is_better}"
            )
        tolerance = overrides.get(dim, tolerance_for(dim))
        if tolerance < 0:
            raise BeatBothScoringError(
                f"tolerance for {dim!r} is negative: {tolerance}"
            )
        delta = current.value - baseline.value
        # Direction: regression = movement against higher_is_better.
        regression_size = -delta if baseline.higher_is_better else delta
        is_regression = regression_size > tolerance
        if is_regression:
            severity = "major" if regression_size > 2 * tolerance else "minor"
            if severity == "major":
                has_major = True
            else:
                has_minor = True
        else:
            severity = "ok"
        entries.append(
            DimensionRegression(
                dimension=dim,
                baseline_value=baseline.value,
                current_value=current.value,
                delta=delta,
                tolerance=tolerance,
                higher_is_better=baseline.higher_is_better,
                is_regression=is_regression,
                severity=severity,
                rationale=(
                    f"{dim}: baseline={baseline.value} → current="
                    f"{current.value} (delta={delta:+.2f}, "
                    f"tolerance={tolerance}, severity={severity})"
                ),
            )
        )
    if has_major:
        verdict = BeatBothVerdict.RED
    elif has_minor:
        verdict = BeatBothVerdict.YELLOW
    else:
        verdict = BeatBothVerdict.GREEN
    return BeatBothReport(
        baseline_scores=baseline_scores,
        current_scores=current_scores,
        dimensions=tuple(entries),
        verdict=verdict,
    )


def report_to_exit_code(report: BeatBothReport) -> int:
    """Map a BeatBothReport verdict to a CI exit code.

    GREEN  → 0 (merge OK)
    YELLOW → 0 (minor regressions — operator review only)
    RED    → 1 (major regression — block merge)

    Mirrors the M-D9 phase 1 `regression_lab.report_to_exit_code`
    convention: only RED blocks the build. YELLOW is a flag, not
    a gate.
    """
    return 1 if report.verdict is BeatBothVerdict.RED else 0


__all__ = [
    "BEAT_BOTH_SCORERS",
    "BeatBothDimension",
    "BeatBothReport",
    "BeatBothScoringError",
    "BeatBothVerdict",
    "DimensionRegression",
    "DimensionScore",
    "DimensionScorer",
    "diff_dimension_scores",
    "report_to_exit_code",
    "score_run",
    "tolerance_for",
]
