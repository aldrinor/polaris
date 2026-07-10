"""I-deepfix-001 B13 (#1357) — bring the Analyst-Synthesis layer UNDER the faithfulness engine.

THE PROBLEM (forensic): ``analyst_synthesis.generate_analyst_synthesis`` is architecturally OUTSIDE
the faithfulness engine — its system prompt FORBIDS ``[#ev:]`` span tokens and cites by ``[N]``
bibliography markers only, so the per-sentence ``strict_verify`` entailment gate NEVER sees it. It is
the longest, most confident block in the report, and its grounded over-assertions (hedges upgraded to
assertions, interpolated specifics, model-asserted author names absent from the pool) ship UNGATED.

THE FIX (the operator-locked "verify AFTER compose = LABEL, never DELETE" pattern, §-1.3 BASKET
FAITHFULNESS / `feedback_always_release_verifier_labels_never_holds_2026_06_14`): this module is a
thin, additive DEVIATION CHECK over the already-composed synthesis prose. It:

  1. splits the synthesis into sentences (reusing ``provenance_generator.split_into_sentences``),
  2. for each sentence, parses its ``[N]`` markers (``report_claim_extractor._NUMBERED_RE``) and
     resolves ``N -> bibliography[N-1].evidence_id -> the cited evidence row's span``,
  3. asks a groundedness judge (the certified MiniMax-M2 Sentinel decomposition by default — a SECOND
     family vs the GLM/DeepSeek writer, so two-family holds) whether the cited span SUPPORTS the
     sentence,
  4. for an UNSUPPORTED sentence appends an inline confidence marker
     (``claim_labeler.render_confidence_marker(BUCKET_LOW)``), and for a sentence whose ``[N]`` resolve
     NO span (``BUCKET_NO_SOURCE``) — KEEP the sentence, NEVER delete it.

FAIL-CLOSED to ``BUCKET_LOW``: a judge error / transport flap / timeout LABELS the sentence low (over-
labeling is the SAFE direction for a previously-ungated layer), never a silent high, never a hold.

FAITHFULNESS ENGINE UNTOUCHED: ``strict_verify`` / NLI / 4-role D8 / provenance / span-grounding are
NOT modified. This is an additive, LABEL-only deviation leg over the previously-ungated synthesis
prose. The judge here is ADVISORY — it never drops a sentence, never changes ``is_verified``.

LAW VI: the leg is gated default-ON by ``PG_ANALYST_SYNTHESIS_DEVIATION_CHECK`` and shares the coarse
``PG_SWEEP_ANALYST_SYNTHESIS`` kill-switch (when the whole analyst layer is off, this never runs).

TESTABILITY / NO HANG (I-arch-006/007 lesson): the per-sentence groundedness call is INJECTABLE
(``judge_fn``) so a test passes a deterministic fake; the real path resolves a bounded, deadline-wrapped
Sentinel judge lazily. The calls run BOUNDED-PARALLEL (never a serial unbounded loop on a trickle
socket — the documented hang class).
"""
from __future__ import annotations

import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FutureTimeout
from typing import Any, Callable

from src.polaris_graph.generator import claim_labeler
from src.polaris_graph.generator.provenance_generator import (
    split_into_sentences,
    verify_sentence_provenance,
)
from src.polaris_graph.benchmark.report_claim_extractor import _NUMBERED_RE

logger = logging.getLogger(__name__)

# LAW VI flags. The leg is default-ON; the coarse analyst-layer kill-switch ALSO gates it (when the
# whole analyst layer is off, this module never runs because the caller returns before invoking it).
_ENV_ENABLED = "PG_ANALYST_SYNTHESIS_DEVIATION_CHECK"
_ENV_ANALYST_KILL = "PG_SWEEP_ANALYST_SYNTHESIS"
# Bounded-parallel fan-out for the per-sentence groundedness calls (NEVER a serial unbounded loop on a
# trickle socket — the I-arch-006/007 hang class). LAW VI; default 8.
_ENV_MAX_INFLIGHT = "PG_ANALYST_SYNTHESIS_DEVIATION_MAX_INFLIGHT"
_DEFAULT_MAX_INFLIGHT = 8
# Per-call deadline (seconds). A judge socket flap fail-CLOSES to BUCKET_LOW (over-label = safe) rather
# than hanging the report. LAW VI; default 60s.
_ENV_DEADLINE_S = "PG_ANALYST_SYNTHESIS_DEVIATION_DEADLINE_S"
_DEFAULT_DEADLINE_S = 60.0

_OFF_VALUES = frozenset({"", "0", "false", "off", "no", "disabled"})

# I-deepfix-001 D3 (#1344) — FAIL-CLOSED PROMOTE gate. Default-OFF (LAW VI). This is the gate that lets
# the analyst-synthesis layer turn ON safely (the layer is REQUIRED_OFF today precisely because it was
# not span-verified). When this flag is ON:
#   * a synthesis sentence renders in the SCORED BODY only if it passes ALL THREE legs of the frozen
#     engine — the same gate every body claim clears (Codex iter-4 P0):
#       (1) the REAL verify_sentence_provenance re-pass (_frozen_engine_verifies_sentence): a genuine
#           [#ev:id:start-end] provenance token is rebuilt per cited source and the UNCHANGED
#           strict_verify + NLI-entailment engine must return is_verified — so a [N]-cited synthesis
#           sentence now carries and clears real [#ev] provenance exactly like a verified body claim;
#       (2) the deterministic span-grounding pre-check (strict_verify §9.1.3 principle — every decimal
#           in the sentence appears in the cited span AND >= _MIN_CONTENT_OVERLAP shared content words); and
#       (3) the D8/NLI groundedness judge (judge_fn / the certified Sentinel).
#     A passing sentence is KEEP-and-PROMOTE'd (BUCKET_MODERATE "verified against the cited source");
#   * a sentence that FAILS either leg — ungrounded, no-source, or judge-fault — is DROPPED from the
#     body (fail-closed) and surfaced in the returned drop telemetry + a fail-LOUD log line, NEVER
#     rendered as a hedged body claim. Over-drop is the safe direction; no source is deleted (the drop
#     removes a model-generated sentence, not an evidence row), strict_verify / NLI / 4-role are NOT
#     touched — this gate is ADDED on top of the frozen engine.
# OFF (default) => the legacy advisory KEEP-and-LABEL leg runs, byte-identical: grounded sentences pass
# bare, ungrounded/no-source sentences are LABELED (never dropped).
_ENV_PROMOTE_GROUNDED = "PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED"

