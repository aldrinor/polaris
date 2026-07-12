#!/usr/bin/env python3
"""S3 CONSOLIDATE replay harness — build cp3_basket_snapshot.json from a cp2 corpus.

Standalone CLI (LAW VII): loads an S2 cp2_corpus_snapshot.json, runs the REAL production
consolidation (src/polaris_graph/synthesis/finding_dedup.dedup_by_finding) with the deployed
flag slate, and writes the cp3 basket snapshot in the same schema the sweep persists. Pure
CPU (NLI OFF) => deterministic, seconds. No LLM, no network.
"""
from __future__ import annotations
import argparse, hashlib, json, os, sys, time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# S2/S3 re-pass Fix 3(b): the deployed S3 slate now flips the SEMANTIC merge authority ON —
# ``PG_CONSOLIDATION_NLI`` (bidirectional-NLI over the literal clusters) and
# ``PG_FINDING_DEDUP_NLI`` — so same-meaning-different-words findings MERGE instead of
# fragmenting on the numeric-tuple key. The Fix-1/3c/4/5/6 kill-switches are pinned ON here
# for an explicit, self-documenting deployed slate (each defaults ON in code; pinning makes
# the run reproducible and the parity with the production sweep visible).
_SLATE = {
    'PG_BASKET_CONSUME_FINDING_DEDUP': '1',
    'PG_CONSOLIDATION_NLI': '1',            # Fix 3(b): semantic merge authority ON
    'PG_FINDING_DEDUP_NLI': '1',            # Fix 3(b): finding-dedup NLI leg ON
    'PG_FINDING_DEDUP_QUALITATIVE': '1',
    'PG_SWEEP_CREDIBILITY_REDESIGN': '1',
    'PG_SAMEWORK_CROSSMIRROR': '1',         # Fix 4: cross-mirror same-work identity
    'PG_CI_ANTIBOT_SHELL': '1',             # Fix 1(a)(b): general anti-bot / shell chrome
    'PG_FINDING_DEDUP_KEY_HYGIENE': '1',    # Fix 3(c): garbage subject/value key guard
    'PG_CORROBORATION_DISTINCT_WORKS': '1',  # Fix 5: corroboration = distinct works
    'PG_CORROBORATION_DERIVATIVE_PRESS': '1',  # Fix 6: derivative-press excluded from count
    'PG_CONSOLIDATION_NLI_QUALITATIVE': '1',  # Fix 3(a): NLI merges qualitative baskets too
    'PG_CONSOLIDATION_NLI_SUBBUCKET': '1',    # iter-2 P0-3a: lexical FALLBACK if the embedder
                                              # is unavailable (embed-block is now the primary
                                              # over-cap path); still never SKIPs-all
    # ── S2/S3 re-pass iter-2 (Fable full-list) ──
    'PG_CONSOLIDATION_NLI_EMBED_BLOCK': '1',  # P0-3a: SEMANTIC embedding blocking for over-cap
                                              # buckets (top-k neighbors, not degenerate lexical)
    'PG_FINDING_NUMERIC_NLI_CONFIRM': '1',    # P0-3b: numeric tuple key is RECALL only; NLI decides
    'PG_FINDING_NUMERIC_NLI_CONFIRM_STRICT': '1',  # P0-3b: fail-open = SPLIT (unconfirmed => singleton)
    'PG_SAMEWORK_TITLE_UNION': '1',           # P0-4a: cross-mirror same-work title union (EL25/EL56)
    'PG_FINDING_NONCLAIM_BASKET_FOLD': '1',   # P0-4b: non-claim fragments fold into their work
    # ── S2/S3 re-pass iter-8 (Fable full-list) ──
    'PG_CONSOLIDATION_NLI_SEMANTIC_RECALL': '1',  # Fix 1: semantic top-k recall -> bidirectional judge
    'PG_FINDING_REVERIFY_SAMEWORK_KEEP': '1',     # Fix 2(c): same-work non-confirm stays in basket
    'PG_SAMEWORK_SUPPLEMENT_FOLD': '1',           # Fix 8: SM/appendix folds into the parent work
}


