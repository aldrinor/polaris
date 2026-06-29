"""
Scope-protocol query validator — HONEST-REBUILD Phase 2e.

Validates that amplified search queries stay within the pre-registered
protocol's research scope. Drops queries that have drifted off-topic
before they waste retrieval budget.

WHY THIS EXISTS (PG_LB_SA_02_CONTENT_AUDIT Section E-04):
The pre-rebuild pipeline amplified a single research question into
10-25 search variants using an LLM. Some variants drifted:
  original: "efficacy of semaglutide for weight loss"
  amplified: "Japan national health insurance elderly care coverage"

These drifted queries pulled in the junk that Phase 2d's post-fetch
off-topic filter then had to remove. Dropping drift at amplification
time is cheaper than fetching and discarding.

DESIGN:
- No new LLM call. Uses token overlap with protocol.research_question +
  PICO fields (intervention / population / outcome) as the anchor.
- Drops any amplified query whose similarity with the anchor is below
  PG_AMPLIFIER_SCOPE_FLOOR (default 0.08, the containment-scale floor — see
  I-retr-001 #1340).
- ALWAYS keeps the verbatim research_question and direct PICO-term
  queries ("{intervention} {population}") as a safety net.
- Logs drops so the user can see which amplifier variants were killed.

SIMILARITY MEASURE (default `containment` per I-retr-001 #1340; was `jaccard`
per BB-001 #1171):
- PG_SCOPE_SIM_MEASURE selects the measure: `containment` (DEFAULT) or `jaccard`.
  Symmetric Jaccard (|q∩a|/|q∪a|) punishes a SHORT on-topic query against a large
  anchor bag (tiny intersection over a huge union) — the #1 retrieval-breadth
  chokepoint (kept=2 of 35 on drb_72, anchor_tokens=136). Containment / overlap-
  coefficient (|q∩a|/min(|q|,|a|)) normalises by the smaller set so a short on-topic
  query clears while genuine drift still fails. The GATE is KEPT either way (genuine
  off-anchor drift still drops); only the measure changes. `jaccard` stays selectable
  for back-compat. Default flipped to `containment` so EVERY run path is correct, not
  only the Gate-B slate (which already set containment explicitly).
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger("polaris_graph.scope_query_validator")


# Very small English stopword set — we care about domain terms, so
# we strip only the grammatical connective tissue.
_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "has", "have", "in", "is", "it", "its", "of", "on", "or", "that",
    "the", "this", "to", "was", "were", "will", "with", "what", "which",
    "how", "why", "when", "where", "who", "whom", "whose", "i", "you",
    "we", "they", "can", "could", "should", "would", "may", "might",
    "do", "does", "did", "done", "being", "been", "about", "into",
    "than", "then", "so", "also", "more", "most", "some", "any", "all",
    "not", "no", "only", "very", "just", "other",
})

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-]{1,}")


def _tokenize(text: str) -> set[str]:
    """Lowercased tokens minus stopwords, minus short tokens."""
    if not text:
        return set()
    tokens = {
        t.lower()
        for t in _TOKEN_RE.findall(text)
        if len(t) > 2
    }
    return tokens - _STOPWORDS


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard (symmetric) similarity |a∩b| / |a∪b|. Empty a or b -> 0.0."""
    if not a or not b:
        return 0.0
    union = a | b
    inter = a & b
    return len(inter) / len(union) if union else 0.0


def _containment(a: set[str], b: set[str]) -> float:
    """Containment / overlap-coefficient similarity |a∩b| / min(|a|, |b|).

    BB-001 (I-beatboth-fix-000 #1171): the symmetric Jaccard punishes a SHORT
    on-topic query against a LARGE anchor bag — a 4-6-token query has a tiny
    intersection over a huge union, so its sim sits far below the floor and the
    query is dropped before it ever issues a search (the #1 retrieval-breadth
    chokepoint: 40->5 kept on drb_72). Containment normalises by the SMALLER set,
    so a short query whose tokens are all in the anchor scores ~1.0 while a query
    that drifts off-anchor still scores low — it KEEPS the gate (reranks against
    intent) rather than removing it. Empty a or b -> 0.0; never raises.
    """
    if not a or not b:
        return 0.0
    inter = a & b
    smaller = min(len(a), len(b))
    return len(inter) / smaller if smaller else 0.0


_SIM_MEASURES = {"jaccard": _jaccard, "containment": _containment}