# Deterministic span-grounding leg (the strict_verify §9.1.3 principle, reused faithfully at the
# synthesis seam so the D3 gate is the FROZEN ENGINE, not a lone judge). PURE, no I/O.
_MIN_CONTENT_OVERLAP = 2
_MARKER_RE = re.compile(r"\[[^\]]*\]")          # [N] citation + [confidence:...] markers
# I-deepfix-001 D3 P1 (#1344): a pre-labeled sentence (already carrying a [confidence:...] marker —
# model-injected, or a defensive double-call) must be STRIPPED of that marker so the promote gate
# re-screens the bare prose through BOTH frozen-engine legs. Without this a hedged, ungrounded claim
# could carry its own [confidence: low] tag past the gate and survive in the scored body.
_CONFIDENCE_MARKER_RE = re.compile(r"\s*\[confidence:[^\]]*\]")
_DECIMAL_RE = re.compile(r"\d+(?:[.,]\d+)?")
_WORD_RE = re.compile(r"[a-z0-9]+")
# A tiny stoplist so the >=2 content-word overlap is genuinely topical (not "the"/"is" agreement).
_GROUND_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "in", "on", "for", "to", "with", "by", "at", "from",
    "as", "is", "are", "was", "were", "be", "been", "being", "this", "that", "these", "those",
    "it", "its", "their", "his", "her", "our", "your", "we", "they", "he", "she", "you",
    "not", "no", "but", "if", "then", "than", "so", "such", "into", "over", "under", "about",
    "which", "who", "whom", "whose", "what", "when", "where", "while", "also", "may", "can",
    "will", "would", "could", "should", "has", "have", "had", "more", "most", "some", "any",
})


def _strip_markers(text: str) -> str:
    """Remove bracketed ``[N]`` / ``[confidence:...]`` markers so number/word extraction reads the
    prose, not the citation index (``[1]`` must never be counted as the decimal ``1``)."""
    return _MARKER_RE.sub(" ", text or "")


def _strip_confidence_markers(text: str) -> str:
    """Remove any ``[confidence:...]`` marker(s) from ``text`` (leaving ``[N]`` citations intact) so a
    pre-labeled sentence is re-screened on its bare prose in PROMOTE mode. PURE."""
    return _CONFIDENCE_MARKER_RE.sub("", text or "").strip()


def _decimals(text: str) -> "set[str]":
    """The distinct decimal number tokens in ``text`` (comma thousands-separators normalized out)."""
    return {d.replace(",", "") for d in _DECIMAL_RE.findall(text or "")}


def _content_tokens(text: str) -> "set[str]":
    """Lower-cased content tokens (>=3 chars, not a stopword)."""
    return {w for w in _WORD_RE.findall(str(text or "").lower())
            if len(w) >= 3 and w not in _GROUND_STOPWORDS}


def _span_grounds_sentence(sentence: str, span: str) -> bool:
    """Deterministic span-grounding leg of the D3 frozen-engine gate (strict_verify §9.1.3 principle).

    True iff the sentence's prose is anchored in the cited span: (a) EVERY decimal in the sentence
    appears in the span (a synthesis sentence must not invent or alter a number the cited source did
    not state), AND (b) the sentence and the span share >= ``_MIN_CONTENT_OVERLAP`` content words. A
    blank span never grounds. PURE. This is a CONSERVATIVE gate — it can only REFUSE to promote (drop
    to the fail-closed audit tail); it never admits a sentence the judge rejected."""
    if not span or not span.strip():
        return False
    core = _strip_markers(sentence)
    sent_nums = _decimals(core)
    if sent_nums and not sent_nums.issubset(_decimals(span)):
        return False
    return len(_content_tokens(core) & _content_tokens(span)) >= _MIN_CONTENT_OVERLAP


def promote_grounded_enabled() -> bool:
    """True iff the default-OFF PROMOTE mode is active (M6 Layer 2). Requires the deviation check to be
    enabled (it shares that gate) AND the fine PROMOTE flag to be explicitly on."""
    promote_on = os.environ.get(_ENV_PROMOTE_GROUNDED, "0").strip().lower() not in _OFF_VALUES
    return promote_on and deviation_check_enabled()


# I-deepfix-001 P1 (box2 DEPTH lever): synthesis-mode basket gate. The extractive PROMOTE gate requires each
# synthesis sentence to be ENTAILED/verbatim-grounded by its cited spans — correct for extractive body claims,
# WRONG for cross-source analytical SYNTHESIS that fuses+interprets sources into a new insight no single span
# entails (box2: 79/81 real cited cross-source sentences dropped). When ON, a synthesis sentence is KEPT iff it
# (1) resolves >=1 valid cited span AND (2) passes the DETERMINISTIC anti-fabrication floor (_span_grounds_sentence:
# every number in the sentence appears in the UNION of cited spans AND >=2 content-word overlap). Default OFF.
_ENV_BASKET_MODE = "PG_ANALYST_SYNTHESIS_BASKET_MODE"


def basket_mode_enabled() -> bool:
    on = os.environ.get(_ENV_BASKET_MODE, "0").strip().lower() not in _OFF_VALUES
    return on and promote_grounded_enabled()


