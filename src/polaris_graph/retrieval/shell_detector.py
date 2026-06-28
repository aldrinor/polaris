"""I-beatboth-001 (#1276) — fetch-shell / web-boilerplate detector (pure leaf module).

WHY THIS EXISTS
---------------
run7 (drb_78 Parkinson's/DBS) shipped junk web-boilerplate spans as VERIFIED cited
clinical findings (state/beatboth_campaign/PHASE1_ISSUES.md P0-1): a 476-char CAPTCHA /
Cloudflare "Just a moment… Performing security verification… verifies you are not a bot"
page grounded 6 top-of-report units, plus cookie-consent banners, an HTTP 404, a
language-picker nav menu, citation-manager UI chrome ("Download Citation"/CrossRef), and
YouTube related-video sidebars — all rendered as corroborated findings. They passed because
the report prose verbatim-copies the junk span, so the numeric/content-overlap/entailment
checks trivially hold (the "self-citation hole"). This is the I-bug-775 fetch-shell class.

The existing ``live_retriever._is_access_denial_stub`` / ``is_content_starved`` runs at
RETRIEVAL / refetch time on the full fetched body. But a shell already in the corpus (or a
shell reloaded UNTOUCHED on resume — resume_refetch.py STILL-SHELL) never gets re-checked at
the per-cited-span faithfulness gate (``verify_sentence_provenance``). This module is the
single source of truth for shell vocabulary so the SAME detector covers both layers (LAW V:
one list, no drift — the markers were historically bolted on in waves I-run11-010 then RC-C,
which is exactly the divergence this consolidation prevents).

POSTURE (binding)
-----------------
* STRICTER gate only — a shell can NEVER ground a claim; it is fail-closed in
  ``verify_sentence_provenance``. Faithfulness is TIGHTENED, never relaxed.
* DETERMINISTIC + pure: no LLM, no network, no row mutation. snake_case, LAW VI env knobs.
* HIGH-PRECISION: every default-on marker is either a challenge-PAGE-specific phrase that
  never appears in real article prose, or an ALL-of co-occurrence tuple. A loose phrase that
  could appear in a legitimate clinical/methods/bibliography span is gated to a SHORT body
  (so a full article that merely mentions the word is never false-dropped) — a false-drop
  would itself be a §-1.3 breadth loss.
"""

from __future__ import annotations

import os

# ─────────────────────────────────────────────────────────────────────────────
# Shell vocabulary — THE single source of truth (LAW V). ``live_retriever``'s
# constants re-point here; do not redefine them there.
# ─────────────────────────────────────────────────────────────────────────────

# Bot-challenge / access-denial markers (I-run11-010 #1056 S1; RC-C TI-05/06). VERY specific
# access-denial phrasing — applied only to a SHORT body so a full article that merely quotes
# one is never false-dropped.
ACCESS_DENIAL_MARKERS: tuple[str, ...] = (
    "are you a robot",
    "captcha challenge",
    "captcha verification",
    "complete the captcha",
    "verify you are human",
    "verifying you are human",
    "confirm you are a human",
    "please confirm you are",
    "access denied",
    "enable javascript and cookies",
    "unusual traffic",
    "checking your browser",
    # Modern Cloudflare / anti-bot interstitial phrasings (challenge-PAGE-specific).
    "security verification",
    "review the security of your connection",
    "needs to review the security",
    "this process is automatic",
    "请完成",  # CN: "please complete (the verification)"
    "人机验证",  # CN: "human-machine verification"
    # I-deepfix-001 B5 (2026-06-28) — modern anti-bot interstitial vendors. Each is
    # a challenge-PAGE-specific phrase that never constitutes article prose; gated to
    # a SHORT body so a security/IT paper merely naming a vendor is not false-dropped.
    "enable javascript and cookies to continue",  # Cloudflare managed-challenge body
    "just a moment...",                            # Cloudflare interstitial title
    "ddos protection by cloudflare",
    "datadome",                                    # DataDome block page
    "px-captcha",                                  # PerimeterX / HUMAN challenge
    "captcha-delivery.com",                        # DataDome CAPTCHA delivery host
    "powered by perimeterx",
    "please enable cookies",                       # generic bot-wall
    "additional security check is required",
    "blocked by network security",
)

