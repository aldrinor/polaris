import json, re, sys
from scripts.run_honest_sweep_r3 import _basket_corroboration_block
bib = json.load(open(sys.argv[1], encoding="utf-8"))
entries = bib if isinstance(bib, list) else bib.get("bibliography", [])
section = _basket_corroboration_block(entries)
# audit the rendered section's HEADER bullets only (lines starting "- **")
headers = re.findall(r"^- \*\*(.+?)\*\* — \d+ verified", section, re.MULTILINE)
hash_h = [h for h in headers if re.match(r"^clm_[0-9a-f]+$", h)]
twoword = [h for h in headers if len(h.split()) <= 2 and not re.match(r"^clm_", h)]
chrome = [h for h in headers if re.search(r"JEL Classification|Keywords$|Markdown Content|Published Time|Associated Records|Member-only|affiliated with|ISSN:|Download$", h, re.I)]
print(f"rendered section bytes: {len(section)}")
print(f"total header bullets: {len(headers)}")
print(f"  clm_<hash> headers: {len(hash_h)}")
print(f"  <=2-word stub headers: {len(twoword)}  e.g. {twoword[:6]}")
print(f"  chrome-bearing headers: {len(chrome)}  e.g. {chrome[:4]}")
print("\n--- first 12 real headers (proof prose/titles render) ---")
for h in headers[:12]:
    print("   ", h[:120])
