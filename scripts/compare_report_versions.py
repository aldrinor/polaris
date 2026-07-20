"""One-shot V23 vs V24 metric comparison. Delete after use."""
import json

m24 = json.load(open("outputs/full_scale_v24/clinical/clinical_tirzepatide_t2dm/manifest.json"))
m23 = json.load(open("outputs/full_scale_v23/clinical/clinical_tirzepatide_t2dm/manifest.json"))
b24 = json.load(open("outputs/full_scale_v24/clinical/clinical_tirzepatide_t2dm/bibliography.json"))
b23 = json.load(open("outputs/full_scale_v23/clinical/clinical_tirzepatide_t2dm/bibliography.json"))
report24 = open("outputs/full_scale_v24/clinical/clinical_tirzepatide_t2dm/report.md", encoding="utf-8").read()
report23 = open("outputs/full_scale_v23/clinical/clinical_tirzepatide_t2dm/report.md", encoding="utf-8").read()

g24 = m24.get("generator", {}) or {}
g23 = m23.get("generator", {}) or {}

print(f"{'Metric':<26}{'V23':<22}{'V24':<22}")
print("-" * 70)
print(f"{'status':<26}{m23.get('status'):<22}{m24.get('status')}")
print(f"{'release_allowed':<26}{str(m23.get('release_allowed')):<22}{str(m24.get('release_allowed'))}")
print(f"{'sections':<26}{len(g23.get('outline_sections') or []):<22}{len(g24.get('outline_sections') or [])}")
print(f"{'outline V23':<26}{str(g23.get('outline_sections'))}")
print(f"{'outline V24':<26}{str(g24.get('outline_sections'))}")
print(f"{'prose words':<26}{str(g23.get('words')):<22}{str(g24.get('words'))}")
print(f"{'verified sentences':<26}{str(g23.get('sentences_verified')):<22}{str(g24.get('sentences_verified'))}")
print(f"{'dropped sentences':<26}{str(g23.get('sentences_dropped')):<22}{str(g24.get('sentences_dropped'))}")
print(f"{'bibliography size':<26}{len(b23):<22}{len(b24)}")
print(f"{'corpus size':<26}{str(m23.get('corpus', {}).get('count')):<22}{str(m24.get('corpus', {}).get('count'))}")
print(f"{'limitations_words':<26}{str(g23.get('limitations_words')):<22}{str(g24.get('limitations_words'))}")
print(f"{'trial_summary_table':<26}{'(V23 had none)':<22}{'(V24 M-36 field)'}")

# Report content scanning
print()
print("--- Report content scans ---")
for label, rep in [("V23", report23), ("V24", report24)]:
    print(f"{label}:")
    print(f"  total words:          {len(rep.split())}")
    print(f"  '### Trial Summary':  {'PRESENT' if '### Trial Summary' in rep else 'MISSING'}")
    print(f"  '### Mechanism':      {'PRESENT' if '### Mechanism' in rep else 'MISSING'}")
    print(f"  mentions 'mechanism': {rep.lower().count('mechanism')}")
    # Count citations [N]
    import re
    cites = re.findall(r"\[(\d+)\]", rep)
    print(f"  [N] citation markers: {len(cites)} (unique={len(set(cites))})")
    # Trial mentions
    for trial in ["SURPASS-1","SURPASS-2","SURPASS-3","SURPASS-4","SURPASS-5","SURPASS-6","SURPASS-CVOT","SURMOUNT-1","SURMOUNT-2","SURMOUNT-3","SURMOUNT-4"]:
        if trial in rep:
            print(f"    {trial}: {rep.count(trial)} mentions")

# Health Canada / jurisdictional check
print()
print("--- Jurisdictional coverage ---")
for label, bib in [("V23", b23), ("V24", b24)]:
    fda = sum(1 for e in bib if "fda" in str(e.get("url", "")).lower())
    ema = sum(1 for e in bib if "ema.europa" in str(e.get("url", "")).lower())
    nice = sum(1 for e in bib if "nice.org" in str(e.get("url", "")).lower())
    hc = sum(1 for e in bib if any(d in str(e.get("url", "")).lower() for d in ["canada.ca", "hres.ca", "hc-sc.gc.ca"]))
    print(f"{label}: FDA={fda}  EMA={ema}  NICE={nice}  HealthCanada={hc}")

# Tier mix
print()
print("--- Corpus tier mix ---")
for label, m in [("V23", m23), ("V24", m24)]:
    tf = m.get("corpus", {}).get("tier_fractions", {})
    tf_str = ", ".join(f"{k}={v:.2%}" for k, v in sorted(tf.items()))
    print(f"{label}: {tf_str}")
