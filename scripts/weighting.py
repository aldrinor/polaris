#!/usr/bin/env python3
"""MULTIDIMENSIONAL WEIGHTING — a source is a VECTOR, never a citation count.

    Sol plan 4 item 6: "NEVER collapse quality into raw citations."

THE FAILURE THIS IS THE STRUCTURAL CURE FOR

  Our own retrieval comment confesses it, verbatim: "Crossref sorted by citations returns ResNet and
  SMOTE -- famous, not relevant." 4,743 citations makes Autor, Levy & Murnane the most important paper
  in labour economics; the SAME 4,743 citations in machine learning is unremarkable. A single scalar
  called `high_quality` cannot tell those two apart, and the moment we sort by it we have sorted by
  fame — the exact thing a literature review is supposed to see past.

WHAT THIS MODULE REFUSES TO PRODUCE

  There is no `high_quality` float here and there never will be. `high_quality` is FORBIDDEN as a bare
  label; a source renders as its COMPONENTS, each with provenance:

      directness=high (from a quantitative_estimate act) | method_quality=low (observational, RoB high)
      | influence_percentile=0.92 (OpenAlex citation_normalized_percentile) | independence=low (4th
      paper by the same authors) | recency=neutral (no temporal need)

  A caller that wants a single number for RANKING gets one from `blended_priority()` — but it is a
  VIEW over the vector, derived transparently from the components in front of you, and it is allowed to
  be recomputed tomorrow by a better blend on the same components. The vector is the evidence; the
  scalar is a display cache, exactly as the LAW says of a `claim`.

MISSING IS 'UNKNOWN', NEVER ZERO

  This is the same disease acquisition.py cures for the network: `if not d: return []` turned four
  transport outcomes into "no evidence". Here the disease is `dimension or 0.0`, which turns "we never
  probed OpenAlex" and "we probed and this paper is genuinely uncited" into the same number — and then
  penalizes a 2023 clinical trial for not yet having citations it cannot possibly have. An UNKNOWN
  dimension is EXCLUDED from the blend and the blend RENORMALIZES over what is known. It is never a 0
  that drags a source down for a fact we do not have.

DOMAIN BEHAVIOUR IS DATA, NOT CODE  (GENERALITY IS NOT OPTIONAL)

  Clinical: risk-of-bias, design, directness, endpoint relevance dominate — a highly-cited biased
  observational paper stays biased. Legal: bindingness, court hierarchy, jurisdictional fit, current
  validity dominate — raw citations are optional context, not authority. Thin evidence: "the
  literature does not settle this" is the CORRECT answer and saying so is a PASS.

  NONE of those three sentences is written in this file's code. They are three ROWS in
  config/authority/weighting_profiles.yaml. The `legal:` profile was added without editing one line
  below. Every scorer looks a value up by a STRUCTURAL key — a design token, an expression kind, an
  evidence-act id, an OpenAlex field — and never by a topic, a venue name, or a regex over the text.
  If a domain needs different behaviour, it needs a new row, not a new branch.

WHAT IT PLUGS INTO (build on it, do not duplicate it)

  acquisition.Acquirer   -- THE ONE DOOR TO THE NETWORK, for the OpenAlex probe. A 429 lands as
                            THROTTLED -> influence UNKNOWN (never 0). We never open our own urllib path.
  provenance             -- derive_source_type: the expression a row CLAIMS (journal_version / preprint
                            / official_text). We weight the expression's authority; we do not re-derive
                            what an expression IS.
  research_contract      -- the coverage matrix supplies marginal_coverage_contribution: a source's
                            worth is partly the cell nothing else closes.
  config/authority/*     -- weighting_profiles.yaml (this module's registry), recency_profile.yaml,
                            domain_packs/*.yaml (source-tier priors). All numbers live in data.

RUN IT:  python3 scripts/weighting.py         # ranks our corpus OLD (raw cites) beside NEW (the vector)
         python3 scripts/weighting.py --offline   # same, but no network (influence -> UNKNOWN)
         python3 scripts/weighting.py --self-test  # the DATA invariants (influence never outranks ...)
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

# ── config locations (all numbers live in DATA) ──────────────────────────────
CONFIG_DIR = ROOT / 'config' / 'authority'
PROFILES_PATH = CONFIG_DIR / 'weighting_profiles.yaml'
DOMAIN_PACK_DIR = ROOT / 'config' / 'domain_packs'
CORPUS_PATH = ROOT / 'outputs' / 'journal_corpus_content.json'
PROBE_CACHE_DIR = ROOT / 'outputs' / 'openalex_cache'
PROBE_LEDGER = ROOT / 'outputs' / 'weighting_probe_ledger.jsonl'

MAILTO = 'aldrin.or@c-polarbiotech.com'

# Confidence lattice — an overall confidence is the MIN over the signals that
# actually fired (mirrors config/authority/blend_weights.yaml:confidence_order).
UNKNOWN, LOW, MEDIUM, HIGH = 'UNKNOWN', 'LOW', 'MEDIUM', 'HIGH'
_CONF_ORDER = {UNKNOWN: 0, LOW: 1, MEDIUM: 2, HIGH: 3}


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# THE PROVENANCE-CARRYING SCALAR.  There are no bare floats in a vector — every number knows where it
# came from and how sure we are of it, or it is UNKNOWN and says so.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Dimension:
    """ONE axis of a source's worth. `value` is None when UNKNOWN — and UNKNOWN is not 0.

    `source` is the PROVENANCE: the field / registry / act the value was read from, never "trust me".
    `basis` is the human-readable why. A Dimension renders as `name=value (source)` and NEVER as a
    bare adjective — that is the whole point of carrying it.
    """
    name: str
    value: float | None
    confidence: str
    source: str                 # provenance: WHERE this number came from
    basis: str = ''             # why, in words

    @property
    def known(self) -> bool:
        return self.value is not None and self.confidence != UNKNOWN

    def render(self) -> str:
        if not self.known:
            return f'{self.name}=UNKNOWN ({self.source})'
        band = 'high' if self.value >= 0.66 else ('mid' if self.value >= 0.4 else 'low')
        return f'{self.name}={self.value:.2f}/{band} ({self.source})'


@dataclass(frozen=True)
class Gate:
    """A HARD GATE — one of the only four things allowed to exclude a source (LAW).

    `passed` is True (admit), False (exclude from the answer body — NOT deleted from the graph), or
    None (not applicable / no explicit constraint, so the gate is inert). `multiplier` is what the
    blend multiplies by: 1.0 when inert or passed, 0.0 when a HARD 'only' constraint failed, or a
    demote in (0,1) when the constraint was a soft 'prefer'.
    """
    name: str
    passed: bool | None
    multiplier: float
    source: str
    basis: str = ''

    def render(self) -> str:
        state = {True: 'PASS', False: 'EXCLUDE', None: 'inert'}[self.passed]
        return f'{self.name}:{state}(x{self.multiplier:g}) ({self.source})'


@dataclass
class WeightVector:
    """A source, as a vector of provenance-carrying dimensions plus its four gates.

    This is what the module PRODUCES. It never collapses on its own; `blended_priority` collapses it
    into a ranking key on demand, and shows its work.
    """
    unit: str                                   # doi or title — what identifies the source
    label: str                                  # human display, e.g. 'Autor et al. (2003), QJE'
    raw_citations: int | None                   # the OLD world's single number — carried for the A/B
    dims: dict[str, Dimension] = field(default_factory=dict)
    gates: dict[str, Gate] = field(default_factory=dict)

    def render(self) -> str:
        gline = '  '.join(g.render() for g in self.gates.values())
        dlines = '\n    '.join(self.dims[n].render() for n in self.dims)
        return f'{self.label}\n  GATES: {gline}\n    {dlines}'


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# THE REGISTRY — loaded once, cached. Domain behaviour is READ FROM HERE, never branched on in code.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

_YAML_CACHE: dict[str, Any] = {}


def _load_yaml(path: Path) -> dict:
    key = str(path)
    if key not in _YAML_CACHE:
        import yaml
        _YAML_CACHE[key] = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    return _YAML_CACHE[key]


def load_registry() -> dict:
    return _load_yaml(PROFILES_PATH)


def profile_for(domain: str) -> dict:
    """The weight profile for a domain. An UNKNOWN domain gets `general` — NEVER clinical or legal.

    This is the ONLY place a domain string touches behaviour, and all it does is a dict lookup. Adding
    a domain is a row in the yaml; this function does not change.
    """
    reg = load_registry()
    profiles = reg.get('profiles', {})
    prof = profiles.get((domain or 'general').lower().strip())
    if prof is None:
        prof = profiles.get('general', {})
    return prof


def load_domain_pack(domain: str) -> dict:
    p = DOMAIN_PACK_DIR / f'{(domain or "general").lower().strip()}.yaml'
    if not p.exists():
        p = DOMAIN_PACK_DIR / 'general.yaml'
    try:
        return _load_yaml(p)
    except Exception:
        return {}


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# THE OPENALEX PROBE — through acquisition.Acquirer (the one door), cached, and it CANNOT return 0.
#
# The whole reason to route this through Acquirer rather than urllib is the reason acquisition.py
# exists: a 429 is a fact about OUR REQUEST RATE, and it must land as UNKNOWN influence, never as a
# zero-cite paper. `probe()` returns a dict with an `outcome` the caller can read, and the influence
# scorer maps every non-RESPONDED outcome to a Dimension with value=None (UNKNOWN), each with a
# DIFFERENT basis so THROTTLED and NOT_INDEXED are never confused with "uncited".
# ══════════════════════════════════════════════════════════════════════════════════════════════════

class OpenAlexProbe:
    """Field+age-normalized scholarly influence from OpenAlex /works, via the one network door.

    We read `citation_normalized_percentile` (OpenAlex field-normalizes by subfield AND publication
    year — a 2003 paper with 4,743 cites and a 2023 paper with 50 can BOTH be top-decile in their
    cohort) and `fwci` (field-weighted citation impact). Raw `cited_by_count` comes back too, but ONLY
    so the __main__ A/B table can show the OLD world — it never enters the vector.
    """

    def __init__(self, offline: bool = False):
        self.offline = offline
        PROBE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._acq = None

    def _acquirer(self):
        if self._acq is None:
            from acquisition import Acquirer, BlobStore, open_ledger
            # A DEDICATED scratch ledger — we are ranking, not building the corpus, and we should not
            # bloat the durable event log with hundreds of probe events.
            self._acq = Acquirer('weighting', ledger=open_ledger(PROBE_LEDGER), blobs=BlobStore())
        return self._acq

    def probe(self, doi: str) -> dict:
        """-> {outcome, fields...}. `outcome` in RESPONDED|NOT_INDEXED|THROTTLED|BLOCKED|
        TRANSPORT_ERROR|OFFLINE|NO_DOI. Cached to disk so a re-run is instant and polite."""
        if not doi:
            return {'outcome': 'NO_DOI'}
        cache = PROBE_CACHE_DIR / (urllib.parse.quote(doi, safe='') + '.json')
        if cache.exists():
            try:
                return json.loads(cache.read_text())
            except Exception:
                pass
        if self.offline:
            return {'outcome': 'OFFLINE'}
        url = f'https://api.openalex.org/works/doi:{urllib.parse.quote(doi)}?mailto={MAILTO}'
        try:
            resp, data = self._acquirer().get_json(f'openalex:{doi}', 'openalex', url, tries=3)
        except Exception as e:                       # a hang is not a gap
            return {'outcome': 'TRANSPORT_ERROR', 'error': type(e).__name__}
        if not resp.ok or not isinstance(data, dict):
            return {'outcome': resp.outcome}          # THROTTLED / NOT_INDEXED / BLOCKED — never "0 cites"
        cnp = data.get('citation_normalized_percentile') or {}
        topic = data.get('primary_topic') or {}
        out = {
            'outcome': 'RESPONDED',
            'cited_by_count': data.get('cited_by_count'),
            'fwci': data.get('fwci'),
            'citation_normalized_percentile': cnp.get('value'),
            'is_in_top_10_percent': cnp.get('is_in_top_10_percent'),
            'publication_year': data.get('publication_year'),
            'type': data.get('type'),
            'subfield': ((topic.get('subfield') or {}).get('display_name')
                         if isinstance(topic.get('subfield'), dict) else None),
            'field': ((topic.get('field') or {}).get('display_name')
                      if isinstance(topic.get('field'), dict) else None),
        }
        try:
            cache.write_text(json.dumps(out))
        except Exception:
            pass
        return out


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# THE CORPUS CONTEXT — the two dimensions that are about a source's RELATIONSHIP to the rest of the
# corpus (independence, marginal coverage) cannot be computed from a row alone. This precomputes them.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

@dataclass
class CorpusContext:
    """Cross-source facts: who shares authors with whom, and how crowded each subfield/topic is."""
    author_counts: dict[str, int] = field(default_factory=dict)
    subfield_counts: dict[str, int] = field(default_factory=dict)
    n_works: int = 0

    @classmethod
    def build(cls, rows: list[dict], row_probes: list[dict]) -> 'CorpusContext':
        """`row_probes` is index-aligned to `rows` (row i's OpenAlex probe is row_probes[i])."""
        ac: dict[str, int] = {}
        sc: dict[str, int] = {}
        for r, probe in zip(rows, row_probes):
            for a in (r.get('authors') or []):
                ac[_norm_author(a)] = ac.get(_norm_author(a), 0) + 1
            sub = (probe or {}).get('subfield')
            if sub:
                sc[sub] = sc.get(sub, 0) + 1
        return cls(author_counts=ac, subfield_counts=sc, n_works=len(rows))


def _norm_author(a: str) -> str:
    return (a or '').strip().lower()


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# THE SCORERS — one per dimension. Each is PURE, each reads its numbers from the registry, each returns
# a Dimension (or Gate) that carries its own provenance. None of them names a topic, a venue or a host.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _expr_kind(row: dict) -> tuple[str, str]:
    """The expression a row CLAIMS — via provenance.derive_source_type (do not re-derive what it is)."""
    try:
        from provenance import derive_source_type
        _wk, expr, basis = derive_source_type(row)
        return (expr or 'unknown'), basis
    except Exception:
        # Degrade to the same DATA the registry keys on, without importing provenance.
        t = str(row.get('type') or '').lower()
        m = {'journal-article': 'journal_version', 'journal article': 'journal_version',
             'proceedings-article': 'proceedings_version', 'preprint': 'preprint',
             'posted-content': 'preprint', 'report': 'working_paper', 'working-paper': 'working_paper',
             'judicial-opinion': 'official_text', 'opinion': 'official_text', 'case': 'official_text',
             'statute': 'official_text', 'legislation': 'official_text',
             'clinical-trial': 'registry_record', 'trial-registration': 'registry_record'}
        if row.get('court') or row.get('case_name'):
            return 'official_text', 'row carries a court/case field'
        return m.get(t, 'unknown'), f'row declares type={t!r}'


# ── HARD GATE 1: explicit_eligibility ────────────────────────────────────────
def gate_eligibility(row: dict, policy: dict) -> Gate:
    """The ONLY source constraint that gates is the one the QUESTION states. `policy` carries the
    verbatim constraints AND their strictness (only=hard, prefer=soft). No constraint => inert.

    Peer-reviewed-only over a preprint is a HARD 'only' gate -> multiplier 0 (excluded from the body,
    kept in the graph). A 'prefer journal' is a soft demote. Language / jurisdiction work the same way.
    """
    if not policy:
        return Gate('explicit_eligibility', None, 1.0, 'no explicit source constraint in the question')
    expr, _ = _expr_kind(row)
    reasons, mult, passed = [], 1.0, True
    hard = policy.get('strictness', 'only') == 'only'

    if policy.get('peer_reviewed_only'):
        is_reviewed = expr in ('journal_version', 'proceedings_version')
        if not is_reviewed:
            passed = False
            mult = 0.0 if hard else float(policy.get('soft_demote', 0.5))
            reasons.append(f'question demands peer-reviewed journal articles; this is {expr!r}')
    langs = [l.lower() for l in (policy.get('languages') or [])]
    row_lang = str(row.get('language') or 'en').lower()[:2]
    if langs and row_lang not in {l[:2] for l in langs}:
        passed = False
        mult = min(mult, 0.0 if hard else float(policy.get('soft_demote', 0.5)))
        reasons.append(f'question restricts to {langs}; source language is {row_lang!r}')
    jur = [j.lower() for j in (policy.get('jurisdictions') or [])]
    row_jur = str(row.get('jurisdiction') or '').lower()
    if jur and row_jur and row_jur not in jur:
        passed = False
        mult = min(mult, 0.0 if hard else float(policy.get('soft_demote', 0.5)))
        reasons.append(f'question is scoped to {jur}; source jurisdiction is {row_jur!r}')

    if passed:
        return Gate('explicit_eligibility', True, 1.0, 'question source constraints',
                    f'satisfies the stated constraints (expression={expr})')
    return Gate('explicit_eligibility', False, mult, 'question source constraints', '; '.join(reasons))


# ── HARD GATE 2: chrome (bytes are not a document) ───────────────────────────
def gate_chrome(row: dict) -> Gate:
    """Fires ONLY when the artifact's NATURE is non-document AND we hold nothing better. A real journal
    article we happen to hold only as a landing page is NOT chrome — that is a failed fetch, and it
    demotes content_completeness instead. This distinction is the entire acquisition.py thesis applied
    to our own holdings: a fact about our fetch is not a fact about the work."""
    reg = load_registry()
    chrome_kinds = set(reg.get('chrome_kinds', []))
    cls = str(row.get('content_class') or '').upper()
    kind = str(row.get('artifact_kind') or '')
    identified_work = bool(row.get('doi') and (row.get('venue') or row.get('title')))
    if cls in ('NOT_DOC', 'UNREADABLE') and not identified_work:
        return Gate('chrome', False, 0.0, 'content reducer',
                    f'bytes are {cls} and the row identifies no scholarly work — this is chrome')
    if kind in chrome_kinds and not identified_work:
        return Gate('chrome', False, 0.0, 'content reducer',
                    f'artifact_kind={kind!r} is non-document and no work is identified')
    return Gate('chrome', None, 1.0, 'content reducer',
                'bytes are a document, or a real work held incompletely (see content_completeness)')


# ── HARD GATE 3: faithfulness (enforced upstream; carried here) ──────────────
def gate_faithfulness(row: dict) -> Gate:
    """Span-grounding is enforced by provenance.verify_span at card construction, not re-litigated
    here. We carry the flag so a source whose spans failed verification cannot be ranked into the body.
    A row with no faithfulness verdict is treated as inert (the upstream gate owns the verdict)."""
    v = row.get('faithfulness')
    if v is False or str(v).upper() in ('FAIL', 'UNFAITHFUL', 'NOT_ENTAILED'):
        return Gate('faithfulness', False, 0.0, 'provenance.verify_span (upstream)',
                    'a span failed verbatim entailment — burned regardless of every weight below')
    return Gate('faithfulness', None, 1.0, 'provenance.verify_span (upstream)',
                'enforced at card construction; not re-litigated in weighting')


# ── HARD GATE 4: off_topic (CONFIRMED, not merely low relevance) ─────────────
def gate_offtopic(row: dict, relevance: Dimension) -> Gate:
    """Only a POSITIVE, high-confidence off-topic finding gates. Low topical_relevance is a WEIGHT.
    An explicit `off_topic=True` flag (a confirmed classifier verdict) gates; a low relevance score
    computed from thin evidence does NOT — that is exactly the confusion the LAW forbids."""
    if row.get('off_topic') is True:
        return Gate('off_topic', False, 0.0, 'off-topic classifier', 'confirmed off-topic')
    return Gate('off_topic', None, 1.0, 'off-topic classifier',
                'not confirmed off-topic; any topical shortfall is a weight, not a gate')


# ── WEIGHT: topical_relevance ────────────────────────────────────────────────
def score_topical_relevance(row: dict, question_terms: list[str]) -> Dimension:
    """Overlap of the source's title/abstract with the question's core concepts. Field-agnostic term
    matching (the same family research_contract.route_terms uses); no topic is named in code — the
    terms come from the compiled contract."""
    if not question_terms:
        return Dimension('topical_relevance', None, UNKNOWN, 'no compiled question terms',
                         'the contract supplied no terms to route against')
    blob = ' '.join(str(row.get(k) or '') for k in ('title', 'abstract', 'venue')).lower()
    if not blob.strip():
        return Dimension('topical_relevance', None, UNKNOWN, 'row has no title/abstract text', '')
    # Word-boundary match on GENERIC terms supplied by the contract (so 'ai' does not match 'said').
    # This is the same family as research_contract.build_matchers — a data-driven matcher, not a
    # domain regex baked into code.
    import re as _re
    hits = sum(1 for t in question_terms
               if _re.search(r'\b' + _re.escape(t.lower()) + r'\b', blob))
    frac = hits / max(1, len(question_terms))
    # A source on-topic on ANY core concept is relevant; saturating so a title cannot game it.
    val = 1.0 - math.exp(-2.2 * frac) if hits else 0.15
    conf = HIGH if row.get('abstract') else MEDIUM       # title-only match is less sure
    return Dimension('topical_relevance', round(val, 3), conf,
                     f'{hits}/{len(question_terms)} contract terms matched',
                     f'matched on title/abstract/venue text')


# ── WEIGHT: evidentiary_directness ───────────────────────────────────────────
def score_directness(row: dict, domain: str) -> Dimension:
    """How directly the source's evidence answers the question — from the TYPE of evidence act it
    bears (evidence_acts.json), refined by whether that act is on the question's endpoint. A forecast
    is less direct than a measured quantity; a doctrinal holding is as direct as an estimate. UNKNOWN
    when we have not mined acts for this source (honest: we do not fabricate directness)."""
    reg = load_registry()
    table = reg.get('act_directness', {})
    acts = row.get('evidence_acts') or row.get('act_types')
    if not acts:
        return Dimension('evidentiary_directness', None, UNKNOWN, 'no mined evidence acts',
                         'directness is read from the acts a source bears; none mined for this row')
    if isinstance(acts, str):
        acts = [acts]
    best_id, best = None, 0.0
    for a in acts:
        v = table.get(a)
        if v is not None and v > best:
            best, best_id = v, a
    if best_id is None:
        return Dimension('evidentiary_directness', None, UNKNOWN,
                         'acts not in directness registry', f'acts={acts}')
    ref = reg.get('endpoint_match_refinement', {})
    ep = str(row.get('endpoint_match') or 'unknown')
    mult = ref.get(ep, ref.get('unknown', 1.0))
    return Dimension('evidentiary_directness', round(best * mult, 3), HIGH,
                     f'evidence act {best_id!r} x endpoint={ep}',
                     'directness prior from the act type, refined by endpoint relevance')


# ── WEIGHT: methodological_quality ───────────────────────────────────────────
def score_method_quality(row: dict, domain: str) -> Dimension:
    """Study DESIGN -> quality, per domain, refined by risk-of-bias. The clinical hierarchy (RCT / SR
    on top) and the economics hierarchy (quasi-experimental identification on top) are different ROWS
    in design_quality, not different code. A highly-cited biased observational paper: design=
    observational is capped low AND risk_of_bias=high multiplies it down — and no citation count is in
    this dimension to rescue it. UNKNOWN when design is unknown (we do not guess a design)."""
    reg = load_registry()
    dq = reg.get('design_quality', {})
    table = dq.get((domain or 'general').lower()) or dq.get('default', {})
    design = str(row.get('design') or '').lower().strip()
    if not design or design not in table or table.get(design) is None:
        return Dimension('methodological_quality', None, UNKNOWN,
                         'design unknown / not in design_quality registry',
                         f'design={design or None!r}; we do not assign a quality to an unknown design')
    base = float(table[design])
    rob = str(row.get('risk_of_bias') or 'unknown').lower()
    rob_mult = float(reg.get('risk_of_bias_refinement', {}).get(rob, 1.0))
    val = base * rob_mult
    basis = f'design={design} ({domain}) prior {base:.2f}'
    if rob != 'unknown':
        basis += f' x risk_of_bias={rob} ({rob_mult:.2f})'
    return Dimension('methodological_quality', round(val, 3), HIGH,
                     f'design_quality[{domain}][{design}]', basis)


# ── WEIGHT: source_authority ─────────────────────────────────────────────────
def score_source_authority(row: dict, domain: str) -> Dimension:
    """STRUCTURAL authority of the expression we hold — a court opinion IS the primary legal authority;
    a working paper is NOT the peer-reviewed article. Refined by court hierarchy (bindingness) or
    peer-review status when the row carries those fields. Domain-agnostic: the court_level refinement
    is simply inert on a row that has no court_level, so no legal branch is needed in code."""
    reg = load_registry()
    ea = reg.get('expression_authority', {})
    expr, expr_basis = _expr_kind(row)
    base = ea.get(expr, ea.get('unknown'))
    if base is None:
        return Dimension('source_authority', None, UNKNOWN, 'expression kind unknown', expr_basis)
    base = float(base)
    val, basis = base, f'expression={expr} (authority {base:.2f}) [{expr_basis}]'
    refs = reg.get('authority_refinements', {})
    for field_name, table in refs.items():
        rv = str(row.get(field_name) or '').lower().strip()
        if rv and rv in table:
            m = float(table[rv])
            val *= m
            basis += f' x {field_name}={rv} ({m:.2f})'
    conf = HIGH if expr != 'unknown' else LOW
    return Dimension('source_authority', round(min(1.0, val), 3), conf,
                     'expression_authority (+refinements)', basis)


# ── WEIGHT: field_year_type_normalized_influence ─────────────────────────────
def score_influence(probe: dict) -> Dimension:
    """The ONE place a citation-derived number enters — and it is FIELD + AGE normalized, never raw.

    OpenAlex citation_normalized_percentile already normalizes by subfield and by publication-year
    cohort, so a 2003 paper with 4,743 cites and a 2023 paper with 50 can BOTH be top-decile. FWCI is
    the fallback. EVERY non-RESPONDED outcome, and RESPONDED-but-missing, yields UNKNOWN with its own
    basis — a THROTTLE is not an uncited paper, and neither is a paper OpenAlex has not scored yet."""
    outcome = probe.get('outcome')
    if outcome != 'RESPONDED':
        why = {'THROTTLED': 'OpenAlex throttled us (429) — a fact about our request rate, not the paper',
               'NOT_INDEXED': 'OpenAlex has no record of this DOI — a fact about their index',
               'BLOCKED': 'OpenAlex blocked us (entitlement) — not a fact about citations',
               'OFFLINE': 'run was --offline; influence not probed',
               'NO_DOI': 'row carries no DOI to probe',
               'TRANSPORT_ERROR': 'the probe never got an answer (timeout/DNS)'}.get(
                   outcome, f'probe outcome {outcome}')
        return Dimension('field_year_type_normalized_influence', None, UNKNOWN,
                         f'OpenAlex probe: {outcome}', why)
    pct = probe.get('citation_normalized_percentile')
    if isinstance(pct, (int, float)):
        return Dimension('field_year_type_normalized_influence', round(float(pct), 3), HIGH,
                         'OpenAlex citation_normalized_percentile',
                         f'field+age-normalized percentile {pct:.3f} '
                         f'(subfield={probe.get("subfield")}, year={probe.get("publication_year")})')
    fwci = probe.get('fwci')
    if isinstance(fwci, (int, float)):
        # FWCI: 1.0 == field/age average. Squash to [0,1] (2.0 -> ~0.6, 5.0 -> ~0.86) as a fallback.
        val = 1.0 - math.exp(-0.35 * float(fwci))
        return Dimension('field_year_type_normalized_influence', round(val, 3), MEDIUM,
                         'OpenAlex fwci (percentile missing)',
                         f'field-weighted citation impact {fwci:.2f} squashed to {val:.2f}')
    return Dimension('field_year_type_normalized_influence', None, UNKNOWN,
                     'OpenAlex responded but scored no impact',
                     'no citation_normalized_percentile and no fwci — too new or too niche to be scored')


# ── WEIGHT: independence ─────────────────────────────────────────────────────
def score_independence(row: dict, ctx: CorpusContext) -> Dimension:
    """How INDEPENDENT this evidence unit is from the rest of the corpus. Six papers by the same two
    authors are not six independent confirmations. Penalizes by the max author-overlap count across
    the corpus — the more of the corpus shares this source's authors, the less independent it is. This
    is why the NEW ranking demotes the 3rd/4th paper by the same lab that the OLD ranking floats to
    the top on raw citations."""
    authors = [_norm_author(a) for a in (row.get('authors') or []) if a]
    if not authors or ctx.n_works <= 1:
        return Dimension('independence', None, UNKNOWN, 'no authors / single-work corpus', '')
    shared = max(ctx.author_counts.get(a, 1) for a in authors)   # how many corpus works share an author
    # 1 appearance -> fully independent (1.0); each extra shared work erodes it, floored so a prolific
    # author is demoted, never dropped.
    val = max(0.35, 1.0 / shared)
    conf = HIGH if ctx.n_works >= 5 else MEDIUM
    return Dimension('independence', round(val, 3), conf,
                     f'max author appears in {shared}/{ctx.n_works} corpus works',
                     'shared authorship erodes independence; floored (demote-not-drop)')


# ── WEIGHT: recency_fit ──────────────────────────────────────────────────────
def score_recency(row: dict, domain: str, current_year: int) -> Dimension:
    """Temporal fit — NEUTRAL unless the question has a recency need. A recent trial is NOT penalized
    for being recent, and an old paper is NOT worthless (floored). The horizon is DATA (per profile):
    0 for general/economics (neutral), positive for legal (current validity) and policy. Mirrors
    src/polaris_graph/authority/recency.py exactly, reading the same knob names."""
    reg = load_registry()
    rp = reg.get('recency', {})
    prof = profile_for(domain)
    horizon = prof.get('default_recency_horizon_years', 0)
    neutral = float(rp.get('neutral_score', 1.0))
    if not horizon or horizon <= 0:
        return Dimension('recency_fit', neutral, MEDIUM, f'{domain} profile: horizon=0',
                         'no temporal need — recency neutral (old is not worthless)')
    year = row.get('year') or row.get('publication_year')
    try:
        year = int(year)
    except (TypeError, ValueError):
        return Dimension('recency_fit', neutral, LOW, 'no known year', 'recency neutral (year unknown)')
    age = max(0, current_year - year)
    hl = float(rp.get('decay_halflife_years', 8.0))
    floor = float(rp.get('floor_score', 0.30))
    decay = 0.5 ** (age / hl) if hl > 0 else 1.0
    val = min(1.0, max(floor, floor + (1.0 - floor) * decay))
    return Dimension('recency_fit', round(val, 3), HIGH,
                     f'{domain} profile: horizon={horizon}y, half-life={hl}y',
                     f'age={age}y decayed to {val:.2f} (current validity fades as doctrine/evidence moves)')


# ── WEIGHT: content_completeness ─────────────────────────────────────────────
def score_completeness(row: dict) -> Dimension:
    """Do we hold a COMPLETE document, per the content reducer — or only a citation / abstract / a
    landing page we mistook for the paper? Read from the class the bytes EARNED (content_class), not a
    label a fetcher wrote. A real article held only as a landing_page is INCOMPLETE (demoted), which is
    why our single most-cited work — held as a 0-word landing page — drops in the NEW ranking."""
    reg = load_registry()
    table = reg.get('content_completeness', {})
    cls = str(row.get('content_class') or '').upper()
    if not cls or cls not in table:
        return Dimension('content_completeness', None, UNKNOWN,
                         'no content class held', f'content_class={cls or None!r}')
    v = table[cls]
    if v is None:
        return Dimension('content_completeness', None, UNKNOWN, f'content_class={cls}',
                         'bytes are not a document — completeness undefined (see chrome gate)')
    words = row.get('fulltext_words')
    basis = f'held as {cls}'
    if isinstance(words, int):
        basis += f' ({words} words)'
    return Dimension('content_completeness', round(float(v), 3), HIGH, 'content reducer', basis)


# ── WEIGHT: marginal_coverage_contribution ───────────────────────────────────
def score_marginal_coverage(row: dict, ctx: CorpusContext, probe: dict) -> Dimension:
    """A source's worth is partly the coverage cell NOTHING ELSE closes. Approximated here by how
    crowded its subfield is: the sole source on a subfield carries high marginal value; the 8th paper
    on the same subfield adds little NEW coverage even if each is excellent. (The full signal is
    research_contract.coverage_matrix marginal cell-closure; this is the corpus-level proxy that needs
    no compiled contract.) UNKNOWN when we could not place the source in a subfield."""
    sub = (probe or {}).get('subfield')
    if not sub or ctx.n_works <= 1:
        return Dimension('marginal_coverage_contribution', None, UNKNOWN,
                         'no subfield / single-work corpus',
                         'cannot judge marginal coverage without a topic placement')
    crowd = ctx.subfield_counts.get(sub, 1)
    val = max(0.3, 1.0 / crowd)           # sole-in-subfield -> 1.0; crowded -> demoted, never 0
    return Dimension('marginal_coverage_contribution', round(val, 3), MEDIUM,
                     f'{crowd}/{ctx.n_works} corpus works share subfield {sub!r}',
                     'scarcer coverage is worth more at the margin (demote-not-drop)')


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# BUILDING THE VECTOR + THE BLEND (a VIEW over the vector, renormalized over KNOWN dims)
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def build_vector(row: dict, *, domain: str, ctx: CorpusContext, probe: dict,
                 policy: dict | None = None, question_terms: list[str] | None = None,
                 current_year: int = 2026) -> WeightVector:
    """Assemble a source's full vector. Every dimension carries provenance; nothing is a bare number.

    The scorers are called unconditionally on EVERY domain — the domain only changes the DATA they
    read and the WEIGHTS the blend applies, never which scorers run. That is what keeps a clinical run
    and a legal run the same code path.
    """
    rel = score_topical_relevance(row, question_terms or [])
    dims = {
        'topical_relevance': rel,
        'evidentiary_directness': score_directness(row, domain),
        'methodological_quality': score_method_quality(row, domain),
        'source_authority': score_source_authority(row, domain),
        'field_year_type_normalized_influence': score_influence(probe),
        'independence': score_independence(row, ctx),
        'recency_fit': score_recency(row, domain, current_year),
        'content_completeness': score_completeness(row),
        'marginal_coverage_contribution': score_marginal_coverage(row, ctx, probe),
    }
    gates = {
        'explicit_eligibility': gate_eligibility(row, policy or {}),
        'faithfulness': gate_faithfulness(row),
        'chrome': gate_chrome(row),
        'off_topic': gate_offtopic(row, rel),
    }
    label = (row.get('attribution_short')
             or (f"{', '.join(row.get('authors'))} ({row.get('year')})" if row.get('authors') else '')
             or (f"{row.get('case_name')} ({row.get('year')}), {row.get('court', '')}".strip(', ')
                 if row.get('case_name') else '')
             or f"{row.get('title', '?')} ({row.get('year')})")
    raw = row.get('citations')
    try:
        raw = int(raw)
    except (TypeError, ValueError):
        raw = None
    return WeightVector(unit=row.get('doi') or row.get('title') or '?', label=label,
                        raw_citations=raw, dims=dims, gates=gates)


@dataclass
class Blend:
    """The ranking VIEW over a vector. Carries its own explanation — it is a display cache, not truth."""
    priority: float
    gate_multiplier: float
    confidence: str
    known_dims: int
    unknown_dims: list[str]
    thin: bool
    explanation: str


def blended_priority(vec: WeightVector, domain: str) -> Blend:
    """Collapse the vector into ONE comparable number for ranking — the honest way.

    RENORMALIZE OVER KNOWN DIMENSIONS. An UNKNOWN dimension is dropped from BOTH the numerator and the
    weight normaliser, so it neither helps nor hurts — a paper OpenAlex has not scored is ranked on
    what we DO know, not sunk to zero for what we do not. Then the four gates multiply: a hard-failed
    gate zeroes the priority (excluded from the body), an inert gate does nothing.

    Confidence is the MIN over the KNOWN dimensions that carried real weight, and if too few dimensions
    are known the source is flagged THIN — the honest input to "the literature does not settle this".
    """
    prof = profile_for(domain)
    weights = prof.get('weights', {})
    num, wsum = 0.0, 0.0
    unknown: list[str] = []
    confs: list[str] = []
    for name, w in weights.items():
        d = vec.dims.get(name)
        if d is None or not d.known:
            unknown.append(name)
            continue
        num += float(w) * float(d.value)
        wsum += float(w)
        confs.append(d.confidence)
    base = (num / wsum) if wsum > 0 else 0.0

    gate_mult = 1.0
    gate_notes = []
    for g in vec.gates.values():
        gate_mult *= g.multiplier
        if g.passed is False:
            gate_notes.append(g.name)

    known = len(weights) - len(unknown)
    # THIN: fewer than half the profile's weighted dimensions are known, OR the total known weight is
    # a minority of the profile. Either way we cannot speak confidently — and that is a licensed PASS.
    thin = (wsum < 0.5) or (known < max(2, len(weights) // 2))
    conf = min(confs, key=lambda c: _CONF_ORDER[c]) if confs else UNKNOWN
    if thin and conf != UNKNOWN:
        conf = LOW

    priority = base * gate_mult
    expl = (f'{known}/{len(weights)} dims known (w={wsum:.2f}); base={base:.3f}'
            + (f' x gates({",".join(gate_notes)})={gate_mult:g}' if gate_notes else '')
            + (f'; THIN -> "the literature does not settle this" is the correct, passing answer' if thin else ''))
    return Blend(priority=round(priority, 4), gate_multiplier=gate_mult, confidence=conf,
                 known_dims=known, unknown_dims=unknown, thin=thin, explanation=expl)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# THE A/B — OLD (raw citations) beside NEW (the vector). This is what the task asks __main__ to print.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def rank_corpus(rows: list[dict], *, domain: str, offline: bool,
                policy: dict | None = None, question_terms: list[str] | None = None,
                current_year: int = 2026) -> tuple[list[dict], CorpusContext, dict[str, dict]]:
    """Probe OpenAlex for every row, build every vector, and return the rows scored BOTH ways."""
    probe_client = OpenAlexProbe(offline=offline)

    def _key(i: int, r: dict) -> str:
        return r.get('doi') or r.get('title') or f'#{i}'

    probes: dict[str, dict] = {_key(i, r): probe_client.probe(r.get('doi') or '')
                               for i, r in enumerate(rows)}
    # CorpusContext gets probes INDEX-ALIGNED to rows, so a DOI-less row cannot collide with another
    # and steal its subfield.
    ctx = CorpusContext.build(rows, [probes[_key(i, r)] for i, r in enumerate(rows)])
    scored = []
    for i, r in enumerate(rows):
        probe = probes[_key(i, r)]
        vec = build_vector(r, domain=domain, ctx=ctx, probe=probe, policy=policy,
                           question_terms=question_terms, current_year=current_year)
        blend = blended_priority(vec, domain)
        scored.append({'row': r, 'vec': vec, 'blend': blend, 'probe': probe})
    return scored, ctx, probes


def print_old_vs_new(scored: list[dict], *, domain: str, title: str) -> None:
    old = sorted(scored, key=lambda s: (s['vec'].raw_citations or -1), reverse=True)
    new = sorted(scored, key=lambda s: s['blend'].priority, reverse=True)
    old_rank = {id(s): i + 1 for i, s in enumerate(old)}
    new_rank = {id(s): i + 1 for i, s in enumerate(new)}

    print(f'\n{"="*100}\n{title}   (domain profile: {domain})\n{"="*100}')
    print(f'{"NEW#":>4} {"OLD#":>4} {"Δ":>4}  {"cites":>6} {"infl%":>6} {"indep":>5} {"cmpl":>5} '
          f'{"NEWpri":>7} {"conf":>5}  source')
    print('-' * 100)
    moved = 0
    for s in new:
        d, o = new_rank[id(s)], old_rank[id(s)]
        delta = o - d
        if delta != 0:
            moved += 1
        infl = s['vec'].dims['field_year_type_normalized_influence']
        indep = s['vec'].dims['independence']
        cmpl = s['vec'].dims['content_completeness']
        fmt = lambda dim: (f'{dim.value:.2f}' if dim.known else ' UNK')
        arrow = f'{"+" if delta>0 else ""}{delta}' if delta else '·'
        print(f'{d:>4} {o:>4} {arrow:>4}  {str(s["vec"].raw_citations or "?"):>6} '
              f'{fmt(infl):>6} {fmt(indep):>5} {fmt(cmpl):>5} '
              f'{s["blend"].priority:>7.3f} {s["blend"].confidence:>5}  {s["vec"].label[:46]}')
    print('-' * 100)
    print(f'{moved}/{len(scored)} sources changed rank between OLD (raw citations) and NEW (the vector).')


def _explain_top_movers(scored: list[dict], k: int = 4) -> None:
    old_rank = {id(s): i + 1 for i, s in
                enumerate(sorted(scored, key=lambda s: (s['vec'].raw_citations or -1), reverse=True))}
    new = sorted(scored, key=lambda s: s['blend'].priority, reverse=True)
    new_rank = {id(s): i + 1 for i, s in enumerate(new)}
    movers = sorted(scored, key=lambda s: abs(old_rank[id(s)] - new_rank[id(s)]), reverse=True)[:k]
    print('\nWHY THE RANKING MOVED (top movers, each explained by its vector, not a label):')
    for s in movers:
        o, n = old_rank[id(s)], new_rank[id(s)]
        print(f'\n  {s["vec"].label}   OLD #{o} -> NEW #{n}')
        print(f'    raw citations = {s["vec"].raw_citations} (the OLD world\'s only number)')
        for name in ('field_year_type_normalized_influence', 'independence', 'content_completeness',
                     'source_authority'):
            print(f'    {s["vec"].dims[name].render()}')
        print(f'    blend: {s["blend"].explanation}')


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# GENERALITY PROOF — the SAME code on a CLINICAL, a LEGAL, and a THIN-EVIDENCE question. Fixture rows
# are DATA; the only thing that changes between them is the profile ROW the blend reads.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _fixture_clinical() -> list[dict]:
    return [
        # A recent RCT with almost no citations yet, and a famous but biased observational study.
        dict(doi='10.9999/rct', title='Randomized trial of drug X for condition Y',
             authors=['Nguyen', 'Okafor'], venue='Journal of Trials', year=2024, type='journal-article',
             citations=12, design='experiment', risk_of_bias='low', content_class='FULLTEXT',
             fulltext_words=6000, artifact_kind='journal_article',
             evidence_acts=['quantitative_estimate'], endpoint_match='on_endpoint'),
        dict(doi='10.9999/obs', title='Large observational cohort on drug X',
             authors=['Famous', 'Author'], venue='Big Journal', year=2009, type='journal-article',
             citations=4200, design='observational', risk_of_bias='high', content_class='FULLTEXT',
             fulltext_words=8000, artifact_kind='journal_article',
             evidence_acts=['qualitative_empirical_result'], endpoint_match='on_endpoint'),
    ]


def _fixture_legal() -> list[dict]:
    return [
        dict(doi='', title='Apex Court ruling on algorithmic liability', case_name='A v. B',
             court='Apex Court', court_level='supreme', authors=[], venue='Apex Court Reports',
             year=2022, type='judicial-opinion', citations=90, jurisdiction='us',
             content_class='FULLTEXT', fulltext_words=9000, artifact_kind='journal_article',
             evidence_acts=['doctrinal_holding_or_rule']),
        dict(doi='', title='Trial court decision, later doctrine moved on', case_name='C v. D',
             court='District Court', court_level='trial', authors=[], venue='F.Supp.',
             year=1994, type='judicial-opinion', citations=15, jurisdiction='us',
             content_class='FULLTEXT', fulltext_words=4000, artifact_kind='journal_article',
             evidence_acts=['doctrinal_holding_or_rule']),
        dict(doi='10.1000/lawrev', title='Law review article arguing a position',
             authors=['Scholar'], venue='Law Review', year=2021, type='journal-article',
             citations=800, jurisdiction='us', content_class='FULLTEXT', fulltext_words=15000,
             artifact_kind='journal_article', evidence_acts=['recommendation_or_guidance']),
    ]


def _fixture_thin() -> list[dict]:
    return [
        dict(doi='', title='A single preprint on a barely-studied question',
             authors=['Solo'], venue='', year=2025, type='preprint', citations=0,
             design='observational', content_class='ABSTRACT', fulltext_words=200,
             artifact_kind='abstract'),
    ]


def run_generality_proof(offline: bool) -> None:
    print(f'\n\n{"#"*100}\n# GENERALITY PROOF — one code path; the domain is a DATA row, never a branch\n{"#"*100}')
    cases = [
        ('clinical', _fixture_clinical(),
         'CLINICAL: risk-of-bias + design + directness dominate; a famous biased observational study '
         'must not beat a clean recent RCT on citations.'),
        ('legal', _fixture_legal(),
         'LEGAL: bindingness (court hierarchy) + current validity dominate; raw citations are not '
         'authority — the 800-cite law-review article is not binding, the 90-cite apex ruling is.'),
        ('general', _fixture_thin(),
         'THIN EVIDENCE: one preprint, nothing to triangulate — the mechanism must say so, and '
         '"the literature does not settle this" is the CORRECT, passing answer (no fabricated score).'),
    ]
    for domain, rows, headline in cases:
        print(f'\n{"-"*100}\n{domain.upper()}  —  {headline}\n{"-"*100}')
        scored, _ctx, _pr = rank_corpus(rows, domain=domain, offline=offline)
        ranked = sorted(scored, key=lambda s: s['blend'].priority, reverse=True)
        for s in ranked:
            b = s['blend']
            print(f'\n  #{ranked.index(s)+1}  {s["vec"].label}  (raw cites={s["vec"].raw_citations})  '
                  f'-> NEW priority {b.priority:.3f}  [{b.confidence}]')
            key = ('methodological_quality', 'evidentiary_directness', 'source_authority',
                   'recency_fit', 'field_year_type_normalized_influence', 'independence')
            for name in key:
                print(f'      {s["vec"].dims[name].render()}')
            print(f'      blend: {b.explanation}')
        if domain == 'general' and ranked and ranked[0]['blend'].thin:
            print('\n  VERDICT: THIN — the corpus cannot settle the question. Reporting that IS the pass.')


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# SELF-TEST — the LAW, encoded as assertions on the DATA. If a profile lets influence outrank method
# or directness, or a scorer treats UNKNOWN as 0, this fails loudly.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def self_test() -> int:
    reg = load_registry()
    fails = []

    # 1. Only the four hard gates gate. build_vector must produce exactly them.
    v = build_vector(dict(doi='x', title='t', authors=['A'], venue='V', year=2020,
                          type='journal-article', content_class='FULLTEXT'),
                     domain='general', ctx=CorpusContext(n_works=1), probe={'outcome': 'OFFLINE'})
    if set(v.gates) != set(reg['hard_gates']):
        fails.append(f'gates {set(v.gates)} != hard_gates {set(reg["hard_gates"])}')

    # 2. In EVERY profile, influence weight <= min(method, directness). "Do not let influence outrank
    #    methodological quality or directness." — the LAW, as a check on the data.
    inv = reg['invariants']['influence_never_outranks']
    for name, prof in reg['profiles'].items():
        w = prof['weights']
        infl = w['field_year_type_normalized_influence']
        cap = min(w[d] for d in inv)
        if infl > cap + 1e-9:
            fails.append(f'profile {name!r}: influence {infl} > min({inv})={cap}')

    # 3. Weighted dims sum to ~1.0 in every profile, and the set matches weighted_dimensions.
    wd = set(reg['weighted_dimensions'])
    for name, prof in reg['profiles'].items():
        w = prof['weights']
        if set(w) != wd:
            fails.append(f'profile {name!r}: dims {set(w)} != weighted_dimensions')
        if abs(sum(w.values()) - 1.0) > 1e-6:
            fails.append(f'profile {name!r}: weights sum to {sum(w.values())}, not 1.0')

    # 4. UNKNOWN is never 0. A throttled probe and a missing design must be UNKNOWN, not value 0.0.
    dth = score_influence({'outcome': 'THROTTLED'})
    if dth.known or dth.value is not None:
        fails.append('THROTTLED influence is not UNKNOWN')
    dm = score_method_quality({'design': None}, 'clinical')
    if dm.known or dm.value is not None:
        fails.append('unknown design is not UNKNOWN')

    # 5. UNKNOWN dims are excluded from the blend (renormalized), NOT zeroed. A vector known ONLY on a
    #    high dim must not be dragged toward 0 by its UNKNOWN siblings.
    only_high = WeightVector('u', 'u', None, dims={
        n: (Dimension(n, 0.9, HIGH, 'test') if n == 'methodological_quality'
            else Dimension(n, None, UNKNOWN, 'test'))
        for n in reg['weighted_dimensions']},
        gates={g: Gate(g, None, 1.0, 'test') for g in reg['hard_gates']})
    b = blended_priority(only_high, 'clinical')
    if abs(b.priority - 0.9) > 1e-6:
        fails.append(f'renormalization broken: one known dim of 0.9 blended to {b.priority}, not 0.9')

    # 6. The clinical LAW: a famous biased observational study does NOT beat a clean recent RCT.
    scored, _c, _p = rank_corpus(_fixture_clinical(), domain='clinical', offline=True)
    top = max(scored, key=lambda s: s['blend'].priority)
    if 'trial' not in top['vec'].label.lower() and top['vec'].raw_citations and top['vec'].raw_citations > 1000:
        fails.append('clinical: the famous biased observational study beat the RCT')

    # 7. Adding a domain is DATA, not code: the legal profile exists and routes without a code branch.
    if 'legal' not in reg['profiles']:
        fails.append('legal profile missing (it must be addable as pure data)')
    if profile_for('legal') is profile_for('nonexistent-domain'):
        fails.append('legal did not resolve to its own row (or unknown domain did not fall back)')

    print('SELF-TEST:', 'PASS — all data invariants hold' if not fails else 'FAIL')
    for f in fails:
        print('  x', f)
    return 1 if fails else 0


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════════════════════════

# The task-72 question. The ONLY place a topic enters this program is HERE, as the question string —
# and it is turned into an eligibility policy + routing terms by research_contract.compile_contract,
# the SAME compiler the pipeline uses. No topic constant lives in any scorer.
_TASK72_QUESTION = ('Please write a literature review on the restructuring impact of Artificial '
                    'Intelligence (AI) on the labor market. Focus on how AI, as a key driver of the '
                    'Fourth Industrial Revolution, is causing significant disruptions and affecting '
                    'various industries. Ensure the review only cites high-quality, English-language '
                    'journal articles.')

# Fallback routing terms for topical_relevance (a WEIGHT, never a gate) IF the deterministic contract
# compile yields none (the term extractor is LLM-backed; offline it may return an empty core set). The
# eligibility GATE never depends on this — it comes from the compiled SourcePolicy below.
_FALLBACK_TERMS = ['ai', 'artificial intelligence', 'labor', 'labour', 'employment', 'job', 'work',
                   'automation', 'wage', 'skill', 'task', 'robot', 'technology', 'occupation',
                   'industry', 'displacement', 'productivity']


def compile_question_inputs(question: str) -> tuple[dict, list[str], str]:
    """Turn the QUESTION into the two things weighting needs — via the real contract compiler.
    -> (eligibility_policy_dict, routing_terms, provenance_note)

    The eligibility policy (the GATE) is read straight off the compiled SourcePolicy: peer-reviewed-
    only, languages, and — because the question says "ONLY cites" — hard strictness. Routing terms
    (the topical_relevance WEIGHT) come from the compiled core concepts, with a disclosed fallback.
    """
    try:
        from research_contract import compile_contract
        c = compile_contract(question, question_id=72, use_llm=False)
        sp = getattr(c, 'source_policy', None)
        policy = {
            'peer_reviewed_only': bool(getattr(sp, 'peer_reviewed_only', False)),
            'languages': list(getattr(sp, 'languages', []) or []),
            'quality_bar': getattr(sp, 'quality_bar', '') or '',
            # "only cites" -> a HARD 'only' constraint (peer_reviewed_only is set from that phrasing).
            'strictness': 'only' if getattr(sp, 'peer_reviewed_only', False) else 'prefer',
        }
        terms = []
        for t in (getattr(c, 'core_concepts', []) or []):
            terms.append(getattr(t, 'label', ''))
            terms += list(getattr(t, 'aliases', []) or [])
        terms = [t for t in terms if t]
        if terms:
            return policy, terms, 'policy + terms from research_contract.compile_contract'
        return policy, list(_FALLBACK_TERMS), ('policy from compiled SourcePolicy; routing terms fell '
                                               'back to the question concepts (LLM term extractor off)')
    except Exception as e:                            # never let the demo die on the compiler
        return (dict(peer_reviewed_only=True, languages=['English'], strictness='only',
                     quality_bar='high-quality'),
                list(_FALLBACK_TERMS), f'contract compile unavailable ({type(e).__name__}); using floor')


def main() -> int:
    ap = argparse.ArgumentParser(description='Multidimensional weighting: rank the corpus OLD (raw '
                                             'citations) vs NEW (the vector), side by side.')
    ap.add_argument('--offline', action='store_true', help='do not hit the network (influence -> UNKNOWN)')
    ap.add_argument('--self-test', action='store_true', help='run the DATA-invariant self-test only')
    ap.add_argument('--domain', default='economics', help='domain profile for the main corpus')
    ap.add_argument('--no-generality', action='store_true', help='skip the clinical/legal/thin proof')
    ap.add_argument('--current-year', type=int, default=2026)
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    if not CORPUS_PATH.exists():
        print(f'corpus not found at {CORPUS_PATH}', file=sys.stderr)
        return 2
    rows = json.loads(CORPUS_PATH.read_text())
    policy, terms, prov_note = compile_question_inputs(_TASK72_QUESTION)
    print(f'Loaded {len(rows)} works from {CORPUS_PATH.name}. '
          f'Probing OpenAlex ({"OFFLINE" if args.offline else "live, cached"}) for '
          f'field+age-normalized influence via acquisition.Acquirer ...')
    print(f'Eligibility gate ({prov_note}): peer_reviewed_only={policy["peer_reviewed_only"]}, '
          f'languages={policy["languages"]}, strictness={policy["strictness"]!r}.')

    scored, ctx, probes = rank_corpus(rows, domain=args.domain, offline=args.offline,
                                      policy=policy, question_terms=terms,
                                      current_year=args.current_year)
    n_probed = sum(1 for p in probes.values() if p.get('outcome') == 'RESPONDED')
    print(f'OpenAlex: {n_probed}/{len(rows)} works scored; the rest -> influence UNKNOWN (never 0). '
          f'Authors clustered: max author appears in '
          f'{max(ctx.author_counts.values()) if ctx.author_counts else 0} works.')

    print_old_vs_new(scored, domain=args.domain, title='OUR CORPUS — raw citations (OLD) vs the vector (NEW)')
    _explain_top_movers(scored)

    if not args.no_generality:
        run_generality_proof(args.offline)

    print(f'\n{"="*100}')
    rc = self_test()
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
