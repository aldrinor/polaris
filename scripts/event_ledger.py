#!/usr/bin/env python3
"""EVENT LEDGER — every status is a PURE REDUCER over an append-only event log.

    Sol, item 8: "NO COMPONENT MAY WRITE `complete`, `fulltext`, `no evidence`, `same work`,
                  or `high quality` DIRECTLY."

THE FAILURE THIS IS THE STRUCTURAL CURE FOR

  Every defect we have shipped had ONE shape: A LABEL THAT ASSERTED MORE THAN ITS CONTENT
  SUPPORTED, WITH NOTHING CHECKING. Not one announced itself; each read as a fact about the world.

      "gate: WIRED"          -> it checked the wrong lane; fabrication shipped
      "span-verified"        -> verified by its FIRST 60 CHARACTERS
      "still paywalled"      -> we asked by DOI; the free copy is a SEPARATE WORK
      "FULLTEXT"             -> 535 words. A cookie banner.
      "no free copy exists"  -> we were HTTP 429/404. A fact about OUR REQUEST and THEIR INDEX,
                                disguised as a fact about the world.
      "working_paper"        -> written by whichever SCRIPT ran, not by what the document IS.

  A component that CAN assert its own success will eventually assert it falsely, and nothing will
  catch it. So here a component may ONLY EMIT EVENTS — observations, in the vocabulary of the world:
  an HTTP status, a word count, a byline, a glyph ratio. The LABEL is DERIVED from those events by a
  reducer nobody can bypass, and the label is never stored anywhere a component could overwrite it.

THE TWO RULES THAT MAKE IT STRUCTURAL, NOT ADVISORY

  1. EMIT-TIME CONCLUSION GUARD. `Ledger.emit()` REJECTS any event whose payload carries a terminal
     conclusion — a key like `content_status`, or a value like "FULLTEXT" / "same work" /
     "no evidence" / "high quality". You cannot write the label into the ledger even if you try.
     Raw text quoted from the world (`header_text`, `span`, `document_title`) is exempt: a fetched
     PDF is allowed to contain the word "complete". A COMPONENT is not.

  2. LABELS ARE NEVER STORED. They are computed on read by `derive_*` pure functions over the event
     list. There is no field to corrupt, no cache to go stale, and no way to "just set it".

THE DISTINCTIONS THAT MUST NEVER COLLAPSE (Sol)

    HTTP 429/503        -> BACKEND_FAILED.  ** NOT "no evidence exists". **
    HTTP 404            -> NOT_INDEXED_BY_THIS_BACKEND. A fact about THEIR INDEX. Also not absence.
    route_complete      -> EVERY PLANNED ADAPTER HAS A TERMINAL OUTCOME RECORD.
                           It must NEVER mean "an adapter was mapped."
    a budget stop       -> IS NOT AN EVIDENCE GAP.
    absence             -> only an ADEQUATE route (every adapter genuinely answered, none throttled,
                           none blocked, no budget stop) can support a scoped absence statement.
    "high_quality"      -> FORBIDDEN as a bare label. It renders as its COMPONENTS, each with
                           provenance: directness=high, method_quality=low, influence_percentile=0.92.

Run it:
    python3 scripts/event_ledger.py            # self-test + replay of our real history
    python3 scripts/event_ledger.py --replay   # just the replay
    python3 scripts/event_ledger.py --selftest # just the invariants
"""
from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

# THE REGISTRY, AND THE ONE COMPLETENESS REDUCER. Imported — never re-implemented. This module used to
# carry its own `FULLTEXT_MIN = 2500` while provenance.py used 1,200, and neither knew about the
# other. See the headstone at "3. content profile", below.
from provenance import (  # noqa: E402
    KIND_PROFILE, judge_completeness,
    SOURCE_TYPE as _SOURCE_TYPE, WORK_KIND_ARTIFACT as _WORK_KIND_ARTIFACT,
    # ONE definition of "what is a repository cover sheet", shared with the provenance lane. Two
    # copies of this pattern would drift, and the one that drifts is always the one a gate reads.
    _COVER_SHEET,
    # ...and ONE definition of "which stamps mark an accepted manuscript", for the SAME reason. This
    # used to be a SECOND copy (`_ACCEPTED_STAMP`, hand-maintained here) and the two DID drift: hop 6
    # widened provenance._AM_MARK to catch the NIH author-manuscript tells ("author manuscript;
    # available in PMC", "NIHMS<digits>") and this file's copy never learned them, so an NIH accepted
    # manuscript that provenance ruled `accepted_manuscript` was scored VERSION_PUBLISHED here and
    # became journal evidence. There is now ONE detector, imported, so the two lanes CANNOT diverge.
    _AM_MARK as _ACCEPTED_STAMP,
)

CORPUS = ROOT / 'outputs' / 'journal_corpus_content.json'
LEDGER_OUT = ROOT / 'outputs' / 'event_ledger.jsonl'


# ══════════════════════════════════════════════════════════════════════════════════════════════
# EVENTS — the only thing a component may write.
# ══════════════════════════════════════════════════════════════════════════════════════════════

class EventKind:
    """Sol's twelve, verbatim, plus the budget stop (which must be distinguishable from a gap)."""
    ROUTE_PLANNED             = 'route_planned'
    BACKEND_ATTEMPTED         = 'backend_attempted'
    RESPONSE_RECEIVED         = 'response_received'
    THROTTLED                 = 'throttled'
    BLOCKED                   = 'blocked'
    CANDIDATE_IDENTIFIED      = 'candidate_identified'
    MANIFESTATION_FETCHED     = 'manifestation_fetched'
    CONTENT_PROFILE_DERIVED   = 'content_profile_derived'
    SEMANTIC_BINDING_DECIDED  = 'semantic_binding_decided'
    ELIGIBILITY_DECIDED       = 'eligibility_decided'
    WEIGHT_COMPONENTS_DERIVED = 'weight_components_derived'
    COVERAGE_STATUS_DERIVED   = 'coverage_status_derived'
    # "a budget stop IS NOT AN EVIDENCE GAP" — so it needs its own event, or it cannot be told apart.
    BUDGET_STOPPED            = 'budget_stopped'

    ALL = {ROUTE_PLANNED, BACKEND_ATTEMPTED, RESPONSE_RECEIVED, THROTTLED, BLOCKED,
           CANDIDATE_IDENTIFIED, MANIFESTATION_FETCHED, CONTENT_PROFILE_DERIVED,
           SEMANTIC_BINDING_DECIDED, ELIGIBILITY_DECIDED, WEIGHT_COMPONENTS_DERIVED,
           COVERAGE_STATUS_DERIVED, BUDGET_STOPPED}


class ForbiddenLabel(Exception):
    """A component tried to write a conclusion into the ledger. That is the whole disease."""


#: Terminal conclusions. A component may not state these — the reducer derives them.
#:
#: Sol V9 §1, verbatim: "The adapter must not write FULLTEXT, THIS_WORK, VERSION_OF_RECORD, ADMISSIBLE,
#: or an expression edge. Those are reducer outputs derived from immutable metadata and document bytes."
#: FULLTEXT, ADMISSIBLE and `same work` were already here. THIS_WORK and VERSION_OF_RECORD were not —
#: and an adapter that may write `version_of_record` into a payload has been handed, by the back door,
#: precisely the authority the V9 P0 was about taking away from it. A repository saying `acceptedVersion`
#: is an OBSERVATION; a component writing `version_of_record` is a VERDICT.
RESERVED_VALUES = (
    'fulltext', 'full text', 'full-text',
    'complete', 'route_complete',
    'no evidence', 'no free copy', 'no free text', 'not available', 'nothing found',
    'same work', 'same_work', 'this work', 'this_work', 'different work', 'different_work',
    'version equivalent', 'version of record', 'version_of_record',
    'high quality', 'high_quality', 'low quality', 'low_quality',
    'paywalled', 'still paywalled',
    'supported', 'searched_none', 'conflicted',
    'admissible', 'inadmissible', 'eligible',
    'verified', 'span-verified', 'fabrication-proof',
)

#: Keys that ARE labels. Naming one is an attempt to set the label directly.
RESERVED_KEYS = (
    'content_status', 'status', 'label', 'verdict', 'quality', 'tier', 'grade',
    'fulltext_source', 'is_fulltext', 'route_complete', 'complete', 'coverage',
    'coverage_status', 'eligibility', 'binding', 'admissible', 'evidence_status',
)

#: Fields that are RAW TEXT QUOTED FROM THE WORLD. A PDF may contain any word at all; that is not
#: the component asserting it. These are exempt from the value scan (never from the key scan).
#: NOTE what is NOT here: `note`. A free-text `note` is the COMPONENT talking, not the world, and it
#: is precisely where a conclusion would be smuggled in ("note: no free copy exists"). It stays
#: scanned. (The guard caught exactly that in this file's own replay code, and the fix was to reword
#: the note into an observation — not to exempt the field.)
#: `locator` is here for the same reason `url` is: IT IS A URL. Publishers put our own reserved words
#: inside their paths (`/articles/PMC.../?report=fulltext`, `/science/article/.../fulltext`), and a
#: guard that refused to record THE ADDRESS THE BYTES CAME FROM — because the address contains the
#: string "fulltext" — would have made the locator unrecordable and left us exactly where we were:
#: holding an NBER working paper under a URL pointing at aeaweb.org.
#: `requested_venue` sits beside `requested_title` for the same reason: it is a NAME, quoted from the
#: bibliography. There is a journal called `Information & Management` and there could be one called
#: `Complete Systems`; a guard that refused to record which journal we asked about, because the
#: journal's name contains one of our reserved words, would be a guard against nothing.
VERBATIM_KEYS = frozenset({
    'header_text', 'identity_window', 'span', 'document_title', 'byline', 'snippet', 'raw', 'title',
    'reason_text', 'requested_title', 'requested_venue', 'url', 'locator', 'doi', 'venue',
})


def _scan_value(k: str, v, bad: list[str], path: str = '') -> None:
    """Scan ONE value, RECURSIVELY.

    IT DID NOT RECURSE. The scan ran over `payload.items()` and tested `isinstance(v, str)` — so a
    conclusion one level down was invisible to it:

        emit(..., adapter_observations={'content_status': 'FULLTEXT'})    # ACCEPTED. Silently.

    A guard that only inspects the top level of a nested structure is a guard you step over by adding
    a dict, and "the checks certify a lane the fabrication no longer uses" is the sentence this whole
    project is trying to stop writing. Payloads stay flat by convention; this makes it true by force.
    """
    where = f'{path}{k}'
    if isinstance(v, str):
        vl = v.lower().strip()
        for r in RESERVED_VALUES:
            # match the whole value or a word-bounded occurrence — not a substring of a word
            if vl == r or re.search(rf'(?<![a-z0-9_]){re.escape(r)}(?![a-z0-9_])', vl):
                bad.append(f'{where}={v!r} states the conclusion {r!r}; emit the OBSERVATION instead '
                           f'(word_count / http_status / byline), and let the reducer conclude')
                return
    elif isinstance(v, dict):
        for k2, v2 in v.items():
            if str(k2).lower() in RESERVED_KEYS:
                bad.append(f'key {where}.{k2!r} IS a label — the reducer derives it; a component may '
                           f'not set it, and burying it one level down does not make it an observation')
                continue
            if str(k2).lower() in VERBATIM_KEYS:
                continue
            _scan_value(str(k2), v2, bad, path=f'{where}.')
    elif isinstance(v, (list, tuple)):
        for i, v2 in enumerate(v):
            _scan_value(f'[{i}]', v2, bad, path=where)


@dataclass(frozen=True)
class Event:
    """An OBSERVATION. Immutable, ordered, and never a conclusion."""
    seq: int
    unit: str                    # what this is about — a DOI, a coverage cell id, a route id
    kind: str
    actor: str                   # which component observed it (for provenance, not for authority)
    payload: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps({'seq': self.seq, 'unit': self.unit, 'kind': self.kind,
                           'actor': self.actor, 'payload': self.payload, 'ts': self.ts},
                          sort_keys=True)


def _scan_for_conclusions(kind: str, payload: dict) -> list[str]:
    """Return the reasons this payload is an ASSERTION rather than an OBSERVATION."""
    bad: list[str] = []
    for k, v in payload.items():
        kl = str(k).lower()
        if kl in RESERVED_KEYS:
            bad.append(f'key {k!r} IS a label — the reducer derives it; a component may not set it')
            continue
        if kl in VERBATIM_KEYS:
            continue                       # raw text from the world. It may say anything.
        _scan_value(str(k), v, bad)
    return bad


def _observations(events: list['Event']) -> list['Event']:
    """THE OBSERVATIONS ONLY. A reducer NEVER reads another reducer's recorded verdict.

    `record_derivation()` writes audit artifacts into the same log, and the module docstring has
    always claimed "NO REDUCER READS THEM". That was true only BY ACCIDENT OF KIND CHOICE — nothing
    enforced it. It was one line from being false in the worst way: a derived record written with
    kind=CONTENT_PROFILE_DERIVED is picked up by `derive_content_profile`'s `for e in events` loop,
    which keeps the LAST match — so the reducer would have read ITS OWN PREVIOUS OUTPUT as if it were
    an observation of the bytes, and the label would have become a cache of itself. That is the cookie
    banner, again, from the inside.

    So the invariant is now structural, in one place, and every derive_*() below goes through it.
    """
    return [e for e in events if 'derived_by' not in e.payload]


class LedgerCorrupt(Exception):
    """The persisted log does not agree with itself. It is REFUSED, never silently repaired."""


