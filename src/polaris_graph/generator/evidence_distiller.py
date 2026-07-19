"""
Map-reduce evidence distiller â€” I-perm-016 (#1209) keystone generation fix.

WHY THIS EXISTS
---------------
The legacy per-section generation path hands V4 Pro the raw ``<<<evidence:...>>>``
quote blocks plus an atom catalog and asks it to write cited prose in ONE pass.
The reasoning-first writer then has to (a) read every quote, (b) decide what is
section-relevant, (c) keep numbers exact, and (d) emit ``[#ev:...]`` provenance
tokens â€” all at once. The drb_72 / drb_76 forensic sweeps showed this conflated
job leaks: the writer over-claims, mis-binds numbers across sources, and
``strict_verify`` then DROPS the over-claimed sentences (drb_76 baseline: 40
verified / 41 dropped, 29 of the drops being entailment failures). The faithful
content is there in the corpus; the single-pass writer just cannot hold it.

THE FIX (map-reduce)
--------------------
1. MAP â€” one LLM call PER SOURCE distills the source into atomic, span-grounded
   findings. Each finding is LOCALLY VALIDATED fail-closed: its support_quote must
   LOCATE a REAL source slice (exact/whitespace/fuzzy recovery, #1217), and a
   FUZZY (paraphrase-recovered) finding must additionally ENTAIL the claim via the
   production verifier (``verify_sentence_provenance``). Exact/whitespace findings
   are verbatim source text, so their per-finding entailment is non-blocking and
   the (slow) verifier call is skipped for them (#1217 perf). A finding that cannot
   be located, or a fuzzy finding the verifier does not entail, is rejected here
   before it can pollute the ledger. Every input source yields >=1 accepted finding
   OR a ``CoverageRow`` so no source ever silently disappears (LAW II fail-loud).
2. REDUCE â€” the section writer composes prose over the VALIDATED findings ledger
   only (reference-first). It never sees raw quotes; it cites findings with the
   same legacy ``[ev_XXX]`` markers used by the raw-evidence path. The downstream
   ``_rewrite_draft_with_spans`` (unchanged) binds those markers to spans for the
   FINAL sentence, then ``strict_verify`` (unchanged) re-checks every sentence
   exactly as today â€” the distiller TIGHTENS, it never relaxes, the faithfulness
   gates.

FAITHFULNESS INVARIANT
----------------------
This module NEVER weakens a gate. A distilled finding is only ever a CANDIDATE
admitted by EXTRACTION-side checks (located in a real source slice; fuzzy
recoveries additionally entailment-gated); the FINAL section prose is re-verified
sentence-by-sentence by the unchanged ``strict_verify`` (numbers-in-span AND >=2
content-word overlap AND enforce-mode entailment) exactly as the legacy path is —
that final gate, NOT the per-finding extraction check, is the SOLE publication
authority. The distiller can only REDUCE what the writer is allowed to assert.

Flag-gated entirely by ``PG_SECTION_DISTILL`` (read in the multi_section seam).
This module is only imported when that flag is ON; when OFF the legacy path is
byte-identical (no import, no call, no prompt change).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.polaris_graph.generator.claim_atom_extractor import (
    build_atom_catalog,
    filter_atoms_for_section,
)
from src.polaris_graph.generator.provenance_generator import (
    verify_sentence_provenance,
)
from src.polaris_graph.settings import resolve

logger = logging.getLogger("polaris_graph.evidence_distiller")

# Bump when the prompt, validation, or dataclass shape changes so stale cache
# entries from an older distiller can never be replayed against a new contract.
DISTILLER_VERSION = "section_distiller_v7"  # bumped #1218: v5=MAP exhaustive+atomic-numeric extraction + REDUCE one-statistic-per-sentence/use-every-finding/[OR]->(OR) (thinness fix) — prompt change invalidates v4 cache


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Env knobs (LAW VI â€” named, env-overridable; no magic numbers)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _env_int(name: str, default: int) -> int:
    """Read a positive-int env knob; fall back to default on missing/garbage."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "[evidence_distiller] %s=%r is not an int â€” using default %d",
            name, raw, default,
        )
        return default


def _map_max_tokens() -> int:
    return _env_int("PG_DISTILL_MAP_MAX_TOKENS", 8192)


def _map_reasoning_tokens() -> int:
    # BUG-2 (#1262): the MAP call is per-SOURCE atomic extraction — short,
    # bounded, NON-prose work (one source -> a few span-grounded findings). Its
    # modest 4096 reasoning budget is the DELIBERATE small-call reduction that
    # protects content per drb_76 (reasoning eating the whole completion ceiling
    # -> ZERO content -> ReasoningFirstTruncationError). It is NOT the starved
    # main-section call and is intentionally LEFT AS-IS by this fix.
    return _env_int("PG_DISTILL_MAP_REASONING_TOKENS", 4096)


def _map_text_mode() -> bool:
    # I-arch-007 distill_map chokepoint: deepseek-v4-pro (a reasoning-first model)
    # DUMPS the answer into the reasoning channel under
    # response_format=json_object, emitting EMPTY content and burning the full
    # 32768 ceiling (~410s) per call (openrouter_client.py:1817-1819,:1838). Text
    # mode (response_format=None) keeps the JSON in the CONTENT channel — proven by
    # the section_reduce control (multi_section_generator.py:6925, same model/same
    # 32768 floor, content populates). _parse_map_json already parses fenced/plain
    # JSON from content. Default OFF = byte-identical json_object behavior
    # (flag-OFF-byte-identical convention); set PG_DISTILL_MAP_TEXT_MODE=1 to
    # activate. NOT a faithfulness change: distill MAP is per-source consolidation,
    # not one of the 4 hard gates; output still flows through
    # _validate_and_store_one_source unchanged.
    return resolve("PG_DISTILL_MAP_TEXT_MODE").strip().lower() in (
        "1", "true", "yes",
    )


def _reduce_max_tokens() -> int:
    return _env_int("PG_DISTILL_REDUCE_MAX_TOKENS", 8192)


# BUG-2 (#1262): sane reasoning FLOOR for the REDUCE call — the MAIN section-prose
# writer in the distillate keystone path (multi_section_generator
# `_reduce_reasoning_tokens()` site, call_type="section_reduce"). This is full
# section composition over the validated findings ledger, NOT a small extraction or
# <=3-sentence contract-slot call. The keystone's birth default (5000, #1209) was an
# initial guess that token-STARVES this call vs CLAUDE.md §9.1.8 ("reasoning always
# max"): deepseek-v4-pro emits ~5-18k reasoning tokens for full prose composition
# (openrouter_client.py:1820-1837 in-code evidence), and the equivalent LEGACY
# section writer (multi_section_generator.py:2802, no explicit reasoning cap) gets
# ~0.4*32768 ≈ 13k reasoning headroom for the SAME job. A 5000 hint sits BELOW that
# band, so a provider that DOES honor reasoning.max_tokens could truncate V4 Pro's
# plan mid-stream -> the REDUCE ReasoningFirstTruncationError guard returns an empty
# draft -> that section DROPS. FAITHFULNESS IS SAFE: raising the reasoning floor can
# only let MORE sections finish composing (never fewer, never a relaxed gate) — the
# content ceiling is independently floored to 32768 (openrouter_client.py:1838) so
# wider reasoning does not starve content, and every REDUCE sentence is still
# re-verified by the UNCHANGED strict_verify / NLI gates downstream. Env-overridable
# (LAW VI); the floor only guarantees the MAIN section call is never capped below a
# sane value — operators may set the env knob HIGHER. The small-call reductions
# (_map_reasoning_tokens above; PG_CONTRACT_SLOT_REASONING_MAX_TOKENS) are untouched.
PG_DISTILL_REDUCE_REASONING_MIN_TOKENS: int = _env_int(
    "PG_DISTILL_REDUCE_REASONING_MIN_TOKENS", 16384
)


def _reduce_reasoning_tokens() -> int:
    # BUG-2 (#1262): clamp the configured REDUCE reasoning budget UP to the sane
    # main-section floor so the keystone section writer can never be token-starved
    # below it (default raised 5000 -> floor). max() keeps a deliberately HIGHER
    # operator override intact; it only prevents an accidentally-tiny value.
    configured = _env_int(
        "PG_DISTILL_REDUCE_REASONING_TOKENS",
        PG_DISTILL_REDUCE_REASONING_MIN_TOKENS,
    )
    return max(configured, PG_DISTILL_REDUCE_REASONING_MIN_TOKENS)


def _max_parallel() -> int:
    # B19/I-arch-011 (KEYSTONE): raise the MAP fan-out default 4 -> 8 so a wide
    # corpus distills with more sources in flight (breadth-positive; the per-call
    # wall below bounds each one). DNA = consolidate-keep-all, never a throttle.
    return max(1, _env_int("PG_DISTILL_MAX_PARALLEL", 8))


def _distill_map_call_wall_s() -> int:
    # B19/I-arch-011 (KEYSTONE — root cause of the B15 generator hang): bound EACH
    # distill_map LLM call with an EXPLICIT per-call wall, mirroring the sibling
    # PG_CREDIBILITY_PASS_WALL_S in multi_section_generator.py. Without an explicit
    # timeout, openrouter_client._call_impl resolves a reasoning-first model
    # (deepseek-v4-pro) to ~6530s (GENERATOR_TIMEOUT_SECONDS + 30); a half-open SSE
    # socket then hangs the asyncio loop for ~1.8h until only the 10800s run-wall
    # backstops. DEFAULT 1800: telemetry shows a HEALTHY distill call ran 1475s and
    # COMPLETED, so 1800 sits safely above the healthy band yet well under the
    # 10800s run-wall. An explicit timeout always wins (_resolve_call_timeout /
    # _call_impl: actual_timeout = timeout or default). LAW VI: env-overridable.
    return _env_int("PG_DISTILL_MAP_CALL_WALL_S", 1800)


async def _call_distill_map_with_wall(client, **call_kwargs):
    """Run ONE distill_map LLM call bounded END-TO-END by PG_DISTILL_MAP_CALL_WALL_S.

    B19/I-arch-011 iter-2 (Codex P1): ``openrouter_client._call`` applies its ``timeout=``
    PER retry attempt and retries up to MAX_RETRIES, so a half-open SSE socket could occupy
    the map fan-out for ~3*(wall+grace)s before a coverage row appears — not the single
    ``wall`` the B19 contract promises, and enough (under many hung sources) to push the
    distill stage past the 10800s run-wall and lose the render. Wrap the whole call in an
    OUTER ``asyncio.wait_for(wall)`` so the TOTAL across internal retries is bounded at
    ``wall``: a FAST transient failure still retries within the remaining budget, but a hung /
    pathologically-slow call is cancelled at ``wall`` and surfaces as the caller's loud
    ``map_failed`` coverage row instead of retry-hanging. The inner per-attempt ``timeout=`` is
    kept as a defensive bound. A wall breach raises ``asyncio.TimeoutError`` (caught by the
    caller). No source is silently dropped; no faithfulness gate is touched.
    """
    wall = float(_distill_map_call_wall_s())
    return await asyncio.wait_for(
        client._call(call_type="distill_map", timeout=wall, **call_kwargs),
        timeout=wall,
    )


