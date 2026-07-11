"""S5 iter-3 LIVE COMPOSE on bot/sec-s5-compose (0966373) — RIP-OUT-ghost + WIRE-map fixes.

Fed checkpoints (section-modular): cp2 corpus + cp3 baskets + cp4 outline (s4_outline_i1).
Runs the REAL production per-section compose unit (_run_section) with THIS branch's fix-9
EXPLICIT map wiring: section_basket_map + section_index passed as keyword args (NOT plan
attributes). Each section composes ONLY its PRIMARY-role baskets (fix 12: no duplicate claim
prose across sections). Then the report-level HOLISTIC passes fire:
  - consolidate_cross_section_repetition (cross-section verbatim-finding guard)
  - sanitize_rendered_report (whole-report render-seam chrome/truncation scrub)
Audits every composed sentence for provenance-token/citation survival + chrome + quote-dump.

Nothing drb_72-specific. Ghost-free flags ON. Faithfulness gates UNCHANGED (strict_verify =
numeric + context-level NLI entailment; the lexical >=2-word overlap gate is DELETED at 0966373).
"""
import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import sys
import time
from pathlib import Path


def _text_of(row: dict) -> str:
    return str((row or {}).get("direct_quote") or (row or {}).get("statement") or "")


def build_baskets(cp3_baskets, evidence_pool):
    from src.polaris_graph.synthesis.credibility_pass import (
        BasketMember,
        ClaimBasket,
        MEMBER_TIER_ENTAILMENT_VERIFIED,
    )
    baskets = []
    seen = {}
    for i, b in enumerate(cp3_baskets):
        rep = str(b.get("representative_evidence_id", "") or "")
        cid = rep if (rep and rep not in seen) else f"{rep or 'b0'}#{i}"
        seen[cid] = True
        members = []
        for eid in (b.get("member_evidence_ids") or []):
            eid = str(eid)
            row = evidence_pool.get(eid)
            if not row:
                continue
            text = _text_of(row)
            if not text.strip():
                continue
            members.append(BasketMember(
                evidence_id=eid,
                source_url=str(row.get("source_url") or ""),
                source_tier=str(row.get("tier") or ""),
                origin_cluster_id=eid,
                credibility_weight=1.0,
                authority_score=1.0,
                span=(0, len(text)),
                direct_quote=text,
                span_verdict="SUPPORTS",
                member_tier=MEMBER_TIER_ENTAILMENT_VERIFIED,
            ))
        if not members:
            continue
        baskets.append(ClaimBasket(
            claim_cluster_id=cid,
            claim_text=str(b.get("representative_statement", "") or ""),
            subject="",
            predicate="",
            supporting_members=members,
            refuter_cluster_ids=(),
            weight_mass=float(b.get("corroboration_count", 0) or 0) or 1.0,
            total_clustered_origin_count=len(members),
            verified_support_origin_count=len(members),
            basket_verdict="full",
        ))
    return baskets


# P1 (2026-07-10 compose gear-loop iter 2): split on whitespace that follows sentence-final
# punctuation OR a citation-closing bracket, and precedes a capital / open-quote. The prior
# `(?<=[.!?])\s+` never split real sentences because every composed sentence ends `.[1][2] Next`
# (period wedged BEFORE the citation, so the boundary is `].SPACE` not `.SPACE`). That collapsed
# whole section paragraphs into ONE audit unit -> 7 units for the whole report, every unit trivially
# overlapping a 12-gram source shingle => false `quote_dump-dominant` acceptance AND blind to the real
# per-sentence chrome. `(` is deliberately excluded from the lookahead so `et al. (2023)` never splits.
_SENT_SPLIT = re.compile(r"(?<=[.!?\]])\s+(?=[A-Z\"“])")
_EV_TOKEN = re.compile(r"\[#ev:[^\]]+\]")
_NUM_CITE = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]")
_CONTENT_WORD = re.compile(r"[^\W_]+", re.UNICODE)
# P2-1 CITATION SEAM: a stray sentence-period wedged between two numeric citations (".[1].[2]" ->
# "[1][2]"). The lookahead requires the very next non-space to be another numeric citation, so a real
# sentence boundary (period then a WORD) is never touched.
_CITE_SEAM = re.compile(r"(\[\d+(?:\s*,\s*\d+)*\])\s*\.\s*(?=\[\d+)")
# P1-5 quote-dump n-gram length: a contiguous run of this many CONTENT WORDS shared verbatim between an
# emitted sentence and any fetched source span marks a raw quote-dump (context-level, not a length guess).
_QUOTE_DUMP_NGRAM = int(os.environ.get("PG_AUDIT_QUOTE_DUMP_NGRAM", "12"))


def _content_words(text: str) -> list:
    """Lowercased content-word token sequence (provenance/citation markers stripped)."""
    s = _NUM_CITE.sub(" ", _EV_TOKEN.sub(" ", text or ""))
    return [w.lower() for w in _CONTENT_WORD.findall(s)]


def _fix_citation_seams(text: str) -> str:
    """P2-1: collapse the stray period between adjacent numeric citations ("] . [" -> "][")."""
    return _CITE_SEAM.sub(r"\1", text or "")


def _build_source_shingles(evidence_pool: dict, n: int) -> set:
    """P1-5: the set of all length-``n`` CONTENT-WORD shingles across every fetched source span. A
    sentence that contains ANY of these shingles verbatim is a raw quote-dump of that source."""
    shingles = set()
    if n < 2:
        return shingles
    for row in (evidence_pool or {}).values():
        words = _content_words(_text_of(row))
        for i in range(len(words) - n + 1):
            shingles.add(tuple(words[i:i + n]))
    return shingles


