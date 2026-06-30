"""
Access Bypass Mechanisms (Research Access)
===========================================
Provides research access through multiple channels.

ETHICAL GUIDELINES:
- Only use for legitimate research purposes
- Respect rate limits and fair use policies
- Prefer legal open access when available
- Document all access methods used

Supports:
- Crawl4AI (free, local Playwright-based markdown extraction)
- Jina Reader (primary markdown extraction)
- Firecrawl (secondary markdown extraction)
- robots.txt bypass (for research indexing)
- Paywall detection and alternatives
- Archive.org fallback
- Institutional proxy support
"""

import asyncio
import html
import logging
import os
import re
import sys
import threading
import time as _time_module
import weakref
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _safe_log_str(text: str, max_len: int = 200) -> str:
    """Sanitize text for Windows console logging (cp1252 safe).

    Unicode chars like arrows, Greek letters, and math symbols cause
    UnicodeEncodeError on Windows cp1252 console handler. This replaces
    non-encodable chars with '?' before logging.
    """
    truncated = text[:max_len]
    try:
        truncated.encode("cp1252")
        return truncated
    except (UnicodeEncodeError, UnicodeDecodeError):
        return truncated.encode("ascii", errors="replace").decode("ascii")

# FIX-BR: Suppress Brotli Accept-Encoding to prevent decompression failures.
# aiohttp advertises `br` (Brotli) by default but cannot decode it without the
# `brotli` package installed, causing 100% failure rate on servers that honour it.
# Explicitly request only gzip/deflate across ALL aiohttp sessions.
_NO_BROTLI_HEADERS = {"Accept-Encoding": "gzip, deflate"}

# FIX-JINA: Jina concurrency semaphore (initialized lazily in _try_jina_reader)
_jina_semaphore: "asyncio.Semaphore | None" = None
# I-arch-007 (#1264): Jina per-loop semaphore map — same cross-loop fix as NCBI/crawl4ai (#1227).
# The single module-global below bound to the first acquiring loop and raised the cross-loop
# RuntimeError when the post-generation contract-frame fetch ran in a different loop than retrieval.
_jina_perloop_semaphores: "weakref.WeakKeyDictionary[Any, asyncio.Semaphore]" = (
    weakref.WeakKeyDictionary()
)

# RC-9: Circuit breaker for fetch providers.
# After N consecutive failures, skip the provider for a cooldown period.
_jina_consecutive_failures: int = 0
_jina_circuit_open_until: float = 0.0
_firecrawl_consecutive_failures: int = 0
_firecrawl_circuit_open_until: float = 0.0
# I-fetch-004 (#1185): circuit breaker for the PAID Zyte fallback. Mirrors the
# firecrawl/jina breaker so a Zyte outage cannot fire N doomed PAID calls on a
# ~1000-URL run. Shares the same threshold/cooldown constants below.
_zyte_consecutive_failures: int = 0
_zyte_circuit_open_until: float = 0.0
# FIX-G: Raised defaults — threshold 5→8, cooldown 60→120s for transient tolerance
_CIRCUIT_BREAKER_THRESHOLD = int(os.getenv("PG_CIRCUIT_BREAKER_THRESHOLD", "8"))
_CIRCUIT_BREAKER_COOLDOWN = float(os.getenv("PG_CIRCUIT_BREAKER_COOLDOWN", "120.0"))

# I-fetch-004 (#1185): Zyte paid-fallback telemetry + tunables (LAW VI — no
# hard-coded thresholds; every knob is env-overridable). These counters are
# separate from the circuit-breaker failure counter above: attempts/successes
# track usage, the breaker tracks consecutive failures.
_zyte_fallback_attempts: int = 0
_zyte_fallback_success: int = 0
# Per-call HTTP timeout for both the cheap (httpResponseBody) and escalated
# (browserHtml) Zyte requests.
_ZYTE_TIMEOUT = float(os.getenv("PG_ZYTE_TIMEOUT", "60.0"))
# Minimum usable-content length. Shared by the escalation trigger (a cheap
# result shorter than this escalates to browserHtml) and the final success
# gate (content shorter than this is rejected). Mirrors the 500-char floor used
# by the PDF/crawl4ai paths.
_ZYTE_MIN_CONTENT_CHARS = int(os.getenv("PG_ZYTE_MIN_CONTENT_CHARS", "500"))
# Zyte API endpoint (override only for testing against a mock server).
_ZYTE_API_ENDPOINT = os.getenv("PG_ZYTE_API_ENDPOINT", "https://api.zyte.com/v1/extract")

# F14 (GH #1245 / D9, D10): paywalled-publisher hosts. The free fetch chain
# (Crawl4AI/Jina/Firecrawl) returns a short abstract SHELL for these hosts; they
# are routed to Zyte FIRST when PG_ZYTE_PAYWALL_FIRST=1 and a key is present, and
# a LOUD warning fires when the key is absent (the Zyte fallback is otherwise a
# silent no-op). Env-extendable via PG_PAYWALL_PUBLISHER_HOSTS (comma-sep,
# additive). Never a hard DROP — only a routing + loud-warning signal.
_PAYWALL_PUBLISHER_HOSTS = (
    "sciencedirect.com",
    "elsevier.com",
    "linkinghub.elsevier.com",
    "onlinelibrary.wiley.com",
    "link.springer.com",
    "nature.com",
    "tandfonline.com",
    "journals.sagepub.com",
    "academic.oup.com",
    "nejm.org",
    "thelancet.com",
    "jamanetwork.com",
    "bmj.com",
    "cell.com",
    "ahajournals.org",
    "annualreviews.org",
)


def _is_paywall_publisher_host(url: str) -> bool:
    """F14: True iff the URL host is a known paywalled publisher (substring
    match on the lowercased netloc; default list + env-additive). Pure, no
    network."""
    if not url:
        return False
    try:
        from urllib.parse import urlparse as _urlparse
        netloc = (_urlparse(url).netloc or "").lower()
    except Exception:
        return False
    if not netloc:
        return False
    hosts = list(_PAYWALL_PUBLISHER_HOSTS)
    extra = os.getenv("PG_PAYWALL_PUBLISHER_HOSTS", "").strip()
    if extra:
        hosts.extend(h.strip().lower() for h in extra.split(",") if h.strip())
    return any(h in netloc for h in hosts)


# ---------------------------------------------------------------------------
# I-beatboth-011 junk-SOURCE screen (#1289).
#
# A high-precision, faithfulness-NEUTRAL screen for non-source pages that
# should never be cited / listed in the bibliography / surfaced as a per-claim
# corroborator. This drops ONLY junk — it never drops a real journal /
# repository / gov / news source (§-1.3 keep-all for REAL sources). Two signals,
# both deliberately narrow:
#
#   (1) HOST allowlist of homework-help / Q&A-not-source domains. These are NOT
#       primary sources; a Chegg "Solved ..." page stands in for a real paper but
#       is paywalled homework chrome. The list is exact-suffix matched (host == d
#       OR host endswith "." + d) so "notchegg.com" or a real domain that merely
#       CONTAINS the token is never caught. Env-additive via
#       PG_JUNK_SOURCE_HOSTS (comma-sep). Repositories/journals/news/gov are NOT
#       on the list — openalex.org, arxiv.org, pubmed, doi.org, oecd.org, etc. all
#       pass the host screen untouched.
#
#   (2) ERROR-SHELL text signatures: a fetched body that IS an error/interstitial
#       page ("doesn't work properly without JavaScript", "Page Not Found",
#       "Access Denied", a CAPTCHA stub, ...). A real article can quote such a
#       phrase in prose, so — mirroring is_boilerplate_or_nonassertional's
#       length-gate — a TEXT match drops the source ONLY when the signature
#       DOMINATES the body: the body is short AND the residual after removing the
#       signature is trivially small. The banked drb_72 junk is a 117-char body
#       that is verbatim the JS-error shell; a 1027-char real abstract on the same
#       host (openalex.org) is untouched.
#
# This is SOURCE-level input hygiene applied at corpus consumption, never a
# faithfulness verdict: strict_verify / NLI / 4-role / span-grounding are
# untouched. A claim left with only a junk corroborator falls to its other
# corroborators or to the honest strict_verify gap path (no fabrication).
# ---------------------------------------------------------------------------

# Homework-help / Q&A-not-source hosts. EXACT domain suffixes only (never a bare
# word). Env-additive via PG_JUNK_SOURCE_HOSTS. Kept deliberately tiny + high
# precision — these are confirmed non-source pages, not "low quality" sources
# (low-quality real sources STAY at low weight per §-1.3).
#
# I-beatboth-011 drb_78 extension (#1289): social / login / video-platform hosts
# that are NON-EVIDENCE pages (a post / login wall / flashcard set / video chrome),
# never a citable source. The §-1.1 audit of drb_78 found facebook.com (3x),
# reddit.com, linkedin.com, quizlet.com cited as "sources" — the facebook posts
# even rendered their `[Log In](https://www.facebook.com/login/device-based/...)`
# wall as a section HEADER. These are EXACT-suffix matched (host == d OR host
# endswith '.' + d) so a real host merely CONTAINING the token is NEVER caught —
# e.g. ``oatext.com`` / ``exponent.com`` do not end with ``.x.com`` and are not
# ``== x.com``, so they pass untouched; a real journal/gov/news source is never
# on this list. A real journal whose fetched BODY happens to carry a social
# share-bar / login-CTA (e.g. a BMJ article body with ``* [Log In](...)``) is NOT
# host-dropped — only the chrome STRING is stripped by ``_INLINE_SOCIAL_CHROME_RE``
# (faithfulness-preserving: the real source stays, the page furniture goes).
_JUNK_SOURCE_HOSTS = (
    # Homework-help / Q&A-not-source.
    "chegg.com",
    "coursehero.com",
    "studocu.com",
    "quizlet.com",
    "scribd.com",
    "brainly.com",
    "brainly.in",
    "sparknotes.com",
    "bartleby.com",
    # Social / login / non-evidence pages (drb_78). A post or login wall is not a
    # citable source; sometimes it reports a real journal, but the JOURNAL is the
    # source (retrieved on its own host at full weight), not the social repost.
    "facebook.com",
    "fb.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "reddit.com",
    "linkedin.com",
    "pinterest.com",
    "tiktok.com",
    "tumblr.com",
    "threads.net",
    "t.co",
    # Video platforms (player chrome, not assertional source text).
    "youtube.com",
    "youtu.be",
)

# Error-shell / interstitial signatures. A body DOMINATED by one of these is a
# fetch-failure shell, not a source. High-precision multi-word phrases a real
# clinical/economic sentence (any language) does not carry as its WHOLE body.
# At least one PRIMARY signature must be present for a body to be flagged.
_ERROR_SHELL_SIGNATURES = (
    "doesn't work properly without javascript",
    "does not work properly without javascript",
    "enable javascript and cookies to continue",
    "please enable javascript",
    "your browser is not supported",
    "your browser is no longer supported",
    "page not found",
    "404 not found",
    "access denied",
    "please verify you are a human",
    "verify you are human",
    "performing security verification",
    "just a moment",
    # CAPTCHA / anti-bot challenge interstitials (drb_78 audit: biorxiv CAPTCHA,
    # u-picardie Anubis bot-wall both cited as findings). High-precision full
    # phrases a real clinical/economic body never carries as its whole content.
    "this question is for testing whether",
    "making sure you're not a bot",
    "you are a human visitor and to prevent automated spam",
    # .gov fetch-navigation chrome (drb_78 audit: ncbi span was the .gov masthead,
    # not the article). The dominance test still keeps a real .gov article whose
    # body merely STARTS with this masthead (residual content survives stripping).
    "official websites use .gov",
    "share sensitive information only on official, secure websites",
    # Site-outage / maintenance interstitials (drb_78 audit: stanfordhealthcare
    # outage notice rendered as prose).
    "users may be experiencing issues",
    "we are working closely with our technical teams",
)

# SECONDARY error-shell chrome phrases. These commonly SURROUND a primary
# signature in a real interstitial body ("We're sorry but our site ... Please
# enable it to continue."). They are NOT sufficient alone (they can appear in
# real prose), but they ARE stripped — along with every primary signature —
# before the residual-content dominance test, so a body that is ONLY shell
# chrome leaves no distinctive content words, while a real article wrapped around
# an error phrase keeps its substantive words and is NOT flagged.
_ERROR_SHELL_CHROME = (
    "we're sorry but",
    "we are sorry but",
    "please enable it to continue",
    "please enable cookies",
    "please try again",
    "to continue",
    "enable it to continue",
    "enabled",
    "javascript",
    "cookies",
    "browser",
    "website",
    "research website",
)

# WAF / HTTP-error CO-TOKENS (Codex P1-1, #1289). A genuine block / interstitial
# page carries one of these alongside the primary signature — exactly the M-23d
# `_is_paywalled` http_error_signals posture (cloudflare-blocked, rate-limit, a
# bare HTTP status, a CAPTCHA/security-verification stub, a Jina "returned error"
# line). When ANY of these co-occurs with a primary signature in a SHORT body the
# body is unambiguously a fetch-failure shell — no coverage math needed. A real
# source TITLE / snippet that merely CONTAINS "access denied" / "just a moment"
# does NOT carry a WAF co-token, so it stays on the coverage path (which keeps it
# unless the signature DOMINATES). Whole-substring, lowercased; high-precision
# multi-word/structured so a real sentence never trips one.
_ERROR_SHELL_WAF_COTOKENS = (
    "cloudflare",
    "cf-ray",
    "rate limit",
    "rate limited",
    "403 forbidden",
    "404 not found",
    "500 internal server",
    "502 bad gateway",
    "503 service unavailable",
    "504 gateway timeout",
    "returned error",
    "target url returned error",
    "captcha",
    "performing security verification",
    "verify you are a human",
    "ddos protection",
    "checking your browser before",
)

# Codex P1-1 (#1289): COVERAGE-dominance threshold + minimum-content floor for
# the error-shell text screen. The pre-fix gate flagged ANY short (<=400-char)
# body containing a primary signature whose residual was <=3 distinctive words —
# which over-strips a real source whose short TITLE / snippet merely CONTAINS a
# generic phrase ("Access Denied: A Memoir", a paper titled "Just a Moment ...").
#
# THE FIX (high-precision, conservative — drops FEWER, never more): on the
# no-co-token path a body is a shell ONLY when the error signature DOMINATES the
# body — the stripped-signature COVERAGE ratio is >= _ERROR_SHELL_MIN_COVERAGE of
# the body's alphabetic content AND the body carries enough total content
# (>= _ERROR_SHELL_MIN_DOMINANCE_ALPHA alpha-chars) for "dominance" to be
# meaningful. A bare 2-3-word title ("Access Denied", "Just a Moment") is below
# the content floor and is KEPT; a substantive titled body ("Access Denied:
# barriers to healthcare ...") is below the coverage ratio and is KEPT; the
# banked drb_72 JS-error shell (~0.88 coverage, 96 alpha-chars) still drops. The
# residual<=3-words guard is RETAINED as the outer gate. Both env-overridable
# (LAW VI); a malformed value falls back to the conservative default.
_ENV_ERROR_SHELL_MIN_COVERAGE = "PG_JUNK_SOURCE_SHELL_MIN_COVERAGE"
_DEFAULT_ERROR_SHELL_MIN_COVERAGE = 0.80
_ENV_ERROR_SHELL_MIN_DOMINANCE_ALPHA = "PG_JUNK_SOURCE_SHELL_MIN_ALPHA"
_DEFAULT_ERROR_SHELL_MIN_DOMINANCE_ALPHA = 40

# A body longer than this is structurally NOT an error shell — a real article
# body. The error-shell text screen only fires on a SHORT body the signature
# dominates. Env-overridable (LAW VI); fail-loud on a non-int.
_ENV_JUNK_SHELL_MAX_CHARS = "PG_JUNK_SOURCE_SHELL_MAX_CHARS"
_DEFAULT_JUNK_SHELL_MAX_CHARS = 400


# Codex P1-2 (#1289): public suffixes / bare TLDs that must NEVER be accepted as
# an env-provided junk host. A bare "com" / "org" / "edu" / "co.uk" as a suffix
# would suffix-match and DROP every real source on that TLD. The hardcoded locked
# list above is exact registrable domains and is NOT subject to this validation;
# ONLY PG_JUNK_SOURCE_HOSTS entries are validated.
_PUBLIC_SUFFIX_BLOCKLIST = frozenset({
    # Bare TLDs.
    "com", "org", "net", "edu", "gov", "mil", "int", "co", "io", "ai", "info",
    "biz", "name", "pro", "us", "uk", "ca", "au", "de", "fr", "jp", "cn", "in",
    "eu", "ac", "nz", "za", "br", "mx", "sg", "tr", "ar",
    # Multi-label public suffixes (Codex P1-2 #1289 expansion): a bare entry
    # here would suffix-match and DROP every real registrable domain under it.
    "gov.uk", "ac.uk", "co.uk", "org.uk",
    "com.br", "com.au", "net.au", "org.au", "gov.au", "edu.au",
    "co.in", "net.in", "org.in", "co.nz", "co.jp", "co.za",
    "com.cn", "com.mx", "com.sg", "com.tr", "com.ar", "com.co",
})

# Codex P1-2 (#1289): registry tokens that, when they are the FIRST label of a
# 2-label env host, mean the host is itself a public suffix (e.g. "com.br",
# "co.in") rather than a registrable domain. An env host must have a REAL
# registrable label in front of a public suffix to be accepted — beyond the
# explicit `_PUBLIC_SUFFIX_BLOCKLIST` this catches a multi-label suffix that
# slipped the hand list. A genuine junk host ("studymoose.com") has a real word
# ("studymoose") in front of "com", so it is still accepted.
_PUBLIC_SUFFIX_REGISTRY_LABELS = frozenset({
    "com", "org", "net", "edu", "gov", "co", "ac", "mil", "int",
    "gob", "go", "or", "ne", "ad",
})

# Codex P1-2 (#1289): known-real / scholarly registrable domains an env entry
# must NEVER be allowed to add to the junk-drop list (a fat-fingered
# PG_JUNK_SOURCE_HOSTS=doi.org would otherwise drop every DOI-resolved source).
# Exact registrable-domain match (a real *.gov / *.edu host is additionally
# protected structurally by `_env_junk_host_is_safe`).
_KNOWN_REAL_DOMAIN_BLOCKLIST = frozenset({
    "doi.org", "dx.doi.org",
    "ncbi.nlm.nih.gov", "pubmed.ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov",
    "nlm.nih.gov", "nih.gov",
    "arxiv.org", "biorxiv.org", "medrxiv.org", "ssrn.com",
    "openalex.org", "semanticscholar.org", "crossref.org", "datacite.org",
    "orcid.org", "core.ac.uk", "base-search.net", "doaj.org",
    "sciencedirect.com", "elsevier.com", "linkinghub.elsevier.com",
    "springer.com", "link.springer.com", "springeropen.com",
    "wiley.com", "onlinelibrary.wiley.com",
    "nature.com", "science.org", "sciencemag.org",
    "tandfonline.com", "sagepub.com", "journals.sagepub.com",
    "oup.com", "academic.oup.com", "cambridge.org", "jstor.org",
    "plos.org", "frontiersin.org", "mdpi.com", "bmj.com", "thelancet.com",
    "nejm.org", "jamanetwork.com", "cell.com", "pnas.org", "ahajournals.org",
    "oecd.org", "worldbank.org", "imf.org", "who.int", "un.org", "europa.eu",
    "bls.gov", "census.gov", "cdc.gov", "fda.gov", "nber.org", "ideas.repec.org",
    "repec.org", "researchgate.net", "scholar.google.com", "google.com",
    "wikipedia.org", "reuters.com", "nytimes.com", "bbc.com", "bbc.co.uk",
})


def _env_junk_host_is_safe(host: str) -> bool:
    """Codex P1-2 (#1289): True iff ``host`` is a VALID env-provided junk-host
    entry (safe to add to the suffix-drop rule).

    Rejects (so a bad env value can never drop real sources):
      - empty / no-dot tokens (a bare "com"/"org" is not a registrable domain),
      - a bare public suffix or TLD (``_PUBLIC_SUFFIX_BLOCKLIST``),
      - a multi-label public suffix NOT on the hand list: a leading-``*.``-stripped
        2-label host whose FIRST label is a registry token (``com.br``, ``co.in``,
        ``org.au``, ``net.au`` ...) has no real registrable label in front of a
        public suffix, so it would suffix-drop every real source under it,
      - a known-real / scholarly registrable domain (``_KNOWN_REAL_DOMAIN_BLOCKLIST``),
      - any ``*.gov`` / ``*.edu`` / ``*.int`` / ``*.mil`` host (gov/academic),
      - any ``*.ac.<tld>`` / ``*.edu.<tld>`` / ``*.gov.<tld>`` academic host.
    Accepts an arbitrary OTHER full registrable host (e.g. ``studymoose.com``,
    ``coursehero.org``) — the env-additive feature is preserved; only unsafe
    values are filtered. Pure, no network."""
    if not host or "." not in host:
        return False
    # Strip a leading wildcard label (``*.example.com`` => ``example.com``) so a
    # wildcarded public suffix can never sneak past the label-count checks.
    h = host.strip().lower().strip(".")
    if h.startswith("*."):
        h = h[2:]
    h = h.strip(".")
    if not h or "." not in h:
        return False
    if h in _PUBLIC_SUFFIX_BLOCKLIST:
        return False
    if h in _KNOWN_REAL_DOMAIN_BLOCKLIST:
        return False
    labels = h.split(".")
    tld = labels[-1]
    # Reject whole gov/academic/treaty TLDs (a *.gov / *.edu host is real).
    if tld in ("gov", "edu", "int", "mil"):
        return False
    # Reject academic second-level suffixes (e.g. *.ac.uk, *.edu.au, *.gov.au).
    if len(labels) >= 2 and labels[-2] in ("ac", "edu", "gov"):
        return False
    # Codex P1-2 (#1289) robustness beyond the hand list: a 2-label host whose
    # FIRST label is a registry token (com/org/net/co/ac/...) IS a public suffix
    # (``com.br``, ``co.in``, ``net.au``), not a registrable domain — reject so a
    # multi-label suffix missed from `_PUBLIC_SUFFIX_BLOCKLIST` can never drop
    # real sources. A real junk host has a true word label in front ("studymoose"
    # before "com"), so it survives this check.
    if len(labels) == 2 and labels[0] in _PUBLIC_SUFFIX_REGISTRY_LABELS:
        return False
    return True


def _junk_source_hosts() -> "tuple[str, ...]":
    """The junk-host suffix list (default + VALIDATED PG_JUNK_SOURCE_HOSTS additive).

    The hardcoded locked list (``_JUNK_SOURCE_HOSTS``) is authoritative and is NOT
    validated. Codex P1-2 (#1289): every PG_JUNK_SOURCE_HOSTS entry passes
    ``_env_junk_host_is_safe`` first — a bare public suffix / TLD / known-real or
    scholarly domain is silently ignored with a LAW-II warning so a bad env value
    can never suffix-drop real sources."""
    hosts = list(_JUNK_SOURCE_HOSTS)
    extra = os.getenv("PG_JUNK_SOURCE_HOSTS", "").strip()
    if extra:
        for raw in extra.split(","):
            cand = raw.strip().lower()
            if not cand:
                continue
            if _env_junk_host_is_safe(cand):
                hosts.append(cand)
            else:
                logger.warning(
                    "[ACCESS] P1-2: ignoring invalid PG_JUNK_SOURCE_HOSTS entry "
                    "%r (bare suffix / TLD / known-real domain would drop real "
                    "sources)", _safe_log_str(cand, 80),
                )
    return tuple(hosts)


def is_junk_source_host(url: str) -> bool:
    """True iff the URL host is a known homework-help / Q&A-not-source domain.

    Exact-suffix match on the lowercased netloc (host == d OR host endswith
    '.' + d) so a real domain merely CONTAINING a junk token is never caught.
    Pure, no network. Repositories / journals / gov / news are not on the list.
    """
    if not url:
        return False
    try:
        from urllib.parse import urlparse as _urlparse  # noqa: PLC0415
        netloc = (_urlparse(url).netloc or "").lower()
    except Exception:
        return False
    if not netloc:
        return False
    # Drop a leading "www." and any :port for the suffix comparison.
    host = netloc.split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return any(host == d or host.endswith("." + d) for d in _junk_source_hosts())


def _junk_shell_max_chars() -> int:
    """Body-length ceiling above which the error-shell text screen never fires."""
    raw = os.getenv(_ENV_JUNK_SHELL_MAX_CHARS)
    if raw is None or not raw.strip():
        return _DEFAULT_JUNK_SHELL_MAX_CHARS
    try:
        val = int(raw.strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{_ENV_JUNK_SHELL_MAX_CHARS}={raw!r} is not an integer "
            f"(junk error-shell body-length ceiling)"
        ) from exc
    return max(0, val)


def _error_shell_min_coverage() -> float:
    """Codex P1-1 (#1289): minimum signature COVERAGE ratio (0..1) for the
    no-co-token dominance path. A malformed / out-of-range value falls back to
    the conservative default (over-strip is worse than a recoverable leak)."""
    raw = os.getenv(_ENV_ERROR_SHELL_MIN_COVERAGE)
    if raw is None or not raw.strip():
        return _DEFAULT_ERROR_SHELL_MIN_COVERAGE
    try:
        val = float(raw.strip())
    except (TypeError, ValueError):
        return _DEFAULT_ERROR_SHELL_MIN_COVERAGE
    if not (0.0 < val <= 1.0):
        return _DEFAULT_ERROR_SHELL_MIN_COVERAGE
    return val


def _error_shell_min_dominance_alpha() -> int:
    """Codex P1-1 (#1289): minimum total alphabetic content (chars) for the
    no-co-token dominance path to fire. A bare 2-3-word title is below this floor
    and is KEPT. A malformed / <=0 value falls back to the conservative
    default."""
    raw = os.getenv(_ENV_ERROR_SHELL_MIN_DOMINANCE_ALPHA)
    if raw is None or not raw.strip():
        return _DEFAULT_ERROR_SHELL_MIN_DOMINANCE_ALPHA
    try:
        val = int(raw.strip())
    except (TypeError, ValueError):
        return _DEFAULT_ERROR_SHELL_MIN_DOMINANCE_ALPHA
    if val <= 0:
        return _DEFAULT_ERROR_SHELL_MIN_DOMINANCE_ALPHA
    return val


def is_error_shell_text(text: str) -> bool:
    """True iff ``text`` is a fetch-error / interstitial SHELL, not real content.

    High-precision + length-gated. The body must be SHORT (<= the env ceiling)
    AND carry a PRIMARY error-shell signature, AND its distinctive residual after
    removing every signature must be trivially small (<= 3 words). Then ONE of two
    independent confirmations must hold (Codex P1-1, #1289 — the OR keeps the
    screen conservative; a real source that merely CONTAINS a generic phrase is
    NOT a shell):

      (1) CO-TOKEN: a WAF / HTTP-error co-token (cloudflare-blocked, rate-limit,
          a bare HTTP status, a CAPTCHA/security-verification stub, a Jina
          "returned error" line) co-occurs with the signature — exactly the M-23d
          ``_is_paywalled`` posture. A genuine block page carries one of these; a
          real article TITLE / snippet does not.
      (2) DOMINANCE: the signature DOMINATES the body — the stripped-signature
          COVERAGE ratio is >= ``_error_shell_min_coverage()`` of the body's
          alphabetic content AND the body has enough total content
          (>= ``_error_shell_min_dominance_alpha()`` alpha-chars) for "dominance"
          to be meaningful. A bare 2-3-word title ("Access Denied", "Just a
          Moment") falls below the content floor and is KEPT; a substantive titled
          body ("Access Denied: barriers to healthcare ...") falls below the
          coverage ratio and is KEPT; the banked drb_72 JS-error shell
          (~0.88 coverage, 96 alpha-chars, no co-token) DROPS via this path.

    A long article that merely quotes an error phrase in prose is NEVER flagged
    (length-gate + residual-word + coverage all exclude it). When in doubt, KEEP
    the source (§-1.3 — only genuine junk dropped; the faithfulness engine is the
    only hard gate). Mirrors the ``is_boilerplate_or_nonassertional`` error-page
    length-gate.
    """
    if not text:
        return False
    stripped = text.strip()
    if not stripped or len(stripped) > _junk_shell_max_chars():
        return False
    lowered = stripped.lower()
    # Require at least one PRIMARY error-shell signature to be present.
    if not any(sig in lowered for sig in _ERROR_SHELL_SIGNATURES):
        return False
    # Total alphabetic content (Unicode words) BEFORE stripping signatures — the
    # denominator for the coverage ratio and the input to the content floor.
    body_words = re.findall(r"[^\W\d_]+", lowered, re.UNICODE)
    total_alpha = sum(len(w) for w in body_words)
    if total_alpha == 0:
        return False
    # DOMINANCE residual: strip every primary signature AND the secondary
    # shell-chrome phrases, then measure what real content remains. A pure shell
    # page leaves essentially nothing; a real article that merely quotes an error
    # phrase keeps its substantive vocabulary and is NOT flagged.
    residual = lowered
    for phrase in (*_ERROR_SHELL_SIGNATURES, *_ERROR_SHELL_CHROME):
        residual = residual.replace(phrase, " ")
    residual_words_all = re.findall(r"[^\W\d_]+", residual, re.UNICODE)
    residual_alpha = sum(len(w) for w in residual_words_all)
    residual_distinct = [w for w in residual_words_all if len(w) > 2]
    # Outer precision gate: a body with substantive residual prose is a real
    # article wrapped around an error phrase — never a shell.
    if len(residual_distinct) > 3:
        return False
    # Confirmation (1): a WAF / HTTP-error co-token makes it an unambiguous block
    # page regardless of coverage (a short genuine interstitial may be co-token-
    # dominated rather than signature-dominated).
    if any(tok in lowered for tok in _ERROR_SHELL_WAF_COTOKENS):
        return True
    # Confirmation (2): the signature DOMINATES the body by coverage AND the body
    # carries enough total content for dominance to be meaningful (so a bare
    # 2-3-word title is KEPT, not flagged).
    coverage = (total_alpha - residual_alpha) / total_alpha
    return (
        coverage >= _error_shell_min_coverage()
        and total_alpha >= _error_shell_min_dominance_alpha()
    )


def is_junk_source(url: str = "", text: str = "") -> bool:
    """True iff a source is a non-citable JUNK page (host OR error-shell body).

    Faithfulness-NEUTRAL SOURCE screen (§-1.3): drops ONLY confirmed junk
    (homework-help/Q&A host, or a fetch-error shell body), never a real
    journal/repository/gov/news source. Either signal alone is sufficient; both
    are high-precision. Never a verify verdict — applied at corpus consumption so
    junk never enters the basket / bibliography / corroboration / citation.
    """
    return is_junk_source_host(url) or is_error_shell_text(text)


# ---------------------------------------------------------------------------
# F4 (I-deepfix-001 #1344): DOI / handle REGISTRY "not found" error-page screen.
#
# The B02/B04 forced-Zyte degraded re-fetch "recovered" a doi.org "DOI Not Found"
# proxy page (~821 chars of real English) and ADOPTED it unchanged as upgraded full
# text (drb_72 ev_057, DOI 10.5555/2485288). Recovery measured LENGTH only
# (is_content_starved → False), and the registry page also slipped past
# is_error_shell_text / classify_block_page (verified live). These signatures are
# full registry-PROXY phrases that NEVER occur in a real article body, so a plain
# lowercased whole-substring hit is a confident "this is the registry error page,
# not the article" verdict — high precision, no length/coverage gate needed.
# §-1.3: a "not found" page is never a corroborator; refusing to adopt a fetch
# FAILURE as grounding is not a hard-drop (the row keeps its disclosed-gap
# disposition). Default-ON, kill-switch PG_REGISTRY_ERROR_GUARD.
_ENV_REGISTRY_ERROR_GUARD = "PG_REGISTRY_ERROR_GUARD"
_REGISTRY_ERROR_SIGNATURES = (
    "this doi cannot be found in the doi system",
    "report this error to the responsible doi registration agency",
    "the doi has not been activated yet",
    "doi name not found",
    "this doi has not been registered",
    "this handle is not registered",
    "handle not found",
)


