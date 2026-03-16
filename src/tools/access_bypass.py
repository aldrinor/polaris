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
import logging
import os
import re
import sys
import time as _time_module
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

# RC-9: Circuit breaker for fetch providers.
# After N consecutive failures, skip the provider for a cooldown period.
_jina_consecutive_failures: int = 0
_jina_circuit_open_until: float = 0.0
_firecrawl_consecutive_failures: int = 0
_firecrawl_circuit_open_until: float = 0.0
# FIX-G: Raised defaults — threshold 5→8, cooldown 60→120s for transient tolerance
_CIRCUIT_BREAKER_THRESHOLD = int(os.getenv("PG_CIRCUIT_BREAKER_THRESHOLD", "8"))
_CIRCUIT_BREAKER_COOLDOWN = float(os.getenv("PG_CIRCUIT_BREAKER_COOLDOWN", "120.0"))

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
_CRAWL4AI_CIRCUIT_BREAKER_THRESHOLD = int(
    os.getenv("PG_CRAWL4AI_CIRCUIT_BREAKER_THRESHOLD", "3")
)
_CRAWL4AI_CIRCUIT_BREAKER_COOLDOWN = float(
    os.getenv("PG_CRAWL4AI_CIRCUIT_BREAKER_COOLDOWN", "120.0")
)

# ---------------------------------------------------------------------------
# Firecrawl free-plan hardening: rate limiter + credit tracker
# ---------------------------------------------------------------------------

_firecrawl_last_request_time: float = 0.0
_firecrawl_credits_used: int = 0

# Load config from env (imported at module level for speed)
_FIRECRAWL_MIN_INTERVAL = float(os.getenv("FIRECRAWL_MIN_INTERVAL_SECONDS", "6.0"))
_FIRECRAWL_MONTHLY_QUOTA = int(os.getenv("FIRECRAWL_MONTHLY_QUOTA", "500"))
_FIRECRAWL_WARN_PCT = float(os.getenv("FIRECRAWL_WARN_THRESHOLD_PCT", "0.80"))


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

        # Paywall detection patterns
        self.paywall_patterns = [
            r"subscribe.*to.*read",
            r"sign.*in.*to.*access",
            r"purchase.*article",
            r"paywall",
            r"members.*only",
            r"premium.*content",
            r"unlock.*full.*article",
        ]

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
        # FIX-QM2: Run Crawl4AI, Jina and Firecrawl concurrently -- first success wins
        logger.info("[ACCESS] FIX-QM2: Concurrent Crawl4AI+Jina+Firecrawl for %s", url[:60])

        # Build concurrent task list: Crawl4AI first (free/local), then Jina, then Firecrawl
        concurrent_tasks: list = []

        crawl4ai_enabled = os.getenv("PG_CRAWL4AI_ENABLED", "1") == "1"
        if crawl4ai_enabled:
            concurrent_tasks.append(self._try_crawl4ai(url))

        concurrent_tasks.append(self._try_jina_reader(url))

        firecrawl_enabled = os.getenv("PG_FIRECRAWL_ENABLED", "1") == "1"
        firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY")
        if firecrawl_enabled and firecrawl_api_key and _firecrawl_has_credits():
            concurrent_tasks.append(self._try_firecrawl(url))

        # FIX-039/B.3: Add trafilatura to concurrent group (was dead-code fallback)
        if os.getenv("PG_TRAFILATURA_ENABLED", "0") == "1":
            concurrent_tasks.append(self._try_trafilatura(url))

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

        for r in concurrent_results:
            if isinstance(r, AccessResult) and r.success and not self._detect_paywall(r.content):
                # FIX-045B: Strip navigation boilerplate before returning
                r.content = _strip_navigation_boilerplate(r.content)
                logger.info(
                    "[ACCESS] FIX-QM2: %s won concurrent fetch for %s (%d chars)",
                    r.access_method, url[:60], len(r.content),
                )
                return r

        # FIX-039/B.3: Trafilatura now runs in concurrent group above (no standalone fallback)

        # Direct HTTP fetch with markdown Accept header (FIX-D6/A3)
        logger.info("[ACCESS] Trying direct fetch for %s", url[:60])
        timeout_occurred = False
        direct_result = await self._direct_fetch(url)

        if direct_result.success and not self._detect_paywall(direct_result.content):
            # FIX-045B: Strip navigation boilerplate
            direct_result.content = _strip_navigation_boilerplate(direct_result.content)
            return direct_result

        # Track if direct fetch failed due to timeout for retry logic (FIX-D5)
        if not direct_result.success and "timeout" in str(direct_result.metadata.get("error", "")).lower():
            timeout_occurred = True

        logger.info("[ACCESS] Direct access blocked for %s, trying alternatives", url[:80])

        # Try Archive.org
        if self.use_archive_org:
            logger.info("[ACCESS] Trying Archive.org for %s", url[:60])
            archive_result = await self._try_archive_org(url)
            if archive_result.success:
                # FIX-045B: Strip navigation boilerplate
                archive_result.content = _strip_navigation_boilerplate(archive_result.content)
                return archive_result

        # Try institutional proxy
        if self.proxy:
            logger.info("[ACCESS] Trying proxy for %s", url[:60])
            proxy_result = await self._try_proxy(url)
            if proxy_result.success:
                # FIX-045B: Strip navigation boilerplate
                proxy_result.content = _strip_navigation_boilerplate(proxy_result.content)
                return proxy_result

        # FIX-D5: Retry once on timeout errors before giving up
        if timeout_occurred:
            logger.info("[ACCESS] Retrying direct fetch after timeout for %s", url[:60])
            await asyncio.sleep(3)
            retry_result = await self._direct_fetch(url)
            if retry_result.success and not self._detect_paywall(retry_result.content):
                # FIX-045B: Strip navigation boilerplate
                retry_result.content = _strip_navigation_boilerplate(retry_result.content)
                return retry_result

        # SF-40: Log total failure at WARNING (was completely silent)
        logger.warning("[ACCESS] ALL access methods exhausted for %s", url[:80])
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
            crawler_config = CrawlerRunConfig(
                page_timeout=page_timeout_ms,
                wait_until="domcontentloaded",
            )

            logger.info(
                "[polaris graph] CRAWL4AI: Fetching %s (timeout=%ds)",
                _safe_log_str(url, 80),
                timeout_seconds,
            )

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

            markdown_content = result.markdown or ""

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

            text = await loop.run_in_executor(
                None,
                lambda: trafilatura.extract(
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

        # FIX-JINA: Jina concurrency semaphore (free tier = 2 concurrent)
        global _jina_semaphore
        if _jina_semaphore is None:
            jina_concurrency = int(os.getenv("PG_JINA_CONCURRENCY", "2"))
            _jina_semaphore = asyncio.Semaphore(jina_concurrency)

        async with _jina_semaphore:
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

    def _detect_paywall(self, content: str) -> bool:
        """Detect if content is behind paywall."""
        content_lower = content.lower()

        for pattern in self.paywall_patterns:
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

        return False

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
