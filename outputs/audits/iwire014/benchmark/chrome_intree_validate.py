"""I-wire-014 #1334 — validate the PRODUCTION render-seam decision
(weighted_enrichment.is_render_chrome_or_unrenderable, now with the whole-unit-collapse
furniture screen) against chrome_gold_augmented.json. GATE LAW: content_preserved_rate MUST = 1.0.

Run ON THE VM:  cd /root/polaris/outputs/audits/iwire014/benchmark && \
  PYTHONPATH=/root/polaris PG_RENDER_CHROME_SCREEN=1 /opt/conda/bin/python chrome_intree_validate.py
"""
import json
import os
import sys

os.environ.setdefault("PG_RENDER_CHROME_SCREEN", "1")
sys.path.insert(0, "/root/polaris")
from src.polaris_graph.generator.weighted_enrichment import (  # noqa: E402
    is_render_chrome_or_unrenderable,
)


def main():
    gold = json.load(open("chrome_gold_augmented.json", encoding="utf-8"))
    items = gold["items"] if isinstance(gold, dict) else gold
    n_chrome = sum(1 for it in items if it["label"] == "chrome")
    n_content = sum(1 for it in items if it["label"] == "content")
    chrome_removed = 0
    content_dropped = []
    new_class_removed = 0
    n_new_class = 0
    NEW = {"journal_html", "affiliation", "paywall_preview", "cookie_consent", "dehyphenation"}
    for it in items:
        removed = is_render_chrome_or_unrenderable(it["text"])
        cls = it.get("chrome_class", "")
        if it["label"] == "chrome":
            if removed:
                chrome_removed += 1
            if cls in NEW:
                n_new_class += 1
                if removed:
                    new_class_removed += 1
        else:  # content MUST be preserved
            if removed:
                content_dropped.append(it["text"][:90])
    print(f"items={len(items)}  chrome={n_chrome}  content={n_content}")
    print(f"chrome_removed_rate   = {chrome_removed / n_chrome:.4f}  ({chrome_removed}/{n_chrome})")
    if n_new_class:
        print(f"new_class_removed     = {new_class_removed / n_new_class:.4f}  ({new_class_removed}/{n_new_class})")
    cpr = (n_content - len(content_dropped)) / n_content if n_content else 1.0
    print(f"content_preserved_rate= {cpr:.4f}  ({n_content - len(content_dropped)}/{n_content})")
    if content_dropped:
        print(f"*** FAITHFULNESS VIOLATION: {len(content_dropped)} content span(s) dropped ***")
        for s in content_dropped[:6]:
            print("   DROPPED:", repr(s))
    else:
        print("OK: GATE LAW held — content_preserved_rate = 1.0")


if __name__ == "__main__":
    main()
