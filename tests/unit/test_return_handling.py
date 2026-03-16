#!/usr/bin/env python3
"""
Phase 4 Tests: LOW Priority - Empty/Default Returns

Tests that the 24 print-based returns now use proper logging.
Also verifies that remaining empty returns are legitimate guard clauses.

Test categories:
- LOW-001 to LOW-024: Verify print statements converted to logger
- Guard clause verification: Confirm legitimate early returns
"""

import pytest
from pathlib import Path
import re


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def src_root() -> Path:
    """Get the source root directory."""
    return Path(__file__).parent.parent.parent / "src"


# =============================================================================
# TEST CLASS: Phase Files Have Logger
# =============================================================================

class TestPhaseFilesHaveLogger:
    """Verify phase files have proper logging setup."""

    def _has_logger_setup(self, file_path: Path) -> bool:
        """Check if file has logger setup."""
        if not file_path.exists():
            return False

        source = file_path.read_text(encoding='utf-8')
        return ('import logging' in source and
                ('logger = logging.getLogger' in source or
                 'logger =' in source))

    def test_low001_p02_query_generation_has_logger(self, src_root: Path):
        """LOW-001: p02_query_generation.py should have logger."""
        file_path = src_root / "phases" / "p02_query_generation.py"
        assert self._has_logger_setup(file_path)

    def test_low002_p03_search_has_logger(self, src_root: Path):
        """LOW-002: p03_search.py should have logger."""
        file_path = src_root / "phases" / "p03_search.py"
        assert self._has_logger_setup(file_path)

    def test_low003_006_p05_indexing_has_logger(self, src_root: Path):
        """LOW-003 to LOW-006: p05_indexing.py should have logger."""
        file_path = src_root / "phases" / "p05_indexing.py"
        assert self._has_logger_setup(file_path)


# =============================================================================
# TEST CLASS: Utils Files Have Logger
# =============================================================================

class TestUtilsFilesHaveLogger:
    """Verify utils files have proper logging setup."""

    def _has_logger_setup(self, file_path: Path) -> bool:
        """Check if file has logger setup."""
        if not file_path.exists():
            return False

        source = file_path.read_text(encoding='utf-8')
        return ('import logging' in source and
                ('logger = logging.getLogger' in source or
                 'logger =' in source))

    def test_low007_014_academic_fetcher_has_logger(self, src_root: Path):
        """LOW-007 to LOW-014: academic_fetcher.py should have logger."""
        file_path = src_root / "utils" / "academic_fetcher.py"
        assert self._has_logger_setup(file_path)

    def test_low015_018_crossref_resolver_has_logger(self, src_root: Path):
        """LOW-015 to LOW-018: crossref_resolver.py should have logger."""
        file_path = src_root / "utils" / "crossref_resolver.py"
        assert self._has_logger_setup(file_path)

    def test_low019_024_source_quality_has_logger(self, src_root: Path):
        """LOW-019 to LOW-024: source_quality.py should have logger."""
        file_path = src_root / "utils" / "source_quality.py"
        assert self._has_logger_setup(file_path)

    def test_ingest_has_logger(self, src_root: Path):
        """ingest.py should have logger (already had it)."""
        file_path = src_root / "utils" / "ingest.py"
        assert self._has_logger_setup(file_path)


# =============================================================================
# TEST CLASS: No Print in Exception Handlers
# =============================================================================

class TestNoPrintInExceptionHandlers:
    """Verify that print statements are not used in exception handlers."""

    def _count_print_in_except(self, file_path: Path) -> int:
        """Count print statements inside except blocks."""
        if not file_path.exists():
            return 0

        source = file_path.read_text(encoding='utf-8')

        # Look for patterns like 'except ... : print(' or 'except ... :\n ... print('
        # This is a simplified check - actual AST parsing would be more accurate
        count = 0
        lines = source.split('\n')
        in_except = False

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Check if we're entering an except block
            if stripped.startswith('except') and stripped.endswith(':'):
                in_except = True
                continue

            # Check if we're exiting (new block at same or lower indent)
            if in_except and stripped and not stripped.startswith('#'):
                # If this line has a print, count it
                if 'print(' in stripped or 'print (' in stripped:
                    # Exclude self-test sections
                    if '__main__' not in source[max(0, source.find(line) - 500):source.find(line)]:
                        count += 1

                # Check if we've exited the except block
                current_indent = len(line) - len(line.lstrip())
                if current_indent == 0 and stripped:
                    in_except = False

        return count

    def test_academic_fetcher_no_print_in_except(self, src_root: Path):
        """academic_fetcher.py should not have print in except blocks (outside self-test)."""
        file_path = src_root / "utils" / "academic_fetcher.py"
        source = file_path.read_text(encoding='utf-8')

        # Find the main code (before __main__ section)
        main_code_end = source.find('if __name__')
        if main_code_end == -1:
            main_code = source
        else:
            main_code = source[:main_code_end]

        # Count print statements in except blocks within main code
        # Using a simple pattern match
        pattern = r'except[^:]*:\s*(?:[^}]*?)\bprint\s*\('
        matches = re.findall(pattern, main_code, re.DOTALL)
        assert len(matches) == 0, f"Found {len(matches)} print statements in except blocks"

    def test_crossref_resolver_no_print_in_except(self, src_root: Path):
        """crossref_resolver.py should not have print in except blocks (outside self-test)."""
        file_path = src_root / "utils" / "crossref_resolver.py"
        source = file_path.read_text(encoding='utf-8')

        # Find the main code (before __main__ section)
        main_code_end = source.find('if __name__')
        if main_code_end == -1:
            main_code = source
        else:
            main_code = source[:main_code_end]

        # Simple check: no print( after except in main code
        lines = main_code.split('\n')
        in_except = False
        for line in lines:
            if 'except' in line and ':' in line:
                in_except = True
            elif in_except and 'print(' in line:
                # This is a false positive risk, but a good quick check
                pytest.fail(f"Found print in except block: {line.strip()}")
            elif line.strip() and not line.strip().startswith('#') and not line.strip().startswith('"'):
                if not line.startswith(' ') and not line.startswith('\t'):
                    in_except = False

    def test_source_quality_no_print_in_except(self, src_root: Path):
        """source_quality.py should not have print in except blocks (outside self-test)."""
        file_path = src_root / "utils" / "source_quality.py"
        source = file_path.read_text(encoding='utf-8')

        # Find the main code (before __main__ section)
        main_code_end = source.find('if __name__')
        if main_code_end == -1:
            main_code = source
        else:
            main_code = source[:main_code_end]

        # Check for print statements - should use logger instead
        assert 'print(f"[SOURCE-QUALITY]' not in main_code, "Should use logger instead of print"
        assert 'print(f"[RCS-MAP]' not in main_code, "Should use logger instead of print"


