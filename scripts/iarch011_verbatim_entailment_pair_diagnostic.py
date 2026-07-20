#!/usr/bin/env python3
"""Diagnostic: dump the REAL (sentence_clean, combined_span) pairs the enrichment-section strict_verify
sees, and WHY FIX-B's is_trivial_verbatim_entailment does/doesn't match. FIX-B fired on only 1/1839
units on drb_78 — this prints the actual data so we see what the bound span really looks like."""
from __future__ import annotations
import json, os, sys
_R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _R)
os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "off"  # basket build free
os.environ.setdefault("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro")
os.environ.setdefault("PG_ENTAILMENT_MODEL", "z-ai/glm-5.1")

corpus = "outputs/corpus_backups/extracted/drb_78_parkinsons_dbs/corpus_snapshot.json"
snap = json.load(open(corpus, encoding="utf-8"))
rows = snap.get("evidence_for_gen") or []
pool = {}
for r in rows:
    eid = str((r or {}).get("evidence_id") or "").strip()
    if eid:
        pool.setdefault(eid, r)

from src.polaris_graph.authority.data_loader import load_authority_data
gov = tuple(load_authority_data().get("psl_gov_suffixes") or ())
from src.polaris_graph.synthesis.credibility_pass import run_credibility_analysis
analysis = run_credibility_analysis(snap.get("question") or "", list(pool.values()),
                                    gov_suffixes=gov, domain=snap.get("domain") or None, judge=None)
from src.polaris_graph.generator.weighted_enrichment import (
    diagnose_unbound_supports_selection, build_verified_span_draft)
wfe = diagnose_unbound_supports_selection(evidence_pool=pool, credibility_analysis=analysis, contract_plans=[])
raw = build_verified_span_draft(wfe.ev_ids, pool)
from src.polaris_graph.generator.live_deepseek_generator import _rewrite_draft_with_spans
rewritten, _c, _u = _rewrite_draft_with_spans(raw, pool)

# Hook is_trivial_verbatim_entailment to capture the first N pairs + matched flag.
import src.polaris_graph.clinical_generator.strict_verify as _sv
_orig = _sv.is_trivial_verbatim_entailment
_captured = []
def _spy(sentence_clean, combined_span):
    r = _orig(sentence_clean, combined_span)
    if len(_captured) < 12:
        _captured.append((r, sentence_clean, combined_span))
    return r
_sv.is_trivial_verbatim_entailment = _spy
# also patch the provenance import path (it imports the name lazily inside the function)
import src.polaris_graph.generator.provenance_generator as _pg

os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "enforce"
# stub the judge so no network
class _Stub:
    def judge(self, s, sp): return "NEUTRAL", "stub"
_sv._get_judge = lambda: _Stub()

from src.polaris_graph.generator.provenance_generator import strict_verify
rep = strict_verify(rewritten, pool)
print(f"\n=== kept={rep.total_kept} dropped={rep.total_dropped} | captured {len(_captured)} pairs ===\n")
for i, (matched, s, sp) in enumerate(_captured):
    print(f"--- pair {i} | FIX-B matched={matched} ---")
    print(f"  SENTENCE_CLEAN ({len(s)} chars): {s!r}")
    print(f"  COMBINED_SPAN  ({len(sp)} chars): {sp[:400]!r}")
    # why-not analysis
    import re as _re
    sn = _re.sub(r'\s+', ' ', s).strip()
    spn = _re.sub(r'\s+', ' ', sp).strip()
    idx = spn.find(sn)
    print(f"  norm: len(sent)={len(sn)} substring_idx={idx} (>=0 means contained)")
    if idx == -1:
        # find longest common prefix-ish: is the sentence a SUPERSET of the span? or different?
        print(f"  span_in_sentence_idx={sn.find(spn) if spn else -1}  (span ⊆ sentence?)")
    print()
