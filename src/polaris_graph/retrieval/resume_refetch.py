"""I-arch-007 ITEM 6 (#1264) — A15 resume FETCH-SHELL re-fetch (over-drop input fix).

THE PROBLEM (the Q90 ``abort_excessive_gap`` 96% over-drop): a resume reloads the frozen
``corpus_snapshot`` with NO re-retrieval, so the V30 contract's REQUIRED T1 anchor rows (e.g.
SAE J3016, ALI product-liability, NTSB guidelines, UNECE ALKS, PACER docket) that were fetched as
EMPTY SHELLS on the crashed run are reloaded UNTOUCHED. The run log shows
``A15 refresh: N reloaded rows fetch-degraded (failed/shell/content-starved) ... detection-only``.
An empty cited span means the generator's claims about that anchor have nothing to ground against,
so ``strict_verify`` CORRECTLY drops them — that cascades into an over-drop abort.

THE FIX — GET THE CONTENT, NEVER RELAX THE GATE: turn the A15 *detection-only* flag into an actual
RE-FETCH of the shell / failed / content-starved rows, routing paywalled/blocked anchors through the
existing AccessBypass cascade (which already includes the Zyte fallback when ``ZYTE_API_KEY`` is set).
When a re-fetch yields a usable (>= the refetch contract's 100-char) provenance quote that is NOT
itself content-starved, the row's ``direct_quote`` grounding is REPOPULATED and the degraded flags are
cleared, so ``strict_verify`` now has a REAL span to verify. A row that is STILL a shell after the
re-fetch stays flagged (disclosed), never fabricated.

FAITHFULNESS-SAFE BY CONSTRUCTION: this module touches the INPUT only — it repopulates a row's fetched
span with freshly-fetched real content. It moves NO strict_verify / NLI / 4-role D8 / span-grounding /
section-floor / sentinel threshold. The re-fetched span flows through the UNCHANGED ``strict_verify``
exactly like any other fetched span; a row that cannot be re-grounded is left degraded (the gate then
honestly drops it). The master flag defaults OFF => no re-fetch => byte-identical resume.
"""

from __future__ import annotations

import os
from typing import Any, Callable

# LAW VI: env-overridable, default OFF (unset => no re-fetch => byte-identical legacy resume).
_ENV_RESUME_REFETCH = "PG_RESUME_REFETCH_DEGRADED"

# The grounding field strict_verify reads (``_build_provenance_quote`` writes it at
# live_retriever.py:4361). A successful re-fetch repopulates THIS field so the gate has a real span.
_GROUNDING_FIELD = "direct_quote"

# The degraded-state flags the A15 detector set on the reloaded row. A successful re-fetch clears
# them so downstream telemetry/disclosure reflects the row is no longer a shell.
_DEGRADED_FLAGS = (
    "content_starved",
    "fetch_failed",
    "landing_page",
    "resume_refresh_pending",
)


def resume_refetch_enabled() -> bool:
    """True iff the default-OFF master flag is explicitly enabled (LAW VI)."""
    return os.environ.get(_ENV_RESUME_REFETCH, "").strip().lower() in (
        "1", "true", "on", "yes",
    )


def _row_url(row: dict[str, Any]) -> str:
    """The best re-fetchable URL for a reloaded row (``source_url`` then ``url``)."""
    return str(row.get("source_url") or row.get("url") or "").strip()


def refetch_degraded_resume_rows(
    degraded_rows: list[dict[str, Any]],
    *,
    refetch_fn: Callable[[str], tuple[str, dict[str, Any]]],
    is_content_starved_fn: Callable[[str], bool],
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Re-fetch each fetch-degraded resume row in place; repopulate its grounding span on success.

    For every row in ``degraded_rows`` this calls ``refetch_fn(url)`` (the live-retriever
    ``refetch_for_extraction_with_diagnostics`` cascade — including the Zyte fallback). When the
    re-fetch returns a non-empty quote that is NOT content-starved, the row's ``direct_quote`` is
    REPOPULATED with the fresh span and the degraded flags are cleared (the row recovered). When the
    re-fetch yields nothing usable (still a shell, no URL, or the cascade failed), the row is left
    flagged — it stays disclosed and the UNCHANGED ``strict_verify`` will honestly drop it (never a
    fabricated span). Mutates the row dicts in place; returns a per-call telemetry summary.

    Faithfulness-neutral: only the INPUT span is refreshed with real fetched content — no gate moves.
    Fail-LOUD per row (each recovery / residual-shell is logged) and fail-open overall (a re-fetch
    exception for one row never aborts the resume; that row stays flagged).
    """
    _log = log or (lambda _m: None)
    recovered: list[str] = []
    still_shell: list[str] = []
    no_url: list[str] = []
    errors: list[str] = []

    for row in degraded_rows:
        if not isinstance(row, dict):
            continue
        eid = str(row.get("evidence_id", "") or "")
        url = _row_url(row)
        if not url:
            no_url.append(eid)
            continue
        try:
            quote, _diag = refetch_fn(url)
        except Exception as exc:  # noqa: BLE001 — one row's re-fetch must never abort the resume
            errors.append(eid)
            _log(
                f"[resume]      A15 re-fetch ERROR for ev={eid} url={url[:80]}: "
                f"{type(exc).__name__}: {exc} — row left flagged (gate will drop if unground-able)"
            )
            continue
        # A usable re-fetch must clear BOTH the refetch contract (non-empty, >=100 chars by
        # construction in refetch_for_extraction_with_diagnostics) AND the content-starvation
        # heuristic, so a shell/landing-page that merely cleared 100 chars is NOT treated as recovered.
        if quote and not is_content_starved_fn(quote):
            row[_GROUNDING_FIELD] = quote
            for _flag in _DEGRADED_FLAGS:
                if _flag in row:
                    row[_flag] = False
            recovered.append(eid)
            _log(
                f"[resume]      A15 re-fetch RECOVERED ev={eid} url={url[:80]} "
                f"(repopulated {_GROUNDING_FIELD} with {len(quote)} chars; "
                "flows through UNCHANGED strict_verify)"
            )
        else:
            still_shell.append(eid)
            _log(
                f"[resume]      A15 re-fetch STILL-SHELL ev={eid} url={url[:80]} "
                "(no usable content after the AccessBypass+Zyte cascade — row left flagged + "
                "disclosed; strict_verify will honestly drop any ungrounded claim, NO fabrication)"
            )

    return {
        "attempted": len(degraded_rows),
        "recovered": recovered,
        "still_shell": still_shell,
        "no_url": no_url,
        "errors": errors,
    }
