"""Verified-only extractive executive summary (I-meta-002-q1d #949 part b).

Frontier DR reports lead with a key-findings-up-front summary; POLARIS opened cold into Efficacy. This
builds a "Key Findings" block by EXTRACTING the first verified sentence (verbatim, with its `[N]` citation)
from each verified section. It is PURELY EXTRACTIVE — it copies sentences that already survived strict_verify
and introduces ZERO new claims, no LLM call, no spend. Empty input → "" (no empty heading).
"""

from __future__ import annotations

import contextvars
import logging
import os
import re
from typing import Any, Callable

# Module logger for the FF3 render-truncation ``[activation]`` markers (I-deepfix-001 Wave-5 #1344).
# A child logger => it propagates to root, so the Gate-B ``_ActivationMarkerCaptureHandler`` (attached to
# the ROOT logger for the in-process query) captures the marker lines exactly like the other 10 modules.
_MODULE_LOGGER = logging.getLogger(__name__)

# One sentence = minimal run up to end punctuation, PLUS any trailing `[N]` citation marker(s), where the
# end punctuation must be a real sentence boundary: followed by whitespace+capital/bracket/digit OR end of
# text. The boundary lookahead prevents stopping inside a decimal ("2.1" — the period is followed by a digit,
# no whitespace, so it is not a boundary). Matching (not splitting) keeps trailing-citation forms (`claim.
# [1]` AND `claim [1].`) attached to the sentence — re.split would consume the trailing `[N]` (Codex
# diff-gate iter-1 P2).
_SENTENCE_RE = re.compile(r".+?[.!?](?:\s*\[\d+\])*(?=\s+[A-Z(\[\d]|\s*$)", re.DOTALL)

# A Key Finding is a SPAN-VERIFIED statement — by definition it carries its `[N]` / `[#ev:`
# citation (module docstring). This is the robust per-SENTENCE gap filter (I-gen-006 #1178
# C07/P07): a gap-disclosure sentence ("... did not survive strict verification; curator-
# actionable gap.") carries NO citation, so in a MIXED V30 section (a leading gap slot +
# later verified prose, where the SECTION still has sentences_verified>0) the uncited gap
# sentence is skipped and the first CITED sentence is lifted instead. Keys on the citation
# invariant, never on matching gap-disclosure text.
_CITATION_RE = re.compile(r"\[\d+\]|\[#ev:")

# Gap-disclosure boilerplate (I-gen-006 #1178 C07/P07, Codex iter-5): the V30 contract-runner
# gap disclosure is a FIXED two-sentence template — "Contract-bound content ... curator-actionable
# gap. See manifest.frame_coverage_report and human_gap_tasks.json for per-entity detail.[N]" — and
# its SECOND sentence DOES carry a `[N]` (a pointer to the gap-task sidecar, NOT an evidence span),
# so the citation filter alone cannot exclude it. A Key Finding must be a span-verified CLAIM, never
# a gap pointer; exclude any sentence carrying a canonical gap-disclosure marker. Robust because the
# disclosure text is generated from fixed constants (contract_section_runner / _GAP_STUB_SENTENCE),
# never free-form prose — this is a rendering filter, not a §-1.1 quality-by-pattern judgement.
_GAP_MARKER_RE = re.compile(
    r"curator-actionable gap|did not survive strict verification|"
    r"did not survive (?:4-role )?verification|frame_coverage_report|human_gap_tasks",
    re.IGNORECASE,
)

# An ATX markdown header: 1-6 '#' followed by whitespace ("### Section"). Used to detect a
# leaked section header WITHOUT mis-classifying hash-leading prose like "#1 ranked" (Codex P2).
_ATX_HEADER_RE = re.compile(r"#{1,6}\s")

_OFF_VALUES = frozenset({"0", "false", "no", "off", ""})

# How many leading verified sentences to lift from each section (default 1 — the headline finding).
_SENTENCES_PER_SECTION = 1
# Hard cap on total bullets so the summary stays a summary.
_MAX_BULLETS = 6

# I-wire-011 (#1325) fix 2/3 — shared render hygiene used by Key Findings (here) AND the
# Abstract/Conclusion harvesters (abstract_conclusion.py imports these). PURE string ops; they
# only change which already-verified sentence RENDERS or trim a marker RUN — never a verdict, never
# a source/count. Faithfulness-STRENGTHENING (they can only suppress a fragment, never promote one).

# Trailing `[N]` / `[#ev:...]` citation markers (stripped before the truncation test so a clean
# "…claim.[12]" is judged on the "." not the marker).
_TRAILING_CITATION_RE = re.compile(r"(?:\s*\[(?:\d+|#ev:[^\]]*)\])+\s*$")
# HIGH-PRECISION mid-word / cut-span truncation MARKERS only (the §-1.1 over-strip ban — never a
# heuristic guess at a cut word): a dangling/closed ellipsis (`…`, `...`, `[...]`, `[…]`, a dangling
# `[...` whose `]` was capped) or a trailing mid-word hyphen. An INTERNAL hyphen
# ("treatment-specific effects were observed.") is NOT a truncation and still renders.
_TRUNCATION_MARKER_RE = re.compile(r"\[\s*(?:\.\.\.|…)\s*\]?\s*$|(?:…|\.\.\.)\s*$|-\s*$")
# A run of 2+ ADJACENT numeric citation markers ("[12][13][14]" / "[12] [13]") — capped to the
# first N (document order = the body's own priority). Non-adjacent markers belong to DISTINCT
# in-sentence claims and are never merged/capped.
_ADJACENT_MARKER_RUN_RE = re.compile(r"\[\d+\](?:\s*\[\d+\])+")

# Default per-run citation cap (LAW VI override PG_KEY_FINDINGS_MAX_MARKERS / the conclusion uses
# its own override). A summary line citing >3 sources in one run is render-noise; the body + the
# bibliography retain every reference, so capping the SUMMARY display can never orphan a citation.
_DEFAULT_MAX_MARKERS = 3

# ─────────────────────────────────────────────────────────────────────────────
# I-wire-013 (#1327) iter-3a — CORPUS-GROUNDED boundary span-cut (the UNBLINDING).
#
# The legacy ``is_truncated_fragment`` only matched an explicit trailing ellipsis / hyphen MARKER,
# so it returned False on the dominant truncation shape in a real render: a span CUT mid-word right
# before its ``[N]`` citation ("… 1.2 Resea.[14]", "… incorporates the ap.[5]"). This adds the
# proven detector rule (scripts/iwire013_sec11_forensic_audit.py): a boundary token is a span cut
# iff it is NOT a word the run's OWN corpus uses AND it is a strict NON-inflectional prefix (end cut)
# / suffix (start cut) of a LONGER corpus word. The corpus-vocabulary allowlist (``known_words``,
# built by the caller from evidence_pool direct_quote/statement/title) is the FALSE-POSITIVE GUARD:
# a real-but-rare sentence-ender ("classifier", "computerisation") is either known or has no longer
# known completion, so it does NOT flag, while a real cut ("Resea"→"research") always does. The
# completion gate keeps precision high (the detector holds ~2% FP on the banked render).
#
# DROP-PATH SAFE / BACKWARD-COMPATIBLE: ``known_words`` is keyword-only and defaults to ``None`` —
# every existing caller (no corpus) gets BYTE-IDENTICAL legacy behaviour (the marker check only).
# The boundary check fires ONLY when a corpus allowlist is supplied AND the caller marks which
# boundary (``ends_before_marker`` / ``starts_after_marker``) is eligible — so a complete sentence's
# trailing complete word is never end-checked unless the caller says a marker follows it.

# An alphabetic word token (the boundary word; mirrors the detector's _WORD_RE).
_BOUNDARY_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*[A-Za-z]|[A-Za-z]")
# Leading `[N]` / `[#ev:...]` citation markers (stripped before reading the first word after a cut).
_LEADING_CITATION_RE = re.compile(r"^(?:\s*\[(?:\d+|#ev:[^\]]*)\])+")
# Suffixes that make a longer known word a mere INFLECTION of the token (so the token is the real
# base word, not a cut): 'disadvantage' -> {'disadvantaged','disadvantages'} only => NOT a cut. A
# real END cut has a NON-inflectional completion ('resea' -> 'research' = 'resea'+'rch').
_INFLECTION_SUFFIXES = ("s", "d", "es", "ed", "ing", "ly", "ic")
# Single-letter boundary tokens that are legitimate one-letter English words (never a cut).
_SINGLE_LETTER_KEEP_TOKENS = frozenset({"a", "i"})
# Two-letter boundary tokens that are legitimate short words / abbreviations (never a cut).
_SHORT_OK_BOUNDARY_TOKENS = frozenset({
    "ai", "it", "is", "of", "to", "in", "on", "or", "an", "as", "be", "by", "we", "us", "no",
    "so", "do", "etc", "al", "eg", "ie", "vs", "id", "ml", "ui", "ux", "hr", "ev", "uk",
    "eu", "gn", "io", "pp", "ed", "co", "re", "at", "if", "up", "my", "go", "he", "me", "ok",
})