# UNAMBIGUOUS challenge-page signatures that NEVER co-occur in real article prose, safe to
# match at ANY length (a long Cloudflare interstitial / enrichment-concatenated shell). Each
# entry is an ALL-of co-occurrence tuple.
CHALLENGE_PAGE_COOCCURRENCE: tuple[tuple[str, ...], ...] = (
    ("cloudflare", "ray id"),
    ("cloudflare", "performance & security"),
    ("cloudflare", "checking if the site connection is secure"),
    ("ddos protection by", "cloudflare"),
    # I-beatboth-001: the run-#7 anchor — "Just a moment..." + "security verification" +
    # "you are not a bot" is the exact Lancet CAPTCHA span (drb_78 key=625). ALL-of, so a real
    # article discussing bot detection cannot trip it.
    ("just a moment", "this page is displayed while the website verifies you are not a bot"),
    ("performing security verification", "protect against malicious bots"),
    # I-deepfix-001 B5 (2026-06-28) — Anubis proof-of-work anti-scraper wall (the
    # increasingly common open-source AI-scraper deterrent). Its interstitial copy
    # is unambiguous chrome that NEVER appears in real article prose; ALL-of so a
    # paper merely discussing scraping/PoW cannot trip it.
    ("anubis", "proof-of-work"),
    ("making sure you're not a bot", "scraping"),
    ("set up anubis", "protect the server"),
    ("scourge of ai companies", "aggressively scraping"),
    # Modern vendor block pages — vendor name + the block/verification CTA co-occur.
    ("datadome", "you have been blocked"),
    ("perimeterx", "press & hold"),
    ("verifying you are human", "needs to review the security of your connection"),
)

# I-beatboth-001 iter-2 (replay-found on the real drb_78 corpus) — ADDITIONAL any-length signatures
# consumed ONLY by the cited-span gate ``is_cited_span_shell`` (NOT by the retrieval-time
# ``is_access_denial_stub`` — kept separate so the retrieval gate stays byte-identical per the
# patch's stated invariant). The crawler HTTP-error shell wrapper: the fetch layer emits "Target
# URL returned error <4xx/5xx>" ONLY for an error page; paired ALL-of with "not found" this is a
# fetch-shell artifact that NEVER appears in genuine article prose. Verified across all 794 drb_78
# rows: fires on exactly the 2 real 404 shells (ev_540 @1500, ev_717 @6639) and ZERO real articles
# — empirical proof it is safe at ANY length, closing the run-#7 leak where the 6639-char
# conference-404 nav-page passed the short-body gate.
CITED_SPAN_ANY_LENGTH_COOCCURRENCE: tuple[tuple[str, ...], ...] = (
    ("target url returned error", "not found"),
)

