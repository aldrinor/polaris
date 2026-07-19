"""I-bug-105 — Analyst Synthesis (two-layer report contract).

Per Codex strategic-review iter 1 + I-bug-105 brief APPROVE:

POLARIS's verified core (the multi-section prose, all per-sentence
span-verified by the entailment gate) is the audit-grade differentiator.
But it is also short — ~14 verified sentences, ~974 words on a typical
clinical question — because strict_verify drops ~73% of attempted
sentences. Frontier DR systems (ChatGPT DR, Gemini DR) ship 4000-7000
words but without the audit guarantee.

This module ships the SECOND layer: an "Analyst Synthesis" pass that
takes the verified prose + the bibliography + the evidence pool and
writes 1500-3000 words of interpretive expert commentary. The synthesis:
  - is CLEARLY labeled in report.md (not span-verified)
  - hedges appropriately ("consistent with verified findings...",
    "the literature suggests...", "in clinical practice this profile
    is consistent with...")
  - cites sources via bibliography [N] markers
  - MUST NOT carry [#ev:...] tokens (those are the audit-grade signal;
    using them in synthesis would dilute their meaning) — enforced by
    a scrub guardrail in this module + a regression test
  - is OMITTED from the report when generation fails (no empty disclosure
    block per Codex iter-1 guidance)

The two-layer disclosure preserves POLARIS's faithfulness wedge while
materially closing the narrative_length gap to frontier DR.
"""

from __future__ import annotations

import logging
import os
import re
from collections import Counter
from typing import Any, Callable
from src.polaris_graph.settings import resolve

logger = logging.getLogger(__name__)


# D-1 / I-ready-017 (#1182): analyst-synthesis CONTENT token budget.
#
# The default writer (deepseek/deepseek-v4-pro per I-cd-009 Carney lock) is
# REASONING-FIRST: it emits 6k-42k+ reasoning tokens BEFORE the synthesis prose.
# The prior hardcoded `4000` ceiling starved the content phase, so
# finish_reason=length truncated mid-planning and the FX-01 (#1105)
# reasoning->content promotion guard correctly REFUSED to ship the scratchpad,
# omitting the synthesis. Per LAW VI this is a NAMED, env-overridable module
# constant (no magic number), defaulting generous so the writer has room to
# FINISH planning AND write the 1500-3000-word synthesis.
#
# IMPORTANT (scope honesty): openrouter_client clamps every reasoning-first
# request to PG_REASONING_FIRST_HARD_CAP (default 16384, DeepInfra's verified
# deepseek-v4-pro cap). So on the DEFAULT provider this constant above 16384 is
# forward-compat HEADROOM, not active room (>16384 clamps down to 16384; <16384
# floors UP to 16384). It only takes effect once an operator points the writer at
# a higher-tier endpoint AND raises PG_REASONING_FIRST_HARD_CAP above the model's
# reasoning burn. The truncation GUARD lives in openrouter_client's promotion
# path and is untouched here — we only widen the requested content budget.
PG_SECTION_MAX_TOKENS: int = int(os.getenv("PG_SECTION_MAX_TOKENS", "24000"))


# Disclosure preamble (Codex iter-1 suggested rewrite, verbatim).
ANALYST_SYNTHESIS_DISCLOSURE = (
    "This section is analyst synthesis: interpretive commentary based on "
    "the verified findings above and the cited evidence. Unlike the "
    "Verified Findings section, these sentences are not individually "
    "span-verified; use them as hedged context, not as audit-grade claims."
)


ANALYST_SYNTHESIS_SYSTEM_PROMPT = """You are an analyst writing the
"Analyst Synthesis" section of a research report. The earlier "Verified
Findings" section contains short, per-sentence span-verified prose. Your
job is to write a longer interpretive narrative that synthesizes those
verified findings with the broader evidence pool — the kind of expert
commentary a research analyst would write to contextualize the audit
core for the reader.

CORE RULES (NON-NEGOTIABLE):

1. **Cite by bibliography [N] markers, NEVER by [#ev:...] tokens.** The
   [#ev:...] tokens are POLARIS's audit-grade signal reserved for the
   Verified Findings section. Using them in synthesis would dilute their
   meaning. Only [1], [2], [3], etc. — bibliography numbers from the
   global bibliography list provided.

2. **Hedge appropriately when going beyond the verified core.** Use
   phrases like:
     - "Consistent with the verified findings above, ..."
     - "The literature broadly suggests ..."
     - "These results are typically interpreted as ..."
     - "In clinical practice, this profile is consistent with ..."
     - "While not directly span-verified, the evidence base suggests ..."
   Do NOT make declarative claims about specifics that go beyond what
   the cited evidence supports. The reader is depending on the hedge
   wording to know which claims are interpretive vs. audited.

3. **Do not introduce facts NOT supported by the evidence pool.** You
   have the same evidence rows the verified pipeline used. Synthesis is
   permitted to discuss implications, comparisons, mechanisms, clinical
   context, and trade-offs — but every concrete factual claim
   (numbers, study names, mechanisms, regulatory facts) MUST be
   traceable to the provided bibliography.

4. **Reference the Verified Findings.** Make the synthesis flow from
   the audit core: "The verified efficacy data show X; clinically, this
   is interpreted as ...". This makes the two-layer architecture
   readable as a single document.

STRUCTURE:

Organize the synthesis into 4-6 sub-sections (your choice based on the
question + verified prose):
  - "Mechanism interpretation"
  - "Clinical implications"
  - "Comparative considerations"
  - "Regulatory and practice context"
  - "Open questions and future directions"
  - (or others appropriate to the domain)

Use ### subheadings for each sub-section (NOT ## — those are reserved
for the parent section header that wraps the synthesis block). Total
length: 1500-3000 words.

OUTPUT: plain prose with [N] citation markers and ### subheadings. No
preamble, no sign-off, no [#ev:...] tokens anywhere. Do NOT emit ##
headers — the renderer wraps this prose under a single ## heading."""


