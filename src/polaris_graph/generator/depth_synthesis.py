"""I-wire-013 (#1327) — the grounded DEPTH cross-source SYNTHESIS pass.

The net-new generation feature: turn the weighted multi-source claim BASKETS into ONE consolidated
cross-source finding per high-corroboration basket — the consolidated claim PLUS the surfaced
agreement / tension across that basket's sources — written by the LOCKED generator-role model
(``polaris_runtime_lock.yaml`` generator arm, resolved at call time), then RE-GROUNDED through the
UNCHANGED faithfulness engine so that a synthesized sentence WITHOUT a grounding span is DROPPED,
never shipped. Zero new fabrication is possible: the synthesis output is NOT trusted prose — every
sentence passes the SAME ``strict_verify`` (provenance token + numeric match + >=2 content-word
overlap) every other composer passes, against a BASKET-ID-BOUND verify pool (a token citing another
basket's source is absent from the scoped pool and fails CLOSED).

FAITHFULNESS (FROZEN engine — nothing here relaxes it):
  * The generator only ORGANIZES + PHRASES already-isolated-verified spans; a fabrication fails
    ``strict_verify`` and is DROPPED (NOT replaced by a verbatim fallback — drop-not-fallback is the
    feature: a cross-source finding that cannot re-ground is simply absent).
  * The verify pool is the basket's own isolated-``SUPPORTS`` members ONLY (``_basket_scoped_pool``),
    so a sentence citing a DIFFERENT basket's source fails closed (the anti-cross-claim contract).
  * Each surviving sentence's ``[#ev:<id>:<a>-<b>]`` token is resolved to the report's EXISTING ``[N]``
    citation number (``bib_num_by_evidence_id``) — never a fresh renumber — and is routed through the
    ONE shared chrome/truncation screen, exactly like the Key-Findings / Abstract / Conclusion bullets.

§-1.3 DNA: the ``>=2 sources`` gate is DEFINITIONAL, not a cap/target/filter — a *cross-source*
finding requires at least two corroborating sources by definition. It is an ADDITIVE render layer: it
drops NO corpus source, touches NO basket, and the existing per-section body composition is untouched.

DEFAULT-OFF: ``synthesize_cross_source_findings`` only runs when a ``synthesizer`` is injected and a
basket clears the ``>=2`` gate; with no synthesizer (the legacy ``build_depth_layer`` call) it never
runs. The cert path injects the live synthesizer below; tests inject a deterministic fake so the
faithfulness backstop (drop-the-ungrounded) is proven OFFLINE with zero spend.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# A resolved provenance token ``[#ev:<evidence_id>:<start>-<end>]`` (the shape strict_verify emits on
# a kept sentence). Captures the evidence_id so it can be mapped to the report's existing ``[N]``.
_EV_TOKEN_FULL_RE = re.compile(r"\[#ev:([A-Za-z0-9_]+):\d+-\d+\]")

# LAW VI: the cross-source corroboration floor is DEFINITIONAL (a cross-source finding needs >=2
# sources), env-overridable, fail-soft floored at 2 so it can never be weakened to a single source.
_ENV_MIN_SOURCES = "PG_DEPTH_SYNTHESIS_MIN_SOURCES"
_DEFAULT_MIN_SOURCES = 2

# Live-call env knobs (LAW VI). The model resolves to the GENERATOR-role slug (the lock) at call time.
_ENV_MODEL = "PG_DEPTH_SYNTHESIS_MODEL"
_DEFAULT_MODEL = "z-ai/glm-5.2"
_ENV_MAX_TOKENS = "PG_DEPTH_SYNTHESIS_MAX_TOKENS"
_DEFAULT_MAX_TOKENS = 32768
_ENV_REASONING_MAX_TOKENS = "PG_DEPTH_SYNTHESIS_REASONING_MAX_TOKENS"
_DEFAULT_REASONING_MAX_TOKENS = 16384
_ENV_TEMPERATURE = "PG_DEPTH_SYNTHESIS_TEMPERATURE"
_DEFAULT_TEMPERATURE = 0.2
_ENV_CONCURRENCY = "PG_DEPTH_SYNTHESIS_CONCURRENCY"
_DEFAULT_CONCURRENCY = 8
_ENV_CALL_DEADLINE_S = "PG_DEPTH_SYNTHESIS_CALL_DEADLINE_S"
_DEFAULT_CALL_DEADLINE_S = 120.0
_ENV_WALL_DEADLINE_S = "PG_DEPTH_SYNTHESIS_WALL_DEADLINE_S"
_DEFAULT_WALL_DEADLINE_S = 720.0
# §-1.3 DNA: there is NO default cap on how many cross-source findings render — breadth EMERGES from
# how many high-corroboration baskets survive the UNCHANGED strict_verify, never a forced number. The
# default is UNBOUNDED (0); an operator who wants a bounded top-of-report DIGEST can set a positive
# ``PG_DEPTH_SYNTHESIS_MAX_FINDINGS`` (a verbosity preference, never a breadth target). A hardcoded
# count cap here would be the exact filter-and-cap anti-pattern the DNA bans.
_ENV_MAX_FINDINGS = "PG_DEPTH_SYNTHESIS_MAX_FINDINGS"
_DEFAULT_MAX_FINDINGS = 0  # 0 => unbounded (let breadth emerge); >0 => operator verbosity bound


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("[depth_synthesis] %s=%r not an int; using default %d", name, raw, default)
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("[depth_synthesis] %s=%r not a float; using default %s", name, raw, default)
        return default


def min_corroboration() -> int:
    """The cross-source corroboration floor (DEFINITIONAL, floored at 2 — never a single source)."""
    return max(_DEFAULT_MIN_SOURCES, _env_int(_ENV_MIN_SOURCES, _DEFAULT_MIN_SOURCES))


def _resolve_model() -> str:
    """The synthesis model: ``PG_DEPTH_SYNTHESIS_MODEL`` overrides; else the GENERATOR-role slug
    (``PG_GENERATOR_MODEL``, pinned by the lock), falling back to the campaign default. The synthesis
    call is a generator-role call (§9.1.8) so it tracks the lock rather than hardcoding a slug."""
    override = os.getenv(_ENV_MODEL, "").strip()
    if override:
        return override
    return os.getenv("PG_GENERATOR_MODEL", "").strip() or _DEFAULT_MODEL


def bib_num_by_evidence_id(bibliography: Any) -> dict[str, int]:
    """Build ``evidence_id -> [N]`` from the report's EXISTING bibliography (``multi.bibliography``).

    The synthesized sentence cites the SAME sources the body already numbered, so its ``[#ev:...]``
    tokens resolve to the report's existing ``[N]`` — NEVER a fresh local renumber (which would
    mis-cite). A bibliography row is ``{num, evidence_id, ...}``; rows missing either key are skipped.
    """
    out: dict[str, int] = {}
    for row in bibliography or []:
        try:
            eid = str(row.get("evidence_id") or "")
            num = row.get("num")
        except AttributeError:
            continue
        if not eid or num is None:
            continue
        try:
            out[eid] = int(num)
        except (TypeError, ValueError):
            continue
    return out


def _resolve_tokens_to_citations(text: str, bib_map: dict[str, int]) -> Optional[str]:
    """Replace each ``[#ev:<id>:<a>-<b>]`` token with the report's existing ``[N]`` number.

    Returns ``None`` (drop the sentence) if ANY token's evidence_id is absent from ``bib_map`` — a
    finding that cannot be cited consistently with the report's own numbering must not ship a dangling
    or fabricated citation. PURE."""
    missing = False

    def _sub(m: re.Match[str]) -> str:
        nonlocal missing
        num = bib_map.get(m.group(1))
        if num is None:
            missing = True
            return m.group(0)
        return f"[{num}]"

    out = _EV_TOKEN_FULL_RE.sub(_sub, text or "")
    if missing:
        return None
    return out


def _default_chrome_screen(sentence: str) -> bool:
    """The ONE shared render-side chrome/truncation predicate (sentence-form). Fail-conservative:
    on any import error keep the sentence (never silently drop a real finding)."""
    try:
        from src.polaris_graph.generator.weighted_enrichment import (  # noqa: PLC0415
            is_render_chrome_or_unrenderable,
        )
    except Exception:  # pragma: no cover - weighted_enrichment is stable in-tree
        return False
    try:
        return bool(is_render_chrome_or_unrenderable(sentence, require_sentence_form=True))
    except Exception:  # pragma: no cover - the predicate is pure in-tree
        return False


def _distinct_origin_supports(basket: Any) -> list[Any]:
    """The basket's isolated-``SUPPORTS`` members deduped to ONE per distinct origin (reuses the
    verified_compose helper so cross-source counting matches the body composer exactly). Fail-soft on
    an import error: fall back to the raw ``supporting_members`` filtered to SUPPORTS."""
    try:
        from src.polaris_graph.generator.verified_compose import (  # noqa: PLC0415
            _distinct_origin_supports as _vc_distinct,
        )
        return _vc_distinct(basket)
    except Exception:  # pragma: no cover - verified_compose is stable in-tree
        members = list(getattr(basket, "supporting_members", None) or [])
        return [
            m for m in members
            if str(getattr(m, "span_verdict", "") or "").upper() == "SUPPORTS"
        ]


def _scoped_pool(basket: Any, evidence_pool: dict) -> dict:
    """The basket-id-bound verify pool (the basket's SUPPORTS members' GLOBAL rows). Reuses the
    verified_compose helper so the anti-cross-claim scoping is byte-identical to the body composer."""
    try:
        from src.polaris_graph.generator.verified_compose import (  # noqa: PLC0415
            _basket_scoped_pool,
        )
        return _basket_scoped_pool(basket, evidence_pool)
    except Exception:  # pragma: no cover - verified_compose is stable in-tree
        own = {str(getattr(m, "evidence_id", "") or "") for m in _distinct_origin_supports(basket)}
        own.discard("")
        return {eid: row for eid, row in (evidence_pool or {}).items() if eid in own}


def synthesize_cross_source_findings(
    baskets: Any,
    evidence_pool: dict,
    *,
    synthesizer: Callable[[Any, dict], str],
    verify_fn: Callable[..., Any],
    bib_num_by_evidence_id: Optional[dict[str, int]] = None,
    min_sources: Optional[int] = None,
    max_findings: Optional[int] = None,
    chrome_screen: Optional[Callable[[str], bool]] = None,
) -> list[str]:
    """The grounded cross-source synthesis CORE (deterministic given ``synthesizer`` + ``verify_fn``).

    For each basket carrying ``>= min_sources`` distinct-origin isolated-``SUPPORTS`` members:
      1. ``synthesizer(basket, evidence_pool)`` drafts ONE consolidated cross-source finding carrying
         ``[#ev:<id>:<a>-<b>]`` provenance tokens (the LOCKED generator on the cert path; an injected
         fake in tests).
      2. ``verify_fn(draft, scoped_pool)`` (= ``strict_verify``) RE-GROUNDS each sentence against the
         basket's OWN members and DROPS any that fail (numeric mismatch / overlap / no provenance /
         cross-claim) — drop-not-fallback. ``scoped_pool`` is basket-id-bound so a cross-basket
         citation fails CLOSED.
      3. Each surviving sentence's tokens resolve to the report's EXISTING ``[N]`` (never a renumber);
         a sentence with an unmappable citation is dropped; a chrome/truncated sentence is dropped.

    Returns the ordered, de-duplicated list of grounded ``[N]``-cited cross-source findings (markdown
    sentence strings, no header). FAITHFULNESS is the ``verify_fn`` — this orchestrator never relaxes
    it and never resurrects a dropped sentence.
    """
    floor = min_corroboration() if min_sources is None else max(_DEFAULT_MIN_SOURCES, int(min_sources))
    cap = _env_int(_ENV_MAX_FINDINGS, _DEFAULT_MAX_FINDINGS) if max_findings is None else int(max_findings)
    screen = _default_chrome_screen if chrome_screen is None else chrome_screen

    findings: list[str] = []
    seen: set[str] = set()
    for basket in baskets or []:
        if cap > 0 and len(findings) >= cap:
            break
        members = _distinct_origin_supports(basket)
        if len(members) < floor:
            continue  # not a CROSS-source basket (definitional, not a filter of corpus sources)
        draft = ""
        try:
            draft = str(synthesizer(basket, evidence_pool) or "")
        except Exception:  # noqa: BLE001 — a per-basket synthesizer failure never aborts the layer
            logger.warning("[depth_synthesis] synthesizer raised for a basket -> skipped", exc_info=True)
            continue
        if not draft.strip():
            continue
        scoped_pool = _scoped_pool(basket, evidence_pool)
        try:
            report = verify_fn(draft, scoped_pool)
        except Exception:  # noqa: BLE001 — a verify failure drops the basket, never ships unverified
            logger.warning("[depth_synthesis] verify_fn raised for a basket -> skipped", exc_info=True)
            continue
        for sv in (getattr(report, "kept_sentences", None) or []):
            sentence = str(getattr(sv, "sentence", "") or "").strip()
            if not sentence:
                continue
            if bib_num_by_evidence_id is not None:
                resolved = _resolve_tokens_to_citations(sentence, bib_num_by_evidence_id)
                if resolved is None:
                    continue  # an unmappable citation must not ship a dangling/fabricated [N]
                sentence = resolved.strip()
            if not sentence or screen(sentence):
                continue
            key = re.sub(r"\s+", " ", sentence).strip().lower()
            if key in seen:
                continue
            seen.add(key)
            findings.append(sentence)
            if cap > 0 and len(findings) >= cap:
                break
    return findings


# ── the live LLM synthesizer (cert path) ─────────────────────────────────────────────────────────
_SYNTHESIS_SYSTEM = (
    "You consolidate several already-verified evidence spans that report the SAME finding into ONE "
    "clean, plain, declarative news-style sentence. You state the consolidated finding, then — only "
    "if the spans themselves show it — note where the sources AGREE or where they are in TENSION. You "
    "NEVER add a fact, number, or claim that is not in a provided span. You copy every number "
    "(decimal, percent, integer, dose) exactly as written; never round, never convert units. You end "
    "the sentence with the exact provenance token(s) supplied, copied character-for-character; you "
    "never invent or edit a token. You output EXACTLY one sentence, nothing else — no markdown, no "
    "bullets, no headings, no preamble."
)


def _build_synthesis_prompt(basket: Any, members: list, evidence_pool: dict) -> str:
    """One cross-source prompt: every distinct-origin SUPPORTS member's verified span + the EXACT
    canonical token (``_member_global_span``). Returns "" when no member resolves a global span."""
    from src.polaris_graph.generator.verified_compose import _member_global_span  # noqa: PLC0415

    subject = str(getattr(basket, "claim_text", "") or getattr(basket, "subject", "") or "").strip()
    lines: list[str] = [
        "Consolidate the corroborating evidence spans below into ONE clean, plain, declarative "
        "news-style sentence that states the shared finding and (only if the spans show it) where "
        "the sources agree or are in tension. End the sentence with EVERY provenance token shown "
        "below, each copied character-for-character. Copy every number verbatim. Output one sentence.",
        "",
    ]
    if subject:
        lines.append(f"CLAIM UNDER CORROBORATION: {subject}")
        lines.append("")
    emitted = 0
    for i, m in enumerate(members, start=1):
        eid = str(getattr(m, "evidence_id", "") or "")
        gspan = _member_global_span(m, evidence_pool)
        quote = str(getattr(m, "direct_quote", "") or "").strip()
        if not eid or gspan is None or not quote:
            continue
        token = f"[#ev:{eid}:{gspan[0]}-{gspan[1]}]"
        lines.append(f"SOURCE {i}: {quote}")
        lines.append(f"TOKEN {i} (append verbatim): {token}")
        lines.append("")
        emitted += 1
    if emitted == 0:
        return ""
    return "\n".join(lines)


async def _synthesize_one_basket(
    basket: Any,
    evidence_pool: dict,
    *,
    model: str,
    max_tokens: int,
    reasoning_max_tokens: int,
    temperature: float,
    call_deadline_s: float,
) -> str:
    """ONE live generator call: consolidate a basket's SUPPORTS spans into one cross-source sentence
    carrying the canonical tokens. Returns "" on any error/timeout (the basket is simply absent from
    the synthesis -> the layer omits it; never crashes the run). Chrome members are input-screened
    BEFORE the call (a paraphrase would mangle the multi-word markers, so only an input screen catches
    them)."""
    from src.polaris_graph.generator.verified_compose import _compose_junk_screen  # noqa: PLC0415
    from src.polaris_graph.llm.openrouter_client import OpenRouterClient  # noqa: PLC0415

    members = [
        m for m in _distinct_origin_supports(basket)
        if not _compose_junk_screen(str(getattr(m, "direct_quote", "") or ""))
    ]
    if len(members) < min_corroboration():
        return ""
    prompt = _build_synthesis_prompt(basket, members, evidence_pool)
    if not prompt:
        return ""
    reasoning_arg = reasoning_max_tokens if reasoning_max_tokens and reasoning_max_tokens > 0 else None
    client = OpenRouterClient(model=model)
    try:
        response = await asyncio.wait_for(
            client.generate(
                prompt=prompt,
                system=_SYNTHESIS_SYSTEM,
                max_tokens=max_tokens,
                temperature=temperature,
                reasoning_max_tokens=reasoning_arg,
            ),
            timeout=call_deadline_s,
        )
        return str(getattr(response, "content", "") or "")
    except Exception:  # noqa: BLE001 — any error/timeout degrades to absent (always-release)
        logger.warning("[depth_synthesis] basket synthesis call failed -> omitted", exc_info=True)
        return ""
    finally:
        try:
            await client.close()
        except Exception:  # noqa: BLE001 — best-effort teardown; never mask the result
            logger.debug("[depth_synthesis] client.close() raised on teardown", exc_info=True)


async def depth_synthesis_pre_pass(
    baskets: Any,
    evidence_pool: dict,
    *,
    min_sources: Optional[int] = None,
) -> dict:
    """ASYNC pre-pass: precompute one cross-source draft per high-corroboration basket, keyed by the
    basket's canonical ``claim_cluster_id``, under a bounded semaphore + a per-call deadline + an OUTER
    wall-deadline. Reuses the PROVEN abstractive-writer teardown-drain (abandon a wall-stuck task; never
    await it — the httpx-teardown hang class). A skipped/failed/abandoned basket is simply absent ->
    the sync synthesizer returns "" -> the layer omits that finding (always-release, fail-open)."""
    from src.polaris_graph.generator.abstractive_writer import (  # noqa: PLC0415
        _DETACHED_WRITER_TASKS,
        _drain_detached_writer_task,
        _force_drop_detached_writer_task,
        install_teardown_drain_hook,
    )

    floor = min_corroboration() if min_sources is None else max(_DEFAULT_MIN_SOURCES, int(min_sources))
    model = _resolve_model()
    max_tokens = max(1, _env_int(_ENV_MAX_TOKENS, _DEFAULT_MAX_TOKENS))
    reasoning_max_tokens = max(0, _env_int(_ENV_REASONING_MAX_TOKENS, _DEFAULT_REASONING_MAX_TOKENS))
    temperature = _env_float(_ENV_TEMPERATURE, _DEFAULT_TEMPERATURE)
    call_deadline_s = max(1.0, _env_float(_ENV_CALL_DEADLINE_S, _DEFAULT_CALL_DEADLINE_S))
    wall_deadline_s = max(1.0, _env_float(_ENV_WALL_DEADLINE_S, _DEFAULT_WALL_DEADLINE_S))
    concurrency = max(1, _env_int(_ENV_CONCURRENCY, _DEFAULT_CONCURRENCY))

    eligible = [
        b for b in (baskets or [])
        if str(getattr(b, "claim_cluster_id", "") or "")
        and len(_distinct_origin_supports(b)) >= floor
    ]
    out: dict = {}
    if not eligible:
        logger.info("[depth_synthesis] pre-pass: 0 eligible high-corroboration baskets (model=%s)", model)
        return out

    sem = asyncio.Semaphore(concurrency)

    async def _one(basket: Any) -> None:
        key = str(getattr(basket, "claim_cluster_id", "") or "")
        async with sem:
            draft = await _synthesize_one_basket(
                basket, evidence_pool,
                model=model, max_tokens=max_tokens,
                reasoning_max_tokens=reasoning_max_tokens, temperature=temperature,
                call_deadline_s=call_deadline_s,
            )
        if draft:
            out[key] = draft

    tasks = [asyncio.ensure_future(_one(b)) for b in eligible]
    try:
        install_teardown_drain_hook(asyncio.get_running_loop())
    except Exception:  # noqa: BLE001 — hook install is best-effort
        logger.debug("[depth_synthesis] teardown-drain hook install skipped", exc_info=True)

    done, pending = await asyncio.wait(tasks, timeout=wall_deadline_s)
    if pending:
        logger.warning(
            "[depth_synthesis] pre-pass WALL %.0fs hit: ABANDONING %d/%d pending basket task(s) "
            "(fail-open). %d drafted before the wall.", wall_deadline_s, len(pending), len(tasks), len(out),
        )
        for t in pending:
            _DETACHED_WRITER_TASKS.add(t)
            t.add_done_callback(_drain_detached_writer_task)
            t.cancel()
            _force_drop_detached_writer_task(t)
    for t in done:
        exc = t.exception()
        if exc is not None:
            logger.warning("[depth_synthesis] a pre-pass basket task raised: %r", exc)
    logger.info(
        "[depth_synthesis] pre-pass complete: %d/%d baskets drafted (model=%s, wall=%.0fs, abandoned=%d)",
        len(out), len(eligible), model, wall_deadline_s, len(pending),
    )
    return out


def make_depth_synthesizer(precomputed: dict) -> Callable[[Any, dict], str]:
    """The SYNC ``synthesizer`` ``synthesize_cross_source_findings`` reads: a pure dict lookup keyed by
    the basket's canonical ``claim_cluster_id``. A missing key returns "" -> that basket is omitted
    from the synthesis layer (never a crash). Mirrors ``abstractive_writer.make_abstractive_writer_fn``."""

    def _synth(basket: Any, _pool: dict) -> str:
        return str(precomputed.get(str(getattr(basket, "claim_cluster_id", "") or ""), "") or "")

    return _synth
