"""SELECT+WEIGH v2 — LINE-LEVEL three-way select/drop reader (S2).

Operator sharpening 2026-07-10 (Design 1 §6, `.codex/I-arch-plan/01_offtopic_subquery.md`;
master plan S2 row). This leaf module reads EVERY line of each SURVIVING source and decides,
per LINE, KEEP vs a DROP-reason in {off_topic, out_of_scope, junk}. A source that is 80%
relevant keeps its 80%; only a source that is 100% off/out/junk drops whole — and even then
only via the EXISTING two-key channels (V5) with the marquee exemption intact.

§-1.3 RECONCILIATION (the axis split, LOCKED DNA):
  * CREDIBILITY = WEIGHT, never drop. A credible, on-topic, in-scope source is NEVER
    dropped; a low tier just carries low weight. ``credibility_pass`` is UNTOUCHED here.
  * EXACTLY THREE DROP TRIGGERS, decided per LINE, fail-open, disclosed:
      1. OFF_TOPIC — off BOTH the row's own sub-query AND the main question (dual-anchor,
         mirrors ``topic_relevance_gate`` D3).
      2. OUT_OF_SCOPE — outside the user's EXPLICIT RunConfig scope (date / recency / source
         type / peer-reviewed-only / geography / language / author). The USER's own hard
         filter — armed ONLY when an explicit scope is present (activation rule, V3); no
         explicit scope ⇒ ZERO out_of_scope drops anywhere.
      3. JUNK — chrome / nav / cookie / subscribe / related-articles boilerplate welded
         into an otherwise-real page.
  * FAIL-OPEN on every doubt (line KEPT); every drop DISCLOSED with the line QUOTED.
  * The FAITHFULNESS ENGINE is UNTOUCHED. The screen runs at S2 BEFORE generation, so it can
    only SHRINK the groundable text — a claim citing a dropped line fails strict_verify;
    nothing that would not have passed before can pass now.

PURE LEAF (LAW V, LAW VII): no network, no faithfulness-engine import, no row mutation in
the judge path (the caller applies the result to a COPY). The LLM is INJECTED
(``llm_callable: str -> str``), so the whole module is unit-testable with a stub, no key.
Every knob is an env flag (LAW VI). Kill-switch ``PG_LINE_SCREEN`` DEFAULT OFF ⇒
byte-identical (no line is ever touched).

REUSE (single source of truth — do NOT re-implement):
  * widest-body probe + marquee + chrome-nonsource accessors — ``topic_relevance_gate``
    (``_CHROME_BODY_FIELDS`` :146-149, ``_row_is_marquee_anchor`` :238-258,
    ``_row_is_chrome_nonsource`` :152-177, ``_row_title_text`` :215-225).
  * deterministic chrome-line vocabulary — ``shell_detector.SHELL_COOCCURRENCE`` :157-184
    (safe at LINE granularity per the :144-152 note) + ``is_cited_span_shell`` :378 as the
    whole-body junk concurrence key.
  * date out-of-window predicate — ``evidence_selector._row_out_of_window_ym`` :999-1021
    (month precision, fail-open on undated).
  * source-type / peer-reviewed / jurisdiction facets — ``scope_facet_classifier``
    ``classify_source_facets`` :207.
  * explicit-scope extraction — ``intake_constraint_extractor`` ``extract_user_constraints``
    :361, ``extract_scope_constraints`` :1035.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

_LOGGER = logging.getLogger("polaris_graph.line_screen")

# ── env knobs (LAW VI) ───────────────────────────────────────────────────────
_ENV_ENABLED = "PG_LINE_SCREEN"                        # kill-switch, DEFAULT OFF
_ENV_PARALLEL = "PG_LINE_SCREEN_PARALLEL"              # default 1 (serial); slate 32
_ENV_MAX_LINES_PER_CALL = "PG_LINE_SCREEN_MAX_LINES_PER_CALL"   # default 120
_ENV_MIN_LINE_CHARS = "PG_LINE_SCREEN_MIN_LINE_CHARS"          # default 24
_ENV_SCOPE = "PG_LINE_SCREEN_SCOPE"                   # out_of_scope leg; auto-inert w/o scope
_ENV_SUBQ_MIN_TOKENS = "PG_LINE_SCREEN_SUBQ_MIN_TOKENS"        # usable-anchor floor, default 3
_ENV_MAX_TOKENS = "PG_LINE_SCREEN_MAX_TOKENS"        # judge completion budget (harness/prod)
_ENV_MODEL = "PG_LINE_SCREEN_MODEL"                 # judge model (harness/prod)

_OFF_VALUES = frozenset({"0", "false", "no", "off", "disabled", ""})

_DEFAULT_MAX_LINES_PER_CALL = 120
_DEFAULT_MIN_LINE_CHARS = 24
_DEFAULT_SUBQ_MIN_TOKENS = 3

# Verdict tokens (module constants — allowed per §4.1).
KEEP = "KEEP"
OFF_TOPIC = "OFF_TOPIC"
OUT_OF_SCOPE = "OUT_OF_SCOPE"
JUNK = "JUNK"
# S2/S3 re-pass Fable Fix 2: NON_CLAIM — a SEMANTIC "this line asserts nothing about the world"
# verdict for boilerplate that is REAL prose (so it is not JUNK chrome) yet claim-empty: TOC /
# page-number runs, acknowledgments, dedications, license / copyright lines, share / alert /
# footer text, citation-metadata blocks, figure-axis / legend dumps, journal mastheads, ad copy.
# It is a SPAN drop (drop the line, KEEP the source, §-1.3.1), decided by the semantic line judge,
# NEVER a keyword blocklist. Kept OUT of ``_DROP_REASONS`` so the whole-drop dominant-reason /
# two-key concurrence stays conservative (a 100%-NON_CLAIM source fails OPEN to keep-all unless a
# chrome/shell key concurs) — the boilerplate root fix is stopping the LINE from becoming a
# finding, not deleting the source.
NON_CLAIM = "NON_CLAIM"
_DROP_REASONS = (OFF_TOPIC, OUT_OF_SCOPE, JUNK)
# All recognised line-drop verdicts (span drops), including the claim-bearing gate.
_LINE_DROP_REASONS = (OFF_TOPIC, OUT_OF_SCOPE, JUNK, NON_CLAIM)

# Provenance LABELS that are NOT a natural-language sub-query — mirrors Design 1 §3 D2's
# ``_usable_subquery_anchor`` reject list (topic_relevance_gate D2). A label must degrade to
# main-question-only judging, never poison the prompt as if it were a sub-query.
_ANCHOR_LABEL_TOKENS = (
    "need_type_backend", "domain_backend", "primary_trial_doi_seed",
)
_ANCHOR_LABEL_SUBSTRINGS = ("required_entity", "anchor")


# ─────────────────────────────────────────────────────────────────────────────
# Flags
# ─────────────────────────────────────────────────────────────────────────────
def line_screen_enabled() -> bool:
    """Kill-switch ``PG_LINE_SCREEN``. DEFAULT OFF ⇒ byte-identical (no line touched).
    Read at call time so tests / the harness toggle without re-import."""
    return os.environ.get(_ENV_ENABLED, "0").strip().lower() not in _OFF_VALUES


def claim_bearing_gate_enabled() -> bool:
    """Kill-switch ``PG_LINE_SCREEN_CLAIM_GATE`` for the NON_CLAIM (claim-bearing) verdict
    (DEFAULT ON — S2/S3 re-pass Fable Fix 2). ON => the line judge is OFFERED a NON_CLAIM
    verdict for real-prose-but-claim-empty boilerplate (TOC / acknowledgments / dedications /
    license-copyright / share-footer / citation-metadata / figure-legend / masthead / ad copy),
    which SPAN-drops the line (keep the source, §-1.3.1). OFF => byte-identical legacy (the
    verdict is neither offered in the prompt nor recognised by the parser)."""
    return os.environ.get("PG_LINE_SCREEN_CLAIM_GATE", "1").strip().lower() not in _OFF_VALUES


def scope_leg_enabled() -> bool:
    """Kill-switch ``PG_LINE_SCREEN_SCOPE`` for the OUT_OF_SCOPE leg. DEFAULT OFF. Even ON,
    the leg is auto-inert unless an explicit RunConfig scope is armed (V3 activation rule):
    no scope ⇒ ZERO out_of_scope drops (the token is not even offered to the judge)."""
    return os.environ.get(_ENV_SCOPE, "0").strip().lower() not in _OFF_VALUES


def _env_int(name: str, default: int) -> int:
    """A positive int env knob; a bad / empty / non-positive value falls back to the
    safe default (FAIL-SAFE: a garbage value must never zero a loop or unbound a chunk)."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def max_lines_per_call() -> int:
    return _env_int(_ENV_MAX_LINES_PER_CALL, _DEFAULT_MAX_LINES_PER_CALL)


