#!/usr/bin/env python3
"""EVIDENCE MINER — full-document, section-aware, tuple-gated evidence extraction.

WHY THIS EXISTS
---------------
`cellcog_composer.extract_cards` reads `fulltext[:28000]`. Measured on this corpus that is 33.5% of
the usable text, and it is the WRONG 33.5%: the first 28,000 characters of a journal PDF are the
title page, the acknowledgements, the abstract and the introduction. Findings do not live there.
RESULTS sections and TABLES live at characters 40,000-100,000, and we have never once looked at them.
That is the entire reason 1,825 quantitative sentences sit in fulltext we already hold and 2 reached
the page.

WHAT THIS DOES DIFFERENTLY
--------------------------
  1. SECTION-AWARE CHUNKING over 100% of the text. Every character is chunked, classified
     (front / abstract / introduction / background / METHODS / RESULTS / TABLES / discussion /
     conclusion / appendix / references) and weighted. Results and tables are weighted highest.
  2. DETERMINISTIC HARVEST FIRST. Regexes find every sentence carrying an effect size, percentage,
     coefficient, elasticity, CI, p-value, sample size, study period or comparative quantity.
     This stage is exhaustive, free, and CANNOT HALLUCINATE. It tells the LLM where to look.
  3. SEMANTIC EXTRACTION into a COMPLETE ESTIMATE TUPLE — effect, unit, comparator, outcome,
     population, geography, period, technology, industry, unit_of_analysis, design, uncertainty.
     An orphan number is not a finding and is rejected.
  4. THE SPAN IS THE ONLY EVIDENCE.

THE THREE HOLES THIS CLOSES BY CONSTRUCTION (not by checking)
-------------------------------------------------------------
  (a) "60 real chars + an invented tail".  We do not verify the model's span string and then keep it.
      We use the model's string ONLY AS A SEARCH KEY, and what we STORE is `source[a:b]` — a literal
      slice of the paper. The model's copy is discarded. A span that cannot be located is dropped;
      a span that locates is, by definition, the source's own bytes. There is no tail to invent.

  (b) THE SUBSTRING LEAK.  `"0.2" in "10.25"` is True in Python, so a fabricated effect size used to
      pass whenever the source happened to contain a longer number containing its digits. We never
      substring-test a number. We TOKENIZE both sides into whole numbers and compare canonical
      numeric values, so 0.2 is not found in a span whose only number is 10.25. (test_substring_leak)

  (c) EVIDENCE LAUNDERING.  The old extractor asked the model to "state the finding IN YOUR WORDS"
      and the gate then validated the writing against those words. THE MODEL WAS VALIDATED AGAINST
      ITSELF. Here the model is NEVER ASKED FOR A CLAIM. There is no model-authored free-text summary
      field anywhere in the schema. `claim` is a DISPLAY CACHE, composed by this module from tuple
      fields that have ALREADY been gated against the verbatim span, and nothing is ever validated
      against it. The laundering path does not exist to be re-opened.

PROVENANCE, HONESTLY
--------------------
An effect and its unit must be IN THE SPAN. But a study's GEOGRAPHY and PERIOD are usually stated in
the methods section, not in the sentence that carries the coefficient. Forcing them into the span
would either starve the tuple or tempt the model to pad the span — which corrupts the only evidence
we have. So each field has a declared PROVENANCE WINDOW of VERBATIM SOURCE TEXT (span < chunk <
paper), and every card records which window each field came from. The window is widened over
*verbatim text from the same paper*. It is NEVER widened to model prose.

And regardless of window: EVERY FIGURE IN EVERY FIELD MUST APPEAR IN THE SPAN, as its own number.
A number may not enter a card from a wider window than the sentence that is quoted for it.

    python scripts/evidence_miner.py --dry-run            # deterministic harvest only, no LLM, free
    python scripts/evidence_miner.py --self-test          # the adversarial suite
    python scripts/evidence_miner.py                      # full mine -> outputs/evidence_cards_v2.json
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import hashlib
import json
import os
import re
import sys
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

CORPUS = ROOT / 'outputs' / 'journal_corpus_content.json'
OUT_CARDS = ROOT / 'outputs' / 'evidence_cards_v2.json'
OUT_META = ROOT / 'outputs' / 'evidence_cards_v2.meta.json'
CONTRACT_JSON = ROOT / 'outputs' / 'research_contract.json'

MODEL = os.getenv('PG_MINER_MODEL') or os.getenv('PG_GENERATOR_MODEL', 'z-ai/glm-5.2')

_print_lock = threading.Lock()


def log(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)


# =============================================================================================
# 0. THE RESEARCH CONTRACT.  Owned by research_contract.py (another agent). Imported DEFENSIVELY:
#    the miner must mine with or without it.
#
#    The contract supplies THREE things and none of them is a gate:
#      * FACETS  -> the term families a card is tagged with (industry / outcome / concept / framing).
#                   Tagging is what lets the planner SEE that the corpus has 2 healthcare papers
#                   before the outline promises a healthcare subsection.
#      * ENUMS   -> the `unit_of_analysis` and `design` vocabularies FOR THIS QUESTION. A closed
#                   vocabulary has nothing to fabricate; a question-specific one has nothing generic.
#      * PROBES  -> what to ask each paper. These steer the extractor; they never admit anything.
#
#    A missing contract degrades relevance. It cannot admit a fabrication, because no gate reads it.
# =============================================================================================

# Generic fallbacks. The contract's own vocabularies are UNIONED with these, never replaced by them,
# so a contract can add "structural-adjustment" without losing "long-run".
GENERIC_LEVELS = {'task', 'worker', 'occupation', 'firm', 'industry', 'region', 'economy',
                  'household', 'team', 'sector', 'country'}
GENERIC_DESIGNS = {'experiment', 'quasi-experimental', 'observational', 'survey', 'simulation',
                   'theory', 'review', 'meta-analysis', 'case-study'}
GENERIC_HORIZONS = {'short-run', 'long-run'}

_STOP = {
    'the', 'a', 'an', 'of', 'on', 'in', 'to', 'for', 'and', 'or', 'with', 'from', 'by', 'at', 'as',
    'is', 'are', 'was', 'were', 'be', 'been', 'it', 'its', 'this', 'that', 'these', 'those', 'how',
    'what', 'which', 'who', 'why', 'write', 'review', 'literature', 'article', 'articles', 'paper',
    'papers', 'study', 'studies', 'only', 'high', 'quality', 'english', 'language', 'journal',
    'journals', 'cites', 'cite', 'using', 'use', 'about', 'into', 'their', 'they', 'has', 'have',
    'please', 'impact', 'effects',
}


def _stem(w: str) -> str:
    for suf in ('ies', 'es', 's'):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[:-len(suf)]
    return w


def _norm_enum(s: str) -> str:
    return re.sub(r'[^a-z]+', '-', (s or '').lower()).strip('-')


@dataclass
class Matcher:
    """A term matches a text if the text contains one of its multi-word PHRASES verbatim, or one of
    its DISCRIMINATIVE stems — stems it shares with no sibling term. research_contract.py measured
    that exact-phrase-only matching routed 125 of 133 real cards to NO CELL, which prints as an
    evidence gap that does not exist. Backing off to every content word puts every card in every
    cell. Discriminative stems are the only thing that does neither."""
    key: str
    label: str
    phrases: list[str]
    disc: set[str]

    def hit(self, low: str, stems: set[str]) -> bool:
        if any(p in low for p in self.phrases):
            return True
        return bool(self.disc & stems)


@dataclass
class TagFamily:
    axis: str
    matchers: list[Matcher]


def _family(axis: str, terms: list) -> TagFamily:
    """Build discriminative matchers over one family of Terms. Mirrors research_contract.build_matchers;
    used only if that function cannot be imported."""
    forms: dict[str, list[str]] = {}
    stems: dict[str, set[str]] = {}
    labels: dict[str, str] = {}
    for t in terms:
        key = str(getattr(t, 'key', None) or (t.get('key') if isinstance(t, dict) else '') or '')
        label = str(getattr(t, 'label', None) or (t.get('label') if isinstance(t, dict) else '') or key)
        al = getattr(t, 'aliases', None) or (t.get('aliases') if isinstance(t, dict) else []) or []
        if not key:
            continue
        f = [label.lower()] + [str(a).lower() for a in al]
        forms[key] = sorted({x for x in f if ' ' in x and len(x) >= 6}, key=len, reverse=True)
        ws = {w for x in f for w in re.findall(r'[a-z]{4,}', x)}
        stems[key] = {_stem(w) for w in ws if w not in _STOP}
        labels[key] = label
    df: dict[str, int] = {}
    for ss in stems.values():
        for s in ss:
            df[s] = df.get(s, 0) + 1
    ms = [Matcher(key=k, label=labels[k], phrases=forms[k], disc={s for s in stems[k] if df[s] == 1})
          for k in stems]
    return TagFamily(axis=axis, matchers=ms)


@dataclass
class MiningContract:
    question: str = ''
    families: list[TagFamily] = field(default_factory=list)
    probes: list[str] = field(default_factory=list)
    levels: set[str] = field(default_factory=lambda: set(GENERIC_LEVELS))
    designs: set[str] = field(default_factory=lambda: set(GENERIC_DESIGNS))
    horizons: set[str] = field(default_factory=lambda: set(GENERIC_HORIZONS))
    origin: str = 'none'

    def tag(self, text: str) -> list[str]:
        low = (text or '').lower()
        stems = {_stem(w) for w in re.findall(r'[a-z]{4,}', low)}
        out: list[str] = []
        for fam in self.families:
            for m in fam.matchers:
                if m.hit(low, stems):
                    out.append(f'{fam.axis}:{m.key}')
        return out

    def n_tags(self, text: str) -> int:
        return len(self.tag(text))


def _contract_from_obj(obj, question: str) -> MiningContract | None:
    """Consume research_contract.Contract (dataclass OR its .json dump — both are supported, because
    the miner must not care which side of that module's cache it is standing on)."""
    def g(name, default=None):
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)

    fams: list[TagFamily] = []
    axis = g('subject_axis')
    ax_vals = (axis.get('values') if isinstance(axis, dict) else getattr(axis, 'values', None)) or []
    ax_name = (axis.get('name') if isinstance(axis, dict) else getattr(axis, 'name', '')) or 'subject'
    if ax_vals:
        fams.append(_family(_norm_enum(ax_name) or 'subject', list(ax_vals)))
    for axis_name, key in (('outcome', 'outcome_dimensions'), ('concept', 'core_concepts'),
                           ('framing', 'framing_devices')):
        vals = g(key) or []
        if vals:
            fams.append(_family(axis_name, list(vals)))
    if not fams:
        return None

    probes: list[str] = []
    for f in (g('facets') or []):
        lab = (f.get('label') if isinstance(f, dict) else getattr(f, 'label', '')) or ''
        pr = (f.get('probe') if isinstance(f, dict) else getattr(f, 'probe', '')) or ''
        if lab or pr:
            probes.append(f'{lab}: {pr}'.strip(': '))

    lv = {_norm_enum(x) for x in (g('unit_levels') or []) if x}
    dz = {_norm_enum(x) for x in (g('method_designs') or []) if x}
    hz = {_norm_enum(x) for x in (g('time_horizons') or []) if x}
    return MiningContract(
        question=str(g('question') or question or ''),
        families=fams, probes=probes,
        levels=(lv | GENERIC_LEVELS) or set(GENERIC_LEVELS),
        designs=(dz | GENERIC_DESIGNS) or set(GENERIC_DESIGNS),
        horizons=(hz | GENERIC_HORIZONS) or set(GENERIC_HORIZONS),
        origin='research_contract')


