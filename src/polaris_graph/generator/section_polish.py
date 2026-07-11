"""Post-compose SECTION-POLISH passes (2026-07-10 compose gear-loop iter 2).

Three question-agnostic, FAIL-OPEN, kill-switched passes that improve the visible quality of an
already-strict_verify-passed section WITHOUT touching the faithfulness engine. Every rewritten or
synthesized sentence is RE-VERIFIED by the base bar (``verify_sentence_provenance`` — context-level
NLI entailment + forward numeric match); on any failure the ORIGINAL is kept and the pass no-ops.

  * :func:`synthesize_qualifier_sentence` — Fix 1 (P0-1). ONE clean LLM-synthesized sentence from a
    boundary QUALIFIER basket (via the same abstractive writer + base verify bar), so the boundary
    line renders synthesis, never a raw span quote. "" when the writer produced nothing or the draft
    failed verify (the caller then emits no boundary line — never a raw quote).
  * :func:`coherence_rewrite_section` — Fix 4 (P1-2). A section-level referent-naming rewrite that
    resolves dangling anaphora ("these estimates" / "the researchers" with no antecedent) by naming
    the referent, keeping every number and every ``[#ev:...]`` token character-for-character and the
    sentence order fixed. Each rewritten sentence is re-verified; a failing or token-altering rewrite
    keeps the ORIGINAL sentence (never loses verified content).
  * :func:`sentence_semantically_duplicates` — Fix 3 (P1-1). A bounded semantic-equivalence judge:
    does a candidate boundary/disclosure sentence state the SAME finding as any of the section's kept
    verified sentences? Used to DROP a duplicated appended unit. FAIL-OPEN — any judge error / doubt
    returns False (keep the unit).

All three are DEFAULT-ON kill-switches (LAW VI). The faithfulness engine (verify_sentence_provenance
/ strict_verify / provenance / D8) is UNTOUCHED — these passes only propose; the base verifier gates.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

_EV_TOKEN_RE = re.compile(r"\[#ev:[^\]]*\]")

# ── env knobs (LAW VI) ────────────────────────────────────────────────────────────────────────────
_COHERENCE_ENV = "PG_SECTION_COHERENCE_PASS"
_BOUNDARY_DEDUP_ENV = "PG_BOUNDARY_SEMANTIC_DEDUP"
_MODEL_ENV = "PG_ABSTRACTIVE_WRITER_MODEL"
_DEFAULT_MODEL = "z-ai/glm-5.2"
_COHERENCE_MAX_TOKENS_ENV = "PG_SECTION_COHERENCE_MAX_TOKENS"
_DEFAULT_COHERENCE_MAX_TOKENS = 32768
_COHERENCE_REASONING_ENV = "PG_SECTION_COHERENCE_REASONING_MAX_TOKENS"
_DEFAULT_COHERENCE_REASONING = 16384
_COHERENCE_DEADLINE_ENV = "PG_SECTION_COHERENCE_DEADLINE_S"
_DEFAULT_COHERENCE_DEADLINE_S = 180.0
_DEDUP_DEADLINE_ENV = "PG_BOUNDARY_DEDUP_DEADLINE_S"
_DEFAULT_DEDUP_DEADLINE_S = 60.0


def _flag_on(name: str, default_on: bool = True) -> bool:
    raw = os.getenv(name, "1" if default_on else "0").strip().lower()
    if default_on:
        return raw not in ("0", "false", "off", "no")
    return raw in ("1", "true", "on", "yes")


def coherence_pass_enabled() -> bool:
    """``PG_SECTION_COHERENCE_PASS`` kill-switch (default ON). OFF => no rewrite, byte-identical body."""
    return _flag_on(_COHERENCE_ENV, default_on=True)


def boundary_semantic_dedup_enabled() -> bool:
    """``PG_BOUNDARY_SEMANTIC_DEDUP`` kill-switch (default ON). OFF => the semantic-dup judge never fires
    (the appended unit is always kept)."""
    return _flag_on(_BOUNDARY_DEDUP_ENV, default_on=True)


def _resolve_model() -> str:
    override = os.getenv(_MODEL_ENV, "").strip()
    if override:
        return override
    gen = os.getenv("PG_GENERATOR_MODEL", "").strip()
    return gen or _DEFAULT_MODEL


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _ev_token_multiset(text: str) -> tuple:
    """The ORDERED tuple of ``[#ev:...]`` provenance tokens in ``text`` — a rewrite must preserve this
    exactly (same tokens, same order) or it is rejected (token drift = citation drift)."""
    return tuple(_EV_TOKEN_RE.findall(text or ""))


def _strip_tokens(text: str) -> str:
    return " ".join(_EV_TOKEN_RE.sub(" ", text or "").split())


# ── Fix 1 (P0-1) — boundary qualifier synthesis ────────────────────────────────────────────────────
async def synthesize_qualifier_sentence(
    qualifier_basket: Any,
    evidence_pool: dict,
    *,
    section_context: "dict | None" = None,
) -> str:
    """Synthesize ONE verified sentence from ``qualifier_basket`` via the abstractive writer + base
    verify bar, for the boundary-conditions line. Returns the FIRST re-verified sentence (still carrying
    its ``[#ev:...]`` token) or "" when the writer produced nothing or no sentence passed verify. Never
    raises (fail-open -> "" -> the caller emits no boundary line, never a raw quote)."""
    try:
        from src.polaris_graph.generator.abstractive_writer import (  # noqa: PLC0415
            abstractive_pre_pass,
            make_writer_verify_fn,
            _basket_key,
        )
        from src.polaris_graph.generator.provenance_generator import (  # noqa: PLC0415
            verify_sentence_provenance,
        )
        from src.polaris_graph.generator.verified_compose import (  # noqa: PLC0415
            _basket_member_regions,
            _basket_scoped_pool,
            _tokens_within_basket_regions,
            split_into_sentences,
        )
    except Exception:  # noqa: BLE001 — infra import failure => no boundary synthesis (fail-open)
        return ""
    try:
        writer_verify_fn = make_writer_verify_fn(verify_sentence_provenance)
        precomputed = await abstractive_pre_pass(
            [qualifier_basket], evidence_pool,
            writer_verify_fn=writer_verify_fn, group_mode=True,
            section_context=section_context,
        )
        draft = str((precomputed or {}).get(_basket_key(qualifier_basket), "") or "")
        if not draft.strip():
            return ""
        scoped_pool = _basket_scoped_pool(qualifier_basket, evidence_pool)
        regions = _basket_member_regions(qualifier_basket, evidence_pool)
        for sentence in split_into_sentences(draft):
            res = writer_verify_fn(sentence, scoped_pool)
            verified_text = str(getattr(res, "sentence", "") or "").strip() or sentence.strip()
            if bool(getattr(res, "is_verified", False)) and _tokens_within_basket_regions(
                verified_text, regions
            ):
                return verified_text
        return ""
    except Exception:  # noqa: BLE001 — any synthesis fault => no boundary line (fail-open)
        logger.warning("[section_polish] boundary qualifier synthesis failed (fail-open)", exc_info=True)
        return ""


# ── Fix 4 (P1-2) — section coherence (referent-naming) rewrite ─────────────────────────────────────
_COHERENCE_SYSTEM = (
    "You are a copy editor. You are given the body of ONE report section as numbered sentences. Some "
    "sentences open with a dangling reference — a pronoun or definite phrase whose antecedent is not in "
    "this section ('these estimates', 'the researchers', 'the treatment group', 'the study') — because "
    "the sentences were drafted independently and concatenated. Rewrite ONLY to resolve those dangling "
    "references: name the specific study, source, actor, or quantity on first mention, and replace an "
    "un-anchored 'these X' / 'the X' with the concrete referent. RULES you must never break: keep the "
    "SAME number of sentences in the SAME order; copy every number (decimal, percent, integer, dose, "
    "year) exactly as written — never round, never convert; copy every bracketed provenance token "
    "'[#ev:...]' character-for-character and keep it on the SAME sentence — never move, drop, add, or "
    "edit a token; never add a fact that is not already in the sentence; never merge or split sentences; "
    "do not use markdown, headings, or bullets. Output the rewritten sentences, one per line, in order, "
    "and nothing else."
)


def _build_coherence_prompt(sentences: list[str], section_context: "dict | None") -> str:
    lines: list[str] = []
    if section_context:
        title = " ".join(str(section_context.get("title", "") or "").split())
        focus = " ".join(str(section_context.get("focus", "") or "").split())
        if title or focus:
            lines.append(f'Section title: "{title}"  focus: "{focus}"')
            lines.append("")
    lines.append("Rewrite these sentences to resolve dangling references, keeping order/count/numbers/tokens:")
    lines.append("")
    for i, s in enumerate(sentences, start=1):
        lines.append(f"{i}. {s}")
    return "\n".join(lines)


_LEAD_ENUM_RE = re.compile(r"^\s*\d+[.)]\s*")


async def _call_coherence_rewrite(sentences: list[str], section_context: "dict | None") -> str:
    from src.polaris_graph.llm.openrouter_client import OpenRouterClient  # noqa: PLC0415

    model = _resolve_model()
    max_tokens = _env_int(_COHERENCE_MAX_TOKENS_ENV, _DEFAULT_COHERENCE_MAX_TOKENS)
    reasoning = _env_int(_COHERENCE_REASONING_ENV, _DEFAULT_COHERENCE_REASONING)
    reasoning_arg = reasoning if reasoning and reasoning > 0 else None
    client = OpenRouterClient(model=model)
    try:
        response = await client.generate(
            prompt=_build_coherence_prompt(sentences, section_context),
            system=_COHERENCE_SYSTEM,
            max_tokens=max_tokens,
            temperature=0.2,
            reasoning_max_tokens=reasoning_arg,
        )
        return str(getattr(response, "content", "") or "")
    finally:
        try:
            await client.close()
        except Exception:  # noqa: BLE001 — best-effort teardown
            pass


async def coherence_rewrite_section(
    raw: str,
    evidence_pool: dict,
    *,
    section_context: "dict | None" = None,
) -> str:
    """Fix 4 (P1-2): resolve dangling anaphora in the composed section body ``raw`` (which still carries
    ``[#ev:...]`` tokens) BEFORE the unchanged strict_verify tail runs. FAIL-OPEN + kill-switched: on any
    fault, a shape/token/count mismatch, or a rewritten sentence that fails the base verifier, the
    ORIGINAL sentence is kept — so the pass can only improve coherence or no-op, never lose verified
    content or a citation. Returns the (possibly) rewritten body; byte-identical ``raw`` when OFF."""
    if not coherence_pass_enabled():
        return raw
    body = raw or ""
    if not body.strip():
        return raw
    try:
        from src.polaris_graph.generator.provenance_generator import (  # noqa: PLC0415
            verify_sentence_provenance,
        )
        from src.polaris_graph.generator.verified_compose import (  # noqa: PLC0415
            split_into_sentences,
        )
    except Exception:  # noqa: BLE001
        return raw
    sentences = split_into_sentences(body)
    # Only sentences carrying a provenance token participate; a body with <2 real sentences has no
    # cross-sentence antecedent to resolve.
    if len([s for s in sentences if _EV_TOKEN_RE.search(s)]) < 2:
        return raw
    deadline = _env_float(_COHERENCE_DEADLINE_ENV, _DEFAULT_COHERENCE_DEADLINE_S)
    try:
        import asyncio  # noqa: PLC0415

        rewritten_text = await asyncio.wait_for(
            _call_coherence_rewrite(sentences, section_context), timeout=deadline
        )
    except Exception:  # noqa: BLE001 — model / timeout fault => keep original body (fail-open)
        logger.warning("[section_polish] coherence rewrite call failed (fail-open, body unchanged)")
        return raw
    if not rewritten_text.strip():
        return raw
    new_sentences = [
        _LEAD_ENUM_RE.sub("", ln).strip()
        for ln in rewritten_text.splitlines()
        if ln.strip()
    ]
    # SHAPE GUARD: the rewrite must return the SAME number of sentences (no merge/split/reorder handling).
    if len(new_sentences) != len(sentences):
        return raw
    out: list[str] = []
    changed = 0
    for orig, new in zip(sentences, new_sentences):
        orig = orig.strip()
        new = new.strip()
        if not new or new == orig:
            out.append(orig)
            continue
        # TOKEN GUARD: exact same provenance tokens in the same order (no citation drift).
        if _ev_token_multiset(new) != _ev_token_multiset(orig):
            out.append(orig)
            continue
        # BASE-BAR RE-VERIFY: context NLI entailment + forward numeric match. Fail => keep original.
        try:
            res = verify_sentence_provenance(new, evidence_pool)
        except Exception:  # noqa: BLE001 — verifier fault on this sentence => keep original
            out.append(orig)
            continue
        if bool(getattr(res, "is_verified", False)):
            out.append(str(getattr(res, "sentence", "") or new).strip() or orig)
            changed += 1
        else:
            out.append(orig)
    if changed:
        logger.info("[section_polish] coherence rewrite resolved referents in %d sentence(s)", changed)
    return " ".join(s for s in out if s)


# ── Fix 3 (P1-1) — semantic duplicate judge for an appended unit ───────────────────────────────────
_DEDUP_SYSTEM = (
    "You compare a candidate sentence against a body of report sentences. Answer with a single word — "
    "YES or NO. Answer YES only if the candidate states the SAME finding (same claim about the same "
    "subject with the same numbers/direction) as at least one sentence already in the body, i.e. it "
    "would be redundant to add it. Answer NO if the candidate adds a genuinely different finding, a "
    "different subject, a different number, or an opposing/limiting qualification. When unsure, answer NO."
)


async def sentence_semantically_duplicates(candidate: str, kept_body: str) -> bool:
    """Fix 3 (P1-1): True iff ``candidate`` (a boundary / disclosure sentence about to be appended)
    states the SAME finding as some sentence already in ``kept_body`` — so the caller can DROP the
    duplicate. Semantic (an LLM yes/no judge), not a string match. FAIL-OPEN: any judge error, empty
    input, timeout, or non-YES answer returns False (KEEP the unit). Never raises."""
    if not boundary_semantic_dedup_enabled():
        return False
    cand = _strip_tokens(candidate)
    body = _strip_tokens(kept_body)
    if not cand or not body:
        return False
    try:
        import asyncio  # noqa: PLC0415

        from src.polaris_graph.llm.openrouter_client import OpenRouterClient  # noqa: PLC0415

        model = _resolve_model()
        deadline = _env_float(_DEDUP_DEADLINE_ENV, _DEFAULT_DEDUP_DEADLINE_S)
        prompt = (
            "BODY (existing report sentences):\n" + body[:6000] + "\n\n"
            "CANDIDATE (a sentence being considered for addition):\n" + cand[:1500] + "\n\n"
            "Does the CANDIDATE state the same finding as any sentence already in the BODY? YES or NO."
        )
        client = OpenRouterClient(model=model)
        try:
            response = await asyncio.wait_for(
                client.generate(prompt=prompt, system=_DEDUP_SYSTEM, max_tokens=8, temperature=0.0),
                timeout=deadline,
            )
        finally:
            try:
                await client.close()
            except Exception:  # noqa: BLE001
                pass
        answer = str(getattr(response, "content", "") or "").strip().lower()
        return answer.startswith("yes")
    except Exception:  # noqa: BLE001 — judge fault => keep the unit (fail-open)
        logger.warning("[section_polish] semantic-dup judge failed (fail-open, unit kept)")
        return False
