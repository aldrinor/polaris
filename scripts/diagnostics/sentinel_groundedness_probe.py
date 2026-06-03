"""I-run11-002 L1 EMPIRICAL PROBE — Sentinel groundedness DISCRIMINATION on OpenRouter.

READ-ONLY DIAGNOSTIC. This script changes NO production wiring. It tests whether any
(model, prompt) combo available on OpenRouter can correctly DISCRIMINATE a genuinely-grounded
claim from a fabricated (ungrounded) claim against the SAME document, so that I-run11-002 L1
can decide whether the Sentinel groundedness role has a safe OpenRouter replacement OR needs the
self-hosted Granite Guardian (operator/GPU-gated).

WHY (run-11 root cause, outputs/audits/I-run11-002/claude_diagnosis.md §L1): the locked Sentinel
model is the task-trained `granite-guardian-4.1-8b` (yes=risk polarity), which is NOT on
OpenRouter. The benchmark route substitutes the GENERAL `ibm-granite/granite-4.1-8b`, which
returned a uniform `<score>yes</score>` (UNGROUNDED) on ALL 54 full-path claims in run 11 —
including a verbatim-quoted (genuinely grounded) claim — so every claim wrongly fail-closed.

FIDELITY (advisor directive #1): for the CURRENT inverted combo this script REUSES the production
request builder (`build_sentinel_request`), the production message normalizer
(`_normalize_messages`), and the production score parser (`parse_sentinel_score`). It POSTs the
EXACT body shape `OpenRouterRoleTransport.complete` sends for the Sentinel role (no reasoning, no
provider block, top-level `documents` dropped, small `max_tokens`, same OpenRouter headers). The
only thing varied is `body["model"]`. So the baseline (ibm-granite + inverted guardian block) row
is provably identical to what run 11 did.

FLIP-PROOF PASS CRITERION (advisor directive #3; CLAUDE.md §-1.1 false-accept guard): a combo
PASSES iff it returns DIFFERENT, CORRECT verdicts — A (grounded fixture) -> GROUNDED and B
(fabricated fixture) -> UNGROUNDED. A uniform responder (same token on both) can NEVER be rescued
by a polarity flip: if it says the same thing to A and B, one reading fails A and the other
false-accepts B. The table records BOTH fixtures' raw outputs so the false-accept is visible, not
hidden.

SPEND: tiny. Single call per (model, prompt, fixture) cell, temperature=0, low max_tokens.
n=1/cell is a PROBE, not a characterization — but granite's uniform-yes is already corroborated by
54 real run-11 calls, so n=1 reproducing it suffices (see the deliverable's honest_note).

LAW VI: the OpenRouter key is read from the environment (`OPENROUTER_API_KEY`) via os.getenv —
NEVER hardcoded. If absent, the script FAILS LOUD (LAW II).

Usage:
    python scripts/diagnostics/sentinel_groundedness_probe.py
    # writes outputs/audits/I-run11-002/l1_groundedness_probe.md and prints the table to stdout.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

# Production code reused for the inverted (current) combo — provable call-shape fidelity.
from src.polaris_graph.roles.role_transport import EvidenceDocument
from src.polaris_graph.roles.sentinel_adapter import (
    _GUARDIAN_BLOCK,
    build_sentinel_request,
)
from src.polaris_graph.roles.openai_compatible_transport import _normalize_messages
from src.polaris_graph.roles.sentinel_contract import (
    SentinelVerdict,
    parse_sentinel_score,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EVIDENCE_POOL = _REPO_ROOT / "outputs" / "q1_run11" / "evidence_pool.json"
_OUTPUT_MD = _REPO_ROOT / "outputs" / "audits" / "I-run11-002" / "l1_groundedness_probe.md"

# The autor evidence id whose verbatim quote is the GROUNDED fixture (traced claim 00-000-679379fc).
_AUTOR_EVIDENCE_ID = "autor_why_still_jobs"
_AUTOR_DOC_ID = "autor_why_still_jobs"

# The verbatim polarization sentence is a SUBSTRING of the autor direct_quote — we slice it out of
# the loaded document (rather than re-typing smart-quoted text) so fixture A's claim is provably a
# literal verbatim quote of the document, matching the run-11 traced <co> span.
_POLARIZATION_ANCHOR_START = "one noticeable change has been"
_POLARIZATION_ANCHOR_END = "not to those in the middle"

# Fixture B: an ON-TOPIC (labor/AI/wages) but FABRICATED specific NOT present in the autor document.
# On-topic-but-false tests GROUNDEDNESS (not topical relevance) — the harder, correct test.
_FABRICATED_CLAIM = (
    "AI raised US median wages by exactly 14 percent in 2024."
)

# OpenRouter call shape (mirrors openrouter_role_transport for the Sentinel/non-reasoning path).
_OPENROUTER_BASE = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
_CHAT_PATH = "/chat/completions"
_SENTINEL_MAX_TOKENS = int(os.getenv("PG_SENTINEL_MAX_TOKENS", "256"))
# Non-inverted prompt may emit a word or two of preamble; give it a little room but stay tiny.
_NONINVERTED_MAX_TOKENS = 64
_TIMEOUT_SECONDS = int(os.getenv("PG_LLM_TIMEOUT_SECONDS", "90"))

# Candidate models — all CONFIRMED present on the live OpenRouter /api/v1/models endpoint
# (queried 2026-06-03). Family note records 4-distinct-family-invariant collisions: the active
# benchmark lineup families are deepseek (Writer), z-ai (Mirror), qwen (Judge), ibm-granite
# (Sentinel). A replacement sharing one of those families would break the all-distinct check.
_CANDIDATE_MODELS = [
    # (slug, family, collision_note)
    ("ibm-granite/granite-4.1-8b", "ibm-granite", "CURRENT Sentinel benchmark slug (the role itself)"),
    ("meta-llama/llama-3.3-70b-instruct", "meta-llama", "NEW family — no collision"),
    ("mistralai/mistral-large-2512", "mistralai", "NEW family — no collision"),
    ("qwen/qwen-2.5-72b-instruct", "qwen", "COLLIDES with Judge family (qwen) — self-verify risk"),
]

# Non-inverted groundedness prompt — direct, robust to a capable general instruct model. Asks for
# a single word GROUNDED or UNGROUNDED. Documents are rendered model-visible by _normalize_messages
# (leading evidence message), exactly as on the production Sentinel path.
_NONINVERTED_BLOCK = (
    "You are a strict groundedness checker. Decide whether the assistant's CLAIM is fully "
    "supported by (entailed by) the EVIDENCE DOCUMENTS shown above. A claim is GROUNDED only if "
    "every factual assertion in it — including any number, percentage, or named entity — is "
    "directly stated in or directly entailed by the documents. If the claim adds any fact, number, "
    "or detail not present in the documents, it is UNGROUNDED.\n"
    "Answer with EXACTLY one word: GROUNDED or UNGROUNDED. Output only that single word."
)

PROMPTS = {
    "inverted_guardian": _GUARDIAN_BLOCK,        # production current prompt (yes=NOT grounded)
    "noninverted_direct": _NONINVERTED_BLOCK,    # clear non-inverted GROUNDED/UNGROUNDED prompt
}


def _read_key() -> str:
    """OpenRouter API key from env (LAW VI). Fail loud if absent (LAW II)."""
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        # Try a one-shot .env load (the repo convention) WITHOUT a third-party dep.
        env_path = _REPO_ROOT / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("OPENROUTER_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not key:
        sys.exit(
            "FATAL (LAW II): OPENROUTER_API_KEY is not set (env or .env). "
            "This probe makes live OpenRouter calls and cannot run without it."
        )
    return key


def _load_autor_document() -> str:
    """Load the verbatim autor `direct_quote` from the run-11 evidence pool (the GROUNDED doc)."""
    pool = json.loads(_EVIDENCE_POOL.read_text(encoding="utf-8"))
    for entry in pool:
        if entry.get("evidence_id") == _AUTOR_EVIDENCE_ID:
            doc = entry.get("direct_quote", "")
            if not doc:
                sys.exit(f"FATAL: {_AUTOR_EVIDENCE_ID} has empty direct_quote in {_EVIDENCE_POOL}")
            return doc
    sys.exit(f"FATAL: {_AUTOR_EVIDENCE_ID} not found in {_EVIDENCE_POOL}")


def _verbatim_polarization_claim(document: str) -> str:
    """Slice the verbatim polarization sentence out of the loaded autor document.

    Guarantees fixture A's claim is a LITERAL substring of the document (a true verbatim quote),
    avoiding any smart-quote transcription error. Matches the run-11 traced <co> span.
    """
    start = document.find(_POLARIZATION_ANCHOR_START)
    end = document.find(_POLARIZATION_ANCHOR_END)
    if start == -1 or end == -1:
        sys.exit(
            "FATAL: polarization anchors not found in the autor document; the fixture cannot be "
            "verified as a verbatim quote."
        )
    end += len(_POLARIZATION_ANCHOR_END)
    return document[start:end].strip()


def _build_sentinel_body(model_slug: str, prompt_block: str, claim: str, document: str,
                         max_tokens: int) -> dict:
    """Build the EXACT Sentinel-path OpenRouter body for one (model, prompt) cell.

    For the inverted_guardian prompt this reuses the production `build_sentinel_request` +
    `_normalize_messages` so the messages are byte-identical to run 11. For the non-inverted prompt
    we assemble the SAME message layout (leading evidence message via _normalize_messages, then
    assistant=claim, then the prompt as the final user turn) but with the non-inverted instruction.
    The body matches openrouter_role_transport's Sentinel branch: no `reasoning`, no `provider`,
    top-level `documents` dropped, explicit small `max_tokens`.
    """
    evidence_docs = [EvidenceDocument(doc_id=_AUTOR_DOC_ID, text=document)]
    if prompt_block is _GUARDIAN_BLOCK:
        # Production path, byte-for-byte: build_sentinel_request -> _normalize_messages.
        request = build_sentinel_request(claim, evidence_docs, model_slug=model_slug)
        messages = _normalize_messages(request)
    else:
        # Non-inverted: same evidence-first layout, assistant=claim, prompt as the final user turn.
        # Reuse _normalize_messages to render the leading evidence message identically, by handing
        # it a request whose messages carry [assistant=claim, user=non_inverted_block].
        request = build_sentinel_request(claim, evidence_docs, model_slug=model_slug)
        request.messages = [
            {"role": "assistant", "content": claim},
            {"role": "user", "content": prompt_block},
        ]
        messages = _normalize_messages(request)
    # openrouter_role_transport drops the top-level `documents` key for the Sentinel path; we never
    # add it (the evidence is already model-visible in the leading message). No reasoning/provider.
    return {
        "model": model_slug,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0,
    }


def _post(client: httpx.Client, key: str, body: dict) -> tuple[str, str | None]:
    """POST one Sentinel-path completion. Returns (raw_text, error). Never raises for a call fault —
    a transport/HTTP/parse fault is recorded as the cell's error so the table is complete."""
    url = f"{_OPENROUTER_BASE}{_CHAT_PATH}"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://polaris-research.ai",
        "X-Title": "polaris graph",
    }
    try:
        resp = client.post(url, json=body, headers=headers, timeout=_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        return "", f"transport_error: {exc}"
    if resp.status_code != httpx.codes.OK:
        return "", f"http_{resp.status_code}: {resp.text[:200]}"
    try:
        raw = resp.json()
    except (json.JSONDecodeError, ValueError) as exc:
        return "", f"non_json: {exc}"
    choices = raw.get("choices")
    if not choices or not isinstance(choices[0], dict):
        return "", f"no_choices: {json.dumps(raw)[:200]}"
    message = choices[0].get("message")
    if not isinstance(message, dict):
        return "", "no_message"
    content = message.get("content")
    if content is None:
        # Some reasoning models put the answer in `reasoning`; record it so the cell isn't blank.
        content = message.get("reasoning")
    return (content or "").strip(), None


def _verdict_inverted(raw_text: str) -> tuple[str, str]:
    """Parse the inverted_guardian output via the PRODUCTION parser. Returns (verdict, detail).

    parse_sentinel_score fail-closes (UNGROUNDED, parsed_ok=False) on anything that is not exactly
    one `<score>yes|no</score>` element — faithful to production. We report the verdict AND whether
    it parsed cleanly, because a fail-closed UNGROUNDED on grounded fixture A is itself the L1 bug.
    """
    result = parse_sentinel_score(raw_text)
    verdict = "GROUNDED" if result.verdict == SentinelVerdict.GROUNDED else "UNGROUNDED"
    detail = "parsed_ok" if result.parsed_ok else "FAIL-CLOSED (unparseable)"
    return verdict, detail


def _verdict_noninverted(raw_text: str) -> tuple[str, str]:
    """Parse the non-inverted output by case-insensitive keyword. Returns (verdict, detail).

    Substring/keyword parse so a little preamble around the word doesn't break it. UNGROUNDED is
    checked FIRST (it contains 'grounded' as a substring, so a naive 'grounded in text' check would
    misfire). Anything that resolves to neither is FAIL-CLOSED to UNGROUNDED (never silently
    grounded) so an unparseable output cannot false-accept.
    """
    low = raw_text.lower()
    has_ungrounded = "ungrounded" in low or "not grounded" in low or "not fully" in low
    has_grounded = "grounded" in low
    if has_ungrounded:
        return "UNGROUNDED", "keyword:ungrounded"
    if has_grounded:
        return "GROUNDED", "keyword:grounded"
    return "UNGROUNDED", "FAIL-CLOSED (no keyword)"


def main() -> int:
    key = _read_key()
    document = _load_autor_document()
    grounded_claim = _verbatim_polarization_claim(document)

    fixtures = {
        "A_grounded": (grounded_claim, "GROUNDED"),       # verbatim quote of the document
        "B_ungrounded": (_FABRICATED_CLAIM, "UNGROUNDED"),  # on-topic fabricated specific
    }

    rows = []  # one row per (model, prompt) with A/B raw + verdict + discriminates?
    calls = 0
    with httpx.Client() as client:
        for model_slug, family, collision in _CANDIDATE_MODELS:
            for prompt_name, prompt_block in PROMPTS.items():
                max_tokens = (
                    _SENTINEL_MAX_TOKENS if prompt_block is _GUARDIAN_BLOCK
                    else _NONINVERTED_MAX_TOKENS
                )
                cell = {
                    "model": model_slug,
                    "family": family,
                    "collision": collision,
                    "prompt": prompt_name,
                }
                for fx_name, (claim, expected) in fixtures.items():
                    body = _build_sentinel_body(
                        model_slug, prompt_block, claim, document, max_tokens
                    )
                    raw_text, err = _post(client, key, body)
                    calls += 1
                    if err is not None:
                        cell[fx_name] = {
                            "raw": "", "verdict": "ERROR", "detail": err,
                            "correct": False, "expected": expected,
                        }
                        print(f"[{model_slug} | {prompt_name} | {fx_name}] ERROR: {err}")
                        continue
                    if prompt_block is _GUARDIAN_BLOCK:
                        verdict, detail = _verdict_inverted(raw_text)
                    else:
                        verdict, detail = _verdict_noninverted(raw_text)
                    correct = verdict == expected
                    cell[fx_name] = {
                        "raw": raw_text, "verdict": verdict, "detail": detail,
                        "correct": correct, "expected": expected,
                    }
                    print(
                        f"[{model_slug} | {prompt_name} | {fx_name}] "
                        f"raw={raw_text!r} -> {verdict} ({detail}) "
                        f"expected={expected} {'OK' if correct else 'WRONG'}"
                    )
                a = cell["A_grounded"]
                b = cell["B_ungrounded"]
                # PASS = different+correct on BOTH (advisor #3 flip-proof criterion).
                cell["discriminates"] = bool(a["correct"] and b["correct"])
                rows.append(cell)

    _write_markdown(rows, grounded_claim, calls)
    print(f"\nWrote {_OUTPUT_MD} ({calls} live calls).")
    return 0


def _write_markdown(rows: list[dict], grounded_claim: str, calls: int) -> None:
    """Render the deliverable table + recommendation. Honest: if nothing discriminates, say so."""
    discriminators = [r for r in rows if r["discriminates"]]
    # The non-inverted prompt is the ROBUST formulation (the inverted Guardian block is fragile for
    # general non-Guardian models — see the granite row). Prefer non-inverted discriminators, and
    # among them a NON-colliding family (preserves the 4-distinct-family invariant, CLAUDE.md §9.1).
    noninverted = [r for r in discriminators if r["prompt"] == "noninverted_direct"]
    safe = [
        r for r in (noninverted or discriminators)
        if "no collision" in r["collision"].lower()
    ]
    colliding = [r for r in (noninverted or discriminators) if r not in safe]

    lines: list[str] = []
    lines.append("# I-run11-002 L1 — Sentinel groundedness DISCRIMINATION probe (OpenRouter)")
    lines.append("")
    lines.append(
        "EMPIRICAL probe. NO production wiring changed. Tests whether any (model, prompt) combo "
        "on OpenRouter can correctly discriminate a genuinely-grounded claim (A) from a "
        "fabricated, ungrounded claim (B) against the SAME autor document. "
        f"Total live calls: {calls} (n=1 per cell, temperature=0)."
    )
    lines.append("")
    lines.append("## Fixtures")
    lines.append("")
    lines.append(f"- **Document** (both fixtures): the verbatim `{_AUTOR_DOC_ID}` `direct_quote` "
                 "from `outputs/q1_run11/evidence_pool.json`.")
    lines.append(f"- **A (GROUNDED, expect GROUNDED)** — claim = verbatim substring of the "
                 f"document (the run-11 traced `<co>` span):")
    lines.append(f"  > {grounded_claim}")
    lines.append(f"- **B (UNGROUNDED, expect UNGROUNDED)** — on-topic but FABRICATED specific NOT "
                 f"in the document:")
    lines.append(f"  > {_FABRICATED_CLAIM}")
    lines.append("")
    lines.append("## PASS criterion (flip-proof, CLAUDE.md §-1.1)")
    lines.append("")
    lines.append(
        "A combo **discriminates (PASS)** iff it returns DIFFERENT, CORRECT verdicts: "
        "A -> GROUNDED **and** B -> UNGROUNDED. A uniform responder (same verdict on A and B) "
        "can NEVER be rescued by a polarity flip: if it says the same on both, one reading fails "
        "A and the other false-accepts B. The B column below shows the raw output so any "
        "false-accept is visible, not hidden. A polarity flip is therefore NOT a valid fix."
    )
    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append("| Model | Prompt | A raw -> verdict (expect GROUNDED) | B raw -> verdict (expect UNGROUNDED) | Discriminates? | Family / collision |")
    lines.append("|---|---|---|---|---|---|")
    for r in rows:
        a = r["A_grounded"]
        b = r["B_ungrounded"]
        a_cell = f"`{_clip(a['raw'])}` -> {a['verdict']} {'OK' if a['correct'] else 'WRONG'} ({a['detail']})"
        b_cell = f"`{_clip(b['raw'])}` -> {b['verdict']} {'OK' if b['correct'] else 'WRONG'} ({b['detail']})"
        disc = "**YES**" if r["discriminates"] else "no"
        lines.append(
            f"| `{r['model']}` | {r['prompt']} | {a_cell} | {b_cell} | {disc} | "
            f"{r['family']} — {r['collision']} |"
        )
    lines.append("")
    lines.append("## RECOMMENDATION")
    lines.append("")
    if not discriminators:
        lines.append(
            "**none discriminate on OpenRouter -> L1 needs self-hosted Guardian "
            "(operator/GPU-gated).** No (model, prompt) combo returned A->GROUNDED AND "
            "B->UNGROUNDED. A polarity flip is explicitly REJECTED: every non-discriminating combo "
            "is uniform (or wrong on A), so flipping the mapping would false-accept fabricated "
            "claims (B) — clinically lethal per §-1.1. The safe path is the locked self-hosted "
            "`granite-guardian-4.1-8b` (yes=risk polarity), which is operator/GPU-gated."
        )
    else:
        best = (safe or colliding)[0]
        lines.append(
            f"**Safe replacement candidate: `{best['model']}` with the `{best['prompt']}` "
            f"prompt** — it returned A->GROUNDED AND B->UNGROUNDED (true discrimination, not a "
            f"polarity artifact)."
        )
        if safe:
            lines.append("")
            lines.append(
                f"Family `{best['family']}` does NOT collide with the active lineup "
                "(deepseek/z-ai/qwen/ibm-granite), so promoting it preserves the 4-distinct-family "
                "invariant (CLAUDE.md §9.1)."
            )
        if colliding and not safe:
            lines.append("")
            lines.append(
                "HONEST CAVEAT: the only discriminator(s) COLLIDE with an existing role family — "
                "promoting one would break the 4-distinct-family self-verify invariant "
                "(CLAUDE.md §9.1). A family-distinct discriminator was NOT found; treat this as "
                "leaning toward the self-hosted Guardian unless a non-colliding model is added."
            )
        lines.append("")
        lines.append(
            "Note: this is a PROBE (n=1/cell). Before any production swap, re-run the winning "
            "combo across more fixtures (multiple grounded + multiple fabricated, incl. "
            "qualitative-negation per `feedback_qualitative_negation_escapes_regex`) and confirm "
            "the non-inverted contract polarity in `sentinel_contract.py` is wired to match."
        )
    lines.append("")
    lines.append("## Honesty notes")
    lines.append("")
    lines.append(
        "- n=1 per cell — a probe, not a characterization. Granite's uniform behavior is "
        "corroborated by 54 real run-11 Sentinel calls (all `<score>yes</score>`), so n=1 "
        "reproducing it suffices for the baseline."
    )
    lines.append(
        "- The inverted_guardian rows reuse the PRODUCTION `build_sentinel_request` + "
        "`_normalize_messages` + `parse_sentinel_score`, so the baseline row is byte-identical "
        "to what run 11 sent/parsed."
    )
    lines.append(
        "- Fixture B is on-topic-but-fabricated (tests groundedness, not topical relevance). An "
        "off-topic B would be a misleadingly easy PASS."
    )
    lines.append(
        "- A polarity flip is NEVER recommended: it false-accepts fabricated claims, which §-1.1 "
        "calls clinically lethal."
    )
    _OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    _OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _clip(text: str, limit: int = 60) -> str:
    """Single-line, table-safe clip of a raw output for the markdown cell."""
    one = " ".join(text.split())
    return (one[:limit] + "…") if len(one) > limit else one


if __name__ == "__main__":
    raise SystemExit(main())
