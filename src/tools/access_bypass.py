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


def _is_interstitial_shell_span(text: str) -> bool:
    """U20 (I-deepfix-001): LAW V delegation to the canonical shell detector
    (``shell_detector.is_cited_span_shell``) for CAPTCHA / cookie-consent /
    bot-challenge interstitial spans that the length-gated ``is_error_shell_text``
    misses.

    ``is_error_shell_text`` only fires on a SHORT (<=400-char) body with a WAF
    co-token / signature-dominance, so an enrichment-concatenated CAPTCHA span or a
    cookie-consent banner slips through it (verified on drb_75: the junk screen
    dropped only YouTube hosts, so captcha/cookie spans inflated breadth
    ~730 -> 893). ``is_cited_span_shell`` is the Codex-hardened single source of
    truth: any-length CAPTCHA/challenge co-occurrence signatures + short-body
    cookie/consent/citation-UI chrome, with the ambiguous-phrase corroboration and
    short-body ceilings that keep a real clinical body (even a long one carrying an
    incidental cookie footer) from being false-dropped.

    Reusing a pure detector is faithfulness-NEUTRAL: strict_verify / NLI / 4-role /
    span-grounding are untouched (this is a SOURCE-hygiene predicate, not a verify
    verdict). Lazy import + fail-OPEN (an import/detector fault KEEPS the source —
    §-1.3: never over-drop). Pure, no network.
    """
    if not text:
        return False
    try:
        from src.polaris_graph.retrieval.shell_detector import (  # noqa: PLC0415
            is_cited_span_shell,
        )
    except Exception:  # noqa: BLE001 — fail-open: an import fault must never drop a real source
        return False
    try:
        return bool(is_cited_span_shell(text))
    except Exception:  # noqa: BLE001 — fail-open on any detector fault
        return False


def is_junk_source(url: str = "", text: str = "") -> bool:
    """True iff a source is a non-citable JUNK page (host OR error-shell body).

    Faithfulness-NEUTRAL SOURCE screen (§-1.3): drops ONLY confirmed junk
    (homework-help/Q&A host, a fetch-error shell body, or a CAPTCHA / cookie-consent
    / bot-challenge interstitial span), never a real journal/repository/gov/news
    source. Each signal is high-precision. Never a verify verdict — applied at
    corpus consumption so junk never enters the basket / bibliography /
    corroboration / citation.

    U20 (I-deepfix-001): the third signal (``_is_interstitial_shell_span``) closes
    the gap where the length-gated ``is_error_shell_text`` missed captcha/cookie
    spans — only YouTube hosts were being dropped before.
    """
    return (
        is_junk_source_host(url)
        or is_error_shell_text(text)
        or _is_interstitial_shell_span(text)
    )


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
    # Cookie-error interstitial: the publisher's "you must enable cookies" wall
    # (e.g. "Error - Cookies Turned Off"). Two single-phrase rules = OR semantics
    # (all-phrases-in-a-tuple is AND). High-precision full phrases; gated to a
    # short visible body so a real article that merely mentions cookies never
    # trips it.
    ("cookie_error", ("cookies turned off",)),
    ("cookie_error", ("error - cookies",)),
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


def detect_content_integrity_junk(
    fetched_body: str, url: str, title: str
) -> tuple[bool, str]:
    """Content-integrity junk screen: is this fetched row a CHROME NON-SOURCE?

    Returns ``(True, <class>)`` iff the row is chrome (a failed fetch / non-article
    stub that is NOT a real source), else ``(False, "")``. This is a pure LEAF
    detector — it never fetches, never touches the faithfulness engine, and judges
    ONLY from the supplied ``title`` and ``fetched_body``.

    Classes, evaluated in order:
      * ``block_page``       — body is a challenge / WAF block / redirect / error
                               stub per :func:`is_block_page_or_stub`.
      * ``empty``            — title is empty / whitespace-only.
      * ``not_found``        — title contains "404" / "not found" /
                               "ressource not found".
      * ``cookie_error``     — title contains "cookies turned off" /
                               "error - cookies".
      * ``login_wall``       — title starts with "login |" or equals "login".
      * ``nonarticle_stub``  — title equals a known non-article stub label
                               ("fulltext01", "download_pub", "conference program",
                               "book of abstracts").

    FAIL-OPEN: any internal error returns ``(False, "")`` — a bug in the screen
    must never flag a real source as junk (§-1.3 weight-not-filter: never a
    false hard-drop).
    """
    try:
        if is_block_page_or_stub(fetched_body, url):
            return (True, "block_page")
        # ZYTE-RECOVERY GUARD (GH I-deepfix-003 #1374): the A15 AccessBypass+Zyte re-fetch
        # runs BEFORE this stamp. If Zyte recovered REAL content the body is substantial —
        # KEEP the source even when its TITLE is a stale bot/error page (a real journal whose
        # first fetch hit "Are you a robot?" but whose body was then Zyte-recovered). NEVER
        # throw away a Zyte-recovered source for a stale title. Only a thin / empty body —
        # i.e. Zyte genuinely could NOT recover it — proceeds to the title screens below.
        if len((fetched_body or "").strip()) >= 200:
            return (False, "")
        normalized_title = (title or "").strip().lower()
        if not normalized_title:
            return (True, "empty")
        if (
            "404" in normalized_title
            or "not found" in normalized_title
            or "ressource not found" in normalized_title
        ):
            return (True, "not_found")
        if (
            "cookies turned off" in normalized_title
            or "error - cookies" in normalized_title
        ):
            return (True, "cookie_error")
        # GH I-deepfix-003 (#1374): anti-bot / captcha challenge pages (Cloudflare
        # "Just a moment...", "Are you a robot?", PerimeterX, "Attention Required") whose
        # BODY was stripped/short enough to slip is_block_page_or_stub still carry a
        # tell-tale challenge TITLE. A challenge page is a failed fetch, not a source.
        if (
            "are you a robot" in normalized_title
            or "just a moment" in normalized_title
            or "attention required" in normalized_title
            or "verify you are human" in normalized_title
            or "verifying you are human" in normalized_title
            or "checking your browser" in normalized_title
            or "checking if the site connection is secure" in normalized_title
            or "access denied" in normalized_title
            or "security check" in normalized_title
            or "one more step" in normalized_title
            or normalized_title == "captcha"
        ):
            return (True, "bot_challenge")
        if normalized_title.startswith("login |") or normalized_title == "login":
            return (True, "login_wall")
        if normalized_title in (
            "fulltext01",
            "download_pub",
            "conference program",
            "book of abstracts",
        ):
            return (True, "nonarticle_stub")
        return (False, "")
    except Exception:
        return (False, "")


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


# ─────────────────────────────────────────────────────────────────────────────
# I-fetch-005 (fetch-speed, #1344) FIX 2 — per-URL TERMINAL-block negative cache.
#
# A hard WAF access-denied (block class ``akamai_access_denied``: "Access Denied /
# you don't have permission to access", ``errors.edgesuite.net``) is DETERMINISTIC
# per URL — the same URL hard-blocks again no matter which backend tries it. Re-walking
# the full AccessBypass cascade (crawl4ai/jina/firecrawl/direct/archive/proxy/zyte,
# ~60s+ of stacked timeouts) on a LATER request for the SAME url is pure wasted
# wall-clock. On the FIRST terminal-class detection the url is cached; a subsequent
# ``fetch_with_bypass`` for that url short-circuits with NO network call.
#
# §-1.3-SAFE (weight-not-filter): this is a PERFORMANCE de-dup, NOT a faithfulness gate.
# The source is NOT dropped — a url that ultimately cannot be fetched is RETAINED
# downstream at ZERO weight (an unfetched source), exactly like any other fetch-miss.
# ONLY the hardest, deterministically-terminal class is cached (a challenge/JS wall is
# NOT terminal — a browser-rendering backend can still pass it). Populated ONLY when the
# block-page detector is ON (its sole populator => OFF path byte-identical) and gated by
# its own default-ON kill-switch.
# ─────────────────────────────────────────────────────────────────────────────
_TERMINAL_BLOCK_CLASSES = frozenset({"akamai_access_denied"})
_terminal_block_urls: "set[str]" = set()
_terminal_block_lock = threading.Lock()
_ENV_TERMINAL_BLOCK_FASTSKIP = "PG_TERMINAL_BLOCK_FASTSKIP"


def terminal_block_fastskip_enabled() -> bool:
    """FIX 2 kill-switch (default-ON). Only ever active when the block-page detector is ALSO
    ON (the detector is the sole populator); OFF here reverts to re-walking the cascade for a
    terminally-blocked url (byte-identical to the pre-fix behavior)."""
    return os.getenv(_ENV_TERMINAL_BLOCK_FASTSKIP, "1").strip().lower() in (
        "1", "true", "yes", "on", "enabled",
    )


def _record_terminal_block(url: str) -> None:
    """FIX 2: cache ``url`` as terminally blocked (hard WAF access-denied). Thread-safe."""
    if not url:
        return
    with _terminal_block_lock:
        _terminal_block_urls.add(url)


def is_terminal_blocked(url: str) -> bool:
    """FIX 2: True iff ``url`` previously hit a TERMINAL hard-block class. Thread-safe."""
    if not url:
        return False
    with _terminal_block_lock:
        return url in _terminal_block_urls


def _discard_terminal_block(url: str) -> None:
    """I-fetch-005 iter-2 (Fable): drop ``url`` from the terminal-block cache on a CLEAN fetch
    success. ``_is_block_page`` can flag a url TERMINAL mid-cascade (e.g. the direct hop hit
    ``akamai_access_denied`` and populated the cache) and THEN a LATER hop in the SAME cascade
    (archive.org / institutional proxy / Zyte) fetches it cleanly — which makes the cached
    terminal entry STALE: a later ``fetch_with_bypass`` for this provably-fetchable url would
    otherwise fast-skip straight to failure. Discarding the url on any clean success keeps the
    fast-skip firing ONLY for a url that has NEVER been fetched cleanly. §-1.3-safe (it can only
    RESTORE a fetch path, never suppress one); thread-safe; idempotent (no-op if not present)."""
    if not url:
        return
    with _terminal_block_lock:
        _terminal_block_urls.discard(url)


def reset_terminal_block_cache() -> None:
    """FIX 2: clear the per-URL terminal-block cache at the START of each run (mirrors
    ``live_retriever.reset_refetch_cache``) so a blocked url from a prior run/vector does not
    leak across runs in a long-lived process. Cheap, no network."""
    with _terminal_block_lock:
        _terminal_block_urls.clear()


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
# to the ``vlm-http-client`` backend: each PDF is parsed by a separate ``mineru``
# CLI child process (its own venv, its own pypdfium2 state) talking to the
# resident ``mineru-vllm-server`` (which owns request batching via --max-num-seqs)
# — the child-process boundary already serializes/isolates the per-PDF state, so
# no in-process mutex is needed. Only the legacy in-process GPU path needs it.
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
    default (the breaker is an operational knob, not a correctness gate).

    I-deepfix-001 B2 (wave-2, 2026-07-08) — GENTLER BREAKER. The binding knob
    ``PG_MINERU25_BREAKER_THRESHOLD`` takes precedence when set, so the operator can
    raise the trip count and one slow big-PDF batch no longer blacks out mineru for
    the small PDFs it would extract cleanly. UNSET => falls through to the legacy
    ``PG_MINERU25_CIRCUIT_THRESHOLD`` then the 3-fail default => BYTE-IDENTICAL."""
    raw = os.getenv("PG_MINERU25_BREAKER_THRESHOLD", "").strip()
    if not raw:
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
    retry if it recovers.

    I-deepfix-001 B2 (wave-2) — GENTLER BREAKER. ``PG_MINERU25_BREAKER_COOLDOWN_S``
    takes precedence when set (a shorter cooldown restores mineru for small PDFs
    sooner). UNSET => falls through to the legacy ``PG_MINERU25_CIRCUIT_COOLDOWN``
    then the 300s default => BYTE-IDENTICAL."""
    raw = os.getenv("PG_MINERU25_BREAKER_COOLDOWN_S", "").strip()
    if not raw:
        raw = os.getenv("PG_MINERU25_CIRCUIT_COOLDOWN", "").strip()
    if not raw:
        return _MINERU25_CIRCUIT_COOLDOWN_DEFAULT
    try:
        value = float(raw)
    except ValueError:
        return _MINERU25_CIRCUIT_COOLDOWN_DEFAULT
    return value if value > 0 else _MINERU25_CIRCUIT_COOLDOWN_DEFAULT


# I-deepfix-001 B2 (wave-2, 2026-07-08) — PAGE-SCALED mineru timeout.
# A flat page-agnostic wall makes a 4-page article and a 458-page report share the
# same budget: the big report times out, the breaker trips, and mineru is blacked
# out for the small PDFs it would extract cleanly. The page-scaled timeout keeps the
# small floor while giving genuinely large PDFs proportional time within a bound.
_MINERU25_TIMEOUT_MAX_DEFAULT = 900.0


def _mineru25_pdf_page_count(pdf_bytes: bytes) -> int:
    """Best-effort PDF page count (fail-open ``0`` on any error). Used ONLY by the
    B2 page-scaled timeout when ``PG_MINERU25_TIMEOUT_PER_PAGE_S`` is set; a ``0``
    return makes the scaler fall back to the flat floor (byte-identical)."""
    try:
        import fitz as _fitz  # PyMuPDF — already a dependency of the extract path
        _doc = _fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            return int(_doc.page_count)
        finally:
            _doc.close()
    except Exception:  # noqa: BLE001 — probe is best-effort; never break extraction
        return 0


def _mineru25_timeout_seconds(pdf_bytes: bytes, floor: float) -> float:
    """I-deepfix-001 B2 (wave-2) — page-SCALED per-PDF mineru timeout.

    ``PG_MINERU25_TIMEOUT_PER_PAGE_S`` UNSET or ``<= 0`` => return ``floor`` unchanged
    (the flat legacy behaviour => BYTE-IDENTICAL). When set, the effective timeout is
    ``max(floor, page_count * per_page_s)`` bounded above by
    ``PG_MINERU25_TIMEOUT_MAX_S`` (default 900s) so a mangled page count can never
    produce an unbounded wall. ``floor`` stays the small-PDF minimum; a failed page
    probe (page_count == 0) falls back to ``floor`` (fail-open, no scaling).

    This is a per-PDF timeout MECHANISM, not a blind time-wall raise: small PDFs keep
    the fast floor; only genuinely large PDFs get proportional time within the bound.
    Faithfulness-neutral (only HOW long the extractor may run changes)."""
    raw = os.getenv("PG_MINERU25_TIMEOUT_PER_PAGE_S", "").strip()
    if not raw:
        return floor
    try:
        per_page = float(raw)
    except ValueError:
        return floor
    if per_page <= 0:
        return floor
    pages = _mineru25_pdf_page_count(pdf_bytes)
    if pages <= 0:
        return floor
    try:
        ceiling = float(
            os.getenv("PG_MINERU25_TIMEOUT_MAX_S", "").strip()
            or _MINERU25_TIMEOUT_MAX_DEFAULT
        )
    except ValueError:
        ceiling = _MINERU25_TIMEOUT_MAX_DEFAULT
    if ceiling <= 0:
        ceiling = _MINERU25_TIMEOUT_MAX_DEFAULT
    effective = max(floor, pages * per_page)
    return min(effective, ceiling)