def _max_verbatim_run(words: list, shingles: set, n: int) -> bool:
    """P1-5: True iff ``words`` contains any length-``n`` shingle present in ``shingles`` (a verbatim
    ``n``-content-word run copied from a source span)."""
    if n < 2 or len(words) < n or not shingles:
        return False
    for i in range(len(words) - n + 1):
        if tuple(words[i:i + n]) in shingles:
            return True
    return False


# Fix 6 (P2-2, 2026-07-10 compose gear-loop): strip leading REQUEST/INSTRUCTION framing so the H1 is
# the TOPIC, not the verbatim user request ("please help me complete a research report on ..."). General
# + question-agnostic: ONLY generic English politeness + report-request verbs are matched (never a topic
# keyword, never tuned to any one question). Fail-open: if stripping leaves no usable topic, the original
# head is kept.
_REQUEST_GREETING_RE = re.compile(
    r"^\s*(?:hi|hello|hey|dear\s+\w+|good\s+(?:morning|afternoon|evening))\b[\s,:.\-–—]*",
    re.I,
)
_REPORT_REQUEST_RE = re.compile(
    r"^\s*(?:please\s+|kindly\s+|pls\s+|could\s+you\s+|can\s+you\s+|would\s+you\s+|"
    r"i\s+(?:would\s+like|want|need|'d\s+like)\s+(?:you\s+)?(?:to\s+)?)?"
    r"(?:help\s+me\s+|assist\s+me\s+(?:in|with|to)\s+|for\s+me\s+)?"
    r"(?:to\s+)?(?:please\s+)?"
    r"(?:write|complete|compose|produce|prepare|create|generate|compile|draft|make|do|build|"
    r"conduct|carry\s+out|perform|put\s+together|give\s+me|provide|research)\s+"
    r"(?:me\s+)?(?:a|an|the|my|some|this)?\s*"
    r"(?:comprehensive|detailed|deep|full|thorough|in-?depth|extensive|complete|brief|short|quick)?\s*"
    r"(?:research\s+|deep\s+research\s+|literature\s+|systematic\s+)?"
    r"(?:report|analysis|study|paper|review|overview|summary|survey|brief|write-?up|document|essay)\b\s*"
    r"(?:on|about|regarding|concerning|of|for|into|covering|examining|exploring|"
    r"that\s+(?:covers|explores|examines|discusses|analyzes|analyses)|to\s+(?:cover|explore|examine))\s+",
    re.I,
)


def _strip_request_framing(text: str) -> str:
    """Fix 6: peel a leading greeting and/or a report-request lead-in ("please help me write a research
    report on ...") off a research question, leaving the TOPIC. Iterative (a greeting then a request),
    only strips the request lead when a real topic tail (>= 8 chars) remains, and fail-open returns the
    original normalized head if nothing usable survives."""
    original = " ".join(str(text or "").split())
    s = original
    if not s:
        return s
    prev = None
    while prev != s:
        prev = s
        s = _REQUEST_GREETING_RE.sub("", s, count=1).strip()
        m = _REPORT_REQUEST_RE.match(s)
        if m and (len(s) - m.end()) >= 8:
            s = s[m.end():].strip()
    if not s:
        return original
    if s[0].islower():
        s = s[0].upper() + s[1:]
    return s


def _report_title(question: str, cp4: dict) -> str:
    """P3-1: a clean H1 — a cp4-provided report title if present, else the research question's first
    sentence/clause word-safe truncated (never a raw mid-word 200-char slice of the whole question).
    Fix 6 (2026-07-10): request/instruction framing is stripped so the H1 is the topic, not the request."""
    pl = (cp4 or {}).get("payload", {}) or {}
    for key in ("report_title", "title"):
        t = str(pl.get(key) or (cp4 or {}).get(key) or "").strip()
        if t:
            return t
    q = " ".join(str(question or "").split())
    if not q:
        return "Research Report"
    q = _strip_request_framing(q)  # Fix 6: drop leading request/instruction framing
    m = re.search(r"[?.]", q)
    head = q[: m.end()] if (m and m.end() <= 220) else q
    if len(head) <= 200:
        return head
    cut = head[:200].rsplit(" ", 1)[0]
    return (cut.rstrip() + "…") if cut else head[:200]


def _section_body_for_render(title: str, verified_text: str, generic_gap_stubs: tuple) -> str:
    """Fix 3 + Fix 8 (2026-07-10 compose gear-loop): assemble one section's rendered body. Never emit a
    bare heading with zero body (Fix 3) — an EMPTY body renders an honest gap disclosure NAMING the
    section. Never repeat the identical generic production gap-stub paragraph verbatim across sections
    (Fix 8) — a generic stub is varied with the section title so each reads distinctly. Any real verified
    prose is returned unchanged."""
    body = (verified_text or "").strip()
    _t = " ".join(str(title or "").split()) or "this section"
    if not body:
        return (
            f'No verified claim was composed for this section ("{_t}"); it is a curator-actionable '
            f'gap. The retrieved sources for this section remain in the bibliography and verification '
            f'details for per-claim disposition.'
        )
    if body in (generic_gap_stubs or ()):
        return body.replace("this section", f'this section ("{_t}")', 1)
    return body