# I-beatboth-001 — ADDITIONAL high-precision chrome shell classes beyond bot-walls. Each is an
# ALL-of co-occurrence tuple so it is chrome-specific and cannot fire on a clinical span that
# merely contains one of the words (the adversarial negatives: a methods span with
# "verification", a bibliography span with "crossref", a nutrition span with "cookie").
#
# PRECISION (I-beatboth-001 iter-2, Codex P1 #1): these chrome co-occurrence tuples are SHORT-BODY
# ONLY — they do NOT fire at any length. Codex's finding establishes that these phrases ("we use
# cookies"+"accept all", "download citation"+"crossref", …) DO appear in long real article bodies
# (verified on the real drb_78 corpus: ev_694/ev_679/ev_295/ev_693 are genuine DBS/Parkinson's
# articles carrying an incidental cookie / download-citation footer). There is therefore NO safe
# length-agnostic firing of these classes — distinguishing a verbose all-chrome page from a long
# article that discusses cookie policy needs content classification (alpha-ratio / NLI), which the
# pipeline already does at other layers, not a string heuristic here. So a chrome class fires ONLY
# on a SHORT body (the chrome IS the whole page); above the ceiling it does not fire and the long
# real article passes. The unambiguous bot-wall / crawler-error ``CHALLENGE_PAGE_COOCCURRENCE``
# signatures above remain any-length — those phrases never occur in real article prose.
SHELL_COOCCURRENCE: tuple[tuple[str, ...], ...] = (
    # Cookie-consent banners (NOT a bibliography line that says "cookie"): the consent CTA +
    # the policy/preferences chrome must co-occur.
    ("we use cookies", "accept all"),
    ("this website uses cookies", "cookie policy"),
    ("manage your cookie preferences", "accept"),
    ("cookies to improve your experience", "accept"),
    # Citation-manager / publisher UI chrome rendered as a "finding" (P1-10 metadata-as-claim:
    # CrossRef/Scite "Download Citation" website chrome). The download CTA + the manager names.
    ("download citation", "crossref"),
    ("export citation", "endnote"),
    ("add to citation manager", "mendeley"),
    ("track citations", "crossref"),
    # Social-media boilerplate sidebars (YouTube related-video chrome, comment-wall footers).
    ("new comments cannot be posted", "votes cannot be cast"),
    ("subscribe", "watch later", "share"),
    ("autoplay is paused", "up next"),
)

# Single-phrase shell markers that ARE challenge/error/chrome-specific but might appear in a
# longer legitimate page, so they fire ONLY on a SHORT body (same safety shape as
# ACCESS_DENIAL_MARKERS). Default-on is justified because each phrase is page-chrome that never
# constitutes a clinical claim AND the short-body gate prevents false-dropping a real article.
SHORT_BODY_SHELL_MARKERS: tuple[str, ...] = (
    # HTTP error / not-found landing pages.
    "404 not found",
    "404 - not found",
    "page not found",
    "403 forbidden",
    "error 404",
    "error 403",
    "the requested url was not found",
    "this page could not be found",
    "pàgina no trobada",  # CA: "page not found" (the run-#7 Catalan 404)
    "página no encontrada",  # ES: "page not found"
    # Language-selector / nav-only pages (a bare list of language names is not article prose).
    "select your language",
    "choose your language",
    # Subscription / paywall interstitials with no body.
    "subscribe to continue reading",
    "to continue reading this article",
    "create a free account to continue",
)

# I-beatboth-001 iter-2 (Codex P1 #2): the subset of single phrases that are NOT shell-specific
# enough to fail-close a cited span on their own. Each of these can appear ONCE inside a
# legitimate short abstract / methods / nav-bearing real page, so the cited-span gate requires
# them to be CORROBORATED — fire only when (a) ANOTHER independent shell signal co-occurs
# (multi-signal), OR (b) the body is VERY short (a bare stub page, governed by a much tighter
# ceiling than the 3000-char one used for the unambiguous strong phrases). A real 1500-char
# abstract that says "access denied" once trips neither clause and passes. Drawn from
# ACCESS_DENIAL_MARKERS / SHORT_BODY_SHELL_MARKERS — this is a VIEW for the cited-span gate's
# precision logic, NOT a separate vocabulary (LAW V: the strings still live in the shared tuples,
# so the retrieval-time ``is_access_denial_stub`` stays byte-identical).
AMBIGUOUS_SHELL_PHRASES: frozenset[str] = frozenset(
    {
        "access denied",  # legit: "access denied to the dataset was reported in 12% of cases"
        "security verification",  # legit: a methods span describing outcome/security verification
        "this process is automatic",  # legit: prose describing an automated clinical workflow
        "change language",  # legit: nav chrome word; appears in real multilingual pages
    }
)

