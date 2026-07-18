#!/usr/bin/env python3
"""End-to-end pipeline validation on the cards available NOW, plus a SMALL real Opus proof.

Sol §7 says the real audit waits for the mine to exit. This script does NOT run the full audit. It only
proves, while the mine is still writing, that (a) the deterministic Tier-0 screen ingests REAL serialized
v2 / recovered cards without crashing, and (b) the Opus transport path (`claude -p --model opus`) actually
returns a schema-valid, Opus-proven verdict for a handful of real cards. It is READ-ONLY: it never writes
to outputs/, never touches the mine, blobs, or the ledger.

Usage:
    PYTHONPATH=scripts:src python scripts/card_audit/validate_now.py --tier0 3 --opus 2
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'src'))

import provenance as P                       # noqa: E402
from card_audit import tier0, harness        # noqa: E402
from card_audit.audit_schema import FAIL     # noqa: E402

OUT = ROOT / 'outputs'


def _load_cards() -> tuple[list[dict], str]:
    """Prefer the recovered-table cards (small) for the Tier-0 ingest proof, else v2. READ-ONLY."""
    rec = OUT / 'recovered_table_cards.json'
    v2 = OUT / 'evidence_cards_v2.json'
    if rec.exists():
        d = json.loads(rec.read_text())
        cards = d.get('cards') if isinstance(d, dict) else d
        if cards:
            return cards, str(rec)
    d = json.loads(v2.read_text())
    return d, str(v2)


def _pinned_question() -> str:
    meta = OUT / 'evidence_cards_v2.meta.json'
    if meta.exists():
        return str(json.loads(meta.read_text()).get('question') or '')
    return ''


def _policy_for(name: str) -> P.SourcePolicy:
    for pol in (P.JOURNAL_ONLY, P.ANY_VERSION):
        if pol.name == name:
            return pol
    return P.JOURNAL_ONLY


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--tier0', type=int, default=3, help='how many real cards to Tier-0 screen')
    ap.add_argument('--opus', type=int, default=2, help='how many real cards to send to a REAL opus call')
    ap.add_argument('--max-corr', type=int, default=0,
                    help='only screen cards with at most this many corroborators (0 = smallest first)')
    args = ap.parse_args()

    cards, src = _load_cards()
    question = _pinned_question()
    v2 = json.loads((OUT / 'evidence_cards_v2.json').read_text())
    policy_name = (json.loads((OUT / 'evidence_cards_v2.meta.json').read_text()).get('source_policy')
                   if (OUT / 'evidence_cards_v2.meta.json').exists() else 'journal_articles_only')
    policy = _policy_for(policy_name)

    print(f'== validate_now ==')
    print(f'card source: {src} ({len(cards)} cards); v2 census: {len(v2)}')
    print(f'pinned question: {question[:90]!r}')
    print(f'derived policy: {policy.name}')

    # ---- graph load (read-only, defensive: the mine may be mid-write) ----------------------------
    graph = None
    gpath = OUT / 'provenance_graph.json'
    if gpath.exists():
        try:
            graph = P.Graph.from_json(json.loads(gpath.read_text()))
            print(f'graph: loaded {len(graph.manifestations)} manifestations, {len(graph.works)} works')
        except Exception as e:                          # noqa: BLE001
            print(f'graph: could NOT strict-load ({type(e).__name__}: {e}); Tier-0 binding checks skipped')
    else:
        print('graph: provenance_graph.json absent; Tier-0 binding checks skipped')

    # ---- Tier-0 ingest proof: screen the smallest real cards -------------------------------------
    print('\n-- Tier-0 ingest on real cards --')
    ordered = sorted(v2, key=lambda c: len(c.get('corroborating_sources') or []))
    tier0_sample = ordered[:max(0, args.tier0)]
    if graph is not None:
        for c in tier0_sample:
            try:
                r = tier0.screen_card(c, graph, policy, taxonomy=None, tagger=None, json_pointer='/x')
                fails = [k for k, d in r.dimensions.items() if d.verdict == FAIL]
                print(f'  {c.get("id","?")[:40]:40s} ncorr={len(c.get("corroborating_sources") or []):<5d}'
                      f' overall={r.overall:12s} fails={fails}')
            except Exception as e:                      # noqa: BLE001
                print(f'  {c.get("id","?")[:40]:40s} Tier-0 CRASHED: {type(e).__name__}: {e}')
                return 2
        print('  Tier-0 ingested every sampled real card without crashing.')
    else:
        print('  (skipped: no graph)')

    # ---- SMALL REAL OPUS PROOF -------------------------------------------------------------------
    print('\n-- REAL opus transport proof --')
    if args.opus <= 0:
        print('  (skipped: --opus 0)')
        return 0
    import shutil
    if not shutil.which('claude'):
        print('  claude CLI not on PATH; cannot prove the opus path here.')
        return 0
    schema = harness.opus_response_json_schema()
    proven = 0
    for c in ordered[:args.opus]:
        rid = f'validate-now:{c.get("id","?")}'

        class _Rec:                                     # a minimal det-receipt shim carrying the row id
            audit_row_id = rid

            def to_json(self):
                return {'audit_row_id': rid, 'note': 'validate_now shim'}

        facets = list(c.get('facet_tags') or c.get('facet_tags_span') or [])
        packet = harness.build_opus_packet(c, graph, question=question, contract_facets=facets,
                                           det_receipt=_Rec()) if graph is not None else dict(
            audit_row_id=rid, research_question=question, contract_facets=facets,
            support_role='primary', card={k: c[k] for k in ('id', 'act', 'claim', 'span')
                                          if isinstance(c.get(k), str)},
            resolved_span=c.get('span_raw') or c.get('span') or '', deterministic_receipt={})
        prompt = harness.build_opus_prompt(packet, schema)
        t0 = time.time()
        try:
            envelope = harness.subprocess_opus_runner(prompt, schema, timeout_s=300, max_retries=2)
        except harness.OpusUnavailable as e:
            print(f'  {c.get("id","?")[:40]:40s} opus UNAVAILABLE: {e}')
            continue
        dt = time.time() - t0
        is_opus = harness.model_is_opus(envelope)
        text = harness._extract_response_text(envelope)
        import re
        m = re.search(r'\{.*\}', text or '', re.S)
        try:
            obj = json.loads(m.group(0)) if m else json.loads(text)
            harness.validate_opus_response(obj, rid)
            schema_ok = True
            verdicts = {'faith': obj['faithfulness'].get('verdict'),
                        'rel': obj['relevance'].get('verdict'),
                        'disp': obj.get('proposed_disposition')}
        except Exception as e:                          # noqa: BLE001
            schema_ok = False
            verdicts = f'{type(e).__name__}: {e}'
        cost = envelope.get('total_cost_usd')
        print(f'  {c.get("id","?")[:40]:40s} opus={is_opus} schema_ok={schema_ok} '
              f'{dt:.1f}s ${cost} -> {verdicts}')
        if is_opus and schema_ok:
            proven += 1

    print(f'\n  REAL opus proof: {proven}/{args.opus} card(s) returned an Opus-proven, schema-valid verdict.')
    print('STOP: this is only the transport + ingest proof. The full audit waits for mine exit (Sol §7).')
    return 0 if proven > 0 else 3


if __name__ == '__main__':
    raise SystemExit(main())