def min_line_chars() -> int:
    return _env_int(_ENV_MIN_LINE_CHARS, _DEFAULT_MIN_LINE_CHARS)


def subquery_min_tokens() -> int:
    return _env_int(_ENV_SUBQ_MIN_TOKENS, _DEFAULT_SUBQ_MIN_TOKENS)


def line_screen_parallel() -> int:
    """``PG_LINE_SCREEN_PARALLEL`` — bounded source-fan-out width. Default 1 (serial,
    byte-identical verdict map); production slate 32. Determinism holds at any width:
    verdicts key positionally per chunk and kept order is the original line order."""
    return _env_int(_ENV_PARALLEL, 1)


# ─────────────────────────────────────────────────────────────────────────────
# Reused accessors (single source of truth — lazy import, fail-open)
# ─────────────────────────────────────────────────────────────────────────────
def _widest_body(row: dict[str, Any]) -> str:
    """The widest fetched body across every plausible content field — the exact probe list
    run_honest_sweep_r3.py:14925-14932 uses (via ``topic_relevance_gate._CHROME_BODY_FIELDS``,
    single source of truth). Screening what the row actually carries is screening exactly
    what composition can cite (V1). Fail-open ""."""
    try:
        from src.polaris_graph.retrieval.topic_relevance_gate import (  # noqa: PLC0415
            _CHROME_BODY_FIELDS,
        )
        fields = _CHROME_BODY_FIELDS
    except Exception:  # noqa: BLE001 — never let an import defect blank a real body
        fields = (
            "fetched_body", "full_text", "content", "extracted_text", "raw_content",
            "raw_text", "page_text", "direct_quote", "statement", "source_text", "body", "text",
        )
    return max((str(row.get(bk) or "") for bk in fields), key=len, default="")


def _row_is_marquee(row: dict[str, Any]) -> bool:
    """True iff the row is a marquee / required-entity / contract anchor (never whole-dropped).
    Reuses ``topic_relevance_gate._row_is_marquee_anchor`` (single source of truth). Fail-open
    False (a marquee-detection bug must never turn OFF the protection... it is a protection, so
    False just means 'screen it like any source' — the two-key rule still guards whole-drop)."""
    try:
        from src.polaris_graph.retrieval.topic_relevance_gate import (  # noqa: PLC0415
            _row_is_marquee_anchor,
        )
        return bool(_row_is_marquee_anchor(row)) or bool(row.get("v30_entity_id"))
    except Exception:  # noqa: BLE001
        return bool(row.get("v30_entity_id"))


def _row_is_chrome_nonsource(row: dict[str, Any]) -> bool:
    """True iff the content-integrity detector confirms the WHOLE row is a chrome non-source.
    The JUNK whole-drop concurrence key (V5). Reuses
    ``topic_relevance_gate._row_is_chrome_nonsource`` (single source of truth). Fail-open False."""
    try:
        from src.polaris_graph.retrieval.topic_relevance_gate import (  # noqa: PLC0415
            _row_is_chrome_nonsource as _detect,
        )
        return bool(_detect(row))
    except Exception:  # noqa: BLE001
        return False


def _row_stamped_off_subject(row: dict[str, Any]) -> bool:
    """True iff the whole-source topic judge stamped this row OFF_SUBJECT (the OFF_TOPIC
    whole-drop concurrence key, V5). Mirrors ``junk_deletion_gate._stamped_off_subject``."""
    v = row.get("topic_off_subject")
    if v is True:
        return True
    if isinstance(v, str) and v.strip().lower() in ("off_subject", "true", "yes", "on", "1"):
        return True
    return str(row.get("topic_relevance_verdict", "") or "").strip().lower() == "off_subject"


def _body_is_shell(body: str) -> bool:
    """True iff the WHOLE body is a fetch-shell / bot-wall (reuses ``shell_detector``). A
    secondary JUNK whole-drop concurrence key. Fail-open False."""
    try:
        from src.polaris_graph.retrieval.shell_detector import is_cited_span_shell  # noqa: PLC0415
        return bool(is_cited_span_shell(body))
    except Exception:  # noqa: BLE001
        return False