# A2 (I-wire Wave-A) — trailing FUNCTION-WORD span cut. A grammatically COMPLETE declarative sentence
# never ends on one of these (an article / possessive-determiner / coordinating-or-subordinating
# conjunction / relative determiner), so a span cut that leaves one dangling before its ``[N]`` is a
# truncation ("… the effect is defined by the.[5]"). PREPOSITIONS are DELIBERATELY EXCLUDED — a
# stranded preposition IS a valid sentence ender ("the group it was compared with.", "the factor we
# adjusted for.") — flagging one would over-strip a real finding (operator drop-path law: over-strip
# is worse than a leak). Terminal-capable pronouns ("this", "these", "those", "it", "them") are
# excluded for the same reason.
_TRAILING_FUNCTION_WORD_CUT = frozenset({
    "the", "a", "an",
    "and", "or", "but", "nor",
    "my", "your", "his", "her", "its", "our", "their",
    "every", "each", "whose", "which",
    "because", "although", "while", "whereas", "whilst",
})
# Pronoun / expletive / demonstrative subjects that legitimately END a comparative or elided tail on a
# bare connective ("… as strong as IT", "… faster than THEY", "… as many as IT"). The FF3-TRUNC-SEM
# semantic leg (``_is_semantically_truncated``) uses this as its keep-guard: when the token immediately
# before a trailing complement-demanding connective is one of these, the clause is COMPLETE (an
# equative / comparative tail needs no complement) and is KEPT — over-strip is the cardinal sin (§-1.3).
# (The retired FF2 lexical copula leg also used this set before it was removed as unsound.)
_COPULA_SUBJECT_PRONOUN_KEEP = frozenset({
    "it", "they", "he", "she", "we", "i", "you", "them", "us", "there",
    "this", "that", "these", "those", "one", "ones", "who", "which", "what",
    "all", "some", "many", "most", "few", "both", "either", "neither", "none", "others", "another",
})
# (The FF2-TRUNC-v2 lexical keep-sets — comparative-ellipsis markers, embedded-question wh / be-copula /
# do-support enders — were removed together with the retired FF2 copula/aux + lone-letter legs. See the
# retirement note at the is_truncated_fragment leg site and the module-top Wave-5 comment. FF2 was unsound:
# a pure last-word list cannot separate a real value cut from a grammatically complete clause; §-1.3.)
# A dangling bibliographic "pp." (page abbreviation) with NO preceding number — distinct from a real
# "rose 4 pp." percentage-points magnitude (a numeric preceding token => KEPT, never flagged).
# Codex P1 (Wave-A iter-3): the page-abbreviation form is ALWAYS lowercase "pp."; a terminal ALL-CAPS
# clinical acronym "PP" (per-protocol) is a valid sentence ender, so this is case-SENSITIVE (no
# IGNORECASE) — "The analysis used PP.[5]" no longer collides with the lowercase page marker.
_DANGLING_PP_RE = re.compile(r"(\S+)\s+pp\.?\s*$")


def _boundary_last_word(text: str) -> str:
    """The trailing alphabetic word of ``text`` (a single artificial '.' a span-truncator appends,
    plus a trailing hyphen/quote, are stripped first). '' when there is no trailing word."""
    s = text.rstrip().rstrip('"”\')')
    if s.endswith("."):
        s = s[:-1].rstrip()
    m = re.search(r"([A-Za-z][A-Za-z'\-]*)$", s)
    return m.group(1).strip("-'") if m else ""


def _boundary_first_word(text: str) -> str:
    """The leading alphabetic word of ``text`` (after any leading citation marker is stripped by the
    caller). '' when there is no leading word."""
    m = re.match(r"\s*([A-Za-z][A-Za-z'\-]*)", text)
    return m.group(1).strip("-'") if m else ""


def _ends_with_terminal_punct(core: str) -> bool:
    """True iff ``core`` ends in sentence-terminal punctuation (``.``/``!``/``?``) after stripping any
    trailing quotes / closing brackets. The FF3-TRUNC-SEM semantic leg gates on this: a
    fragment that already carries a full stop is a complete rendered unit and is FAIL-OPEN kept
    (over-strip is worse than a leak, §-1.3), so only a BARE unpunctuated dangling token flags."""
    s = core.rstrip().rstrip('"”\'’)]}')
    return bool(s) and s[-1] in ".!?"


# ─────────────────────────────────────────────────────────────────────────────
# I-deepfix-001 Wave-5 (#1344) — RENDER-TRUNCATION CLEANLINESS. One flag-gated, default-OFF,
# render-seam-only guard (FF3-TRUNC-SEM) that drops DISPLAY-truncated fragments the drb_72 audit found
# leaking into the rendered report. RENDER-ONLY / FAITHFULNESS-NEUTRAL: it never changes the MEANING of a
# verified claim, never fabricates a word to "complete" a fragment, never touches a faithfulness verdict
# (strict_verify / NLI / 4-role D8 / provenance / span-grounding stay byte-untouched). When a fragment
# cannot be SAFELY repaired the guard DROPS it (returns True => the render seam removes it) — dropping an
# unrenderable truncated stub is render cleanliness, NOT a §-1.3 source drop (a render fragment is not a
# source).
#
#   * FF3-TRUNC-SEM (PG_FF3_TRUNC_SEM) — the SEMANTIC-truncation leg below (a grammatically-plausible but
#     semantically-incomplete clause a pure lexical last-word rule misses). Default OFF => the leg is
#     SKIPPED => is_truncated_fragment is BYTE-IDENTICAL to its pre-Wave-5 (HEAD) behaviour.
#
# The FF2-TRUNC-v2 LEXICAL legs (a trailing copula/aux cut + a lone-letter-after-connective cut) were
# RETIRED as UNSOUND (never shipped): a pure last-word list cannot separate a real value cut from a
# grammatically COMPLETE fronted-complement / relative / possession / noun-homograph clause. §-1.3
# over-strip is the cardinal sin. Genuine cuts remain covered by FF3-TRUNC-SEM (semantic) + the always-on
# corpus-grounded span-cut leg.
_FF3_TRUNC_SEM_ENV = "PG_FF3_TRUNC_SEM"
# The producer truthy predicate the run_gate_b canary mirrors (flag_whitelist=("1","true","on","yes")).
_TRUNC_GUARD_ON_TOKENS = ("1", "true", "on", "yes")


def _ff3_trunc_sem_enabled() -> bool:
    """Is the FF3-TRUNC-SEM semantic render-truncation guard ON? Default OFF (byte-identical). LAW VI."""
    return os.getenv(_FF3_TRUNC_SEM_ENV, "0").strip().lower() in _TRUNC_GUARD_ON_TOKENS


# FF3-TRUNC-SEM complement-DEMANDING connectives — tokens that grammar guarantees CANNOT terminate a
# complete clause, so a sentence ending on one (with NO terminal punctuation) is a SEMANTICALLY-truncated
# fragment even though it reads as plausible prose. These are DELIBERATELY distinct from FF2's lexical sets
# (they are legitimate short tokens ELSEWHERE — the exact reason FF2's last-word lists miss them):
#   * dangling COMPARATIVE — demands a second operand ("… adoption spread faster than", "… arm A versus").
#   * cut SUBORDINATOR — demands its clause ("… the effect held unless", "… unclear whether").
#   * open APPOSITIVE / list lead-in — demands the enumerated item ("… several factors namely",
#     "… drivers such").
# HIGH-PRECISION on purpose (§-1.3 over-strip is worse than a leak): only tokens with NO valid
# sentence-final use are listed; ambiguous prepositions ("to"/"toward"/"with") that A2 keeps as valid
# enders are EXCLUDED. NOUNS never enter this set.
_FF3_TRAILING_COMPLEMENT_DEMAND = frozenset({
    "than", "versus", "vs",        # dangling comparative
    "whether", "unless",           # cut subordinator
    "namely", "such",              # open appositive / list lead-in
})