# I-deepfix-001 wave-2 (#1370): whole-basket FULL-TEXT grounding (default ON within basket mode). Ground a
# synthesis sentence against the FULL text of each cited source (direct_quote + statement + title + snippet),
# unioned across all cited [N], NOT the narrow direct_quote slice — the box2 over-drop where ~18-20 real
# cross-source analytical sentences (the task-based / substitution-complementarity framework, the
# Brynjolfsson +14% and Eloundou exposure findings) were dropped because their grounded numbers sat in the
# source ``statement`` but not the exact quote slice. A number in NO cited source still drops (anti-fabrication
# floor holds). §-1.3 whole-basket faithfulness: STRENGTHENS, never relaxes. Set 0 to revert to the narrow union.
_ENV_BASKET_FULLTEXT = "PG_ANALYST_SYNTHESIS_BASKET_FULLTEXT"


def _basket_fulltext_enabled() -> bool:
    return os.environ.get(_ENV_BASKET_FULLTEXT, "1").strip().lower() not in _OFF_VALUES


# I-deepfix-001 wave-2 (#1370) DEPTH — disclosed analyst layer. The analyst-synthesis composer is DESIGNED
# to write hedged interpretive framing UNCITED (its system prompt reserves [N] for concrete factual claims
# and instructs qualitative interpretation to be hedged, not cited), and the layer already carries the
# ANALYST_SYNTHESIS_DISCLOSURE preamble ("interpretive commentary … not individually span-verified"). The D3
# PROMOTE gate was fighting that design — dropping every uncited interpretive sentence (box2: 31 real
# analytical-framework sentences lost). This renders an uncited hedged QUALITATIVE interpretation under that
# disclosure instead of dropping it (verify-after-compose = LABEL, never DELETE — operator-authorized gated
# analyst-synthesis). Default OFF; only active WITH basket mode. A fabrication (uncited + a number / a named
# study absent from the pool) STILL drops.
_ENV_DISCLOSED_ANALYST = "PG_ANALYST_SYNTHESIS_DISCLOSED_KEEP"


def _disclosed_analyst_enabled() -> bool:
    return os.environ.get(_ENV_DISCLOSED_ANALYST, "0").strip().lower() not in _OFF_VALUES


# An author attribution ("Acemoglu and Restrepo", "Brynjolfsson et al") inside an UNCITED interpretive
# sentence is disclosable ONLY if EVERY named surname is actually in the evidence pool (a real study being
# interpreted). A surname absent from the pool is a fabricated attribution and must DROP.
_AUTHOR_ATTR_RE = re.compile(r"\b[A-Z][a-z]{2,}\s+(?:et al|and\s+[A-Z][a-z]{2,})")
_SURNAME_RE = re.compile(r"[A-Z][a-z]{2,}")
_POOL_TOKEN_RE = re.compile(r"[a-z]{3,}")
# Codex + Fable depth-gate P1 (load-bearing §-1.3 fix): a disclosable NON-header sentence must carry a
# HEDGE / INTERPRETIVE cue — the markers the composer's own system prompt tells the LLM to use for hedged
# interpretation (suggests / implies / may / typically / broadly / consistent with / framework / logic /
# depends on / …). A bare UNHEDGED categorical assertion ("Generative AI will replace all lawyers") carries
# no hedge => NOT disclosable => drops. Deliberately EXCLUDES bare analytical nouns (trend / pattern /
# evidence) that a fabricated declarative could carry. Verified to still admit box2's real analytical
# framework tissue.
_INTERPRETIVE_CUE_RE = re.compile(
    r"\b(?:suggest\w*|impl(?:y|ies|ied|ication\w*)|may|might|could|consistent with|typical\w*|broad\w*|"
    r"appears?|likely|interpret\w*|framework\w*|mechanism\w*|logic\w*|depends?\s+on|reflect\w*|align\w*|"
    r"underscore\w*|in principle|plausibl\w*|tends?\s+to|contextualiz\w*|represent\w*|modulat\w*|"
    r"reinforc\w*|poses?\b|requir\w*|nuance\w*|distinction\w*|dimension\w*|paradox\w*|conceptual\w*|"
    r"scaffold\w*|thesis|hypothes\w*|unresolved|underexplored|remain\w*|applies\b|extension\b)",
    re.IGNORECASE,
)
# Codex depth-gate iter-2 P1: a contentful CATEGORICAL header ("### Generative AI will replace all lawyers")
# must NOT pass as a structural label. A structural header is a NOUN-PHRASE section label with NO
# categorical CLAIM verb; a header carrying one is a mislabeled assertion => drops. (box2's real headers —
# "Mechanism Interpretation: …", "Positive Views: …", "Challenges: …", "Open Questions …" — carry none.)
_CLAIM_VERB_RE = re.compile(
    r"\b(?:will|shall|would|eliminat\w*|replac\w*|destroy\w*|caus\w*|guarantee\w*|prove[sd]?|proven|"
    r"cure[sd]?|kill\w*|ends?\b|end\s+of)\b",
    re.IGNORECASE,
)
# Codex/Fable depth-gate: a CRISP quantitative claim in ANY form — digit, spelled percent, spelled cardinal
# over a domain noun, a fraction "of all X", a "one in N" ratio, or a "millions of X" magnitude — is a
# numeric claim that must ground => NOT disclosable. Deliberately does NOT match SOFT quantifiers
# ("many/most/some workers") which are legitimate qualitative interpretive prose. Domain noun set is the
# labor-market subjects a proportion claim would quantify.
_QUANT_DOMAIN = r"(?:jobs|workers|occupations|tasks|employment|roles|people|firms|companies|households|professionals|positions)"
_QUANT_CLAIM_RE = re.compile(
    r"\bone\s+in\s+(?:a\s+)?(?:two|three|four|five|six|seven|eight|nine|ten|\d+)\b"          # one in five
    r"|\b(?:a|one|two|three|four)\s+(?:half|third|quarter|fifth|sixth|seventh|eighth|ninth|tenth)\b"  # a fifth / two thirds
    r"|\b(?:half|third|quarter|fifth|sixth|seventh|eighth|ninth|tenth)\s+of\s+(?:all\s+)?" + _QUANT_DOMAIN + r"\b"  # BARE "half of all jobs" / "quarter of workers"
    r"|\b(?:millions?|billions?|thousands?|hundreds?)\s+of\s+" + _QUANT_DOMAIN + r"\b"        # millions of workers
    r"|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
    r"sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|"
    r"hundred|thousand|million|billion)\b[\w\s-]{0,20}\b(?:of\s+(?:all\s+)?)?" + _QUANT_DOMAIN + r"\b",  # spelled N … jobs
    re.IGNORECASE,
)