class Ledger:
    """Append-only, DURABLE, and RELOADABLE. You may add an observation. You may not edit, delete,
    or conclude.

    IT DID NOT RELOAD. `__init__` set `self._events = []` and never read the file, so a ledger opened
    over an existing JSONL began with an EMPTY HISTORY — while still appending to the end of it. Every
    standalone script therefore reduced over the handful of events IT had emitted, not over what
    happened. `derive_route_status()` would find one adapter planned instead of four and call the route
    COMPLETE; `derive_coverage_status()` would license a scoped absence off a history it could not see.
    A reducer over an append-only log that does not read the log is not a reducer over anything — and
    it fails in the direction of CONFIDENCE, which is the only direction that ships.
    """

    def __init__(self, path: Path | str | None = None, *, load: bool = True):
        self._events: list[Event] = []
        self._path = Path(path) if path else None
        self._seq = 0
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            if load and self._path.exists():
                self._load()

    @classmethod
    def load(cls, path: Path | str) -> 'Ledger':
        """Open the ledger AS IT STANDS ON DISK. This is the constructor a standalone script wants."""
        return cls(path, load=True)

    # -- read the history back --------------------------------------------------------------------
    def _load(self) -> None:
        """A PERSISTED LEDGER IS AN UNTRUSTED INPUT, and it is exactly as untrusted as the corpus was.

        The emit-time guard is RE-APPLIED here. Bypassing it on read would leave the door it locks
        standing open: `echo '{"payload":{"content_status":"FULLTEXT"}}' >> ledger.jsonl` is not a
        harder attack than calling emit(), it is an easier one.

        A record written by a reducer (it carries `derived_by`) is exempt from that scan, because its
        whole job is to hold a derived verdict. Forging one buys nothing: NO REDUCER READS THEM. They
        are audit artifacts, and every derive_*() in this file re-derives from the OBSERVATIONS. That
        is the difference between a ledger and a cache, and caching the label is how we shipped
        FULLTEXT on a cookie banner.
        """
        seen: set[int] = set()
        events: list[Event] = []
        for i, line in enumerate(self._path.read_text().splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            where = f'{self._path.name}:{i}'
            try:
                d = json.loads(line)
            except json.JSONDecodeError as e:
                raise LedgerCorrupt(f'{where}: not JSON — {e}')
            missing = {'seq', 'unit', 'kind', 'actor', 'payload', 'ts'} - set(d)
            if missing:
                raise LedgerCorrupt(f'{where}: missing field(s) {sorted(missing)}')
            if d['kind'] not in EventKind.ALL:
                raise LedgerCorrupt(f'{where}: unknown event kind {d["kind"]!r}')
            if not isinstance(d['payload'], dict):
                raise LedgerCorrupt(f'{where}: payload is not an object')
            if not isinstance(d['seq'], int) or d['seq'] in seen:
                raise LedgerCorrupt(f'{where}: seq {d["seq"]!r} is duplicated or not an integer — an '
                                    f'append-only log with a repeated sequence number has been edited')
            if 'derived_by' not in d['payload']:
                problems = _scan_for_conclusions(d['kind'], d['payload'])
                if problems:
                    raise LedgerCorrupt(
                        f'{where}: this line writes a CONCLUSION into the ledger — the emit guard '
                        f'refuses it, and so does the loader:\n    ' + '\n    '.join(problems))
            seen.add(d['seq'])
            events.append(Event(seq=d['seq'], unit=d['unit'], kind=d['kind'], actor=d['actor'],
                                payload=d['payload'], ts=d['ts']))
        events.sort(key=lambda e: e.seq)
        self._events = events
        self._seq = max(seen, default=0)     # ...so the next append CONTINUES the log, never collides

    # -- write side: exactly one method, and it is guarded -------------------------------------
    def emit(self, unit: str, kind: str, actor: str, **payload) -> Event:
        if kind not in EventKind.ALL:
            raise ForbiddenLabel(f'unknown event kind {kind!r}')
        problems = _scan_for_conclusions(kind, payload)
        if problems:
            raise ForbiddenLabel(
                f'{actor} tried to write a CONCLUSION into the ledger:\n    ' + '\n    '.join(problems))
        return self._append(unit, kind, actor, payload)

    def _append(self, unit: str, kind: str, actor: str, payload: dict) -> Event:
        self._seq += 1
        ev = Event(seq=self._seq, unit=unit, kind=kind, actor=actor, payload=dict(payload))
        self._events.append(ev)
        if self._path:
            # One line, one open, closed immediately: the record is with the OS before emit() returns.
            # An event that is in memory but not on disk is a history that disagrees with itself the
            # moment the process dies.
            with open(self._path, 'a') as fh:
                fh.write(ev.to_json() + '\n')
                fh.flush()
        return ev

    # -- the reducer's audit trail --------------------------------------------------------------
    def record_derivation(self, unit: str, kind: str, reducer: str, inputs: list[int],
                          **verdict) -> Event:
        """A reducer may append its own verdict — FOR AUDIT ONLY. Nobody else can call this.

        The frame check below is not decoration. `emit()` is the door components use, and it refuses
        conclusions. This is the door the reducer uses, and it is bolted from the inside: if the
        calling frame is not this module, it raises. There is no third door.

        Downstream reducers NEVER TRUST these records — they RE-DERIVE from the observations. A
        recorded verdict is an audit artifact, not an authority. That is the difference between a
        ledger and a cache, and caching the label is how we shipped "FULLTEXT" on a cookie banner.
        """
        import inspect
        caller = inspect.currentframe().f_back
        if caller.f_globals.get('__name__') != __name__:
            raise ForbiddenLabel(
                f'{caller.f_globals.get("__name__")!r} tried to record a DERIVED label directly. '
                f'Only a reducer inside {__name__} may. Emit OBSERVATIONS and call derive_*().')
        return self._append(unit, kind, reducer,
                            {**verdict, 'derived_by': reducer, 'from_events': list(inputs)})

    # -- read side ------------------------------------------------------------------------------
    def events(self, unit: str | None = None, kind: str | None = None) -> list[Event]:
        return [e for e in self._events
                if (unit is None or e.unit == unit) and (kind is None or e.kind == kind)]

    def units(self) -> list[str]:
        return list(dict.fromkeys(e.unit for e in self._events))

    def __len__(self) -> int:
        return len(self._events)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# OBSERVERS — pure functions from raw content to OBSERVATIONS. They conclude nothing.
# ══════════════════════════════════════════════════════════════════════════════════════════════

_CID = re.compile(r'\(cid:\d+\)')
_CHROME = re.compile(
    r'website uses cookies|accept\s+(?:all\s+)?cookies|by clicking the "accept" button|'
    r'enable javascript|sign in to (?:your account|continue)|create an account|'
    r'this site requires|subscribe to (?:read|view)|purchase access|add to cart|'
    # ...the repository LANDING PAGES that fooled us: Oxford ORA, PubMed Central, generic portals.
    r'skip to main content|we welcome feedback|send message|research archive|'
    r'privacy policy|terms of use|all rights reserved|official websites use',
    re.I)
_PUBLISHED_STAMP = re.compile(r'published version|version of record|\(refereed\)|original citation', re.I)

#: ══ THE ACCEPTED-MANUSCRIPT STAMP — THE V9 P0'S FIFTH HOP, AND ITS SEVENTH ══════════════════════════
#:
#: `_PUBLISHED_STAMP` above matches the phrase "published version". A repository cover sheet prints that
#: phrase IN TWO OPPOSITE SENSES, and until an accepted-manuscript stamp existed the reducer could not
#: tell them apart:
#:
#:    LSE, on the file that IS the AER article:
#:        "Article (Published version) (Refereed)"        <- the library says: THIS FILE is the VoR
#:    White Rose, on an author's manuscript:
#:        "This is an author produced version of a paper published in <journal>.
#:         Citation for the published version: ..."       <- the library says: THE VoR IS ELSEWHERE
#:
#: The second one is a cover sheet POINTING AWAY FROM ITSELF, and `_PUBLISHED_STAMP` read it as the
#: document testifying that it IS the version of record. `derive_semantic_binding` returned
#: VERSION_PUBLISHED, `derive_eligibility` returned ADMISSIBLE, and an accepted manuscript became
#: journal evidence — the SAME P0 as the census ladder, in a different file, reached by a different road.
#:
#: `_ACCEPTED_STAMP` IS NO LONGER DEFINED HERE. It WAS — a second, hand-maintained copy of the same
#: pattern that lives in provenance._AM_MARK — and the two DIVERGED, which is the seventh hop: hop 6
#: widened `_AM_MARK` to catch the NIH author-manuscript tells ("author manuscript; available in PMC",
#: "NIHMS<digits>") and this copy never learned them, so `derive_semantic_binding` scored an NIH
#: accepted manuscript VERSION_PUBLISHED while provenance ruled it `accepted_manuscript`. Two detectors
#: for ONE question ("which stamps mark an accepted manuscript") is two answers waiting to disagree, and
#: the one that drifts is always the one a gate reads. So the name now BINDS THE IMPORTED `_AM_MARK`
#: (see the import at the top of this file): ONE statement, ONE place, and the two lanes cannot drift.
#: PREPRINT / WORKING-PAPER STAMPS — a DATA-DRIVEN REGISTRY, not a wall of ifs. Each row is
#: (repository/series key, header-regex fragment). ADDING A NEW REPOSITORY IS A ONE-LINE DATA EDIT.
#:
#: A stamp in a document's OWN header is evidence the manifestation is a WORKING-PAPER / PREPRINT
#: EXPRESSION — NOT the journal version of record. Peer review CHANGES NUMBERS (Acemoglu & Restrepo's
#: robot effect: 0.37pp in the NBER working paper, 0.2pp in the published JPE), so under a journal-only
#: policy a stamped manifestation is a DISCOVERY LEAD, never journal evidence (derive_semantic_binding
#: -> VERSION_PREPRINT -> derive_eligibility -> DISCOVERY_LEAD).
#:
#: WHY THE LIST GREW: the census caught the reducer scoring a GLO Discussion Paper and an arXiv preprint
#: AS JOURNAL FULLTEXT — the P0 crawling back through a gap. The old pattern knew nber|iza|arxiv but NOT
#: the working-paper vocabulary below, so an EconStor working paper (Gray 2013) passed as the journal
#: article. Whenever a new repository stamps its cover page, ADD A ROW HERE — do not touch a reducer.
PREPRINT_STAMP_REGISTRY: list[tuple[str, str]] = [
    #  registry key           header pattern (case-insensitive; matched as a fragment)
    ('nber',              r'nber working paper|national bureau of economic research'),
    ('iza',               r'iza\s+(?:dp|discussion paper)'),
    ('glo',               r'glo discussion paper'),
    ('cepr',              r'cepr discussion paper'),
    ('ssrn',              r'\bssrn\b'),
    ('repec',             r'\brepec\b'),
    ('mpra',              r'\bmpra\b'),
    ('munich_repec',      r'munich personal repec'),
    ('econstor',          r'\beconstor\b'),
    ('documento_trabajo', r'documento de trabajo'),
    ('cahier_recherche',  r'cahier de recherche'),
    ('discussion_paper',  r'discussion paper no'),
    ('working_paper',     r'working paper'),
    ('arxiv',             r'arxiv:\s*\d'),
    ('preprint',          r'\bpreprint\b'),
    ('this_version',      r'this\s+(?:draft|version):'),
    ('preliminary',       r'preliminary(?: and incomplete)?|do not (?:cite|quote) without'),
]

#: The registry compiled to ONE alternation. Named groups let a self-test report WHICH stamp fired
#: (see preprint_stamp_key). observe_text scans the HEADER ONLY: every economics paper CITES NBER
#: working papers in its REFERENCES, and a whole-text scan reads the bibliography, not the paper —
#: which is exactly how a naive scan once called the actual JEP article a working paper.
_PREPRINT_STAMP = re.compile(
    '|'.join(f'(?P<{key}>{pat})' for key, pat in PREPRINT_STAMP_REGISTRY), re.I)


def preprint_stamp_key(text: str) -> str | None:
    """The registry key of the FIRST preprint/working-paper stamp in `text`, or None.

    A pure OBSERVATION helper — it CONCLUDES NOTHING. derive_semantic_binding() decides what a stamp
    MEANS (a DIFFERENT SOURCE until version equivalence is proven); this only reports which one is
    present, for provenance and for the self-test that proves the registry covers each repository.
    """
    m = _PREPRINT_STAMP.search(text)
    return m.lastgroup if m else None


#: A REPOSITORY COVER SHEET IS NOT THE ARTICLE'S FRONT MATTER (Sol V9 §5).
#:
#: An institutional repository staples its own page onto the front of the PDF: "This is a repository copy
#: of…", the handle, the licence, and — fatally — A FULL CITATION OF THE ARTICLE, DOI AND ALL. So the
#: first thing a front-matter DOI extractor sees is a DOI printed by the LIBRARY, not by the publisher,
#: and it is printed identically whether the file underneath is the VoR, the accepted manuscript, or
#: (this has happened) a DIFFERENT PAPER filed under the wrong handle. A cover sheet proves what a
#: repository BELIEVES it deposited. The article's own front matter proves what it IS.
#:
#: So the cover sheet is SEGMENTED OFF and the article's front matter is read after it. The cover sheet
#: is not discarded — it is a real observation, kept under `cover_sheet_text` — it is just not allowed
#: to be the article's own testimony about itself.
#: (the pattern itself now lives in provenance._COVER_SHEET and is imported at the top of this file —
#:  see the note there. It is the SAME cover sheet in both lanes, so it is described in ONE place.)

_DOI_RE = re.compile(r'\b10\.\d{4,9}/[^\s"\'<>,;)\]]+', re.I)

#: IS THERE A BYLINE AT ALL? Sol V9 §5 lets DIFFERENT_WORK be reached by "an incompatible foreign title
#: PLUS A DISJOINT BYLINE" — and BOTH halves are load-bearing. A byline that is ABSENT is not a byline
#: that is disjoint, and the difference is the whole of this project's disease.
#:
#: This was not academic. My first cut of the rule read "no requested author appears in the front matter"
#: as disjointness, and the router's own demo convicted it INSIDE A MINUTE: the cookie-banner fixture —
#: "This website uses cookies. Sign in to continue." — came out DIFFERENT_WORK. A landing page names no
#: author because IT IS NOT A DOCUMENT, and reading that silence as "somebody else's paper" would have
#: quarantined it under a claim about authorship that nothing supported. It is a landing page. Say that.
#:
#: So a byline must be POSITIVELY OBSERVED: an explicit authorship cue, or two full names conjoined. When
#: this is False the reducer may not use disjointness for anything, in either direction.
#: An explicit authorship CUE. Case-insensitive: "By Yang-Hui He", "AUTHORS:", "Author —".
_BYLINE_CUE = re.compile(r'\bby\s+[A-Z]|\bauthors?\s*[:—-]', re.I)
#: ...or a conjoined pair of full names. CASE-SENSITIVE ON PURPOSE — names are capitalised, and folding
#: case here would match "the paper and the data", which is not a byline.
_BYLINE = re.compile(r'[A-Z][a-z]+\s+[A-Z][\w.-]+\s*(?:,|\band\b)\s*[A-Z][a-z]+\s+[A-Z][\w.-]+')


def segment_front_matter(text: str, header_chars: int = 1500) -> tuple[str, str]:
    """-> (cover_sheet_text, article_front_matter). Sol V9 §5: "Repository cover sheets are SEGMENTED
    from article front matter."

    The boundary is taken at the first form-feed after the last cover-sheet marker (a PDF page break —
    the cover sheet IS a separate page, which is the one structural thing that is reliably true of it),
    and failing that at the end of the marker block. If no cover-sheet marker is present, the cover sheet
    is empty and the article's front matter is simply the header — which is the common case and must
    stay cheap.
    """
    head = text[:header_chars * 4]           # look further than the header: a cover sheet displaces it
    hits = list(_COVER_SHEET.finditer(head))
    if not hits:
        return '', text[:header_chars]
    end = hits[-1].end()
    ff = text.find('\x0c', end)
    boundary = ff + 1 if 0 <= ff < len(head) else end
    return text[:boundary], text[boundary:boundary + header_chars]


def observe_text(text: str, header_chars: int = 1500) -> dict:
    """Everything the ledger needs to know about a blob of retrieved text — and NOT ONE CONCLUSION.

    Note `header_chars`: a preprint stamp is only evidence of what a document IS when it appears in
    the document's OWN header. Every economics paper cites NBER working papers in its REFERENCES —
    scanning the whole text for "NBER Working Paper" identifies the bibliography, not the paper.
    (That naive scan called the actual Journal of Economic Perspectives article a working paper.)
    """
    words = text.split()
    header = text[:header_chars]
    # THE ARTICLE'S OWN FRONT MATTER, with any repository cover sheet segmented off it. The DOIs found
    # HERE are the document's own claim about which article it is — as distinct from the DOI a library
    # printed on a cover page, which is the library's claim about what it filed.
    cover, article_front = segment_front_matter(text, header_chars)
    front_dois = sorted({d.rstrip('.').lower() for d in _DOI_RE.findall(article_front)})
    cid_tokens = sum(1 for t in words if 'cid:' in t)
    stripped = _CID.sub('', text)
    real_words = len(re.findall(r'[A-Za-z]{3,}', stripped))
    # How much REAL text is in the header? A title page of pure (cid:NN) glyph codes decodes to
    # nothing — and a header we cannot READ is a header we cannot CHECK AN IDENTITY AGAINST. It is
    # not a stranger's paper. It is an unreadable one, and those are different facts.
    header_real = len(re.findall(r'[A-Za-z]{3,}', _CID.sub('', header)))
    return {
        'word_count': len(words),
        'char_count': len(text),
        'readable_word_count': real_words,
        'glyph_garbage_ratio': round(cid_tokens / max(1, len(words)), 4),
        'chrome_markers': len(_CHROME.findall(text)),
        # ---- VERSION FURNITURE, READ IN THE RIGHT VOICE ----------------------------------------
        # A stamp means something different depending on WHO PRINTED IT. The article's own front
        # matter is the DOCUMENT'S TESTIMONY ABOUT ITSELF; the cover sheet is THE LIBRARY'S OPINION OF
        # WHAT IT FILED. These were previously read from the same undifferentiated `header` slice, so a
        # library's "citation for the published version" was scored as the article calling itself the
        # version of record. They are separated now, and `derive_semantic_binding` weighs them by voice.
        'has_cover_sheet': bool(cover),
        'published_stamp_in_header': bool(_PUBLISHED_STAMP.search(article_front)),
        'published_stamp_in_cover': bool(_PUBLISHED_STAMP.search(cover)),
        'accepted_stamp_in_header': bool(_ACCEPTED_STAMP.search(article_front)),
        'accepted_stamp_in_cover': bool(_ACCEPTED_STAMP.search(cover)),
        'preprint_stamp_in_header': bool(_PREPRINT_STAMP.search(article_front)),
        'preprint_stamp_in_cover': bool(_PREPRINT_STAMP.search(cover)),
        'preprint_stamp_anywhere': bool(_PREPRINT_STAMP.search(text)),
        'header_real_words': header_real,
        # the window identity is checked in. BOUNDED ON PURPOSE: searching the WHOLE document for an
        # author name matches the REFERENCES — every requested author is "present" somewhere in every
        # paper. (A mathematician named Parry is cited in the maths paper we misfiled under Parry
        # et al. A whole-text search "confirmed" the wrong paper.)
        'identity_window': header,
        'header_text': header[:400],
        # ---- SOL V9 §5: IDENTITY FROM THE FETCHED CONTENT ITSELF -------------------------------
        # The DOI the ARTICLE prints on itself (JATS article-DOI, PDF front matter, HTML header) — with
        # any repository COVER SHEET segmented off, because a cover sheet's DOI is the library's opinion
        # of what it deposited, not the document's testimony about what it is.
        'front_matter_dois': front_dois,
        'cover_sheet_chars': len(cover),
        'cover_sheet_text': cover[:400],
        'article_front_matter': article_front[:400],
        # A BYLINE IS PRESENT — or it is not. `False` means the reducer may not reason about
        # disjointness AT ALL: an absent byline is not a disjoint one. (A cookie banner names no author
        # because it is not a document, not because a stranger wrote it.)
        'byline_present': bool(_BYLINE_CUE.search(article_front) or _BYLINE.search(article_front)),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# REDUCERS — the ONLY place a label may come into existence.
# ══════════════════════════════════════════════════════════════════════════════════════════════

# ---- 1. backend outcome ----------------------------------------------------------------------

RESPONDED            = 'RESPONDED'                    # the backend answered with content
NOT_INDEXED          = 'NOT_INDEXED_BY_THIS_BACKEND'  # 404 — a fact about THEIR INDEX, not the world
BACKEND_FAILED       = 'BACKEND_FAILED'               # 429/503/timeout — a fact about OUR REQUEST
ACCESS_BLOCKED       = 'ACCESS_BLOCKED'               # 401/403/paywall — a fact about ENTITLEMENT
NO_OUTCOME           = 'NO_OUTCOME'                   # attempted, never came back. A HANG, not a gap.


#: The four kinds that constitute A REQUEST. CANDIDATE_IDENTIFIED and MANIFESTATION_FETCHED also carry
#: an `adapter` (for provenance — WHICH backend found this), but they are not request outcomes and must
#: not be read as one.
_REQUEST_KINDS = (EventKind.BACKEND_ATTEMPTED, EventKind.RESPONSE_RECEIVED,
                  EventKind.THROTTLED, EventKind.BLOCKED)

#: Worst-first. An adapter that hung on one request and answered another has NOT answered: we asked it
#: something and never found out. Between RESPONDED and NOT_INDEXED, RESPONDED wins — a backend that
#: answered "not in my index" for one query and returned a paper for another IS WORKING.
_OUTCOME_PRECEDENCE = (NO_OUTCOME, BACKEND_FAILED, ACCESS_BLOCKED, RESPONDED, NOT_INDEXED)


def _outcome_of_request(evs: list[Event]) -> str:
    """The outcome of ONE logical request, read from its FINAL terminal event.

    A retry loop emits BACKEND_ATTEMPTED + one terminal event PER ATTEMPT, all sharing a `request_id`.
    So a request reads:  ATTEMPTED, THROTTLED, ATTEMPTED, THROTTLED, ATTEMPTED, RESPONSE_RECEIVED(200)

    The 429s ARE NOT DELETED — they are on disk forever, and `Ledger` has no operation that could
    remove them. But a throttle the backoff RESOLVED and a throttle we GAVE UP ON are different facts
    about the world, and only the second one means we never got the answer. Reading "any 429 anywhere"
    as BACKEND_FAILED would mark every route degraded the moment a single retry succeeded, and a route
    that is always degraded can never license a scoped absence — which sounds conservative and is
    actually just as blind as always calling it complete.

        exhausted retries -> final terminal event is THROTTLED         -> BACKEND_FAILED. FOREVER.
        429 then 200      -> final terminal event is RESPONSE_RECEIVED -> RESPONDED.
    """
    terminal = [e for e in evs if e.kind in (EventKind.RESPONSE_RECEIVED, EventKind.THROTTLED,
                                             EventKind.BLOCKED)]
    if not terminal:
        return NO_OUTCOME               # attempted and never came back. A HANG, not a gap.
    e = terminal[-1]
    if e.kind == EventKind.THROTTLED:
        return BACKEND_FAILED
    if e.kind == EventKind.BLOCKED:
        return ACCESS_BLOCKED
    code = e.payload.get('http_status')
    if code in (429, 503):
        return BACKEND_FAILED           # even if someone logged it as a "response"
    if code in (401, 403):
        return ACCESS_BLOCKED
    if code == 404:
        return NOT_INDEXED
    if e.payload.get('transport_error'):
        return BACKEND_FAILED           # timeout / DNS / reset / bad JSON / 5xx
    return RESPONDED


# ---- 1b. ROUTE LINEAGE — WHOSE DOCUMENT IS THIS? (Sol V9 §1) ---------------------------------
#
# THE BUG THIS EXISTS TO CLOSE: a route could be credited with a document some OTHER route fetched.
#
# The chain is:  resolver request -> candidate -> content request -> redirects -> manifestation
# and `candidate_id` is the thread that runs through all of it. A MANIFESTATION_FETCHED event carries the
# CONTENT HOST in `adapter` (`content:arxiv.org`) — never the resolver that proposed the URL — so
# "which adapter found this document?" is NOT answerable from the manifestation alone. It is answerable
# only by walking back to the CANDIDATE_IDENTIFIED event that minted the candidate_id, whose `adapter`
# IS the resolver.
#
# Reducing over "all manifestations of the unit", as the discovery reducer did, answers a different
# question — "did ANYBODY get a document for this work?" — and reports it once per route. Every route
# then inherits every other route's success, unique incremental yield is identically equal to gross
# yield, and the ladder Sol asks for in §9 measures nothing at all.


def candidates_of_adapter(events: list[Event], adapter: str) -> set[str]:
    """The candidate_ids THIS ADAPTER PROPOSED. The lineage root — an adapter owns what it discovered."""
    return {str(e.payload['candidate_id']) for e in _observations(events)
            if e.kind == EventKind.CANDIDATE_IDENTIFIED
            and e.payload.get('adapter') == adapter
            and e.payload.get('candidate_id')}


def manifestations_of_adapter(events: list[Event], adapter: str) -> list[Event]:
    """The MANIFESTATION_FETCHED events that descend from a candidate `adapter` proposed.

    Also includes manifestations whose OWN adapter is `adapter` — a content host IS a route (if nber.org
    403s us we were blocked BY NBER), and when a fetcher pulls a URL with no candidate lineage the
    content host is the only route there is.

    A manifestation with NO candidate_id and a different adapter belongs to NOBODY, and is therefore
    credited to nobody. That is the safe default and the honest one: we do not know which route earned
    it, and inventing an answer is the failure this reducer exists to end.
    """
    mine = candidates_of_adapter(events, adapter)
    out = []
    for e in _observations(events):
        if e.kind != EventKind.MANIFESTATION_FETCHED:
            continue
        cid = str(e.payload.get('candidate_id') or '')
        if (cid and cid in mine) or e.payload.get('adapter') == adapter:
            out.append(e)
    return out


def events_of_adapter_lineage(events: list[Event], adapter: str) -> list[Event]:
    """This unit's events with EVERY OTHER ROUTE'S DOCUMENTS REMOVED — and their profiles with them.

    This is what lets the existing content reducers (`derive_content_profile`, `derive_semantic_binding`)
    answer "what did THIS ROUTE get?" without any of them learning a second vocabulary. They still reduce
    over an event list; the list is just no longer somebody else's.

    MANIFESTATION_FETCHED and its CONTENT_PROFILE_DERIVED are emitted ADJACENTLY and are paired by
    adjacency downstream (`_holdings`), so a foreign manifestation must take its profile out with it.
    Dropping the manifestation alone would leave an orphan profile that pairs with the NEXT
    manifestation — one route's bytes wearing another route's word count, which is the same class of bug
    one layer down.
    """
    keep = {id(e) for e in manifestations_of_adapter(events, adapter)}
    out: list[Event] = []
    drop_profile = False
    for e in events:
        if e.kind == EventKind.MANIFESTATION_FETCHED and 'derived_by' not in e.payload:
            drop_profile = id(e) not in keep
            if not drop_profile:
                out.append(e)
            continue
        if e.kind == EventKind.CONTENT_PROFILE_DERIVED and drop_profile:
            drop_profile = False
            continue
        drop_profile = False
        out.append(e)
    return out


def derive_backend_outcome(events: list[Event], adapter: str) -> str:
    """What actually happened to one adapter. `None` is not an answer — it is four different worlds.

    An adapter may be asked more than once (four candidate PDFs from one content host; a DOI lookup and
    a title search). Each logical request is scored on its own; the adapter reports its WORST.
    """
    mine = [e for e in _observations(events)
            if e.payload.get('adapter') == adapter and e.kind in _REQUEST_KINDS]
    if not mine:
        return NO_OUTCOME

    # Events carrying no `request_id` are a HISTORY WRITTEN BEFORE RETRIES EXISTED (our replay, the
    # hand-written invariants, any older log). They are one bucket, scored by the original rule: ANY
    # throttle anywhere condemns the adapter. Back-compat is not politeness here — a reducer that
    # changed its answer about a log it had already reduced would make the whole record unreadable.
    buckets: dict[str, list[Event]] = {}
    for e in mine:
        buckets.setdefault(str(e.payload.get('request_id') or ''), []).append(e)

    outcomes: list[str] = []
    for rid, evs in buckets.items():
        if rid == '':
            if any(e.kind == EventKind.THROTTLED for e in evs):
                outcomes.append(BACKEND_FAILED)
            elif any(e.kind == EventKind.BLOCKED for e in evs):
                outcomes.append(ACCESS_BLOCKED)
            else:
                first = [e for e in evs if e.kind == EventKind.RESPONSE_RECEIVED][:1]
                outcomes.append(_outcome_of_request(first) if first else NO_OUTCOME)
        else:
            outcomes.append(_outcome_of_request(evs))

    for o in _OUTCOME_PRECEDENCE:
        if o in outcomes:
            return o
    return NO_OUTCOME


# ---- 2. route status -------------------------------------------------------------------------

@dataclass(frozen=True)
class RouteStatus:
    state: str                     # UNROUTED | INCOMPLETE | COMPLETE_DEGRADED | COMPLETE
    planned: tuple[str, ...]
    outcomes: dict[str, str]
    missing: tuple[str, ...]       # planned adapters with NO terminal outcome
    failed: tuple[str, ...]        # adapters that were throttled/blocked/errored
    budget_stopped: bool

    @property
    def supports_absence(self) -> bool:
        """THE question. Only an ADEQUATE route licenses "we looked, and it is not there."

        Every planned adapter must have genuinely ANSWERED. One 429, one hang, or a budget stop and
        the honest label is SEARCH_FAILED — we do not know, and we may not say we do.
        """
        return (self.state == 'COMPLETE'
                and not self.missing and not self.failed and not self.budget_stopped
                and bool(self.planned))


def derive_route_status(events: list[Event]) -> RouteStatus:
    """route_complete means EVERY PLANNED ADAPTER HAS A TERMINAL OUTCOME RECORD.

    It NEVER means "an adapter was mapped".
    """
    events = _observations(events)
    planned: list[str] = []
    for e in events:
        if e.kind == EventKind.ROUTE_PLANNED:
            planned += [a for a in e.payload.get('adapters', []) if a not in planned]
    if not planned:
        return RouteStatus('UNROUTED', (), {}, (), (), False)

    budget = any(e.kind == EventKind.BUDGET_STOPPED for e in events)
    outcomes = {a: derive_backend_outcome(events, a) for a in planned}
    missing = tuple(a for a, o in outcomes.items() if o == NO_OUTCOME)

    # ── A BLOCKED RETRIEVAL IS A FAILED ROUTE. ───────────────────────────────────────────────────
    # The SEARCH adapters are the ones in ROUTE_PLANNED. But finding the document's address is not
    # holding the document: after a search answers, we go to the CONTENT HOST for the bytes, and that
    # host is a backend too — it can throttle us, and it can shut the door in our face.
    #
    # This was live, and it was the whole disease wearing a new coat. Autor (2015), JEP:
    #
    #     crossref                RESPONDED        (the metadata)
    #     unpaywall               RESPONDED        (...and here is where the PDF lives)
    #     content:www.aeaweb.org  ACCESS_BLOCKED   HTTP 403
    #
    # and because the content host was not a PLANNED adapter, the route read COMPLETE, `supports_
    # absence` read TRUE, and coverage reduced to SEARCHED_NONE — "a SCOPED ABSENCE, and the only
    # state that licenses one". A 403 FROM THE PUBLISHER had become a statement that the literature
    # is silent. That is a fact about ENTITLEMENT, printed as a fact about the world: the identical
    # error to reading a 429 as "no free copy exists", committed one layer down, by the cure.
    #
    # So EVERY adapter that failed counts against the route — planned or not. We do not get to say we
    # looked and found nothing when we were shown the door.
    all_adapters = {e.payload.get('adapter') for e in events
                    if e.kind in _REQUEST_KINDS and e.payload.get('adapter')}
    for a in sorted(all_adapters - set(planned)):
        o = derive_backend_outcome(events, a)
        if o in (BACKEND_FAILED, ACCESS_BLOCKED):
            outcomes[a] = o
    failed = tuple(a for a, o in outcomes.items() if o in (BACKEND_FAILED, ACCESS_BLOCKED))

    if missing:
        state = 'INCOMPLETE'
    elif failed or budget:
        state = 'COMPLETE_DEGRADED'     # every adapter has a record — but the search DID NOT WORK
    else:
        state = 'COMPLETE'
    return RouteStatus(state, tuple(planned), outcomes, missing, failed, budget)


# ---- 3. content profile — DRIVEN BY THE ONE REGISTRY, NOT BY A NUMBER ------------------------
#
# THERE WAS A `FULLTEXT_MIN = 2500` HERE. It is deleted, and this comment is its headstone.
#
# It was written in the fix for the bug it is. `provenance.py`'s own header says, in Sol's words: "A
# universal word threshold cannot define 'full text': a short judicial opinion, statute section,
# trial-registry record, and journal article have different completeness profiles" — and then this
# module, the CURE, reinstated one universal number two files away, where nothing compared them. It
# did not merely contradict the principle; it contradicted `provenance.profile()`, whose scholarly
# floor is 1,200. TWO REDUCERS THAT DISAGREE ARE NOT A SHARED RULE. Which document a card could cite
# depended on which module happened to look at it last.
#
# So completeness is not decided here at all. It is READ FROM THE REGISTRY, by the ONE reducer:
#
#     provenance.KIND_PROFILE      what each artifact kind is, and its stub floor (or None)
#     provenance.judge_completeness(kind, n_words, extraction_verdict)
#
# A judicial opinion, a statute section and a trial-registry record have stub_floor=None and are
# COMPLETE AT ANY LENGTH. A cookie banner is incomplete at any length. Neither fact is a word count.

C_FULLTEXT     = 'FULLTEXT'
C_ABSTRACT     = 'ABSTRACT'
C_CITATION     = 'CITATION_ONLY'
C_NOT_DOC      = 'NOT_A_DOCUMENT'        # a cookie banner, a login wall, a paywall interstitial
C_UNREADABLE   = 'UNREADABLE_ENCODING'   # a PDF whose glyphs never decoded

GLYPH_GARBAGE_MAX = 0.10   # > this share of (cid:NN) tokens => the font never decoded
CHROME_PER_1K_MAX = 5.0    # web furniture DENSITY. Density, not length — see below.

#: THE LEGACY THREE-WAY VOCABULARY. `cellcog_composer` and `evidence_miner` both select their usable
#: corpus with `content_status != 'CITATION_ONLY'`, so the coarse label they contract on is a
#: PROJECTION of the five-way derived class — computed in ONE place, here, and never by a word count.
#:
#: NOTE THE DIRECTION OF THE PROJECTION. NOT_A_DOCUMENT and UNREADABLE_ENCODING collapse to
#: CITATION_ONLY — that is, TO UNUSABLE. It is tempting to send them to ABSTRACT_ONLY (they have
#: hundreds of words, after all, and a word-count rule sends them there automatically — which is what
#: `corpus_truth.FULLTEXT_MIN=2500` did). That would make a COOKIE BANNER MINABLE. The 535-word aeaweb
#: banner and the 548-word ORA landing page would both have passed `!= 'CITATION_ONLY'` and been mined
#: as the paper's own summary. Every collapse in this table must fail SAFE, and the safe direction for
#: bytes that are not a document is: not evidence.
LEGACY_STATUS = {
    C_FULLTEXT:   'FULLTEXT',
    C_ABSTRACT:   'ABSTRACT_ONLY',
    C_CITATION:   'CITATION_ONLY',
    C_NOT_DOC:    'CITATION_ONLY',      # a cookie banner is NOT an abstract of the paper
    C_UNREADABLE: 'CITATION_ONLY',      # a PDF whose font never decoded is not a summary of anything
}

#: The content class each artifact kind reports as. The finding-bearing kinds are absent on purpose:
#: for those, THE REGISTRY decides (complete => FULLTEXT), and hardcoding them here would be a second
#: opinion about completeness, which is the whole defect.
_CLASS_OF_KIND = {
    'extraction_failure': C_UNREADABLE,
    'landing_page':       C_NOT_DOC,
    'wrong_work':         C_NOT_DOC,
    'abstract':           C_ABSTRACT,
    'citation_only':      C_CITATION,
    'unknown':            C_CITATION,
}


def derive_artifact_kind(prof: dict, source_type: str = '') -> tuple[str, str]:
    """WHAT KIND OF DOCUMENT IS THIS? Registry-driven, from OBSERVATIONS only.

    `source_type` is the kind of RECORD the unit came from — a Crossref `journal-article`, a court's
    opinions endpoint, ClinicalTrials.gov. It selects WHICH COMPLETENESS PROFILE APPLIES and nothing
    else, and it is REBUTTABLE BY THE BYTES: the demotions below run first, so a login wall served by
    a court's website is a login wall.

    It is NOT `fulltext_source` wearing a new hat. `fulltext_source='working_paper'` was a claim about
    WHAT THE DOCUMENT IS, written by whichever script ran, believed by everyone, and false in both
    directions. `source_type` cannot promote anything: it cannot make a cookie banner an article, and
    it cannot make a working paper a journal version — the header stamp decides that, in
    derive_semantic_binding(), untouched. All it can do is stop us judging a judicial opinion by a
    journal article's word count.
    """
    wc = prof.get('word_count', 0)
    readable = prof.get('readable_word_count', 0)
    chrome = prof.get('chrome_markers', 0)
    glyph = prof.get('glyph_garbage_ratio', 0)

    # Which profile do we judge this against? Default: the scholarly one (every row in this corpus is
    # a Crossref journal-article). An UNREGISTERED type is not silently accepted — it falls back to
    # scholarly and SAYS SO, because a kind nobody registered has no completeness profile to use.
    work_kind, _claimed = _SOURCE_TYPE.get((source_type or '').strip().lower(), ('study', ''))
    declared = _WORK_KIND_ARTIFACT.get(work_kind) or 'journal_article'
    spec = KIND_PROFILE[declared]
    floor = spec['stub_floor']
    src = f'source_type={source_type!r}' if source_type else 'no source_type declared (scholarly default)'

    if wc <= 0:
        return 'citation_only', 'we hold no bytes at all'
    if glyph > GLYPH_GARBAGE_MAX:
        return 'extraction_failure', (f'{glyph:.0%} of tokens are (cid:NN) glyph codes — the font '
                                      f'never decoded')
    # A cookie banner is not a short paper. It is NOT A PAPER — and that is true of a 300-word statute
    # section's landing page too, which is why the LENGTH half of this test applies only where there
    # IS a length below which a document is a fragment. Where there is not (stub_floor=None), only
    # web-furniture DENSITY may condemn it.
    chrome_per_kw = 1000.0 * chrome / max(1, wc)
    if chrome and (chrome_per_kw >= CHROME_PER_1K_MAX or (floor is not None and wc < floor)):
        return 'landing_page', (f'{chrome} site-chrome marker(s) in {wc}w ({chrome_per_kw:.0f}/1k) — '
                                f'this is a web page about the document, not the document')
    if floor is not None and readable < floor:
        # A SCHOLARLY FRAGMENT. Which fragment it is, is the registry's abstract_floor — not a second
        # universal number invented here.
        af = spec['abstract_floor']
        if af is not None and readable < af:
            return 'citation_only', f'{readable:,} readable words — a citation stub, not even an abstract'
        return 'abstract', (f'{readable:,} readable words is below the stub floor for `{declared}` '
                            f'({floor:,}) — a fragment of the article, not the article')
    return declared, f'{readable:,} readable words; judged as `{declared}` ({src})'


def _source_type_of(events: list[Event]) -> str:
    """The record type OBSERVED for this unit. An observation about what we asked for, with a basis."""
    for e in reversed(_observations(events)):
        st = e.payload.get('source_type')
        if st:
            return str(st)
    return ''


#: WHICH DOCUMENT WE HOLD IS BETTER. Used ONLY to pick which of several manifestations a unit-level
#: question is about — never to decide what any one of them IS.
_CLASS_RANK = {C_FULLTEXT: 4, C_ABSTRACT: 3, C_CITATION: 2, C_NOT_DOC: 1, C_UNREADABLE: 1}


def _holdings(events: list[Event]) -> list[tuple[dict, dict]]:
    """Every (manifestation, ITS OWN profile) PAIR this unit holds, in order.

    `record_manifestation()` emits MANIFESTATION_FETCHED and CONTENT_PROFILE_DERIVED adjacently, so a
    pair is a document and the profile OF THAT DOCUMENT. Pairing matters: without it, a unit holding a
    body and an abstract would answer identity questions from one and completeness questions from the
    other, and the answer would describe no document that exists.
    """
    pairs: list[tuple[dict, dict]] = []
    pending: dict | None = None
    for e in _observations(events):
        if e.kind == EventKind.MANIFESTATION_FETCHED:
            pending = e.payload
        elif e.kind == EventKind.CONTENT_PROFILE_DERIVED:
            pairs.append((pending or {}, e.payload))
            pending = None
    return pairs


def _classify(prof: dict, source_type: str) -> tuple[str, dict]:
    """ONE document's bytes -> its content class. The whole of the completeness rule, for one blob."""
    kind, basis = derive_artifact_kind(prof, source_type)
    readable = prof.get('readable_word_count', 0) or prof.get('word_count', 0)
    verdict = 'CORRUPT' if prof.get('glyph_garbage_ratio', 0) > GLYPH_GARBAGE_MAX else 'CLEAN'
    # THE ONE REDUCER. Not a number in this file.
    complete, reasons = judge_completeness(kind, readable, verdict)
    cls = _CLASS_OF_KIND.get(kind)
    if cls is None:                       # a finding-bearing kind: THE REGISTRY says if it is whole
        cls = C_FULLTEXT if complete else C_ABSTRACT
    info = {'reason': basis if complete else '; '.join(reasons) or basis,
            'artifact_kind': kind, 'complete': complete, **prof}
    return cls, info


def _best_holding(events: list[Event]) -> tuple[dict, dict, str, dict] | None:
    """THE BEST DOCUMENT WE HOLD for this unit -> (manifestation, profile, class, info).

    IT USED TO TAKE THE LAST ONE PROFILED, AND THAT WAS A LIVE DEFECT — introduced, of course, in the
    fix for the defect it is. Once acquisition began retaining EVERY set of bytes instead of deleting
    all but one, a work commonly held two: the fetched body AND the bibliography's abstract. The
    abstract was ingested second, so `for e in events: prof = e.payload` ended holding the ABSTRACT'S
    profile — and the unit's label was derived from it.

    Result, on the real corpus, before this was fixed:

        Damioli (2021)   label = CITATION_ONLY    while the row carried 13,085 words
        Tolan (2021)     label = ABSTRACT         while the row carried 18,225 words

    A label that asserts less than its content supports is the same disease as one that asserts more:
    it is a claim about a document nobody is holding. Five rows had it, and every one of them would
    have been skipped by the miner.

    So the question "what do we hold for this work?" is answered by THE BEST DOCUMENT WE HOLD. A cookie
    banner sitting beside a journal article does not make the article an abstract; we hold the article.
    """
    pairs = _holdings(events)
    if not pairs:
        return None
    st = _source_type_of(events)
    scored = []
    for manif, prof in pairs:
        cls, info = _classify(prof, st)
        scored.append((_CLASS_RANK.get(cls, 0), prof.get('readable_word_count', 0) or 0,
                       manif, prof, cls, info))
    best = max(scored, key=lambda x: (x[0], x[1]))
    return best[2], best[3], best[4], best[5]


def derive_content_profile(events: list[Event]) -> tuple[str, dict]:
    """FULLTEXT IS EARNED — AGAINST THE PROFILE FOR ITS KIND. It is never a thing a fetcher declares,
    and it is never a number this module keeps to itself."""
    best = _best_holding(events)
    if best is None:
        return C_CITATION, {'reason': 'no content was ever profiled'}
    _manif, _prof, cls, info = best
    n = len(_holdings(events))
    if n > 1:
        info = {**info, 'n_documents_held': n,
                'reason': f'{info["reason"]} (the best of {n} documents held for this work)'}
    return cls, info


# ---- 4. semantic binding ---------------------------------------------------------------------

SAME_WORK        = 'SAME_WORK'              # this IS the journal article
VERSION_PUBLISHED = 'VERSION_OF_PUBLISHED'  # a repository copy OF the published version
VERSION_ACCEPTED = 'VERSION_OF_ACCEPTED'    # an ACCEPTED MANUSCRIPT. Peer review is not the last edit.
VERSION_PREPRINT = 'VERSION_OF_PREPRINT'    # a working paper. A DIFFERENT SOURCE until proven equal.
DIFFERENT_WORK   = 'DIFFERENT_WORK'         # we fetched somebody else's paper
UNRESOLVED       = 'UNRESOLVED_BINDING'


#: ══ WHICH EXPRESSION DO THESE BYTES TESTIFY TO BEING? ════════════════════════════════════════════
#:
#: THE ORDER OF THIS TUPLE IS THE RULE, AND IT IS A STATEMENT — not an accident of where an `if` landed
#: in a ladder. The INADMISSIBLE kinds are asked FIRST, on purpose, because the commonest shape in an
#: institutional repository carries BOTH kinds of stamp at once:
#:
#:     "This is an author produced version of a paper published in <journal>.     <- ACCEPTED
#:      Citation for the published version: ..."                                  <- PUBLISHED
#:
#: The old reducer asked `published_stamp_in_header` first and answered VERSION_PUBLISHED. Reading the
#: SECOND line and ignoring the FIRST is how an accepted manuscript became journal evidence. Whichever
#: way a future edit reorders the code, the precedence lives HERE, in data, and `derive_eligibility`
#: re-checks the result against a veto that does not consult this order at all.
#:
#: (`*_in_cover` is the LIBRARY's voice, `*_in_header` the DOCUMENT's own. For the two inadmissible
#: kinds EITHER voice convicts — a repository saying "this is the author's manuscript" is describing
#: the file it filed. For PUBLISHED, either voice may acquit, but only because nothing above it fired.)
VERSION_EVIDENCE: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (VERSION_ACCEPTED,  ('accepted_stamp_in_cover', 'accepted_stamp_in_header'),
     'the bytes (or the repository that filed them) declare this an ACCEPTED MANUSCRIPT — acceptance '
     'precedes copy-editing, proofs and the editor\'s last round, and THE NUMBERS MOVE ACROSS THEM'),
    (VERSION_PREPRINT,  ('preprint_stamp_in_cover', 'preprint_stamp_in_header'),
     'the header carries a preprint/working-paper stamp — peer review CHANGES NUMBERS; this is a '
     'DIFFERENT SOURCE until version equivalence is proven'),
    (VERSION_PUBLISHED, ('published_stamp_in_cover', 'published_stamp_in_header'),
     'a published-version/refereed stamp, and NO accepted-manuscript or preprint stamp contradicting it'),
)


def version_evidence(prof: dict) -> tuple[str, str]:
    """-> (binding, why). The ONE place a stamp becomes a version. Consulted by nothing else."""
    for binding, fields, why in VERSION_EVIDENCE:
        if any(prof.get(f) for f in fields):
            return binding, why
    return SAME_WORK, 'no version furniture contradicts the identity we confirmed'


def _norm(s: str) -> set[str]:
    stop = {'the', 'a', 'an', 'of', 'and', 'for', 'in', 'on', 'to', 'from', 'with'}
    return {w for w in re.findall(r'[a-z]+', (s or '').lower()) if w not in stop and len(w) > 2}


def derive_semantic_binding(events: list[Event]) -> tuple[str, dict]:
    """Is the text we fetched the work we asked for? A fetcher MAY NOT ANSWER THIS ABOUT ITSELF.

    Sol: "A predecessor working paper and later journal article may be closely related, but they are
    DIFFERENT SOURCES until version equivalence is proven."
    """
    # THE SAME DOCUMENT THE LABEL DESCRIBES. `_best_holding` returns a manifestation TOGETHER WITH ITS
    # OWN profile — so identity is checked against the header of the very bytes whose completeness was
    # judged. Reading "the last manifestation" and "the last profile" independently could pair one
    # document's byline with another document's word count, and answer about a document that does not
    # exist.
    best = _best_holding(events)
    if best is None:
        return UNRESOLVED, {'reason': 'nothing was fetched'}
    fetched, prof, _cls, _info = best

    # The identity window is BOUNDED (see observe_text): a whole-document scan finds every author in
    # the references and "confirms" anything you ask it to.
    window = fetched.get('document_title', '') or prof.get('identity_window', '') \
        or prof.get('header_text', '')
    want_t = _norm(fetched.get('requested_title', ''))
    got_t = _norm(window)
    want_a = {a.lower() for a in fetched.get('requested_authors', [])}
    byline = (fetched.get('byline', '') or window).lower()

    overlap = len(want_t & got_t) / max(1, len(want_t))
    author_hit = any(a in byline for a in want_a if a)
    title_match = overlap >= 0.90
    # A SPECIFIC title (>=4 content words) matching in full is itself strong identity evidence.
    # A GENERIC one is not: {rise, machines} sits entirely inside {mathematics, rise, machines}.
    title_specific = len(want_t) >= 4

    # ── THE DOCUMENT'S OWN DOI (Sol V9 §5) ────────────────────────────────────────────────────
    # Read from the ARTICLE'S front matter, with any repository cover sheet segmented off. This is the
    # ONE identity signal that is both positive and decisive in BOTH directions: an exact front-matter
    # DOI CONFIRMS, and a front matter that prints a DIFFERENT DOI and NOT ours is the positive evidence
    # of a stranger's paper that DIFFERENT_WORK has always needed and never had.
    want_doi = str(fetched.get('requested_doi') or '').strip().lower().rstrip('.')
    front_dois = [str(d).lower().rstrip('.') for d in (prof.get('front_matter_dois') or [])]
    doi_hit = bool(want_doi and want_doi in front_dois)
    foreign_doi = bool(want_doi and front_dois and not doi_hit)
    #: A byline was POSITIVELY OBSERVED. Absence of one is NOT disjointness — see _BYLINE.
    byline_present = bool(prof.get('byline_present'))

    ev = {'title_overlap': round(overlap, 2), 'author_in_byline': author_hit,
          'title_content_words': len(want_t),
          'requested_title': fetched.get('requested_title', '')[:70],
          'front_matter_dois': front_dois[:4], 'doi_in_front_matter': doi_hit,
          'cover_sheet_chars': prof.get('cover_sheet_chars', 0),
          'header_text': (prof.get('header_text') or '')[:120]}

    # ── AN UNREADABLE HEADER IS NOT A STRANGER'S PAPER. ───────────────────────────────────────
    # Autor, Levy & Murnane (2003) arrives as a PDF whose title page is pure (cid:NN) glyph codes:
    # ZERO readable words in the header, though the BODY has 10,902. An earlier version of this
    # reducer read "no title, no author" as DIFFERENT_WORK — turning a FONT-ENCODING FAILURE into a
    # confident claim about whose paper it is. That is this project's whole disease, committed by
    # the cure. We cannot read it, therefore we cannot bind it. Say exactly that.
    if prof.get('header_real_words', 0) < 10:
        return UNRESOLVED, {'reason': f'the header decoded to {prof.get("header_real_words", 0)} '
                                      f'readable words — we CANNOT READ it, so we cannot establish '
                                      f'identity. Not a stranger\'s paper: an unreadable one', **ev}

    # ── DIFFERENT_WORK NEEDS POSITIVE EVIDENCE OF A STRANGER. IT ALWAYS DID. ──────────────────
    # Sol V9 §5 sets the bar exactly: DIFFERENT_WORK requires "a positive foreign DOI, or an
    # incompatible foreign title PLUS a disjoint byline". And, verbatim: "A generic title without an
    # author must NOT produce DIFFERENT_WORK; the current event reducer is TOO AGGRESSIVE here."
    #
    # It was. Two branches below used to return DIFFERENT_WORK on ABSENCE:
    #
    #   1. a generic-title match with no author in the header -> DIFFERENT_WORK ("title collision")
    #   2. an author match with a weak title                  -> DIFFERENT_WORK ("same author, different
    #                                                                             paper")
    #
    # Neither is positive evidence of anyone else's paper. (1) fires on a real article with a two-word
    # title whose PDF header happens not to carry a byline — which describes a large fraction of
    # publisher HTML. (2) fires on the RIGHT paper whose title page decoded badly, and it fires while the
    # BYLINE AGREES WITH US, which is the opposite of a disjoint byline. Both convict on absence, and
    # DIFFERENT_WORK is not a shrug — it is `wrong_work`, a QUARANTINE, and it destroys the document.
    #
    # UNRESOLVED is the honest verdict for both, and it costs us the same evidence while making a claim
    # we can actually support. Absence of our evidence read as evidence of absence is the 429-means-"no
    # free copy exists" error, and it does not become sound by being pointed at a PDF.
    if foreign_doi:
        # POSITIVE. The document PRINTS A DOI ON ITSELF, and it is not ours. (Cover sheet already
        # segmented off — a library's citation of us is not the document identifying itself as us.)
        return DIFFERENT_WORK, {
            'reason': f'the article front matter prints DOI {front_dois[0]!r}, and we asked for '
                      f'{want_doi!r}. The document says whose it is, and it is not ours', **ev}

    # ── IDENTITY IS CONFIRMED BY ITS OWN DOI, AN AUTHOR, OR A SPECIFIC TITLE IN FULL. ─────────
    confirmed = doi_hit or author_hit or (title_match and title_specific)

    if not confirmed:
        # POSITIVE, the second way: A DISJOINT BYLINE. The document SAYS WHO WROTE IT, we know who we
        # asked for, and they are different people — while nothing else (its DOI, its title) puts our
        # work in these bytes. That is testimony from the document, not an inference from silence.
        #
        # BOTH halves are required, and both are checked:
        #   - `byline_present`: an authorship cue was POSITIVELY OBSERVED in the article's own front
        #     matter (cover sheet segmented off). An ABSENT byline is not a disjoint one.
        #   - `want_a`: we actually asked for named authors. If we asked for none, no byline on earth
        #     can be disjoint from them, and claiming otherwise convicts every document we hold.
        #
        # THIS IS THE PARRY / YANG-HUI HE CASE, and it stays quarantined: we asked for Parry, the front
        # matter says "By Yang-Hui He", and the only thing that "matched" was the two-word phrase "rise
        # of the machines". What convicts it is the BYLINE — not the title collision, which convicts
        # nothing.
        if byline_present and want_a and not author_hit:
            return DIFFERENT_WORK, {
                'reason': f'the article front matter carries a byline, and it names NONE of the '
                          f'{len(want_a)} requested author(s). Nothing else identifies these bytes as '
                          f'ours (title overlap {overlap:.0%}, no matching front-matter DOI) — an '
                          f'incompatible work with a DISJOINT BYLINE', **ev}
        if title_match and not title_specific:
            # A TITLE COLLISION, with NO byline to convict on. {rise, machines} sits inside
            # {mathematics, rise, machines}. Sol V9 §5, verbatim: "A generic title without an author must
            # NOT produce DIFFERENT_WORK." This is not knowledge that we hold a stranger's paper. It is
            # knowledge that WE CANNOT TELL — and those are different facts, one of which is true.
            return UNRESOLVED, {
                'reason': f'the requested title has only {len(want_t)} content word(s) and no requested '
                          f'author appears in the front matter. A {overlap:.0%} match on a GENERIC title '
                          f'is a TITLE COLLISION — it establishes NEITHER identity NOR its absence. '
                          f'UNRESOLVED, and therefore not attributable', **ev}
        return UNRESOLVED, {'reason': f'title overlap {overlap:.0%}, no requested author in the '
                                      f'header — identity is NOT established, so this text may not '
                                      f'be attributed to this source', **ev}

    # ...an author alone is not identity either: prolific authors write many papers. But the byline
    # AGREES WITH US, so this is NOT a stranger's paper — it is a paper we cannot pin down. This branch
    # used to return DIFFERENT_WORK ("same author, DIFFERENT PAPER") and it was the second half of Sol's
    # "too aggressive" finding: it convicted while the byline was CONFIRMING us, which is the exact
    # opposite of the disjoint byline the rule requires.
    if author_hit and not doi_hit and not title_match and not title_specific:
        return UNRESOLVED, {'reason': f'a requested author appears in the front matter but the title '
                                      f'matches only {overlap:.0%} — same author, possibly a different '
                                      f'paper. The byline is NOT disjoint, so this is not positive '
                                      f'evidence of a stranger\'s work: it is UNRESOLVED', **ev}

    # IDENTITY IS SETTLED — these bytes ARE the work we asked for. The remaining question is WHICH
    # EXPRESSION of it, and that is decided in ONE place, by a declared precedence (VERSION_EVIDENCE),
    # so that no reordering of this function can promote a manuscript to the version of record.
    binding, why = version_evidence(prof)
    if binding is SAME_WORK:
        return SAME_WORK, {'reason': 'identity confirmed by '
                                     + ('the article\'s OWN front-matter DOI' if doi_hit
                                        else 'author and title' if author_hit and title_match
                                        else 'author in the header' if author_hit
                                        else f'a specific {len(want_t)}-word title matched in full')
                                     + ', and no version furniture contradicting it', **ev}
    return binding, {'reason': f'identity confirmed, but {why}', **ev}


# ---- 5. eligibility --------------------------------------------------------------------------

ADMISSIBLE     = 'ADMISSIBLE'
DISCOVERY_LEAD = 'DISCOVERY_LEAD'     # Sol's word, exactly. Real text — but not attributable HERE.
INADMISSIBLE   = 'INADMISSIBLE'

#: ══ THE VERSION VETO (event lane) ═══════════════════════════════════════════════════════════════
#: WHICH BINDINGS CAN NEVER BE JOURNAL EVIDENCE. A STATEMENT — so that adding a version kind without
#: deciding its admissibility is impossible, and so that no branch can admit one by answering first.
#: (`derive_eligibility` asserts on this AFTER it has chosen, which is the check that does not care
#:  what order anything ran in.)
NEVER_JOURNAL_EVIDENCE: dict[str, str] = {
    VERSION_PREPRINT: ('working-paper text. A DISCOVERY LEAD, not automatically journal-attributable '
                       'evidence — version equivalence is not proven'),
    VERSION_ACCEPTED: ('accepted-manuscript text. Peer review is NOT the last thing that changes a '
                       'number: copy-editing, proofs and the editor\'s final round come after it '
                       '(Acemoglu & Restrepo, 0.37pp in the manuscript -> 0.2pp in the JPE). A '
                       'DISCOVERY LEAD; a span reaches the journal only across a verified per-span '
                       'correspondence into the VoR\'s own bytes'),
}


def derive_eligibility(events: list[Event], journal_articles_only: bool = True) -> tuple[str, dict]:
    """May this text be attributed to THIS source, under THIS task's instruction?

    Task 72 demands JOURNAL ARTICLES ONLY. So citing the working paper BREAKS THE INSTRUCTION, and
    citing the journal with the working paper's text IS FABRICATION. There is no version in which the
    working-paper span ships as journal evidence.
    """
    cls, cinfo = derive_content_profile(events)
    binding, binfo = derive_semantic_binding(events)

    if cls == C_NOT_DOC:
        return INADMISSIBLE, {'reason': f'not a document ({cinfo["reason"]})',
                              'content_class': cls, 'binding': binding}
    if cls == C_UNREADABLE:
        return INADMISSIBLE, {'reason': f'unreadable ({cinfo["reason"]})',
                              'content_class': cls, 'binding': binding}
    if binding == DIFFERENT_WORK:
        return INADMISSIBLE, {'reason': f'wrong paper ({binfo["reason"]})',
                              'content_class': cls, 'binding': binding}
    # ---- THE VERSION VETO. A PRECONDITION, checked before anything may be admitted. -------------
    if binding in NEVER_JOURNAL_EVIDENCE:
        return DISCOVERY_LEAD, {
            'reason': NEVER_JOURNAL_EVIDENCE[binding]
                      + (' and the task demands journal articles only' if journal_articles_only else ''),
            'content_class': cls, 'binding': binding}
    if binding == UNRESOLVED:
        return INADMISSIBLE, {'reason': 'we cannot show this text is the work we cite',
                              'content_class': cls, 'binding': binding}
    if cls == C_CITATION:
        return INADMISSIBLE, {'reason': 'no content', 'content_class': cls, 'binding': binding}

    # ---- THE POSTCONDITION. It does not care which branch answered, or in what order. -----------
    assert binding not in NEVER_JOURNAL_EVIDENCE, (
        f'ADMISSIBLE was about to be minted for a {binding} binding. THE V9 P0 IS REOPENED.')
    return ADMISSIBLE, {'reason': f'{binding.lower().replace("_", " ")}; {cinfo["reason"]}',
                        'content_class': cls, 'binding': binding}


# ---- 6. weight components — "high_quality" IS FORBIDDEN ---------------------------------------

@dataclass(frozen=True)
class WeightComponents:
    """Sol: "high_quality" must render as its COMPONENTS, each with provenance.

    There is deliberately NO `.label` and NO `__str__` that collapses to a scalar. A single word
    ("high quality") is exactly the kind of claim that outruns its evidence — one strong component
    carries the two weak ones, and nobody can see it happen.
    """
    components: dict[str, Any]
    provenance: dict[str, str]

    def render(self) -> str:
        return ', '.join(f'{k}={v} [{self.provenance.get(k, "?")}]'
                         for k, v in self.components.items())


def derive_weight_components(events: list[Event]) -> WeightComponents:
    comps, prov = {}, {}
    for e in _observations(events):
        if e.kind != EventKind.WEIGHT_COMPONENTS_DERIVED:
            continue
        for k, v in e.payload.items():
            if k.endswith('_provenance'):
                continue
            comps[k] = v
            prov[k] = e.payload.get(f'{k}_provenance', f'observed by {e.actor}')
    return WeightComponents(comps, prov)


# ---- 7. coverage status ----------------------------------------------------------------------

UNSEARCHED    = 'UNSEARCHED'
SEARCH_FAILED = 'SEARCH_FAILED'
UNROUTED      = 'UNROUTED'
SEARCHED_NONE = 'SEARCHED_NONE'
THIN          = 'THIN'
SUPPORTED     = 'SUPPORTED'
CONFLICTED    = 'CONFLICTED'

THIN_MAX = 1     # 1 admissible source is THIN; 2+ agreeing is SUPPORTED


def derive_coverage_status(ledger: 'Ledger', cell: str, thin_max: int = THIN_MAX) -> tuple[str, dict]:
    """The seven-way distinction. Collapsing any two of these is how we lied about the world.

    Only SEARCHED_NONE — after ADEQUATE route completion — supports a scoped absence statement.
    CONFLICTED and THIN directly support "the literature does not settle this", which is a CORRECT
    ANSWER, not a failure.

    NOTE THE SIGNATURE. It takes the LEDGER, not a flat event list, because it must go and RE-DERIVE
    the eligibility of every candidate source from that source's OWN observations. It will not read
    an `admissible` flag — no component is allowed to write one, and a reducer that trusted a stored
    verdict would re-open the exact hole this module closes.
    """
    events = _observations(ledger.events(cell))
    route = derive_route_status(events)
    if route.state == 'UNROUTED':
        return UNROUTED, {'reason': 'no route was ever planned for this cell'}
    if route.missing:
        return UNSEARCHED, {'reason': f'planned but never answered: {", ".join(route.missing)} '
                                      f'— an attempt with no outcome is a HANG, not an absence'}
    if route.budget_stopped:
        return SEARCH_FAILED, {'reason': 'we stopped on BUDGET. A budget stop IS NOT AN EVIDENCE GAP '
                                         '— we do not know what is there'}
    if route.failed:
        detail = ', '.join(f'{a}={route.outcomes[a]}' for a in route.failed)
        return SEARCH_FAILED, {'reason': f'the search itself failed ({detail}) — this is a fact about '
                                         f'OUR REQUEST, not about the literature'}

    # Re-derive admissibility for every candidate, from that candidate's own event stream.
    cards, rejected = [], []
    for e in events:
        if e.kind != EventKind.CANDIDATE_IDENTIFIED or not e.payload.get('source_unit'):
            continue
        src = e.payload['source_unit']
        elig, einfo = derive_eligibility(ledger.events(src))
        if elig == ADMISSIBLE:
            cards.append(e)
        else:
            rejected.append((src, elig, einfo.get('reason', '')))

    dirs = {e.payload.get('direction') for e in cards} - {None}

    if not cards:
        if not route.supports_absence:
            return SEARCH_FAILED, {'reason': 'route did not complete adequately; absence is not '
                                             'established'}
        n = len(route.planned)
        if rejected:
            # WE RETRIEVED THINGS AND COULD NOT ADMIT THEM. That is a statement about OUR EVIDENCE,
            # and it must never be read as "the literature is silent". A scoped absence sentence
            # written off this cell has to say so out loud.
            detail = '; '.join(f'{s}={e} ({r})' for s, e, r in rejected[:4])
            return SEARCHED_NONE, {
                'reason': f'all {n} adapters answered, but every one of the {len(rejected)} candidate(s) '
                          f'retrieved was INADMISSIBLE — we hold no usable evidence. This is a fact '
                          f'about OUR EVIDENCE, not about the literature: {detail}',
                'n_sources': 0, 'n_rejected': len(rejected), 'rejected': rejected}
        return SEARCHED_NONE, {'reason': f'every planned adapter genuinely answered ({n}/{n}) and '
                                         f'returned nothing — a SCOPED ABSENCE, and the only state '
                                         f'that licenses one',
                               'n_sources': 0, 'n_rejected': 0}
    if len(dirs) > 1:
        return CONFLICTED, {'reason': f'{len(cards)} admissible sources disagree ({", ".join(sorted(dirs))}) '
                                      f'— "the literature does not settle this" IS THE CORRECT ANSWER',
                            'n_sources': len(cards), 'n_rejected': len(rejected)}
    if len(cards) <= thin_max:
        return THIN, {'reason': f'{len(cards)} admissible source — enough to report, not enough to '
                                f'settle', 'n_sources': len(cards), 'n_rejected': len(rejected)}
    return SUPPORTED, {'reason': f'{len(cards)} admissible sources agree', 'n_sources': len(cards),
                       'n_rejected': len(rejected)}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE AUDITED REDUCER ENTRY POINTS — the ONLY way a derived label may enter the durable log.
#
# `record_derivation()` is bolted to this module from the inside (it checks the calling frame), so a
# downstream reducer like merge_corpus CANNOT write its verdict into the ledger by hand. It calls one
# of these instead: the derivation runs HERE, over the observations, and the verdict is appended as an
# AUDIT ARTIFACT that carries `derived_by` — which `_observations()` makes invisible to every reducer,
# including this one on its next run. A verdict that no reducer reads back cannot become a cache.
# ══════════════════════════════════════════════════════════════════════════════════════════════

def record_content_profile(ledger: 'Ledger', unit: str) -> tuple[str, dict]:
    """Derive the content class for `unit` from its observations, and MINUTE it. -> (class, info)"""
    events = ledger.events(unit)
    cls, info = derive_content_profile(events)
    ledger.record_derivation(
        unit, EventKind.CONTENT_PROFILE_DERIVED, 'derive_content_profile',
        [e.seq for e in _observations(events)],
        content_class=cls, artifact_kind=info.get('artifact_kind'),
        is_complete=bool(info.get('complete')), basis=str(info.get('reason', ''))[:400])
    return cls, info


def record_eligibility(ledger: 'Ledger', unit: str,
                       journal_articles_only: bool = True) -> tuple[str, dict]:
    """Derive whether a span from these bytes may be attributed to THIS source, and MINUTE it."""
    events = ledger.events(unit)
    elig, info = derive_eligibility(events, journal_articles_only=journal_articles_only)
    binding, _ = derive_semantic_binding(events)
    ledger.record_derivation(
        unit, EventKind.ELIGIBILITY_DECIDED, 'derive_eligibility',
        [e.seq for e in _observations(events)],
        eligibility_class=elig, semantic_binding=binding,
        basis=str(info.get('reason', ''))[:400])
    return elig, info


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The bypass detector — which labels in a corpus have NO ledger behind them?
# ══════════════════════════════════════════════════════════════════════════════════════════════

def find_underived_labels(row: dict) -> list[str]:
    """A label with no event behind it is a component asserting its own success."""
    out = []
    if 'content_status' in row:
        out.append(f'content_status={row["content_status"]!r} — written directly, derived from nothing')
    if row.get('fulltext_source'):
        out.append(f'fulltext_source={row["fulltext_source"]!r} — names the SCRIPT THAT RAN, '
                   f'not what the document IS')
    fw, actual = row.get('fulltext_words'), len((row.get('fulltext') or '').split())
    if fw and fw != actual:
        out.append(f'fulltext_words={fw:,} but the row holds {actual:,} — the count describes a '
                   f'document we no longer have')
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# SELF-TEST — the invariants that must never regress.
# ══════════════════════════════════════════════════════════════════════════════════════════════

def selftest() -> int:
    ok = fail = 0

    def check(name, cond, detail=''):
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f'  [PASS] {name}')
        else:
            fail += 1
            print(f'  [FAIL] {name}\n         {detail}')

    print('\n=== INVARIANTS ===')

    # 1. A component cannot write the label. At all.
    L = Ledger()
    try:
        L.emit('d', EventKind.CONTENT_PROFILE_DERIVED, 'wp_fetch', content_status='FULLTEXT')
        check('a component CANNOT write content_status directly', False, 'IT WAS ACCEPTED')
    except ForbiddenLabel:
        check('a component CANNOT write content_status directly', True)

    try:
        L.emit('d', EventKind.RESPONSE_RECEIVED, 'deep_fetch', note='no free copy exists')
        check('a component CANNOT assert "no free copy exists"', False, 'IT WAS ACCEPTED')
    except ForbiddenLabel:
        check('a component CANNOT assert "no free copy exists"', True)

    try:
        L.emit('d', EventKind.WEIGHT_COMPONENTS_DERIVED, 'scorer', quality='high quality')
        check('a component CANNOT assert "high quality"', False, 'IT WAS ACCEPTED')
    except ForbiddenLabel:
        check('a component CANNOT assert "high quality"', True)

    # ...but the WORLD may say anything. Raw quoted text is not an assertion.
    try:
        L.emit('d', EventKind.CONTENT_PROFILE_DERIVED, 'observer',
               header_text='Full text available. This work is complete.', word_count=9000)
        check('raw text from the world MAY contain those words (it is quoted, not claimed)', True)
    except ForbiddenLabel as e:
        check('raw text from the world MAY contain those words', False, str(e))

    # 1b. ...and the reducer's own door is bolted from the inside. Call it from a FOREIGN module and
    #     it refuses — this exec() really does run with __name__ = 'evil_component'.
    ns = {'__name__': 'evil_component', 'L': L, 'EventKind': EventKind}
    try:
        exec("L.record_derivation('d', EventKind.ELIGIBILITY_DECIDED, 'sneaky', [1], eligible=True)", ns)
        check('an outside module CANNOT call record_derivation', False, 'IT WAS ACCEPTED')
    except ForbiddenLabel:
        check('an outside module CANNOT call record_derivation (the reducer door is bolted inside)',
              True)

    # 2. 429 is not absence.
    L = Ledger()
    L.emit('p1', EventKind.ROUTE_PLANNED, 'router', adapters=['s2', 'openalex'])
    for a in ('s2', 'openalex'):
        L.emit('p1', EventKind.BACKEND_ATTEMPTED, 'fetch', adapter=a)
        L.emit('p1', EventKind.THROTTLED, 'fetch', adapter=a, http_status=429)
    st, info = derive_coverage_status(L, 'p1')
    check('HTTP 429 on every adapter -> SEARCH_FAILED (never SEARCHED_NONE)',
          st == SEARCH_FAILED, f'got {st}')
    check('a throttled route does NOT support an absence claim',
          not derive_route_status(L.events('p1')).supports_absence)

    # 3. route_complete requires an OUTCOME for every planned adapter, not a mapping.
    L = Ledger()
    L.emit('p2', EventKind.ROUTE_PLANNED, 'router', adapters=['s2', 'openalex', 'arxiv'])
    L.emit('p2', EventKind.BACKEND_ATTEMPTED, 'fetch', adapter='s2')
    L.emit('p2', EventKind.RESPONSE_RECEIVED, 'fetch', adapter='s2', http_status=200)
    r = derive_route_status(L.events('p2'))
    check('route with 1/3 adapters answered is NOT complete',
          r.state == 'INCOMPLETE' and set(r.missing) == {'openalex', 'arxiv'}, f'got {r.state} {r.missing}')

    # an attempt that never returned is a HANG, not an absence
    L.emit('p2', EventKind.BACKEND_ATTEMPTED, 'fetch', adapter='openalex')
    L.emit('p2', EventKind.BACKEND_ATTEMPTED, 'fetch', adapter='arxiv')
    r = derive_route_status(L.events('p2'))
    check('adapters ATTEMPTED but never answered are still MISSING (a hang is not a gap)',
          r.state == 'INCOMPLETE' and set(r.missing) == {'openalex', 'arxiv'}, f'got {r.state} {r.missing}')

    # 4. a budget stop is not an evidence gap.
    L = Ledger()
    L.emit('p3', EventKind.ROUTE_PLANNED, 'router', adapters=['s2'])
    L.emit('p3', EventKind.BACKEND_ATTEMPTED, 'fetch', adapter='s2')
    L.emit('p3', EventKind.RESPONSE_RECEIVED, 'fetch', adapter='s2', http_status=200)
    L.emit('p3', EventKind.BUDGET_STOPPED, 'driver', spent_usd=4.0, cap_usd=4.0)
    st, _ = derive_coverage_status(L, 'p3')
    check('a BUDGET STOP -> SEARCH_FAILED, not SEARCHED_NONE', st == SEARCH_FAILED, f'got {st}')

    # 5. a clean, complete route with nothing found DOES license absence.
    L = Ledger()
    L.emit('p4', EventKind.ROUTE_PLANNED, 'router', adapters=['s2', 'openalex'])
    for a in ('s2', 'openalex'):
        L.emit('p4', EventKind.BACKEND_ATTEMPTED, 'fetch', adapter=a)
        L.emit('p4', EventKind.RESPONSE_RECEIVED, 'fetch', adapter=a, http_status=200, n_results=0)
    st, _ = derive_coverage_status(L, 'p4')
    check('an ADEQUATE route with zero results -> SEARCHED_NONE (a scoped absence IS sayable)',
          st == SEARCHED_NONE, f'got {st}')

    # 6. 404 is a fact about their index, not the world.
    L = Ledger()
    L.emit('p5', EventKind.ROUTE_PLANNED, 'router', adapters=['s2'])
    L.emit('p5', EventKind.BACKEND_ATTEMPTED, 'fetch', adapter='s2')
    L.emit('p5', EventKind.RESPONSE_RECEIVED, 'fetch', adapter='s2', http_status=404)
    check('HTTP 404 -> NOT_INDEXED_BY_THIS_BACKEND (not "no free copy exists")',
          derive_backend_outcome(L.events('p5'), 's2') == NOT_INDEXED)

    # 7. CONFLICTED and THIN are correct answers, not failures.
    #    Note what the component emits: a source_unit and a DIRECTION (an observation — the sign of
    #    the reported effect). It does NOT get to say the source is admissible. The reducer goes and
    #    re-derives that from each source's own observations, below.
    L = Ledger()
    L.emit('c1', EventKind.ROUTE_PLANNED, 'router', adapters=['s2'])
    L.emit('c1', EventKind.BACKEND_ATTEMPTED, 'fetch', adapter='s2')
    L.emit('c1', EventKind.RESPONSE_RECEIVED, 'fetch', adapter='s2', http_status=200)
    for src, direction, words in (('10.1/a', 'positive', 9000), ('10.1/b', 'negative', 8000)):
        L.emit('c1', EventKind.CANDIDATE_IDENTIFIED, 'miner', source_unit=src, direction=direction)
        L.emit(src, EventKind.MANIFESTATION_FETCHED, 'fetch', url='u',
               requested_title='Robots and Jobs', requested_authors=['Acemoglu'])
        L.emit(src, EventKind.CONTENT_PROFILE_DERIVED, 'observer',
               **observe_text('Robots and Jobs by Acemoglu and Restrepo. ' + 'word ' * words))
    st, info = derive_coverage_status(L, 'c1')
    check('two admissible sources that disagree -> CONFLICTED', st == CONFLICTED, f'got {st} {info}')

    # 7b. a cell whose every candidate is INADMISSIBLE must not read as "the literature is silent".
    L = Ledger()
    L.emit('c2', EventKind.ROUTE_PLANNED, 'router', adapters=['s2'])
    L.emit('c2', EventKind.BACKEND_ATTEMPTED, 'fetch', adapter='s2')
    L.emit('c2', EventKind.RESPONSE_RECEIVED, 'fetch', adapter='s2', http_status=200)
    L.emit('c2', EventKind.CANDIDATE_IDENTIFIED, 'miner', source_unit='10.1/junk', direction='positive')
    L.emit('10.1/junk', EventKind.MANIFESTATION_FETCHED, 'fetch', url='u',
           requested_title='Rise of the Machines', requested_authors=['Parry'])
    L.emit('10.1/junk', EventKind.CONTENT_PROFILE_DERIVED, 'observer',
           **observe_text('This website uses cookies. By clicking the "Accept" button you agree. '
                          + 'word ' * 300))
    st, info = derive_coverage_status(L, 'c2')
    check('every candidate inadmissible -> SEARCHED_NONE that says so ("about OUR EVIDENCE")',
          st == SEARCHED_NONE and info['n_rejected'] == 1 and 'OUR EVIDENCE' in info['reason'],
          f'got {st} {info}')

    # 8. weight components never collapse to a scalar.
    L = Ledger()
    L.emit('w1', EventKind.WEIGHT_COMPONENTS_DERIVED, 'scorer',
           directness='high', directness_provenance='span names the outcome variable',
           method_quality='low', method_quality_provenance='cross-section, no identification',
           influence_percentile=0.92, influence_percentile_provenance='4,743 citations (S2)')
    w = derive_weight_components(L.events('w1'))
    check('weights render as COMPONENTS with provenance, never as "high_quality"',
          not hasattr(w, 'label') and 'directness=high' in w.render() and 'method_quality=low' in w.render(),
          w.render())
    print(f'         {w.render()}')

    # 9. NO UNIVERSAL WORD THRESHOLD. `FULLTEXT_MIN = 2500` lived here, in the CURE for itself.
    print('\n=== NO UNIVERSAL WORD THRESHOLD (the bug that reappeared inside its own fix) ===')
    check('FULLTEXT_MIN is GONE from this module (it contradicted provenance.profile() by 1,300 words)',
          not hasattr(sys.modules[__name__], 'FULLTEXT_MIN')
          and not hasattr(sys.modules[__name__], 'ABSTRACT_MIN'))

    def _profile_of(text, source_type=''):
        L = Ledger()
        L.emit('u', EventKind.MANIFESTATION_FETCHED, 'fetch', url='u', source_type=source_type,
               requested_title='Smith v. Jones', requested_authors=['Smith'])
        L.emit('u', EventKind.CONTENT_PROFILE_DERIVED, 'observer', **observe_text(text))
        return derive_content_profile(L.events('u'))

    opinion = ('Smith v. Jones. The appellant challenges the order of the court below. We have '
               'considered the record and the submissions of both parties. The appeal is dismissed '
               'with costs. It is so ordered. ') * 3
    cls_op, info_op = _profile_of(opinion, source_type='judicial-opinion')
    check(f'a {len(opinion.split())}-word JUDICIAL OPINION is COMPLETE (the old floor called it an ABSTRACT)',
          cls_op == C_FULLTEXT and info_op['complete'] and info_op['artifact_kind'] == 'judicial_opinion',
          f'got {cls_op} / {info_op.get("artifact_kind")}')
    cls_sch, _ = _profile_of(opinion)          # the SAME BYTES, judged as a scholarly work
    check(f'...and THE SAME {len(opinion.split())} WORDS as a scholarly article is a fragment, NOT the article',
          cls_sch != C_FULLTEXT, f'got {cls_sch}')
    cls_tr, info_tr = _profile_of('Recruiting. Estimated enrolment 240. Primary outcome: overall '
                                  'survival at 24 months.', source_type='clinical-trial')
    check('a 13-word TRIAL-REGISTRY RECORD is COMPLETE AT ANY LENGTH',
          cls_tr == C_FULLTEXT and info_tr['complete'], f'got {cls_tr}')
    # ...and the bytes may still DEMOTE a kind that has no floor. `source_type` cannot promote.
    cls_wall, _ = _profile_of('This website uses cookies. By clicking the "Accept" button you agree. '
                              'Sign in to your account. Privacy policy. ' * 4,
                              source_type='judicial-opinion')
    check('a LOGIN WALL served from a court website is STILL not a document (source_type cannot promote)',
          cls_wall == C_NOT_DOC, f'got {cls_wall}')
    check('the completeness rule is provenance.judge_completeness — ONE reducer, not two',
          judge_completeness('judicial_opinion', 105)[0] is True
          and judge_completeness('journal_article', 105)[0] is False)

    # 9b. THE GUARD MUST NOT BE STEPPABLE-OVER BY ADDING A DICT.
    print('\n=== THE CONCLUSION GUARD RECURSES (it used to inspect only the top level) ===')
    L = Ledger()
    try:
        L.emit('d', EventKind.MANIFESTATION_FETCHED, 'wp_fetch',
               adapter_observations={'content_status': 'FULLTEXT'})
        check('a conclusion NESTED one level down is REFUSED', False, 'IT WAS ACCEPTED')
    except ForbiddenLabel:
        check('a conclusion NESTED one level down is REFUSED', True)
    try:
        L.emit('d', EventKind.RESPONSE_RECEIVED, 'deep_fetch', notes=['ok', 'no free copy exists'])
        check('a conclusion inside a LIST is REFUSED', False, 'IT WAS ACCEPTED')
    except ForbiddenLabel:
        check('a conclusion inside a LIST is REFUSED', True)
    # ...and a URL that merely CONTAINS a reserved word is still recordable. A guard that refused to
    # record the address the bytes came from would be a guard that keeps us where we started.
    try:
        L.emit('d', EventKind.MANIFESTATION_FETCHED, 'fetch',
               locator='https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1/?report=fulltext',
               requested_authors=['Autor', 'Levy', 'Murnane'])
        check('a LOCATOR containing the word "fulltext" is still recordable (it is a URL, not a claim)',
              True)
    except ForbiddenLabel as e:
        check('a LOCATOR containing the word "fulltext" is still recordable', False, str(e))

    # 9c. RETRIES. A throttle the backoff RESOLVED is not a throttle we GAVE UP ON.
    print('\n=== 429 -> THROTTLED -> BACKEND_FAILED, AND THE RETRY THAT SUCCEEDED IS NOT A FAILURE ===')
    L = Ledger()
    for a in range(1, 4):                                   # one request, three attempts, all 429
        L.emit('r1', EventKind.BACKEND_ATTEMPTED, 'fetch', adapter='s2', request_id='s2#1', attempt=a)
        L.emit('r1', EventKind.THROTTLED, 'fetch', adapter='s2', request_id='s2#1', attempt=a,
               http_status=429)
    check('retries EXHAUSTED on 429 -> BACKEND_FAILED (a fact about OUR REQUEST RATE)',
          derive_backend_outcome(L.events('r1'), 's2') == BACKEND_FAILED,
          derive_backend_outcome(L.events('r1'), 's2'))

    L = Ledger()
    for a, kind, code in ((1, EventKind.THROTTLED, 429), (2, EventKind.THROTTLED, 429),
                          (3, EventKind.RESPONSE_RECEIVED, 200)):
        L.emit('r2', EventKind.BACKEND_ATTEMPTED, 'fetch', adapter='s2', request_id='s2#1', attempt=a)
        L.emit('r2', kind, 'fetch', adapter='s2', request_id='s2#1', attempt=a, http_status=code)
    check('429, 429, then 200 -> RESPONDED (the backoff is what backoff is FOR)',
          derive_backend_outcome(L.events('r2'), 's2') == RESPONDED,
          derive_backend_outcome(L.events('r2'), 's2'))
    check('...and BOTH 429s are STILL IN THE LOG — nothing was deleted to get that answer',
          len(L.events('r2', EventKind.THROTTLED)) == 2)

    # ...and a SECOND request to the same adapter that died still condemns it.
    L.emit('r2', EventKind.BACKEND_ATTEMPTED, 'fetch', adapter='s2', request_id='s2#2', attempt=1)
    L.emit('r2', EventKind.THROTTLED, 'fetch', adapter='s2', request_id='s2#2', attempt=1,
           http_status=429)
    check('a LATER request to the same adapter that exhausted its retries -> BACKEND_FAILED',
          derive_backend_outcome(L.events('r2'), 's2') == BACKEND_FAILED)

    # CANDIDATE_IDENTIFIED carries an `adapter` for provenance. It is NOT a request outcome.
    L = Ledger()
    L.emit('r3', EventKind.ROUTE_PLANNED, 'router', adapters=['s2'])
    L.emit('r3', EventKind.BACKEND_ATTEMPTED, 'fetch', adapter='s2', request_id='s2#1', attempt=1)
    L.emit('r3', EventKind.RESPONSE_RECEIVED, 'fetch', adapter='s2', request_id='s2#1', attempt=1,
           http_status=200)
    L.emit('r3', EventKind.CANDIDATE_IDENTIFIED, 'fetch', adapter='s2', url='https://x/y.pdf')
    check('a CANDIDATE_IDENTIFIED carrying an adapter does not make that adapter a HANG',
          derive_route_status(L.events('r3')).state == 'COMPLETE',
          derive_route_status(L.events('r3')).state)

    # 9c-ter. A BLOCKED RETRIEVAL IS A FAILED ROUTE. Observed live on Autor (2015), JEP.
    print('\n=== A 403 FROM THE PUBLISHER IS NOT "THE LITERATURE IS SILENT" ===')
    L = Ledger()
    L.emit('b1', EventKind.ROUTE_PLANNED, 'fetch', adapters=['crossref', 'unpaywall'])
    for a in ('crossref', 'unpaywall'):
        L.emit('b1', EventKind.BACKEND_ATTEMPTED, 'fetch', adapter=a, request_id=f'{a}#1', attempt=1)
        L.emit('b1', EventKind.RESPONSE_RECEIVED, 'fetch', adapter=a, request_id=f'{a}#1', attempt=1,
               http_status=200)
    # unpaywall told us exactly where the PDF is. The publisher then shut the door.
    L.emit('b1', EventKind.CANDIDATE_IDENTIFIED, 'fetch', adapter='unpaywall',
           url='https://www.aeaweb.org/articles?id=10.1257/jep.29.3.3')
    L.emit('b1', EventKind.BACKEND_ATTEMPTED, 'fetch', adapter='content:www.aeaweb.org',
           request_id='c#1', attempt=1)
    L.emit('b1', EventKind.BLOCKED, 'fetch', adapter='content:www.aeaweb.org', request_id='c#1',
           attempt=1, http_status=403)
    rb = derive_route_status(L.events('b1'))
    check('a 403 from the CONTENT HOST degrades the route, though it is not a PLANNED adapter',
          rb.state == 'COMPLETE_DEGRADED' and 'content:www.aeaweb.org' in rb.failed,
          f'got {rb.state}, failed={rb.failed}')
    check('** a blocked retrieval CANNOT support an absence claim **',
          not rb.supports_absence,
          'this was LIVE: route=COMPLETE, supports_absence=True, coverage=SEARCHED_NONE — a 403 from '
          'the publisher printed as "we looked and the literature is silent"')
    stb, _ = derive_coverage_status(L, 'b1')
    check('...and coverage reduces to SEARCH_FAILED, never SEARCHED_NONE',
          stb == SEARCH_FAILED, f'got {stb}')

    # 9c-bis. A WORK THAT HOLDS TWO DOCUMENTS IS LABELLED FOR THE BEST ONE — NOT THE LAST ONE PROFILED.
    print('\n=== TWO DOCUMENTS, ONE WORK: the label describes THE ONE WE HOLD, not the last ingested ===')
    L = Ledger()
    BODY = ('Journal of Economic Perspectives—Volume 33, Number 2—Spring 2019—Pages 3–30. '
            'Automation and New Tasks. By Daron Acemoglu and Pascual Restrepo. '
            + 'one more robot per thousand workers reduces employment by 0.2 percentage points. ' * 200)
    ABS = 'We estimate the effect of robots on employment using a task-based framework. ' * 3
    for text in (BODY, ABS):                                  # the ABSTRACT is ingested LAST
        L.emit('m1', EventKind.MANIFESTATION_FETCHED, 'fetch', locator='u',
               requested_title='Automation and New Tasks',
               requested_authors=['Acemoglu', 'Restrepo'])
        L.emit('m1', EventKind.CONTENT_PROFILE_DERIVED, 'observe_text', **observe_text(text))
    cls_m, info_m = derive_content_profile(L.events('m1'))
    check('a work holding a 2,000w ARTICLE and a 24w ABSTRACT is FULLTEXT — the abstract was profiled '
          'LAST, and the old reducer would have called the whole work an ABSTRACT',
          cls_m == C_FULLTEXT and info_m['artifact_kind'] == 'journal_article',
          f'got {cls_m} / {info_m.get("artifact_kind")} — this was LIVE: Damioli (2021) read '
          f'CITATION_ONLY over 13,085 words')
    check('...and it says how many documents it chose between', info_m.get('n_documents_held') == 2)
    b_m, _ = derive_semantic_binding(L.events('m1'))
    check('...and the semantic binding describes THE SAME document the label describes',
          b_m in (SAME_WORK, VERSION_PUBLISHED), f'got {b_m}')

    # 9d. A REDUCER NEVER READS ANOTHER REDUCER'S VERDICT. The docstring said so; nothing enforced it.
    print('\n=== A RECORDED VERDICT IS INVISIBLE TO EVERY REDUCER (it was invisible only BY LUCK) ===')
    L = Ledger()
    L.emit('u9', EventKind.MANIFESTATION_FETCHED, 'fetch', locator='u',
           requested_title='Robots and Jobs', requested_authors=['Acemoglu'])
    L.emit('u9', EventKind.CONTENT_PROFILE_DERIVED, 'observe_text',
           **observe_text('Robots and Jobs by Acemoglu and Restrepo. ' + 'word ' * 9000))
    first, _ = record_content_profile(L, 'u9')
    again, _ = record_content_profile(L, 'u9')          # the audit record is now IN the log...
    check('recording a derived verdict does NOT change the next derivation (no cache, no drift)',
          first == again == C_FULLTEXT, f'{first} then {again}')
    check('...and the verdict IS on the record, as an audit artifact carrying `derived_by`',
          any(e.payload.get('derived_by') == 'derive_content_profile'
              for e in L.events('u9', EventKind.CONTENT_PROFILE_DERIVED)))
    # the killer: a derived record written with an OBSERVATION's kind must not be read as the profile.
    prof_events = [e for e in L.events('u9', EventKind.CONTENT_PROFILE_DERIVED)]
    check('a derived record shares the OBSERVATION kind and is STILL not read as the profile',
          len(prof_events) == 3 and len(_observations(prof_events)) == 1,
          f'{len(prof_events)} events, {len(_observations(prof_events))} observations')

    # 10. THE LEDGER MUST SURVIVE THE PROCESS. It did not reload, so every standalone script started
    #     with an empty history and reduced over nothing.
    print('\n=== DURABILITY (a reducer over a log it cannot read is a reducer over nothing) ===')
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / 'sub' / 'ledger.jsonl'          # the parent dir does not exist yet, either
        L1 = Ledger(p)
        L1.emit('p9', EventKind.ROUTE_PLANNED, 'router', adapters=['s2', 'openalex', 'arxiv'])
        for a in ('s2', 'openalex', 'arxiv'):
            L1.emit('p9', EventKind.BACKEND_ATTEMPTED, 'fetch', adapter=a)
            L1.emit('p9', EventKind.RESPONSE_RECEIVED, 'fetch', adapter=a, http_status=200, n_results=0)
        before, _ = derive_coverage_status(L1, 'p9')

        L2 = Ledger.load(p)                            # A DIFFERENT PROCESS'S VIEW OF THE SAME LOG
        after, _ = derive_coverage_status(L2, 'p9')
        check('a reopened Ledger RELOADS its history (it used to start empty and reduce over nothing)',
              len(L2) == len(L1) == 7 and [e.seq for e in L2.events()] == [e.seq for e in L1.events()],
              f'reloaded {len(L2)} of {len(L1)} events')
        check('...and the reducers give THE SAME ANSWER on the reloaded log',
              after == before == SEARCHED_NONE, f'{before!r} -> {after!r}')

        # the empty in-memory history did not merely lose events — it CHANGED THE VERDICT.
        blind = Ledger(p, load=False)
        blind_st, _ = derive_coverage_status(blind, 'p9')
        check('WITHOUT the reload the very same log reduces to UNROUTED — the old behaviour, exposed',
              blind_st == UNROUTED, f'got {blind_st}')

        L2.emit('p9', EventKind.BUDGET_STOPPED, 'driver', spent_usd=4.0, cap_usd=4.0)
        check('an append after reload CONTINUES the sequence (it does not collide at seq=1)',
              L2.events('p9')[-1].seq == 8)
        check('...and the appended event is on disk, and changes the verdict on the NEXT reload',
              derive_coverage_status(Ledger.load(p), 'p9')[0] == SEARCH_FAILED)

        # A PERSISTED LEDGER IS AN UNTRUSTED INPUT. The emit guard is re-applied on read.
        with open(p, 'a') as fh:
            fh.write(json.dumps({'seq': 99, 'unit': 'p9', 'kind': 'content_profile_derived',
                                 'actor': 'evil', 'payload': {'content_status': 'FULLTEXT'},
                                 'ts': 0.0}) + '\n')
        try:
            Ledger.load(p)
            check('a CONCLUSION hand-written into the JSONL is REFUSED ON LOAD', False, 'IT WAS LOADED')
        except LedgerCorrupt:
            check('a CONCLUSION hand-written into the JSONL is REFUSED ON LOAD (echo >> is not a '
                  'harder attack than emit())', True)

    print(f'\n  {ok} passed, {fail} failed')
    return 1 if fail else 0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# REPLAY — our REAL history, through the ledger. What SHOULD the labels have been?
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _row(rows, author, year):
    for r in rows:
        if (r.get('authors') or ['?'])[0] == author and r.get('year') == year:
            return r
    raise KeyError(f'{author} {year}')