# I-retr-001 (#1340): the DEFAULT measure is `containment` (overlap-coefficient
# |q∩a| / min(|q|,|a|)) with floor 0.08. Under SYMMETRIC jaccard a short on-topic
# query against a long research-question anchor (drb_72: anchor_tokens=136) caps at
# ~8/136 ≈ 0.06 and was wrongly dropped (kept=2 of 35) — the §-1.3 filter-strangles-
# breadth defect. Containment normalises by the SMALLER set, so a short on-topic query
# scores ~1.0 while genuine off-anchor drift still scores low and is still dropped: the
# de-drift GATE is KEPT, only the measure is corrected. `jaccard` remains selectable via
# PG_SCOPE_SIM_MEASURE for back-compat. Faithfulness-NEUTRAL — this is a pre-fetch
# query/scope gate; it touches no strict_verify / NLI / 4-role / span faithfulness gate.
# (Supersedes BB-001 #1171, whose `jaccard`-default "byte-identical OFF" choice was the
# source of the breadth collapse on every run path that does not apply the Gate-B slate.)
_DEFAULT_SIM_MEASURE = "containment"
_DEFAULT_SCOPE_FLOOR = 0.08

# ─────────────────────────────────────────────────────────────────────────────
# I-deepfix-001 keystone (#1344) — KEEP-BEST-N anti-empty-round guard.
# Relaunch forensic P1-8: the scope validator could drop a whole snowball / CRAG-
# corrective sub-query set to "0 unique candidates". An empty kept-set fires NO
# search => no new sources merge => the CRAG adequacy grader re-grades the unchanged
# corpus not-sufficient => the corrective loop burns its budget WITHOUT widening the
# corpus (retrieval never converges). A validator that HARD-DROPS to empty is the
# §-1.3 "filter, not weight" anti-pattern. KEEP-BEST-N rescues the round: when EVERY
# non-directive, non-empty candidate would be scope-dropped, keep the top-N by scope
# similarity (a WEIGHT — the most on-intent survivors) so the round still fires.
# This is keep-and-proceed; it is a pre-fetch query/scope gate and touches NO
# faithfulness gate (strict_verify / NLI / 4-role / span). It NEVER acts when the
# kept-set is already non-empty (an always-kept anchor or any passing query satisfies
# the >=1 guarantee), so the default-ON path is byte-identical except for the precise
# empty-round case it exists to prevent. `PG_SCOPE_KEEP_BEST_N=0` reverts to the
# legacy drop-to-empty.
_KEEP_BEST_N_ENV = "PG_SCOPE_KEEP_BEST_N"
_DEFAULT_KEEP_BEST_N = 1


def _keep_best_n() -> int:
    """Top-N survivors to keep when the scope floor would strand an empty round.

    Reads ``PG_SCOPE_KEEP_BEST_N`` (default 1). ``0`` => legacy drop-to-empty
    (byte-identical). A malformed value falls back to the default rather than
    raising — the anti-empty-round budget is an operational knob, not a
    correctness gate (the floor itself is unchanged)."""
    raw = os.getenv(_KEEP_BEST_N_ENV, "").strip()
    if not raw:
        return _DEFAULT_KEEP_BEST_N
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_KEEP_BEST_N
    return max(0, value)


def _select_sim_measure():
    """Return the (name, fn) for the configured similarity measure.

    Reads ``PG_SCOPE_SIM_MEASURE`` (default ``containment`` per I-retr-001 #1340).
    An unrecognised value FAILS LOUD (LAW II) — a typo'd measure must not
    silently fall back to a different gate behaviour on a paid benchmark run.
    """
    raw = os.getenv("PG_SCOPE_SIM_MEASURE", _DEFAULT_SIM_MEASURE).strip().lower()
    if raw not in _SIM_MEASURES:
        raise ValueError(
            f"PG_SCOPE_SIM_MEASURE={raw!r} is not a recognised similarity measure "
            f"(expected one of {sorted(_SIM_MEASURES)})."
        )
    return raw, _SIM_MEASURES[raw]


# ─────────────────────────────────────────────────────────────────────────────
# I-deepfix-001 B3 (2026-06-28) — prompt-injection-inversion backstop.
# A pure, no-network, deterministic screen that drops DIRECTIVE-SHAPED clauses
# (do-not-view / prohibition blocks, "highest priority rule" framing, output-shape
# demands, embedded URL/DOI deny-list literals, imperative meta-instructions) so an
# injected instruction in the raw prompt NEVER becomes a search query — even when
# the LLM intent-frame (B3 primary) is OFF or misses one. This is defense-in-depth,
# fires deterministically, and is faithfulness-NEUTRAL (a query/scope screen only).
# ─────────────────────────────────────────────────────────────────────────────

