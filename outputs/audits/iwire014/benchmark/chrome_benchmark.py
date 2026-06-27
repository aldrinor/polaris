"""CHROME scoring harness for the iwire014 benchmark (mirrors dedup_benchmark.py).

Scoring unit = a SINGLE gold span run through the candidate: candidate(text)->cleaned.
  removed   : the candidate strips the span to empty / near-empty
              (cleaned has < REMOVED_WORD_FLOOR alphabetic words OR <= REMOVED_FRAC of
               the original alphabetic-word count survives).
  preserved : a content span survives LARGELY INTACT
              (cleaned retains > PRESERVED_FRAC of the original alphabetic-word count).

Metrics:
  chrome_removed_rate      = (chrome spans the candidate REMOVED) / (total chrome spans)
                             GRADED -- higher is better.
  content_preserved_rate   = (content spans the candidate PRESERVED) / (total content)
                             FAITHFULNESS GATE. MUST equal 1.0. Any value < 1.0 means a
                             real-content span was dropped/gutted -> a faithfulness
                             violation -> AUTO-DISQUALIFY.

FAITHFULNESS LAW (task DNA): dropping a content span = LETHAL = auto-disqualify
regardless of how much chrome was removed. Winner = highest chrome_removed_rate among
candidates whose content_preserved_rate == 1.0.

Dependency: imports the candidate module + (for candidate 1/2/3) src.tools.access_bypass;
candidate 3 also uses symspellpy/wordfreq. Run ON THE VM.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GOLD = os.path.join(HERE, "chrome_gold_augmented.json")

# A content span "survives largely intact" iff it keeps > this fraction of its
# alphabetic words. A chrome span is "removed" iff it keeps <= REMOVED_FRAC of its
# alphabetic words OR drops below REMOVED_WORD_FLOOR absolute words.
PRESERVED_FRAC = 0.60
REMOVED_FRAC = 0.40
REMOVED_WORD_FLOOR = 4


def _alpha_words(s):
    return [w for w in re.findall(r"[^\W\d_]{2,}", s or "", re.UNICODE)]


def _survival_frac(original, cleaned):
    """Fraction of the original's alphabetic words that survive in the cleaned text
    (multiset-aware: counts how many original word-occurrences remain)."""
    from collections import Counter
    o = Counter(w.lower() for w in _alpha_words(original))
    c = Counter(w.lower() for w in _alpha_words(cleaned))
    if not o:
        return 0.0 if _alpha_words(cleaned) else 1.0
    survived = sum(min(o[w], c.get(w, 0)) for w in o)
    return survived / sum(o.values())


def is_removed(original, cleaned):
    if len(_alpha_words(cleaned)) < REMOVED_WORD_FLOOR:
        return True
    return _survival_frac(original, cleaned) <= REMOVED_FRAC


def is_preserved(original, cleaned):
    return _survival_frac(original, cleaned) > PRESERVED_FRAC


def load_gold(path=GOLD):
    g = json.load(open(path, encoding="utf-8"))
    return g["items"] if isinstance(g, dict) else g


def score(gold, candidate):
    chrome = [g for g in gold if g["label"] == "chrome"]
    content = [g for g in gold if g["label"] == "content"]
    removed = preserved = 0
    chrome_missed = []
    content_violations = []
    per_class = {}
    for g in chrome:
        cleaned = candidate(g["text"])
        cls = g.get("chrome_class", "?")
        per_class.setdefault(cls, [0, 0])
        per_class[cls][1] += 1
        if is_removed(g["text"], cleaned):
            removed += 1
            per_class[cls][0] += 1
        else:
            chrome_missed.append(g)
    for g in content:
        cleaned = candidate(g["text"])
        if is_preserved(g["text"], cleaned):
            preserved += 1
        else:
            content_violations.append((g, cleaned))
    return {
        "n_chrome": len(chrome),
        "n_content": len(content),
        "chrome_removed": removed,
        "chrome_removed_rate": removed / len(chrome) if chrome else 1.0,
        "content_preserved": preserved,
        "content_preserved_rate": preserved / len(content) if content else 1.0,
        "chrome_missed": chrome_missed,
        "content_violations": content_violations,
        "per_class": per_class,
    }


def report(name, gold, candidate):
    s = score(gold, candidate)
    print(f"\n=== candidate: {name} ===")
    print(f"  chrome={s['n_chrome']}  content={s['n_content']}")
    print(f"  chrome_removed_rate    = {s['chrome_removed_rate']:.4f}"
          f"  ({s['chrome_removed']}/{s['n_chrome']})  [GRADED]")
    print(f"  content_preserved_rate = {s['content_preserved_rate']:.4f}"
          f"  ({s['content_preserved']}/{s['n_content']})  [GATE: MUST=1.0]")
    print("  per-chrome-class removed:")
    for cls, (r, t) in sorted(s["per_class"].items()):
        print(f"      {cls:16s} {r}/{t}")
    if s["content_preserved_rate"] < 1.0:
        print(f"  *** FAITHFULNESS VIOLATION *** candidate gutted "
              f"{len(s['content_violations'])} content span(s) -> AUTO-DISQUALIFY:")
        for g, cleaned in s["content_violations"][:12]:
            print(f"      orig[{_short(g['text'])}]")
            print(f"      ->  [{_short(cleaned)}]")
    else:
        print("  OK: content_preserved_rate == 1.0 (faithfulness gate passed).")
    return s


def _short(t, n=110):
    t = re.sub(r"\s+", " ", (t or "").strip())
    return (t[:n] + "...") if len(t) > n else t


def main():
    gold = load_gold()

    # Oracle self-check: a perfect candidate that empties exactly the gold-chrome spans
    # and leaves content untouched MUST score removed=1.0 AND preserved=1.0 -> validates
    # the harness math + that the gold round-trips through the scoring semantics.
    labels = {g["text"]: g["label"] for g in gold}
    def oracle(text):
        return "" if labels.get(text) == "chrome" else text
    os_ = score(gold, oracle)
    assert abs(os_["chrome_removed_rate"] - 1.0) < 1e-9, \
        f"ORACLE chrome_removed_rate != 1.0 ({os_['chrome_removed_rate']}) -- harness math wrong"
    assert abs(os_["content_preserved_rate"] - 1.0) < 1e-9, \
        f"ORACLE content_preserved_rate != 1.0 ({os_['content_preserved_rate']}) -- harness math wrong"
    print("[self-check passed] oracle scored chrome_removed=1.0 and content_preserved=1.0.")

    from chrome_candidates import CANDIDATES
    results = {}
    for name, fn in CANDIDATES.items():
        results[name] = report(name, gold, fn)

    # Winner = highest chrome_removed_rate among candidates with preserved==1.0.
    eligible = {n: r for n, r in results.items()
                if abs(r["content_preserved_rate"] - 1.0) < 1e-9}
    print("\n================ VERDICT ================")
    if not eligible:
        print("NO candidate passed the content_preserved==1.0 gate. ALL disqualified.")
    else:
        winner = max(eligible, key=lambda n: eligible[n]["chrome_removed_rate"])
        print(f"WINNER: {winner}  (chrome_removed_rate={eligible[winner]['chrome_removed_rate']:.4f}, "
              f"content_preserved_rate=1.0)")
        for n, r in results.items():
            dq = "" if n in eligible else "  [DISQUALIFIED: content_preserved<1.0]"
            print(f"  {n:24s} removed={r['chrome_removed_rate']:.4f} "
                  f"preserved={r['content_preserved_rate']:.4f}{dq}")

    # persist machine-readable results (drop the heavy span lists)
    slim = {}
    for n, r in results.items():
        slim[n] = {k: v for k, v in r.items()
                   if k not in ("chrome_missed", "content_violations")}
        slim[n]["content_violations_sample"] = [
            {"orig": _short(g["text"], 200), "cleaned": _short(c, 200)}
            for g, c in r["content_violations"][:20]
        ]
        slim[n]["chrome_missed_sample"] = [
            {"class": g.get("chrome_class"), "text": _short(g["text"], 200)}
            for g in r["chrome_missed"][:30]
        ]
    json.dump(slim, open(os.path.join(HERE, "chrome_benchmark_results.json"), "w",
                         encoding="utf-8"), indent=1, ensure_ascii=False)
    print("\nresults -> chrome_benchmark_results.json")


if __name__ == "__main__":
    main()
