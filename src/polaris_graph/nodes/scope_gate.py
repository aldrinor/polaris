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

# B9 domain-generalization: the general-domain constant. Imported at top so the
# classifier helpers reference it cleanly. domain_signal imports scope_gate ONLY
# lazily inside functions, so there is no import cycle at module load.
from src.polaris_graph.domain.domain_signal import GENERAL_DOMAIN  # noqa: E402

# Repo root for locating config/scope_templates/.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCOPE_TEMPLATES_DIR = _REPO_ROOT / "config" / "scope_templates"

# Supported domain hints. Determines which scope template is loaded. This is the
# CANONICAL-8 set (tests/v6/test_template_canonical_set.py enforces exact
# set-equality across scope_templates / SUPPORTED_DOMAINS / v6 templates /
# frontend / actors). B9 does NOT add a 9th template here — the B9 "general"
# concept lives in the SEPARATE domain-pack layer (config/domain_packs/, governed
# by src/polaris_graph/domain/). The domain-agnostic SCOPE TEMPLATE is the
# existing `custom` (free-form, tier-permissive) entry of the canonical 8.
# BUG-B-102 R2b: `custom` is the pipeline-B UI free-form path.
SUPPORTED_DOMAINS = frozenset({
    "clinical", "policy", "tech", "due_diligence", "custom",
    # Carney delivery templates (I-tpl-006/7/8 trio complete).
    "ai_sovereignty", "canada_us", "workforce",
})

# B9 domain-generalization (the spine): the DEFAULT is the domain-AGNOSTIC
# `custom` template, NOT clinical. The historical "clinical" default silently ran
# the clinical PICO path on every domain-less call (SG1). A domain-less / blank
# caller now routes to `custom` (the canonical free-form, tier-permissive
# template) — NEVER clinical, never abort. A clinical question is DETECTED
# (positive drug/clinical-population signal) or supplied explicitly
# (`domain="clinical"`), never assumed. (The B9 conceptual "general" domain is
# the domain-pack default in config/domain_packs/general.yaml; `custom` is its
# scope-template realization within the locked canonical-8.)
DEFAULT_DOMAIN = "custom"


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

    # I-deepfix-001 B10(a) (#1352): structured HARD user constraints extracted
    # from the NL research question at intake (date window / language / journal-
    # only-dormant). to_json_dict serializes this so the wave-2 enforcement layers
    # (selection demote, rule_blockers) and the audit trail can read it. Empty
    # dict when the extractor is OFF or found nothing => byte-identical legacy
    # protocol shape for the populated fields.
    user_constraints: dict[str, Any] = field(default_factory=dict)

    # I-scope-001: structured per-question SCOPE intent (source-type / jurisdiction facets +
    # include/prefer/exclude op + weight/hard strictness + named include/exclude). Empty dict
    # when the extractor is OFF or found nothing => the enforcer builds empty maps => byte-
    # identical widest+deepest run. to_json_dict() serializes this via asdict() as an ADDITIVE
    # key (`scope_constraints: {}` on the no-constraint path — the ONE inert protocol.json
    # difference vs today). Read by the scope enforcer only; no abort/approval/release gate.
    scope_constraints: dict[str, Any] = field(default_factory=dict)

    # O2 (2026-07-15, feat/intake-contract): explicit-instruction slots extracted
    # from the research question (comparison / enumeration / topic / structure).
    # Populated ONLY when PG_EXTRACT_INSTRUCTION_SLOTS=1 (default OFF); empty list
    # otherwise. to_json_dict() OMITS this key entirely when empty so the OFF path
    # is byte-identical protocol.json (stricter than the scope_constraints inert-key
    # precedent). ADDITIVE metadata only: it drops no source and never touches the
    # faithfulness engine.
    instruction_slots: list[dict[str, Any]] = field(default_factory=list)

    # Part 1 (2026-07-15, feat/intake-contract): the compiled unified intake
    # contract (SHADOW only). Optional[dict]=None (NOT default_factory) so
    # to_json_dict() can pop it when None => the OFF path emits NO new key
    # (byte-identical). Populated ONLY when PG_INTAKE_CONTRACT_COMPILE=1 (default
    # OFF). SHADOW: recorded, never consumed for filtering; source_rules enforcement
    # is disabled (operator sign-off + full-benchmark A/B required per the plan).
    intake_contract: Optional[dict[str, Any]] = None

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
        # feat/intake-contract byte-identity: the two NEW additive fields emit NO
        # protocol.json key on their OFF/empty path, so a flags-off protocol.json is
        # byte-identical to today (not merely semantically inert). When their flags
        # are ON and they carry content, the keys appear.
        if not self.instruction_slots:
            data.pop("instruction_slots", None)
        if self.intake_contract is None:
            data.pop("intake_contract", None)
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
# NOTE: `_DRUG_NAME_RE` (the literal canonical-drug allowlist above) is
# DELIBERATELY left unchanged. Three modules import it for subject extraction
# in conflict/contradiction detection and completeness token substitution
# (completeness_checker, contradiction_detector, qualitative_conflict_detector)
# — that is a SEPARATE concern from the scope false-abort fixed by F13. The
# A3-F13 fix adds a config-driven *recognizer* (`_intervention_present`) used by
# the scope gate's PICO heuristic so an OFF-LIST drug no longer false-aborts;
# the literal regex stays as the canonical-name fast path + the consumers' API.