_DIRECTIVE_FLAG = "PG_QUERY_DIRECTIVE_SCREEN"
_DIRECTIVE_OFF = frozenset({"0", "false", "no", "off", "disabled", ""})

# Substrings whose presence marks a clause as a META-DIRECTIVE rather than a research
# query. High-precision: each is instruction/prohibition chrome that does not occur in
# a genuine research sub-question. Lowercased compare.
_DIRECTIVE_MARKERS: tuple[str, ...] = (
    "do not view",
    "do not visit",
    "do not access",
    "do not use",
    "do not cite",
    "do not read",
    "not allowed to view",
    "you are not allowed",
    "must not",
    "highest priority",
    "highest-priority",
    "this is the most important rule",
    "ignore previous",
    "ignore all previous",
    "disregard previous",
    "system prompt",
    "column headers",
    "output format",
    "respond only",
    "format your answer",
    "use the following format",
    "blocked sources",
    "blocked reference",
    "denylist",
    "deny-list",
    "do-not-view",
)

# A clause that is a bare URL/DOI dict/list literal is a deny-list payload, never a
# research question. I-deepfix-001 Codex wave-2 P1: the prior regex marked ANY
# `doi.org/` or `10.xxxx/` occurrence as a directive, so a legitimate research
# sub-query that merely CITES a DOI ("What does DOI 10.1016/j.x report about
# wages?") was wrongly stripped. The URL/DOI leg now fires ONLY on a BARE payload
# (a dict/list literal, or a clause that is essentially just URLs/DOIs with no
# prose). A real deny-list INSTRUCTION ("do not view <url>") is still caught by the
# high-precision `_DIRECTIVE_MARKERS` regardless.
_URL_DOI_DICT_LITERAL_RE = re.compile(r"^\s*[\[{]|\{\s*['\"]?url", re.IGNORECASE)
_URL_DOI_TOKEN_RE = re.compile(
    r"\S*(?:https?://|www\.|doi\.org/|10\.\d{4,9}/)\S*", re.IGNORECASE
)


def _is_bare_url_doi_payload(low: str) -> bool:
    """True iff the clause is a BARE URL/DOI deny-list payload (a dict/list literal,
    or essentially just URLs/DOIs with no prose), NOT a research query that happens
    to cite a DOI. Used by `is_directive_clause` (Codex wave-2 P1 narrowing)."""
    if _URL_DOI_DICT_LITERAL_RE.search(low):
        return True
    if not _URL_DOI_TOKEN_RE.search(low):
        return False
    # Strip the URL/DOI tokens; a genuine research query around a DOI keeps several
    # content words, a bare payload keeps almost none (<=2 glue words like "see at").
    stripped = _URL_DOI_TOKEN_RE.sub(" ", low)
    content_words = re.findall(r"[a-z]{2,}", stripped)
    return len(content_words) <= 2
# Imperative opener: a clause that BEGINS with an unambiguous injection-command
# verb. I-deepfix-001 Codex wave-1 P2: the prior list included polysemous
# research-domain verbs (return/output/ensure/keep/put) that match legitimate
# queries — "return-to-work outcomes", "output of the assay", "ensure adequate
# dosing" — and over-dropped them. Those verbs' genuine INJECTION forms ("output
# format", "respond only", "must not", "do not view") are already high-precision
# entries in `_DIRECTIVE_MARKERS`; this opener is now restricted to the five
# command openers that do not occur in a research sub-question, each requiring a
# trailing SPACE so hyphenated compounds (e.g. a leading "do-not-resuscitate"
# term) cannot trip it.
# Codex wave-2 P2: dropped bare "please " — a polite research sub-query ("please
# compare wage outcomes…") is legitimate, and the real injection forms ("please
# ignore", "please respond only", "please output format") are already caught by the
# remaining openers + the high-precision `_DIRECTIVE_MARKERS`.
_IMPERATIVE_OPENER_RE = re.compile(
    r"^\s*(ignore\s|disregard\s|do not\s|don't\s)",
    re.IGNORECASE,
)


def directive_screen_enabled() -> bool:
    """B3 directive-screen kill-switch. DEFAULT ON (faithfulness-neutral injection
    defense). ``PG_QUERY_DIRECTIVE_SCREEN=0`` reverts to byte-identical behaviour."""
    return os.getenv(_DIRECTIVE_FLAG, "1").strip().lower() not in _DIRECTIVE_OFF