def _microbatch_size() -> int:
    """MAP micro-batch size, clamped to 1..3 (per spec: per-source by default,
    allow 1..3 only)."""
    n = _env_int("PG_DISTILL_MICROBATCH_SIZE", 1)
    return min(3, max(1, n))


def _default_cache_dir() -> Path:
    return Path(".cache") / "polaris" / "evidence_distiller"


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Dataclasses (spec Â§1)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@dataclass(frozen=True)
class DistilledFinding:
    """One distilled, span-grounded finding extracted from a single evidence row.

    Carries the claim text, its source span (``span_start``/``span_end`` +
    ``support_quote``), extracted numbers/entities, an optional caveat, the
    contradiction key used for clustering, the source tier, and the ids of the
    claim atoms it maps to.
    """

    finding_id: str
    evidence_id: str
    claim: str
    span_start: int
    span_end: int
    support_quote: str
    numbers: list[str]
    entities: list[str]
    caveat: str
    contradiction_key: str
    source_tier: str
    atom_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CoverageRow:
    """Per-evidence distillation outcome: its status, finding count, and optional reason."""

    evidence_id: str
    status: str  # mapped | no_relevant_findings | map_failed | validation_failed
    n_findings: int
    reason: str = ""


@dataclass(frozen=True)
class ContradictionCluster:
    """A group of findings sharing one contradiction key, with an optional summary."""

    contradiction_key: str
    finding_ids: list[str]
    summary: str = ""


@dataclass(frozen=True)
class SectionDistillate:
    """Full distillation output for one section.

    Bundles the section's findings, per-evidence coverage rows, contradiction
    clusters, and atom catalog, plus token/cache telemetry and the distiller
    version.
    """

    section_title: str
    section_focus: str
    findings: list[DistilledFinding]
    coverage: list[CoverageRow]
    contradiction_clusters: list[ContradictionCluster]
    atom_catalog: dict[str, Any]
    input_tokens: int = 0
    output_tokens: int = 0
    cache_hits: int = 0
    version: str = DISTILLER_VERSION


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Prompts (spec Â§3 â€” verbatim)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_MAP_SYSTEM = (
    "You extract atomic, provenance-preserving findings for one report section.\n"
    "Return JSON only. Use only the supplied evidence text. Do not infer beyond it.\n"
    "Each finding must be one atomic claim grounded in one exact substring of "
    "direct_quote.\n"
    "EXHAUSTIVE BUT STRICTLY ON-TOPIC (#1218): first decide what THIS section is about "
    "from SECTION_TITLE/SECTION_FOCUS, then extract EVERY distinct finding that is "
    "GENUINELY ABOUT THAT TOPIC as its own atomic finding — including every on-topic "
    "numeric outcome (incidence, rate, fatality, odds ratio, relative risk, hazard "
    "ratio, confidence interval, count, percentage), and every on-topic qualifier or "
    "caveat. Do NOT stop at the most salient few WITHIN the topic; but do NOT pad with "
    "OFF-TOPIC findings. For a SAFETY / ADVERSE-EVENT / CONTRAINDICATION section, "
    "ON-TOPIC = harms, adverse events, contraindications, toxicity, warnings, "
    "infections, and risks attributable to THE INTERVENTION itself (with their numbers); "
    "OFF-TOPIC = general disease-causation or carcinogenesis MECHANISMS not framed as a "
    "risk of the intervention — return no_relevant_findings=true for a source that only "
    "describes such mechanisms.\n"
    "ONE STATISTIC PER FINDING (#1218): each finding's support_quote MUST be an EXACT, "
    "CONTIGUOUS substring of direct_quote that contains EVERY number in the claim. If "
    "the numbers for one result are NOT contiguous in the source (e.g. a count in one "
    "sentence and an odds ratio in another), SPLIT into separate findings, each with "
    "its own contiguous support_quote. Never bundle numbers from different source "
    "locations into one finding.\n"
    "If no section-relevant finding exists, return no_relevant_findings=true with "
    "a reason."
)

_REDUCE_SYSTEM = (
    "Write the section using only the validated findings ledger.\n"
    "Every factual sentence must cite at least one [[finding:f...]] marker and the "
    "evidence marker copied EXACTLY from that finding's ledger 'cite=[...]' field — "
    "reproduce the bracketed id verbatim; do NOT add or remove an 'ev_' prefix.\n"
    "CRITICAL marker placement: put ALL markers INSIDE the sentence they support, "
    "immediately BEFORE that sentence's terminal period. NEVER place markers on their "
    "own line, in a separate sentence, or after the period. Correct: "
    "'Colibactin induces double-strand breaks in cultured cells [[finding:f002_000]] "
    "[ev_colibactin_pks].' Wrong: 'Colibactin induces double-strand breaks in cultured "
    "cells. [[finding:f002_000]] [ev_colibactin_pks]'\n"
    "USE EVERY validated finding (#1218): emit AT LEAST ONE sentence for each finding "
    "in the ledger (co-cite true duplicates together); do not summarize findings away.\n"
    "ONE STATISTIC PER SENTENCE (#1218): write each NUMERIC result in its OWN sentence; "
    "NEVER combine two distinct statistics (e.g. an odds ratio from one finding and a "
    "fatality rate or sample count from another) into a single sentence. Every number "
    "in a sentence must come from ONE finding's quote so it binds to one source span.\n"
    "Rewrite any source bracket abbreviation (e.g. [OR], [CI], [RR]) as PARENTHESES — "
    "(OR), (CI), (RR) — so it is never mistaken for a citation marker.\n"
    "A sentence must be exactly one type: single-source claim, multi-source "
    "conjunction (NON-numeric only), or conflict-limitation.\n"
    "For numeric outcome/incidence/effect claims, copy the finding's atom_ids as "
    "(atom_NNN) before the evidence marker.\n"
    "Do not emit [#ev:...] span tokens; spans are computed after drafting. "
    "No uncited prose. No headings."
)


def _render_map_user(
    *,
    section_title: str,
    section_focus: str,
    evidence_id: str,
    tier: str,
    statement: str,
    direct_quote: str,
    atom_rows: str,
    research_question: str = "",
) -> str:
    """Render the MAP user prompt (spec Â§3).

    I-arch-004 F21 (#1255): when `research_question` is supplied, a FRAMING-ONLY
    line is prepended so the per-source extractor can decide on-topic relevance
    against the actual question (the _MAP_SYSTEM rules already turn on
    "what THIS section is about"). It is NOT a citable source: findings are still
    extracted ONLY from DIRECT_QUOTE and validated against it. Empty (the default)
    => byte-identical to pre-F21."""
    _rq = (research_question or "").strip()
    rq_line = (
        "RESEARCH_QUESTION (framing only — extract findings ONLY from "
        f"DIRECT_QUOTE, never from this line): {_rq}\n"
        if _rq
        else ""
    )
    return (
        f"{rq_line}"
        f"SECTION_TITLE: {section_title}\n"
        f"SECTION_FOCUS: {section_focus}\n"
        f"EVIDENCE_ID: {evidence_id}\n"
        f"SOURCE_TIER: {tier}\n"
        f"STATEMENT: {statement}\n"
        f"DIRECT_QUOTE:\n"
        f"{direct_quote}\n\n"
        f"NUMERIC_ATOMS_AVAILABLE:\n"
        f"{atom_rows}\n\n"
        "Return JSON:\n"
        "{\n"
        '  "evidence_id": "...",\n'
        '  "no_relevant_findings": false,\n'
        '  "no_relevant_reason": "",\n'
        '  "findings": [\n'
        "    {\n"
        '      "claim": "single atomic claim",\n'
        '      "support_quote": "exact substring from DIRECT_QUOTE",\n'
        '      "span_start": 0,\n'
        '      "span_end": 0,\n'
        '      "numbers": [],\n'
        '      "entities": [],\n'
        '      "caveat": "",\n'
        '      "contradiction_key": "",\n'
        '      "source_tier": "T1"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Rules: every number in claim must appear in support_quote; do not round; "
        "do not combine multiple claims; caveats/limitations are findings only when "
        "the quote directly states them.\n"
        "#1218 EXHAUSTIVE + ATOMIC: return a SEPARATE finding for EVERY distinct "
        "numeric outcome (rate, incidence, fatality, odds/risk/hazard ratio, "
        "confidence interval, count, percentage), contraindication, adverse event, and "
        "caveat the quote states — do not stop early. Each finding's support_quote is "
        "an EXACT contiguous substring holding ALL of that finding's numbers; if a "
        "result's numbers are not contiguous in the source, split into separate "
        "findings each with its own contiguous quote (never bundle scattered numbers)."
    )


def _render_reduce_narrative_context(
    advisory_text: str = "",
    cross_trial_summaries: list[str] | None = None,
) -> str:
    """I-perm-018 (#1210): render the domain advisory + cross-trial inferences as
    FRAMING-ONLY narrative context for the REDUCE prompt.

    The legacy path threads `advisory_text` (domain tone/emphasis guidance) and the
    M-72 cross-trial synthesis block into the section prompt; the distill REDUCE
    branch previously dropped both, so the distilled section lost that narrative
    richness. This block restores it WITHOUT touching faithfulness: it is explicitly
    framing-only — the REDUCE writer must still produce every sentence from the
    VALIDATED_FINDINGS_LEDGER and cite its [[finding:]] marker; nothing here is a
    finding or a citable source. (We deliberately do NOT reuse
    `render_cross_trial_synthesis_block`, whose 'Cite the contributing [ev_XXX]
    markers' instruction is incompatible with the distill filter that drops any
    sentence lacking a [[finding:]] ledger marker.) Empty inputs → "" → the prompt
    is byte-identical to pre-#1210."""
    advisory = (advisory_text or "").strip()
    summaries = [s.strip() for s in (cross_trial_summaries or []) if s and s.strip()]
    if not advisory and not summaries:
        return ""
    parts = [
        "NARRATIVE FRAMING CONTEXT (framing ONLY — NOT findings, NOT sources):",
        "Use the guidance below to shape TONE, EMPHASIS, and the ORDER in which you "
        "present the ledger findings. You must NOT write or cite any sentence FROM "
        "this block: every sentence still comes from the VALIDATED_FINDINGS_LEDGER "
        "above and carries its [[finding:]] marker. Do NOT introduce numbers, claims, "
        "or sources that are not in the ledger.",
    ]
    if advisory:
        parts.append(f"\nDOMAIN_ADVISORY:\n{advisory}")
    if summaries:
        bullets = "\n".join(f"  - {s}" for s in summaries)
        parts.append(
            "\nCROSS_TRIAL_CONNECTIONS (relationships among ledger findings you may "
            f"emphasise when ordering your sentences):\n{bullets}"
        )
    return "\n".join(parts)


