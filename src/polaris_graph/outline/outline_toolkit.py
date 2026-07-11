"""T1 rich toolkit for the agentic outliner (docs/agentic_outline_redesign.md PART 4, step 1+5).

``register_outline_toolkit(registry, workspace, agent_model, deadline)`` wires the read-only /
deterministic primitives + the moat ``verified_compute`` onto the driver's existing
``ToolRegistry``. The driver (``OutlineAgent``) does not change shape when tools are added — every
tool speaks the standard ``execute(evidence_store, data_points, client, **kw) -> ToolResult``
contract.

Faithfulness posture of this toolkit:
  * Every tool here is READ-ONLY over the workspace (search_corpus, get_evidence, list_baskets,
    coverage_audit, preview_section_evidence) or DETERMINISTIC-COMPUTE (calculator,
    verified_compute). None fetches network content — so none re-enters evidence and none can
    widen the render surface.
  * ``calculator`` is EXPLORATORY: a bare arithmetic result carries no evidence span, so it is
    planner-facing only (``renderable=False``). To RENDER a derived number the agent must use
    ``verified_compute``, which re-derives it through the verified ``[#calc:]`` lane
    (outline/verified_compute.py). This is the same two-lane discipline as execute_python.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any, Callable, Optional

from src.polaris_graph.tools.tool_registry import ToolDefinition, ToolRegistry, ToolResult

_WORD_RE = re.compile(r"[A-Za-z0-9]+")

# The evidence text fields, richest first (mirrors _fold_in / tradeoff_modeler ordering).
_TEXT_FIELDS = (
    "direct_quote", "statement", "full_text", "content", "extracted_text",
    "fetched_body", "raw_content", "raw_text", "page_text", "source_text", "body", "text",
)


def _row_text(row: dict[str, Any]) -> str:
    return max(
        (str(row.get(k) or "") for k in _TEXT_FIELDS),
        key=len, default="",
    )


def _tokens(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


# ─────────────────────────────────────────────────────────────────────────────
# calculator — single deterministic arithmetic expression (EXPLORATORY lane)
# ─────────────────────────────────────────────────────────────────────────────
async def _tool_calculator(
    workspace: Any, *, expression: str = "", **_ignored: Any,
) -> ToolResult:
    """Evaluate ONE whitelisted-AST arithmetic expression (reuses tradeoff_modeler's validator +
    interpreter). Deterministic, no LLM, no sandbox. EXPLORATORY: the result carries no evidence
    span, so it is planner-facing (``renderable=False``) — to RENDER a derived number use
    verified_compute."""
    from src.polaris_graph.synthesis.tradeoff_modeler import (  # noqa: PLC0415
        _eval_formula, _formula_names,
    )

    expr = str(expression or "").strip()
    if not expr:
        return ToolResult(
            success=False, tool_name="calculator",
            markdown="calculator requires an `expression`.", error="missing_expression",
        )
    ok, reason, refs = _formula_names(expr, set())
    if not ok:
        return ToolResult(
            success=False, tool_name="calculator",
            markdown=f"calculator rejected {expr!r}: {reason}", error=f"formula_invalid:{reason}",
        )
    if refs:
        return ToolResult(
            success=False, tool_name="calculator",
            markdown=f"calculator is constant-only; unknown names {sorted(refs)}",
            error="unbound_names",
        )
    try:
        value = _eval_formula(expr, {})
    except (ValueError, ZeroDivisionError, OverflowError) as exc:
        return ToolResult(
            success=False, tool_name="calculator",
            markdown=f"calculator failed on {expr!r}: {exc}", error=f"eval_error:{str(exc)[:80]}",
        )
    return ToolResult(
        success=True, tool_name="calculator",
        markdown=f"`{expr}` = {value} (EXPLORATORY — planner-facing; render via verified_compute)",
        statistics={"expression": expr, "value": value},
        insights=[f"{expr} = {value}"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# get_evidence — full text + metadata of ONE evidence row
# ─────────────────────────────────────────────────────────────────────────────
async def _tool_get_evidence(
    workspace: Any, *, ev_id: str = "", max_chars: int = 4000, **_ignored: Any,
) -> ToolResult:
    """Return the FULL text + key metadata of one evidence row by id (the agent normally sees
    only the digest). Read-only, no network."""
    eid = str(ev_id or "").strip()
    row = workspace.ev_store.get(eid) if eid else None
    if not isinstance(row, dict):
        return ToolResult(
            success=False, tool_name="get_evidence",
            markdown=f"No evidence row {eid!r} in the pool.", error="ev_not_found",
        )
    text = _row_text(row)
    try:
        cap = int(max_chars)
    except (TypeError, ValueError):
        cap = 4000
    body = text[:cap]
    md = [
        f"**{eid}** [CITE:{eid}]",
        f"- title: {str(row.get('title') or row.get('source_title') or '')[:200]}",
        f"- url: {str(row.get('source_url') or row.get('url') or '')[:200]}",
        f"- text ({len(text)} chars{', truncated' if len(text) > cap else ''}):",
        body,
    ]
    return ToolResult(
        success=True, tool_name="get_evidence", markdown="\n".join(md),
        source_evidence_ids=[eid],
    )


# ─────────────────────────────────────────────────────────────────────────────
# search_corpus — keyword search over the CURRENT ev_store (read-only, no network)
# ─────────────────────────────────────────────────────────────────────────────
async def _tool_search_corpus(
    workspace: Any, *, query: str = "", top_k: int = 8, **_ignored: Any,
) -> ToolResult:
    """Rank rows already in the pool by query-term frequency; snippet per hit. The mandatory
    'do we already have this?' stop BEFORE any live fetch. Read-only, no network, no LLM."""
    q = str(query or "").strip()
    if not q:
        return ToolResult(
            success=False, tool_name="search_corpus",
            markdown="search_corpus requires a `query`.", error="missing_query",
        )
    try:
        k = max(1, int(top_k))
    except (TypeError, ValueError):
        k = 8
    q_tokens = set(_tokens(q))
    if not q_tokens:
        return ToolResult(
            success=False, tool_name="search_corpus",
            markdown="query had no searchable tokens.", error="empty_query_tokens",
        )
    scored: list[tuple[float, str, dict]] = []
    for eid, row in workspace.ev_store.items():
        if not isinstance(row, dict):
            continue
        text = f"{row.get('title') or ''} {_row_text(row)}"
        toks = _tokens(text)
        if not toks:
            continue
        counts = sum(toks.count(t) for t in q_tokens)
        if counts <= 0:
            continue
        # length-normalized term frequency (cheap BM25-ish) so a long junk page can't win on raw counts
        score = counts / (1.0 + 0.001 * len(toks))
        scored.append((score, str(eid), row))
    scored.sort(key=lambda t: (-t[0], t[1]))
    hits = scored[:k]
    if not hits:
        return ToolResult(
            success=True, tool_name="search_corpus",
            markdown=f"No rows in the pool match {q!r} (searched {len(workspace.ev_store)}).",
            statistics={"matches": 0, "searched": len(workspace.ev_store)},
        )
    lines = [f"**search_corpus {q!r}: {len(hits)} of {len(scored)} matches**", ""]
    for score, eid, row in hits:
        snippet = _snippet(_row_text(row), q_tokens)
        lines.append(f"- {eid} (score={score:.2f}): {snippet} [CITE:{eid}]")
    return ToolResult(
        success=True, tool_name="search_corpus", markdown="\n".join(lines),
        source_evidence_ids=[eid for _, eid, _ in hits],
        statistics={"matches": len(scored), "searched": len(workspace.ev_store)},
    )


def _snippet(text: str, q_tokens: set[str], width: int = 160) -> str:
    low = text.lower()
    pos = -1
    for t in q_tokens:
        i = low.find(t)
        if i >= 0 and (pos < 0 or i < pos):
            pos = i
    if pos < 0:
        return text[:width].strip()
    start = max(0, pos - width // 4)
    return ("..." if start > 0 else "") + text[start:start + width].strip()


# ─────────────────────────────────────────────────────────────────────────────
# list_baskets — one-line-per-basket index of the whole corpus shape
# ─────────────────────────────────────────────────────────────────────────────
async def _tool_list_baskets(
    workspace: Any, *, max_rows: int = 200, **_ignored: Any,
) -> ToolResult:
    """One line per basket: id, member count, work-level corroboration, assignment status. Lets
    the agent scan the whole corpus without N inspect_basket calls. Read-only."""
    menu = workspace.basket_menu
    member_map = dict(getattr(menu, "basket_member_ev_ids", {}) or {}) if menu is not None else {}
    if not member_map:
        return ToolResult(
            success=True, tool_name="list_baskets",
            markdown="No basket digest available (no multi-member clusters).",
            statistics={"baskets": 0},
        )
    corr_map = dict(getattr(menu, "basket_work_corroboration", {}) or {})
    assigned_ev = _assigned_ev_ids(workspace)
    try:
        cap = max(1, int(max_rows))
    except (TypeError, ValueError):
        cap = 200
    lines = [f"**{len(member_map)} baskets**", ""]
    for bid in sorted(member_map)[:cap]:
        members = list(member_map.get(bid) or [])
        n_assigned = sum(1 for m in members if m in assigned_ev)
        status = "assigned" if n_assigned == len(members) and members else (
            "unassigned" if n_assigned == 0 else f"partial({n_assigned}/{len(members)})"
        )
        lines.append(
            f"- {bid}: {len(members)} member(s), corroboration={corr_map.get(bid, len(members))}, {status}"
        )
    return ToolResult(
        success=True, tool_name="list_baskets", markdown="\n".join(lines),
        statistics={"baskets": len(member_map)},
    )


# ─────────────────────────────────────────────────────────────────────────────
# coverage_audit — deterministic (never-LLM) coverage accounting
# ─────────────────────────────────────────────────────────────────────────────
async def _tool_coverage_audit(workspace: Any, **_ignored: Any) -> ToolResult:
    """Deterministic accounting: unassigned basket ids, per-section basket/ev counts, residual
    fraction. The O2/O3 math on demand so the agent SEES its own coverage. Never-LLM."""
    from src.polaris_graph.outline.outline_agent import _plan_field  # noqa: PLC0415

    menu = workspace.basket_menu
    member_map = dict(getattr(menu, "basket_member_ev_ids", {}) or {}) if menu is not None else {}
    assigned_ev = _assigned_ev_ids(workspace)

    unassigned_baskets = sorted(
        bid for bid, members in member_map.items()
        if not any(m in assigned_ev for m in (members or []))
    )
    total_ev = len(workspace.ev_store)
    n_assigned_ev = len(assigned_ev & set(workspace.ev_store.keys()))
    residual = 0.0 if total_ev == 0 else round(1.0 - n_assigned_ev / total_ev, 4)

    per_section = []
    for p in workspace.outline_draft:
        title = str(_plan_field(p, "title", "") or "")
        ev_ids = list(_plan_field(p, "ev_ids", []) or [])
        basket_ids = list(_plan_field(p, "basket_ids", []) or [])
        per_section.append((title, len(ev_ids), len(basket_ids)))

    lines = [
        f"**coverage_audit**: {total_ev} ev rows, {n_assigned_ev} assigned, "
        f"residual={residual:.2%}",
        f"- unassigned baskets ({len(unassigned_baskets)}): {unassigned_baskets[:40]}",
        "- per section (title: ev_ids, baskets):",
    ]
    for title, n_ev, n_b in per_section:
        floor_flag = " [BELOW FLOOR: 0 baskets]" if n_b == 0 else ""
        lines.append(f"    {title!r}: {n_ev} ev, {n_b} baskets{floor_flag}")
    return ToolResult(
        success=True, tool_name="coverage_audit", markdown="\n".join(lines),
        statistics={
            "total_ev": total_ev, "assigned_ev": n_assigned_ev, "residual": residual,
            "unassigned_baskets": len(unassigned_baskets),
            "sections": len(per_section),
            "sections_below_floor": sum(1 for _, _, n_b in per_section if n_b == 0),
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# preview_section_evidence — what compose will receive for ONE section
# ─────────────────────────────────────────────────────────────────────────────
async def _tool_preview_section_evidence(
    workspace: Any, *, section: str = "", **_ignored: Any,
) -> ToolResult:
    """For one section: its assigned ev rows' titles + gists — exactly what compose receives.
    Read-only ('walk in the reader's shoes')."""
    from src.polaris_graph.outline.outline_agent import _plan_field  # noqa: PLC0415

    sec = str(section or "").strip()
    if not sec:
        return ToolResult(
            success=False, tool_name="preview_section_evidence",
            markdown="preview_section_evidence requires a `section`.", error="missing_section",
        )
    sec_l = sec.lower()
    match = None
    for p in workspace.outline_draft:
        title = str(_plan_field(p, "title", "") or "")
        if title.strip().lower() == sec_l or (sec_l and sec_l in title.strip().lower()):
            match = p
            break
    if match is None:
        return ToolResult(
            success=False, tool_name="preview_section_evidence",
            markdown=f"No section matching {sec!r}.", error="section_not_found",
        )
    title = str(_plan_field(match, "title", "") or "")
    ev_ids = list(_plan_field(match, "ev_ids", []) or [])
    lines = [f"**Section {title!r}**: {len(ev_ids)} assigned ev row(s)", ""]
    for eid in ev_ids[:30]:
        row = workspace.ev_store.get(eid, {})
        gist = (str(row.get("title") or "") or _row_text(row)[:80]).strip()
        lines.append(f"- {eid}: {gist[:120]} [CITE:{eid}]")
    return ToolResult(
        success=True, tool_name="preview_section_evidence", markdown="\n".join(lines),
        source_evidence_ids=ev_ids,
    )


# ─────────────────────────────────────────────────────────────────────────────
# verified_compute — THE moat tool: derive a number that renders via [#calc:]
# ─────────────────────────────────────────────────────────────────────────────
async def _tool_verified_compute(
    workspace: Any, *, question: str = "", datapoints: Any = None, spec: Any = None,
    render_field: Optional[str] = None, lead: str = "", section: str = "", **_ignored: Any,
) -> ToolResult:
    """Derive a number through the VERIFIED lane (build_quantified_spec -> execute_quantified_model)
    and return a render-eligible sentence carrying its ``[#calc:]`` token — the ONLY compute output
    allowed to render. Fail-closed: a bad spec yields success=False and renders nothing.

    ``section`` names the outline section this number belongs in; the render-ready sentence is
    recorded on the workspace so the FULL-CORPUS composer can APPEND it into that section body
    DETERMINISTICALLY (the writer LLM cannot copy the unguessable spec_hash). If ``section`` is
    omitted the composer auto-homes the claim by matching the sourced datapoints' ev_ids against
    the section's ev_ids. Either way the appended sentence only survives strict_verify if the
    computed model verifies its token — emission is fail-closed."""
    from src.polaris_graph.outline.verified_compute import run_verified_compute  # noqa: PLC0415

    if not isinstance(datapoints, list) or not isinstance(spec, dict):
        return ToolResult(
            success=False, tool_name="verified_compute",
            markdown="verified_compute requires `datapoints` (list) and `spec` (dict).",
            error="bad_args",
        )
    claim = await run_verified_compute(
        workspace, question=str(question or workspace.research_question),
        datapoints=datapoints, raw_spec=spec, render_field=render_field,
    )
    if claim is None:
        return ToolResult(
            success=False, tool_name="verified_compute",
            markdown="verified_compute: spec failed to build/execute (fail-closed) — no number rendered.",
            error="spec_rejected_or_exec_failed",
        )
    lead_text = str(lead or "").strip() or "The computed value is"
    sentence = claim.render_sentence(lead_text)
    # MOAT DETERMINISTIC EMISSION: record the render-ready sentence on the workspace so the
    # composer can inject it into the target section body verbatim (fail-closed: it renders only if
    # strict_verify re-verifies its [#calc:] token against the registered model).
    input_ev_ids = [
        str(dp.get("evidence_id"))
        for dp in datapoints
        if isinstance(dp, dict) and dp.get("evidence_id")
    ]
    claims_sink = getattr(workspace, "computed_claims", None)
    if isinstance(claims_sink, list):
        claims_sink.append({
            "section": str(section or "").strip(),
            "sentence": sentence,
            "calc_token": claim.calc_token,
            "input_ev_ids": input_ev_ids,
        })
    return ToolResult(
        success=True, tool_name="verified_compute",
        markdown=(
            f"VERIFIED computed value **{claim.display_value}** renders via `{claim.calc_token}`.\n\n"
            f"Render-ready sentence: {sentence}"
        ),
        statistics={
            "display_value": claim.display_value, "model_id": claim.model_id,
            "spec_hash": claim.spec_hash, "field_id": claim.field_id,
            "calc_token": claim.calc_token, "formula": claim.formula,
            "render_sentence": sentence,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# fetch_url — targeted re-fetch of ONE named URL, folded in through the SHARED seam
# ─────────────────────────────────────────────────────────────────────────────
async def _default_fetch_row(url: str, max_chars: int) -> Optional[dict[str, Any]]:
    """Production single-URL fetch: the AccessBypass cascade (Crawl4AI/Jina/Firecrawl + fallbacks)
    via live_retriever._fetch_content, shaped into ONE cp-format evidence row. Network path —
    exercised only in live runs; unit tests inject a fake fetcher instead."""
    from src.polaris_graph.retrieval.live_retriever import _fetch_content  # noqa: PLC0415

    content, ok, title, _body_type, _jsonld = await asyncio.to_thread(
        _fetch_content, url, max_chars,
    )
    if not ok or not str(content or "").strip():
        return None
    return {
        "source_url": url, "url": url, "title": title or url,
        "fetched_body": content, "full_text": content,
    }


async def _tool_fetch_url(
    workspace: Any, agent_model: str, *, url: str = "", max_chars: int = 20000,
    fetch_fn: Optional[Callable[[str, int], "Any"]] = None, **_ignored: Any,
) -> ToolResult:
    """Targeted re-fetch of ONE named URL (the agent saw a citation/link inside evidence and wants
    the primary). The fetched page re-enters evidence through the SAME shared fold-in seam as
    search_more_evidence (``fold_in_fetched_rows``: url-dedup -> offset-renumber with hard
    id-collision assert -> S2 stamp/delete -> insert), so a second content path can NEVER diverge
    from the id guard or the junk/off-topic screen. No number and no citation is invented here.

    ``fetch_fn(url, max_chars) -> row|None`` is injectable so the fold-in re-entry is unit-testable
    without network; it defaults to the production AccessBypass cascade."""
    from src.polaris_graph.outline._fold_in import fold_in_fetched_rows  # noqa: PLC0415

    u = str(url or "").strip()
    if not u:
        return ToolResult(success=False, tool_name="fetch_url",
                          markdown="fetch_url requires a `url`.", error="missing_url")
    try:
        cap = max(1000, int(max_chars))
    except (TypeError, ValueError):
        cap = 20000
    if u in workspace.existing_urls():
        return ToolResult(
            success=False, tool_name="fetch_url",
            markdown=f"URL already in the pool (no re-fetch): {u}", error="url_already_present")

    fetcher = fetch_fn or _default_fetch_row
    try:
        maybe = fetcher(u, cap)
        row = await maybe if asyncio.iscoroutine(maybe) else maybe
    except Exception as exc:  # noqa: BLE001 — a single fetch must not crash the loop
        return ToolResult(success=False, tool_name="fetch_url",
                          markdown=f"fetch_url failed for {u}: {exc}", error=str(exc)[:300])
    if not isinstance(row, dict):
        return ToolResult(success=False, tool_name="fetch_url",
                          markdown=f"fetch_url got no usable content from {u}.", error="empty_fetch")

    fold = await fold_in_fetched_rows(
        workspace, [row], research_question=workspace.research_question, agent_model=agent_model,
    )
    disclosure = (
        f"fetch_url[{u}] kept {fold.n_kept}, url-dup {fold.n_url_dup}, deleted {fold.n_deleted} "
        f"(chrome={len(fold.deleted_chrome)}, off-topic={len(fold.deleted_offtopic)})"
    )
    workspace.disclose(disclosure)
    kept_ids = [r.get("evidence_id") for r in fold.kept_rows]
    md = [f"**{disclosure}**"]
    for eid in kept_ids:
        md.append(f"- {eid}: {u} [CITE:{eid}]")
    return ToolResult(
        success=fold.n_kept > 0, tool_name="fetch_url", markdown="\n".join(md),
        source_evidence_ids=[e for e in kept_ids if e],
        statistics={"kept": fold.n_kept, "url_dup": fold.n_url_dup, "deleted": fold.n_deleted},
    )


# ─────────────────────────────────────────────────────────────────────────────
# find_contradictions — surface conflict (direction / magnitude outlier), never average
# ─────────────────────────────────────────────────────────────────────────────
_NUM_RE = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")


def _headline_numbers(text: str) -> list[float]:
    """All parseable magnitudes in a row's text (commas stripped), skipping bare 4-digit years."""
    vals: list[float] = []
    for m in _NUM_RE.findall(text or ""):
        raw = m.replace(",", "")
        try:
            v = float(raw)
        except ValueError:
            continue
        # skip a bare calendar year (1900-2099) so a date is not mistaken for a magnitude
        if raw.isdigit() and 1900 <= v <= 2099 and "." not in raw:
            continue
        vals.append(v)
    return vals


async def _tool_find_contradictions(
    workspace: Any, *, ev_ids: Any = None, outlier_ratio: float = 100.0, **_ignored: Any,
) -> ToolResult:
    """Surface CONFLICT among a set of evidence rows on the same aspect — deterministic, spend-free.

    Two conflict modes (design Category D #26): (1) DIRECTION conflict — one row asserts an explicit
    increase and another an explicit decrease on the endpoint; (2) MAGNITUDE outlier — one row's
    headline value is >= ``outlier_ratio`` x another's (the 1000x-off poison outlier, H22). Conflicts
    are surfaced as named material with BOTH ev_ids; nothing is averaged and nothing is deleted
    (§-1.3 weight, don't filter). Read-only: never mutates ``ev_store``.

    NOTE: this is the deterministic core. Pairwise NLI-entailment via the mirror model is an
    OPTIONAL fail-open enrichment (not run here to stay spend-free); it can only ADD advisory
    conflicts, never suppress a deterministic one.
    """
    from src.polaris_graph.retrieval.contradiction_detector import _extract_direction  # noqa: PLC0415

    ids = [str(e) for e in (ev_ids or list(workspace.ev_store.keys()))]
    rows = [(e, workspace.ev_store.get(e)) for e in ids]
    rows = [(e, r) for e, r in rows if isinstance(r, dict)]
    try:
        ratio = float(outlier_ratio)
    except (TypeError, ValueError):
        ratio = 100.0

    raw_feats = []
    for e, r in rows:
        text = _row_text(r)
        raw_feats.append((e, _extract_direction(text), _headline_numbers(text)))

    # Strip magnitudes that appear IDENTICALLY in every row (a shared denominator/unit such as the
    # "per 100,000" in a rate, or a common cohort size) — they are not distinguishing values and
    # would false-flag a magnitude outlier (rate vs its own denominator). Deterministic, order-free.
    shared: set[float] | None = None
    for _e, _d, nums in raw_feats:
        s = set(nums)
        shared = s if shared is None else (shared & s)
    shared = shared or set()
    feats = [
        (e, d, [n for n in nums if n not in shared] or list(nums))
        for e, d, nums in raw_feats
    ]

    pairs: list[dict[str, Any]] = []
    involved: set[str] = set()
    for i in range(len(feats)):
        for j in range(i + 1, len(feats)):
            ei, di, ni = feats[i]
            ej, dj, nj = feats[j]
            if di and dj and di != dj:
                pairs.append({"a": ei, "b": ej, "type": "direction_conflict",
                              "direction": f"{ei}:{di} vs {ej}:{dj}"})
                involved.update((ei, ej))
                continue
            if ni and nj:
                hi, lo = max(ni), min(nj)
                hi2, lo2 = max(nj), min(ni)
                best = max(
                    (hi / lo if lo else float("inf")),
                    (hi2 / lo2 if lo2 else float("inf")),
                )
                if best >= ratio:
                    pairs.append({"a": ei, "b": ej, "type": "magnitude_outlier",
                                  "ratio": round(best, 2)})
                    involved.update((ei, ej))

    if not pairs:
        return ToolResult(
            success=True, tool_name="find_contradictions",
            markdown=f"No direction/magnitude conflict among {len(rows)} row(s) "
                     "(agreement or unresolved — never silently averaged).",
            statistics={"conflicts": 0, "rows": len(rows), "pairs": []},
        )
    lines = [f"**find_contradictions: {len(pairs)} conflict pair(s)** across {len(rows)} rows", ""]
    for p in pairs:
        if p["type"] == "direction_conflict":
            lines.append(f"- DIRECTION CONFLICT {p['a']} <-> {p['b']}: {p['direction']} "
                         f"[CITE:{p['a']}] [CITE:{p['b']}]")
        else:
            lines.append(f"- MAGNITUDE OUTLIER {p['a']} <-> {p['b']}: {p['ratio']}x apart "
                         f"[CITE:{p['a']}] [CITE:{p['b']}]")
    lines.append("")
    lines.append("These are CONFLICTING-evidence material (surface both sides; never average, "
                 "never delete — §-1.3 weight, don't filter).")
    return ToolResult(
        success=True, tool_name="find_contradictions", markdown="\n".join(lines),
        source_evidence_ids=sorted(involved),
        statistics={"conflicts": len(pairs), "rows": len(rows), "pairs": pairs},
    )


# ─────────────────────────────────────────────────────────────────────────────
# helpers + registration
# ─────────────────────────────────────────────────────────────────────────────
def _assigned_ev_ids(workspace: Any) -> set[str]:
    from src.polaris_graph.outline.outline_agent import _plan_field  # noqa: PLC0415
    return {
        eid
        for p in workspace.outline_draft
        for eid in (_plan_field(p, "ev_ids", None) or [])
    }


def register_outline_toolkit(
    registry: ToolRegistry,
    workspace: Any,
    agent_model: str,
    deadline: Optional[float] = None,
) -> list[str]:
    """Wire the T1 read-only/deterministic tools + verified_compute onto ``registry``. Returns the
    list of registered tool names. The driver iterates the registry unchanged."""

    def _bind(fn):
        async def _exec(evidence_store, data_points, client, **kw):  # noqa: ANN001
            return await fn(workspace, **kw)
        return _exec

    def _bind_am(fn):
        # fetch_url needs agent_model (for the fold-in topic judge); capture it in the closure so
        # the driver's uniform execute(...) contract is unchanged.
        async def _exec(evidence_store, data_points, client, **kw):  # noqa: ANN001
            return await fn(workspace, agent_model, **kw)
        return _exec

    specs = [
        ("fetch_url", _tool_fetch_url,
         "Targeted re-fetch of ONE named URL — turns 'source B cites source A' into actually "
         "reading A. Re-enters evidence through the SAME fold-in seam as search_more_evidence.",
         {"url": "the URL to fetch", "max_chars": "optional body cap (default 20000)"}),
        ("calculator", _tool_calculator,
         "Evaluate ONE arithmetic expression (deterministic, no LLM). EXPLORATORY — render a "
         "derived number via verified_compute, not this.",
         {"expression": "a pure arithmetic expression, e.g. (1493602-903095)*1000"}),
        ("get_evidence", _tool_get_evidence,
         "Return the FULL text + metadata of one evidence row by id.",
         {"ev_id": "the evidence id", "max_chars": "optional text cap (default 4000)"}),
        ("search_corpus", _tool_search_corpus,
         "Keyword search over the evidence ALREADY in the pool (no network). The 'do we already "
         "have this?' stop before any live fetch.",
         {"query": "keywords to search", "top_k": "max hits (default 8)"}),
        ("list_baskets", _tool_list_baskets,
         "One line per basket (id, members, corroboration, assignment) — scan the whole corpus "
         "shape at once.",
         {}),
        ("coverage_audit", _tool_coverage_audit,
         "Deterministic coverage accounting: unassigned baskets, per-section counts, residual "
         "fraction, sections below floor.",
         {}),
        ("preview_section_evidence", _tool_preview_section_evidence,
         "Preview one section's assigned evidence — exactly what compose will receive.",
         {"section": "the section title"}),
        ("find_contradictions", _tool_find_contradictions,
         "Surface CONFLICT among evidence rows (opposite direction, or a magnitude outlier) — both "
         "sides cited, never averaged, never deleted. Deterministic, no network, no LLM.",
         {"ev_ids": "list of evidence ids to compare (default: all in the pool)",
          "outlier_ratio": "magnitude-outlier threshold (default 100)"}),
        ("verified_compute", _tool_verified_compute,
         "Derive a number through the VERIFIED lane and render it via a [#calc:] token (the ONLY "
         "compute output allowed to render).",
         {"question": "what is being computed",
          "datapoints": "list of sourced datapoints {evidence_id,label,context,value,unit}",
          "spec": "the model spec {model_id,title,inputs,outputs}",
          "render_field": "optional output field to render (default first)",
          "lead": "optional lead prose for the rendered sentence",
          "section": "outline section title this number belongs in — the composer appends the "
                     "verified sentence into that section body deterministically (default: "
                     "auto-home by the sourced datapoints' ev_ids)"}),
    ]
    _agent_model_tools = {"fetch_url"}
    registered: list[str] = []
    for name, fn, desc, params in specs:
        binder = _bind_am if name in _agent_model_tools else _bind
        registry.register(ToolDefinition(
            name=name, description=desc, requires_data=False, requires_llm=False,
            parameters=params, execute=binder(fn),
        ))
        registered.append(name)
    return registered
