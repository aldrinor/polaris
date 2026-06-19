#!/usr/bin/env python3
"""I-arch-011 FINAL behavioral gate (§-1.4): the enrichment-section strict_verify under the REAL judge
+ PG_PARALLEL_VERIFY=16 (FIX-C) on the banked drb_78 corpus. Proves the section COMPLETES in minutes
(run #6 took ~173 min serial), KEEPS >=200 cited sources on the real enforce path, and quantifies the
junk-screen leakage (metadata / URL / off-topic units the judge entails but aren't useful citations).

This is the real-output proof the deploy rides on. ~1839 free-route glm-5.1 calls (operator-authorized).
"""
from __future__ import annotations
import json, os, sys, time, re
_R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _R)
for line in open(os.path.join(_R, ".env"), encoding="utf-8", errors="ignore"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("="); os.environ.setdefault(k.strip(), v.strip())
os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "off"   # basket build free
os.environ["PG_ROLE_ALLOW_FALLBACKS"] = "1"           # free-route glm-5.1 (run condition)
os.environ["PG_PARALLEL_VERIFY"] = "16"               # FIX-C under test
os.environ["PG_ENTAILMENT_TOTAL_S"] = "45"            # the proven per-call deadline
os.environ.setdefault("PG_ENTAILMENT_MODEL", "z-ai/glm-5.1")
os.environ.setdefault("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro")
MIN_CITED = int(os.getenv("GATE_MIN_CITED", "200"))
MAX_WALL_MIN = float(os.getenv("GATE_MAX_WALL_MIN", "30"))

snap = json.load(open("outputs/corpus_backups/extracted/drb_78_parkinsons_dbs/corpus_snapshot.json", encoding="utf-8"))
pool = {}
for r in (snap.get("evidence_for_gen") or []):
    e = str((r or {}).get("evidence_id") or "").strip()
    if e: pool.setdefault(e, r)
from src.polaris_graph.authority.data_loader import load_authority_data
gov = tuple(load_authority_data().get("psl_gov_suffixes") or ())
from src.polaris_graph.synthesis.credibility_pass import run_credibility_analysis
an = run_credibility_analysis(snap.get("question") or "", list(pool.values()), gov_suffixes=gov, domain=snap.get("domain") or None, judge=None)
from src.polaris_graph.generator.weighted_enrichment import diagnose_unbound_supports_selection, build_verified_span_draft
wfe = diagnose_unbound_supports_selection(evidence_pool=pool, credibility_analysis=an, contract_plans=[])
raw = build_verified_span_draft(wfe.ev_ids, pool)
from src.polaris_graph.generator.live_deepseek_generator import _rewrite_draft_with_spans
rewritten, _c, _u = _rewrite_draft_with_spans(raw, pool)
print(f"[GATE] candidates={len(wfe.ev_ids)} draft_chars={len(raw)} | PG_PARALLEL_VERIFY=16, REAL judge, ENFORCE", flush=True)

os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "enforce"
from src.polaris_graph.generator.provenance_generator import strict_verify
t0 = time.time()
rep = strict_verify(rewritten, pool)
wall = time.time() - t0

kept = rep.total_kept
distinct = len({t.evidence_id for sv in rep.kept_sentences for t in (getattr(sv, "tokens", None) or [])})

# junk heuristic on KEPT units (rough magnitude; manual sample below for truth)
_URL = re.compile(r"https?://|www\.|doi\.org|\.gov/|\.com/", re.I)
_SUBMIT = re.compile(r"\b(Received|Revised|Accepted|Published online|Correspondence|Reprints?)\b\s*[:.]", re.I)
_REFY = re.compile(r"\bet al\b|\bbibr\d|\b(19|20)\d\d[a-z]?\)|\bVol\.|\bpp?\.\s*\d")
def _is_junk(s: str) -> bool:
    return bool(_URL.search(s) or _SUBMIT.search(s) or len(_REFY.findall(s)) >= 2)
kept_texts = [getattr(sv, "sentence", "") or "" for sv in rep.kept_sentences]
junk = [t for t in kept_texts if _is_junk(t)]

print(f"\n[GATE] verify wall={wall:.1f}s ({wall/60:.1f} min) | kept_sentences={kept} distinct_cited={distinct} dropped={rep.total_dropped}", flush=True)
print(f"[GATE] suspected junk among kept (URL/submission-metadata/reference-list): {len(junk)} ({100*len(junk)//max(1,kept)}%)", flush=True)
print("\n--- 10 kept-unit samples (eyeball clinical vs junk) ---")
for t in kept_texts[:10]:
    print(f"   [{'JUNK?' if _is_junk(t) else 'clin '}] {t[:130]!r}")
print("\n--- 6 suspected-junk samples ---")
for t in junk[:6]:
    print(f"   {t[:140]!r}")

problems = []
if wall/60 > MAX_WALL_MIN: problems.append(f"verify wall {wall/60:.1f}min > {MAX_WALL_MIN}min — FIX-C did not bound it")
if kept < MIN_CITED: problems.append(f"kept {kept} < {MIN_CITED} — enforce-path breadth below target")
print("\n" + "="*76)
if problems:
    for p in problems: print(f"   FAIL: {p}")
    print("[GATE][NO-GO]"); sys.exit(1)
print(f"[GATE][GO] enrichment verify COMPLETES in {wall/60:.1f}min (was ~173min serial) and KEEPS")
print(f"   {kept} cited sentences / {distinct} distinct sources on the REAL enforce path (target {MIN_CITED}).")
print(f"   junk leakage ~{100*len(junk)//max(1,kept)}% (separate quality follow-up; not a hang blocker).")
print("="*76); sys.exit(0)
