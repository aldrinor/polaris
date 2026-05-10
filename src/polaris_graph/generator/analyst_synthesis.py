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
import re
from typing import Any

logger = logging.getLogger(__name__)


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


_EV_TOKEN_RE = re.compile(r"\[#ev:[^\]]*\]")
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
}


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
    """Remove any [#ev:...] tokens from synthesis output.

    Codex iter-1 P0: must be a runtime guardrail, not just a test.
    Synthesis prose MUST NOT carry [#ev:...] tokens. If the LLM emits
    them anyway, scrub them and log a warning.
    """
    cleaned, n = _EV_TOKEN_RE.subn("", text)
    if n > 0:
        logger.warning(
            "[analyst_synthesis] scrubbed %d [#ev:...] token(s) from "
            "synthesis output — synthesis MUST cite by [N] only",
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
    max_rows: int = 30,
) -> str:
    """Render the evidence pool as <<<evidence:ev_X>>> blocks the LLM
    can read for context. Capped at max_rows to bound the prompt size.
    """
    blocks = []
    for row in evidence_rows[:max_rows]:
        ev_id = row.get("evidence_id") or row.get("id") or "ev_?"
        quote = (
            row.get("direct_quote")
            or row.get("statement")
            or ""
        )[:1200]
        blocks.append(f"<<<evidence:{ev_id}>>>\n{quote}\n<<<end>>>")
    return "\n\n".join(blocks)


async def generate_analyst_synthesis(
    *,
    verified_prose: str,
    bibliography: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    research_question: str,
    model: str = "deepseek/deepseek-v3.2-exp",
    max_tokens: int = 4000,
    temperature: float = 0.3,
) -> tuple[str, int, int]:
    """Generate the Analyst Synthesis section.

    Per Codex iter-1 brief verdict: DeepSeek V3.2-Exp is the writer
    (consistent with verified prose voice; Gemma stays in the
    judge/evaluator role).

    Returns (text, input_tokens, output_tokens). Returns ("", 0, 0)
    on failure — caller MUST treat empty text as "omit synthesis
    section entirely" (no empty disclosure block per Codex iter-1).
    """
    from src.polaris_graph.llm.openrouter_client import OpenRouterClient

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
        f"=== TASK ===\n\n"
        f"Write the Analyst Synthesis section now, following the rules. "
        f"Hedge interpretive claims; cite by [N] only; no [#ev:...] tokens; "
        f"4-6 sub-sections with ### subheadings; 1500-3000 words total."
    )

    client = OpenRouterClient(model=model)
    try:
        response = await client.generate(
            prompt=prompt,
            system=ANALYST_SYNTHESIS_SYSTEM_PROMPT,
            max_tokens=max_tokens,
            temperature=temperature,
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
    return cleaned, in_tok, out_tok