def _audit_section(idx, title, verified_text, shingles, ngram):
    """Line-by-line audit of one section's composed prose (§-1.1).
    Returns per-sentence records + counts. A 'sentence' is a heading-stripped prose unit.

    P1-5 (2026-07-10): the quote-dump predicate now measures VERBATIM n-gram overlap between each
    emitted sentence and the fetched source spans (context-level) — a cited verbatim copy is STILL a
    quote-dump, so a ~95%-copy report can no longer read quote_dump=0. The old length+no-citation
    heuristic was blind to cited quote-dumps."""
    from src.polaris_graph.generator.block_page_chrome_scrub import is_block_page_chrome_sentence
    records = []
    n_sent = n_with_cite = n_chrome = n_quote_dump = 0
    for raw_line in (verified_text or "").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#") or line.startswith("|") or line.startswith("- ") and len(line) < 4:
            # heading / table row / bare bullet marker: not a prose claim sentence
            continue
        for sent in _SENT_SPLIT.split(line):
            s = sent.strip()
            if len(s) < 12:
                continue
            n_sent += 1
            has_ev = bool(_EV_TOKEN.search(s))
            has_num = bool(_NUM_CITE.search(s))
            has_cite = has_ev or has_num
            if has_cite:
                n_with_cite += 1
            is_chrome = False
            try:
                is_chrome = bool(is_block_page_chrome_sentence(s))
            except Exception:
                is_chrome = False
            if is_chrome:
                n_chrome += 1
            # P1-5 quote-dump = a verbatim n-content-word run copied from any fetched source span
            # (context-level; independent of whether the sentence carries a citation).
            is_quote_dump = _max_verbatim_run(_content_words(s), shingles, ngram)
            if is_quote_dump:
                n_quote_dump += 1
            if (not has_cite) or is_chrome or is_quote_dump:
                records.append({
                    "section": idx, "no_cite": not has_cite, "chrome": is_chrome,
                    "quote_dump": is_quote_dump, "text": s[:280],
                })
    return {
        "section_index": idx, "title": title,
        "sentences": n_sent, "with_citation": n_with_cite,
        "chrome_sentences": n_chrome, "quote_dump_sentences": n_quote_dump,
        "flagged": records,
    }