# I-meta-002-q1d (#946): match BOTH the prefixed audit token `[#ev:<id>:<start>-<end>]` AND a bare
# `[ev_012]` / `[ev_012:1-5]` leak. The `[:_]` after `ev` is the guard: it requires `ev:`/`ev_` (optionally
# `#`-prefixed), so numeric `[N]` citations and ordinary bracketed words (`[event]`, `[evidence]`) are NOT
# matched. The synthesis layer must cite by bibliography `[N]` only; any ev-token there is a leak to scrub.
_EV_TOKEN_RE = re.compile(r"\[#?ev[:_][^\]]*\]")
# I-bug-108 iter-2 P0 fix: extend regex to catch malformed markers
# (negative numbers, leading zeros, whitespace) that pass through the
# original positive-integer-only pattern. Downstream PT12 parser may
# treat any of these as invalid; scrub them all to be safe.
_N_MARKER_RE = re.compile(r"\[(-?\d+)\]")
_MALFORMED_MARKER_RE = re.compile(r"\[\s*(-?\d+)\s*\]")


# I-bug-110: process-lifetime telemetry for synthesis [N] scrub.
# When the synthesis LLM hallucinates [N] markers beyond the
# bibliography size, _scrub_invalid_n_markers strips them at runtime.
# An operator monitoring synthesis quality wants two signals:
#   - synthesis_n_scrub_count: total markers scrubbed across this
#     process's lifetime (cumulative).
#   - synthesis_n_scrub_runs: number of synthesis calls that needed
#     ANY scrub (i.e., at least one invalid marker present).
# These mirror the entailment-judge telemetry pattern at
# polaris_graph.llm.entailment_judge._JUDGE_TELEMETRY.
_SYNTHESIS_TELEMETRY: dict[str, int] = {
    "synthesis_n_scrub_count": 0,
    "synthesis_n_scrub_runs": 0,
    # I-meta-002-q1d (#953 q1d-c, clinical-safety): redactions applied to the analyst evidence pool
    # by sanitize_evidence_text (§9.1.7 injection/delimiter defense) and qualitative-negation SAFETY
    # sentences DROPPED from the unverified synthesis output (the lethal fabrication class).
    "synthesis_evidence_redaction_count": 0,
    "synthesis_negation_dropped_count": 0,
    # I-deepfix-001 B13 (#1357): the deviation-check LABEL counts — synthesis sentences whose cited
    # span does NOT support them (labeled low confidence) and sentences whose [N] resolved NO span
    # (labeled no-source). KEEP-and-LABEL, never deleted — the analyst layer brought under the
    # faithfulness engine via the "verify AFTER compose = label, never hold" pattern.
    "synthesis_deviation_labeled_count": 0,
    "synthesis_deviation_unresolved_count": 0,
}


# I-meta-002-q1d (#953): qualitative-negation SAFETY screen for the UNVERIFIED analyst layer. A sentence
# carrying BOTH a negation cue AND a safety/clinical-consequence term is DROPPED fail-closed — the
# unverified layer must NOT assert the negation class already caught fabricating on a real smoke
# ("did not lead to discontinuation"). Pure regex, no network/LLM. Over-dropping is the SAFE direction
# (the span-verified core retains any real finding); false positives only remove an unverified sentence.
# Broad negation cues — bare `no`/`not`/`n't` subsume "did not"/"does not"/"not contraindicated"/etc.
# (fail-closed: over-matching only removes UNVERIFIED sentences). Codex diff-gate iter-1.
_NEGATION_CUE_RE = re.compile(
    r"(\bno\b|\bnot\b|\bnever\b|\bwithout\b|\babsent\b|\bnone\b|\bneither\b|\bnor\b"
    r"|n['’]t\b|\black(?:s|ed|ing)?\b|\bfree of\b|\bfail(?:s|ed)? to\b)",
    re.IGNORECASE,
)
# Safety / clinical-consequence terms WITH suffix handling (Codex diff-gate iter-1 P1: truncated stems
# wrapped by `\b` did NOT match "hospitalization"/"contraindicated"/"toxicity"/"pregnancy"/"teratogenic"
# — `\w*` restores the inflected/plural forms).
_SAFETY_TERM_RE = re.compile(
    r"(\bdiscontinu\w*|\badverse\b|\bcontraindicat\w*|\binteraction\w*|\bmortality\b|"
    r"\bdeaths?\b|\bfatal\w*|\bserious\b|\bhospitali\w*|\bwithdraw\w*|\btoxicit\w*|"
    r"\bside\s+effects?\b|\bharm\w*|\bwarning\w*|\bblack[-\s]?box\w*|\bpregnan\w*|"
    r"\bteratogen\w*|\brenal\b|\bhepatic\b)",
    re.IGNORECASE,
)
# Conservative sentence splitter: terminator + whitespace + a likely new-sentence/list start. A decimal
# ("0.3") has no whitespace after the dot so it never splits; common abbreviations are masked first.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[\d])")
_SYNTH_ABBREVIATIONS = ("e.g.", "i.e.", "etc.", "et al.", "vs.", "fig.", "no.", "approx.", "ca.", "dr.")
_SYNTH_ABBREV_RE = re.compile("|".join(re.escape(a) for a in _SYNTH_ABBREVIATIONS), re.IGNORECASE)
_SYNTH_PERIOD_MASK = "\x00"