def _is_semantically_truncated(core: str) -> bool:
    """FF3-TRUNC-SEM detector: True iff ``core`` ends on a complement-DEMANDING connective that grammar
    guarantees cannot terminate a complete clause (a dangling comparative / cut subordinator / open
    appositive). The caller gates this on ABSENT terminal punctuation (a full-stopped clause is complete
    and FAIL-OPEN kept, §-1.3). PURE — never repairs, never fabricates, only classifies.

    Precision guards (over-strip is worse than a leak):
      * >= 2 boundary tokens (a real clause, not a bare 1-word stub).
      * an UPPERCASE trailing acronym / single-CAPITAL label is a valid ender, never a semantic cut.
      * a demander preceded by a PRONOUN / demonstrative subject marks a legitimate elided tail
        ("… as many as it") — KEPT (mirrors the FF2 copula keep-guard)."""
    tokens = _BOUNDARY_WORD_RE.findall(core)
    if len(tokens) < 2:
        return False
    raw_last = tokens[-1]
    # A trailing ALL-CAPS acronym / single-CAPITAL label ("… per protocol PP", "… vitamin C") is a valid
    # ender, never a dangling connective (str.isupper() is True only when every cased char is uppercase).
    if raw_last.isupper():
        return False
    if raw_last.lower() not in _FF3_TRAILING_COMPLEMENT_DEMAND:
        return False
    # "as such" is a valid sentence-final idiom ("… was classified AS SUCH", "… recognized AS SUCH"),
    # NOT the "such as" list lead-in FF3 targets ("… key drivers SUCH [as X]"). The two are distinguished
    # by the token BEFORE "such": "as" => the complete idiom (KEEP); a content noun => the cut lead-in
    # (flag). Codex Wave-5 P1; §-1.3 over-strip is worse than a leak.
    if raw_last.lower() == "such" and tokens[-2].lower() == "as":
        return False
    # keep a legitimate elided/comparative tail whose demander sits right after a pronoun subject.
    if tokens[-2].lower() in _COPULA_SUBJECT_PRONOUN_KEEP:
        return False
    return True


# ── Wave-5 realized-effect telemetry (the honest [activation] marker counts) ──────────────────────────
# HONEST-LIVENESS: each guard is a DETECT-and-DROP render screen — returning True is the drop signal every
# render-seam consumer honors (a truncated fragment is removed from the render). So detected == dropped and
# repaired is ALWAYS 0 (§-1.3: the guard NEVER fabricates a word to complete a fragment — an unsafe-to-
# repair stub is dropped, never "repaired"). ``failopen`` counts a guard-INTERNAL fault (the detection
# logic raised): the leg then FAILS OPEN (keeps the fragment, never crashes the render) and the emit
# surfaces a DISTINCT ``unavailable_failopen`` marker the run_gate_b canary REJECTS. Counts are DETECTION
# EVENTS (a fragment screened at multiple render seams counts once per screen) — a liveness signal, never a
# quality/threshold gate (the canary accepts detected=0). Reset per-report by the Gate-B entrypoint.
#
# TASK-LOCAL (Codex Wave-5 P1): the counters live in a ``contextvars.ContextVar`` per FF-leg, NOT a module-
# global dict, so a concurrent in-process query (each ``run_gate_b_query`` runs as its own asyncio Task with
# its own copied context) can never interleave another query's reset / detect / emit into false marker
# counts or a wiped fail-open. ``reset`` binds a FRESH dict into the CURRENT context via ``.set`` — that
# ``.set`` (not an in-place zero of a shared object) is what isolates the counter: each per-report Task gets
# its own binding, its child ``run_one_query`` Task inherits that dict by reference (detect mutates it), and
# the same Task's ``emit`` reads it back. The ContextVar default is ``None`` (never a shared mutable default,
# which would re-introduce the global-dict bug); a context that never called reset lazily gets its own zeroed
# dict on first touch.
def _new_trunc_counters() -> "dict[str, int]":
    """A fresh zeroed FF3 counter dict. ``screened`` (I-deepfix-001 Wave-5 reviewer P0) is the LIVENESS
    counter — how many fragments the guard actually EXAMINED at the render seam, incremented whether or not
    a leg fired. The emitted marker's ``reached`` boolean is ``screened > 0``, so a flag-ON-but-never-reached
    (still-dark) guard can no longer pass the activation canary on a bare ``detected=0`` marker. ``screened``
    is a pure liveness/observability signal — it is NOT a quality/detection count and gates NOTHING about the
    report contents (§-1.3): ``detected=0`` is still an accepted eligible-yet-zero fire when ``reached`` is
    True."""
    return {"screened": 0, "detected": 0, "repaired": 0, "dropped": 0, "failopen": 0}


_FF3_TRUNC_TELEMETRY_VAR: "contextvars.ContextVar[dict[str, int] | None]" = contextvars.ContextVar(
    "ff3_trunc_telemetry", default=None
)


def _ff3_telemetry() -> "dict[str, int]":
    """The CURRENT context's FF3 counter dict (lazily created + bound the first time it is touched)."""
    d = _FF3_TRUNC_TELEMETRY_VAR.get()
    if d is None:
        d = _new_trunc_counters()
        _FF3_TRUNC_TELEMETRY_VAR.set(d)
    return d


def _note_ff3_truncation_detected() -> None:
    """One FF3 semantic-truncation fragment detected => it is DROPPED from render (never repaired)."""
    _d = _ff3_telemetry()
    _d["detected"] += 1
    _d["dropped"] += 1


def _note_ff3_truncation_failopen() -> None:
    """FF3 leg raised => FAIL OPEN (keep the fragment) + record the distinct degrade the canary rejects."""
    _ff3_telemetry()["failopen"] += 1


def _note_ff3_truncation_screened() -> None:
    """One fragment EXAMINED by the FF3 render-truncation guard (flag ON + render seam reached this call) —
    the LIVENESS/reach signal, incremented whether or not a leg fires. It proves the guard is wired into the
    render path; detected>0 is NEVER required for the emitted marker's ``reached`` to be True (§-1.3)."""
    _ff3_telemetry()["screened"] += 1


def reset_truncation_telemetry() -> None:
    """Bind a FRESH zeroed FF3 counter dict into the CURRENT context. The Gate-B entrypoint calls this at the
    per-report boundary (inside the per-query Task) so the emitted marker counts are THIS report's realized
    effect, never a cross-report/cross-query carry. ``.set`` (not an in-place zero of a shared dict) is what
    makes the counter task-local — a concurrent query's reset touches only its own context binding."""
    _FF3_TRUNC_TELEMETRY_VAR.set(_new_trunc_counters())


def emit_truncation_activation_markers(logger: "logging.Logger | None" = None) -> None:
    """Emit the FF3 realized-effect ``[activation]`` marker ONCE per report (called by the Gate-B
    entrypoint AFTER render, within the in-process query so the marker reaches the activation-canary
    capture buffer). It fires ONLY when the FF3 flag is ON (OFF => no line => byte-identical).

    FALSE-GREEN FIX (I-deepfix-001 Wave-5 reviewer P0): the marker leads with ``reached=<True|False>``, the
    LIVENESS proof that the guard's render seam actually invoked ``is_truncated_fragment`` this report
    (``reached`` = ``screened > 0``). The canary bool-checks ``reached=True`` — so a flag-ON guard that
    stayed DARK (the render seam never called it) emits ``reached=False`` and FAILS the canary, closing the
    false-green where a bare ``detected=0`` marker passed a guard that never ran. This is a BOOLEAN liveness
    check, NOT a count threshold: a realized ``detected=0`` with ``reached=True`` is still an HONEST
    ran-ok-zero the canary ACCEPTS (§-1.3 never gate the report on a detection count). A guard-internal
    fault additionally emits the DISTINCT ``unavailable_failopen`` degrade the canary REJECTS. Never raises
    into the caller (a telemetry emit must never abort a render)."""
    _log = logger if logger is not None else _MODULE_LOGGER
    try:
        if _ff3_trunc_sem_enabled():
            _ff3 = _ff3_telemetry()
            _log.info(
                "[activation] ff3_trunc_sem: reached=%s screened=%d detected=%d repaired=%d dropped=%d",
                bool(_ff3["screened"]),
                _ff3["screened"],
                _ff3["detected"],
                _ff3["repaired"],
                _ff3["dropped"],
            )
            if _ff3["failopen"] > 0:
                _log.info("[activation] ff3_trunc_sem: unavailable_failopen")
    except Exception:  # pragma: no cover - a telemetry emit must never abort a render
        pass


def _known_word_has_longer_prefix(word: str, known_words: "set[str] | frozenset[str]") -> bool:
    """True iff some KNOWN corpus word is ``word`` + a NON-inflectional tail (``word`` is a chopped-
    END prefix: 'resea' -> 'research'). A token whose only longer completions are inflections
    ('disadvantage' -> 'disadvantaged') is the real base word and returns False."""
    return any(
        len(k) > len(word) and k.startswith(word) and k[len(word):] not in _INFLECTION_SUFFIXES
        for k in known_words
    )


def _known_word_has_longer_suffix(word: str, known_words: "set[str] | frozenset[str]") -> bool:
    """True iff some KNOWN corpus word ENDS with ``word`` and is longer (``word`` is a chopped-START
    suffix: 'hodology' -> 'methodology', 'nization' -> 'mechanization')."""
    return any(len(k) > len(word) and k.endswith(word) for k in known_words)