def _line_is_deterministic_junk(line: str) -> bool:
    """DETERMINISTIC junk pre-pass (V2): True iff a ``shell_detector.SHELL_COOCCURRENCE``
    chrome class (cookie / citation-UI / social) appears ENTIRELY WITHIN this one line. At
    line granularity the :144-152 whole-body false-positive objection dissolves — a real
    sentence discussing cookie policy does not carry the full CTA co-occurrence in one line.
    Fail-open False (any import / error ⇒ defer to the LLM judge, never invent a drop)."""
    try:
        from src.polaris_graph.retrieval.shell_detector import SHELL_COOCCURRENCE  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return False
    low = line.lower()
    return any(all(tok in low for tok in combo) for combo in SHELL_COOCCURRENCE)


# ── Content-integrity line classifiers (P0-3a, S2/S3 re-pass) ────────────────
# Chrome LINES that survived the V2 co-occurrence pass still minted fake baskets downstream:
# a PDF xref/FlateDecode byte run from a partially-failed extraction, a nav/menu link-list, a
# license/copyright footer, a table-of-contents dot-leader, a javascript:/mailto:/tel: fragment.
# These are GENERAL classifiers (structure, not a phrase blocklist), fail-open on any doubt.
_ENV_CI_JUNK = "PG_LINE_SCREEN_CI_JUNK"                # default ON
_XREF_MARKER_RE = re.compile(
    r"%PDF|FlateDecode|endstream|endobj|startxref|\bxref\b|/Type\s*/|/Font\b|/MediaBox|"
    r"/Contents\b|/Annots\b|\bobj\b\s*<<",
    re.IGNORECASE,
)
_HEX_RUN_RE = re.compile(r"[0-9a-fA-F]{24,}")           # long unbroken hex run (binary dump)
_NAV_SEP_RE = re.compile(r"[|·•»›►▸•▪]")
_LICENSE_RE = re.compile(
    r"all rights reserved|creative commons|\bcc[\s-]?by(?:-[a-z]{2})?\b|"
    r"terms of (?:use|service)|privacy policy|licensed under|©\s*\d{4}|"
    r"copyright\s*(?:©|\(c\))|©\s*copyright",
    re.IGNORECASE,
)
_TOC_LEADER_RE = re.compile(r"\.{5,}\s*\d+\s*$|…\s*\d+\s*$|\.{8,}")
_URI_FRAGMENT_RE = re.compile(r"javascript:|mailto:|tel:")
_WORD_TOKEN_RE = re.compile(r"[A-Za-zÀ-ɏ]{2,}")


def ci_junk_enabled() -> bool:
    """Kill-switch ``PG_LINE_SCREEN_CI_JUNK`` for the content-integrity line classifiers
    (P0-3a). DEFAULT ON. OFF ⇒ only the legacy V2 co-occurrence pre-pass runs (byte-identical
    to before this fix)."""
    return os.environ.get(_ENV_CI_JUNK, "1").strip().lower() not in _OFF_VALUES


def _line_is_content_integrity_junk(line: str) -> bool:
    """DETERMINISTIC content-integrity junk (P0-3a): True iff the LINE is a binary/xref byte
    run, a nav/menu link-list, a license/copyright footer, a TOC dot-leader, or a
    javascript:/mailto:/tel: fragment. GENERAL structural classifiers (not a phrase blocklist);
    FAIL-OPEN on any doubt. A line carrying substantive propositional prose is never junked by
    the SOFT classes (license/nav/toc/uri stay short by construction), so a real statistic /
    sentence survives (§-1.3 keep-all; P2-10 fail-open at line level)."""
    if not ci_junk_enabled():
        return False
    text = (line or "").strip()
    if not text:
        return False
    # HARD: PDF operator markers or a long hex byte run — never real prose.
    if _XREF_MARKER_RE.search(text) or _HEX_RUN_RE.search(text):
        return True
    words = _WORD_TOKEN_RE.findall(text)
    # SOFT: a javascript:/mailto:/tel:-dominated fragment (few real words around the URI).
    if _URI_FRAGMENT_RE.search(text) and len(words) < 6:
        return True
    # SOFT: license / copyright footer (a short chrome line, not a paragraph mentioning rights).
    if _LICENSE_RE.search(text) and len(words) < 25:
        return True
    # SOFT: table-of-contents dot-leaders.
    if _TOC_LEADER_RE.search(text):
        return True
    # SOFT: a nav / menu link-list — several SHORT segments split by nav separators.
    if len(_NAV_SEP_RE.findall(text)) >= 3:
        segs = [s.strip() for s in _NAV_SEP_RE.split(text) if s.strip()]
        if len(segs) >= 4 and all(len(s.split()) <= 4 for s in segs):
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Sub-query anchor (Design 1 §3 D2 precedence, self-contained until D2 lands)
# ─────────────────────────────────────────────────────────────────────────────
def _row_subquery_anchor(row: dict[str, Any]) -> str:
    """The judge-facing sub-query anchor: ``retrieval_subquery`` > ``query_origin`` > ""
    (Design 1 §3 D2). ``seed_query_origin`` is deliberately EXCLUDED (seed rows are anchors,
    gate-exempt). Returns a plain string (never None)."""
    for key in ("retrieval_subquery", "query_origin"):
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _usable_subquery_anchor(text: str) -> bool:
    """True only for a REAL natural-language sub-query (Design 1 §3 D2). Rejects: empty; the
    known provenance labels; any string with fewer than ``PG_LINE_SCREEN_SUBQ_MIN_TOKENS``
    whitespace tokens. A label or junk anchor degrades to main-question-only judging."""
    t = (text or "").strip()
    if not t:
        return False
    low = t.lower()
    if low in _ANCHOR_LABEL_TOKENS:
        return False
    if any(sub in low for sub in _ANCHOR_LABEL_SUBSTRINGS):
        return False
    return len(t.split()) >= subquery_min_tokens()