def render_reduce_user(
    distillate: SectionDistillate,
    *,
    advisory_text: str = "",
    cross_trial_summaries: list[str] | None = None,
    research_question: str = "",
) -> str:
    """Render the REDUCE user prompt (spec Â§3): the validated findings ledger,
    one line per finding, plus contradiction clusters.

    I-perm-018 (#1210): when `advisory_text` / `cross_trial_summaries` are supplied,
    a FRAMING-ONLY narrative-context block is appended (see
    `_render_reduce_narrative_context`). Both empty (the default) → byte-identical.

    I-arch-004 F21 (#1255): when `research_question` is supplied, a single
    FRAMING-ONLY line is prepended so the REDUCE writer knows what the report is
    about. It is NOT a finding and NOT a citable source — every sentence still
    comes from the VALIDATED_FINDINGS_LEDGER and carries its [[finding:]] marker
    (the distill filter drops any sentence lacking one, and strict_verify is
    unchanged), so the question text can never publish as an unsupported claim.
    Empty (the default) => byte-identical to pre-F21."""
    ledger_lines: list[str] = []
    for f in distillate.findings:
        atom_ids = ",".join(f.atom_ids)
        quote = f.support_quote.replace("\n", " ")
        ledger_lines.append(
            f"{f.finding_id} | {f.evidence_id} | {f.source_tier} | "
            f"cite=[{f.evidence_id}] | atom_ids={atom_ids} | "
            f"claim={f.claim} | caveat={f.caveat} | "
            f"contradiction_key={f.contradiction_key} | quote={quote}"
        )
    ledger = "\n".join(ledger_lines) if ledger_lines else "(no findings)"

    cluster_lines: list[str] = []
    for c in distillate.contradiction_clusters:
        ids = ",".join(c.finding_ids)
        cluster_lines.append(
            f"{c.contradiction_key}: {ids}"
            + (f" â€” {c.summary}" if c.summary else "")
        )
    clusters = "\n".join(cluster_lines) if cluster_lines else "(none)"

    narrative = _render_reduce_narrative_context(advisory_text, cross_trial_summaries)
    narrative_section = f"{narrative}\n\n" if narrative else ""

    # F21 (#1255): framing-only research-question line. Empty => byte-identical.
    _rq = (research_question or "").strip()
    rq_section = (
        "RESEARCH_QUESTION (framing only — NOT a finding, NOT a citable source): "
        f"{_rq}\n\n"
        if _rq
        else ""
    )

    return (
        f"{rq_section}"
        f"SECTION_TITLE: {distillate.section_title}\n"
        f"SECTION_FOCUS: {distillate.section_focus}\n\n"
        f"VALIDATED_FINDINGS_LEDGER:\n{ledger}\n\n"
        f"CONTRADICTION_CLUSTERS:\n{clusters}\n\n"
        f"{narrative_section}"
        "Write the section now. COVER EVERY finding in the ledger (one sentence each, "
        "co-citing true duplicates), and write each NUMERIC result in its OWN sentence "
        "(never merge two distinct statistics). Each sentence must use ledger facts "
        "only and place its finding marker(s), atom id(s) when needed, and [ev_XXX] "
        "marker(s) INSIDE the sentence, immediately BEFORE the terminal period — never "
        "on a separate line or after the period. Do not write [#ev:...] span tokens."
    )


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# JSON parsing â€” content-or-reasoning, defensive (spec Â§4)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