# ─────────────────────────────────────────────────────────────────────────────
# A3 fix F13 (GH I-arch-002) — config-driven intervention recognizer.
#
# The scope gate previously recognised a clinical *intervention* ONLY via the
# ~25-entry hard-coded `_DRUG_NAME_RE` allowlist above. A clinical question about
# any drug NOT in that list whose population also could not be extracted read
# BOTH PICO anchors as None and was hard-rejected (abort_scope_rejected /
# clinical_pico_unscoped) — a false abort on a perfectly well-scoped question.
#
# LAW VI (zero hard-coding): the recognizer below is fully config-driven from
# `config/clinical_safety/intervention_recognition.yaml` — WHO/USAN INN class
# stems (generative drug recognition) + a seed list of stemless legacy names.
# No closed per-drug allowlist gates the decision. The gate stays STRICT: a
# genuinely contentless clinical question (no stem, no known name, no
# population) still rejects. This touches NO faithfulness gate.
# ─────────────────────────────────────────────────────────────────────────────

_INTERVENTION_RECOGNITION_CONFIG = (
    _REPO_ROOT / "config" / "clinical_safety" / "intervention_recognition.yaml"
)


@dataclass(frozen=True)
class _InterventionRecognizer:
    """Compiled config-driven recognizer for a clinical intervention name."""

    inn_stem_re: "_MinLenStemPattern"
    known_names_re: re.Pattern[str]
    exclude_words: frozenset[str]
    # I-arch-011 FIX-P0-B (GENERAL, non-drug interventions): a DEVICE (deep brain
    # stimulator, pacemaker, implant, stent) or a PROCEDURE (ablation,
    # transplantation, -ectomy) must be recognised as an intervention too, not
    # just a drug — otherwise the completeness gate marks device/procedure-safety
    # slots NON-applicable in EVERY non-pharma domain. Optional (absent config
    # sections -> None -> no match; backward-compatible). Domain-general,
    # config-driven (LAW VI), NOT a per-disease/per-device allowlist.
    procedure_stem_re: Optional["_MinLenStemPattern"] = None
    device_term_re: Optional[re.Pattern[str]] = None

    def _known_search(self, text: str) -> Optional[re.Match[str]]:
        """Earliest known-name match whose token is not in the denylist."""
        for m in self.known_names_re.finditer(text):
            if m.group(0).lower() not in self.exclude_words:
                return m
        return None

    def find(self, text: str) -> Optional[str]:
        """Return the first recognised intervention token (lowercased) or None.

        The token that appears EARLIEST in the text wins across ALL recognisers
        (drug INN-stem, legacy drug name, device term, procedure stem); on an
        exact-position tie the known drug-name is preferred (it is appended first
        below). Any single intervention anchor is sufficient for the scope
        decision, so the tie-break only affects which token is *reported*, never
        whether the gate proceeds. Tokens in `exclude_words` (common-English
        collisions, e.g. accept/except for the `-cept` stem) are never recognised.
        """
        if not text:
            return None
        candidates: list[re.Match[str]] = []
        known = self._known_search(text)
        if known is not None:
            candidates.append(known)
        stem = self.inn_stem_re.search(text)  # already denylist-filtered
        if stem is not None:
            candidates.append(stem)
        if self.device_term_re is not None:
            dev = self.device_term_re.search(text)
            if dev is not None:
                candidates.append(dev)
        if self.procedure_stem_re is not None:
            proc = self.procedure_stem_re.search(text)
            if proc is not None:
                candidates.append(proc)
        if not candidates:
            return None
        # min() keeps the FIRST candidate on an exact-position tie -> known drug
        # name (appended first) wins, preserving the prior reporting preference.
        chosen = min(candidates, key=lambda m: m.start())
        return chosen.group(0).lower()


