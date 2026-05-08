"""I-f12-003 — claim-level diff. Per-section best-Jaccard pairing of shipped sentences; classify on text-overlap × evidence-id-overlap. MVP thresholds (F12 calibration debt)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from polaris_v6.schemas.evidence_contract import EvidenceContract, VerifiedSentence

ClaimVerdict = Literal["agreement", "partial", "disagreement", "only_left", "only_right"]
AGREEMENT_TOKEN_OVERLAP = 0.7
PARTIAL_TOKEN_OVERLAP = 0.3
_PROV_RE = re.compile(r"\[#ev:([^:\]]+):\d+-\d+\]")
_WORD_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class ClaimDiffEntry:
    section_id: str
    verdict: ClaimVerdict
    left_sentence: str | None
    right_sentence: str | None
    shared_evidence_ids: list[str]
    only_left_evidence_ids: list[str]
    only_right_evidence_ids: list[str]
    text_overlap_ratio: float


@dataclass(frozen=True)
class ClaimDiffReport:
    left_run_id: str
    right_run_id: str
    entries: list[ClaimDiffEntry]
    counts_by_verdict: dict[ClaimVerdict, int]


def _eids(s: VerifiedSentence) -> set[str]:
    return {m for tok in s.provenance_tokens for m in _PROV_RE.findall(tok)}


def _entry(sid: str, v: ClaimVerdict, ls: VerifiedSentence | None, rs: VerifiedSentence | None, ov: float) -> ClaimDiffEntry:
    le = _eids(ls) if ls else set()
    re_ = _eids(rs) if rs else set()
    return ClaimDiffEntry(
        sid, v,
        ls.sentence_text if ls else None, rs.sentence_text if rs else None,
        sorted(le & re_), sorted(le - re_), sorted(re_ - le), ov,
    )


def compute_claim_diff(left: EvidenceContract, right: EvidenceContract) -> ClaimDiffReport:
    if left.run_id == right.run_id:
        raise ValueError("compute_claim_diff requires two distinct runs")

    def _by_section(c: EvidenceContract) -> dict[str, list[VerifiedSentence]]:
        out: dict[str, list[VerifiedSentence]] = {}
        for s in c.verified_sentences:
            if s.drop_reason is None and s.verifier_local_pass and s.verifier_global_pass:
                out.setdefault(s.section_id, []).append(s)
        return out

    def _toks(t: str) -> set[str]:
        return set(_WORD_RE.findall(t.lower()))

    def _jac(a: set[str], b: set[str]) -> float:
        return len(a & b) / len(a | b) if (a or b) else 0.0

    def _classify(ov: float, shared: int) -> ClaimVerdict:
        if shared >= 1 and ov >= AGREEMENT_TOKEN_OVERLAP:
            return "agreement"
        if shared == 0 and ov < PARTIAL_TOKEN_OVERLAP:
            return "disagreement"
        return "partial"

    lb, rb = _by_section(left), _by_section(right)
    entries: list[ClaimDiffEntry] = []
    counts: dict[ClaimVerdict, int] = {
        "agreement": 0, "partial": 0, "disagreement": 0, "only_left": 0, "only_right": 0,
    }

    def _add(v: ClaimVerdict, ls: VerifiedSentence | None, rs: VerifiedSentence | None, ov: float) -> None:
        entries.append(_entry(sid, v, ls, rs, ov))
        counts[v] += 1

    for sid in sorted(set(lb) | set(rb)):
        lss, rss = lb.get(sid, []), list(rb.get(sid, []))
        consumed: set[int] = set()
        for ls in lss:
            if not rss:
                _add("only_left", ls, None, 0.0)
                continue
            lt = _toks(ls.sentence_text)
            best, best_ov = -1, -1.0
            for i, rs in enumerate(rss):
                if i in consumed:
                    continue
                ov = _jac(lt, _toks(rs.sentence_text))
                if ov > best_ov:
                    best, best_ov = i, ov
            if best < 0:
                _add("only_left", ls, None, 0.0)
                continue
            rs = rss[best]
            consumed.add(best)
            _add(_classify(best_ov, len(_eids(ls) & _eids(rs))), ls, rs, best_ov)
        for i, rs in enumerate(rss):
            if i not in consumed:
                _add("only_right", None, rs, 0.0)

    return ClaimDiffReport(left.run_id, right.run_id, entries, counts)
