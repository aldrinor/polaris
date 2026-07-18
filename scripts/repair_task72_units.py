import json, re
from pathlib import Path
from synthesis_contract import level_span_support
src=Path("outputs/compose_inputs/task72_cards_curated.json")
dst=Path("outputs/compose_inputs/task72_cards_facet_repaired.json")
lex=[("worker",r"\bworkers?\b"),("firm",r"\bfirms?\b"),
("occupation",r"\b(?:occupations?|occupational)\b"),
("economy",r"\beconom(?:y|ies|ic|ical|ically)(?:-wide)?\b"),
("industry",r"\bindustr(?:y|ies|ial)\b"),("task",r"\btasks?\b"),
("region",r"\b(?:regions?|regional)\b"),("household",r"\bhouseholds?\b"),
("team",r"\bteams?\b")]
cards=json.loads(src.read_text())
for c in cards:
    span=c.get("span") or c.get("span_raw") or ""
    hits=[(m.start(),i,u) for i,(u,p) in enumerate(lex)
          if (m:=re.search(p,span,re.I))]
    unit=min(hits)[2] if hits else ""
    unit=unit if level_span_support(span,unit) else ""
    c["level"]=c["unit_of_analysis"]=unit
dst.write_text(json.dumps(cards,indent=2,ensure_ascii=False)+"\n")
print(f"repaired {len(cards)} cards -> {dst}")
import collections
print("level distribution:", dict(collections.Counter(c['level'] or '(empty)' for c in cards)))