def replay() -> int:
    if not CORPUS.exists():
        print(f'!! corpus not found: {CORPUS}')
        return 1
    rows = json.loads(CORPUS.read_text())

    print('\n' + '=' * 98)
    print('REPLAY OF OUR REAL HISTORY — the label we shipped vs the label the events earn')
    print('=' * 98)
    print(f'corpus: {CORPUS}  ({len(rows)} papers)')

    caught = []

    # ── CASE 1 ────────────────────────────────────────────────────────────────────────────────
    # Autor (2015), JEP. We stamped FULLTEXT. It is 535 words of aeaweb.org COOKIE BANNER.
    r = _row(rows, 'Autor', 2015)
    L = Ledger()
    u = r['doi']
    L.emit(u, EventKind.ROUTE_PLANNED, 'wp_fetch', adapters=['s2/doi', 'openalex', 's2/title', 'arxiv'])
    for a in ('s2/doi', 'openalex', 's2/title', 'arxiv'):
        L.emit(u, EventKind.BACKEND_ATTEMPTED, 'wp_fetch', adapter=a)
        L.emit(u, EventKind.RESPONSE_RECEIVED, 'wp_fetch', adapter=a, http_status=200)
    L.emit(u, EventKind.CANDIDATE_IDENTIFIED, 'wp_fetch', adapter='s2/doi', url=r.get('oa_url', ''))
    L.emit(u, EventKind.MANIFESTATION_FETCHED, 'wp_fetch', url=r.get('oa_url', ''),
           requested_title=r['title'], requested_authors=r.get('authors', []))
    L.emit(u, EventKind.CONTENT_PROFILE_DERIVED, 'observer', **observe_text(r.get('fulltext') or ''))
    cls, cinfo = derive_content_profile(L.events(u))
    elig, einfo = derive_eligibility(L.events(u))
    caught.append(dict(
        case='Autor (2015) — Journal of Economic Perspectives', doi=u,
        shipped='content_status = FULLTEXT   (fulltext_source = working_paper)',
        derived=f'{cls} -> {elig}',
        why=cinfo['reason'],
        proof=f'the 535 "words": {(r.get("fulltext") or "")[:96]!r}',
        events=len(L)))

    # ── CASE 2 ────────────────────────────────────────────────────────────────────────────────
    # Parry (2016), Group & Organization Management. The title search matched SOMEBODY ELSE'S PAPER.
    r = _row(rows, 'Parry', 2016)
    L = Ledger()
    u = r['doi']
    L.emit(u, EventKind.ROUTE_PLANNED, 'wp_fetch', adapters=['s2/doi', 'openalex', 's2/title', 'arxiv'])
    for a, code in (('s2/doi', 404), ('openalex', 404), ('s2/title', 200), ('arxiv', 200)):
        L.emit(u, EventKind.BACKEND_ATTEMPTED, 'wp_fetch', adapter=a)
        L.emit(u, EventKind.RESPONSE_RECEIVED, 'wp_fetch', adapter=a, http_status=code)
    L.emit(u, EventKind.CANDIDATE_IDENTIFIED, 'wp_fetch', adapter='s2/title',
           url='https://arxiv.org/pdf/2511.17203', matched_on='title substring "rise of the machines"')
    L.emit(u, EventKind.MANIFESTATION_FETCHED, 'wp_fetch', url='https://arxiv.org/pdf/2511.17203',
           requested_title=r['title'], requested_authors=r.get('authors', []),
           document_title='MATHEMATICS: THE RISE OF THE MACHINES', byline='YANG-HUI HE')
    L.emit(u, EventKind.CONTENT_PROFILE_DERIVED, 'observer', **observe_text(r.get('fulltext') or ''))
    binding, binfo = derive_semantic_binding(L.events(u))
    elig, einfo = derive_eligibility(L.events(u))
    caught.append(dict(
        case='Parry (2016) — Group & Organization Management', doi=u,
        shipped='content_status = FULLTEXT, 4,027w  (fulltext_source = working_paper)',
        derived=f'{binding} -> {elig}',
        why=binfo['reason'],
        proof='we hold Yang-Hui He, "Mathematics: The Rise of the Machines" (arXiv, 2025) — a paper '
              'on theorem-proving — filed under an HR journal article by Parry et al. (2016)',
        events=len(L)))

    # ── CASE 3 ────────────────────────────────────────────────────────────────────────────────
    # Autor/Levy/Murnane (2003), QJE. "no free text" — the sentence that is four worlds at once.
    r = _row(rows, 'Autor', 2003)
    L = Ledger()
    u = r['doi']
    L.emit(u, EventKind.ROUTE_PLANNED, 'wp_fetch', adapters=['s2/doi', 'openalex', 's2/title', 'arxiv'])
    # what actually happens, verified live: S2 does not resolve this DOI. jget turns it into None.
    L.emit(u, EventKind.BACKEND_ATTEMPTED, 'wp_fetch', adapter='s2/doi')
    L.emit(u, EventKind.RESPONSE_RECEIVED, 'wp_fetch', adapter='s2/doi', http_status=404,
           note='live probe 2026-07-13: S2 returned 404 for this DOI')
    L.emit(u, EventKind.BACKEND_ATTEMPTED, 'wp_fetch', adapter='openalex')
    L.emit(u, EventKind.THROTTLED, 'wp_fetch', adapter='openalex', http_status=429,
           note='we hammered OpenAlex all night with repeated fetch runs')
    L.emit(u, EventKind.BACKEND_ATTEMPTED, 'wp_fetch', adapter='s2/title')
    L.emit(u, EventKind.THROTTLED, 'wp_fetch', adapter='s2/title', http_status=429)
    # arxiv: attempted, never came back. THAT IS A HANG, and it looked exactly like a gap.
    L.emit(u, EventKind.BACKEND_ATTEMPTED, 'wp_fetch', adapter='arxiv')
    route = derive_route_status(L.events(u))
    cov, cinfo = derive_coverage_status(L, u)
    caught.append(dict(
        case='Autor, Levy & Murnane (2003) — QJE  [the "no free text" line]', doi=u,
        shipped='log: "no free text"    (read by us as: no free copy of this paper exists)',
        derived=f'route={route.state}  coverage={cov}',
        why=cinfo['reason'] + f'; outcomes: ' +
            ', '.join(f'{a}={o}' for a, o in route.outcomes.items()),
        proof='and the paper IS free — NBER Working Paper 8337, in full, forever. "no free text" was '
              'false in every reading: 404 = their index, 429 = our request rate, no-outcome = a hang',
        events=len(L)))

    # ── CASE 4 ────────────────────────────────────────────────────────────────────────────────
    # Acemoglu & Restrepo (2019), JEP. Labelled working_paper. IT IS THE JOURNAL ARTICLE.
    # The reducer must not be a sledgehammer: a blanket quarantine would DESTROY real evidence.
    r = _row(rows, 'Acemoglu', 2019)
    L = Ledger()
    u = r['doi']
    L.emit(u, EventKind.ROUTE_PLANNED, 'wp_fetch', adapters=['s2/doi'])
    L.emit(u, EventKind.BACKEND_ATTEMPTED, 'wp_fetch', adapter='s2/doi')
    L.emit(u, EventKind.RESPONSE_RECEIVED, 'wp_fetch', adapter='s2/doi', http_status=200)
    L.emit(u, EventKind.MANIFESTATION_FETCHED, 'wp_fetch', url=r.get('oa_url', ''),
           requested_title=r['title'], requested_authors=r.get('authors', []))
    L.emit(u, EventKind.CONTENT_PROFILE_DERIVED, 'observer', **observe_text(r.get('fulltext') or ''))
    binding, binfo = derive_semantic_binding(L.events(u))
    elig, einfo = derive_eligibility(L.events(u))
    prof = observe_text(r.get('fulltext') or '')
    caught.append(dict(
        case='Acemoglu & Restrepo (2019) — JEP  [the label was false in the OTHER direction]', doi=u,
        shipped='fulltext_source = working_paper  (so a blanket quarantine would DELETE it)',
        derived=f'{binding} -> {elig}',
        why=f'header reads "Journal of Economic Perspectives—Volume 33, Number 2—Spring 2019—Pages 3–30". '
            f'It IS the article. The "working_paper" label named the SCRIPT, not the document. '
            f'(NBER appears at char 74,747 — in the REFERENCES.)',
        proof=f'preprint stamp in header: {prof["preprint_stamp_in_header"]}   '
              f'anywhere in text: {prof["preprint_stamp_anywhere"]}  <- a whole-text scan reads the '
              f'BIBLIOGRAPHY and calls the JEP article a working paper',
        events=len(L)))

    # ── CASE 5 ────────────────────────────────────────────────────────────────────────────────
    # The counts that describe a document we threw away.
    trunc = [x for x in rows if x.get('fulltext_words')
             and x['fulltext_words'] != len((x.get('fulltext') or '').split())]

    # ── CASE 6 — THE DECISIVE ONE ─────────────────────────────────────────────────────────────
    # Sol's P0 says working-paper text is filed under journal DOIs. It is. But the label that is
    # supposed to mark it, `fulltext_source='working_paper'`, is written by WHICHEVER SCRIPT RAN —
    # so we tested it against what the documents ACTUALLY ARE.
    marked, truly_preprint, binding_of = set(), set(), {}
    for r in rows:
        if r.get('content_status') != 'FULLTEXT':
            continue
        key = f'{(r.get("authors") or ["?"])[0]} {r.get("year")}'
        if r.get('fulltext_source') == 'working_paper':
            marked.add(key)
        L = Ledger()
        u = r.get('doi') or r.get('title', '?')
        L.emit(u, EventKind.MANIFESTATION_FETCHED, 'corpus', url=r.get('oa_url', ''),
               requested_title=r.get('title', ''), requested_authors=r.get('authors', []))
        L.emit(u, EventKind.CONTENT_PROFILE_DERIVED, 'observer',
               **observe_text(r.get('fulltext') or ''))
        b, _ = derive_semantic_binding(L.events(u))
        e, _ = derive_eligibility(L.events(u))
        binding_of[key] = (b, e)
        if b == VERSION_PREPRINT:
            truly_preprint.add(key)

    # ── render ────────────────────────────────────────────────────────────────────────────────
    for i, c in enumerate(caught, 1):
        print(f'\n┌─ CASE {i}: {c["case"]}')
        print(f'│  doi        {c["doi"]}')
        print(f'│  WE SHIPPED {c["shipped"]}')
        print(f'│  LEDGER SAYS{"":1}{c["derived"]}')
        print(f'│  because    {c["why"]}')
        print(f'│  proof      {c["proof"]}')
        print(f'└─ ({c["events"]} events)')

    print('\n┌─ CASE 5: four word-counts that describe text we no longer hold')
    for x in trunc:
        au = (x.get('authors') or ['?'])[0]
        print(f'│  {au[:12]:<12}{x["year"]}  claims {x["fulltext_words"]:>6,}w   holds '
              f'{len((x.get("fulltext") or "").split()):>6,}w   (truncated at 120,000 chars)')
    print('└─ the count was taken BEFORE the truncation and never re-derived')

    # Count ONLY what the evidence supports: the marked rows that are genuinely ADMISSIBLE journal
    # articles. ("marked but not a preprint" would include the cookie banner and the stranger's
    # paper — calling those "genuine journal articles" would be this project's own disease, in the
    # summary line of its cure.)
    would_destroy = sorted(k for k in marked if binding_of.get(k, ('', ''))[1] == ADMISSIBLE)

    print('\n┌─ CASE 6: THE LABEL THAT IS SUPPOSED TO CATCH SOL\'S P0 — TESTED AGAINST THE DOCUMENTS')
    print(f'│  rows the LABEL `fulltext_source=working_paper` marks : {len(marked)}')
    for k in sorted(marked):
        b, e = binding_of.get(k, ('?', '?'))
        print(f'│      {k:<18} is actually {b:<22} -> {e}')
    print(f'│  rows whose HEADER SAYS they are working papers        : {len(truly_preprint)}')
    for k in sorted(truly_preprint):
        print(f'│      {k:<18} <- NOT marked by the label')
    print(f'│')
    print(f'│  AGREEMENT BETWEEN THE LABEL AND THE TRUTH: {len(marked & truly_preprint)}')
    print(f'│')
    print(f'│  The label is wrong in BOTH directions, because it names THE SCRIPT THAT FETCHED, not the')
    print(f'│  document. Quarantining on it would have DELETED {len(would_destroy)} genuine journal articles')
    print(f'│      ({", ".join(would_destroy)})')
    print(f'│  AND LEFT ALL {len(truly_preprint - marked)} REAL WORKING PAPERS IN THE CORPUS — the fabrication ships anyway.')
    print('└─ this is why the label must be DERIVED FROM THE HEADER, and never asserted by a fetcher')

    # ── the whole corpus, re-derived ──────────────────────────────────────────────────────────
    print('\n' + '=' * 98)
    print('THE WHOLE CORPUS, RE-DERIVED FROM CONTENT')
    print('=' * 98)
    claimed = {}
    derived = {}
    for r in rows:
        claimed[r.get('content_status')] = claimed.get(r.get('content_status'), 0) + 1
        L = Ledger()
        u = r.get('doi') or r.get('title', '?')
        if (r.get('fulltext') or r.get('abstract')):
            L.emit(u, EventKind.MANIFESTATION_FETCHED, 'corpus', url=r.get('oa_url', ''),
                   requested_title=r.get('title', ''), requested_authors=r.get('authors', []))
            L.emit(u, EventKind.CONTENT_PROFILE_DERIVED, 'observer',
                   **observe_text(r.get('fulltext') or r.get('abstract') or ''))
        cls, _ = derive_content_profile(L.events(u))
        derived[cls] = derived.get(cls, 0) + 1

    print(f'\n  {"label":<22}{"the corpus CLAIMS":>18}{"the CONTENT earns":>20}')
    for k in ('FULLTEXT', 'ABSTRACT', 'ABSTRACT_ONLY', 'CITATION_ONLY', 'NOT_A_DOCUMENT',
              'UNREADABLE_ENCODING'):
        c, d = claimed.get(k, 0), derived.get(k, 0)
        if not c and not d:
            continue
        mark = '   <-- ' if c != d else ''
        print(f'  {k:<22}{c if c else "-":>18}{d if d else "-":>20}{mark}')

    # admissibility of everything the corpus calls FULLTEXT
    adm = lead = inad = 0
    for r in rows:
        if r.get('content_status') != 'FULLTEXT':
            continue
        L = Ledger()
        u = r.get('doi') or r.get('title', '?')
        L.emit(u, EventKind.MANIFESTATION_FETCHED, 'corpus', url=r.get('oa_url', ''),
               requested_title=r.get('title', ''), requested_authors=r.get('authors', []))
        L.emit(u, EventKind.CONTENT_PROFILE_DERIVED, 'observer',
               **observe_text(r.get('fulltext') or ''))
        e, _ = derive_eligibility(L.events(u))
        adm += e == ADMISSIBLE
        lead += e == DISCOVERY_LEAD
        inad += e == INADMISSIBLE

    n_underived = sum(1 for r in rows if find_underived_labels(r))
    print(f'\n  of the {adm + lead + inad} rows the corpus calls FULLTEXT, the events earn:')
    print(f'      ADMISSIBLE as journal evidence : {adm}')
    print(f'      DISCOVERY_LEAD (working paper) : {lead}   <- real text, NOT journal-attributable')
    print(f'      INADMISSIBLE                   : {inad}   <- chrome, unreadable, or a stranger\'s paper')
    print(f'\n  rows carrying at least one label NO EVENT SUPPORTS: {n_underived}/{len(rows)}')
    print('\n  Sol: "The recovered text is presently A DISCOVERY LEAD, not automatically')
    print('        journal-attributable evidence."')
    print('\n  And note what the reducer did NOT do: it did not blanket-quarantine. It ADMITTED the')
    print('  rows whose headers prove they are the real article (Acemoglu 2019 JEP, Goos 2014 AER,')
    print('  Chalmers 2021 ETP) — every one of which the "working_paper" label would have destroyed —')
    print('  while catching four NBER/MIT/Fed working papers that same label never saw.')
    print('\n  A label that names the script will be wrong in both directions. A label derived from the')
    print('  header is right in both.')
    return 0


if __name__ == '__main__':
    import sys
    args = sys.argv[1:]
    rc = 0
    if not args or '--selftest' in args:
        rc |= selftest()
    if not args or '--replay' in args:
        rc |= replay()
    raise SystemExit(rc)