def _boundary_token_is_span_cut(
    token: str, known_words: "set[str] | frozenset[str]", *, mode: str
) -> bool:
    """A boundary token is a span cut iff it is NOT a known corpus word AND it is a strict prefix
    (end cut) / suffix (start cut) of a LONGER known corpus word. The completion gate keeps
    precision high: a legit-but-rare sentence-ender is either known or has no longer known
    completion, so it does NOT flag; a real span cut ('Resea'->'research') always does. A len-1
    token also requires a longer-corpus-word completion (so a legit one-letter finding survives);
    a len-2 token keeps an abbreviation allowlist."""
    if not token or not known_words:
        return False
    t = token.lower()
    completes = (
        _known_word_has_longer_prefix(t, known_words) if mode == "end"
        else _known_word_has_longer_suffix(t, known_words)
    )
    if len(t) == 1:
        # I-wire-017 (#1339) FIX A: a LOWERCASE single-letter END boundary token ("At t.[2]",
        # "restricted to s.[89]") is a mid-word span cut even when the bare letter is itself a known
        # corpus token (footnote/stat markers make "t"/"s" "known") — so this len-1 branch runs
        # BEFORE the ``t in known_words`` early-out below. Precision guard (this is §-1.1-lethal):
        # the cut is gated on the ORIGINAL token being lowercase, so a legitimate single-CAPITAL
        # label finding — "vitamin C [5]", "hepatitis B [8]", "grade B [12]" — never flags (its
        # boundary token is uppercase). mode=="end" only (a START-of-unit single letter is too weak
        # a signal to drop on). Still gated on the completion test and the {"a","i"} keep-list, per
        # the I-wire-013 (#1327) iter-3b D-P1-2 rationale (a true cut "research"->"r" flags via
        # completion; a legit "type 2 diabetes ... a" survives via {"a","i"}).
        if (
            mode == "end"
            and token[:1].islower()
            and t not in _SINGLE_LETTER_KEEP_TOKENS
            and completes
        ):
            return True
        if t in known_words:
            return False
        return t not in _SINGLE_LETTER_KEEP_TOKENS and completes
    if t in known_words:
        return False
    if len(t) == 2:
        return t not in _SHORT_OK_BOUNDARY_TOKENS and completes
    return completes  # len>=3 and a chopped fragment of a known corpus word -> a span cut


def is_truncated_fragment(
    text: str,
    known_words: "set[str] | frozenset[str] | None" = None,
    *,
    ends_before_marker: bool = False,
    starts_after_marker: bool = False,
) -> bool:
    """True iff ``text`` carries a mid-word / cut-span truncation.

    Two independent, drop-path-safe signals:
      1. UNAMBIGUOUS MARKER (always, no corpus needed): a trailing/closed ellipsis or a trailing
         mid-word hyphen, after stripping trailing ``[N]`` citation markers. Never guesses at a cut
         word from letters alone — a complete sentence with an internal hyphen still passes.
      2. CORPUS-GROUNDED BOUNDARY SPAN-CUT (I-wire-013 #1327, only when ``known_words`` is supplied):
         the boundary token before a ``[N]`` (``ends_before_marker``) or the lowercase token after
         one (``starts_after_marker``) is a non-inflectional prefix/suffix of a LONGER corpus word
         and is itself absent from the corpus — e.g. "… 1.2 Resea.[14]". The corpus allowlist is the
         false-positive guard (a real, complete word is known or has no longer completion).

    BACKWARD-COMPATIBLE: ``known_words=None`` (the default for every legacy caller) skips ONLY the
    corpus-allowlist span-cut leg (signal 2); the always-on truncation-marker leg (signal 1) AND the
    corpus-INDEPENDENT trailing function-word / dangling-"pp." leg (I-wire Wave-A) still run.

    I-deepfix-001 Wave-5 (#1344) adds one OPT-IN, default-OFF render-truncation leg (BYTE-IDENTICAL when
    OFF): FF3-TRUNC-SEM (``PG_FF3_TRUNC_SEM`` — a semantic complement-demanding cut a pure lexical last-word
    rule misses). It DROPS the fragment (return True), never repairs/fabricates; a fault FAILS OPEN + records
    a distinct degrade the Gate-B activation canary rejects. Faithfulness-neutral (no verdict touched). PURE
    except the flag-gated detection-event telemetry (a benign counter side effect, active ONLY when the FF3
    flag is ON). The FF2-TRUNC-v2 lexical legs (copula/aux + lone-letter) were RETIRED as unsound."""
    if not text:
        return False
    core = _TRAILING_CITATION_RE.sub("", text.strip()).rstrip()
    if core and _TRUNCATION_MARKER_RE.search(core):
        return True
    # A2 (I-wire Wave-A) — corpus-INDEPENDENT trailing function-word / dangling-"pp." span cut. High
    # precision (a complete sentence never ends on these), so it runs for EVERY caller (no corpus
    # needed) alongside the always-on marker leg above.
    if core:
        # I-deepfix-001 Wave-5 (#1344): the FF3 semantic render-truncation leg is OPT-IN (default OFF => the
        # leg below is SKIPPED => byte-identical to the pre-Wave-5 HEAD behaviour). The FF2 lexical legs were
        # retired as unsound (see the retirement note below). Read once (LAW VI, call-time) so a per-run
        # slate/env change lands without an import-time freeze.
        _ff3_on = _ff3_trunc_sem_enabled()
        # I-deepfix-001 Wave-5 (#1344) FALSE-GREEN FIX (reviewer P0): record that the flag-ON guard ACTUALLY
        # examined this fragment at the render seam — the LIVENESS proof the activation canary needs. A guard
        # that is flag-ON but whose render seam never called this function leaves ``screened`` at the per-
        # report reset zero, so the emitted marker carries ``reached=False`` and the canary REJECTS it; a
        # still-dark guard can no longer pass on a bare ``detected=0`` marker. Incremented for EVERY examined
        # fragment (before the terminal-punct gate), so a clean report of complete sentences still proves the
        # guard ran with ``detected=0`` — reach is proven WITHOUT requiring detected>0. Gated on the flag =>
        # OFF is byte-identical (no counter is touched when the guard is disabled).
        if _ff3_on:
            _note_ff3_truncation_screened()
        raw_last = _boundary_last_word(core)
        # Codex P1 (Wave-A): an UPPERCASE clinical/statistical acronym or a single-CAPITAL label is a
        # VALID sentence ender, never a dangling function word — do NOT lowercase-collide it into the
        # article/conjunction set. "… an adjusted OR.[5]" ("or"), "… used ITS.[7]" ("its"), "… had
        # type A.[3]" / "… vitamin C.[9]" ("a"/"c") must be KEPT (fail-open per §-1.3, over-strip is
        # worse than a leak). ``str.isupper()`` is True only when every cased char is uppercase, so a
        # genuinely dangling lowercase "the"/"and"/"its" (mixed/lower case) still flags.
        if raw_last and not raw_last.isupper():
            last_word = raw_last.lower()
            # Codex P1 (Wave-A iter-3): defer to the EXISTING short-token keep-lists. "a"/"i"
            # (_SINGLE_LETTER_KEEP_TOKENS) and "an"/"or"/"my" (_SHORT_OK_BOUNDARY_TOKENS) are
            # legitimate short sentence enders already whitelisted by the iwire017 fix ("glucose
            # a.", "vitamin a.", "hepatitis a."), so the function-word cut MUST NOT override them —
            # over-strip is worse than a leak (§-1.3). Only a token that is a dangling function word
            # AND is not an accepted short ender ("… defined by the.", "… driven by and.") flags.
            if (
                last_word in _TRAILING_FUNCTION_WORD_CUT
                and last_word not in _SINGLE_LETTER_KEEP_TOKENS
                and last_word not in _SHORT_OK_BOUNDARY_TOKENS
            ):
                return True
        # FF2-TRUNC-v2 LEXICAL cut legs (a trailing copula/aux cut + a lone-letter-after-connective cut) —
        # RETIRED as UNSOUND (I-deepfix-001; never shipped), for the SAME reason the lone-letter leg was
        # already removed at Wave-5 iter-4 (Codex P1). A trailing copula/aux is lexically AMBIGUOUS between a
        # value cut ("… the share of workers is") and a grammatically COMPLETE fronted-complement / relative /
        # possession / noun-homograph clause ("the tasks that workers do", "the skills workers have", "what
        # assets households have", "political will", "a must", "recovered in May"). No last-word keep-set can
        # separate the two; a corpus-grounded or semantic signal is required, which a pure last-word list
        # lacks. §-1.3 over-strip is the cardinal sin, so both lexical legs are removed entirely. Genuine cuts
        # remain covered by the FF3-TRUNC-SEM semantic leg (below) + the always-on corpus-grounded span-cut
        # leg (``ends_before_marker`` + ``_boundary_token_is_span_cut``, which flags a chopped "China" -> "C"
        # ONLY when it non-inflectionally completes a longer corpus word — the grounded signal the lexical
        # allowlist lacked).
        # FF3-TRUNC-SEM (inv_5) — SEMANTIC truncation: the clause ends on a complement-DEMANDING connective
        # grammar guarantees cannot terminate it (a dangling comparative "…faster than", a cut subordinator
        # "…held unless", an open appositive "…factors namely"/"…drivers such"). FF2's lexical last-word
        # lists MISS these — the tokens are legitimate short words elsewhere — so FF3 is a SEPARATE flag-
        # gated leg (PG_FF3_TRUNC_SEM, default OFF => byte-identical). RENDER-ONLY / FAITHFULNESS-NEUTRAL:
        # it DROPS the unsafe-to-render fragment (returns True), NEVER repairs / fabricates a completion
        # (§-1.3). Gated on ABSENT terminal punctuation (fail-open on a full stop). Fault => FAIL OPEN.
        if _ff3_on and not _ends_with_terminal_punct(core):
            try:
                if _is_semantically_truncated(core):
                    _note_ff3_truncation_detected()
                    return True
            except Exception:  # pragma: no cover - pure string logic; fail-OPEN + disclose degrade
                _note_ff3_truncation_failopen()
        pp_match = _DANGLING_PP_RE.search(core)
        if pp_match and not any(ch.isdigit() for ch in pp_match.group(1)):
            return True
    if not known_words:
        return False
    if ends_before_marker and _boundary_token_is_span_cut(
        _boundary_last_word(core), known_words, mode="end"
    ):
        return True
    if starts_after_marker:
        lead = _LEADING_CITATION_RE.sub("", text).lstrip()
        first = _boundary_first_word(lead)
        if first and first[:1].islower() and _boundary_token_is_span_cut(
            first, known_words, mode="start"
        ):
            return True
    return False


