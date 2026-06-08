"""I-cred-012b — production credibility JUDGE factory (LLM-backed) for the P2 credibility skill.

Builds the injected ``judge(research_question, payload) -> dict`` that
``credibility_skill.score_source_credibility`` consumes per source. The factory is PURE prompt-format +
JSON-parse; the LLM call is DEPENDENCY-INJECTED (``call_llm``) so it is offline-testable and the model /
client live entirely in the caller the sweep runner supplies (012a). Open-weight model ONLY (the certified
voter slate) — the caller binds the model.

Robustness contract (matches `credibility_skill._apply_judge`): on ANY malformed LLM output the judge
returns a dict missing/!=reliability_score (or ``{}``), which P2 isolates as a per-row ``judge_error``
(recall-first, fail-loud-but-bounded). It NEVER raises into P2 (P2 catches, but we keep it clean).
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

# The judge sees ONLY the bounded payload (source identity + title/url/snippet + authority prior +
# domain_hint) — same payload `credibility_skill._build_judge_payload` assembles. No rubric branch.
# The judge sees ONLY the bounded payload — the SAME deterministic signals `_build_judge_payload`
# assembles (plan §9.1): identity + descriptors + authority prior + source_class + corroboration_count +
# authority_confidence + signal_scores + junk_class + predatory_oa + origin_cluster_id. No rubric branch.
_PROMPT = (
    "You are a source-credibility judge for ONE source against ONE research question. Judge only this "
    "source, for this question, reasoning from the deterministic signals below.\n"
    "QUESTION: {question}\n"
    "SOURCE:\n"
    "  title: {title}\n"
    "  url: {url}\n"
    "  snippet: {snippet}\n"
    "  authority_score (deterministic prior, 0..1): {authority_score}\n"
    "  authority_confidence: {authority_confidence}\n"
    "  source_class: {source_class}\n"
    "  corroboration_count (independent corroborating sources): {corroboration_count}\n"
    "  signal_scores: {signal_scores}\n"
    "  junk_class: {junk_class}\n"
    "  predatory_oa (predatory open-access flag): {predatory_oa}\n"
    "  origin_cluster_id (Phase-4 independence cluster): {origin_cluster_id}\n"
    "  domain_hint: {domain_hint}\n\n"
    "Return STRICT JSON only, no prose, no code fence:\n"
    '{{"reliability_score": <0..1: how reliable/authoritative this source is FOR THIS QUESTION, '
    "reasoning from authority_score / authority_confidence / source_class / corroboration_count / "
    "signal_scores / junk_class / predatory_oa>, "
    '"relevance_score": <0..1: how on-topic this source is for the question>, '
    '"rationale": "<one sentence citing the signals you relied on>", '
    '"signals_cited": [<deterministic signal names you relied on, e.g. authority_score, corroboration_count>], '
    '"query_need": "<a follow-up query if this source is thin, else empty>"}}'
)

# The deterministic signal fields the prompt MUST surface (plan §9.1 — guards against a future edit
# dropping them again, which would have the judge score credibility blind to its evidence).
REQUIRED_SIGNAL_FIELDS = (
    "authority_score", "authority_confidence", "source_class", "corroboration_count",
    "signal_scores", "junk_class", "predatory_oa", "origin_cluster_id",
)


def build_credibility_prompt(research_question: str, payload: dict[str, Any]) -> str:
    """Pure: render the per-source judging prompt from the FULL P2 deterministic-signal payload."""
    payload = payload or {}
    return _PROMPT.format(
        question=research_question,
        title=payload.get("title", ""),
        url=payload.get("url", ""),
        snippet=payload.get("snippet", ""),
        authority_score=payload.get("authority_score", ""),
        authority_confidence=payload.get("authority_confidence", ""),
        source_class=payload.get("source_class", ""),
        corroboration_count=payload.get("corroboration_count", ""),
        signal_scores=payload.get("signal_scores", {}),
        junk_class=payload.get("junk_class", ""),
        predatory_oa=payload.get("predatory_oa", ""),
        origin_cluster_id=payload.get("origin_cluster_id", ""),
        domain_hint=payload.get("domain_hint", ""),
    )


def parse_credibility_response(text: str) -> dict[str, Any]:
    """Parse the FIRST JSON object in the LLM text (Codex #012b P2-1: not the greedy first-{ to last-}).

    Tolerates a leading code fence / prose; trailing prose or extra objects are ignored. Non-dict / no
    valid first object => {} (=> P2 bounded per-row judge_error)."""
    if not text or not isinstance(text, str):
        return {}
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9_]*\n?", "", stripped)
        stripped = re.sub(r"\n?```\s*$", "", stripped).strip()
    start = stripped.find("{")
    if start == -1:
        return {}
    try:
        obj, _ = json.JSONDecoder().raw_decode(stripped[start:])  # FIRST JSON value, ignores the rest
    except (ValueError, TypeError):
        return {}
    return obj if isinstance(obj, dict) else {}


def make_credibility_judge(call_llm: Callable[[str], str]) -> Callable[[str, dict], dict]:
    """Return ``judge(research_question, payload) -> dict`` for ``score_source_credibility``.

    ``call_llm(prompt) -> text`` is injected — the sweep runner (012a) binds the open-weight model + the
    OpenRouter client; tests inject a deterministic stub. The judge formats the prompt, calls the LLM, and
    parses JSON; a malformed/empty response yields ``{}`` so P2 records a bounded per-row ``judge_error``.
    """
    if call_llm is None:
        raise ValueError("make_credibility_judge requires an injected call_llm(prompt) -> text")

    def judge(research_question: str, payload: dict) -> dict:
        prompt = build_credibility_prompt(research_question, payload)
        try:
            text = call_llm(prompt)
        except Exception:
            return {}  # transport failure for this row => P2 judge_error (isolated, bounded)
        return parse_credibility_response(text)

    return judge