# ─────────────────────────────────────────────────────────────────────────────
# Explicit user scope (V3) — the OUT_OF_SCOPE leg's activation gate
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class ScreenScope:
    """The user's EXPLICIT RunConfig scope. ``armed`` is the V3 activation switch — the
    OUT_OF_SCOPE leg fires ONLY when armed (an explicit trigger span or a control-panel
    override). An all-empty scope is INERT: zero out_of_scope drops anywhere."""

    armed: bool = False
    date_start_idx: Optional[int] = None   # year*12 + (month-1) inclusive floor
    date_end_idx: Optional[int] = None     # inclusive ceiling
    journal_only: bool = False             # explicit "peer-reviewed / journal articles only"
    language: Optional[str] = None         # ISO code, e.g. 'en'
    trigger_spans: list[str] = field(default_factory=list)

    def is_active(self) -> bool:
        """Armed AND the scope leg kill-switch is ON AND at least one concrete axis is set."""
        return (
            self.armed
            and scope_leg_enabled()
            and (
                self.date_start_idx is not None
                or self.date_end_idx is not None
                or self.journal_only
                or bool(self.language)
            )
        )

    def scope_block_text(self) -> str:
        """The verbatim USER SCOPE block for the judge prompt (only rendered when active)."""
        parts: list[str] = []
        if self.date_start_idx is not None:
            parts.append(f"- publication date on or after {_idx_to_ym(self.date_start_idx)}")
        if self.date_end_idx is not None:
            parts.append(f"- publication date on or before {_idx_to_ym(self.date_end_idx)}")
        if self.journal_only:
            parts.append("- ONLY peer-reviewed journal articles (exclude blogs, news, "
                         "reports, working papers, and other non-journal sources)")
        if self.language:
            parts.append(f"- ONLY sources written in language '{self.language}'")
        for span in self.trigger_spans:
            if span:
                parts.append(f"- (user's words: \"{span.strip()[:160]}\")")
        return "\n".join(parts)

    def sha(self) -> str:
        payload = json.dumps({
            "armed": self.armed,
            "date_start_idx": self.date_start_idx,
            "date_end_idx": self.date_end_idx,
            "journal_only": self.journal_only,
            "language": self.language,
        }, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _ym_to_idx(year: int, month: int) -> int:
    return year * 12 + (month - 1)


def _idx_to_ym(idx: int) -> str:
    return f"{idx // 12:04d}-{(idx % 12) + 1:02d}"


def _parse_ym(value: Any) -> Optional[tuple[int, int]]:
    """Parse 'YYYY-MM' or 'YYYY' into (year, month), else None. Pure."""
    s = str(value or "").strip()
    if not s:
        return None
    import re  # noqa: PLC0415
    m = re.match(r"^(\d{4})-(\d{1,2})", s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            return (y, mo)
    m2 = re.match(r"^(\d{4})$", s)
    if m2:
        return (int(m2.group(1)), 1)
    return None


def build_scope_from_dict(spec: dict[str, Any] | None) -> ScreenScope:
    """Build an EXPLICIT (armed) scope from a control-panel-style dict (the harness
    ``--scope`` override, V3 'explicit control-panel override in RunConfig.scope'). Keys:
    ``date_start`` / ``date_end`` ('YYYY-MM' or 'YYYY'), ``journal_only`` (bool),
    ``language`` (ISO), ``trigger`` (verbatim user words). An empty / None spec ⇒ inert."""
    sc = ScreenScope()
    if not isinstance(spec, dict) or not spec:
        return sc
    ds = _parse_ym(spec.get("date_start"))
    de = _parse_ym(spec.get("date_end"))
    if ds is not None:
        sc.date_start_idx = _ym_to_idx(*ds)
    if de is not None:
        sc.date_end_idx = _ym_to_idx(*de)
    sc.journal_only = bool(spec.get("journal_only"))
    lang = spec.get("language")
    if isinstance(lang, str) and lang.strip():
        sc.language = lang.strip().lower()
    trig = spec.get("trigger")
    if isinstance(trig, str) and trig.strip():
        sc.trigger_spans.append(trig.strip())
    sc.armed = (
        sc.date_start_idx is not None or sc.date_end_idx is not None
        or sc.journal_only or bool(sc.language)
    )
    return sc


def build_scope_from_question(
    question: str, *, llm_fn: Optional[Callable[[str], str]] = None,
) -> ScreenScope:
    """Extract an explicit scope from the QUESTION text via the REAL intake extractors
    (``extract_user_constraints`` + ``extract_scope_constraints``). ARMED ONLY on an explicit
    HARD trigger (a verbatim trigger span) — a plain 'before June 2023' with no exclusivity
    token stays WEIGHT and does NOT arm (V3 anti-invention). Reuses
    ``intake_constraint_extractor`` (single source of truth); fail-open to inert on any error.

    NOTE: this is opt-in for the harness (``--scope-from-question``); the default harness path
    leaves the scope leg INERT so credible non-journal institutions survive lock bar (b)."""
    sc = ScreenScope()
    try:
        from src.polaris_graph.retrieval.intake_constraint_extractor import (  # noqa: PLC0415
            extract_user_constraints, extract_scope_constraints,
        )
    except Exception:  # noqa: BLE001
        return sc
    try:
        uc = extract_user_constraints(question, llm_fn=llm_fn)
    except Exception:  # noqa: BLE001
        uc = None
    if uc is not None:
        # Date window arms only when the timeline is HARD (an explicit exclusivity /
        # requirement trigger span) — a plain weight window does NOT arm.
        if getattr(uc, "timeline_strictness", "weight") == "hard":
            if uc.date_start_year is not None:
                sc.date_start_idx = _ym_to_idx(uc.date_start_year, uc.date_start_month or 1)
            if uc.date_end_year is not None:
                sc.date_end_idx = _ym_to_idx(uc.date_end_year, uc.date_end_month or 12)
            if getattr(uc, "timeline_trigger_span", ""):
                sc.trigger_spans.append(uc.timeline_trigger_span)
        if uc.journal_only:
            sc.journal_only = True
            sc.trigger_spans.append("peer-reviewed / journal articles only")
        if uc.language:
            sc.language = uc.language
            sc.trigger_spans.append(f"{uc.language}-language sources only")
    try:
        scope_c = extract_scope_constraints(question, llm_fn=llm_fn)
        for facet in getattr(scope_c, "facets", []) or []:
            if getattr(facet, "strictness", "weight") == "hard" and facet.facet_id == "peer_reviewed_journal":
                sc.journal_only = True
                if getattr(facet, "trigger_span", ""):
                    sc.trigger_spans.append(facet.trigger_span)
    except Exception:  # noqa: BLE001
        pass
    sc.armed = (
        sc.date_start_idx is not None or sc.date_end_idx is not None
        or sc.journal_only or bool(sc.language)
    )
    return sc


def _source_out_of_scope_reason(row: dict[str, Any], scope: ScreenScope) -> str:
    """DETERMINISTIC source-level explicit-scope violation (V3). Returns a short reason string
    (the axis that fired) iff the WHOLE source metadata provably violates the armed scope,
    else "". FAIL-OPEN: undated / unresolvable-facet rows return "" (KEEP). Reuses
    ``evidence_selector._row_out_of_window_ym`` + ``scope_facet_classifier``."""
    if not scope.is_active():
        return ""
    # Date window — month precision, fail-open on undated (single source of truth).
    if scope.date_start_idx is not None or scope.date_end_idx is not None:
        try:
            from src.polaris_graph.retrieval.evidence_selector import (  # noqa: PLC0415
                _row_out_of_window_ym,
            )
            if _row_out_of_window_ym(row, scope.date_start_idx, scope.date_end_idx):
                return "date_window"
        except Exception:  # noqa: BLE001 — never drop on a predicate defect
            pass
    # Peer-reviewed-only — drop ONLY a source POSITIVELY classified as a non-journal type;
    # an unresolved source KEEPS (fail-open, never punish what we cannot prove out of scope).
    if scope.journal_only:
        try:
            from src.polaris_graph.retrieval.scope_facet_classifier import (  # noqa: PLC0415
                classify_source_facets,
            )
            facets, basis = classify_source_facets(row)
            if "peer_reviewed_journal" not in facets and basis != "unresolved":
                return "peer_reviewed_only"
        except Exception:  # noqa: BLE001
            pass
    # Language — drop ONLY when the row carries an explicit conflicting language stamp.
    if scope.language:
        row_lang = str(row.get("language") or row.get("lang") or "").strip().lower()[:2]
        if row_lang and row_lang != scope.language[:2]:
            return "language"
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Line splitting (V1)
# ─────────────────────────────────────────────────────────────────────────────
def split_line_units(body: str, min_chars: int | None = None) -> list[str]:
    """Split a fetched body into JUDGEABLE line units (V1): non-empty physical lines; a line
    shorter than ``PG_LINE_SCREEN_MIN_LINE_CHARS`` is merged into its NEIGHBOR (appended to the
    previous unit, or prepended to the next when it is the first) so every unit is long enough
    to judge. Pure, deterministic, order-preserving. Empty body ⇒ []."""
    floor = min_chars if (min_chars and min_chars > 0) else min_line_chars()
    raw = [ln.rstrip() for ln in (body or "").splitlines() if ln.strip()]
    if not raw:
        return []
    units: list[str] = []
    for ln in raw:
        if len(ln.strip()) < floor and units:
            units[-1] = units[-1] + " " + ln.strip()
        else:
            units.append(ln)
    # A leading short line (units was empty) stays as its own unit — merge forward instead.
    if len(units) >= 2 and len(units[0].strip()) < floor:
        units[1] = units[0].strip() + " " + units[1]
        units = units[1:]
    return units


# ─────────────────────────────────────────────────────────────────────────────
# Prompt (V2) — reuses the topic_relevance_gate D3 scaffold + a scope block
# ─────────────────────────────────────────────────────────────────────────────
def build_line_prompt(
    main_question: str,
    subquery: str,
    scope_block: str,
    numbered_lines: list[tuple[int, str]],
) -> str:
    """Build ONE per-source (or per-chunk) three-way line-screen prompt. Mirrors the
    ``topic_relevance_gate`` verdict-only discipline (:300-305). Verdict contract:
    ``<idx>: KEEP | OFF_TOPIC | OUT_OF_SCOPE | JUNK``. OUT_OF_SCOPE is OFFERED only when a
    scope block is present. The DATE-BLIND rule applies to OFF_TOPIC but NOT to OUT_OF_SCOPE
    (dates are exactly what an explicit date window judges)."""
    has_sub = _usable_subquery_anchor(subquery)
    has_scope = bool(scope_block.strip())
    has_claim_gate = claim_bearing_gate_enabled()
    verdict_menu = (
        "KEEP | OFF_TOPIC | "
        + ("OUT_OF_SCOPE | " if has_scope else "")
        + "JUNK"
        + (" | NON_CLAIM" if has_claim_gate else "")
    )
    lines: list[str] = [
        "You are a strict LINE-LEVEL relevance screener for a research report. You read the "
        "raw fetched body of ONE source, LINE BY LINE, and decide for EACH numbered line "
        "whether to KEEP it or DROP it for one specific reason.",
        "",
        f"MAIN RESEARCH QUESTION:\n{main_question.strip()}",
    ]
    if has_sub:
        lines += [
            "",
            "SUB-QUERY (this source was retrieved specifically to answer this):\n"
            + subquery.strip(),
        ]
    if has_scope:
        lines += [
            "",
            "USER SCOPE (explicit, from the user's own prompt — a line OUTSIDE this scope is "
            "OUT_OF_SCOPE):\n" + scope_block.strip(),
        ]
    lines += [
        "",
        "STEP 1 (do this SILENTLY — never write this reasoning): name to yourself the subject "
        "entity + specific aspect of the MAIN RESEARCH QUESTION"
        + (" and of the SUB-QUERY" if has_sub else "") + ".",
        "",
        "STEP 2 — for EACH numbered line choose EXACTLY ONE verdict:",
        "- KEEP: the line is real source content that plausibly bears on "
        + ("EITHER anchor" if has_sub else "the research question")
        + ((" AND is within the USER SCOPE") if has_scope else "") + ".",
        "- OFF_TOPIC: real prose, but about a clearly different subject/aspect that bears on "
        + ("NEITHER anchor" if has_sub else "the research question") + ".",
    ]
    if has_scope:
        lines.append(
            "- OUT_OF_SCOPE: real, on-topic content whose metadata (date / source type / "
            "language) puts the line OUTSIDE the USER SCOPE above."
        )
    lines += [
        "- JUNK: navigation / cookie-consent / subscribe / login / related-articles / "
        "share-buttons / breadcrumb / copyright chrome — website furniture, not article prose. "
        "(Examples of chrome vocabulary: 'we use cookies', 'accept all cookies', 'download "
        "citation', 'subscribe', 'watch later', '404 not found', 'skip to main content'.)",
    ]
    if has_claim_gate:
        lines.append(
            "- NON_CLAIM: real prose from the document that nevertheless ASSERTS NOTHING about "
            "the world — it makes no factual claim, reports no finding, states no result. Judge "
            "by MEANING, not keywords. This covers a table-of-contents / page-number run, an "
            "acknowledgments or dedication line, a license / copyright / rights statement, a "
            "share / alert / 'cite this' / footer line, a bare citation-metadata / reference-list "
            "block, a figure-axis / legend / caption label dump, a journal masthead / editorial "
            "board line, or advertising copy. If the line makes ANY assertion that bears on the "
            "research question, it is NOT NON_CLAIM — KEEP it. When unsure, KEEP."
        )
    lines += [
        "",
        "TOPICALITY IS DATE-BLIND for OFF_TOPIC: never mark a line OFF_TOPIC because of a date. "
        "A date only matters for OUT_OF_SCOPE, and only when the USER SCOPE names a date window.",
        "",
        "FAIL-OPEN: if you cannot confidently place a line, mark it KEEP. When in doubt, KEEP.",
        "",
        "OUTPUT CONTRACT (strict — the parser accepts nothing else): output ONLY the verdict "
        f"lines, exactly one per numbered line, each EXACTLY in the form `<index>: <{verdict_menu}>`. "
        "No reasoning, no quotes, no other words anywhere.",
        "",
        "LINES:",
    ]
    for idx, text in numbered_lines:
        lines.append(f"{idx}: {text}")
    lines.append("")
    lines.append(f"VERDICTS (one `<index>: {verdict_menu}` line per source line):")
    return "\n".join(lines)


def parse_line_verdicts(
    raw: str, expected_indices: list[int], *, scope_offered: bool,
) -> dict[int, str] | None:
    """Parse ``<idx>: KEEP|OFF_TOPIC|OUT_OF_SCOPE|JUNK`` into ``{idx: verdict}``. Returns None
    (FAIL-OPEN — keep the whole chunk) on empty input or any result that is not exactly one
    RECOGNISED verdict per requested index (mirrors ``topic_relevance_gate`` :476-477). When a
    scope block was NOT offered, an OUT_OF_SCOPE token is treated as unrecognised (it must not
    fire without an armed scope). A bare 'DROP'/'OFF' with no reason maps to OFF_TOPIC
    (conservative — the safest keep-adjacent non-scope drop)."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    verdicts: dict[int, str] = {}
    wanted = set(expected_indices)
    claim_offered = claim_bearing_gate_enabled()  # Fable Fix 2: recognise NON_CLAIM only when armed
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or ":" not in stripped:
            continue
        idx_part, _, verdict_part = stripped.partition(":")
        idx_token = idx_part.strip().lstrip("-").strip()
        if not idx_token.isdigit():
            continue
        idx = int(idx_token)
        if idx not in wanted:
            continue
        norm = verdict_part.strip().lower().replace("-", "_").replace(" ", "_")
        if norm.startswith("keep"):
            verdicts[idx] = KEEP
        elif norm.startswith("out_of_scope") or norm.startswith("outofscope") or norm.startswith("oos"):
            verdicts[idx] = OUT_OF_SCOPE if scope_offered else KEEP  # never fire w/o armed scope
        elif norm.startswith("off_topic") or norm.startswith("offtopic") or norm.startswith("off"):
            verdicts[idx] = OFF_TOPIC
        elif norm.startswith("junk") or norm.startswith("chrome"):
            verdicts[idx] = JUNK
        elif claim_offered and (norm.startswith("non_claim") or norm.startswith("nonclaim")):
            # Fable Fix 2: claim-empty boilerplate — a SPAN drop (keep the source). Only
            # recognised when the gate is armed (else it stays unset → fail-open keep-all).
            verdicts[idx] = NON_CLAIM
        elif norm.startswith("drop"):
            verdicts[idx] = OFF_TOPIC  # bare drop w/o reason → conservative OFF_TOPIC
        # else: unrecognised → leave unset → count mismatch → fail-open.
    if set(verdicts.keys()) != wanted:
        return None
    return verdicts


# ─────────────────────────────────────────────────────────────────────────────
# Per-source screen (V1-V5)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class SourceScreenResult:
    """Outcome of screening ONE source. The judge path is PURE — the caller applies this to
    a COPY of the row (rewrites the widest body / direct_quote to the kept lines)."""

    evidence_id: str
    n_lines: int
    n_kept: int
    kept_lines: list[str] = field(default_factory=list)
    dropped: list[dict[str, Any]] = field(default_factory=list)  # {line_idx, reason, quote}
    whole_dropped: bool = False
    whole_drop_reason: str = ""
    disagreement: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def kept_body(self) -> str:
        return "\n".join(self.kept_lines)

    def reason_counts(self) -> dict[str, int]:
        counts = {r.lower(): 0 for r in _DROP_REASONS}
        for d in self.dropped:
            r = str(d.get("reason", "")).lower()
            if r in counts:
                counts[r] += 1
        return counts

    def sidecar(self) -> dict[str, Any]:
        return {
            "n_lines": self.n_lines,
            "n_dropped": len(self.dropped),
            "reasons": self.reason_counts(),
            "whole_dropped": self.whole_dropped,
            "whole_drop_reason": self.whole_drop_reason,
            "disagreement": self.disagreement,
        }


def screen_source(
    row: dict[str, Any],
    main_question: str,
    llm_callable: Callable[[str], str],
    *,
    scope: ScreenScope | None = None,
    max_lines: int | None = None,
) -> SourceScreenResult:
    """Screen ONE source line-by-line (V1-V5). Pure (no row mutation). FAIL-OPEN throughout:
    an unusable body keeps everything; an LLM error / count-mismatch keeps the whole chunk; a
    100%-drop that the whole-source verdict does NOT concur on (V5 two-key) restores ALL lines;
    a marquee source is NEVER whole-dropped."""
    scope = scope or ScreenScope()
    eid = str(row.get("evidence_id", "") or "")
    body = _widest_body(row)
    units = split_line_units(body)
    n = len(units)
    result = SourceScreenResult(evidence_id=eid, n_lines=n, n_kept=n, kept_lines=list(units))
    if n == 0:
        result.notes.append("empty body — nothing to screen")
        return result
    if not (main_question or "").strip():
        result.notes.append("empty main question — fail-open keep-all")
        return result

    is_marquee = _row_is_marquee(row)

    # V3 — deterministic source-level explicit-scope violation → whole out_of_scope drop
    # (two-key: line screen + deterministic metadata key), unless marquee.
    src_scope_reason = _source_out_of_scope_reason(row, scope)

    subquery = _row_subquery_anchor(row)
    scope_active = scope.is_active()
    scope_block = scope.scope_block_text() if scope_active else ""

    # Per-line verdicts. Deterministic junk pre-pass first; the remainder go to the judge.
    verdict_by_idx: dict[int, str] = {}
    to_judge: list[tuple[int, str]] = []
    for idx, text in enumerate(units):
        if _line_is_deterministic_junk(text) or _line_is_content_integrity_junk(text):
            # P0-3a: a binary/xref byte run, nav link-list, license footer, TOC leader, or
            # javascript:/mailto:/tel: fragment is chrome — dropped deterministically before the
            # judge so it can never mint a downstream basket (§-1.3-safe: only the LINE drops).
            verdict_by_idx[idx] = JUNK
        else:
            to_judge.append((idx, text))

    chunk_size = max_lines if (max_lines and max_lines > 0) else max_lines_per_call()
    for start in range(0, len(to_judge), chunk_size):
        chunk = to_judge[start:start + chunk_size]
        numbered = [(local, text) for local, (_orig, text) in enumerate(chunk)]
        expected = [local for local, _ in numbered]
        prompt = build_line_prompt(main_question, subquery, scope_block, numbered)
        try:
            raw = llm_callable(prompt)
        except Exception as exc:  # noqa: BLE001 — FAIL-OPEN: keep the whole chunk on any LLM error
            _LOGGER.warning("[line_screen] source=%s chunk LLM error — fail-open keep %d lines: %s",
                            eid, len(chunk), str(exc)[:160])
            for local, (orig, _t) in enumerate(chunk):
                verdict_by_idx[orig] = KEEP
            continue
        parsed = parse_line_verdicts(raw, expected, scope_offered=bool(scope_block))
        if parsed is None:  # FAIL-OPEN: count mismatch / unparseable → keep the whole chunk.
            for local, (orig, _t) in enumerate(chunk):
                verdict_by_idx[orig] = KEEP
            continue
        for local, (orig, _t) in enumerate(chunk):
            verdict_by_idx[orig] = parsed.get(local, KEEP)

    # Assemble kept lines + dropped records (original order).
    kept_lines: list[str] = []
    dropped: list[dict[str, Any]] = []
    for idx, text in enumerate(units):
        v = verdict_by_idx.get(idx, KEEP)
        if v == KEEP:
            kept_lines.append(text)
        else:
            dropped.append({"line_idx": idx, "reason": v.lower(), "quote": text})

    result.kept_lines = kept_lines
    result.n_kept = len(kept_lines)
    result.dropped = dropped

    # V3 deterministic source-scope: if the whole source is out of the armed scope, that is a
    # metadata whole-drop key — every line drops out_of_scope (unless marquee, which never
    # whole-drops). Recorded even when the line judge kept some lines (the metadata is decisive).
    if src_scope_reason and not is_marquee:
        result.whole_dropped = True
        result.whole_drop_reason = f"out_of_scope:{src_scope_reason}"
        # Mark any not-already-dropped line as out_of_scope for a complete quoted disclosure.
        already = {d["line_idx"] for d in dropped}
        extra = [
            {"line_idx": i, "reason": OUT_OF_SCOPE.lower(), "quote": t}
            for i, t in enumerate(units) if i not in already
        ]
        result.dropped = sorted(dropped + extra, key=lambda d: d["line_idx"])
        result.kept_lines = []
        result.n_kept = 0
        result.notes.append(f"whole out_of_scope by metadata: {src_scope_reason}")
        return result

    # V5 — whole-drop two-key + marquee protection. A source only whole-drops (n_kept==0) when
    # a CONCURRING whole-source verdict of the same dominant reason class exists.
    if result.n_kept == 0 and n > 0:
        counts = result.reason_counts()
        dominant = max(_DROP_REASONS, key=lambda r: counts[r.lower()])
        concurs = False
        if dominant == OFF_TOPIC:
            concurs = _row_stamped_off_subject(row)
            key = "topic_off_subject"
        elif dominant == JUNK:
            concurs = _row_is_chrome_nonsource(row) or _body_is_shell(body)
            key = "content_integrity_junk/shell"
        else:  # OUT_OF_SCOPE line-level with no metadata key already handled above
            concurs = bool(src_scope_reason)
            key = "source_scope_metadata"
        if is_marquee or not concurs:
            # Fail-open: restore ALL lines (keep the source unscreened) + disclose the
            # disagreement (V5) / marquee protection.
            result.kept_lines = list(units)
            result.n_kept = n
            result.dropped = []
            result.disagreement = True
            reason = "marquee — never whole-dropped" if is_marquee else (
                f"100% {dominant.lower()} lines but no concurring whole-source key ({key}) — "
                "fail-open keep-all"
            )
            result.notes.append(reason)
        else:
            result.whole_dropped = True
            result.whole_drop_reason = f"{dominant.lower()}:concur:{key}"
            result.notes.append(f"whole-drop {dominant.lower()} (two-key: line screen + {key})")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Checkpoint (V7) — crash-resilient incremental JSONL
# ─────────────────────────────────────────────────────────────────────────────
def _body_sha(body: str) -> str:
    return hashlib.sha256((body or "").encode("utf-8")).hexdigest()[:16]


def _checkpoint_header(main_question: str, scope: ScreenScope, flag_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "_header": True,
        "main_question_sha": hashlib.sha256((main_question or "").encode("utf-8")).hexdigest()[:16],
        "scope_sha": scope.sha(),
        "flag_state": flag_state,
    }


def _load_checkpoint(
    path: Path, header: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Load prior per-source records whose header matches (V7 resume replay). A mismatched
    header ⇒ ignore the file entirely (never replay verdicts from a different question / scope /
    flag config). Fail-open: any read/parse error ⇒ empty (re-screen from scratch)."""
    replay: dict[str, dict[str, Any]] = {}
    try:
        if not path.is_file():
            return replay
        first = True
        with path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                except json.JSONDecodeError:
                    continue  # a torn last line (crash mid-write) — skip it
                if first:
                    first = False
                    if not (isinstance(rec, dict) and rec.get("_header")):
                        return {}  # no header ⇒ do not trust the file
                    if (rec.get("main_question_sha") != header["main_question_sha"]
                            or rec.get("scope_sha") != header["scope_sha"]):
                        return {}  # different identity ⇒ ignore + re-screen fresh
                    continue
                if isinstance(rec, dict) and rec.get("evidence_id"):
                    replay[str(rec["evidence_id"])] = rec
    except Exception as exc:  # noqa: BLE001 — a checkpoint bug must never drop / invent a verdict
        _LOGGER.warning("[line_screen] checkpoint load failed (%s) — re-screening fresh", str(exc)[:160])
        return {}
    return replay


def _result_to_record(result: SourceScreenResult, body_sha: str) -> dict[str, Any]:
    return {
        "evidence_id": result.evidence_id,
        "body_sha": body_sha,
        "n_lines": result.n_lines,
        "n_kept": result.n_kept,
        "kept_lines": result.kept_lines,
        "dropped": result.dropped,
        "whole_dropped": result.whole_dropped,
        "whole_drop_reason": result.whole_drop_reason,
        "disagreement": result.disagreement,
    }


def _record_to_result(rec: dict[str, Any]) -> SourceScreenResult:
    return SourceScreenResult(
        evidence_id=str(rec.get("evidence_id", "")),
        n_lines=int(rec.get("n_lines", 0) or 0),
        n_kept=int(rec.get("n_kept", 0) or 0),
        kept_lines=list(rec.get("kept_lines", []) or []),
        dropped=list(rec.get("dropped", []) or []),
        whole_dropped=bool(rec.get("whole_dropped")),
        whole_drop_reason=str(rec.get("whole_drop_reason", "") or ""),
        disagreement=bool(rec.get("disagreement")),
        notes=["replayed from checkpoint"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Corpus screen (V6 parallel + V7 checkpoint)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class CorpusScreenResult:
    results: list[SourceScreenResult]
    n_sources: int = 0
    n_screened_llm: int = 0
    n_replayed: int = 0
    n_whole_dropped: int = 0
    n_disagreement: int = 0


def screen_corpus(
    rows: list[dict[str, Any]],
    main_question: str,
    llm_callable: Callable[[str], str],
    *,
    scope: ScreenScope | None = None,
    parallel: int | None = None,
    max_lines: int | None = None,
    checkpoint_path: Path | None = None,
    on_result: Optional[Callable[[SourceScreenResult, dict[str, Any]], None]] = None,
) -> CorpusScreenResult:
    """Screen the whole surviving corpus line-by-line (V6 parallel dispatch + V7 crash-resilient
    checkpoint). Determinism holds at any ``parallel`` width. ``on_result`` (if given) is called
    once per source AS SOON AS its verdict is known (incremental disclosure sink for the harness),
    under a lock so a caller can write incrementally from a bounded thread pool."""
    scope = scope or ScreenScope()
    width = parallel if (parallel and parallel > 0) else line_screen_parallel()
    flag_state = {
        "PG_LINE_SCREEN_SCOPE": scope_leg_enabled(),
        "scope_active": scope.is_active(),
        "max_lines_per_call": max_lines if (max_lines and max_lines > 0) else max_lines_per_call(),
        "min_line_chars": min_line_chars(),
    }
    header = _checkpoint_header(main_question, scope, flag_state)
    replay = _load_checkpoint(checkpoint_path, header) if checkpoint_path else {}

    # Prepare the incremental checkpoint file (header first) if fresh.
    write_lock = threading.Lock()
    ckpt_fh = None
    if checkpoint_path is not None:
        try:
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            if not replay:  # fresh (or ignored) → (re)write header
                with checkpoint_path.open("w", encoding="utf-8") as fh:
                    fh.write(json.dumps(header) + "\n")
            ckpt_fh = checkpoint_path.open("a", encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 — a checkpoint bug must never drop / invent a verdict
            _LOGGER.warning("[line_screen] checkpoint open failed (%s) — proceeding uncheckpointed",
                            str(exc)[:160])
            ckpt_fh = None

    results: list[Optional[SourceScreenResult]] = [None] * len(rows)
    n_replayed = 0
    n_llm = 0

    def _emit(i: int, result: SourceScreenResult, row: dict[str, Any], body_sha: str, replayed: bool) -> None:
        nonlocal n_replayed, n_llm
        results[i] = result
        with write_lock:
            if replayed:
                n_replayed += 1
            else:
                n_llm += 1
                if ckpt_fh is not None:
                    try:
                        ckpt_fh.write(json.dumps(_result_to_record(result, body_sha)) + "\n")
                        ckpt_fh.flush()
                    except Exception as exc:  # noqa: BLE001
                        _LOGGER.warning("[line_screen] checkpoint write failed (%s)", str(exc)[:160])
            if on_result is not None:
                try:
                    on_result(result, row)
                except Exception as exc:  # noqa: BLE001 — a sink defect must never abort the screen
                    _LOGGER.warning("[line_screen] on_result sink error (%s)", str(exc)[:160])

    def _work(i: int) -> None:
        row = rows[i]
        eid = str(row.get("evidence_id", "") or "")
        body = _widest_body(row)
        bsha = _body_sha(body)
        rec = replay.get(eid)
        if rec is not None and str(rec.get("body_sha", "")) == bsha:
            _emit(i, _record_to_result(rec), row, bsha, replayed=True)
            return
        result = screen_source(row, main_question, llm_callable, scope=scope, max_lines=max_lines)
        _emit(i, result, row, bsha, replayed=False)

    try:
        if width <= 1:
            for i in range(len(rows)):
                _work(i)
        else:
            import concurrent.futures as _futures  # noqa: PLC0415
            with _futures.ThreadPoolExecutor(max_workers=width) as pool:
                list(pool.map(_work, range(len(rows))))
    finally:
        if ckpt_fh is not None:
            try:
                ckpt_fh.close()
            except Exception:  # noqa: BLE001
                pass

    final = [r for r in results if r is not None]
    return CorpusScreenResult(
        results=final,
        n_sources=len(rows),
        n_screened_llm=n_llm,
        n_replayed=n_replayed,
        n_whole_dropped=sum(1 for r in final if r.whole_dropped),
        n_disagreement=sum(1 for r in final if r.disagreement),
    )


def apply_result_to_row(row: dict[str, Any], result: SourceScreenResult) -> dict[str, Any]:
    """Return a COPY of ``row`` with the grounding body rewritten to the KEPT lines only (V4)
    + a ``line_screen`` sidecar. The original body is left intact in the caller's audit copy
    (fetch_snapshot). A whole-dropped source is NOT returned by the caller's kept pool — this
    still rewrites its body (empty) for a consistent record. Pure (never mutates the input)."""
    new_row = dict(row)
    kept = result.kept_body
    # Rewrite the field that held the widest body (the grounding surface composition cites).
    try:
        from src.polaris_graph.retrieval.topic_relevance_gate import (  # noqa: PLC0415
            _CHROME_BODY_FIELDS,
        )
        fields = _CHROME_BODY_FIELDS
    except Exception:  # noqa: BLE001
        fields = ("direct_quote", "statement")
    widest_key = max(
        (k for k in fields if isinstance(row.get(k), str) and row.get(k)),
        key=lambda k: len(str(row.get(k))), default="direct_quote",
    )
    new_row[widest_key] = kept
    if "direct_quote" in new_row and widest_key != "direct_quote":
        # keep direct_quote consistent with the screened body when it WAS the cite surface
        if isinstance(row.get("direct_quote"), str) and row.get("direct_quote"):
            new_row["direct_quote"] = kept
    new_row["line_screen"] = result.sidecar()
    return new_row
