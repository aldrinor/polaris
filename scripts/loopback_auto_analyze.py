"""Auto-responder for SourceAnalysisBatch requests in the loopback queue.

Produces minimal but schema-valid responses preserving URL fidelity (critical for
the D3 url_to_ref test). Each source gets 2-3 atomic facts built from short
quoted substrings of the fetched content, with realistic tier assignments.

Thin sources (content < 500 chars of real text, dominated by captcha / paywall
markers) get zero atomic facts and low relevance/quality scores.

Handles only call_type == 'structured:SourceAnalysisBatch' prompts that begin
with 'Research question:' and contain 'Analyze the following'. Other requests
are left for the operator.
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

PAYWALL_PATTERNS = re.compile(
    r"INSUFFICIENT_CONTENT|captcha|403 (Forbidden|:)|Cloudflare|Performing security|"
    r"Database connection failed|Just a moment|Sign in|security verification",
    re.I,
)


def extract_short_quote(text: str, start: int = 0, max_len: int = 200) -> str:
    """Return a ~max_len-char substring starting near `start` that is a reasonable fact candidate."""
    slice_ = text[start : start + max_len + 300]
    # Trim to a sentence boundary if possible
    m = re.search(r"\.(?:\s+[A-Z]|\s+$|$)", slice_[:max_len + 200])
    if m:
        return slice_[: m.end()].strip()
    return slice_[:max_len].strip()


def parse_sources(prompt: str) -> list[dict]:
    """Split prompt into per-source blocks."""
    parts = re.split(r"^Source URL:\s*", prompt, flags=re.MULTILINE)
    sources = []
    for part in parts[1:]:
        m_url = re.match(r"(\S+)", part)
        if not m_url:
            continue
        url = m_url.group(1).strip()
        m_title = re.search(r"^Source title:\s*(.+)", part, re.MULTILINE)
        title = m_title.group(1).strip() if m_title else ""
        m_type = re.search(r"^Source type:\s*(\S+)", part, re.MULTILINE)
        stype = m_type.group(1).strip() if m_type else "web"
        m_content = re.search(r"^Content:\s*\n(.*?)(?:\n---\s*|\nSource URL:|\Z)", part, re.DOTALL | re.MULTILINE)
        content = m_content.group(1).strip() if m_content else ""
        sources.append({"url": url, "title": title, "type": stype, "content": content})
    return sources


def build_analysis(src: dict) -> dict:
    content = src["content"] or ""
    # Detect shell/paywall
    real_content = re.sub(r"<[^>]+>", "", content)  # strip html
    is_shell = len(real_content) < 500 or PAYWALL_PATTERNS.search(real_content[:2000]) is not None
    source_type_map = {
        "academic": "journal_article",
        "web": "web",
        "news": "news",
        "other": "other",
    }
    src_type = source_type_map.get(src["type"], "web")

    if is_shell:
        return {
            "source_url": src["url"],
            "source_title": src["title"] or src["url"][:80],
            "source_type": "other",
            "source_quality": 0.0,
            "overall_relevance": 0.0,
            "year": 0,
            "authors": [],
            "venue": "",
            "doi": "",
            "atomic_facts": [],
            "evidence_summary": "INSUFFICIENT_CONTENT: paywall/shell/captcha.",
        }

    # Topic-agnostic fact extraction: any sentence with quantitative/technical substance.
    # FIX-HALLUC-3: Broadened from IF/MetS-only to work across all 10 loopback topics
    # (materials, economics, climate, AI/ML, law, chemistry, biology, public health, engineering).
    facts = []
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", real_content[:12000])
    # Quantitative signals: numbers, percentages, statistical markers, citation markers
    quantitative = re.compile(
        r"\d+\s*(%|kg|mg|mm|cm|km|nm|ppm|ppb|GHz|MHz|Hz|GPa|MPa|kPa|Pa|°C|K|J|eV|keV|MeV|"
        r"mol|mmol|μmol|dL|mL|L|g|mcg|IU|bp|kb|Mb|Gb|USD|EUR|years?|months?|weeks?|days?|hours?|"
        r"participants|patients|adults|subjects|cases|events|sites|samples|measurements)|"
        r"\b(SMD|MD|OR|RR|HR|CI|SD|SE|SEM|95%|99%|p\s*[=<>]|n\s*=|r\s*=|β\s*=|R²|R\^2|ICC|AUC|"
        r"RMSE|MAE|MSE|F1|IC50|EC50|Kd|Km|pH)\b|"
        r"\b(19|20)\d{2}\b|"  # years (1900s-2000s)
        r"\b\d+\.\d+\b",  # decimals
        re.I,
    )
    # Technical-entity signals: named entities, technical terminology
    technical = re.compile(
        r"\b(meta-analysis|systematic review|RCT|randomized|cohort|longitudinal|cross-sectional|"
        r"catalyst|Faradaic|electrolyte|adhesion|fatigue|yield|tensile|modulus|crystalline|"
        r"permafrost|carbon|emission|RCP|IPCC|scenario|mitigation|adaptation|"
        r"RLHF|alignment|transformer|attention|embedding|fine-tuning|"
        r"regulation|directive|article|clause|compliance|obligation|"
        r"tau|prion|neuron|synaptic|propagation|aggregation|"
        r"obesity|prevalence|intervention|LMIC|income|country|"
        r"fiber optic|sensor|bridge|steel|corrosion|inspection|monitoring|"
        r"Regulation \d+|Directive \d+|ISO \d+|ASTM|IEC|IEEE \d+)\b",
        re.I,
    )
    relevance_base = 0.55
    confidence_base = 0.88
    for s in sentences:
        s = s.strip()
        if not s or len(s) < 40 or len(s) > 400:
            continue
        has_quant = bool(quantitative.search(s))
        has_tech = bool(technical.search(s))
        if has_quant or has_tech:
            q = s[:250]
            statement = q if len(q) < 140 else q[:140].rsplit(" ", 1)[0] + "..."
            facts.append({
                "statement": statement,
                "direct_quote": q,
                "fact_category": "statistic" if has_quant else "causal_link",
                "relevance_score": relevance_base + (0.15 if has_quant and has_tech else 0.0),
                "confidence": confidence_base,
                "perspective": "Scientific",
                "entities": [],
            })
        if len(facts) >= 3:
            break

    if not facts:
        # Fall back to first meaningful sentence
        for s in sentences:
            s = s.strip()
            if 40 <= len(s) <= 300:
                facts.append({
                    "statement": s[:140] + ("..." if len(s) > 140 else ""),
                    "direct_quote": s[:250],
                    "fact_category": "named_entity",
                    "relevance_score": 0.4,
                    "confidence": 0.8,
                    "perspective": "Scientific",
                    "entities": [],
                })
                break

    return {
        "source_url": src["url"],
        "source_title": src["title"] or src["url"][:80],
        "source_type": "journal_article" if src_type == "academic" else src_type,
        "source_quality": 0.7,
        "overall_relevance": 0.65,
        "year": 0,
        "authors": [],
        "venue": "",
        "doi": "",
        "atomic_facts": facts,
        "evidence_summary": f"Auto-extracted {len(facts)} facts from {src['title'][:60]}.",
    }


def try_handle(req_path: Path) -> bool:
    try:
        with req_path.open(encoding="utf-8") as f:
            req = json.load(f)
    except Exception:
        return False
    if req.get("call_type", "") != "structured:SourceAnalysisBatch":
        return False
    prompt = req.get("prompt", "") or ""
    if "Analyze the following" not in prompt:
        return False
    sources = parse_sources(prompt)
    if not sources:
        return False
    analyses = [build_analysis(s) for s in sources]
    result = {"analyses": analyses}
    req_id = req.get("request_id") or req_path.stem.replace("req_", "")
    resp_path = RESPONSES / f"resp_{req_id}.json"
    tmp = resp_path.with_suffix(".tmp")
    total_facts = sum(len(a["atomic_facts"]) for a in analyses)
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(
            {"content": json.dumps(result, ensure_ascii=False),
             "input_tokens": len(prompt) // 4,
             "output_tokens": total_facts * 60 + 100},
            f,
            ensure_ascii=False,
        )
    tmp.replace(resp_path)
    print(f"  [auto-ANALYZE] {req_path.name} -> {len(analyses)} sources, {total_facts} facts total")
    return True


def main() -> int:
    handled_total = 0
    idle_polls = 0
    MAX_IDLE_POLLS = 1800
    while True:
        handled_this_cycle = 0
        for p in sorted(PENDING.glob("req_*.json")):
            try:
                if try_handle(p):
                    handled_this_cycle += 1
                    handled_total += 1
            except Exception as exc:  # noqa: BLE001
                print(f"  [auto-ANALYZE] error on {p.name}: {exc}")
        if handled_this_cycle == 0:
            idle_polls += 1
            if idle_polls >= MAX_IDLE_POLLS:
                break
            time.sleep(1.0)
        else:
            idle_polls = 0
            time.sleep(0.5)
    print(f"[auto-ANALYZE] drained {handled_total} source-analysis batches")
    return 0


if __name__ == "__main__":
    sys.exit(main())