# LAW VI — env knobs, no magic numbers.
# Master kill-switch for the CITED-SPAN shell gate in verify_sentence_provenance. Default ON
# (this is a faithfulness-TIGHTENING gate); set PG_CITED_SPAN_SHELL_DETECT=0 to revert to the
# byte-identical pre-#1276 behaviour (a shell span verifies on numeric/content overlap as before).
_ENV_ENABLED = "PG_CITED_SPAN_SHELL_DETECT"
_OFF_VALUES = frozenset({"0", "false", "off", "no", "disabled"})

# Max body length at which a STRONG (unambiguous) short-body single-phrase marker may fire (the
# bot-wall + http-error + nav classes). A real article body is far longer; this guards against
# false-dropping a full article that merely quotes one phrase. Shared default with live_retriever's
# prior 3000.
_ENV_SHORT_BODY_MAX = "PG_SHELL_SHORT_BODY_MAX_CHARS"
_DEFAULT_SHORT_BODY_MAX = 3000

# I-beatboth-001 iter-2 — chrome ceiling for the SHELL_COOCCURRENCE classes (cookie / citation-UI /
# social). A genuine chrome shell is SHORT — a near-empty page whose whole body IS the widget
# (verified on the real drb_78 corpus: the genuine chrome shells are <=1500 chars, while the rows
# >800 carrying the same vocab are real articles with an incidental footer). A chrome class fires
# ONLY when the body is at or under this ceiling; above it the class does NOT fire and the long
# real article passes (no pure-string test can safely re-fire these on a long body — see the
# SHELL_COOCCURRENCE comment). This is a plain length gate, deliberately NOT a "dominance ratio":
# the ratio approach was dead code (matched-marker length can never reach 50% of an >800-char body)
# AND, per Codex P1 #1, no length-agnostic firing of these classes is safe.
_ENV_CHROME_MAX = "PG_SHELL_CHROME_MAX_CHARS"
_DEFAULT_CHROME_MAX = 800

# I-beatboth-001 iter-2 — the much-tighter ceiling under which a single AMBIGUOUS phrase may fire
# WITHOUT a corroborating second signal (a bare "Access Denied" stub page is tiny). A real
# abstract that says "access denied" once is well above this, so it is never false-dropped on a
# single ambiguous phrase.
_ENV_AMBIGUOUS_SHORT_BODY_MAX = "PG_SHELL_AMBIGUOUS_SHORT_BODY_MAX_CHARS"
_DEFAULT_AMBIGUOUS_SHORT_BODY_MAX = 200


def cited_span_shell_detect_enabled() -> bool:
    """True (default) ⇒ the cited-span shell gate fires in ``verify_sentence_provenance``.

    ``PG_CITED_SPAN_SHELL_DETECT=0`` (or off/false/no/disabled) ⇒ byte-identical pre-#1276
    behaviour. Read at call time so tests toggle without re-import.
    """
    return os.environ.get(_ENV_ENABLED, "1").strip().lower() not in _OFF_VALUES


def _env_int(name: str, default: int) -> int:
    """Read a positive int env knob (LAW VI). A bad/empty/non-positive value falls back to the
    safe default — never an unbounded ceiling that would let a long shell through, never a tiny
    one that would over-fire on a clinical abstract."""
    try:
        value = int(os.environ.get(name, default) or default)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _short_body_max_chars() -> int:
    """The body-length ceiling under which STRONG short-body single-phrase markers may fire."""
    return _env_int(_ENV_SHORT_BODY_MAX, _DEFAULT_SHORT_BODY_MAX)


def _chrome_max_chars() -> int:
    """The body-length ceiling under which a SHELL_COOCCURRENCE chrome class may fire (short-body
    only — above this a long real article carrying the same chrome vocab must pass)."""
    return _env_int(_ENV_CHROME_MAX, _DEFAULT_CHROME_MAX)


def _ambiguous_short_body_max_chars() -> int:
    """The much-tighter ceiling under which a single AMBIGUOUS phrase may fire without a co-signal."""
    return _env_int(_ENV_AMBIGUOUS_SHORT_BODY_MAX, _DEFAULT_AMBIGUOUS_SHORT_BODY_MAX)