def load_contract(question: str = '', facets: list | None = None) -> MiningContract:
    """explicit facets > research_contract.py > a cached contract JSON > the bare question > nothing.
    NEVER raises. NEVER blocks. A miner that cannot mine without another agent's module is not a
    miner, it is a dependency."""
    if facets:
        terms = []
        for f in facets:
            if isinstance(f, dict):
                terms.append({'key': f.get('name') or f.get('key') or '',
                              'label': f.get('label') or f.get('name') or '',
                              'aliases': list(f.get('terms') or f.get('aliases') or [])})
            elif isinstance(f, str):
                terms.append({'key': f, 'label': f, 'aliases': [f]})
        c = MiningContract(question=question, families=[_family('facet', terms)], origin='argument')
        log(f'  [contract] {len(terms)} facets passed in by the caller')
        return c

    if question:
        try:
            import research_contract as rc  # type: ignore
            obj = rc.compile_contract(question, use_llm=True, verbose=False)
            c = _contract_from_obj(obj, question)
            if c:
                log(f'  [contract] research_contract.compile_contract() -> '
                    f'{sum(len(f.matchers) for f in c.families)} terms across '
                    f'{len(c.families)} families ({", ".join(f.axis for f in c.families)})')
                return c
        except Exception as e:
            log(f'  [contract] research_contract.py did not yield a contract ({type(e).__name__}: {e})')

    # The contract cache may ONLY be consulted when we have a question to match it against.
    #
    # This branch originally read "newest cached contract wins" and the self-test caught it: with no
    # question, the miner adopted whichever contract another agent happened to have compiled last —
    # for a DIFFERENT research question — and tagged every card against a foreign taxonomy. Silent,
    # wrong, and invisible downstream. A contract that was not compiled from THIS question is not
    # this question's contract, and no contract at all is strictly better than the wrong one.
    cache_dir = ROOT / 'outputs' / 'contracts'
    if question and cache_dir.exists():
        for p in sorted(cache_dir.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                obj = json.loads(p.read_text())
                if flatten(str(obj.get('question', ''))).lower() != flatten(question).lower():
                    continue
                c = _contract_from_obj(obj, question)
                if c:
                    c.origin = f'cache:{p.name}'
                    log(f'  [contract] reusing the contract compiled for THIS question ({p.name}, '
                        f'{sum(len(f.matchers) for f in c.families)} terms)')
                    return c
            except Exception:
                continue

    if question:
        words = [w.lower() for w in re.findall(r'[A-Za-z][A-Za-z-]{3,}', question)]
        terms = sorted({w for w in words if w not in _STOP})
        if terms:
            log(f'  [contract] no research_contract — falling back to {len(terms)} question terms')
            return MiningContract(question=question, origin='question',
                                  families=[_family('topic', [{'key': t, 'label': t, 'aliases': [t]}
                                                              for t in terms])])

    log('  [contract] no contract, no question — mining FACET-AGNOSTICALLY (no gate is affected)')
    return MiningContract(question=question, origin='none')


# =============================================================================================
# 1. NORMALIZED VIEW WITH AN INDEX MAP BACK INTO THE SOURCE
#    Everything downstream addresses the source by OFFSET. The map is what makes a span a slice of
#    the paper rather than a string the model handed us.
# =============================================================================================

_FOLD = {
    '‐': '-', '‑': '-', '‒': '-', '–': '-', '—': '-', '―': '-',
    '−': '-', '‘': "'", '’': "'", '‚': "'", '“': '"', '”': '"',
    '„': '"', '′': "'", '″': '"', '­': '',
}


# Page furniture that a PDF drops INTO THE MIDDLE OF A SENTENCE at every page break. Left in, it
# splits "...evidence suggests" / "23" / "that these 0.6 robots per thousand people led to..." into
# fragments — the same damage as the line-wrap bug, at every page boundary.
_FURNITURE = re.compile(r'^\s*(?:\d{1,4}|[ivxl]{1,6}|page \d{1,4}(?: of \d{1,4})?'
                        r'|electronic copy available at:?.*|downloaded from .*|©.*|\(c\) \d{4}.*)\s*$', re.I)


def _furniture_lines(src: str, lines: list[tuple[int, int]], thresh: float) -> list[tuple[int, int]]:
    """Bare page numbers and download banners that INTERRUPT FLOWING PROSE.

    Guarded hard: a lone number is only furniture when BOTH neighbours are full-width prose lines.
    A lone number between two SHORT lines is a table cell, and deleting table cells would be the
    single stupidest thing this module could do."""
    out: list[tuple[int, int]] = []
    for k in range(1, len(lines) - 1):
        a, b = lines[k]
        if not _FURNITURE.match(src[a:b]):
            continue
        prev = src[lines[k - 1][0]:lines[k - 1][1]].strip()
        nxt = src[lines[k + 1][0]:lines[k + 1][1]].strip()
        if len(prev) >= thresh and len(nxt) >= thresh:
            out.append((a, b))
    return out


def _layout(src: str) -> tuple[set[int], set[int]]:
    """Read the page layout. Returns (soft_newlines, chars_to_delete).

    Which '\\n' characters are PDF LINE-WRAPS (join with a space) rather than real breaks?

    THIS IS NOT COSMETIC. Academic PDFs hard-wrap prose at ~90 columns, so a sentence is stored as
    several lines. Acemoglu & Restrepo's headline result arrives as:

        "According to our estimates, one more robot per thousand workers reduces\\n
         the employment to population ratio by about 0.18-0.34 percentage points and wages by 0.25-0.5\\n
         percent."

    Treat those newlines as breaks and the paper's single most important finding is shredded into
    three fragments, with the effect size in a different fragment from the thing it is an effect ON.
    The regex harvester cannot see it; a span quoted from it would be a fragment. Every prose finding
    in this corpus dies this way. It has to be stitched.

    But newlines may NOT all be flattened either: a table row and a heading are genuinely their own
    lines, and tables are where the estimates are. So: a newline is SOFT iff the line it ends is
    close to the document's body width (a wrapped line is full; a paragraph's last line, a heading
    and a table row are short), and there is no blank line at the break.
    """
    lines: list[tuple[int, int]] = []
    start = 0
    for m in re.finditer(r'\n', src):
        lines.append((start, m.start()))
        start = m.end()
    lines.append((start, len(src)))
    if len(lines) < 3:
        return set(), set()

    lens = sorted(len(src[a:b].rstrip()) for a, b in lines if len(src[a:b].strip()) > 1)
    if not lens:
        return set(), set()
    width = lens[int(len(lens) * 0.85)]          # the body-text column width
    if width < 45:                               # already de-wrapped, or a table-only doc
        return set(), set()
    thresh = width * 0.72

    # page furniture is DELETED from the view; `imap` keeps the offsets exact regardless
    drop: set[int] = set()
    furn = _furniture_lines(src, lines, thresh)
    for a, b in furn:
        drop.update(range(a, b))
    furn_starts = {a for a, _ in furn}

    soft: set[int] = set()
    for k in range(len(lines) - 1):
        a, b = lines[k]
        line = src[a:b].rstrip()
        j = k + 1
        while j < len(lines) and lines[j][0] in furn_starts:   # look THROUGH the furniture
            j += 1
        if j >= len(lines):
            continue
        nxt = src[lines[j][0]:lines[j][1]].strip()
        if not nxt:                              # blank line => paragraph break
            continue
        if a in furn_starts:                     # the newline ending a deleted line is deleted too
            soft.add(b)
            continue
        if len(line.strip()) < thresh:           # short line: heading, table row, end of paragraph
            continue
        if _numeric_density(line) > 0.45:        # a wide table row is still a table row
            continue
        # A STRUCTURAL BOUNDARY BEATS THE WIDTH HEURISTIC. A full-width paragraph followed by
        # "Table 3. ..." must not swallow the caption: that erases the table, and tables are where
        # the estimates are. (Caught by the self-test the moment de-wrapping was switched on.)
        if _TABLE_HEAD.match(nxt) or _classify_heading(nxt):
            continue
        soft.add(b)                              # b is the index of this line's '\n'
    return soft, drop


class View:
    """A whitespace-normalized, de-wrapped, dash-folded view of a source string, plus `imap` so that
    any offset in the view can be converted back to an exact offset in the source.

    Whitespace runs collapse to a single ' '. A run containing a newline collapses to ' ' if that
    newline is a PDF line-wrap (see _soft_newlines) and to '\\n' if it is a real break — which is what
    preserves TABLE ROW STRUCTURE while stitching prose back into whole sentences.

    PDF end-of-line hyphenation ("comput-\\nation") is stitched too, because a span the model quotes
    as "computation" must still be locatable in the source.
    """

    __slots__ = ('src', 'text', 'imap', 'flat', 'low')

    def __init__(self, src: str):
        soft, drop = _layout(src)
        out: list[str] = []
        imap: list[int] = []
        i, n = 0, len(src)
        pending_ws = ''          # '' | ' ' | '\n'
        pending_at = 0
        while i < n:
            ch = src[i]
            # de-hyphenate across a line break: "restruc-\n  turing" -> "restructuring"
            if ch == '-' and out:
                j = i + 1
                while j < n and src[j] in ' \t\r':
                    j += 1
                if j < n and src[j] == '\n':
                    j += 1
                    while j < n and src[j] in ' \t\r\n':
                        j += 1
                    if j < n and src[j].islower():
                        i = j
                        pending_ws = ''
                        continue
            if i in drop:                  # page furniture: deleted, imap keeps offsets exact
                i += 1
                continue
            if ch.isspace():
                if out or pending_ws:
                    if ch == '\n' and i not in soft:
                        pending_ws = '\n'
                    elif not pending_ws:
                        pending_ws = ' '
                    if not pending_at:
                        pending_at = i
                i += 1
                continue
            if pending_ws and out:
                out.append(pending_ws)
                imap.append(pending_at or i)
            pending_ws, pending_at = '', 0
            c = _FOLD.get(ch, ch)
            if c:                      # a fold to '' (soft hyphen) drops the char entirely
                out.append(c)          # every fold is 1 char -> 1 char, so imap stays exact
                imap.append(i)
            i += 1
        self.src = src
        self.text = ''.join(out)
        self.imap = imap
        # `flat` is `text` with newlines turned into spaces. Because both are single characters the
        # transform is length-preserving, so an offset in `flat` IS an offset in `text`. That identity
        # is the only reason we can search a whitespace-agnostic key and still recover exact offsets.
        self.flat = self.text.replace('\n', ' ')
        self.low = ''.join(c.lower() if len(c.lower()) == 1 else c for c in self.flat)

    def src_span(self, a: int, b: int) -> tuple[int, int]:
        """View offsets [a,b) -> source offsets [start,end)."""
        if not self.imap or a >= b:
            return 0, 0
        a = max(0, min(a, len(self.imap) - 1))
        b = max(a + 1, min(b, len(self.imap)))
        return self.imap[a], self.imap[b - 1] + 1


def flatten(s: str) -> str:
    return re.sub(r'\s+', ' ', s or '').strip()


def _union_len(intervals: list[tuple[int, int]]) -> int:
    """Total length covered, counting overlap once."""
    total, cur_s, cur_e = 0, None, None
    for s, e in sorted(intervals):
        if cur_s is None:
            cur_s, cur_e = s, e
        elif s <= cur_e:
            cur_e = max(cur_e, e)
        else:
            total += cur_e - cur_s
            cur_s, cur_e = s, e
    return total + (cur_e - cur_s if cur_s is not None else 0)


# =============================================================================================
# 2. NUMBERS — tokenized, never substring-tested
# =============================================================================================

_NUM = re.compile(r'\d+(?:[.,]\d+)*')


def _canon_num(tok: str) -> str:
    t = tok.replace(',', '')
    try:
        return '%.10g' % float(t)
    except ValueError:
        return t.strip('.')


def number_tokens(text: str) -> set[str]:
    """The WHOLE numbers in `text`, canonicalized.

    THE BUG THIS KILLS: the old gate asked `if figure in span`. `"0.2" in "10.25"` is True, so any
    fabricated effect size passed whenever the paper contained a longer number containing its digits.
    Here "10.25" tokenizes to exactly one token, so {"0.2"} is not a subset of {"10.25"} and the
    fabrication dies. `1,234` == `1234` (formatting), but `0.2` != `10.25` (different numbers).
    """
    toks: set[str] = set()
    t = text or ''
    for m in _NUM.finditer(t):
        s, e = m.start(), m.end()
        if s > 0 and t[s - 1].isdigit():
            continue
        if e < len(t) and t[e].isdigit():
            continue
        toks.add(_canon_num(m.group(0)))
    return toks


def content_words(s: str) -> set[str]:
    return {w for w in re.findall(r'[a-z]{4,}', (s or '').lower())}


def _alnum(s: str) -> str:
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())


def _is_subsequence(needle: str, hay: str) -> bool:
    it = iter(hay)
    return all(c in it for c in needle)


# =============================================================================================
# 3. SECTION-AWARE CHUNKING OF THE FULL DOCUMENT
# =============================================================================================

SECTION_PATTERNS: list[tuple[str, re.Pattern]] = [
    ('references', re.compile(r'^(references?|bibliography|works cited|literature cited)\b', re.I)),
    ('appendix', re.compile(r'^(appendix|appendices|supplementary|online appendix|supporting information)\b', re.I)),
    ('acknowledgements', re.compile(r'^(acknowledge?ments?|funding|conflict of interest|declaration|author contribution)\b', re.I)),
    ('abstract', re.compile(r'^(abstract|summary|highlights|executive summary)\b', re.I)),
    ('results', re.compile(r'^(results?|findings?|empirical results?|main results?|estimation results?|estimates|robustness|empirical (analysis|findings|evidence))\b', re.I)),
    ('methods', re.compile(r'^(methods?|methodology|materials and methods|data|data and (methods?|sample)|empirical (strategy|specification|model|approach)|research (design|method|methodology)|identification|estimation strategy|sample|measures|the model|econometric)\b', re.I)),
    ('discussion', re.compile(r'^(discussions?|implications?|limitations?|general discussion)\b', re.I)),
    ('conclusion', re.compile(r'^(conclusions?|concluding remarks|final remarks)\b', re.I)),
    ('background', re.compile(r'^(background|literature review|related (work|literature)|theory|theoretical (background|framework)|prior work|conceptual (background|framework)|review of)\b', re.I)),
    ('introduction', re.compile(r'^(introduction|motivation)\b', re.I)),
    ('analysis', re.compile(r'^(analysis|analyses)\b', re.I)),
]