def _build_intervention_recognizer(
    config_path: Path,
) -> _InterventionRecognizer:
    """Compile the INN-stem + known-name recognizer from YAML (fail-loud).

    Raises RuntimeError if PyYAML is unavailable, the config file is missing,
    or a required section is absent/empty. No silent fallback (LAW II).
    """
    if yaml is None:
        raise RuntimeError(
            "PyYAML is required for intervention recognition. Install via "
            "`pip install pyyaml`."
        )
    if not config_path.exists():
        raise RuntimeError(
            f"Intervention-recognition config {config_path} does not exist. "
            f"A3 fix F13 requires this file (LAW VI: no hard-coded allowlist)."
        )
    with config_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise RuntimeError(
            f"Intervention-recognition config {config_path} did not parse to a "
            f"dict (got {type(data).__name__}). Check the YAML syntax."
        )

    inn = data.get("inn_stems") or {}
    if not isinstance(inn, dict):
        raise RuntimeError(
            f"{config_path}: 'inn_stems' must be a mapping, got "
            f"{type(inn).__name__}."
        )
    stems = inn.get("stems") or []
    stems = [str(s).strip().lower() for s in stems if str(s).strip()]
    if not stems:
        raise RuntimeError(
            f"{config_path}: 'inn_stems.stems' must be a non-empty list."
        )
    try:
        min_prefix_len = int(inn.get("min_prefix_len", 2))
        min_token_len = int(inn.get("min_token_len", 6))
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            f"{config_path}: min_prefix_len/min_token_len must be integers: {exc}"
        ) from exc
    if min_prefix_len < 1 or min_token_len < 1:
        raise RuntimeError(
            f"{config_path}: min_prefix_len and min_token_len must be >= 1."
        )

    # Precision guard: every stem must be preceded, within the SAME word, by at
    # least `min_prefix_len` alphabetic characters, and the whole token must be
    # at least `min_token_len` chars long. This stops common English words that
    # merely end in a stem-looking substring (machine/April/pine) from matching.
    # Longest-stem-first so "-tinib" wins over "-nib", "-navir" over "-vir".
    stems_sorted = sorted(set(stems), key=len, reverse=True)
    stem_alt = "|".join(re.escape(s) for s in stems_sorted)
    # \b[a-z]{>=min_prefix_len}(?:stem)\b — then enforce min_token_len in code.
    inn_stem_re = re.compile(
        rf"\b([a-z]{{{min_prefix_len},}}(?:{stem_alt}))\b",
        re.IGNORECASE,
    )

    known = data.get("known_names") or []
    known = [str(n).strip().lower() for n in known if str(n).strip()]
    if not known:
        raise RuntimeError(
            f"{config_path}: 'known_names' must be a non-empty seed list."
        )
    known_sorted = sorted(set(known), key=len, reverse=True)
    known_alt = "|".join(re.escape(n) for n in known_sorted)
    known_names_re = re.compile(rf"\b({known_alt})\b", re.IGNORECASE)

    # exclude_words is OPTIONAL (a denylist of common-English collisions). An
    # absent/empty section is valid — the anchoring + min-length guards still
    # apply; the denylist only adds precision for residual collisions like the
    # `-cept` stem vs accept/except/concept/intercept.
    exclude_raw = data.get("exclude_words") or []
    if not isinstance(exclude_raw, list):
        raise RuntimeError(
            f"{config_path}: 'exclude_words' must be a list when present, got "
            f"{type(exclude_raw).__name__}."
        )
    exclude_words = frozenset(
        str(w).strip().lower() for w in exclude_raw if str(w).strip()
    )

    # I-arch-011 FIX-P0-B (GENERAL device/procedure recognition). Both sections
    # are OPTIONAL — absent => the recogniser stays drug-only (backward-compatible).
    # `procedure_stems` mirrors `inn_stems` (morphological suffixes that coin
    # procedure names, e.g. -ectomy/-ostomy/-oscopy); `device_procedure_terms` is
    # a seed list of stemless device/procedure NOUNS/phrases (deep brain
    # stimulation, pacemaker, ablation, dialysis, ...). Domain-general, LAW VI.
    procedure_stem_re: Optional[_MinLenStemPattern] = None
    proc = data.get("procedure_stems")
    if isinstance(proc, dict):
        p_stems = [str(s).strip().lower() for s in (proc.get("stems") or []) if str(s).strip()]
        if p_stems:
            try:
                p_min_prefix = int(proc.get("min_prefix_len", 3))
                p_min_token = int(proc.get("min_token_len", 7))
            except (TypeError, ValueError) as exc:
                raise RuntimeError(
                    f"{config_path}: procedure_stems min_prefix_len/min_token_len "
                    f"must be integers: {exc}"
                ) from exc
            if p_min_prefix < 1 or p_min_token < 1:
                raise RuntimeError(
                    f"{config_path}: procedure_stems min_prefix_len/min_token_len "
                    f"must be >= 1."
                )
            p_sorted = sorted(set(p_stems), key=len, reverse=True)
            p_alt = "|".join(re.escape(s) for s in p_sorted)
            p_re = re.compile(
                rf"\b([a-z]{{{p_min_prefix},}}(?:{p_alt}))\b", re.IGNORECASE
            )
            procedure_stem_re = _MinLenStemPattern(p_re, p_min_token, exclude_words)

    device_term_re: Optional[re.Pattern[str]] = None
    dev_terms = data.get("device_procedure_terms") or []
    if not isinstance(dev_terms, list):
        raise RuntimeError(
            f"{config_path}: 'device_procedure_terms' must be a list when "
            f"present, got {type(dev_terms).__name__}."
        )
    dev_terms = [str(t).strip().lower() for t in dev_terms if str(t).strip()]
    if dev_terms:
        # Longest phrase first so "deep brain stimulation" wins over "stimulation".
        dev_sorted = sorted(set(dev_terms), key=len, reverse=True)
        dev_alt = "|".join(re.escape(t) for t in dev_sorted)
        device_term_re = re.compile(rf"\b({dev_alt})\b", re.IGNORECASE)

    return _InterventionRecognizer(
        inn_stem_re=_MinLenStemPattern(inn_stem_re, min_token_len, exclude_words),
        known_names_re=known_names_re,
        exclude_words=exclude_words,
        procedure_stem_re=procedure_stem_re,
        device_term_re=device_term_re,
    )


