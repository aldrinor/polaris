"""Attribution-origin provenance guard for the faithfulness engine.

Root cause (mis-attribution, "correctness is not faithfulness"): a report claim
that names an explicit finder / actor ("International Labour Organization and
Poland's National Research Institute found that 3.5% of men's jobs...") can be
cited to a source that merely RE-REPORTS the finding (e.g. a UN Regional
Information Centre article on ``unric.org``) rather than the source that
PRODUCED it. Every existing faithfulness gate PASSES because the pipeline
verifies TEXT CONTAINMENT / ENTAILMENT, never PROVENANCE ORIGIN: the secondary
source's fetched span verbatim restates the attribution clause, so strict_verify
(evidence-id-in-pool, span-bounds, numeric-in-span, content-overlap) and the NLI
entailment judge all clear it. The one attribution-style guard that exists
(M-25a ``extract_trial_names``) is scoped to clinical-trial acronyms only. There
is no point in the pipeline that (a) extracts the named finder from an
"<ORG> found/reported/estimated Y" sentence and (b) checks whether the CITED
SOURCE'S IDENTITY IS that actor (primary) versus merely re-reports it
(secondary).

This module is an **ADDITIVE, DISCLOSURE-ONLY** leg layered on top of
``verify_sentence_provenance`` (mirrors the existing ``overstatement_guard`` /
``shell_detector`` / ``_detect_unhedged_superlative`` additive patterns). Per the
WEIGHT / WITHHOLD-DISCLOSE / CONSOLIDATE architecture DNA (CLAUDE.md §-1.3):

  * It NEVER drops a sentence, NEVER fails ``is_verified``, NEVER touches
    strict_verify / NLI / D8. It ONLY ever APPENDS a ``soft_warning`` disclosure
    label ("attribution via a source whose publisher identity does not match the
    named finder"). This TIGHTENS faithfulness (surfaces a new provenance-quality
    label) without relaxing any existing gate and without a hard corpus drop.
  * It is HIGH-PRECISION and FAIL-OPEN on ambiguity: it fires ONLY when the
    claim names a recognizable ORGANIZATIONAL finder (org-keyword phrase or a
    3-6-letter ALL-CAPS acronym) via an attribution verb AND NONE of the cited
    sources' publisher DOMAIN identities match that finder. When a cited source's
    publisher identity cannot be determined from its domain (bare gov TLD, a DOI
    resolver, an opaque aggregator host), the leg stays INERT — we cannot rule out
    that the opaque source IS the actor, so we never flag.

Matching is done against the cited source's DOMAIN (its publisher identity),
NOT its title/body: a re-reporting article's headline and body naturally restate
the primary org's name, so matching those would suppress the exact case we target.

Research grounding (2025-2026 frontier gap; this is not a solved problem):
  - Wallat et al. (UvA, 2025) "Correctness is not Faithfulness in RAG Attributions"
  - "Cited but Not Verified" (arXiv 2605.06635, 2026)
  - DeepTRACE (arXiv 2509.04499) — cite accuracy 40-80%, partly attribution to
    sources that merely restate.
  - CiteGuard (arXiv 2510.17853, 2025) — retrieval-augmented citation validation.
"""

from __future__ import annotations

import os
import re
from src.polaris_graph.settings import resolve

# ─────────────────────────────────────────────────────────────────────────────
# Env flag (LAW VI — named, env-gated). Default ON: this is faithfulness-
# TIGHTENING (it only ever ADDS a disclosure soft-warning, never a drop). Setting
# the flag to a falsy value reverts to byte-identical pre-guard behaviour (no
# extra soft-warning emitted).
# ─────────────────────────────────────────────────────────────────────────────
_TRUE_TOKENS = frozenset({"1", "true", "yes", "on", "enforce", "warn"})


def attribution_origin_guard_enabled() -> bool:
    """Whether the attribution-origin disclosure leg is active (default ON)."""
    return resolve("PG_ATTRIBUTION_ORIGIN_GUARD").strip().lower() in _TRUE_TOKENS