def _build_pool_surnames(evidence_rows: "list[dict[str, Any]]") -> "set[str]":
    """Word-boundary TOKEN set of the pool's author/title words (len>=3), for the author-attribution guard.
    Token membership (not substring) so a fabricated 'Autor et al' can't pass via 'autor' ⊂ 'author'."""
    text = " ".join(
        f"{r.get('authors', '')} {r.get('title', '') or r.get('source_title', '')}"
        for r in (evidence_rows or [])
    ).lower()
    return set(_POOL_TOKEN_RE.findall(text))


def _is_disclosable_interpretation(sentence: str, pool_surnames: "set[str]") -> bool:
    """True iff an UNCITED synthesis sentence is safe to render under the disclosed analyst label — a HEDGED
    QUALITATIVE interpretation carrying NO ungrounded SPECIFIC claim. Faithfulness guards (applied to headers
    TOO): any decimal / percent / integer / year => a numeric claim that MUST ground => NOT disclosable; an
    author attribution with ANY surname absent from the pool token-set => a fabricated study => NOT
    disclosable. A structural section header (no number, no bad author) is disclosable. A NON-header sentence
    ALSO requires a HEDGE/INTERPRETIVE cue — a bare unhedged categorical assertion is NOT disclosable.
    §-1.3: hedged qualitative interpretation is disclosed under an honest 'not span-verified' label; numeric,
    named, and bare-categorical claims still drop."""
    raw = _strip_markers(sentence).strip()
    if not raw:
        return False
    is_header = raw.startswith("#")
    core = raw.lstrip("#").strip()
    if not core:
        return False
    # numeric guard — applies to HEADERS too (Codex P1-2): a number/percent/year must ground, never disclose.
    if _decimals(core):
        return False
    # ANY percent/percentage word is a quantitative claim that must ground — a robust catch-all covering
    # every digit AND spelled form ("40%" / "forty percent" / "fifteen percent"), ending the spelled-number
    # enumeration (Codex depth-gate iter-3/4). Real qualitative interpretation never states a bare percent.
    if "percent" in core.lower():
        return False
    # any CRISP quantitative claim without the word "percent" ("a fifth of all jobs", "one in five workers",
    # "millions of workers", "fifteen … jobs") — same numeric-claim class; soft quantifiers (many/most) pass.
    if _QUANT_CLAIM_RE.search(core):
        return False
    # author-attribution guard — EVERY named surname (first + co-authors) must be a pool TOKEN (Codex/Fable P2).
    for m in _AUTHOR_ATTR_RE.finditer(core):
        if any(name.lower() not in pool_surnames for name in _SURNAME_RE.findall(m.group(0))):
            return False
    if is_header:
        # Codex iter-2 P1: a structural section-label header is disclosable, but a contentful CATEGORICAL
        # header ("### Generative AI will replace all lawyers") is a mislabeled assertion => drops.
        return not bool(_CLAIM_VERB_RE.search(core))
    # Codex/Fable P1-1: a NON-header interpretive sentence must actually be HEDGED interpretation, not a bare
    # unhedged categorical assertion.
    return bool(_INTERPRETIVE_CUE_RE.search(core))

# A confidence marker is appended ONCE per sentence; this guards against a double-append when the
# function is (defensively) called twice on already-labeled prose.
_ALREADY_LABELED_MARKER = "[confidence:"


def deviation_check_enabled() -> bool:
    """True iff the default-ON B13 deviation check is active. Requires BOTH the fine flag
    (``PG_ANALYST_SYNTHESIS_DEVIATION_CHECK``, default ON) AND the coarse analyst-layer flag
    (``PG_SWEEP_ANALYST_SYNTHESIS``, default ON) to be on."""
    fine_on = os.environ.get(_ENV_ENABLED, "1").strip().lower() not in _OFF_VALUES
    coarse_on = os.environ.get(_ENV_ANALYST_KILL, "1").strip() in ("1", "true", "True")
    return fine_on and coarse_on


def _max_inflight() -> int:
    try:
        value = int(os.environ.get(_ENV_MAX_INFLIGHT, _DEFAULT_MAX_INFLIGHT) or _DEFAULT_MAX_INFLIGHT)
    except (TypeError, ValueError):
        return _DEFAULT_MAX_INFLIGHT
    return value if value >= 1 else _DEFAULT_MAX_INFLIGHT


def _deadline_s() -> float:
    try:
        value = float(os.environ.get(_ENV_DEADLINE_S, _DEFAULT_DEADLINE_S) or _DEFAULT_DEADLINE_S)
    except (TypeError, ValueError):
        return _DEFAULT_DEADLINE_S
    return value if value > 0 else _DEFAULT_DEADLINE_S