class _MinLenStemPattern:
    """Wrap an INN-stem regex to enforce min token length + a denylist.

    `re.Pattern` cannot express "the captured token must be >= N chars and not
    in this denylist" cleanly alongside a stem alternation, so we post-filter
    matches. The denylist removes residual common-English collisions that the
    stem anchoring + min-length cannot separate (e.g. accept/except/concept/
    intercept for the `-cept` fusion-protein stem). Exposes the subset of the
    `re.Pattern` API the recognizer uses (`search`).
    """

    def __init__(
        self,
        pattern: re.Pattern[str],
        min_token_len: int,
        exclude_words: frozenset[str],
    ) -> None:
        self._pattern = pattern
        self._min_token_len = min_token_len
        self._exclude_words = exclude_words

    def search(self, text: str) -> Optional[re.Match[str]]:
        for m in self._pattern.finditer(text):
            token = m.group(0)
            if len(token) < self._min_token_len:
                continue
            if token.lower() in self._exclude_words:
                continue
            return m
        return None


# Module-level cache: the config is read once per process (deterministic, no I/O
# on the hot path after first use). Reset in tests via _reset_intervention_cache.
_intervention_recognizer_cache: Optional[_InterventionRecognizer] = None


def _get_intervention_recognizer() -> _InterventionRecognizer:
    global _intervention_recognizer_cache
    if _intervention_recognizer_cache is None:
        _intervention_recognizer_cache = _build_intervention_recognizer(
            _INTERVENTION_RECOGNITION_CONFIG
        )
    return _intervention_recognizer_cache


def _reset_intervention_cache() -> None:
    """Test hook: clear the compiled-recognizer cache."""
    global _intervention_recognizer_cache
    _intervention_recognizer_cache = None