def _is_render_chrome_claim(sentence: str) -> bool:
    """I-wire-012 (#1326): True iff ``sentence`` is render-side chrome / page-furniture /
    an unrenderable fragment per THE ONE shared predicate
    (``weighted_enrichment.is_render_chrome_or_unrenderable``). Lifting Key-Findings /
    Abstract / Conclusion / depth findings through this is faithfulness-STRENGTHENING — a
    chrome span that survived strict_verify (it is a verbatim span of fetched furniture)
    must NOT lead a finding. Lazy import (the predicate lazy-imports this module's
    ``is_truncated_fragment``, so a module-top import would cycle). Fail-CONSERVATIVE: on
    any import error, keep the sentence (never silently drop a real finding)."""
    try:
        from src.polaris_graph.generator.weighted_enrichment import (  # noqa: PLC0415
            is_render_chrome_or_unrenderable,
        )
    except Exception:  # pragma: no cover - weighted_enrichment is stable in-tree
        return False
    try:
        return bool(is_render_chrome_or_unrenderable(sentence, require_sentence_form=True))
    except Exception:  # pragma: no cover - the predicate is pure in-tree
        return False


def _max_key_findings_markers() -> int:
    """Per-run citation cap for the Key-Findings summary (LAW VI). Floored at 1; fail-soft on a
    non-int (the summary must never be silently emptied of citations)."""
    raw = os.getenv("PG_KEY_FINDINGS_MAX_MARKERS", "").strip()
    if not raw:
        return _DEFAULT_MAX_MARKERS
    try:
        return max(1, int(raw))
    except ValueError:
        return _DEFAULT_MAX_MARKERS


def cap_citation_marker_runs(sentence: str, max_markers: int) -> str:
    """Trim every RUN of adjacent ``[N]`` markers in ``sentence`` to its first ``max_markers``.

    The markers are carried VERBATIM from a body span that already passed strict_verify, so each is
    span-supported; this only bounds how many co-citations a SUMMARY line displays per run (document
    order = the body's own relevance priority). PURE; ``max_markers <= 0`` returns the input
    unchanged (never strips all citations)."""
    if max_markers <= 0 or not sentence:
        return sentence

    def _cap(match: re.Match[str]) -> str:
        nums = re.findall(r"\[(\d+)\]", match.group(0))
        return "".join(f"[{n}]" for n in nums[:max_markers])

    return _ADJACENT_MARKER_RUN_RE.sub(_cap, sentence)


def key_findings_enabled() -> bool:
    """Default ON. `PG_SWEEP_KEY_FINDINGS=0` ships the report without the exec-summary block (cold-open)."""
    return os.getenv("PG_SWEEP_KEY_FINDINGS", "1").strip().lower() not in _OFF_VALUES


def _strip_leading_markdown_headers(text: str) -> str:
    """Drop leading markdown header lines (and blanks) from a section's verified_text
    (I-perm-008 #1202). A section header that leaked into ``verified_text`` (e.g.
    "### Pathogenic bacteria...") would otherwise be lifted AS the headline finding via the
    DOTALL sentence regex, producing a "- **Section.** ### <header> ..." bullet that breaks the
    Key-Findings block boundary. Stripping leading headers makes the lift a clean prose sentence."""
    lines = (text or "").split("\n")
    i = 0
    while i < len(lines) and (not lines[i].strip() or _ATX_HEADER_RE.match(lines[i].lstrip())):
        i += 1
    return "\n".join(lines[i:])


def _relevance_weight(
    sentence_relevance: "Callable[[str], float]", sentence: str
) -> float:
    """The caller-supplied question-relevance weight for ``sentence``, fail-CONSERVATIVE.

    A higher value means more on-topic. The ranker is caller-owned (the render seam wires the
    already-computed cross-encoder question-relevance); on ANY exception we return a NEUTRAL 0.0
    so a ranker bug can never crash the report NOR silently drop a finding — it only falls back to
    document order for that sentence. PURE."""
    try:
        return float(sentence_relevance(sentence))
    except Exception:  # pragma: no cover - the ranker is caller-owned; neutral on failure
        return 0.0


def make_question_relevance_ranker(
    question_text: str,
) -> "Callable[[str], float] | None":
    """Build a WEIGHT-only question-relevance ranker for the headline / Abstract render seam.

    Returns a PURE callable ``ranker(sentence) -> float`` = the count of content words the sentence
    shares with ``question_text`` (higher = more on-topic). It is a RE-ORDER WEIGHT over sentences
    that ALREADY passed the frozen faithfulness engine (§-1.3 Principle 1 — WEIGHT, never FILTER): it
    can only change bullet / abstract ORDER, never drop, filter, or re-verify a claim. Reuses the
    EXISTING grounding tokenizer (``provenance_generator._content_words``: alphabetic, ≥3 chars,
    stopword-stripped) — no new model, no new magic word list, no spend. The tokenizer is imported
    LAZILY (mirrors ``plan_sufficiency_gate._content_words``) so this light no-spend module keeps its
    import-time independence from the generator stack.

    Returns ``None`` when ``question_text`` has NO content words, so the caller threads
    ``sentence_relevance=None`` and gets byte-identical document order (never a degenerate all-zero
    ranker). PURE; no network, no GPU, no LLM."""
    from src.polaris_graph.generator.provenance_generator import (  # noqa: PLC0415
        _content_words,
    )
    question_words = _content_words(question_text or "")
    if not question_words:
        return None

    def _ranker(sentence: str) -> float:
        # Overlap COUNT is a monotone on-topicness weight; it never drops or re-verifies a sentence.
        return float(len(_content_words(sentence or "") & question_words))

    return _ranker


# I-deepfix-001 U13 (representation faithfulness): a numeric-claim headline must carry a
# SUBJECT/POPULATION anchor. Otherwise a bare quantity ("highest reduction of 99.4%") LEADS and
# misrepresents its cited span — whose subject (e.g. an animal / in-vitro model) was stripped —
# so a lab number reads as a human/clinical finding (strict_verify passes on decimal + content-word
# overlap; it does not check subject faithfulness). This DEMOTES an unanchored numeric-claim
# sentence BELOW subject-anchored / non-numeric verified sentences so it never occupies the lead
# slot. SUPPRESS / STABLE-REORDER ONLY — it never rewrites a sentence and never drops a source
# (§-1.3 WEIGHT-not-filter): the sentence still renders if it is the only verified candidate. The
# frozen faithfulness engine is untouched. Default-ON; PG_KF_SUBJECT_ANCHOR=0 reverts byte-identical.
_U13_SUBJECT_ANCHOR_ENV = "PG_KF_SUBJECT_ANCHOR"
# Citation markers ("[12]") are stripped BEFORE the numeric test so a reference number is never
# mistaken for a numeric claim. A numeric CLAIM = a decimal, a percentage, a fold/times multiplier,
# any integer >=2 digits, or a small integer directly modifying a count noun (deaths/cases/...).
# (I-deepfix-001 U13 iter5, Codex: whole-number fold/count claims like "2-fold"/"18-fold"/"17 deaths"
# must be treated as numeric claims that need a subject anchor, not skipped as "non-numeric".)
_CITATION_STRIP_RE = re.compile(r"\[\d+\]")
_NUMERIC_CLAIM_RE = re.compile(
    r"\d\.\d"
    r"|\b\d+(?:\.\d+)?\s?%"
    r"|\b\d+(?:\.\d+)?\s?-?\s?(?:fold|times|x)\b"
    r"|\d+(?:\.\d+)?\s?[×✕]"  # Unicode multiplier ("2×"/"2 ×") — no trailing \b (× is non-word)
    r"|\b\d{2,}\b"
    r"|\b\d+\s+(?:deaths?|cases?|events?|fatalit\w+|patients?|participants?|subjects?|"
    r"infections?|hospitali\w+|admissions?|responders?)\b",
    re.I,
)
_SUBJECT_ANCHOR_RE = re.compile(
    r"\b(patients?|adults?|children|participants?|subjects?|women|men|"
    r"population|cohort|trial|studies|study|meta-?analysis|systematic review|"
    r"mice|rats?|animals?|poultry|livestock|cells?|in ?vitro|in ?vivo|humans?|"
    r"individuals?|cases?|infants?|neonat\w+|elderly|volunteers?|"
    r"carriers?|genotypes?|alleles?|variants?|homozygous|heterozygous|"
    r"mutations?|APOE\w*|BRCA\w*|receptors?|patients)\b",
    re.I,
)
# I-deepfix-001 U13 iter2: capitalized CALENDAR / STRUCTURAL tokens are NOT subjects — "Week 12",
# "Phase 2", "Table 3", "Figure 1", "Arm B", "Q3" must NOT anchor a bare numeric headline, else a
# misrepresenting quantity ("reduction of 99.4% at Week 12") falsely reads as subject-anchored.
_STRUCTURAL_NONSUBJECT = frozenset(
    "week weeks phase phases table tables figure figures fig day days month months year years "
    "group groups arm arms visit visits section sections chapter chapters baseline timepoint "
    "timepoints panel appendix supplementary supplement q1 q2 q3 q4 h1 h2 no vol volume "
    "part parts step steps stage stages level levels tier round rounds "
    # metric / outcome nouns — a headline naming only a metric + a bare number (no population)
    # is NOT subject-anchored ("Efficacy reached 88%" must not lead over a population-anchored finding)
    "efficacy response responses mortality incidence survival prevalence sensitivity specificity "
    "accuracy remission recurrence relapse adherence compliance tolerability safety uptake "
    "reduction increase improvement decline decrease rate rates ratio ratios odds hazard".split()
)