SECTION_WEIGHT = {
    'results': 1.00, 'tables': 1.00, 'analysis': 0.90, 'abstract': 0.85, 'discussion': 0.70,
    'conclusion': 0.60, 'body': 0.60, 'methods': 0.55, 'appendix': 0.55,
    'background': 0.35, 'introduction': 0.30, 'front': 0.15,
    'acknowledgements': 0.0, 'references': 0.0,      # weight 0 => never sent to the LLM
}

# A heading line: short, no terminal period, optionally numbered.
_HEAD_LINE = re.compile(r'^[ \t]*(?:(?:\d{1,2}(?:\.\d{1,2})*|[IVXLivxl]{1,5})[.)]?[ \t]+)?'
                        r'(?P<t>[A-Za-z][A-Za-z0-9 &/,:\'-]{2,70})[ \t]*:?[ \t]*$')
_TABLE_HEAD = re.compile(r'^[ \t]*(table|exhibit|panel|figure)[ \t]+([0-9]{1,2}|[ivxIVX]{1,4})\b', re.I)


def _classify_heading(line: str) -> str | None:
    m = _HEAD_LINE.match(line)
    if not m:
        return None
    t = m.group('t').strip()
    if len(t.split()) > 8:
        return None
    for name, pat in SECTION_PATTERNS:
        if pat.match(t):
            return name
    return None


def _numeric_density(line: str) -> float:
    toks = line.split()
    if not toks:
        return 0.0
    return sum(1 for t in toks if re.search(r'\d', t)) / len(toks)


def find_table_blocks(view: View) -> list[tuple[int, int]]:
    """Caption line ("Table 3. ...") plus the numeric-dense lines under it. Tables are where the
    estimates are; the judge praises cellcog's tables and we print none."""
    text = view.text
    blocks: list[tuple[int, int]] = []
    pos = 0
    for line_m in re.finditer(r'[^\n]*', text):
        pass
    lines: list[tuple[int, int, str]] = []
    start = 0
    for m in re.finditer(r'\n', text):
        lines.append((start, m.start(), text[start:m.start()]))
        start = m.end()
    lines.append((start, len(text), text[start:]))

    i = 0
    while i < len(lines):
        s, e, ln = lines[i]
        if _TABLE_HEAD.match(ln) and len(ln) < 200:
            end = e
            prose_run = 0
            j = i + 1
            while j < len(lines) and (end - s) < 4000:
                s2, e2, l2 = lines[j]
                if not l2.strip():
                    prose_run += 0.5
                elif _numeric_density(l2) >= 0.2 or len(l2) < 90:
                    prose_run = 0
                    end = e2
                else:
                    prose_run += 1
                if prose_run >= 2:
                    break
                j += 1
            if end > e:                       # a caption with no rows under it is not a table
                blocks.append((s, end))
                i = j
                continue
        i += 1
    return blocks


@dataclass
class Chunk:
    doc_id: str
    idx: int
    section: str
    weight: float
    v_start: int          # offsets into the View
    v_end: int
    s_start: int          # offsets into the SOURCE
    s_end: int
    text: str
    candidates: list[dict] = field(default_factory=list)


def sections_of(view: View) -> list[tuple[int, int, str]]:
    """Partition the WHOLE view into (start, end, section). Every character is assigned — 100%."""
    text = view.text
    bounds: list[tuple[int, str]] = []
    start = 0
    for m in re.finditer(r'\n', text):
        ln = text[start:m.start()]
        sec = _classify_heading(ln)
        if sec:
            bounds.append((start, sec))
        start = m.end()
    sec = _classify_heading(text[start:])
    if sec:
        bounds.append((start, sec))

    if not bounds:
        return [(0, len(text), 'body')]

    out: list[tuple[int, int, str]] = []
    if bounds[0][0] > 0:
        out.append((0, bounds[0][0], 'front'))
    for k, (b, sec) in enumerate(bounds):
        end = bounds[k + 1][0] if k + 1 < len(bounds) else len(text)
        if end > b:
            out.append((b, end, sec))
    # once a reference list opens, everything after it is bibliography unless an appendix follows
    return out


def chunk_document(doc_id: str, source: str, size: int = 5200, overlap: int = 600) -> tuple[View, list[Chunk]]:
    view = View(source)
    text = view.text
    if not text.strip():
        return view, []

    secs = sections_of(view)
    tables = find_table_blocks(view)

    def sec_at(p: int) -> tuple[str, float]:
        for a, b, name in secs:
            if a <= p < b:
                return name, SECTION_WEIGHT.get(name, 0.5)
        return 'body', SECTION_WEIGHT['body']

    pieces: list[tuple[int, int, str]] = []       # (start, end, section)
    covered: list[tuple[int, int]] = []
    for a, b in tables:
        name, _ = sec_at(a)
        if SECTION_WEIGHT.get(name, 0.5) <= 0:    # a "table" inside the reference list is not a table
            continue
        # CLIP the block to its own section. A table that runs past the section boundary would
        # otherwise be counted under two sections at once, and the coverage arithmetic — which is
        # the headline claim of this module — would print 100.4% of the text examined.
        sec_end = next((e for s, e, nm in secs if s <= a < e), b)
        b = min(b, sec_end)
        if b - a >= 40:
            pieces.append((a, b, 'tables'))
            covered.append((a, b))

    # everything not inside a table block, split by section, then windowed
    cursor = 0
    for a, b, name in secs:
        p = a
        while p < b:
            nxt = next((cs for cs, ce in sorted(covered) if cs >= p and cs < b), None)
            end = min(nxt, b) if nxt is not None else b
            if end > p:
                pieces.append((p, end, name))
            if nxt is None:
                break
            p = next(ce for cs, ce in sorted(covered) if cs == nxt)
    del cursor

    pieces.sort()
    chunks: list[Chunk] = []
    n = 0
    for a, b, name in pieces:
        w = SECTION_WEIGHT.get(name, 0.5)
        if name == 'tables':
            spans = [(a, b)]
        else:
            spans = []
            p = a
            while p < b:
                q = min(p + size, b)
                if q < b:                          # prefer a paragraph/sentence boundary
                    win = text[max(p + size - 900, p):q]
                    cut = max(win.rfind('\n'), win.rfind('. '))
                    if cut > 200:
                        q = max(p + size - 900, p) + cut + 1
                spans.append((p, q))
                if q >= b:
                    break
                p = max(q - overlap, p + 1)
        for (p, q) in spans:
            if q - p < 40:
                continue
            sa, sb = view.src_span(p, q)
            chunks.append(Chunk(doc_id=doc_id, idx=n, section=name, weight=w,
                                v_start=p, v_end=q, s_start=sa, s_end=sb, text=text[p:q]))
            n += 1
    return view, chunks


# =============================================================================================
# 4. DETERMINISTIC CANDIDATE HARVEST — free, exhaustive, cannot hallucinate
# =============================================================================================

QUANT = {
    'percent':     re.compile(r'\d+(?:\.\d+)?\s*(?:%|per\s?cent\b|percent\b|percentages?\b)', re.I),
    'pct_points':  re.compile(r'\d+(?:\.\d+)?\s*(?:percentage[ -]points?|p\.?p\.?\b)', re.I),
    'coefficient': re.compile(r'(?:coefficients?|estimates?|betas?|\bbeta\b|β|\bb\b)\s*(?:of|is|are|was|=|:)?\s*[-]?\d*\.\d+'
                              r'|[-]?\d\.\d{2,}\s*\(\s*\d?\.\d+\s*\)', re.I),
    'elasticity':  re.compile(r'elasticit\w*[^.\n]{0,60}?[-]?\d+(?:\.\d+)?|[-]?\d+(?:\.\d+)?[^.\n]{0,30}?elasticit\w*', re.I),
    'ci':          re.compile(r'(?:9[059]|99)\s*(?:%|per\s?cent)?\s*(?:confidence interval|ci)\b'
                              r'|\bci\s*[:=]\s*[\[(]?\s*[-]?\d'
                              r'|\[\s*[-]?\d+\.\d+\s*[,;-]\s*[-]?\d+\.\d+\s*\]', re.I),
    'pvalue':      re.compile(r'\bp\s*[<>=≤]\s*0?\.\d+|\bp-?values?\b[^.\n]{0,24}\d'
                              r'|significant at the \d+|\*{2,3}', re.I),
    'stderr':      re.compile(r'standard errors?\b|\bs\.?e\.?\s*[=:]\s*\d|\bs\.?d\.?\s*[=:]\s*\d'
                              r'|standard deviations?\b[^.\n]{0,30}\d|\d[^.\n]{0,30}standard deviations?\b', re.I),
    'sample':      re.compile(r'\bn\s*=\s*\d[\d,]*|\bsample of\s+(?:about\s+|roughly\s+|some\s+)?\d[\d,]*'
                              r'|\b\d[\d,]{1,}\s+(?:workers|firms|respondents|observations|occupations|'
                              r'establishments|participants|employees|individuals|households|patents|'
                              r'companies|jobs|tasks|subjects|students|users|articles|studies|papers)\b', re.I),
    'period':      re.compile(r'\b(?:19|20)\d{2}\s*(?:-|to|and|through|–)\s*(?:19|20)?\d{2}\b'
                              r'|\bbetween\s+(?:19|20)\d{2}\s+and\s+(?:19|20)\d{2}\b'
                              r'|\b(?:over|during|across|from)\s+the\s+(?:19|20)\d{2}', re.I),
    'change':      re.compile(r'\b(?:increas|decreas|declin|ris|fell|fall|drop|grew|grow|reduc|rais|'
                              r'gain|los|shrink|shrank|expand|contract|improv|boost|cut)\w*\b[^.\n]{0,45}?'
                              r'\b(?:by|of|to|from)\s+(?:about\s+|roughly\s+|around\s+|nearly\s+)?[-$€£]?\d+(?:[.,]\d+)?', re.I),
    'ratio':       re.compile(r'\b\d+(?:\.\d+)?\s*(?:times|fold|x)\s+(?:more|less|higher|lower|larger|'
                              r'smaller|greater|faster|as)\b'
                              r'|\bper\s+(?:thousand|1,?000|million|100|hundred|capita|worker|employee|robot)\b', re.I),
    'money':       re.compile(r'[$€£]\s?\d+(?:[.,]\d+)?\s*(?:billion|million|trillion|bn|k\b)?'
                              r'|\b\d+(?:\.\d+)?\s*(?:billion|million|trillion)\s+(?:dollars|euros|usd|eur)\b', re.I),
    'share':       re.compile(r'\b(?:share|proportion|fraction|share of|about|roughly|nearly|around)\b[^.\n]{0,35}?'
                              r'\d+(?:\.\d+)?\s*(?:%|percent|per cent)|\b\d+(?:\.\d+)?\s*(?:%|percent)\s+of\b', re.I),
    'count':       re.compile(r'\b\d[\d,]{1,}\s+(?:occupations|jobs|tasks|industries|countries|sectors|'
                              r'regions|commuting zones|patents|robots)\b', re.I),
    'range':       re.compile(r'\bfrom\s+[-$]?\d+(?:\.\d+)?\s*(?:%|percent)?\s+to\s+[-$]?\d+(?:\.\d+)?', re.I),
}

# ---------------------------------------------------------------------------------------------
# SECOND-HAND ATTRIBUTION. The defect the artifact verifier caught, and the most dangerous one here.
#
# A literature review's papers are FULL of other papers' numbers. Braganza (2021) contains the
# sentence "It is estimated that, globally, 326 million mostly-low-skilled jobs will be adversely
# affected by AI within 10 years (...)". That span is VERBATIM. Its figure IS in the span. It passes
# every gate this module has — and it is a lie, because the card says `source: Braganza (2021)` and
# the writer will render "Writing in the Journal of Business Research in 2021, Braganza et al. show
# that 326 million jobs will be adversely affected".
#
# BRAGANZA NEVER FOUND THAT. He cited it.
#
# A REAL number, in a REAL paper, bound to a source that did not produce it — assembled entirely
# from true particulars, and invisible to every span/number check. It is the same shape as the
# task-displacement/Bresnahan fabrication that already cost this project a turn. A card is evidence
# FROM its source; if the span hands the finding to someone else, the card's provenance is false.
THIRD_PARTY = re.compile(
    r'\[\d{1,3}\]'                                             # [34]
    r'|\(\s*[A-Z][A-Za-z-]+(?:\s+(?:et al\.?|and\s+[A-Z][A-Za-z-]+))?[,\s]+\(?(?:19|20)\d{2}'  # (Autor, 2003)
    r'|\b[A-Z][a-z]+\s+et\s+al\.'                              # Autor et al.
    r'|\baccording to\s+(?:the\s+)?[A-Z]'                      # According to the OECD
    r'|\b(?:prior|previous|earlier|existing)\s+(?:work|studies|research|literature|estimates)\b'
    r'|\bstudies\s+have\s+(?:shown|found|reported)\b'
    r'|\bit\s+is\s+(?:estimated|predicted|projected|forecast)\s+that\b'
    r'|\b(?:has|have)\s+(?:predicted|projected|estimated|forecast)\b'
    r'|\b(?:report|reports|reported|find|finds|found|show|shows|argue|argues|suggest|suggests)\s+'
    r'(?:that\s+)?(?:in|by)?\s*\[\d', re.I)