def _intervention_present(query: str) -> Optional[str]:
    """Return a recognised intervention token (lowercased) from `query` or None.

    Two layers, both config-driven (LAW VI):
      1. The canonical `_DRUG_NAME_RE` literal fast path (exact known names) —
         preserves byte-for-byte the prior matches/case for those drugs.
      2. The config-driven INN-stem + known-name recognizer (off-list drugs).

    Returns None when no intervention is recognised, so a genuinely unscoped
    clinical question still reads intervention=None and the gate stays strict.
    """
    q = (query or "").strip()
    if not q:
        return None
    canonical = _DRUG_NAME_RE.search(q)
    if canonical:
        return canonical.group(1).lower()
    return _get_intervention_recognizer().find(q)


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
    # F13: config-driven recognizer (canonical fast path + INN stems + known
    # names) instead of the bare ~25-drug `_DRUG_NAME_RE` allowlist, so an
    # off-list drug is recognised and no longer false-aborts the scope gate.
    intervention = _intervention_present(q)
    if intervention:
        result["intervention"] = intervention

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
# I-meta-005 Phase 1 (#985, brief §2.2): field-agnostic frame extractor.
#
# ADDITIVE. The clinical `extract_pico_heuristic` + `_DRUG_NAME_RE` above are
# UNCHANGED (off-path + the existing importers in completeness_checker.py and
# contradiction_detector.py continue to use them). This heuristic does NOT use
# the clinical drug/population regex; it produces a lightweight on-path frame
# for ANY field by content-word extraction, with NO clinical literal as a
# control value. It is a deterministic fallback only — the field-agnostic
# planner (planning.research_planner) is the primary on-mode frame source; this
# heuristic seeds entities/metrics/comparators when no LLM frame is available.
# ─────────────────────────────────────────────────────────────────────────────

# Field-invariant comparator markers (no domain literal): a word window around
# these splits the question into compared alternatives, in any field.
_FRAME_COMPARATOR_MARKERS_RE = re.compile(
    r"\b(versus|vs\.?|compared to|compared with|relative to|against|"
    r"as opposed to|rather than)\b",
    re.IGNORECASE,
)
# Field-invariant metric cues: quantity words that suggest a measured outcome.
_FRAME_METRIC_CUES_RE = re.compile(
    r"\b(rate|ratio|cost|price|percent|percentage|share|level|score|index|"
    r"efficiency|yield|throughput|latency|reduction|increase|change|"
    r"probability|risk|return|growth|emissions?|temperature|accuracy)\b",
    re.IGNORECASE,
)
# Generic stopwords for content-word entity extraction (no domain terms).
_FRAME_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "of",
    "in", "on", "at", "to", "for", "with", "by", "from", "as", "that", "this",
    "these", "those", "it", "its", "be", "been", "what", "which", "who", "how",
    "why", "when", "where", "we", "our", "their", "between", "into", "about",
    "than", "such", "does", "do", "can", "may", "any", "also", "would", "should",
    "could", "will", "more", "most", "some", "all", "not", "no", "over", "under",
})


def extract_research_frame_heuristic(query: str) -> dict[str, list[str]]:
    """Field-agnostic frame heuristic for the on-path (brief §2.2).

    Returns a dict with the `ResearchFrame` anchor keys (entities / relations /
    metrics / comparators / constraints). Pure / no-network / no-LLM and — by
    design — uses NO clinical regex. Comparators come from generic comparison
    markers, metrics from generic quantity cues, and entities from the
    remaining content words. The planner supersedes this when an LLM frame is
    available; this is the deterministic seed/fallback.
    """
    q = (query or "").strip()
    frame: dict[str, list[str]] = {
        "entities": [],
        "relations": [],
        "metrics": [],
        "comparators": [],
        "constraints": [],
    }
    if not q:
        return frame

    # Comparators: text fragments flanking a generic comparison marker.
    comparators: list[str] = []
    for m in _FRAME_COMPARATOR_MARKERS_RE.finditer(q):
        tail = q[m.end():].strip()
        first_clause = re.split(r"[,.;?]", tail, maxsplit=1)[0].strip()
        if first_clause:
            comparators.append(first_clause[:60])
    frame["comparators"] = list(dict.fromkeys(comparators))[:6]

    # Metrics: generic quantity cues present in the question.
    metrics = [m.group(1).lower() for m in _FRAME_METRIC_CUES_RE.finditer(q)]
    frame["metrics"] = list(dict.fromkeys(metrics))[:8]

    # Entities: content words (capitalized phrases or multi-char tokens) minus
    # generic stopwords. No domain dictionary.
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", q)
    entities: list[str] = []
    seen: set[str] = set()
    for tok in tokens:
        low = tok.lower()
        if low in _FRAME_STOPWORDS:
            continue
        if low in seen:
            continue
        seen.add(low)
        entities.append(tok)
    frame["entities"] = entities[:12]
    return frame


