"""GAP-1: Dynamic package installation with safety whitelist.

Allows the LLM to request Python packages during analysis. Only packages
on the approved whitelist are installed. This closes the gap with Claude Code
which can pip install anything.

The whitelist contains scientific/analysis packages that are safe for research:
no system-level packages, no network libraries, no code execution tools.
"""

import logging
import os
import subprocess
import sys

logger = logging.getLogger("polaris_graph")

# Approved packages for research analysis (LAW VI: from env with defaults)
_DEFAULT_WHITELIST = (
    "pdfplumber,tabula-py,networkx,scikit-learn,statsmodels,seaborn,"
    "plotly,wordcloud,textblob,spacy,gensim,pingouin,lifelines,"
    "prophet,pymannkendall,ruptures,kneed,adjustText,squarify,"
    "openpyxl,xlrd,pyarrow,fastparquet"
)
_WHITELIST = frozenset(
    p.strip() for p in
    os.getenv("PG_APPROVED_PACKAGES", _DEFAULT_WHITELIST).split(",")
    if p.strip()
)
_INSTALL_TIMEOUT = int(os.getenv("PG_PACKAGE_INSTALL_TIMEOUT", "120"))
_installed_cache: set[str] = set()  # Track what's already installed this session


def get_approved_packages() -> list[str]:
    """Return the list of approved packages for LLM reference."""
    return sorted(_WHITELIST)


def is_approved(package_name: str) -> bool:
    """Check if a package is on the approved whitelist."""
    # Normalize: strip version specifiers
    base_name = package_name.split("==")[0].split(">=")[0].split("<=")[0].split("[")[0].strip().lower()
    return base_name in _WHITELIST or base_name.replace("-", "_") in _WHITELIST or base_name.replace("_", "-") in _WHITELIST


def safe_install(packages: list[str]) -> dict:
    """Install packages from the approved whitelist.

    Args:
        packages: List of package names to install.

    Returns:
        {
            "installed": [str],      # Successfully installed
            "already_installed": [str],  # Already available
            "rejected": [str],       # Not on whitelist
            "failed": [str],         # Install failed
            "errors": [str],         # Error messages
        }
    """
    result = {
        "installed": [],
        "already_installed": [],
        "rejected": [],
        "failed": [],
        "errors": [],
    }

    for pkg in packages:
        base_name = pkg.split("==")[0].split(">=")[0].split("<=")[0].split("[")[0].strip()

        # Check whitelist
        if not is_approved(base_name):
            result["rejected"].append(pkg)
            result["errors"].append(f"'{pkg}' not on approved whitelist. Approved: {', '.join(sorted(list(_WHITELIST))[:10])}...")
            logger.warning("[package_installer] Rejected '%s' — not on whitelist", pkg)
            continue

        # Check if already installed
        if base_name in _installed_cache:
            result["already_installed"].append(pkg)
            continue

        try:
            __import__(base_name.replace("-", "_"))
            result["already_installed"].append(pkg)
            _installed_cache.add(base_name)
            continue
        except ImportError:
            pass

        # Install
        try:
            logger.info("[package_installer] Installing '%s'...", pkg)
            proc = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--quiet", "--no-input", pkg],
                capture_output=True, text=True,
                timeout=_INSTALL_TIMEOUT,
            )
            if proc.returncode == 0:
                result["installed"].append(pkg)
                _installed_cache.add(base_name)
                logger.info("[package_installer] Installed '%s' successfully", pkg)
            else:
                result["failed"].append(pkg)
                result["errors"].append(f"pip install {pkg} failed: {proc.stderr[:200]}")
                logger.warning("[package_installer] Failed to install '%s': %s", pkg, proc.stderr[:200])
        except subprocess.TimeoutExpired:
            result["failed"].append(pkg)
            result["errors"].append(f"pip install {pkg} timed out after {_INSTALL_TIMEOUT}s")
        except Exception as exc:
            result["failed"].append(pkg)
            result["errors"].append(f"pip install {pkg} error: {str(exc)[:200]}")

    return result


def ensure_available(packages: list[str]) -> bool:
    """Ensure packages are available, installing if needed. Returns True if all available."""
    result = safe_install(packages)
    return len(result["rejected"]) == 0 and len(result["failed"]) == 0