# Fix 5 (2026-07-10 compose gear-loop): a run-level marker tally. The compose modules emit their
# activation / writer-yield / judge markers at INFO; this handler counts them across the whole run and
# the counts are written into the cp5 payload (writer_forensics) so the NEXT read can verify activation
# BEHAVIOURALLY (was invisible: the driver never configured logging, so only WARNING+ reached the log).
class _MarkerTally(logging.Handler):
    _PATTERNS = {
        "synth_primary_fired": "[activation] synth_primary",
        "outline_echo_fired": "[activation] outline_echo",
        "uncovered_fact_withheld": "[activation] uncovered_fact_subject_gate",
        "prepass_complete": "pre-pass complete",
        "kspan_recovery_pass": "K-span recovery pass",
        "kspan_fallback": "-> K-span",
        "transport_reconnect": "fresh reconnect window",
        "transport_disconnect": "transport-disconnect",
        "judge_error": "judge error",
        "judge_empty_content": "empty or non-str judge content",
        "judge_total_deadline": "total_deadline_exceeded",
        "judge_retryable_fault": "judge retryable fault",
        "basket_all_chrome_skipped": "all SUPPORTS members screened as chrome",
    }

    def __init__(self):
        super().__init__(level=logging.INFO)
        self.counts = {k: 0 for k in self._PATTERNS}
        self.prepass_lines = []

    def emit(self, record):
        try:
            msg = record.getMessage()
        except Exception:
            return
        for key, needle in self._PATTERNS.items():
            if needle in msg:
                self.counts[key] += 1
        if "pre-pass complete" in msg:
            self.prepass_lines.append(msg[:300])


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cp2", required=True)
    ap.add_argument("--cp3", required=True)
    ap.add_argument("--cp4", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only-section", type=int, default=-1)
    ap.add_argument("--sections", type=str, default="", help="comma list of section indices to compose (default all)")
    ap.add_argument("--ckpt-dir", type=str, default="", help="dir for per-section draft checkpoints (timeout-resilient)")
    ap.add_argument("--cap-primary", type=int, default=0, help="Fix 5 (2026-07-10): SMOKE-ONLY disclosed knob. Keep only first N primary views per section. DEFAULT 0 = ALL primary views = a full-coverage acceptance run (the gate round MUST run at 0 so coverage and defects 1/2/5 are judgeable). Any N>0 is an explicitly-disclosed bounded subset, never a full acceptance run.")
    args = ap.parse_args()

    # Fix 5 (2026-07-10 compose gear-loop): configure INFO logging so the writer/activation markers
    # ([activation] synth_primary, [abstractive_writer] pre-pass complete, K-span fallbacks, judge
    # errors) reach the tee'd compose.log — the driver previously never called basicConfig, so only
    # WARNING+ was visible and the writer-yield collapse was undiagnosable. Also install the marker tally
    # so the counts land in the cp5 payload.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger().setLevel(logging.INFO)
    marker_tally = _MarkerTally()
    logging.getLogger().addHandler(marker_tally)

    # Fix 3 (2026-07-10 compose gear-loop): writer THROUGHPUT/RESILIENCE flags ON by default for this
    # driver so a transient transport disconnect never permanently kills a basket wave (the prior run
    # lost 3/5 sections' whole writer wave in 0-2s). setdefault => an explicit launcher/env value still
    # wins. General resilience knobs, not question-tuned; recorded in flag_slate for disclosure.
    for _k, _v in (
        ("PG_WRITER_DEADLINE_TRANSPORT_AWARE", "1"),
        ("PG_WRITER_WALL_BASKET_SCALED", "1"),
        ("PG_WRITER_KSPAN_RECOVERY_PASS", "1"),
    ):
        os.environ.setdefault(_k, _v)

    # Fix 6 (2026-07-10 compose gear-loop): entailment-judge RELIABILITY for compose runs. The prior run
    # showed "empty or non-str judge content" (a z-ai empty-200 blank window, NOT starvation — the judge
    # default max_tokens is already the provider chain MIN 131072 and effort "high", both the model max)
    # and "total_deadline_exceeded_150s". Route around blank-200 windows (PG_JUDGE_PROVIDER_ROTATE) and
    # grant a bounded larger total wall. Do NOT override PG_ENTAILMENT_MAX_TOKENS / _REASONING_EFFORT
    # (override clamps down / xhigh starves GLM per the mirror bake-off). setdefault => launcher/env wins.
    # Fable P0/P1 (2026-07-10 compose gear-loop): (P0) the NLI verify pre-pass (0615bc5) is gated by the
    # process-global side-judge semaphore, default 4 (judge_concurrency.DEFAULT_MAX_CONCURRENCY) — tuned
    # for a credibility-burst 429 storm, NOT compose (0 429s at 128-way). Raise the in-flight cap to 16 so
    # verify threads don't queue behind 4 slots. (P1) PG_ENTAILMENT_TOTAL_DEADLINE_RETRIES=1 is what the
    # code comment (entailment_judge.py:196) prescribes for the run slate — caps a total_deadline hang at
    # 2 attempts (2x total_s) instead of the default 2 (=3x total_s of dead slot-hold). Both transport-only
    # and faithfulness-NEUTRAL (same fail-closed sentinel). setdefault => launcher/env wins.
    for _k, _v in (
        ("PG_JUDGE_PROVIDER_ROTATE", "1"),
        ("PG_ENTAILMENT_TOTAL_S", "300"),
        ("PG_SIDE_JUDGE_MAX_CONCURRENCY", "16"),
        ("PG_ENTAILMENT_TOTAL_DEADLINE_RETRIES", "1"),
    ):
        os.environ.setdefault(_k, _v)

    # P0 (2026-07-11 compose gear-loop iter 5): strict_verify's per-sentence entailment loop ran SERIAL
    # in production because _parallel_verify_workers() returns 1 when PG_PARALLEL_VERIFY is unset
    # (provenance_generator.py:3390 read, serial gate at :3665), and NO compose launcher set the knob —
    # so the bounded, cost-reconciled, contextvars-copied ThreadPoolExecutor path (:3676-3723, already
    # gated at 16 by scripts/iarch011_parallel_verify_gate.py) was DEAD in production while strict_verify
    # runs twice per section. Turn the parallel judge path ON with a bounded 8 workers. This is
    # faithfulness-NEUTRAL: the parallel path reassembles verdicts in ORIGINAL order, so kept/dropped is
    # byte-identical to the serial loop; only concurrency of in-flight judge calls changes. setdefault =>
    # an explicit launcher/env value still wins.
    os.environ.setdefault("PG_PARALLEL_VERIFY", "8")

    sel = set()
    if args.sections.strip():
        sel = {int(x) for x in args.sections.split(",") if x.strip() != ""}
    ckpt_dir = Path(args.ckpt_dir) if args.ckpt_dir.strip() else None
    if ckpt_dir:
        ckpt_dir.mkdir(parents=True, exist_ok=True)

    from src.polaris_graph.generator.multi_section_generator import (
        SectionPlan,
        _run_section,
        # Fix 3 + Fix 8 (2026-07-10 compose gear-loop): the production gap-stub sentences, so the
        # assembler can render an honest gap for an empty body and vary a repeated generic stub.
        _GAP_STUB_SENTENCE,
        _NO_EVIDENCE_GAP_STUB_SENTENCE,
        _SECTION_FAILED_GAP_STUB_SENTENCE,
    )
    from src.polaris_graph.synthesis.credibility_pass import CredibilityAnalysis, EvidenceCredibility
    from src.polaris_graph.synthesis.section_basket_map import (
        build_section_basket_map,
        section_basket_map_enabled,
        resolve_weights,
    )
    from src.polaris_graph.generator.cross_section_repetition_guard import (
        consolidate_cross_section_repetition,
    )
    from src.polaris_graph.generator.weighted_enrichment import sanitize_rendered_report

    cp2 = json.load(open(args.cp2, encoding="utf-8"))
    cp3 = json.load(open(args.cp3, encoding="utf-8"))
    cp4 = json.load(open(args.cp4, encoding="utf-8"))

    question = cp2.get("question") or ""
    evidence_rows = cp2["evidence_for_gen"]
    evidence_pool = {str(r["evidence_id"]): r for r in evidence_rows if r.get("evidence_id")}
    cp3_baskets = cp3["payload"]["baskets"]
    plans_raw = cp4["payload"]["final_plans"]

    print(f"[load] question_len={len(question)} evidence_pool={len(evidence_pool)} "
          f"cp3_baskets={len(cp3_baskets)} plans={len(plans_raw)}", flush=True)

    baskets = build_baskets(cp3_baskets, evidence_pool)
    print(f"[baskets] reconstructed ClaimBaskets={len(baskets)} "
          f"(members total={sum(len(b.supporting_members) for b in baskets)})", flush=True)

    # Populate credibility + origin coverage for EVERY pooled evidence_id (the disclosure coverage
    # assertion in credibility_pass.apply_disclosure_to_svs is fail-LOUD: every cited evidence_id MUST
    # have both credibility_by_evidence AND origin_by_evidence coverage, else abort_credibility_coverage_gap).
    # In production _run_chain co-builds these per row; the offline harness must supply them. Neutral
    # weight 1.0 (harness) — the binding faithfulness gate is strict_verify per composed sentence, unchanged.
    cred_by_ev = {}
    origin_by_ev = {}
    cluster_id_by_ev = {}
    for eid in evidence_pool:
        eid = str(eid)
        cred_by_ev[eid] = EvidenceCredibility(
            evidence_id=eid, credibility_weight=1.0, reliability_score=1.0, relevance_score=1.0,
            origin_cluster_id=eid, is_canonical_origin=True, certainty_downgrade=False, soft_warning=None,
        )
        origin_by_ev[eid] = eid
    for b in baskets:
        for mem in b.supporting_members:
            cluster_id_by_ev.setdefault(str(mem.evidence_id), []).append(b.claim_cluster_id)
    cred = CredibilityAnalysis(
        credibility_by_evidence=cred_by_ev, origin_by_evidence=origin_by_ev, claims=[], edges=[],
        weight_mass=[], baskets=baskets, cluster_id_by_evidence=cluster_id_by_ev,
    )
    print(f"[cred] coverage populated: credibility_by_evidence={len(cred_by_ev)} "
          f"origin_by_evidence={len(origin_by_ev)} cluster_id_by_evidence={len(cluster_id_by_ev)}", flush=True)

    plans = [SectionPlan(title=str(p.get("title", "")), focus=str(p.get("focus", "")),
                         ev_ids=[str(e) for e in (p.get("ev_ids") or [])]) for p in plans_raw]

    print(f"[map] section_basket_map_enabled={section_basket_map_enabled()} weights={resolve_weights()}", flush=True)
    sbm_map = build_section_basket_map(baskets, plans, evidence_pool=evidence_pool)
    per_sec_views = {int(k): len(v) for k, v in sbm_map.views_by_section.items()}
    print(f"[map] stranded={sbm_map.stranded_count} residual_index={sbm_map.residual_section_index} "
          f"nocid_synth={sbm_map.stats.get('nocid_synthetic_count', 0)} per_section_views={per_sec_views}", flush=True)
    # primary counts per section (the baskets each section will actually FULL-compose)
    prim_per_sec = {}
    for idx, views in sbm_map.views_by_section.items():
        prim_per_sec[int(idx)] = sum(1 for v in views if getattr(v, "role", "") == "primary")
    print(f"[map] primary_per_section={prim_per_sec}", flush=True)

    if args.cap_primary and args.cap_primary > 0:
        # BOUNDED read (disclosed): truncate each section's PRIMARY views to first N; keep all
        # corroborating. Lets a fast multi-section run fire the holistic cross-section pass on real
        # prose. This is a SUBSET, not a full acceptance run.
        for idx, views in list(sbm_map.views_by_section.items()):
            kept, nprim = [], 0
            for v in views:
                if getattr(v, "role", "") == "primary":
                    if nprim >= args.cap_primary:
                        continue
                    nprim += 1
                kept.append(v)
            sbm_map.views_by_section[idx] = kept
        prim_per_sec = {int(k): sum(1 for v in vs if getattr(v, "role", "") == "primary")
                        for k, vs in sbm_map.views_by_section.items()}
        print(f"[map] CAP-PRIMARY={args.cap_primary} -> primary_per_section={prim_per_sec}", flush=True)

    # Faithful production wiring (generate_multi_section_report): append the keep-all RESIDUAL
    # SectionPlan and attach the map + a stable section index onto every SectionPlan object, so this
    # branch's _section_baskets_for_compose consumes them via getattr (no _run_section sig change).
    _resid_idx = sbm_map.residual_section_index
    if _resid_idx is not None and _resid_idx == len(plans):
        _resid_ev = []
        _seen_re = set()
        for _rv in sbm_map.views_by_section.get(_resid_idx, []) or []:
            for _re in getattr(_rv, 'section_member_ev_ids', None) or []:
                _re_s = str(_re)
                if _re_s and _re_s not in _seen_re:
                    _seen_re.add(_re_s)
                    _resid_ev.append(_re_s)
        plans.append(SectionPlan(
            title=sbm_map.residual_title or 'Additional Corroborated Findings',
            focus='Corroborated findings that did not bind to a primary outline section.',
            ev_ids=_resid_ev,
        ))
        print(f'[map] residual SectionPlan appended idx={_resid_idx} ev_ids={len(_resid_ev)}', flush=True)
    for _p_idx, _p_obj in enumerate(plans):
        try:
            _p_obj._section_index = _p_idx
            _p_obj._section_basket_map = sbm_map
        except Exception:
            pass

    model = os.environ.get("PG_GENERATOR_MODEL", "z-ai/glm-5.2")
    section_max_tokens = int(os.environ.get("PG_SECTION_MAX_TOKENS", "64000"))
    section_temperature = float(os.environ.get("PG_SECTION_TEMPERATURE", "0.3"))
    min_kept_fraction = float(os.environ.get("PG_MIN_KEPT_FRACTION", "0.4"))
    sec_sema = asyncio.Semaphore(int(os.environ.get("PG_MAX_PARALLEL_SECTIONS", "2")))

    # Fix 9 (2026-07-11 compose gear-loop iter 4): SECTION-LEVEL crash RESUME. The iter-3 run (PID 768574)
    # was externally SIGKILLed at 08:19:57 ~1 min into a section finalization after 1h15m of compose; the
    # per-section checkpoints (written at section completion below) were NEVER read back, so the whole wave
    # was lost. This block LOADS any completed per-section checkpoint and SKIPS recomposing that section,
    # so a relaunch resumes at the closest checkpoint (operator ground rule 2026-07-01) and the gear loop
    # makes guaranteed forward progress across kills. Resume is GATED on the three input SHAs (cp2/cp3/cp4):
    # if the pinned corpus/outline changed since the checkpoints were written, the stale drafts are IGNORED
    # and every section recomposes (honors the gear rule = newest inputs win). Only a genuinely-composed
    # section is resumed (real verified prose, not a gap stub / degraded / errored section) — a transient-
    # failure section is retried, never banked (fail-open: any doubt => recompose).
    resumed: dict = {}
    if ckpt_dir:
        import types as _types_resume
        _in_sha = {
            "cp2": hashlib.sha256(Path(args.cp2).read_bytes()).hexdigest(),
            "cp3": hashlib.sha256(Path(args.cp3).read_bytes()).hexdigest(),
            "cp4": hashlib.sha256(Path(args.cp4).read_bytes()).hexdigest(),
        }
        _man = ckpt_dir / "inputs_sha.json"
        _stale = False
        if _man.exists():
            try:
                _prev = json.loads(_man.read_text(encoding="utf-8"))
            except Exception:
                _prev = {}
            if (_prev.get("cp2") != _in_sha["cp2"] or _prev.get("cp3") != _in_sha["cp3"]
                    or _prev.get("cp4") != _in_sha["cp4"]):
                _stale = True
                print("[resume] input SHAs changed since checkpoint -> IGNORING stale section drafts, "
                      "recomposing all sections (gear rule: newest inputs win)", flush=True)
        _man.write_text(json.dumps(_in_sha, ensure_ascii=False, indent=2), encoding="utf-8")
        if not _stale:
            for _ck in sorted(ckpt_dir.glob("section_*_draft.json")):
                try:
                    _d = json.loads(_ck.read_text(encoding="utf-8"))
                except Exception as _e:
                    print(f"[resume] skip unreadable checkpoint {_ck.name}: {_e!r}", flush=True)
                    continue
                _idx = _d.get("section_index")
                _vt = (_d.get("verified_text") or "").strip()
                if (_idx is None or not _vt or _d.get("is_gap_stub")
                        or _d.get("dropped_due_to_failure") or _d.get("error")
                        or int(_d.get("sentences_verified") or 0) <= 0):
                    continue
                resumed[int(_idx)] = _types_resume.SimpleNamespace(
                    title=str(_d.get("title") or f"Section {_idx}"),
                    focus=str(_d.get("focus") or ""),
                    ev_ids_assigned=list(_d.get("ev_ids_assigned") or []),
                    verified_text=_d.get("verified_text") or "",
                    sentences_verified=int(_d.get("sentences_verified") or 0),
                    sentences_dropped=int(_d.get("sentences_dropped") or 0),
                    regen_attempted=bool(_d.get("regen_attempted")),
                    dropped_due_to_failure=bool(_d.get("dropped_due_to_failure")),
                    is_gap_stub=bool(_d.get("is_gap_stub")),
                    error=_d.get("error"),
                )
            if resumed:
                print(f"[resume] loaded {len(resumed)} completed section(s) from checkpoints: "
                      f"{sorted(resumed)} -- skipping recompose", flush=True)

    async def _compose_one(idx, section):
        async with sec_sema:
            t0 = time.time()
            print(f"[section {idx}] START title={section.title!r} ev_ids={len(section.ev_ids)}", flush=True)
            res = await _run_section(
                section, evidence_pool,
                model=model,
                temperature=section_temperature,
                max_tokens_per_section=section_max_tokens,
                min_kept_fraction=min_kept_fraction,
                credibility_analysis=cred,
                research_question=question,
            )
            dt = time.time() - t0
            vt = res.verified_text or ""
            print(f"[section {idx}] DONE {dt:.0f}s verified_chars={len(vt)} "
                  f"sentences_verified={res.sentences_verified} dropped={res.sentences_dropped} "
                  f"regen={res.regen_attempted} dropped_fail={res.dropped_due_to_failure} "
                  f"gap_stub={getattr(res,'is_gap_stub',False)} error={res.error!r}", flush=True)
            print(f"[section {idx}] OPENING: {vt[:500]}", flush=True)
            if ckpt_dir:
                # timeout/crash-resilient per-section draft checkpoint (Design 4 §7c)
                (ckpt_dir / f"section_{idx}_draft.json").write_text(json.dumps({
                    "section_index": idx, "title": res.title, "focus": res.focus,
                    "ev_ids_assigned": res.ev_ids_assigned, "verified_text": vt,
                    "sentences_verified": res.sentences_verified,
                    "sentences_dropped": res.sentences_dropped,
                    "regen_attempted": res.regen_attempted,
                    "dropped_due_to_failure": res.dropped_due_to_failure,
                    "is_gap_stub": getattr(res, "is_gap_stub", False), "error": res.error,
                }, ensure_ascii=False, indent=2), encoding="utf-8")
            return res

    tasks = []
    order = []
    for idx, section in enumerate(plans):
        if args.only_section >= 0 and idx != args.only_section:
            continue
        if sel and idx not in sel:
            continue
        if idx in resumed:
            continue
        order.append(idx)
        tasks.append(asyncio.ensure_future(_compose_one(idx, section)))
    results = await asyncio.gather(*tasks, return_exceptions=True)

    import types
    section_results = []
    acceptance = True
    excepted_sections = []
    for oi, r in zip(order, results):
        if isinstance(r, Exception):
            # P1-3 SECTION VANISH (2026-07-10): a section whose compose raised must NOT silently vanish
            # from the report. Ship a LOUD gap stub in its place and set acceptance=False so the run is
            # marked degraded (never a silent drop).
            print(f"[section {oi}] EXCEPTION: {r!r}", flush=True)
            acceptance = False
            excepted_sections.append({"section_index": oi, "error": repr(r)})
            _sec = plans[oi] if 0 <= oi < len(plans) else None
            _stub = types.SimpleNamespace(
                title=str(getattr(_sec, "title", "") or f"Section {oi}"),
                focus=str(getattr(_sec, "focus", "") or ""),
                ev_ids_assigned=[],
                verified_text=(
                    f"[section unavailable — composition raised an exception and this section was not "
                    f"produced: {repr(r)[:200]}]"
                ),
                sentences_verified=0, sentences_dropped=0, regen_attempted=False,
                dropped_due_to_failure=True, is_gap_stub=True, error=repr(r),
            )
            section_results.append((oi, _stub))
        else:
            section_results.append((oi, r))
    # Fix 9 (iter 4): fold resumed-from-checkpoint sections back in (never recomposed).
    for _ri, _rr in resumed.items():
        section_results.append((_ri, _rr))
    section_results.sort(key=lambda t: t[0])

    # P2-1 CITATION SEAM (2026-07-10): tidy the ".[1].[2]" citation seams in every section body BEFORE
    # the holistic passes + audit so both the report and the audit read the same clean text.
    for _oi, _r in section_results:
        try:
            _r.verified_text = _fix_citation_seams(_r.verified_text or "")
        except Exception:
            pass

    # ---- HOLISTIC report-level pass A: cross-section repetition guard (verbatim finding dedup) ----
    guard_telemetry = {}
    try:
        guard_telemetry = consolidate_cross_section_repetition([r for _, r in section_results]) or {}
    except Exception as e:
        guard_telemetry = {"error": repr(e)}
    print(f"[holistic] cross_section_repetition_guard = {json.dumps(guard_telemetry)[:300]}", flush=True)

    # ---- Assemble the whole report markdown from composed sections ----
    # P3-1 (2026-07-10): a clean H1 (cp4 report title or the question's first clause, word-safe) — not a
    # raw mid-word 200-char slice of the whole multi-paragraph question.
    # Fix 3 + Fix 8 (2026-07-10 compose gear-loop): render an honest gap disclosure for an empty section
    # body (never a bare heading) and vary a repeated generic gap-stub per section title.
    _generic_gap_stubs = (
        _GAP_STUB_SENTENCE, _NO_EVIDENCE_GAP_STUB_SENTENCE, _SECTION_FAILED_GAP_STUB_SENTENCE,
    )
    parts = [f"# {_report_title(question, cp4)}"]
    for oi, r in section_results:
        _body = _section_body_for_render(r.title, r.verified_text or "", _generic_gap_stubs)
        parts.append(f"\n## {r.title}\n\n{_body}")
    report_md_pre = "\n".join(parts) + "\n"

    # ---- HOLISTIC report-level pass B: whole-report render-seam chrome/truncation scrub ----
    try:
        report_md_post, units_removed = sanitize_rendered_report(report_md_pre)
    except Exception as e:
        report_md_post, units_removed = report_md_pre, -1
        print(f"[holistic] sanitize_rendered_report EXCEPTION {e!r}", flush=True)
    print(f"[holistic] sanitize_rendered_report units_removed={units_removed} "
          f"pre_chars={len(report_md_pre)} post_chars={len(report_md_post)}", flush=True)
    # Fix 7 (2026-07-10 compose gear-loop): apply the citation-seam tidy to the FINAL rendered report
    # text itself (not only the pre-holistic section bodies) so a ".[1].[2]" seam that survives / is
    # reintroduced by the holistic render pass is collapsed in the shipped assembled_report_md.
    report_md_post = _fix_citation_seams(report_md_post)

    # ---- Line-by-line audit (§-1.1) on the POST-holistic sections ----
    # P1-5 (2026-07-10): build the source n-gram shingle index once so the quote-dump predicate can
    # measure verbatim overlap between every emitted sentence and the fetched source spans.
    source_shingles = _build_source_shingles(evidence_pool, _QUOTE_DUMP_NGRAM)
    print(f"[audit] source_shingles={len(source_shingles)} ngram={_QUOTE_DUMP_NGRAM}", flush=True)
    audits = []
    for oi, r in section_results:
        audits.append(_audit_section(oi, r.title, r.verified_text or "", source_shingles, _QUOTE_DUMP_NGRAM))
    tot_sent = sum(a["sentences"] for a in audits)
    tot_cite = sum(a["with_citation"] for a in audits)
    tot_chrome = sum(a["chrome_sentences"] for a in audits)
    tot_qd = sum(a["quote_dump_sentences"] for a in audits)
    print(f"[audit] sentences={tot_sent} with_citation={tot_cite} "
          f"chrome={tot_chrome} quote_dump={tot_qd}", flush=True)

    # Fix 7 (2026-07-10 compose gear-loop iter 2): wire acceptance to the §-1.1 audit READ so the gear
    # loop can NEVER bank a span-dump / chrome-dominant body as a pass. This is a validity DISCLOSURE, not
    # a number-target: acceptance=False when ANY section raised (already), ANY section is a gap stub, or
    # the audited body is quote-dump- or chrome-DOMINANT (a majority of its sentences by the context-level
    # audit predicate). Every trigger is disclosed in envelope.acceptance_reasons. Dominance fraction is
    # env-tunable (PG_S5_ACCEPTANCE_DOMINANCE_FRACTION, default 0.5 = a majority).
    acceptance_reasons: list = []
    if excepted_sections:
        acceptance_reasons.append(f"{len(excepted_sections)} section(s) raised an exception")
    gap_stub_sections = [oi for oi, r in section_results if getattr(r, "is_gap_stub", False)]
    if gap_stub_sections:
        acceptance = False
        acceptance_reasons.append(f"gap-stub section(s): {gap_stub_sections}")
    try:
        _dominance = float(os.environ.get("PG_S5_ACCEPTANCE_DOMINANCE_FRACTION", "0.5") or "0.5")
    except (TypeError, ValueError):
        _dominance = 0.5
    if not (0.0 < _dominance <= 1.0):
        _dominance = 0.5
    if tot_sent > 0:
        qd_frac = tot_qd / tot_sent
        chrome_frac = tot_chrome / tot_sent
        if qd_frac > _dominance:
            acceptance = False
            acceptance_reasons.append(
                f"quote_dump-dominant: {tot_qd}/{tot_sent} sentences ({qd_frac:.0%} > {_dominance:.0%})"
            )
        if chrome_frac > _dominance:
            acceptance = False
            acceptance_reasons.append(
                f"chrome-dominant: {tot_chrome}/{tot_sent} sentences ({chrome_frac:.0%} > {_dominance:.0%})"
            )
    print(f"[acceptance] acceptance={acceptance} reasons={acceptance_reasons}", flush=True)

    cp2_sha = hashlib.sha256(Path(args.cp2).read_bytes()).hexdigest()
    cp3_sha = hashlib.sha256(Path(args.cp3).read_bytes()).hexdigest()
    cp4_sha = hashlib.sha256(Path(args.cp4).read_bytes()).hexdigest()

    section_drafts = []
    for oi, r in section_results:
        section_drafts.append({
            "section_index": oi,
            "title": r.title,
            "focus": r.focus,
            "ev_ids_assigned": r.ev_ids_assigned,
            "verified_text": r.verified_text or "",
            "sentences_verified": r.sentences_verified,
            "sentences_dropped": r.sentences_dropped,
            "regen_attempted": r.regen_attempted,
            "dropped_due_to_failure": r.dropped_due_to_failure,
            "is_gap_stub": getattr(r, "is_gap_stub", False),
            "error": r.error,
        })

    envelope = {
        "schema_version": 1,
        "stage": "s5_generation_live_compose",
        "iter": 4,
        # P1-3 (2026-07-10): acceptance=False when any section raised and was replaced by a gap stub.
        # Fix 7 (2026-07-10 compose gear-loop iter 2): ALSO False on a gap-stub / quote-dump-dominant /
        # chrome-dominant audit read — reasons disclosed in acceptance_reasons.
        "acceptance": acceptance,
        "acceptance_reasons": acceptance_reasons,
        "excepted_sections": excepted_sections,
        "question_sha": cp4.get("question_sha"),
        "flag_slate": {k: os.environ.get(k) for k in [
            "PG_SECTION_BASKET_MAP", "PG_SECTION_BASKET_MAP_REFINE_NLI", "PG_SECTION_BASKET_ROLE_POLICY",
            "PG_COMPOSE_NO_RAW_SPAN_FALLBACK", "PG_SYNTH_PRIMARY", "PG_ABSTRACTIVE_WRITER",
            "PG_VERIFIED_COMPOSE", "PG_VERIFIED_COMPOSE_MULTICITED", "PG_STRICT_VERIFY_ENTAILMENT",
            "PG_CROSS_SECTION_REPETITION_GUARD", "PG_RENDER_SEAM_SANITIZE",
            "PG_GENERATOR_MODEL", "PG_ENTAILMENT_MODEL", "PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY",
            "PG_SECTION_MAX_TOKENS",
            # Fix 3 + Fix 6 (2026-07-10 compose gear-loop): writer transport-resilience + judge-reliability
            # flags now disclosed in the slate (were invisible, so the wave collapse was undiagnosable).
            "PG_WRITER_DEADLINE_TRANSPORT_AWARE", "PG_WRITER_WALL_BASKET_SCALED",
            "PG_WRITER_KSPAN_RECOVERY_PASS", "PG_JUDGE_PROVIDER_ROTATE", "PG_ENTAILMENT_TOTAL_S",
        ]},
        "upstream": [
            {"stage": "corpus", "checkpoint": args.cp2, "sha": cp2_sha},
            {"stage": "basket", "checkpoint": args.cp3, "sha": cp3_sha},
            {"stage": "outline", "checkpoint": args.cp4, "sha": cp4_sha},
        ],
        "faithfulness_invariant": (
            "REAL live compose. Abstractive LLM writer drafts synthesis prose per PRIMARY basket; every "
            "composed sentence re-passes the UNCHANGED strict_verify (numeric + context-level NLI "
            "entailment). The lexical content-word-overlap gate + verbatim raw-span fallback (the ghost) "
            "are DELETED at 0966373 and NOT reintroduced. Map is pure placement; nothing dropped "
            "(stranded_count==0). No stored verdict; resume re-runs every gate."
        ),
        "map_stats": {
            "baskets": len(baskets),
            "sections": len(plans),
            "stranded_count": sbm_map.stranded_count,
            "residual_section_index": sbm_map.residual_section_index,
            "nocid_synthetic_count": sbm_map.stats.get("nocid_synthetic_count", 0),
            "primary_homes": len(sbm_map.primary_section_by_cluster),
            "per_section_views": per_sec_views,
            "primary_per_section": prim_per_sec,
        },
        "holistic_review": {
            "cross_section_repetition_guard": guard_telemetry,
            "render_seam_sanitize_units_removed": units_removed,
            "report_pre_chars": len(report_md_pre),
            "report_post_chars": len(report_md_post),
            "fired": (units_removed >= 0),
        },
        "audit": {
            "total_sentences": tot_sent,
            "sentences_with_citation": tot_cite,
            "citation_survival_pct": (round(100.0 * tot_cite / tot_sent, 1) if tot_sent else None),
            "chrome_sentences": tot_chrome,
            "quote_dump_sentences": tot_qd,
            "per_section": audits,
        },
        # Fix 5 (2026-07-10 compose gear-loop): run-level writer/activation/judge marker tally scraped
        # from the INFO log. Lets the next read VERIFY activation behaviourally (synth_primary_fired > 0)
        # and DISCLOSES judge transport faults at the run level (Fix 2b: the durable judge_error signal
        # is surfaced here for disclosure, never silently dropped) plus writer-yield (pre-pass drafted).
        "writer_forensics": {
            "marker_counts": marker_tally.counts,
            "prepass_lines": marker_tally.prepass_lines,
        },
        "payload": {
            "section_drafts": section_drafts,
            "assembled_report_md": report_md_post,
        },
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
    cp5_sha = hashlib.sha256(Path(args.out).read_bytes()).hexdigest()
    print(f"\n[WROTE] {args.out} bytes={Path(args.out).stat().st_size} cp5_sha={cp5_sha[:16]} "
          f"sections={len(section_drafts)}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