def is_access_denial_stub(content: str, *, max_chars: int | None = None) -> bool:
    """True if ``content`` looks like a bot-challenge / access-denial page rather than article
    content. Mirrors the prior ``live_retriever._is_access_denial_stub`` byte-for-byte (the
    short-body markers fire only on a short body; the unambiguous Cloudflare co-occurrence
    signatures fire at any length), so re-pointing live_retriever here is behaviour-preserving.
    """
    if not content:
        return False
    low = content.lower()
    if any(all(tok in low for tok in combo) for combo in CHALLENGE_PAGE_COOCCURRENCE):
        return True
    ceiling = max_chars if max_chars is not None else _short_body_max_chars()
    if len(content.strip()) > ceiling:
        return False
    return any(marker in low for marker in ACCESS_DENIAL_MARKERS)


def _chrome_class_present(low: str, body_len: int) -> bool:
    """I-beatboth-001 iter-2 (Codex P1 #1) — True iff a SHELL_COOCCURRENCE chrome class is present
    AND the body is SHORT enough to be the chrome page itself. A genuine cookie / citation-UI /
    social chrome shell is a near-empty page whose whole body IS the widget; a long real article
    merely carries an incidental footer. Per Codex's finding these chrome phrases DO appear in long
    real article bodies, so there is no safe length-agnostic firing — the class fires ONLY on a
    short body. Above the ceiling the long real article passes (no false-drop = no §-1.3 breadth
    loss). This is a plain length gate, NOT a ratio: a ratio of matched-marker length to body length
    can never exceed 50% of an >800-char body (dead code), and no string ratio can distinguish a
    verbose all-chrome page from a long article discussing cookie policy — that needs the
    content/NLI classification the pipeline already applies at other layers."""
    if body_len > _chrome_max_chars():
        return False
    return any(all(tok in low for tok in combo) for combo in SHELL_COOCCURRENCE)


def _ambiguous_phrase_fires(low: str, body_len: int) -> bool:
    """I-beatboth-001 iter-2 (Codex P1 #2) — True iff an AMBIGUOUS single phrase ("access denied",
    "security verification", "this process is automatic", "change language") may fail-close a cited
    span. These are NOT shell-specific enough alone, so they require CORROBORATION: fire only when
    (a) a SECOND independent shell signal co-occurs (multi-signal), OR (b) the body is VERY short (a
    bare stub page, a much tighter ceiling than the strong-phrase 3000). A real abstract that says
    "access denied" once is above the tight ceiling and carries no second signal, so it passes."""
    present = [phrase for phrase in AMBIGUOUS_SHELL_PHRASES if phrase in low]
    if not present:
        return False
    # (b) bare stub page — very short body, a single ambiguous phrase is enough.
    if body_len <= _ambiguous_short_body_max_chars():
        return True
    # (a) multi-signal — a SECOND, independent shell signal must co-occur, AND the body must be
    # SHORT. Every corroboration branch is bounded by ``_short_body_max_chars()`` for the SAME reason
    # as the main path (Codex P1 #1): otherwise a long real article that happens to carry two
    # ambiguous phrases (plausible once generalized off-clinical: a security/IT/systems-methods paper
    # using "access denied" + "security verification"), or one ambiguous phrase plus an incidental
    # cookie footer, would be false-dropped here at ANY length — re-opening exactly the finding the
    # main path closed. A genuine corroborated stub is short; a long real article is not.
    if body_len > _short_body_max_chars():
        return False
    # second signal: another ambiguous phrase, a strong access-denial marker, an HTTP/nav marker, or
    # a (short-body) chrome class. A lone ambiguous phrase in a real short abstract trips none of it.
    if len(present) >= 2:
        return True
    strong_denial = [m for m in ACCESS_DENIAL_MARKERS if m not in AMBIGUOUS_SHELL_PHRASES]
    if any(marker in low for marker in strong_denial):
        return True
    if any(marker in low for marker in SHORT_BODY_SHELL_MARKERS):
        return True
    if _chrome_class_present(low, body_len):
        return True
    return False