def _subject_anchor_enabled() -> bool:
    import os
    return os.getenv(_U13_SUBJECT_ANCHOR_ENV, "1").strip().lower() not in ("0", "false", "no", "off")


# Common sentence-initial function/determiner/framing words whose leading capital is grammatical,
# NOT a proper-noun subject. A sentence-initial capitalized word NOT in this set (e.g. a drug /
# organism / trial name like "Metformin") counts as a subject anchor.
_COMMON_STARTERS = frozenset(
    "the a an this that these those it its they their there we our overall results "
    "result findings finding data evidence highest lowest mean median average approximately "
    "about around nearly over under up to at in on of for by with among between across after "
    "before during however moreover additionally notably importantly furthermore similarly "
    "conversely subsequently significant significantly increased decreased reduced higher lower "
    "when where while although though because since if compared relative".split()
)


def _is_subject_anchored_numeric(sentence: str) -> bool:
    """True iff `sentence` is safe to LEAD a headline: either it is not a numeric claim (nothing to
    misrepresent) OR its numeric claim is anchored to a subject/population/study noun-phrase or a
    capitalized proper-noun subject (drug / organism / trial name), including a sentence-initial one
    that is not a common function/framing word. A bare "quantity + metric" numeric fragment with no
    such anchor returns False and is demoted (never dropped)."""
    if not _NUMERIC_CLAIM_RE.search(_CITATION_STRIP_RE.sub(" ", sentence or "")):
        return True
    # ALLOWLIST-only anchoring (I-deepfix-001 U13 iter6, Codex): a numeric claim is safe to LEAD a
    # headline ONLY if it carries a POSITIVE subject/population term from _SUBJECT_ANCHOR_RE
    # (patients/adults/cohort/mice/in-vitro/carriers/APOE*/...). We do NOT try to guess a proper-noun
    # subject from capitalization — that repeatedly false-anchored on capitalized NON-subjects
    # (sentence-initial "Risk"/"Efficacy", and mid-sentence structural labels "Cycle 4"/"Dose 2"/
    # "Grade 3"), an open-ended blocklist that never converges. A bare quantity that names only a
    # drug/trial/structural label but no population is demoted (reorder-only, never dropped). This is
    # convergent: an allowlist cannot false-anchor on an unknown capitalized token.
    return bool(_SUBJECT_ANCHOR_RE.search(sentence or ""))


def _first_verified_sentences(
    verified_text: str,
    n: int,
    *,
    sentence_relevance: "Callable[[str], float] | None" = None,
    demote_unanchored: bool = False,
) -> list[str]:
    matches = [m.group(0).strip() for m in _SENTENCE_RE.finditer(verified_text or "")]
    # A Key Finding is a span-verified CLAIM: it must carry a citation, must NOT be
    # gap-disclosure boilerplate (whose 2nd sentence is cited to the gap-task sidecar, not
    # an evidence span), and must NOT be a markdown header line (I-perm-008 — a leaked "###"
    # header is never a finding). The filters together exclude every gap/header shape in a
    # mixed section (I-gen-006 #1178 C07/P07, Codex iter-5).
    # I-wire-011 (#1325) fix 2: also exclude a sentence carrying an unambiguous mid-word truncation
    # marker (a cut fetch span like "…comprehensi [...") so a fragment never leads a finding. Shared
    # by the Abstract/Conclusion harvesters; strengthening (it can only suppress a fragment).
    # I-wire-012 (#1326): also exclude a sentence that is render-side chrome / page-furniture
    # per THE ONE shared predicate (masthead/ISSN/ResearchGate/ToC/CC-license/ORCID/doc-label/
    # mid-word-start/incomplete) — so a chrome span never LEADS a Key-Findings / Abstract /
    # Conclusion / depth finding. Default-ON (PG_RENDER_CHROME_SCREEN=0 reverts to byte-identical).
    verified = [
        s for s in matches
        if s
        and not _ATX_HEADER_RE.match(s.lstrip())
        and _CITATION_RE.search(s)
        and not _GAP_MARKER_RE.search(s)
        and not is_truncated_fragment(s)
        and not _is_render_chrome_claim(s)
    ]
    # headline_relevance (I-deepfix-001): WEIGHT, not filter (§-1.3 Principle 1). When the caller
    # wires a question-relevance ranker, STABLE-sort the ALREADY-verified candidates by descending
    # on-topicness so the most on-topic verified sentence leads. It NEVER drops a sentence — the
    # head-``n`` slice is the pre-existing summary cap, not a faithfulness gate. None => byte-identical.
    # I-deepfix-001 U13: STABLE-partition subject-anchored / non-numeric verified sentences BEFORE
    # unanchored bare-number claims so a misrepresenting bare quantity never LEADS. When a relevance
    # ranker is wired the key is (anchor primary, relevance secondary); otherwise anchor-only stable
    # partition. Reorder-only + STABLE — an unanchored claim still appears (and still leads if it is
    # the ONLY candidate); nothing is dropped (§-1.3). PG_KF_SUBJECT_ANCHOR=0 => byte-identical.
    # I-deepfix-001 U13 iter2 (Codex P1): the anchor demote is OPT-IN via demote_unanchored so it
    # applies ONLY to the Key-Findings headline slot. `_first_verified_sentences` is SHARED — the
    # Abstract/Conclusion harvester (abstract_conclusion.py) calls it for ALL verified sentences in
    # DOCUMENT ORDER and picks ordered[-1] as the Conclusion; reordering there would push a demoted
    # bare-number sentence to the end and PROMOTE it into the Conclusion. Default False => document
    # order preserved for every non-KF caller (byte-identical).
    anchor_on = _subject_anchor_enabled() and demote_unanchored
    if sentence_relevance is not None:
        verified = sorted(
            verified,
            key=lambda s: (
                0 if (not anchor_on or _is_subject_anchored_numeric(s)) else 1,
                -_relevance_weight(sentence_relevance, s),
            ),
        )
    elif anchor_on:
        verified = sorted(
            verified, key=lambda s: 0 if _is_subject_anchored_numeric(s) else 1
        )
    return verified[:n]