# ─────────────────────────────────────────────────────────────────────────────
# Finder / actor extraction.
# ─────────────────────────────────────────────────────────────────────────────
# Attribution verbs — the strong signal that the preceding proper-noun phrase is
# being named as the ORIGINATOR of the finding ("<ORG> found/reported/estimated
# that ..."). Present + past tense.
_ATTRIBUTION_VERB = (
    r"(?:found|finds|reported|reports|estimated|estimates|showed|shows"
    r"|concluded|concludes|determined|determines|projected|projects"
    r"|calculated|calculates|observed|observes|noted|notes|stated|states"
    r"|announced|announces|published|publishes|warned|warns|predicted|predicts"
    r"|revealed|reveals|documented|documents|identified|identifies"
    r"|confirmed|confirms)"
)

# A single proper-noun token: a Capitalized word (allowing internal
# apostrophe / ampersand / period / hyphen — "Poland's", "AT&T", "U.S.").
_CAP_TOKEN = r"[A-Z][A-Za-z0-9'’&.\-]*"
# Lowercase connectors that legitimately sit INSIDE an organization name
# ("Bureau of Labor Statistics", "Centers for Disease Control and Prevention").
_CONNECTOR = r"(?:of|for|the|and|&|de|del|la|von|van|und|et|à|da|do)"
# A proper-noun run: one cap token followed by any number of connector-or-cap
# tokens. Greedy so it captures the whole "<Org> and <Org>" run before the verb.
_PROPER_RUN = rf"{_CAP_TOKEN}(?:\s+(?:{_CONNECTOR}|{_CAP_TOKEN}))*"

_FINDER_RE = re.compile(rf"\b({_PROPER_RUN})\s+{_ATTRIBUTION_VERB}\b")

# Org-type keywords: a proper-noun run that contains one of these is an
# INSTITUTION (not a person / place / generic capitalized phrase). Precision
# guard — we only treat the run as an organizational finder when it self-declares
# as an institution OR carries a standalone ALL-CAPS acronym token.
_ORG_KEYWORDS = frozenset({
    "organization", "organisation", "organizations", "organisations",
    "institute", "institutes", "institution", "institutions",
    "university", "universities", "college", "colleges", "school", "schools",
    "department", "departments", "agency", "agencies", "ministry", "ministries",
    "bureau", "bureaus", "association", "associations", "foundation",
    "foundations", "commission", "commissions", "council", "councils",
    "laboratory", "laboratories", "office", "offices", "fund", "funds",
    "bank", "banks", "center", "centre", "centers", "centres",
    "company", "companies", "corporation", "corporations", "committee",
    "committees", "society", "societies", "administration", "administrations",
    "authority", "authorities", "board", "boards", "consortium", "consortia",
    "coalition", "coalitions", "union", "unions", "federation", "federations",
    "network", "networks", "observatory", "programme", "program",
})

# Generic words that appear in many org names — stripped from the DISTINCTIVE-word
# signature so matching keys on the org-specific token(s) ("labour"->generic,
# "poland"->distinctive). The ACRONYM builder still uses ALL significant words.
_GENERIC_ORG_WORDS = frozenset(_ORG_KEYWORDS) | frozenset({
    "national", "international", "research", "global", "world", "general",
    "federal", "state", "states", "united", "european", "american", "americas",
    "statistics", "health", "science", "sciences", "economic", "economics",
    "monetary", "labor", "labour", "development", "affairs", "human", "social",
    "public", "policy", "data", "regional", "central", "advanced", "applied",
    "medical", "clinical", "technology", "technical", "environmental", "energy",
    "finance", "financial", "trade", "labour", "education", "population",
})

# All-caps acronym token (3-6 letters), e.g. "WHO", "ILO", "IMF", "OECD",
# "NBER". 2-letter acronyms ("US", "UN", "EU") are excluded — too noisy.
_ALLCAPS_ACRONYM_RE = re.compile(r"\b[A-Z]{3,6}\b")

# Splitters between co-attributed organizations in a run.
_ORG_SPLIT_RE = re.compile(r"\s+(?:and|&)\s+|\s*[,;/]\s*", re.IGNORECASE)


def _significant_words(phrase: str) -> list[str]:
    """Capitalized / acronym words in ``phrase`` (drops lowercase connectors)."""
    out: list[str] = []
    for tok in re.findall(r"[A-Za-z][A-Za-z0-9'’&.\-]*", phrase):
        low = tok.lower().strip(".'’&-")
        if not low:
            continue
        # Keep a token as significant when it is Capitalized or ALL-CAPS
        # (connectors like "of"/"and"/"the" are lowercase -> dropped).
        if tok[0].isupper():
            out.append(tok)
    return out


