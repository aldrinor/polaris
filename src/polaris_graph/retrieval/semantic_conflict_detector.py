"""Semantic/NLI cross-document contradiction detector (I-ready-012 / #1079).

The THIRD contradiction detector, complementing the numeric-regex detector
(``contradiction_detector``) and the NegEx/ConText rule-cue qualitative detector
(``qualitative_conflict_detector``). Those two cap detection recall at the rule
layer: a genuine prose-only directional contradiction with NO shared number and
NO lexicon cue — e.g. "adjuvant chemotherapy improved overall survival" vs
"...provided no overall survival benefit" — passes both silently. In a clinical
report that is the lethal-miss class (F12).

This module adds an LLM-NLI pass that:
  1. clusters evidence rows by shared SALIENT content words computed from the raw
     row text (``cluster_candidate_rows``) — RECALL-oriented, independent of the
     rule extractors (which are blind to the no-number/no-cue rows). The cheap
     pre-filter bounds the O(n^2) judge cost; the judge provides precision.
  2. emits same-cluster row pairs (``extract_pairs``), hard-capped, highest-tier
     first.
  3. judges each pair (claim A vs claim B -> contradict/entail/neutral) and keeps
     ``contradict`` pairs above a confidence threshold (``detect_semantic_conflicts``).

Design invariants:
  * ADDITIVE + fail-open: a detector / judge / import / budget error logs and
    skips; it NEVER aborts the sweep and NEVER weakens an existing gate. It can
    only ADD disclosures and (via PT08) make the release gate stricter.
  * Default OFF (``PG_SWEEP_NLI_CONFLICT``): flag-off is byte-identical — no judge
    is constructed and no network call is made.
  * The judge is INJECTED (a ``(claim_a, claim_b) -> (label, confidence)``
    callable), so the detector is fully offline-testable with a fake. The
    production judge (``get_default_judge``) reuses the family-segregated,
    cost-ledgered OpenRouter substrate (``PG_ENTAILMENT_MODEL``, Gemma-4-31B by
    default) — the same two-family evaluator the strict_verify entailment judge
    uses — with a CONTRADICTION prompt. The strict_verify entailment path is NOT
    modified.

Records are shaped (``SemanticConflictRecord``) so the existing ``contradictions.json``
merge consumes them, and they are routed by the caller into a dedicated report
disclosure block + the PT08 evaluator input (the numeric renderer is untouched).
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import time
from dataclasses import asdict, dataclass, field

logger = logging.getLogger(__name__)

# --- configuration (LAW VI: all knobs are env-overridable) -------------------
_FLAG = "PG_SWEEP_NLI_CONFLICT"
_OFF_VALUES = frozenset({"", "0", "false", "off", "no"})

_ENV_MIN_OVERLAP = "PG_SWEEP_NLI_CONFLICT_MIN_OVERLAP"      # default 2 shared salient words
_ENV_MAX_PAIRS = "PG_SWEEP_NLI_CONFLICT_MAX_PAIRS"          # default 60 judged pairs
_ENV_MAX_ROWS = "PG_SWEEP_NLI_CONFLICT_MAX_ROWS"            # default 200 rows clustered
_ENV_MIN_CONFIDENCE = "PG_SWEEP_NLI_CONFLICT_MIN_CONFIDENCE"  # default 0.7

_DEFAULT_MIN_OVERLAP = 2
_DEFAULT_MAX_PAIRS = 60
_DEFAULT_MAX_ROWS = 200
_DEFAULT_MIN_CONFIDENCE = 0.7

# I-arch-002 (operator 2026-06-13): default to the sovereign open-weight evaluator GLM-5.1 (was the stale
# non-reasoning "google/gemma-4-31b-it" leftover — #1249/#1252; only env PG_ENTAILMENT_MODEL had masked it).
_DEFAULT_ENTAILMENT_MODEL = "z-ai/glm-5.1"
_JUDGE_TIMEOUT_S = 30.0
# I-arch-006 HANG-J1 sibling (#1262): the semantic-conflict judge had the SAME bare-float per-read gap
# timeout that let a trickled / idle-open OpenRouter socket run UNBOUNDED. Tight read-stall (dead socket
# trips fast; keep-alives reset the timer so a slow-but-alive judge is unaffected) + bounded keepalive to
# reap half-open CLOSE_WAIT sockets. Transport-only — the fail-open ("neutral", 0.0) verdict logic that
# prevents a transient outage from FABRICATING a conflict is UNCHANGED. (LAW VI: env-driven.)
_JUDGE_CONNECT_S = float(os.getenv("PG_NLI_CONFLICT_CONNECT_S", "30"))
_JUDGE_READ_STALL_S = float(os.getenv("PG_NLI_CONFLICT_READ_STALL_S", "120"))
_JUDGE_WRITE_S = float(os.getenv("PG_NLI_CONFLICT_WRITE_S", "60"))
_JUDGE_POOL_S = float(os.getenv("PG_NLI_CONFLICT_POOL_S", "30"))
_JUDGE_MAX_KEEPALIVE = int(os.getenv("PG_NLI_CONFLICT_MAX_KEEPALIVE", "8"))
_JUDGE_KEEPALIVE_EXPIRY_S = float(os.getenv("PG_NLI_CONFLICT_KEEPALIVE_EXPIRY_S", "30"))

# I-arch-004 F19 (#1256, §9.1.8 "max_tokens ALWAYS go to the model REAL max — never starve; a generous cap is
# free, billed by usage not pre-allocated"): the NLI conflict judge is the SAME GLM-5.1 model pinned to the
# SAME LOCKED mirror provider chain (`get_role_provider("mirror")`, allow_fallbacks=False — see judge() below)
# as the main Mirror role, so its binding output cap is the SAME chain MIN the Mirror transport derived from a
# LIVE OpenRouter read 2026-06-14 (openrouter_role_transport.py:295, `_MIRROR_MAX_TOKENS_CHAIN_MIN`): mirror
# chain order=[atlas-cloud, z-ai, baidu, novita, gmicloud] -> MIN max_completion_tokens 131072. A budget ABOVE
# 131072 would hard-400 on the z-ai/baidu/novita fallbacks under allow_fallbacks=False; so the default IS the
# chain MIN (the model REAL max for this pinned chain), env-overridable but CLAMPED DOWN to that ceiling. The
# old 2000 was the SMALL hardcode §9.1.8 prohibits — one provider hiccup from a finish=length truncation that
# returns the fail-open ('neutral', 0.0) and SILENTLY MISSES a real cross-document contradiction (the F19
# starvation class). Effort stays "high" (NOT xhigh): the Mirror GLM bake-off
# (openrouter_role_transport.py:700-705, mirror_glm_provider_bakeoff.py, 2026-06-14) proved xhigh is a NO-OP on
# GLM that lets reasoning eat the whole budget -> blank content -> the very collapse F19 closes. Kept as a
# LOCAL constant (NOT imported from roles) so this leaf retrieval module stays import-light. RE-DERIVE if the
# mirror chain is re-pinned in config/settings/openrouter_provider_routing.yaml to higher-cap-only providers.
_CONFLICT_MAX_TOKENS_CHAIN_MIN = 131072
_DEFAULT_CONFLICT_MAX_TOKENS = _CONFLICT_MAX_TOKENS_CHAIN_MIN

# Small, domain-aware stopword set. Salient-word overlap (NOT all words) keys the
# clustering, so generic connectives never group unrelated rows.
_STOPWORDS = frozenset({
    "the", "and", "for", "with", "was", "were", "has", "have", "had", "are", "but",
    "not", "from", "that", "this", "these", "those", "their", "its", "than", "then",
    "into", "onto", "over", "under", "between", "within", "without", "during", "after",
    "before", "while", "which", "when", "where", "what", "who", "whom", "how", "why",
    "study", "trial", "patients", "patient", "group", "groups", "results", "result",
    "showed", "shown", "found", "reported", "compared", "versus", "vs", "among",
    "using", "based", "data", "analysis", "associated", "may", "can", "also", "both",
    "more", "most", "less", "high", "low", "higher", "lower", "year", "years",
})

# Tier ordering: highest-evidence pairs judged first (so the pair cap keeps the
# most decision-relevant conflicts). Unknown tiers sort last.
_TIER_RANK = {"T1": 0, "gold": 0, "T2": 1, "T3": 2, "T4": 3, "T5": 4, "T6": 5, "T7": 6}


@dataclass
class SemanticConflictRecord:
    """A cross-document semantic contradiction (type discriminator: ``semantic``).

    Shaped for: (a) the merged ``contradictions.json`` dump; (b) the dedicated
    report disclosure block (subject + predicate + the two conflicting claims);
    (c) the PT08 evaluator gate (substring(subject) + substring(predicate) in
    report text). ``claims`` always has length 2 — the two conflicting sources.
    """

    subject: str
    predicate: str
    claims: list = field(default_factory=list)  # [{evidence_id, text, tier, nli_label}, ...] (len 2)
    type: str = "semantic"
    severity: str = "review"
    nli_confidence: float = 0.0


# I-arch-005 B13 (#1257): the conflict side-judge's EMPTY-CONTENT collapse (a reasoning
# model returns a 200 with empty/None content) used to raise → the caller HELD the report.
# Operator-locked 2026-06-14 ("nothing shall hold the report"): on PERSISTENT empty (after
# the B14 retry) the unadjudicated pair is LABELED ``conflict_unscored`` and the run SHIPS.
# This is a DISCLOSED GAP, never an assertion: the judge could NOT adjudicate this pair — it
# does NOT say "no conflict" and it does NOT fabricate one. The faithfulness contract is
# unchanged; this only converts a HOLD into a disclosed label.
#
# The sentinel label the production judge returns when content stays empty after the B14
# retry. ``detect_semantic_conflicts`` recognizes it and emits a ``ConflictUnscoredRecord``
# (a disclosed-gap label) instead of skipping silently or raising.
CONFLICT_UNSCORED_LABEL = "unscored"


@dataclass
class ConflictUnscoredRecord:
    """A cross-document evidence PAIR the NLI conflict judge could NOT adjudicate.

    Emitted (alongside the ``contradict`` records) when the side judge returns persistent
    empty content for the pair after the B14 retry. It is a DISCLOSED GAP, not a finding:
    it asserts nothing about whether the two claims conflict — only that the judge could not
    decide. The run-side glue (SWEEP lane) routes these into the disclosed-gaps artifact so
    the report ships with the gap surfaced rather than HELD. ``severity`` is fixed to the
    label so a consumer never mistakes it for a real ``review`` contradiction.
    """

    subject: str
    evidence_ids: list = field(default_factory=list)  # the two pair members' evidence_ids
    reason: str = "conflict_judge_unavailable: empty judge content (could not adjudicate)"
    type: str = "conflict_unscored"
    severity: str = "unscored"


class ConflictJudgeUnavailableError(RuntimeError):
    """I-arch-004 F07 (#1249/#1252): the cross-document NLI conflict judge ERRORED while the
    strict-gate benchmark slate is active. Under strict gates a judge error must FAIL CLOSED
    — the run HOLDS for human review (the caller maps this to a run-level hold status) instead
    of the detector's additive fail-open silently dropping a POSSIBLE real contradiction as
    ('neutral', 0.0). This carries NO fabricated conflict: it signals "could not adjudicate",
    never "a conflict exists" — fabricating a phantom SemanticConflictRecord would itself be a
    faithfulness bug (and a false PT08 abort). Default (non-strict) path NEVER raises this."""


def semantic_conflict_enabled() -> bool:
    """True unless ``PG_SWEEP_NLI_CONFLICT`` is unset/falsey. Default OFF — flag-off
    is byte-identical (no judge constructed, no network)."""
    return os.environ.get(_FLAG, "").strip().lower() not in _OFF_VALUES


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default


def _row_text(row: dict) -> str:
    return str(row.get("direct_quote") or row.get("statement") or row.get("text") or "")


def _content_words(text: str) -> set:
    """Salient (>=3 char, non-stopword) lowercase tokens for overlap keying."""
    return {
        t for t in re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(t) >= 3 and t not in _STOPWORDS
    }


def _tier_rank(row: dict) -> int:
    return _TIER_RANK.get(str(row.get("tier") or ""), 99)


def cluster_candidate_rows(evidence_rows, *, min_overlap: int | None = None,
                           max_rows: int | None = None) -> list:
    """Group rows that share >= ``min_overlap`` salient content words (connected
    components). RECALL-oriented pre-filter, independent of the rule extractors.

    Bounded: only the top ``max_rows`` rows (highest tier first) are clustered, so
    the O(n^2) comparison is capped at full scale. Returns a list of clusters
    (each a list of the original row dicts); singletons are dropped.
    """
    min_overlap = _DEFAULT_MIN_OVERLAP if min_overlap is None else min_overlap
    max_rows = _DEFAULT_MAX_ROWS if max_rows is None else max_rows

    rows = [r for r in (evidence_rows or []) if _row_text(r).strip()]
    rows = sorted(rows, key=_tier_rank)[:max_rows]
    words = [_content_words(_row_text(r)) for r in rows]

    n = len(rows)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(n):
        if not words[i]:
            continue
        for j in range(i + 1, n):
            if len(words[i] & words[j]) >= min_overlap:
                union(i, j)

    groups: dict = {}
    for idx in range(n):
        groups.setdefault(find(idx), []).append(rows[idx])
    return [g for g in groups.values() if len(g) >= 2]


def extract_pairs(clusters, *, max_pairs: int | None = None) -> list:
    """Same-cluster row pairs, highest-tier first, hard-capped at ``max_pairs``."""
    max_pairs = _DEFAULT_MAX_PAIRS if max_pairs is None else max_pairs
    pairs: list = []
    for cluster in clusters:
        ordered = sorted(cluster, key=_tier_rank)
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                pairs.append((ordered[i], ordered[j]))
    # Rank pairs by best tier in the pair so the cap keeps the strongest evidence.
    pairs.sort(key=lambda p: (_tier_rank(p[0]) + _tier_rank(p[1])))
    return pairs[:max_pairs]


def _shared_subject(row_a: dict, row_b: dict) -> str:
    """Top shared salient words → a stable subject phrase (for PT08 + disclosure)."""
    shared = _content_words(_row_text(row_a)) & _content_words(_row_text(row_b))
    # Preserve appearance order in row A for readability.
    ordered = [w for w in re.findall(r"[a-z0-9]+", _row_text(row_a).lower()) if w in shared]
    seen: set = set()
    uniq = [w for w in ordered if not (w in seen or seen.add(w))]
    return " ".join(uniq[:4]) if uniq else "cross-document claim"


def detect_semantic_conflicts(
    pairs, judge, *, min_confidence: float | None = None,
    strict_fail_closed: bool = False,
    unscored_out: list | None = None,
) -> list:
    """Judge each pair; keep ``contradict`` pairs above ``min_confidence``.

    ``judge`` is a ``(claim_a, claim_b) -> (label, confidence)`` callable, label in
    {"contradict","entail","neutral"}. Fail-open (default):
      * a per-pair judge error skips THAT pair (never fabricates a conflict);
      * a ``BudgetExceededError`` stops judging, KEEPS records found so far, and
        propagates as a clean stop signal (caught by the caller's fail-open block)
        — it never aborts mid-record.

    I-arch-004 F07 (#1249/#1252) — ``strict_fail_closed`` (the strict-gate benchmark
    slate): a per-pair judge error must NOT silently skip (that could drop a real
    contradiction). Instead RAISE ``ConflictJudgeUnavailableError`` so the caller HOLDS
    the run for human review. This signals "could not adjudicate", NOT "a conflict
    exists" — no phantom record is ever fabricated. ``BudgetExceededError`` still
    propagates to keep-partial regardless of the flag (it is a clean stop, not an
    unadjudicated pair).

    I-arch-005 B13 (#1257) — ``unscored_out`` (optional collector, operator-locked
    2026-06-14 "nothing shall hold the report"): the production judge returns the
    ``CONFLICT_UNSCORED_LABEL`` when its content stayed EMPTY after the B14 retry (the
    GLM reasoning-model collapse). When ``unscored_out`` is provided, that pair is appended
    as a ``ConflictUnscoredRecord`` (a DISCLOSED GAP — never a fabricated conflict, never a
    dropped one) and the loop CONTINUES. When ``unscored_out`` is None the unscored label is
    simply skipped (byte-identical to the pre-B13 "not contradict -> skip" path). This
    converts the empty-content HOLD into a label and is INDEPENDENT of ``strict_fail_closed``
    (an empty judge is always a label, never a hold).
    """
    from src.polaris_graph.llm.openrouter_client import BudgetExceededError

    min_confidence = _DEFAULT_MIN_CONFIDENCE if min_confidence is None else min_confidence
    records: list = []
    for row_a, row_b in pairs:
        text_a, text_b = _row_text(row_a), _row_text(row_b)
        try:
            label, confidence = judge(text_a, text_b)
        except BudgetExceededError:
            logger.warning(
                "[semantic-conflict] budget exceeded after %d record(s); "
                "stopping judge calls (fail-open, keep-partial).", len(records),
            )
            break
        except Exception as exc:  # noqa: BLE001 — per-pair fail-open; never fabricate a conflict
            if strict_fail_closed:
                # I-arch-004 F07: under strict gates, an unadjudicable pair FAILS CLOSED ->
                # the caller holds the run for review (no silent drop, no fabricated conflict).
                raise ConflictJudgeUnavailableError(
                    f"conflict judge errored on an evidence pair under strict gates: {exc}"
                ) from exc
            logger.warning("[semantic-conflict] judge error on a pair (skipped): %s", exc)
            continue
        # I-arch-005 B13: the EMPTY-CONTENT collapse arrives here as CONFLICT_UNSCORED_LABEL
        # (the B14 guard already retried and returned a sentinel rather than raising). LABEL
        # the pair conflict_unscored (disclosed gap) and continue — never hold, never drop a
        # real conflict (none was adjudicated), never fabricate one.
        if str(label).strip().lower() == CONFLICT_UNSCORED_LABEL:
            if unscored_out is not None:
                unscored_out.append(ConflictUnscoredRecord(
                    subject=_shared_subject(row_a, row_b),
                    evidence_ids=[
                        str(row_a.get("evidence_id") or ""),
                        str(row_b.get("evidence_id") or ""),
                    ],
                ))
            continue
        if str(label).strip().lower() != "contradict":
            continue
        try:
            conf = float(confidence)
        except (TypeError, ValueError):
            conf = 0.0
        # Codex diff-gate P2: reject non-finite / out-of-range confidence. A NaN/inf from a
        # malformed judge response must NOT pass the threshold and fabricate a phantom conflict
        # — a phantom contradiction would falsely abort a legitimate run via PT08. (NaN < x is
        # False, so a bare `conf < min_confidence` would let NaN slip through; guard explicitly.)
        if not math.isfinite(conf) or not (0.0 <= conf <= 1.0):
            logger.warning("[semantic-conflict] dropping pair with non-finite/out-of-range "
                           "confidence %r (fail-safe, never fabricate a conflict)", confidence)
            continue
        if conf < min_confidence:
            continue
        subject = _shared_subject(row_a, row_b)
        predicate = "cross-document directional disagreement"
        # Each claim carries evidence_id + predicate + a finite value (0.0) so a
        # contradictions.json holding a semantic record stays loadable by
        # audit_ir.loader._parse_contradiction_claim (which REQUIRES those three keys
        # and does float(value)). Semantic conflicts are prose-only — there is no
        # numeric value — so value is the finite sentinel 0.0; the `type:"semantic"`
        # discriminator + `nli_label` distinguish them from numeric records downstream.
        records.append(SemanticConflictRecord(
            subject=subject,
            predicate=predicate,
            claims=[
                {"evidence_id": str(row_a.get("evidence_id") or ""), "predicate": predicate,
                 "value": 0.0, "text": text_a, "tier": str(row_a.get("tier") or ""),
                 "nli_label": "contradict"},
                {"evidence_id": str(row_b.get("evidence_id") or ""), "predicate": predicate,
                 "value": 0.0, "text": text_b, "tier": str(row_b.get("tier") or ""),
                 "nli_label": "contradict"},
            ],
            nli_confidence=conf,
        ))
    return records


def detect_semantic_conflicts_for_rows(
    evidence_rows, judge=None, *, strict_fail_closed: bool = False,
) -> list:
    """End-to-end convenience: cluster -> pairs -> judge. Used by the sweep block.

    If ``judge`` is None the production default judge is lazily constructed
    (``get_default_judge``). Returns ``list[SemanticConflictRecord]``.

    I-arch-004 F07 (#1249/#1252): ``strict_fail_closed`` (the strict-gate benchmark
    slate) makes the default production judge RAISE on a transport/parse error rather
    than return its additive fail-open ('neutral', 0.0), and makes the pair loop RAISE
    ``ConflictJudgeUnavailableError`` so the caller HOLDS the run (never a silent drop,
    never a fabricated conflict). Default False => byte-identical additive fail-open.
    """
    clusters = cluster_candidate_rows(
        evidence_rows,
        min_overlap=_int_env(_ENV_MIN_OVERLAP, _DEFAULT_MIN_OVERLAP),
        max_rows=_int_env(_ENV_MAX_ROWS, _DEFAULT_MAX_ROWS),
    )
    if not clusters:
        return []
    pairs = extract_pairs(clusters, max_pairs=_int_env(_ENV_MAX_PAIRS, _DEFAULT_MAX_PAIRS))
    if not pairs:
        return []
    if judge is None:
        judge = get_default_judge(strict_fail_closed=strict_fail_closed)
    return detect_semantic_conflicts(
        pairs, judge,
        min_confidence=_float_env(_ENV_MIN_CONFIDENCE, _DEFAULT_MIN_CONFIDENCE),
        strict_fail_closed=strict_fail_closed,
    )


def detect_semantic_conflicts_for_rows_with_unscored(
    evidence_rows, judge=None, *, strict_fail_closed: bool = False,
) -> tuple:
    """I-arch-005 B13 (#1257): cluster -> pairs -> judge, returning BOTH the contradict
    records AND the ``conflict_unscored`` disclosed-gap labels.

    Returns ``(list[SemanticConflictRecord], list[ConflictUnscoredRecord])``. The unscored
    list carries the pairs whose judge content stayed EMPTY after the B14 retry — a DISCLOSED
    GAP the run-side glue (SWEEP lane) routes into the disclosed-gaps artifact so the report
    SHIPS rather than HELD. Identical clustering/pairing/threshold logic as
    ``detect_semantic_conflicts_for_rows``; the ONLY difference is it threads the
    ``unscored_out`` collector through so the empty-content label is surfaced rather than
    silently skipped. The legacy ``detect_semantic_conflicts_for_rows`` stays byte-identical
    (no collector) so its existing caller is untouched until SWEEP opts into this entry point.
    """
    clusters = cluster_candidate_rows(
        evidence_rows,
        min_overlap=_int_env(_ENV_MIN_OVERLAP, _DEFAULT_MIN_OVERLAP),
        max_rows=_int_env(_ENV_MAX_ROWS, _DEFAULT_MAX_ROWS),
    )
    if not clusters:
        return [], []
    pairs = extract_pairs(clusters, max_pairs=_int_env(_ENV_MAX_PAIRS, _DEFAULT_MAX_PAIRS))
    if not pairs:
        return [], []
    if judge is None:
        judge = get_default_judge(strict_fail_closed=strict_fail_closed)
    unscored: list = []
    records = detect_semantic_conflicts(
        pairs, judge,
        min_confidence=_float_env(_ENV_MIN_CONFIDENCE, _DEFAULT_MIN_CONFIDENCE),
        strict_fail_closed=strict_fail_closed,
        unscored_out=unscored,
    )
    return records, unscored


# --- production judge (isolated; reuses the openrouter cost/family substrate) ---

_CONTRADICTION_PROMPT = """You are a strict cross-document contradiction judge. You are given two independent CLAIMS, each from a different source document, about a related subject. Decide their logical relation.

Rules:
- CONTRADICT: the two claims cannot both be true for the same population/endpoint — one asserts something the other explicitly denies or reverses (e.g. "improved overall survival" vs "no overall survival benefit"; "first-line therapy" vs "reserved for refractory cases").
- ENTAIL: the claims agree, or one restates / refines the other.
- NEUTRAL: the claims are about different things, or could both be true (different populations, endpoints, doses, or time points), or there is not enough overlap to judge a conflict.

Be conservative: only answer CONTRADICT when the disagreement is direct and on the same subject. Return STRICT JSON only, no prose:
{{"verdict": "CONTRADICT" | "ENTAIL" | "NEUTRAL", "confidence": <number 0.0-1.0>}}

CLAIM A:
{claim_a}

CLAIM B:
{claim_b}

JSON:"""


class _SemanticContradictionJudge:
    """Synchronous httpx wrapper around a cross-document contradiction call.

    Mirrors ``llm.entailment_judge._EntailmentJudge`` (same two-family evaluator
    model, the same ``openrouter_client`` cost/budget helpers, family segregation
    enforced at construction) but with a CONTRADICTION prompt and a (label,
    confidence) return. Kept SEPARATE from ``_EntailmentJudge`` so the
    faithfulness-critical strict_verify entailment path is never touched.
    """

    def __init__(self, *, strict_fail_closed: bool = False) -> None:
        import httpx

        from src.polaris_graph.llm.openrouter_client import check_family_segregation

        # I-arch-004 F07 (#1249/#1252): under the strict-gate benchmark slate, a
        # transport/parse error must RAISE (caller holds the run) instead of returning the
        # additive fail-open ('neutral', 0.0) that silently drops a possible real conflict.
        self._strict_fail_closed = bool(strict_fail_closed)
        api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("PG_SWEEP_NLI_CONFLICT requires OPENROUTER_API_KEY")
        self._api_key = api_key
        base_url = os.environ.get(
            "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
        ).rstrip("/")
        self._endpoint = f"{base_url}/chat/completions"
        self._model = os.environ.get("PG_ENTAILMENT_MODEL", _DEFAULT_ENTAILMENT_MODEL)
        # Two-family invariant (§9.1.1): the conflict judge is an evaluator-family
        # call and MUST differ from the generator family — raises at construction.
        check_family_segregation(evaluator_model=self._model)
        # I-arch-006 HANG-J1 sibling (#1262): explicit tight read-stall + bounded keepalive (see the
        # constant block above) replaces the bare-float per-read 30s gap that let a trickled judge POST
        # run unbounded. Verdict logic unchanged.
        self._client = httpx.Client(
            timeout=httpx.Timeout(
                connect=_JUDGE_CONNECT_S,
                read=_JUDGE_READ_STALL_S,
                write=_JUDGE_WRITE_S,
                pool=_JUDGE_POOL_S,
            ),
            limits=httpx.Limits(
                max_keepalive_connections=_JUDGE_MAX_KEEPALIVE,
                keepalive_expiry=_JUDGE_KEEPALIVE_EXPIRY_S,
            ),
        )

    def judge(self, claim_a: str, claim_b: str) -> tuple:
        """Return ``(label, confidence)`` with label in {contradict,entail,neutral}.

        Fail-open on API/parse error → ("neutral", 0.0) so a transient outage never
        FABRICATES a conflict. ``BudgetExceededError`` is re-raised (the caller
        stops + keeps partial) — never masked as a neutral result.
        """
        from src.polaris_graph.llm import openrouter_client as _orc

        prompt = _CONTRADICTION_PROMPT.format(claim_a=claim_a, claim_b=claim_b)
        # I-arch-002 (#1251 sibling): GLM-5.1 is a REASONING model; at max_tokens=60 it truncated mid-
        # reasoning -> EMPTY content -> json.loads(None) NoneType -> fail-open neutral (silently misses real
        # conflicts). Operator 2026-06-13: reasoning stays MAX. Un-starve so high-effort reasoning completes
        # AND emits the JSON verdict; any sub-max/off effort is coerced UP to high. Env-overridable (LAW VI).
        _sc_effort = (os.environ.get("PG_SEMANTIC_CONFLICT_REASONING_EFFORT", "").strip().lower()
                      or "high")
        if _sc_effort not in ("high", "xhigh"):
            _sc_effort = "high"
        # I-arch-004 F19 (§9.1.8): default to the GLM-5.1 mirror-chain MIN (model REAL max for the pinned
        # chain), env-overridable but CLAMPED DOWN to that ceiling so a bad override can never hard-400 the
        # judge under allow_fallbacks=False (the old hardcoded 2000 was the starvation-class small cap).
        try:
            _sc_maxtok = max(256, int(os.environ.get("PG_SEMANTIC_CONFLICT_MAX_TOKENS", _DEFAULT_CONFLICT_MAX_TOKENS)
                                      or _DEFAULT_CONFLICT_MAX_TOKENS))
        except (TypeError, ValueError):
            _sc_maxtok = _DEFAULT_CONFLICT_MAX_TOKENS
        _sc_maxtok = min(_sc_maxtok, _CONFLICT_MAX_TOKENS_CHAIN_MIN)
        json_body: dict = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": _sc_maxtok,
            "reasoning": {"effort": _sc_effort},
            "response_format": {"type": "json_object"},
        }
        # I-arch-004 F09: route via "mirror" (the LOCKED 4-role key), NOT the RETIRED "evaluator"
        # key. The preflight-resolved role_provider_map only carries generator/mirror/sentinel/judge
        # (pathB_runner._LOCKED_ROLES); the legacy "evaluator" key is absent, so get_role_provider(
        # "evaluator") returned None -> NO provider pin -> this NLI conflict judge FREE-ROUTED to an
        # unpinned provider instead of the locked mirror chain. Per polaris_runtime_lock.yaml:
        # legacy_compat the retired evaluator role maps_to_role: mirror (GLM-5.1), so the side-judge
        # pins to the SAME provider chain as the main mirror role (allow_fallbacks=False,
        # require_parameters=True).
        try:
            from src.polaris_graph.benchmark import pathB_capture as _pathb_for_routing
            _gate_provider = _pathb_for_routing.get_role_provider("mirror")
        except Exception:
            _gate_provider = None
        # I-arch-002 (#1250): operator-directed — skip the single-provider pin when
        # PG_ROLE_ALLOW_FALLBACKS is set so the open-weight evaluator model free-routes to its
        # fastest provider (the model is the sovereign unit; hosting provider may be US/China).
        _free_route = os.environ.get("PG_ROLE_ALLOW_FALLBACKS", "").strip().lower() in (
            "1", "true", "yes", "on",
        )
        if _gate_provider and not _free_route:
            json_body["provider"] = {
                "order": [_gate_provider],
                "allow_fallbacks": False,
                "require_parameters": True,
            }
        def _emit_raw_io(status: str, raw_response) -> None:
            # I-obs-001 #1141 AC3 (gate iter-1 P1): ONE raw-IO record per call tagged by its TRUE
            # outcome — "ok" only after a parsed verdict; "judge_error" on parse-failure / fail-open.
            try:
                _io_sink = _orc.current_raw_io_sink()
                if _io_sink is None:
                    return
                import uuid as _uuid
                _io_sink.record(
                    call_id=_uuid.uuid4().hex, call_type="nli_conflict_judge", role="evaluator",
                    request={**json_body, "messages": [{"role": "user", "content": prompt}]},
                    raw_response=raw_response, duration_ms=None, status=status,
                )
            except Exception:  # noqa: BLE001
                pass

        from src.polaris_graph.llm.openrouter_client import BudgetExceededError

        def _post_once() -> dict:
            """ONE real POST + cost-ledger + budget check. Returns the raw provider JSON.

            Billed per ACTUAL call (each B14 retry that re-invokes this is a real call), so
            the cost ledger stays honest. ``BudgetExceededError`` propagates unchanged (the
            B14 guard re-raises it via ``propagate``) so the caller's keep-partial fires."""
            response = self._client.post(
                self._endpoint,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=json_body,
            )
            response.raise_for_status()
            served = response.json()
            usage = served.get("usage", {}) or {}
            input_tokens = int(usage.get("prompt_tokens", 0) or 0)
            output_tokens = int(usage.get("completion_tokens", 0) or 0)
            api_cost = float(usage.get("cost", 0) or 0)
            actual_cost = api_cost or _orc._impute_cost_from_tokens(
                self._model, input_tokens, output_tokens, 0,
            )
            if actual_cost == 0 and not usage:
                actual_cost = _orc._impute_cost_from_tokens(self._model, 400, 60, 0)
            _orc._add_run_cost(actual_cost)
            # FX-11b (#1117): also write the canonical cost-ledger ROW for this
            # NLI-conflict judge call. It already feeds the run BUDGET via
            # _add_run_cost above, but without a ledger row the persisted ledger
            # total trails the run-budget total whenever PG_SWEEP_NLI_CONFLICT is
            # on. Route through the same canonical writer + ambient-run-id key the
            # judge/role writers use, so all rows of one run share one accumulator.
            # append_cost_ledger_row bumps the SEPARATE ledger accumulator (not
            # _RUN_COST_CTX), so this does NOT double-count the run budget.
            # FX-11c (#1136): write the row BEFORE check_run_budget — a
            # budget-BREACHING call is already billed to the accumulator by
            # _add_run_cost, so it must also land in the ledger; if check_run_budget
            # raised first the breaching call would be billed-but-unledgered (the
            # exact ledger<budget drift FX-11/FX-11b exist to eliminate).
            try:
                _orc.append_cost_ledger_row(
                    session_id=_orc.current_run_id() or "",
                    call_type="nli_conflict_judge",
                    cost_usd=actual_cost,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
            except Exception:  # noqa: BLE001 — ledger I/O must never abort detection
                pass
            _orc.check_run_budget(0)  # raises BudgetExceededError if cap breached
            return served

        # I-arch-005 B13 (#1257): route the call through the B14 empty-content guard so a
        # GLM-5.1 empty/None ``message.content`` (the reasoning-model collapse class) is
        # RETRIED before it ever reaches ``json.loads(None)``. On a NON-empty response the
        # guard returns it on the first attempt (byte-equivalent to the old single POST for
        # the happy path); on PERSISTENT empty it returns a ``JudgeUnavailable`` sentinel
        # (it does NOT raise) which we translate to the ``CONFLICT_UNSCORED_LABEL`` so the
        # pair is LABELED ``conflict_unscored`` (disclosed gap) rather than HELD. The guard
        # captures every attempt's raw request/response to the active raw-IO sink (the
        # empty-content upstream cause is confirmed, not inferred). ``BudgetExceededError``
        # is re-raised unchanged via ``propagate`` so keep-partial still fires.
        from src.polaris_graph.llm.side_judge_guard import (  # noqa: PLC0415
            call_side_judge_with_guard,
        )

        data = None  # I-obs-001 #1141 AC3: bound before the try so the fail-open capture can prefer
        # the served response (post ok, parse failed) over the exception string.
        try:
            _guard = call_side_judge_with_guard(
                _post_once,
                extract_content=lambda r: r["choices"][0]["message"]["content"],
                call_type="nli_conflict_judge",
                role="evaluator",
                build_request=lambda: {
                    **json_body, "messages": [{"role": "user", "content": prompt}],
                },
                propagate=(BudgetExceededError,),
            )
            if _guard.is_unavailable:
                # PERSISTENT empty content after the B14 retry → LABEL the pair
                # conflict_unscored, never HOLD (operator-locked "nothing shall hold the
                # report"). This is a disclosed gap: no conflict asserted, none dropped — the
                # judge could not adjudicate. Strict-fail-closed does NOT raise here: the B13
                # contract is that an EMPTY judge is always a LABEL, never a hold.
                logger.warning(
                    "[semantic-conflict] judge content empty after retry -> "
                    "conflict_unscored LABEL (could not adjudicate): %s",
                    _guard.unavailable.reason if _guard.unavailable else "",
                )
                return CONFLICT_UNSCORED_LABEL, 0.0
            data = _guard.value
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            verdict = str(parsed.get("verdict", "")).strip().upper()
            confidence = float(parsed.get("confidence", 0.0) or 0.0)
            label = {"CONTRADICT": "contradict", "ENTAIL": "entail",
                     "NEUTRAL": "neutral"}.get(verdict, "neutral")
            # Parsed verdict → the ONE success raw-IO record, AFTER parse (gate iter-1 P1).
            _emit_raw_io("ok", data)
            return label, confidence
        except Exception:
            # BudgetExceededError is a subclass-free RuntimeError in openrouter_client;
            # re-raise it explicitly so the caller's keep-partial path fires.
            from src.polaris_graph.llm.openrouter_client import BudgetExceededError
            import sys
            exc = sys.exc_info()[1]
            if isinstance(exc, BudgetExceededError):
                raise
            # I-arch-004 F07 (#1249/#1252): under strict gates, a transport/parse failure must
            # FAIL CLOSED — RAISE so detect_semantic_conflicts converts it to a run-level HOLD
            # (ConflictJudgeUnavailableError) instead of returning the fail-open ('neutral',
            # 0.0) that silently drops a possible real contradiction. NO conflict is fabricated:
            # the raise means "could not adjudicate", not "a conflict exists".
            if self._strict_fail_closed:
                logger.warning(
                    "[semantic-conflict] judge call failed under strict gates -> "
                    "FAIL CLOSED (run holds for review): %s", exc,
                )
                raise
            logger.warning("[semantic-conflict] judge call failed (fail-open neutral): %s", exc)
            # I-obs-001 #1141 AC3: capture the fail-OPEN judge_error — like the entailment judge, this
            # silently drops a possible real conflict on a transient/parse failure (drb_72-class
            # signal). Prefer the bound served `data`. Default-OFF; never raises.
            try:
                _io_sink = _orc.current_raw_io_sink()
                if _io_sink is not None:
                    import uuid as _uuid
                    _io_sink.record(
                        call_id=_uuid.uuid4().hex, call_type="nli_conflict_judge", role="evaluator",
                        request={**json_body, "messages": [{"role": "user", "content": prompt}]},
                        raw_response=(data if data is not None else {"error": str(exc)}),
                        duration_ms=None, status="judge_error",
                    )
            except Exception:  # noqa: BLE001
                pass
            return "neutral", 0.0


_JUDGE_SINGLETON = None


def get_default_judge(*, strict_fail_closed: bool = False):
    """Lazy singleton production judge callable ``(a, b) -> (label, confidence)``.

    Constructed only when ``PG_SWEEP_NLI_CONFLICT`` is ON and first used — off-mode
    never instantiates it (no network, no httpx client).

    I-arch-004 F07 (#1249/#1252): ``strict_fail_closed`` propagates to the judge so a
    transport/parse error RAISES (fail-closed hold) instead of the additive fail-open
    ('neutral', 0.0). The singleton is keyed on the flag so a strict caller never reuses
    a non-strict judge instance (and vice-versa)."""
    global _JUDGE_SINGLETON
    if _JUDGE_SINGLETON is None or getattr(
        _JUDGE_SINGLETON, "_strict_fail_closed", False
    ) != bool(strict_fail_closed):
        _JUDGE_SINGLETON = _SemanticContradictionJudge(strict_fail_closed=strict_fail_closed)
    return _JUDGE_SINGLETON.judge