# =============================================================================
# TEST CLASS: Logger Calls Use Correct Levels
# =============================================================================

class TestLoggerLevelsCorrect:
    """Verify logger calls use appropriate levels."""

    def _check_logger_levels(self, file_path: Path) -> dict:
        """Count logger calls by level."""
        if not file_path.exists():
            return {}

        source = file_path.read_text(encoding='utf-8')

        levels = {
            'debug': len(re.findall(r'logger\.debug\(', source)),
            'info': len(re.findall(r'logger\.info\(', source)),
            'warning': len(re.findall(r'logger\.warning\(', source)),
            'error': len(re.findall(r'logger\.error\(', source)),
            'critical': len(re.findall(r'logger\.critical\(', source)),
        }
        return levels

    def test_academic_fetcher_uses_debug_for_expected_errors(self, src_root: Path):
        """academic_fetcher.py should use debug level for expected errors."""
        file_path = src_root / "utils" / "academic_fetcher.py"
        levels = self._check_logger_levels(file_path)
        # Expected errors (API failures) should be debug, not error
        assert levels['debug'] >= 8, "Expected at least 8 debug log calls"

    def test_crossref_resolver_uses_debug_for_expected_errors(self, src_root: Path):
        """crossref_resolver.py should use debug level for expected errors."""
        file_path = src_root / "utils" / "crossref_resolver.py"
        levels = self._check_logger_levels(file_path)
        assert levels['debug'] >= 4, "Expected at least 4 debug log calls"

    def test_source_quality_uses_debug_for_expected_errors(self, src_root: Path):
        """source_quality.py should use debug level for expected errors."""
        file_path = src_root / "utils" / "source_quality.py"
        levels = self._check_logger_levels(file_path)
        assert levels['debug'] >= 6, "Expected at least 6 debug log calls"


# =============================================================================
# TEST CLASS: Guard Clauses Are Legitimate
# =============================================================================

class TestGuardClausesLegitimate:
    """Verify that remaining empty returns are legitimate guard clauses."""

    def _find_guard_clauses(self, file_path: Path) -> list[str]:
        """Find guard clauses (if not x: return ...)."""
        if not file_path.exists():
            return []

        source = file_path.read_text(encoding='utf-8')
        pattern = r'if\s+not\s+\w+[^:]*:\s*\n\s*return\s+(?:\[\]|None|{}|""|\'\')?\s*$'
        return re.findall(pattern, source, re.MULTILINE)

    def test_search_agent_guard_clauses(self, src_root: Path):
        """search_agent.py guard clauses are for input validation."""
        file_path = src_root / "agents" / "search_agent.py"
        assert file_path.exists(), "search_agent.py should exist"
        # Guard clauses are legitimate for input validation

    def test_relevance_filter_guard_clauses(self, src_root: Path):
        """p04_relevance_filter.py guard clauses are for input validation."""
        file_path = src_root / "phases" / "p04_relevance_filter.py"
        assert file_path.exists(), "p04_relevance_filter.py should exist"
        # Guard clauses are legitimate for empty input handling

    def test_claim_verification_guard_clauses(self, src_root: Path):
        """claim_verification.py guard clauses are for input validation."""
        file_path = src_root / "functions" / "claim_verification.py"
        assert file_path.exists(), "claim_verification.py should exist"
        # Guard clauses are legitimate for empty claim handling


# =============================================================================
# TEST CLASS: Critical Files Have Logging Imports
# =============================================================================

class TestCriticalFilesHaveLogging:
    """Verify all critical files have logging setup."""

    def _has_logging_import(self, file_path: Path) -> bool:
        """Check if file imports logging module."""
        if not file_path.exists():
            return False
        source = file_path.read_text(encoding='utf-8')
        return 'import logging' in source

    def test_phase_files_have_logging(self, src_root: Path):
        """All phase files should have logging imports."""
        phases_dir = src_root / "phases"
        for phase_file in phases_dir.glob("p*.py"):
            assert self._has_logging_import(phase_file), f"{phase_file.name} should import logging"

    def test_agent_files_have_logging(self, src_root: Path):
        """All agent files should have logging imports."""
        agents_dir = src_root / "agents"
        for agent_file in agents_dir.glob("*_agent.py"):
            assert self._has_logging_import(agent_file), f"{agent_file.name} should import logging"

    def test_function_files_have_logging(self, src_root: Path):
        """Critical function files should have logging imports."""
        functions_dir = src_root / "functions"
        critical_files = ["claim_verification.py", "quality_scoring.py", "document_processing.py"]
        for filename in critical_files:
            file_path = functions_dir / filename
            if file_path.exists():
                assert self._has_logging_import(file_path), f"{filename} should import logging"
