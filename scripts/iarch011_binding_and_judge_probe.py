#!/usr/bin/env python3
"""Advisor-mandated two measurements before any rebuild:
  (1) FREE: over ALL rendered enrichment units, % unit-verbatim-in-span and % unit-content-words-in-span
      (does the binder point spans at their units, for clean units too?). + dump 12 pairs incl. short.
  (2) SMALL SPEND: ~N residual (non-FIX-B) units -> the REAL glm-5.1 judge -> keep-rate + per-call latency.
      This is the enforce-path breadth number + whether 16-way parallel finishes in minutes.
"""
from __future__ import annotations
import json, os, sys, time, statistics, random
_R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _R)

# load OPENROUTER_API_KEY (+ any PG_*) from .env for the real-judge sample
for line in open(os.path.join(_R, ".env"), encoding="utf-8", errors="ignore"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())
os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "off"  # basket build free
os.environ["PG_ROLE_ALLOW_FALLBACKS"] = "1"          # free-route glm-5.1 (the run condition)
os.environ.setdefault("PG_ENTAILMENT_MODEL", "z-ai/glm-5.1")
os.environ.setdefault("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro")
os.environ["PG_ENTAILMENT_TOTAL_S"] = "30"
N_SAMPLE = int(os.getenv("PROBE_N", "40"))

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

# capture EVERY (sentence_clean, combined_span) pair via a spy, with a stub judge so the pass is offline.
import re as _re
import src.polaris_graph.clinical_generator.strict_verify as _sv
from src.polaris_graph.clinical_generator.strict_verify import _content_words as _cw, is_trivial_verbatim_entailment as _fixb
pairs = []
_orig = _sv.is_trivial_verbatim_entailment
def _spy(s, sp):
    r = _orig(s, sp); pairs.append((bool(r), s, sp)); return r
_sv.is_trivial_verbatim_entailment = _spy
class _Stub:
    def judge(self, s, sp): return "NEUTRAL", "stub"
_sv._get_judge = lambda: _Stub()
os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "enforce"
from src.polaris_graph.generator.provenance_generator import strict_verify
strict_verify(rewritten, pool)

def _norm(x): return _re.sub(r"\s+", " ", x or "").strip()
verb = sum(1 for _, s, sp in pairs if _norm(s) in _norm(sp))
cw_cov = sum(1 for _, s, sp in pairs if _cw(s) and _cw(s).issubset(_cw(sp)))
fixb_hit = sum(1 for m, _, _ in pairs if m)
tot = len(pairs)
print(f"\n=== (1) BINDING COVERAGE over {tot} rendered units ===")
print(f"  unit is VERBATIM substring of its span:        {verb} ({100*verb//max(1,tot)}%)  [FIX-B can fire]")
print(f"  unit content-words SUBSET of span words:       {cw_cov} ({100*cw_cov//max(1,tot)}%)  [judge likely ENTAILED]")
print(f"  FIX-B matched (boundary-aligned verbatim):     {fixb_hit} ({100*fixb_hit//max(1,tot)}%)")
print("\n--- 12 sample pairs (mix of lengths) ---")
short = [p for p in pairs if len(p[1]) <= 220][:6]
longp = [p for p in pairs if len(p[1]) > 220][:6]
for m, s, sp in (short + longp):
    contained = _norm(s) in _norm(sp)
    print(f"  [fixb={m} verbatim_in_span={contained}] sent({len(s)}c)={s[:120]!r}")
    print(f"      span({len(sp)}c)={sp[:120]!r}")

# (2) real-judge sample on residual (non-FIX-B) units -> keep-rate + latency
residual = [(s, sp) for m, s, sp in pairs if not m]
random.seed(7)
random.shuffle(residual)
sample = residual[:N_SAMPLE]
print(f"\n=== (2) REAL glm-5.1 judge on {len(sample)} residual units (free-route) ===", flush=True)
judge = _sv._get_judge  # currently stub; build a REAL one
import importlib
ej = importlib.import_module("src.polaris_graph.llm.entailment_judge")
real = ej._EntailmentJudge()
kept = 0; lats = []; verds = {}
for i, (s, sp) in enumerate(sample):
    t = time.time()
    try:
        v, reason = real.judge(s, sp)
    except Exception as exc:
        v, reason = "ERR", f"{type(exc).__name__}:{exc}"
    dt = time.time() - t
    lats.append(dt)
    verds[v] = verds.get(v, 0) + 1
    if v == "ENTAILED" and not str(reason).startswith("judge_error"):
        kept += 1
    if i < 8:
        print(f"  [{i}] {dt:5.1f}s {v:12} reason={str(reason)[:60]!r} | sent={s[:70]!r}", flush=True)
print(f"\n  verdict_counts={verds}")
print(f"  KEEP-RATE (real ENTAILED): {kept}/{len(sample)} = {100*kept//max(1,len(sample))}%")
if lats:
    lats.sort()
    print(f"  latency: median={statistics.median(lats):.1f}s p90={lats[int(0.9*len(lats))-1]:.1f}s max={max(lats):.1f}s")
    est_serial = statistics.median(lats) * tot
    est_16way = est_serial / 16
    print(f"  PROJECTION for {tot} units: serial~{est_serial/60:.0f}min  16-way~{est_16way/60:.0f}min")
print("\n=== PROBE DONE ===")