def refilter_key_findings_block(report_text: str) -> str:
    """Drop Key-Findings bullets that became a redaction STUB after the four-role seam
    (I-perm-008 #1202, blueprint R7).

    ``build_key_findings`` is assembled PRE-four-role on strict_verify-passed prose, so a lifted
    headline finding the four-role seam later marks non-VERIFIED is redacted in report.md into a
    "- **Section.** <gap stub>" pseudo-finding. The redactor runs AFTER Key Findings is built, so
    it cannot prevent the stub bullet; this post-redaction pass removes any KF bullet whose body
    now matches the gap-disclosure boilerplate (``_GAP_MARKER_RE``). With the leaked-header strip
    in ``build_key_findings`` each bullet is a clean single line, so a line-scoped drop is exact.
    If no genuine finding remains, the whole block is dropped (no empty heading). Idempotent +
    byte-identical when no KF bullet was redacted.
    """
    if not key_findings_enabled():
        return report_text
    header_match = re.search(r"(?m)^##\s*Key Findings\s*$", report_text)
    if not header_match:
        return report_text
    block_start = header_match.start()
    rest = report_text[header_match.end():]
    next_header = re.search(r"(?m)^#{1,6}\s", rest)
    block_end = header_match.end() + (next_header.start() if next_header else len(rest))

    kept_lines: list[str] = []
    dropped_any = False
    for line in report_text[block_start:block_end].splitlines():
        # Within the bounded KF block, ANY gap-disclosure line is a redacted finding — the real
        # `reconcile_report_against_verdicts` replaces the WHOLE bullet (including the
        # "- **Section.**" prefix) with a BARE stub line, so a `- `-prefix check misses it
        # (Codex iter-1 P1). The block's only other lines are the heading + the italic preamble,
        # neither of which matches `_GAP_MARKER_RE`, so this never drops a legitimate line.
        if _GAP_MARKER_RE.search(line):
            dropped_any = True
            continue
        kept_lines.append(line)
    if not dropped_any:
        return report_text  # byte-identical when nothing was a stub
    new_block = "\n".join(kept_lines)
    if not re.search(r"(?m)^\s*-\s+\S", new_block):
        trimmed = report_text[:block_start] + report_text[block_end:]
        return re.sub(r"^\n+", "", trimmed) if block_start == 0 else trimmed
    if not new_block.endswith("\n"):
        new_block += "\n"
    return report_text[:block_start] + new_block + report_text[block_end:]


def humanize_section_title(title: str) -> str:
    """Render a RAW contract entity_id section title as its human display title.

    I-deepfix-001: an outline section bound to a contract entity sometimes carries the raw snake_case
    entity_id as its title (e.g. "Generative_AI_Evidence", "Foundational_Theory"), which then leaks
    into a "### Generative_AI_Evidence" header / "**Generative_AI_Evidence.**" bullet. Heuristic that
    fires ONLY on the raw-id shape: an underscore present AND no space (a real multi-word title like
    "Robots and Jobs" already has spaces and is returned untouched). Underscores collapse to single
    spaces; existing token casing is preserved so initialisms ("AI", "U.S.") survive. Pure render-only
    — touches no claim, verdict, count, or faithfulness path."""
    t = (title or "").strip()
    if t and "_" in t and " " not in t:
        t = re.sub(r"_+", " ", t).strip()
    return t


def build_key_findings(
    sections: list[Any],
    *,
    sentence_relevance: "Callable[[str], float] | None" = None,
) -> str:
    """Return a markdown "## Key Findings" block: the first verified sentence (verbatim, citation intact)
    from each non-dropped section with verified_text. Verified-only + extractive — never a new claim.
    Returns "" when disabled or when no section has verified prose (no empty heading).

    ``sentence_relevance`` (headline_relevance, I-deepfix-001): OPTIONAL caller-wired question-
    relevance ranker. WEIGHT never filter (§-1.3): within-section the most on-topic verified sentence
    leads and bullets are GLOBALLY ordered by descending relevance; off-topic sinks past
    ``_MAX_BULLETS``. ``None`` (every existing caller) => byte-identical document order."""
    if not key_findings_enabled():
        return ""
    candidates: list[tuple[float, str]] = []
    for sr in sections or []:
        if getattr(sr, "dropped_due_to_failure", False):
            continue
        # I-gen-006 (#1178) BB5-C07/P07: a 0-verified gap DISCLOSURE renders disclosure
        # text in verified_text (the legacy is_gap_stub or a V30 contract gap) but is NOT
        # span-verified prose — it must never surface as a Key-Findings "span-verified
        # statement". Skip every gap disclosure (universal signal: sentences_verified == 0).
        if getattr(sr, "is_gap_stub", False) or getattr(sr, "sentences_verified", 1) == 0:
            continue
        # I-perm-008: strip any leaked leading section header so it is never lifted as the
        # headline finding (a "### ..." header would otherwise break the KF block boundary).
        verified_text = _strip_leading_markdown_headers(getattr(sr, "verified_text", "") or "")
        if not verified_text.strip():
            continue
        title = humanize_section_title(getattr(sr, "title", "") or "")
        _marker_cap = _max_key_findings_markers()
        for sentence in _first_verified_sentences(
            verified_text,
            _SENTENCES_PER_SECTION,
            sentence_relevance=sentence_relevance,
            demote_unanchored=True,  # U13: KF headline is the ONLY surface that demotes bare numbers
        ):
            # Weigh the ORIGINAL sentence (all `[N]` markers intact) BEFORE capping the display run.
            weight = (
                _relevance_weight(sentence_relevance, sentence)
                if sentence_relevance is not None
                else 0.0
            )
            # I-wire-011 (#1325) fix 2: cap each adjacent citation-marker RUN to the most-relevant
            # few (document order). Render-only; the body + bibliography keep every reference.
            sentence = cap_citation_marker_runs(sentence, _marker_cap)
            label = f"**{title}.** " if title else ""
            candidates.append((weight, f"- {label}{sentence}"))
    if sentence_relevance is not None:
        # STABLE descending-weight order: ties keep document order; off-topic sinks past _MAX_BULLETS.
        candidates = sorted(candidates, key=lambda c: -c[0])
    bullets = [bullet for _, bullet in candidates][:_MAX_BULLETS]
    if not bullets:
        return ""
    # I-beatboth-011 §3.2 (#1289): HONEST self-cert label (was the over-claiming absolute
    # "span-verified statement" — a verbatim self-quote tautologically passes strict_verify, so the
    # absolute phrasing implied a guarantee the engine does not make). State the REAL guarantee.
    # LABEL honesty only — the faithfulness engine is UNTOUCHED.
    header = (
        "## Key Findings\n\n"
        "_Each finding below is verbatim text carried up from a cited body span; it passes strict_verify "
        "(span bounds + numeric match + ≥2 content-word grounding) but is single-origin unless marked "
        "corroborated, and span-grounding is NOT a peer-reviewed or on-topic guarantee. Citations are "
        "the body's._\n\n"
    )
    return header + "\n".join(bullets) + "\n\n"


# I-wire-011 (#1325) fix 6 — per-section analytical-depth layer (default-OFF, LAW VI).
#
# GENUINE grounded synthesis (NOT pattern-injection — the §-1.1 ban). For each verified section it
# labels the section's HEADLINE verified finding under a per-section ``**Key Findings**`` subhead and,
# ONLY when the section's own verified prose actually carries a challenge/limitation, lifts that
# verbatim challenge sentence under a ``**Challenges**`` subhead. Every emitted line is verbatim,
# cited, span-verified body text — so it raises the advisory analytical_depth key_findings/challenge
# counts HONESTLY (real content), never by injecting empty marker strings. No challenge sentence => no
# Challenges line (never a fabricated limitation). Default-OFF => no block => byte-identical.
_DEPTH_LAYER_ENV = "PG_SWEEP_DEPTH_LAYER"
# The SAME challenge cues the analytical_depth metric scores (kept in sync deliberately) — used to
# pick a REAL limitation sentence from the section's verified prose, never to fabricate one.
_CHALLENGE_CUE_RE = re.compile(
    r"\b(limitation|contradict|conflicting|gap in|insufficient evidence|notable absence|"
    r"remains unclear|further research|caveat|uncertain)\b",
    re.I,
)
# I-wire-012 (#1326) synthesis pass — a SURFACED TENSION is a verbatim verified sentence that
# expresses cross-source DISAGREEMENT / opposition (however / in contrast / whereas / conversely /
# disagree / diverge). Like the challenge lift it is verbatim, cited, span-verified body prose —
# faithful BY IDENTITY (never a generated cross-claim recombination, which abstract_conclusion.py
# proved unsound). Distinct cue set from the challenge so a section can surface BOTH.
_TENSION_CUE_RE = re.compile(
    r"\b(however|in contrast|by contrast|conversely|whereas|on the other hand|disagree\w*|"
    r"diverg\w*|inconsistent\w*|at odds|opposite\w*)\b",
    re.I,
)


def depth_layer_enabled() -> bool:
    """DEFAULT-ON (I-deepfix-001 cov C2). Appends the per-section analytical-depth layer AND injects
    the depth_synthesis DS-* live synthesizer (``make_depth_synthesizer`` ->
    ``synthesize_cross_source_findings``, each within-basket cross-source finding RE-GROUNDED through
    the UNCHANGED strict_verify — a finding with no grounding span is DROPPED) on the cert render path
    by default, not only when the benchmark cert slate force-pins the flag.

    Kill-switch (LAW VI): ``PG_SWEEP_DEPTH_LAYER=0`` (or false/off/no) => the depth layer + DS-*
    synthesis are skipped and the render is BYTE-IDENTICAL to the pre-cov legacy path. §-1.3: additive
    keep-all analysis lever, never a cap; faithfulness untouched."""
    return os.getenv(_DEPTH_LAYER_ENV, "1").strip().lower() not in _OFF_VALUES