# ---------------------------------------------------------------------------
# I-deepfix-001 U8 (#1344): MINERU-FIRES LIVE-CANARY (fail-loud DISCLOSE).
#
# The W4 clinical-PDF winner is mineru25 (GPU VLM). ``_maybe_mineru25_extract``
# already records, per PDF, a ground-truth ``pdf_extract`` tool-trace row — a WIN
# (``selected_extractor == "mineru25"``; logged "[ACCESS] W4: mineru25 (GPU VLM)
# extracted N chars") or a DEGRADE (``requested_extractor == "mineru25"`` +
# ``fallback_reason``; logged "[W4-CANARY] clinical_pdf_winner_degraded=true ...").
# ``tool_tracer.clinical_pdf_winner_status()`` aggregates those rows into
# ``{requested, degraded, fallback_count, win_count, reasons, selected_extractors}``
# and stamps it on ``manifest['clinical_pdf_winner_degraded']`` on EVERY manifest
# path. That data is present but PASSIVE — nothing surfaces the specific "requested
# but NEVER won" case LOUDLY. The belt check below turns that raw telemetry into a
# clear disclosed flag + warning string: when mineru25 was REQUESTED yet produced
# ZERO real GPU-VLM extractions (win_count == 0) while >=1 clinical PDF degraded to
# a CPU fallback, the winner is DARK — a silent degrade. Disclose it, do not hard-
# abort (the docling/PyMuPDF text still grounds strict_verify). A run that never
# requested mineru25 (docling baseline) is ``requested`` False => silent_degrade
# False (a legit baseline, NOT a degrade). Pure telemetry read — touches no
# faithfulness gate and drops no source.
# ---------------------------------------------------------------------------