def _row_field(row, *names):
    for n in names:
        v = row.get(n)
        if v:
            return str(v)
    return ''


def _nli_score_stats():
    """S2/S3 re-pass iter-4 fix 9 (Fable / P0-2(d)): the consolidation-NLI scoring telemetry from
    the LAST score_pairs call plus a derived scored fraction and a BLIND flag (total>0, scored==0
    => the semantic judge saw nothing — a loud run-validity failure). Never raises."""
    try:
        from src.polaris_graph.synthesis.consolidation_nli import get_last_score_stats
        st = dict(get_last_score_stats())
    except Exception as exc:  # noqa: BLE001 — telemetry disclosure must never crash the replay
        return {'available': False, 'error': str(exc)}
    total = int(st.get('total_pairs', 0) or 0)
    scored = int(st.get('scored_pairs', 0) or 0)
    st['available'] = True
    st['scored_fraction'] = round(scored / total, 4) if total > 0 else None
    st['judge_blind'] = bool(total > 0 and scored == 0)
    return st


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--cp2', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    for k, v in _SLATE.items():
        os.environ[k] = v

    from src.polaris_graph.authority.data_loader import load_authority_data
    from src.polaris_graph.synthesis.finding_dedup import dedup_by_finding

    cp2_path = Path(args.cp2)
    data = json.load(cp2_path.open(encoding='utf-8'))
    rows = [r for r in data.get('evidence_for_gen', []) if isinstance(r, dict)]
    question = str(data.get('question', '') or '')
    domain = str(data.get('domain', '') or 'workforce')
    slug = str(data.get('slug', '') or '')

    gov = load_authority_data()['psl_gov_suffixes']
    res = dedup_by_finding(rows, gov_suffixes=gov, domain=domain)

    def _eid(i):
        return str(rows[i].get('evidence_id', '')) if 0 <= i < len(rows) else ''

    def _url(i):
        # Fable Fix 5 (provenance): resolve the member URL from the corpus record by ANY of the
        # common URL fields (a row whose source_url/url is blank may still carry link / canonical /
        # source / page_url) so a basket never emits an empty provenance slot for an otherwise
        # citable source. Returns '' only when the record truly carries no URL anywhere.
        if not (0 <= i < len(rows)):
            return ''
        return _row_field(
            rows[i], 'source_url', 'url', 'link', 'canonical_url', 'source', 'page_url'
        )

    def _tier(i):
        return (str(rows[i].get('tier', '') or 'UNKNOWN')) if 0 <= i < len(rows) else 'UNKNOWN'

    def _stmt(i):
        # Fix 7/9 (Fable): the representative_statement must be a READABLE, COMPLETE claim
        # sentence — not the page title, not a mid-word value-window ('us change the task...'),
        # not letter-spaced extraction garbage. General/question-agnostic: collapse letter
        # spacing, split into complete sentences (>=5 words), and prefer the COMPLETE sentence
        # carrying the numeric finding; fall back to the first complete sentence, then the
        # snippet, then the title.
        import re as _re
        from src.polaris_graph.synthesis.finding_dedup import (
            _collapse_letter_spacing, _is_boilerplate_or_metadata_line,
        )
        if not (0 <= i < len(rows)):
            return ''
        row = rows[i]
        body = _collapse_letter_spacing(_row_field(row, 'direct_quote', 'statement'))
        # Fix 4b/9: skip a nav/chrome/menu sentence when a clean content sentence exists, so the
        # representative_statement never reads as boilerplate (login / search-UI / share / cookie).
        _chrome = _re.compile(
            r'log ?in|sign ?in|subscribe|cookie|search text|search type|logical operator|'
            r'add_circle|remove_circle|skip to|newsletter|\bmenu\b|share this|©|›|»',
            _re.IGNORECASE)
        _all = [
            s.strip() for s in _re.split(r'(?<=[.!?])\s+', body.strip())
            if len(s.split()) >= 5 and (s.strip()[:1].isupper() or s.strip()[:1].isdigit())
            and not _chrome.search(s)
        ]
        # iter-8 Fable Fix 4: also skip a masthead / license / byline / cover-page metadata
        # sentence ('Authored By: ...', 'CEPR Press, Paris & London.', 'Prepared by ... Authorized
        # for distribution', a 'This version:' header, an ISBN reference line) when a real
        # claim-bearing sentence exists, so a basket never SURFACES metadata as its statement.
        # Prefer the non-boilerplate sentences; fall back to the full list only if none remain.
        _clean = [s for s in _all if not _is_boilerplate_or_metadata_line(s)]
        sentences = _clean if _clean else _all
        value_tok = None
        try:
            from src.polaris_graph.retrieval.contradiction_detector import extract_numeric_claims
            claims = extract_numeric_claims([row])
            if claims:
                v = float(getattr(claims[0], 'value', 0.0) or 0.0)
                value_tok = (str(int(v)) if v == int(v) else str(v))
                snip = _collapse_letter_spacing((getattr(claims[0], 'context_snippet', '') or '').strip())
        except Exception:
            claims = []
            snip = ''
        # Fix 9: a COMPLETE sentence containing the finding value is the best representative.
        if value_tok:
            for s in sentences:
                if value_tok in s:
                    return s[:300]
        if sentences:
            return sentences[0][:300]
        if claims and snip:
            return snip[:300]
        if body.strip():
            return body.strip()[:300]
        return _row_field(row, 'title', 'statement')

    def _claim_group_id(cluster):
        # P3-10 (S2/S3 re-pass iter-5, Fable): a SEMANTIC group id derived from the basket's
        # reader-visible representative claim sentence — NOT the numeric-tuple recall key. The
        # tuple ('their', 'level', 4.0, ...) is RECALL-ONLY (candidate clustering); presenting it
        # as the claim let forensics read a garbage token as the claim key. The semantic id is a
        # short stable hash of the normalized representative statement, so two baskets show the
        # same id iff they assert the same visible claim. General/question-agnostic.
        stmt = _stmt(cluster.representative_index) or ''
        norm = ' '.join(stmt.lower().split())
        return 'cg_' + hashlib.sha256(norm.encode('utf-8')).hexdigest()[:12]

    baskets = []
    # Fable Fix 5 (provenance): a member with NO resolvable URL is uncitable; it is DROPPED (with a
    # disclosure row) so a basket never emits an empty provenance slot, and a basket left with NO
    # citable member is dropped entirely (disclosed). §-1.3.1 fail-loud: every drop is recorded.
    provenance_gap_disclosure = []
    for c in res.clusters:
        mi = list(c.member_indices)
        citable = [i for i in mi if str(_url(i)).strip()]
        dropped = [i for i in mi if not str(_url(i)).strip()]
        for i in dropped:
            provenance_gap_disclosure.append({
                'evidence_id': _eid(i),
                'representative_evidence_id': _eid(c.representative_index),
                'reason': 'no_resolvable_url_uncitable_member',
            })
        if not citable:
            # Whole basket uncitable — drop it, disclose (a claim no reader can locate).
            provenance_gap_disclosure.append({
                'evidence_id': _eid(c.representative_index),
                'representative_evidence_id': _eid(c.representative_index),
                'reason': 'basket_dropped_no_citable_member',
            })
            continue
        # Under-count corroboration to the citable members (safe direction — never inflate).
        corr = min(int(c.corroboration_count), len(citable)) if dropped else int(c.corroboration_count)
        baskets.append({
            'corroboration_count': corr,
            # P3-10: the semantic claim-group id is the primary claim identity; the numeric tuple
            # below is retained for debugging but LABELED recall-only so it is never read as the
            # claim.
            'claim_group_id': _claim_group_id(c),
            'finding_key': list(c.finding_key),
            'finding_key_role': 'recall_only_not_the_claim',
            'member_count': len(citable),
            'member_evidence_ids': [_eid(i) for i in citable],
            'member_hosts': list(c.member_hosts),
            'member_tiers_weight': [_tier(i) for i in citable],
            'member_urls': [_url(i) for i in citable],
            'representative_evidence_id': _eid(c.representative_index),
            'representative_statement': _stmt(c.representative_index),
        })

    # Fable Fix 2(a): assert NO duplicate claim_group_id before the snapshot is written (fail-loud).
    # A duplicate cg means two surviving baskets assert the SAME visible claim — a residual same-
    # claim false-split the consolidation passes should have merged. The collision is DISCLOSED (not
    # hidden) and each colliding basket after the first is given a disambiguated cg so the snapshot
    # stays unique; the disclosure count surfaces the anomaly for the forensic read (§-1.3.1).
    duplicate_claim_group_ids = []
    _seen_cg: dict = {}
    for b in baskets:
        cg = b['claim_group_id']
        if cg in _seen_cg:
            _seen_cg[cg] += 1
            disambiguated = cg + '_dup' + str(_seen_cg[cg])
            duplicate_claim_group_ids.append({
                'claim_group_id': cg,
                'representative_evidence_id': b['representative_evidence_id'],
                'representative_statement': b['representative_statement'][:200],
                'disambiguated_to': disambiguated,
            })
            b['claim_group_id'] = disambiguated
            b['claim_group_id_collision'] = cg
        else:
            _seen_cg[cg] = 0
    if duplicate_claim_group_ids:
        print('WARN Fix2a duplicate_claim_group_ids=%d (disambiguated + disclosed)'
              % len(duplicate_claim_group_ids), file=sys.stderr)

    sw = res.same_work
    sw_groups_payload = []
    sw_total = 0
    sw_multi = 0
    if sw is not None:
        sw_total = len(sw.groups)
        for g in sw.groups:
            if len(g.member_indices) > 1:
                sw_multi += 1
                sw_groups_payload.append({
                    'same_work_id': g.same_work_id,
                    'canonical_index': g.canonical_index,
                    'member_evidence_ids': list(g.member_evidence_ids),
                    'member_urls': list(g.member_urls),
                })

    multi_member = sum(1 for b in baskets if b['member_count'] > 1)
    multi_corrob = sum(1 for b in baskets if b['corroboration_count'] > 1)

    consolidation_summary = {
        'basket_total': len(baskets),
        'basket_multi_member': multi_member,
        'basket_multi_corroboration': multi_corrob,
        'raw_row_count': res.raw_row_count,
        'distinct_finding_count': res.distinct_finding_count,
        'collapsed_row_count': res.collapsed_row_count,
        'nli_merge_count': res.nli_merge_count,
        'qualitative_basket_count': res.qualitative_basket_count,
        # S2/S3 re-pass iter-4 disclosure (Fable Fix 1(d), §-1.3.1 fail-loud): number of
        # numeric baskets UNIONED by the representative-invariant post-pass (residual same-claim
        # false-splits the numeric split-confirm's fail-open-on-None left behind). >0 proves the
        # THE-GHOST repair fired; 0 = clean/off. Never a DROP — UNION-only, corroboration over
        # DISTINCT works.
        'rep_invariant_merge_count': getattr(res, 'rep_invariant_merge_count', 0),
        # S2/S3 re-pass iter-5 P0-1(b) (Fable): per-cluster confirm/split telemetry from the
        # numeric split-confirm pass — how many clusters lost a member, members kept vs split,
        # and members split specifically by the numbers-strict value gate (rep/member claim
        # sentence lacked the cluster's value). >0 members_split_numbers_strict proves the
        # basket-27 'their/level/4.0'-class false merges dissolved (§-1.3.1 fail-loud).
        'numeric_confirm_telemetry': dict(getattr(res, 'numeric_confirm_telemetry', {}) or {}),
        # S2/S3 re-pass iter-4 fix 9 (Fable / P0-2(d) §-1.3.1 fail-loud): the consolidation-NLI
        # scoring telemetry from the LAST score_pairs call (the semantic merge judge). Discloses
        # scored_pairs / total_pairs so a STARVED / BLIND judge is visible in every run;
        # scored_pairs == 0 while total_pairs > 0 is a loud run-validity failure (the judge saw
        # nothing). Also surfaces whether the wall truncated or an OOM forced a batch-halve/degrade.
        'nli_score_stats': _nli_score_stats(),
        'same_work_groups': sw_total,
        'same_work_multi_member': sw_multi,
        'same_work_dropped_captcha': len(sw.dropped_captcha_indices) if sw else 0,
        'same_work_dropped_prefix': len(sw.dropped_prefix_indices) if sw else 0,
        # Fix 1(e): recover-before-delete disclosure counts (§-1.3.1 fail-loud).
        'same_work_dropped_captcha_recovered': len(sw.dropped_captcha_recovered) if sw else 0,
        'same_work_dropped_captcha_gap': len(sw.dropped_captcha_gap) if sw else 0,
        # iter-8 Fable Fix 5 (provenance) + Fix 2(a) (duplicate-cg assert) — §-1.3.1 fail-loud.
        'provenance_gap_dropped': len(provenance_gap_disclosure),
        'duplicate_claim_group_ids': len(duplicate_claim_group_ids),
    }

    # Fix 1(e): DISCLOSE every chrome deletion (row count + reason) — §-1.3.1(a) fail-loud,
    # never silent. A RECOVERED drop's work survives via a clean same-work sibling; a GAP
    # drop is a coverage loss disclosed here, never fabricated.
    chrome_deletion_disclosure = []
    if sw is not None:
        for i in sorted(sw.dropped_captcha_indices):
            chrome_deletion_disclosure.append({
                'evidence_id': _eid(i),
                'url': _url(i),
                'title': (_row_field(rows[i], 'title', 'statement')[:120] if 0 <= i < len(rows) else ''),
                'reason': 'chrome_non_source',
                'recovery': ('recovered_via_same_work_sibling'
                             if i in sw.dropped_captcha_recovered else 'coverage_gap'),
            })

    # Fix 11 (Fable): ONE merged, machine-readable deletion disclosure that composition can cite
    # in Methods (§-1.3.1 fail-loud). It unifies the S2 whole-source / line drops (from the
    # sibling s2/summary.json produced by the line screen) with the S3 same-work chrome deletions
    # above — instead of the two living in separate artifacts (s2/disclosure.txt vs this snapshot).
    unified_deletion_disclosure = {
        's3_chrome_deletions': {
            'count': len(chrome_deletion_disclosure),
            'by_reason': {'chrome_non_source': len(chrome_deletion_disclosure)},
            'recovered': consolidation_summary['same_work_dropped_captcha_recovered'],
            'coverage_gap': consolidation_summary['same_work_dropped_captcha_gap'],
            'rows': chrome_deletion_disclosure,
        },
        's2_line_screen': {},
    }
    try:
        s2_summary_path = cp2_path.parent / 'summary.json'
        if s2_summary_path.exists():
            s2s = json.load(s2_summary_path.open(encoding='utf-8'))
            # P3-9 (S2/S3 re-pass iter-5, Fable): the prior by_class did ``len(dict)`` on each
            # cond_* BLOCK (a dict), so it counted the number of DICT KEYS (~19 total), not the
            # actual drop counts — which never reconciled with totals.n_whole_dropped=271. LABEL
            # what each number actually counts and read the REAL numeric fields. LINE drops and
            # WHOLE-SOURCE drops are DISJOINT categories (a line removed from a KEPT source vs a
            # WHOLE source removed) — they are reported separately and NEVER summed. §-1.3.1
            # fail-loud: the reconciliation block asserts the whole-source count matches totals.
            _tot = s2s.get('totals', {}) or {}
            _ca = s2s.get('cond_a_lines_dropped_quoted', {}) or {}
            _cb = s2s.get('cond_b_no_credible_whole_drop', {}) or {}
            _cd = s2s.get('cond_d_scope', {}) or {}
            _cc = s2s.get('cond_c_mixed_partial_keep', {}) or {}
            _line_drops = int(_ca.get('n_dropped_lines', _tot.get('n_dropped_lines', 0)) or 0)
            _whole_drops = int(_cb.get('n_whole_dropped', _tot.get('n_whole_dropped', 0)) or 0)
            unified_deletion_disclosure['s2_line_screen'] = {
                'totals': _tot,
                'by_class': {
                    # LINE-level drops (a line removed from a source that is otherwise KEPT).
                    'line_drops_total': _line_drops,
                    'line_drops_by_reason': _ca.get('by_reason', {}),
                    # WHOLE-SOURCE drops (an entire source removed — chrome / out-of-scope).
                    'whole_source_drops_total': _whole_drops,
                    'whole_source_scope_drops': int(_cd.get('n_source_scope_whole_drops', 0) or 0),
                    'mixed_partial_keep_sources': int(_cc.get('n_partial_sources', 0) or 0),
                    'counts_note': ('line_drops_total and whole_source_drops_total are DISJOINT '
                                    'categories (a LINE removed from a kept source vs a WHOLE '
                                    'source removed); they are reported separately, never summed.'),
                },
                # §-1.3.1 fail-loud reconciliation: whole_source_drops_total MUST equal
                # totals.n_whole_dropped; a mismatch is a disclosure bug, surfaced not hidden.
                'reconciliation': {
                    'totals_n_whole_dropped': int(_tot.get('n_whole_dropped', 0) or 0),
                    'whole_source_drops_reconciles': (
                        _whole_drops == int(_tot.get('n_whole_dropped', 0) or 0)),
                    'totals_n_dropped_lines': int(_tot.get('n_dropped_lines', 0) or 0),
                    'line_drops_reconciles': (
                        _line_drops == int(_tot.get('n_dropped_lines', 0) or 0)),
                },
                'source': 's2/summary.json',
            }
    except Exception as _exc:  # fail-loud but never crash the harness
        unified_deletion_disclosure['s2_line_screen'] = {'error': str(_exc)}

    upstream_sha = hashlib.sha256(cp2_path.read_bytes()).hexdigest()
    envelope = {
        'schema_version': data.get('schema_version', 1),
        'stage': 's3_consolidate',
        'run_id': str(data.get('run_id', '') or ('SWEEP_' + slug)),
        'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'question': question,
        'question_sha': hashlib.sha256(question.encode('utf-8')).hexdigest(),
        'domain': domain,
        'slug': slug,
        'flag_slate': dict(_SLATE),
        'faithfulness_invariant': 'DATA ONLY; no verdict stored; a resume re-runs every gate.',
        'upstream': {'name': cp2_path.name, 'sha256': upstream_sha},
        'adjustments_applied': [],
        'payload': {
            'baskets': baskets,
            'consolidation_summary': consolidation_summary,
            'contradiction_edges': [],
            'same_work_groups': sw_groups_payload,
            'chrome_deletion_disclosure': chrome_deletion_disclosure,
            'deletion_disclosure': unified_deletion_disclosure,  # Fix 11: merged S2+S3
            # iter-8 Fable Fix 5 / Fix 2(a) — §-1.3.1 fail-loud disclosure rows.
            'provenance_gap_disclosure': provenance_gap_disclosure,
            'duplicate_claim_group_id_disclosure': duplicate_claim_group_ids,
        },
    }
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / 'cp3_basket_snapshot.json'
    out_path.write_text(json.dumps(envelope, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print('wrote', out_path, 'baskets', len(baskets))
    print('consolidation_summary', json.dumps(consolidation_summary))
    print('upstream_sha', upstream_sha[:16])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
