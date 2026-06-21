"""I-beatboth-005 (#1282) — the FAITHFUL ABSTRACTIVE WRITER for per-basket verified-compose.

Replaces the deterministic ``build_short_member_sentence`` render-probe stub (verified_compose.py)
that ships SPAN-FAITHFUL but BROKEN prose (dangling markdown-link fragments, orphaned section
numbers, HR/Reddit chrome) with an LLM writer that rephrases each verified span into CLEAN plain
declarative news-style prose carrying the EXACT canonical provenance token + every span numeric
verbatim. Each rewritten sentence is RE-RUN through the UNCHANGED ``verify_sentence_provenance``
(+ the existing region gate) by the unchanged ``_compose_one_basket`` loop; on FAIL the loop falls
back to today's verbatim K-span. Default-OFF behind ``PG_ABSTRACTIVE_WRITER``; byte-identical OFF.

ARCHITECTURE (design §3, ABSTRACTIVE_WRITER_DESIGN.md):
  * The writer is async (OpenRouter) but ``_compose_one_basket`` calls ``writer_fn`` SYNCHRONOUSLY.
    An async PRE-PASS (:func:`abstractive_pre_pass`) precomputes one verified draft per basket up
    front (LLM + bounded retry, bounded-parallel); the sync ``writer_fn``
    (:func:`make_abstractive_writer_fn`) is a pure dict lookup keyed by the basket's canonical id.
  * The writer-specific verify wrapper (:func:`make_writer_verify_fn`) is STRICTER than the K-span
    path — the four P1 closures, all in the wrapper / pre-pass, ENGINE UNTOUCHED:
      - P1-1: a TRANSPORT entailment ``judge_error`` is a WRITER FAILURE (the wrapper forces
        ``is_verified=False`` -> retry -> K-span). An advisory judge-error never ships as a
        paraphrase, only ever as the grounded-by-construction K-span.
      - P1-2: the wrapper verifies with ``allow_local_window_fallback=False`` (the K-span path keeps
        the ``True`` default via the unwrapped ``verify_fn``); a NEUTRAL/CONTRADICTED bound span
        cannot pass on a same-row local window.
      - P1-3: a numeric COMPLETENESS guard (span->sentence) — every substantive span numeric must
        appear verbatim in the rewrite, else ``is_verified=False`` -> retry -> K-span. The
        guard reuses the ENGINE'S OWN substantive-numeral definition (``_decimals_in`` /
        ``_numbers_in`` / ``_INTEGER_PERCENT_RE`` / ``_strip_dose_patterns``), so "substantive"
        means the same thing in both directions; it lives HERE, never in ``verify_sentence_provenance``.
      - P1-4: the async/sync adapter above.
  * Fail-closed activation (design §3.6 / §5.5): the writer REFUSES to activate (raises, fail-LOUD,
    LAW II) unless ``PG_STRICT_VERIFY_ENTAILMENT`` resolves to ``enforce`` — the writer's only
    semantic guarantee for a paraphrase IS the entailment leg. The env guard is the ACTIVATION
    precondition; the per-call ``judge_error`` demotion (P1-1) is the call-time enforcement.

FAITHFULNESS: ``verify_sentence_provenance`` / NLI / 4-role D8 / provenance / ``build_verified_span_draft``
/ ``_compose_one_basket`` / ``_compose_section_per_basket`` / the region gate are UNTOUCHED. Every
abstractive rewrite is re-run through the unchanged verifier + region gate; fabrication degrades to
the verbatim K-span. Always-release; never strand; never empty.
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import os
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ── env knobs (LAW VI — all parameters env-configurable; defaults documented) ────────────────────
_ENV_ENABLE = "PG_ABSTRACTIVE_WRITER"
# Model: the writer is a GENERATOR-role call (design §5.6 / §9.1.8). The campaign generator arm =
# z-ai/glm-5.2 (config/architecture/polaris_runtime_lock.yaml generator.model_slug), which is also
# the operator-specified default for #1282. Resolves to the GENERATOR-role slug at call time so it
# tracks the lock (and the campaign's all-GLM-5.2 override) rather than hardcoding a value that
# could drift from the lock; env-overridable per LAW VI.
_ENV_MODEL = "PG_ABSTRACTIVE_WRITER_MODEL"
_DEFAULT_MODEL = "z-ai/glm-5.2"
_ENV_MAX_RETRIES = "PG_ABSTRACTIVE_WRITER_MAX_RETRIES"
_DEFAULT_MAX_RETRIES = 1                       # 2 total attempts (design §5.2)
_ENV_MAX_TOKENS = "PG_ABSTRACTIVE_WRITER_MAX_TOKENS"
_DEFAULT_MAX_TOKENS = 2048                     # a rephrase, not an essay; a cap is free insurance (§3.5)
_ENV_REASONING_MAX_TOKENS = "PG_ABSTRACTIVE_WRITER_REASONING_MAX_TOKENS"
_DEFAULT_REASONING_MAX_TOKENS = 8192           # GLM burns reasoning budget — generous per §9.1.8
_ENV_CONCURRENCY = "PG_ABSTRACTIVE_WRITER_CONCURRENCY"
_DEFAULT_CONCURRENCY = 8                       # bounded fan-out (§3.5), matches campaign verify fan-out
_ENV_TEMPERATURE = "PG_ABSTRACTIVE_WRITER_TEMPERATURE"
_DEFAULT_TEMPERATURE = 0.2                     # low — faithful rephrase, not creative
_ENV_CALL_DEADLINE_S = "PG_ABSTRACTIVE_WRITER_CALL_DEADLINE_S"
_DEFAULT_CALL_DEADLINE_S = 120.0               # per-call total deadline -> force-close to K-span (§3.5)


def _abstractive_writer_enabled() -> bool:
    """``PG_ABSTRACTIVE_WRITER`` gate. DEFAULT-OFF => the caller keeps the deterministic
    ``build_short_member_sentence`` stub + bare ``_vc_verify`` byte-identical; ON => the LLM
    abstractive writer is the per-basket prose producer (behind the fail-closed activation guard)."""
    return os.getenv(_ENV_ENABLE, "0").strip().lower() not in ("", "0", "false", "off", "no")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("[abstractive_writer] %s=%r not an int; using default %d", name, raw, default)
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("[abstractive_writer] %s=%r not a float; using default %s", name, raw, default)
        return default


def _resolve_model() -> str:
    """The writer model. ``PG_ABSTRACTIVE_WRITER_MODEL`` overrides; else the GENERATOR-role slug
    (``PG_GENERATOR_MODEL``, which the lock pins to the campaign generator arm), falling back to the
    operator-specified ``z-ai/glm-5.2`` default if the generator knob is unset. The writer is a
    generator-role call (§9.1.8) so it tracks the lock rather than hardcoding a slug that could drift."""
    override = os.getenv(_ENV_MODEL, "").strip()
    if override:
        return override
    gen = os.getenv("PG_GENERATOR_MODEL", "").strip()
    return gen or _DEFAULT_MODEL


def _basket_key(basket: Any) -> str:
    """A STABLE per-basket key for the precomputed-draft dict — the basket's canonical
    ``claim_cluster_id`` (credibility_pass.ClaimBasket). Empty/missing => "" (the sync writer_fn
    treats a missing key as a writer-empty basket -> K-span fallback, never a crash)."""
    return str(getattr(basket, "claim_cluster_id", "") or "")


# ── P1-3 numeric COMPLETENESS guard helpers (reuse the ENGINE'S substantive-numeral definition) ──
def _substantive_span_numerics(span_text: str) -> set[str]:
    """The set of SUBSTANTIVE numerals in a span, using the ENGINE'S OWN definition so "substantive"
    means the same thing in both directions (design §3.2c): every decimal (``_decimals_in`` over
    dose-stripped text) PLUS every percent-expressed integer (``_INTEGER_PERCENT_RE``). Structural /
    study-marker integers (``STEP 1``, ``week 68``, ``104 weeks``, ``phase 3``) are NOT substantive
    — the engine's sentence->span numeric check exempts them via ``_DECIMAL_NUMBER_RE``, so the
    reverse span->sentence guard must exempt them too (else it would demand study markers the engine
    itself ignores and force a universal K-span no-op)."""
    from src.polaris_graph.generator.provenance_generator import (  # noqa: PLC0415
        _INTEGER_PERCENT_RE,
        _decimals_in,
        _numbers_in,
        _strip_dose_patterns,
    )
    stripped = _strip_dose_patterns(span_text or "")
    decimals = _decimals_in(stripped)
    # Percent-expressed integers (e.g. "50%", "19 percent") ARE claimed values; capture them but
    # exclude any that are already decimals.
    pct_ints = {m.group(1) for m in _INTEGER_PERCENT_RE.finditer(stripped)} - decimals
    # Restrict pct_ints to genuine integers present as standalone numbers in the span (mirrors the
    # engine's claimed_pct_ints handling, which subtracts decimals and checks integer membership).
    span_numbers = _numbers_in(stripped)
    pct_ints = {n for n in pct_ints if n in span_numbers}
    return decimals | pct_ints


def _numeral_appears_verbatim(numeral: str, sentence: str) -> bool:
    """True iff ``numeral`` appears verbatim among the sentence's numbers (after the same
    dose-strip + unicode-minus normalization the engine applies), so e.g. "13.0" vs "13" is not a
    false match. Reuses ``_numbers_in`` so extraction matches the engine exactly."""
    from src.polaris_graph.generator.provenance_generator import (  # noqa: PLC0415
        _numbers_in,
        _strip_dose_patterns,
    )
    return numeral in _numbers_in(_strip_dose_patterns(sentence or ""))


def _cited_span_text_for(tokens: list, scoped_pool: dict) -> str:
    """The combined CITED sub-span text for the parsed provenance ``tokens`` against ``scoped_pool``,
    i.e. ``direct_quote[token.start:token.end]`` per token (NOT the whole row — the whole-row text
    would demand OTHER claims' numerics and force a universal K-span no-op). Used by the
    completeness guard's span->sentence direction. Bounds-safe (out-of-range slices to "")."""
    parts: list[str] = []
    for tok in tokens or []:
        eid = str(getattr(tok, "evidence_id", "") or "")
        row = (scoped_pool or {}).get(eid) or {}
        haystack = str(row.get("direct_quote") or row.get("statement") or "")
        start = int(getattr(tok, "start", -1))
        end = int(getattr(tok, "end", -1))
        if 0 <= start < end <= len(haystack):
            parts.append(haystack[start:end])
    return " ".join(parts)


def make_writer_verify_fn(base_verify: Callable[..., Any]) -> Callable[..., Any]:
    """The WRITER-SPECIFIC verify wrapper injected as ``_compose_one_basket``'s ``verify_fn``
    (design §3.2). Pure (verify-only; no retry, no LLM). The K-span path keeps the bare
    ``base_verify`` (default ``allow_local_window_fallback=True``); ONLY the writer path wraps it.
    ``_compose_one_basket``'s signature + body are byte-identical — it just receives a different
    ``verify_fn``. The wrapper is STRICTER than the K-span path:

      P1-2: verifies with ``allow_local_window_fallback=False`` (no same-row local-window rescue).
      P1-1: a TRANSPORT entailment ``judge_error`` (the durable ``SentenceVerification.judge_error``
            field) is forced to ``is_verified=False`` (``writer_judge_error_fail_closed``).
      P1-3: a DROPPED substantive span numeric (span->sentence completeness) forces
            ``is_verified=False`` (``writer_numeric_dropped``).
    """

    def _wrapped(sentence: str, scoped_pool: dict, *args: Any, **kwargs: Any) -> Any:
        # P1-2: pin the local-window loophole shut for the writer path. (The K-span path keeps the
        # bare base_verify default True via the unwrapped verify_fn — the shared default is untouched.)
        kwargs.setdefault("allow_local_window_fallback", False)
        res = base_verify(sentence, scoped_pool, *args, **kwargs)

        # P1-1: a TRANSPORT entailment judge_error is a WRITER FAILURE. The shared verifier (with
        # PG_ENTAILMENT_JUDGE_ERROR_ADVISORY=1, the I-arch-010 default) advisory-KEEPS such a result
        # as is_verified=True and sets the durable judge_error=True marker. That advisory keep is
        # CORRECT for the deterministic K-span (a verbatim substring is grounded by construction) but
        # WRONG for an abstractive paraphrase, whose ONLY semantic guarantee is the entailment leg.
        # Read the BOOL FIELD (the canonical marker), not the soft_warnings string.
        if getattr(res, "judge_error", False) and bool(getattr(res, "is_verified", False)):
            res = dataclasses.replace(
                res,
                is_verified=False,
                failure_reasons=[*list(getattr(res, "failure_reasons", []) or []),
                                 "writer_judge_error_fail_closed"],
            )

        # P1-3: span->sentence numeric COMPLETENESS (the reverse direction the engine does NOT check).
        # Only meaningful when the sentence is otherwise verified (a sentence already failing for
        # another reason needs no completeness escalation). The cited span text is resolved from the
        # parsed tokens of the INPUT sentence against the scoped pool (the exact cited sub-spans), so
        # the denominator is the writer's own cited spans — never the whole row.
        if bool(getattr(res, "is_verified", False)):
            from src.polaris_graph.generator.provenance_generator import (  # noqa: PLC0415
                parse_provenance_tokens,
            )
            cited_span_text = _cited_span_text_for(parse_provenance_tokens(sentence), scoped_pool)
            span_numerics = _substantive_span_numerics(cited_span_text)
            if span_numerics and not all(
                _numeral_appears_verbatim(n, sentence) for n in span_numerics
            ):
                res = dataclasses.replace(
                    res,
                    is_verified=False,
                    failure_reasons=[*list(getattr(res, "failure_reasons", []) or []),
                                     "writer_numeric_dropped"],
                )
        return res

    return _wrapped


# ── the writer prompt contract (design §3.3) ─────────────────────────────────────────────────────
_WRITER_SYSTEM = (
    "You rewrite already-verified evidence spans into clean, plain, declarative news-style "
    "sentences. You NEVER add a fact that is not in a provided span. You copy every number "
    "(decimal, percent, integer, dose) exactly as written — never round, never convert units. "
    "You end each sentence with the exact provenance token supplied for the span it rephrases, "
    "copied character-for-character; you never invent or edit a token. You write subject-verb-object "
    "sentences that name the specific finding, number, and actor. You do NOT use markdown, links, "
    "bullets, headings, section numbers, captions, or academic chrome like 'this study' or "
    "'the framework'. You output exactly one sentence per span, nothing else."
)


def _build_writer_prompt(
    members: list,
    evidence_pool: dict,
    *,
    revise_reasons: Optional[list[str]] = None,
) -> str:
    """Build the user prompt: one SUPPORTS member per line, each given its verified span text and
    the EXACT canonical token (the same ``[#ev:<id>:<start>-<end>]`` ``build_verified_span_draft``
    would emit, computed by ``_member_global_span``). The writer rephrases each span into one
    declarative sentence ending with that token. On a retry, the specific wrapper failure reasons
    are fed back (RARR-style revise)."""
    from src.polaris_graph.generator.verified_compose import _member_global_span  # noqa: PLC0415

    lines: list[str] = [
        "Rewrite each verified evidence span below into ONE clean, plain, declarative "
        "news-style sentence. End each sentence with the exact provenance token shown for it, "
        "copied character-for-character. Copy every number verbatim. Output one sentence per span, "
        "in order, one per line, and nothing else.",
        "",
    ]
    for i, m in enumerate(members, start=1):
        eid = str(getattr(m, "evidence_id", "") or "")
        gspan = _member_global_span(m, evidence_pool)
        quote = str(getattr(m, "direct_quote", "") or "").strip()
        if not eid or gspan is None or not quote:
            continue
        start, end = gspan
        token = f"[#ev:{eid}:{start}-{end}]"
        lines.append(f"SPAN {i}: {quote}")
        lines.append(f"TOKEN {i} (append verbatim to sentence {i}): {token}")
        lines.append("")
    if revise_reasons:
        lines.append(
            "Your previous attempt FAILED verification for these reasons — fix them and try again:"
        )
        for r in revise_reasons:
            lines.append(f"  - {r}")
        lines.append("")
    return "\n".join(lines)


# ── the async per-basket LLM writer call ─────────────────────────────────────────────────────────
async def _call_writer(
    members: list,
    evidence_pool: dict,
    *,
    model: str,
    max_tokens: int,
    reasoning_max_tokens: int,
    temperature: float,
    revise_reasons: Optional[list[str]] = None,
) -> str:
    """ONE LLM writer call for a basket: rephrase the SUPPORTS members' verified spans into clean
    declarative prose carrying the canonical tokens. Returns the raw draft text (re-verified by the
    unchanged compose loop). On any error returns "" -> the loop falls back to the K-span (fail-loud
    to the K-span, never a silent crash)."""
    from src.polaris_graph.llm.openrouter_client import OpenRouterClient  # noqa: PLC0415

    prompt = _build_writer_prompt(members, evidence_pool, revise_reasons=revise_reasons)
    client = OpenRouterClient(model=model)
    try:
        response = await client.generate(
            prompt=prompt,
            system=_WRITER_SYSTEM,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_max_tokens=reasoning_max_tokens,
        )
        return str(getattr(response, "content", "") or "")
    finally:
        try:
            await client.close()
        except Exception:  # noqa: BLE001  — best-effort teardown; never mask the writer result
            logger.debug("[abstractive_writer] client.close() raised on teardown", exc_info=True)


def _draft_passes_wrapper(
    draft: str,
    basket: Any,
    evidence_pool: dict,
    writer_verify_fn: Callable[..., Any],
) -> tuple[bool, list[str]]:
    """Verify a candidate draft with the WRITER WRAPPER + region gate against the basket-scoped pool
    — exactly the gate ``_compose_one_basket`` will apply — to decide whether the pre-pass needs a
    retry. Returns (all_sentences_pass, failure_reasons). This MIRRORS the loop's accept condition;
    the loop remains the authoritative gate (the pre-pass only proposes)."""
    from src.polaris_graph.generator.verified_compose import (  # noqa: PLC0415
        _basket_member_regions,
        _basket_scoped_pool,
        _tokens_within_basket_regions,
        split_into_sentences,
    )
    scoped_pool = _basket_scoped_pool(basket, evidence_pool)
    regions = _basket_member_regions(basket, evidence_pool)
    sentences = split_into_sentences(draft or "")
    if not sentences:
        return False, ["writer_empty_draft"]
    reasons: list[str] = []
    for sentence in sentences:
        res = writer_verify_fn(sentence, scoped_pool)
        verified_text = str(getattr(res, "sentence", "") or "").strip() or sentence.strip()
        if not (bool(getattr(res, "is_verified", False))
                and _tokens_within_basket_regions(verified_text, regions)):
            rs = list(getattr(res, "failure_reasons", []) or [])
            reasons.extend(rs or ["writer_sentence_rejected"])
            return False, reasons
    return True, reasons


async def _pre_pass_one_basket(
    basket: Any,
    evidence_pool: dict,
    *,
    writer_verify_fn: Callable[..., Any],
    model: str,
    max_retries: int,
    max_tokens: int,
    reasoning_max_tokens: int,
    temperature: float,
    call_deadline_s: float,
) -> Optional[str]:
    """Compute one basket's draft: call the LLM writer, verify the candidate with the writer wrapper,
    and on failure retry up to ``max_retries`` times feeding the specific failure reasons back. The
    LAST attempt's draft is returned (even if failing) — the unchanged compose loop re-verifies it
    and falls back to the K-span if it does not pass (the pre-pass NEVER emits the K-span itself).
    Returns None only when the basket has no resolvable SUPPORTS member (writer skipped)."""
    from src.polaris_graph.generator.verified_compose import (  # noqa: PLC0415
        _basket_supports_members,
        _compose_junk_screen,
    )

    members = _basket_supports_members(basket)
    if not members:
        return None

    # §3.1 input-screen (#1289, advisor 2026-06-21): drop chrome members BEFORE the LLM writer call.
    # The abstractive path emits via the precomputed dict, NOT build_verified_span_draft, so the §3.4
    # OUTPUT junk screen never runs on it — AND a paraphrase mangles the multi-word chrome markers, so
    # only an INPUT screen catches them. Reuse the §3.4 high-precision allowlist screen on each
    # member's verified span text. Faithfulness-safe (§-1.3): boilerplate is not a corroborating
    # source. A MIXED basket (chrome member + real member) keeps the real member + its citation; an
    # ALL-chrome basket leaves zero members -> writer skipped (None) -> the loop K-span-falls-back and
    # §3.4 screens that too, so the all-chrome basket emits nothing (it never cascades a REAL section
    # to empty — only baskets that carry no real content drop out).
    screened_members = [
        m for m in members
        if not _compose_junk_screen(str(getattr(m, "direct_quote", "") or ""))
    ]
    if not screened_members:
        logger.info(
            "[abstractive_writer] basket=%s all SUPPORTS members screened as chrome -> writer skipped "
            "(K-span fallback)", _basket_key(basket),
        )
        return None
    members = screened_members

    revise_reasons: Optional[list[str]] = None
    last_draft = ""
    for attempt in range(max_retries + 1):
        try:
            draft = await asyncio.wait_for(
                _call_writer(
                    members, evidence_pool,
                    model=model, max_tokens=max_tokens,
                    reasoning_max_tokens=reasoning_max_tokens, temperature=temperature,
                    revise_reasons=revise_reasons,
                ),
                timeout=call_deadline_s,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "[abstractive_writer] basket=%s writer call exceeded %.0fs deadline (attempt %d) "
                "-> K-span fallback", _basket_key(basket), call_deadline_s, attempt + 1,
            )
            break
        except Exception:  # noqa: BLE001 — any writer error degrades to the K-span, never crashes the run
            logger.warning(
                "[abstractive_writer] basket=%s writer call raised (attempt %d) -> K-span fallback",
                _basket_key(basket), attempt + 1, exc_info=True,
            )
            break
        last_draft = draft
        passed, reasons = _draft_passes_wrapper(draft, basket, evidence_pool, writer_verify_fn)
        if passed:
            return draft
        revise_reasons = reasons or None
    # Return the last (failing) draft; the unchanged compose loop will fall back to the K-span.
    return last_draft


async def abstractive_pre_pass(
    baskets: list,
    evidence_pool: dict,
    *,
    writer_verify_fn: Callable[..., Any],
) -> dict:
    """ASYNC pre-pass (design §3.4a): precompute one verified draft per basket up front, under a
    ``PG_ABSTRACTIVE_WRITER_CONCURRENCY`` semaphore with a per-call total deadline. Keyed by the
    basket's canonical ``claim_cluster_id`` so the sync ``writer_fn`` is a deterministic dict lookup.
    A basket that the writer skipped/failed is simply absent (or maps to a failing draft) -> the sync
    writer_fn returns "" / the failing draft -> the unchanged loop K-span-falls-back. Never raises on
    a per-basket failure (always-release)."""
    model = _resolve_model()
    max_retries = max(0, _env_int(_ENV_MAX_RETRIES, _DEFAULT_MAX_RETRIES))
    max_tokens = max(1, _env_int(_ENV_MAX_TOKENS, _DEFAULT_MAX_TOKENS))
    reasoning_max_tokens = max(0, _env_int(_ENV_REASONING_MAX_TOKENS, _DEFAULT_REASONING_MAX_TOKENS))
    temperature = _env_float(_ENV_TEMPERATURE, _DEFAULT_TEMPERATURE)
    call_deadline_s = max(1.0, _env_float(_ENV_CALL_DEADLINE_S, _DEFAULT_CALL_DEADLINE_S))
    concurrency = max(1, _env_int(_ENV_CONCURRENCY, _DEFAULT_CONCURRENCY))

    sem = asyncio.Semaphore(concurrency)
    out: dict = {}

    async def _one(basket: Any) -> None:
        key = _basket_key(basket)
        if not key:
            return
        async with sem:
            draft = await _pre_pass_one_basket(
                basket, evidence_pool,
                writer_verify_fn=writer_verify_fn,
                model=model, max_retries=max_retries,
                max_tokens=max_tokens, reasoning_max_tokens=reasoning_max_tokens,
                temperature=temperature, call_deadline_s=call_deadline_s,
            )
        if draft is not None:
            out[key] = draft

    await asyncio.gather(*[_one(b) for b in (baskets or [])], return_exceptions=False)
    logger.info(
        "[abstractive_writer] pre-pass complete: %d/%d baskets drafted (model=%s, retries=%d)",
        len(out), len(baskets or []), model, max_retries,
    )
    return out


def make_abstractive_writer_fn(precomputed: dict) -> Callable[[Any, dict], str]:
    """The SYNC ``writer_fn`` ``_compose_one_basket`` reads: a pure dict lookup keyed by the basket's
    canonical id. A MISSING key returns "" — the loop treats a writer-empty basket as a K-span
    fallback (never a crash). So a pre-pass that skipped/failed a basket degrades safely."""

    def _writer_fn(basket: Any, _scoped_pool: dict) -> str:
        return str(precomputed.get(_basket_key(basket), "") or "")

    return _writer_fn


def assert_activation_preconditions() -> None:
    """Fail-closed activation guard (design §3.6 / §5.5). When the writer is ON it REFUSES to
    activate (raises, fail-LOUD per LAW II — no silent downgrade) unless the entailment leg resolves
    to ``enforce``: the writer's ONLY semantic guarantee for a paraphrase is the entailment leg, so
    activating it with entailment ``off``/``warn`` would ship un-entailment-checked rewritten prose.
    The env guard is the ACTIVATION precondition; the per-call ``judge_error`` demotion (P1-1) is the
    per-sentence call-time enforcement — both are required."""
    from src.polaris_graph.clinical_generator.strict_verify import _entailment_mode  # noqa: PLC0415

    mode = _entailment_mode()
    if mode != "enforce":
        raise RuntimeError(
            "abort_abstractive_writer_unsafe_activation: PG_ABSTRACTIVE_WRITER is ON but "
            f"PG_STRICT_VERIFY_ENTAILMENT resolves to {mode!r}, not 'enforce'. The abstractive "
            "writer's only semantic guarantee for a paraphrase is the entailment leg; activating it "
            "without entailment=enforce would ship un-entailment-checked rewritten prose. Set "
            "PG_STRICT_VERIFY_ENTAILMENT=enforce or disable PG_ABSTRACTIVE_WRITER."
        )