def _split_sentences(line: str) -> list[str]:
    """Split one prose line into sentences, protecting abbreviation periods (no network)."""
    masked = _SYNTH_ABBREV_RE.sub(lambda m: m.group(0).replace(".", _SYNTH_PERIOD_MASK), line)
    parts = _SENTENCE_SPLIT_RE.split(masked)
    return [p.replace(_SYNTH_PERIOD_MASK, ".") for p in parts]


def _screen_qualitative_negations(text: str) -> tuple[str, int]:
    """Drop UNVERIFIED qualitative-negation SAFETY sentences from the analyst synthesis (fail-closed).

    Pure / no-network. Operates per LINE so markdown structure (### subheadings, blank lines, paragraph
    breaks) is preserved; only prose sentences matching BOTH a negation cue AND a safety term are removed.
    Returns (cleaned_text, dropped_count). Returns the input unchanged when nothing is dropped.
    """
    if not text or not text.strip():
        return text, 0
    out_lines: list[str] = []
    dropped = 0
    for line in text.split("\n"):
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            out_lines.append(line)  # preserve blank lines + headings verbatim
            continue
        kept: list[str] = []
        for sentence in _split_sentences(line):
            if _NEGATION_CUE_RE.search(sentence) and _SAFETY_TERM_RE.search(sentence):
                dropped += 1
                continue
            kept.append(sentence)
        out_lines.append(" ".join(s.strip() for s in kept if s.strip()))
    if dropped == 0:
        return text, 0
    cleaned = "\n".join(out_lines)
    return cleaned, dropped


# I-bug-111: WARN-level alert threshold per single scrub call. When
# synthesis hallucinates >5 [N] markers in ONE call, the bibliography
# rendering / synthesis prompt is likely degenerating (typical clean
# runs scrub 0; a healthy run with one stray hallucination scrubs 1-2).
# Operators see a distinct "synthesis_n_scrub_alert" log + the manifest
# bool flag below.
SYNTHESIS_SCRUB_ALERT_THRESHOLD = 5

_SYNTHESIS_SCRUB_ALERT_FIRED = False


def synthesis_scrub_alert_state() -> bool:
    """Return True if any scrub call in this process exceeded the
    alert threshold (`SYNTHESIS_SCRUB_ALERT_THRESHOLD`).

    Operator-facing: aggregators (sweep manifest writers) read this
    once at end-of-run and surface the bool as
    `manifest.synthesis_n_scrub_alert`. The flag is sticky across
    calls (true if any single call tripped it) — a transient spike
    in any one call is still worth surfacing.
    """
    return _SYNTHESIS_SCRUB_ALERT_FIRED


def reset_synthesis_scrub_alert() -> None:
    """Reset the sticky alert flag in-place. Tests + sweep
    orchestrators call this at start-of-run.
    """
    global _SYNTHESIS_SCRUB_ALERT_FIRED
    _SYNTHESIS_SCRUB_ALERT_FIRED = False


def get_synthesis_telemetry() -> dict[str, int]:
    """Snapshot of process-lifetime synthesis-scrub counters.

    Operator-facing: the existence of any scrub on a production run
    is a signal the synthesis prompt or bibliography rendering may
    be drifting. Aggregated trends should be tracked.
    """
    return dict(_SYNTHESIS_TELEMETRY)


def reset_synthesis_telemetry() -> None:
    """Zero all synthesis-telemetry counters in-place.

    Public so callers (sweep orchestrators, tests) can deliberately
    bound the counter window to a single run.
    """
    for key in _SYNTHESIS_TELEMETRY:
        _SYNTHESIS_TELEMETRY[key] = 0