def is_directive_clause(text: str) -> bool:
    """True iff ``text`` is a directive/meta-instruction clause rather than an
    answerable research query (I-deepfix-001 B3). Pure, deterministic, no network."""
    if not text:
        return False
    low = text.strip().lower()
    if not low:
        return False
    if any(marker in low for marker in _DIRECTIVE_MARKERS):
        return True
    if _is_bare_url_doi_payload(low):
        return True
    if _IMPERATIVE_OPENER_RE.match(low):
        return True
    return False


def strip_directive_clauses(queries: list[str]) -> tuple[list[str], list[str]]:
    """Partition ``queries`` into (kept, dropped_directives). The B3 backstop the
    foreign query-decomposer SHOULD also call before issuing searches; applied here
    inside ``validate_amplified_queries`` so it fires on the retrieval path regardless.
    """
    kept: list[str] = []
    dropped: list[str] = []
    for q in queries:
        if is_directive_clause(q):
            dropped.append(q)
        else:
            kept.append(q)
    return kept, dropped


@dataclass
class ValidationResult:
    """Return value of validate_amplified_queries()."""

    kept: list[str]
    dropped: list[tuple[str, float, str]]  # (query, similarity, reason)
    anchor_tokens_used: list[str]


def _build_anchor_tokens(protocol: dict[str, Any]) -> set[str]:
    """Merge research_question + anchor tokens into one anchor set.

    Accepts either a ProtocolDocument dict (from scope_gate) or any dict with
    similar fields. Missing fields are skipped gracefully.

    Clinical PICO fields (population / intervention / comparator / outcome) are
    string-valued and tokenized as before — OFF byte-identical.

    I-meta-005 Phase 1 (#985, brief §2.4): ADDITIVELY also merge the field-
    agnostic `ResearchFrame` anchor fields (entities / relations / metrics /
    comparators / constraints) when present, so planner sub-queries derived
    from a non-clinical frame validate against the frame's OWN tokens. These
    fields may be list-valued (from `ResearchFrame.to_anchor_protocol`); each
    element is tokenized. A clinical PICO protocol carries none of them, so
    this extension does not change PICO behavior.
    """
    bag: set[str] = set()
    # Legacy clinical PICO anchors (string-valued). Unchanged.
    for field in (
        "research_question", "population", "intervention",
        "comparator", "outcome",
    ):
        val = protocol.get(field) or ""
        bag |= _tokenize(str(val))
    # I-meta-005 Phase 1: field-agnostic frame anchors (list-valued). Skipped
    # gracefully when absent (clinical PICO protocols), so OFF is unchanged.
    for field in (
        "entities", "relations", "metrics", "comparators", "constraints",
    ):
        val = protocol.get(field)
        if isinstance(val, (list, tuple, set)):
            for item in val:
                bag |= _tokenize(str(item))
        elif val:
            bag |= _tokenize(str(val))
    return bag