def registry_error_guard_enabled() -> bool:
    """Kill-switch ``PG_REGISTRY_ERROR_GUARD`` (default ON). OFF
    ('0'/'false'/'no'/'off', case-insensitive) => :func:`is_registry_error_page`
    is bypassed by its callers so the recovery path is byte-identical to the legacy
    length-only adopt."""
    return os.getenv(_ENV_REGISTRY_ERROR_GUARD, "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def is_registry_error_page(text: str) -> bool:
    """True iff ``text`` is a DOI / handle REGISTRY "not found" error page.

    Lowercased whole-substring match against full registry-proxy phrases a real
    article body never carries. High-precision (no length gate): the phrases are
    long and registry-specific, so a real paper that merely DISCUSSES DOIs / the
    handle system (e.g. "the DOI was not found in our local cache", "Crossref",
    "handle.net proxy") never trips one. When in doubt, KEEP (return False)."""
    if not text:
        return False
    lowered = text.lower()
    return any(sig in lowered for sig in _REGISTRY_ERROR_SIGNATURES)


# ---------------------------------------------------------------------------
# D (I-extract-001 #1327): Layer-A block-page / stub DETECTOR.
#
# Per the I-extract-001 forensic the DOMINANT Layer-A junk source was NOT the
# HTML extractor: 10 of 21 raw pages were Cloudflare/Akamai challenge pages,
# Google reCAPTCHA walls, or publisher redirect/error stubs that returned
# HTTP 200 with junk in the body — so `success=True` and the junk text reached
# extraction and became "evidence". This detector flags such a body BEFORE it
# becomes evidence so the bypass chain RE-ROUTES to the next backend (re-fetch)
# or, when every backend is blocked, the fetch is marked FAILED → the empty/junk
# body drops at strict_verify, NEVER fabricated.
#
# Faithfulness-NEUTRAL (§-1.3): it never drops a real source. A block page is
# not a low-credibility source — it is a fetch FAILURE masquerading as content.
# Re-routing recovers the REAL body when any backend can reach it; marking the
# fetch failed (when none can) is the honest "we could not fetch this" signal,
# which strict_verify already handles. Default-OFF (PG_BLOCK_PAGE_DETECTOR); when
# OFF every fetch call site is byte-identical to the pre-existing behaviour.
#
# Two tiers of signal:
#   (1) DECISIVE raw markers — interstitial-only tokens that NEVER occur in a
#       real article body (Cloudflare `window._cf_chl_opt`, reCAPTCHA
#       challengepage, Akamai `errors.edgesuite.net`, the publisher "there was a
#       problem providing the content you requested" error card). Length-UNGATED:
#       one hit is sufficient. The BROAD Cloudflare CSP/Turnstile tokens are
#       excluded — they appear on real protected pages (see the marker table).
#   (2) VISIBLE-TEXT phrases that CAN appear in real prose ("access denied",
#       "enable javascript and cookies to continue") — gated to a SHORT visible
#       body so a real article that merely QUOTES the phrase is never flagged.
#       The visible body of every real block page is tiny (a CF "Just a moment"
#       card ≈ 60 chars); a real article body is thousands of chars.
# ---------------------------------------------------------------------------

# Flag (LAW VI). Default OFF: '1'/'true'/'yes'/'on' (case-insensitive) enable.
_ENV_BLOCK_PAGE_DETECTOR = "PG_BLOCK_PAGE_DETECTOR"

# Decisive raw-HTML markers. Whole-substring, matched on the HTML-unescaped,
# lowercased body. Each is specific to a challenge / WAF / stub INTERSTITIAL and
# NEVER occurs in a legitimate article body, so no length gate is needed.
#
# PRECISION NOTE (validated on the I-extract-001 raw substrate): the broad
# Cloudflare tokens "/cdn-cgi/challenge-platform/" and "challenges.cloudflare.com"
# are DELIBERATELY EXCLUDED — they appear once on REAL Cloudflare-protected
# article pages (the background Turnstile / bot-management beacon + CSP allow-
# lists), so flagging on them dropped real bodies (drb ev_586 / ev_729 = §-1.3
# false positive). `window._cf_chl_opt` (the challenge orchestration object) and
# "checking your browser before accessing" appear ONLY on the actual interstitial.
_BLOCK_PAGE_DECISIVE_MARKERS = (
    ("cloudflare_challenge", "window._cf_chl_opt"),
    ("cloudflare_challenge", "checking your browser before accessing"),
    ("recaptcha_challenge", "recaptcha/challengepage"),
    ("recaptcha_challenge", "recaptchachallengepageui"),
    ("akamai_access_denied", "errors.edgesuite.net"),
    (
        "publisher_error_stub",
        "there was a problem providing the content you requested",
    ),
)

# Visible-text phrase rules: (failure_class, required-phrase tuple). ALL phrases
# in the tuple must be present in the visible text AND the visible text must be
# SHORT (<= _block_page_max_visible_chars). High-precision PAIRS / full phrases
# (not single common words) so a real article never trips one.
_BLOCK_PAGE_VISIBLE_RULES = (
    ("akamai_access_denied", ("access denied", "you don't have permission to access")),
    ("cloudflare_challenge", ("just a moment", "enable javascript and cookies to continue")),
    ("javascript_wall", ("enable javascript and cookies to continue",)),
    ("captcha_wall", ("verify you are human",)),
    ("captcha_wall", ("performing security verification",)),
)

# Visible-body ceiling for the gated VISIBLE-TEXT rules. A CF "Just a moment"
# card / Akamai "Access Denied" body / publisher error card all have a tiny
# visible body; a real article body is far larger. Generous default so a short
# real abstract is never mistaken for a stub, yet far below any real article.
# Env-overridable (LAW VI); a malformed/<=0 value falls back to the default.
_ENV_BLOCK_PAGE_MAX_VISIBLE_CHARS = "PG_BLOCK_PAGE_MAX_VISIBLE_CHARS"
_DEFAULT_BLOCK_PAGE_MAX_VISIBLE_CHARS = 1500

# Upper bound (chars) on the RAW body the detector will tag-strip for the
# visible-text rules. A multi-MB real article never needs the visible-text path
# (its raw length alone proves it is not a stub) — skipping the tag-strip there
# keeps the screen cheap on big bodies. The decisive raw-marker scan still runs
# (cheap substring) regardless of size. Named constant (LAW VI).
_BLOCK_PAGE_VISIBLE_SCAN_MAX_CHARS = 300000

# Visible-text floor below which a meta-refresh body is a bare redirect stub.
_BLOCK_PAGE_REDIRECT_STUB_MAX_VISIBLE_CHARS = 300

# Meta-refresh redirect detector (a stub whose only job is to bounce). A body
# carrying a meta-refresh AND essentially no visible text is a redirect shell.
_BLOCK_PAGE_META_REFRESH_RE = re.compile(
    r"<meta[^>]+http-equiv=['\"]?refresh['\"]?", re.IGNORECASE
)
# Strip <script>/<style> bodies (their content is never user-visible text); keep
# <noscript> inner text — the block message lives there on JS-challenge pages.
_BLOCK_PAGE_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)
_BLOCK_PAGE_TAG_RE = re.compile(r"<[^>]+>")