def _scrub_invalid_n_markers(text: str, biblio_size: int) -> tuple[str, int]:
    """Remove [N] bibliography markers where N is invalid.

    Invalid means:
      - N > biblio_size (out-of-range hallucination)
      - N < 1 (zero, negative — bibliography indices start at 1)
      - whitespace-padded forms like [ 5 ] (parser-fragile)

    I-bug-108 P0 fix: the synthesis LLM occasionally hallucinates [N]
    indices beyond the bibliography. The downstream evaluator rule
    PT12 (rule_pt12_invalid_citation_marker) aborts the report when
    max_marker > evidence_pool size. Scrub them runtime so production
    runs don't abort. Returns (cleaned_text, num_scrubbed).

    Iter-2 P0 hardening per Codex review: also catch [-N], [ N ],
    [01], etc. — anything that looks like a citation marker but isn't
    a valid 1..biblio_size index.
    """
    scrubbed = 0

    def _replace(match: re.Match) -> str:
        nonlocal scrubbed
        try:
            n = int(match.group(1))
        except (ValueError, TypeError):
            scrubbed += 1
            return ""
        if n < 1 or n > biblio_size:
            scrubbed += 1
            return ""  # drop the invalid marker entirely
        # Also drop if the original raw form had padding/leading zero
        # (bibliography emits "[1]" not "[ 1 ]" or "[01]")
        raw = match.group(0)
        canonical = f"[{n}]"
        if raw != canonical:
            scrubbed += 1
            return ""
        return raw

    cleaned = _MALFORMED_MARKER_RE.sub(_replace, text)
    if scrubbed > 0:
        logger.warning(
            "[analyst_synthesis] scrubbed %d invalid [N] marker(s) "
            "(out-of-range OR malformed; biblio_size=%d) — "
            "synthesis LLM hallucinated indices",
            scrubbed, biblio_size,
        )
        # I-bug-110: increment process-lifetime telemetry counters.
        # synthesis_n_scrub_count is total marker count; synthesis_n_scrub_runs
        # is the number of synthesis calls that needed any scrub.
        _SYNTHESIS_TELEMETRY["synthesis_n_scrub_count"] += scrubbed
        _SYNTHESIS_TELEMETRY["synthesis_n_scrub_runs"] += 1
        # I-bug-111: trip the sticky alert flag on any high-scrub call.
        # Threshold = 5 markers in ONE call — typical healthy synthesis
        # scrubs 0; the I-bug-108 incident scrubbed 6 in one call,
        # validating this threshold empirically.
        if scrubbed > SYNTHESIS_SCRUB_ALERT_THRESHOLD:
            global _SYNTHESIS_SCRUB_ALERT_FIRED
            _SYNTHESIS_SCRUB_ALERT_FIRED = True
            logger.warning(
                "[analyst_synthesis] synthesis_n_scrub_alert: %d markers "
                "scrubbed in single call (threshold=%d). Synthesis "
                "prompt or bibliography rendering may be degenerating.",
                scrubbed, SYNTHESIS_SCRUB_ALERT_THRESHOLD,
            )
    return cleaned, scrubbed


def _scrub_ev_tokens(text: str) -> str:
    """Remove any ev-token ([#ev:...] OR bare [ev_NNN]) from synthesis output.

    Codex iter-1 P0: must be a runtime guardrail, not just a test.
    I-meta-002-q1d (#946): the original pattern matched only the prefixed
    [#ev:...] token; a bare [ev_012] leaked into a published report.md.
    Synthesis prose MUST NOT carry any ev-token — it cites by bibliography
    [N] markers only. If the LLM emits one anyway, scrub it and log a warning.
    """
    cleaned, n = _EV_TOKEN_RE.subn("", text)
    if n > 0:
        logger.warning(
            "[analyst_synthesis] scrubbed %d ev-token(s) ([#ev:...] or bare "
            "[ev_NNN]) from synthesis output — synthesis MUST cite by [N] only",
            n,
        )
    return cleaned


def _format_bibliography_for_prompt(bibliography: list[dict[str, Any]]) -> str:
    """Render the global bibliography as numbered [N] entries for the prompt.

    Mirrors the bibliography format the Verified Findings section already
    uses, so the synthesis cites the same [N] indices the audit core does.
    """
    lines = []
    for i, entry in enumerate(bibliography, start=1):
        title = entry.get("title") or "Untitled"
        url = entry.get("url") or ""
        tier = entry.get("tier") or ""
        tier_str = f" (tier {tier})" if tier else ""
        lines.append(f"[{i}] {title} — {url}{tier_str}")
    return "\n".join(lines)


def _format_evidence_pool_for_prompt(
    evidence_rows: list[dict[str, Any]],
    max_rows: int | None = None,
) -> str:
    """Render the evidence pool as <<<evidence:ev_X>>> blocks the LLM
    can read for context. Capped at max_rows to bound the prompt size.
    """
    # I-deepfix-001 P2 (box2): env-tunable so the synthesis writer can SEE enough evidence spans to cite
    # valid [N] indices instead of hallucinating out-of-range ones. LAW VI; default 30 = byte-identical.
    if max_rows is None:
        try:
            max_rows = int(resolve("PG_ANALYST_SYNTHESIS_EVIDENCE_MAX_ROWS") or "30")
        except (TypeError, ValueError):
            max_rows = 30
    # I-meta-002-q1d (#953 q1d-c): sanitize evidence text AND the id (§9.1.7 delimiter/injection defense)
    # BEFORE building the <<<evidence>>> blocks — the analyst layer previously passed RAW evidence,
    # letting content forge a closing/opening delimiter (the same defense the verified path already has).
    from src.polaris_graph.generator.provenance_generator import sanitize_evidence_text

    blocks = []
    total_redacted = 0
    for row in evidence_rows[:max_rows]:
        ev_id_raw = str(row.get("evidence_id") or row.get("id") or "ev_?")
        ev_id, ev_id_red = sanitize_evidence_text(ev_id_raw)
        quote_raw = (
            row.get("direct_quote")
            or row.get("statement")
            or ""
        )[:1200]
        quote, quote_red = sanitize_evidence_text(quote_raw)
        total_redacted += ev_id_red + quote_red
        # Use the SAME closing delimiter as the verified wrap (`<<<end_evidence>>>`) so a forged copy
        # inside evidence is in sanitize_evidence_text's redaction set (bare `<<<end>>>` was NOT).
        blocks.append(f"<<<evidence:{ev_id}>>>\n{quote}\n<<<end_evidence>>>")
    if total_redacted:
        _SYNTHESIS_TELEMETRY["synthesis_evidence_redaction_count"] += total_redacted
        logger.info(
            "[analyst_synthesis] sanitized analyst evidence pool: %d redactions", total_redacted
        )
    return "\n\n".join(blocks)