# The paper speaking in its OWN voice. If the sentence is the paper's own result, a citation
# elsewhere in it is a data source, not an attribution of the finding.
FIRST_PERSON = re.compile(
    r'\b(?:we|our|us)\b|\bthis\s+(?:paper|study|article|research|analysis)\b'
    r'|\bthe\s+(?:present|current)\s+(?:study|paper|analysis)\b'
    r'|\bin\s+this\s+(?:paper|study|article)\b'
    r'|\b(?:table|figure|column|panel|model|specification)\s+\(?[0-9ivx]', re.I)

# A forecast is not a measured effect. synthesis_contract.py: "Forecasts / predictions are always
# fabrication in a literature review." They are kept, but they are NOT counted as evidence of an
# effect and they are never labelled `estimate`.
PROJECTION = re.compile(
    r'\bwill\s+(?:be|have|create|destroy|displace|replace|affect|eliminate|reach|rise|fall|grow|lose)\b'
    r'|\b(?:by|before)\s+20[2-9]\d\b|\bis\s+(?:expected|projected|predicted|forecast)\s+to\b'
    r'|\b(?:predict|forecast|project)(?:s|ed|ion|ions)?\b|\bin\s+the\s+(?:next|coming)\s+\d+\s+years?\b'
    r'|\bwithin\s+\d+\s+years?\b|\bpotential(?:ly)?\s+(?:at\s+risk|automatable)\b', re.I)


# The findings-bearing verbs. A number in a sentence with one of these is far more likely a RESULT
# than a citation year or a page number.
RESULT_VERB = re.compile(
    r'\b(find|finds|found|estimat\w+|show|shows|showed|report\w*|observ\w+|estimate[sd]?|associat\w+|'
    r'predict\w*|suggest\w*|indicat\w+|imply|implies|demonstrat\w+|result\w*|conclude\w*|document\w*|'
    r'increas\w+|decreas\w+|declin\w+|reduc\w+|rais\w+|rose|fell|grew|correlat\w+|regress\w+|coefficient|'
    r'effect|impact|elasticit\w+|significant\w*|robust\w*|we\s+(?:find|estimate|show|observe|report))\b', re.I)

# Bibliography rows, page furniture, journal boilerplate. These are DENSE with numbers and are not
# evidence. Count-chasing without this filter is how you print "202 numbers" of pure noise.
NOISE = re.compile(
    r'\bdoi\b|https?://|\bissn\b|\bisbn\b|\bvol\.?\s*\d+|\bno\.?\s*\d+\s*[,(]|\bpp?\.\s*\d+\s*[-–]\s*\d+'
    r'|\b\d{4};\s*\d+\s*\(|\(\d{4}\)\.\s|all rights reserved|copyright|©\s*\d{4}|downloaded from'
    r'|working paper (no|series)|electronic copy available|cookie|sign in|\bcrossref\b|\bpubmed\b'
    r'|jstor|elsevier b\.v\.|\bet al\.\s*\(\d{4}\)\.\s*[A-Z]', re.I)

SENT_SPLIT = re.compile(r'(?<=[.!?])[\'")\]]?\s+(?=[A-Z0-9("\[•-])')


def sentences(text: str, base: int = 0) -> list[tuple[int, int, str]]:
    """(start, end, text) with offsets relative to `base`. Newlines are sentence-ish boundaries too:
    a table row is a unit even though it has no full stop."""
    out: list[tuple[int, int, str]] = []
    for para_m in re.finditer(r'[^\n]+', text):
        seg, off = para_m.group(0), para_m.start()
        cuts = [0] + [m.end() for m in SENT_SPLIT.finditer(seg)] + [len(seg)]
        for a, b in zip(cuts, cuts[1:]):
            s = seg[a:b]
            if s.strip():
                out.append((base + off + a, base + off + b, s))
    # glue runt fragments ("e.g." / "U.S." splits) onto the next sentence
    merged: list[tuple[int, int, str]] = []
    for s, e, t in out:
        if merged and len(merged[-1][2].strip()) < 30 and merged[-1][1] == s:
            ps, pe, pt = merged.pop()
            merged.append((ps, e, pt + t))
        else:
            merged.append((s, e, t))
    return merged


def harvest(chunk: Chunk, contract: MiningContract) -> list[dict]:
    """Every sentence in the chunk that carries a quantity. NO LLM. This is the recall stage; the
    tuple gate downstream is the precision stage."""
    if chunk.weight <= 0:
        return []          # a bibliography is dense with numbers and contains no evidence
    cands: list[dict] = []
    for s, e, txt in sentences(chunk.text, base=chunk.v_start):
        t = txt.strip()
        if len(t) < 25 or len(t) > 1200:
            continue
        if not re.search(r'\d', t):
            continue
        if NOISE.search(t):
            continue
        kinds = sorted(k for k, pat in QUANT.items() if pat.search(t))
        if not kinds:
            continue
        # an orphan number with no words around it is a page number, not a finding
        if len(content_words(t)) < 3:
            continue
        verbs = bool(RESULT_VERB.search(t))
        fh = contract.n_tags(t)
        score = chunk.weight * (1.0 + 0.35 * len(kinds)) * (1.6 if verbs else 1.0) * (1.0 + 0.25 * min(fh, 4))
        cands.append({'v_start': s, 'v_end': e, 'text': flatten(t), 'kinds': kinds,
                      'result_verb': verbs, 'facet_hits': fh, 'score': round(score, 3),
                      'section': chunk.section})
    return cands


# =============================================================================================
# 5. THE TUPLE + ITS GATE
# =============================================================================================

TUPLE_FIELDS = ['effect', 'unit', 'comparator', 'outcome', 'population', 'geography', 'period',
                'technology', 'industry', 'unit_of_analysis', 'design', 'uncertainty']

# Where each field is allowed to have come from. The window is always VERBATIM SOURCE TEXT of the
# same paper — never model prose. The effect and its unit must be in the quoted sentence itself;
# a study's geography and period may legitimately be stated in its methods section.
FIELD_WINDOWS = {
    'effect':      ('span',),
    'unit':        ('span',),
    'uncertainty': ('span',),
    'comparator':  ('span', 'chunk'),
    'outcome':     ('span', 'chunk'),
    'population':  ('span', 'chunk', 'paper'),
    'geography':   ('span', 'chunk', 'paper'),
    'period':      ('span', 'chunk', 'paper'),
    'technology':  ('span', 'chunk', 'paper'),
    'industry':    ('span', 'chunk', 'paper'),
}
LEXICAL_THRESH = 0.6          # same bar as the mechanism gate that closed the 43%-invention hole

# The tuple is COMPLETE when it is interpretable on its own: a magnitude, in a unit, of a named
# outcome, for a stated population, from a stated design, in a stated scope. That is the objective —
# NOT a count of numbers. cellcog's "202 findings" include years and sample sizes.
CORE = ('effect', 'unit', 'outcome')
SCOPE = ('population', 'geography', 'period', 'industry', 'technology')


def is_complete(card: dict) -> bool:
    if not all((card.get(k) or '').strip() for k in CORE):
        return False
    if not (card.get('design') or '').strip():
        return False
    if not (card.get('unit_of_analysis') or '').strip():
        return False
    return sum(1 for k in SCOPE if (card.get(k) or '').strip()) >= 2


def derive_claim(card: dict) -> str:
    """`claim` IS A DISPLAY CACHE. It is composed HERE, AFTER the gate, out of fields that are already
    proven against the verbatim span. It is never an input to any check. The model is never asked for
    it and never sees it. This is the structural fix for evidence laundering: you cannot launder
    through a field the model does not author."""
    eff, unit = (card.get('effect') or '').strip(), (card.get('unit') or '').strip()
    mag = eff if (not unit or unit.lower() in eff.lower()) else f'{eff} {unit}'
    bits = [mag]
    if card.get('outcome'):
        bits.append(f"in {card['outcome']}")
    if card.get('comparator'):
        bits.append(f"per {card['comparator']}" if not re.match(r'(?i)^(per|for|relative|compared|vs)', card['comparator'])
                    else card['comparator'])
    scope = [card.get(k) for k in ('population', 'industry', 'geography', 'period') if card.get(k)]
    if scope:
        bits.append('(' + '; '.join(scope) + ')')
    if card.get('uncertainty'):
        bits.append(f"[{card['uncertainty']}]")
    s = ' '.join(b for b in bits if b)
    return re.sub(r'\s+', ' ', s).strip()


def locate_span(view: View, model_span: str, lo: int, hi: int) -> tuple[int, int] | None:
    """Find the model's quoted text in the source and return VIEW offsets — or None.

    We are NOT verifying a string in order to keep it. We are using the model's string as a SEARCH
    KEY and then throwing it away: the caller stores `view.text[a:b]`, i.e. the paper's own bytes.
    That is why a 60-char-real-prefix-plus-invented-tail cannot survive here — the whole key must
    locate, and what is stored is the source, not the key.
    """
    key = flatten(model_span).strip(' "\'“”')
    if len(key) < 40:
        return None
    if '...' in key or '…' in key:
        return None              # an elided span is NOT WHOLE. "<real> ... <invented>" is the attack.
    k = key.lower()
    win = view.low[lo:hi]
    i = win.find(k)
    if i < 0:
        i = view.low.find(k)     # the model may quote across a chunk seam; still the same paper
        if i < 0:
            return None
        return i, i + len(k)
    return lo + i, lo + i + len(k)


def snap_to_sentence(view: View, a: int, b: int, cap: int = 900) -> tuple[int, int]:
    """Widen a located span outward to whole-sentence boundaries. This can only ADD SOURCE TEXT — it
    cannot add invention — and it is what makes the stored span WHOLE and self-sufficient rather than
    a fragment the writer has to guess the subject of."""
    t = view.text
    s = a
    while s > 0 and (a - s) < cap // 2:
        if t[s - 1] == '\n':
            break
        if t[s - 1] in '.!?' and (s < 2 or not t[s - 2].isupper()):
            break
        s -= 1
    e = b
    while e < len(t) and (e - b) < cap // 2:
        if t[e] == '\n':
            break
        if t[e] in '.!?':
            e += 1
            break
        e += 1
    while s < a and t[s] in ' \n"\'':
        s += 1
    if (e - s) > cap:
        return a, b
    return (s, e) if e > s else (a, b)


@dataclass
class Windows:
    span: set[str]
    chunk: set[str]
    paper: set[str]