def mineru_fire_canary_enabled() -> bool:
    """PG_MINERU_FIRE_CANARY kill-switch (default ON). OFF => the U8 mineru-fires belt check
    is not surfaced (the raw ``clinical_pdf_winner_degraded`` telemetry is unaffected). Read at
    CALL time (LAW VI) so a slate/operator override after import wins."""
    return os.getenv("PG_MINERU_FIRE_CANARY", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def mineru_silent_degrade_disclosure(
    winner_status: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Belt check on the W4 mineru25 clinical-PDF winner telemetry.

    ``winner_status`` is the dict produced by ``tool_tracer.clinical_pdf_winner_status()`` (the
    SAME source stamped on ``manifest['clinical_pdf_winner_degraded']``). Returns a disclosure
    dict; ``silent_degrade`` is True iff mineru25 was REQUESTED (``requested``) yet recorded ZERO
    genuine GPU-VLM extractions (``win_count == 0``) while >=1 clinical PDF degraded to a CPU
    fallback (``degraded``). Pure: no I/O, no mutation of the input.

    Shape::

        {"mineru_expected": bool, "gpu_vlm_extractions": int, "clinical_pdf_degrades": int,
         "silent_degrade": bool, "disclosure": str | None}
    """
    ws = dict(winner_status or {})
    requested = bool(ws.get("requested"))
    try:
        win_count = int(ws.get("win_count") or 0)
    except (TypeError, ValueError):
        win_count = 0
    try:
        fallback_count = int(ws.get("fallback_count") or 0)
    except (TypeError, ValueError):
        fallback_count = 0
    degraded = bool(ws.get("degraded"))
    silent_degrade = requested and win_count == 0 and degraded
    disclosure = None
    if silent_degrade:
        selected = ws.get("selected_extractors") or []
        selected_str = ", ".join(str(s) for s in selected) if selected else "docling"
        disclosure = (
            "clinical_pdf_extractor_all_degraded: mineru25 (W4 GPU-VLM clinical-PDF winner) was "
            f"REQUESTED but produced ZERO real GPU-VLM extractions; all {fallback_count} clinical "
            f"PDF(s) degraded to a CPU fallback ({selected_str}). The winner is DARK — degrade is "
            f"DISCLOSED, not silent (reasons: {ws.get('reasons') or {}})."
        )
    return {
        "mineru_expected": requested,
        "gpu_vlm_extractions": win_count,
        "clinical_pdf_degrades": fallback_count,
        "silent_degrade": silent_degrade,
        "disclosure": disclosure,
    }


# ---------------------------------------------------------------------------
# I-deepfix-001 U8 (#1344): mineru25 vlm-http-client "Semaphore bound to a
# different event loop" -> circuit trip -> silent degrade to Docling.
#
# The third-party ``mineru_vl_utils`` HttpVlmClient caches ONE process-wide
# async client whose ``asyncio.Semaphore(1)`` binds to the FIRST event loop it
# runs under. Our ``_mineru25_extract`` runs on a fetch-worker thread via
# ``run_in_executor`` (NO running loop), so MinerU falls back to
# ``asyncio.run()`` — a FRESH loop — for EVERY extraction. The 2nd call then
# trips ``<Semaphore ...> is bound to a different event loop`` (observed live:
# drb_78 `Semaphore object ... is bound to a different event loop`), which the
# W4 circuit counts as a genuine failure and, after 3, OPENS the breaker so
# every clinical PDF degrades to Docling — AND removes the U1 rasterization
# throttle behind it. Same failure class as the crawl4ai loop-keyed cache
# (#1227).
#
# FIX: before each ``do_parse`` on the vlm-http-client path, swap the cached
# client's loop-bound ``asyncio.Semaphore(1)`` for a fresh one and clear its
# per-loop client cache, so every extraction sees clean, unbound loop state.
#
# §-1.3 / faithfulness: this touches only the EXTRACTOR's async-plumbing state
# inside a THIRD-PARTY client — it changes NOTHING about which PDFs are
# extracted, the verbatim text, or any faithfulness gate (strict_verify / NLI /
# 4-role / provenance are all downstream and untouched). It only stops a
# spurious degrade so the disclosed W4 winner keeps winning.
#
# Fully defensive: absent package / unexpected object shape => quiet no-op (the
# caller's Docling fallback still runs); a genuinely unexpected AttributeError
# on a present attribute is surfaced LOUDLY (W4-CANARY) but NEVER raised.
# ---------------------------------------------------------------------------
def _reset_loop_bound_client(holder: object) -> bool:
    """PL: reset one HttpVlmClient-shaped object's loop-bound async state.

    Given ``holder`` that may carry ``_aio_client_sem`` (an ``asyncio.Semaphore``
    bound to a stale event loop) and/or ``_aio_client_cache`` (a per-loop client
    cache), swap the semaphore for a fresh ``asyncio.Semaphore(1)`` and clear the
    cache. Returns ``True`` iff at least one field was reset.

    Pure + fully guarded: every attribute read/write is behind ``hasattr`` and a
    try/except so an unexpected object shape is a no-op, never a crash. An
    unexpected ``AttributeError`` on an attribute that ``hasattr`` reported
    present (e.g. a read-only property / ``__slots__`` without setter) is logged
    LOUDLY and swallowed."""
    if holder is None:
        return False
    reset = False
    if hasattr(holder, "_aio_client_sem"):
        try:
            setattr(holder, "_aio_client_sem", asyncio.Semaphore(1))
            reset = True
        except AttributeError as exc:  # noqa: PERF203 — loud, not fatal
            logger.warning(
                "[ACCESS] W4-CANARY: mineru25 vlm-http-client _aio_client_sem "
                "present but not settable (%s) — cannot reset loop-bound "
                "semaphore; U8 degrade may persist.", str(exc)[:120],
            )
    if hasattr(holder, "_aio_client_cache"):
        try:
            cache = getattr(holder, "_aio_client_cache")
            if isinstance(cache, dict):
                cache.clear()
            else:
                setattr(holder, "_aio_client_cache", None)
            reset = True
        except AttributeError as exc:  # noqa: PERF203 — loud, not fatal
            logger.warning(
                "[ACCESS] W4-CANARY: mineru25 vlm-http-client _aio_client_cache "
                "present but not resettable (%s) — cannot clear per-loop client "
                "cache; U8 degrade may persist.", str(exc)[:120],
            )
    return reset


def _reset_mineru_http_client_loop_state() -> None:
    """PL: clear the mineru_vl_utils HttpVlmClient's stale-loop async state.

    Walks the MinerU VLM ``ModelSingleton`` model cache and, for each cached
    predictor, resets the loop-bound async state on its ``.client`` (or the
    predictor itself). Call ONLY on the vlm-http-client path, immediately before
    ``do_parse``.

    Absent package / internal layout drift => quiet no-op: there is simply
    nothing to reset and the caller's disclosed Docling fallback still runs. This
    is intentional (not a silent capability downgrade): the reset is a
    best-effort de-wedging of a third-party client whose shape we do not own."""
    try:
        from mineru.backend.vlm.vlm_analyze import ModelSingleton  # type: ignore
    except Exception:  # noqa: BLE001 — package absent / layout drift => nothing to reset
        return
    try:
        singleton = ModelSingleton()  # singleton __new__ returns the shared instance
    except Exception:  # noqa: BLE001 — cannot obtain singleton => nothing to reset
        return
    models = getattr(singleton, "_models", None)
    if not isinstance(models, dict):
        return
    for predictor in list(models.values()):
        # The HttpVlmClient carrying the loop-bound semaphore may hang off
        # ``predictor.client`` OR be the predictor object itself. Try the client
        # first; stop at the first holder that actually reset something.
        for holder in (getattr(predictor, "client", None), predictor):
            if _reset_loop_bound_client(holder):
                break


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
# I-fetch-005 (fetch-speed, #1344) FIX 1: HALF-OPEN recovery state. When the breaker is OPEN
# and the cooldown has elapsed, EXACTLY ONE caller becomes the single-flight PROBE
# (`_crawl4ai_half_open_probe_active`); every other caller keeps using the fallback chain. A
# probe that survives the browser region CLOSES the breaker; a probe that fails RE-opens it
# with EXPONENTIAL backoff keyed by `_crawl4ai_open_generation` (capped). This stops a
# TRANSIENT browser hiccup from disabling crawl4ai for the WHOLE run, and stops the
# post-cooldown SWARM of concurrent failures from re-inflating the failure counter (the
# observed "circuit breaker OPENED after 16 consecutive failures" latch).
_crawl4ai_half_open_probe_active: bool = False
_crawl4ai_open_generation: int = 0
# Guards EVERY read/write of the breaker state above. Fetches run on separate worker threads
# (each with its own event loop), so the single-flight probe REQUIRES an atomic check-and-set.
_crawl4ai_breaker_lock = threading.Lock()
# I-fetch-002 (#1168): raise 3->6 so a couple of TRANSIENT subprocess crashes (EPIPE under concurrent
# load) do not trip the breaker and disable crawl4ai for the whole run. Pairs with the new concurrency
# semaphore below — fewer concurrent browsers means fewer crashes in the first place.
_CRAWL4AI_CIRCUIT_BREAKER_THRESHOLD = int(
    os.getenv("PG_CRAWL4AI_CIRCUIT_BREAKER_THRESHOLD", "6")
)
# I-fetch-005 (fetch-speed, #1344) FIX 1: the BASE cooldown default is SHORTENED 120->60 so a
# TRANSIENT browser hiccup recovers within ~60s via the half-open probe (was: crawl4ai dead for
# the whole ~48min run). A GENUINELY-dead browser (e.g. missing OS libs — the confirmed Box B
# root cause) does NOT hot-loop: the exponential backoff grows the cooldown 60->120->240...->MAX
# on each failed probe, so at most ONE cheap browser-launch attempt is paid per (growing)
# cooldown, and the fallback chain (jina/trafilatura/Zyte) is the honestly-disclosed fetch path.
# All env-overridable (LAW VI); BACKOFF<=1.0 => constant BASE cooldown (legacy shape).
_CRAWL4AI_CIRCUIT_BREAKER_COOLDOWN = float(
    os.getenv("PG_CRAWL4AI_CIRCUIT_BREAKER_COOLDOWN", "60.0")
)
_CRAWL4AI_CIRCUIT_BREAKER_BACKOFF = float(
    os.getenv("PG_CRAWL4AI_CIRCUIT_BREAKER_BACKOFF", "2.0")
)
_CRAWL4AI_CIRCUIT_BREAKER_MAX_COOLDOWN = float(
    os.getenv("PG_CRAWL4AI_CIRCUIT_BREAKER_MAX_COOLDOWN", "600.0")
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
# browser subprocess). Env-overridable. Aligned to (not below) the live_retriever
# parallel `max_workers` ceiling (48) so the 48 fetch workers no longer funnel
# through a narrower 16-slot in-flight bound where wedged mineru-PDF workers hold
# their slot past the abandon-join and drain the pool (UNIT 6 WAVE-B fetch
# robustness). Named constant (LAW VI — no magic numbers).
_BYPASS_INFLIGHT_DEFAULT_LIMIT = 32
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

# I-deepfix-001 wave-2 4IR (#1344): Cookiebot / Usercentrics consent-manager
# chrome taxonomy. A CMP (consent-management platform) renders each control on
# its OWN line, so these strings leak into the fetched body as whole lines that
# the existing cookie patterns (2051-2055) do not cover. Applied inside
# ``strip_web_boilerplate`` gated DEFAULT-ON by ``PG_FETCH_COOKIE_CHROME_STRIP``
# — flag OFF ("0") is byte-identical to the pre-fix behaviour (this regex is
# simply never applied). EVERY pattern is WHOLE-LINE + MULTI-TOKEN anchored:
# NONE matches a bare single word, and the category-tab row requires >=2 of the
# four category words IN CANONICAL ORDER (the leading lookahead guarantees a
# second whitespace-separated token on the line), so a real sentence that merely
# CONTAINS "Marketing" / "Statistics" / "Necessary" — or STARTS with one before
# prose — survives byte-for-byte (the §-1.3 no-real-claim-dropped invariant).
# Input hygiene only; strict_verify / NLI / 4-role / span-grounding untouched.
_COOKIE_CONSENT_CHROME_RE = re.compile(
    r"|".join([
        r"^[ \t]*Consent Selection[ \t]*$",                                  # Cookiebot dialog header
        # Category-tab strip: an ORDERED subset of the four Cookiebot categories,
        # whole-line, >=2 tokens REQUIRED. The leading lookahead demands a second
        # whitespace-separated token, so a bare "Marketing"/"Statistics" line — or
        # a real sentence that only begins with a category word — is NEVER matched.
        r"^(?=[ \t]*\S+[ \t]+\S)[ \t]*(?:Necessary\b[ \t]*)?(?:Preferences\b[ \t]*)?(?:Statistics\b[ \t]*)?(?:Marketing\b[ \t]*)?$",
        r"^[ \t]*(?:Show/Hide|Show|Hide)[ \t]+details[ \t]*$",               # "Show details" / "Show/Hide details" toggle
        r"^[ \t]*(?:Powered by Cookiebot(?:[ \t]+by[ \t]+Usercentrics)?|Cookiebot by Usercentrics)[ \t]*$",  # CMP attribution line
        r"^[ \t]*About cookies[ \t]*$",                                      # Cookiebot "About cookies" link/header
        # Button trio: a WHOLE line that is >=2 of the Allow all / Allow selection
        # / Deny / Customize buttons. The {2,} means a bare single "Deny" /
        # "Customize" line — or those words inside real prose — is NEVER matched.
        r"^[ \t]*(?:(?:Allow all|Allow selection|Deny|Customize)\b[ \t]*){2,}$",
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
    # I-deepfix-001 wave-2 4IR (#1344): additionally strip the Cookiebot /
    # Usercentrics consent-manager chrome taxonomy. Gated DEFAULT-ON by
    # PG_FETCH_COOKIE_CHROME_STRIP; flag OFF ("0") is byte-identical to the
    # pre-fix behaviour (the cookie regex is simply not applied). Whole-line +
    # multi-token anchored, so real prose is preserved byte-for-byte.
    if os.getenv("PG_FETCH_COOKIE_CHROME_STRIP", "1") != "0":
        cleaned = _COOKIE_CONSENT_CHROME_RE.sub("", cleaned)
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


# ─────────────────────────────────────────────────────────────────────────────
# I-fetchclean-001 B1 (2026-07-10) — markdown nav / boilerplate line filter.
#
# Jina Reader / crawl4ai return FULL-PAGE markdown: nav menus, gov banners, skip-
# nav links, reading-time widgets, Cookiebot/Scopus chrome all welded into the real
# article. The existing ``clean_fetch_body`` allowlist is literal-pattern whack-a-mole;
# there is NO generic main-content pass on the markdown, so every new site's nav leaks.
# This ports the jusText / boilerpipe CORE HEURISTIC (link-density + prose-density block
# classification) to markdown LINES — the data shape the HTML-DOM extractors (trafilatura
# et al) cannot ingest — plus a few structure-anchored standalone-chrome patterns the
# density test cannot see. Pure / deterministic / zero new deps.
#
# GUARDS (byte-preserve real content — §-1.3 never drop a real claim / reference):
#   * REFERENCE MODE: a "References"/"Bibliography"/... heading opens keep-all mode until
#     the next same-or-higher-level heading (the ev_037 bipartisanpolicy guard case).
#   * reference-like line (DOI / et al / year / pp. / vol(issue) / arxiv|pmid|isbn /
#     "retrieved from"|accessed) is KEPT even outside reference mode.
#   * prose-like line (>=60% chars outside link markup AND ends with sentence punctuation)
#     is KEPT — a real sentence with incidental inline links survives.
# INPUT HYGIENE ONLY: strict_verify / NLI / 4-role / span-grounding untouched.
# ─────────────────────────────────────────────────────────────────────────────

# A markdown inline link ``[text](url)`` — the exact span the density heuristic measures.
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\([^)]*\)")

# A markdown ATX heading ``#..###### Title`` (space required, standard form).
_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+\S.*$")

# A reference-section heading (``\s*`` per design, so ``#References`` also opens the mode).
_MD_REFERENCE_HEADING_RE = re.compile(
    r"^(#{1,6})\s*(?:references|bibliography|works cited|notes|endnotes|sources|"
    r"citations|further reading)\b",
    re.IGNORECASE,
)

# Per-line citation signals — ANY one makes the line reference-like (KEEP). A nav menu
# carries none of these; a citation line with URLs carries at least one.
_CITATION_SIGNAL_RES: tuple[re.Pattern, ...] = (
    re.compile(r"10\.\d{4,9}/"),                       # DOI
    re.compile(r"\bet al\b", re.IGNORECASE),           # author-list marker
    re.compile(r"\b(?:19|20)\d{2}\b"),                 # 4-digit year
    re.compile(r"\bpp?\.\s*\d"),                        # p. / pp. page
    re.compile(r"\d+\s*\(\d+\)"),                       # volume(issue)
    re.compile(r"\b(?:arxiv|pmid|isbn)\b", re.IGNORECASE),
    re.compile(r"\b(?:retrieved from|accessed)\b", re.IGNORECASE),
)

# Line ends with sentence punctuation (allowing trailing quote/paren/bracket).
_SENTENCE_END_RE = re.compile(r"[.!?…][\"')\]]*\s*$")

# STRUCTURE-ANCHORED standalone chrome — a WHOLE line that IS one of these is dropped
# (single-link / no-link chrome the density test cannot see).
_STANDALONE_CHROME_LINE_RE = re.compile(
    r"^\s*(?:"
    r"An official website of the United States government"
    r"|Here'?s how you know"
    r"|Official websites use \.gov"
    r"|Secure \.gov websites use HTTPS"
    r"|\d+\s*(?:Minute Read Time|min(?:ute)? read)"
    r"|\[?Skip to (?:main )?content\]?(?:\([^)]*\))?"
    r"|#main-?content"
    r")\s*$",
    re.IGNORECASE,
)

# INLINE token-only removals (surrounding prose preserved).
# Skip-nav link used as a line PREFIX before real content.
_SKIP_NAV_LINK_RE = re.compile(r"\[Skip to (?:main )?content\]\([^)]*\)", re.IGNORECASE)
# Scopus citation-count chrome (ev_1048 wustl) — token-only, prose preserved.
_SCOPUS_CHROME_RE = re.compile(
    r"\[\d+\s*Link opens in a new tab\]\(https?://www\.scopus\.com[^)]*\)"
    r"(?:\s*Scopus citations)?",
    re.IGNORECASE,
)
# Cookiebot marker on the line gates removal of the empty cookiebot link + the adjacent
# Consent/Details/About consent-link run (the ev_954 ACM strip). The Consent/Details/About
# links are removed ONLY on a confirmed-cookiebot line so a real footer "About" link elsewhere
# is never touched.
_COOKIEBOT_MARKER_RE = re.compile(r"cookiebot\.com", re.IGNORECASE)
_COOKIEBOT_CHROME_RE = re.compile(
    r"\[\]\(https?://www\.cookiebot\.com[^)]*\)"
    r"|\[(?:Consent|Details|About)\]\([^)]*\)",
    re.IGNORECASE,
)

# ─────────────────────────────────────────────────────────────────────────────
# I-fetchclean-001 round-1 (2026-07-10) — remaining welded-chrome leaks. Jina/crawl4ai
# weld a whole page region onto ONE line, so the per-line rules above miss chrome that a
# real heading / a year / a trailing period elsewhere in the mega-line shields. All of the
# additions below stay INSIDE ``strip_markdown_nav_chrome`` and its helpers, so the existing
# ``PG_FETCH_MD_NAV_STRIP`` default-ON gate ("0" ⇒ never applied ⇒ byte-identical) governs
# every one. INPUT HYGIENE ONLY: strict_verify / NLI / 4-role / span-grounding untouched.
# ─────────────────────────────────────────────────────────────────────────────

# F1 — welded-mega-line heading cap. A ``#..######`` heading line is kept unconditionally
# only when it is SHORT (real headings are short); a long ``#``-prefixed line is a welded
# nav / banner region and must fall through to the token/segment rules. Env-tunable.
_ENV_MD_HEADING_MAX_CHARS = "PG_MD_HEADING_MAX_CHARS"
_DEFAULT_MD_HEADING_MAX_CHARS = 160

# F4 — a welded nav-link RUN is removed only when the run itself is pure nav (this many of the
# run's own characters sit inside markdown-link markup). Per-run, so a year in the welded
# line's prose tail no longer shields the nav head.
_NAV_RUN_MIN_LINK_DENSITY = 0.8


def _md_heading_max_chars() -> int:
    """F1 — max chars for a markdown heading kept unconditionally (env, default 160)."""
    try:
        return int(os.getenv(_ENV_MD_HEADING_MAX_CHARS, str(_DEFAULT_MD_HEADING_MAX_CHARS)))
    except (TypeError, ValueError):
        return _DEFAULT_MD_HEADING_MAX_CHARS


# F2 — inline token-only chrome removals (surrounding prose byte-preserved). Each shape NEVER
# occurs inside real article prose or a reference/citation line, so removal is safe ANYWHERE in
# the line; a line reduced to whitespace was pure chrome and drops downstream (as now).
_INLINE_CHROME_TOKEN_RES: "tuple[re.Pattern, ...]" = (
    # F2.1 — US-gov site banner welded inline with real prose (ev_497 bls.gov).
    re.compile(
        r"An official website of the United States government"
        r"(?:\s+Here'?s how you know)?",
        re.IGNORECASE,
    ),
    # F2.2 — reading-time widget welded inline with date/title/prose (ev_957 cbreim).
    re.compile(r"\b\d+\s*Minute Read Time\b", re.IGNORECASE),
    # F2.3 — skip-nav in paren-title form (ev_258) + line-leading bare ``#content`` anchor (ev_195).
    re.compile(
        r"\(\s*https?://[^)\s]+\s+\"skip to (?:main )?content\"\s*\)", re.IGNORECASE
    ),
    re.compile(r"^\(\s*https?://[^)\s]+#content\s*\)", re.IGNORECASE),
    # F2.4 — inline video-player chrome (ev_272 bls lawyers, likely ev_672).
    re.compile(r"Please enable javascript to play this video\.?", re.IGNORECASE),
    re.compile(r"\[Video transcript available at [^\]]*\]\([^)]*\)", re.IGNORECASE),
    # F2.5 — IAB TCF consent anchor (ev_954 ACM).
    re.compile(r"\[\[#IABV2SETTINGS#\]\]\([^)]*\)"),
    # F2.6 — Taylor & Francis PDF cover-sheet tokens (ev_524): the print/online ISSN pair token
    # and the "Journal homepage:" URL never occur in article prose or a reference line (a real
    # citation writes "ISSN 1466-4402", never the "(Print) … (Online)" pair token).
    re.compile(r"\(Print\)\s*\d{4}-\d{3}[\dxX]\s*\(Online\)", re.IGNORECASE),
    re.compile(r"Journal homepage:\s*\S+", re.IGNORECASE),
)

# F2.7 — Crossref citation-count widget (ev_497) — GUARDED: removed only when the line is NOT
# reference-like / not ref_mode, so a bibliography line naming Crossref near a year/DOI survives.
_CROSSREF_WIDGET_RE = re.compile(r"\bCrossref\s+\d+\b", re.IGNORECASE)

# F3 — consent-banner LINE rule (multilingual, 2-signal). A line is dropped iff a consent ANCHOR
# matches at line start (after optional bullets / heading marks) AND ≥1 additional consent SIGNAL
# appears later in the line. Two anchored consent signals on one line is not natural article prose;
# ref_mode / reference-like lines WIN (a cited privacy-paper title with a year survives).
_CONSENT_ANCHOR_RE = re.compile(
    r"^[\s#>*\-]*"
    r"(?:we use cookies"
    r"|this (?:web)?site uses cookies"
    r"|you control your data"
    r"|we and our (?:business )?partners use (?:technologies|cookies)"
    r"|nel nostro sito utilizziamo"
    r"|questo sito utilizza(?: i)? cookie)",
    re.IGNORECASE,
)
_CONSENT_SIGNAL_RE = re.compile(
    r"cookies? policy"
    r"|accept all"
    r"|personaliz(?:e|ation of) content(?: and ads)?"
    r"|analyz(?:e|ing) our traffic"
    r"|il tuo consenso"
    r"|cookie tecnici"
    r"|withdraw (?:your )?consent"
    r"|\bconsent\b",
    re.IGNORECASE,
)

# F4 — welded nav-RUN detection. A maximal run of ≥3 markdown links (empty-anchor ``[ ](url)`` /
# ``[](url)`` included) separated ONLY by whitespace / separator tokens (``| * ** • > · \``).
_MD_LINK_TOKEN_PATTERN = r"\[[^\]]*\]\([^)]*\)"
_NAV_RUN_SEP_PATTERN = r"[\s|*•·>\\]*"
_NAV_LINK_RUN_RE = re.compile(
    _MD_LINK_TOKEN_PATTERN
    + r"(?:" + _NAV_RUN_SEP_PATTERN + _MD_LINK_TOKEN_PATTERN + r"){2,}"
)
# Link TEXT only (the ``[text]`` part) — a run whose links are mostly pure digits is citation
# apparatus (footnote markers ``[1](#fn1)[2](#fn2)``), NOT nav, and is kept.
_MD_LINK_TEXT_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")


# ─────────────────────────────────────────────────────────────────────────────
# I-fetchclean-001 round-2 (2026-07-10) — the 15 residual welded-chrome leaks from the
# live retest. Four root causes (see .codex/I-fetchclean-001/fable_fix_round2.md):
#   RC1 heading-line bypass · RC2 density-dilution (chrome welded inside a prose line) ·
#   RC3 vocab gaps · RC4 span windows cut mid-link (fixed in live_retriever, not here).
# Every addition below is gated DEFAULT-ON by ``PG_FETCH_MD_NAV_STRIP_V2``; OFF ("0") ⇒
# the round-2 helpers are never invoked ⇒ byte-identical to round-1. The SACRED GUARD is
# unchanged: ref-mode + citation-signal lines are byte-identical (the sole exception is an
# empty/symbolic-anchor same-page back-link, which carries zero citation content). INPUT
# HYGIENE ONLY — strict_verify / NLI / 4-role / span-grounding are untouched.
# ─────────────────────────────────────────────────────────────────────────────

_ENV_MD_NAV_STRIP_V2 = "PG_FETCH_MD_NAV_STRIP_V2"


def _md_nav_strip_v2_enabled() -> bool:
    """Round-2 additions (Fix 1-4) default-ON; OFF ("0") ⇒ byte-identical to round-1."""
    return os.getenv(_ENV_MD_NAV_STRIP_V2, "1") != "0"


# Fix 2 (RC2 core) — inline markdown-link policy, applied per link on a KEPT line.
# (a) empty-anchor link ``[]()`` / ``[ ]()`` — no anchor text = pure chrome.
# (b) image token ``![alt](url)`` + a dangling line-trailing ``![alt`` (window cut).
# (c)/(d) per-link classify+rewrite via ``_MD_LINK_ANCHOR_TARGET_RE`` (anchor, target groups).
_MD_IMAGE_TOKEN_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_DANGLING_IMAGE_RE = re.compile(r"!\[[^\]]*$")
_MD_LINK_ANCHOR_TARGET_RE = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
# An anchor that is EMPTY or SYMBOLIC (no letter/digit at all — e.g. "", "↩", "^", "#", "*").
_ANCHOR_HAS_ALNUM_RE = re.compile(r"[^\W_]", re.UNICODE)
# Fix 3 (RC3) — a bare parenthesised URL echo ``(https://… )`` NOT preceded by ``]`` (so a real
# markdown link's ``(url)`` tail is never touched); dropped only OFF a reference-like line.
_BARE_PAREN_URL_RE = re.compile(r"(?<!\])\(\s*https?://[^)\s]+\s*\)")

# Fix 3 (RC3) — chrome vocab additions, all structure-anchored token-only inline removals
# applied ONLY on a NON-ref / NON-reference-like line (surrounding prose byte-preserved).
_INLINE_CHROME_TOKEN_RES_V2: "tuple[re.Pattern, ...]" = (
    # Login-wall (ev_117 nationalacademies): the wall sentence + the "Download as guest" CTA.
    re.compile(r"You must be logged in to \w+ this publication\.?", re.IGNORECASE),
    re.compile(r"\[Download as guest\]\([^)]*\)", re.IGNORECASE),
    # Cookie/CMP sentence runs, CTA-anchored so real prose ABOUT cookies never matches
    # (ev_726 social-economy-gateway; ev_244 appunite IAB copy welded MID-line after prose).
    re.compile(
        r"This site uses cookies\.\s*Visit our \[cookies policy page\]\([^)]*\)[^.]*\.?",
        re.IGNORECASE,
    ),
    re.compile(
        r"We and our (?:business )?partners use technologies, including cookies,.*?(?:\.|:)",
        re.IGNORECASE,
    ),
    # Standalone CMP heading text (ev_244) — exact, so it only strips the banner label.
    re.compile(r"You control your data", re.IGNORECASE),
    # News-ticker relative-time token (ev_195 thehill "2 hours ago").
    re.compile(r"\b\d+\s+(?:hour|minute|day)s?\s+ago\b", re.IGNORECASE),
)


def _link_policy_repl(match: "re.Match") -> str:
    """Fix 2 (c)+(d) — classify one ``[anchor](target)`` on a NON-guarded line:
      * empty / symbolic anchor            → DELETE (pure chrome / back-link).
      * numeric anchor into a ``#`` frag   → KEEP wrapped (footnote MARKER, citation apparatus).
      * relative ``/…`` or ``#…`` target   → DELETE whole link (site nav / in-page ToC).
      * anything else (absolute URL, …)    → UNWRAP to the anchor text (prose byte-preserved).
    """
    anchor = match.group(1)
    target = match.group(2).strip()
    a = anchor.strip()
    if not a or not _ANCHOR_HAS_ALNUM_RE.search(a):
        return ""  # empty / symbolic anchor → chrome / back-link
    if a.isdigit() and target.startswith("#"):
        return match.group(0)  # numeric footnote marker → keep wrapped
    if target.startswith("/") or target.startswith("#"):
        return ""  # relative / in-page fragment nav link → drop whole link
    return anchor  # absolute-URL (or other) link → unwrap to anchor text


def _symbolic_backlink_repl(match: "re.Match") -> str:
    """The ref-mode / reference-like EXCEPTION — delete ONLY an empty/symbolic-anchor same-page
    ``#…`` back-link (ev_037 footnote back-link); every real citation link is byte-preserved."""
    anchor = match.group(1)
    target = match.group(2)
    a = anchor.strip()
    if (not a or not _ANCHOR_HAS_ALNUM_RE.search(a)) and "#" in target:
        return ""
    return match.group(0)


def _apply_inline_link_policy(line: str, ref_mode: bool) -> str:
    """Fix 2 — the inline markdown-link policy. On a NON-ref, NON-reference-like line: delete
    images / empty-anchor / relative-nav links, unwrap remaining links to anchor text, and drop
    bare parenthesised URL echoes. On a ref-mode / reference-like line (the sacred guard): only an
    empty/symbolic-anchor same-page back-link is deleted; everything else is byte-identical."""
    if "[" not in line and "(" not in line:
        return line
    if ref_mode or _line_is_reference_like(line):
        return _MD_LINK_ANCHOR_TARGET_RE.sub(_symbolic_backlink_repl, line)
    # (b) images first — an image's ``[alt](url)`` sub-token must not reach the link policy.
    line = _MD_IMAGE_TOKEN_RE.sub("", line)
    line = _MD_DANGLING_IMAGE_RE.sub("", line)
    # (Fix 3) bare parenthesised URL echo — lookbehind protects a real link's ``(url)`` tail.
    line = _BARE_PAREN_URL_RE.sub("", line)
    # (a)+(c)+(d) per-link classify / delete / unwrap.
    line = _MD_LINK_ANCHOR_TARGET_RE.sub(_link_policy_repl, line)
    return line


def _strip_inline_chrome_tokens_v2(line: str, ref_mode: bool) -> str:
    """Fix 3 — remove the round-2 chrome vocab tokens inline (login-wall / cookie-CMP sentence /
    CMP heading label / news-ticker). GUARDED: never touches a ref-mode or reference-like line, so
    a cited privacy/cookie-policy paper title with a year survives byte-identical."""
    if ref_mode or _line_is_reference_like(line):
        return line
    for rx in _INLINE_CHROME_TOKEN_RES_V2:
        line = rx.sub("", line)
    return line


def _line_is_reference_like(line: str) -> bool:
    """True iff the line carries >=1 citation signal (KEEP guard, §Fix B step 4)."""
    return any(rx.search(line) for rx in _CITATION_SIGNAL_RES)


def _line_is_prose_like(stripped: str, link_chars: int) -> bool:
    """True iff >=60% of the line's chars sit OUTSIDE link markup AND the line ends
    with sentence punctuation — a real sentence with incidental inline links (step 5)."""
    n = len(stripped)
    if n == 0:
        return False
    if (n - link_chars) / n < 0.6:
        return False
    return bool(_SENTENCE_END_RE.search(stripped))


def _is_nav_link_line(line: str, ref_mode: bool) -> bool:
    """§Fix B step 3 — DROP iff link-density >= 0.5 AND link_count >= 2 AND NOT
    reference-like AND NOT prose-like. Pure; measures markdown-link density on the line."""
    stripped = line.strip()
    if not stripped:
        return False
    links = _MD_LINK_RE.findall(stripped)
    if len(links) < 2:
        return False
    link_chars = sum(len(m) for m in links)
    if link_chars / len(stripped) < 0.5:
        return False
    if ref_mode or _line_is_reference_like(line):
        return False  # reference-like → KEEP
    if _line_is_prose_like(stripped, link_chars):
        return False  # prose-like → KEEP
    return True


def _strip_inline_chrome_tokens(line: str, ref_mode: bool) -> str:
    """F2 — remove inline chrome tokens welded into a real line (surrounding prose preserved).
    The unguarded tokens are shapes that never occur in article prose / a reference line; the
    Crossref citation-count widget is guarded so a bibliography line naming Crossref survives."""
    for rx in _INLINE_CHROME_TOKEN_RES:
        line = rx.sub("", line)
    if not ref_mode and not _line_is_reference_like(line):
        line = _CROSSREF_WIDGET_RE.sub("", line)
    return line


def _is_consent_banner_line(line: str, ref_mode: bool) -> bool:
    """F3 — True iff the line is a cookie-consent banner: a consent ANCHOR at line start AND ≥1
    additional consent SIGNAL later in the line. ref_mode / reference-like lines are never banners
    (KEEP guard — a cited privacy-paper title with a year survives)."""
    if ref_mode or _line_is_reference_like(line):
        return False
    m = _CONSENT_ANCHOR_RE.match(line)
    if not m:
        return False
    return _CONSENT_SIGNAL_RE.search(line[m.end():]) is not None


def _strip_nav_link_runs(line: str, ref_mode: bool) -> str:
    """F4 — remove each maximal ≥3-link nav RUN welded into a line, evaluating the guards PER RUN
    so a year in the welded line's prose tail no longer shields the nav head. A run carrying a
    citation signal, or one whose links are mostly pure digits (footnote markers), is KEPT. Prose
    outside a removed run is byte-preserved. A line with no markdown link is returned unchanged."""
    if ref_mode or "](" not in line:
        return line
    removed = False

    def _repl(match):
        nonlocal removed
        run = match.group(0)
        links = _MD_LINK_RE.findall(run)
        if len(links) < 3:
            return run
        link_chars = sum(len(x) for x in links)
        if not run or (link_chars / len(run)) < _NAV_RUN_MIN_LINK_DENSITY:
            return run
        if _line_is_reference_like(run):
            return run  # a citation signal inside the run → citation apparatus, KEEP
        texts = [t.strip() for t in _MD_LINK_TEXT_RE.findall(run)]
        if texts and sum(1 for t in texts if t.isdigit()) * 2 >= len(texts):
            return run  # footnote-marker run (mostly digit link texts) → KEEP
        removed = True
        return " "

    out = _NAV_LINK_RUN_RE.sub(_repl, line)
    if not removed:
        return line
    # collapse stray separator tokens left behind by a removed run (whitespace-bounded only, so
    # markdown emphasis ``**word**`` that hugs its text is untouched).
    out = re.sub(r"(?<=\s)[|*•·>\\]+(?=\s)", " ", out)
    out = re.sub(r"^[\s|*•·>\\]+", "", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out


def strip_markdown_nav_chrome(text: "Optional[str]") -> str:
    """I-fetchclean-001 B1 — remove full-page markdown nav / boilerplate / structure-
    anchored chrome from a fetched markdown body, byte-preserving reference lists and
    real prose. Pure / deterministic. See the module block above for the guards.

    NEVER a faithfulness gate: this is INPUT hygiene. A page that is ONLY nav becomes
    empty here → the caller's existing ``empty_after_clean`` shell path refuses it (a
    failed fetch, not a source). A reference section / real prose paragraph survives via
    the reference-mode / citation-signal / prose-like guards.
    """
    if not text:
        return text or ""
    out: "list[str]" = []
    ref_mode = False
    ref_level = 0
    for raw in text.split("\n"):
        # (step 1) heading-context tracking — headings are never chrome, kept byte-identical.
        ref_h = _MD_REFERENCE_HEADING_RE.match(raw)
        if ref_h:
            ref_mode = True
            ref_level = len(ref_h.group(1))
            out.append(raw)
            continue
        h = _MD_HEADING_RE.match(raw)
        if h:
            if ref_mode and len(h.group(1)) <= ref_level:
                ref_mode = False
                ref_level = 0
            # F1: a SHORT heading is real → kept (round-1 byte-identical). Round-2 Fix 1: run the
            # SAME inline token/link removals on it (heading TEXT is never dropped — a heading that
            # cleaned to only marks/whitespace falls back to the raw line). A LONG `#`-prefixed line
            # is a welded nav/banner region → fall through to the token/segment rules below.
            if len(raw) <= _md_heading_max_chars():
                if _md_nav_strip_v2_enabled():
                    hline = _apply_inline_link_policy(
                        _strip_inline_chrome_tokens_v2(raw, ref_mode), ref_mode
                    )
                    out.append(hline if hline.strip("# \t") else raw)
                else:
                    out.append(raw)
                continue
        # (step 6) inline structure-anchored token removals — surrounding prose preserved.
        line = _SKIP_NAV_LINK_RE.sub("", raw)
        line = _SCOPUS_CHROME_RE.sub("", line)
        if _COOKIEBOT_MARKER_RE.search(line):
            line = _COOKIEBOT_CHROME_RE.sub("", line)
        # F2: inline chrome tokens welded into the line (gov banner / reading-time / skip-nav
        # paren+bare anchor / video-player chrome / IAB consent anchor / T&F cover sheet / Crossref).
        line = _strip_inline_chrome_tokens(line, ref_mode)
        # F4: remove welded nav-link RUNs (per-run guards) inside a long line; prose tail preserved.
        line = _strip_nav_link_runs(line, ref_mode)
        # A line that became whitespace-only after token removal was pure chrome → drop (round-1).
        if raw.strip() and not line.strip():
            continue
        # F3: cookie-consent banner line (multilingual, anchor + signal) → drop (guarded by
        # ref_mode / reference-like). Runs BEFORE the round-2 inline vocab so a PURE consent line
        # (banner label at line start) is dropped WHOLE (round-1 behaviour preserved); a welded
        # prose+consent line (anchor NOT at line start) falls to the inline vocab below.
        if _is_consent_banner_line(line, ref_mode):
            continue
        # Round-2 Fix 3 then Fix 2, in that ORDER: the inline chrome vocab (login-wall / cookie-CMP
        # sentence welded mid-line / CMP label / news-ticker) deletes CTA links wholesale FIRST, then
        # the inline link policy unwraps any REMAINING prose links to anchor text. Order matters — a
        # ``[Download as guest](url)`` CTA must be deleted before the unwrap would turn it into text.
        # Both guarded so a ref-mode / reference-like line only loses an empty/symbolic back-link.
        if _md_nav_strip_v2_enabled():
            line = _strip_inline_chrome_tokens_v2(line, ref_mode)
            line = _apply_inline_link_policy(line, ref_mode)
            if raw.strip() and not line.strip():
                continue
        # (step 6) whole-line standalone chrome (gov banner / skip-nav / reading-time).
        if _STANDALONE_CHROME_LINE_RE.match(line):
            continue
        # (steps 2-5) high link-density nav line → drop (guarded by reference / prose keeps).
        if _is_nav_link_line(line, ref_mode):
            continue
        out.append(line)
    # (step 7) collapse the blank-line runs left behind; preserve paragraph breaks.
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(out))
    return cleaned.strip()


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
    # I-fetchclean-001 B1: generic markdown nav/boilerplate line filter (link-density
    # heuristic + structure-anchored standalone chrome) — removes full-page nav menus /
    # gov banners / skip-nav / reading-time / Cookiebot & Scopus chrome that Jina/crawl4ai
    # markdown welds into real articles, while byte-preserving reference lists and real
    # prose (guards). Gated DEFAULT-ON by PG_FETCH_MD_NAV_STRIP; flag OFF ("0") ⇒ never
    # applied ⇒ byte-identical. Input hygiene only.
    if os.getenv("PG_FETCH_MD_NAV_STRIP", "1") != "0":
        text = strip_markdown_nav_chrome(text)
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


# ---------------------------------------------------------------------------
# I-deepfix-004 STEP B — cited-work slice extraction for PDFs.
#
# Root cause (Fable 5, 2026-07-09): the pipeline defines a citable span by
# POSITION ("first N chars of whatever bytes came back") and never checks
# IDENTITY ("is this text the article the citation names?"). DOI->PDF
# redirects never reach the PDF extractor (the branch keys on
# url.endswith('.pdf')), so a `doi.org/...` that redirects to a WHOLE-issue
# combined PDF is scraped as one blob and the `#page=N` anchor is thrown away.
# STEP B resolves the redirect, captures the page anchor, and slices the cited
# work out of the combined PDF.
#
# All of STEP B is gated by PG_PDF_CITED_WORK_SLICE (default ON; OFF =>
# byte-identical). Faithfulness engine (strict_verify / provenance / NLI /
# 4-role) is UNTOUCHED — this only changes WHICH verbatim span is extracted,
# never how a claim is verified against it. No fixed page-count window and no
# per-source cap: the end page comes from real metadata only, and slicing
# accumulates under the SAME existing char budget the caller already applies.
# ---------------------------------------------------------------------------

# The caller (fetch_with_bypass PDF branch) already caps PDF content at 50 000
# chars (`content=pdf_text[:50000]`). The cited-work slice accumulates forward
# under that SAME budget when no explicit end page is known — it is NOT a new
# page-count window, just the existing char ceiling surfaced as a named
# constant so the accumulation loop stops at parity with the caller cap.
_PDF_EXTRACT_CHAR_CAP = 50000


def pdf_cited_work_slice_enabled() -> bool:
    """True iff STEP B (cited-work PDF slice extraction) is enabled.

    Gated by PG_PDF_CITED_WORK_SLICE. DEFAULT ON — enabled by
    '1'/'true'/'yes'/'on' (case-insensitive) AND by unset/empty (default).
    Only an explicit falsey value ('0'/'false'/'no'/'off') turns it OFF, in
    which case every STEP-B call site is byte-identical to the prior behaviour
    (no redirect resolution, no page slice, no extra metadata keys)."""
    raw = os.getenv("PG_PDF_CITED_WORK_SLICE")
    if raw is None or not raw.strip():
        return True
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _parse_pdf_page_fragment(text: "Optional[str]") -> "Optional[int]":
    """Parse a 1-indexed PDF page anchor from a `#page=N` fragment.

    Accepts a raw fragment, a full URL, or a Location-header value. Prefers the
    canonical PDF open-parameter form `#page=N`; falls back to a `?page=` /
    `&page=` query form. Returns the integer N (>=1) or None. Pure / no
    network — a malformed value simply yields None (fail-open: no anchor)."""
    if not text:
        return None
    m = re.search(r"#page=(\d+)", text, re.IGNORECASE)
    if not m:
        m = re.search(r"[?&]page=(\d+)", text, re.IGNORECASE)
    if not m:
        return None
    try:
        n = int(m.group(1))
    except (TypeError, ValueError):
        return None
    return n if n >= 1 else None


def _parse_doi_page_range(doi: "Optional[str]") -> "tuple[Optional[int], Optional[int]]":
    """Parse a (start_page, end_page) range from a DOI whose suffix encodes the
    article's page span, e.g. `10.34142/...-2026-9-2-203-210` => (203, 210).

    Matches the LAST two hyphen-separated numeric groups at the end of the DOI
    (`-<start>-<end>`). Returns (None, None) when the DOI does not end that way
    or when end < start (an inconsistent range is discarded, not trusted). Pure
    / deterministic — no network. Fail-open: any parse miss yields (None, None)
    so the caller simply carries no page anchor from the DOI suffix."""
    if not doi:
        return (None, None)
    m = re.search(r"-(\d+)-(\d+)\s*$", doi)
    if not m:
        return (None, None)
    try:
        start = int(m.group(1))
        end = int(m.group(2))
    except (TypeError, ValueError):
        return (None, None)
    if start < 1 or end < start:
        return (None, None)
    return (start, end)


# ---------------------------------------------------------------------------
# I-deepfix-004 F2 (B3) — SLICE-IDENTITY VERIFICATION.
# A DOI suffix page range (e.g. `-203-210`) encodes the article's PRINTED page
# numbers. Using a printed page number as a PHYSICAL PDF page index on a whole-
# ISSUE PDF slices a DIFFERENT article (printed p.203 is rarely physical page 203
# of the issue). Before ADOPTING such a slice, confirm it IS the cited work; if
# unverifiable, DO NOT adopt it — recover to whole-doc (kept + disclosed
# downstream, never a wrong-content adoption, §-1.3). A `#page=N` FRAGMENT anchor
# is a physical page reference (PDF Open Parameters) and is trusted as-is — only
# the printed-page-suffix anchor is verified.
# ---------------------------------------------------------------------------

# The verification reads ONLY the running-header zone at the TOP of the slice. In
# clinical context the dangerous direction is a false-CONFIRM (adopting a wrong
# slice); a small window keeps an incidental page-number-shaped token (a sample
# size / year / citation) deep in the slice from confirming a wrong physical page.
# A false-reject only recovers to whole-doc (safe).
_SLICE_IDENTITY_TOP_CHARS = 400
# Minimum cited-title length that may serve as an identity signal (a very short
# title fragment is not distinctive enough to confirm identity).
_SLICE_TITLE_MIN_CHARS = 12


def pdf_slice_identity_verify_enabled() -> bool:
    """True iff SLICE-IDENTITY VERIFICATION (I-deepfix-004 F2/B3) is enabled.

    Gated by PG_PDF_SLICE_IDENTITY_VERIFY. DEFAULT ON (unset/empty => ON). Only an
    explicit falsey value ('0'/'false'/'no'/'off') turns it OFF, in which case a
    printed-page slice is adopted BLINDLY exactly as before this fix (byte-identical
    OFF). Read at call time so tests toggle without re-import."""
    raw = os.getenv("PG_PDF_SLICE_IDENTITY_VERIFY")
    if raw is None or not raw.strip():
        return True
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _slice_identity_verified(
    slice_text: "Optional[str]",
    printed_start_page: "Optional[int]",
    cited_title: "Optional[str]" = None,
    top_chars: int = _SLICE_IDENTITY_TOP_CHARS,
) -> bool:
    """Confirm a printed-page PDF slice IS the cited work (I-deepfix-004 F2/B3).

    Reads ONLY the TOP ``top_chars`` of the slice (the running-header zone) and
    confirms identity via EITHER high-precision signal:
      1. the cited article TITLE (when supplied) appears near the top; OR
      2. the printed START page number appears near the top as a standalone token.
    Returns ``False`` (UNVERIFIED) when neither confirms — the caller then does NOT
    adopt the slice (recover -> whole-doc; never a wrong-content adoption). Pure /
    deterministic; no network. Precision-first: a miss recovers (safe), so brittle
    matching only ever causes a safe whole-doc fallback, never a wrong adoption.

    ``cited_title`` is threaded from row / DOI / OpenAlex metadata WHEN PRESENT; the
    live ``access_bypass`` path has no title source (that metadata lives in the
    retrieval layer), so in production the page-number signal is the working check
    and the title branch activates once the owning lane wires a title through."""
    if not slice_text:
        return False
    head = slice_text[: max(1, top_chars)]
    low_head = head.lower()
    # Signal 1 — cited title near the top (only when a distinctive title is supplied).
    if cited_title:
        norm_title = re.sub(r"\s+", " ", cited_title.strip().lower())
        if len(norm_title) >= _SLICE_TITLE_MIN_CHARS:
            norm_head = re.sub(r"\s+", " ", low_head)
            if norm_title in norm_head:
                return True
    # Signal 2 — printed start page number as a standalone token near the top.
    if printed_start_page is not None and printed_start_page >= 1:
        if re.search(rf"\b{printed_start_page}\b", head):
            return True
    return False


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


def _crawl4ai_backed_off_cooldown(generation: int) -> float:
    """I-fetch-005 (#1344) FIX 1: exponential-backoff cooldown for the crawl4ai breaker.

    generation 1 -> BASE, 2 -> BASE*BACKOFF, 3 -> BASE*BACKOFF^2, ... capped at MAX_COOLDOWN.
    A genuinely-dead browser (missing OS libs on the box) therefore backs OFF geometrically
    instead of being re-probed every BASE seconds forever; a transient hiccup still recovers
    at BASE (the generation resets to 0 on the first successful probe). BACKOFF<=1 =>
    constant BASE cooldown (legacy shape)."""
    base = _CRAWL4AI_CIRCUIT_BREAKER_COOLDOWN
    backoff = _CRAWL4AI_CIRCUIT_BREAKER_BACKOFF
    if backoff <= 1.0 or generation <= 1:
        cooldown = base
    else:
        cooldown = base * (backoff ** (generation - 1))
    return min(cooldown, _CRAWL4AI_CIRCUIT_BREAKER_MAX_COOLDOWN)


def _crawl4ai_breaker_admit() -> "tuple[str, float]":
    """I-fetch-005 (#1344) FIX 1: breaker admission decision, computed ATOMICALLY under the lock.

    Returns ``(decision, remaining_seconds)`` where decision is:
      * ``"closed"`` — breaker not open (never opened, or a prior probe closed it). Proceed
        as a NORMAL fetch.
      * ``"probe"``  — breaker WAS open and the cooldown has elapsed; THIS caller is the
        single-flight HALF-OPEN probe. Proceed and try ONE real browser fetch.
      * ``"open"``   — breaker still cooling down, OR another caller already holds the probe
        slot. Skip crawl4ai (use the fallback chain). ``remaining_seconds`` is for logging.
    Only ONE caller ever gets ``"probe"`` per cooldown window (atomic check-and-set of
    ``_crawl4ai_half_open_probe_active``), so a genuinely-dead browser costs at most ONE
    wasted browser-launch attempt per (backed-off) cooldown — never a per-URL storm."""
    global _crawl4ai_half_open_probe_active
    now = _time_module.time()
    with _crawl4ai_breaker_lock:
        if _crawl4ai_circuit_open_until <= 0.0:
            return "closed", 0.0
        if _crawl4ai_circuit_open_until > now:
            return "open", _crawl4ai_circuit_open_until - now
        # Cooldown elapsed -> HALF-OPEN. Grant the single probe slot to the first caller.
        if _crawl4ai_half_open_probe_active:
            return "open", 0.0
        _crawl4ai_half_open_probe_active = True
        return "probe", 0.0


def _crawl4ai_breaker_on_success() -> None:
    """I-fetch-005 (#1344) FIX 1: a crawl4ai fetch reached the browser-survived point — the
    browser is HEALTHY. Fully CLOSE the breaker: zero the failure counter, clear the open
    window, release the probe slot, and reset the backoff generation."""
    global _crawl4ai_consecutive_failures, _crawl4ai_circuit_open_until
    global _crawl4ai_half_open_probe_active, _crawl4ai_open_generation
    with _crawl4ai_breaker_lock:
        _crawl4ai_consecutive_failures = 0
        _crawl4ai_circuit_open_until = 0.0
        _crawl4ai_half_open_probe_active = False
        _crawl4ai_open_generation = 0


def _crawl4ai_track_failure() -> None:
    """FIX-EPIPE + I-fetch-005 (#1344) FIX 1: record a crawl4ai subprocess/browser failure.

    Increments the consecutive-failure counter and, on the OPEN TRANSITION only, arms the
    (exponentially backed-off) cooldown. Guarded so a SWARM of concurrent in-flight failures
    that arrive AFTER the breaker is already open cannot re-inflate the generation or reset
    the cooldown — the single transition already armed it. A failed HALF-OPEN probe reaches
    this from the elapsed-open window (``_circuit_open_until <= now``) and RE-opens with the
    NEXT backoff generation."""
    global _crawl4ai_consecutive_failures, _crawl4ai_circuit_open_until
    global _crawl4ai_open_generation
    with _crawl4ai_breaker_lock:
        now = _time_module.time()
        _crawl4ai_consecutive_failures += 1
        # Already OPEN (still cooling down) -> a concurrent in-flight failure. Do NOT bump the
        # generation or reset the cooldown; the single open transition already armed it.
        if _crawl4ai_circuit_open_until > now:
            return
        if _crawl4ai_consecutive_failures >= _CRAWL4AI_CIRCUIT_BREAKER_THRESHOLD:
            _crawl4ai_open_generation += 1
            cooldown = _crawl4ai_backed_off_cooldown(_crawl4ai_open_generation)
            _crawl4ai_circuit_open_until = now + cooldown
            logger.warning(
                "[polaris graph] CRAWL4AI: FIX-EPIPE circuit breaker OPENED "
                "after %d consecutive failures (gen %d, cooldown %.0fs) — a HALF-OPEN "
                "probe will retry ONE browser fetch after the cooldown",
                _crawl4ai_consecutive_failures,
                _crawl4ai_open_generation,
                cooldown,
            )


def _crawl4ai_breaker_finalize_probe() -> None:
    """I-fetch-005 (#1344) FIX 1: backstop that ALWAYS runs in ``_try_crawl4ai``'s finally when
    THIS call was the half-open probe. Releases the single-flight slot no matter which exit path
    ran (success, tracked failure, OR a NEUTRAL path that recorded neither — e.g. RuntimeError /
    crawl-returned-False / timeout) so a probe can never wedge the breaker OPEN forever. If the
    probe resolved via neither success (breaker CLOSED) nor a tracked failure (breaker RE-opened)
    — i.e. the breaker is still sitting in the elapsed-open window — re-open it with backoff so
    callers never hot-loop re-probing a browser of unproven health. Idempotent: a no-op when
    success/failure already resolved it."""
    global _crawl4ai_half_open_probe_active, _crawl4ai_circuit_open_until
    global _crawl4ai_open_generation
    with _crawl4ai_breaker_lock:
        _crawl4ai_half_open_probe_active = False
        now = _time_module.time()
        if 0.0 < _crawl4ai_circuit_open_until <= now:
            _crawl4ai_open_generation += 1
            _crawl4ai_circuit_open_until = now + _crawl4ai_backed_off_cooldown(
                _crawl4ai_open_generation
            )


def _crawl4ai_timeout_seconds() -> int:
    """I-fetch-005 iter-2 P1: parse ``PG_CRAWL4AI_TIMEOUT`` DEFENSIVELY (never raises).

    A malformed / non-integer value falls back to 30s (and a non-positive value clamps to 30,
    since a zero/negative page timeout is nonsensical). This MUST NOT raise, and MUST be
    evaluated BEFORE ``_crawl4ai_breaker_admit`` grants the single-flight half-open probe slot:
    the prior code parsed the env with a bare ``int(...)`` AFTER the admit but BEFORE the
    try/finally backstop, so a bad env raised ``ValueError`` in the gap and left
    ``_crawl4ai_half_open_probe_active`` wedged ``True`` forever — the breaker could then never
    admit another probe and never recover. Parsing here can never raise, so no probe slot can
    leak on a malformed timeout."""
    raw = os.getenv("PG_CRAWL4AI_TIMEOUT", "30")
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return 30
    return value if value > 0 else 30


def reset_crawl4ai_breaker_state() -> None:
    """I-fetch-005 (#1344) FIX 1: reset ALL crawl4ai breaker state (test isolation + per-run).
    Not required on the production hot path (the breaker self-recovers via the half-open probe),
    but keeps the state per-run so a prior run's open window never carries over."""
    global _crawl4ai_consecutive_failures, _crawl4ai_circuit_open_until
    global _crawl4ai_half_open_probe_active, _crawl4ai_open_generation
    with _crawl4ai_breaker_lock:
        _crawl4ai_consecutive_failures = 0
        _crawl4ai_circuit_open_until = 0.0
        _crawl4ai_half_open_probe_active = False
        _crawl4ai_open_generation = 0


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


# ---------------------------------------------------------------------------
# I-deepfix-001 (#1344): FIX-QM2 concurrent-fetch late-racer double-resolution
# guard.
#
# THE BUG (observed 5x in the drb_78/drb_90 autopsy runs): the FIX-QM2 concurrent
# fetch races Crawl4AI (a Playwright browser subprocess) + Jina + Trafilatura
# (a thread-pool executor) + the clinical-PDF mineru CLI (an asyncio subprocess).
# A slow racer `_bounded_backend`-cancelled at its wall-clock (e.g. an
# ansys.com / gspublishing read-timeout at ~30s) keeps its underlying subprocess
# / executor thread alive. When that abandoned worker FINALLY completes — long
# after a faster racer already won and the gather returned (drb_90: gather
# returns 00:08:58, the error fires 00:09:59), and even during `asyncio.run`
# teardown where `shutdown_default_executor` joins the still-running executor —
# the library / asyncio transport internals schedule a
# `loop.call_soon(future.set_result, None)` on a future that is ALREADY done.
# `Future.set_result` on a done future raises `asyncio.InvalidStateError`, which
# asyncio's Handle runner routes to `loop.call_exception_handler`; the DEFAULT
# handler logs it as a scary "asyncio ERROR Exception in callback
# Future.set_result(None)".
#
# It is logged-only (never crashes the run) but pollutes the forensic log and
# hides that the slow racer was abandoned. The double `set_result` lives in
# asyncio / Playwright / mineru INTERNALS — there is NO `set_result` in our code
# to wrap with a `not future.done()` guard. The faithful orchestration-level fix
# is a NARROW custom loop exception handler that swallows EXACTLY this benign
# late-racer `InvalidStateError`-from-`set_result` / `set_exception` case and
# DELEGATES every other exception to the previously-installed handler.
#
# Installed idempotently at the top of `fetch_with_bypass` (the FIX-QM2
# orchestration entry) and NOT restored, so it stays active through the late
# completion AND the loop-teardown window where the error actually fires. Pure
# reliability (log hygiene) — it touches NO fetched content, NO verification
# gate, NO backend selection. Kill-switch: PG_FETCH_LATE_RACER_RACE_GUARD=0.
# ---------------------------------------------------------------------------

PG_FETCH_LATE_RACER_RACE_GUARD_ENV = "PG_FETCH_LATE_RACER_RACE_GUARD"

# Loops that already carry the guard — keyed by the loop OBJECT. A WeakSet auto-
# evicts a GC'd per-thread bypass loop (no leak over ~1000 URLs) and cannot alias
# a recycled loop address. A threading.Lock guards it (each bypass fetch runs on
# its own thread; WeakSet is not safe under concurrent inserts + weakref-removal
# callbacks).
_late_racer_guarded_loops: "weakref.WeakSet[Any]" = weakref.WeakSet()
_late_racer_guard_lock = threading.Lock()


def _late_racer_guard_enabled() -> bool:
    """Guard is ON unless PG_FETCH_LATE_RACER_RACE_GUARD=0 (default-ON correct
    fix; '0' reverts to the noisy default handler that logs the benign error)."""
    return os.getenv(PG_FETCH_LATE_RACER_RACE_GUARD_ENV, "1").strip() != "0"


def _is_late_racer_double_resolution(context: Dict[str, Any]) -> bool:
    """True iff `context` is the benign late-racer double-resolution: an
    `asyncio.InvalidStateError` raised by a `set_result` / `set_exception`
    callback on an already-done future.

    NARROW by design — an InvalidStateError with no set_result / set_exception
    provenance (e.g. a genuine `task.result()`-before-done bug) is NOT swallowed;
    it falls through to the delegate so real bugs stay visible."""
    exc = context.get("exception")
    if not isinstance(exc, asyncio.InvalidStateError):
        return False
    parts: List[str] = []
    handle = context.get("handle")
    if handle is not None:
        try:
            parts.append(repr(handle))
        except Exception:  # noqa: BLE001 — repr must never break the handler
            pass
    message = context.get("message")
    if message:
        parts.append(str(message))
    blob = " ".join(parts)
    return "set_result" in blob or "set_exception" in blob


def _install_late_racer_double_resolve_guard(
    loop: "asyncio.AbstractEventLoop",
) -> None:
    """Install the narrow late-racer double-resolution exception handler on
    `loop` — idempotently (once per loop) and NON-restoring, so it outlives the
    gather to catch the late completion + teardown-time error. Delegates every
    non-matching exception to the handler set BEFORE us (the default handler when
    None). Safe on a long-lived loop (pipeline B): idempotent-install + delegate
    never clobbers a foreign handler's behavior."""
    if not _late_racer_guard_enabled():
        return
    with _late_racer_guard_lock:
        if loop in _late_racer_guarded_loops:
            return
        previous_handler = loop.get_exception_handler()

        def _guard(
            guarded_loop: "asyncio.AbstractEventLoop",
            context: Dict[str, Any],
            _previous=previous_handler,
        ) -> None:
            if _is_late_racer_double_resolution(context):
                logger.debug(
                    "[ACCESS] late-racer double-resolution swallowed "
                    "(benign %s from an abandoned slow racer): %s",
                    type(context.get("exception")).__name__,
                    str(context.get("message", ""))[:120],
                )
                return
            if _previous is None:
                guarded_loop.default_exception_handler(context)
            else:
                _previous(guarded_loop, context)

        loop.set_exception_handler(_guard)
        _late_racer_guarded_loops.add(loop)


def reset_late_racer_guard_state() -> None:
    """Test-isolation ONLY: forget which loops carry the guard (mirrors
    `reset_crawl4ai_semaphore_state`). Not called on the production path."""
    with _late_racer_guard_lock:
        _late_racer_guarded_loops.clear()


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
        # I-deepfix-001 (#1344): install the narrow late-racer double-resolution
        # guard on THIS loop BEFORE any backend races — it must already be active
        # when a slow abandoned racer (Crawl4AI/mineru subprocess, Trafilatura
        # executor) completes late and the transport internals double-resolve an
        # already-done future (see `_install_late_racer_double_resolve_guard`).
        # Best-effort: guard install must never break a fetch.
        try:
            _install_late_racer_double_resolve_guard(asyncio.get_running_loop())
        except Exception as _guard_err:  # noqa: BLE001 — log-hygiene guard only
            logger.debug(
                "[ACCESS] late-racer guard install skipped: %s",
                str(_guard_err)[:120],
            )

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

        # I-fetch-005 (#1344) FIX 2: TERMINAL-block fast-skip. A url that previously hit a hard
        # WAF access-denied (akamai_access_denied) will hard-block again on EVERY backend —
        # short-circuit the whole cascade (no network, no 60s+ timeout re-walk). Gated by the
        # block-page detector (the sole populator, so OFF => never populated => byte-identical)
        # + PG_TERMINAL_BLOCK_FASTSKIP. §-1.3-SAFE: NOT a drop — the caller records an unfetched
        # source that is RETAINED downstream at ZERO weight (same as any fetch-miss).
        if (
            block_page_detector_enabled()
            and terminal_block_fastskip_enabled()
            and is_terminal_blocked(url)
        ):
            logger.info(
                "[ACCESS] I-fetch-005 FIX 2: terminal-block fast-skip for %s (prior "
                "akamai_access_denied) — cascade short-circuited, source kept at zero "
                "weight downstream (§-1.3)", url[:80],
            )
            return AccessResult(
                url=url, content="", access_method="terminal_block_skipped",
                legal_alternative=None, success=False,
                metadata={
                    "error": "terminal_block_fast_skip",
                    "reason": "akamai_access_denied",
                },
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

        # I-deepfix-004 STEP B1 (gated by PG_PDF_CITED_WORK_SLICE, default ON;
        # OFF => this block is skipped and the url/anchors are untouched =>
        # byte-identical). A `doi.org` / `dx.doi.org` citation URL currently
        # never reaches the PDF branch below (it fails `.endswith('.pdf')`), so a
        # DOI that redirects to a WHOLE-issue combined PDF is scraped as one blob
        # and the `#page=N` cited-work anchor is thrown away. Resolve the
        # redirect: if the FINAL target is a PDF, swap `url` to it so the branch
        # below fires, and carry the parsed page anchor/range into the slice.
        _slice_on = pdf_cited_work_slice_enabled()
        _pdf_page_anchor: "Optional[int]" = None
        _pdf_page_end: "Optional[int]" = None
        _pdf_anchor_is_printed_page = False
        if _slice_on and "doi.org/" in url.lower():
            _doi_target = await self._resolve_doi_pdf_target(url)
            if _doi_target and _doi_target.get("is_pdf"):
                logger.info(
                    "[B1-DOI] doi->pdf resolved %s -> %s (page_anchor=%s page_end=%s)",
                    url[:50], str(_doi_target.get("final_url"))[:70],
                    _doi_target.get("page_anchor"), _doi_target.get("page_end"),
                )
                url = _doi_target["final_url"]
                _pdf_page_anchor = _doi_target.get("page_anchor")
                _pdf_page_end = _doi_target.get("page_end")
                _pdf_anchor_is_printed_page = bool(
                    _doi_target.get("anchor_is_printed_page")
                )

        # FIX-CITE-3/GAP4: Detect PDF URLs and extract text directly.
        # Academic open-access PDFs (from S2 openAccessPdf) need PDF parsing,
        # not HTML scraping. This gives the analyzer full paper content with
        # forest plots, I² values, GRADE ratings — the detail Gemini captures.
        #
        # I-deepfix-004 F6: a resolved final PDF URL can carry a `#page=N` fragment
        # (e.g. `.../article.pdf#page=5`) or a `?token=…` query. `url.lower()
        # .endswith('.pdf')` then MISSES it because the raw string ends with the
        # fragment/query, not `.pdf`, so a valid cited-work PDF is scraped as HTML
        # and the page anchor is thrown away. Test the fragment-/query-STRIPPED
        # `urlparse(url).path` so a `...pdf#page=N` still enters the PDF extractor.
        # Flag-gated: OFF => exact pre-F6 raw-url `url.lower().endswith('.pdf')`
        # predicate (byte-identical rollback; a bare `...pdf#page=N` / `...pdf?token=`
        # reverts to the old raw-url MISS, so no new URL enters the extractor).
        if _slice_on:
            _pdf_ext_match = urlparse(url).path.lower().endswith(".pdf")
        else:
            _pdf_ext_match = url.lower().endswith(".pdf")
        if _pdf_ext_match or "/pdf/" in url.lower():
            try:
                # B4: collect blob identity only when STEP B is ON (out_meta
                # None when OFF => no sha computed, metadata byte-identical).
                _pdf_out_meta: "Optional[Dict[str, Any]]" = {} if _slice_on else None
                pdf_text = await self._extract_pdf_text(
                    url,
                    page_anchor=_pdf_page_anchor,
                    page_end=_pdf_page_end,
                    out_meta=_pdf_out_meta,
                    anchor_is_printed_page=_pdf_anchor_is_printed_page,
                )
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
                    # B4: stamp blob identity onto the evidence row's metadata so
                    # downstream content-identity consolidation (STEP E) can fold
                    # combined-issue PDFs that share one blob but carry many DOIs.
                    # Only when STEP B is ON (out_meta populated) => flag-OFF keeps
                    # metadata byte-identical to the prior {"content_type": ...}.
                    _pdf_metadata: "Dict[str, Any]" = {"content_type": "application/pdf"}
                    if _slice_on and _pdf_out_meta:
                        _blob_sha = _pdf_out_meta.get("fetched_blob_sha")
                        _src_url = _pdf_out_meta.get("content_source_url")
                        if _blob_sha:
                            _pdf_metadata["fetched_blob_sha"] = _blob_sha
                        if _src_url:
                            _pdf_metadata["content_source_url"] = _src_url
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
                        metadata=_pdf_metadata,
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
          - PG_CRAWL4AI_CIRCUIT_BREAKER_THRESHOLD (default "6")
          - PG_CRAWL4AI_CIRCUIT_BREAKER_COOLDOWN (default "60.0", BASE; I-fetch-005 FIX 1)
          - PG_CRAWL4AI_CIRCUIT_BREAKER_BACKOFF (default "2.0", exponential per re-open)
          - PG_CRAWL4AI_CIRCUIT_BREAKER_MAX_COOLDOWN (default "600.0")

        Returns AccessResult. NEVER raises -- all exceptions are caught
        and converted to failure results.
        """
        global _crawl4ai_available

        # Fast-path: already know crawl4ai is not installed (a PERMANENT availability gate,
        # separate from the browser-health circuit breaker below — an un-importable package
        # is never a "browser hiccup" and must not consume a half-open probe slot).
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

        # I-fetch-005 iter-2 P1: parse the timeout DEFENSIVELY and BEFORE the breaker admit
        # below. A malformed PG_CRAWL4AI_TIMEOUT must NOT (a) raise out of this "NEVER raises"
        # method, nor (b) leak the single-flight half-open probe slot — a raise-capable
        # statement BETWEEN _crawl4ai_breaker_admit() (which sets the probe slot) and the
        # try/finally backstop that releases it would wedge the breaker OPEN forever. Keeping
        # the (now non-raising) parse ABOVE the admit removes that gap entirely.
        timeout_seconds = _crawl4ai_timeout_seconds()
        page_timeout_ms = timeout_seconds * 1000

        # FIX-EPIPE + I-fetch-005 (#1344) FIX 1: circuit breaker with HALF-OPEN recovery.
        # Evaluated AFTER the import (browser health, not package availability) and BEFORE the
        # main try/finally so a granted probe is ALWAYS released by the finally backstop below.
        #   "open"   -> skip crawl4ai, use the fallback chain (jina/trafilatura/Zyte);
        #   "probe"  -> THIS caller is the single-flight half-open trial (one real browser fetch);
        #   "closed" -> normal fetch.
        # A probe that survives the browser region CLOSES the breaker (on_success); a probe that
        # fails RE-opens it with exponential backoff (track_failure / the finally backstop).
        # NOTHING between this admit and the try/finally below may raise (the timeout parse that
        # used to sit here is hoisted above — see I-fetch-005 iter-2 P1).
        _breaker_decision, _breaker_remaining = _crawl4ai_breaker_admit()
        _is_probe = _breaker_decision == "probe"
        if _breaker_decision == "open":
            logger.debug(
                "[polaris graph] CRAWL4AI: FIX-EPIPE circuit breaker OPEN "
                "(%.0fs remaining) -- skipping %s",
                _breaker_remaining, _safe_log_str(url, 60),
            )
            return _crawl4ai_failure_result(
                url, f"circuit_breaker_open ({_breaker_remaining:.0f}s remaining)"
            )
        if _is_probe:
            logger.info(
                "[polaris graph] CRAWL4AI: FIX-EPIPE half-open probe — trying ONE browser "
                "fetch to test recovery for %s", _safe_log_str(url, 60),
            )

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
            # If we reached here, the subprocess survived — the browser is HEALTHY, so fully
            # CLOSE the breaker (and, if this was a half-open probe, release the probe slot and
            # reset the backoff generation). I-fetch-005 (#1344) FIX 1.
            _crawl4ai_breaker_on_success()

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
            # I-fetch-005 (#1344) FIX 1: if THIS call was the single-flight half-open probe,
            # ALWAYS release the probe slot here — even on exit paths that recorded neither
            # success nor a tracked failure (RuntimeError / crawl-returned-False / timeout) — so
            # a probe can never wedge the breaker OPEN forever. Idempotent (no-op if
            # success/failure already resolved it).
            if _is_probe:
                _crawl4ai_breaker_finalize_probe()
            # FIX-UNICODE: Do NOT restore original encoding. Multiple
            # concurrent Crawl4AI calls race: one call's restore undoes
            # another call's reconfigure. utf-8 is strictly superior.

    async def _resolve_doi_pdf_target(
        self, url: str
    ) -> "Optional[Dict[str, Any]]":
        """I-deepfix-004 STEP B1 — resolve a doi.org / dx.doi.org URL to its
        FINAL target and, when that target is a PDF, capture the cited-work page
        anchor.

        Does a lightweight aiohttp GET (``allow_redirects=True``) and inspects
        ONLY the response headers + redirect chain — it never reads the body
        (the real byte fetch stays in :meth:`_extract_pdf_text`). Captures:

          * the FINAL url (``resp.url`` after redirects) so the existing
            ``.pdf`` / ``/pdf/`` PDF branch fires on the resolved publisher URL;
          * a 1-indexed page anchor ``N`` from a ``#page=N`` fragment found on
            any redirect-chain ``Location`` header, on ``resp.url``, or on the
            original url. The Location headers are checked FIRST because
            ``resp.url`` frequently drops the fragment across a redirect;
          * a page range ``(start, end)`` parsed from a DOI suffix such as
            ``...-2026-9-2-203-210`` (=> pages 203-210) when the DOI ends
            ``-<start>-<end>``.

        Returns ``{"final_url", "is_pdf", "page_anchor", "page_end"}`` or
        ``None`` on any error (fail-open: the caller then leaves the url
        untouched and the pre-existing fetch path runs unchanged).

        Faithfulness-neutral: this only decides WHICH url + page span is handed
        to the extractor; no faithfulness gate is touched.
        """
        import aiohttp

        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, allow_redirects=True) as resp:
                    final_url = str(resp.url)
                    content_type = (resp.headers.get("Content-Type") or "").lower()
                    # Redirect-chain Location headers are the authoritative
                    # fragment source (resp.url can drop `#page=N`); check them
                    # first, then the final url, then the original url.
                    frag_sources: list[str] = []
                    for _hist in resp.history:
                        _loc = _hist.headers.get("Location")
                        if _loc:
                            frag_sources.append(_loc)
                    frag_sources.append(final_url)
                    frag_sources.append(url)
        except Exception as _exc:  # noqa: BLE001 — resolver must never break a fetch
            logger.debug(
                "[B1-DOI] doi->pdf resolve failed for %s: %s",
                url[:60], str(_exc)[:100],
            )
            return None

        final_path = urlparse(final_url).path.lower()
        is_pdf = final_path.endswith(".pdf") or "application/pdf" in content_type

        page_anchor: "Optional[int]" = None
        _anchor_from_fragment = False
        for _s in frag_sources:
            _n = _parse_pdf_page_fragment(_s)
            if _n is not None:
                page_anchor = _n
                _anchor_from_fragment = True
                break

        doi = self._extract_doi(url) or self._extract_doi(final_url)
        doi_start, doi_end = _parse_doi_page_range(doi) if doi else (None, None)
        # Fragment anchor wins; fall back to the DOI-suffix start page.
        if page_anchor is None:
            page_anchor = doi_start
        page_end = doi_end

        # I-deepfix-004 F2/B3: a `#page=N` fragment is a PHYSICAL page reference
        # (PDF Open Parameters) and its slice is trusted; a DOI-suffix start page
        # is a PRINTED page number used as a physical index and its slice MUST be
        # identity-verified before adoption. True ONLY when the anchor came from
        # the printed-page suffix (no fragment supplied it).
        anchor_is_printed_page = page_anchor is not None and not _anchor_from_fragment

        return {
            "final_url": final_url,
            "is_pdf": bool(is_pdf),
            "page_anchor": page_anchor,
            "page_end": page_end,
            "anchor_is_printed_page": bool(anchor_is_printed_page),
        }

    async def _extract_pdf_text(
        self,
        url: str,
        page_anchor: "Optional[int]" = None,
        page_end: "Optional[int]" = None,
        out_meta: "Optional[Dict[str, Any]]" = None,
        anchor_is_printed_page: bool = False,
    ) -> str:
        """FIX-CITE-3/GAP4: Download and extract text from academic PDF.

        Uses PyMuPDF (fitz) for extraction. Falls back to basic text
        extraction if PyMuPDF is not available.

        I-deepfix-004 STEP B (gated by PG_PDF_CITED_WORK_SLICE, default ON;
        OFF => byte-identical because all three new params stay None):
          * ``page_anchor`` / ``page_end`` — thread a 1-indexed cited-work page
            slice down to :meth:`_extract_pdf_text_from_bytes_impl` (B2);
          * ``out_meta`` — when a dict is supplied, stamp ``fetched_blob_sha``
            (sha256 of the fetched PDF bytes) + ``content_source_url`` (the
            final resolved url that produced those bytes) so the caller can put
            them on the evidence row's ``AccessResult.metadata`` (B4). When
            ``out_meta`` is None nothing is computed and the path is unchanged.
        """
        import aiohttp

        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return ""
                pdf_bytes = await resp.read()
                if len(pdf_bytes) < 1000:
                    return ""
                _final_source_url = str(resp.url)

        # B4: stamp blob identity for the caller (only when an out_meta dict is
        # supplied — i.e. the STEP-B branch with the flag ON). Best-effort:
        # a hashing error must never break extraction.
        if out_meta is not None:
            try:
                import hashlib
                out_meta["fetched_blob_sha"] = hashlib.sha256(pdf_bytes).hexdigest()
                out_meta["content_source_url"] = _final_source_url
            except Exception as _sha_exc:  # noqa: BLE001 — stamp is best-effort
                logger.debug(
                    "[B4-BLOB] blob sha stamp skipped for %s: %s",
                    url[:60], str(_sha_exc)[:80],
                )

        return await self._extract_pdf_text_from_bytes(
            url, pdf_bytes, page_anchor=page_anchor, page_end=page_end,
            anchor_is_printed_page=anchor_is_printed_page,
        )

    async def _extract_pdf_text_from_bytes(
        self,
        url: str,
        pdf_bytes: bytes,
        page_anchor: "Optional[int]" = None,
        page_end: "Optional[int]" = None,
        anchor_is_printed_page: bool = False,
    ) -> str:
        """I-deepfix-001 B1 (wave-2, 2026-07-08) — extraction-time FURNITURE screen.

        Delegates to the UNCHANGED extractor selector
        ``_extract_pdf_text_from_bytes_impl`` and — ONLY when
        ``PG_FURNITURE_DENSITY_SCREEN`` is on — checks whether the extracted body is
        furniture-DOMINANT (masthead / nav / DOI / license chrome welded as the whole
        body, the degraded-big-PDF case). If so it marks the fetch DEGRADED (loud,
        disclosed) and, when ``PG_FURNITURE_REFETCH`` is on, re-runs a DIFFERENT
        extractor to RECOVER the real article; a recovered non-furniture body replaces
        the furniture one. If recovery still yields furniture the ORIGINAL body is
        KEPT and disclosed (§-1.3: down-weight/disclose downstream, NEVER hard-drop).

        Both flags default OFF => this returns the impl output unchanged =>
        BYTE-IDENTICAL. Faithfulness engine untouched — only WHICH extractor's
        verbatim text is returned can change.

        I-deepfix-004 STEP B2: ``page_anchor`` / ``page_end`` (default None =>
        byte-identical) thread the cited-work page slice to the impl's fitz
        path. The furniture screen below is UNCHANGED and runs on whatever body
        (whole-doc or sliced) the impl returns.
        """
        # Byte-identical when no slice is requested: call the impl EXACTLY as
        # before (positional only) so pre-existing callers / stubs that use the
        # old 2-arg signature are unaffected. Only thread the page-slice kwargs
        # when an anchor was actually resolved (STEP B1).
        if page_anchor is None and page_end is None:
            body = await self._extract_pdf_text_from_bytes_impl(url, pdf_bytes)
        else:
            body = await self._extract_pdf_text_from_bytes_impl(
                url, pdf_bytes, page_anchor=page_anchor, page_end=page_end,
                anchor_is_printed_page=anchor_is_printed_page,
            )
        try:
            from src.polaris_graph.retrieval import shell_detector as _sd
        except Exception:  # noqa: BLE001 — detector import must never break extraction
            return body
        if not _sd.furniture_density_screen_enabled():
            return body
        if not body or not _sd.is_furniture_dominant(body):
            return body
        logger.warning(
            "[B1-FURNITURE] fetch_degraded=true density=%.2f chars=%d url=%s — "
            "extracted body is furniture-dominant (degraded extraction)",
            _sd.furniture_density(body), len(body), url[:60],
        )
        if _sd.furniture_refetch_enabled():
            try:
                recovered = await self._refetch_alternate_extractor(url, pdf_bytes)
            except Exception as _exc:  # noqa: BLE001 — recovery never breaks the fetch
                logger.debug(
                    "[B1-FURNITURE] alternate re-fetch errored: %s", str(_exc)[:100]
                )
                recovered = ""
            if recovered and not _sd.is_furniture_dominant(recovered):
                logger.info(
                    "[B1-FURNITURE] recovered real content via alternate extractor "
                    "(%d chars) url=%s", len(recovered), url[:60],
                )
                return recovered
        # Still furniture (or re-fetch disabled): keep + disclose, NEVER drop (§-1.3).
        logger.warning(
            "[B1-FURNITURE] alternate re-fetch did not recover clean content; keeping "
            "degraded body for downstream down-weight+disclose (no drop) url=%s",
            url[:60],
        )
        return body

    @staticmethod
    def _docling_oom_safe(pdf_bytes: bytes) -> bool:
        """B1 re-fetch guard: True iff a PDF is within the docling OOM gate (bytes +
        page count) so re-running Docling cannot ``std::bad_alloc`` / SIGSEGV. Mirrors
        the ``PG_MAX_DOCLING_PDF_*`` gate in ``_extract_pdf_text_from_bytes_impl``.
        FAIL-CLOSED (``False``) on any probe error — never risk a crash to recover a
        furniture body."""
        try:
            max_bytes = int(os.getenv("PG_MAX_DOCLING_PDF_BYTES", str(5 * 1024 * 1024)))
            max_pages = int(os.getenv("PG_MAX_DOCLING_PDF_PAGES", "40"))
        except (TypeError, ValueError):
            return False
        if max_bytes > 0 and len(pdf_bytes) > max_bytes:
            return False
        if max_pages > 0:
            try:
                import fitz as _fitz
                _doc = _fitz.open(stream=pdf_bytes, filetype="pdf")
                try:
                    if int(_doc.page_count) > max_pages:
                        return False
                finally:
                    _doc.close()
            except Exception:  # noqa: BLE001 — cannot verify size => do not risk OOM
                return False
        return True

    async def _refetch_alternate_extractor(self, url: str, pdf_bytes: bytes) -> str:
        """I-deepfix-001 B1 step 2 — re-extract a furniture-degraded PDF body with a
        DIFFERENT extractor to RECOVER the real article. Tries the structured
        extractors the flat-PyMuPDF-furniture path bypassed and returns the FIRST
        non-furniture body:

          1. mineru25 (GPU VLM) when a GPU is present — the cleanest extractor,
             safe on big PDFs (remote server, no local OOM), breaker-guarded;
          2. Docling — ONLY when the PDF is within the OOM gate (never risk a
             ``std::bad_alloc`` SIGSEGV on a big PDF the gate would have skipped).

        Returns ``""`` when nothing recovers clean content (the caller keeps +
        discloses the original — never a hard-drop). Faithfulness-neutral: only which
        extractor's verbatim text is returned changes; bounded by the existing
        PG_DOCLING_TIMEOUT_S / mineru walls — no new time-wall."""
        import asyncio as _aio

        from src.polaris_graph.retrieval import shell_detector as _sd

        candidates: "list[str]" = []
        # 1. mineru25 (GPU) — the structured VLM extractor; safe on big PDFs.
        if self._gpu_available():
            try:
                _mineru_text = await self._maybe_mineru25_extract(url, pdf_bytes)
                if _mineru_text:
                    candidates.append(_mineru_text)
            except Exception as _exc:  # noqa: BLE001
                logger.debug(
                    "[B1-FURNITURE] mineru re-extract skipped: %s", str(_exc)[:80]
                )
        # 2. Docling — only when OOM-safe (bounded); the flat-furniture path skipped it.
        if self._docling_oom_safe(pdf_bytes):
            try:
                loop = _aio.get_event_loop()
                _docling_to = float(os.getenv("PG_DOCLING_TIMEOUT_S", "60"))
                _docling_text = await _aio.wait_for(
                    loop.run_in_executor(None, self._docling_extract, pdf_bytes),
                    timeout=max(1.0, _docling_to),
                )
                if _docling_text:
                    candidates.append(_docling_text)
            except Exception as _exc:  # noqa: BLE001
                logger.debug(
                    "[B1-FURNITURE] docling re-extract skipped: %s", str(_exc)[:80]
                )
        for _cand in candidates:
            if _cand and not _sd.is_furniture_dominant(_cand):
                return _cand
        return ""

    async def _extract_pdf_text_from_bytes_impl(
        self,
        url: str,
        pdf_bytes: bytes,
        page_anchor: "Optional[int]" = None,
        page_end: "Optional[int]" = None,
        anchor_is_printed_page: bool = False,
        cited_title: "Optional[str]" = None,
    ) -> str:
        """Extract text from already-fetched PDF bytes (offline-testable).

        Split out of :meth:`_extract_pdf_text` (which owns the network fetch)
        so the extractor SELECTOR + docling-OOM gate + docling/PyMuPDF routing
        can be unit-tested without a network round-trip (I-deepfix-001 U19).

        Faithfulness-neutral: this only decides WHICH extractor produces the
        verbatim text that strict_verify later grounds — no faithfulness gate
        (strict_verify / NLI / 4-role / provenance) is touched.

        I-deepfix-004 STEP B2 (gated upstream by PG_PDF_CITED_WORK_SLICE;
        ``page_anchor`` default None => byte-identical): when ``page_anchor`` is
        set on a multi-page doc, the PyMuPDF (fitz) fallback path below extracts
        the cited work as a page SLICE starting at page ``page_anchor`` (1-indexed
        -> ``doc[page_anchor-1]``) forward — stopping at ``page_end`` when known,
        else accumulating under the EXISTING char budget (the caller's 50 000-char
        cap, surfaced as ``_PDF_EXTRACT_CHAR_CAP``; no new page-count window). If
        ``page_anchor`` exceeds the page count the whole-doc extraction runs
        (fail-open). ``strip_pdf_frontmatter`` still runs on the slice (in the
        caller's PDF branch). The docling / mineru paths are unchanged — for the
        big combined-issue PDFs this targets they are OOM-gated to this fitz path.
        """
        import tempfile

        def _trace_extractor(
            backend: str, status: str, latency_ms: float, **meta: object
        ) -> None:
            """U19: authoritative record of which PDF extractor ACTUALLY ran.

            The mineru25 wrapper logs a ``selected_extractor=docling`` DEGRADE
            row when it falls through, but the TRUE final extractor (docling
            vs PyMuPDF) is only known here — so a run whose docling-OOM gate
            skipped docling and used PyMuPDF was mislabeled ``docling`` in the
            manifest. Emit the ground-truth extractor. Fail-safe: a tracer
            error can never break extraction (observability only)."""
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
                    selected_extractor=backend,
                    **meta,
                )
            except Exception as _exc:  # noqa: BLE001 — observability must not abort
                logger.debug("[ACCESS] U19: extractor trace skipped: %s", str(_exc)[:80])

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
        # Env overrides (a threshold of <= 0 DISABLES that guard — see U19):
        #   PG_MAX_DOCLING_PDF_BYTES (default 5MB; <=0 = unlimited)
        #   PG_MAX_DOCLING_PDF_PAGES (default 40 pages; <=0 = unlimited)
        max_docling_bytes = int(
            os.getenv("PG_MAX_DOCLING_PDF_BYTES", str(5 * 1024 * 1024))
        )
        max_docling_pages = int(
            os.getenv("PG_MAX_DOCLING_PDF_PAGES", "40")
        )

        # I-deepfix-001 U19 (#1344): a threshold of <= 0 means "no limit"
        # (the standard escape-hatch idiom already used by the mineru25 circuit
        # breaker at PG_MINERU25_CIRCUIT_THRESHOLD <= 0). The prior code treated
        # 0 as a LITERAL cap, so PG_MAX_DOCLING_PDF_BYTES=0 made
        # `len(pdf_bytes) > 0` true for EVERY non-empty PDF -> docling was ALWAYS
        # skipped and every clinical PDF silently fell to flat PyMuPDF text
        # (which mangles tables). Guarding each check on `> 0` lets a 0/negative
        # threshold mean unlimited so docling actually runs when intended.
        _skip_docling_reason = None
        if max_docling_bytes > 0 and len(pdf_bytes) > max_docling_bytes:
            _skip_docling_reason = f"bytes={len(pdf_bytes)}>{max_docling_bytes}"
        elif max_docling_pages > 0:
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
                    # U19: record the REAL extractor that produced the text.
                    _trace_extractor("docling", "ok", 0.0, chars=len(docling_text))
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
            _page_count = doc.page_count
            # I-deepfix-004 STEP B2: cited-work page slice. Fires ONLY when a
            # page anchor was resolved (STEP B1) AND the doc is multi-page AND
            # the anchor is within range; otherwise the whole-doc extraction
            # below runs byte-identically (also the fail-open path when
            # page_anchor > page_count).
            if (
                page_anchor is not None
                and _page_count > 1
                and 1 <= page_anchor <= _page_count
            ):
                start_idx = page_anchor - 1  # 1-indexed anchor -> 0-indexed page
                _end_valid = page_end is not None and page_end >= page_anchor
                # page_end is 1-indexed INCLUSIVE; clamp to the real page count.
                stop_idx = min(page_end, _page_count) if _end_valid else _page_count
                _acc_chars = 0
                for _pi in range(start_idx, stop_idx):
                    _ptext = doc[_pi].get_text()
                    pages_text.append(_ptext)
                    _acc_chars += len(_ptext)
                    # No explicit end page: accumulate forward only until the
                    # existing char budget (NOT a new page-count window).
                    if not _end_valid and _acc_chars >= _PDF_EXTRACT_CHAR_CAP:
                        break
                logger.info(
                    "[B2-SLICE] cited-work page slice pages %d..%d of %d (%d chars) url=%s",
                    page_anchor, min(stop_idx, _page_count), _page_count,
                    _acc_chars, url[:60],
                )
                # I-deepfix-004 F2/B3: SLICE-IDENTITY VERIFICATION. A PRINTED-page
                # anchor (DOI suffix) used as a physical index can slice a DIFFERENT
                # article from an issue PDF. Confirm the slice IS the cited work; if
                # unverifiable, DO NOT adopt it — recover the whole doc (kept +
                # disclosed downstream, never a wrong-content adoption, §-1.3). A
                # `#page=N` fragment anchor is physical and trusted (never verified).
                if (
                    anchor_is_printed_page
                    and pdf_slice_identity_verify_enabled()
                    and not _slice_identity_verified(
                        "\n\n".join(pages_text), page_anchor, cited_title
                    )
                ):
                    logger.warning(
                        "[B3-SLICE-IDENTITY] slice_unverified=true printed_start_page=%d "
                        "pages=%d..%d of %d url=%s — cited-work identity NOT confirmed at "
                        "the slice top; NOT adopting the printed-page slice, recovering "
                        "whole doc (kept+disclosed, no drop)",
                        page_anchor, page_anchor, min(stop_idx, _page_count),
                        _page_count, url[:60],
                    )
                    pages_text = [doc[_i].get_text() for _i in range(_page_count)]
            else:
                for page in doc:
                    pages_text.append(page.get_text())
            doc.close()

            import os as _os
            _os.unlink(tmp_path)

            full_text = "\n\n".join(pages_text)
            _stripped = full_text.strip()
            # U19: PyMuPDF actually ran — record it as the REAL extractor so the
            # manifest no longer mislabels a PyMuPDF fallback as "docling".
            _trace_extractor(
                "pymupdf", "ok" if _stripped else "fail", 0.0, chars=len(_stripped)
            )
            return _stripped
        except ImportError:
            logger.warning("[ACCESS] FIX-GAP4: PyMuPDF not installed, PDF extraction unavailable")
            _trace_extractor("pymupdf", "fail", 0.0, error="pymupdf_not_installed")
            return ""
        except Exception as exc:
            logger.warning("[ACCESS] FIX-GAP4: PDF extraction error: %s", str(exc)[:100])
            _trace_extractor("pymupdf", "fail", 0.0, error=str(exc)[:120])
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
                    # I-fetchclean-001 B2: ask Jina Reader to drop chrome elements at the
                    # SOURCE via the supported ``X-Remove-Selector`` header so nav/header/
                    # footer/aside never enter the pipe. Defense-in-depth — B1 remains the
                    # guarantee (covers crawl4ai/Zyte/httpx too). Empty ⇒ header NOT sent ⇒
                    # byte-identical request.
                    _jina_remove_selector = os.getenv(
                        "PG_JINA_REMOVE_SELECTOR", "nav,header,footer,aside"
                    ).strip()
                    if _jina_remove_selector:
                        headers["X-Remove-Selector"] = _jina_remove_selector

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
            # default is 90 (UNIT 6 WAVE-B: cap the wedged mineru-PDF worker so a 300s hang
            # can no longer exceed the ~90s abandon-join and hold its in-flight slot forever).
            # I-deepfix-001 B2 (wave-2): page-SCALE the flat floor. Unset
            # PG_MINERU25_TIMEOUT_PER_PAGE_S => returns the floor unchanged =>
            # byte-identical. The fetch-deadline cap below still applies, so at
            # relaunch the operator raises PG_FETCH_DEADLINE_SECONDS to let a big
            # PDF actually use the scaled budget (the inner-subprocess wall is not
            # so capped and takes the scaled value directly).
            _raw_mineru_to = _mineru25_timeout_seconds(
                pdf_bytes, float(os.getenv("PG_MINERU25_TIMEOUT_S", "90"))
            )
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
        """W4 winner: MinerU 2.5 VLM PDF -> markdown via the PROVEN dedicated-GPU
        ``mineru-vllm-server`` + the ``vlm-http-client`` subprocess protocol.

        REWRITE (I-deepfix-001 Box-C S1b): the pipeline no longer imports MinerU or
        runs ``do_parse`` in the pipeline process. It shells out to the isolated-
        venv ``mineru`` CLI in ``vlm-http-client`` mode — the EXACT transport that
        produced the real Box-A extraction (13/13 pages, ~36s, 6 reconstructed
        HTML ``<table>`` cells Docling loses):

            mineru -p <pdf> -o <out> -b vlm-http-client -u <server_url> -l <lang>

        The CLI runs in its OWN venv (the prod venv does NOT ship mineru) and its
        OWN process, so pypdfium2 page rasterization (process-global, non-thread-
        safe: the SIGSEGV that killed drb_78/drb_90) and the process-singleton VLM
        client are isolated in the CHILD process. The heavy VLM inference runs on
        the resident ``mineru-vllm-server`` (bounded on the dedicated GPU card);
        this process loads no model and holds no GPU lock. A child crash is a
        non-zero exit that degrades LOUDLY to Docling (never a pipeline crash).

        (The earlier httpx POST to ``mineru-api`` ``/file_parse`` targeted a server
        that was never launched or proven; the install proof launched
        ``mineru-vllm-server``, which serves the OpenAI-compatible API — NOT
        ``/file_parse`` — so that client 404'd every PDF. This aligns the client to
        the server that was actually proven.)

        TRANSPORT-ONLY / faithfulness-neutral: the returned markdown is the CLI's
        verbatim output — byte-for-byte what ``strict_verify`` later grounds. No
        faithfulness gate (strict_verify / NLI / 4-role / provenance) is touched;
        only HOW the text is obtained changes.

        FAIL LOUD (LAW II / LAW VI): the backend + server URL + CLI path come from
        ``resolve_mineru_backend`` (env > YAML), which RAISES when ``vlm-http-
        client`` is selected without a server URL. A missing URL, a missing CLI, a
        non-zero exit, or no markdown output RAISES so the async wrapper degrades
        LOUDLY to Docling and the circuit breaker counts the health failure —
        never a silent in-process fall-back (that re-creates the CUBLAS OOM this
        fix removes).

        Returns the markdown string (tables + sections preserved), or ``""`` when
        the CLI produced no markdown (a per-PDF content outcome the async wrapper
        treats as a disclosed thin-output Docling fallback).
        """
        import shutil
        import subprocess
        import tempfile
        from pathlib import Path as _Path

        from src.polaris_graph.scale.mineru_vllm_config import resolve_mineru_backend

        # Resolve transport config (env > YAML). Fail-loud contract: selecting
        # ``vlm-http-client`` without a server URL raises MineruBackendConfigError
        # here (the operator-locked no-silent-fallback rule); it propagates to the
        # async wrapper's LOUD Docling degrade.
        cfg = resolve_mineru_backend()
        server_url = (cfg.server_url or "").strip().rstrip("/")
        if not server_url:
            # No server URL: the in-process path is RETIRED, so there is nothing
            # to fall back to in-process. Raise so the wrapper degrades LOUDLY to
            # Docling (disclosed, never a silent capability downgrade).
            raise RuntimeError(
                "mineru25 vlm-http-client: no server URL configured "
                "(PG_MINERU25_SERVER_URL or server_url in "
                "config/serving/mineru_vllm_server.yaml). The in-process mineru "
                "path is retired (pypdfium2 / GPU-lock crash class); refusing to "
                "silently fall back to in-process — degrade LOUDLY to Docling."
            )

        # Resolve the isolated-venv mineru CLI (env > YAML > PATH). The prod venv
        # does NOT ship mineru; the CLI must be reachable, else degrade LOUD (no
        # silent capability downgrade to a lesser extractor).
        cli = (cfg.client_cli or "").strip() or "mineru"
        cli_path = cli if os.path.isabs(cli) else (shutil.which(cli) or "")
        if not cli_path or not os.path.exists(cli_path):
            raise RuntimeError(
                f"mineru25 vlm-http-client: mineru CLI not found (resolved "
                f"{cli!r} -> {cli_path!r}). Set PG_MINERU25_CLI_PATH (or "
                f"client_cli in config/serving/mineru_vllm_server.yaml) to the "
                f"isolated-venv mineru binary (e.g. /root/mineru_svc/bin/mineru). "
                f"Refusing to silently degrade — degrade LOUDLY to Docling."
            )

        lang = os.getenv("PG_MINERU25_LANG", "en").strip() or "en"
        # Finite-generous subprocess timeout — never infinite (a hung CLI/server
        # must not pin the fetch-worker thread). The outer async wait_for already
        # bounds this to the per-URL fetch deadline; this is the inner belt.
        # I-deepfix-001 B2 (wave-2): page-SCALE the inner subprocess wall too. Unset
        # PG_MINERU25_TIMEOUT_PER_PAGE_S => returns the resolved floor unchanged =>
        # byte-identical. This inner belt is NOT bounded by the fetch deadline, so a
        # large PDF gets its full proportional budget here (the outer async wall is
        # separately capped by PG_FETCH_DEADLINE_SECONDS).
        _http_floor = float(
            os.getenv(
                "PG_MINERU25_HTTP_TIMEOUT_S",
                os.getenv("PG_MINERU25_TIMEOUT_S", "90"),
            )
        )
        timeout_s = _mineru25_timeout_seconds(pdf_bytes, _http_floor)

        with tempfile.TemporaryDirectory(prefix="mineru25_") as _td:
            tdp = _Path(_td)
            stem = "doc"
            pdf_path = tdp / f"{stem}.pdf"
            pdf_path.write_bytes(pdf_bytes)
            out_dir = tdp / "out"
            out_dir.mkdir()

            argv = cfg.client_cli_argv(str(pdf_path), str(out_dir), lang)

            # Child env: strip PYTHONPATH / VIRTUAL_ENV so the prod venv can never
            # shadow the isolated mineru venv (the CLI shebang pins its own
            # interpreter). The CLI rasterizes on CPU and sends images to the
            # remote GPU server, so it needs no local card — but we leave
            # CUDA_VISIBLE_DEVICES untouched (the proven Box-A run inherited it and
            # the http-client backend loads no local model).
            child_env = {
                k: v
                for k, v in os.environ.items()
                if k not in ("PYTHONPATH", "VIRTUAL_ENV", "PYTHONHOME")
            }

            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                env=child_env,
                cwd=str(tdp),
            )
            if proc.returncode != 0:
                # Non-zero exit = a genuine mineru HEALTH failure (CLI/server
                # error, child crash). Raise so the async wrapper degrades LOUDLY
                # to Docling and the circuit breaker counts it.
                _tail = (proc.stderr or proc.stdout or "")[-600:]
                raise RuntimeError(
                    f"mineru vlm-http-client CLI exited {proc.returncode} "
                    f"(server {server_url}): {_tail}"
                )

            # MinerU writes the markdown to <out>/<stem>/vlm/<stem>.md. Prefer the
            # stem-matched file; fall back to the largest .md anywhere under out.
            md_files = sorted(out_dir.rglob("*.md"))
            if not md_files:
                # A clean exit with no markdown is a per-PDF CONTENT outcome (e.g.
                # a landing stub) — the async wrapper treats "" as a disclosed
                # thin-output Docling fallback (NOT a health failure).
                return ""
            chosen = None
            for f in md_files:
                if f.stem == stem:
                    chosen = f
                    break
            if chosen is None:
                chosen = max(md_files, key=lambda f: f.stat().st_size)
            md = chosen.read_text(encoding="utf-8", errors="replace")
            # VERBATIM pass-through — the CLI's markdown is returned unchanged.
            return md.strip() if isinstance(md, str) else ""

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
        # I-fetch-005 (#1344) FIX 2: a TERMINAL hard-block class (akamai_access_denied) is
        # DETERMINISTIC per url — cache it so a LATER fetch of the SAME url short-circuits the
        # whole cascade (no 60s+ re-walk of dead backends). §-1.3: the source is NOT dropped —
        # an unfetched source is retained downstream at ZERO weight. Only the hardest class is
        # cached (a JS/challenge wall is NOT terminal — a browser backend can still pass it).
        if klass in _TERMINAL_BLOCK_CLASSES and terminal_block_fastskip_enabled():
            _record_terminal_block(url)
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
        # I-fetch-005 iter-2 (Fable): this cascade reached a CLEAN winner for `result.url`, so
        # the url is provably fetchable. If a mid-cascade hop flagged it terminal
        # (akamai_access_denied) and populated the terminal-block cache, that entry is now
        # STALE — discard it so a LATER fetch of this same url is not wrongly fast-skipped to
        # failure. All fetch helpers preserve the original requested url on `result.url`, so
        # this clears exactly the key `_is_block_page`/`_record_terminal_block` cached.
        _discard_terminal_block(getattr(result, "url", "") or "")
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