def _format_prior_verified_context(prior_verified_context: list[dict[str, Any]] | None) -> str:
    """Render the campaign KG-reuse advisory block (I-meta-002-q1d #948). Each item is a prior-VERIFIED
    claim that the MECHANICAL match-gate already confirmed is INDEPENDENTLY supported by THIS question's
    evidence (anchored to a CURRENT evidence id). Advisory only — the analyst still cites by [N] from the
    current bibliography; no prior evidence ids appear. Empty input → empty block (prompt byte-identical)."""
    items = [c for c in (prior_verified_context or []) if c.get("claim_text")]
    if not items:
        return ""
    lines = [
        "=== CROSS-QUESTION CONSISTENCY (advisory) ===\n",
        "These facts were VERIFIED on prior campaign questions AND are independently supported by THIS",
        "question's evidence pool. Prioritise them where relevant, but cite ONLY by [N] from the",
        "bibliography above (the matching current source); do NOT invent citations or reuse prior ids.\n",
    ]
    for c in items:
        lines.append(f"- {c['claim_text']}  (supported here by evidence {c.get('evidence_id', '')})")
    return "\n".join(lines) + "\n\n"


def _promote_mode_active() -> bool:
    """True iff the D3 fail-closed PROMOTE gate is active. Probes the deviation-check module's own
    ``promote_grounded_enabled`` (which requires the deviation check ON AND the promote flag ON); if
    that probe itself raises (e.g. the module failed to import — the very fault that trips the caller's
    fail-closed path), fall back to the RAW promote flag. Fail-closed is the safe direction whenever the
    promote gate was requested, so a probe failure must not silently choose the legacy keep path."""
    try:
        from src.polaris_graph.generator.analyst_synthesis_deviation_check import (
            promote_grounded_enabled as _pge,
        )
        return bool(_pge())
    except Exception:
        _off_values = {"", "0", "false", "off", "no", "disabled"}
        return (
            os.environ.get("PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED", "0").strip().lower()
            not in _off_values
        )


def _apply_synthesis_deviation_screen(
    cleaned: str,
    bibliography: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    deviation_judge_fn: "Callable[[str, str], bool] | None",
) -> str:
    """Run the B13/D3 deviation screen over the composed synthesis prose and return the screened text.

    A synthesis sentence whose cited ``[N]`` span does NOT support it is labeled (legacy advisory mode)
    or DROPPED (D3 promote mode). ``strict_verify`` is NOT touched — this is an additive gate on top of
    the frozen engine. Default-ON (``PG_ANALYST_SYNTHESIS_DEVIATION_CHECK``) + shares the coarse
    ``PG_SWEEP_ANALYST_SYNTHESIS`` kill-switch.

    I-deepfix-001 D3 P0 (#1344) FAIL-CLOSED: if the screen itself RAISES (wiring / import / checker
    fault) the synthesis was NEVER gated. Under promote mode returning the ungated ``cleaned`` would
    render UNGATED synthesis into the scored body — the fail-OPEN hole. So under promote mode a screen
    exception DROPS the whole synthesis block (returns ""); in legacy advisory mode the text ships
    UNLABELED (as before) with a fail-loud DISTINCT telemetry counter."""
    try:
        from src.polaris_graph.generator.analyst_synthesis_deviation_check import (
            screen_synthesis_against_baskets,
        )
        cleaned, _dev_tel = screen_synthesis_against_baskets(
            cleaned, bibliography, evidence_rows, judge_fn=deviation_judge_fn,
        )
        for _k, _v in _dev_tel.items():
            if _v:
                _SYNTHESIS_TELEMETRY[_k] = _SYNTHESIS_TELEMETRY.get(_k, 0) + _v
        if _dev_tel.get("synthesis_deviation_dropped_count"):
            # I-deepfix-001 D3 (#1344): fail-closed mode DROPPED ungrounded/no-source synthesis
            # sentences from the scored body (the module already fail-loud-logs the exact sentences).
            logger.warning(
                "[analyst_synthesis] D3 fail-closed: %d ungrounded/no-source synthesis sentence(s) "
                "DROPPED from the scored body (never rendered as a body claim); %d promoted grounded",
                _dev_tel.get("synthesis_deviation_dropped_count", 0),
                _dev_tel.get("synthesis_deviation_promoted_count", 0),
            )
        if _dev_tel.get("synthesis_deviation_labeled_count") or _dev_tel.get(
            "synthesis_deviation_unresolved_count"
        ):
            logger.info(
                "[analyst_synthesis] B13 deviation check labeled %d unsupported + %d unresolved "
                "synthesis sentence(s) (advisory KEEP-and-LABEL)",
                _dev_tel.get("synthesis_deviation_labeled_count", 0),
                _dev_tel.get("synthesis_deviation_unresolved_count", 0),
            )
        _rendered_any = _dev_tel.get("synthesis_deviation_disclosed_count") or _dev_tel.get(
            "synthesis_deviation_promoted_count"
        )
        if _rendered_any and cleaned.strip() and ANALYST_SYNTHESIS_DISCLOSURE[:40] not in cleaned:
            # wave-2 (#1370) DEPTH: prepend ANALYST_SYNTHESIS_DISCLOSURE whenever the analyst block renders
            # ANY content (Fable depth-gate b1: the PROMOTED analyst sentences also cleared only the
            # deterministic floor, not strict_verify entailment — the WHOLE analyst section is interpretive
            # and must always carry its section-level "interpretive commentary, not individually span-verified"
            # label; each disclosed sentence ALSO carries a per-sentence "shown unverified" marker). Guarded
            # against double-prepend.
            logger.info(
                "[analyst_synthesis] wave-2 DEPTH: analyst block rendered (%d promoted + %d disclosed "
                "interpretation sentence(s)); section disclosure prepended",
                _dev_tel.get("synthesis_deviation_promoted_count", 0),
                _dev_tel.get("synthesis_deviation_disclosed_count", 0),
            )
            cleaned = f"{ANALYST_SYNTHESIS_DISCLOSURE}\n\n{cleaned}"
        return cleaned
    except Exception as _dev_exc:  # the deviation check is ADDITIVE — never abort the report on it
        # A checker/wiring exception (distinct from an in-checker judge fault, which is already handled
        # LOW/DROP per-sentence) means the analyst layer was NOT screened. Fail-LOUD with a DISTINCT
        # telemetry counter so a wiring break is visible in the manifest, never mistaken for a clean run.
        _SYNTHESIS_TELEMETRY["synthesis_deviation_check_error_count"] = (
            _SYNTHESIS_TELEMETRY.get("synthesis_deviation_check_error_count", 0) + 1
        )
        if _promote_mode_active():
            # I-deepfix-001 D3 P0: under PROMOTE mode the synthesis is only admissible if it PASSED the
            # gate. It was never gated -> DROP the whole block (never render ungated synthesis).
            _SYNTHESIS_TELEMETRY["synthesis_deviation_promote_failclosed_drop_count"] = (
                _SYNTHESIS_TELEMETRY.get("synthesis_deviation_promote_failclosed_drop_count", 0) + 1
            )
            logger.error(
                "[analyst_synthesis] D3 PROMOTE fail-CLOSED: the deviation screen raised (%s) so the "
                "analyst synthesis was NEVER gated — DROPPING the whole synthesis block from the scored "
                "body (never render ungated synthesis under promote mode)",
                _dev_exc,
                exc_info=True,
            )
            return ""
        logger.error(
            "[analyst_synthesis] B13 deviation check FAILED (wiring/checker error — analyst layer "
            "ships UNLABELED in legacy advisory mode, faithfulness labels lost for this section; "
            "fail-loud telemetry emitted): %s",
            _dev_exc,
            exc_info=True,
        )
        return cleaned


