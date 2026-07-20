"""I-deepfix-001 (#1344) item 2 — winner-firing fail-closed gate (relevance layer).

WHY THIS EXISTS
---------------
Two winners-only PAID runs (FRONT=drb_72, MIDDLE=drb_76) burned GPU + tokens
while the relevance-layer WINNERS were structurally DARK: the W6 embedder / B4
semantic scorer fell back to the legacy lexical cut every round, and the W5
content-relevance reranker logged ``reranker_device=unavailable`` and reverted to
full weight for every passage. The deliverable would have been labeled
"winners-only" while three of the headline winners never fired. A 7-agent
line-by-line forensic read found only 4 of 14 winners fired.

WHAT THIS MODULE IS
-------------------
A PURE, offline-testable decision function. It reads the ALREADY-DETERMINED
structural state of the relevance-layer winners at the post-retrieval /
pre-generation seam and returns a verdict: which REQUESTED winners are
structurally dark, and whether the run must ABORT before the expensive
generation. It performs ZERO model loads, ZERO network, ZERO GPU work — it only
inspects state the retrieval phase already produced.

THE DISTINCTION (so this is NOT a faithfulness hold — CLAUDE.md §-1.3)
---------------------------------------------------------------------
This is a CONFIG / WIRING firing-gate: a relevance-layer WINNER is dark =>
the run is NOT actually running winners-only => abort BEFORE producing a
falsely-labeled "winners-only" deliverable. It is NOT a faithfulness hold on
rendered claims. The faithfulness engine (strict_verify / 4-role / D8 / NLI /
span-grounding) is UNTOUCHED and still always releases + labels per §-1.3. A
"structural dark" here means the model could not be IMPORTED / LOADED at all
(the wiring is wrong) — never a single transient encode exception, and never a
weight/down-weight decision on a source (no source is ever dropped here).

WHAT COUNTS AS STRUCTURAL-DARK (per the Codex-approved fix brief item 2)
-----------------------------------------------------------------------
A winner is dark ONLY when it was REQUESTED (its slate flag is ON) AND its
structural state proves a load/import failure (NOT a transient):

  * W6 embedder / B4 semantic scorer: the cached embedder handle is the ``False``
    sentinel (``evidence_selector._SEMANTIC_EMBEDDER_CACHE is False`` == "load
    attempted, unavailable") OR the selection telemetry shows the semantic scorer
    was REQUESTED but fell back to the lexical scorer.
  * W5 content-relevance reranker: ``retrieval.content_relevance['reranker_device']
    == 'unavailable'`` (set by content_relevance_judge when the reranker LOAD
    raised → full weight for all passages).
  * W7 selection reranker: a caller-supplied ``w7_load_failed`` flag (the selection
    reranker fires AFTER this seam, so its structural-dark state is supplied by the
    caller when known; absent => not yet determined => not tripped here).

A CPU fallback (``used_cpu_fallback``) is a DISCLOSED degrade, NOT a structural
dark — the winner DID fire, just slower. It does NOT trip this gate (§-1.3:
disclosed down-weight, never an abort on a working-but-slow path).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any
from src.polaris_graph.settings import resolve


# Truthy env values shared with the winner flags (mirrors the per-winner enabled
# checks in content_relevance_judge.content_relevance_enabled /
# evidence_selector._reranker_selection_enabled — duplicated here as a pure,
# import-free check so this module never pulls the heavy retrieval chain).
_ON_VALUES = frozenset({"1", "true", "yes", "on"})
_OFF_VALUES = frozenset({"0", "false", "no", "off", ""})


def _env_on(name: str, default: str) -> bool:
    """True iff env var ``name`` (defaulting to ``default``) is an ON value."""
    return os.getenv(name, default).strip().lower() in _ON_VALUES


def _w6_embedder_requested() -> bool:
    """W6 embedder / B4 semantic scorer requested.

    The B4 semantic relevance scorer is requested when the redesign credibility
    pass is ON (PG_SWEEP_CREDIBILITY_REDESIGN, default 'on') AND a semantic
    embedder model is configured (PG_EMBEDDER_MODEL set to a non-empty value).
    The Gate-B slate sets PG_EMBEDDER_MODEL=qwen3, so on the deepfix winners path
    this is True; on the default/legacy path PG_EMBEDDER_MODEL is unset => False
    => the gate never trips (byte-identical OFF).
    """
    if not _env_on("PG_SWEEP_CREDIBILITY_REDESIGN", "on"):
        return False
    return bool(resolve("PG_EMBEDDER_MODEL").strip())


def _w5_content_relevance_requested() -> bool:
    """W5 content-relevance reranker requested (PG_CONTENT_RELEVANCE_JUDGE, default ON)."""
    return _env_on("PG_CONTENT_RELEVANCE_JUDGE", "1")


def _w7_reranker_requested() -> bool:
    """W7 selection reranker requested.

    The Gate-B slate sets ``PG_RERANKER_MODEL=qwen3`` (a MODEL NAME, not a boolean
    ON value), so the prior ``in _ON_VALUES`` check wrongly read it as NOT-requested
    and W7 was never hard-gated. Mirror ``_w6_embedder_requested``'s
    ``bool(os.getenv(...).strip())`` style: requested iff PG_RERANKER_MODEL is a
    NON-EMPTY value — EXCEPT the explicit off-values (``0``/``false``/``no``/``off``/
    ``""``) which mean not-requested (byte-identical OFF on the default/legacy path
    where PG_RERANKER_MODEL is unset). This matches the per-winner enabled check in
    ``evidence_selector._reranker_selection_enabled`` (any model name turns W7 on).
    """
    value = os.environ.get("PG_RERANKER_MODEL", "").strip().lower()
    return bool(value) and value not in _OFF_VALUES


@dataclass
class WinnerFiringVerdict:
    """The pure gate verdict. ``abort`` True => the run MUST stop before generation."""

    abort: bool = False
    dark_winners: list[str] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    # Per-winner state, for the disclosed manifest field (never a drop list).
    winners_checked: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "abort": self.abort,
            "dark_winners": list(self.dark_winners),
            "diagnostics": list(self.diagnostics),
            "winners_checked": dict(self.winners_checked),
        }


def evaluate_winner_firing(
    *,
    content_relevance: dict[str, Any] | None,
    embedder_cache_sentinel: Any,
    w6_requested: bool | None = None,
    w5_requested: bool | None = None,
    w7_requested: bool | None = None,
    semantic_fell_back: bool = False,
    w7_load_failed: bool | None = None,
) -> WinnerFiringVerdict:
    """Decide whether a relevance-layer winner is STRUCTURALLY dark.

    PURE: no IO, no model load, no network. All inputs are already-determined
    state captured by the retrieval phase.

    Args:
      content_relevance: ``retrieval.content_relevance`` (the W5 / W2 report
        ``to_dict()``), or None when W5 was OFF / never produced a report. The
        structural-dark signal is ``reranker_device == 'unavailable'``.
      embedder_cache_sentinel: ``evidence_selector._SEMANTIC_EMBEDDER_CACHE``.
        The ``False`` sentinel == "embedder load attempted and FAILED" (structural
        dark for W6). ``None`` == not yet tried (NOT dark). A truthy handle ==
        loaded fine (NOT dark).
      w6_requested / w5_requested / w7_requested: override the env-derived
        "was this winner requested" checks (used by tests; None => read env).
      semantic_fell_back: True iff the selection telemetry recorded the semantic
        scorer was REQUESTED but fell back to lexical (a second W6/B4 dark signal,
        independent of the cache sentinel).
      w7_load_failed: True iff the caller KNOWS the W7 selection reranker failed to
        load structurally. None => W7 load state not yet determined at this seam =>
        W7 is not tripped here (it fires after generation begins; its own loud
        fallback + the identity log tag cover the post-seam case).

    Returns a ``WinnerFiringVerdict``. ``abort`` is True iff at least one REQUESTED
    winner is structurally dark.
    """
    w6_on = _w6_embedder_requested() if w6_requested is None else w6_requested
    w5_on = _w5_content_relevance_requested() if w5_requested is None else w5_requested
    w7_on = _w7_reranker_requested() if w7_requested is None else w7_requested

    verdict = WinnerFiringVerdict()

    # ── W6 embedder / B4 semantic scorer ─────────────────────────────────────
    if w6_on:
        # `False` sentinel = load attempted and failed (structural). `None` = not
        # yet tried (not dark). Truthy handle = loaded (not dark).
        cache_dark = embedder_cache_sentinel is False
        if cache_dark or semantic_fell_back:
            verdict.dark_winners.append("W6_embedder")
            verdict.winners_checked["W6_embedder"] = "dark"
            reason = (
                "cached embedder handle is the False sentinel (load attempted, unavailable)"
                if cache_dark
                else "semantic scorer requested but fell back LOUDLY to the lexical cut"
            )
            verdict.diagnostics.append(
                f"W6 embedder / B4 semantic scorer STRUCTURALLY DARK: {reason}. "
                "The relevance-layer winner did not fire — the run is NOT winners-only."
            )
        else:
            verdict.winners_checked["W6_embedder"] = "fired_or_pending"
    else:
        verdict.winners_checked["W6_embedder"] = "not_requested"

    # ── W5 content-relevance reranker ────────────────────────────────────────
    if w5_on:
        cr = content_relevance or {}
        device = str(cr.get("reranker_device", "") or "").strip().lower()
        if device == "unavailable":
            verdict.dark_winners.append("W5_content_relevance")
            verdict.winners_checked["W5_content_relevance"] = "dark"
            verdict.diagnostics.append(
                "W5 content-relevance reranker STRUCTURALLY DARK: reranker_device="
                "'unavailable' (load failed → full weight for all passages). The "
                "relevance-layer winner did not fire — the run is NOT winners-only."
            )
        elif content_relevance is None:
            # Requested but produced NO report at all (the judge never ran). This is
            # a structural miss for a force-ON winner.
            verdict.dark_winners.append("W5_content_relevance")
            verdict.winners_checked["W5_content_relevance"] = "dark"
            verdict.diagnostics.append(
                "W5 content-relevance reranker REQUESTED (PG_CONTENT_RELEVANCE_JUDGE "
                "on) but produced NO telemetry report — the judge never ran. The "
                "relevance-layer winner did not fire — the run is NOT winners-only."
            )
        else:
            verdict.winners_checked["W5_content_relevance"] = (
                "cpu_fallback_disclosed" if cr.get("used_cpu_fallback") else "fired"
            )
    else:
        verdict.winners_checked["W5_content_relevance"] = "not_requested"

    # ── W7 selection reranker ────────────────────────────────────────────────
    if w7_on:
        if w7_load_failed is True:
            verdict.dark_winners.append("W7_reranker")
            verdict.winners_checked["W7_reranker"] = "dark"
            verdict.diagnostics.append(
                "W7 selection reranker (Qwen3-Reranker-4B) STRUCTURALLY DARK: the "
                "model failed to load. The relevance-layer winner did not fire — the "
                "run is NOT winners-only."
            )
        elif w7_load_failed is None:
            # The selection reranker fires AFTER this seam; its load state is not
            # known here. Record as pending — NOT a trip.
            verdict.winners_checked["W7_reranker"] = "pending_post_seam"
        else:
            verdict.winners_checked["W7_reranker"] = "fired"
    else:
        verdict.winners_checked["W7_reranker"] = "not_requested"

    verdict.abort = bool(verdict.dark_winners)
    return verdict
