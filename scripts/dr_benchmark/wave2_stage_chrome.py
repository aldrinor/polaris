"""wave-2 CHROME stage-harness — run the fixed chrome predicate over a FROZEN rendered report.md
and report how many claim units it would now DROP as chrome/furniture. Frozen input, no LLM, seconds.

Usage: PYTHONPATH=/c/POLARIS python scripts/dr_benchmark/wave2_stage_chrome.py <report.md>
Green/red signal: prints DROP count + every dropped unit (eyeball = real chrome, not a finding) +
a KEEP sample. Compare DROP count across PG_SOURCE_FURNITURE_CHROME / PG_RENDER_CHROME_SCREEN variants.
"""
import os
import re
import sys

os.environ.setdefault("PG_RENDER_CHROME_SCREEN", "1")
os.environ.setdefault("PG_SOURCE_FURNITURE_CHROME", "1")

from src.polaris_graph.generator.weighted_enrichment import (  # noqa: E402
    is_render_chrome_or_unrenderable as chrome,
)

path = sys.argv[1] if len(sys.argv) > 1 else "scratchpad/box2_wave1_report.md"
text = open(path, encoding="utf-8", errors="replace").read()

# Extract claim UNITS: top-level "- " bullets, and prose sentences from body paragraphs.
# Skip headings, tables (| ...), blockquotes, and the numbered bibliography.
units: list[str] = []
for line in text.split("\n"):
    s = line.strip()
    if not s or s.startswith("#") or s.startswith("|") or s.startswith(">") or re.match(r"^\d+\.\s", s):
        continue
    body = re.sub(r"^[-*+]\s+", "", s)  # strip a leading bullet marker
    # split a prose line into sentences (keep it coarse; the predicate is per-unit)
    for sent in re.split(r"(?<=[.!?])\s+(?=[A-Z\[])", body):
        sent = sent.strip()
        if len(sent) >= 25:  # ignore tiny fragments
            units.append(sent)

dropped = [u for u in units if chrome(u, require_sentence_form=True)]
kept = [u for u in units if not chrome(u, require_sentence_form=True)]

print(f"report: {path}")
print(f"units={len(units)}  DROP(chrome)={len(dropped)}  KEEP={len(kept)}  "
      f"drop_rate={len(dropped)/max(1,len(units)):.1%}")
print("\n=== DROPPED as chrome (eyeball: real furniture, not a finding) ===")
for u in dropped[:60]:
    print("  [DROP] " + u[:150])
print(f"\n=== KEEP sample (eyeball: real findings, not over-dropped) ===")
for u in kept[:15]:
    print("  [keep] " + u[:150])