# ─────────────────────────────────────────────────────────────────────────────
# I-deepfix-006 C5 — clean analyst-synthesis render (PG_SYNTH_RENDER_CLEAN, default ON)
# ─────────────────────────────────────────────────────────────────────────────
# De-clutters the rendered "Analyst Synthesis" block WITHOUT touching the frozen faithfulness engine
# or any claim. Two render-only edits:
#   (1) DEDUPE the DOUBLED disclosure. ``_apply_synthesis_deviation_screen`` prepends the
#       ``ANALYST_SYNTHESIS_DISCLOSURE`` INTO ``analyst_synthesis_text`` whenever the analyst block
#       renders, AND the sole report renderer (run_honest_sweep_r3.py ~L15436) ALSO emits that same
#       disclosure as the italic "## Analyst Synthesis" section preamble. Result in report.md: the
#       disclosure twice, back-to-back. This pass removes the IN-TEXT copy so the renderer's canonical
#       preamble is the single one. The section STAYS labeled interpretive (the renderer always adds
#       the preamble — it is the only consumer of ``analyst_synthesis_text`` — so the section is never
#       left unlabeled).
#   (2) LIFT the per-sentence ``[confidence: <bucket> — …]`` markers (appended by the B13/D3 deviation
#       check via ``claim_labeler.render_confidence_marker``) OUT of the prose into ONE compact
#       per-section confidence note (bucket counts). The section-level disclosure remains the binding
#       honesty signal; no claim is upgraded, none dropped — the labels are aggregated, not discarded.
# Faithfulness-neutral + render-only. Default-ON; OFF => byte-identical (returns the text unchanged);
# ON with an already-clean block (no in-text disclosure, no markers) is also byte-identical.
_RENDER_CLEAN_ENV = "PG_SYNTH_RENDER_CLEAN"
_RENDER_CLEAN_OFF_VALUES = ("0", "false", "off", "no")
# Mirrors analyst_synthesis_deviation_check._CONFIDENCE_MARKER_RE (leading whitespace + the bracket).
_RENDER_CLEAN_CONF_MARKER_RE = re.compile(r"[ \t]*\[confidence:[^\]]*\]")
# The bucket label is the first token after "[confidence:" up to the " — " separator; buckets are the
# claim_labeler VALID_BUCKETS (high / moderate / low / no-source-found — lowercase, may carry hyphens).
_RENDER_CLEAN_CONF_BUCKET_RE = re.compile(r"\[confidence:\s*([A-Za-z-]+)")
_RENDER_CLEAN_BUCKET_ORDER = ("high", "moderate", "low", "no-source-found")


def _render_clean_enabled() -> bool:
    """C5 kill-switch. Default-ON; OFF only for an explicit off-value (byte-identical legacy render)."""
    return (
        os.environ.get(_RENDER_CLEAN_ENV, "1").strip().lower()
        not in _RENDER_CLEAN_OFF_VALUES
    )


