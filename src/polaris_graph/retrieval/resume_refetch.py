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

import dataclasses
import os
from typing import Any, Callable, Sequence

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
    recovered_error_class_fn: Callable[[str], str] | None = None,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Re-fetch each fetch-degraded resume row in place; repopulate its grounding span on success.

    For every row in ``degraded_rows`` this calls ``refetch_fn(url)`` (the live-retriever
    ``refetch_for_extraction_with_diagnostics`` cascade — including the Zyte fallback). When the
    re-fetch returns a non-empty quote that is NOT content-starved AND is NOT a registry/error/block
    page (per ``recovered_error_class_fn`` — the SAME ``live_retriever._recovered_content_error_class``
    screen the live forced-Zyte adoption path uses), the row's ``direct_quote`` is REPOPULATED with the
    fresh span and the degraded flags are cleared (the row recovered). When the re-fetch yields nothing
    usable (still a shell, no URL, an error/registry/block page, or the cascade failed), the row is left
    flagged — it stays disclosed and the UNCHANGED ``strict_verify`` will honestly drop it (never a
    fabricated span). Mutates the row dicts in place; returns a per-call telemetry summary.

    ``recovered_error_class_fn`` (optional injection, default None == legacy length-only path): a
    ``text -> class-token`` classifier (empty token == real content, ADOPT it). The production caller
    wires ``live_retriever._recovered_content_error_class`` so an 821-char doi.org "DOI Not Found"
    registry page (non-starved, real English prose) is NOT adopted as grounding and does NOT clear the
    degraded flags — closing the Codex P1 where a non-starved error page's flags were cleared, letting
    ``is_row_genuinely_recovered`` accept it and ``propagate_recovered_spans_to_frame_rows`` relabel a
    HOLLOW FrameRow to OPEN_ACCESS. §-1.3: refusing to adopt a fetch FAILURE as grounding is
    faithfulness-STRENGTHENING, not a source DROP — the row stays disclosed and flows through the
    UNCHANGED strict_verify.

    Faithfulness-neutral: only the INPUT span is refreshed with real fetched content — no gate moves.
    Fail-LOUD per row (each recovery / residual-shell / error-page is logged) and fail-open overall (a
    re-fetch exception for one row never aborts the resume; that row stays flagged).
    """
    _log = log or (lambda _m: None)
    _error_class_fn = recovered_error_class_fn or (lambda _t: "")
    recovered: list[str] = []
    still_shell: list[str] = []
    error_page: list[str] = []
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
        # A usable re-fetch must clear the refetch contract (non-empty, >=100 chars by construction in
        # refetch_for_extraction_with_diagnostics), the content-starvation heuristic, AND the
        # registry/error/block-page screen — so neither a shell that merely cleared 100 chars NOR a
        # non-starved error/registry page (e.g. an 821-char doi.org "DOI Not Found") is treated as
        # recovered. The error screen runs on the SAME classifier the live forced-Zyte adoption path
        # uses, so the resume path can never adopt a fetch FAILURE the live path would reject.
        if quote and not is_content_starved_fn(quote):
            try:
                _err_class = _error_class_fn(quote) or ""
            except Exception as exc:  # noqa: BLE001 — fail-OPEN: a screen error never rejects a real body
                _err_class = ""
                _log(
                    f"[resume]      A15 re-fetch error-screen raised for ev={eid} "
                    f"(fail-open, adopting the recovered body): {type(exc).__name__}: {exc}"
                )
            if _err_class:
                error_page.append(eid)
                _log(
                    f"[resume]      A15 re-fetch ERROR-PAGE ev={eid} url={url[:80]} "
                    f"(re-fetch returned a {_err_class} page — non-starved but a fetch FAILURE, "
                    "NOT grounding; degraded flags KEPT, row left flagged + disclosed; strict_verify "
                    "will honestly drop any ungrounded claim, NO fabrication)"
                )
                continue
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
        "error_page": error_page,
        "no_url": no_url,
        "errors": errors,
    }


# I-deepfix-001 P6 (#1344) — A15 resume-recovery propagation to the V30 contract slot generator.
#
# THE GAP the P6 fix closes (traced at scripts/run_honest_sweep_r3.py:11595-11612):
# ``refetch_degraded_resume_rows`` above re-grounds a degraded reloaded ``evidence_for_gen`` ROW
# dict's ``direct_quote`` in place, so ``strict_verify`` + the legacy/enrichment sections see real
# spans. But the V30 CONTRACT slot generator reads its span from the FrameRow
# (``frame_row.direct_quote``, contract_section_runner.py) — a SEPARATE object that
# ``fetch_compiled_frame`` re-fetches FRESH on the resume and that can come back a SHELL again (same
# paywall/block). So a recovered anchor still RENDERS HOLLOW. This helper propagates the recovered
# span from the reloaded contract row (matched by ``v30_entity_id`` == FrameRow ``entity_id``) into
# any HOLLOW FrameRow so a resumed contract run renders the REAL anchor, not an empty gap.

# The verifiable-span floor a FrameRow must clear to be a usable (non-hollow) contract anchor. Mirrors
# ``contract_section_runner._MIN_VERIFIABLE_SPAN_CHARS`` / ``frame_manifest`` via the SAME env name so
# the "hollow" decision here is identical to the render-side gap decision (LAW VI, env-overridable).
_ENV_MIN_VERIFIABLE_SPAN_CHARS = "PG_MIN_VERIFIABLE_SPAN_CHARS"


def _min_verifiable_span_chars() -> int:
    try:
        return int(os.environ.get(_ENV_MIN_VERIFIABLE_SPAN_CHARS, "50"))
    except ValueError:
        return 50


def is_row_genuinely_recovered(row: dict[str, Any]) -> bool:
    """True iff a reloaded contract row is a GENUINE A15 recovery safe to propagate as a span.

    A row qualifies only when it (a) carries a non-empty grounding span AND (b) has NO residual
    A15 degraded flag still set. ``refetch_degraded_resume_rows`` clears ``_DEGRADED_FLAGS``
    (``content_starved`` / ``fetch_failed`` / ``landing_page`` / ``resume_refresh_pending``) ONLY on
    real recovery; a still-shell / un-refetched row keeps them. Without this guard a still-degraded
    shell whose leftover span merely clears the length floor (a paywall/landing-page notice) would be
    harvested as a "recovered" span and relabel a HOLLOW FrameRow to OPEN_ACCESS — a shell rendered as
    a real anchor (the P6 caller defect). Excluding it is faithfulness-STRENGTHENING (no fake anchor),
    not a source DROP: the degraded row itself stays in ``evidence_for_gen`` untouched and still flows
    through the UNCHANGED strict_verify, which honestly drops any ungrounded claim.
    """
    if not isinstance(row, dict):
        return False
    if not str(row.get(_GROUNDING_FIELD) or "").strip():
        return False
    for _flag in _DEGRADED_FLAGS:
        if bool(row.get(_flag)):
            return False
    return True


def recovered_spans_from_reloaded_rows(
    evidence_for_gen: Sequence[Any],
    *,
    recovered_error_class_fn: Callable[[str], str] | None = None,
    log: Callable[[str], None] | None = None,
) -> dict[str, str]:
    """Build the ``{v30_entity_id -> recovered direct_quote}`` propagation map for the P6 resume path.

    Mirrors the run_honest_sweep V30 caller but ONLY admits GENUINELY-recovered contract rows
    (``is_row_genuinely_recovered`` — a non-empty span AND every A15 degraded flag cleared). A
    reloaded row that is still a degraded shell — even one whose leftover span cleared the length
    floor — is EXCLUDED so it can never relabel a hollow FrameRow to OPEN_ACCESS. Fail-LOUD: any
    excluded non-empty-but-degraded shell is logged (never silently swallowed). Faithfulness-neutral:
    the excluded row stays in the corpus and flows through the UNCHANGED strict_verify.

    CONTENT RE-SCREEN (the P6 propagation-map Codex BLOCKER): is_row_genuinely_recovered gates on
    FLAG-STATE alone. But the resume degraded-detector (run_honest_sweep_r3.py, the
    flags+is_content_starved selector) only ever FLAGS a starved/failed/landing row, so an UNFLAGGED,
    non-starved fetch-FAILURE registry/error page (e.g. an 821-char doi.org "DOI Not Found" page
    reloaded straight from the snapshot) is NEVER flagged, NEVER re-fetched, and so the error-page
    screen inside refetch_degraded_resume_rows never runs on it. Such a row passes the flag-only guard
    and would relabel a HOLLOW FrameRow to OPEN_ACCESS (a fetch FAILURE rendered as a real anchor).
    recovered_error_class_fn (the production caller wires the SAME live-path screen,
    live_retriever._recovered_content_error_class, NO new detector) RE-SCREENS the candidate span
    CONTENT here at the propagation-map build point, REGARDLESS of flag-state; a non-empty class token
    (a registry / error-shell / block page) is REJECTED from the map. Per DNA §-1.3: refusing to
    propagate a fetch FAILURE as a filled anchor is faithfulness-STRENGTHENING, not a source DROP, the
    row still stays in evidence_for_gen as a disclosed gap and flows through the UNCHANGED
    strict_verify. Default None == legacy no-screen (byte-identical); FAIL-OPEN, a screen exception
    never rejects a real body (it is adopted, with a loud warning).
    """
    _log = log or (lambda _m: None)
    _error_class_fn = recovered_error_class_fn or (lambda _t: "")
    out: dict[str, str] = {}
    skipped_degraded: list[str] = []
    skipped_error_page: list[str] = []
    for row in evidence_for_gen:
        if not isinstance(row, dict) or not row.get("v30_frame_row"):
            continue
        eid = str(row.get("v30_entity_id") or row.get("evidence_id") or "")
        if not eid:
            continue
        if is_row_genuinely_recovered(row):
            span = row[_GROUNDING_FIELD]
            # Re-screen the CONTENT with the same live-path error-page screen, regardless of
            # flag-state, so an unflagged/never-re-fetched fetch-FAILURE page is rejected here.
            try:
                _err_class = _error_class_fn(str(span or "")) or ""
            except Exception as exc:  # noqa: BLE001 fail-OPEN: a screen error never rejects a real body
                _err_class = ""
                _log(
                    f"[resume]      A15 P6: propagation-map error-screen raised for entity={eid} "
                    f"(fail-open, adopting the span): {type(exc).__name__}: {exc}"
                )
            if _err_class:
                skipped_error_page.append(f"{eid}({_err_class})")
                continue
            out[eid] = span
        elif str(row.get(_GROUNDING_FIELD) or "").strip():
            # Non-empty span but a residual A15 degraded flag is still set => still a shell, NOT a
            # recovery. Do NOT propagate (would fake a hollow anchor into OPEN_ACCESS). Disclose loudly.
            skipped_degraded.append(eid)
    if skipped_error_page:
        _log(
            "[resume]      A15 P6: EXCLUDED "
            f"{len(skipped_error_page)} reloaded contract row(s) from span propagation whose span "
            "CONTENT is a fetch-FAILURE registry/error/block page (re-screened regardless of "
            f"flag-state): {skipped_error_page[:10]} — a fetch FAILURE is NOT a recovery, the hollow "
            "anchor stays a disclosed gap (NO fabrication; the row still flows through UNCHANGED "
            "strict_verify)"
        )
    if skipped_degraded:
        _log(
            "[resume]      A15 P6: EXCLUDED "
            f"{len(skipped_degraded)} still-degraded reloaded contract row(s) from span "
            f"propagation (non-empty shell span but a residual degraded flag is set): "
            f"{skipped_degraded[:10]} — a shell is NOT a recovery, the hollow anchor stays a "
            "disclosed gap (NO fabrication; the row still flows through UNCHANGED strict_verify)"
        )
    return out


def propagate_recovered_spans_to_frame_rows(
    frame_rows: Sequence[Any],
    *,
    recovered_span_by_entity: dict[str, str],
    min_span_chars: int | None = None,
    log: Callable[[str], None] | None = None,
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    """Propagate A15-recovered spans into HOLLOW V30 contract FrameRows on ``--resume``.

    For each FrameRow whose fresh ``fetch_compiled_frame`` result is HOLLOW — a
    ``FRAME_GAP_UNRECOVERABLE`` row, OR a row whose ``direct_quote`` is shorter than the verifiable-
    span floor (the SAME predicate the contract runner's ``_frame_row_has_usable_quote`` uses to route
    a slot to gap-disclosure) — this looks up a recovered span in ``recovered_span_by_entity`` (keyed
    by the FrameRow ``entity_id`` == the reloaded contract row's ``v30_entity_id``). When a usable
    recovered span (non-empty AND >= the floor) exists, the FrameRow is rebuilt (``dataclasses.replace``
    on the frozen row) with ``direct_quote`` = the recovered span, ``provenance_class`` lifted to
    ``OPEN_ACCESS`` (it now carries real fetched content), and ``quote_source="a15_resume_refetch"``.

    HOLLOW-ONLY + NO-CLOBBER: a FrameRow that already carries a usable span is returned UNCHANGED, so
    a fresh re-fetch that DID recover is never overwritten by a stale snapshot span. A ``HUMAN_CURATED``
    row (a PERMANENT provenance marker) is never overwritten. A hollow row with NO matching recovered
    span is returned unchanged — it stays a disclosed gap and the UNCHANGED ``strict_verify`` honestly
    drops any ungrounded claim (NO fabrication).

    FAITHFULNESS-NEUTRAL BY CONSTRUCTION: this only refreshes a row's INPUT span with real recovered
    fetched content (the exact content ``refetch_degraded_resume_rows`` already re-grounded and that
    flows through the UNCHANGED strict_verify via ``register_frame_rows_into_evidence_pool`` + slot-fill).
    It moves NO gate/threshold. Empty ``recovered_span_by_entity`` => every row unchanged => byte-identical.

    Returns ``(new_frame_rows_tuple, telemetry)`` where ``telemetry["propagated"]`` is the list of
    entity_ids whose hollow FrameRow was filled.
    """
    from .frame_fetcher import ProvenanceClass  # noqa: PLC0415 — lazy: keep module-top deps minimal

    _log = log or (lambda _m: None)
    floor = _min_verifiable_span_chars() if min_span_chars is None else int(min_span_chars)

    propagated: list[str] = []
    out: list[Any] = []
    for row in frame_rows:
        eid = str(getattr(row, "entity_id", "") or "")
        prov = getattr(row, "provenance_class", None)
        quote = str(getattr(row, "direct_quote", "") or "").strip()

        # A HUMAN_CURATED marker is permanent — never relabel/overwrite it.
        if prov == ProvenanceClass.HUMAN_CURATED:
            out.append(row)
            continue

        is_hollow = (
            prov == ProvenanceClass.FRAME_GAP_UNRECOVERABLE
            or len(quote) < floor
        )
        recovered_raw = recovered_span_by_entity.get(eid)
        recovered = str(recovered_raw or "").strip()

        if is_hollow and recovered and len(recovered) >= floor:
            new_row = dataclasses.replace(
                row,
                direct_quote=recovered_raw,
                provenance_class=ProvenanceClass.OPEN_ACCESS,
                quote_source="a15_resume_refetch",
            )
            out.append(new_row)
            propagated.append(eid)
            _log(
                f"[resume]      A15 P6: filled HOLLOW V30 contract frame row entity={eid} "
                f"with {len(recovered)} chars recovered on resume "
                "(flows through UNCHANGED strict_verify; no gate moved)"
            )
        else:
            out.append(row)

    return tuple(out), {
        "attempted": len(frame_rows),
        "propagated": propagated,
    }
