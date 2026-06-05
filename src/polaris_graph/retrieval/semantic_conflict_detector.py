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

_DEFAULT_ENTAILMENT_MODEL = "google/gemma-4-31b-it"
_JUDGE_TIMEOUT_S = 30.0

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


def detect_semantic_conflicts(pairs, judge, *, min_confidence: float | None = None) -> list:
    """Judge each pair; keep ``contradict`` pairs above ``min_confidence``.

    ``judge`` is a ``(claim_a, claim_b) -> (label, confidence)`` callable, label in
    {"contradict","entail","neutral"}. Fail-open:
      * a per-pair judge error skips THAT pair (never fabricates a conflict);
      * a ``BudgetExceededError`` stops judging, KEEPS records found so far, and
        propagates as a clean stop signal (caught by the caller's fail-open block)
        — it never aborts mid-record.
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
            logger.warning("[semantic-conflict] judge error on a pair (skipped): %s", exc)
            continue
        if str(label).strip().lower() != "contradict":
            continue
        try:
            conf = float(confidence)
        except (TypeError, ValueError):
            conf = 0.0
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


def detect_semantic_conflicts_for_rows(evidence_rows, judge=None) -> list:
    """End-to-end convenience: cluster -> pairs -> judge. Used by the sweep block.

    If ``judge`` is None the production default judge is lazily constructed
    (``get_default_judge``). Returns ``list[SemanticConflictRecord]``.
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
        judge = get_default_judge()
    return detect_semantic_conflicts(
        pairs, judge,
        min_confidence=_float_env(_ENV_MIN_CONFIDENCE, _DEFAULT_MIN_CONFIDENCE),
    )


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

    def __init__(self) -> None:
        import httpx

        from src.polaris_graph.llm.openrouter_client import check_family_segregation

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
        self._client = httpx.Client(timeout=_JUDGE_TIMEOUT_S)

    def judge(self, claim_a: str, claim_b: str) -> tuple:
        """Return ``(label, confidence)`` with label in {contradict,entail,neutral}.

        Fail-open on API/parse error → ("neutral", 0.0) so a transient outage never
        FABRICATES a conflict. ``BudgetExceededError`` is re-raised (the caller
        stops + keeps partial) — never masked as a neutral result.
        """
        from src.polaris_graph.llm import openrouter_client as _orc

        prompt = _CONTRADICTION_PROMPT.format(claim_a=claim_a, claim_b=claim_b)
        json_body: dict = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 60,
            "response_format": {"type": "json_object"},
        }
        try:
            from src.polaris_graph.benchmark import pathB_capture as _pathb_for_routing
            _gate_provider = _pathb_for_routing.get_role_provider("evaluator")
        except Exception:
            _gate_provider = None
        if _gate_provider:
            json_body["provider"] = {
                "order": [_gate_provider],
                "allow_fallbacks": False,
                "require_parameters": True,
            }
        try:
            response = self._client.post(
                self._endpoint,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=json_body,
            )
            response.raise_for_status()
            data = response.json()
            usage = data.get("usage", {}) or {}
            input_tokens = int(usage.get("prompt_tokens", 0) or 0)
            output_tokens = int(usage.get("completion_tokens", 0) or 0)
            api_cost = float(usage.get("cost", 0) or 0)
            actual_cost = api_cost or _orc._impute_cost_from_tokens(
                self._model, input_tokens, output_tokens, 0,
            )
            if actual_cost == 0 and not usage:
                actual_cost = _orc._impute_cost_from_tokens(self._model, 400, 60, 0)
            _orc._add_run_cost(actual_cost)
            _orc.check_run_budget(0)  # raises BudgetExceededError if cap breached
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            verdict = str(parsed.get("verdict", "")).strip().upper()
            confidence = float(parsed.get("confidence", 0.0) or 0.0)
            label = {"CONTRADICT": "contradict", "ENTAIL": "entail",
                     "NEUTRAL": "neutral"}.get(verdict, "neutral")
            return label, confidence
        except Exception:
            # BudgetExceededError is a subclass-free RuntimeError in openrouter_client;
            # re-raise it explicitly so the caller's keep-partial path fires.
            from src.polaris_graph.llm.openrouter_client import BudgetExceededError
            import sys
            exc = sys.exc_info()[1]
            if isinstance(exc, BudgetExceededError):
                raise
            logger.warning("[semantic-conflict] judge call failed (fail-open neutral): %s", exc)
            return "neutral", 0.0


_JUDGE_SINGLETON = None


def get_default_judge():
    """Lazy singleton production judge callable ``(a, b) -> (label, confidence)``.

    Constructed only when ``PG_SWEEP_NLI_CONFLICT`` is ON and first used — off-mode
    never instantiates it (no network, no httpx client)."""
    global _JUDGE_SINGLETON
    if _JUDGE_SINGLETON is None:
        _JUDGE_SINGLETON = _SemanticContradictionJudge()
    return _JUDGE_SINGLETON.judge
