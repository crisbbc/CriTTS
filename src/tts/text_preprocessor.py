"""
Text Preprocessor Module
Handles text preprocessing including abbreviation expansion before TTS generation.
"""
import re
import logging

logger = logging.getLogger(__name__)


class TextPreprocessor:
    """Preprocesses text for TTS generation with abbreviation expansion."""
    
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
        
        # Sort abbreviations by length (longest first) to handle overlapping matches
        sorted_abbrevs = sorted(abbreviations.items(), key=lambda x: len(x[0]), reverse=True)
        
        result = text
        
        for abbrev, expansion in sorted_abbrevs:
            if not abbrev:
                continue
            
            # Use word boundaries for whole-word matching
            # Handle case-insensitive matching while preserving original casing style
            pattern = r'\b' + re.escape(abbrev) + r'\b'
            
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
            
            result = re.sub(pattern, replace_match, result, flags=re.IGNORECASE)
        
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
        sorted_abbrevs = sorted(abbreviations.items(), key=lambda x: len(x[0]), reverse=True)
        
        for abbrev, expansion in sorted_abbrevs:
            if not abbrev:
                continue
            
            pattern = r'\b' + re.escape(abbrev) + r'\b'
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                matches.append((abbrev, expansion, match.start()))
        
        # Sort by position
        matches.sort(key=lambda x: x[2])
        return matches