def _render_clean_synthesis(text: str) -> str:
    """Return the render-cleaned analyst-synthesis text (C5). See module block above.

    Pure, no-network, faithfulness-neutral. Returns the input UNCHANGED when the flag is OFF or when
    there is nothing to clean (no in-text disclosure copy AND no inline confidence markers)."""
    if not text or not text.strip() or not _render_clean_enabled():
        return text
    had_disclosure = ANALYST_SYNTHESIS_DISCLOSURE in text
    buckets = [b.lower() for b in _RENDER_CLEAN_CONF_BUCKET_RE.findall(text)]
    if not had_disclosure and not buckets:
        return text  # already clean -> byte-identical
    cleaned = text
    if had_disclosure:
        # Remove EVERY in-text copy (guarded ≤1 upstream, but be defensive) — the renderer re-adds one.
        cleaned = cleaned.replace(ANALYST_SYNTHESIS_DISCLOSURE, "")
    if buckets:
        cleaned = _RENDER_CLEAN_CONF_MARKER_RE.sub("", cleaned)
    # Tidy whitespace the strips left behind (trailing spaces, >2 consecutive blank lines, leading blanks).
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).lstrip("\n")
    if buckets:
        counts = Counter(buckets)
        ordered = [f"{counts[b]} {b}" for b in _RENDER_CLEAN_BUCKET_ORDER if counts.get(b)]
        for b in counts:  # any non-standard label -> keep it, appended after the known order
            if b not in _RENDER_CLEAN_BUCKET_ORDER:
                ordered.append(f"{counts[b]} {b}")
        note = (
            "_Confidence labels for this interpretive section: "
            + ", ".join(ordered)
            + ". Each was a per-sentence groundedness check, summarized here; the whole section is "
            "interpretive and not individually span-verified._"
        )
        cleaned = f"{note}\n\n{cleaned}" if cleaned.strip() else note
    return cleaned