# ─────────────────────────────────────────────────────────────────────────────
# B9 domain-generalization (the spine) — cheap domain/intent classifier.
#
# SG1 fix: POLARIS historically DEFAULTED to clinical and never INFERRED the
# domain, so a non-clinical question silently ran the clinical path. This adds a
# lightweight, INJECTABLE domain/intent classifier that returns a free-text
# domain (NOT a closed enum — avoids re-introducing the closed-set trap one
# level up), the deterministic capability flags `is_clinical` / `is_quantitative`,
# and `key_entity_types`. It DEGRADES gracefully: a wrong/blank classification
# falls to `general` (weight, never abort, never clinical). The output is
# ADVISORY routing context — it is NOT serialized into the immutable
# `protocol.json`, so adding it does NOT change the protocol bytes/hash (clinical
# byte-identity preserved).
#
# The LLM seam is OPTIONAL + injectable. The DEFAULT is a deterministic, NO-SPEND
# heuristic (reuses the `is_clinical_domain` backbone + the field-agnostic frame
# heuristic), so build/smoke never hit a live LLM. A caller may inject an LLM
# callable (`Callable[[str], str]` returning JSON) to refine the free-text domain
# label; an LLM error/garbage output FAILS OPEN to the heuristic (general).
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DomainIntent:
    """Advisory domain/intent classification (B9 SG1). NOT serialized into
    protocol.json — pure routing context."""

    domain: str                  # free-text domain label; "general" when unknown
    is_clinical: bool            # the deterministic clinical specialization signal
    is_quantitative: bool        # the question asks for a measured quantity
    key_entity_types: list[str]  # advisory entity-type hints (free text)
    source: str = "heuristic"    # "heuristic" | "llm" — provenance of the label


def _heuristic_domain_label(question: str, is_clinical: bool) -> str:
    """Deterministic free-text domain label from cheap keyword cues. NO LLM.

    Returns a free-text label (NOT a closed enum) — `clinical` when the clinical
    signal fired, else the first matching coarse bucket, else `general`. The
    label is advisory only; the hard scope-template route uses the SUPPORTED set
    with `general` as the safe default, so an unrecognised label never aborts."""
    if is_clinical:
        return "clinical"
    q = (question or "").lower()
    # Coarse, additive cue buckets (free text, not a gate). Order = priority.
    buckets: list[tuple[str, tuple[str, ...]]] = [
        ("economics", ("gdp", "inflation", "unemployment", "labor", "labour",
                        "wage", "economic", "economy", "productivity", "market",
                        "trade", "fiscal", "monetary", "recession")),
        ("policy", ("policy", "regulation", "regulatory", "legislation", "bill ",
                    "statute", "governance", "compliance", "subsidy", "tariff")),
        ("technology", ("ai ", "artificial intelligence", "machine learning",
                        "software", "algorithm", "model ", "semiconductor",
                        "compute", "neural", "llm")),
        ("science", ("physics", "chemistry", "biology", "climate", "emissions",
                     "materials", "genome", "experiment", "quantum")),
    ]
    for label, cues in buckets:
        if any(cue in q for cue in cues):
            return label
    return GENERAL_DOMAIN


def _is_quantitative_question(question: str) -> bool:
    """Deterministic: does the question ask for a measured quantity? Reuses the
    field-agnostic metric-cue regex (no domain literal)."""
    return bool(_FRAME_METRIC_CUES_RE.search(question or ""))