def is_cited_span_shell(direct_quote: str) -> bool:
    """I-beatboth-001 (#1276) — True iff the cited source body is a fetch-shell / web-boilerplate
    page that can NEVER ground a clinical claim (CAPTCHA / security-verification interstitial,
    cookie-consent, HTTP 404/403, language-nav, citation-UI chrome, social-media boilerplate).

    DETERMINISTIC + HIGH-PRECISION (iter-2 hardening, Codex 2×P1):
      * The unambiguous any-length signatures — ``CHALLENGE_PAGE_COOCCURRENCE`` (bot-wall, shared
        with the retrieval gate) and ``CITED_SPAN_ANY_LENGTH_COOCCURRENCE`` (crawler HTTP-error
        wrapper, cited-span-only) — NEVER occur in real article prose, so they fire at ANY length
        (the 476-char run-#7 CAPTCHA span and the 6639-char conference-404 shell are both caught).
      * The chrome ``SHELL_COOCCURRENCE`` classes (cookie / citation-UI / social) fire ONLY on a
        SHORT body (``_chrome_class_present``). Per Codex P1 #1 these phrases DO appear in long real
        article bodies (the drb_78 corpus has 4 such genuine articles), so an incidental cookie
        footer / citation widget inside a long real article is NOT a shell and passes.
      * STRONG single-phrase markers (unambiguous bot-wall / http-error / nav / paywall) fire on a
        SHORT body. AMBIGUOUS phrases ("access denied", "security verification", "this process is
        automatic", "change language") require CORROBORATION — a second shell signal, or a
        much-shorter body — so a legit short abstract mentioning one of them once is NOT dropped
        (Codex P1 #2).

    A false-drop is itself a §-1.3 breadth loss, so the bias is toward PASS unless the body is
    clearly a shell. Used fail-closed in ``verify_sentence_provenance`` on each cited token's source
    ``direct_quote`` — a token whose source is a shell fails exactly like ``span_out_of_bounds``, so
    the sentence drops and the shell can never ride on a real co-token. This propagates to every
    render path (the SUPPORTS-only enrichment surfacing, ``verified_support_origin_count``,
    ``basket_verdict``) through the existing verify wiring; no separate render filter is needed.
    """
    if not direct_quote:
        return False
    low = direct_quote.lower()
    body_len = len(direct_quote.strip())
    # ANY-length unambiguous signatures: bot-wall challenge pages (shared with the retrieval gate)
    # + the cited-span-only crawler HTTP-error wrappers (never appear in real article prose).
    for combo in (*CHALLENGE_PAGE_COOCCURRENCE, *CITED_SPAN_ANY_LENGTH_COOCCURRENCE):
        if all(tok in low for tok in combo):
            return True
    # Chrome co-occurrence classes (cookie / citation-UI / social) — SHORT-body only (Codex P1 #1):
    # a long real article carrying the same chrome vocab as an incidental footer is NOT a shell.
    if _chrome_class_present(low, body_len):
        return True
    # STRONG short-body single-phrase markers (bot-wall, http-error, nav, paywall): fire only on a
    # short body so a real article is never false-dropped on a single incidental phrase. AMBIGUOUS
    # phrases are EXCLUDED here — they go through the corroboration path below.
    if body_len <= _short_body_max_chars():
        strong_denial = [m for m in ACCESS_DENIAL_MARKERS if m not in AMBIGUOUS_SHELL_PHRASES]
        if any(marker in low for marker in strong_denial):
            return True
        if any(marker in low for marker in SHORT_BODY_SHELL_MARKERS):
            return True
    # AMBIGUOUS single phrases — corroborated multi-signal OR very-short-body only (Codex P1 #2).
    if _ambiguous_phrase_fires(low, body_len):
        return True
    return False
