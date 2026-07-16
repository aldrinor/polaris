"""feat/intake-contract — query-type PROFILES (defaults-only presentation lane).

A query-type profile supplies DEFAULT values for the champion-missing PRESENTATION
fields (tone / audience / format / length) plus a ``typical_sections`` skeleton, per
query TYPE (literature_review / comparison / clinical / market_industry / how_to /
general). Profiles are DECLARATIVE DEFAULTS ONLY:

  * a profile value is written into a contract field ONLY when that field is UNSET
    (the ``is_set()`` gate in contract_compiler._apply_profiles) — an explicit prompt
    directive, a floor value, or an enrich value ALWAYS wins;
  * every profile-injected field carries origin='profile_default', strength='default'
    (the weakest tier), so it can never masquerade as a user directive;
  * profiles NEVER touch date_window / language / source_rules / scope_constraints /
    user_constraints / instruction_slots — no scope-narrowing, no citation influence.

This module is imported ONLY when PG_CONTRACT_QUERY_TYPE_PROFILES is ON, so the hot
floor path never pulls in yaml when the flag is off. An in-code fallback constant is
returned verbatim if the yaml files or the yaml library are unavailable, so a profile
lookup can never raise on the compile path.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("polaris_graph.intake.contract_profiles")

# The presentation fields a profile is ALLOWED to default. Deliberately excludes
# output_language (never defaulted) and every narrowing/scope field.
PROFILE_PRESENTATION_FIELDS = ("tone", "audience", "format", "length")

# config/intake_contract/profiles under the repo root.
_PROFILE_DIR = Path(__file__).resolve().parents[3] / "config" / "intake_contract" / "profiles"

# ─────────────────────────────────────────────────────────────────────────────
# In-code fallback (authoritative shape). Mirrors the yaml files 1:1 so the
# compile path NEVER hard-depends on yaml being importable/present. ``priority``
# orders stacked profiles: a HIGHER priority is more specific and applies FIRST
# (first writer of a field wins), so clinical > comparison > how_to >
# literature_review > market_industry > general.
# ─────────────────────────────────────────────────────────────────────────────

_FALLBACK_PROFILES: dict[str, dict[str, Any]] = {
    "clinical": {
        "priority": 100,
        "tone": "precise, cautious, clinically neutral",
        "audience": "clinicians and evidence-literate practitioners",
        "format": "evidence synthesis with explicit strength-of-evidence framing",
        "length": "comprehensive",
        "typical_sections": [
            "Background and Clinical Question",
            "Evidence Summary",
            "Safety and Adverse Effects",
            "Strength of Evidence and Limitations",
            "Clinical Bottom Line",
        ],
    },
    "comparison": {
        "priority": 90,
        "tone": "balanced, evaluative, evidence-weighing",
        "audience": "a decision-maker weighing options",
        "format": "structured comparison across shared dimensions",
        "length": "focused",
        "typical_sections": [
            "Overview of the Options",
            "Comparison Across Key Dimensions",
            "Trade-offs and Contradicting Evidence",
            "Bottom Line",
        ],
    },
    "how_to": {
        "priority": 80,
        "tone": "clear, instructional, pragmatic",
        "audience": "a practitioner following the steps",
        "format": "step-by-step procedural guide",
        "length": "focused",
        "typical_sections": [
            "Prerequisites",
            "Step-by-Step Procedure",
            "Common Pitfalls",
            "Verification",
        ],
    },
    "literature_review": {
        "priority": 70,
        "tone": "scholarly, analytical, measured",
        "audience": "researchers and domain experts",
        "format": "narrative synthesis organized by theme",
        "length": "comprehensive",
        "typical_sections": [
            "Introduction and Scope",
            "Thematic Findings",
            "Cross-Study Synthesis and Contradictions",
            "Research Gaps",
            "Conclusions",
        ],
    },
    "market_industry": {
        "priority": 60,
        "tone": "objective, commercially aware, data-driven",
        "audience": "business and strategy stakeholders",
        "format": "market analysis organized by segment and driver",
        "length": "comprehensive",
        "typical_sections": [
            "Market Overview",
            "Key Segments and Players",
            "Drivers and Headwinds",
            "Outlook",
        ],
    },
    "general": {
        "priority": 0,
        "tone": "clear, neutral, informative",
        "audience": "an informed general reader",
        "format": "narrative organized by theme",
        "length": "balanced",
        "typical_sections": [
            "Overview",
            "Key Findings",
            "Conclusions",
        ],
    },
}

_ALLOWED_KEYS = frozenset(
    {"priority", "typical_sections"} | set(PROFILE_PRESENTATION_FIELDS)
)

_cache: "dict[str, dict[str, Any]] | None" = None


def _sanitize(name: str, raw: Any) -> "dict[str, Any] | None":
    """Coerce a loaded profile dict into the trusted shape, dropping any unknown
    key so a profile file can only ever declare defaults for the whitelisted
    presentation fields + typical_sections + priority. Returns None if unusable."""
    if not isinstance(raw, dict):
        return None
    out: dict[str, Any] = {}
    for key in PROFILE_PRESENTATION_FIELDS:
        val = raw.get(key)
        if isinstance(val, str) and val.strip():
            out[key] = val.strip()
    secs = raw.get("typical_sections")
    if isinstance(secs, list):
        out["typical_sections"] = [str(s).strip() for s in secs if str(s).strip()]
    else:
        out["typical_sections"] = []
    try:
        out["priority"] = int(raw.get("priority", 0))
    except (TypeError, ValueError):
        out["priority"] = 0
    return out


def load_profiles() -> dict[str, dict[str, Any]]:
    """Return the query-type profile table (cached). Tries the yaml files under
    config/intake_contract/profiles; on ANY failure (missing dir, missing yaml
    library, parse error) falls back to the in-code constant. Never raises."""
    global _cache
    if _cache is not None:
        return _cache

    profiles: dict[str, dict[str, Any]] = {
        name: dict(spec) for name, spec in _FALLBACK_PROFILES.items()
    }
    try:
        import yaml  # noqa: PLC0415 — imported only under the flag

        for name in list(profiles):
            path = _PROFILE_DIR / f"{name}.yaml"
            if not path.exists():
                continue
            try:
                loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001 — a bad file keeps the fallback
                logger.warning(
                    "[contract_profiles] %s unreadable (%s) — using in-code default",
                    path.name, str(exc)[:120],
                )
                continue
            sanitized = _sanitize(name, loaded)
            if sanitized is not None:
                profiles[name] = sanitized
    except Exception as exc:  # noqa: BLE001 — no yaml => pure in-code fallback
        logger.info("[contract_profiles] yaml unavailable (%s) — in-code defaults", str(exc)[:120])

    _cache = profiles
    return _cache