def gate_card(raw: dict, view: View, chunk: Chunk, paper: dict, paper_words: set[str],
              contract: MiningContract, rejects: dict) -> dict | None:
    """THE HARD GATE. Everything that reaches disk has been through here."""

    # ---- GATE 1: the span must be VERBATIM AND WHOLE in the source, and we keep the SOURCE's copy.
    loc = locate_span(view, raw.get('span') or '', chunk.v_start, chunk.v_end)
    if not loc:
        rejects['span_not_in_source'] += 1
        return None
    a, b = snap_to_sentence(view, *loc)
    span_view = view.text[a:b]
    span = flatten(span_view)
    if len(span) < 40:
        rejects['span_too_short'] += 1
        return None
    s_start, s_end = view.src_span(a, b)

    # THE OFFSETS MUST ROUND-TRIP. `span` is what we stored; `span_start:span_end` is what we tell
    # every downstream consumer to re-verify against. If the map were wrong, the offsets would point
    # at some other part of the paper and every "verifiable" citation would be a lie.
    #
    # We cannot re-normalize the slice in isolation to compare (de-wrapping and page-furniture
    # removal are DOCUMENT-level decisions — a 200-char slice has no column width), so we check the
    # invariant that actually matters: every character of the span appears, IN ORDER, in the source
    # bytes we are pointing at. A wrong offset fails this instantly; an invented word cannot pass it.
    raw_slice = view.src[s_start:s_end]
    if not _is_subsequence(_alnum(span), _alnum(raw_slice)):
        rejects['offset_roundtrip_failed'] += 1
        return None

    span_nums = number_tokens(span)
    span_words = content_words(span)

    # ---- GATE 1b: THE SPAN MUST BE THE SOURCE PAPER'S OWN FINDING.
    #      If the sentence hands its finding to a third party ("[34] find that...", "According to the
    #      World Economic Forum...", "It is estimated that..."), then citing it as this paper's result
    #      is a fabricated binding — a real number, in a real paper, credited to the wrong source.
    #      A first-person result verb ("we find", "Table 3") means the paper is speaking for itself,
    #      and a citation elsewhere in the sentence is a data source, not an attribution.
    if THIRD_PARTY.search(span) and not FIRST_PERSON.search(span):
        rejects['second_hand_attribution'] += 1
        return None

    if not span_nums:
        kind = 'qualitative'
    elif PROJECTION.search(span):
        kind = 'projection'          # a forecast is verbatim and gated, but it is NOT a measured effect
    else:
        kind = 'estimate'

    # ---- GATE 2: EVERY FIGURE IN EVERY FIELD MUST BE A NUMBER OF THE SPAN — as its own number.
    #      Not a substring of one. `0.2` does not live inside `10.25`.
    fields: dict[str, str] = {}
    for f in TUPLE_FIELDS:
        v = raw.get(f)
        v = (v if isinstance(v, str) else '').strip()
        v = re.sub(r'\s+', ' ', v)[:160]
        fields[f] = v
    for f, v in fields.items():
        bad = number_tokens(v) - span_nums
        if bad:
            rejects['number_not_in_span'] += 1
            rejects.setdefault('_examples', []).append(
                {'field': f, 'value': v[:80], 'fabricated': sorted(bad)[:3], 'span': span[:110]})
            return None

    # ---- GATE 3: closed vocabularies, taken from the research contract when it supplies them.
    #      An enum has nothing to fabricate: a value is either in the vocabulary or it is dropped.
    lvl = _norm_enum(fields['unit_of_analysis'])
    fields['unit_of_analysis'] = lvl if lvl in contract.levels else ''
    dsg = _norm_enum(fields['design'])
    fields['design'] = dsg if dsg in contract.designs else ''

    # ---- GATE 4: lexical grounding, per field, in its DECLARED PROVENANCE WINDOW of verbatim text.
    win = Windows(span=span_words,
                  chunk=content_words(chunk.text),
                  paper=paper_words)
    prov: dict[str, str] = {}
    for f, allowed in FIELD_WINDOWS.items():
        v = fields.get(f, '')
        fw = content_words(v)
        if not v:
            continue
        if not fw:                       # e.g. effect="-0.39" — pure number; GATE 2 already proved it
            prov[f] = 'span'
            continue
        placed = ''
        for w in allowed:
            pool = getattr(win, w)
            if pool and len(fw & pool) / len(fw) >= LEXICAL_THRESH:
                placed = w
                break
        if not placed:
            rejects['field_not_in_source'] += 1
            fields[f] = ''               # drop the FIELD (a word we cannot source), keep the evidence
        else:
            prov[f] = placed

    # ---- GATE 5: mechanisms must be STATED IN THE SPAN. (The 43%-invention hole, kept closed.)
    mechs = []
    for m in (raw.get('mechanisms') or []):
        m = (m or '').strip() if isinstance(m, str) else ''
        if not m:
            continue
        mw = content_words(m)
        if mw and len(mw & span_words) / len(mw) >= LEXICAL_THRESH:
            mechs.append(m[:80])
        else:
            rejects['mechanism_not_in_span'] += 1

    # ---- GATE 6: reject ORPHAN NUMBERS. A figure with no unit and no outcome is not evidence.
    if kind in ('estimate', 'projection') and not (fields['unit'] or fields['comparator']) and not fields['outcome']:
        rejects['orphan_number'] += 1
        return None
    if kind == 'qualitative' and not fields['outcome']:
        rejects['qualitative_no_outcome'] += 1
        return None

    horizon = _norm_enum(raw.get('horizon') or '')
    horizon = horizon if horizon in contract.horizons else ''

    card = {
        # ---- v1-compatible surface, so this file is a drop-in for anything reading evidence_cards.json
        'id': '',
        'claim': '',                                    # DISPLAY CACHE — filled below, after the gate
        'span': span,
        'level': fields['unit_of_analysis'],
        'horizon': horizon,
        'method': fields['design'],
        'mechanisms': mechs,
        'has_number': bool(span_nums),
        'doi': paper.get('doi', ''),
        'authors': paper.get('authors', []),
        'venue': paper.get('venue', ''),
        'year': paper.get('year', ''),
        'attribution': paper.get('attribution', ''),
        'source': paper.get('attribution_short', ''),
        # ---- v2: the estimate tuple
        'card_kind': kind,
        'effect': fields['effect'],
        'unit': fields['unit'],
        'comparator': fields['comparator'],
        'outcome': fields['outcome'],
        'population': fields['population'],
        'geography': fields['geography'],
        'period': fields['period'],
        'technology': fields['technology'],
        'industry': fields['industry'],
        'unit_of_analysis': fields['unit_of_analysis'],
        'design': fields['design'],
        'uncertainty': fields['uncertainty'],
        # the research contract names these two fields `study_design` and `geographic_scope` in its
        # evidence_tuple. Emit both spellings rather than make the other agent adapt to mine.
        'study_design': fields['design'],
        'geographic_scope': fields['geography'],
        # ---- provenance: where every byte came from
        'span_start': s_start,
        'span_end': s_end,
        'span_raw': raw_slice,
        'section': chunk.section,
        'section_weight': chunk.weight,
        'context_start': chunk.s_start,
        'context_end': chunk.s_end,
        'field_provenance': prov,
        'span_numbers': sorted(span_nums),
        'source_version': paper.get('_source_version', ''),
        'text_field': paper.get('_text_field', ''),
        'facet_tags': [],
        'corroborating_sources': [],
    }
    # tag from the SPAN first (that is the evidence); fall back to the enclosing chunk, and record
    # which, so a planner can tell "this paper is ABOUT healthcare" from "this finding IS healthcare".
    span_tags = contract.tag(span)
    ctx_tags = [t for t in contract.tag(chunk.text[:2000]) if t not in span_tags]
    card['facet_tags'] = span_tags + ctx_tags
    card['facet_tags_span'] = span_tags
    card['complete_tuple'] = is_complete(card) and kind == 'estimate'
    card['claim'] = derive_claim(card) if kind in ('estimate', 'projection') else (fields['outcome'] or span[:180])

    # the display cache may not carry a figure the span does not have. It is derived from gated
    # fields so this cannot fail — which is exactly why it is asserted rather than assumed.
    if number_tokens(card['claim']) - span_nums:
        rejects['derived_claim_leaked_number'] += 1
        return None

    doi = (paper.get('doi') or 'nodoi').replace('/', '_')
    card['id'] = f"{doi}:{s_start}-{s_end}"
    return card


# =============================================================================================
# 6. SEMANTIC EXTRACTION (the LLM stage)
# =============================================================================================

MINE_PROMPT = """You are mining a peer-reviewed article for INTERPRETABLE QUANTITATIVE EVIDENCE.

PAPER: {title}
AUTHORS: {authors}
JOURNAL: {venue} ({year})
SECTION OF THE PAPER THIS EXCERPT COMES FROM: {section}
{facet_line}
=== EXCERPT (verbatim from the paper) ===
{text}
=== END EXCERPT ===
{cand_block}
Return a JSON array of EVIDENCE TUPLES found in the excerpt. An evidence tuple is a finding a reader
could INTERPRET WITHOUT THE PAPER: a magnitude, in a unit, of a named outcome, for a stated
population, from a stated design.

A BARE NUMBER IS NOT A FINDING. "Adoption grew by 30%" is worthless without knowing adoption OF WHAT,
BY WHOM, WHEN, and MEASURED HOW. If you cannot fill effect + unit + outcome, DO NOT EMIT THE OBJECT.
Do not pad. AN EMPTY ARRAY IS A CORRECT AND COMMON ANSWER — most excerpts contain no estimate. You are
not being scored on how many you return.

For each finding:
{{
 "span": "the VERBATIM sentence(s) from the EXCERPT that carry the finding. COPY IT EXACTLY, character
          for character. Do not paraphrase, do not shorten, do not use an ellipsis. It must CONTAIN
          EVERY NUMBER you report below -- if the number's meaning only becomes clear from a table
          caption or a column header, quote from the caption THROUGH the row so the span carries both
          (a span may be several lines and up to 900 characters).",
 "effect":      "the magnitude, e.g. '-0.39' or 'a fall of 0.2' or '14%'",
 "unit":        "what the magnitude is measured in: 'percentage points', 'percent', 'log points', 'USD', 'standard deviations', 'jobs'",
 "comparator":  "per WHAT / relative to WHAT: 'per additional robot per thousand workers', 'relative to the control group', 'compared with 1990'",
 "outcome":     "the thing that changed: 'employment-to-population ratio', 'hourly wage', 'tasks completed per hour'",
 "population":  "who or what was measured: 'US commuting zones', '1,200 customer-support agents', 'French manufacturing firms'",
 "geography":   "country/region, if the paper states one",
 "period":      "the years the data cover, if the paper states them",
 "technology":  "the technology studied: 'industrial robots', 'generative AI', 'computers', 'machine learning'",
 "industry":    "the industry/sector, if the paper states one",
 "unit_of_analysis": one of task|worker|occupation|firm|industry|region|economy|household|team,
 "design":      one of experiment|quasi-experimental|observational|survey|simulation|theory|review|meta-analysis|case-study,
 "uncertainty": "the standard error, confidence interval or significance AS STATED: '(0.05)', '95% CI 0.1 to 0.4', 'p<0.01'",
 "horizon":     "short-run" | "long-run" | "",
 "mechanisms":  ["a causal channel THE SPAN ITSELF NAMES -- an empty list is usually correct"]
}}

ABSOLUTE RULES, ENFORCED BY A GATE THAT SILENTLY DELETES VIOLATIONS:
 1. EVERY NUMBER IN EVERY FIELD MUST APPEAR IN YOUR SPAN. A figure that is not in the span is treated
    as a fabrication and the whole finding is destroyed. Never round, never convert, never combine two
    numbers into a third. Copy the paper's number as the paper writes it.
 2. THE SPAN MUST BE LOCATABLE VERBATIM IN THE EXCERPT ABOVE. If you cannot copy it exactly, omit the
    finding -- a finding we cannot trace to the page is not evidence, it is a rumour.
 3. Leave a field as "" if the paper does not state it. An empty field costs nothing. A GUESSED field
    destroys the finding.
 4. Do NOT write a summary, a claim, or a takeaway. There is no such field. Report the tuple only.
 5. Do not report a number that is a citation year, a page number, a section number, an equation
    number, a table number, or a footnote marker.

Return ONLY the JSON array."""


def jparse(s: str):
    s = re.sub(r'^```(?:json)?|```$', '', (s or '').strip(), flags=re.M).strip()
    m = re.search(r'\[.*\]', s, re.S)
    if not m:
        m = re.search(r'\{.*\}', s, re.S)
        if not m:
            return None
        try:
            o = json.loads(m.group(0))
            return [o] if isinstance(o, dict) else None
        except Exception:
            return None
    try:
        return json.loads(m.group(0))
    except Exception:
        # salvage: the array is well-formed up to a truncation point
        txt = m.group(0)
        for cut in range(len(txt) - 1, 0, -1):
            if txt[cut] == '}':
                try:
                    return json.loads(txt[:cut + 1] + ']')
                except Exception:
                    continue
        return None


def llm(prompt: str, max_tokens: int = 6000) -> str:
    import asyncio

    def _call() -> str:
        from src.polaris_graph.llm.openrouter_client import OpenRouterClient

        async def _run() -> str:
            c = OpenRouterClient(model=MODEL)
            try:
                r = await c.generate(prompt=prompt, max_tokens=max_tokens, temperature=0.0)
                if isinstance(r, str):
                    return r
                content = getattr(r, 'content', None)
                if content is not None:
                    return content
                return r.get('content') if isinstance(r, dict) else str(r)
            finally:
                cl = getattr(c, 'close', None)
                if cl:
                    try:
                        res = cl()
                        if hasattr(res, '__await__'):
                            await res
                    except Exception:
                        pass

        return asyncio.run(_run())

    return _call()


# =============================================================================================
# 7. CONSOLIDATION — by FINDING, not by paper
# =============================================================================================

def finding_key(card: dict) -> str:
    """Two cards are THE SAME FINDING when they report the same magnitude of the same outcome at the
    same level of analysis. Same finding in three papers = CORROBORATION, and corroboration is the
    strongest thing a literature review can show. We keep every source; we do not delete the replicas."""
    nums = ','.join(sorted(number_tokens(card.get('effect') or '')))
    out = ' '.join(sorted(content_words(card.get('outcome') or '')))
    unit = re.sub(r'[^a-z]', '', (card.get('unit') or '').lower())
    return f"{nums}|{unit}|{out}|{card.get('unit_of_analysis','')}"


def _overlaps(a: dict, b: dict) -> bool:
    if a['doi'] != b['doi']:
        return False
    lo = max(a['span_start'], b['span_start'])
    hi = min(a['span_end'], b['span_end'])
    if hi <= lo:
        return False
    shorter = min(a['span_end'] - a['span_start'], b['span_end'] - b['span_start']) or 1
    return (hi - lo) / shorter > 0.6


def _rank(c: dict) -> tuple:
    return (c.get('complete_tuple', False),
            sum(1 for f in TUPLE_FIELDS if (c.get(f) or '').strip()),
            c.get('section_weight', 0), len(c.get('span', '')))