# Match the first balanced-looking top-level JSON object in a noisy string.
# Reasoning-first models sometimes wrap the JSON in ```json fences or prose.
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_map_json(content: str | None, reasoning: str | None) -> Optional[dict]:
    """Parse the MAP JSON defensively from content OR reasoning.

    OpenRouter's reasoning-first behaviour (per openrouter_client) can route the
    JSON object into either the content field or the reasoning field. Try content
    first (the response_format target), then reasoning, then a regex-extracted
    object from either. Returns None if nothing parses â€” the caller treats that as
    a map failure and emits a CoverageRow (no source disappears).
    """
    for raw in (content, reasoning):
        if not raw or not raw.strip():
            continue
        # Strip code fences if present.
        candidate = raw.strip()
        if candidate.startswith("```"):
            candidate = candidate.strip("`")
            # drop a leading "json" language tag
            if candidate.lstrip().lower().startswith("json"):
                candidate = candidate.lstrip()[4:]
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            pass
        # Last resort: extract the first {...} block.
        m = _JSON_OBJECT_RE.search(raw)
        if m:
            try:
                obj = json.loads(m.group(0))
                if isinstance(obj, dict):
                    return obj
            except (json.JSONDecodeError, ValueError):
                continue
    return None


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Cache (spec Â§5) â€” store VALIDATED outputs only
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _cache_key(
    *,
    section_title: str,
    section_focus: str,
    evidence_id: str,
    direct_quote: str,
) -> str:
    """sha256(distiller_version + fuzzy_threshold + title + focus + evidence_id +
    sha256(direct_quote)).

    #1217 Codex diff-gate P2: the key includes ``PG_DISTILL_FUZZY_MIN_OVERLAP`` so
    that retuning the fuzzy-recovery threshold after a cache is populated cannot
    replay stale fuzzy ACCEPTS at the old threshold — a tighter/looser threshold is
    a different validation outcome and must miss the cache."""
    dq_hash = hashlib.sha256(direct_quote.encode("utf-8")).hexdigest()
    payload = "\n".join(
        [
            DISTILLER_VERSION,
            f"fuzzy_min_overlap={_distill_fuzzy_min_overlap_frac()}",
            section_title, section_focus, evidence_id, dq_hash,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cache_path(cache_dir: Path, key: str) -> Path:
    return cache_dir / f"{key}.json"


def _cache_load(cache_dir: Path, key: str) -> Optional[list[dict]]:
    """Load a cached list of VALIDATED finding dicts, or None on miss/corruption."""
    path = _cache_path(cache_dir, key)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        logger.warning(
            "[evidence_distiller] cache read failed for %s: %s â€” treating as miss",
            path, exc,
        )
    return None


def _cache_store(cache_dir: Path, key: str, validated: list[dict]) -> None:
    """Persist VALIDATED finding dicts only (never raw/invalid LLM JSON)."""
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        _cache_path(cache_dir, key).write_text(
            json.dumps(validated, ensure_ascii=False), encoding="utf-8",
        )
    except OSError as exc:
        logger.warning(
            "[evidence_distiller] cache write failed for key %s: %s â€” continuing",
            key, exc,
        )


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Numeric helpers â€” mirror strict_verify's definitions (spec Â§1 validation)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _numbers_in_text(text: str) -> set[str]:
    """Numeric tokens under the boundary-aware definition shared with the
    downstream verifier (spec section 1 check 4: "the same numeric definitions
    as strict_verify plus claim_atom_extractor").

    Uses claim_atom_extractor._NUMBER_ATOM_RE, whose ``(?<![A-Za-z0-9_.])``
    lookbehind correctly excludes the ``1`` embedded in "HbA1c" (preceded by a
    letter) while still catching ``-1.86``, ``99.9``, and ranges. The bare
    strict_verify._decimals pattern (no boundary) over-tokenizes "HbA1c" into a
    junk ``1`` that would both over-strict the numbers-in-span pre-filter AND let
    a non-numeric claim spuriously satisfy the numeric->atom map (via
    ``"1" in atom_literal``). The boundary-aware regex is therefore the
    authoritative tokenizer here. The AUTHORITATIVE numeric verdict is still
    delegated to verify_sentence_provenance(require_number_match=True) downstream
    (check 5), which runs strict_verify's full numbers-in-span machinery — this
    pre-filter is a cheap, boundary-correct subset of it.

    claim_atom_extractor is imported lazily so this module does not couple to its
    import graph at load. claim_atom_extractor + strict_verify are UNCHANGED.
    """
    from src.polaris_graph.generator.claim_atom_extractor import _NUMBER_ATOM_RE

    nums: set[str] = set()
    for m in _NUMBER_ATOM_RE.finditer(text):
        raw = m.group("value").strip()
        if not raw:
            continue
        nums.add(raw)
        # sign-normalize the unicode minus so "-1.86" and the unicode-minus form
        # both count as the same number.
        nums.add(raw.replace("−", "-"))
    return nums


def _all_numbers_in_span(
    claim: str, numbers: list[str], support_quote: str,
) -> bool:
    """Every number asserted in the claim (and the declared `numbers` list) must
    appear in the support span. One-way constraint, identical in spirit to
    strict_verify's numeric_mismatch check. The authoritative numeric verdict is
    still delegated to verify_sentence_provenance(require_number_match=True); this
    is the cheap local pre-filter so an out-of-span number is rejected before the
    (more expensive) entailment call."""
    span_numbers = _numbers_in_text(support_quote)
    claim_numbers = _numbers_in_text(claim)
    declared = {str(n) for n in numbers}
    declared_numeric = {n for n in declared if _numbers_in_text(n)}
    required = claim_numbers | declared_numeric
    return required.issubset(span_numbers)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Atom matching (spec Â§1: numeric findings must map to a section-local atom)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _match_atom_ids(
    *,
    evidence_id: str,
    numbers: set[str],
    section_atoms: dict[str, Any],
) -> list[str]:
    """Deterministic atom match rule:

    A finding maps to a section-local atom iff the atom shares the finding's
    evidence_id AND one of the finding's numbers equals the atom's `value` OR
    appears in the atom's `literal_text`. Returns the sorted matched atom_ids.

    Numeric findings with NO matching section-local atom are rejected upstream,
    because the downstream atom validator only sees the section catalog (spec Â§1).
    """
    matched: list[str] = []
    for aid, atom in sorted(section_atoms.items()):
        if getattr(atom, "evidence_id", "") != evidence_id:
            continue
        atom_value = str(getattr(atom, "value", "") or "")
        atom_literal = str(getattr(atom, "literal_text", "") or "")
        # Tokenize BOTH sides with the boundary-aware tokenizer so a finding
        # number matches an atom only on a WHOLE-number basis (e.g. "2.30" does
        # NOT match inside "12.301"). Same boundary class as the tokenizer fix.
        atom_numbers = _numbers_in_text(atom_value) | _numbers_in_text(atom_literal)
        if numbers & atom_numbers:
            matched.append(aid)
    return matched


def _distill_fuzzy_min_overlap_frac() -> float:
    """Min fraction of the quote's content words that must appear in a candidate
    source window for #1217 fuzzy span recovery to ACCEPT it (LAW VI: env-tunable,
    default 0.6). Higher = stricter recovery."""
    try:
        return float(resolve("PG_DISTILL_FUZZY_MIN_OVERLAP"))
    except ValueError:
        return 0.6


def _fuzzy_locate_span(quote: str, source: str) -> Optional[tuple[int, int]]:
    """#1217 Bug B fix (Codex pre-approved candidate (c), CONSTRAINED): recover the
    REAL source window that best matches a PARAPHRASED MAP support_quote, or None.

    The MAP model frequently paraphrases (drops markdown italics like ``_S.
    cerevisiae_``; atomizes one source sentence into several) so the quote is not a
    verbatim or whitespace-flexible substring — the live probe on the CDC safety
    source rejected all 3 contraindication findings here ("3 proposed, 0 validated"),
    the exact claims the legacy arm verified. This finds the source window with the
    highest content-word overlap with the quote and ACCEPTS it only if the overlap
    meets a threshold, then SHRINKS to the tight span between the first and last
    matched content word. Faithfulness-safe (Codex constraint): it returns a GENUINE
    source slice — NEVER the model's paraphrase text — and the claim is still
    entailment-checked against it, then the final REDUCE prose is re-checked by the
    UNCHANGED strict_verify, so a wrong recovery can never publish an unsupported
    claim. It only RAISES recall to parity with the final gate's own span binder."""
    from src.polaris_graph.generator.provenance_generator import _content_words

    qwords = _content_words(quote)
    if len(qwords) < 2:
        return None  # too little signal to recover safely
    need = max(2, int(_distill_fuzzy_min_overlap_frac() * len(qwords) + 0.9999))

    n = len(source)
    window = min(n, max(200, len(quote) * 2))
    stride = max(20, window // 8)

    best: Optional[tuple[int, int]] = None
    best_ov = 0
    starts = list(range(0, max(1, n - window + 1), stride))
    starts.append(max(0, n - window))  # always include the tail window
    for i in starts:
        end = min(i + window, n)
        ov = len(qwords & _content_words(source[i:end]))
        if ov > best_ov:
            best_ov = ov
            best = (i, end)
    if best is None or best_ov < need:
        return None

    # Localize to the matched content-word region, then EXPAND to the enclosing
    # clause/sentence boundary — do NOT shrink to the first/last content word.
    # #1217 Codex diff-gate P2 (clinical faithfulness): a tight content-word shrink
    # drops leading FUNCTION words, so a source clause "... are not recommended for
    # immunocompromised patients" would shrink to "recommended for immunocompromised
    # patients" — flipping the negation BEFORE the per-finding entailment check sees
    # it. Widening each side to the nearest sentence terminator keeps "not"/"no"/
    # "without"/qualifier words inside the span so the entailment gate judges the TRUE
    # meaning. (The final strict_verify still rebinds against the original evidence
    # row, but the fuzzy gate must not be blind to negation.)
    wstart, wend = best
    win = source[wstart:wend]
    first_off: Optional[int] = None
    last_off: Optional[int] = None
    for m in re.finditer(r"[A-Za-z0-9]+", win):
        if m.group(0).lower() in qwords:
            if first_off is None:
                first_off = m.start()
            last_off = m.end()
    if first_off is None or last_off is None:
        return best
    # Left boundary: just after the previous sentence terminator (. ! ? or newline).
    left = max(win.rfind(".", 0, first_off), win.rfind("\n", 0, first_off),
               win.rfind("!", 0, first_off), win.rfind("?", 0, first_off))
    start_off = left + 1 if left >= 0 else 0
    while start_off < first_off and win[start_off] in " \t\r\n":
        start_off += 1
    # Right boundary: through the next sentence terminator at/after the last match.
    m_end = re.search(r"[.\n!?]", win[last_off:])
    end_off = last_off + m_end.end() if m_end else len(win)
    return wstart + start_off, wstart + end_off


def _locate_span_with_method(quote: str, source: str) -> Optional[tuple[int, int, str]]:
    """Locate ``quote`` inside ``source``, returning (start, end, method) of the
    REAL source slice, or None. ``method`` ∈ {"exact", "stripped", "whitespace",
    "fuzzy"} — the caller uses it to apply an EXTRA entailment gate to the riskier
    "fuzzy" (paraphrase-recovered) case (#1217).

    I-perm-016 / #1217: the MAP model rarely copies a span VERBATIM — it reformats
    whitespace/newlines AND paraphrases (drops markdown italics, atomizes a source
    sentence). An exact-substring-only check rejected ~most findings, collapsing the
    distillate to empty. We recover the real span at four escalating tolerances; the
    output gates (entailment + the final strict_verify) remain the authority on the
    prose, and "fuzzy" recoveries get an additional blocking entailment check in
    `_validate_finding` so a meaning-changing paraphrase (e.g. "all" -> "some",
    negation flips) cannot enter the ledger on content-word overlap alone."""
    if not quote or not source:
        return None
    i = source.find(quote)
    if i >= 0:
        return i, i + len(quote), "exact"
    stripped = quote.strip()
    if stripped and stripped != quote:
        i = source.find(stripped)
        if i >= 0:
            return i, i + len(stripped), "stripped"
    toks = stripped.split()
    if not toks:
        return None
    # Same tokens, any whitespace run between them (newline/space reformatting).
    pattern = r"\s+".join(re.escape(t) for t in toks)
    try:
        m = re.search(pattern, source)
    except re.error:
        m = None
    if m:
        return m.start(), m.end(), "whitespace"
    # #1217 Bug B: exact + whitespace-flexible failed -> the MAP paraphrased the
    # quote (markdown italics dropped, source sentence atomized). Recover the REAL
    # source window by content-word overlap (CONSTRAINED, threshold-gated). Returns a
    # genuine source slice or None; the caller adds a blocking entailment gate.
    fz = _fuzzy_locate_span(stripped, source)
    if fz is not None:
        return fz[0], fz[1], "fuzzy"
    return None


def _locate_span_in_source(quote: str, source: str) -> Optional[tuple[int, int]]:
    """Backward-compatible wrapper: (start, end) of the REAL source slice, or None.
    See `_locate_span_with_method` for the recovery tolerances."""
    r = _locate_span_with_method(quote, source)
    return None if r is None else (r[0], r[1])


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# MAP validation â€” fail-closed (spec Â§1)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _validate_finding(
    raw: dict,
    *,
    evidence_id: str,
    direct_quote: str,
    tier: str,
    evidence_pool: dict[str, dict[str, Any]],
    section_atoms: dict[str, Any],
    finding_id: str,
    raw_index: int = -1,
) -> Optional[DistilledFinding]:
    """Validate one raw MAP finding fail-closed. Returns the DistilledFinding on
    success, or None if it fails a BLOCKING check (the source then falls to a
    validation_failed CoverageRow if no finding survives).

    Checks (in order; only steps 1-3 are BLOCKING after the #1217 recall fixes):
      1. (BLOCKING) support_quote is LOCATABLE in direct_quote, tolerant of
         whitespace/newline reformatting (`_locate_span_in_source`); a reworded
         quote is unlocatable -> reject.
      2. Offsets: if supplied offsets already point at a matching occurrence keep
         them; otherwise use the located (recovered) span.
      3. (BLOCKING) direct_quote[start:end] is non-empty.
      4. (NON-BLOCKING, #1217) numbers-in-span is computed for telemetry only; it
         never rejects — strict_verify re-checks numbers against the final span.
      5. Atom mapping: a numeric finding with NO section-local atom is KEPT
         (atom_ids stays []) per the #1209 Codex diff-gate ruling.
      6. Per-finding entailment is computed via the UNCHANGED production verifier.
         It is NON-BLOCKING for exact/whitespace matches; BLOCKING for a FUZZY
         (paraphrase-recovered) span (#1217) — a fuzzy span was matched on
         content-word overlap, blind to meaning-changing function words, so it must
         additionally ENTAIL the claim. A verifier EXCEPTION rejects (fail-closed).
         The FINAL per-sentence strict_verify on the REDUCE prose remains the SOLE
         publication authority for all paths.

    raw_index: the 0-based index of this finding in the MAP `findings` array, used
    for #1217 PG_DISTILL_DEBUG reject tracing (rejected findings do NOT consume a
    finding_id, so finding_id alone cannot disambiguate which proposal was killed).
    """
    _dbg = resolve("PG_DISTILL_DEBUG").strip().lower() in ("1", "true", "yes", "on")

    def _rej(step: str, reason: str) -> None:
        """#1217 diagnostic: log which validation STEP killed this proposal (keyed on
        evidence_id + raw_index) then return None. Logging only — no behavior change."""
        if _dbg:
            logger.warning(
                "[DISTILL_DEBUG] REJECT ev=%s raw_index=%d step=%s reason=%s claim=%r",
                evidence_id, raw_index, step, reason,
                str(raw.get("claim", ""))[:90],
            )
        return None

    claim = str(raw.get("claim", "") or "").strip()
    support_quote = str(raw.get("support_quote", "") or "")
    if not claim or not support_quote:
        return _rej("step0_empty", "empty claim or support_quote")

    # (1) Locate support_quote in direct_quote, TOLERANT of whitespace/newline
    # reformatting (the MAP model rarely copies verbatim). On a hit we ADOPT the
    # real source slice as support_quote below — faithfulness-safe (same words,
    # real offsets). A reworded quote stays unlocatable -> reject. (#1217: the
    # prior exact-substring-only check rejected ~most findings -> empty distillate
    # -> section collapse. The MAP filter is an EXTRACTION filter; strict_verify +
    # the 4-role gate remain the authority on the final prose.)
    located = _locate_span_with_method(support_quote, direct_quote)
    if located is None:
        return _rej("step1_locate", "support_quote not locatable in direct_quote (reworded/paraphrased)")
    loc_start, loc_end, locate_method = located

    # (2) Offset reconciliation: prefer the model's supplied offsets ONLY if they
    # already point at the EXACT support_quote (handles duplicate occurrences);
    # otherwise use the located (recovered) span.
    try:
        supplied_start = int(raw.get("span_start", -1))
        supplied_end = int(raw.get("span_end", -1))
    except (TypeError, ValueError):
        supplied_start, supplied_end = -1, -1

    if (
        0 <= supplied_start < supplied_end <= len(direct_quote)
        and direct_quote[supplied_start:supplied_end] == support_quote
    ):
        span_start, span_end = supplied_start, supplied_end
        locate_method = "exact"  # model offsets pointed at the exact quote
    else:
        span_start, span_end = loc_start, loc_end

    # (3) Adopt the REAL source slice as support_quote (this is what the
    # whitespace-flexible recovery returns) and re-assert it is non-empty.
    support_quote = direct_quote[span_start:span_end]
    if not support_quote.strip():
        return _rej("step3_empty_slice", "recovered source slice is empty/whitespace")

    # Parse declared numbers/entities defensively.
    raw_numbers = raw.get("numbers") or []
    numbers = [str(n) for n in raw_numbers if str(n).strip()]
    raw_entities = raw.get("entities") or []
    entities = [str(e) for e in raw_entities if str(e).strip()]
    caveat = str(raw.get("caveat", "") or "").strip()
    contradiction_key = str(raw.get("contradiction_key", "") or "").strip()
    source_tier = str(raw.get("source_tier", "") or tier or "").strip()

    # (4) Numbers-in-span local check is NON-BLOCKING (#1217 RECALL fix — both
    # Claude AND Codex independent re-forensics AGREE on candidate (b)). This was a
    # hard `return None` reject; it collapsed distill recall below legacy on the
    # drb_76 Safety replay (legacy kept 6 numeric-heavy sentences; distill kept the
    # ONE non-numeric claim). The reject is pure recall loss with ZERO faithfulness
    # benefit: this narrow-`support_quote` pre-filter is STRICTER than the final
    # gate, which re-fits an 800-char prose-matched span over the whole direct_quote
    # (`_find_best_span_for_sentence`, live_deepseek_generator.py:244) and re-runs
    # strict_verify `require_number_match=True` on it. Concrete killer (Codex): the
    # CDC stat "14 (95% CI 4-44)" tokenizes "4-44" as ONE range token here, while the
    # model declares "4" and "44" separately, so a perfectly extractable numeric
    # finding is rejected before REDUCE ever sees it — even though final strict_verify
    # normalizes the range dash and would accept/drop the published span correctly.
    # Its own docstring states this is only a "cheap local pre-filter ... before the
    # (more expensive) entailment call"; entailment is already non-blocking at step
    # (6) below, so the pre-filter's sole rationale is dead. Mirrors the step-(6)
    # treatment exactly: compute the boolean for telemetry, NEVER gate on it.
    # Faithfulness UNCHANGED: strict_verify on the final REDUCE prose stays the SOLE
    # publication authority (numbers-in-span AND >=2 content-word overlap AND
    # enforce-mode entailment); 4-role / D8 byte-untouched.
    numbers_in_span = _all_numbers_in_span(claim, numbers, support_quote)
    if not numbers_in_span:
        logger.debug(
            "[evidence_distiller] finding %s/%s: declared numbers not all inside the "
            "narrow support_quote (KEPT — non-blocking per #1217; the final "
            "strict_verify re-checks numbers against the prose-matched span)",
            evidence_id, finding_id,
        )

    # (5) Atom mapping for numeric findings.
    claim_numbers = _numbers_in_text(claim)
    atom_ids: list[str] = []
    if claim_numbers:
        atom_ids = _match_atom_ids(
            evidence_id=evidence_id,
            numbers=claim_numbers,
            section_atoms=section_atoms,
        )
        # I-perm-016 (#1209) Codex diff-gate iter-1 P1 ruling: KEEP a numeric
        # finding that has NO matching section-local atom (atom_ids stays []),
        # do NOT reject. `claim_atom_extractor` routes each minted atom to a
        # SINGLE primary_section, so a span-exact + numbers-in-span + ENTAILED
        # finding in a non-matching section would otherwise be shed solely on a
        # cataloguing artifact â€” lowering verified coverage on the safety/
        # incidence-heavy drb_76 replay (the OPPOSITE of this keystone's goal).
        # Faithfulness is unaffected: step (6) below still gates the finding
        # through the UNCHANGED production verifier (numbers-in-span AND
        # span-entails-claim), and the final REDUCE prose is re-checked by the
        # unchanged strict_verify. A kept empty-atom_ids finding renders NO
        # (atom_NNN) marker, so the default-OFF atom_refusal_validator treats it
        # as narrative-only. (Codex: "choose (b) ... faithfulness-safe".)

    # (6) Per-finding entailment via the UNCHANGED production verifier path —
    # BLOCKING for FUZZY recoveries ONLY, and the verifier is CALLED only for them.
    # A fuzzy span was matched on content-word OVERLAP, blind to meaning-changing
    # function words ("all"->"some", negation flips), so it must additionally ENTAIL
    # the claim. Exact/whitespace matches are verbatim source text that cannot drift
    # in meaning, so their per-finding entailment was NON-BLOCKING — and #1217 Codex
    # diff-gate P2 (perf) flagged that calling verify_sentence_provenance for EVERY
    # finding made MAXEV=40 prohibitively slow. We therefore SKIP the (slow) verifier
    # call entirely for exact/whitespace, since its verdict never gated them. The
    # final per-sentence strict_verify on the REDUCE prose remains the SOLE
    # publication authority for ALL paths.
    finding_entailed = True  # exact/whitespace: verbatim, gated downstream by strict_verify
    if locate_method == "fuzzy":
        probe = f"{claim} [#ev:{evidence_id}:{span_start}-{span_end}]"
        try:
            verdict = verify_sentence_provenance(
                probe, evidence_pool, require_number_match=True,
            )
        except Exception as exc:  # noqa: BLE001 — fail closed on any verifier error
            logger.warning(
                "[evidence_distiller] verifier raised on finding %s/%s: %s — rejecting",
                evidence_id, finding_id, exc,
            )
            return _rej("step6_verifier_error", f"verify_sentence_provenance raised: {exc}")
        finding_entailed = bool(getattr(verdict, "is_verified", False))
        if not finding_entailed:
            return _rej("step6_fuzzy_not_entailed",
                        "fuzzy-recovered (paraphrased) span does not entail the claim")
    if _dbg:
        logger.warning(
            "[DISTILL_DEBUG] KEPT ev=%s raw_index=%d finding_id=%s method=%s entailed=%s numbers_in_span=%s claim=%r",
            evidence_id, raw_index, finding_id, locate_method, finding_entailed, numbers_in_span,
            claim[:90],
        )

    return DistilledFinding(
        finding_id=finding_id,
        evidence_id=evidence_id,
        claim=claim,
        span_start=span_start,
        span_end=span_end,
        support_quote=support_quote,
        numbers=numbers,
        entities=entities,
        caveat=caveat,
        contradiction_key=contradiction_key,
        source_tier=source_tier,
        atom_ids=atom_ids,
    )


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Atom rows for the MAP prompt
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _atom_rows_for_evidence(
    evidence_id: str, section_atoms: dict[str, Any],
) -> str:
    """Render the section-local numeric atoms for ONE evidence_id as compact rows
    for the MAP prompt's NUMERIC_ATOMS_AVAILABLE block."""
    rows: list[str] = []
    for aid, atom in sorted(section_atoms.items()):
        if getattr(atom, "evidence_id", "") != evidence_id:
            continue
        value = getattr(atom, "value", "")
        unit = getattr(atom, "unit", "")
        endpoint = getattr(atom, "endpoint", "")
        entity = getattr(atom, "entity", "")
        rows.append(
            f"{aid}: value={value}{(' ' + unit) if unit else ''} "
            f"endpoint={endpoint}"
            + (f" entity={entity}" if entity else "")
        )
    return "\n".join(rows) if rows else "(none)"


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# MAP â€” one LLM call per source (or 1..3 micro-batch)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _findings_to_cache_dicts(validated: list[DistilledFinding]) -> list[dict]:
    """Serialize VALIDATED findings to the per-source cache dict shape."""
    return [
        {
            "claim": f.claim,
            "support_quote": f.support_quote,
            "span_start": f.span_start,
            "span_end": f.span_end,
            "numbers": f.numbers,
            "entities": f.entities,
            "caveat": f.caveat,
            "contradiction_key": f.contradiction_key,
            "source_tier": f.source_tier,
            "atom_ids": f.atom_ids,
        }
        for f in validated
    ]


def _cache_lookup_one(
    ev: dict[str, Any],
    *,
    section_title: str,
    section_focus: str,
    cache_dir: Path,
    finding_id_prefix: str,
) -> Optional[tuple[list[DistilledFinding], CoverageRow, int, int, int]]:
    """Per-source cache lookup. Returns the cache-hit 5-tuple, or None on miss.

    F28 (#1255): the cache is PER SOURCE (key = section + evidence_id + quote
    hash). Both the single-source and micro-batch MAP paths reuse this so caching
    granularity is UNCHANGED by batching — only sources that miss the cache are
    sent to a live MAP call, batched or not."""
    evidence_id = ev.get("evidence_id", "") or ""
    direct_quote = ev.get("direct_quote", "") or ""
    tier = str(ev.get("tier", "") or "")
    if not evidence_id or not direct_quote:
        return None
    key = _cache_key(
        section_title=section_title, section_focus=section_focus,
        evidence_id=evidence_id, direct_quote=direct_quote,
    )
    cached = _cache_load(cache_dir, key)
    if cached is None:
        return None
    findings = [
        DistilledFinding(
            finding_id=f"{finding_id_prefix}{i:03d}",
            evidence_id=evidence_id,
            claim=d["claim"],
            span_start=d["span_start"],
            span_end=d["span_end"],
            support_quote=d["support_quote"],
            numbers=list(d.get("numbers", [])),
            entities=list(d.get("entities", [])),
            caveat=d.get("caveat", ""),
            contradiction_key=d.get("contradiction_key", ""),
            source_tier=d.get("source_tier", tier),
            atom_ids=list(d.get("atom_ids", [])),
        )
        for i, d in enumerate(cached)
    ]
    if findings:
        return (
            findings,
            CoverageRow(
                evidence_id=evidence_id, status="mapped",
                n_findings=len(findings), reason="cache_hit",
            ),
            0, 0, 1,
        )
    return (
        [],
        CoverageRow(
            evidence_id=evidence_id, status="no_relevant_findings",
            n_findings=0, reason="cache_hit_empty",
        ),
        0, 0, 1,
    )


def _validate_and_store_one_source(
    *,
    ev: dict[str, Any],
    raw_findings: list,
    no_relevant: bool,
    no_relevant_reason: str,
    section_title: str,
    section_focus: str,
    evidence_pool: dict[str, dict[str, Any]],
    section_atoms: dict[str, Any],
    cache_dir: Path,
    finding_id_prefix: str,
) -> tuple[list[DistilledFinding], CoverageRow]:
    """Validate ONE source's raw MAP findings fail-closed AGAINST THAT SOURCE'S
    OWN direct_quote (F28 cross-source-contamination guard), store the VALIDATED
    cache entry, and return (findings, coverage_row).

    This is the SOLE validation entrypoint for both the single-source and the
    micro-batch MAP paths, so a batched finding can NEVER be located/validated
    against another source's text — `direct_quote` here is always THIS ev's quote,
    routed by `evidence_id`. The faithfulness gates downstream are unchanged."""
    evidence_id = ev.get("evidence_id", "") or ""
    direct_quote = ev.get("direct_quote", "") or ""
    tier = str(ev.get("tier", "") or "")

    if no_relevant:
        return (
            [],
            CoverageRow(
                evidence_id=evidence_id, status="no_relevant_findings",
                n_findings=0,
                reason=(no_relevant_reason or "no_relevant_findings")[:200],
            ),
        )

    if not isinstance(raw_findings, list):
        return (
            [],
            CoverageRow(
                evidence_id=evidence_id, status="map_failed",
                n_findings=0, reason="findings_not_a_list",
            ),
        )

    validated: list[DistilledFinding] = []
    for i, rf in enumerate(raw_findings):
        if not isinstance(rf, dict):
            continue
        finding = _validate_finding(
            rf,
            evidence_id=evidence_id,
            direct_quote=direct_quote,  # F28: THIS source's quote, never the batch's
            tier=tier,
            evidence_pool=evidence_pool,
            section_atoms=section_atoms,
            finding_id=f"{finding_id_prefix}{len(validated):03d}",
            raw_index=i,
        )
        if finding is not None:
            validated.append(finding)

    if not validated:
        # The model proposed findings but NONE survived validation. Fail-closed
        # coverage so the source is visible, not silently dropped.
        return (
            [],
            CoverageRow(
                evidence_id=evidence_id, status="validation_failed",
                n_findings=0,
                reason=f"{len(raw_findings)} proposed, 0 validated",
            ),
        )

    # Cache VALIDATED outputs only, under THIS source's per-source key.
    key = _cache_key(
        section_title=section_title, section_focus=section_focus,
        evidence_id=evidence_id, direct_quote=direct_quote,
    )
    _cache_store(cache_dir, key, _findings_to_cache_dicts(validated))
    return (
        validated,
        CoverageRow(
            evidence_id=evidence_id, status="mapped",
            n_findings=len(validated), reason="",
        ),
    )


async def _map_one_source(
    ev: dict[str, Any],
    *,
    section_title: str,
    section_focus: str,
    model: str,
    evidence_pool: dict[str, dict[str, Any]],
    section_atoms: dict[str, Any],
    cache_dir: Path,
    finding_id_prefix: str,
    research_question: str = "",
) -> tuple[list[DistilledFinding], CoverageRow, int, int, int]:
    """Distill ONE source. Returns (findings, coverage_row, in_tok, out_tok,
    cache_hit). Cache stores VALIDATED finding dicts only.

    This is the micro-batch-size-1 path (byte-identical to the pre-F28 single
    call). The micro-batch (size>1) path is `_map_microbatch`."""
    evidence_id = ev.get("evidence_id", "") or ""
    direct_quote = ev.get("direct_quote", "") or ""
    tier = str(ev.get("tier", "") or "")
    statement = ev.get("statement", "") or ""

    if not evidence_id or not direct_quote:
        return (
            [],
            CoverageRow(
                evidence_id=evidence_id, status="no_relevant_findings",
                n_findings=0, reason="empty evidence_id or direct_quote",
            ),
            0, 0, 0,
        )

    # â”€â”€ cache â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    cached = _cache_lookup_one(
        ev, section_title=section_title, section_focus=section_focus,
        cache_dir=cache_dir, finding_id_prefix=finding_id_prefix,
    )
    if cached is not None:
        return cached

    # â”€â”€ live MAP call â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    from src.polaris_graph.llm.openrouter_client import OpenRouterClient

    atom_rows = _atom_rows_for_evidence(evidence_id, section_atoms)
    user = _render_map_user(
        section_title=section_title, section_focus=section_focus,
        evidence_id=evidence_id, tier=tier, statement=statement,
        direct_quote=direct_quote, atom_rows=atom_rows,
        research_question=research_question,
    )
    messages = [
        {"role": "system", "content": _MAP_SYSTEM},
        {"role": "user", "content": user},
    ]

    client = OpenRouterClient(model=model)
    in_tok = out_tok = 0
    try:
        resp = await _call_distill_map_with_wall(
            client,
            messages=messages,
            reasoning_enabled=False,
            temperature=0.1,
            max_tokens=_map_max_tokens(),
            response_format=(None if _map_text_mode() else {"type": "json_object"}),
            reasoning_max_tokens=_map_reasoning_tokens(),
        )
        in_tok = getattr(resp, "input_tokens", 0) or 0
        out_tok = getattr(resp, "output_tokens", 0) or 0
        parsed = _parse_map_json(
            getattr(resp, "content", None), getattr(resp, "reasoning", None),
        )
    except Exception as exc:  # noqa: BLE001 â€” a MAP failure must not crash the section
        logger.warning(
            "[evidence_distiller] MAP call failed for %s: %s â€” coverage row map_failed",
            evidence_id, exc,
        )
        return (
            [],
            CoverageRow(
                evidence_id=evidence_id, status="map_failed",
                n_findings=0, reason=str(exc)[:200],
            ),
            in_tok, out_tok, 0,
        )
    finally:
        if hasattr(client, "close"):
            try:
                await client.close()
            except Exception:  # noqa: BLE001
                pass

    if parsed is None:
        return (
            [],
            CoverageRow(
                evidence_id=evidence_id, status="map_failed",
                n_findings=0, reason="unparseable_json",
            ),
            in_tok, out_tok, 0,
        )

    findings, cov = _validate_and_store_one_source(
        ev=ev,
        raw_findings=parsed.get("findings") or [],
        no_relevant=parsed.get("no_relevant_findings") is True,
        no_relevant_reason=str(parsed.get("no_relevant_reason", "") or ""),
        section_title=section_title, section_focus=section_focus,
        evidence_pool=evidence_pool, section_atoms=section_atoms,
        cache_dir=cache_dir, finding_id_prefix=finding_id_prefix,
    )
    return (findings, cov, in_tok, out_tok, 0)


def _render_map_batch_user(
    *,
    section_title: str,
    section_focus: str,
    sources: list[dict[str, str]],
    research_question: str = "",
) -> str:
    """Render the MAP user prompt for a MICRO-BATCH of 2..3 sources (F28 #1255).

    Each source is presented with its OWN EVIDENCE_ID + DIRECT_QUOTE + atoms, and
    the model returns a JSON object keyed by evidence_id. The per-source extraction
    rules are byte-identical to the single-source prompt; only the envelope groups
    several sources to amortize the request. Findings are STILL routed back to
    each source's own direct_quote for validation (see `_validate_and_store_one_
    source`), so batching never crosses provenance between sources."""
    _rq = (research_question or "").strip()
    rq_line = (
        "RESEARCH_QUESTION (framing only — extract findings ONLY from each "
        f"source's DIRECT_QUOTE, never from this line): {_rq}\n\n"
        if _rq
        else ""
    )
    blocks: list[str] = []
    for s in sources:
        blocks.append(
            f"=== SOURCE evidence_id={s['evidence_id']} (SOURCE_TIER={s['tier']}) ===\n"
            f"STATEMENT: {s['statement']}\n"
            f"DIRECT_QUOTE:\n{s['direct_quote']}\n\n"
            f"NUMERIC_ATOMS_AVAILABLE:\n{s['atom_rows']}\n"
        )
    sources_block = "\n".join(blocks)
    ids = ", ".join(s["evidence_id"] for s in sources)
    return (
        f"{rq_line}"
        f"SECTION_TITLE: {section_title}\n"
        f"SECTION_FOCUS: {section_focus}\n\n"
        f"You are given {len(sources)} sources. Extract findings for EACH one "
        "INDEPENDENTLY, using ONLY that source's own DIRECT_QUOTE.\n\n"
        f"{sources_block}\n"
        "Return JSON of the form:\n"
        "{\n"
        '  "by_source": {\n'
        '    "<evidence_id>": {\n'
        '      "no_relevant_findings": false,\n'
        '      "no_relevant_reason": "",\n'
        '      "findings": [\n'
        "        {\n"
        '          "claim": "single atomic claim",\n'
        '          "support_quote": "exact substring from THIS source DIRECT_QUOTE",\n'
        '          "span_start": 0,\n'
        '          "span_end": 0,\n'
        '          "numbers": [],\n'
        '          "entities": [],\n'
        '          "caveat": "",\n'
        '          "contradiction_key": "",\n'
        '          "source_tier": "T1"\n'
        "        }\n"
        "      ]\n"
        "    }\n"
        "  }\n"
        "}\n"
        f"Provide a key for EVERY one of these evidence_ids: {ids}. "
        "Each finding's support_quote MUST be an EXACT contiguous substring of "
        "THAT SAME source's DIRECT_QUOTE (never another source's). Every number "
        "in a claim must appear in its support_quote; do not round; do not combine "
        "multiple claims; split scattered numbers into separate findings. If a "
        "source has no section-relevant finding, set no_relevant_findings=true "
        "with a reason."
    )


async def _map_microbatch(
    evs: list[dict[str, Any]],
    *,
    section_title: str,
    section_focus: str,
    model: str,
    evidence_pool: dict[str, dict[str, Any]],
    section_atoms: dict[str, Any],
    cache_dir: Path,
    finding_id_prefixes: list[str],
    research_question: str = "",
) -> list[tuple[list[DistilledFinding], CoverageRow, int, int, int]]:
    """Distill a MICRO-BATCH of 2..3 CACHE-MISS sources in ONE MAP call (F28).

    Returns one 5-tuple PER input source (index-aligned to `evs`), so the caller's
    "no source disappears" invariant holds even when a whole batch fails. Each
    source's findings are validated against ITS OWN direct_quote and stored under
    ITS OWN per-source cache key. A batch-level MAP/parse failure yields a
    map_failed CoverageRow for EVERY source in the batch (fail-closed)."""
    # Defensive: an empty batch maps to nothing.
    if not evs:
        return []
    # A size-1 batch is exactly the single-source path (byte-identical).
    if len(evs) == 1:
        one = await _map_one_source(
            evs[0],
            section_title=section_title, section_focus=section_focus,
            model=model, evidence_pool=evidence_pool, section_atoms=section_atoms,
            cache_dir=cache_dir, finding_id_prefix=finding_id_prefixes[0],
            research_question=research_question,
        )
        return [one]

    from src.polaris_graph.llm.openrouter_client import OpenRouterClient

    # Drop rows with no id/quote up front so the live call only sees valid sources;
    # they get their own no_relevant_findings coverage row (never silently dropped).
    valid_idx: list[int] = []
    sources: list[dict[str, str]] = []
    for j, ev in enumerate(evs):
        eid = ev.get("evidence_id", "") or ""
        dq = ev.get("direct_quote", "") or ""
        if not eid or not dq:
            continue
        valid_idx.append(j)
        sources.append({
            "evidence_id": eid,
            "tier": str(ev.get("tier", "") or ""),
            "statement": ev.get("statement", "") or "",
            "direct_quote": dq,
            "atom_rows": _atom_rows_for_evidence(eid, section_atoms),
        })

    results: list[Optional[tuple[list[DistilledFinding], CoverageRow, int, int, int]]] = [
        None
    ] * len(evs)

    # Empty-evidence rows -> no_relevant_findings coverage row.
    for j, ev in enumerate(evs):
        if j not in valid_idx:
            results[j] = (
                [],
                CoverageRow(
                    evidence_id=ev.get("evidence_id", "") or "",
                    status="no_relevant_findings",
                    n_findings=0, reason="empty evidence_id or direct_quote",
                ),
                0, 0, 0,
            )

    if not sources:
        # All rows were empty-evidence; every index is already filled above.
        return [r for r in results]  # type: ignore[misc]

    user = _render_map_batch_user(
        section_title=section_title, section_focus=section_focus,
        sources=sources, research_question=research_question,
    )
    messages = [
        {"role": "system", "content": _MAP_SYSTEM},
        {"role": "user", "content": user},
    ]
    client = OpenRouterClient(model=model)
    in_tok = out_tok = 0
    parsed: Optional[dict] = None
    map_error: Optional[str] = None
    try:
        resp = await _call_distill_map_with_wall(
            client,
            messages=messages,
            reasoning_enabled=False,
            temperature=0.1,
            max_tokens=_map_max_tokens(),
            response_format=(None if _map_text_mode() else {"type": "json_object"}),
            reasoning_max_tokens=_map_reasoning_tokens(),
        )
        in_tok = getattr(resp, "input_tokens", 0) or 0
        out_tok = getattr(resp, "output_tokens", 0) or 0
        parsed = _parse_map_json(
            getattr(resp, "content", None), getattr(resp, "reasoning", None),
        )
    except Exception as exc:  # noqa: BLE001 — a MAP failure must not crash the section
        map_error = str(exc)[:200]
        logger.warning(
            "[evidence_distiller] MAP micro-batch call failed for %s: %s — "
            "map_failed for the whole batch",
            ",".join(s["evidence_id"] for s in sources), exc,
        )
    finally:
        if hasattr(client, "close"):
            try:
                await client.close()
            except Exception:  # noqa: BLE001
                pass

    by_source: dict[str, Any] = {}
    parse_failed = parsed is None
    if not parse_failed:
        bs = parsed.get("by_source")  # type: ignore[union-attr]
        if isinstance(bs, dict):
            by_source = bs
        else:
            parse_failed = True

    # The batch's token cost is recorded ONCE, on the first valid source, so the
    # section totals are not double-counted across the batch members.
    cost_assigned = False
    for j in valid_idx:
        ev = evs[j]
        # locate this source's prefix
        prefix = finding_id_prefixes[j]
        eid = ev.get("evidence_id", "") or ""
        this_in = in_tok if not cost_assigned else 0
        this_out = out_tok if not cost_assigned else 0

        if map_error is not None or parse_failed:
            reason = map_error if map_error is not None else "unparseable_json"
            results[j] = (
                [],
                CoverageRow(
                    evidence_id=eid, status="map_failed",
                    n_findings=0, reason=reason,
                ),
                this_in, this_out, 0,
            )
            cost_assigned = True
            continue

        entry = by_source.get(eid)
        if not isinstance(entry, dict):
            # The model omitted this source's key entirely -> fail-closed map_failed
            # (the source is visible, never silently dropped).
            results[j] = (
                [],
                CoverageRow(
                    evidence_id=eid, status="map_failed",
                    n_findings=0, reason="missing_in_batch_response",
                ),
                this_in, this_out, 0,
            )
            cost_assigned = True
            continue

        findings, cov = _validate_and_store_one_source(
            ev=ev,
            raw_findings=entry.get("findings") or [],
            no_relevant=entry.get("no_relevant_findings") is True,
            no_relevant_reason=str(entry.get("no_relevant_reason", "") or ""),
            section_title=section_title, section_focus=section_focus,
            evidence_pool=evidence_pool, section_atoms=section_atoms,
            cache_dir=cache_dir, finding_id_prefix=prefix,
        )
        results[j] = (findings, cov, this_in, this_out, 0)
        cost_assigned = True

    # Index-aligned to `evs`: every index is filled (valid sources above + empty-
    # evidence rows earlier), so a defensive fill guards any unexpected gap so the
    # caller's "one tuple per source" contract (and LAW II no-disappear) holds.
    for j, ev in enumerate(evs):
        if results[j] is None:
            results[j] = (
                [],
                CoverageRow(
                    evidence_id=ev.get("evidence_id", "") or "",
                    status="map_failed", n_findings=0,
                    reason="unaccounted_in_batch",
                ),
                0, 0, 0,
            )
    return [r for r in results]  # type: ignore[misc]


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Contradiction clustering (group validated findings by contradiction_key)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _cluster_contradictions(
    findings: list[DistilledFinding],
) -> list[ContradictionCluster]:
    """Group findings that share a non-empty contradiction_key AND span >=2
    distinct sources (a single-source key is not a contradiction)."""
    by_key: dict[str, list[DistilledFinding]] = {}
    for f in findings:
        if f.contradiction_key:
            by_key.setdefault(f.contradiction_key, []).append(f)
    clusters: list[ContradictionCluster] = []
    for key, group in sorted(by_key.items()):
        sources = {f.evidence_id for f in group}
        if len(sources) >= 2:
            clusters.append(
                ContradictionCluster(
                    contradiction_key=key,
                    finding_ids=[f.finding_id for f in group],
                )
            )
    return clusters


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Public: distill_section_evidence (spec Â§1)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

async def distill_section_evidence(
    section: Any,
    ev_subset: list[dict[str, Any]],
    evidence_pool: dict[str, dict[str, Any]],
    *,
    model: str,
    max_parallel: int | None = None,
    microbatch_size: int | None = None,
    cache_dir: str | Path | None = None,
    research_question: str = "",
) -> SectionDistillate:
    """MAP per-source -> validate fail-closed -> build the validated findings
    ledger for ONE section.

    Every input row in ``ev_subset`` yields either >=1 accepted finding OR a
    CoverageRow (no source silently disappears â€” LAW II). A runtime assertion at
    the end enforces this invariant.

    F28 (#1255): cache-MISS sources are grouped into MICRO-BATCHES of size
    ``PG_DISTILL_MICROBATCH_SIZE`` (clamped 1..3) and distilled in ONE MAP call
    per batch (a real >1 batch, not the prior size-1-only path). Each batched
    finding is still validated against ITS OWN source's direct_quote and cached
    under ITS OWN per-source key, so batching changes ONLY request packing —
    never provenance routing or cache granularity. Cache HITS bypass batching
    entirely (no live call). The bounded ``asyncio.Semaphore`` pool (F18) caps
    concurrent batch calls at ``PG_DISTILL_MAX_PARALLEL``.
    F21 (#1255): ``research_question`` is threaded into the MAP prompt as
    framing-only context (extraction stays bound to each source's direct_quote).
    """
    section_title = getattr(section, "title", "") or ""
    section_focus = getattr(section, "focus", "") or ""

    # Build the section atom catalog ONCE, same order/derivation as _call_section
    # (build_atom_catalog over ev_subset, then filter_atoms_for_section by title).
    full_catalog = build_atom_catalog(ev_subset)
    section_atoms = filter_atoms_for_section(full_catalog, section_title)

    resolved_cache_dir = Path(cache_dir) if cache_dir is not None else _default_cache_dir()
    parallel = max_parallel if max_parallel is not None else _max_parallel()
    parallel = max(1, parallel)
    # F28: micro-batch size, clamped 1..3 per spec. size==1 keeps the byte-identical
    # single-source path; size>1 groups cache-miss sources into a shared MAP call.
    _mb = microbatch_size if microbatch_size is not None else _microbatch_size()
    _mb = min(3, max(1, _mb))

    # Stable per-source finding-id prefix keyed by ORIGINAL ev_subset index, so
    # finding ids do not depend on batching/cache order.
    prefixes = [f"f{idx:03d}_" for idx in range(len(ev_subset))]

    # ── Pass 1: resolve the per-source cache FIRST. Hits never enter a batch. ──
    results_by_idx: list[Optional[tuple[list[DistilledFinding], CoverageRow, int, int, int]]] = [
        None
    ] * len(ev_subset)
    miss_indices: list[int] = []
    for i, ev in enumerate(ev_subset):
        hit = _cache_lookup_one(
            ev, section_title=section_title, section_focus=section_focus,
            cache_dir=resolved_cache_dir, finding_id_prefix=prefixes[i],
        )
        if hit is not None:
            results_by_idx[i] = hit
        else:
            miss_indices.append(i)

    # ── Pass 2: batch the cache MISSES into groups of _mb; one MAP call each. ──
    batches: list[list[int]] = [
        miss_indices[k:k + _mb] for k in range(0, len(miss_indices), _mb)
    ]
    semaphore = asyncio.Semaphore(parallel)

    async def _guarded_batch(idx_group: list[int]):
        async with semaphore:
            batch_evs = [ev_subset[i] for i in idx_group]
            batch_prefixes = [prefixes[i] for i in idx_group]
            return idx_group, await _map_microbatch(
                batch_evs,
                section_title=section_title,
                section_focus=section_focus,
                model=model,
                evidence_pool=evidence_pool,
                section_atoms=section_atoms,
                cache_dir=resolved_cache_dir,
                finding_id_prefixes=batch_prefixes,
                research_question=research_question,
            )

    # B19/I-arch-011 (KEYSTONE, part c): return_exceptions=True so ONE batch
    # raising (e.g. a per-call wall timeout that escapes _map_microbatch's inner
    # except, or any unexpected error in _guarded_batch) does NOT cancel the whole
    # gather and silently drop EVERY other source. A timed-out / failed batch leaves
    # its indices None here; the fail-closed None-net below converts each into a
    # LOUD `unaccounted_after_dispatch` coverage row (LAW II — never a silent drop,
    # never an unverified-as-verified claim). Breadth preserved: the siblings still
    # return their findings/rows.
    # B19/I-arch-011 (KEYSTONE, part c): return_exceptions=True so ONE batch
    # raising (e.g. a per-call wall timeout that escapes _map_microbatch's inner
    # except, or any unexpected error in _guarded_batch) does NOT cancel the whole
    # gather and silently drop EVERY other source. A timed-out / failed batch leaves
    # its indices None here; the fail-closed None-net below converts each into a
    # LOUD `unaccounted_after_dispatch` coverage row (LAW II — never a silent drop,
    # never an unverified-as-verified claim). Breadth preserved: the siblings still
    # return their findings/rows.
    batch_results = await asyncio.gather(
        *[_guarded_batch(group) for group in batches],
        return_exceptions=True,
    )
    for item in batch_results:
        if isinstance(item, BaseException):
            # A batch failed AFTER its inner except (the wall fired at the await, or
            # an unexpected error). It carries no idx_group, so we cannot emit a
            # per-source row here; we leave those indices None and let the
            # fail-closed None-net below account for every still-unfilled source.
            logger.warning(
                "[evidence_distiller] MAP batch raised past the inner guard: %r — "
                "affected sources fall through to the fail-closed coverage net",
                item,
            )
            continue
        idx_group, tuples = item
        # _map_microbatch returns one tuple per input source, index-aligned.
        for local_i, idx in enumerate(idx_group):
            results_by_idx[idx] = tuples[local_i]

    all_findings: list[DistilledFinding] = []
    coverage: list[CoverageRow] = []
    total_in = total_out = cache_hits = 0
    for i, res in enumerate(results_by_idx):
        if res is None:
            # Defensive: a row that produced no tuple in either pass (should not
            # happen — every miss is batched and every batch index is filled).
            # Emit a fail-closed coverage row so no source silently disappears
            # (LAW II), rather than dropping it.
            eid = ev_subset[i].get("evidence_id", "") or ""
            coverage.append(CoverageRow(
                evidence_id=eid, status="map_failed", n_findings=0,
                reason="unaccounted_after_dispatch",
            ))
            continue
        findings, cov, in_tok, out_tok, hit = res
        all_findings.extend(findings)
        coverage.append(cov)
        total_in += in_tok
        total_out += out_tok
        cache_hits += hit

    # Fail-loud invariant: every input row is accounted for (>=1 finding OR a row).
    covered_ids = {c.evidence_id for c in coverage}
    finding_ids = {f.evidence_id for f in all_findings}
    accounted = covered_ids | finding_ids
    for ev in ev_subset:
        eid = ev.get("evidence_id", "") or ""
        if eid and eid not in accounted:
            raise AssertionError(
                f"evidence_distiller: source {eid!r} silently disappeared "
                f"(no finding and no coverage row) â€” LAW II fail-loud"
            )

    clusters = _cluster_contradictions(all_findings)

    return SectionDistillate(
        section_title=section_title,
        section_focus=section_focus,
        findings=all_findings,
        coverage=coverage,
        contradiction_clusters=clusters,
        atom_catalog=dict(section_atoms),
        input_tokens=total_in,
        output_tokens=total_out,
        cache_hits=cache_hits,
        version=DISTILLER_VERSION,
    )


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# REDUCE post-processing: strip finding markers, drop uncited prose (spec Â§2)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_FINDING_MARKER_RE = re.compile(r"\[\[finding:(?P<fid>[A-Za-z0-9_]+)\]\]")
# Full provenance token (matches provenance_generator._PROVENANCE_TOKEN_RE).
_FULL_EV_TOKEN_RE = re.compile(
    r"\[#ev:(?P<ev_id>[A-Za-z0-9_]+):(?P<start>\d+)-(?P<end>\d+)\]"
)
_BARE_EV_MARKER_RE = re.compile(r"\[(?P<ev_id>[A-Za-z_][A-Za-z0-9_]*)\]")
_DUP_BARE_EV_MARKER_RE = re.compile(
    r"(\[(?P<ev_id>[A-Za-z_][A-Za-z0-9_]*)\])(?:\s+\[(?P=ev_id)\])+"
)
_ATOM_MARKER_RE = re.compile(r"\(atom_[A-Za-z0-9_]+\)")


def _is_marker_only_fragment(sent: str) -> bool:
    """True if ``sent`` carries citation markers but NO prose words.

    #1217 Bug A (Claude live-repro + Codex independent confirm): the REDUCE model
    sometimes places its ``[[finding:...]]``/``[ev_XXX]``/``(atom_NNN)`` markers in
    their OWN sentence, AFTER the claim sentence's terminal period. ``split_into_
    sentences`` then yields a marker-only fragment; the per-sentence filter keeps that
    fragment (it carries the markers) and DROPS the actual claim sentence (no marker)
    -> bare marker reaches strict_verify -> 0 verified -> placeholder. This detector
    lets the filter REATTACH such a fragment to the preceding prose sentence so the
    claim and its markers travel together. A fragment qualifies only if it (a) carries
    at least one finding/evidence marker AND (b) has no remaining alphanumeric prose
    after all marker shapes are stripped."""
    had_marker = bool(
        _FINDING_MARKER_RE.search(sent)
        or _FULL_EV_TOKEN_RE.search(sent)
        or _BARE_EV_MARKER_RE.search(sent)
    )
    if not had_marker:
        return False
    stripped = _FINDING_MARKER_RE.sub(" ", sent)
    stripped = _FULL_EV_TOKEN_RE.sub(" ", stripped)
    stripped = _BARE_EV_MARKER_RE.sub(" ", stripped)
    stripped = _ATOM_MARKER_RE.sub(" ", stripped)
    return not any(ch.isalnum() for ch in stripped)


def filter_and_strip_reduce_markers(
    raw: str,
    distillate: SectionDistillate,
) -> str:
    """Post-process the REDUCE output before the UNCHANGED _rewrite_draft_with_spans
    and strict_verify run.

    For each sentence:
      - DROP it unless it carries BOTH (a) at least one KNOWN [[finding:<id>]]
        marker (a finding_id present in the distillate ledger) AND (b) at least
        one evidence marker. The intended marker is legacy [ev_XXX]; stale
        reducer outputs that still contain [#ev:evidence_id:start-end] are
        normalized back to [ev_XXX].
      - STRIP the [[finding:...]] markers (the downstream gate does not understand
        them; the [ev_XXX] marker is rebound by _rewrite_draft_with_spans).

    The returned clean prose carries legacy evidence markers (and any (atom_NNN)
    the reducer copied), so the unchanged downstream pipeline binds spans from
    the FINAL sentence exactly as it would a legacy draft. Uncited reducer prose
    is dropped so it can never reach strict_verify as a pass-through limitations
    sentence.
    """
    from src.polaris_graph.generator.provenance_generator import split_into_sentences

    finding_by_id = {f.finding_id: f for f in distillate.findings}
    # #1218: the evidence pool is INCONSISTENT — 457/462 ids start with "ev_" but a
    # few (incl. the key safety sources) do NOT. The REDUCE, biased by the majority +
    # the "[ev_001]" example, sometimes ADDS an "ev_" prefix to an unprefixed id, so
    # the marker [ev_<id>] fails to resolve and strict_verify drops the whole (faithful,
    # on-topic) sentence. Normalize a bare marker to the REAL evidence_id below (drop or
    # add the "ev_" prefix to match a known id). Faithfulness-safe: it only ever rewrites
    # to a GENUINE pool/ledger id; the final strict_verify still validates the span.
    known_ev_ids = {f.evidence_id for f in distillate.findings}

    def _normalize_ev_prefix(marker_text: str) -> str:
        def _sub(m: "re.Match[str]") -> str:
            x = m.group("ev_id")
            if x in known_ev_ids:
                return m.group(0)
            if x.startswith("ev_") and x[3:] in known_ev_ids:
                return f"[{x[3:]}]"
            if f"ev_{x}" in known_ev_ids:
                return f"[ev_{x}]"
            return m.group(0)
        return _BARE_EV_MARKER_RE.sub(_sub, marker_text)

    sentences = split_into_sentences(raw)
    _dbg = resolve("PG_DISTILL_DEBUG").strip().lower() in ("1", "true", "yes", "on")
    if _dbg:
        logger.warning(
            "[DISTILL_DEBUG] section=%r: ledger=%d findings; REDUCE raw=%d chars / %d sentences; raw_sample=%r",
            distillate.section_title, len(distillate.findings), len(raw), len(sentences), raw[:900],
        )
    # #1217 Bug A pre-pass (Claude+Codex AGREE, fix=both): REATTACH an orphaned
    # marker-only fragment to the immediately preceding sentence before filtering, so
    # the claim prose and its citation markers are filtered as ONE unit. Without this,
    # a REDUCE that emits "claim." then "[[finding]] [ev]" on the next line loses the
    # claim (no marker) and keeps a bare marker -> total section collapse. Faithfulness
    # is unchanged: the reassembled sentence still goes through the UNCHANGED
    # _rewrite_draft_with_spans + strict_verify, which re-bind and re-verify the span
    # for the claim prose — a mis-attached marker cannot publish an unsupported claim.
    merged: list[str] = []
    reattached = 0
    for sent in sentences:
        if merged and _is_marker_only_fragment(sent):
            merged[-1] = f"{merged[-1].rstrip()} {sent.strip()}"
            reattached += 1
        else:
            merged.append(sent)
    sentences = merged
    if _dbg and reattached:
        logger.warning(
            "[DISTILL_DEBUG] section=%r: reattached %d orphaned marker-only fragment(s) to preceding sentence(s)",
            distillate.section_title, reattached,
        )
    kept: list[str] = []
    for sent in sentences:
        # #1217 Bug A: a sentence that is ONLY markers (no prose) must never reach
        # strict_verify as a bare token. The pre-pass above already REATTACHED any
        # marker-only fragment that had a preceding sentence; whatever is still
        # marker-only here is a LEADING orphan with nothing to attach to — drop it.
        if _is_marker_only_fragment(sent):
            continue
        finding_ids = _FINDING_MARKER_RE.findall(sent)
        cited_known = [fid for fid in finding_ids if fid in finding_by_id]
        has_known_finding = bool(cited_known)
        # #1217 follow-up: require an evidence marker to be PRESENT, but do NOT
        # require its evidence_id to exactly match the cited finding's. This
        # filter's job is only to drop UNcited reducer prose; the UNCHANGED
        # _rewrite_draft_with_spans + strict_verify downstream validates the
        # final [#ev:...] token against the evidence pool. Permissive filter,
        # strict output gate.
        has_full_token = bool(_FULL_EV_TOKEN_RE.search(sent))
        has_bare_marker = bool(_BARE_EV_MARKER_RE.search(sent))
        if not (has_known_finding and (has_bare_marker or has_full_token)):
            # Uncited reducer prose, or a marker pointing at an unknown finding:
            # drop it. It must not survive into strict_verify as pass-through prose.
            continue
        # Strip the finding markers. Normalize stale full provenance tokens back
        # to legacy [ev_XXX] so the sentence-aware span binder recomputes spans
        # for the reducer's FINAL prose instead of trusting MAP support-quote
        # offsets.
        clean = _FINDING_MARKER_RE.sub("", sent)
        clean = _FULL_EV_TOKEN_RE.sub(lambda m: f"[{m.group('ev_id')}]", clean)
        clean = _normalize_ev_prefix(clean)  # #1218: fix model-added/dropped "ev_" prefix
        clean = _DUP_BARE_EV_MARKER_RE.sub(lambda m: m.group(1), clean)
        # Collapse any double spaces introduced by marker removal.
        clean = re.sub(r"\s{2,}", " ", clean).strip()
        if clean:
            kept.append(clean)
    out = " ".join(kept)
    if _dbg:
        logger.warning(
            "[DISTILL_DEBUG] section=%r: filter kept %d/%d sentences -> output=%d chars; out_sample=%r",
            distillate.section_title, len(kept), len(sentences), len(out), out[:900],
        )
    return out
