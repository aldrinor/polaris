"""I-wire-014 chrome gold builder (deterministic, reactive rebuild after the prep agent's
stream-idle timeout). Labels each unique-basket representative span (claim_text + each member
direct_quote) from a run's bibliography.json as chrome|content with a chrome_class.

Faithfulness rule: label "chrome" ONLY on a clear page-furniture anchor; when unsure -> content
(never over-drop). This is the gold the chrome benchmark scores candidates against:
  - chrome_removed_rate = chrome spans a candidate strips / total chrome spans
  - content_preserved_rate = content spans a candidate KEEPS / total content spans  (MUST = 1.0)

Usage: python build_chrome_gold.py <bibliography.json> <out.json>
"""
import json
import re
import sys

# Chrome-class anchors (whole-span or inline). Order = priority.
CLASSES = [
    ("journal_html", re.compile(
        r"JEL Classification|^\s*Keywords\b|View All Journal Metrics|Associated Records|"
        r"References\s+Biographies|Cite\s+Cite|Receive email alerts|Markdown Content\s*:|"
        r"URL Source\s*:|Published Time\s*:|\bISSN\b|Web of Science|Crossref\s*:|"
        r"Download to reference manager|Publication usage|Number of Pages\s*:|"
        r"View All Journal Metrics|Information, rights and permissions", re.I)),
    ("affiliation", re.compile(
        r"\baffiliated with\b|Federal Reserve Bank|Principal investigator\s*:|"
        r"Conflict of Interest Disclosure|Corporate Vice-President|"
        r"\bis a trustee\b|Liquidator\)", re.I)),
    ("paywall_preview", re.compile(
        r"Member-only story|What you.?ll learn\s*:|Feature Story\b|Last update [A-Z][a-z]+ \d", re.I)),
    ("cookie_consent", re.compile(
        r"region that you are in|content references language|accept all cookies|"
        r"without these cookies|cookie (?:settings|policy)|enable javascript and cookies", re.I)),
    # intra-word glue: "Governan; ce", "Agricultural Oc; b", "X- Y" hyphen-space split
    ("dehyphenation", re.compile(r"[A-Za-z]{2,};\s+[a-z]{1,3}\b|\b[a-z]{2,}-\s+[a-z]{2,}\b")),
]
# mid-word truncation = lowercase-start (sliced mid-token) OR a known truncation marker
TRUNC_START = re.compile(r"^[a-z]")
TRUNC_MARK = re.compile(r"\busand\b|restricted to s\.|,\s*p\.\[?\d|^\s*hodology|^\s*atch out")


def classify(text: str) -> tuple[str, str]:
    """Return (label, chrome_class). content => ('content','none')."""
    s = (text or "").strip()
    if not s:
        return ("chrome", "empty")
    for name, pat in CLASSES:
        if pat.search(s):
            return ("chrome", name)
    if TRUNC_MARK.search(s) or (TRUNC_START.match(s) and len(s.split()) >= 3):
        return ("chrome", "truncation")
    # content: a real claim — capitalized opener, >= 6 words, no chrome anchor
    if len(s.split()) >= 6 and s[:1].isupper():
        return ("content", "none")
    # short/ambiguous -> content (never over-drop), but flag
    return ("content", "short_ambiguous")


def main() -> None:
    bib = json.load(open(sys.argv[1], encoding="utf-8"))
    out_path = sys.argv[2] if len(sys.argv) > 2 else "chrome_gold.json"
    entries = bib if isinstance(bib, list) else bib.get("bibliography", [])
    seen: set[str] = set()
    items = []
    for b in entries:
        for basket in (b.get("baskets") or []):
            ccid = str(basket.get("claim_cluster_id") or "")
            cands = []
            ct = str(basket.get("claim_text") or "").strip()
            if ct:
                cands.append(("claim_text", ct))
            for m in (basket.get("supporting_members") or []):
                dq = str(m.get("direct_quote") or "").strip()
                if dq:
                    cands.append(("member_quote", dq))
            for origin, text in cands:
                key = text[:120]
                if key in seen:
                    continue
                seen.add(key)
                label, cls = classify(text)
                items.append({"text": text[:600], "label": label, "chrome_class": cls,
                              "origin": origin, "ccid": ccid[:18]})
    n_chrome = sum(1 for i in items if i["label"] == "chrome")
    n_content = len(items) - n_chrome
    cls_counts: dict[str, int] = {}
    for i in items:
        if i["label"] == "chrome":
            cls_counts[i["chrome_class"]] = cls_counts.get(i["chrome_class"], 0) + 1
    json.dump({"items": items, "n_items": len(items), "n_chrome": n_chrome,
               "n_content": n_content, "class_counts": cls_counts},
              open(out_path, "w", encoding="utf-8"), indent=1)
    print(f"chrome_gold: {len(items)} spans -> {n_chrome} chrome / {n_content} content")
    print("class_counts:", cls_counts)
    print("samples chrome:")
    for i in [x for x in items if x["label"] == "chrome"][:8]:
        print(f"  [{i['chrome_class']}] {i['text'][:90]!r}")


if __name__ == "__main__":
    main()
