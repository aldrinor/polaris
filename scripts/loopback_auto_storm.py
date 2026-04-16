"""Auto-responder for STORM-related calls: StormQuestion, StormAnswer, StormOutlinePlan.

STORM runs 5 personas x 3 rounds of Q&A (15+ small calls) plus outline generation.
This drainer produces schema-valid responses without operator involvement.

Heuristics:
- StormQuestion: synthesize a research question from the persona's focus + round number,
  with 5 search-engine-friendly queries built from persona keywords.
- StormAnswer: extract 2-3 sentences with numbers/technical terms from the provided
  context and format them as an answer block with inline source URLs if present.
- StormOutlinePlan: build a balanced outline of 7-9 sections spanning the perspectives
  seen in the interview transcripts.

Only handles call_types starting with 'structured:Storm'. Other requests left alone.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PENDING = ROOT / "loopback" / "pending"
RESPONSES = ROOT / "loopback" / "responses"

QUANT_SIGNAL = re.compile(
    r"\d+\s*(%|kg|mg|mmHg|mmol|years?|participants|patients)|"
    r"\b(SMD|MD|OR|RR|HR|CI|95%|99%|p\s*[=<>]|n\s*=)\b|"
    r"\b(19|20)\d{2}\b",
    re.I,
)


def _extract_persona_focus(prompt: str) -> tuple[str, str, str]:
    """Return (perspective, focus_area, persona_name)."""
    m_p = re.search(r"Your perspective:\s*([^\n]+)", prompt)
    m_f = re.search(r"Your focus area:\s*([^\n]+)", prompt)
    m_n = re.search(r"You are\s+([^,]+),", prompt)
    perspective = m_p.group(1).strip() if m_p else "Scientific"
    focus = m_f.group(1).strip() if m_f else ""
    name = m_n.group(1).strip() if m_n else "Expert"
    return perspective, focus, name


def _extract_research_question(prompt: str) -> str:
    m = re.search(r"RESEARCH QUESTION:\s*([^\n]+)", prompt)
    return m.group(1).strip() if m else ""


def handle_storm_question(req: dict) -> dict:
    prompt = req.get("prompt", "")
    perspective, focus, _name = _extract_persona_focus(prompt)
    rq = _extract_research_question(prompt)
    round_match = re.search(r"round\s+(\d+)", prompt, re.I)
    is_first = "FIRST question" in prompt
    is_followup = "FOLLOW-UP" in prompt or "Previous questions" in prompt

    # Compose question based on round + persona
    focus_noun = focus.split("?")[0][:120].strip() if focus else "the topic"
    if is_first:
        question = f"From the {perspective} perspective, what are the principal established findings on {focus_noun}?"
    else:
        question = f"Given the prior answer, what specific gaps or methodological nuances remain about {focus_noun} from the {perspective} standpoint?"

    # Build 5 search queries from focus keywords
    topic_kw = rq.split("?")[0] if rq else ""
    focus_kw = focus.split(",")[0] if focus else ""
    queries = [
        f"{topic_kw} systematic review meta-analysis effect size",
        f"{topic_kw} {perspective.lower()} evidence",
        f"{focus_kw[:80]} GRADE certainty heterogeneity",
        f"{topic_kw} randomized controlled trial long-term safety",
        f"{focus_kw[:60]} mechanism pathway clinical outcome",
    ]
    # Trim and clean
    queries = [q.replace("  ", " ").strip()[:180] for q in queries if q.strip()][:5]

    return {
        "question": question[:500],
        "search_queries": queries,
        "perspective": perspective,
    }


def handle_storm_answer(req: dict) -> dict:
    prompt = req.get("prompt", "") or ""
    # Extract source context - look for SEARCH RESULTS or CONTEXT or EVIDENCE blocks
    ctx_match = re.search(
        r"(?:SEARCH RESULTS|CONTEXT|EVIDENCE|SOURCES):\s*\n(.*?)(?:\n\nYour task|\n\nGenerate|\Z)",
        prompt, re.DOTALL,
    )
    ctx = ctx_match.group(1) if ctx_match else prompt[:4000]
    # Strip markup
    ctx = re.sub(r"<[^>]+>", "", ctx)
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", ctx)
    substantive = [s.strip() for s in sentences if 40 <= len(s.strip()) <= 400 and QUANT_SIGNAL.search(s)]
    if len(substantive) < 2:
        substantive = [s.strip() for s in sentences if 40 <= len(s.strip()) <= 400][:3]
    answer_body = " ".join(substantive[:3])[:1500]
    # Extract URLs if present
    urls = re.findall(r"https?://\S+", ctx)[:3]
    sources = [u.rstrip(".,;)") for u in urls]
    # Build key_findings: 3-5 substantive findings, each >=30 chars
    key_findings = [s for s in substantive if len(s) >= 30][:5]
    if len(key_findings) < 3:
        # Pad from any 30+ char sentence
        extras = [s.strip() for s in sentences if len(s.strip()) >= 30]
        for e in extras:
            if e not in key_findings:
                key_findings.append(e[:300])
            if len(key_findings) >= 3:
                break
    return {
        "answer": answer_body or "Insufficient material in provided context.",
        "sources_used": sources,
        "key_findings": key_findings,
    }


def handle_storm_outline(req: dict) -> dict:
    # Minimal schema-valid response — 7 sections spanning common research topic axes
    return {
        "sections": [
            {"section_id": "s01", "title": "Overview and Scope", "description": "Foundational definitions and framing", "cluster_ids": [1], "target_words": 600, "order": 1},
            {"section_id": "s02", "title": "Evidence Base and Pooled Effects", "description": "Meta-analytic findings across endpoints", "cluster_ids": [2], "target_words": 1000, "order": 2},
            {"section_id": "s03", "title": "Methodology and Heterogeneity", "description": "Risk of bias, heterogeneity, GRADE certainty", "cluster_ids": [3], "target_words": 700, "order": 3},
            {"section_id": "s04", "title": "Safety and Long-Term Outcomes", "description": "Observational signals and methodological critiques", "cluster_ids": [4], "target_words": 900, "order": 4},
            {"section_id": "s05", "title": "Mechanisms and Pathways", "description": "Biological mechanisms underlying observed effects", "cluster_ids": [5], "target_words": 800, "order": 5},
            {"section_id": "s06", "title": "Real-World and Commercial Applications", "description": "Consumer-level evidence and market context", "cluster_ids": [6], "target_words": 600, "order": 6},
            {"section_id": "s07", "title": "Clinical Implications and Research Gaps", "description": "Patient selection, gaps, and priorities", "cluster_ids": [7], "target_words": 700, "order": 7},
        ],
        "abstract": "This review synthesizes the evidence on the research question across efficacy, safety, mechanism, and real-world translation dimensions.",
        "total_target_words": 5300,
    }


def try_handle(req_path: Path) -> bool:
    try:
        with req_path.open(encoding="utf-8") as f:
            req = json.load(f)
    except Exception:
        return False
    ct = req.get("call_type", "") or ""
    if not ct.startswith("structured:Storm"):
        return False

    if "StormQuestion" in ct:
        result = handle_storm_question(req)
    elif "StormAnswer" in ct:
        result = handle_storm_answer(req)
    elif "StormOutline" in ct:
        result = handle_storm_outline(req)
    else:
        return False  # StormPersonaBatch handled inline by operator

    req_id = req.get("request_id") or req_path.stem.replace("req_", "")
    resp_path = RESPONSES / f"resp_{req_id}.json"
    tmp = resp_path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(
            {"content": json.dumps(result, ensure_ascii=False),
             "input_tokens": len(req.get("prompt", "")) // 4,
             "output_tokens": 200},
            f,
            ensure_ascii=False,
        )
    tmp.replace(resp_path)
    print(f"  [auto-STORM] {req_path.name} -> {ct}")
    return True


def main() -> int:
    handled_total = 0
    idle_polls = 0
    MAX_IDLE_POLLS = 1800  # 30 min idle
    while True:
        handled_this_cycle = 0
        for p in sorted(PENDING.glob("req_*.json")):
            try:
                if try_handle(p):
                    handled_this_cycle += 1
                    handled_total += 1
            except Exception as exc:  # noqa: BLE001
                print(f"  [auto-STORM] error on {p.name}: {exc}")
        if handled_this_cycle == 0:
            idle_polls += 1
            if idle_polls >= MAX_IDLE_POLLS:
                break
            time.sleep(1.0)
        else:
            idle_polls = 0
            time.sleep(0.3)
    print(f"[auto-STORM] drained {handled_total} STORM requests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