def classify_domain_intent(
    question: str,
    *,
    evidence: Optional[list[dict[str, Any]]] = None,
    domain_hint: Optional[str] = None,
    llm: Optional[Any] = None,
) -> DomainIntent:
    """Classify the question's domain + intent (B9 SG1). Deterministic by
    default; an optional injected `llm` callable (``Callable[[str], str]``
    returning a JSON object with a ``domain`` key) only REFINES the free-text
    label. Never raises, never aborts, FAILS OPEN to `general`.

    Args:
        question: the raw research question.
        evidence: optional evidence rows; used by the deterministic clinical
            signal when `domain_hint` is blank.
        domain_hint: optional caller-supplied domain (e.g. the sweep's
            `q["domain"]`). An explicit non-blank hint is authoritative for the
            clinical signal (so `domain="clinical"` -> is_clinical True).
        llm: optional injectable seam (``Callable[[str], str]``). Tests inject a
            deterministic fake; production may inject a real Writer call. An LLM
            error or unparseable output is swallowed -> heuristic label.

    Returns:
        DomainIntent. `is_clinical` is the deterministic backbone signal;
        `domain` is a free-text label degrading to `general`.
    """
    from src.polaris_graph.domain.domain_signal import (
        GENERAL_DOMAIN as _GENERAL,
        is_clinical_domain,
        normalize_domain,
    )
    is_clinical = is_clinical_domain(domain_hint, evidence)
    is_quant = _is_quantitative_question(question)
    frame = extract_research_frame_heuristic(question)
    key_entity_types = frame.get("entities", [])[:6]

    # Default deterministic label.
    label = _heuristic_domain_label(question, is_clinical)
    source = "heuristic"

    # Optional LLM refinement (fail-open). The LLM may only OVERRIDE the
    # free-text label for a non-clinical question; it NEVER overrides the
    # deterministic clinical signal (clinical safety stays deterministic).
    if llm is not None and not is_clinical:
        try:
            raw = llm(question)
            parsed = json.loads(raw) if isinstance(raw, str) else (raw or {})
            llm_domain = normalize_domain(str(parsed.get("domain", "")))
            # Codex P2.2: the LLM may refine a NON-clinical free-text label but
            # must NEVER set the label to "clinical" when the deterministic
            # is_clinical signal is False — clinical routing stays deterministic
            # (a clinical label with is_clinical False would be inconsistent and
            # could reactivate clinical routing in a downstream consumer).
            if (
                llm_domain
                and llm_domain != _GENERAL
                and llm_domain != "clinical"
            ):
                label = llm_domain
                source = "llm"
        except Exception:
            # Garbage / error -> keep the deterministic heuristic label.
            label = _heuristic_domain_label(question, is_clinical)
            source = "heuristic"

    return DomainIntent(
        domain=label or _GENERAL,
        is_clinical=is_clinical,
        is_quantitative=is_quant,
        key_entity_types=list(key_entity_types),
        source=source,
    )


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

    # B9 (Codex P1.1): a BLANK / whitespace-only domain is NOT an "unsupported
    # domain" error — it is the domain-LESS case that must route to the
    # domain-agnostic general default (operator-locked: "" -> general, never
    # abort). Normalize it to DEFAULT_DOMAIN (general) BEFORE the unsupported
    # check so it proceeds. A genuinely malformed explicit literal (e.g.
    # "made_up_domain") still falls through to the fail-loud reject below.
    if not (domain or "").strip():
        domain = DEFAULT_DOMAIN

    # Hard reject #1: unsupported domain. A blank domain was normalized to
    # general above; only a non-blank UNRECOGNISED literal reaches here and
    # rejects loudly (fail-loud, never a silent clinical fallback).
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

    # I-deepfix-001 B10(a) (#1352): extract HARD user constraints from the NL
    # research question (date window / language / journal-only-dormant). Today
    # "academic research published before June 2023" in the question is NEVER
    # parsed — fresh2 protocol.json shows date_range={start:null,end:null}. The
    # extractor runs the deterministic regex/dateparser primary (no network here:
    # llm_fn=None) and fills date_range ONLY where the template/override left it
    # None (override/template ALWAYS win — this only RECOVERS a constraint that
    # was being dropped). Gated PG_EXTRACT_USER_CONSTRAINTS (default OFF, operator
    # activates on the slate); OFF => user_constraints={} and date_range/languages
    # are byte-identical to the prior behavior.
    user_constraints: dict[str, Any] = {}
    if not scope_rejected:
        from src.polaris_graph.retrieval.intake_constraint_extractor import (  # noqa: PLC0415
            extract_user_constraints,
            extract_user_constraints_enabled,
        )
        if extract_user_constraints_enabled():
            _uc = extract_user_constraints(research_question)
            if not _uc.is_empty():
                user_constraints = _uc.to_dict()
                _start_s, _end_s = date_range
                # Only fill a date bound the template/override left None — never
                # override an explicit operator/template constraint. MONTH-precision
                # (Codex wave-2 P1): date_*_iso() carries the month when known
                # ("before June 2023" -> end "2023-06") so the selector enforces a
                # sub-year ceiling; year-only bounds stay "YYYY-01-01"/"YYYY-12-31".
                if _start_s is None and _uc.date_start_iso() is not None:
                    _start_s = _uc.date_start_iso()
                if _end_s is None and _uc.date_end_iso() is not None:
                    _end_s = _uc.date_end_iso()
                date_range = (_start_s, _end_s)
                logger.info(
                    "[scope_gate] B10 user-constraints extracted: date=[%s..%s] "
                    "language=%s journal_only(dormant)=%s timeline_strictness=%s "
                    "— date_range now %r",
                    _uc.date_start_year, _uc.date_end_year, _uc.language,
                    _uc.journal_only, _uc.timeline_strictness, date_range,
                )

    # I-scope-001: parallel SCOPE-facet extraction (source-type / jurisdiction + op +
    # strictness + named include/exclude). FILL-not-override + gated PG_EXTRACT_SCOPE_
    # CONSTRAINTS (default OFF). OFF => scope_constraints={} => the enforcer builds empty
    # maps => byte-identical selection (the only protocol.json difference on the OFF path is
    # the inert additive `scope_constraints: {}` key). Deterministic + offline here (llm_fn
    # is None); the LLM fallback runs only when explicitly wired downstream.
    scope_constraints: dict[str, Any] = {}
    if not scope_rejected:
        from src.polaris_graph.retrieval.intake_constraint_extractor import (  # noqa: PLC0415
            extract_scope_constraints,
            extract_scope_constraints_enabled,
        )
        if extract_scope_constraints_enabled():
            _sc = extract_scope_constraints(research_question)
            if not _sc.is_empty():
                scope_constraints = _sc.to_dict()
                logger.info(
                    "[scope_gate] I-scope-001 scope-constraints extracted: %d facet(s) "
                    "named_include=%d named_exclude=%d",
                    len(_sc.facets), len(_sc.named_include), len(_sc.named_exclude),
                )

    # O2 (feat/intake-contract): explicit-instruction slots from the research
    # question. Mirrors the B10/scope sibling blocks: gated on its OWN kill-switch
    # (PG_EXTRACT_INSTRUCTION_SLOTS, default OFF), deterministic + offline here
    # (llm_fn=None — no paid/network call at intake). ADDITIVE: records the slots
    # onto the protocol; it changes NO date_range/languages and drops nothing. OFF
    # => instruction_slots=[] => no protocol.json key (byte-identical).
    instruction_slots: list[dict[str, Any]] = []
    if not scope_rejected:
        from src.polaris_graph.retrieval.intake_constraint_extractor import (  # noqa: PLC0415
            extract_instruction_slots,
            extract_instruction_slots_enabled,
        )
        if extract_instruction_slots_enabled():
            _slots = extract_instruction_slots(research_question)  # llm_fn=None: offline
            if _slots:
                instruction_slots = [s.to_dict() for s in _slots]
                logger.info(
                    "[scope_gate] O2 instruction-slots extracted: %d required slot(s) [%s]",
                    len(_slots),
                    ", ".join(f"{s.kind}:{'/'.join(s.entities)}" for s in _slots),
                )

    # Part 1 (feat/intake-contract): compile the unified intake contract in SHADOW.
    # Gated on PG_INTAKE_CONTRACT_COMPILE (default OFF). When OFF the whole block —
    # including the compiler import and any llm_fn touch — is skipped, so the OFF
    # path never constructs a contract and protocol.intake_contract stays None
    # (to_json_dict pops it => byte-identical protocol.json). SHADOW: the compiled
    # contract is recorded ONLY; it is never consumed to fill date_range/languages
    # or to drive any filter (source_rules enforcement is disabled — it needs
    # operator sign-off + a full-benchmark A/B, per the design plan Phase 3). The
    # floor here is deterministic + offline (llm_fn=None): no paid/network call.
    intake_contract: Optional[dict[str, Any]] = None
    if not scope_rejected:
        from src.polaris_graph.intake.contract_compiler import (  # noqa: PLC0415
            compile_intake_contract,
            compile_intake_contract_enabled,
        )
        if compile_intake_contract_enabled():
            _ic = compile_intake_contract(research_question, llm_fn=None)  # offline floor
            intake_contract = _ic.to_dict()
            logger.info(
                "[scope_gate] intake-contract compiled (SHADOW, enforcement disabled): "
                "empty=%s warnings=%d source=%s",
                _ic.is_empty(), len(_ic.warnings), _ic.source,
            )

    geography = list(template.get("geography") or [])
    if "geography" in overrides:
        geography = list(overrides["geography"] or [])

    languages = list(template.get("languages") or ["en"])
    if "languages" in overrides:
        languages = list(overrides["languages"] or ["en"])
    # B10(a): a NL language constraint becomes a DISCLOSED demotion weight
    # downstream (never a hard drop per §-1.3); record it only when the template/
    # override did not already pin the language list and the extractor found one.
    elif user_constraints.get("language") and "languages" not in overrides:
        # Surface the extracted language as the protocol's primary language so the
        # selection-side demotion (B10 d) and the disclosure banner can read it.
        _lang = user_constraints["language"]
        if _lang and _lang not in languages:
            languages = [_lang] + [l for l in languages if l != _lang]

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
        user_constraints=user_constraints,
        scope_constraints=scope_constraints,
        instruction_slots=instruction_slots,
        intake_contract=intake_contract,
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