def _acronym_of(phrase: str) -> str:
    """First-letter acronym over the significant words of ``phrase`` (lowercased).

    "International Labour Organization" -> "ilo"; "World Health Organization" ->
    "who"; "Poland's National Research Institute" -> "pnri"; "Bureau of Labor
    Statistics" -> "bls" (the connector "of" is skipped).
    """
    letters = [w[0].lower() for w in _significant_words(phrase) if w[:1].isalpha()]
    return "".join(letters)


def _distinctive_words(phrase: str) -> set[str]:
    """Org-specific content words (>=4 chars, minus generic org words)."""
    out: set[str] = set()
    for w in _significant_words(phrase):
        low = re.sub(r"[^a-z]", "", w.lower())
        if len(low) >= 4 and low not in _GENERIC_ORG_WORDS:
            out.add(low)
    return out


def _phrase_is_org(phrase: str) -> bool:
    """A run qualifies as an ORGANIZATIONAL finder when it self-declares as an
    institution (org keyword) OR carries a 3-6-letter ALL-CAPS acronym token."""
    lowered = {re.sub(r"[^a-z]", "", w.lower()) for w in _significant_words(phrase)}
    if lowered & _ORG_KEYWORDS:
        return True
    return bool(_ALLCAPS_ACRONYM_RE.search(phrase))


def _actor_signatures(run: str) -> tuple[set[str], set[str]]:
    """Build the (acronyms, distinctive_words) match signature for a finder run.

    Splits the run on inter-org connectors ("and"/"&"/","/";") into per-org
    pieces AND also keeps the WHOLE-run acronym as an extra candidate, so an
    org whose own name contains "and" ("Food and Drug Administration" -> "fda",
    "Centers for Disease Control and Prevention") is still matched by its true
    acronym even though the split mangled it. Only ORG-qualifying pieces (or the
    whole run when it qualifies) contribute; a signature key is used only when it
    is discriminating (acronym >=3 chars, distinctive word >=4 chars).
    """
    acronyms: set[str] = set()
    distinctive: set[str] = set()

    pieces = [p.strip() for p in _ORG_SPLIT_RE.split(run) if p and p.strip()]
    any_org = False
    for piece in pieces:
        if not _phrase_is_org(piece):
            continue
        any_org = True
        acr = _acronym_of(piece)
        if len(acr) >= 3:
            acronyms.add(acr)
        distinctive |= _distinctive_words(piece)
        # Standalone ALL-CAPS acronym tokens are themselves keys ("WHO"->who).
        for m in _ALLCAPS_ACRONYM_RE.finditer(piece):
            acronyms.add(m.group(0).lower())

    # Whole-run acronym rescue for internal-"and" org names.
    if _phrase_is_org(run):
        any_org = True
        whole = _acronym_of(run)
        if 3 <= len(whole) <= 8:
            acronyms.add(whole)
        distinctive |= _distinctive_words(run)

    if not any_org:
        return set(), set()
    return acronyms, distinctive


# ─────────────────────────────────────────────────────────────────────────────
# Cited-source publisher identity (domain-only).
# ─────────────────────────────────────────────────────────────────────────────
# TLD / opaque host labels stripped when reducing a domain to its publisher
# identity token(s). After stripping, an EMPTY signature means the publisher
# cannot be determined from the URL (bare gov TLD, a DOI resolver, an opaque
# aggregator) -> the guard stays INERT for that source (fail-open).
_HOST_STOP_LABELS = frozenset({
    # generic + country TLDs
    "com", "org", "net", "int", "edu", "gov", "io", "co", "info", "biz",
    "uk", "us", "ca", "au", "eu", "de", "fr", "es", "it", "nl", "se", "no",
    "pl", "ru", "cn", "jp", "in", "br", "za", "ch", "be", "at", "dk", "fi",
    "ie", "nz", "mx", "kr", "sg", "hk", "tw", "gr", "pt", "cz", "ro", "hu",
    # non-identifying subdomain labels
    "www", "www2", "www3", "web", "en", "m", "mobile", "amp",
    # opaque resolvers / aggregators (publisher identity not in the host)
    "doi", "dx", "ncbi", "pubmed", "pmc", "arxiv", "ssrn", "researchgate",
    "jstor", "semanticscholar", "biorxiv", "medrxiv", "preprints", "zenodo",
    "figshare", "scholar", "sci", "hub",
})


