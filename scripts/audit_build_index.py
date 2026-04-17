"""Build audit index: [N] -> evidence_ids -> source_url -> direct_quote -> verbatim-in-content.

Output: docs/pg_lb_sa_01_audit_index.json

Each entry:
{
  "ref_num": 1,
  "url": "...",
  "title": "...",
  "year": 2024,
  "doi": "...",
  "source_type": "...",
  "fetched_content_len": N or null,
  "evidence_ids": [...],
  "evidence_records": [
    {
      "evidence_id": "ev_xxx",
      "direct_quote": "...",
      "statement": "...",
      "fact_category": "...",
      "quality_tier": "...",
      "relevance_score": X,
      "nli_score": X,
      "is_faithful": bool,
      "quote_in_content": "VERBATIM|PARAPHRASE|ABSENT",
      "quote_position": int or null,
      "content_length": int or null
    }
  ]
}
"""
from __future__ import annotations
import json
import re
from pathlib import Path


def normalize_text(text: str) -> str:
    """Lowercase, collapse whitespace, strip quotes for fuzzy matching."""
    t = text.lower()
    t = re.sub(r"[\u2018\u2019\u201C\u201D\u2212\u2013\u2014]", lambda m: {
        "\u2018": "'", "\u2019": "'", "\u201C": '"', "\u201D": '"',
        "\u2212": "-", "\u2013": "-", "\u2014": "-"
    }[m.group()], t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def check_quote_in_content(quote: str, content: str) -> tuple[str, int | None]:
    """Return (VERBATIM|PARAPHRASE|ABSENT, position_or_None)."""
    if not quote or not content:
        return ("ABSENT", None)

    # Exact match
    pos = content.find(quote)
    if pos >= 0:
        return ("VERBATIM", pos)

    # Normalized match
    n_quote = normalize_text(quote)
    n_content = normalize_text(content)
    pos = n_content.find(n_quote)
    if pos >= 0:
        return ("VERBATIM_NORMALIZED", pos)

    # Token overlap heuristic for paraphrase
    q_tokens = set(re.findall(r"\w+", n_quote))
    q_tokens -= {"the", "a", "an", "of", "in", "to", "and", "or", "for", "with", "by", "on", "at", "is", "was", "are", "be"}
    if not q_tokens:
        return ("ABSENT", None)

    c_tokens = set(re.findall(r"\w+", n_content))
    overlap = q_tokens & c_tokens
    ratio = len(overlap) / len(q_tokens) if q_tokens else 0

    if ratio >= 0.8:
        return ("PARAPHRASE_HIGH", None)
    elif ratio >= 0.5:
        return ("PARAPHRASE_PARTIAL", None)
    else:
        return ("ABSENT", None)


def main() -> None:
    state_path = Path("outputs/polaris_graph/PG_LB_SA_01.json")
    with state_path.open(encoding="utf-8") as f:
        state = json.load(f)

    bibliography = state.get("bibliography", [])
    evidence = {e["evidence_id"]: e for e in state.get("evidence", [])}
    fc_raw = state.get("fetched_content", [])

    def canon(u: str) -> str:
        u = (u or "").lower().strip()
        u = u.replace("https://www.", "https://").replace("http://www.", "http://")
        u = u.replace("http://", "https://")
        u = u.rstrip("/")
        return u

    if isinstance(fc_raw, list):
        fetched_content = {canon(item.get("url", "")): item.get("content", "") for item in fc_raw}
    else:
        fetched_content = {canon(k): v for k, v in fc_raw.items()}

    index = []
    total_ev = 0
    verbatim = 0
    normalized = 0
    paraphrase_high = 0
    paraphrase_partial = 0
    absent = 0
    content_missing = 0

    for bib in sorted(bibliography, key=lambda b: b.get("ref_num", 0)):
        ref_num = bib.get("ref_num")
        url = bib.get("url", "")
        content = fetched_content.get(canon(url), "")
        content_len = len(content) if content else None

        ev_records = []
        for ev_id in bib.get("evidence_ids", []):
            total_ev += 1
            ev = evidence.get(ev_id)
            if not ev:
                continue
            direct_quote = ev.get("direct_quote", "")

            if not content:
                classification = "CONTENT_MISSING"
                position = None
                content_missing += 1
            else:
                classification, position = check_quote_in_content(direct_quote, content)
                if classification == "VERBATIM":
                    verbatim += 1
                elif classification == "VERBATIM_NORMALIZED":
                    normalized += 1
                elif classification == "PARAPHRASE_HIGH":
                    paraphrase_high += 1
                elif classification == "PARAPHRASE_PARTIAL":
                    paraphrase_partial += 1
                else:
                    absent += 1

            ev_records.append({
                "evidence_id": ev_id,
                "direct_quote": direct_quote,
                "statement": ev.get("statement", ""),
                "fact_category": ev.get("fact_category", ""),
                "quality_tier": ev.get("quality_tier", ""),
                "relevance_score": ev.get("relevance_score"),
                "nli_score": ev.get("nli_score"),
                "is_faithful": ev.get("is_faithful"),
                "perspective": ev.get("perspective", ""),
                "quote_in_content": classification,
                "quote_position": position,
                "content_length": content_len,
            })

        index.append({
            "ref_num": ref_num,
            "url": url,
            "title": bib.get("title", ""),
            "year": bib.get("year"),
            "doi": bib.get("doi", ""),
            "source_type": bib.get("source_type", ""),
            "fetched_content_len": content_len,
            "evidence_count": len(ev_records),
            "evidence_records": ev_records,
        })

    summary = {
        "total_refs": len(index),
        "total_evidence": total_ev,
        "verbatim": verbatim,
        "verbatim_normalized": normalized,
        "paraphrase_high": paraphrase_high,
        "paraphrase_partial": paraphrase_partial,
        "absent": absent,
        "content_missing": content_missing,
        "verbatim_rate": (verbatim + normalized) / total_ev if total_ev else 0,
        "grounded_rate": (verbatim + normalized + paraphrase_high) / total_ev if total_ev else 0,
    }

    output = {"summary": summary, "index": index}
    out_path = Path("docs/pg_lb_sa_01_audit_index.json")
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"[INDEX] Wrote {out_path}")
    print(f"[INDEX] {total_ev} evidence across {len(index)} refs")
    print(f"[INDEX] verbatim={verbatim} ({verbatim/total_ev*100:.1f}%)")
    print(f"[INDEX] verbatim_normalized={normalized} ({normalized/total_ev*100:.1f}%)")
    print(f"[INDEX] paraphrase_high={paraphrase_high} ({paraphrase_high/total_ev*100:.1f}%)")
    print(f"[INDEX] paraphrase_partial={paraphrase_partial} ({paraphrase_partial/total_ev*100:.1f}%)")
    print(f"[INDEX] absent={absent} ({absent/total_ev*100:.1f}%)")
    print(f"[INDEX] content_missing={content_missing} ({content_missing/total_ev*100:.1f}%)")
    print(f"[INDEX] verbatim_rate={summary['verbatim_rate']*100:.1f}%")
    print(f"[INDEX] grounded_rate={summary['grounded_rate']*100:.1f}%")


if __name__ == "__main__":
    main()