def build_depth_layer(
    sections: list[Any],
    *,
    synthesized_findings: list[str] | None = None,
) -> str:
    """Return a ``## Analytical synthesis`` block.

    Two grounded layers, both verbatim/cited/span-verified — zero new unverified claims:

    * ``synthesized_findings`` (I-wire-013 #1327 iter-3c): the OPTIONAL grounded digest produced by
      ``depth_synthesis.synthesize_cross_source_findings`` — a list of
      ``{"sentence", "tier", "label"}`` dicts (a bare string from a legacy caller is treated as
      ``cross_source``). Each sentence ALREADY passed the UNCHANGED ``strict_verify`` (a synthesized
      sentence with no grounding span was DROPPED) and carries the report's own ``[N]`` citations. The
      per-basket TWO-TIER split renders the ``>=2``-distinct-surviving-origin findings under a
      ``### Cross-source synthesis`` subhead and the post-verify COLLAPSE case (1 surviving origin)
      under ``### Single-source findings`` with each bullet ``(single source)``-labeled (surfaced, not
      dropped — §-1.3). ``None``/empty (the legacy call) => both subheads omitted.
    * Per verified section: the headline finding under ``**Key Findings**`` and (only when the
      evidence raises one) a verbatim ``**Challenges**`` / ``**Tension**`` sentence — lifted verbatim
      from the section's already-verified prose.

    "" when disabled, or when there is neither a synthesized finding nor any section with verified
    prose (no empty heading)."""
    if not depth_layer_enabled():
        return ""
    # I-wire-013 (#1327) iter-3c — TWO-TIER render. ``synthesize_cross_source_findings`` returns dicts
    # ``{"sentence", "tier", "label"}``; a bare string (a legacy caller) is treated as cross_source with
    # no label. The ``>=2``-distinct-surviving-origin baskets render under ``### Cross-source synthesis``;
    # the post-verify COLLAPSE case (1 surviving origin) renders under ``### Single-source findings`` with
    # each bullet carrying its ``(single source)`` label — SURFACED, never dropped (§-1.3).
    cross_items: list[str] = []
    single_items: list[str] = []
    for item in (synthesized_findings or []):
        if isinstance(item, dict):
            sentence = str(item.get("sentence", "") or "").strip()
            tier = str(item.get("tier", "") or "cross_source").strip().lower()
            label = str(item.get("label", "") or "").strip()
        else:
            sentence = str(item or "").strip()
            tier = "cross_source"
            label = ""
        if not sentence:
            continue
        rendered = f"{sentence} {label}".strip() if label else sentence
        if tier == "single_source":
            single_items.append(rendered)
        else:
            cross_items.append(rendered)
    blocks: list[str] = []
    if cross_items:
        # HONEST provenance sub-label (§-1.1 — a misstated provenance label is treated as lethal): the
        # cross-source bullets are GENERATOR-PHRASED then re-grounded, NOT verbatim body lifts, so they
        # must NOT inherit the per-section block's "verbatim … no new claim" framing. State the REAL
        # guarantee: each consolidates >=2 corroborating sources and re-passed strict_verify (or was
        # dropped). LABEL honesty only — the faithfulness engine is UNTOUCHED.
        cross_label = (
            "_Each finding below consolidates >=2 corroborating sources; it is generator-phrased "
            "(not a verbatim quote) and every sentence re-passed strict_verify (span bounds + numeric "
            "match + content grounding) or was dropped. Citations are the report's._"
        )
        blocks.append(
            "### Cross-source synthesis\n\n" + cross_label + "\n\n"
            + "\n".join(f"- {item}" for item in cross_items)
        )
    if single_items:
        # HONEST sub-label for the COLLAPSE tier: drawn from a multi-source basket where only ONE source
        # re-grounded after strict_verify — so it must NOT claim >=2 corroboration. Surfaced + labeled
        # (§-1.3 "don't drop, label weak weak"); each sentence re-passed strict_verify or was dropped.
        single_label = (
            "_Each finding below is drawn from a multi-source basket where only one source re-grounded "
            "after strict_verify; it is generator-phrased, marked (single source), and every sentence "
            "re-passed strict_verify (span bounds + numeric match + content grounding) or was dropped. "
            "Citations are the report's._"
        )
        blocks.append(
            "### Single-source findings\n\n" + single_label + "\n\n"
            + "\n".join(f"- {item}" for item in single_items)
        )
    _cap = _max_key_findings_markers()
    # FIX-3 (#1344): the front ``## Key Findings`` block (build_key_findings) already renders
    # each verified section's first sentence as a headline. When that block is rendered, the
    # per-section Analytical-synthesis headline below is a CROSS-SURFACE DUPLICATE — so omit it
    # here and carry only the DISTINCT Challenges/Tension sentences. Headline-LABEL de-dup only:
    # nothing leaves the corpus/bibliography/body; the headline still renders once in the front
    # KF block and once in the section body. Built only when the front KF block is rendered.
    front_headlines: set[str] = set()
    if key_findings_enabled():
        for sr in sections or []:
            if getattr(sr, "dropped_due_to_failure", False):
                continue
            if getattr(sr, "is_gap_stub", False) or getattr(sr, "sentences_verified", 1) == 0:
                continue
            _vt = _strip_leading_markdown_headers(getattr(sr, "verified_text", "") or "")
            _first = _first_verified_sentences(_vt, 1)
            if _first:
                front_headlines.add(_first[0])
    for sr in sections or []:
        if getattr(sr, "dropped_due_to_failure", False):
            continue
        if getattr(sr, "is_gap_stub", False) or getattr(sr, "sentences_verified", 1) == 0:
            continue
        verified_text = _strip_leading_markdown_headers(getattr(sr, "verified_text", "") or "")
        if not verified_text.strip():
            continue
        ordered = _first_verified_sentences(verified_text, 10_000)
        if not ordered:
            continue
        title = humanize_section_title(getattr(sr, "title", "") or "Section") or "Section"
        headline = cap_citation_marker_runs(ordered[0], _cap)
        lines = [f"### {title}", ""]
        # Lift a REAL challenge sentence (a verbatim verified sentence carrying a challenge cue) —
        # never fabricate one. Prefer one distinct from the headline.
        challenge = next(
            (s for s in ordered if _CHALLENGE_CUE_RE.search(s) and s != headline),
            "",
        )
        if challenge:
            lines.append(f"**Challenges** {cap_citation_marker_runs(challenge, _cap)}")
        # I-wire-012 (#1326): surface a REAL cross-source tension — a verbatim verified sentence
        # carrying a disagreement/opposition cue, distinct from the headline AND the challenge. Never
        # fabricated: if the section's own verified prose raises no opposition, no Tension line.
        # I-deepfix-001 (#1369) STEP 4 anti-signal: also exclude a Tension that is the SAME sentence as the
        # headline (or challenge) modulo citation markers / whitespace — the exact ``!= headline`` string
        # guard misses a formatting-only difference, which is how a Tension line duplicated its own headline
        # in the drb_72 report. Normalized = strip [N] markers + collapse whitespace + lowercase. Default-ON
        # kill-switch PG_TENSION_HEADLINE_DEDUP (OFF => byte-identical exact-string guard only).
        _tension_dedup_on = os.getenv("PG_TENSION_HEADLINE_DEDUP", "1").strip().lower() not in (
            "", "0", "false", "off", "no",
        )

        def _norm_dedup(_s: str) -> str:
            return re.sub(r"\s+", " ", re.sub(r"\[[^\]]*\]", "", _s or "")).strip().lower()

        _hl_norm = _norm_dedup(headline) if _tension_dedup_on else None
        _ch_norm = _norm_dedup(challenge) if _tension_dedup_on else None
        tension = next(
            (s for s in ordered
             if _TENSION_CUE_RE.search(s) and s != headline and s != challenge
             and (not _tension_dedup_on or (_norm_dedup(s) != _hl_norm and _norm_dedup(s) != _ch_norm))),
            "",
        )
        if tension:
            lines.append(f"**Tension** {cap_citation_marker_runs(tension, _cap)}")
        # FIX-3 (#1344): emit the headline line ONLY when there is no distinct Challenges/Tension
        # to carry this subsection. If the front KF block already owns the headline, omit the whole
        # subsection (no duplicate); if the KF block is off, the headline has no other home so keep it.
        if not challenge and not tension:
            if ordered[0] in front_headlines:
                continue  # KF block already owns the headline -> omit, don't duplicate
            lines.append(f"**Key Findings** {headline}")  # KF block off -> headline's only home
        if len(lines) == 2:  # only "### title" + "" -> no distinct content to carry
            continue
        blocks.append("\n".join(lines))
    if not blocks:
        return ""
    header = (
        "## Analytical synthesis\n\n"
        "_Per-section, the distinct **Challenges**/**Tension** the evidence itself raises (the "
        "headline finding lives in the Key Findings block above and is not repeated here); a "
        "headline appears below only when the section raises no separate tension/challenge. All "
        "carried up verbatim from cited, span-verified body prose; no new claim._\n\n"
    )
    return header + "\n\n".join(blocks) + "\n\n"