def validate_amplified_queries(
    amplified: list[str],
    protocol: dict[str, Any],
    *,
    floor: Optional[float] = None,
    always_keep_anchor: bool = True,
) -> ValidationResult:
    """Drop amplified queries that drift off the scope protocol.

    Args:
        amplified: Raw output from query amplifier — plain string queries.
        protocol: Dict form of protocol.json, OR any dict with the
            fields research_question / intervention / population / outcome.
        floor: Minimum scope similarity (query-tokens-vs-anchor-tokens) to
            keep a query. Default: PG_AMPLIFIER_SCOPE_FLOOR env var,
            fallback 0.08 (the containment-scale floor; see I-retr-001 #1340).
        always_keep_anchor: When True, the verbatim research_question is
            always kept even if its own similarity is below floor (which
            can happen for very short questions). Default True.

    Returns:
        ValidationResult with `kept` (queries that passed), `dropped`
        (tuples with reason), and `anchor_tokens_used` for debugging.
    """
    if floor is None:
        floor = float(os.getenv("PG_AMPLIFIER_SCOPE_FLOOR", str(_DEFAULT_SCOPE_FLOOR)))

    # I-retr-001 (#1340): default `containment` (overlap-coefficient) so a short
    # on-topic query clears the floor against a long anchor. The de-drift gate is
    # KEPT either way (off-anchor queries still fail) — only the MEASURE changes.
    sim_name, sim_fn = _select_sim_measure()

    anchor_tokens = _build_anchor_tokens(protocol)
    anchor_tokens_sorted = sorted(anchor_tokens)

    research_question = (protocol.get("research_question") or "").strip()

    kept: list[str] = []
    dropped: list[tuple[str, float, str]] = []
    seen: set[str] = set()

    # I-deepfix-001 B3 backstop: drop directive/meta-instruction clauses BEFORE
    # the scope-similarity gate so an injected do-not-view / output-shape / deny-list
    # directive in the amplified set never issues a search (fires even when the LLM
    # intent-frame is OFF). Deterministic, no network; faithfulness-neutral.
    directive_dropped: list[str] = []
    if directive_screen_enabled():
        amplified, directive_dropped = strip_directive_clauses(list(amplified))
        if directive_dropped:
            logger.info(
                "[scope_validator] B3 directive-screen dropped %d injected/meta "
                "clause(s) before search.",
                len(directive_dropped),
            )

    # Dedupe while preserving order
    unique_amplified: list[str] = []
    for q in amplified:
        norm = (q or "").strip().lower()
        if norm and norm not in seen:
            seen.add(norm)
            unique_amplified.append(q.strip())

    # I-deepfix-001 keystone (#1344): track the below-floor (but non-directive,
    # non-empty) candidates with their scope similarity so KEEP-BEST-N can rescue
    # the most on-intent survivors if the kept-set would otherwise be EMPTY.
    below_floor: list[tuple[str, float, str]] = []
    for q in unique_amplified:
        q_tokens = _tokenize(q)
        if not q_tokens:
            dropped.append((q, 0.0, "empty_after_tokenization"))
            continue
        sim = sim_fn(q_tokens, anchor_tokens)
        if sim >= floor:
            kept.append(q)
        else:
            # I-retr-001 (#1340): the drop reason carries the active measure name
            # (default now `containment`) for debuggability; bare `jaccard` keeps the
            # legacy suffix-less form for back-compat with the explicit-jaccard path.
            _reason = f"below_scope_floor_{floor:.2f}"
            if sim_name != "jaccard":
                _reason = f"{_reason}_{sim_name}"
            below_floor.append((q, sim, _reason))

    # Record the B3 directive drops in the telemetry so they are auditable
    # (sim=0.0, an explicit injected-directive reason — never silently swallowed).
    for q in directive_dropped:
        dropped.append((q, 0.0, "injected_directive_clause"))

    # Safety net: always keep the verbatim research_question, even if
    # its own similarity was below floor (happens for very short PICO
    # questions like "Semaglutide efficacy?").
    if always_keep_anchor and research_question:
        if research_question not in kept:
            kept.insert(0, research_question)

    # I-deepfix-001 keystone (#1344): KEEP-BEST-N anti-empty-round rescue. Fires ONLY
    # when the floor loop left the kept-set EMPTY (the convergence-blocking case) AND
    # there were below-floor candidates to rescue. Keep the top-N by scope similarity
    # — the most on-intent survivors — so the round still fires. §-1.3 keep-and-proceed:
    # this can only ADD on-intent queries the floor would have stranded; it never
    # drops a source, never relaxes a faithfulness gate. When kept is already non-empty
    # (an always-kept anchor or any passing query) this no-ops => byte-identical.
    keep_best_n = _keep_best_n()
    if not kept and keep_best_n > 0 and below_floor:
        # Deterministic: highest sim first; ties broken by original (stable) order.
        ranked = sorted(
            enumerate(below_floor), key=lambda iv: (-iv[1][1], iv[0])
        )
        rescued_idx = {i for i, _ in ranked[:keep_best_n]}
        for i, (q, sim, _reason) in enumerate(below_floor):
            if i in rescued_idx:
                kept.append(q)
            else:
                dropped.append((q, sim, _reason))
        logger.info(
            "[scope_validator] KEEP-BEST-N rescued %d of %d below-floor query(ies) "
            "to avoid a stranded empty retrieval round (PG_SCOPE_KEEP_BEST_N=%d).",
            len(rescued_idx), len(below_floor), keep_best_n,
        )
    else:
        # No rescue needed (or disabled): every below-floor candidate stays dropped.
        dropped.extend(below_floor)

    logger.info(
        "[scope_validator] measure=%s floor=%.2f kept=%d dropped=%d (anchor_tokens=%d)",
        sim_name, floor, len(kept), len(dropped), len(anchor_tokens),
    )
    if dropped:
        sample = dropped[:3]
        for q, sim, reason in sample:
            logger.debug(
                "[scope_validator] DROP q=%r sim=%.3f reason=%s",
                q[:80], sim, reason,
            )

    return ValidationResult(
        kept=kept,
        dropped=dropped,
        anchor_tokens_used=anchor_tokens_sorted,
    )