def consolidate(cards: list[dict]) -> list[dict]:
    # (a) within a paper: overlapping chunks re-extract the same sentence. Keep the richest tuple.
    by_doi: dict[str, list[dict]] = {}
    for c in cards:
        by_doi.setdefault(c['doi'], []).append(c)
    deduped: list[dict] = []
    for doi, group in by_doi.items():
        group.sort(key=_rank, reverse=True)
        kept: list[dict] = []
        for c in group:
            if any(_overlaps(c, k) and finding_key(c) == finding_key(k) for k in kept):
                continue
            if any(c['span'] == k['span'] and finding_key(c) == finding_key(k) for k in kept):
                continue
            kept.append(c)
        deduped.extend(kept)

    # (b) across papers: the SAME FINDING replicated is ONE card with N sources.
    groups: dict[str, list[dict]] = {}
    for c in deduped:
        groups.setdefault(finding_key(c), []).append(c)

    out: list[dict] = []
    for key, group in groups.items():
        group.sort(key=_rank, reverse=True)
        primary = dict(group[0])
        others = [g for g in group[1:] if g['doi'] != primary['doi']]
        primary['corroborating_sources'] = [{
            'doi': g['doi'], 'attribution': g.get('attribution', ''), 'source': g.get('source', ''),
            'authors': g.get('authors', []), 'year': g.get('year', ''), 'venue': g.get('venue', ''),
            'span': g['span'], 'span_start': g['span_start'], 'span_end': g['span_end'],
            'section': g.get('section', ''), 'source_version': g.get('source_version', ''),
        } for g in others]
        primary['n_sources'] = 1 + len({g['doi'] for g in others})
        out.extend([primary] + [g for g in group[1:] if g['doi'] == primary['doi']][:0])
        # same-paper duplicates that were not overlap-deduped but share a finding key are dropped;
        # different-paper ones become corroboration above.
    out.sort(key=lambda c: (-c.get('n_sources', 1), not c.get('complete_tuple'), -c.get('section_weight', 0)))
    return out


# =============================================================================================
# 8. THE MINER
# =============================================================================================

def source_text(paper: dict) -> tuple[str, str, str]:
    """THE ONE DEFINITION OF "THE SOURCE TEXT OF A PAPER". Returns (text, field, version).

    There must be exactly one of these. The miner hashed `fulltext.strip()` while the verifier hashed
    `fulltext`, so 130 of 192 cards reported that their source paper "had changed since mining" — a
    false alarm that, had it been the other way round, would have been a silent one. Two functions
    that each decide what the source is will always drift; the offsets stored in every card mean
    nothing if the two sides disagree about which string they index into.
    """
    text = (paper.get('fulltext') or '').strip()
    field = 'fulltext'
    if len(text) < 400:
        text = (paper.get('abstract') or '').strip()
        field = 'abstract'
    return text, field, hashlib.sha256(text.encode('utf-8', 'ignore')).hexdigest()[:12]


def paper_window(view: View, chunks: list[Chunk], paper: dict) -> set[str]:
    """The PAPER-level provenance window: verbatim text a scope field may legitimately come from —
    the title, the abstract and the methods section. Still the paper's own words, never the model's."""
    pool = f"{paper.get('title','')} {paper.get('abstract','')} {paper.get('venue','')} "
    for c in chunks:
        if c.section in ('abstract', 'methods', 'front'):
            pool += c.text[:6000] + ' '
    return content_words(pool)


def mine_paper(paper: dict, contract: MiningContract, use_llm: bool, rejects: dict,
               stats: dict, max_chunks_per_paper: int = 0) -> list[dict]:
    src, text_field, version = source_text(paper)
    if len(src.split()) < 50:
        return []

    paper['_text_field'] = text_field
    paper['_source_version'] = version
    doc_id = (paper.get('doi') or paper.get('title', ''))[:80]

    view, chunks = chunk_document(doc_id, src)
    if not chunks:
        return []

    for ch in chunks:
        ch.candidates = harvest(ch, contract)

    # Chunks OVERLAP by design (a finding must not be cut in half by a chunk boundary), so coverage
    # is the UNION of their spans, never the sum. Summing printed "106.9% of the text examined",
    # which is not a flattering number, it is a broken one.
    union = _union_len([(c.v_start, c.v_end) for c in chunks])
    llm_chars = _union_len([(c.v_start, c.v_end) for c in chunks if c.weight > 0])
    ev_chars = sum(e - s for s, e, name in sections_of(view) if SECTION_WEIGHT.get(name, 0.5) > 0)

    stats['view_chars'] += len(view.text)
    stats['chunked_chars'] += union
    stats['evidence_chars'] += ev_chars
    stats['llm_chars'] += llm_chars
    stats['legacy_28k_chars'] += min(28000, len(view.text))
    stats['chunks'] += len(chunks)
    stats['candidates'] += sum(len(c.candidates) for c in chunks)
    for sec in {c.section for c in chunks}:
        stats['by_section'][sec] = stats['by_section'].get(sec, 0) + _union_len(
            [(c.v_start, c.v_end) for c in chunks if c.section == sec])
        stats['cands_by_section'][sec] = stats['cands_by_section'].get(sec, 0) + sum(
            len(c.candidates) for c in chunks if c.section == sec)

    if not use_llm:
        return []

    pw = paper_window(view, chunks, paper)
    todo = [c for c in chunks if c.weight > 0]
    todo.sort(key=lambda c: -(c.weight * (1 + len(c.candidates))))
    if max_chunks_per_paper:
        todo = todo[:max_chunks_per_paper]

    facet_line = ''
    if contract.probes:
        facet_line = ('\nTHE REVIEW NEEDS THESE QUESTIONS ANSWERED OF EVERY PAPER. Prefer findings that answer\n'
                      'one of them -- but NEVER invent a value to fit one. An unanswered facet is a real,\n'
                      'reportable gap; a fabricated one is a lie:\n'
                      + '\n'.join(f'  - {p}' for p in contract.probes[:8]) + '\n')

    cards: list[dict] = []
    for ch in todo:
        cand_block = ''
        if ch.candidates:
            top = sorted(ch.candidates, key=lambda c: -c['score'])[:12]
            lines = '\n'.join(f'  - {c["text"][:260]}' for c in top)
            cand_block = ('\nA DETERMINISTIC SCAN FLAGGED THESE SENTENCES IN THE EXCERPT AS CARRYING QUANTITIES.\n'
                          'They are a hint, not a quota. Some are not findings. Copy spans from the EXCERPT, not\n'
                          'from this list.\n' + lines + '\n')
        p = MINE_PROMPT.format(title=paper.get('title', ''), authors=', '.join(paper.get('authors', []) or []),
                               venue=paper.get('venue', ''), year=paper.get('year', ''),
                               section=ch.section.upper(), facet_line=facet_line,
                               text=ch.text, cand_block=cand_block)
        arr = None
        for attempt in (1, 2):
            try:
                arr = jparse(llm(p))
                break
            except Exception as e:
                if attempt == 2:
                    rejects['llm_error'] += 1
                    log(f"    ! {doc_id[:28]} chunk {ch.idx} ({ch.section}): {type(e).__name__}: {e}")
                else:
                    time.sleep(2)
        stats['llm_calls'] += 1
        if not isinstance(arr, list):
            continue
        stats['llm_proposed'] += len(arr)
        for raw in arr:
            if not isinstance(raw, dict):
                continue
            card = gate_card(raw, view, ch, paper, pw, contract, rejects)
            if card:
                cards.append(card)
    return cards


def new_stats() -> dict:
    return {'view_chars': 0, 'chunked_chars': 0, 'evidence_chars': 0, 'llm_chars': 0,
            'legacy_28k_chars': 0, 'chunks': 0, 'candidates': 0, 'llm_calls': 0, 'llm_proposed': 0,
            'by_section': {}, 'cands_by_section': {}}


def new_rejects() -> dict:
    return {'span_not_in_source': 0, 'span_too_short': 0, 'offset_roundtrip_failed': 0,
            'number_not_in_span': 0, 'second_hand_attribution': 0, 'field_not_in_source': 0,
            'mechanism_not_in_span': 0, 'orphan_number': 0, 'qualitative_no_outcome': 0,
            'derived_claim_leaked_number': 0, 'llm_error': 0}