def block_page_detector_enabled() -> bool:
    """True iff the block-page/stub detector is enabled (PG_BLOCK_PAGE_DETECTOR).

    Default OFF. Enabled by '1'/'true'/'yes'/'on' (case-insensitive); anything
    else (incl. unset/empty/'0') is OFF, so the screen is a no-op and every fetch
    call site is byte-identical to the pre-existing behaviour."""
    return os.getenv(_ENV_BLOCK_PAGE_DETECTOR, "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _block_page_max_visible_chars() -> int:
    """Visible-body ceiling for the gated visible-text rules. Malformed/<=0 ->
    conservative default (a bad knob must never widen the screen into real
    article bodies)."""
    raw = os.getenv(_ENV_BLOCK_PAGE_MAX_VISIBLE_CHARS)
    if raw is None or not raw.strip():
        return _DEFAULT_BLOCK_PAGE_MAX_VISIBLE_CHARS
    try:
        val = int(raw.strip())
    except (TypeError, ValueError):
        return _DEFAULT_BLOCK_PAGE_MAX_VISIBLE_CHARS
    return val if val > 0 else _DEFAULT_BLOCK_PAGE_MAX_VISIBLE_CHARS


def _block_page_visible_text(body: str) -> str:
    """Cheap visible-text projection: drop <script>/<style> blocks, strip the
    remaining tags, unescape entities, collapse whitespace, lowercase.
    Pure string ops — never parses, never raises."""
    no_blocks = _BLOCK_PAGE_SCRIPT_STYLE_RE.sub(" ", body)
    no_tags = _BLOCK_PAGE_TAG_RE.sub(" ", no_blocks)
    text = html.unescape(no_tags)
    return " ".join(text.split()).lower()


def classify_block_page(body: str, url: str = "") -> str:
    """Return the block-page/stub FAILURE CLASS for a fetched body, or "" when
    the body is NOT a block page (real content / unknown — KEEP).

    Decisive raw markers fire length-UNGATED; visible-text phrase rules fire only
    when the visible body is SHORT (so a real article quoting "access denied" is
    never flagged). A bare meta-refresh body with negligible visible text is a
    redirect stub. `url` is accepted for logging / future host-aware rules; the
    verdict is body-driven (host alone is never sufficient — §-1.3). Never
    raises (the screen must never itself abort a fetch)."""
    if not body:
        return ""
    unescaped_lower = html.unescape(body).lower()
    # (1) DECISIVE raw markers — one hit is sufficient, no length gate.
    for klass, marker in _BLOCK_PAGE_DECISIVE_MARKERS:
        if marker in unescaped_lower:
            return klass
    # (2) VISIBLE-TEXT rules — only worth computing for a body small enough to
    # plausibly be a stub; a multi-MB article is never a visible-text stub.
    if len(body) > _BLOCK_PAGE_VISIBLE_SCAN_MAX_CHARS:
        return ""
    visible = _block_page_visible_text(body)
    visible_len = len(visible)
    if visible and visible_len <= _block_page_max_visible_chars():
        for klass, phrases in _BLOCK_PAGE_VISIBLE_RULES:
            if all(phrase in visible for phrase in phrases):
                return klass
    # Redirect/refresh shell: a meta-refresh body with negligible visible text.
    if (
        visible_len <= _BLOCK_PAGE_REDIRECT_STUB_MAX_VISIBLE_CHARS
        and _BLOCK_PAGE_META_REFRESH_RE.search(body)
    ):
        return "redirect_stub"
    return ""


def is_block_page_or_stub(body: str = "", url: str = "") -> bool:
    """True iff `body` is a challenge / WAF block / redirect or error stub that
    must NOT become evidence. Thin boolean wrapper over `classify_block_page`."""
    return bool(classify_block_page(body, url))


# Block-page detector canary (behavioral telemetry, REAL counts):
#   detected   — total fetched bodies flagged as a block-page/stub.
#   re_fetched — flagged URLs for which a SUBSEQUENT backend then returned clean
#                content (a successful re-fetch / recovery). re_fetched < detected
#                means some URLs were blocked on every backend → marked failed →
#                dropped at strict_verify (never fabricated).
# Guarded by its own lock (the bypass chain runs on many worker threads).
_BLOCK_PAGE_CANARY: "dict[str, int]" = {"detected": 0, "re_fetched": 0}
_block_page_canary_lock = threading.Lock()


def _record_block_page_detection() -> int:
    """Increment + return the block-page DETECTED counter. Thread-safe."""
    with _block_page_canary_lock:
        _BLOCK_PAGE_CANARY["detected"] += 1
        return _BLOCK_PAGE_CANARY["detected"]


def _record_block_page_refetch() -> int:
    """Increment + return the block-page RE_FETCHED (recovered-clean) counter.
    Thread-safe."""
    with _block_page_canary_lock:
        _BLOCK_PAGE_CANARY["re_fetched"] += 1
        return _BLOCK_PAGE_CANARY["re_fetched"]


def get_block_page_canary() -> "dict[str, int]":
    """Snapshot of the block-page-detector canary (detected / re_fetched)."""
    with _block_page_canary_lock:
        return dict(_BLOCK_PAGE_CANARY)


def reset_block_page_canary() -> None:
    """Zero the block-page-detector canary. Test isolation / between runs."""
    with _block_page_canary_lock:
        _BLOCK_PAGE_CANARY["detected"] = 0
        _BLOCK_PAGE_CANARY["re_fetched"] = 0


# ---------------------------------------------------------------------------
# I-wire-014 ISSUE B (#1313 W4): PROCESS-WIDE mineru25 GPU-VLM serialization lock.
#
# THE BUG (reproduced on the VM, GPU 1 isolated, 2026-06-27): MinerU's in-process
# ``do_parse`` is NOT safe to call concurrently across threads. Two independent
# causes converge:
#   (1) PDFium / pypdfium2 (the PDF loader ``do_parse`` calls at
#       ``load_images_from_pdf`` -> ``pdfium.PdfDocument``) has PROCESS-GLOBAL,
#       non-thread-safe state. Upstream is explicit: "PDFium is not thread-safe;
#       it is not allowed to call pdfium functions simultaneously across threads,
#       not even with different documents" (pypdfium2 #303 / pdfium google-group).
#   (2) MinerU's model manager is a PROCESS-SINGLETON (``__new__`` instance cache)
#       sharing ONE VLM model + processor across every ``do_parse`` call, so
#       concurrent batched inference interleaves tensor state.
#
# In production, ``live_retriever._fetch_content`` fans each PDF fetch onto its
# OWN daemon thread, and ``_maybe_mineru25_extract`` runs ``_mineru25_extract``
# via ``loop.run_in_executor(None, ...)``. Two clinical PDFs fetched concurrently
# therefore call ``do_parse`` simultaneously and CORRUPT each other. The symptom
# is timing-dependent: the iwire014 confirm run saw a torch tensor-shape error
# ("expanded size (2) must match existing size (0) ... [3, 2,"); the VM repro saw
# ``PdfiumError: Failed to import pages`` / ``Data format error`` on the SAME two
# PDFs that BOTH extract cleanly when serialized. Both faces, one race.
#
# THE FIX (upstream-prescribed mutex, faithfulness-NEUTRAL): a single module-wide
# ``threading.Lock`` held around the in-process VLM extraction so at most ONE
# ``do_parse`` runs at a time per process. This is OUTPUT-PRESERVING — it changes
# only the timing of already-selected extractions, never which PDFs are
# extracted, never the verbatim text strict_verify grounds, never any
# faithfulness gate. A 24 GB GPU VLM at batch_size 8 is single-tenant anyway, so
# serialization costs nothing the GPU was not already forcing; it only removes
# the corruption. The disclosed Docling -> PyMuPDF fallback + W4-CANARY remain
# the honest path for a genuine per-PDF mineru failure. The lock does NOT apply
# to the ``vlm-http-client`` backend (a remote mineru-api server is the server's
# concurrency domain) — only the in-process ``vlm-transformers`` GPU path needs
# it, but holding the lock for either is correct and cheap.
# ---------------------------------------------------------------------------
_mineru25_gpu_lock = threading.Lock()

# ---------------------------------------------------------------------------
# I-deepfix-001 BUG-B (#1344): mineru25 (W4 clinical-PDF VLM) CIRCUIT BREAKER.
#
# `_maybe_mineru25_extract` already has a per-call `PG_MINERU25_TIMEOUT_S` (300s)
# wall, but had NO circuit breaker. On a GPU host where mineru25 is CONSISTENTLY
# failing/timing out (model-load failure, CUDA OOM, hung VLM), EVERY clinical PDF in
# a ~1000-URL run paid the full 300s before falling back to Docling — the run ground
# for hours. This mirrors the module-global jina/firecrawl/zyte/crawl4ai breakers
# above: after N CONSECUTIVE genuine mineru25 failures (timeout OR hard exception —
# NOT a thin/empty per-PDF CONTENT outcome), OPEN the breaker for a cooldown so
# subsequent PDFs skip mineru25 directly and go straight to the UNCHANGED
# Docling -> PyMuPDF fallback. A genuine success (md > 500 chars) resets the counter.
#
# §-1.3 / faithfulness: this changes only the EXTRACTOR-SELECTION TIMING. The body is
# STILL extracted by the disclosed Docling/PyMuPDF fallback (no source dropped, no
# cap/thin/target), and the verbatim text strict_verify grounds is unchanged. Every
# open-skip is a LOUD, disclosed degradation (W4-CANARY + tool-trace), never silent.
#
# Default-ON (a healthy run never trips => byte-identical happy path); a disable
# sentinel (`PG_MINERU25_CIRCUIT_THRESHOLD <= 0`) turns it off. Separate knobs from
# the shared `_CIRCUIT_BREAKER_THRESHOLD=8` — at 300s/failure, 8 = ~40 min to trip
# (useless); the default is 3.
# ---------------------------------------------------------------------------
_mineru25_consecutive_failures: int = 0
_mineru25_circuit_open_until: float = 0.0
_MINERU25_CIRCUIT_THRESHOLD_DEFAULT = 3
_MINERU25_CIRCUIT_COOLDOWN_DEFAULT = 300.0


def _mineru25_circuit_threshold() -> int:
    """Consecutive-failure count that OPENS the mineru25 breaker. ``<= 0`` disables
    the breaker entirely (the operator escape hatch, mirroring the campaign's FIX-1
    ``=0`` / FIX-2 unset sentinels). A malformed value falls back to the small
    default (the breaker is an operational knob, not a correctness gate)."""
    raw = os.getenv("PG_MINERU25_CIRCUIT_THRESHOLD", "").strip()
    if not raw:
        return _MINERU25_CIRCUIT_THRESHOLD_DEFAULT
    try:
        return int(raw)
    except ValueError:
        return _MINERU25_CIRCUIT_THRESHOLD_DEFAULT


def _mineru25_circuit_cooldown() -> float:
    """Seconds the mineru25 breaker stays OPEN after tripping. Default 300s (one
    per-call timeout window) — long enough to ride out a wedged VLM, short enough to
    retry if it recovers."""
    raw = os.getenv("PG_MINERU25_CIRCUIT_COOLDOWN", "").strip()
    if not raw:
        return _MINERU25_CIRCUIT_COOLDOWN_DEFAULT
    try:
        value = float(raw)
    except ValueError:
        return _MINERU25_CIRCUIT_COOLDOWN_DEFAULT
    return value if value > 0 else _MINERU25_CIRCUIT_COOLDOWN_DEFAULT


# ---------------------------------------------------------------------------
# Crawl4AI availability flag (set on first import attempt)
# ---------------------------------------------------------------------------
_crawl4ai_available: "bool | None" = None

# ---------------------------------------------------------------------------
# FIX-EPIPE: Crawl4AI circuit breaker for subprocess crashes.
# After consecutive subprocess crashes (EPIPE, BrokenPipeError, OSError),
# skip crawl4ai entirely for a cooldown period to avoid cascading failures
# from a broken Playwright installation or dead browser process.
# ---------------------------------------------------------------------------
_crawl4ai_consecutive_failures: int = 0
_crawl4ai_circuit_open_until: float = 0.0
# I-fetch-002 (#1168): raise 3->6 so a couple of TRANSIENT subprocess crashes (EPIPE under concurrent
# load) do not trip the breaker and disable crawl4ai for the whole run. Pairs with the new concurrency
# semaphore below — fewer concurrent browsers means fewer crashes in the first place.
_CRAWL4AI_CIRCUIT_BREAKER_THRESHOLD = int(
    os.getenv("PG_CRAWL4AI_CIRCUIT_BREAKER_THRESHOLD", "6")
)
_CRAWL4AI_CIRCUIT_BREAKER_COOLDOWN = float(
    os.getenv("PG_CRAWL4AI_CIRCUIT_BREAKER_COOLDOWN", "120.0")
)

# I-fetch-002 (#1168): crawl4ai launches a Playwright browser subprocess PER URL; under the ~1000-URL
# benchmark fan-out, many concurrent browsers exhaust the OS and crash (EPIPE), which then trips the
# circuit breaker and disables crawl4ai run-wide. Bound the number of concurrently-LIVE browsers with a
# semaphore (mirrors the PG_JINA_CONCURRENCY=2 pattern). Lazy-init so it binds to the running loop.
_crawl4ai_semaphore: "asyncio.Semaphore | None" = None

# I-pipe-002 (#1227): per-running-loop crawl4ai concurrency gates.
#
# THE BUG (old global path below): `_crawl4ai_semaphore` was a SINGLE module-global
# `asyncio.Semaphore`. `live_retriever._fetch_content` runs each bypass fetch on a fresh
# daemon thread with its OWN `asyncio.run` loop. An `asyncio.Semaphore` binds (on 3.11
# via `_LoopBoundMixin`, lazily on FIRST acquire) to the loop that first acquired it. The
# first worker thread's loop wins the binding; EVERY OTHER worker thread then hits
# `RuntimeError: <Semaphore> is bound to a different event loop` inside `async with`,
# crashing the fetch -> EPIPE -> ~159 distinct JS-rendered journal sources (Oxford/Cambridge)
# never fetched (553 EPIPE in the forensic).
#
# THE FIX (default, kill-switch): keep ONE `asyncio.Semaphore` PER running loop, looked up
# inside the async context by the loop OBJECT. A `weakref.WeakKeyDictionary` keyed by the
# loop (NOT a plain dict keyed by `id(loop)`):
#   - auto-evicts the entry when the worker's loop is GC'd (no per-fetch leak over 1000 URLs),
#   - is immune to `id()` address-recycling: a closed loop whose address is reused would, with
#     an id-keyed dict, hand a NEW loop the dead loop's semaphore -> the exact RuntimeError
#     we are fixing, now intermittent. Keying by the live object cannot alias.
# A `threading.Lock` guards the dict (WeakKeyDictionary is not safe under concurrent inserts +
# weakref-removal callbacks).
#
# This is a PURE-RELIABILITY kill-switch (default-ON correct fix). It does NOT change WHICH urls
# are fetched, the concurrency VALUE (still PG_CRAWL4AI_CONCURRENCY), or any verification gate —
# only that already-selected fetches stop crashing cross-loop. Each worker loop runs ~1 crawl4ai
# call, so the per-loop value (2) is never contended: the gate never BLOCKS, it just stops the
# crash. Setting PG_CRAWL4AI_PERLOOP_SEMAPHORE=0 reverts to the old single-global behavior.
PG_CRAWL4AI_PERLOOP_SEMAPHORE_ENV = "PG_CRAWL4AI_PERLOOP_SEMAPHORE"
_crawl4ai_perloop_semaphores: "weakref.WeakKeyDictionary[Any, asyncio.Semaphore]" = (
    weakref.WeakKeyDictionary()
)
_crawl4ai_perloop_lock = threading.Lock()


def _crawl4ai_perloop_enabled() -> bool:
    """I-pipe-002 (#1227): per-loop semaphore is ON unless PG_CRAWL4AI_PERLOOP_SEMAPHORE=0.

    Default-ON is the sanctioned kill-switch (pure-reliability correct fix); '0' reverts to
    the old loop-bound module-global that crashed on every worker thread but the first."""
    return os.getenv(PG_CRAWL4AI_PERLOOP_SEMAPHORE_ENV, "1").strip() != "0"


def _crawl4ai_concurrency() -> int:
    """Concurrency ceiling for crawl4ai browsers. Default 2 (env PG_CRAWL4AI_CONCURRENCY).
    A malformed/<=0 value falls back to 2 so a bad knob never disables the bound."""
    raw = os.getenv("PG_CRAWL4AI_CONCURRENCY", "2")
    try:
        parsed = int(raw)
        if parsed > 0:
            return parsed
    except (TypeError, ValueError):
        pass
    return 2


def _get_crawl4ai_semaphore() -> "asyncio.Semaphore":
    """I-fetch-002 (#1168) + I-pipe-002 (#1227): crawl4ai browser-concurrency gate.

    MUST be called from inside the running event loop (the `async with` site at the crawl
    region). Default (PG_CRAWL4AI_PERLOOP_SEMAPHORE != '0'): one `asyncio.Semaphore` per
    running loop, keyed by the loop object in a `WeakKeyDictionary` — so each worker thread's
    fresh loop gets a semaphore bound to ITSELF and the `async with` never raises the cross-loop
    `RuntimeError`. Old path (='0'): the single loop-bound module-global (preserved verbatim).
    Default 2 concurrent browsers (env PG_CRAWL4AI_CONCURRENCY)."""
    if not _crawl4ai_perloop_enabled():
        # --- OLD GLOBAL PATH (PG_CRAWL4AI_PERLOOP_SEMAPHORE=0): byte-for-byte the pre-#1227
        # behavior. Binds to the first acquiring loop; crashes on every other worker loop. ---
        global _crawl4ai_semaphore
        if _crawl4ai_semaphore is None:
            _crawl4ai_semaphore = asyncio.Semaphore(
                int(os.getenv("PG_CRAWL4AI_CONCURRENCY", "2"))
            )
        return _crawl4ai_semaphore

    # --- PER-LOOP PATH (default): a semaphore bound to THIS running loop. ---
    loop = asyncio.get_running_loop()
    with _crawl4ai_perloop_lock:
        sem = _crawl4ai_perloop_semaphores.get(loop)
        if sem is None:
            sem = asyncio.Semaphore(_crawl4ai_concurrency())
            _crawl4ai_perloop_semaphores[loop] = sem
        return sem


def reset_crawl4ai_semaphore_state() -> None:
    """I-pipe-002 (#1227): reset BOTH crawl4ai semaphore holders (global + per-loop map).
    For test isolation ONLY — not called on the production path (mirrors
    `reset_bypass_leak_state`)."""
    global _crawl4ai_semaphore
    _crawl4ai_semaphore = None
    with _crawl4ai_perloop_lock:
        _crawl4ai_perloop_semaphores.clear()


# ---------------------------------------------------------------------------
# BB5-S02 (#1177): cross-THREAD in-flight bypass-worker bound + leak gauge.
#
# `live_retriever._fetch_content` runs each `AccessBypass.fetch_with_bypass`
# on a fresh daemon thread with its OWN `asyncio.run` loop, joined with a hard
# timeout. On timeout the thread is ABANDONED (it keeps running, holding a live
# Crawl4AI/Playwright browser subprocess mid-`arun`). Under the ~740-URL
# benchmark fan-out, hundreds of abandoned threads + browser subprocesses
# accumulate (the resource-exhaustion / segfault mechanism).
#
# `_get_crawl4ai_semaphore()` cannot bound this: it is lazy-bound to the
# RUNNING loop, and every bypass worker thread has its OWN fresh loop — so it
# only caps browsers WITHIN one thread. A `threading`-level BoundedSemaphore is
# the only primitive that bounds the abandoned-thread FLEET across loops.
#
# Acquire at the TOP of the worker (in `live_retriever`), release in THAT
# worker's `finally` — never in the outer join path (releasing on abandonment
# would over-release; not releasing would leak the slot). Sized BELOW the
# parallel `max_workers` so it creates back-pressure; no deadlock because the
# inner per-backend wall-clocks guarantee every abandoned worker eventually
# terminates and releases its slot.
# ---------------------------------------------------------------------------

# Default ceiling on concurrently-LIVE bypass worker threads (each may hold a
# browser subprocess). Env-overridable. Below the live_retriever parallel
# `max_workers` ceiling (48) so abandoned in-flight workers cannot fan out a
# browser-per-candidate. Named constant (LAW VI — no magic numbers).
_BYPASS_INFLIGHT_DEFAULT_LIMIT = 16
PG_BYPASS_MAX_INFLIGHT_ENV = "PG_BYPASS_MAX_INFLIGHT"

_bypass_inflight_semaphore: "threading.BoundedSemaphore | None" = None
_bypass_inflight_semaphore_lock = threading.Lock()

# BB5-S02 leaked-worker gauge: monotonically-incremented count of bypass worker
# threads that were ABANDONED (outer join timed out while the worker was still
# alive). A non-zero gauge is the auditable signal that orphan browser
# subprocesses may have accumulated. Guarded by its own lock.
_bypass_leaked_worker_count: int = 0
_bypass_leaked_worker_lock = threading.Lock()


def _get_bypass_inflight_semaphore() -> "threading.BoundedSemaphore":
    """BB5-S02 (#1177): lazy-init the cross-thread in-flight bypass-worker
    bound. A `threading.BoundedSemaphore` (NOT asyncio) — it must bound worker
    threads across their independent per-thread event loops.

    Limit from `PG_BYPASS_MAX_INFLIGHT` (positive int), else
    `_BYPASS_INFLIGHT_DEFAULT_LIMIT`. A malformed/<=0 value falls back to the
    default — a bad knob must never disable the bound (which would re-open the
    abandoned-fleet leak)."""
    global _bypass_inflight_semaphore
    if _bypass_inflight_semaphore is None:
        with _bypass_inflight_semaphore_lock:
            if _bypass_inflight_semaphore is None:
                raw = os.getenv(PG_BYPASS_MAX_INFLIGHT_ENV)
                limit = _BYPASS_INFLIGHT_DEFAULT_LIMIT
                if raw is not None and raw.strip():
                    try:
                        parsed = int(raw)
                        if parsed > 0:
                            limit = parsed
                    except ValueError:
                        limit = _BYPASS_INFLIGHT_DEFAULT_LIMIT
                _bypass_inflight_semaphore = threading.BoundedSemaphore(limit)
    return _bypass_inflight_semaphore


def record_bypass_leaked_worker() -> int:
    """BB5-S02 (#1177): increment + return the leaked-bypass-worker gauge. The
    caller (live_retriever) invokes this when an outer fetch join times out
    while the worker thread is still alive (abandoned → potential orphan
    browser subprocess). Thread-safe; returns the new total for logging."""
    global _bypass_leaked_worker_count
    with _bypass_leaked_worker_lock:
        _bypass_leaked_worker_count += 1
        return _bypass_leaked_worker_count


def bypass_leaked_worker_count() -> int:
    """BB5-S02 (#1177): read the current leaked-bypass-worker gauge (auditable
    orphan-subprocess signal). Thread-safe snapshot."""
    with _bypass_leaked_worker_lock:
        return _bypass_leaked_worker_count


def reset_bypass_leak_state() -> None:
    """BB5-S02 (#1177): reset the leak gauge + in-flight semaphore. For test
    isolation ONLY — not called on the production path."""
    global _bypass_leaked_worker_count, _bypass_inflight_semaphore
    with _bypass_leaked_worker_lock:
        _bypass_leaked_worker_count = 0
    with _bypass_inflight_semaphore_lock:
        _bypass_inflight_semaphore = None
    with _bypass_abandoned_lock:
        _bypass_abandoned_workers.clear()


# ---------------------------------------------------------------------------
# FIX-3 PIECE 1 (I-deepfix-001): bounded drain + live/cumulative gauge split.
#
# `record_bypass_leaked_worker` above is a CUMULATIVE monotonic event counter —
# it climbs by design every time the outer join abandons a still-alive worker.
# It CANNOT tell "how many abandoned workers are still alive right now" from
# "how many were ever abandoned this process". In a long-lived UI/server process
# cooperatively-finishable abandoned workers also persist ACROSS questions with
# no end-of-run reclamation.
#
# This adds, ALONGSIDE the cumulative counter (which stays untouched):
#   * a LIVE registry of abandoned worker Threads (a set guarded by a lock),
#   * `register_abandoned_bypass_worker` / `deregister_abandoned_bypass_worker`
#     so the timeout path registers on abandon and the worker self-deregisters
#     in its OWN finally,
#   * `bypass_live_leaked_count()` — the count of registered workers STILL alive
#     (distinct from the cumulative gauge),
#   * `drain_bypass_workers(budget)` — a BOUNDED best-effort join of the
#     registered workers within `PG_BYPASS_DRAIN_SECONDS` (default 30.0),
#     called ONCE at end of run_live_retrieval so cooperative abandoned workers
#     are reclaimed and the registry cannot grow unbounded across questions.
#
# The existing `threading.BoundedSemaphore` (PG_BYPASS_MAX_INFLIGHT) stays the
# concurrency bound — this adds NO second bound, only reclamation + an honest
# live gauge.
#
# HONEST LIMITATION (mirrors the BB5-S02 active-teardown + trafilatura SIGSEGV
# notes): a worker wedged in a synchronous C-level Playwright call CANNOT be
# joined in-process — `join(timeout)` returns when the budget elapses but the
# thread is still alive. The drain reclaims COOPERATIVE cases and caps
# cross-question accumulation; it does NOT promise zero residual threads, and a
# wedged worker is still counted live by `bypass_live_leaked_count()`.
# ---------------------------------------------------------------------------

# Default wall-clock budget (seconds) for the end-of-run bounded drain. Named
# constant (LAW VI — no magic number). Env-overridable via PG_BYPASS_DRAIN_SECONDS.
_BYPASS_DRAIN_SECONDS_DEFAULT = 30.0
PG_BYPASS_DRAIN_SECONDS_ENV = "PG_BYPASS_DRAIN_SECONDS"

# The LIVE registry of abandoned bypass worker threads, guarded by its own lock
# (NOT the cumulative-counter lock — the two gauges are independent).
_bypass_abandoned_workers: "set[threading.Thread]" = set()
_bypass_abandoned_lock = threading.Lock()


def register_abandoned_bypass_worker(worker: "threading.Thread") -> None:
    """FIX-3 piece 1: record a worker the outer join abandoned (still alive past
    the deadline) into the LIVE registry so the end-of-run drain can attempt to
    reclaim it. Thread-safe. Idempotent (a set). The worker self-deregisters in
    its own finally; the `is_alive()` filter in count/drain prunes any
    already-dead entry from the register/deregister race."""
    with _bypass_abandoned_lock:
        _bypass_abandoned_workers.add(worker)


def deregister_abandoned_bypass_worker(worker: "threading.Thread") -> None:
    """FIX-3 piece 1: remove a worker from the LIVE registry. Called from the
    worker's OWN finally so a worker that eventually terminates (after being
    abandoned) drops out of the live gauge. Thread-safe; no-op if not present."""
    with _bypass_abandoned_lock:
        _bypass_abandoned_workers.discard(worker)


def bypass_live_leaked_count() -> int:
    """FIX-3 piece 1: count abandoned workers that are STILL ALIVE right now —
    the LIVE gauge, distinct from the CUMULATIVE `bypass_leaked_worker_count`.
    Counts only `is_alive()` threads so a dead-but-not-yet-deregistered entry
    (register/deregister race) is not over-counted. Thread-safe snapshot."""
    with _bypass_abandoned_lock:
        return sum(1 for t in _bypass_abandoned_workers if t.is_alive())


def _bypass_drain_budget_seconds() -> float:
    """Resolve the drain budget (seconds) from PG_BYPASS_DRAIN_SECONDS, else the
    named default. A malformed/<=0 value falls back to the default — mirrors the
    `_get_bypass_inflight_semaphore` parse pattern; a bad knob must never disable
    the drain (LAW VI)."""
    raw = os.getenv(PG_BYPASS_DRAIN_SECONDS_ENV)
    if raw is not None and raw.strip():
        try:
            parsed = float(raw)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
    return _BYPASS_DRAIN_SECONDS_DEFAULT


def drain_bypass_workers(budget: "float | None" = None) -> int:
    """FIX-3 piece 1: BOUNDED best-effort join of the abandoned-worker registry.

    Joins each registered worker with a per-worker `join(timeout=remaining)`
    where `remaining` is whatever is left of the total `budget` (default
    PG_BYPASS_DRAIN_SECONDS / `_BYPASS_DRAIN_SECONDS_DEFAULT`). The TOTAL drain
    can never exceed the budget — a wedged worker consumes the rest of the
    budget and the loop then breaks, so the drain NEVER re-introduces the
    #554-class hang. After the bounded join it prunes every dead thread from the
    registry and returns the number of workers STILL ALIVE (the residual live
    leak — typically C-wedged Playwright workers that cannot be joined
    in-process).

    Returns the residual live count (0 when everything was reclaimed).
    """
    budget = _bypass_drain_budget_seconds() if budget is None else max(0.0, budget)
    deadline = _time_module.monotonic() + budget
    with _bypass_abandoned_lock:
        snapshot = list(_bypass_abandoned_workers)
    for worker in snapshot:
        remaining = deadline - _time_module.monotonic()
        if remaining <= 0:
            break
        try:
            worker.join(timeout=remaining)
        except Exception:  # noqa: BLE001 — best-effort; a join error never breaks the run
            pass
    # Prune dead threads from the registry (cooperative cases that terminated,
    # plus any dead-from-the-race entry) and report the residual live count.
    with _bypass_abandoned_lock:
        for worker in list(_bypass_abandoned_workers):
            if not worker.is_alive():
                _bypass_abandoned_workers.discard(worker)
        return sum(1 for t in _bypass_abandoned_workers if t.is_alive())


# ---------------------------------------------------------------------------
# BB5-S03 (#1177): SIGSEGV-mitigated shared trafilatura extractor.
#
# `trafilatura.extract` runs libxml2 (a C extension). On a pathological /
# malformed / adversarial document libxml2 can SIGSEGV (drb_76 exit 139) — a
# C-level crash that is NOT a Python exception and CANNOT be caught by
# `except Exception`. A try/except around the call is false confidence.
#
# True containment is a per-page hard-killable subprocess, but that is heavy at
# hundreds of calls/run AND `resource` RLIMIT is Unix-only (no-op on win32).
# So the DEFAULT is lean MITIGATION (not containment): size-bound the HTML and
# prefer the caller's regex fallback for oversized/suspect docs, which never
# enters libxml2 at all. An optional hard-killable subprocess path is gated
# behind `PG_TRAFILATURA_SUBPROCESS=1` (OFF by default).
#
# Lives in access_bypass (NOT live_retriever): live_retriever already imports
# access_bypass, so the reverse import would be circular. Both trafilatura
# sites import this one guarded entrypoint.
# ---------------------------------------------------------------------------

# Upper bound (chars) on HTML handed to libxml2 via trafilatura. A document
# larger than this is treated as suspect/oversized: we skip trafilatura and
# signal the caller to use its regex fallback (which never enters the C
# extension). Env-overridable. Named constant (LAW VI).
_TRAFILATURA_MAX_HTML_CHARS = int(
    os.getenv("PG_TRAFILATURA_MAX_HTML_CHARS", "3000000")
)
PG_TRAFILATURA_SUBPROCESS_ENV = "PG_TRAFILATURA_SUBPROCESS"
# Hard wall-clock for the optional subprocess extractor path (seconds).
_TRAFILATURA_SUBPROCESS_TIMEOUT = float(
    os.getenv("PG_TRAFILATURA_SUBPROCESS_TIMEOUT_SECONDS", "20")
)


def _html_is_extract_safe(html: str) -> bool:
    """BB5-S03 (#1177): cheap pre-validation gate. Returns False for an
    oversized document (over `_TRAFILATURA_MAX_HTML_CHARS`) that should bypass
    libxml2 entirely. Pure size check — no parsing, never itself crashes."""
    if not html:
        return False
    if len(html) > _TRAFILATURA_MAX_HTML_CHARS:
        return False
    return True


def _trafilatura_extract_subprocess(html: str, **kwargs: Any) -> "str | None":
    """BB5-S03 (#1177): run `trafilatura.extract` in a hard-killable child
    process so a libxml2 SIGSEGV takes down the child (exit 139) instead of the
    sweep. Returns the extracted text, or None on timeout/crash/error.

    Gated OFF by default (`PG_TRAFILATURA_SUBPROCESS=1` to enable) — true
    containment is heavy at hundreds of calls/run. Best-effort: any failure
    (spawn error, non-zero exit incl. -11/139 SIGSEGV, timeout) returns None so
    the caller falls back to regex extraction. Never raises."""
    import json
    import subprocess

    payload = json.dumps({"html": html, "kwargs": kwargs})
    code = (
        "import sys, json\n"
        "data = json.loads(sys.stdin.read())\n"
        "import trafilatura\n"
        "out = trafilatura.extract(data['html'], **data['kwargs']) or ''\n"
        "sys.stdout.write(out)\n"
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            input=payload,
            capture_output=True,
            text=True,
            timeout=_TRAFILATURA_SUBPROCESS_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
        logger.warning(
            "[ACCESS] BB5-S03 trafilatura subprocess failed (%s) — "
            "regex fallback", type(exc).__name__,
        )
        return None
    if proc.returncode != 0:
        # A negative return code is a signal (e.g. -11 == SIGSEGV / exit 139):
        # the child crashed on a pathological doc and the SWEEP survived.
        logger.warning(
            "[ACCESS] BB5-S03 trafilatura subprocess exited rc=%s "
            "(SIGSEGV-class crash contained) — regex fallback",
            proc.returncode,
        )
        return None
    return proc.stdout or None


def safe_trafilatura_extract(html: str, **kwargs: Any) -> "str | None":
    """BB5-S03 (#1177): the ONE guarded trafilatura entrypoint used by every
    extraction site (live_retriever `_strip_html`, access_bypass
    `_try_crawl4ai`).

    Contract:
      - Returns extracted text (str) on success, or None when extraction is
        unsafe/empty/failed (caller falls back to its own regex path).
      - Honest MITIGATION, not containment, on the default in-process path:
        an oversized/suspect doc skips libxml2 (returns None → regex fallback);
        a SIGSEGV on a doc that passes the size gate is still uncatchable
        in-process. Enable `PG_TRAFILATURA_SUBPROCESS=1` for true containment.
      - Never raises (the C-extension SIGSEGV is the one thing it cannot
        promise to catch on the in-process path — documented, not hidden)."""
    if not _html_is_extract_safe(html):
        return None
    if os.getenv(PG_TRAFILATURA_SUBPROCESS_ENV, "0") == "1":
        return _trafilatura_extract_subprocess(html, **kwargs)
    try:
        import trafilatura  # type: ignore
        return trafilatura.extract(html, **kwargs) or None
    except Exception as exc:  # noqa: BLE001 — Python-level errors only; a
        # libxml2 SIGSEGV is NOT a Python exception and escapes this guard (by
        # design — that is what PG_TRAFILATURA_SUBPROCESS=1 contains).
        logger.debug(
            "[ACCESS] BB5-S03 trafilatura in-process extract error (%s) — "
            "regex fallback", type(exc).__name__,
        )
        return None


# Fields the metadata callers actually consume (src/utils/ingest.py). The
# subprocess door serializes exactly these to JSON and the parent rebuilds a
# lightweight object exposing the same attributes — never the live trafilatura
# Document (it does not survive a process boundary).
_TRAFILATURA_METADATA_FIELDS = ("title", "author", "date", "description")


def _trafilatura_metadata_subprocess(html: str) -> "Any | None":
    """GH #1260: run `trafilatura.extract_metadata` in a hard-killable child so
    a libxml2 SIGSEGV takes down the child (exit 139 / Windows 0xC0000005)
    instead of the sweep. Returns an object exposing the four consumed metadata
    fields, or None on timeout/crash/error. Never raises."""
    import json
    import subprocess
    from types import SimpleNamespace

    payload = json.dumps({"html": html})
    code = (
        "import sys, json\n"
        "data = json.loads(sys.stdin.read())\n"
        "import trafilatura\n"
        "meta = trafilatura.extract_metadata(data['html'])\n"
        "fields = " + repr(list(_TRAFILATURA_METADATA_FIELDS)) + "\n"
        "out = {} if meta is None else {\n"
        "    f: (lambda v: None if v is None else str(v))(getattr(meta, f, None))\n"
        "    for f in fields\n"
        "}\n"
        "sys.stdout.write(json.dumps(out))\n"
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            input=payload,
            capture_output=True,
            text=True,
            timeout=_TRAFILATURA_SUBPROCESS_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
        logger.warning(
            "[ACCESS] BB5-S03 trafilatura metadata subprocess failed (%s) — "
            "skip", type(exc).__name__,
        )
        return None
    if proc.returncode != 0:
        logger.warning(
            "[ACCESS] BB5-S03 trafilatura metadata subprocess exited rc=%s "
            "(SIGSEGV-class crash contained) — skip", proc.returncode,
        )
        return None
    raw = (proc.stdout or "").strip()
    if not raw:
        return None
    try:
        fields = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return SimpleNamespace(**{
        f: fields.get(f) for f in _TRAFILATURA_METADATA_FIELDS
    })


def safe_trafilatura_extract_metadata(html: str) -> "Any | None":
    """GH #1260: the ONE guarded `trafilatura.extract_metadata` entrypoint.
    `extract_metadata` enters libxml2 exactly like `extract`, so it carries the
    SAME uncatchable-SIGSEGV surface — it must pass through the SAME size gate
    and the SAME `PG_TRAFILATURA_SUBPROCESS` containment.

    Returns an object exposing `.title/.author/.date/.description` (str or
    None) on success, or None when extraction is unsafe/empty/failed (caller
    falls back to its own BS4 metadata path). Cannot return the live
    trafilatura Document on the subprocess path (it does not cross a process
    boundary); the four consumed fields are preserved on a SimpleNamespace.
    Never raises (the in-process libxml2 SIGSEGV is the one thing it cannot
    promise to catch — that is what PG_TRAFILATURA_SUBPROCESS=1 contains)."""
    if not _html_is_extract_safe(html):
        return None
    if os.getenv(PG_TRAFILATURA_SUBPROCESS_ENV, "0") == "1":
        return _trafilatura_metadata_subprocess(html)
    try:
        import trafilatura  # type: ignore
        return trafilatura.extract_metadata(html)
    except Exception as exc:  # noqa: BLE001 — Python-level errors only; a
        # libxml2 SIGSEGV is NOT a Python exception and escapes this guard (by
        # design — that is what PG_TRAFILATURA_SUBPROCESS=1 contains).
        logger.debug(
            "[ACCESS] BB5-S03 trafilatura in-process metadata error (%s) — "
            "skip", type(exc).__name__,
        )
        return None

# ---------------------------------------------------------------------------
# Firecrawl free-plan hardening: rate limiter + credit tracker
# ---------------------------------------------------------------------------

_firecrawl_last_request_time: float = 0.0
_firecrawl_credits_used: int = 0

# Load config from env (imported at module level for speed)
_FIRECRAWL_MIN_INTERVAL = float(os.getenv("FIRECRAWL_MIN_INTERVAL_SECONDS", "6.0"))
_FIRECRAWL_MONTHLY_QUOTA = int(os.getenv("FIRECRAWL_MONTHLY_QUOTA", "500"))
_FIRECRAWL_WARN_PCT = float(os.getenv("FIRECRAWL_WARN_THRESHOLD_PCT", "0.80"))

# ---------------------------------------------------------------------------
# I-bug-775 (#815): NCBI PMC BioC full-text limiter. Conservative per Codex
# decision — max 1 concurrent + a min-interval (~3 req/s), NOT the API-key 10rps
# allowance (the BioC endpoint is separate from E-Utilities and we do not assume
# it honours the key). Lazy-init the semaphore so it binds to the running loop.
# ---------------------------------------------------------------------------
_ncbi_semaphore: "asyncio.Semaphore | None" = None
# I-arch-007 (#1264): NCBI/PMC-BioC per-loop semaphore map — mirrors the I-pipe-002 (#1227)
# crawl4ai fix. The single module-global above bound to the FIRST acquiring loop and raised
# `RuntimeError: <Semaphore> is bound to a different event loop` when the post-generation
# contract-frame fetch ran in a different loop than retrieval (the cQ76 / clean_deepseek crash
# that failed every PMC-BioC full-text fetch -> empty spans -> strict_verify over-drop).
_ncbi_perloop_semaphores: "weakref.WeakKeyDictionary[Any, asyncio.Semaphore]" = (
    weakref.WeakKeyDictionary()
)
_ncbi_last_request_time: float = 0.0
_NCBI_MIN_INTERVAL = float(os.getenv("PG_NCBI_MIN_INTERVAL_SECONDS", "0.34"))  # ~3 req/s
_PMC_BIOC_MIN_FULLTEXT_CHARS = int(os.getenv("PG_PMC_BIOC_MIN_FULLTEXT_CHARS", "1000"))

# BioC passage section_types that are NOT article body (so a doc with ONLY these
# is abstract-only / references-only and must be rejected per Codex guardrail).
_BIOC_NON_BODY_SECTIONS = frozenset({
    "TITLE", "ABSTRACT", "REF", "COMP_INT", "AUTH_CONT", "ACK_FUND",
    "SUPPL", "FIG", "TABLE", "KEYWORD", "ABBR",
})


def _get_ncbi_semaphore() -> "asyncio.Semaphore":
    """NCBI/PMC-BioC concurrency gate (max 1), bound to the RUNNING loop.

    I-arch-007 (#1264): mirrors the I-pipe-002 (#1227) crawl4ai per-loop fix. MUST be called
    from inside the running loop (the `async with` site). Default (PG_CRAWL4AI_PERLOOP_SEMAPHORE
    != '0'): one `asyncio.Semaphore` per running loop, keyed by the loop in a WeakKeyDictionary —
    so the post-generation contract-frame fetch (which runs in a fresh loop, distinct from the
    retrieval loop) gets a semaphore bound to ITSELF and the `async with` never raises the
    cross-loop `RuntimeError: <Semaphore> is bound to a different event loop` (the cQ76 killer:
    every PMC-BioC full-text fetch failed -> empty spans -> strict_verify over-drop ->
    abort_excessive_gap). Old path ('0'): the single loop-bound module-global (preserved verbatim).
    """
    if not _crawl4ai_perloop_enabled():
        global _ncbi_semaphore
        if _ncbi_semaphore is None:
            _ncbi_semaphore = asyncio.Semaphore(1)
        return _ncbi_semaphore
    loop = asyncio.get_running_loop()
    with _crawl4ai_perloop_lock:
        sem = _ncbi_perloop_semaphores.get(loop)
        if sem is None:
            sem = asyncio.Semaphore(1)
            _ncbi_perloop_semaphores[loop] = sem
        return sem


def _get_jina_semaphore() -> "asyncio.Semaphore":
    """Jina concurrency gate, bound to the RUNNING loop (I-arch-007 #1264).

    Mirrors `_get_ncbi_semaphore` / the I-pipe-002 (#1227) crawl4ai per-loop fix. Default
    (PG_CRAWL4AI_PERLOOP_SEMAPHORE != '0'): one `asyncio.Semaphore` per running loop so the
    post-generation contract-frame fetch (fresh loop) never hits the cross-loop RuntimeError.
    Old path ('0'): the single loop-bound module-global (preserved verbatim).
    """
    jina_concurrency = int(os.getenv("PG_JINA_CONCURRENCY", "2"))
    if not _crawl4ai_perloop_enabled():
        global _jina_semaphore
        if _jina_semaphore is None:
            _jina_semaphore = asyncio.Semaphore(jina_concurrency)
        return _jina_semaphore
    loop = asyncio.get_running_loop()
    with _crawl4ai_perloop_lock:
        sem = _jina_perloop_semaphores.get(loop)
        if sem is None:
            sem = asyncio.Semaphore(jina_concurrency)
            _jina_perloop_semaphores[loop] = sem
        return sem


def _parse_bioc_fulltext(raw: str) -> str:
    """I-bug-775 (#815): extract body full text from a PMC BioC_json response.

    Returns '' (reject) if the response is an error, abstract-only, or
    references-only — Codex guardrail: never accept non-full-text. Accepts only
    when there is an explicit body section (INTRO/METHODS/RESULTS/DISCUSS/CONCL/
    CASE/...) OR a clearly article-sized passage set (>=5 passages, >=3000 chars)
    for OA docs whose passages lack section_type infons.
    """
    import json
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return ""
    collections = data if isinstance(data, list) else [data]
    all_parts: list[str] = []
    has_body_section = False
    for coll in collections:
        if not isinstance(coll, dict):
            continue
        for doc in coll.get("documents", []) or []:
            for psg in doc.get("passages", []) or []:
                ptext = (psg.get("text") or "").strip()
                if not ptext:
                    continue
                all_parts.append(ptext)
                infons = psg.get("infons") or {}
                section = str(
                    infons.get("section_type") or infons.get("type") or ""
                ).upper()
                if section and section not in _BIOC_NON_BODY_SECTIONS:
                    has_body_section = True
    if not all_parts:
        return ""
    total_len = sum(len(p) for p in all_parts)
    # Reject abstract/refs/error-only: require a body section OR an article-sized
    # passage set.
    if not has_body_section and not (len(all_parts) >= 5 and total_len >= 3000):
        return ""
    return "\n\n".join(all_parts).strip()


async def _firecrawl_rate_limit() -> None:
    """Enforce minimum interval between Firecrawl requests (free plan: 10 RPM)."""
    global _firecrawl_last_request_time
    now = _time_module.monotonic()
    elapsed = now - _firecrawl_last_request_time
    if elapsed < _FIRECRAWL_MIN_INTERVAL and _firecrawl_last_request_time > 0:
        wait = _FIRECRAWL_MIN_INTERVAL - elapsed
        logger.info(
            "[ACCESS] Firecrawl rate limit: waiting %.1fs (10 RPM free plan)",
            wait,
        )
        await asyncio.sleep(wait)
    _firecrawl_last_request_time = _time_module.monotonic()


def _firecrawl_has_credits() -> bool:
    """Check if monthly Firecrawl credit quota has remaining credits."""
    if _firecrawl_credits_used >= _FIRECRAWL_MONTHLY_QUOTA:
        logger.error(
            "[ACCESS] Firecrawl monthly quota exhausted: %d/%d credits used",
            _firecrawl_credits_used,
            _FIRECRAWL_MONTHLY_QUOTA,
        )
        return False
    return True


def _firecrawl_track_credit() -> None:
    """Increment Firecrawl credit counter and warn at threshold."""
    global _firecrawl_credits_used
    _firecrawl_credits_used += 1
    pct = _firecrawl_credits_used / _FIRECRAWL_MONTHLY_QUOTA
    if pct >= _FIRECRAWL_WARN_PCT:
        logger.warning(
            "[ACCESS] Firecrawl credit warning: %d/%d used (%.0f%% of monthly quota)",
            _firecrawl_credits_used,
            _FIRECRAWL_MONTHLY_QUOTA,
            pct * 100,
        )


@dataclass
class AccessResult:
    """Result from access attempt."""
    url: str
    content: str
    access_method: str
    legal_alternative: Optional[str]
    success: bool
    metadata: Dict[str, Any]


# FIX-045B: Navigation boilerplate patterns to strip from fetched content
_BOILERPLATE_RE = re.compile(
    r"|".join([
        r"\[Skip to [^\]]*\]",           # [Skip to Main Content], [Skip to Navigation]
        r"\[Jump to [^\]]*\]",           # [Jump to Content]
        r"^\s*Menu\s*$",                 # Standalone "Menu" lines
        r"^\s*Navigation\s*$",           # Standalone "Navigation" lines
        r"^\s*Toggle navigation\s*$",    # Mobile nav toggle
        r"^\s*Search\.\.\.\s*$",         # Search placeholder
        r"^\s*Sign [Ii]n\s*$",          # Standalone sign-in links
        r"^\s*Create [Aa]ccount\s*$",   # Standalone create account
        r"^\s*Log [Ii]n\s*$",           # Standalone login
        r"^\s*Subscribe\s*$",            # Standalone subscribe
        r"^\s*Share on .*$",             # Share on Twitter/Facebook/etc.
        r"^\s*Cookie [Pp]olicy\s*$",    # Cookie policy links
    ]),
    re.MULTILINE,
)


def _strip_navigation_boilerplate(content: str) -> str:
    """FIX-045B: Strip navigation boilerplate from fetched content.

    Removes common HTML-to-markdown artifacts like [Skip to Main Content],
    standalone navigation links, and similar boilerplate that degrades
    evidence quality.
    """
    if not content:
        return content
    cleaned = _BOILERPLATE_RE.sub("", content)
    # Remove runs of blank lines left by stripping
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


# ─────────────────────────────────────────────────────────────────────────────
# BUG-19 (GH #1262): reusable ALLOWLIST-ONLY web-boilerplate hygiene helpers.
#
# THE BUG: the web-crawl chrome that the free fetch backends (Crawl4AI / Jina /
# Firecrawl) prepend to every body — "URL Source:", "Markdown Content:",
# "Title:" header lines, "Split View", "Cite Cite", "Views", "Download full
# text from publisher", "References listed on IDEAS", cookie-consent lines —
# was leaking into the evidence pool as if it were article prose. Worse, a
# *pure* error page (a literal NTSB "Page not found" / "404 Not Found" body)
# was extracted as a "finding sentence" and then passed the entailment gate,
# because boilerplate trivially entails itself ("Page not found" ⊨ "Page not
# found"). A self-entailing chrome line is a faithfulness HOLE, not a finding.
#
# THE FIX: two INPUT-HYGIENE helpers the generator calls BEFORE finding
# extraction and BEFORE the faithfulness gate:
#   • strip_web_boilerplate(text)            — removes ONLY confirmed crawl
#     markers and the lines they sit on.
#   • is_boilerplate_or_nonassertional(s)    — True for a sentence/unit that
#     is pure metadata / nav chrome / a bare DOI / a table-number row / an
#     error-page stub, i.e. carries no assertional content to ground.
#
# WHY FAITHFULNESS IS SAFE (NOT a gate relaxation):
#   • ALLOWLIST-ONLY: every pattern below is a literal, confirmed crawl marker
#     or error-page token. Real prose — including legitimate multilingual
#     content — is byte-preserved; we only delete the known marker lines and
#     flag units that are 100% chrome. We NEVER drop, alter, or down-rank a
#     real claim, and we NEVER touch the strict_verify / NLI / 4-role /
#     span-grounding gates. This is the same WEIGHT/CONSOLIDATE-not-FILTER
#     posture as live_retriever._is_landing_or_abstract_page (§-1.3 DNA):
#     clean the gate's INPUT so it can't "verify" its own chrome; the gate's
#     strictness on real claims is untouched. Removing self-entailing chrome
#     can only RAISE faithfulness — a dropped 404 stub was never a finding.
#
# These are surfaced for callers (the generator) as module-level functions.
# ─────────────────────────────────────────────────────────────────────────────

# Allowlist of literal crawl-chrome MARKER lines. Each entry matches a WHOLE
# line (MULTILINE, case-insensitive). Anchored so a marker word appearing
# mid-sentence in real prose is never matched — only a line that IS the marker.
_WEB_BOILERPLATE_LINE_RE = re.compile(
    r"|".join([
        r"^\s*URL Source\s*:.*$",                       # Jina/Crawl4AI header
        r"^\s*Markdown Content\s*:.*$",                  # Jina/Crawl4AI header
        r"^\s*Title\s*:.*$",                             # crawl Title: header line
        r"^\s*Published Time\s*:.*$",                    # Jina/Crawl4AI header (I-beatboth-010)
        r"^\s*Number of Pages\s*:.*$",                   # Jina/Crawl4AI header (I-beatboth-010)
        r"^\s*Warning:\s*Target URL returned error \d+.*$",  # Jina fetch-error line (I-beatboth-010)
        r"^\s*Split View\s*$",                           # IDEAS/RePEc nav
        r"^\s*Cite\s+Cite\s*$",                          # duplicated cite chrome
        r"^\s*Views?\s*$",                               # bare "Views" counter label
        r"^\s*Download full text from publisher\s*$",    # RePEc/IDEAS chrome
        r"^\s*References listed on IDEAS\s*$",            # IDEAS chrome
        r"^\s*This (website|site) uses cookies.*$",      # cookie-consent banner
        r"^\s*We use cookies.*$",                        # cookie-consent banner
        r"^\s*Accept (all )?[Cc]ookies\s*$",             # cookie-consent button
        r"^\s*Cookie [Cc]onsent\s*$",                    # cookie-consent header
        r"^\s*Manage (your )?[Cc]ookies?.*$",            # cookie-consent button
        # I-beatboth-011 idx 46/68 (#1289): high-precision BODY social-chrome (Scribd / Facebook /
        # YouTube) + journal masthead/ISSN. These sit AFTER ``Markdown Content:`` in the body, so the
        # preamble drop never touches them. EVERY pattern is whole-line + MULTI-TOKEN anchored — a bare
        # "Share"/"Download"/"subscribers"/"cite" in real prose is NEVER matched (the §-1.3 no-real-
        # claim-dropped invariant; only fetch chrome is removed).
        r"^\s*Like\s+Comment\s+Share\s*$",                       # Facebook reaction bar
        r"^\s*Download free for \d+ days\s*$",                   # Scribd upsell (IGNORECASE covers casing)
        r"^\s*Upload Document\s*$",                              # Scribd nav
        r"^\s*blob:https?://localhost[/\w:.\-]*\s*$",            # Facebook inline blob image URL line
        r"^\s*Tap to unmute\s*$",                                # YouTube player chrome
        r"^\s*[\d.,]+[KMB]\s+subscribers\s+Subscribed\b.*$",     # YouTube channel header (K/M/B count REQUIRED — never a bare "1000 subscribers subscribed" prose line)
        r"^\s*Share\s+Save\s+Download\b.*$",                     # YouTube action row
        r"^\s*Cite this paper as\b.*$",                          # journal masthead cite chrome
        r"^\s*ISSN\s*:?\s*\d{4}-\d{3}[\dXx]\s*$",                # bare ISSN identifier row
        # I-beatboth-011 b1 (#1289): publisher login-nav line + image-URL masthead line that leaked into
        # the answer BODY (drb_72 report.md). Whole-line + MULTI-TOKEN anchored — a bare
        # "password"/"image"/"logo" in real prose is NEVER matched (only a line that IS the chrome unit).
        r"^\s*Change Password\s+Old Password\s+New Password\b.*$",   # Wiley/publisher login-nav line (3-token anchored)
        r"^\s*!\[Image\b[^\]]{0,120}\]\([^)\s]{0,300}\)\s*$",        # a line that IS one markdown image ``![Image N: ...](url)``
        # I-beatboth-011 b2 (#1289): whole-LINE forms of the NEW chrome classes (these also appear
        # standalone as their OWN line in some fetched bodies). MULTI-TOKEN / STRUCTURE anchored. These
        # are deliberately TIGHT (no greedy ``.*$`` prose tail): when the chrome is collapsed inline as a
        # PREFIX of a line that continues into real prose (the drb_72 report.md reality), the inline
        # ``_INLINE_SOCIAL_CHROME_RE`` removes the chrome token-only and PRESERVES the prose — a greedy
        # whole-line ``.*$`` here would instead delete the trailing real sentence, so it is forbidden.
        r"^\s*(?:onomic|Economic) Perspectives\s*[—–]\s*Volume\s+\d+,\s*Number\s+\d+(?:\s*[—–]\s*[\w\s]+)?(?:\s*[—–]\s*Pages\s+[\d–\-]+)?\s*$",  # JEP masthead/running-header line (bounded chrome tail only)
        r"^\s*CITATIONS\s+\d+\s+READS\s+\d+\s*$",                    # ResearchGate "CITATIONS N READS N" metadata line
        r"^\s*\d+\s+authors,\s+including\s*:\s*$",                   # ResearchGate "N authors, including:" line (COLON anchored, no prose tail)
        r"^\s*Crossref reports the following \S+ citing(?:\s+this\s+\w+)?\.?\s*$",  # Crossref citing-articles line (bounded)
        r"^\s*Share\s+Help\s*$",                                     # MDPI "Share Help" action bar line
        r"^\s*#main-content\s*$",                                    # MIT skip-to-content nav anchor line
    ]),
    re.MULTILINE | re.IGNORECASE,
)

# Allowlist of literal error-page / "no content" tokens. A UNIT (sentence or
# short body) that is essentially ONLY one of these is a failed fetch, not a
# finding. Matched case-insensitively as a whole-unit signal.
_ERROR_PAGE_TOKENS = (
    "page not found",
    "404 not found",
    "404 - not found",
    "error 404",
    "403 forbidden",
    "access denied",
    # NOTE (Codex P1, #1262): bare "not found" was REMOVED here — as a substring
    # token it silently dropped real NEGATIVE clinical findings ("Metastases were
    # not found"). The literal whole-unit 404 stub ("Not Found") is re-caught by an
    # EXACT whole-unit check in is_boilerplate_or_nonassertional (never a clause).
)

# A bare DOI / identifier row carries no assertional prose to ground.
_BARE_DOI_RE = re.compile(
    r"^\s*(?:doi\s*:?\s*)?10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\s*$",
    re.IGNORECASE,
)

# A pure table-number / metadata row: only digits, separators, units and short
# table glue (e.g. "Table 3 12.4 95% CI 1.2-3.4"). No verb, no clause — nothing
# to entail. Kept deliberately tight (must be SHORT and digit-dominated) so a
# real numeric SENTENCE ("Mortality fell to 12.4% (95% CI ...)" with words) is
# never flagged.
_TABLE_NUMBER_ROW_RE = re.compile(
    r"^\s*(?:table|fig(?:ure)?|row|col(?:umn)?)?\s*[\d.,%()\[\]:;/+\-–—\s]*$",
    re.IGNORECASE,
)

# Max length (chars) for the error-page whole-unit check. An error STUB is
# short; a long article that merely quotes "not found" deep in prose must not
# be flagged. Env-overridable per LAW VI; sane default mirrors the M-23d /
# live_retriever landing-page short-body windows.
_BOILERPLATE_ERROR_UNIT_MAX_CHARS_DEFAULT = 400


def strip_web_boilerplate(text: str) -> str:
    """BUG-19 (#1262): remove ONLY confirmed web-crawl chrome lines from text.

    Allowlist-only, byte-safe hygiene for the generator to call BEFORE finding
    extraction and BEFORE the faithfulness gate. Deletes whole lines that ARE a
    known crawl marker ("URL Source:", "Markdown Content:", "Title:" headers,
    "Split View", "Cite Cite", "Views", "Download full text from publisher",
    "References listed on IDEAS", cookie-consent banners). Real prose — including
    legitimate multilingual content — is preserved byte-for-byte; a marker word
    appearing mid-sentence is never touched because every pattern is whole-line
    anchored.

    FAITHFULNESS: this is INPUT hygiene, not a gate. It can only stop the gate
    from "verifying" its own chrome (self-entailment); it never drops, alters,
    or down-ranks a real claim, and the strict_verify / NLI / 4-role /
    span-grounding gates keep full strictness on everything that remains.
    """
    if not text:
        return text
    cleaned = _WEB_BOILERPLATE_LINE_RE.sub("", text)
    # Collapse blank-line runs left by stripping; preserve paragraph breaks.
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def is_boilerplate_or_nonassertional(sentence: str) -> bool:
    """BUG-19 (#1262): True iff a sentence/unit carries no assertional content.

    Flags (does NOT silently drop — the caller decides, and per §-1.3 a flagged
    unit may still be disclosed at low weight) units that are pure metadata, nav
    chrome, a bare DOI, a table-number row, or an error-page stub:
      • a line that IS a known crawl marker (see strip_web_boilerplate),
      • a bare DOI / identifier row (no prose),
      • a pure table-number / metadata row (digits + separators, no clause),
      • an error-page stub ("Page not found" / "404 Not Found" / "403
        Forbidden" / "Access Denied") when the WHOLE unit is short and is
        essentially only that token — the literal NTSB "Page not found" 404
        body that previously self-entailed through the gate.

    A real assertional sentence (subject + verb + claim, in any language) is
    NEVER flagged: the marker/DOI/table patterns are whole-unit anchored, and
    the error-page check requires a SHORT unit dominated by the error token.

    FAITHFULNESS: pure-chrome / error stubs are not findings; removing them from
    the gate's INPUT raises faithfulness. No real claim can be flagged, and the
    hard gates are untouched.
    """
    if not sentence:
        return True  # empty unit is non-assertional by definition

    stripped = sentence.strip()
    if not stripped:
        return True

    # 1) Whole-line crawl marker.
    if _WEB_BOILERPLATE_LINE_RE.fullmatch(stripped):
        return True

    # 2) Bare DOI / identifier row.
    if _BARE_DOI_RE.fullmatch(stripped):
        return True

    # 3) Pure table-number / metadata row — must contain at least one digit so
    #    a short all-words phrase is not mistaken for a number row, and must be
    #    entirely digits/separators (no alphabetic words beyond table glue).
    if any(ch.isdigit() for ch in stripped) and _TABLE_NUMBER_ROW_RE.fullmatch(
        stripped
    ):
        return True

    # 4) Error-page stub: SHORT unit that is essentially only an error token.
    #    Length-gated so a long article quoting "not found" in prose is safe.
    max_chars = int(
        os.getenv(
            "PG_BOILERPLATE_ERROR_UNIT_MAX_CHARS",
            str(_BOILERPLATE_ERROR_UNIT_MAX_CHARS_DEFAULT),
        )
    )
    if len(stripped) <= max_chars:
        lowered = stripped.lower()
        for token in _ERROR_PAGE_TOKENS:
            if token in lowered:
                # Require the error token to DOMINATE the unit (no surrounding
                # real clause) — the residual after removing the token and
                # non-alphanumerics must be trivially short.
                residual = re.sub(re.escape(token), " ", lowered)
                residual_words = [
                    w for w in re.findall(r"[^\W\d_]+", residual, re.UNICODE)
                    if len(w) > 1
                ]
                if len(residual_words) <= 3:
                    return True
        # Codex P1 (#1262): bare "not found" was removed from _ERROR_PAGE_TOKENS
        # because as a substring it silently dropped real NEGATIVE clinical
        # findings (e.g. "Metastases were not found" → residual "metastases were"
        # ≤3). Re-catch ONLY the literal whole-unit 404 stub: the unit's alpha
        # content is EXACTLY "not found", never a real clause containing it.
        if re.sub(r"[\W_]+", " ", lowered, flags=re.UNICODE).strip() == "not found":
            return True

    return False


# ─────────────────────────────────────────────────────────────────────────────
# I-beatboth-010 (#1288) FIX-A — shared fetch-body cleaner.
#
# The Jina/Crawl4AI reader emits a metadata PREAMBLE before the article body:
#
#     Title: <title>
#     URL Source: <url>
#     Published Time: <ts>
#     Number of Pages: <n>
#     Warning: Target URL returned error 403: Forbidden    (optional)
#     Markdown Content: <the actual article body …>
#
# In the banked v3 corpus 335/586 cited `direct_quote` rows carried this preamble
# verbatim — and ~330 of them had it COLLAPSED INLINE (newlines gone), so the
# whole-line `strip_web_boilerplate` allowlist caught only ~5. The body proper
# always begins after the `Markdown Content:` marker, so the robust, faithfulness-
# safe cleaner DROPS the preamble up to and including that marker, then runs the
# whole-line allowlist for any residual chrome lines. This is INPUT hygiene only:
# the preamble is pure fetch metadata (title / url / timestamp / page count /
# fetch-error), never an assertional claim, so strict_verify / NLI / 4-role /
# span-grounding are untouched. In a fresh run this runs BEFORE the provenance
# quote is built, so span offsets are computed on the cleaned body and stay
# self-consistent.
# ─────────────────────────────────────────────────────────────────────────────

# The `Markdown Content:` marker that separates the Jina reader preamble from the
# article body. Matched case-insensitively anywhere in the head window.
_JINA_MARKDOWN_CONTENT_RE = re.compile(r"Markdown Content\s*:", re.IGNORECASE)

# Bare Jina/Crawl4AI reader marker TOKENS. Some fetched pages embed a SECOND
# reader preamble inline deep in the body (e.g. an aeaweb.org listing page with an
# "About the _AER_" nav block past the head window). These literal tokens are pure
# reader artifacts that never occur in legitimate article prose, so after the
# head-preamble drop they are removed wherever they remain — the token only, the
# surrounding text is preserved (tier weighting handles residual low-value nav).
_JINA_INLINE_TOKEN_RE = re.compile(
    r"(?:URL Source|Markdown Content|Published Time|Number of Pages)\s*:"
    r"|Warning:\s*Target URL returned error \d+:?",
    re.IGNORECASE,
)

# I-beatboth-011 idx 46/68 (#1289): INLINE social-chrome (Scribd / Facebook / YouTube nav + journal
# masthead/ISSN). The banked corpus shows these COLLAPSED inline in the cited body (16x ISSN, 16x
# "Tap to unmute", 13x YouTube "<count>K subscribers Subscribed", 12x "Share Save Download", Scribd
# "Download free for N days", FB "Like Comment Share", masthead "Cite this paper as"), so the
# whole-line allowlist misses them just like the inline reader headers. Each alternative is a
# DISTINCTIVE multi-token chrome signature anchored so it can NEVER match legitimate prose: the
# YouTube subscriber run REQUIRES a K/M/B count (so "1000 subscribers subscribed" in prose is not
# matched), and every other phrase is a fixed multi-word nav literal. Removed token-only; surrounding
# prose is preserved (tier weighting handles residual low-value nav).
_INLINE_SOCIAL_CHROME_RE = re.compile(
    r"|".join([
        r"Like\s+Comment\s+Share",                                   # Facebook reaction bar
        r"Download free for \d+ days",                               # Scribd upsell
        r"Tap to unmute(?:\s+\d+x)?",                                # YouTube player
        r"[\d.,]+[KMB]\s+subscribers\s+Subscribed(?:\s+\d+)?",       # YouTube channel header (K/M count REQUIRED)
        r"Share\s+Save\s+Download(?:\s+Download)?",                  # YouTube action row (sometimes doubled)
        r"Cite this paper as\s*:?",                                  # journal masthead cite chrome
        r"ISSN\s*:?\s*\d{4}-\d{3}[\dXx]",                            # ISSN identifier
        # I-beatboth-011 b1 (#1289): publisher login-nav run + image-URL masthead chrome that leaked into
        # the answer BODY/Key-Findings in the banked v3 run (drb_72 report.md carried the literal Wiley
        # masthead+login-nav run ``.../logo-header-1690978619437.png) ## Change Password Old Password New
        # Password Too Short.[13]...`` cited as a "verified independent source"). These collapse INLINE in
        # the cited body so the whole-line allowlist misses them, exactly like the idx46 social chrome.
        # EVERY pattern is MULTI-TOKEN / STRUCTURE anchored so a bare ``password``/``image``/``logo``/
        # ``favicon`` mid-sentence in real prose is NEVER matched (the §-1.3 no-real-claim-dropped
        # invariant); removed token-only, surrounding prose preserved.
        r"Change Password\s+Old Password\s+New Password"
        r"(?:\s+(?:Very Strong|Too Short|Too Long|Strong|Medium|Weak))*",  # Wiley login-nav run + trailing password-strength meter (anchored to the 3-token form; meter labels stripped ONLY when they follow the login-nav, so a bare "Weak"/"Strong" in real prose is never touched)
        r"!\[Image\b[^\]]{0,120}\]\([^)\s]{0,300}\)",                      # markdown image ``![Image N: ...](url)`` (full structure)
        r"\S*logo-header[-\w]*\.png\)(?:\]\([^)\s]{0,300}\))?",            # masthead image URL ``.../logo-header-<digits>.png)`` (+ optional ``](url)`` link tail)
        r"\S*/pb-assets/\S+",                                              # publisher /pb-assets/ asset URL token
        r"\S*favicon[\w.\-]*\.(?:ico|png|svg|gif|jpe?g)\b",                # favicon image file (extension REQUIRED — never bare "favicon" prose)
        # I-beatboth-011 b2 (#1289): NEW inline chrome classes seen VERBATIM in the drb_72 report.md
        # Key-Findings/Comparative/Implications/Limitations bodies (page furniture that survived
        # strict_verify because chrome IS verbatim source text). Every pattern is MULTI-TOKEN /
        # STRUCTURE anchored so a real economics sentence in ANY language is NEVER screened (the §-1.3
        # no-real-claim-dropped invariant); removed token-only, surrounding prose preserved. Adversarial
        # near-misses these must NOT match: "Trading volume rose; Number 2 ranked…", "12 countries,
        # including Brazil", "see section 2.3.2 for details", "papers in the same series examine wages".
        r"(?:onomic|Economic) Perspectives\s*[—–]\s*Volume\s+\d+,\s*Number\s+\d+",  # JEP masthead/running-header (full AND the truncated "onomic Perspectives—Volume" form; em-dash U+2014 / en-dash U+2013 both handled; "Volume N, Number N" structure anchors it away from prose)
        r"CITATIONS\s+\d+\s+READS\s+\d+",                                  # ResearchGate metadata block ("CITATIONS 12 READS 345")
        r"\d+\s+authors,\s+including\s*:",                                 # ResearchGate author block (COLON discriminates from "12 countries, including Brazil")
        r"Crossref reports the following \S+ citing",                      # ResearchGate/Crossref citing-articles nav
        r"\[\s*Twitter\s*\]\(https?://\S*",                               # markdown share-button "[ Twitter ](http…)"
        r"https?://twitter\.com/intent/\S+",                              # Twitter-intent share URL
        # I-beatboth-011 b2-fix (#1289): Codex diff-review P1 over-strip catches. Three of the b2
        # inline patterns were TOO BROAD under the global IGNORECASE sub() (a real economics sentence
        # could be screened — over-strip is WORSE than a recoverable chrome leak per §-1.1/§-1.3):
        #   • bare ``Share\s+Help\b`` ate lowercase prose ("workers share help to retrain") and is
        #     not structurally tied to MDPI chrome -> REMOVED. The genuine standalone MDPI "Share Help"
        #     action-bar LINE is still screened by the whole-line ``^\s*Share\s+Help\s*$`` allowlist
        #     (above), and any residual inline leak is a recoverable chrome bullet the render-boundary
        #     screen in run_honest_sweep_r3.py drops via a safer path.
        #   • bare ``-\s+Working paper`` matched ordinary markdown/list prose ("- Working paper 245
        #     examines wage effects"); "working paper" is common economics content -> TIGHTENED to the
        #     FULL ILO series-nav literal (the hyphen-led title + the fixed "Insights from job vacancy
        #     data" nav tail are BOTH required), so a bare "- Working paper …" body line is never matched.
        #   • bare three-part ``\d+\.\d+\.\d+ Title Case`` stripped legitimate in-prose section refs
        #     ("Section 2.3.2 Skill-Biased Technological Change shows rising inequality"); it was not
        #     anchored to a TOC-only context -> REMOVED. A TOC-only line is still screened by the
        #     whole-line allowlist path; an in-prose section reference is real content and stays.
        r"-\s+Working paper\s+Insights from job vacancy data\b",          # ILO series-nav run (FULL literal: hyphen-led title + the fixed "Insights from job vacancy data" nav tail BOTH required; a bare "- Working paper …" markdown/list line in real prose is NEVER matched)
        r"\d+\s+Pages\s+-\s+\d+\s+\w+ \d{4}",                             # ILO "56 Pages - 10 February 2026" series-listing run (Pages-date structure; distinct from Jina "Number of Pages:")
        r"#main-content\b",                                               # MIT skip-to-content nav anchor
        # I-beatboth-011 drb_78 (#1289): LOGIN-CTA chrome that leaked into KEPT real-source bodies
        # (a BMJ/Wiley article body whose footer carries ``* [Subscribe](url) * [Log In](url)``) AND
        # into the social-post bodies that this corpus cited as headers. EVERY pattern is STRUCTURE
        # anchored to a markdown CTA-LINK or a login-URL form so a bare ``log in``/``subscribe``/
        # ``sign in`` in real prose is NEVER matched (the §-1.3 no-real-claim-dropped invariant —
        # over-strip is worse than a recoverable leak). The CTA link + its bracketed URL are removed
        # token-only; surrounding prose is preserved (so the real journal body keeps its content,
        # the host screen having already dropped the social-post SOURCES). The optional leading
        # ``*``/``-`` markdown list bullet is consumed with the CTA so a stranded bullet is not left.
        r"(?:[*\-]\s*)?\[\s*Log\s*[Ii]n\s*\]\([^)\s]*\)",                  # markdown ``[Log In](url)`` CTA (login wall)
        r"(?:[*\-]\s*)?\[\s*Sign\s*[Ii]n\s*\]\([^)\s]*\)",                 # markdown ``[Sign In](url)`` CTA
        r"(?:[*\-]\s*)?\[\s*Subscribe\s*\]\([^)\s]*\)",                    # markdown ``[Subscribe](url)`` CTA (publisher paywall nav)
        r"(?:[*\-]\s*)?\[\s*Log\s*[Ii]n\s+to\s+Facebook\s*\]\([^)\s]*\)",  # ``[Log In to Facebook](url)`` CTA
        r"https?://[^\s)]*/login/device-based[^\s)]*",                     # Facebook device-based login URL token
        r"https?://[^\s)]*login_attempt=\d[^\s)]*",                        # any login_attempt=N redirect URL token
    ]),
    re.IGNORECASE,
)

# The reader preamble sits at the very TOP of the fetched content. Only treat a
# `Markdown Content:` marker as the preamble terminator if it appears within this
# many chars of the start, so a stray "Markdown Content:" deep in real prose can
# never truncate a legitimate body. Env-overridable per LAW VI.
_JINA_PREAMBLE_MAX_CHARS_DEFAULT = 4000


@dataclass(frozen=True)
class CleanedFetch:
    """Structured result of :func:`clean_fetch_body` (Codex iter-1 P2 contract).

    ``cleaned_text`` is the article body with crawl-reader chrome removed.
    ``shell_reason`` is ``None`` when the cleaned body carries real assertional
    content, or a short reason string when the WHOLE cleaned unit is a fetch
    shell / boilerplate stub (so the caller can route it to the existing
    METADATA_ONLY / not_extractable gap branch — NOT a new hard drop).
    """

    cleaned_text: str
    shell_reason: "Optional[str]"


def clean_fetch_body(content: "Optional[str]") -> CleanedFetch:
    """Strip Jina/Crawl4AI reader chrome from fetched content (I-beatboth-010).

    Two mechanisms, in order:
      1. If a ``Markdown Content:`` marker appears within the head preamble window,
         drop everything up to and including it — that removes the inline OR
         whole-line ``Title:/URL Source:/Published Time:/Number of Pages:/Warning:``
         preamble that the whole-line allowlist alone misses when the reader
         collapsed the newlines.
      2. Run :func:`strip_web_boilerplate` for any residual whole-line crawl-chrome.

    Returns a :class:`CleanedFetch`. Allowlist-only, faithfulness-neutral input
    hygiene: it removes only confirmed fetch metadata / chrome, never assertional
    prose; the strict_verify / NLI / 4-role / span-grounding gates keep full
    strictness on everything that remains.
    """
    if not content:
        return CleanedFetch(content or "", "empty_fetch_body")

    text = content
    marker = _JINA_MARKDOWN_CONTENT_RE.search(text)
    if marker is not None:
        preamble_max = int(
            os.getenv(
                "PG_JINA_PREAMBLE_MAX_CHARS",
                str(_JINA_PREAMBLE_MAX_CHARS_DEFAULT),
            )
        )
        if marker.start() <= preamble_max:
            text = text[marker.end():]

    text = strip_web_boilerplate(text)
    # Remove any residual inline reader marker tokens (a second embedded preamble
    # deep in the body that the head-window drop + whole-line strip both miss).
    text = _JINA_INLINE_TOKEN_RE.sub(" ", text)
    # I-beatboth-011 idx 46/68: remove inline social-chrome (Scribd/FB/YouTube/masthead) the same way —
    # distinctive multi-token nav literals, anchored so prose is never touched.
    text = _INLINE_SOCIAL_CHROME_RE.sub(" ", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = text.strip()

    shell_reason: "Optional[str]" = None
    if not text:
        shell_reason = "empty_after_clean"
    elif is_boilerplate_or_nonassertional(text):
        shell_reason = "boilerplate_or_error_stub"
    return CleanedFetch(text, shell_reason)


# ─────────────────────────────────────────────────────────────────────────────
# I-wire-013 (#1327): PDF/HTML line-wrap de-hyphenation (truncation-at-source).
#
# A hard line break inside a fetched body frequently splits a word at a trailing
# hyphen ("patent-\ning activity"). When that fragment lands in a STORED, cited
# ``direct_quote`` it later re-anchors / renders as a truncated token ("ning
# activity"). This joins ONLY a hyphen that sits at a hard line break BETWEEN TWO
# LETTERS ("word-\nrest" -> "wordrest"). A legitimate intra-word hyphen
# ("co-author", "GLP-1") is never followed by a newline, so it is preserved
# byte-for-byte; a hyphen before a DIGIT is never joined (GLP-1 stays GLP-1); a
# paragraph break (blank line) is not crossed (single ``\r?\n`` only). The Unicode
# letter class ``[^\W\d_]`` matches accented / CJK letters, so multilingual prose
# is preserved and its own line-wraps repair identically. INPUT HYGIENE ONLY —
# never a faithfulness gate; strict_verify / NLI / 4-role / span-grounding FROZEN.
# ─────────────────────────────────────────────────────────────────────────────
_LINE_WRAP_HYPHEN_RE = re.compile(
    r"(?P<pre>[^\W\d_])"            # a letter (Unicode-aware) ...
    r"[-\u00ad\u2010]"             # ... then a hyphen (ASCII -, soft U+00AD, U+2010) ...
    r"[^\S\r\n]*\r?\n[^\S\r\n]*"    # ... inline ws, ONE hard line break, inline ws ...
    r"(?P<post>[^\W\d_])"          # ... then a letter (NOT a digit -> GLP-1 is safe).
)


def dehyphenate_line_wraps(text: "Optional[str]") -> str:
    """Join PDF/HTML line-wrap hyphens (``"patent-\\ning"`` -> ``"patenting"``).

    ONLY a hyphen at a hard line break BETWEEN TWO LETTERS is removed. A
    legitimate intra-word hyphen (``"co-author"``, ``"GLP-1"``) has no following
    newline and is preserved byte-for-byte; a hyphen before a digit is never
    joined; multilingual content (and its own line-wraps) is handled via the
    Unicode letter class. Pure / deterministic — no model, no network.
    """
    if not text:
        return text or ""
    return _LINE_WRAP_HYPHEN_RE.sub(
        lambda m: m.group("pre") + m.group("post"), text,
    )


# ─────────────────────────────────────────────────────────────────────────────
# I-beatboth (ev_461): deterministic PDF front-matter (masthead) stripper.
#
# A PDF text-extractor (mineru25 / docling / PyMuPDF) pulls the journal MASTHEAD
# as the FIRST run of "content": a running-head token ("PERSPECTIVE"), the title,
# the author + superscript-affiliation list, an "Edited by ..." byline, and the
# editorial submission-date clause ("approved February 28, 2019 (received for
# review January 18, 2019)"). That leading block then becomes a provenance span and
# renders as a "finding" — but a title / author list / submission date is NEVER a
# verifiable claim. This strips ONLY a contiguous LEADING masthead block, on
# PDF-origin content, BEFORE the body is windowed into a span. It is NOT GROBID — a
# lightweight, deterministic, precision-first prefix trimmer.
#
# GROUND TRUTH (the real ev_461 extracted text): the PyMuPDF/MinerU output is
# space-COLLAPSED — the entire masthead AND the first body sentence sit on ONE
# physical line, with no newline between them:
#   "PERSPECTIVE Toward understanding the impact of artificial intelligence on
#    labor Morgan R. Franka, David Autorb, ... Edited by Jose A. Scheinkman, ...,
#    and approved February 28, 2019 (received for review January 18, 2019) Rapid
#    advances in artificial intelligence (AI) ..."
# A LINE-based stripper would no-op (no newline to split on). So this operates on
# the leading CHARACTER region and anchors on the editorial submission-date clause
# — canonically the LAST masthead element — and cuts at its END. That is robust to
# BOTH the single-line collapsed form AND a line-wrapped form.
#
# FAITHFULNESS (the part that can hurt a patient): front-matter is not assertional,
# so removing it cannot drop a finding; the first real body sentence onward is left
# byte-identical. We cut at the END of the editorial submission-date clause and
# never inside prose, so a real sentence that merely CONTAINS a date
# ("...approved February 28, 2019, and enrolled 200 patients.") is body and is
# kept — it has no editorial "(received for review ...)" / "approved <date> (" form.
# When unsure, DO NOT strip — a recoverable bit of masthead is far safer than
# deleting a real claim. INPUT HYGIENE ONLY; strict_verify / NLI / 4-role /
# span-grounding are untouched.
# ─────────────────────────────────────────────────────────────────────────────

# Flag-gate: default ON for PDF origin, env-reversible per LAW VI.
_PDF_FRONTMATTER_STRIP_FLAG_DEFAULT = "1"

# The masthead lives at the very HEAD of the document. The editorial submission-
# date clause that terminates it must START within this many leading chars, else we
# treat a later "(received for review ...)" as a coincidence in body prose and do
# NOT strip. A masthead (running-head + title + ~15-author list + edited-by) is
# comfortably under this; real body almost never opens with this clause.
_FRONTMATTER_HEAD_REGION_CHARS = 2000

_MONTH = (
    r"(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
)
# A date in EITHER US "Month D, YYYY" ("February 28, 2019") OR international
# "D Month YYYY" ("18 January 2019") order, full or 3-letter abbreviated months.
# Recall-broadening is safe: the date only ever matches INSIDE the editorial
# "(received for review ...)" parenthetical below — the paren disambiguates from
# prose, so precision is untouched (Codex/advisor catch: non-US journals).
_DATE = (
    rf"(?:{_MONTH}\.?\s+\d{{1,2}},?\s+\d{{4}}"   # February 28, 2019 / Feb 28 2019
    rf"|\d{{1,2}}\s+{_MONTH}\.?,?\s+\d{{4}})"     # 18 January 2019 / 18 Jan 2019
)

# (a) Running-head banner at the VERY START (case-sensitive ALL-CAPS masthead
# token). Anchored to start so a lowercase "perspective" in prose, or the word
# mid-sentence, is never matched. One of the strong masthead anchors.
_FRONTMATTER_RUNNING_HEAD_RE = re.compile(
    r"^(?:PERSPECTIVE|RESEARCH ARTICLE|REVIEW ARTICLE|BRIEF REPORT|CASE REPORT|"
    r"ARTICLE|LETTERS|LETTER|REVIEW|EDITORIAL|COMMENTARY)\b"
)

# (b) Author/affiliation signature: a capitalized Name immediately followed by a
# superscript-style affiliation marker glued to the surname ("Franka,", "Autorb,",
# "Rahwana,m,n,1") — the distinctive PDF-extraction artifact where the superscript
# letters/digits collapse onto the name. Also the "and <First Last>" author-join.
# This is a strong masthead anchor when it appears in the head region.
_FRONTMATTER_AUTHOR_AFFIL_RE = re.compile(
    r"[A-Z][a-z]+[a-z][a-z](?:,[a-z0-9])+,"        # "Franka," / "Rahwana,m,n,1,"  (name + glued superscripts)
    r"|[A-Z][a-z]+[a-z][a-z],\s+(?:and\s+)?[A-Z][a-z]+"  # "Autorb, and Manuel"
    r"|\band\s+[A-Z][a-z]+\s+[A-Z]\.?\s*[A-Z][a-z]+\b"   # "and Iyad R. Rahwan"
)

# "Edited by ..." byline (PNAS/PNAS-style mastheads). Supporting masthead signal.
_FRONTMATTER_EDITED_BY_RE = re.compile(r"\bEdited by\b", re.IGNORECASE)

# (c) The editorial submission-date clause — the masthead TERMINATOR. VERB-anchored
# to the editorial process ("received for review <date>") inside a parenthetical, so
# an ordinary prose sentence that merely mentions a date is never matched. The
# terminator is the "(received for review <date> ... )" parenthetical:
#   1. "... (received for review <date>)"                       — PNAS canonical.
#   2. "approved/accepted <date> (received for review <date>)"  — leading approve verb.
#   3. "(received for review <date>; accepted <date>)"          — multi-clause paren.
# After the first received-for-review date, an optional BOUNDED run of further
# editorial clauses (``; revised ...; accepted ...``) up to the closing paren is
# tolerated — bounded by ``[^)]{0,80}`` so it can never swallow body prose (a real
# body sentence sits OUTSIDE the paren). Each form captures THROUGH the closing
# paren so the cut lands exactly at the body boundary. ``re.search`` over the head
# region (single-line or wrapped; DOTALL so a wrapped clause still matches).
_FRONTMATTER_DATE_TERMINATOR_RE = re.compile(
    rf"(?:(?:approved|accepted|received|revised)\s+{_DATE}\s*)?"  # optional leading "approved <date>"
    rf"\(\s*received for review\s+{_DATE}[^)]{{0,80}}\)"          # (received for review <date>[; ...])
    rf"|received for review\s+{_DATE}[^)]{{0,80}}\)",             # ... received for review <date>[; ...])
    re.IGNORECASE | re.DOTALL,
)


def strip_pdf_frontmatter(text: "Optional[str]") -> str:
    """Strip a contiguous LEADING journal-masthead block from PDF-extracted text.

    Anchors on the editorial submission-date clause ("(received for review <Month
    day, year>)"), which is canonically the LAST masthead element, and cuts the
    document at the END of that clause — so the running-head banner, title, author/
    affiliation list, "Edited by" byline and submission dates are removed and the
    body begins at the next character. Works on the real (space-collapsed,
    single-line) PDF-extraction output AND on line-wrapped output, because it is
    character-offset based, not line based.

    Conservative guards (when unsure, DO NOT strip — faithfulness overrides):
      * The editorial date clause must START within the leading ``_FRONTMATTER_
        HEAD_REGION_CHARS`` of the document (a masthead is at the head; a stray
        "(received for review ...)" deep in prose is left alone).
      * A STRONG masthead anchor must also appear BEFORE that clause in the head
        region: a start-of-document running-head banner, OR an author/affiliation
        signature, OR an "Edited by" byline. A lone date clause does not trigger a
        strip.
      * Only ever removes a leading PREFIX up to the clause end; never scans nor
        cuts mid-body. The body from the first post-clause character is byte-
        identical.
      * If no editorial date clause / no anchor is found, returns the input
        UNCHANGED. If the cut would leave no body (masthead-only fetch), returns
        the input UNCHANGED (nothing to protect; downstream thin/shell gates
        handle an all-masthead body).

    Pure / deterministic — no model, no network. Flag-gated (default ON) by
    PG_PDF_FRONTMATTER_STRIP per LAW VI.
    """
    if not text:
        return text or ""
    if os.getenv(
        "PG_PDF_FRONTMATTER_STRIP", _PDF_FRONTMATTER_STRIP_FLAG_DEFAULT
    ).strip().lower() in ("0", "false", "no", "off"):
        return text

    head = text[:_FRONTMATTER_HEAD_REGION_CHARS]

    term = _FRONTMATTER_DATE_TERMINATOR_RE.search(head)
    if term is None:
        return text  # no editorial submission-date clause in the head -> no strip

    cut = term.end()

    # STRONG-anchor requirement (precision-first): the region BEFORE the date clause
    # must carry a masthead signature, else this date clause is not a masthead
    # terminator and we do not strip.
    before = head[: term.start()]
    has_running_head = bool(_FRONTMATTER_RUNNING_HEAD_RE.search(text.lstrip()[:60]))
    has_author_affil = bool(_FRONTMATTER_AUTHOR_AFFIL_RE.search(before))
    has_edited_by = bool(_FRONTMATTER_EDITED_BY_RE.search(before))
    if not (has_running_head or has_author_affil or has_edited_by):
        return text

    body = text[cut:].lstrip(" \t\r\n.")
    # Never return empty / whitespace-only when the input had content: if the cut
    # leaves no body (masthead-only fetch), leave the input untouched — there is no
    # claim to protect and the thin/shell gates downstream handle it.
    if not body.strip():
        return text
    return body


# M-23c: Structural markers for content quality scoring.
# Presence of academic-paper markers indicates full article body
# (vs paywall stub or landing page).
_STRUCTURAL_MARKERS = (
    "abstract", "methods", "results", "conclusion",
    "discussion", "introduction", "background", "references",
    "materials and methods", "statistical analysis",
)

_NUMERIC_TOKEN_RE = re.compile(r"\d+\.\d+|\d+\s*%|\d{3,}|\bp\s*[<=>]\s*0\.\d+\b")


def _score_content_quality(content: str) -> float:
    """Score a fetched-content candidate on quality (0.0 .. ~1.5).

    Combines normalized length, structural-marker hits, and numeric
    density. Fully stripped stubs and paywall shells score low; full
    article bodies with numeric data score high. Used to pick the winner
    when multiple concurrent backends (Crawl4AI, Jina, Trafilatura)
    return successful results — replaces first-success-wins, which let
    Jina stubs beat Crawl4AI full-article fetches.

    This is NOT just length: a long paywall page with repeated
    "subscribe to read" blocks will have no structural markers and low
    numeric density, so it loses to a shorter true article body.
    """
    if not content:
        return 0.0

    length = len(content)
    # 30K chars normalizes to 1.0 — NEJM/Lancet full articles are ~40-70K
    length_norm = min(length / 30000.0, 1.0)

    lower = content.lower()
    marker_hits = sum(1 for m in _STRUCTURAL_MARKERS if m in lower)
    marker_score = min(marker_hits / 6.0, 1.0)

    numeric_count = len(_NUMERIC_TOKEN_RE.findall(content))
    # Numeric tokens per KB of text; cap at 1.0
    density = min(numeric_count / max(length / 1000.0, 1.0) / 5.0, 1.0)

    return 0.5 * length_norm + 0.3 * marker_score + 0.2 * density


def _crawl4ai_failure_result(url: str, error: str) -> AccessResult:
    """Build a standard failure AccessResult for crawl4ai.

    FIX-EPIPE: Extracted to reduce duplication across the many except
    branches in _try_crawl4ai.
    """
    return AccessResult(
        url=url,
        content="",
        access_method="crawl4ai",
        legal_alternative=None,
        success=False,
        metadata={"error": error[:200]},
    )


def _crawl4ai_track_failure() -> None:
    """FIX-EPIPE: Increment crawl4ai failure counter and open circuit breaker
    if threshold is reached. Extracted to avoid duplicating the circuit
    breaker logic in every except branch."""
    global _crawl4ai_consecutive_failures, _crawl4ai_circuit_open_until
    _crawl4ai_consecutive_failures += 1
    if _crawl4ai_consecutive_failures >= _CRAWL4AI_CIRCUIT_BREAKER_THRESHOLD:
        _crawl4ai_circuit_open_until = (
            _time_module.time() + _CRAWL4AI_CIRCUIT_BREAKER_COOLDOWN
        )
        logger.warning(
            "[polaris graph] CRAWL4AI: FIX-EPIPE circuit breaker OPENED "
            "after %d consecutive failures (cooldown %.0fs)",
            _crawl4ai_consecutive_failures,
            _CRAWL4AI_CIRCUIT_BREAKER_COOLDOWN,
        )


async def _safe_close_crawler(crawler: Any, url: str) -> None:
    """FIX-EPIPE: Safely close a crawl4ai AsyncWebCrawler instance.

    When the Playwright browser subprocess dies (EPIPE on websocket close),
    calling __aexit__ on the crawler will attempt to close the dead socket
    and raise BrokenPipeError. This function catches ALL exceptions from
    __aexit__ to prevent the cleanup from killing the server.

    Args:
        crawler: The AsyncWebCrawler instance to close.
        url: The URL being fetched (for logging only).
    """
    if crawler is None:
        return
    try:
        await crawler.__aexit__(None, None, None)
    except (BrokenPipeError, ConnectionError, OSError) as exit_err:
        # PRIMARY CRASH VECTOR: Browser subprocess died, socket is broken.
        # This is expected and non-fatal -- the crawl result (if any) is
        # already captured.
        logger.warning(
            "[polaris graph] CRAWL4AI: FIX-EPIPE browser cleanup pipe "
            "error for %s (non-fatal, server protected): %s: %s",
            _safe_log_str(url, 60),
            type(exit_err).__name__,
            _safe_log_str(str(exit_err)),
        )
    except asyncio.CancelledError:
        # Task cancellation during cleanup -- non-fatal.
        logger.warning(
            "[polaris graph] CRAWL4AI: FIX-EPIPE browser cleanup "
            "cancelled for %s (non-fatal)",
            _safe_log_str(url, 60),
        )
    except Exception as exit_err:
        logger.warning(
            "[polaris graph] CRAWL4AI: FIX-EPIPE browser cleanup "
            "exception for %s (non-fatal): %s: %s",
            _safe_log_str(url, 60),
            type(exit_err).__name__,
            _safe_log_str(str(exit_err)),
        )
    except BaseException as exit_err:
        # Even GeneratorExit or exotic BaseException subclasses from
        # native Playwright extensions must not kill the server.
        if isinstance(exit_err, (KeyboardInterrupt, SystemExit)):
            logger.warning(
                "[polaris graph] CRAWL4AI: FIX-EPIPE browser cleanup "
                "interrupted for %s -- re-raising",
                _safe_log_str(url, 60),
            )
            raise
        logger.warning(
            "[polaris graph] CRAWL4AI: FIX-EPIPE browser cleanup "
            "BaseException for %s (non-fatal, server protected): %s: %s",
            _safe_log_str(url, 60),
            type(exit_err).__name__,
            _safe_log_str(str(exit_err)),
        )


# ---------------------------------------------------------------------------
# I-bug-114 (#551): per-backend hard wall-clock bound for the concurrent fetch
# fan-out. A single backend wedged in a Playwright op must not freeze the whole
# `asyncio.gather`. `_bounded_backend` returns within PG_BACKEND_FETCH_TIMEOUT
# + PG_BACKEND_CLEANUP_GRACE regardless of backend state — it uses
# `asyncio.wait` (which returns after its timeout unconditionally) and never
# `asyncio.wait_for` (which would await the cancelled coroutine's cleanup).
# The post-artifacts asyncio.run-teardown residual is tracked in #552.
# ---------------------------------------------------------------------------

# Strong refs to backend tasks abandoned after the cancel-grace window — kept
# so they are not GC-warned; the done-callback also retrieves any exception.
_DETACHED_BACKEND_TASKS: "set[asyncio.Task]" = set()


def _backend_fetch_timeout() -> float:
    """Per-backend in-flight wall-clock ceiling (seconds)."""
    try:
        return float(os.getenv("PG_BACKEND_FETCH_TIMEOUT", "60.0"))
    except ValueError:
        return 60.0


def _backend_cleanup_grace() -> float:
    """Bounded grace window for a cancelled backend's cleanup (seconds)."""
    try:
        return float(os.getenv("PG_BACKEND_CLEANUP_GRACE", "10.0"))
    except ValueError:
        return 10.0


def _drain_detached(task: "asyncio.Task") -> None:
    """Done-callback for a detached backend task: drop the strong ref and
    retrieve any exception so asyncio does not log 'exception never retrieved'.
    """
    _DETACHED_BACKEND_TASKS.discard(task)
    if not task.cancelled():
        try:
            task.exception()
        except Exception:  # noqa: BLE001 — exception retrieval is best-effort
            pass


def _force_drop_detached_task(task: "asyncio.Task") -> None:
    """I-cd-032 (#632): forcibly remove a wedged detached task from the
    main asyncio loop's await-list at teardown.

    `asyncio.run`'s built-in shutdown calls `_cancel_all_tasks` which
    `await`s every still-pending task. If a detached backend ignores
    cancellation, that await is unbounded.

    Mitigation: close the task's underlying coroutine via
    `_coro.close()` — this raises GeneratorExit in the coroutine,
    cleanup runs synchronously, and the task is finalized as cancelled
    so `_cancel_all_tasks` does not have to await it.

    Best-effort: if `_coro` is not accessible OR `close()` itself blocks
    (it shouldn't — close just raises GeneratorExit into the frame), the
    fallback path drops the strong reference and lets asyncio teardown
    proceed with the standard cancellation + await behavior.

    Called by an `asyncio.run`-teardown hook installed at run start.
    """
    if task.done():
        return
    coro = getattr(task, "_coro", None)
    if coro is None:
        return
    try:
        # close() raises GeneratorExit into the coroutine's current
        # suspension point, which runs any finally/except blocks but
        # cannot await anything new (GeneratorExit suppresses yields).
        coro.close()
    except Exception:  # noqa: BLE001 — close() must never raise here
        pass
    _DETACHED_BACKEND_TASKS.discard(task)


def install_teardown_drain_hook(loop: "asyncio.AbstractEventLoop") -> None:
    """I-cd-032 (#632) DEPRECATED — hooking loop.close() runs too late:
    `asyncio.run` calls `_cancel_all_tasks` (which awaits every pending
    task) BEFORE `loop.close()`, so a wedged detached task hangs the
    cancel-all phase. Use `polaris_asyncio_run()` below instead. Kept
    as a thin shim that ALSO patches `_cancel_all_tasks` for callers
    that already use `asyncio.run` directly.
    """
    original_close = loop.close

    def _drain_then_close() -> None:
        for task in list(_DETACHED_BACKEND_TASKS):
            _force_drop_detached_task(task)
        original_close()

    loop.close = _drain_then_close  # type: ignore[method-assign]


def polaris_asyncio_run(coro: Any) -> Any:
    """I-cd-032 (#632): drop-in replacement for `asyncio.run` that
    drains wedged detached backend tasks BEFORE the loop's
    `_cancel_all_tasks` phase awaits them.

    Sequence:
      1. Create a new event loop.
      2. Run the main coroutine to completion (or exception).
      3. **Drain `_DETACHED_BACKEND_TASKS` by force-closing each.** This
         must happen BEFORE `_cancel_all_tasks` so the task is already
         finalized (cancelled) when the standard shutdown iterates it.
      4. Mirror `asyncio.run`'s standard shutdown: cancel all remaining
         tasks, run them until complete, run async generator shutdown,
         shutdown default executor, close the loop.

    Replaces `asyncio.run(...)` at pipeline-A entry (`run_one_query`)
    when the run includes any Playwright-bound fetch backend.
    """
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        main_task = loop.create_task(coro)
        try:
            return loop.run_until_complete(main_task)
        finally:
            # I-cd-032: force-close wedged detached tasks BEFORE the
            # standard cancel-all-tasks step so it has nothing
            # un-cancellable to await.
            for task in list(_DETACHED_BACKEND_TASKS):
                _force_drop_detached_task(task)
            # Mirror asyncio.run's shutdown phases.
            try:
                _polaris_cancel_all_tasks(loop)
                loop.run_until_complete(loop.shutdown_asyncgens())
                if hasattr(loop, "shutdown_default_executor"):
                    loop.run_until_complete(loop.shutdown_default_executor())
            finally:
                asyncio.set_event_loop(None)
                loop.close()
    except BaseException:
        # Ensure the loop is closed on any exception path.
        if not loop.is_closed():
            loop.close()
        raise


def _polaris_cancel_all_tasks(loop: "asyncio.AbstractEventLoop") -> None:
    """Mirror of stdlib asyncio.runners._cancel_all_tasks but with a
    GENUINE hard wall-clock. Codex iter-2 P0 fix: stdlib
    `asyncio.wait_for(asyncio.gather(...), timeout=2)` does NOT bound
    because gather's child-task cancellation cleanup continues past
    the wait_for's own cancellation. Use `asyncio.wait(..., timeout)`
    instead — it returns `(done, pending)` sets unconditionally at
    the timeout AND does not propagate cancellation to children.

    After the 2s wall, every task still in `pending` is force-closed
    via `_force_drop_detached_task` so the subsequent loop.close()
    has nothing pending to await.
    """
    to_cancel = [t for t in asyncio.all_tasks(loop) if not t.done()]
    if not to_cancel:
        return
    for task in to_cancel:
        task.cancel()

    async def _wait_with_hard_wall():
        # asyncio.wait returns (done, pending) at timeout — does NOT
        # await child-task cleanup beyond the wall. Defense-in-depth
        # against untracked wedged tasks.
        done, pending = await asyncio.wait(to_cancel, timeout=2.0)
        return done, pending

    try:
        _done, pending = loop.run_until_complete(_wait_with_hard_wall())
    except BaseException:
        # Best-effort — if even our wait helper raises, just force-
        # drop every pending task.
        pending = [t for t in to_cancel if not t.done()]

    for task in pending:
        if not task.done():
            _force_drop_detached_task(task)


def _backend_failure(label: str, url: str, error: str) -> AccessResult:
    """A failure AccessResult for a backend that timed out or errored."""
    return AccessResult(
        url=url,
        content="",
        access_method=label,
        legal_alternative=None,
        success=False,
        metadata={"error": error},
    )


async def _bounded_backend(label: str, coro: Any, url: str) -> AccessResult:
    """Run one fetch-backend coroutine under a hard wall-clock bound.

    Returns within PG_BACKEND_FETCH_TIMEOUT + PG_BACKEND_CLEANUP_GRACE
    regardless of whether `coro` ever finishes — `asyncio.wait` returns after
    its timeout unconditionally (unlike `asyncio.wait_for`, which awaits the
    cancelled coroutine's cleanup). A backend whose cancellation cleanup itself
    exceeds the grace window is detached (post-artifacts teardown — see #552).
    """
    timeout = _backend_fetch_timeout()
    grace = _backend_cleanup_grace()
    task = asyncio.ensure_future(coro)
    done, _pending = await asyncio.wait({task}, timeout=timeout)
    if task in done:
        exc = task.exception()
        if exc is not None:
            return _backend_failure(label, url, f"{type(exc).__name__}: {exc}")
        return task.result()
    # Timed out — cancel, then allow a BOUNDED grace window for cleanup.
    task.cancel()
    done, _pending = await asyncio.wait({task}, timeout=grace)
    if task in done:
        if not task.cancelled():
            try:
                task.exception()  # retrieve, discard
            except Exception:  # noqa: BLE001
                pass
        logger.warning(
            "[ACCESS] backend %s exceeded %.0fs wall-clock for %s — cancelled",
            label, timeout, _safe_log_str(url, 60),
        )
    else:
        # Cleanup itself exceeded the grace window: detach (ref-kept,
        # exception-drained). Residual asyncio.run-teardown case: #552.
        _DETACHED_BACKEND_TASKS.add(task)
        task.add_done_callback(_drain_detached)
        logger.warning(
            "[ACCESS] backend %s exceeded %.0fs + %.0fs grace for %s — "
            "detached (see #552)", label, timeout, grace, _safe_log_str(url, 60),
        )
    return _backend_failure(label, url, f"backend_timeout_{timeout:.0f}s")


class AccessBypass:
    """
    Research access manager.

    Provides multiple methods to access research content.
    """

    def __init__(
        self,
        respect_robots_txt: bool = False,  # For research indexing
        use_archive_org: bool = True,
        institutional_proxy: Optional[str] = None,
        user_agent: str = "POLARIS Research Bot (academic research)",
    ):
        self.respect_robots = respect_robots_txt
        self.use_archive_org = use_archive_org
        self.proxy = institutional_proxy
        self.user_agent = user_agent

        # Paywall detection patterns.
        # M-23f: Tightened to fix false positives on long article bodies.
        # The old patterns used greedy `.*` across arbitrary spans, which
        # meant a 50K-char NEJM article saying "the authors had full
        # access to the data" (far from any "sign in") would match
        # `sign.*in.*to.*access` because regex `.*` spans ~49K chars.
        # New patterns use `\s+` / `\s*[.:]?\s*` for tight token adjacency
        # and word boundaries. Length-gating in `_detect_paywall`
        # further protects long article bodies from the loosest patterns.
        self.paywall_patterns_strict = [
            # These fire on ANY content length — extremely specific
            r"\bpaywall\b",
            r"\bpremium\s+content\b",
            r"\bunlock\s+(the\s+)?full\s+article\b",
            r"\bthis\s+article\s+is\s+available\s+to\s+subscribers\b",
            r"\blog\s+in\s+to\s+read\s+this\s+article\b",
            r"\bsubscribe\s+to\s+read\s+the\s+full\s+article\b",
        ]
        self.paywall_patterns_short_only = [
            # These fire ONLY when content is short (<2K chars) — the
            # bare phrase "members only" or "sign in to access" in a
            # 50K article body is almost always incidental.
            r"\bsubscribe\s+to\s+read\b",
            r"\bsign\s+in\s+to\s+access\b",
            r"\bpurchase\s+(this\s+)?article\b",
            r"\bmembers\s+only\b",
        ]
        # Back-compat: tests or callers referencing .paywall_patterns get
        # the strict-always list (the safer set).
        self.paywall_patterns = self.paywall_patterns_strict

    async def fetch_with_bypass(
        self,
        url: str,
        prefer_legal: bool = True,
    ) -> AccessResult:
        """
        Fetch content with bypass mechanisms.

        FIX-QM2: Crawl4AI, Jina and Firecrawl run concurrently -- first
        success wins.  Crawl4AI is checked first (free, local, no API credits).

        Fallback cascade (if concurrent fetch fails):
        1. Direct HTTP with Accept: text/markdown
        2. Unpaywall (legal open access)
        3. Archive.org (historical)
        4. Institutional proxy
        5. Sci-Hub (last resort for academic papers)
        """
        # D (I-extract-001 #1327): per-fetch block-page/stub state. `seen` flips
        # True on the first block-page detection across any backend so a later
        # clean fetch on this URL is counted as a successful re-fetch (canary
        # `re_fetched`). Default-OFF detector → this stays {"seen": False} and
        # every screen below is a no-op.
        _block_state: Dict[str, bool] = {"seen": False}

        # PL: Skip S2 landing pages — they're metadata, not content.
        # S2 bulk search returns paper IDs that are 404 via individual API.
        # S2's value is the search metadata (title, abstract, DOI), not the landing page.
        if "semanticscholar.org/paper/" in url:
            logger.debug("[ACCESS] PL: Skipping S2 landing page: %s", url[:60])
            return AccessResult(
                url=url, content="", access_method="skipped_s2_landing",
                legal_alternative=None, success=False,
                metadata={"reason": "S2 landing pages have no content"},
            )

        # PL: Resolve ScienceDirect PIIs and extract DOIs for Sci-Hub fallback.
        resolved_url, resolved_doi = await self._resolve_academic_url(url)
        if resolved_url and resolved_url != url:
            logger.info("[ACCESS] PL: Resolved %s -> %s", url[:50], resolved_url[:50])
            url = resolved_url

        # I-bug-775 (#815): PMC BioC full-text FIRST. PMC HTML/PDF scraping is
        # flaky (jina 60s timeouts, 111-char crawl4ai stubs); the BioC OA API
        # gives structured full text reliably for the OA Subset. Try it before
        # Unpaywall/PDF/scrapers when the URL already carries a PMCID. Falls
        # through (returns None) on non-OA / error / abstract-only.
        _pmcid = self._extract_pmcid(url)
        if _pmcid:
            _bioc_text = await self._try_pmc_bioc_fulltext(_pmcid)
            if _bioc_text:
                return AccessResult(
                    url=url, content=_bioc_text[:50000], access_method="pmc_bioc",
                    legal_alternative=None, success=True,
                    metadata={"pmcid": _pmcid, "source": "pmc_bioc_oa"},
                )

        # M-23a: Unpaywall step 0 — try legal OA before anything else.
        # For DOI-bearing URLs (NEJM, Lancet, JAMA, Elsevier, Springer...)
        # Unpaywall frequently returns a PMC or arXiv OA PDF that is the
        # same article, legally free, full-text. This fixes the "NEJM/Lancet
        # return 400-char paywall stubs" problem upstream of any paywall
        # bypass logic.
        if os.getenv("PG_UNPAYWALL_ENABLED", "1") == "1":
            candidate_doi = self._extract_doi(url) or resolved_doi
            if candidate_doi:
                oa_url = await self._try_unpaywall(candidate_doi)
                if oa_url and oa_url != url:
                    logger.info(
                        "[ACCESS] M-23a: Swapping %s -> OA %s",
                        url[:60], oa_url[:80],
                    )
                    url = oa_url
                    # I-bug-775 (#815): Unpaywall frequently resolves to a PMC
                    # OA copy (e.g. .../PMCxxxxxxx/pdf/main.pdf). Prefer the BioC
                    # full-text API over scraping that PDF (mode-2: PMC PDF
                    # fetches sometimes returned 54-char stubs).
                    _oa_pmcid = self._extract_pmcid(url)
                    if _oa_pmcid:
                        _oa_bioc = await self._try_pmc_bioc_fulltext(_oa_pmcid)
                        if _oa_bioc:
                            return AccessResult(
                                url=url, content=_oa_bioc[:50000],
                                access_method="pmc_bioc",
                                legal_alternative=None, success=True,
                                metadata={"pmcid": _oa_pmcid,
                                          "source": "pmc_bioc_oa_via_unpaywall"},
                            )

        # FIX-CITE-3/GAP4: Detect PDF URLs and extract text directly.
        # Academic open-access PDFs (from S2 openAccessPdf) need PDF parsing,
        # not HTML scraping. This gives the analyzer full paper content with
        # forest plots, I² values, GRADE ratings — the detail Gemini captures.
        if url.lower().endswith(".pdf") or "/pdf/" in url.lower():
            try:
                pdf_text = await self._extract_pdf_text(url)
                if pdf_text and len(pdf_text) > 500:
                    # ev_461: strip a leading journal-masthead block (running-head /
                    # author-affiliation list / submission-date line) from the
                    # PDF-extracted text BEFORE it is capped + windowed into a span.
                    # PDF-origin by construction (this is the .pdf / /pdf/ branch);
                    # flag-gated, conservative (body sentence onward is byte-identical).
                    pdf_text = strip_pdf_frontmatter(pdf_text)
                    logger.info(
                        "[ACCESS] FIX-GAP4: PDF text extracted for %s (%d chars)",
                        url[:60], len(pdf_text),
                    )
                    return AccessResult(
                        url=url,
                        content=pdf_text[:50000],  # Cap at 50K chars
                        # FIX-GAP4-KWARG: was `method=`, dataclass field is
                        # `access_method`. The old kwarg triggered TypeError
                        # every successful docling/PyMuPDF extraction, which
                        # was then caught as "PDF extraction failed" and
                        # replaced with a 153-char snippet. Every successful
                        # 10K-50K char PDF extract was being silently discarded.
                        access_method="pdf_extract",
                        legal_alternative=None,
                        success=True,
                        metadata={"content_type": "application/pdf"},
                    )
            except Exception as pdf_exc:
                logger.warning(
                    "[ACCESS] FIX-GAP4: PDF extraction failed for %s: %s — falling back to HTML",
                    url[:60], str(pdf_exc)[:100],
                )

        # F14 (GH #1245 / D9, D10): route paywalled publishers to Zyte FIRST.
        # The free scraper group (Crawl4AI/Jina/Firecrawl) reliably returns a
        # few-hundred-char ABSTRACT SHELL for these hosts, which then gets logged
        # as an "ok" source — a dead fetch masquerading as good content. For a
        # known paywalled-publisher host, try Zyte (the paid browser fetch) FIRST
        # so a REAL body is fetched instead of a shell. This runs AFTER the free
        # LEGAL OA chain (PMC-BioC / Unpaywall / direct PDF) above — a legally
        # free full-text copy always wins over a paid call. Gated by
        # PG_ZYTE_PAYWALL_FIRST (default OFF => byte-identical: the early Zyte
        # attempt never fires). When ON but ZYTE_API_KEY is UNSET, a LOUD warning
        # fires (the Zyte path is otherwise a silent no-op without the key) so a
        # Zyte-blind run on paywalled journals is auditable. Zyte content still
        # flows through the SAME extractor + strict_verify / 4-role gates — no
        # faithfulness gate is bypassed (§-1.3: the only hard gate is untouched).
        if (
            os.getenv("PG_ZYTE_PAYWALL_FIRST", "0") == "1"
            and _is_paywall_publisher_host(url)
        ):
            if os.getenv("ZYTE_API_KEY"):
                logger.info(
                    "[ACCESS] F14: paywalled publisher %s — trying Zyte FIRST "
                    "(before the free scraper group)", url[:60],
                )
                _zyte_first = await self._try_zyte(url)
                if _zyte_first.success:
                    return _zyte_first
            else:
                logger.warning(
                    "[ACCESS] F14: paywalled publisher %s but ZYTE_API_KEY is "
                    "UNSET — Zyte-first routing is a silent no-op; the free "
                    "scraper group will likely return only an abstract shell. "
                    "Set ZYTE_API_KEY to recover full text.", url[:80],
                )

        # FIX-QM2: Run the enabled fetch backends concurrently -- first success wins.
        # Build concurrent task list: Crawl4AI first (free/local), then Jina, then Firecrawl
        concurrent_tasks: list = []
        # GH #1260 (cosmetic): track the backends ACTUALLY queued so the log line
        # names only those (the old unconditional "Crawl4AI+Jina+Firecrawl" lied
        # when PG_CRAWL4AI_ENABLED=0 / Firecrawl had no key/credits).
        _queued_backends: list[str] = []

        # I-bug-114 (#551): every concurrent backend is wrapped in
        # `_bounded_backend` so a single wedged backend (e.g. a Playwright op
        # stuck on an anti-bot interstitial) cannot freeze the gather. Each
        # wrapper returns an AccessResult within the per-backend wall-clock.
        crawl4ai_enabled = os.getenv("PG_CRAWL4AI_ENABLED", "1") == "1"
        if crawl4ai_enabled:
            concurrent_tasks.append(
                _bounded_backend("crawl4ai", self._try_crawl4ai(url), url))
            _queued_backends.append("Crawl4AI")

        concurrent_tasks.append(
            _bounded_backend("jina_reader", self._try_jina_reader(url), url))
        _queued_backends.append("Jina")

        firecrawl_enabled = os.getenv("PG_FIRECRAWL_ENABLED", "1") == "1"
        firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY")
        if firecrawl_enabled and firecrawl_api_key and _firecrawl_has_credits():
            concurrent_tasks.append(
                _bounded_backend("firecrawl", self._try_firecrawl(url), url))
            _queued_backends.append("Firecrawl")

        # FIX-039/B.3: Add trafilatura to concurrent group (was dead-code fallback)
        if os.getenv("PG_TRAFILATURA_ENABLED", "0") == "1":
            concurrent_tasks.append(
                _bounded_backend("trafilatura", self._try_trafilatura(url), url))
            _queued_backends.append("Trafilatura")

        # GH #1260 (cosmetic): log AFTER the backend list is built so it names
        # only the backends actually queued, not a hardcoded triple.
        logger.info(
            "[ACCESS] FIX-QM2: Concurrent %s for %s",
            "+".join(_queued_backends) or "(none)", url[:60],
        )

        # FIX-EPIPE: Wrap gather in try/except to catch CancelledError and
        # any BaseException that escapes from subprocess crashes in crawl4ai.
        # asyncio.gather(return_exceptions=True) captures Exception subclasses
        # as return values, but CancelledError (BaseException in Python 3.9+)
        # can still propagate if the gather task itself is cancelled.
        try:
            concurrent_results = await asyncio.gather(
                *concurrent_tasks, return_exceptions=True
            )
        except asyncio.CancelledError:
            logger.warning(
                "[ACCESS] FIX-EPIPE: Concurrent fetch cancelled for %s "
                "(likely subprocess crash or task cancellation)",
                url[:60],
            )
            concurrent_results = []
        except BaseException as gather_err:
            # Safety net for anything that escapes gather
            if isinstance(gather_err, (KeyboardInterrupt, SystemExit)):
                raise
            logger.warning(
                "[ACCESS] FIX-EPIPE: Unexpected %s from concurrent fetch "
                "for %s: %s -- server protected",
                type(gather_err).__name__, url[:60], str(gather_err)[:150],
            )
            concurrent_results = []

        # M-23b/c: Replace first-success-wins with quality-scored winner.
        # OLD BUG: Jina 422-char paywall stub won the race over Crawl4AI's
        # 45K-char NEJM SURPASS-5 fetch, because Jina's task finished first.
        # NEW: Collect ALL successful candidates, strip boilerplate FIRST
        # (so nav chrome containing "sign in" doesn't trigger paywall
        # false-positives on full article bodies), filter by paywall check,
        # then pick the highest-scoring candidate by content quality
        # (length + structural markers + numeric density).
        candidates: list[AccessResult] = []
        rejected_log: list[tuple[str, str, int]] = []
        for r in concurrent_results:
            if not isinstance(r, AccessResult):
                continue
            if not r.success:
                continue
            # D (I-extract-001 #1327): block-page/stub screen on the RAW backend
            # body BEFORE strip — a 200 challenge/stub candidate is dropped (and
            # re-routed) rather than boilerplate-stripped and quality-scored.
            # Dropping every candidate here falls through to the direct/archive/
            # proxy chain below (NOT an empty-success return). Flag-gated no-op.
            if self._is_block_page(url, r.content, _block_state):
                rejected_log.append((r.access_method, "block_page", len(r.content)))
                continue
            # M-23b: strip boilerplate BEFORE paywall check
            r.content = _strip_navigation_boilerplate(r.content)
            if self._detect_paywall(r.content):
                rejected_log.append((r.access_method, "paywall", len(r.content)))
                continue
            candidates.append(r)

        if candidates:
            # M-23c: quality-scored winner
            scored = [(c, _score_content_quality(c.content)) for c in candidates]
            scored.sort(key=lambda x: x[1], reverse=True)
            winner, winner_score = scored[0]
            winner.metadata = {
                **(winner.metadata or {}),
                "quality_score": round(winner_score, 3),
                "n_candidates": len(candidates),
                "all_scores": {
                    c.access_method: round(s, 3) for c, s in scored
                },
            }
            logger.info(
                "[ACCESS] M-23c: %s won quality-scored fetch for %s "
                "(%d chars, score=%.3f, %d candidates, scores=%s)",
                winner.access_method, url[:60], len(winner.content),
                winner_score, len(candidates),
                {c.access_method: round(s, 3) for c, s in scored},
            )
            if rejected_log:
                logger.debug(
                    "[ACCESS] M-23b: rejected %d stub/paywall/block candidates: %s",
                    len(rejected_log), rejected_log,
                )
            return self._finalize_clean_fetch(winner, _block_state)

        # FIX-039/B.3: Trafilatura now runs in concurrent group above (no standalone fallback)

        # Direct HTTP fetch with markdown Accept header (FIX-D6/A3)
        logger.info("[ACCESS] Trying direct fetch for %s", url[:60])
        timeout_occurred = False
        direct_result = await self._direct_fetch(url)

        if direct_result.success:
            # D (I-extract-001 #1327): screen the RAW body (best signal for
            # CF/edgesuite/recaptcha markers) BEFORE strip; a 200 block/stub
            # re-routes to the alternatives below instead of becoming evidence.
            if not self._is_block_page(url, direct_result.content, _block_state):
                # M-23b: strip BEFORE paywall detection
                direct_result.content = _strip_navigation_boilerplate(direct_result.content)
                if not self._detect_paywall(direct_result.content):
                    return self._finalize_clean_fetch(direct_result, _block_state)

        # Track if direct fetch failed due to timeout for retry logic (FIX-D5)
        if not direct_result.success and "timeout" in str(direct_result.metadata.get("error", "")).lower():
            timeout_occurred = True

        logger.info("[ACCESS] Direct access blocked for %s, trying alternatives", url[:80])

        # Try Archive.org
        if self.use_archive_org:
            logger.info("[ACCESS] Trying Archive.org for %s", url[:60])
            archive_result = await self._try_archive_org(url)
            if archive_result.success and not self._is_block_page(
                url, archive_result.content, _block_state
            ):
                # FIX-045B: Strip navigation boilerplate
                archive_result.content = _strip_navigation_boilerplate(archive_result.content)
                return self._finalize_clean_fetch(archive_result, _block_state)

        # Try institutional proxy
        if self.proxy:
            logger.info("[ACCESS] Trying proxy for %s", url[:60])
            proxy_result = await self._try_proxy(url)
            if proxy_result.success and not self._is_block_page(
                url, proxy_result.content, _block_state
            ):
                # FIX-045B: Strip navigation boilerplate
                proxy_result.content = _strip_navigation_boilerplate(proxy_result.content)
                return self._finalize_clean_fetch(proxy_result, _block_state)

        # FIX-D5: Retry once on timeout errors before giving up
        if timeout_occurred:
            logger.info("[ACCESS] Retrying direct fetch after timeout for %s", url[:60])
            await asyncio.sleep(3)
            retry_result = await self._direct_fetch(url)
            if retry_result.success and not self._is_block_page(
                url, retry_result.content, _block_state
            ):
                # M-23b: strip BEFORE paywall detection
                retry_result.content = _strip_navigation_boilerplate(retry_result.content)
                if not self._detect_paywall(retry_result.content):
                    return self._finalize_clean_fetch(retry_result, _block_state)

        # Sci-Hub is DISABLED BY DEFAULT (I-faith-002): the legal OA full-text
        # path is now CORE (src/tools/core_client.py) wired at
        # frame_fetcher.py Step 2b. PG_SCIHUB_ENABLED defaults to "0" so NO
        # outbound request is ever issued to any sci-hub.* host unless an
        # operator explicitly opts in by setting PG_SCIHUB_ENABLED=1. When
        # the flag is not "1" this block is skipped entirely — _try_scihub
        # (the sole sci-hub.* URL builder) is never called.
        # Use resolved DOI if available (more reliable than URL-based DOI extraction)
        if os.getenv("PG_SCIHUB_ENABLED", "0") == "1":
            scihub_url = url
            if resolved_doi:
                scihub_url = f"https://doi.org/{resolved_doi}"
            scihub_result = await self._try_scihub(scihub_url)
            if scihub_result.success and not self._is_block_page(
                url, scihub_result.content, _block_state
            ):
                logger.info("[ACCESS] Sci-Hub succeeded for %s (%d chars)", url[:60], len(scihub_result.content))
                scihub_result.content = _strip_navigation_boilerplate(scihub_result.content)
                return self._finalize_clean_fetch(scihub_result, _block_state)

        # I-fetch-004 (#1185): PAID Zyte fallback — the genuine LAST resort,
        # ONLY after the entire FREE chain (PDF/Unpaywall/PMC-BioC -> concurrent
        # quality-scored group -> direct -> Archive.org -> proxy -> timeout-retry
        # -> Sci-Hub) has failed. STRICT NO-OP: when ZYTE_API_KEY is absent the
        # helper is never even invoked, so behaviour here is byte-identical to
        # before (zero spend, zero risk on un-keyed runs). Zyte only RETRIEVES
        # raw content; the returned text still flows through the SAME extractor
        # and the downstream strict_verify / 4-role faithfulness gates — no gate
        # is bypassed. _try_zyte strips boilerplate internally and only returns
        # success on non-paywalled content above the min-length floor, so there
        # is no extra strip needed at this call site.
        if os.getenv("ZYTE_API_KEY"):
            logger.info(
                "[ACCESS] I-fetch-004: Trying Zyte paid fallback for %s", url[:60]
            )
            zyte_result = await self._try_zyte(url)
            if zyte_result.success and not self._is_block_page(
                url, zyte_result.content, _block_state
            ):
                return self._finalize_clean_fetch(zyte_result, _block_state)

        # SF-40: Log total failure at WARNING (was completely silent)
        logger.warning("[ACCESS] ALL access methods exhausted for %s", url[:80])
        # F14 (GH #1245 / D9, D10): when a PAYWALLED-publisher URL exhausts every
        # method and ZYTE_API_KEY is UNSET, surface a LOUD diagnostic — this is
        # exactly the case where the Zyte paid fallback (the one method that
        # could recover the body) was a silent no-op. Makes a Zyte-blind run on
        # paywalled journals auditable instead of a quiet exhaustion.
        if _is_paywall_publisher_host(url) and not os.getenv("ZYTE_API_KEY"):
            logger.warning(
                "[ACCESS] F14: paywalled publisher %s exhausted ALL free "
                "methods and ZYTE_API_KEY is UNSET — the Zyte paid fallback "
                "was never invoked (silent no-op). Set ZYTE_API_KEY to recover "
                "full text for paywalled journals.", url[:80],
            )
        return AccessResult(
            url=url,
            content="",
            access_method="failed",
            legal_alternative=None,
            success=False,
            metadata={"error": "All access methods failed"}
        )

    async def _try_crawl4ai(self, url: str) -> AccessResult:
        """
        Crawl4AI: Free, local, Playwright-based web crawler that generates
        LLM-ready markdown.  No API key or credits required.

        FIX-EPIPE: Hardened against Node.js subprocess EPIPE/broken pipe
        errors that can kill the Python server process. The Playwright
        browser subprocess can crash (EPIPE on websocket close), and the
        error propagates through AsyncWebCrawler.__aenter__/__aexit__.

        Defense layers:
        1. Circuit breaker -- skip crawl4ai after repeated subprocess crashes
        2. Import error catch -- handles corrupted crawl4ai installations
        3. Explicit __aenter__/__aexit__ -- no `async with` so __aexit__
           failures are caught independently via _safe_close_crawler()
        4. Specific catches for BrokenPipeError, ConnectionError, OSError
        5. asyncio.CancelledError catch (BaseException in Python 3.9+)
        6. BaseException safety net (re-raises KeyboardInterrupt/SystemExit)

        Controlled by env vars:
          - PG_CRAWL4AI_ENABLED (default "1")
          - PG_CRAWL4AI_TIMEOUT (default 30, in seconds)
          - PG_CRAWL4AI_CIRCUIT_BREAKER_THRESHOLD (default "3")
          - PG_CRAWL4AI_CIRCUIT_BREAKER_COOLDOWN (default "120.0")

        Returns AccessResult. NEVER raises -- all exceptions are caught
        and converted to failure results.
        """
        global _crawl4ai_available
        global _crawl4ai_consecutive_failures, _crawl4ai_circuit_open_until

        # FIX-EPIPE: Circuit breaker -- skip after repeated subprocess crashes
        now = _time_module.time()
        if _crawl4ai_circuit_open_until > now:
            remaining = _crawl4ai_circuit_open_until - now
            logger.debug(
                "[polaris graph] CRAWL4AI: FIX-EPIPE circuit breaker OPEN "
                "(%.0fs remaining) -- skipping %s",
                remaining, _safe_log_str(url, 60),
            )
            return _crawl4ai_failure_result(
                url, f"circuit_breaker_open ({remaining:.0f}s remaining)"
            )

        # Fast-path: already know crawl4ai is not installed
        if _crawl4ai_available is False:
            return _crawl4ai_failure_result(url, "crawl4ai not installed")

        # Lazy import with availability caching.
        # FIX-EPIPE: Catch all exceptions during import, not just ImportError.
        # crawl4ai's __init__.py may spawn subprocesses or load native libs
        # that can fail with OSError/RuntimeError on corrupted installations.
        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
            try:
                from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
                from crawl4ai.content_filter_strategy import PruningContentFilter
                _crawl4ai_filter_available = True
            except ImportError:
                _crawl4ai_filter_available = False
            _crawl4ai_available = True
        except ImportError:
            _crawl4ai_available = False
            logger.warning(
                "[polaris graph] CRAWL4AI: crawl4ai package not installed. "
                "Install with: pip install crawl4ai"
            )
            return _crawl4ai_failure_result(url, "crawl4ai not installed")
        except Exception as import_err:
            _crawl4ai_available = False
            logger.warning(
                "[polaris graph] CRAWL4AI: FIX-EPIPE import failed with "
                "%s: %s -- disabling crawl4ai for this session",
                type(import_err).__name__,
                _safe_log_str(str(import_err)),
            )
            return _crawl4ai_failure_result(
                url,
                f"import failed: {type(import_err).__name__}: {str(import_err)}",
            )

        timeout_seconds = int(os.getenv("PG_CRAWL4AI_TIMEOUT", "30"))
        page_timeout_ms = timeout_seconds * 1000

        # FIX-UNICODE: Crawl4AI/Playwright write Unicode to stdout/stderr.
        # Windows console uses cp1252 which cannot encode many chars.
        try:
            if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception as enc_err:
            logger.debug("Windows encoding reconfiguration skipped: %s", enc_err)

        # ---------------------------------------------------------------
        # FIX-EPIPE: Main crawl execution with decomposed context manager.
        #
        # Instead of `async with AsyncWebCrawler(...) as crawler:` which
        # makes __aexit__ failures escape into the caller, we manually
        # call __aenter__ and __aexit__ with independent error handling.
        # This ensures that a BrokenPipeError during browser cleanup
        # (the primary crash vector) cannot kill the server.
        # ---------------------------------------------------------------
        crawler = None
        try:
            browser_config = BrowserConfig(
                headless=True,
                verbose=False,
            )
            # PL: Use PruningContentFilter to strip nav/ads/footers/cookie banners.
            # Without this, result.markdown contains full page including junk.
            # With fit_markdown, we get clean article body with proper tables.
            if _crawl4ai_filter_available:
                crawler_config = CrawlerRunConfig(
                    page_timeout=page_timeout_ms,
                    wait_until="domcontentloaded",
                    markdown_generator=DefaultMarkdownGenerator(
                        content_filter=PruningContentFilter(threshold=0.48),
                        options={"ignore_links": False, "body_width": 0},
                    ),
                )
            else:
                crawler_config = CrawlerRunConfig(
                    page_timeout=page_timeout_ms,
                    wait_until="domcontentloaded",
                )

            logger.info(
                "[polaris graph] CRAWL4AI: Fetching %s (timeout=%ds)",
                _safe_log_str(url, 80),
                timeout_seconds,
            )

            # I-fetch-002 (#1168): hold a crawl4ai concurrency slot ONLY for the browser-active region
            # (startup -> crawl -> close). The extraction (Step 4, trafilatura — CPU-bound) and the
            # cheap config build above run OUTSIDE the slot so a browser slot is never pinned by
            # non-browser work. `result` is assigned inside and read after the `async with` (it persists
            # in the enclosing scope). The inner early-returns release the slot cleanly on `async with`
            # exit. At most PG_CRAWL4AI_CONCURRENCY browsers are live at once.
            async with _get_crawl4ai_semaphore():
                # Step 1: Start the browser subprocess.
                # FIX-EPIPE: Separate try for __aenter__ to catch startup failures.
                try:
                    crawler = AsyncWebCrawler(config=browser_config)
                    await crawler.__aenter__()
                except (BrokenPipeError, ConnectionError, OSError) as enter_err:
                    logger.warning(
                        "[polaris graph] CRAWL4AI: FIX-EPIPE browser startup "
                        "pipe/OS error for %s: %s: %s",
                        _safe_log_str(url, 60),
                        type(enter_err).__name__,
                        _safe_log_str(str(enter_err)),
                    )
                    _crawl4ai_track_failure()
                    return _crawl4ai_failure_result(
                        url,
                        f"Browser startup failed: {type(enter_err).__name__}: "
                        f"{str(enter_err)}",
                    )
                except Exception as enter_err:
                    logger.warning(
                        "[polaris graph] CRAWL4AI: FIX-EPIPE browser init "
                        "exception for %s: %s: %s",
                        _safe_log_str(url, 60),
                        type(enter_err).__name__,
                        _safe_log_str(str(enter_err)),
                    )
                    _crawl4ai_track_failure()
                    return _crawl4ai_failure_result(
                        url,
                        f"Browser init failed: {type(enter_err).__name__}: "
                        f"{str(enter_err)}",
                    )

                # Step 2: Run the crawl with timeout guard.
                try:
                    result = await asyncio.wait_for(
                        crawler.arun(url=url, config=crawler_config),
                        timeout=timeout_seconds + 10,
                    )
                finally:
                    # Step 3: Close browser via _safe_close_crawler which catches
                    # ALL exceptions from __aexit__ independently.
                    await _safe_close_crawler(crawler, url)
                    crawler = None  # Prevent double-close in outer finally

            # Step 4: Process the crawl result.
            # If we reached here, the subprocess survived (reset breaker).
            _crawl4ai_consecutive_failures = 0

            if not result.success:
                error_msg = result.error_message or "Crawl returned success=False"
                logger.warning(
                    "[polaris graph] CRAWL4AI: Failed for %s: %s",
                    _safe_log_str(url, 60),
                    _safe_log_str(str(error_msg)),
                )
                return AccessResult(
                    url=url,
                    content="",
                    access_method="crawl4ai",
                    legal_alternative=None,
                    success=False,
                    metadata={
                        "error": str(error_msg)[:200],
                        "status_code": result.status_code,
                    },
                )

            # PL: Crawl4AI renders JS → Trafilatura extracts article body.
            # Trafilatura (F1=0.958) strips nav/ads/gov banners/footers that
            # PruningContentFilter misses. Falls back to fit_markdown/raw.
            markdown_content = ""
            if result.html:
                # BB5-S03 (#1177): route through the SIGSEGV-mitigated shared
                # extractor (size-bounds the HTML, optional subprocess
                # containment) instead of a bare `trafilatura.extract` under
                # `except Exception` — a libxml2 C-crash on Crawl4AI's raw HTML
                # is not a catchable Python exception.
                clean = safe_trafilatura_extract(
                    result.html,
                    include_tables=True,
                    include_links=False,
                    output_format="txt",
                )
                if clean and len(clean) > 500:
                    markdown_content = clean
                    logger.info(
                        "[ACCESS] PL: Trafilatura cleaned Crawl4AI HTML: %d chars",
                        len(clean),
                    )

            # Fallback: fit_markdown or raw markdown from Crawl4AI
            if not markdown_content:
                if hasattr(result, "markdown") and result.markdown:
                    md_obj = result.markdown
                    if hasattr(md_obj, "fit_markdown") and md_obj.fit_markdown:
                        markdown_content = md_obj.fit_markdown
                    elif isinstance(md_obj, str):
                        markdown_content = md_obj
                    else:
                        markdown_content = str(md_obj)

            if not markdown_content or len(markdown_content.strip()) <= 100:
                logger.warning(
                    "[polaris graph] CRAWL4AI: Insufficient content for %s (%d chars)",
                    _safe_log_str(url, 60),
                    len(markdown_content),
                )
                return AccessResult(
                    url=url,
                    content="",
                    access_method="crawl4ai",
                    legal_alternative=None,
                    success=False,
                    metadata={
                        "error": "Insufficient content",
                        "content_length": len(markdown_content),
                        "status_code": result.status_code,
                    },
                )

            logger.info(
                "[polaris graph] CRAWL4AI: Succeeded for %s (%d chars, status %s)",
                _safe_log_str(url, 60),
                len(markdown_content),
                result.status_code,
            )
            return AccessResult(
                url=url,
                content=markdown_content,
                access_method="crawl4ai",
                legal_alternative=None,
                success=True,
                metadata={
                    "content_length": len(markdown_content),
                    "format": "markdown",
                    "status_code": result.status_code,
                    "redirected_url": result.redirected_url,
                },
            )

        except asyncio.TimeoutError:
            logger.warning(
                "[polaris graph] CRAWL4AI: Timeout after %ds for %s",
                timeout_seconds,
                _safe_log_str(url, 80),
            )
            return _crawl4ai_failure_result(
                url, f"Timeout after {timeout_seconds}s"
            )

        except asyncio.CancelledError:
            # FIX-EPIPE: CancelledError is BaseException in Python 3.9+.
            # NOT caught by `except Exception`. Happens when asyncio.wait_for
            # cancels the inner task, parent task is cancelled, or event loop
            # shuts down during a crawl.
            logger.warning(
                "[polaris graph] CRAWL4AI: FIX-EPIPE task cancelled for %s "
                "(CancelledError -- subprocess crash or shutdown)",
                _safe_log_str(url, 80),
            )
            _crawl4ai_track_failure()
            return _crawl4ai_failure_result(
                url, "Task cancelled (CancelledError)"
            )

        except (BrokenPipeError, ConnectionError) as pipe_err:
            # FIX-EPIPE: PRIMARY CRASH VECTOR. Playwright browser subprocess
            # dies, Node.js sends EPIPE on the websocket. Propagates as
            # BrokenPipeError or ConnectionError through asyncio transport.
            logger.warning(
                "[polaris graph] CRAWL4AI: FIX-EPIPE broken pipe for %s: "
                "%s: %s -- subprocess likely crashed, server protected",
                _safe_log_str(url, 60),
                type(pipe_err).__name__,
                _safe_log_str(str(pipe_err)),
            )
            _crawl4ai_track_failure()
            return _crawl4ai_failure_result(
                url,
                f"Subprocess pipe error: {type(pipe_err).__name__}: "
                f"{str(pipe_err)}",
            )

        except OSError as os_err:
            # FIX-EPIPE: Parent of BrokenPipeError/ConnectionError. Also
            # covers "Invalid argument" (errno 22), "Bad file descriptor"
            # (errno 9), and other OS-level subprocess handle failures.
            logger.warning(
                "[polaris graph] CRAWL4AI: FIX-EPIPE OS error for %s: "
                "%s (errno=%s) -- subprocess likely crashed",
                _safe_log_str(url, 60),
                _safe_log_str(str(os_err)),
                getattr(os_err, "errno", "unknown"),
            )
            _crawl4ai_track_failure()
            return _crawl4ai_failure_result(
                url, f"OS error (errno={getattr(os_err, 'errno', '?')}): {str(os_err)}"
            )

        except RuntimeError as rt_err:
            # FIX-EPIPE: Playwright/asyncio internal errors after subprocess
            # death ("Event loop is closed", "Cannot write to closing
            # transport", etc.).
            logger.warning(
                "[polaris graph] CRAWL4AI: FIX-EPIPE RuntimeError for %s: %s",
                _safe_log_str(url, 80),
                _safe_log_str(str(rt_err)),
            )
            return _crawl4ai_failure_result(
                url, f"RuntimeError: {str(rt_err)}"
            )

        except Exception as e:
            logger.warning(
                "[polaris graph] CRAWL4AI: Failed for %s: %s: %s",
                _safe_log_str(url, 80),
                type(e).__name__,
                _safe_log_str(str(e)),
            )
            return _crawl4ai_failure_result(
                url, f"{type(e).__name__}: {str(e)}"
            )

        except BaseException as be:
            # FIX-EPIPE: Ultimate safety net. Catches anything not a
            # subclass of Exception (GeneratorExit, exotic BaseException
            # subclasses from native extensions). Re-raise only
            # KeyboardInterrupt and SystemExit for clean shutdown.
            if isinstance(be, (KeyboardInterrupt, SystemExit)):
                raise
            logger.error(
                "[polaris graph] CRAWL4AI: FIX-EPIPE unexpected "
                "BaseException for %s (server protected): %s: %s",
                _safe_log_str(url, 80),
                type(be).__name__,
                _safe_log_str(str(be)),
            )
            _crawl4ai_track_failure()
            return _crawl4ai_failure_result(
                url, f"BaseException: {type(be).__name__}: {str(be)}"
            )

        finally:
            # FIX-EPIPE: Safety close in case crawler was not closed above
            # (e.g., exception during __aenter__ after partial init).
            if crawler is not None:
                await _safe_close_crawler(crawler, url)
            # FIX-UNICODE: Do NOT restore original encoding. Multiple
            # concurrent Crawl4AI calls race: one call's restore undoes
            # another call's reconfigure. utf-8 is strictly superior.

    async def _extract_pdf_text(self, url: str) -> str:
        """FIX-CITE-3/GAP4: Download and extract text from academic PDF.

        Uses PyMuPDF (fitz) for extraction. Falls back to basic text
        extraction if PyMuPDF is not available.
        """
        import aiohttp
        import tempfile

        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return ""
                pdf_bytes = await resp.read()
                if len(pdf_bytes) < 1000:
                    return ""

        # I-wire-001/W4 (#1313): clinical-PDF extractor SELECTOR.
        #
        # WINNER = mineru25 (MinerU 2.5 VLM, validated 0.9852 / TEDS #1 /
        # OmniDocBench-v1.6 SOTA; GPU). Docling (already on the path below) is
        # the disclosed CPU FALLBACK. This block is DEFAULT-OFF and fully gated
        # by PG_CLINICAL_PDF_EXTRACTOR: when the flag is unset or "docling" the
        # branch is skipped entirely and the path below runs byte-identically to
        # today (Docling-first -> PyMuPDF). Only PG_CLINICAL_PDF_EXTRACTOR=mineru25
        # activates the new GPU-VLM path. Faithfulness engine UNTOUCHED — this only
        # changes which extractor produces the verbatim text strict_verify grounds.
        _clinical_pdf_extractor = (
            os.getenv("PG_CLINICAL_PDF_EXTRACTOR", "docling").strip().lower()
        )
        if _clinical_pdf_extractor == "mineru25":
            _mineru_text = await self._maybe_mineru25_extract(url, pdf_bytes)
            if _mineru_text:
                return _mineru_text
            # _maybe_mineru25_extract returns "" when it did NOT win (no GPU,
            # mineru unavailable, or empty output). It already emitted a LOUD
            # WARN + recorded the disclosed Docling fallback in the tool trace.
            # Fall through to the unchanged Docling -> PyMuPDF path below.

        # FIX-DOCLING-OOM-V2: Guard against docling std::bad_alloc on large PDFs.
        # Docling's C++ preprocess stage has memory complexity proportional to
        # total_pages x image_resolution^2, doesn't release memory between
        # pages, and throws std::bad_alloc on 100+ page PDFs — killing the
        # Python process with SIGSEGV.
        #
        # V2 improvement: check BOTH byte size AND page count. A 3MB 200-page
        # dense-text PDF wouldn't trip a bytes-only guard but would still OOM
        # docling. PyMuPDF page count costs ~50ms and is memory-safe.
        #
        # Env overrides:
        #   PG_MAX_DOCLING_PDF_BYTES (default 5MB)
        #   PG_MAX_DOCLING_PDF_PAGES (default 40 pages)
        max_docling_bytes = int(
            os.getenv("PG_MAX_DOCLING_PDF_BYTES", str(5 * 1024 * 1024))
        )
        max_docling_pages = int(
            os.getenv("PG_MAX_DOCLING_PDF_PAGES", "40")
        )

        _skip_docling_reason = None
        if len(pdf_bytes) > max_docling_bytes:
            _skip_docling_reason = f"bytes={len(pdf_bytes)}>{max_docling_bytes}"
        else:
            # Cheap page count via PyMuPDF before committing to docling.
            try:
                import fitz as _fitz
                import tempfile as _tempfile
                with _tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as _tmp:
                    _tmp.write(pdf_bytes)
                    _tmp_path = _tmp.name
                _doc = _fitz.open(_tmp_path)
                _page_count = _doc.page_count
                _doc.close()
                import os as _os_pc
                _os_pc.unlink(_tmp_path)
                if _page_count > max_docling_pages:
                    _skip_docling_reason = f"pages={_page_count}>{max_docling_pages}"
            except Exception as _exc:
                # If PyMuPDF can't even open it, docling probably can't either.
                # Skip docling and let PyMuPDF fallback handle with its own error.
                logger.debug(
                    "[ACCESS] FIX-DOCLING-OOM-V2: page count failed (%s), skipping docling",
                    str(_exc)[:80],
                )
                _skip_docling_reason = "pymupdf_open_failed"

        if _skip_docling_reason:
            logger.warning(
                "[ACCESS] FIX-DOCLING-OOM-V2: Skipping docling (%s), using PyMuPDF: %s",
                _skip_docling_reason, url[:50],
            )
        else:
            # PL: Try Docling first (97.9% table accuracy), PyMuPDF fallback
            try:
                import asyncio as _aio
                loop = _aio.get_event_loop()
                # I-deepfix-001 W10-docling-extract-timeout (#1344): BOUND the docling
                # extraction with asyncio.wait_for (the mineru path is already wrapped; this
                # one was NOT). docling's C++ convert can wedge/run-minutes on a malformed/
                # encrypted/image-heavy PDF that passed the OOM-V2 page/byte gate, bounded only
                # by the 90s outer join. With mineru25 OFF this is the PRIMARY extraction path.
                # A wedged docling now fails-fast to the PyMuPDF fallback INSIDE the worker
                # window instead of abandoning the whole worker. Env-driven, < the 90s outer
                # join. Faithfulness-neutral: only changes WHICH extractor produces the text.
                _docling_to = float(os.getenv("PG_DOCLING_TIMEOUT_S", "60"))
                docling_text = await _aio.wait_for(
                    loop.run_in_executor(None, self._docling_extract, pdf_bytes),
                    timeout=max(1.0, _docling_to),
                )
                if docling_text and len(docling_text) > 500:
                    logger.info("[ACCESS] PL: Docling extracted %d chars from PDF %s", len(docling_text), url[:50])
                    return docling_text
            except _aio.TimeoutError:
                logger.warning(
                    "[ACCESS] W10: Docling extraction timed out (PG_DOCLING_TIMEOUT_S) "
                    "-> PyMuPDF fallback for %s", url[:50],
                )
            except Exception as exc:
                logger.debug("[ACCESS] PL: Docling failed, trying PyMuPDF: %s", str(exc)[:80])

        # Fallback: PyMuPDF (text-only, no table structure)
        try:
            import fitz
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name

            doc = fitz.open(tmp_path)
            pages_text = []
            for page in doc:
                pages_text.append(page.get_text())
            doc.close()

            import os as _os
            _os.unlink(tmp_path)

            full_text = "\n\n".join(pages_text)
            return full_text.strip()
        except ImportError:
            logger.warning("[ACCESS] FIX-GAP4: PyMuPDF not installed, PDF extraction unavailable")
            return ""
        except Exception as exc:
            logger.warning("[ACCESS] FIX-GAP4: PDF extraction error: %s", str(exc)[:100])
            return ""

    async def _try_trafilatura(self, url: str) -> Optional[AccessResult]:
        """Fetch content via trafilatura in thread pool (non-blocking).

        FIX-QM25-REVIVE: Trafilatura was disabled because its CPU-bound
        lxml/BS4 parsing blocks the asyncio event loop. This fix runs
        it in a thread pool executor to avoid GIL contention.

        Controlled by PG_TRAFILATURA_ENABLED env var (default "0").
        Returns None when disabled or when extraction fails.
        """
        if os.getenv("PG_TRAFILATURA_ENABLED", "0") != "1":
            return None

        try:
            import trafilatura

            loop = asyncio.get_event_loop()
            downloaded = await loop.run_in_executor(
                None, trafilatura.fetch_url, url
            )
            if not downloaded:
                return None

            # GH #1260: route the extraction through the ONE SIGSEGV-guarded
            # door (size gate + optional hard-killable subprocess) instead of a
            # bare `trafilatura.extract` in this thread-pool worker. A libxml2
            # C-crash on a pathological doc is NOT a catchable Python exception;
            # in a ThreadPoolExecutor thread it would take down the whole sweep.
            text = await loop.run_in_executor(
                None,
                lambda: safe_trafilatura_extract(
                    downloaded, include_links=True, include_tables=True
                ),
            )
            if text and len(text) > 200:
                logger.info(
                    "[ACCESS] Trafilatura succeeded for %s (%d chars)",
                    url[:60], len(text),
                )
                return AccessResult(
                    url=url,
                    content=text,
                    access_method="trafilatura",
                    legal_alternative=None,
                    success=True,
                    metadata={
                        "content_length": len(text),
                        "format": "text",
                    },
                )
            return None
        except ImportError:
            logger.warning(
                "[ACCESS] trafilatura not installed — skipping. "
                "Install with: pip install trafilatura"
            )
            return None
        except Exception as e:
            logger.warning(
                "[ACCESS] Trafilatura failed for %s: %s",
                url[:60], _safe_log_str(str(e)),
            )
            return None

    async def _try_jina_reader(self, url: str) -> AccessResult:
        """
        FIX-D1: Jina Reader as primary fetch tier.
        FIX-QM2: Exponential backoff on 429 (up to 2 retries).
        FIX-JINA: Also retry 401 (Jina returns 401 when concurrency
        exceeds free tier limit of 2). Add jitter to backoff.
        RC-9: Circuit breaker — skip after consecutive failures.

        Calls GET https://r.jina.ai/{url} to extract clean markdown content.
        With API key: 500 RPM. Without: 20 RPM.
        """
        import aiohttp
        import random

        # RC-9: Circuit breaker check
        global _jina_consecutive_failures, _jina_circuit_open_until
        now = _time_module.time()
        if _jina_circuit_open_until > now:
            logger.debug(
                "[ACCESS] RC-9: Jina circuit breaker OPEN (%.0fs remaining) — skipping %s",
                _jina_circuit_open_until - now, url[:60],
            )
            return AccessResult(
                url=url, content="", access_method="jina_reader",
                legal_alternative=None, success=False,
                metadata={"error": "circuit_breaker_open"},
            )

        jina_url = f"https://r.jina.ai/{url}"
        max_retries = int(os.getenv("PG_JINA_MAX_RETRIES", "3"))

        # FIX-JINA: Jina concurrency semaphore (free tier = 2 concurrent).
        # I-arch-007 (#1264): bound to the RUNNING loop (per-loop map) so the post-gen
        # contract-frame fetch in a fresh loop never hits the cross-loop RuntimeError.
        async with _get_jina_semaphore():
            for attempt in range(max_retries + 1):
                try:
                    timeout = aiohttp.ClientTimeout(total=30)
                    headers = {
                        **_NO_BROTLI_HEADERS,
                        "User-Agent": self.user_agent,
                        "Accept": "text/markdown",
                    }

                    jina_api_key = os.getenv("JINA_API_KEY")
                    if jina_api_key:
                        headers["Authorization"] = f"Bearer {jina_api_key}"

                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.get(jina_url, headers=headers) as response:
                            # FIX-JINA: Retry on 401 (concurrency exceeded) AND 429
                            if response.status in (401, 429):
                                if attempt < max_retries:
                                    jitter = random.uniform(0, 1.0)
                                    wait = 2.0 ** (attempt + 1) + jitter
                                    logger.warning(
                                        "[ACCESS] Jina %d for %s, "
                                        "backing off %.1fs (attempt %d/%d)",
                                        response.status,
                                        url[:60], wait, attempt + 1, max_retries + 1,
                                    )
                                    await asyncio.sleep(wait)
                                    continue
                                logger.warning(
                                    "[ACCESS] Jina %d exhausted retries for %s",
                                    response.status, url[:60],
                                )
                                return AccessResult(
                                    url=url,
                                    content="",
                                    access_method="jina_reader",
                                    legal_alternative=None,
                                    success=False,
                                    metadata={
                                        "status": response.status,
                                        "retries_exhausted": True,
                                    },
                                )

                            if response.status == 200:
                                content = await response.text()
                                if content and len(content.strip()) > 100:
                                    # RC-9: Reset circuit breaker on success
                                    _jina_consecutive_failures = 0
                                    logger.info(
                                        "[ACCESS] Jina Reader succeeded for %s (%d chars)",
                                        url[:60], len(content),
                                    )
                                    return AccessResult(
                                        url=url,
                                        content=content,
                                        access_method="jina_reader",
                                        legal_alternative=jina_url,
                                        success=True,
                                        metadata={
                                            "jina_url": jina_url,
                                            "content_length": len(content),
                                            "authenticated": bool(jina_api_key),
                                        },
                                    )

                            # RC-9: Track consecutive failure for circuit breaker
                            _jina_consecutive_failures += 1
                            if _jina_consecutive_failures >= _CIRCUIT_BREAKER_THRESHOLD:
                                _jina_circuit_open_until = _time_module.time() + _CIRCUIT_BREAKER_COOLDOWN
                                logger.warning(
                                    "[ACCESS] RC-9: Jina circuit breaker OPENED after "
                                    "%d consecutive failures (cooldown %.0fs)",
                                    _jina_consecutive_failures, _CIRCUIT_BREAKER_COOLDOWN,
                                )
                            logger.warning(
                                "[ACCESS] Jina Reader returned status %d for %s",
                                response.status, url[:60],
                            )
                            return AccessResult(
                                url=url,
                                content="",
                                access_method="jina_reader",
                                legal_alternative=None,
                                success=False,
                                metadata={"status": response.status},
                            )

                except Exception as e:
                    if attempt < max_retries:
                        # FIX-G: Exponential backoff for exceptions (was flat 1s)
                        jitter = random.uniform(0, 1.0)
                        wait = 2.0 ** (attempt + 1) + jitter
                        logger.warning(
                            "[ACCESS] Jina Reader exception for %s: %s — "
                            "backing off %.1fs (attempt %d/%d)",
                            url[:60], str(e)[:100], wait,
                            attempt + 1, max_retries + 1,
                        )
                        await asyncio.sleep(wait)
                        continue
                    # RC-9: Track consecutive failure for circuit breaker
                    _jina_consecutive_failures += 1
                    if _jina_consecutive_failures >= _CIRCUIT_BREAKER_THRESHOLD:
                        _jina_circuit_open_until = _time_module.time() + _CIRCUIT_BREAKER_COOLDOWN
                        logger.warning(
                            "[ACCESS] RC-9: Jina circuit breaker OPENED after "
                            "%d consecutive failures",
                            _jina_consecutive_failures,
                        )
                    logger.warning("[ACCESS] Jina Reader failed for %s: %s", url[:80], str(e)[:150])
                    return AccessResult(
                        url=url,
                        content="",
                        access_method="jina_reader",
                        legal_alternative=None,
                        success=False,
                        metadata={"error": str(e)},
                    )

        # Should not reach here, but safety fallback
        return AccessResult(
            url=url,
            content="",
            access_method="jina_reader",
            legal_alternative=None,
            success=False,
            metadata={"error": "Unexpected loop exit"},
        )

    async def _try_zyte(self, url: str) -> AccessResult:
        """I-fetch-004 (#1185): PAID Zyte fallback — the genuine last resort.

        Called by `fetch_with_bypass` ONLY after the entire free chain
        (direct -> concurrent quality-scored group -> Archive.org -> proxy ->
        timeout-retry -> Sci-Hub) has failed.

        Safety couplings (all required):
          - ENV-GATED: with ZYTE_API_KEY absent this is a complete NO-OP that
            returns a failure AccessResult and spends nothing. The call site
            also guards on the key, so the helper is never even invoked on
            un-keyed runs (double-safe — behaviour byte-identical to before).
          - COST-SMART: tries the cheap httpResponseBody mode first and
            escalates to the pricier JS-rendering browserHtml mode ONLY when
            the cheap result is unusable (empty / short / paywalled). A hard
            auth/quota error (401/402/429) returns fast WITHOUT a second paid
            call.
          - CIRCUIT BREAKER: after N consecutive failures the breaker opens for
            a cooldown so a Zyte outage cannot fire N doomed PAID calls on a
            ~1000-URL run.
          - FAITHFULNESS-UNAFFECTED: Zyte only RETRIEVES raw HTML; it is routed
            through the SAME `safe_trafilatura_extract` extractor every other
            backend uses, then through the downstream strict_verify / 4-role
            gates. No faithfulness gate is bypassed. The issue notes scraping
            bypasses bot-blocks, NOT paywalls — so a paywall stub remains a
            live possibility and is rejected by `_detect_paywall` before any
            success is returned.

        Zyte API (docs.zyte.com): POST https://api.zyte.com/v1/extract, HTTP
        Basic auth with the API key as username and an EMPTY password.
        httpResponseBody is BASE64-encoded; browserHtml is a plain HTML string.
        """
        import aiohttp
        import base64

        # Telemetry + breaker globals. Declared together so the `+= 1` lines
        # below do not raise UnboundLocalError.
        global _zyte_consecutive_failures, _zyte_circuit_open_until
        global _zyte_fallback_attempts, _zyte_fallback_success

        # ENV-GATE (strict NO-OP, zero spend when the key is absent).
        key = os.getenv("ZYTE_API_KEY")
        if not key:
            return AccessResult(
                url=url,
                content="",
                access_method="zyte",
                legal_alternative=None,
                success=False,
                metadata={"error": "ZYTE_API_KEY not set"},
            )

        # CIRCUIT BREAKER: skip (no paid call) while open.
        now = _time_module.time()
        if _zyte_circuit_open_until > now:
            remaining = _zyte_circuit_open_until - now
            logger.debug(
                "[ACCESS] Zyte circuit breaker OPEN for %s (%.0fs remaining)",
                url[:60], remaining,
            )
            return AccessResult(
                url=url,
                content="",
                access_method="zyte",
                legal_alternative=None,
                success=False,
                metadata={
                    "error": "circuit_breaker_open",
                    "cooldown_remaining": remaining,
                },
            )

        def _record_failure() -> None:
            """Increment the breaker and open it at threshold."""
            global _zyte_consecutive_failures, _zyte_circuit_open_until
            _zyte_consecutive_failures += 1
            if _zyte_consecutive_failures >= _CIRCUIT_BREAKER_THRESHOLD:
                _zyte_circuit_open_until = (
                    _time_module.time() + _CIRCUIT_BREAKER_COOLDOWN
                )
                logger.warning(
                    "[ACCESS] Zyte circuit breaker OPENED after %d consecutive "
                    "failures (cooldown %.0fs)",
                    _zyte_consecutive_failures, _CIRCUIT_BREAKER_COOLDOWN,
                )

        def _is_usable(text: "str | None") -> bool:
            """Usable = extracted, long enough, and not a paywall stub."""
            if not text or len(text) < _ZYTE_MIN_CONTENT_CHARS:
                return False
            if self._detect_paywall(text):
                return False
            return True

        timeout = aiohttp.ClientTimeout(total=_ZYTE_TIMEOUT)
        headers = {**_NO_BROTLI_HEADERS, "Content-Type": "application/json"}
        auth = aiohttp.BasicAuth(key, "")

        _zyte_fallback_attempts += 1

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # (1) CHEAP mode: httpResponseBody (base64-encoded).
                async with session.post(
                    _ZYTE_API_ENDPOINT,
                    headers=headers,
                    auth=auth,
                    json={"url": url, "httpResponseBody": True},
                ) as resp:
                    status = resp.status
                    # DIFFERENTIATED hard-error handling: auth/quota/rate-limit
                    # return fast and count toward the breaker — do NOT escalate
                    # a hard error into a second paid call.
                    if status in (401, 402, 403, 429):
                        body = (await resp.text())[:200]
                        logger.warning(
                            "[ACCESS] Zyte cheap request returned %d for %s: %s",
                            status, url[:60], _safe_log_str(body, 120),
                        )
                        _record_failure()
                        return AccessResult(
                            url=url, content="", access_method="zyte",
                            legal_alternative=None, success=False,
                            metadata={"status": status, "error": "auth_or_quota"},
                        )
                    if status != 200:
                        logger.warning(
                            "[ACCESS] Zyte cheap request returned status %d for %s",
                            status, url[:60],
                        )
                        _record_failure()
                        return AccessResult(
                            url=url, content="", access_method="zyte",
                            legal_alternative=None, success=False,
                            metadata={"status": status},
                        )
                    data = await resp.json()

                encoded = (data or {}).get("httpResponseBody")
                cheap_text: "str | None" = None
                if encoded:
                    html = base64.b64decode(encoded).decode(
                        "utf-8", errors="replace"
                    )
                    cheap_text = safe_trafilatura_extract(
                        html,
                        include_tables=True,
                        include_links=False,
                        output_format="txt",
                    )

                used_text = cheap_text
                mode = "httpResponseBody"
                escalated = False

                # (2) ESCALATE to browserHtml ONLY when the cheap result is
                # unusable (None / too short / paywalled). browserHtml is the
                # pricier JS-rendering, ban-solving mode.
                if not _is_usable(cheap_text):
                    escalated = True
                    mode = "browserHtml"
                    async with session.post(
                        _ZYTE_API_ENDPOINT,
                        headers=headers,
                        auth=auth,
                        json={"url": url, "browserHtml": True},
                    ) as resp2:
                        status2 = resp2.status
                        if status2 in (401, 402, 403, 429):
                            body2 = (await resp2.text())[:200]
                            logger.warning(
                                "[ACCESS] Zyte browserHtml returned %d for %s: %s",
                                status2, url[:60], _safe_log_str(body2, 120),
                            )
                            _record_failure()
                            return AccessResult(
                                url=url, content="", access_method="zyte",
                                legal_alternative=None, success=False,
                                metadata={"status": status2, "error": "auth_or_quota"},
                            )
                        if status2 != 200:
                            logger.warning(
                                "[ACCESS] Zyte browserHtml returned status %d for %s",
                                status2, url[:60],
                            )
                            _record_failure()
                            return AccessResult(
                                url=url, content="", access_method="zyte",
                                legal_alternative=None, success=False,
                                metadata={"status": status2},
                            )
                        data2 = await resp2.json()
                    browser_html = (data2 or {}).get("browserHtml")
                    used_text = None
                    if browser_html:
                        used_text = safe_trafilatura_extract(
                            browser_html,
                            include_tables=True,
                            include_links=False,
                            output_format="txt",
                        )

            # POST-PROCESSING CONSISTENCY: strip boilerplate (every sibling
            # return does this) then gate on paywall + min-length so a stub
            # can never pollute the evidence pool.
            content = _strip_navigation_boilerplate(used_text or "")
            if (
                content
                and len(content) >= _ZYTE_MIN_CONTENT_CHARS
                and not self._detect_paywall(content)
            ):
                _zyte_consecutive_failures = 0
                _zyte_fallback_success += 1
                logger.info(
                    "[ACCESS] Zyte succeeded for %s (%d chars, mode=%s, "
                    "escalated=%s, attempts=%d, successes=%d)",
                    url[:60], len(content), mode, escalated,
                    _zyte_fallback_attempts, _zyte_fallback_success,
                )
                return AccessResult(
                    url=url,
                    content=content[:50000],
                    access_method="zyte",
                    legal_alternative=None,
                    success=True,
                    metadata={
                        "content_length": len(content),
                        "zyte_mode": mode,
                        "escalated": escalated,
                    },
                )

            # Unusable (short / paywalled / empty) — terminal failure, no
            # further escalation.
            _record_failure()
            logger.info(
                "[ACCESS] Zyte produced unusable content for %s "
                "(mode=%s, escalated=%s)",
                url[:60], mode, escalated,
            )
            return AccessResult(
                url=url, content="", access_method="zyte",
                legal_alternative=None, success=False,
                metadata={
                    "error": "unusable_content",
                    "zyte_mode": mode,
                    "escalated": escalated,
                },
            )

        except Exception as e:
            # Never crash the fetch loop — any error returns a failure result.
            _record_failure()
            logger.warning(
                "[ACCESS] Zyte failed for %s: %s", url[:80], str(e)[:150],
            )
            return AccessResult(
                url=url, content="", access_method="zyte",
                legal_alternative=None, success=False,
                metadata={"error": str(e)[:200]},
            )

    async def _try_firecrawl(self, url: str) -> AccessResult:
        """
        FIX-D2 Hardened: Firecrawl with rate limiting, credit tracking,
        and differentiated error handling.

        Free plan limits: 500 credits/month, 10 req/min.
        """
        # FIX-044/Issue3: Respect PG_FIRECRAWL_ENABLED kill switch
        if os.getenv("PG_FIRECRAWL_ENABLED", "1") != "1":
            return AccessResult(
                url=url,
                content="",
                access_method="firecrawl",
                legal_alternative=None,
                success=False,
                metadata={"error": "Firecrawl disabled via PG_FIRECRAWL_ENABLED=0"},
            )

        import aiohttp

        # RC-10: Circuit breaker check for Firecrawl (mirrors Jina pattern)
        global _firecrawl_consecutive_failures, _firecrawl_circuit_open_until
        now = _time_module.time()
        if _firecrawl_circuit_open_until > now:
            remaining = _firecrawl_circuit_open_until - now
            logger.debug(
                "[ACCESS] Firecrawl circuit breaker OPEN for %s (%.0fs remaining)",
                url[:60], remaining,
            )
            return AccessResult(
                url=url,
                content="",
                access_method="firecrawl",
                legal_alternative=None,
                success=False,
                metadata={"error": "circuit_breaker_open", "cooldown_remaining": remaining},
            )

        firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY")
        if not firecrawl_api_key:
            logger.warning("[ACCESS] Firecrawl skipped — FIRECRAWL_API_KEY not set")
            return AccessResult(
                url=url,
                content="",
                access_method="firecrawl",
                legal_alternative=None,
                success=False,
                metadata={"error": "FIRECRAWL_API_KEY not set"},
            )

        # Credit gate: check before making request
        if not _firecrawl_has_credits():
            return AccessResult(
                url=url,
                content="",
                access_method="firecrawl",
                legal_alternative=None,
                success=False,
                metadata={
                    "error": "Monthly credit quota exhausted",
                    "credits_used": _firecrawl_credits_used,
                    "credits_quota": _FIRECRAWL_MONTHLY_QUOTA,
                },
            )

        # Rate limit: enforce minimum interval
        await _firecrawl_rate_limit()

        firecrawl_endpoint = "https://api.firecrawl.dev/v1/scrape"

        try:
            timeout = aiohttp.ClientTimeout(total=30)
            headers = {
                **_NO_BROTLI_HEADERS,
                "Authorization": f"Bearer {firecrawl_api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "url": url,
                "formats": ["markdown"],
            }

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    firecrawl_endpoint, headers=headers, json=payload
                ) as response:
                    status_code = response.status

                    # Differentiated error handling
                    if status_code == 429:
                        retry_after = response.headers.get("Retry-After", "10")
                        logger.warning(
                            "[ACCESS] Firecrawl 429 rate limited for %s — "
                            "Retry-After: %s",
                            url[:60],
                            retry_after,
                        )
                        return AccessResult(
                            url=url,
                            content="",
                            access_method="firecrawl",
                            legal_alternative=None,
                            success=False,
                            metadata={
                                "status": 429,
                                "retry_after": retry_after,
                                "error": "Rate limited",
                            },
                        )

                    if status_code == 401:
                        logger.error(
                            "[ACCESS] Firecrawl 401 unauthorized — "
                            "check FIRECRAWL_API_KEY"
                        )
                        return AccessResult(
                            url=url,
                            content="",
                            access_method="firecrawl",
                            legal_alternative=None,
                            success=False,
                            metadata={"status": 401, "error": "Unauthorized"},
                        )

                    if status_code == 402:
                        logger.error(
                            "[ACCESS] Firecrawl 402 payment required — "
                            "credits exhausted"
                        )
                        return AccessResult(
                            url=url,
                            content="",
                            access_method="firecrawl",
                            legal_alternative=None,
                            success=False,
                            metadata={"status": 402, "error": "Credits exhausted"},
                        )

                    if status_code == 200:
                        data = await response.json()

                        # Track credit usage
                        _firecrawl_track_credit()

                        # Validate response success field
                        if isinstance(data, dict) and not data.get("success", True):
                            error_msg = data.get("error", "Unknown error")
                            logger.warning(
                                "[ACCESS] Firecrawl returned success=false for %s: %s",
                                url[:60],
                                str(error_msg)[:200],
                            )
                            return AccessResult(
                                url=url,
                                content="",
                                access_method="firecrawl",
                                legal_alternative=None,
                                success=False,
                                metadata={
                                    "status": 200,
                                    "firecrawl_success": False,
                                    "error": str(error_msg)[:200],
                                },
                            )

                        # Extract markdown content
                        markdown_content = ""
                        resp_metadata: dict = {}
                        if isinstance(data, dict):
                            resp_data = data.get("data", {})
                            if isinstance(resp_data, dict):
                                markdown_content = resp_data.get("markdown", "")
                                resp_metadata = {
                                    "status_code": resp_data.get("statusCode"),
                                    "credits_used": _firecrawl_credits_used,
                                    "credits_quota": _FIRECRAWL_MONTHLY_QUOTA,
                                }

                        if markdown_content and len(markdown_content.strip()) > 100:
                            # RC-10: Reset circuit breaker on success
                            _firecrawl_consecutive_failures = 0
                            logger.info(
                                "[ACCESS] Firecrawl succeeded for %s "
                                "(%d chars, credit %d/%d)",
                                url[:60],
                                len(markdown_content),
                                _firecrawl_credits_used,
                                _FIRECRAWL_MONTHLY_QUOTA,
                            )
                            return AccessResult(
                                url=url,
                                content=markdown_content,
                                access_method="firecrawl",
                                legal_alternative=None,
                                success=True,
                                metadata={
                                    "content_length": len(markdown_content),
                                    "format": "markdown",
                                    **resp_metadata,
                                },
                            )

                    # RC-10: Track failure for circuit breaker
                    _firecrawl_consecutive_failures += 1
                    if _firecrawl_consecutive_failures >= _CIRCUIT_BREAKER_THRESHOLD:
                        _firecrawl_circuit_open_until = _time_module.time() + _CIRCUIT_BREAKER_COOLDOWN
                        logger.warning(
                            "[ACCESS] Firecrawl circuit breaker OPENED after %d consecutive failures "
                            "(cooldown %.0fs)",
                            _firecrawl_consecutive_failures, _CIRCUIT_BREAKER_COOLDOWN,
                        )
                    logger.warning(
                        "[ACCESS] Firecrawl returned status %d for %s",
                        status_code,
                        url[:60],
                    )
                    return AccessResult(
                        url=url,
                        content="",
                        access_method="firecrawl",
                        legal_alternative=None,
                        success=False,
                        metadata={"status": status_code},
                    )

        except Exception as e:
            # RC-10: Track failure for circuit breaker
            _firecrawl_consecutive_failures += 1
            if _firecrawl_consecutive_failures >= _CIRCUIT_BREAKER_THRESHOLD:
                _firecrawl_circuit_open_until = _time_module.time() + _CIRCUIT_BREAKER_COOLDOWN
                logger.warning(
                    "[ACCESS] Firecrawl circuit breaker OPENED after %d consecutive failures "
                    "(cooldown %.0fs)",
                    _firecrawl_consecutive_failures, _CIRCUIT_BREAKER_COOLDOWN,
                )
            logger.warning(
                "[ACCESS] Firecrawl failed for %s: %s",
                url[:80],
                str(e)[:150],
            )
            return AccessResult(
                url=url,
                content="",
                access_method="firecrawl",
                legal_alternative=None,
                success=False,
                metadata={"error": str(e)},
            )

    async def _try_unpaywall(self, doi: str) -> Optional[str]:
        """M-23a: Query Unpaywall for best legal open-access URL for a DOI.

        Unpaywall indexes 30M+ OA articles from repositories (arXiv,
        PMC, institutional) and publisher DOIs. Returns the best OA URL
        (PDF preferred) if available, else None. Free, ethical, and the
        first thing to try for paywalled journals like NEJM/Lancet/JAMA
        whose authors frequently post preprints or PMC copies.

        Reference: https://unpaywall.org/products/api
        Endpoint: https://api.unpaywall.org/v2/{doi}?email={email}
        Rate limit: 100K/day with free email-tagged access.
        """
        import aiohttp

        email = os.getenv("UNPAYWALL_EMAIL")
        if not email:
            return None

        api_url = f"https://api.unpaywall.org/v2/{doi}?email={email}"
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    api_url, headers=_NO_BROTLI_HEADERS
                ) as response:
                    if response.status == 404:
                        # Unknown DOI — normal, don't log noisily
                        return None
                    if response.status != 200:
                        logger.info(
                            "[ACCESS] M-23a: Unpaywall HTTP %d for DOI %s",
                            response.status, doi,
                        )
                        return None
                    data = await response.json()
                    if not data.get("is_oa"):
                        return None
                    # M-23e: Prefer a direct PDF URL across ALL oa_locations.
                    # Live testing exposed: Unpaywall's best_oa_location may
                    # be a repository landing page (figshare, discovery.ucl)
                    # whose bare URL 403s on headless fetch. A PDF URL from
                    # any location gets clean extraction via _extract_pdf_text.
                    # Only fall back to best.url when NO location has a PDF.
                    oa_locations = data.get("oa_locations") or []
                    pdf_urls = [
                        loc.get("url_for_pdf")
                        for loc in oa_locations
                        if loc.get("url_for_pdf")
                    ]
                    if pdf_urls:
                        oa_url = pdf_urls[0]
                        host_type = next(
                            (loc.get("host_type", "unknown")
                             for loc in oa_locations
                             if loc.get("url_for_pdf") == oa_url),
                            "unknown",
                        )
                        logger.info(
                            "[ACCESS] M-23a: Unpaywall PDF OA for %s: %s (%s)",
                            doi, oa_url[:80], host_type,
                        )
                        return oa_url
                    # No PDF. I-bug-775 (#815, Codex B): do NOT swap to a
                    # publisher / doi.org / DOI-resolver landing page — those
                    # fetch as 280-400-char stubs (mode 1) and are no better
                    # than the paywalled original. The ONLY non-PDF swap we
                    # allow is a PMC URL (it carries a PMCID, so the caller's
                    # BioC full-text path will resolve it). Everything else:
                    # return None and let the main cascade try the original URL.
                    best = data.get("best_oa_location") or {}
                    landing = best.get("url")
                    host_type = best.get("host_type", "unknown")
                    # Scan all OA locations for a PMC URL (PMCID-bearing).
                    pmc_landing = next(
                        (
                            loc.get("url")
                            for loc in oa_locations
                            if loc.get("url")
                            and re.search(r"/PMC\d+\b", loc.get("url"), re.IGNORECASE)
                        ),
                        None,
                    )
                    if pmc_landing:
                        logger.info(
                            "[ACCESS] M-23a: Unpaywall PMC OA URL for %s: %s "
                            "(BioC full-text will resolve)",
                            doi, pmc_landing[:80],
                        )
                        return pmc_landing
                    # No PDF, no PMC URL — do not swap to a landing page
                    # (mode-1 stub). Keep the original URL for the cascade.
                    if landing:
                        logger.info(
                            "[ACCESS] M-23a: Unpaywall %s landing without PDF/PMC "
                            "for %s — keeping original URL (no landing swap)",
                            host_type, doi,
                        )
                    return None
        except asyncio.TimeoutError:
            logger.info("[ACCESS] M-23a: Unpaywall timeout for DOI %s", doi)
            return None
        except Exception as e:
            logger.warning(
                "[ACCESS] M-23a: Unpaywall failed for DOI %s: %s",
                doi, str(e)[:120],
            )
            return None

    async def _direct_fetch(self, url: str) -> AccessResult:
        """Direct HTTP fetch with markdown Accept header (FIX-D6/A3) and 5xx retry (FIX-D5)."""
        import aiohttp

        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # FIX-D6/A3: Add markdown Accept header to prefer markdown responses
                headers = {
                    **_NO_BROTLI_HEADERS,
                    "User-Agent": self.user_agent,
                    "Accept": "text/markdown, text/html;q=0.9, */*;q=0.8",
                }

                async with session.get(url, headers=headers) as response:
                    # FIX-D6/A3: Log if server returned markdown content type
                    content_type = response.headers.get("Content-Type", "")
                    if "text/markdown" in content_type.lower():
                        logger.info(
                            "[ACCESS] Server returned markdown content for %s",
                            url[:60],
                        )

                    # FIX-D5: Retry once with 3s delay for 5xx status codes
                    if response.status >= 500:
                        logger.info(
                            "[ACCESS] Direct fetch got %d for %s, retrying in 3s",
                            response.status, url[:60],
                        )
                        await asyncio.sleep(3)
                        async with session.get(url, headers=headers) as retry_response:
                            retry_content_type = retry_response.headers.get("Content-Type", "")
                            if "text/markdown" in retry_content_type.lower():
                                logger.info(
                                    "[ACCESS] Server returned markdown content on retry for %s",
                                    url[:60],
                                )
                            content = await retry_response.text()
                            return AccessResult(
                                url=url,
                                content=content,
                                access_method="direct",
                                legal_alternative=None,
                                success=retry_response.status == 200,
                                metadata={
                                    "status": retry_response.status,
                                    "retried": True,
                                    "original_status": response.status,
                                    "content_type": retry_content_type,
                                },
                            )

                    content = await response.text()

                    return AccessResult(
                        url=url,
                        content=content,
                        access_method="direct",
                        legal_alternative=None,
                        success=response.status == 200,
                        metadata={
                            "status": response.status,
                            "content_type": content_type,
                        },
                    )

        except Exception as e:
            # SF-35: Log direct fetch failures (was completely silent)
            logger.warning("[ACCESS] direct fetch failed for %s: %s", url[:80], str(e)[:150])
            return AccessResult(
                url=url,
                content="",
                access_method="direct",
                legal_alternative=None,
                success=False,
                metadata={"error": str(e)}
            )

    async def _try_archive_org(self, url: str) -> AccessResult:
        """Try Archive.org Wayback Machine."""
        import aiohttp

        try:
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # Check availability
                api_url = f"https://archive.org/wayback/available?url={url}"

                async with session.get(api_url, headers=_NO_BROTLI_HEADERS) as response:
                    data = await response.json()

                    snapshots = data.get("archived_snapshots", {})
                    closest = snapshots.get("closest", {})

                    if closest.get("available"):
                        archive_url = closest["url"]

                        async with session.get(archive_url, headers=_NO_BROTLI_HEADERS) as archive_response:
                            content = await archive_response.text()

                            return AccessResult(
                                url=url,
                                content=content,
                                access_method="archive.org",
                                legal_alternative=archive_url,
                                success=True,
                                metadata={"archive_url": archive_url, "timestamp": closest.get("timestamp")}
                            )

                    return AccessResult(url=url, content="", access_method="archive.org",
                                      legal_alternative=None, success=False,
                                      metadata={"error": "No archive available"})

        except Exception as e:
            # SF-37: Log Archive.org failures (was completely silent)
            logger.warning("[ACCESS] Archive.org failed for %s: %s", url[:80], str(e)[:150])
            return AccessResult(url=url, content="", access_method="archive.org",
                              legal_alternative=None, success=False,
                              metadata={"error": str(e)})

    @staticmethod
    def _docling_extract(pdf_bytes: bytes) -> str:
        """PL: Extract markdown from PDF using IBM Docling (97.9% table accuracy)."""
        import tempfile
        import os as _os

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        try:
            from docling.document_converter import DocumentConverter
            converter = DocumentConverter()
            result = converter.convert(tmp_path)
            md_text = result.document.export_to_markdown()
            return md_text.strip()
        finally:
            _os.unlink(tmp_path)

    # ── I-wire-001/W4 (#1313): clinical-PDF mineru25 (winner) selector ──────
    @staticmethod
    def _gpu_available() -> bool:
        """True iff a CUDA GPU is visible (mineru25 is a GPU VLM extractor).

        Mirrors the repo-standard probe used by the NLI verifier / embedder
        (``torch.cuda.is_available()``). Returns False — never raises — when
        torch is absent, so a CPU-only fetch host degrades to Docling LOUDLY.
        """
        try:
            import torch  # type: ignore
            return bool(torch.cuda.is_available())
        except Exception:  # noqa: BLE001 — no torch / no driver => no GPU
            return False

    async def _maybe_mineru25_extract(self, url: str, pdf_bytes: bytes) -> str:
        """W4 winner: run MinerU 2.5 (GPU VLM) iff a GPU is present.

        Returns the extracted markdown on a genuine mineru25 win, or ``""`` to
        signal the caller to fall through to the UNCHANGED Docling -> PyMuPDF
        path. Every non-win is a DISCLOSED, LOUD degradation (point-1 of the
        wiring standard): it logs a WARN and records the selected extractor in
        the process-global tool tracer (point-8 highest-visibility stream) so
        the run manifest / console / fail-loud canary can see which extractor
        actually fired. NEVER a silent no-op.

        Faithfulness engine is untouched — this only chooses the extractor that
        produces the verbatim text strict_verify later grounds.
        """
        import time as _time

        def _record(backend: str, status: str, latency_ms: float, **meta: object) -> None:
            # I-wire-003 B3 (#1317): LOUD canary on EVERY winner-degrade branch. A
            # ``fallback_reason`` in meta means mineru25 (W4 clinical-PDF winner) did
            # NOT win and the run silently fell back to a CPU extractor. Emit a single
            # grep-able token so a future run cannot silently degrade the winner —
            # the run-log surface for the manifest ``clinical_pdf_winner_degraded``
            # flag (derived from the SAME row recorded just below). Fail-safe: a log
            # error can never break extraction.
            _reason = meta.get("fallback_reason")
            if _reason:
                logger.warning(
                    "[W4-CANARY] clinical_pdf_winner_degraded=true reason=%s "
                    "selected_extractor=%s url=%s — mineru25 requested but did NOT "
                    "win; verify on the GPU fetch host (B3 #1317).",
                    _reason, meta.get("selected_extractor", backend), url[:60],
                )
            # Highest-visibility event (point 8) via the EXISTING tool tracer:
            # lands in tool_trace.jsonl + manifest['tool_utilization'] + the live
            # console (_tool_event renders backend_used). Fail-safe: a tracer
            # error can never break extraction.
            try:
                from src.polaris_graph.telemetry.tool_tracer import (
                    get_tool_tracer,
                    tool_tracker_enabled,
                )
                if not tool_tracker_enabled():
                    return
                get_tool_tracer().record(
                    tool_name="pdf_extract",
                    target=url,
                    status=status,
                    latency_ms=latency_ms,
                    backend_used=backend,
                    bytes_received=len(pdf_bytes),
                    **meta,
                )
            except Exception as _exc:  # noqa: BLE001 — observability must not abort
                logger.debug("[ACCESS] W4: tool-trace record skipped: %s", str(_exc)[:80])

        # GPU-first (point 2): mineru25 is a GPU VLM. No GPU => disclosed CPU fallback.
        if not self._gpu_available():
            logger.warning(
                "[ACCESS] W4: PG_CLINICAL_PDF_EXTRACTOR=mineru25 but NO GPU visible "
                "-> DISCLOSED fallback to Docling (CPU) for %s", url[:60],
            )
            _record("docling", "retry", 0.0, selected_extractor="docling",
                    requested_extractor="mineru25", fallback_reason="no_gpu")
            return ""

        # I-deepfix-001 BUG-B (#1344): mineru25 circuit breaker. After N CONSECUTIVE
        # genuine failures (timeout / hard exception) the breaker OPENS and skips the
        # 300s-per-PDF mineru attempt — going straight to the disclosed Docling/PyMuPDF
        # fallback so a wedged VLM cannot grind a ~1000-URL run for hours. `<= 0`
        # threshold disables it (escape hatch). The body is STILL extracted by the
        # fallback (no source dropped); the skip is LOUD (W4-CANARY + tool-trace).
        _ckt_threshold = _mineru25_circuit_threshold()
        if _ckt_threshold > 0 and _mineru25_circuit_open_until > _time.monotonic():
            _remaining = _mineru25_circuit_open_until - _time.monotonic()
            logger.warning(
                "[ACCESS] W4: mineru25 circuit breaker OPEN (%.0fs remaining after "
                "%d consecutive failures) -> DISCLOSED fallback to Docling for %s "
                "(PG_MINERU25_CIRCUIT_THRESHOLD)",
                _remaining, _mineru25_consecutive_failures, url[:60],
            )
            _record("docling", "retry", 0.0, selected_extractor="docling",
                    requested_extractor="mineru25",
                    fallback_reason="mineru25_circuit_open")
            return ""

        def _note_mineru25_failure() -> None:
            """I-deepfix-001 BUG-B: count one consecutive mineru25 HEALTH failure
            (timeout / hard exception); OPEN the breaker at the threshold. Disabled
            when the threshold is ``<= 0``."""
            global _mineru25_consecutive_failures, _mineru25_circuit_open_until
            if _ckt_threshold <= 0:
                return
            _mineru25_consecutive_failures += 1
            if _mineru25_consecutive_failures >= _ckt_threshold:
                _mineru25_circuit_open_until = (
                    _time.monotonic() + _mineru25_circuit_cooldown()
                )
                logger.warning(
                    "[ACCESS] W4: mineru25 circuit breaker TRIPPED after %d "
                    "consecutive failures — skipping mineru25 for %.0fs (Docling "
                    "fallback only)",
                    _mineru25_consecutive_failures, _mineru25_circuit_cooldown(),
                )

        def _reset_mineru25_circuit() -> None:
            """I-deepfix-001 BUG-B: a genuine success clears the consecutive-failure
            run (mirrors jina:3802) so a transient blip never false-trips a healthy
            mineru."""
            global _mineru25_consecutive_failures
            _mineru25_consecutive_failures = 0

        _t0 = _time.perf_counter()
        try:
            import asyncio as _aio
            loop = _aio.get_event_loop()
            # Finite-generous timeout (point 5): never infinite. A hung VLM
            # must not stall the per-URL fetch fan-out.
            # I-deepfix-001 W09-mineru-gpu-lock-bound (#1344): the per-PDF mineru timeout
            # must NOT exceed the OUTER per-URL fetch deadline (PG_FETCH_DEADLINE_SECONDS,
            # ~90s). When it did (300 > 90) the outer fetch abandoned the worker at 90s while
            # this wait_for kept the inner thread running do_parse to completion (holding the
            # GPU lock) — so the inner TimeoutError NEVER fired, the BUG-B breaker never saw a
            # timeout, and the convoy persisted. ALIGN: cap mineru's own wait_for to the fetch
            # deadline minus a small margin so it fails-fast to docling INSIDE the 90s window,
            # letting the breaker actually see + count the timeout. Env-driven (LAW VI); the
            # default is still 300 when no fetch deadline is set.
            _raw_mineru_to = float(os.getenv("PG_MINERU25_TIMEOUT_S", "300"))
            # COMPLETENESS-CRITIC fix (I-deepfix-001 round-2): the GOVERNING per-URL
            # wall that abandons the bypass worker is live_retriever's worker.join on
            # PG_FETCH_DEADLINE_SECONDS, whose code default is 90 (live_retriever.py:3003)
            # — NOT 0. The cert slate sets NEITHER PG_FETCH_DEADLINE_SECONDS nor
            # PG_LIVE_RETRIEVER_FETCH_TIMEOUT_SECONDS, so both fall to their code
            # defaults (90 and 120). Reading "0" here made the alignment a NO-OP in the
            # configured run (mineru kept its 300s wait_for while the worker was
            # abandoned at 90s). Mirror live_retriever's 90 default so the mineru
            # wait_for aligns to min(300, 90 - margin) even when the slate is silent.
            _fetch_deadline = float(os.getenv("PG_FETCH_DEADLINE_SECONDS", "90") or "90")
            _mineru_margin = float(os.getenv("PG_MINERU25_TIMEOUT_MARGIN_S", "5"))
            if _fetch_deadline > 0:
                timeout_s = max(1.0, min(_raw_mineru_to, _fetch_deadline - _mineru_margin))
            else:
                timeout_s = max(1.0, _raw_mineru_to)
            md_text = await _aio.wait_for(
                loop.run_in_executor(None, self._mineru25_extract, pdf_bytes),
                timeout=timeout_s,
            )
            latency_ms = (_time.perf_counter() - _t0) * 1000.0
            if md_text and len(md_text) > 500:
                logger.info(
                    "[ACCESS] W4: mineru25 (GPU VLM) extracted %d chars from PDF %s",
                    len(md_text), url[:60],
                )
                # I-deepfix-001 BUG-B: a genuine success clears the breaker's
                # consecutive-failure run (mineru is healthy).
                _reset_mineru25_circuit()
                _record("mineru25", "ok", latency_ms,
                        selected_extractor="mineru25", chars=len(md_text))
                return md_text
            # Empty / landing-stub output => disclosed fallback (the §1B mode).
            # I-deepfix-001 BUG-B: this is a per-PDF CONTENT outcome (this PDF was a
            # landing stub), NOT a mineru HEALTH failure — it does NOT count toward
            # the breaker (tripping on it would skip PDFs mineru could handle).
            logger.warning(
                "[ACCESS] W4: mineru25 returned thin/empty output (%d chars) "
                "-> DISCLOSED fallback to Docling for %s",
                len(md_text or ""), url[:60],
            )
            _record("docling", "retry", latency_ms, selected_extractor="docling",
                    requested_extractor="mineru25", fallback_reason="mineru25_empty")
            return ""
        except _aio.TimeoutError:
            latency_ms = (_time.perf_counter() - _t0) * 1000.0
            # I-deepfix-001 BUG-B: a hung VLM is a genuine HEALTH failure (the
            # dominant grind mode) — count it toward the breaker.
            _note_mineru25_failure()
            logger.warning(
                "[ACCESS] W4: mineru25 timed out after %.0fs -> DISCLOSED fallback "
                "to Docling for %s", latency_ms / 1000.0, url[:60],
            )
            _record("docling", "timeout", latency_ms, selected_extractor="docling",
                    requested_extractor="mineru25", fallback_reason="mineru25_timeout")
            return ""
        except Exception as exc:  # noqa: BLE001 — any mineru failure => LOUD fallback
            latency_ms = (_time.perf_counter() - _t0) * 1000.0
            # I-deepfix-001 BUG-B: a hard exception (model-load failure, CUDA OOM)
            # is a genuine HEALTH failure — count it toward the breaker.
            _note_mineru25_failure()
            logger.warning(
                "[ACCESS] W4: mineru25 failed (%s) -> DISCLOSED fallback to Docling "
                "for %s", str(exc)[:120], url[:60],
            )
            _record("docling", "fail", latency_ms, selected_extractor="docling",
                    requested_extractor="mineru25", fallback_reason="mineru25_error",
                    error=str(exc)[:160])
            return ""

    @staticmethod
    def _mineru25_extract(pdf_bytes: bytes) -> str:
        """W4 winner: MinerU 2.5 VLM PDF -> markdown (GPU, sovereign OSS).

        Uses the offline in-process ``do_parse`` entry point of the MinerU
        package (opendatalab/MinerU2.5-2509-1.2B, custom-Apache, self-hosted).
        Runs on the CALLER's GPU-gated thread; this static method assumes a GPU
        is present (the async wrapper enforces that). Returns the markdown
        string (tables + sections preserved), or ``""`` on any failure so the
        async wrapper degrades LOUDLY to Docling.

        Zero hard-code (LAW VI): model lang, backend, source, and server URL are
        env knobs. The backend defaults to ``vlm-transformers`` — the verified
        in-process, no-separate-server, GPU-local VLM backend (MinerU 2.5 README
        + arXiv 2509.22186). ``vlm-vllm-engine`` / ``vlm-vllm-async-engine`` are
        the higher-throughput vLLM modes (more CUDA-setup-sensitive) and
        ``vlm-http-client`` targets a remote mineru-api server via
        PG_MINERU25_SERVER_URL.

        Model pin (point-16, §9.1.8 "model must be RIGHT"): the validated winner
        is opendatalab/MinerU2.5-2509-1.2B. do_parse has NO model-name parameter
        — MinerU resolves the VLM model from MINERU_MODEL_SOURCE + its bundled
        default. We surface MINERU_MODEL_SOURCE + MINERU_DEVICE_MODE as knobs and
        export them before the call so the run uses the pinned source, never a
        silently-drifted default.
        """
        import tempfile
        import os as _os
        from pathlib import Path as _Path

        backend = os.getenv("PG_MINERU25_BACKEND", "vlm-transformers").strip()
        lang = os.getenv("PG_MINERU25_LANG", "en").strip()
        server_url = os.getenv("PG_MINERU25_SERVER_URL", "").strip() or None

        # Pin model source + device mode for MinerU (it reads these from the
        # environment). Defaults: huggingface source, CUDA (GPU-first point-2).
        # Only SET when not already provided by the operator (no clobber).
        _os.environ.setdefault(
            "MINERU_MODEL_SOURCE", os.getenv("PG_MINERU25_MODEL_SOURCE", "huggingface")
        )
        _os.environ.setdefault(
            "MINERU_DEVICE_MODE", os.getenv("PG_MINERU25_DEVICE_MODE", "cuda")
        )

        # do_parse writes artifacts to disk under output_dir/<name>/vlm/<name>.md.
        with tempfile.TemporaryDirectory(prefix="mineru25_") as _out_dir:
            name = "doc"
            try:
                from mineru.cli.common import do_parse  # type: ignore
            except Exception as exc:  # noqa: BLE001 — package absent => caller falls back
                raise RuntimeError(
                    f"mineru not installed (pip install 'mineru[core]' / "
                    f"'mineru-vl-utils[transformers]' from "
                    f"github.com/opendatalab/MinerU; winner model "
                    f"opendatalab/MinerU2.5-2509-1.2B): {exc!r}"
                ) from exc

            # I-wire-014 ISSUE B (#1313 W4): SERIALIZE the in-process VLM
            # extraction under the process-wide ``_mineru25_gpu_lock``. ``do_parse``
            # drives PDFium (non-thread-safe, process-global state) AND the shared
            # MinerU model singleton; calling it concurrently from two fetch worker
            # threads corrupts both (proven on the VM: PdfiumError / tensor-shape
            # crash when concurrent, both succeed when serialized). The lock is
            # held ONLY around ``do_parse`` — the temp-dir setup above and the
            # per-call markdown read below are thread-local and stay parallel. This
            # is OUTPUT-PRESERVING: it changes only timing, never which PDFs are
            # extracted, the verbatim text, or any faithfulness gate. A 24 GB GPU
            # VLM at batch_size 8 is single-tenant regardless, so serialization is
            # ~free; it only removes the corruption.
            # Codex gate P1 (#1336): hold the lock ONLY for the IN-PROCESS VLM backend — the
            # PDFium + shared-model-singleton race is in-process. The remote "vlm-http-client"
            # backend's concurrency is the API server's domain; locking it here would needlessly
            # serialize concurrent PDF fetches (throughput cliff) without fixing any race.
            _inproc_vlm = backend != "vlm-http-client"
            # I-deepfix-001 W09-mineru-gpu-lock-bound (#1344): a BOUNDED lock acquire. The
            # plain blocking `with _mineru25_gpu_lock:` had NO timeout — when the outer 90s
            # fetch deadline abandoned a worker mid-do_parse, that worker's executor thread
            # kept the GPU lock held, and the NEXT worker blocked here FOREVER (the convoy).
            # Acquire with a timeout; on failure emit a LOUD W4-CANARY and return "" to fall
            # through to the disclosed docling path (no source dropped, §-1.3). The remote
            # "vlm-http-client" backend takes the nullcontext (its concurrency is the API
            # server's domain) — unchanged.
            _lock_held = False
            if _inproc_vlm:
                _lock_wait = float(os.getenv("PG_MINERU25_LOCK_WAIT_S", "60"))
                if not _mineru25_gpu_lock.acquire(timeout=_lock_wait):
                    logger.warning(
                        "[ACCESS] W4-CANARY: mineru25 GPU lock not acquired within %.0fs "
                        "(a prior abandoned do_parse still holds it) -> DISCLOSED docling "
                        "fallback (PG_MINERU25_LOCK_WAIT_S)", _lock_wait,
                    )
                    return ""
                _lock_held = True
            try:
                do_parse(
                    output_dir=_out_dir,
                    pdf_file_names=[name],
                    pdf_bytes_list=[pdf_bytes],
                    p_lang_list=[lang],
                    backend=backend,
                    server_url=server_url,
                    # Tables + formulas ON (the clinical-PDF table-fidelity lane).
                    formula_enable=True,
                    table_enable=True,
                    # We only need the markdown; skip bbox/pdf/json dumps for speed.
                    f_dump_md=True,
                    f_draw_layout_bbox=False,
                    f_draw_span_bbox=False,
                    f_dump_middle_json=False,
                    f_dump_model_output=False,
                    f_dump_orig_pdf=False,
                    f_dump_content_list=False,
                )
            finally:
                # I-deepfix-001 W09 (#1344): ALWAYS release the bounded GPU lock, even if
                # do_parse raised — otherwise an exception inside do_parse would leak the lock
                # and re-create the convoy this fix removes.
                if _lock_held:
                    _mineru25_gpu_lock.release()

            # Locate the produced markdown. VLM backend lands it at
            # <out>/<name>/vlm/<name>.md; be tolerant of layout drift.
            md_path = _Path(_out_dir) / name / "vlm" / f"{name}.md"
            if not md_path.exists():
                hits = sorted(_Path(_out_dir).rglob(f"{name}.md"))
                if not hits:
                    hits = sorted(_Path(_out_dir).rglob("*.md"))
                if hits:
                    md_path = hits[0]
            if md_path.exists():
                return md_path.read_text(encoding="utf-8").strip()
            return ""

    async def _resolve_academic_url(self, url: str) -> tuple[str, str]:
        """PL: Resolve academic metadata URLs to actual paper URLs + DOIs.

        Handles three cases:
        1. S2 landing pages (semanticscholar.org/paper/xxx) -> OA PDF URL or DOI
        2. ScienceDirect PIIs -> CrossRef -> DOI
        3. doi.org URLs -> follow redirect to publisher

        Returns (resolved_url, doi). Both may be empty if resolution fails.
        """
        import aiohttp
        import re

        resolved_url = ""
        doi = ""

        # Case 1: Semantic Scholar landing pages
        if "semanticscholar.org/paper/" in url:
            paper_id = url.rstrip("/").split("/")[-1]
            # Strip any title slug (e.g., "Title-of-Paper/abc123" -> "abc123")
            if len(paper_id) < 10:
                parts = url.rstrip("/").split("/")
                paper_id = parts[-1] if len(parts[-1]) >= 10 else parts[-2] if len(parts) > 1 else paper_id

            s2_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
            headers = {"x-api-key": s2_key} if s2_key else {}

            try:
                timeout = aiohttp.ClientTimeout(total=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    api_url = (
                        f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}"
                        f"?fields=doi,openAccessPdf,url"
                    )
                    async with session.get(api_url, headers=headers) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            doi = data.get("doi", "") or ""
                            oa_pdf = data.get("openAccessPdf")
                            if oa_pdf and oa_pdf.get("url"):
                                resolved_url = oa_pdf["url"]
                                logger.info(
                                    "[ACCESS] PL: S2 %s -> OA PDF: %s",
                                    paper_id[:12], resolved_url[:60],
                                )
                            elif doi:
                                resolved_url = f"https://doi.org/{doi}"
                                logger.info(
                                    "[ACCESS] PL: S2 %s -> DOI: %s",
                                    paper_id[:12], doi,
                                )
            except Exception as exc:
                logger.debug("[ACCESS] PL: S2 resolve failed for %s: %s", paper_id[:12], str(exc)[:60])

        # Case 2: ScienceDirect PIIs
        elif "sciencedirect.com" in url and "pii/" in url:
            pii_match = re.search(r"pii/([A-Z0-9]+)", url)
            if pii_match:
                pii = pii_match.group(1)
                try:
                    timeout = aiohttp.ClientTimeout(total=10)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        cr_url = f"https://api.crossref.org/works?filter=alternative-id:{pii}&rows=1"
                        async with session.get(cr_url) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                items = data.get("message", {}).get("items", [])
                                if items:
                                    doi = items[0].get("DOI", "")
                                    if doi:
                                        resolved_url = f"https://doi.org/{doi}"
                                        logger.info(
                                            "[ACCESS] PL: ScienceDirect PII %s -> DOI: %s",
                                            pii[:12], doi,
                                        )
                except Exception as exc:
                    logger.debug("[ACCESS] PL: CrossRef resolve failed for %s: %s", pii[:12], str(exc)[:60])

        # Case 3: Extract DOI from URL for Nature, JAMA, tandfonline, etc.
        if not doi:
            doi_match = re.search(r"(10\.\d{4,9}/[^\s\"<>',;]+)", url)
            if doi_match:
                doi = doi_match.group(1).rstrip(".")
            # Nature: /articles/s41574-022-00638-x -> 10.1038/s41574-022-00638-x
            elif "nature.com/articles/" in url:
                art_match = re.search(r"articles/(s\d+-\d+-\d+-\w+)", url)
                if art_match:
                    doi = f"10.1038/{art_match.group(1)}"

        return resolved_url or url, doi

    async def _try_scihub(self, url: str) -> AccessResult:
        """PL: Try Sci-Hub for paywalled academic papers.

        Extracts DOI from URL, queries Sci-Hub mirrors, downloads PDF,
        and converts to text via PyMuPDF. Last resort after all legal
        methods exhausted.
        """
        import aiohttp
        import re

        # Extract DOI from URL
        doi = None
        doi_match = re.search(r"(10\.\d{4,9}/[^\s\])<>\"',;]+)", url)
        if doi_match:
            doi = doi_match.group(1).rstrip(".")

        if not doi:
            return AccessResult(url=url, content="", access_method="scihub",
                                legal_alternative=None, success=False,
                                metadata={"error": "No DOI found in URL"})

        mirrors = ["https://sci-hub.st", "https://sci-hub.ru"]
        timeout = aiohttp.ClientTimeout(total=20)

        for mirror in mirrors:
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    scihub_url = f"{mirror}/{doi}"
                    async with session.get(scihub_url) as resp:
                        if resp.status != 200:
                            continue
                        html = await resp.text()

                        # Check if paper is available
                        if "not available" in html.lower()[:500]:
                            continue

                        # Extract PDF URL from embed/iframe
                        pdf_match = re.search(
                            r'(?:embed|iframe)[^>]+src=["\']([^"\']+\.pdf[^"\']*)',
                            html,
                        )
                        if not pdf_match:
                            # Try direct PDF link pattern
                            pdf_match = re.search(r'(//[^\s"<>]+\.pdf)', html)

                        if not pdf_match:
                            # No PDF found but page loaded — try extracting
                            # text content from the HTML itself
                            if len(html) > 5000:
                                return AccessResult(
                                    url=url, content=html[:30000],
                                    access_method="scihub_html",
                                    legal_alternative=scihub_url,
                                    success=True,
                                    metadata={"doi": doi, "mirror": mirror},
                                )
                            continue

                        pdf_url = pdf_match.group(1)
                        if pdf_url.startswith("//"):
                            pdf_url = "https:" + pdf_url

                        # Download PDF
                        async with session.get(pdf_url) as pdf_resp:
                            if pdf_resp.status != 200:
                                continue
                            pdf_bytes = await pdf_resp.read()

                        # Extract text from PDF
                        try:
                            import fitz  # PyMuPDF
                            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                            text_parts = []
                            for page in doc:
                                text_parts.append(page.get_text())
                            doc.close()
                            full_text = "\n\n".join(text_parts)

                            if len(full_text) > 500:
                                # ev_461: same masthead strip as the .pdf branch —
                                # this is a separate PDF->text seam (Sci-Hub PyMuPDF).
                                full_text = strip_pdf_frontmatter(full_text)
                                logger.info(
                                    "[ACCESS] Sci-Hub PDF extracted for %s: %d chars from %d pages",
                                    doi, len(full_text), len(text_parts),
                                )
                                return AccessResult(
                                    url=url, content=full_text[:50000],
                                    access_method="scihub_pdf",
                                    legal_alternative=scihub_url,
                                    success=True,
                                    metadata={"doi": doi, "mirror": mirror, "pages": len(text_parts)},
                                )
                        except ImportError:
                            logger.warning("[ACCESS] PyMuPDF not installed — cannot extract Sci-Hub PDF")
                        except Exception as pdf_exc:
                            logger.warning("[ACCESS] Sci-Hub PDF extraction failed: %s", str(pdf_exc)[:100])

            except Exception as exc:
                logger.debug("[ACCESS] Sci-Hub mirror %s failed: %s", mirror, str(exc)[:80])

        return AccessResult(url=url, content="", access_method="scihub",
                            legal_alternative=None, success=False,
                            metadata={"error": "All Sci-Hub mirrors failed", "doi": doi})

    async def _try_proxy(self, url: str) -> AccessResult:
        """Try institutional proxy."""
        import aiohttp

        if not self.proxy:
            return AccessResult(url=url, content="", access_method="proxy",
                              legal_alternative=None, success=False,
                              metadata={"error": "No proxy configured"})

        try:
            # Rewrite URL through proxy
            parsed = urlparse(url)
            proxied_url = url.replace(parsed.netloc, f"{parsed.netloc}.{self.proxy}")

            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(proxied_url, headers={**_NO_BROTLI_HEADERS, "User-Agent": self.user_agent}) as response:
                    content = await response.text()

                    return AccessResult(
                        url=url,
                        content=content,
                        access_method="proxy",
                        legal_alternative=proxied_url,
                        success=response.status == 200,
                        metadata={"proxied_url": proxied_url}
                    )

        except Exception as e:
            # SF-38: Log proxy failures (was completely silent)
            logger.warning("[ACCESS] Proxy failed for %s: %s", url[:80], str(e)[:150])
            return AccessResult(url=url, content="", access_method="proxy",
                              legal_alternative=None, success=False,
                              metadata={"error": str(e)})

    def _is_block_page(
        self, url: str, content: str, block_state: Dict[str, bool]
    ) -> bool:
        """D (I-extract-001 #1327): flag-gated block-page/stub screen for ONE
        fetched body.

        When the detector is ON and the body is a challenge / WAF block /
        redirect-or-error stub, this records the detection (canary `detected`),
        marks `block_state` so a later clean fetch on this URL counts as a
        re-fetch, logs the behavioral canary line, and returns True — the caller
        MUST NOT return this body (re-route to the next backend; or, when no
        backend remains, the fetch falls through to the failed path → drops at
        strict_verify, never fabricated). Returns False (pure no-op) when the
        detector is OFF or the body is real content. Faithfulness-neutral."""
        if not block_page_detector_enabled():
            return False
        klass = classify_block_page(content, url)
        if not klass:
            return False
        total = _record_block_page_detection()
        block_state["seen"] = True
        logger.warning(
            "[ACCESS] block_page_detector: %s flagged for %s — re-route/re-fetch "
            "(detected=%d)",
            klass, url[:80], total,
        )
        return True

    def _finalize_clean_fetch(
        self, result: "AccessResult", block_state: Dict[str, bool]
    ) -> "AccessResult":
        """D (I-extract-001 #1327): record a successful RE-FETCH when a clean
        result is about to be returned for a URL that had >=1 prior block-page
        detection on this fetch. No-op when the detector is OFF or no block was
        seen. Returns `result` unchanged (pure telemetry, faithfulness-neutral)."""
        if block_page_detector_enabled() and block_state.get("seen"):
            total = _record_block_page_refetch()
            logger.info(
                "[ACCESS] block_page_detector: re-fetch recovered clean content "
                "via %s for %s (re_fetched=%d)",
                getattr(result, "access_method", "?"), result.url[:80], total,
            )
        return result

    def _detect_paywall(self, content: str) -> bool:
        """Detect if content is behind paywall OR an HTTP-error stub.

        M-23d: Extended to detect HTTP error stubs (403/404/5xx proxied
        through Jina Reader or similar). Jina returns success=True with
        a 200-500 char "403 Forbidden" / "Access Denied" page when the
        upstream server rejected its request. Without this detection,
        those stubs wait through all paywall patterns (which don't
        match "403 Forbidden" text) and get picked as fetch winners.

        M-23f: Paywall patterns are split into strict (fire on any
        length) and short-only (fire only on <2K char content). This
        prevents greedy-regex false positives like `sign.*in.*to.*
        access` matching "signed...had full access" in a 50K-char
        NEJM article body.
        """
        content_lower = content.lower()
        is_short = len(content) < 2000

        # Strict patterns: always apply
        for pattern in self.paywall_patterns_strict:
            if re.search(pattern, content_lower):
                return True

        # Loose patterns: only apply to short content
        if is_short:
            for pattern in self.paywall_patterns_short_only:
                if re.search(pattern, content_lower):
                    return True

        # SF-42: Short content with paywall indicators is likely paywalled
        # (removed dead `pass` code — either implement or remove)
        if len(content) < 2000 and any(
            re.search(p, content_lower) for p in [
                r"sign\s*in", r"log\s*in", r"create.*account",
            ]
        ):
            logger.info("[ACCESS] Short content (%d chars) with auth prompt — likely paywalled", len(content))
            return True

        # M-23d: HTTP error stubs. Short pages (<2K chars) containing
        # error status text are almost always failed fetches, not real
        # content. "403 Forbidden" / "404 Not Found" / "Error 5xx" /
        # "Access Denied" / "Target URL returned error" (Jina's phrasing).
        if len(content) < 2000:
            http_error_signals = [
                r"\b403\s+forbidden\b",
                r"\b404\s+not\s+found\b",
                r"\b5\d{2}\s+(internal\s+server\s+error|bad\s+gateway|service\s+unavailable|gateway\s+timeout)\b",
                r"access\s+denied",
                r"returned\s+error\s+\d{3}",
                r"target\s+url\s+returned\s+error",
                r"\bcloudflare\b.*\bblocked\b",
                r"\brate\s+limit(ed)?\b",
            ]
            for pattern in http_error_signals:
                if re.search(pattern, content_lower):
                    logger.info(
                        "[ACCESS] M-23d: Short content (%d chars) with "
                        "HTTP-error signal (%s) — treating as failed fetch",
                        len(content), pattern,
                    )
                    return True

        return False

    def _extract_pmcid(self, url: str) -> Optional[str]:
        """I-bug-775 (#815): extract a PMCID (e.g. 'PMC6490750') from a PMC URL
        — pmc.ncbi.nlm.nih.gov/articles/PMC<digits>/ or a PMC PDF URL."""
        if not url:
            return None
        m = re.search(r"/(PMC\d+)\b", url, re.IGNORECASE)
        return m.group(1).upper() if m else None

    async def _try_pmc_bioc_fulltext(self, pmcid: str) -> Optional[str]:
        """I-bug-775 (#815): fetch PMC Open-Access full text via the BioC API
        (Codex decision A). Returns normalized full text (>= the min-fulltext
        threshold, with body-like sections) or None. Conservative NCBI throttle
        (max 1 concurrent + ~3 req/s) with 429 exponential backoff. NEVER returns
        abstract-only / references-only / API-error text (see _parse_bioc_fulltext)."""
        global _ncbi_last_request_time
        import aiohttp

        bioc_url = (
            "https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/"
            f"BioC_json/{pmcid}/unicode"
        )
        raw: Optional[str] = None
        try:
            async with _get_ncbi_semaphore():
                elapsed = _time_module.monotonic() - _ncbi_last_request_time
                if _ncbi_last_request_time > 0 and elapsed < _NCBI_MIN_INTERVAL:
                    await asyncio.sleep(_NCBI_MIN_INTERVAL - elapsed)
                timeout = aiohttp.ClientTimeout(total=30)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    for attempt in range(3):
                        async with session.get(
                            bioc_url, headers=_NO_BROTLI_HEADERS
                        ) as resp:
                            _ncbi_last_request_time = _time_module.monotonic()
                            if resp.status == 429:
                                await asyncio.sleep(1.0 * (2 ** attempt))
                                continue
                            if resp.status != 200:
                                logger.info(
                                    "[ACCESS] PMC-BioC HTTP %d for %s",
                                    resp.status, pmcid,
                                )
                                return None
                            raw = await resp.text()
                            break
        except asyncio.TimeoutError:
            logger.info("[ACCESS] PMC-BioC timeout for %s", pmcid)
            return None
        except Exception as e:
            logger.warning(
                "[ACCESS] PMC-BioC failed for %s: %s", pmcid, str(e)[:120]
            )
            return None

        if not raw:
            return None
        text = _parse_bioc_fulltext(raw)
        if not text or len(text) < _PMC_BIOC_MIN_FULLTEXT_CHARS:
            logger.info(
                "[ACCESS] PMC-BioC %s: no body-like full text (len=%d) — falling through",
                pmcid, len(text or ""),
            )
            return None
        logger.info(
            "[ACCESS] PMC-BioC full text for %s (%d chars)", pmcid, len(text)
        )
        return text

    def _extract_doi(self, url: str) -> Optional[str]:
        """Extract DOI from URL."""
        # DOI patterns
        patterns = [
            r'10\.\d{4,9}/[-._;()/:A-Z0-9]+',
            r'doi\.org/(10\.\d{4,9}/[-._;()/:A-Z0-9]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                return match.group(1) if len(match.groups()) > 0 else match.group(0)

        return None

    def _is_academic_url(self, url: str) -> bool:
        """Check if URL is likely academic."""
        academic_domains = [
            "springer", "wiley", "elsevier", "sciencedirect",
            "nature", "science", "jstor", "ieee", "acm",
            "arxiv", "pubmed", "ncbi", "nih.gov",
            "semanticscholar.org",
        ]

        url_lower = url.lower()
        return any(domain in url_lower for domain in academic_domains) or bool(self._extract_doi(url))

    def get_access_stats(self) -> Dict[str, Any]:
        """Get statistics about access methods used."""
        return {
            "archive_org_enabled": self.use_archive_org,
            "proxy_configured": bool(self.proxy),
            "respect_robots_txt": self.respect_robots,
            "crawl4ai_enabled": os.getenv("PG_CRAWL4AI_ENABLED", "1") == "1",
            "jina_reader_enabled": True,
            "firecrawl_enabled": bool(os.getenv("FIRECRAWL_API_KEY")),
        }
