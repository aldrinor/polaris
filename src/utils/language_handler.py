"""
POLARIS Multi-Language Handler
==============================
Supports multi-language research queries and content processing.

Features:
- Language detection for queries and content
- Query translation to English for processing
- Language-aware formatting
- Multi-language source handling

Usage:
    from src.utils.language_handler import LanguageHandler

    handler = LanguageHandler()

    # Detect language
    lang = handler.detect_language("Bonjour le monde")

    # Translate to English
    english = handler.translate_to_english("Hola mundo", source_lang="es")
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import unicodedata

logger = logging.getLogger(__name__)


# =============================================================================
# Language Constants
# =============================================================================

class Language(str, Enum):
    """Supported languages."""
    ENGLISH = "en"
    SPANISH = "es"
    FRENCH = "fr"
    GERMAN = "de"
    ITALIAN = "it"
    PORTUGUESE = "pt"
    DUTCH = "nl"
    RUSSIAN = "ru"
    CHINESE = "zh"
    JAPANESE = "ja"
    KOREAN = "ko"
    ARABIC = "ar"
    HINDI = "hi"
    TURKISH = "tr"
    POLISH = "pl"
    UNKNOWN = "unknown"


# Language name mappings
LANGUAGE_NAMES = {
    Language.ENGLISH: "English",
    Language.SPANISH: "Spanish",
    Language.FRENCH: "French",
    Language.GERMAN: "German",
    Language.ITALIAN: "Italian",
    Language.PORTUGUESE: "Portuguese",
    Language.DUTCH: "Dutch",
    Language.RUSSIAN: "Russian",
    Language.CHINESE: "Chinese",
    Language.JAPANESE: "Japanese",
    Language.KOREAN: "Korean",
    Language.ARABIC: "Arabic",
    Language.HINDI: "Hindi",
    Language.TURKISH: "Turkish",
    Language.POLISH: "Polish",
    Language.UNKNOWN: "Unknown",
}

# Common words for language detection (stopwords)
LANGUAGE_INDICATORS = {
    Language.ENGLISH: {
        "the", "is", "are", "was", "were", "have", "has", "been",
        "what", "which", "how", "why", "when", "where", "who",
        "this", "that", "these", "those", "and", "or", "but",
    },
    Language.SPANISH: {
        "el", "la", "los", "las", "un", "una", "es", "son", "está",
        "qué", "cómo", "cuándo", "dónde", "por", "que", "de", "en",
        "y", "o", "pero", "para", "con", "sin", "sobre",
    },
    Language.FRENCH: {
        "le", "la", "les", "un", "une", "est", "sont", "été",
        "que", "qui", "quoi", "comment", "pourquoi", "quand", "où",
        "et", "ou", "mais", "pour", "avec", "sans", "sur", "dans",
    },
    Language.GERMAN: {
        "der", "die", "das", "ein", "eine", "ist", "sind", "war",
        "was", "wie", "warum", "wann", "wo", "wer", "welche",
        "und", "oder", "aber", "für", "mit", "ohne", "auf", "in",
    },
    Language.ITALIAN: {
        "il", "la", "lo", "i", "gli", "le", "un", "una", "è", "sono",
        "che", "cosa", "come", "perché", "quando", "dove", "chi",
        "e", "o", "ma", "per", "con", "senza", "su", "in",
    },
    Language.PORTUGUESE: {
        "o", "a", "os", "as", "um", "uma", "é", "são", "foi",
        "que", "como", "porque", "quando", "onde", "quem",
        "e", "ou", "mas", "para", "com", "sem", "sobre", "em",
    },
    Language.DUTCH: {
        "de", "het", "een", "is", "zijn", "was", "waren", "heeft",
        "wat", "hoe", "waarom", "wanneer", "waar", "wie",
        "en", "of", "maar", "voor", "met", "zonder", "op", "in",
    },
    Language.RUSSIAN: {
        "и", "в", "на", "с", "к", "по", "за", "из", "от",
        "что", "как", "когда", "где", "кто", "почему",
        "это", "он", "она", "они", "мы", "вы", "я", "ты",
    },
}

# Character set patterns for script detection
SCRIPT_PATTERNS = {
    Language.CHINESE: re.compile(r'[\u4e00-\u9fff]'),
    Language.JAPANESE: re.compile(r'[\u3040-\u309f\u30a0-\u30ff]'),
    Language.KOREAN: re.compile(r'[\uac00-\ud7af]'),
    Language.ARABIC: re.compile(r'[\u0600-\u06ff]'),
    Language.RUSSIAN: re.compile(r'[\u0400-\u04ff]'),
    Language.HINDI: re.compile(r'[\u0900-\u097f]'),
}


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class LanguageConfig:
    """Configuration for language handling."""

    # Detection settings
    min_text_length: int = 10
    confidence_threshold: float = 0.3
    default_language: Language = Language.ENGLISH

    # Translation settings
    auto_translate: bool = True
    preserve_original: bool = True

    # Formatting settings
    rtl_languages: List[Language] = field(
        default_factory=lambda: [Language.ARABIC]
    )

    # Source handling
    prioritize_english_sources: bool = True
    include_translated_sources: bool = True


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class LanguageDetectionResult:
    """Result of language detection."""
    detected_language: Language
    confidence: float
    is_multilingual: bool = False
    detected_scripts: List[str] = field(default_factory=list)
    language_distribution: Dict[Language, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "detected_language": self.detected_language.value,
            "language_name": LANGUAGE_NAMES.get(self.detected_language, "Unknown"),
            "confidence": round(self.confidence, 3),
            "is_multilingual": self.is_multilingual,
            "detected_scripts": self.detected_scripts,
            "language_distribution": {
                lang.value: round(score, 3)
                for lang, score in self.language_distribution.items()
            },
        }


@dataclass
class TranslationResult:
    """Result of translation."""
    original_text: str
    translated_text: str
    source_language: Language
    target_language: Language
    translation_method: str = "heuristic"  # heuristic, api, cached
    success: bool = True
    error_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "original_text": self.original_text,
            "translated_text": self.translated_text,
            "source_language": self.source_language.value,
            "target_language": self.target_language.value,
            "translation_method": self.translation_method,
            "success": self.success,
            "error_message": self.error_message,
        }


@dataclass
class MultiLanguageContent:
    """Multi-language content container."""
    original_text: str
    original_language: Language
    english_text: str
    translations: Dict[Language, str] = field(default_factory=dict)

    def get_text(self, language: Language = Language.ENGLISH) -> str:
        """Get text in specified language."""
        if language == self.original_language:
            return self.original_text
        if language == Language.ENGLISH:
            return self.english_text
        return self.translations.get(language, self.english_text)


# =============================================================================
# Language Handler
# =============================================================================

class LanguageHandler:
    """
    Handles multi-language processing for research queries and content.

    Provides language detection, translation, and language-aware formatting.
    """

    def __init__(self, config: Optional[LanguageConfig] = None):
        """
        Initialize the language handler.

        Args:
            config: Language handling configuration
        """
        self.config = config or LanguageConfig()
        self._translation_cache: Dict[str, str] = {}

    def detect_language(self, text: str) -> LanguageDetectionResult:
        """
        Detect the language of text.

        Args:
            text: Text to analyze

        Returns:
            LanguageDetectionResult with detected language and confidence
        """
        if not text or len(text.strip()) < self.config.min_text_length:
            return LanguageDetectionResult(
                detected_language=self.config.default_language,
                confidence=0.0,
            )

        # Check for script-based detection first
        scripts = self._detect_scripts(text)
        if scripts:
            primary_script = scripts[0]
            return LanguageDetectionResult(
                detected_language=primary_script,
                confidence=0.95,
                detected_scripts=[primary_script.value],
            )

        # Word-based detection for Latin-script languages
        scores = self._calculate_language_scores(text)

        if not scores:
            return LanguageDetectionResult(
                detected_language=self.config.default_language,
                confidence=0.1,
            )

        # Get best match
        best_lang = max(scores, key=scores.get)
        best_score = scores[best_lang]

        # Check for multilingual content
        is_multilingual = False
        if len(scores) > 1:
            sorted_scores = sorted(scores.values(), reverse=True)
            if len(sorted_scores) > 1 and sorted_scores[1] > 0.3 * sorted_scores[0]:
                is_multilingual = True

        return LanguageDetectionResult(
            detected_language=best_lang,
            confidence=min(best_score, 1.0),
            is_multilingual=is_multilingual,
            language_distribution=scores,
        )

    def translate_to_english(
        self,
        text: str,
        source_lang: Optional[Language] = None,
    ) -> TranslationResult:
        """
        Translate text to English.

        Args:
            text: Text to translate
            source_lang: Source language (auto-detected if None)

        Returns:
            TranslationResult with translated text
        """
        if not text:
            return TranslationResult(
                original_text=text,
                translated_text=text,
                source_language=Language.UNKNOWN,
                target_language=Language.ENGLISH,
            )

        # Detect language if not provided
        if source_lang is None:
            detection = self.detect_language(text)
            source_lang = detection.detected_language

        # Already English
        if source_lang == Language.ENGLISH:
            return TranslationResult(
                original_text=text,
                translated_text=text,
                source_language=Language.ENGLISH,
                target_language=Language.ENGLISH,
            )

        # Check cache
        cache_key = f"{source_lang.value}:{text[:100]}"
        if cache_key in self._translation_cache:
            return TranslationResult(
                original_text=text,
                translated_text=self._translation_cache[cache_key],
                source_language=source_lang,
                target_language=Language.ENGLISH,
                translation_method="cached",
            )

        # Heuristic translation (placeholder for API integration)
        translated = self._heuristic_translate(text, source_lang)

        self._translation_cache[cache_key] = translated

        return TranslationResult(
            original_text=text,
            translated_text=translated,
            source_language=source_lang,
            target_language=Language.ENGLISH,
            translation_method="heuristic",
        )

    def is_english(self, text: str) -> bool:
        """
        Quick check if text is in English.

        Args:
            text: Text to check

        Returns:
            True if text is English
        """
        detection = self.detect_language(text)
        return detection.detected_language == Language.ENGLISH

    def prepare_query(self, query: str) -> MultiLanguageContent:
        """
        Prepare a query for multi-language research.

        Args:
            query: User query in any language

        Returns:
            MultiLanguageContent with original and English versions
        """
        detection = self.detect_language(query)

        if detection.detected_language == Language.ENGLISH:
            return MultiLanguageContent(
                original_text=query,
                original_language=Language.ENGLISH,
                english_text=query,
            )

        translation = self.translate_to_english(query, detection.detected_language)

        return MultiLanguageContent(
            original_text=query,
            original_language=detection.detected_language,
            english_text=translation.translated_text,
        )

    def get_language_name(self, language: Language) -> str:
        """Get human-readable language name."""
        return LANGUAGE_NAMES.get(language, "Unknown")

    def is_rtl_language(self, language: Language) -> bool:
        """Check if language is right-to-left."""
        return language in self.config.rtl_languages

    def get_supported_languages(self) -> List[Dict[str, str]]:
        """Get list of supported languages."""
        return [
            {"code": lang.value, "name": LANGUAGE_NAMES.get(lang, lang.value)}
            for lang in Language
            if lang != Language.UNKNOWN
        ]

    # =========================================================================
    # Internal Methods
    # =========================================================================

    def _detect_scripts(self, text: str) -> List[Language]:
        """Detect non-Latin scripts in text."""
        detected = []

        # Check Japanese first (has unique hiragana/katakana)
        # Japanese text contains both kana and kanji, but kana is unique to Japanese
        if SCRIPT_PATTERNS[Language.JAPANESE].search(text):
            return [Language.JAPANESE]

        # Check Korean (unique Hangul script)
        if SCRIPT_PATTERNS[Language.KOREAN].search(text):
            return [Language.KOREAN]

        # Check Chinese (after Japanese/Korean since they may contain Chinese chars)
        if SCRIPT_PATTERNS[Language.CHINESE].search(text):
            return [Language.CHINESE]

        # Check other scripts
        for lang in [Language.ARABIC, Language.RUSSIAN, Language.HINDI]:
            if lang in SCRIPT_PATTERNS and SCRIPT_PATTERNS[lang].search(text):
                detected.append(lang)

        return detected

    def _calculate_language_scores(self, text: str) -> Dict[Language, float]:
        """Calculate language scores based on word matching."""
        # Normalize text
        text_lower = text.lower()
        words = set(re.findall(r'\b\w+\b', text_lower))

        if not words:
            return {}

        scores = {}

        for lang, indicators in LANGUAGE_INDICATORS.items():
            matches = len(words.intersection(indicators))
            if matches > 0:
                score = matches / len(indicators)
                scores[lang] = score

        # Normalize scores
        if scores:
            max_score = max(scores.values())
            if max_score > 0:
                scores = {lang: score / max_score for lang, score in scores.items()}

        return scores

    def _heuristic_translate(self, text: str, source_lang: Language) -> str:
        """
        Perform heuristic translation (preserves structure, marks for translation).

        In production, this would use a translation API.
        """
        # For now, return original with language marker
        # This is a placeholder for actual translation API integration
        return f"[{source_lang.value}→en] {text}"


# =============================================================================
# Convenience Functions
# =============================================================================

def detect_language(text: str) -> Language:
    """
    Detect language of text.

    Args:
        text: Text to analyze

    Returns:
        Detected Language
    """
    handler = LanguageHandler()
    result = handler.detect_language(text)
    return result.detected_language


def is_english(text: str) -> bool:
    """
    Check if text is in English.

    Args:
        text: Text to check

    Returns:
        True if English
    """
    handler = LanguageHandler()
    return handler.is_english(text)


def translate_to_english(
    text: str,
    source_lang: Optional[str] = None,
) -> str:
    """
    Translate text to English.

    Args:
        text: Text to translate
        source_lang: Source language code (optional)

    Returns:
        Translated text
    """
    handler = LanguageHandler()
    lang = Language(source_lang) if source_lang else None
    result = handler.translate_to_english(text, lang)
    return result.translated_text


def get_language_name(lang_code: str) -> str:
    """
    Get human-readable language name.

    Args:
        lang_code: Language code (e.g., "en", "es")

    Returns:
        Language name
    """
    try:
        lang = Language(lang_code)
        return LANGUAGE_NAMES.get(lang, lang_code)
    except ValueError:
        return lang_code


def get_supported_languages() -> List[str]:
    """
    Get list of supported language codes.

    Returns:
        List of language codes
    """
    return [lang.value for lang in Language if lang != Language.UNKNOWN]


# =============================================================================
# Self-Test
# =============================================================================

def self_test() -> bool:
    """Run self-tests for language handler."""
    print("Running Language Handler self-tests...")

    handler = LanguageHandler()

    # Test English detection
    result = handler.detect_language("The quick brown fox jumps over the lazy dog.")
    assert result.detected_language == Language.ENGLISH
    print("  [PASS] English detection")

    # Test Spanish detection
    result = handler.detect_language("El rápido zorro marrón salta sobre el perro perezoso.")
    assert result.detected_language == Language.SPANISH
    print("  [PASS] Spanish detection")

    # Test French detection
    result = handler.detect_language("Le renard brun rapide saute par-dessus le chien paresseux.")
    assert result.detected_language == Language.FRENCH
    print("  [PASS] French detection")

    # Test German detection
    result = handler.detect_language("Der schnelle braune Fuchs springt über den faulen Hund.")
    assert result.detected_language == Language.GERMAN
    print("  [PASS] German detection")

    # Test Chinese script detection (use longer text)
    result = handler.detect_language("这是中文测试文本，用于验证语言检测功能")
    assert result.detected_language == Language.CHINESE
    print("  [PASS] Chinese detection")

    # Test Japanese script detection (use longer text)
    result = handler.detect_language("これは日本語のテストです。言語検出機能を確認します")
    assert result.detected_language == Language.JAPANESE
    print("  [PASS] Japanese detection")

    # Test Korean script detection (use longer text)
    result = handler.detect_language("이것은 한국어 테스트입니다. 언어 감지 기능을 확인합니다")
    assert result.detected_language == Language.KOREAN
    print("  [PASS] Korean detection")

    # Test translation (heuristic)
    trans = handler.translate_to_english("Hola mundo", Language.SPANISH)
    assert trans.source_language == Language.SPANISH
    assert trans.success
    print("  [PASS] Translation")

    # Test is_english
    assert handler.is_english("This is English text")
    assert not handler.is_english("Esto es texto en español")
    print("  [PASS] is_english")

    # Test prepare_query
    content = handler.prepare_query("What is machine learning?")
    assert content.original_language == Language.ENGLISH
    print("  [PASS] prepare_query")

    # Test convenience functions
    lang = detect_language("The quick brown fox")
    assert lang == Language.ENGLISH
    print("  [PASS] detect_language convenience")

    assert is_english("Hello world")
    print("  [PASS] is_english convenience")

    langs = get_supported_languages()
    assert len(langs) > 10
    print("  [PASS] get_supported_languages")

    name = get_language_name("es")
    assert name == "Spanish"
    print("  [PASS] get_language_name")

    # Test result serialization
    result = handler.detect_language("Test text")
    data = result.to_dict()
    assert "detected_language" in data
    print("  [PASS] Result serialization")

    print("\nAll Language Handler self-tests PASSED!")
    return True


if __name__ == "__main__":
    self_test()