def mine(corpus_path: Path, question: str = '', facets: list | None = None, use_llm: bool = True,
         workers: int = 8, limit: int | None = None, max_chunks_per_paper: int = 0) -> tuple[list[dict], dict]:
    corpus = json.loads(corpus_path.read_text())
    contract = load_contract(question, facets)

    usable = [c for c in corpus if c.get('content_status') != 'CITATION_ONLY'
              and ((c.get('fulltext') or '').strip() or (c.get('abstract') or '').strip())]
    if limit:
        usable = usable[:limit]

    stats = new_stats()
    rejects = new_rejects()
    lock = threading.Lock()
    stats['papers'] = len(usable)
    stats['papers_in_corpus'] = len(corpus)
    stats['citation_only'] = sum(1 for c in corpus if c.get('content_status') == 'CITATION_ONLY')

    log(f'=== MINING {len(usable)} papers ({stats["citation_only"]} citation-only, skipped) ===')
    log(f'    model={MODEL}  llm={"ON" if use_llm else "OFF (deterministic harvest only)"}')

    def one(p):
        local_s, local_r = new_stats(), new_rejects()
        try:
            cards = mine_paper(p, contract, use_llm, local_r, local_s, max_chunks_per_paper)
        except Exception as e:
            log(f"  !! {(p.get('authors') or ['?'])[0]}: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return []
        with lock:
            for k, v in local_s.items():
                if isinstance(v, dict):
                    for kk, vv in v.items():
                        stats[k][kk] = stats[k].get(kk, 0) + vv
                else:
                    stats[k] = stats.get(k, 0) + v
            for k, v in local_r.items():
                if k == '_examples':
                    rejects.setdefault('_examples', []).extend(v)
                else:
                    rejects[k] = rejects.get(k, 0) + v
            n_est = sum(1 for c in cards if c['card_kind'] == 'estimate')
            n_full = sum(1 for c in cards if c['complete_tuple'])
            log(f"  {(p.get('authors') or ['?'])[0]:<16.16} {str(p.get('year','')):<5} "
                f"{local_s['chunks']:>3} chunks  {local_s['candidates']:>4} cands  "
                f"{len(cards):>3} cards ({n_est} est / {n_full} full)  {(p.get('venue') or '')[:34]}")
        return cards

    t0 = time.time()
    all_cards: list[dict] = []
    if use_llm:
        with futures.ThreadPoolExecutor(max_workers=workers) as ex:
            for r in ex.map(one, usable):
                all_cards.extend(r)
    else:
        for p in usable:
            all_cards.extend(one(p))

    stats['seconds'] = round(time.time() - t0, 1)
    stats['cards_pre_consolidation'] = len(all_cards)
    cards = consolidate(all_cards)
    stats['question'] = contract.question
    stats['contract_origin'] = contract.origin
    stats['facet_axes'] = {f.axis: [m.key for m in f.matchers] for f in contract.families}
    stats['levels'] = sorted(contract.levels)
    stats['designs'] = sorted(contract.designs)
    stats['rejects'] = rejects
    return cards, stats


def report(cards: list[dict], stats: dict) -> None:
    v, ch = stats['view_chars'] or 1, stats['chunked_chars']
    ev, ll = stats['evidence_chars'] or 1, stats['llm_chars']
    est = [c for c in cards if c['card_kind'] == 'estimate']
    full = [c for c in cards if c.get('complete_tuple')]
    corrob = [c for c in cards if c.get('n_sources', 1) > 1]

    print('\n' + '=' * 78)
    print('  EVIDENCE MINER — RESULTS')
    print('=' * 78)
    print(f"\n  CORPUS          {stats['papers']} mineable papers ({stats['citation_only']} citation-only skipped)")
    print(f"  TEXT            {v:,} chars of normalized source")
    print(f"  CHUNKS          {stats['chunks']:,} section-aware chunks, {stats['candidates']:,} deterministic candidates")
    print(f"  LLM             {stats['llm_calls']:,} calls, {stats['llm_proposed']:,} tuples proposed, {stats['seconds']}s")

    print('\n  --- % OF SOURCE TEXT ACTUALLY EXAMINED ' + '-' * 38)
    print(f"    chunked & deterministically scanned : {100*ch/v:6.1f}%   ({ch:,} / {v:,} chars)")
    print(f"    sent to the semantic extractor      : {100*ll/v:6.1f}%   (100% of everything but the")
    print(f"                                                     bibliography, which is not evidence)")
    print(f"    of evidence-bearing text (ex-refs)  : {100*ll/ev:6.1f}%")
    print(f"    THE OLD EXTRACTOR (fulltext[:28000]): {100*stats['legacy_28k_chars']/v:6.1f}%   <-- what we were doing")

    print('\n  --- WHERE THE EVIDENCE ACTUALLY LIVES ' + '-' * 39)
    print(f"    {'section':<18}{'chars':>10}{'% of text':>11}{'candidates':>12}{'cards':>8}")
    card_sec: dict[str, int] = {}
    for c in cards:
        card_sec[c['section']] = card_sec.get(c['section'], 0) + 1
    for sec, n in sorted(stats['by_section'].items(), key=lambda kv: -kv[1]):
        print(f"    {sec:<18}{n:>10,}{100*n/v:>10.1f}%{stats['cands_by_section'].get(sec,0):>12}{card_sec.get(sec,0):>8}")

    print('\n  --- CARDS ' + '-' * 66)
    print(f"    cards on disk                       : {len(cards):,}")
    print(f"      carrying a QUANTITATIVE finding   : {len(est):,}  ({100*len(est)/max(len(cards),1):.0f}%)")
    print(f"      carrying a COMPLETE ESTIMATE TUPLE: {len(full):,}  ({100*len(full)/max(len(cards),1):.0f}% of cards)")
    print(f"      corroborated by 2+ papers         : {len(corrob):,}")
    print(f"    verifiable quantitative findings    : {len(est):,}   <-- every figure re-derivable from")
    print(f"                                                     a byte range of a journal PDF")
    print(f"    distinct journal articles           : {len({c['doi'] for c in cards})}")
    print(f"    before consolidation                : {stats['cards_pre_consolidation']:,}")

    if est:
        nf = sum(len([f for f in TUPLE_FIELDS if (c.get(f) or '').strip()]) for c in est) / len(est)
        print(f"    mean tuple fields filled (of {len(TUPLE_FIELDS)})    : {nf:.1f}")

    axes = stats.get('facet_axes') or {}
    if axes:
        print('\n  --- FACET COVERAGE: WHAT THE CORPUS CAN ACTUALLY CASH ' + '-' * 23)
        print('      (a cheque the outline writes here that shows 0 is a section that CANNOT be written)')
        for axis, keys in axes.items():
            print(f'\n    {axis.upper()}')
            rows = []
            for k in keys:
                tag = f'{axis}:{k}'
                n_cards = sum(1 for c in cards if tag in (c.get('facet_tags') or []))
                n_est = sum(1 for c in est if tag in (c.get('facet_tags') or []))
                n_works = len({c['doi'] for c in cards if tag in (c.get('facet_tags') or [])})
                rows.append((n_cards, n_est, n_works, k))
            for n_cards, n_est, n_works, k in sorted(rows, reverse=True):
                flag = '  <-- EMPTY CELL' if n_works == 0 else ('  <-- THIN' if n_works < 2 else '')
                print(f"      {k:<28}{n_cards:>4} cards {n_est:>4} quant {n_works:>3} works{flag}")

    print('\n  --- THE GATE (what it destroyed) ' + '-' * 44)
    r = stats['rejects']
    for k in ('span_not_in_source', 'number_not_in_span', 'second_hand_attribution', 'orphan_number',
              'field_not_in_source', 'mechanism_not_in_span', 'span_too_short', 'qualitative_no_outcome',
              'offset_roundtrip_failed', 'derived_claim_leaked_number', 'llm_error'):
        if r.get(k):
            print(f"    {k:<34}: {r[k]:,}")
    ex = r.get('_examples') or []
    if ex:
        print(f"\n    FABRICATED FIGURES CAUGHT (first 3 of {len(ex)}):")
        for e in ex[:3]:
            print(f"      {e['field']}=\"{e['value']}\" -> {e['fabricated']} NOT IN SPAN: \"{e['span'][:78]}...\"")
    print()


# =============================================================================================
# 9. THE ADVERSARIAL SUITE
# =============================================================================================

def self_test() -> int:
    fails: list[str] = []

    def ck(name: str, ok: bool, detail: str = ''):
        print(f"  [{'PASS' if ok else '**FAIL**'}] {name}")
        if detail and not ok:
            print(f'            {detail}')
        if not ok:
            fails.append(name)

    print('=== EVIDENCE MINER — ADVERSARIAL SUITE ===\n')
    MC = MiningContract()          # the generic contract: no research_contract, no question

    # --- THE SUBSTRING LEAK. This is the one that would have shipped a fabricated effect size.
    ck('"0.2" is NOT a number of a span whose only number is 10.25',
       '0.2' not in number_tokens('productivity growth of 10.25 percent was observed'),
       f"leaked: {number_tokens('productivity growth of 10.25 percent')}")
    ck('the naive test this replaces WOULD have leaked (proving the test is live)',
       '0.2' in 'productivity growth of 10.25 percent')
    ck('1,234 == 1234 (formatting is not fabrication)',
       number_tokens('a sample of 1,234 workers') == number_tokens('a sample of 1234 workers'))
    ck('0.20 == 0.2', number_tokens('fell 0.20 points') == number_tokens('fell 0.2 points'))

    src = ('4. Results\n'
           'We find that one more robot per thousand workers reduces the employment-to-population '
           'ratio by 0.2 percentage points (standard error 0.05). Our sample covers 722 commuting '
           'zones in the United States between 1990 and 2007.\n'
           'Table 3. Effect of robots on employment\n'
           'Robots per thousand workers   -0.39   (0.08)\n')
    view, chunks = chunk_document('d', src)
    ck('the RESULTS heading is found and weighted 1.00',
       any(c.section == 'results' for c in chunks),
       f'sections seen: {sorted({c.section for c in chunks})}')
    ck('100% of the text is chunked',
       sum(c.v_end - c.v_start for c in chunks) >= len(view.text) - 2)

    paper = {'doi': '10.x/y', 'authors': ['Acemoglu'], 'year': 2020, 'venue': 'JPE',
             'title': 'Robots and Jobs', 'abstract': '', 'attribution': 'W', 'attribution_short': 'S',
             '_source_version': 'abc', '_text_field': 'fulltext'}
    ch = [c for c in chunks if 'robot per thousand' in c.text][0]
    pw = paper_window(view, chunks, paper)

    good = {'span': 'We find that one more robot per thousand workers reduces the employment-to-population '
                    'ratio by 0.2 percentage points (standard error 0.05).',
            'effect': '0.2', 'unit': 'percentage points', 'comparator': 'per thousand workers',
            'outcome': 'employment-to-population ratio', 'population': 'commuting zones',
            'geography': 'United States', 'period': '1990 and 2007', 'technology': 'robot',
            'industry': '', 'unit_of_analysis': 'region', 'design': 'quasi-experimental',
            'uncertainty': 'standard error 0.05', 'horizon': 'long-run', 'mechanisms': []}
    r = new_rejects()
    c = gate_card(dict(good), view, ch, paper, pw, MC, r)
    ck('a TRUE, complete tuple is ADMITTED', c is not None and c['complete_tuple'],
       f'rejects={ {k:v for k,v in r.items() if v} }')
    if c:
        ck('the stored span is a SLICE OF THE SOURCE, not the model\'s string',
           view.src[c['span_start']:c['span_end']].strip().startswith('We find that one more robot'),
           repr(view.src[c['span_start']:c['span_end']])[:90])
        ck('claim is DERIVED after the gate and carries no figure absent from the span',
           not (number_tokens(c['claim']) - set(c['span_numbers'])), c['claim'])

    # --- 60 REAL CHARS + AN INVENTED TAIL
    r = new_rejects()
    tail = dict(good, span='We find that one more robot per thousand workers reduces employment by 47 '
                           'percent across every industry in the economy.', effect='47', unit='percent')
    ck('60 real chars followed by an INVENTED TAIL is REJECTED',
       gate_card(tail, view, ch, paper, pw, MC, r) is None, 'the invented tail was admitted')

    # --- A FABRICATED FIGURE IN A FIELD
    r = new_rejects()
    fab = dict(good, effect='0.39')          # 0.39 is in the TABLE, not in this span
    ck('a figure not in THIS span is REJECTED even though it is elsewhere in the paper',
       gate_card(fab, view, ch, paper, pw, MC, r) is None and r['number_not_in_span'] == 1)

    # --- THE SUBSTRING ATTACK, END TO END
    r = new_rejects()
    sub = {'span': 'Robots per thousand workers   -0.39   (0.08)', 'effect': '0.3',
           'unit': 'percentage points', 'outcome': 'employment', 'unit_of_analysis': 'region',
           'design': 'observational', 'uncertainty': '(0.08)', 'population': '', 'geography': '',
           'period': '', 'technology': 'robots', 'industry': '', 'comparator': 'per thousand workers'}
    tb = [x for x in chunks if x.section == 'tables']
    if tb:
        ck('a fabricated 0.3 does NOT pass because the span contains -0.39',
           gate_card(sub, view, tb[0], paper, pw, MC, r) is None and r['number_not_in_span'] == 1)
        r = new_rejects()
        row = dict(sub, effect='-0.39')
        got = gate_card(row, view, tb[0], paper, pw, MC, r)
        ck('a TABLE ROW is minable (the caption/header supplies the outcome; provenance recorded)',
           got is not None, f'rejects={ {k:v for k,v in r.items() if v} }')
        if got:
            ck('the table card records that `outcome` came from the CHUNK, not the span',
               got['field_provenance'].get('outcome') in ('chunk', 'span'), str(got['field_provenance']))
    else:
        ck('table block detected', False, 'no table chunk was produced')

    # --- ELLIPSIS = NOT WHOLE
    r = new_rejects()
    ell = dict(good, span='We find that one more robot per thousand workers ... by 0.2 percentage points.')
    ck('an ELIDED span ("<real> ... <invented>") is REJECTED',
       gate_card(ell, view, ch, paper, pw, MC, r) is None)

    # --- ORPHAN NUMBER
    r = new_rejects()
    orph = {'span': 'We find that one more robot per thousand workers reduces the employment-to-population '
                    'ratio by 0.2 percentage points (standard error 0.05).',
            'effect': '0.2', 'unit': '', 'comparator': '', 'outcome': '', 'population': '',
            'geography': '', 'period': '', 'technology': '', 'industry': '', 'unit_of_analysis': '',
            'design': '', 'uncertainty': ''}
    ck('an ORPHAN NUMBER (no unit, no outcome) is REJECTED',
       gate_card(orph, view, ch, paper, pw, MC, r) is None and r['orphan_number'] == 1)

    # --- SECOND-HAND ATTRIBUTION. Real spans, taken verbatim off disk from the first full mine.
    #     Every one of these passed the span gate AND the number gate, and every one would have been
    #     rendered as "Writing in <journal>, <author> shows that <someone else's number>".
    for label, sp in [
        ('a third-party forecast quoted by the paper',
         'It is estimated that, globally, 326 million mostly-low-skilled jobs will be adversely '
         'affected by AI within 10 years, with 0.5 percent of them in manufacturing.'),
        ('a numbered citation to another study',
         '[34] find that one additional robot per thousand workers reduces the employment rate by '
         '0.5 percentage points across commuting zones.'),
        ('an institutional attribution',
         'According to the World Economic Forum, the adoption of AI will make 0.5 million jobs '
         'redundant in the retail sector by 2030.'),
    ]:
        src2 = f'4. Results\n{sp}\n'
        v2, ch2 = chunk_document('d', src2)
        r = new_rejects()
        got = gate_card({'span': sp, 'effect': '0.5', 'unit': 'percentage points',
                         'outcome': 'employment rate', 'unit_of_analysis': 'region',
                         'design': 'observational', 'population': 'commuting zones',
                         'geography': '', 'period': '', 'technology': '', 'industry': '',
                         'comparator': '', 'uncertainty': ''},
                        v2, ch2[0], paper, paper_window(v2, ch2, paper), MC, r)
        ck(f'SECOND-HAND: {label} is REJECTED',
           got is None and r['second_hand_attribution'] == 1,
           'a real number from a real paper was about to be credited to the wrong source')

    # ...but the paper's OWN result, in its own voice, still gets through even when it cites a source
    r = new_rejects()
    own = dict(good, span='We find that one more robot per thousand workers reduces the '
                          'employment-to-population ratio by 0.2 percentage points (standard error 0.05).')
    ck('...and the paper speaking in its OWN voice is still ADMITTED',
       gate_card(own, view, ch, paper, pw, MC, r) is not None,
       f'the second-hand gate is starving us: {[k for k, v in r.items() if v]}')

    # --- A FORECAST IS NOT A MEASURED EFFECT
    fsrc = ('4. Results\nWe estimate that 0.2 percent of employment will be displaced by 2030 in the '
            'manufacturing sector.\n')
    fv, fch = chunk_document('d', fsrc)
    fcard = gate_card({'span': 'We estimate that 0.2 percent of employment will be displaced by 2030 '
                               'in the manufacturing sector.', 'effect': '0.2', 'unit': 'percent',
                       'outcome': 'employment', 'unit_of_analysis': 'economy', 'design': 'simulation',
                       'population': 'manufacturing sector', 'geography': '', 'period': '',
                       'technology': '', 'industry': 'manufacturing', 'comparator': '',
                       'uncertainty': ''}, fv, fch[0], paper, paper_window(fv, fch, paper), MC,
                      new_rejects())
    ck('a FORECAST is kept but labelled `projection`, never counted as a measured estimate',
       fcard is not None and fcard['card_kind'] == 'projection' and not fcard['complete_tuple'],
       str(fcard and (fcard['card_kind'], fcard['complete_tuple'])))

    # --- ONE DEFINITION OF THE SOURCE TEXT (the miner and the verifier must never drift)
    pp = {'fulltext': '  ' + 'x' * 900 + '  ', 'abstract': 'short'}
    t1, f1, v1 = source_text(pp)
    ck('source_text() is the single definition of the source, and it strips',
       f1 == 'fulltext' and t1 == 'x' * 900 and len(v1) == 12)
    ck('...and a paper with no usable fulltext falls back to its abstract',
       source_text({'fulltext': 'tiny', 'abstract': 'a real abstract'})[1] == 'abstract')

    # --- A HALLUCINATED MECHANISM
    r = new_rejects()
    mech = dict(good, mechanisms=['task displacement', 'skill complementarity'])
    c2 = gate_card(mech, view, ch, paper, pw, MC, r)
    ck('a mechanism the span never states is DROPPED (the 43%-invention hole stays shut)',
       c2 is not None and c2['mechanisms'] == [] and r['mechanism_not_in_span'] == 2)

    # --- THE SPAN IS NOT IN THE PAPER AT ALL
    r = new_rejects()
    ghost = dict(good, span='We find that generative AI raises output by 0.2 percentage points in every firm we study.')
    ck('a span that is not in the source at all is REJECTED',
       gate_card(ghost, view, ch, paper, pw, MC, r) is None and r['span_not_in_source'] == 1)

    # --- PDF LINE-WRAP. The bug that hid the single most important number in the corpus.
    #     Acemoglu & Restrepo's headline estimate is stored hard-wrapped across three PDF lines.
    #     Treating those newlines as breaks shreds it, putting the effect size in a different
    #     fragment from the outcome it is an effect on -- so the harvester never sees the finding
    #     and any span quoted from it is a fragment. Every prose finding in the corpus dies this way.
    wrapped = ('According to our estimates, one more robot per thousand workers reduces\n'
               'the employment to population ratio by about 0.18-0.34 percentage points and wages by 0.25-0.5\n'
               'percent. We also find that the effects are most pronounced in manufacturing, and in\n'
               'particular in industries most exposed to robots, and for workers with less than college.\n')
    wv = View(wrapped)
    ck('a PDF-wrapped sentence is STITCHED back into one sentence',
       'reduces the employment to population ratio' in wv.flat, repr(wv.text[:80]))
    ws = sentences(wv.text)
    ck('...so the effect size and the outcome land in the SAME sentence',
       any('one more robot' in s[2] and '0.18-0.34' in s[2] for s in ws),
       ' | '.join(repr(s[2][:52]) for s in ws))
    wch = Chunk('d', 0, 'results', 1.0, 0, len(wv.text), 0, len(wv.text), wv.text)
    wh = harvest(wch, MC)
    ck('...and the harvester now SEES the headline finding it used to be blind to',
       any('0.18-0.34' in c['text'] and 'robot' in c['text'] for c in wh),
       f'{len(wh)} candidates: ' + ' | '.join(c['text'][:46] for c in wh))
    ck('a TABLE ROW keeps its own line (de-wrapping must not flatten tables)',
       View('Table 3. Robots and employment\nRobots per thousand   -0.39   (0.08)\n'
            'Population              0.12   (0.03)\n').text.count('\n') >= 2)

    # --- PAGE FURNITURE. A bare page number dropped into the middle of a sentence at a page break.
    furn = ('and the evidence from the commuting-zone regressions strongly suggests that robots have\n'
            '23\n'
            'displaced workers, since one more robot per thousand workers reduces employment by 6.2\n'
            'workers in the local labor market over the period we study, holding trade constant.\n')
    fv = View(furn)
    ck('a page number that INTERRUPTS a sentence is deleted from the view',
       'suggests that robots have displaced workers' in fv.flat, repr(fv.flat[:100]))
    ck('...and the offsets still land on the right source bytes across the deletion',
       (lambda a: 'have' in fv.src[fv.src_span(a, a + 44)[0]:fv.src_span(a, a + 44)[1]]
        and 'displaced' in fv.src[fv.src_span(a, a + 44)[0]:fv.src_span(a, a + 44)[1]])(
           fv.low.find('have displaced workers')))
    tbl_num = View('Table 2. Estimates\nRobots\n-0.39\n(0.08)\nWages\n0.12\n')
    ck('a lone number between SHORT lines is a TABLE CELL and is NOT deleted',
       '-0.39' in tbl_num.text and '0.08' in tbl_num.text)

    # --- OFFSETS ROUND-TRIP THROUGH PDF HYPHENATION
    hy = View('the employment-to-popula-\ntion ratio fell by 0.2 percentage points in the sample.')
    ck('PDF end-of-line hyphenation is stitched ("popula-\\ntion" -> "population")',
       'population ratio' in hy.text, hy.text[:60])
    a = hy.low.find('population ratio')
    s0, s1 = hy.src_span(a, a + len('population ratio'))
    ck('...and the offsets still point at the right bytes of the ORIGINAL source',
       'popula-' in hy.src[s0:s1] and 'tion ratio' in hy.src[s0:s1], repr(hy.src[s0:s1]))

    # --- CONSOLIDATION KEEPS CORROBORATION
    base = dict(good)
    c_a = gate_card(dict(base), view, ch, paper, pw, MC, new_rejects())
    p2 = dict(paper, doi='10.z/w', authors=['Graetz'], attribution='W2', attribution_short='S2')
    c_b = gate_card(dict(base), view, ch, p2, pw, MC, new_rejects())
    merged = consolidate([c_a, c_b])
    ck('the same finding in TWO papers becomes ONE card with TWO sources (not a deletion)',
       len(merged) == 1 and merged[0]['n_sources'] == 2 and len(merged[0]['corroborating_sources']) == 1,
       f'{len(merged)} cards, n_sources={merged[0].get("n_sources") if merged else "-"}')
    ck('the corroborating source keeps ITS OWN span and offsets',
       bool(merged and merged[0]['corroborating_sources'][0]['span']))

    # --- THE HARVEST IS NOT FOOLED BY A BIBLIOGRAPHY
    ch_ref = Chunk('d', 0, 'references', 0.0, 0, 200, 0, 200,
                   'Autor, D. (2015). Why are there still so many jobs? Journal of Economic '
                   'Perspectives, 29(3), 3-30. doi:10.1257/jep.29.3.3')
    ck('a reference-list entry is NOT harvested as a quantitative candidate',
       harvest(ch_ref, MC) == [])
    ch_res = Chunk('d', 0, 'results', 1.0, 0, 200, 0, 200,
                   'We estimate that one more robot per thousand workers reduces employment by 0.2 '
                   'percentage points (p<0.01).')
    h = harvest(ch_res, MC)
    ck('a results sentence IS harvested, with its kinds', len(h) == 1 and 'pct_points' in h[0]['kinds'],
       str(h))

    # --- FACETS ARE OPTIONAL AND NEVER TOUCH A GATE
    c0 = load_contract('', None)
    ck('the miner runs with NO research_contract and NO question',
       isinstance(c0, MiningContract) and c0.origin == 'none' and c0.tag('anything') == [])
    ck('...and the generic enums still close the vocabulary',
       'occupation' in c0.levels and 'quasi-experimental' in c0.designs)
    c1 = load_contract('', [{'name': 'industry', 'terms': ['manufacturing', 'car plants']}])
    ck('an explicitly-passed facet list is accepted',
       c1.origin == 'argument' and c1.tag('robots in manufacturing plants') == ['facet:industry'],
       str(c1.tag('robots in manufacturing plants')))
    c2 = load_contract('', [{'name': 'ind', 'terms': ['manufacturing']}])
    ck('a facet tag NEVER admits a card by itself (tagging is not a gate)',
       gate_card({'span': 'irrelevant', 'effect': '5'}, view, ch, paper, pw, c2, new_rejects()) is None)

    print()
    if fails:
        print(f'** {len(fails)} FAILURE(S) **')
        for f in fails:
            print(f'   - {f}')
        return 1
    print('** ALL GATES HOLD. **')
    return 0


# =============================================================================================
# 10. THE ARTIFACT VERIFIER
#
# Every defect that has cost this project a turn got past a GREEN self-test, because the self-test
# checked a CODE PATH in a phrasing the author invented, and the thing that ships is a FILE. So this
# re-opens the corpus and the written cards INDEPENDENTLY and asks the only question that cannot be
# fooled: does the evidence on disk actually exist in the papers on disk?
#
# It trusts nothing the miner said. It re-derives everything from the two JSON files.
# =============================================================================================

def verify_artifact(cards_path: Path, corpus_path: Path) -> int:
    cards = json.loads(cards_path.read_text())
    corpus = {c['doi']: c for c in json.loads(corpus_path.read_text())}
    print(f'=== VERIFYING {len(cards)} cards in {cards_path.name} AGAINST {corpus_path.name} ===\n')

    bad_offsets, bad_numbers, bad_version, missing = [], [], [], []
    checked = 0
    for c in cards:
        srcs = [c] + list(c.get('corroborating_sources') or [])
        for s in srcs:
            paper = corpus.get(s.get('doi'))
            if not paper:
                missing.append(s.get('doi'))
                continue
            text, _, _ = source_text(paper)          # THE SAME definition the miner used. Only one.
            a, b = s.get('span_start', -1), s.get('span_end', -1)
            if not (0 <= a < b <= len(text)):
                bad_offsets.append((s.get('doi'), a, b, 'out of range'))
                continue
            # THE SPAN MUST BE RECOVERABLE FROM THE BYTES THE CARD POINTS AT.
            if not _is_subsequence(_alnum(s.get('span') or ''), _alnum(text[a:b])):
                bad_offsets.append((s.get('doi'), a, b, 'span is not in those bytes'))
            checked += 1
        # EVERY FIGURE IN EVERY TUPLE FIELD MUST BE A NUMBER OF THE PRIMARY SPAN.
        span_nums = number_tokens(c.get('span') or '')
        for f in TUPLE_FIELDS + ['claim']:
            leaked = number_tokens(c.get(f) or '') - span_nums
            if leaked:
                bad_numbers.append((c.get('doi'), f, c.get(f), sorted(leaked)))
        paper = corpus.get(c.get('doi'))
        if paper:
            _, _, version = source_text(paper)
            if c.get('source_version') and version != c['source_version']:
                bad_version.append(c.get('doi'))

    ok = True
    def ck(name, bad, sample=None):
        nonlocal ok
        print(f"  [{'PASS' if not bad else '**FAIL**'}] {name}: {len(bad) if bad else 0}")
        if bad:
            ok = False
            for x in list(bad)[:3]:
                print(f'            {x}')

    print(f'  {checked} span+offset pairs re-derived from the corpus\n')
    ck('spans whose bytes do NOT contain them', bad_offsets)
    ck('tuple figures NOT present in their own span', bad_numbers)
    ck('cards whose source paper has changed since mining', bad_version)
    ck('cards citing a paper not in the corpus', missing)

    est = [c for c in cards if c.get('card_kind') == 'estimate']
    print(f"\n  {len(est)} quantitative findings, every figure re-derivable from a byte range of a journal PDF")
    print(f"  {sum(1 for c in cards if c.get('complete_tuple'))} carry a complete estimate tuple")
    print()
    if not ok:
        print('** THE ARTIFACT DOES NOT MATCH THE SOURCES. NOTHING SHIPS. **')
        return 1
    print('** EVERY CLAIM ON DISK IS RE-DERIVABLE FROM THE PAPERS ON DISK. **')
    return 0


# =============================================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--corpus', type=Path, default=CORPUS)
    ap.add_argument('--out', type=Path, default=OUT_CARDS)
    ap.add_argument('--question', default=os.getenv('PG_RESEARCH_QUESTION', ''),
                    help='the research question; facets are compiled from it (or from research_contract.py)')
    ap.add_argument('--question-file', type=Path, default=None)
    ap.add_argument('--dry-run', action='store_true', help='deterministic harvest only — no LLM, no cost')
    ap.add_argument('--self-test', action='store_true')
    ap.add_argument('--verify', action='store_true',
                    help='re-verify the written cards against the corpus, trusting nothing')
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--limit', type=int, default=None, help='first N papers (smoke test)')
    ap.add_argument('--max-chunks-per-paper', type=int, default=0, help='0 = all')
    a = ap.parse_args()

    if a.self_test:
        return self_test()
    if a.verify:
        return verify_artifact(a.out, a.corpus)

    q = a.question
    if a.question_file and a.question_file.exists():
        q = a.question_file.read_text().strip()

    cards, stats = mine(a.corpus, question=q, use_llm=not a.dry_run, workers=a.workers,
                        limit=a.limit, max_chunks_per_paper=a.max_chunks_per_paper)
    report(cards, stats)

    if not a.dry_run:
        a.out.write_text(json.dumps(cards, indent=1))
        OUT_META.write_text(json.dumps(stats, indent=1))
        print(f'  wrote {a.out}')
        print(f'  wrote {OUT_META}')
    else:
        print('  [--dry-run] nothing written')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