async def generate_analyst_synthesis(
    *,
    verified_prose: str,
    bibliography: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    research_question: str,
    prior_verified_context: list[dict[str, Any]] | None = None,
    model: str = "deepseek/deepseek-v4-pro",
    # D-1 / I-ready-017 (#1182): was a hardcoded 4000; the reasoning-first writer
    # needs room to finish planning before the synthesis prose. Named, env-overridable
    # default (openrouter_client clamps reasoning-first to PG_REASONING_FIRST_HARD_CAP
    # =16384 on the default provider — see the module-level PG_SECTION_MAX_TOKENS note).
    max_tokens: int = PG_SECTION_MAX_TOKENS,
    temperature: float = 0.3,
    # I-deepfix-001 B13 (#1357): optional injectable groundedness judge ((claim, span) -> bool, True
    # == supported) for the post-compose deviation check. None (default) => the check lazily builds the
    # certified-Sentinel judge; the run path may inject its already-built sentinel transport judge.
    deviation_judge_fn: "Callable[[str, str], bool] | None" = None,
) -> tuple[str, int, int]:
    """Generate the Analyst Synthesis section.

    Per I-cd-009 (GH#624) Carney demo lock: DeepSeek V4 Pro 1.6T (49B
    active MoE) is the writer (consistent with verified prose voice;
    Gemma 4 31B-it stays in the judge/evaluator role).

    Returns (text, input_tokens, output_tokens). Returns ("", 0, 0)
    on failure — caller MUST treat empty text as "omit synthesis
    section entirely" (no empty disclosure block per Codex iter-1).
    """
    # I-meta-002-q1d (#953 q1d-c): operator kill-switch. Checked BEFORE prompt construction + the model
    # call so disabling the unverified analyst layer costs nothing (Codex brief-gate P2). When off, the
    # report ships the span-verified core ONLY (caller omits an empty synthesis section).
    if resolve("PG_SWEEP_ANALYST_SYNTHESIS").strip() not in ("1", "true", "True"):
        logger.info(
            "[analyst_synthesis] PG_SWEEP_ANALYST_SYNTHESIS=0 — unverified layer omitted "
            "(verified core only)"
        )
        return "", 0, 0

    # I-deepfix-001 (#1369) iter2 (Codex P0): EMITTER-level fail-closed. The Gate-B preflight refuses an
    # ungated launch, but the RESUME-render / direct-sweep path SKIPS that preflight — so the same guard
    # must bind HERE at the emitter. If the layer is ON while the D3 PROMOTE (drop-if-ungrounded) gate is
    # NOT active, shipping would emit legacy KEEP-and-LABEL (un-dropped) synthesis — the exact ungated
    # posture that was banned. Refuse it: ship the span-verified core ONLY. Default-ON kill-switch so only
    # an explicit operator opt-out disables the guard. The frozen faithfulness engine is untouched.
    if os.environ.get(
        "PG_ANALYST_SYNTHESIS_EMITTER_FAILCLOSED", "1"
    ).strip().lower() not in ("0", "false", "off", "no") and not _promote_mode_active():
        logger.warning(
            "[analyst_synthesis] EMITTER fail-CLOSED: layer ON but D3 PROMOTE gate is OFF — refusing "
            "UNGATED synthesis (verified core only). Set PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED=1 to ship it."
        )
        return "", 0, 0

    from src.polaris_graph.llm.openrouter_client import (
        OpenRouterClient,
        set_reasoning_call_context,
    )

    biblio_block = _format_bibliography_for_prompt(bibliography)
    evidence_block = _format_evidence_pool_for_prompt(evidence_rows)

    prompt = (
        f"Research question: {research_question}\n\n"
        f"=== VERIFIED FINDINGS (above the synthesis section) ===\n\n"
        f"{verified_prose}\n\n"
        f"=== BIBLIOGRAPHY (cite by [N] only) ===\n\n"
        f"{biblio_block}\n\n"
        f"=== EVIDENCE POOL (for synthesis context) ===\n\n"
        f"{evidence_block}\n\n"
        f"{_format_prior_verified_context(prior_verified_context)}"
        f"=== TASK ===\n\n"
        f"Write the Analyst Synthesis section now, following the rules. "
        f"Hedge interpretive claims; cite by [N] only; no [#ev:...] tokens; "
        f"4-6 sub-sections with ### subheadings; 1500-3000 words total."
    )

    client = OpenRouterClient(model=model)
    try:
        # I-gen-004 (#496): tag the analyst-synthesis call for the trace sink.
        set_reasoning_call_context(
            section="Analyst Synthesis", call_type="analyst_synthesis",
        )
        # I-safety-002b (#925) PR-2: role-tagging for the Path-B gate is applied at the
        # runner chokepoint (run_honest_sweep_r3.py wraps generate_multi_section_report
        # with llm_role("generator")) — this nested call inherits the contextvar.
        response = await client.generate(
            prompt=prompt,
            system=ANALYST_SYNTHESIS_SYSTEM_PROMPT,
            max_tokens=max_tokens,
            temperature=temperature,
            # I-wire-009 (#1323): BOUND the reasoning pool on the analyst-synthesis writer. The
            # generator (GLM-5.2 in-campaign) is in openrouter_client._ALWAYS_REASON_MODELS, whose
            # branch-1 path runs reasoning at effort=high with NO cap when no reasoning_max_tokens
            # is passed — it can consume the whole max_tokens (PG_SECTION_MAX_TOKENS=64000) ceiling
            # on reasoning and return content="". A generous reasoning slice leaves the bulk of the
            # ceiling for the 1500-3000-word synthesis. LAW VI env-tunable; §9.1.8 token-budget fix only,
            # faithfulness-neutral (this is the UNVERIFIED analyst layer; strict_verify governs the
            # verified core).
            # I-deepfix-001 M6 (Layer 2): the reasoning-first writer was returning empty in drb_72 (the
            # #1323/#1335 dark-synthesis trap — reasoning burned the slice, content=""). Per §9.1
            # token-MAX ("reasoning effort + max_tokens ALWAYS go MAX; a starved budget truncates
            # reasoning -> empty content"), raise the DEFAULT slice 16384 -> 32768 (a CAP, not a target,
            # billed by actual usage -> generous cap is free insurance). Still LAW VI env-overridable.
            reasoning_max_tokens=int(
                os.getenv("PG_ANALYST_SYNTHESIS_REASONING_MAX_TOKENS", "32768")
            ),
        )
        text = (response.content or "").strip()
        in_tok = response.input_tokens
        out_tok = response.output_tokens
    except Exception as exc:
        logger.warning("[analyst_synthesis] generation failed: %s", exc)
        return "", 0, 0
    finally:
        try:
            await client.close()
        except Exception:
            pass

    if not text:
        logger.warning("[analyst_synthesis] empty response — section omitted")
        return "", in_tok, out_tok

    # Codex iter-1 P0 guardrail: scrub [#ev:...] tokens from synthesis.
    cleaned = _scrub_ev_tokens(text)
    # I-bug-108 P0: scrub [N] markers exceeding bibliography size
    # to prevent rule_pt12_invalid_citation_marker from aborting the
    # report. Synthesis LLM occasionally hallucinates indices; scrub
    # them runtime so production runs don't abort.
    cleaned, _ = _scrub_invalid_n_markers(cleaned, biblio_size=len(bibliography))
    # I-meta-002-q1d (#953 q1d-c, CLINICAL-SAFETY): fail-closed drop of unverified qualitative-negation
    # SAFETY sentences from the analyst layer (the lethal fabrication class) — runs AFTER the syntactic
    # scrubs, BEFORE the report appends this prose. The span-verified core above is untouched.
    cleaned, n_neg_dropped = _screen_qualitative_negations(cleaned)
    if n_neg_dropped:
        _SYNTHESIS_TELEMETRY["synthesis_negation_dropped_count"] += n_neg_dropped
        logger.warning(
            "[analyst_synthesis] synthesis_negation_dropped: %d unverified qualitative-negation "
            "safety sentence(s) removed from the analyst layer (fail-closed)", n_neg_dropped
        )
    # I-deepfix-001 B13 (#1357) + D3 (#1344): bring the analyst layer UNDER the faithfulness engine via
    # the deviation check. Extracted into a synchronous, testable helper (the fail-closed-on-exception
    # path is behavioral, not an untested branch). Runs AFTER the regex scrubs + negation screen,
    # BEFORE return.
    cleaned = _apply_synthesis_deviation_screen(
        cleaned, bibliography, evidence_rows, deviation_judge_fn,
    )
    # I-deepfix-006 C5 (PG_SYNTH_RENDER_CLEAN, default ON): dedupe the doubled section disclosure +
    # lift the per-sentence [confidence:…] markers into a compact per-section note. Render-only, runs
    # LAST (after the deviation screen has appended its confidence markers). OFF => byte-identical.
    cleaned = _render_clean_synthesis(cleaned)
    return cleaned, in_tok, out_tok