def _resolve_span_for_evidence_id(
    evidence_id: str, evidence_rows: list[dict[str, Any]], *, full_text: bool = False
) -> str:
    """Resolve an evidence_id to its cited span text (``direct_quote`` first, then ``statement``).
    Returns ``""`` when the id is not in the pool or carries no span text. wave-2 (#1370): ``full_text``
    widens the resolved text to the source's TRUSTED evidence-BODY fields (``direct_quote`` + ``statement``)
    so a number/word that lives in the source body but not the exact quote slice grounds — the box2
    over-drop where a real Brynjolfsson/Eloundou number sat in the source ``statement`` but not the exact
    quote slice, so a grounded synthesis sentence was dropped. Codex depth-gate P1: ``title``/``snippet``
    (retrieval METADATA) are DELIBERATELY EXCLUDED so a number that appears only incidentally in a search
    snippet or title can NEVER ground a synthesis sentence — the anti-fabrication floor stays honest."""
    for row in evidence_rows or []:
        rid = str(row.get("evidence_id") or row.get("id") or "")
        if rid and rid == evidence_id:
            if full_text:
                return " ".join(
                    str(row.get(k, "") or "") for k in ("direct_quote", "statement")
                ).strip()
            return str(row.get("direct_quote") or row.get("statement") or "")
    return ""


def _resolve_sentence_span(
    sentence: str,
    bibliography: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    *,
    full_text: bool = False,
) -> str:
    """Concatenate the cited spans for ALL ``[N]`` markers in ``sentence``. ``N`` indexes the
    bibliography 1-based -> ``bibliography[N-1].evidence_id`` -> the evidence row's span. Returns
    ``""`` when the sentence carries NO resolvable ``[N]`` span (=> the caller labels BUCKET_NO_SOURCE).
    wave-2 (#1370): ``full_text`` resolves each cited source to its WHOLE text (see
    ``_resolve_span_for_evidence_id``) so a synthesis sentence grounds against the whole-basket union,
    not the narrow direct_quote slice. PURE (no I/O)."""
    spans: list[str] = []
    for m in _NUMBERED_RE.finditer(sentence):
        try:
            n = int(m.group(1))
        except (TypeError, ValueError):
            continue
        if n < 1 or n > len(bibliography or []):
            continue
        entry = bibliography[n - 1]
        eid = str(entry.get("evidence_id") or "")
        if not eid:
            continue
        span = _resolve_span_for_evidence_id(eid, evidence_rows, full_text=full_text)
        if span:
            spans.append(span)
    return "\n".join(spans)


