#!/usr/bin/env python3
"""
Unit tests for Language Handler.

Tests:
- Language enum
- LanguageConfig
- LanguageHandler class
- Language detection
- Translation
- Convenience functions

Run:
    pytest tests/unit/test_language_handler.py -v
"""

import pytest
from pathlib import Path
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.language_handler import (
    LanguageHandler,
    LanguageConfig,
    Language,
    LanguageDetectionResult,
    TranslationResult,
    MultiLanguageContent,
    LANGUAGE_NAMES,
    LANGUAGE_INDICATORS,
    detect_language,
    is_english,
    translate_to_english,
    get_language_name,
    get_supported_languages,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def default_handler():
    """Default language handler instance."""
    return LanguageHandler()


@pytest.fixture
def custom_config():
    """Custom language configuration."""
    return LanguageConfig(
        min_text_length=5,
        confidence_threshold=0.5,
    )


# =============================================================================
# Language Enum Tests
# =============================================================================

class TestLanguage:
    """Tests for Language enum."""

    def test_all_languages_defined(self):
        """Test all expected languages are defined."""
        expected = [
            "en", "es", "fr", "de", "it", "pt", "nl", "ru",
            "zh", "ja", "ko", "ar", "hi", "tr", "pl", "unknown"
        ]
        for code in expected:
            assert any(lang.value == code for lang in Language)

    def test_language_values(self):
        """Test enum values."""
        assert Language.ENGLISH.value == "en"
        assert Language.SPANISH.value == "es"
        assert Language.CHINESE.value == "zh"

    def test_language_count(self):
        """Test correct number of languages."""
        assert len(Language) >= 15


# =============================================================================
# LanguageConfig Tests
# =============================================================================

class TestLanguageConfig:
    """Tests for LanguageConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = LanguageConfig()
        assert config.min_text_length == 10
        assert config.confidence_threshold == 0.3
        assert config.default_language == Language.ENGLISH
        assert config.auto_translate is True

    def test_custom_values(self):
        """Test custom configuration values."""
        config = LanguageConfig(
            min_text_length=5,
            auto_translate=False,
        )
        assert config.min_text_length == 5
        assert config.auto_translate is False


# =============================================================================
# LanguageDetectionResult Tests
# =============================================================================

class TestLanguageDetectionResult:
    """Tests for LanguageDetectionResult dataclass."""

    def test_default_values(self):
        """Test default result values."""
        result = LanguageDetectionResult(
            detected_language=Language.ENGLISH,
            confidence=0.9,
        )
        assert result.is_multilingual is False
        assert len(result.detected_scripts) == 0

    def test_to_dict(self):
        """Test dictionary conversion."""
        result = LanguageDetectionResult(
            detected_language=Language.SPANISH,
            confidence=0.85,
        )
        data = result.to_dict()
        assert data["detected_language"] == "es"
        assert data["language_name"] == "Spanish"
        assert data["confidence"] == 0.85


# =============================================================================
# LanguageHandler Tests
# =============================================================================

class TestLanguageHandler:
    """Tests for LanguageHandler class."""

    def test_initialization_default(self, default_handler):
        """Test default initialization."""
        assert default_handler.config is not None

    def test_initialization_custom(self, custom_config):
        """Test initialization with custom config."""
        handler = LanguageHandler(config=custom_config)
        assert handler.config.min_text_length == 5


# =============================================================================
# Language Detection Tests
# =============================================================================

class TestLanguageDetection:
    """Tests for language detection."""

    def test_detect_english(self, default_handler):
        """Test English detection."""
        result = default_handler.detect_language(
            "The quick brown fox jumps over the lazy dog."
        )
        assert result.detected_language == Language.ENGLISH
        assert result.confidence > 0.5

    def test_detect_spanish(self, default_handler):
        """Test Spanish detection."""
        result = default_handler.detect_language(
            "El rápido zorro marrón salta sobre el perro perezoso."
        )
        assert result.detected_language == Language.SPANISH

    def test_detect_french(self, default_handler):
        """Test French detection."""
        result = default_handler.detect_language(
            "Le renard brun rapide saute par-dessus le chien paresseux."
        )
        assert result.detected_language == Language.FRENCH

    def test_detect_german(self, default_handler):
        """Test German detection."""
        result = default_handler.detect_language(
            "Der schnelle braune Fuchs springt über den faulen Hund."
        )
        assert result.detected_language == Language.GERMAN

    def test_detect_short_text(self, default_handler):
        """Test detection of short text (below threshold)."""
        result = default_handler.detect_language("Hi")
        # Should return default language with low confidence
        assert result.detected_language == Language.ENGLISH
        assert result.confidence == 0.0

    def test_detect_empty_text(self, default_handler):
        """Test detection of empty text."""
        result = default_handler.detect_language("")
        assert result.detected_language == Language.ENGLISH
        assert result.confidence == 0.0


# =============================================================================
# Script Detection Tests
# =============================================================================

class TestScriptDetection:
    """Tests for script-based detection."""

    def test_detect_chinese(self, default_handler):
        """Test Chinese script detection."""
        # Longer Chinese text
        result = default_handler.detect_language(
            "\u8fd9\u662f\u4e2d\u6587\u6d4b\u8bd5\u6587\u672c\uff0c\u7528\u4e8e\u9a8c\u8bc1\u8bed\u8a00\u68c0\u6d4b\u529f\u80fd"
        )
        assert result.detected_language == Language.CHINESE

    def test_detect_japanese(self, default_handler):
        """Test Japanese script detection (hiragana/katakana)."""
        # Japanese text with hiragana
        result = default_handler.detect_language(
            "\u3053\u308c\u306f\u65e5\u672c\u8a9e\u306e\u30c6\u30b9\u30c8\u3067\u3059\u3002\u8a00\u8a9e\u691c\u51fa\u6a5f\u80fd\u3092\u78ba\u8a8d\u3057\u307e\u3059"
        )
        assert result.detected_language == Language.JAPANESE

    def test_detect_korean(self, default_handler):
        """Test Korean script detection."""
        # Korean text with Hangul
        result = default_handler.detect_language(
            "\uc774\uac83\uc740 \ud55c\uad6d\uc5b4 \ud14c\uc2a4\ud2b8\uc785\ub2c8\ub2e4. \uc5b8\uc5b4 \uac10\uc9c0 \uae30\ub2a5\uc744 \ud655\uc778\ud569\ub2c8\ub2e4"
        )
        assert result.detected_language == Language.KOREAN

    def test_detect_russian(self, default_handler):
        """Test Russian script detection."""
        result = default_handler.detect_language(
            "\u042d\u0442\u043e \u0442\u0435\u0441\u0442 \u0440\u0443\u0441\u0441\u043a\u043e\u0433\u043e \u044f\u0437\u044b\u043a\u0430"
        )
        assert result.detected_language == Language.RUSSIAN


# =============================================================================
# Translation Tests
# =============================================================================

class TestTranslation:
    """Tests for translation."""

    def test_translate_english_to_english(self, default_handler):
        """Test that English is not translated."""
        result = default_handler.translate_to_english(
            "Hello world",
            Language.ENGLISH
        )
        assert result.translated_text == "Hello world"
        assert result.source_language == Language.ENGLISH

    def test_translate_spanish(self, default_handler):
        """Test Spanish translation."""
        result = default_handler.translate_to_english(
            "Hola mundo",
            Language.SPANISH
        )
        assert result.source_language == Language.SPANISH
        assert result.target_language == Language.ENGLISH
        assert result.success

    def test_translate_auto_detect(self, default_handler):
        """Test translation with auto-detection."""
        result = default_handler.translate_to_english(
            "Le monde est beau et magnifique"
        )
        assert result.source_language == Language.FRENCH

    def test_translate_empty(self, default_handler):
        """Test translation of empty text."""
        result = default_handler.translate_to_english("")
        assert result.translated_text == ""

    def test_translation_caching(self, default_handler):
        """Test that translations are cached."""
        text = "Hola mundo"
        result1 = default_handler.translate_to_english(text, Language.SPANISH)
        result2 = default_handler.translate_to_english(text, Language.SPANISH)
        assert result2.translation_method == "cached"


# =============================================================================
# Helper Method Tests
# =============================================================================

class TestHelperMethods:
    """Tests for helper methods."""

    def test_is_english_true(self, default_handler):
        """Test is_english returns True for English."""
        assert default_handler.is_english("This is English text")

    def test_is_english_false(self, default_handler):
        """Test is_english returns False for non-English."""
        assert not default_handler.is_english("Esto es texto en español y más")

    def test_prepare_query_english(self, default_handler):
        """Test prepare_query with English query."""
        content = default_handler.prepare_query("What is machine learning?")
        assert content.original_language == Language.ENGLISH
        assert content.original_text == content.english_text

    def test_prepare_query_non_english(self, default_handler):
        """Test prepare_query with non-English query."""
        content = default_handler.prepare_query(
            "Qu'est-ce que l'apprentissage automatique et comment fonctionne-t-il?"
        )
        assert content.original_language != Language.ENGLISH

    def test_get_language_name(self, default_handler):
        """Test getting language name."""
        name = default_handler.get_language_name(Language.SPANISH)
        assert name == "Spanish"

    def test_is_rtl_language(self, default_handler):
        """Test RTL language detection."""
        assert default_handler.is_rtl_language(Language.ARABIC)
        assert not default_handler.is_rtl_language(Language.ENGLISH)

    def test_get_supported_languages(self, default_handler):
        """Test getting supported languages list."""
        langs = default_handler.get_supported_languages()
        assert len(langs) > 10
        assert all("code" in lang and "name" in lang for lang in langs)


# =============================================================================
# MultiLanguageContent Tests
# =============================================================================

class TestMultiLanguageContent:
    """Tests for MultiLanguageContent dataclass."""

    def test_get_text_original(self):
        """Test getting text in original language."""
        content = MultiLanguageContent(
            original_text="Hola mundo",
            original_language=Language.SPANISH,
            english_text="Hello world",
        )
        assert content.get_text(Language.SPANISH) == "Hola mundo"

    def test_get_text_english(self):
        """Test getting text in English."""
        content = MultiLanguageContent(
            original_text="Hola mundo",
            original_language=Language.SPANISH,
            english_text="Hello world",
        )
        assert content.get_text(Language.ENGLISH) == "Hello world"


# =============================================================================
# Convenience Function Tests
# =============================================================================

class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_detect_language(self):
        """Test detect_language function."""
        lang = detect_language("The quick brown fox jumps")
        assert lang == Language.ENGLISH

    def test_is_english_function(self):
        """Test is_english function."""
        assert is_english("Hello world from Python")
        assert not is_english("Hola mundo desde Python con mucho texto")

    def test_translate_to_english_function(self):
        """Test translate_to_english function."""
        translated = translate_to_english("Hola mundo", "es")
        assert isinstance(translated, str)

    def test_get_language_name_function(self):
        """Test get_language_name function."""
        name = get_language_name("es")
        assert name == "Spanish"

    def test_get_supported_languages_function(self):
        """Test get_supported_languages function."""
        langs = get_supported_languages()
        assert "en" in langs
        assert "es" in langs
        assert len(langs) >= 15


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases."""

    def test_mixed_language_text(self, default_handler):
        """Test text with mixed languages."""
        text = "Hello world and also bonjour le monde"
        result = default_handler.detect_language(text)
        # Should detect primary language
        assert result.detected_language in [Language.ENGLISH, Language.FRENCH]

    def test_numbers_only(self, default_handler):
        """Test text with only numbers."""
        result = default_handler.detect_language("12345 67890 12345")
        assert result.detected_language == Language.ENGLISH
        assert result.confidence < 0.5

    def test_special_characters(self, default_handler):
        """Test text with special characters."""
        result = default_handler.detect_language("Hello! How are you? I'm fine.")
        assert result.detected_language == Language.ENGLISH

    def test_unicode_normalization(self, default_handler):
        """Test Unicode text handling."""
        # Text with accents
        result = default_handler.detect_language(
            "Café résumé naïve coöperate"
        )
        assert result.detected_language is not None


# =============================================================================
# Language Indicators Tests
# =============================================================================

class TestLanguageIndicators:
    """Tests for language indicators."""

    def test_indicators_exist(self):
        """Test language indicators are defined."""
        assert len(LANGUAGE_INDICATORS) > 5

    def test_indicator_sets(self):
        """Test indicators are non-empty sets."""
        for lang, indicators in LANGUAGE_INDICATORS.items():
            assert len(indicators) > 5


# =============================================================================
# Self-Test Function
# =============================================================================

class TestSelfTest:
    """Tests for self_test function."""

    def test_self_test_passes(self):
        """Test that self-test function passes."""
        from src.utils.language_handler import self_test
        assert self_test() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