def _domain_signature(url: str) -> set[str]:
    """Publisher-identity token set from a URL's host, or empty if opaque.

    "https://unric.org/en/..." -> {"unric"}; "https://ilo.org/..." -> {"ilo"};
    "https://www.who.int/..." -> {"who"}; "https://bls.gov/..." -> {"bls"};
    "https://gov.pl/..." -> set() (bare gov TLD -> opaque); "https://doi.org/10..."
    -> set() (resolver -> opaque).
    """
    if not url:
        return set()
    host = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://", "", url.strip())
    host = host.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    host = host.split("@")[-1].split(":", 1)[0].lower()
    if not host:
        return set()
    labels = [lbl for lbl in host.split(".") if lbl]
    sig = {lbl for lbl in labels if lbl not in _HOST_STOP_LABELS and len(lbl) >= 2}
    return sig


def _actor_matches_domain(
    acronyms: set[str], distinctive: set[str], domain_sig: set[str]
) -> bool:
    """Whether the finder signature is present in a cited source's domain.

    Lenient toward a MATCH (precision on the fires we DO make): an acronym key
    matches a domain token when either contains the other; a distinctive word
    matches when either contains the other. If NO cited source matches, the
    disclosure fires.
    """
    for tok in domain_sig:
        for acr in acronyms:
            if acr == tok or acr in tok or tok in acr:
                return True
        for word in distinctive:
            if word == tok or word in tok or tok in word:
                return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Public leg API. Returns a DISCLOSURE reason string (soft-warning) or None.
# ─────────────────────────────────────────────────────────────────────────────
def attribution_origin_reason(claim: str, cited_source_urls: list[str]) -> str | None:
    """Return a DISCLOSURE reason if the claim names an organizational finder that
    none of the cited sources' publisher domains match.

    Fires only when ALL hold (HIGH-PRECISION, FAIL-OPEN on ambiguity):
      - the leg is enabled (PG_ATTRIBUTION_ORIGIN_GUARD, default ON),
      - the claim names a recognizable ORGANIZATIONAL finder (org-keyword phrase
        or a 3-6-letter ALL-CAPS acronym) immediately before an attribution verb,
      - EVERY cited source has a determinable publisher domain (no opaque host —
        an opaque host makes us unable to rule out that IT is the actor -> inert),
      - and NONE of those domains matches the finder's acronym / distinctive-word
        signature.
    Otherwise returns None (inert — no false disclosure). DISCLOSURE-only: the
    caller APPENDS a soft-warning; this NEVER drops a sentence, NEVER changes a
    verdict, NEVER touches strict_verify / NLI / D8 (§-1.3).
    """
    if not attribution_origin_guard_enabled():
        return None
    if not claim or not cited_source_urls:
        return None

    domain_sigs = [_domain_signature(u) for u in cited_source_urls]
    # FAIL-OPEN: if any cited source's publisher identity is opaque (empty
    # signature — bare TLD / resolver / aggregator), we cannot assert it is NOT
    # the finder. Stay inert.
    if any(not sig for sig in domain_sigs):
        return None

    fired_actors: list[str] = []
    for m in _FINDER_RE.finditer(claim):
        run = m.group(1).strip()
        acronyms, distinctive = _actor_signatures(run)
        if not acronyms and not distinctive:
            continue  # no discriminating signature -> ambiguous -> skip (fail-open)
        matched = any(
            _actor_matches_domain(acronyms, distinctive, sig) for sig in domain_sigs
        )
        if not matched:
            fired_actors.append(run)

    if not fired_actors:
        return None

    actors = "|".join(dict.fromkeys(a[:80] for a in fired_actors))
    domains = ",".join(
        dict.fromkeys(sorted(t for sig in domain_sigs for t in sig))
    )[:120]
    return f"attribution_origin_unverified:actors={actors}:cited_domains={domains}"
