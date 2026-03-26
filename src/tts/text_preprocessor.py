"""
Text Preprocessor Module
Handles text preprocessing including abbreviation expansion before TTS generation.
"""
import re
import logging

logger = logging.getLogger(__name__)


class TextPreprocessor:
    """Preprocesses text for TTS generation with abbreviation expansion."""

    def __init__(self):
        # Cache for compiled regex patterns keyed by abbreviations content.
        # Avoids recompiling patterns on every call when abbreviations are unchanged.
        self._compiled_pattern_cache_key = None
        self._compiled_patterns = []  # List of (compiled_pattern, abbrev, expansion)
        self._soundboard_token_pattern = re.compile(r'\[([1-9]\d?)\]')

    def _get_compiled_patterns(self, abbreviations: dict):
        """Return cached compiled patterns, rebuilding only when abbreviations change.

        Each entry is a 3-tuple: (compiled_pattern, abbrev, expansion).
        """
        cache_key = frozenset(abbreviations.items())
        if self._compiled_pattern_cache_key != cache_key:
            self._compiled_pattern_cache_key = cache_key
            sorted_abbrevs = sorted(abbreviations.items(), key=lambda x: len(x[0]), reverse=True)
            self._compiled_patterns = [
                (re.compile(r'\b' + re.escape(abbrev) + r'\b', re.IGNORECASE), abbrev, expansion)
                for abbrev, expansion in sorted_abbrevs
                if abbrev
            ]
        return self._compiled_patterns

    def preprocess_text(self, text: str, abbreviations: dict = None) -> str:
        """
        Preprocess text for TTS generation with abbreviation expansion.
        
        Args:
            text: Input text to process
            abbreviations: Dictionary of abbreviations to expand. If None, no expansion is performed.
            
        Returns:
            Preprocessed text with abbreviations expanded
        """
        # Log input for debugging
        logger.debug("Preprocessing input: '%s'", text)
        
        # Use provided abbreviations or empty dict (no-op)
        if abbreviations is None:
            abbreviations = {}
        
        result = self.expand_abbreviations(text, abbreviations)
        
        # Log output for debugging
        logger.debug("Preprocessing output: '%s'", result)
        
        return result
    
    def expand_abbreviations(self, text: str, abbreviations: dict) -> str:
        """
        Expand abbreviations in text using case-insensitive whole-word matching.
        
        Args:
            text: Input text to process
            abbreviations: Dictionary mapping abbreviations to their expansions
            
        Returns:
            Text with abbreviations expanded
        """
        if not abbreviations or not text:
            return text
        
        result = text
        
        for pattern, _abbrev, expansion in self._get_compiled_patterns(abbreviations):
            def replace_match(match):
                matched_text = match.group(0)
                # Preserve casing style
                if matched_text.isupper():
                    return expansion.upper()
                elif matched_text.islower():
                    return expansion.lower()
                elif matched_text and matched_text[0].isupper():
                    return expansion.capitalize()
                else:
                    return expansion
            
            result = pattern.sub(replace_match, result)
        
        return result
    
    def preview_expansions(self, text: str, abbreviations: dict) -> list:
        """
        Preview which abbreviations will be expanded in the text.
        
        Args:
            text: Input text to analyze
            abbreviations: Dictionary mapping abbreviations to their expansions
            
        Returns:
            List of tuples (abbreviation, expansion, position) for matches found
        """
        if not abbreviations or not text:
            return []
        
        matches = []
        
        for pattern, abbrev, expansion in self._get_compiled_patterns(abbreviations):
            for match in pattern.finditer(text):
                matches.append((abbrev, expansion, match.start()))
        
        # Sort by position
        matches.sort(key=lambda x: x[2])
        return matches

    def split_soundboard_segments(self, text: str) -> list:
        """Split text into ordered text and soundboard token segments.

        Returns a list of dictionaries in the original order:
        - {"type": "text", "content": "..."}
        - {"type": "sound", "slot": "1"}

        Only strict [1]..[99] tokens are recognized. Everything else remains text.
        Empty/whitespace-only text segments are skipped.
        """
        if not text:
            return []

        segments = []
        last_end = 0

        for match in self._soundboard_token_pattern.finditer(text):
            start, end = match.span()
            if start > last_end:
                text_segment = text[last_end:start]
                if text_segment.strip():
                    segments.append({"type": "text", "content": text_segment})

            slot_num = int(match.group(1))
            if 1 <= slot_num <= 99:
                segments.append({"type": "sound", "slot": str(slot_num)})
            else:
                token_text = text[start:end]
                if token_text.strip():
                    segments.append({"type": "text", "content": token_text})

            last_end = end

        if last_end < len(text):
            trailing_text = text[last_end:]
            if trailing_text.strip():
                segments.append({"type": "text", "content": trailing_text})

        if not segments and text.strip():
            return [{"type": "text", "content": text}]

        return segments