def _resolve_sentence_ev_rows(
    sentence: str,
    bibliography: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve the EVIDENCE ROW dict for every ``[N]`` marker in ``sentence``. ``N`` indexes the
    bibliography 1-based -> ``bibliography[N-1].evidence_id`` -> the matching evidence row. Returns the
    list of cited rows (deduped by evidence_id, order-preserving) so the D3 frozen-engine re-pass can
    build a real ``[#ev:id:start-end]`` provenance token per cited source. Rows with no span text are
    skipped. PURE (no I/O)."""
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for m in _NUMBERED_RE.finditer(sentence):
        try:
            n = int(m.group(1))
        except (TypeError, ValueError):
            continue
        if n < 1 or n > len(bibliography or []):
            continue
        eid = str((bibliography[n - 1] or {}).get("evidence_id") or "")
        if not eid or eid in seen:
            continue
        for row in evidence_rows or []:
            rid = str(row.get("evidence_id") or row.get("id") or "")
            if rid and rid == eid:
                if str(row.get("direct_quote") or row.get("statement") or "").strip():
                    seen.add(eid)
                    rows.append(row)
                break
    return rows


def _frozen_engine_verifies_sentence(
    base_sentence: str, cited_rows: list[dict[str, Any]]
) -> bool:
    """D3 P0 (#1344) — re-pass a promoted synthesis sentence through the FROZEN faithfulness engine.

    Codex iter-4 P0: the analyst-synthesis writer cites by ``[N]`` bibliography markers, so the
    per-sentence ``strict_verify`` / NLI entailment gate never saw it — promoted synthesis prose entered
    the scored body without the same provenance gate every body claim clears. This function CLOSES that
    hole: it deterministically rebuilds a real ``[#ev:<key>:<start>-<end>]`` provenance token for EACH
    cited source (the full cited span) and calls the UNCHANGED ``verify_sentence_provenance`` — the exact
    strict_verify (numeric-in-span + >=2 content-word overlap + percent-role + trial-name +
    overstatement) AND NLI-entailment engine every body claim passes. The sentence is admissible to the
    body ONLY if the frozen engine returns ``is_verified``.

    Synthetic token-safe keys (``s0``, ``s1`` ...) are used because a real evidence_id may contain
    characters ``_PROVENANCE_TOKEN_RE`` ([A-Za-z0-9_]+) rejects; the key identity is irrelevant to the
    engine (it grounds against the SPAN TEXT, keyed by the token's id in the pool). The full evidence row
    is carried into the pool (so the engine's shell / trial-name / attribution legs read real fields);
    only ``direct_quote`` is pinned to the resolved span text so the span offsets are exact.

    The engine is NOT modified — this is an ADDITIVE re-pass on top of the frozen gate. FAIL-CLOSED: any
    resolution / engine fault returns ``False`` (the sentence drops from the body), never a silent True."""
    if not cited_rows:
        return False
    try:
        evidence_pool: dict[str, dict[str, Any]] = {}
        token_parts: list[str] = []
        for idx, row in enumerate(cited_rows):
            span = str(row.get("direct_quote") or row.get("statement") or "")
            if not span.strip():
                continue
            key = f"s{idx}"
            pool_row = dict(row)
            pool_row["direct_quote"] = span
            evidence_pool[key] = pool_row
            token_parts.append(f"[#ev:{key}:0-{len(span)}]")
        if not evidence_pool:
            return False
        # Strip the writer's [N] / [confidence:] brackets from the prose BEFORE appending the real
        # provenance tokens, so the engine reads the claim prose (never a bracket digit as a claim
        # number) plus exactly the reconstructed [#ev] tokens.
        prose = _strip_markers(base_sentence).strip()
        if not prose:
            return False
        converted = f"{prose} {' '.join(token_parts)}"
        result = verify_sentence_provenance(converted, evidence_pool)
        return bool(getattr(result, "is_verified", False))
    except Exception as exc:  # fail-closed: an engine/wiring fault DROPS the sentence, never admits it
        logger.warning(
            "[analyst_deviation] D3 frozen-engine re-pass faulted (fail-closed DROP): %s", exc,
        )
        return False


def promote_synthesis_entailment_finding(
    audit_sentence: str, cited_rows: "list[dict[str, Any]]", *, entails_fn=None
) -> bool:
    """I-deepfix-006-compose C3 — the ENTAILMENT analog of the D3 ``_frozen_engine_verifies_sentence``
    promote hook, living beside it in the analyst module. A cross-source SYNTHESIS finding is a
    PARAPHRASE that fuses several corroborating spans, so the D3 verbatim ``_span_grounds_sentence`` leg
    (>=2 content-word overlap) wrongly drops it. This hook instead confirms the finding is (a) number-
    grounded in the union of its cited spans AND (b) ENTAILED by that union — delegating to the C1
    ``synthesis_entailment_verify.entailment_grounds_sentence`` (the SAME numeric + directional-NLI legs
    the C1 verify path uses). Returns True => the finding may be PROMOTED into the D8 4-role input set;
    a NON-entailed / number-mismatched finding => False (not promoted). FAIL-CLOSED on a wiring fault
    (a missing module / import error returns False, never a silent True)."""
    if not cited_rows:
        return False
    try:
        from src.polaris_graph.synthesis.synthesis_entailment_verify import (
            entailment_grounds_sentence,
        )
    except Exception as exc:  # pragma: no cover — synthesis_entailment_verify is stable in-tree
        logger.warning("[analyst_deviation] C3 entailment promote hook unavailable (fail-closed): %s", exc)
        return False
    return bool(entailment_grounds_sentence(audit_sentence, cited_rows, entails_fn=entails_fn))


def _default_sentinel_judge() -> "Callable[[str, str], bool]":
    """Build the real groundedness judge: the certified MiniMax-M2 Sentinel decomposition (a SECOND
    family vs the GLM/DeepSeek writer, so two-family holds). Returns a ``judge_fn(claim, span) -> bool``
    where True == the span SUPPORTS the claim. Resolved LAZILY so importing this module never
    constructs a transport. FAIL-CLOSED: any construction / call failure surfaces as ``False`` (=>
    BUCKET_LOW), never a silent True."""
    def _judge(claim: str, span: str) -> bool:
        if not span.strip():
            return False
        try:
            from src.polaris_graph.roles.sentinel_adapter import (
                _configured_sentinel_slug,
                run_sentinel,
            )
            from src.polaris_graph.roles.role_transport import EvidenceDocument
            from src.polaris_graph.roles.openrouter_role_transport import (
                OpenRouterRoleTransport,
                _default_role_http_client,
            )
            from src.polaris_graph.roles.sentinel_contract import SentinelVerdict
        except Exception as exc:  # pragma: no cover — wiring resolved at runtime on the paid path
            logger.warning("[analyst_deviation] sentinel imports unavailable (fail-closed LOW): %s", exc)
            return False
        try:
            slug = _configured_sentinel_slug()
            if not slug:
                logger.warning("[analyst_deviation] no Sentinel slug configured (fail-closed LOW)")
                return False
            transport = OpenRouterRoleTransport(_default_role_http_client())
            result, _records = run_sentinel(
                transport,
                claim,
                [EvidenceDocument(doc_id="span", text=span)],
                model_slug=slug,
            )
            # GROUNDED + a clean parse == supported. UNGROUNDED OR a fail-closed parse == NOT supported
            # (BUCKET_LOW). NEVER trust a non-clean parse as supported (lethal-inversion guard).
            return bool(result.verdict == SentinelVerdict.GROUNDED and result.parsed_ok)
        except Exception as exc:  # transport flap / cap-adjacent / parse error -> fail-closed LOW
            logger.warning("[analyst_deviation] sentinel call failed (fail-closed LOW): %s", exc)
            return False
    return _judge


def screen_synthesis_against_baskets(
    text: str,
    bibliography: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    *,
    judge_fn: "Callable[[str, str], bool] | None" = None,
) -> "tuple[str, dict[str, int]]":
    """Bring the analyst-synthesis layer UNDER the faithfulness engine. Returns ``(body_text, telemetry)``.

    Two modes, one gate flag (``PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED``):

    * D3 FAIL-CLOSED (promote flag ON) — the gate that lets the analyst layer turn ON safely. A
      synthesis sentence renders in ``body_text`` ONLY if it passes BOTH legs of the frozen engine —
      the deterministic span-grounding leg (``_span_grounds_sentence``: numbers + >=2 content-word
      overlap vs the cited span) AND the D8/NLI groundedness judge. A passing sentence is
      KEEP-and-PROMOTE'd (BUCKET_MODERATE). A sentence that FAILS either leg — ungrounded, no-source,
      or judge-fault — is DROPPED from ``body_text`` (fail-closed) and surfaced only in the drop
      telemetry + a fail-LOUD log, NEVER rendered as a hedged body claim.

    * LEGACY ADVISORY (promote flag OFF, default) — byte-identical KEEP-and-LABEL: no-source sentences
      get a BUCKET_NO_SOURCE marker, judge-unsupported sentences a BUCKET_LOW marker, supported
      sentences pass bare. Nothing is dropped.

    For each synthesis sentence the ``[N]`` markers resolve to cited evidence spans. ``judge_fn``
    (``(claim, span) -> bool``, True == supported) is INJECTABLE for offline tests; the default lazily
    builds the certified-Sentinel judge. FAIL-CLOSED on any judge fault (LABEL LOW in legacy mode; DROP
    in D3 mode — both the safe direction). NEVER touches ``strict_verify`` / NLI / 4-role (this gate is
    ADDED on top of the frozen engine). Returns the input unchanged (telemetry zeroed) when disabled."""
    telemetry = {
        "synthesis_deviation_labeled_count": 0,
        "synthesis_deviation_unresolved_count": 0,
        "synthesis_deviation_promoted_count": 0,
        "synthesis_deviation_dropped_count": 0,
    }
    if not text or not text.strip() or not deviation_check_enabled():
        return text, telemetry

    # I-deepfix-001 M6 (Layer 2): default-OFF PROMOTE mode — a grounded sentence is positively labeled
    # (KEEP-and-PROMOTE) instead of passing bare. Resolved once; OFF => grounded sentences stay bare.
    promote = promote_grounded_enabled()

    if judge_fn is None:
        judge_fn = _default_sentinel_judge()

    sentences = split_into_sentences(text)
    if not sentences:
        return text, telemetry

    # Resolve each sentence's cited span ONCE (pure). A sentence with no resolvable span never calls
    # the judge (it is a BUCKET_NO_SOURCE label, not an UNSUPPORTED verdict). Span resolution reads the
    # ``[N]`` markers, which are untouched by the confidence-marker strip below.
    spans = [_resolve_sentence_span(s, bibliography, evidence_rows) for s in sentences]
    # I-deepfix-001 wave-2 (#1370) basket faithfulness (§-1.3): in basket mode, ALSO resolve each sentence's
    # cited sources to their WHOLE-basket full text (direct_quote + statement + title + snippet), unioned
    # across all cited [N], so a synthesis sentence whose grounded numbers/words live anywhere in its cited
    # sources is not falsely dropped for citing only the narrow direct_quote slice (box2 over-drop; harness
    # T2). A number in NO cited source still drops (harness T3). The legacy 4-leg path keeps the narrow
    # `spans`. Default-ON within basket mode; PG_ANALYST_SYNTHESIS_BASKET_FULLTEXT=0 reverts to the narrow union.
    basket_spans = (
        [_resolve_sentence_span(s, bibliography, evidence_rows, full_text=True) for s in sentences]
        if (basket_mode_enabled() and _basket_fulltext_enabled())
        else spans
    )
    # wave-2 (#1370) DEPTH disclosed-analyst layer: computed ONCE (not per-sentence). When ON, an uncited
    # hedged QUALITATIVE interpretive sentence renders under the analyst disclosure instead of dropping.
    _disclose_analyst = basket_mode_enabled() and _disclosed_analyst_enabled()
    _pool_surnames = _build_pool_surnames(evidence_rows) if _disclose_analyst else set()
    # D3 P0 (#1344): the cited EVIDENCE ROWS per sentence, for the frozen-engine re-pass in PROMOTE
    # mode (a real [#ev:id:start-end] token is rebuilt per cited row -> verify_sentence_provenance).
    # Resolved once (pure); used only in the promote branch below.
    cited_rows_per_sentence = [
        _resolve_sentence_ev_rows(s, bibliography, evidence_rows) for s in sentences
    ]

    # I-deepfix-001 D3 P1 (#1344): screen the BARE prose. A pre-labeled sentence (already carrying a
    # ``[confidence:...]`` marker) has that marker stripped so the judge + span-grounding legs see the
    # claim itself, never a self-asserted confidence tag. For an un-labeled sentence this is a no-op
    # (byte-identical). In PROMOTE mode the stripped form is what re-enters the gate and is re-labeled;
    # the legacy path still short-circuits on the ORIGINAL sentence (idempotent keep-unchanged).
    screen_sentences = [_strip_confidence_markers(s) for s in sentences]

    # BOUNDED-PARALLEL groundedness for the sentences that DO resolve a span (never a serial unbounded
    # loop). A per-future deadline fail-CLOSES to "not supported" (=> BUCKET_LOW).
    supported: dict[int, bool] = {}
    judge_indices = [i for i, sp in enumerate(spans) if sp.strip()]
    if judge_indices:
        deadline = _deadline_s()
        # Codex wave-2 P1 (hang class): the judge futures run CONCURRENTLY in the
        # pool, so the batch is bounded by ONE TOTAL wall deadline, never the sum of
        # per-future deadlines. AND the pool is shut down with wait=False +
        # cancel_futures=True so a Sentinel worker still stuck in a slow role-
        # transport call is ABANDONED — the `with`-block shutdown(wait=True) would
        # otherwise re-block on the timed-out worker and stall the synthesis return.
        # Every unresolved sentence fail-CLOSES to LOW (not supported).
        pool = ThreadPoolExecutor(max_workers=_max_inflight())
        try:
            futures = {
                pool.submit(judge_fn, screen_sentences[i], spans[i]): i for i in judge_indices
            }
            _end = time.monotonic() + deadline
            for fut, i in futures.items():
                _remaining = max(0.0, _end - time.monotonic())
                try:
                    supported[i] = bool(fut.result(timeout=_remaining))
                except (_FutureTimeout, Exception) as exc:  # fail-closed LOW on any judge fault
                    logger.warning(
                        "[analyst_deviation] groundedness judge fault on sentence %d "
                        "(fail-closed LOW): %s", i, exc,
                    )
                    supported[i] = False
        finally:
            # Never block the synthesis return on a stuck judge worker.
            pool.shutdown(wait=False, cancel_futures=True)
        # Any sentence whose future never resolved within the TOTAL deadline is
        # fail-closed to LOW (covers the case where the loop exhausted the wall
        # budget before reaching a later future).
        for i in judge_indices:
            supported.setdefault(i, False)

    out_sentences: list[str] = []
    dropped: list[str] = []
    for i, sentence in enumerate(sentences):
        has_span = bool(spans[i].strip())

        if promote:
            # ── D3 FAIL-CLOSED gate ──────────────────────────────────────────────────────────────
            # A synthesis sentence enters the SCORED BODY only if it passes ALL THREE legs of the
            # FROZEN faithfulness engine (Codex iter-4 P0 — the promoted sentence must clear the SAME
            # gate every body claim clears, not a lone Sentinel judge):
            #   (1) the REAL ``verify_sentence_provenance`` re-pass (_frozen_engine_verifies_sentence):
            #       a genuine ``[#ev:id:start-end]`` provenance token is rebuilt for each cited source
            #       and the UNCHANGED strict_verify (numeric-in-span + >=2 content-word overlap +
            #       percent-role + trial-name + overstatement) AND NLI-entailment engine must return
            #       is_verified. THIS is the leg that was missing — a [N]-cited synthesis sentence now
            #       carries and clears real [#ev] provenance exactly like a body claim;
            #   (2) the deterministic span-grounding pre-check (_span_grounds_sentence — a conservative
            #       superset guard, kept so a sentence can never be promoted on the judge alone), AND
            #   (3) the D8/NLI groundedness judge (supported[i], the 4-role Sentinel leg).
            # Anything else — no cited span, engine says unverified, judge says unsupported, or a
            # judge/engine fault (fail-closed to False) — is DROPPED from the body and collected for the
            # fail-loud audit.
            #
            # P1 (#1344): a PRE-LABELED sentence does NOT get an idempotent free pass here — it is
            # re-screened on its bare prose (``base`` = confidence-marker stripped). An ungrounded
            # sentence that arrived already carrying a ``[confidence: low]`` tag is therefore DROPPED,
            # not admitted as a hedged body claim. A grounded one is re-promoted with a fresh moderate
            # marker on the stripped base (never a double marker).
            base = screen_sentences[i]
            if basket_mode_enabled():
                # P1 basket mode: KEEP grounded cross-source synthesis. The deterministic anti-fabrication
                # floor (numbers-in-union + >=2 content-word overlap vs the UNION of cited spans) is the
                # faithfulness gate; the extractive single-span ENTAILMENT requirement is dropped (it
                # over-kills interpretive synthesis). Fabricated numbers + no-citation sentences still drop.
                # wave-2 (#1370): ground against the WHOLE-basket FULL-TEXT union of the cited sources
                # (basket_spans[i]) so a real number living in a source's statement/title — not the narrow
                # quote slice — is not falsely dropped (box2 over-drop of the cross-source analytical layer).
                _bspan = basket_spans[i]
                grounded = bool(_bspan.strip()) and _span_grounds_sentence(base, _bspan)
            else:
                grounded = (
                    has_span
                    and supported.get(i, False)
                    and _span_grounds_sentence(base, spans[i])
                    and _frozen_engine_verifies_sentence(base, cited_rows_per_sentence[i])
                )
            if grounded:
                marker = claim_labeler.render_confidence_marker(claim_labeler.BUCKET_MODERATE)
                out_sentences.append(f"{base} {marker}")
                telemetry["synthesis_deviation_promoted_count"] += 1
            elif _disclose_analyst and _is_disclosable_interpretation(base, _pool_surnames):
                # wave-2 (#1370) DEPTH — verify-after-compose = LABEL, never DELETE: a hedged, uncited,
                # PURELY-QUALITATIVE interpretive sentence (the analytical connective tissue the composer is
                # DESIGNED to write uncited) renders under the analyst-layer DISCLOSURE instead of dropping.
                # A fabrication (uncited + a specific number, or a named study absent from the pool) does NOT
                # reach here — _is_disclosable_interpretation returns False for it — so it still drops below.
                marker = claim_labeler.render_confidence_marker(claim_labeler.BUCKET_NO_SOURCE)
                out_sentences.append(f"{base} {marker}")
                telemetry["synthesis_deviation_disclosed_count"] = (
                    telemetry.get("synthesis_deviation_disclosed_count", 0) + 1
                )
            else:
                dropped.append(sentence)
                telemetry["synthesis_deviation_dropped_count"] += 1
            continue

        # ── LEGACY ADVISORY KEEP-and-LABEL (promote OFF, default) — byte-identical ────────────────
        # Idempotent: never double-label an already-labeled sentence (advisory mode only; the promote
        # gate above deliberately re-screens pre-labeled sentences rather than pass them through).
        if _ALREADY_LABELED_MARKER in sentence:
            out_sentences.append(sentence)
            continue
        if not has_span:
            # No resolvable cited [N] span at all -> a genuinely uncited / unresolvable claim.
            marker = claim_labeler.render_confidence_marker(claim_labeler.BUCKET_NO_SOURCE)
            out_sentences.append(f"{sentence} {marker}")
            telemetry["synthesis_deviation_unresolved_count"] += 1
            continue
        if supported.get(i, False):
            out_sentences.append(sentence)  # supported -> KEEP unchanged
            continue
        # Cited span does NOT support the sentence (or the judge fail-closed) -> LABEL low, KEEP.
        marker = claim_labeler.render_confidence_marker(claim_labeler.BUCKET_LOW)
        out_sentences.append(f"{sentence} {marker}")
        telemetry["synthesis_deviation_labeled_count"] += 1

    if dropped:
        # Fail-LOUD: the dropped sentences never reach the scored body — surface them so a D3 drop is
        # visible in the run log (the typed non-answer audit trail), never a silent deletion.
        logger.warning(
            "[analyst_deviation] D3 fail-closed: DROPPED %d ungrounded/no-source synthesis sentence(s) "
            "from the scored body (retained only in this audit log, never rendered as a body claim): %s",
            len(dropped), dropped,
        )
    return " ".join(out_sentences), telemetry
