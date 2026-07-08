"""
Semantic topic-relevance gate — I-scope-001 (#1244).

WHY THIS EXISTS (grounded diagnosis, do not re-derive):
A consolidated drb_72 breadth run cited 76 distinct sources with 0
fabrication, but ~9 were contamination — including 4 OFF-TOPIC-but-CREDIBLE
journals (spinal-cord stimulation, blockchain-sustainability, etc.). The
tier system rates CREDIBILITY, not RELEVANCE, so a credible-but-irrelevant
journal passes the tier gate. The lexical/embedding relevance floor ALSO
fails: en.wikipedia.org scored 0.583 relevance (above the clean median
0.500) because contaminants share generic content words with on-topic
sources. So neither tier nor embedding similarity can separate
off-topic-credible from on-topic — a TOPIC gate (semantic ON/OFF judgement
on the research-question domain) is required.

This module is the pure, LLM-based topic gate. It is DEFAULT-OFF: the
orchestrator (run_honest_sweep_r3.py) only calls it when PG_SCOPE_TOPIC_GATE
is truthy, and passes the production LLM callable + batch size. Keeping all
batching / parsing / exemption logic here (pure) means the gate is fully
unit-testable with a stub `llm_callable`, with NO OpenRouter key required.

FAITHFULNESS LOCK: this gate is SELECTION-SIDE ONLY. It can only SUBTRACT a
candidate source from the pool handed to the generator; it NEVER edits a
sentence, span, or citation. strict_verify / the NLI entailment judge / the
4-role D8 audit / provenance are UNTOUCHED — every surviving sentence still
passes the identical faithfulness stack. Subtraction cannot fabricate.

FAIL-OPEN CONTRACT (LAW II — never drop on uncertainty):
The gate drops a source ONLY on an explicit, confident OFF verdict. It KEEPS
the source (fail-open) on:
  - any LLM exception,
  - a returned verdict count that does not match the requested count,
  - any unparseable / unrecognised verdict line,
  - an empty / missing title+snippet (nothing to judge on).
A marquee / required-entity anchor is NEVER dropped, regardless of verdict.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable

_LOGGER = logging.getLogger(__name__)

# Default batch size for PG_SCOPE_TOPIC_BATCH — how many sources are
# classified per LLM call. Bounds cost: one call covers up to this many
# sources. A small denominator keeps the prompt short + the parse simple.
_DEFAULT_TOPIC_BATCH = 25

# Cap on the title+snippet length fed per source so a batch prompt stays
# bounded even with long live-retriever statements.
_MAX_SNIPPET_CHARS = 320


def topic_gate_enabled() -> bool:
    """Kill-switch ``PG_SCOPE_TOPIC_GATE`` (default ON — I-deepfix-001 DEFER-1).

    Default flipped ``"0"->"1"`` (2026-06-30): the gate is the SEMANTIC
    discriminator the cite-surface off-topic suppression keys on (a lexical floor
    cannot separate on-topic from off-topic — disproven on drb_72). It is §-1.3
    keystone-compatible: the DEFAULT verdict is DEMOTE-not-DROP (every source stays
    in the pool, the confident-OFF ones carry the ``topic_offtopic_demoted``
    sidecar), so turning it ON adds a disclosed WEIGHT, never a hard filter. Set
    ``PG_SCOPE_TOPIC_GATE=0`` to restore the byte-identical legacy (gate never
    called) behaviour."""
    raw = os.environ.get("PG_SCOPE_TOPIC_GATE", "1").strip().lower()
    return raw not in ("0", "false", "no", "off", "")


def resume_run_topic_judge_enabled() -> bool:
    """Kill-switch ``PG_RESUME_RUN_TOPIC_JUDGE`` (default OFF — I-deepfix-001 wave-2).

    A RESUME normally SKIPS this gate (the orchestrator guards the call with
    ``not _resume_active`` because the corpus_snapshot is reloaded post-selection). That
    leaves every reloaded row UNJUDGED, so an off-topic source can leak into the finding
    surface. When this flag is set, the orchestrator ALSO runs the EXISTING
    :func:`classify_topic_relevance` on a resume, so the reloaded rows get a topic verdict
    stamped. Default OFF => the ``not _resume_active`` short-circuit holds => byte-identical
    (the judge is not run on a resume, exactly as before)."""
    raw = os.environ.get("PG_RESUME_RUN_TOPIC_JUDGE", "").strip().lower()
    return raw in ("1", "true", "on", "yes", "enabled")


def mark_topic_judge_ran() -> None:
    """Set the run-scoped signal ``PG_TOPIC_JUDGE_RAN=1`` the moment the topic judge has
    executed this run (fresh or the resume path opened by
    :func:`resume_run_topic_judge_enabled`). The downstream unjudged-topic quarantine
    (``weighted_enrichment.topic_judge_ran`` / ``partition_unjudged_topic_rows``) reads this
    to prove the judge ran — so a row that STILL lacks a verdict is a genuine leak
    (quarantinable), NEVER a legitimately-skipped-judge false positive. Process/run-scoped
    (each sweep is its own process); the quarantine ALSO derives the same fact from the data,
    so this write is the explicit belt to that suspenders."""
    os.environ["PG_TOPIC_JUDGE_RAN"] = "1"


def topic_gate_hard_drop_enabled() -> bool:
    """LEGACY escape hatch ``PG_SCOPE_TOPIC_GATE_HARD_DROP`` (default OFF).

    §-1.3 (WEIGHT, DON'T FILTER — the operator names the "scope hard-filter" as a
    BANNED anti-pattern; the ONLY hard gate is the faithfulness engine): a
    confident-OFF source is, by DEFAULT, KEPT in the pool and DEMOTED (disclosed
    as off-topic), NEVER hard-dropped. Topicality is a WEIGHT, not a DROP — the
    source still flows to composition where the UNCHANGED strict_verify / NLI /
    4-role faithfulness engine is the only gate. Set this flag truthy ONLY to
    restore the pre-I-deepfix-001 hard-drop (audit / reversal); the default
    keep-all + demote is the §-1.3-correct behavior."""
    raw = os.environ.get("PG_SCOPE_TOPIC_GATE_HARD_DROP", "0").strip().lower()
    return raw not in ("0", "false", "no", "off", "")


def topic_batch_size() -> int:
    """``PG_SCOPE_TOPIC_BATCH`` (default 25), the max sources per LLM call.
    A non-positive / unparseable value falls back to the default (FAIL-SAFE:
    a garbage batch size must never produce a zero-size loop)."""
    raw = os.environ.get("PG_SCOPE_TOPIC_BATCH", "").strip()
    if not raw:
        return _DEFAULT_TOPIC_BATCH
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_TOPIC_BATCH
    return value if value > 0 else _DEFAULT_TOPIC_BATCH


@dataclass
class TopicGateResult:
    """Return value of :func:`classify_topic_relevance`."""

    kept_rows: list[dict[str, Any]]
    dropped_rows: list[dict[str, Any]]
    dropped_titles: list[str] = field(default_factory=list)
    n_in: int = 0
    n_kept: int = 0
    n_dropped_offtopic: int = 0
    n_exempt: int = 0
    notes: list[str] = field(default_factory=list)
    # I-deepfix-001 (§-1.3 WEIGHT-not-FILTER): confident-OFF sources that were
    # KEPT-and-DEMOTED instead of hard-dropped (the DEFAULT). They remain in
    # ``kept_rows`` (the source flows to composition) but are disclosed here as
    # off-topic-demoted. Empty when the legacy hard-drop flag is set.
    demoted_rows: list[dict[str, Any]] = field(default_factory=list)
    demoted_titles: list[str] = field(default_factory=list)
    n_demoted_offtopic: int = 0


def _row_title_text(row: dict[str, Any]) -> str:
    """Title-like text accessor mirroring evidence_selector._row_title_text.

    Live evidence rows populate ``statement`` with ``cand.title[:300]`` (not
    ``title``). Precedence: explicit ``title`` > ``statement`` >
    ``source_title`` > "". Returns a plain string (never None)."""
    for key in ("title", "statement", "source_title"):
        v = row.get(key)
        if isinstance(v, str) and v:
            return v
    return ""


def _row_snippet_text(row: dict[str, Any]) -> str:
    """Short snippet for the topic judgement. Uses ``snippet`` /
    ``direct_quote`` (whichever is present), bounded to _MAX_SNIPPET_CHARS."""
    for key in ("snippet", "direct_quote", "summary"):
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()[:_MAX_SNIPPET_CHARS]
    return ""


def _row_is_marquee_anchor(row: dict[str, Any]) -> bool:
    """True iff the row is a marquee / required-entity anchor that must NOT be
    dropped. Mirrors evidence_selector._row_is_marquee_anchor (I-pipe-006
    #1231) — a truthy ``is_marquee`` / ``required_entity`` / ``anchor_seed`` /
    ``is_anchor`` / ``entity_anchor`` / ``marquee`` flag, OR a
    ``required_entity``/``anchor`` substring in ``seed_source`` /
    ``query_origin`` / ``seed_query_origin``."""
    if not isinstance(row, dict):
        return False
    for flag in ("is_marquee", "required_entity", "anchor_seed", "is_anchor",
                 "entity_anchor", "marquee"):
        if row.get(flag):
            return True
    seed_source = str(row.get("seed_source") or "").lower()
    if "required_entity" in seed_source or "anchor" in seed_source:
        return True
    for origin_key in ("query_origin", "seed_query_origin"):
        origin = str(row.get(origin_key) or "").lower()
        if "required_entity" in origin or "anchor" in origin:
            return True
    return False


def _build_batch_prompt(
    research_question: str,
    batch: list[tuple[int, str, str]],
) -> str:
    """Build a single ON/OFF-topic classification prompt for a batch of
    sources. ``batch`` is a list of (local_index, title, snippet). The LLM is
    asked to return exactly one line per source: ``<index>: ON`` or
    ``<index>: OFF``. Confident-OFF-only is enforced at parse time."""
    lines = [
        "You are a strict topic-relevance classifier for a research report.",
        "",
        f"RESEARCH QUESTION:\n{research_question.strip()}",
        "",
        # I-deepfix-001 FF4-ASPECT (v2, forensic-corrected): FACET-SCOPED rubric
        # (was entity-only) + a STRICT verdict-only output contract. An
        # entity-only "different subject?" prompt is structurally blind to a
        # same-entity / wrong-ASPECT source (e.g. a GenAI-in-education paper
        # grounding a GenAI-labor-market question): the shared entity satisfies
        # "not a different field" and the fail-open keeps it ON. The two-step
        # rubric below makes the model name the question's SUBJECT ENTITY *and*
        # its SPECIFIC ASPECT *silently* (internal reasoning only), then requires
        # a source to bear on BOTH. It is domain-agnostic (LAW VI — the aspect is
        # derived at runtime from the RESEARCH QUESTION; nothing domain-specific
        # is hardcoded) and preserves the explicit fail-open.
        #
        # FORENSIC ADJUSTMENT #2 (off-topic fix_change_needed): the entity+aspect
        # naming MUST stay INTERNAL and the output MUST be strictly one
        # `<index>: ON|OFF` line per source and nothing else. Inline reasoning on
        # a verdict line ("1: this is about L2 writing, OFF") is not recognised by
        # _parse_batch_verdicts (below, unchanged) -> count mismatch -> the WHOLE
        # batch fails OPEN, silently letting the off-aspect source survive. So the
        # output contract is hardened here rather than the parser being relaxed.
        "STEP 1 (do this SILENTLY — this reasoning must NOT appear anywhere in "
        "your output): read the RESEARCH QUESTION and name to yourself its two "
        "parts — the SUBJECT ENTITY it is about, and the SPECIFIC ASPECT it asks "
        "about that entity (the outcome, relation, sub-domain, use-case, or "
        "population the question is actually asking about).",
        "",
        "STEP 2 — for EACH numbered source below, mark it ON only if it plausibly "
        "bears on BOTH the subject entity AND that specific aspect. A source about "
        "the SAME entity but a DIFFERENT aspect / use-case / population than the "
        "question asks about is OFF-TOPIC — same subject, wrong question. A source "
        "about a clearly different subject entity (different field, disease, "
        "population) is also OFF-TOPIC.",
        "",
        "Example (domain-neutral): if the question is about entity X and aspect A, "
        "then a source about entity X but aspect B is OFF; a source about entity X "
        "and aspect A is ON.",
        "",
        # I-deepfix-001 (drb_72 forensic): the seminal on-topic papers were wrongly marked OFF
        # because the question text embeds a DATE window ("before June 2023") and the judge read a
        # post-cutoff date/marker in a snippet as a "different aspect". TOPICALITY IS DATE-BLIND.
        "TOPICALITY IS DATE-BLIND: a publication date — or ANY date in the research question — is "
        "NOT an aspect. NEVER mark a source OFF because of its publication date or a date range in "
        "the question; recency is a SEPARATE axis handled elsewhere. Judge ONLY subject-entity + "
        "aspect. An exposure / projection / potential-impact / early-evidence study of the "
        "question's aspect is ON (it bears on that aspect), not OFF.",
        "",
        "FAIL-OPEN: if you genuinely cannot tell whether the source addresses the "
        "question's specific aspect, mark it ON. When in doubt, answer ON.",
        "",
        "OUTPUT CONTRACT (strict — the parser accepts nothing else): OUTPUT ONLY "
        "THE VERDICT LINES, exactly one per source, each line EXACTLY in the form "
        "`<index>: ON` or `<index>: OFF`. Do NOT write the entity or aspect names, "
        "any reasoning, any explanation, or any other words — not on a verdict "
        "line and not anywhere else in the output.",
        "",
        "SOURCES:",
    ]
    for local_idx, title, snippet in batch:
        text = title.strip()
        if snippet:
            text = f"{text} — {snippet}" if text else snippet
        if not text:
            text = "(no title or snippet)"
        lines.append(f"{local_idx}: {text}")
    lines.append("")
    lines.append("VERDICTS (one `<index>: ON|OFF` line per source):")
    return "\n".join(lines)


def _parse_batch_verdicts(
    raw: str,
    expected_indices: list[int],
) -> dict[int, bool] | None:
    """Parse the LLM batch response into ``{local_index: is_offtopic}``.

    Returns None (FAIL-OPEN signal — keep the whole batch) when the parse is
    not exactly one recognised verdict per requested index. A recognised
    verdict line is ``<index>: ON`` or ``<index>: OFF`` (case-insensitive,
    tolerant of surrounding punctuation). Anything else => fail-open."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    verdicts: dict[int, bool] = {}
    wanted = set(expected_indices)
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or ":" not in stripped:
            continue
        idx_part, _, verdict_part = stripped.partition(":")
        idx_token = idx_part.strip().lstrip("-").strip()
        if not idx_token.isdigit():
            continue
        idx = int(idx_token)
        if idx not in wanted:
            continue
        verdict_token = verdict_part.strip().lower()
        # Confident ON / confident OFF only. Anything ambiguous is ignored
        # (so the count check below will trip fail-open).
        if verdict_token.startswith("on"):
            verdicts[idx] = False
        elif verdict_token.startswith("off"):
            verdicts[idx] = True
        # else: leave unset -> count mismatch -> fail-open
    if set(verdicts.keys()) != wanted:
        # Missing / extra / unparseable verdicts: keep the whole batch.
        return None
    return verdicts


def classify_topic_relevance(
    sources: list[dict[str, Any]],
    research_question: str,
    llm_callable: Callable[[str], str],
    *,
    batch_size: int | None = None,
    primary_trial_anchors: list[str] | None = None,
    anchor_predicate: Callable[[dict[str, Any]], bool] | None = None,
) -> TopicGateResult:
    """Drop sources CONFIDENTLY classified OFF-topic for the research question.

    Pure + side-effect-free (apart from logging): the caller supplies the LLM
    via ``llm_callable(prompt: str) -> str`` so this is fully unit-testable
    with a stub. Marquee / required-entity anchors are EXEMPT (never dropped).
    FAIL-OPEN: any LLM exception, count mismatch, or unparseable verdict keeps
    the whole batch. Drops ONLY on an explicit confident OFF verdict.

    Args:
        sources: evidence rows (selection-stage, post floor + dedup).
        research_question: the user's raw question (the topic anchor).
        llm_callable: synchronous ``str -> str`` LLM interface.
        batch_size: sources per LLM call (default :func:`topic_batch_size`).
        primary_trial_anchors: named-trial anchors; a row matching one is
            exempt (handled via ``anchor_predicate`` when supplied).
        anchor_predicate: optional extra "is this a primary anchor" test
            (the orchestrator passes the selector's anchor matcher so the
            exemption is identical to the floor stage). Marquee detection is
            always applied in addition.

    Returns:
        TopicGateResult with kept/dropped rows + honest telemetry.
    """
    n_in = len(sources)
    if n_in == 0:
        return TopicGateResult(
            kept_rows=[], dropped_rows=[], n_in=0, n_kept=0,
            n_dropped_offtopic=0, notes=["topic_gate: empty pool"],
        )
    if not (research_question or "").strip():
        # Nothing to anchor on — FAIL-OPEN, keep everything.
        return TopicGateResult(
            kept_rows=list(sources), dropped_rows=[], n_in=n_in,
            n_kept=n_in, n_dropped_offtopic=0,
            notes=["topic_gate: empty research_question — fail-open"],
        )

    size = batch_size if (batch_size and batch_size > 0) else topic_batch_size()

    def _is_exempt(row: dict[str, Any]) -> bool:
        if _row_is_marquee_anchor(row):
            return True
        if anchor_predicate is not None:
            try:
                return bool(anchor_predicate(row))
            except Exception:
                return False
        return False

    # Partition exempt rows out — they bypass classification entirely.
    exempt_rows: list[dict[str, Any]] = []
    judged_rows: list[dict[str, Any]] = []
    judged_meta: list[tuple[str, str]] = []  # (title, snippet) per judged row
    for row in sources:
        if _is_exempt(row):
            exempt_rows.append(row)
            continue
        title = _row_title_text(row)
        snippet = _row_snippet_text(row)
        if not title and not snippet:
            # Nothing to judge on -> keep (fail-open per-row).
            exempt_rows.append(row)
            continue
        judged_rows.append(row)
        judged_meta.append((title, snippet))

    # Confident-OFF verdicts are accumulated in the loop. The kept set is
    # computed once below preserving the caller's ORIGINAL order — critical
    # because `evidence_for_gen` arrives already ranked best-first (relevance x
    # authority) and there is NO re-rank between this gate and the generator.
    # Partitioning exempt/kept to the end would push high-value marquee / anchor
    # rows to the tail of the list the generator sees (a real regression on the
    # gate-ON acceptance path).
    #
    # I-deepfix-001 (§-1.3 WEIGHT, DON'T FILTER — the operator names the "scope
    # hard-filter" as a BANNED anti-pattern; the ONLY hard gate is the
    # faithfulness engine): a confident-OFF source is, BY DEFAULT, KEPT in the
    # pool and DEMOTED (disclosed off-topic via the ``topic_offtopic_demoted``
    # sidecar), NEVER hard-dropped. Topicality is a WEIGHT — the source still
    # flows to composition where the UNCHANGED strict_verify / NLI / 4-role
    # engine is the only gate. The legacy hard-drop is preserved behind
    # ``PG_SCOPE_TOPIC_GATE_HARD_DROP`` (audit / reversal). Order is unchanged in
    # BOTH modes (no tail-partition), so a demoted row stays best-first-ranked.
    hard_drop = topic_gate_hard_drop_enabled()
    rescue_on_stamp = os.environ.get("PG_TOPIC_GATE_RESCUE_ON_STAMP", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )
    offtopic_rows: list[dict[str, Any]] = []
    offtopic_titles: list[str] = []
    ontopic_rows: list[dict[str, Any]] = []  # I-deepfix-001: confident-ON, for the rescue False-stamp

    for start in range(0, len(judged_rows), size):
        end = min(start + size, len(judged_rows))
        batch_rows = judged_rows[start:end]
        batch_meta = judged_meta[start:end]
        batch = [
            (local_idx, batch_meta[local_idx][0], batch_meta[local_idx][1])
            for local_idx in range(len(batch_rows))
        ]
        expected = [b[0] for b in batch]
        prompt = _build_batch_prompt(research_question, batch)
        try:
            raw = llm_callable(prompt)
        except Exception as exc:  # FAIL-OPEN on any LLM error -> keep batch.
            _LOGGER.warning(
                "[scope] topic_gate batch LLM error — fail-open, keeping "
                "%d sources: %s", len(batch_rows), str(exc)[:200],
            )
            continue
        verdicts = _parse_batch_verdicts(raw, expected)
        if verdicts is None:  # FAIL-OPEN on count mismatch / unparseable.
            _LOGGER.warning(
                "[scope] topic_gate batch unparseable / count mismatch — "
                "fail-open, keeping %d sources", len(batch_rows),
            )
            continue
        for local_idx, row in enumerate(batch_rows):
            v = verdicts.get(local_idx)
            if v is True:  # confident OFF only
                offtopic_rows.append(row)
                # batch_meta is already the per-batch slice -> index locally.
                offtopic_titles.append(batch_meta[local_idx][0] or "(no title)")
            elif v is False:  # confident ON
                # I-deepfix-001 (drb_72 forensic): RESCUE semantics. Historically the gate wrote
                # ONLY True (never False), so a re-judge (PG_RESUME_RUN_TOPIC_JUDGE) could ADD demotes
                # but never CLEAR a stale bad stamp baked into the corpus_snapshot by an earlier run.
                # Stamping False on a confident-ON verdict lets a fixed-prompt re-judge un-bury the
                # seminal papers wrongly demoted upstream. Faithfulness-neutral: downstream
                # (_is_confirmed_offtopic keys on `is True`; is_topic_unjudged on `is not None`) already
                # handles False. Gated PG_TOPIC_GATE_RESCUE_ON_STAMP (default ON); OFF = byte-identical.
                ontopic_rows.append(row)

    if hard_drop:
        # LEGACY (explicit opt-in): hard-drop the confident-OFF set.
        _off_ids = {id(r) for r in offtopic_rows}
        kept_rows = [r for r in sources if id(r) not in _off_ids]
        dropped_rows, dropped_titles = offtopic_rows, offtopic_titles
        demoted_rows: list[dict[str, Any]] = []
        demoted_titles: list[str] = []
    else:
        # DEFAULT (§-1.3 keep-all + demote): KEEP every source (original order),
        # disclose the confident-OFF set as DEMOTED, and stamp a faithfulness-
        # neutral sidecar so a downstream weighter can sink it WITHOUT dropping.
        kept_rows = list(sources)
        for row in offtopic_rows:
            row["topic_offtopic_demoted"] = True
        # I-deepfix-001 (drb_72): RESCUE — stamp False on confident-ON rows so a fixed-prompt
        # re-judge CLEARS a stale bad True baked into the corpus_snapshot by an earlier run.
        # Gated PG_TOPIC_GATE_RESCUE_ON_STAMP (default ON); OFF => no False stamp = byte-identical.
        if rescue_on_stamp:
            for row in ontopic_rows:
                row["topic_offtopic_demoted"] = False
        dropped_rows, dropped_titles = [], []
        demoted_rows, demoted_titles = offtopic_rows, offtopic_titles

    verb = "dropped_offtopic" if hard_drop else "demoted_offtopic"
    notes = [
        f"topic_gate: in={n_in} kept={len(kept_rows)} "
        f"{verb}={len(offtopic_rows)} exempt={len(exempt_rows)} "
        f"batch_size={size}"
    ]
    if offtopic_titles:
        _LOGGER.info(
            "[scope] topic_gate %s %d off-topic source(s): %s",
            "DROPPED" if hard_drop else "DEMOTED(kept, disclosed)",
            len(offtopic_titles),
            "; ".join(t[:120] for t in offtopic_titles),
        )

    return TopicGateResult(
        kept_rows=kept_rows,
        dropped_rows=dropped_rows,
        dropped_titles=dropped_titles,
        n_in=n_in,
        n_kept=len(kept_rows),
        n_dropped_offtopic=len(dropped_rows),
        n_exempt=len(exempt_rows),
        notes=notes,
        demoted_rows=demoted_rows,
        demoted_titles=demoted_titles,
        n_demoted_offtopic=len(demoted_rows),
    )
