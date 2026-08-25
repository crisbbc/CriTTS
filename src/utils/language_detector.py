"""
Language Detection Module
Provides robust language detection with multiple backends and fallback mechanisms.
"""
import re
import logging
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
import threading

# langid import with graceful degradation
try:
    import langid
    _LANGID_AVAILABLE = True
except ImportError:
    langid = None  # type: ignore[assignment]
    _LANGID_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class LanguageDetectionResult:
    """Result of language detection with confidence and metadata."""
    language: str  # ISO 639-1 code (e.g., 'en', 'es', 'fr')
    confidence: float  # 0.0 to 1.0
    method: str  # 'langid', 'script', 'heuristic', 'fallback'
    is_mixed: bool = False  # True if text contains multiple languages
    segment_languages: Optional[List[Tuple[str, str]]] = None  # [(text_segment, lang), ...]


class LanguageDetector:
    """
    Robust language detection with multiple backends.
    
    Detection strategy:
    1. Script-based detection for non-Latin scripts (CJK, Cyrillic, Arabic, etc.)
    2. langid for fast, accurate detection on remaining text
    3. Heuristic scoring as fallback for edge cases
    """
    
    # Supported languages with their default voices (for TTS integration)
    SUPPORTED_LANGUAGES = {
        'en', 'es', 'fr', 'de', 'it', 'pt', 'zh', 'ja', 'ko', 'ru', 'ar', 'hi',
        'nl', 'pl', 'tr', 'vi', 'th', 'id', 'ms', 'cs', 'da', 'fi', 'el', 'hu',
        'no', 'ro', 'sk', 'sv', 'uk', 'bg', 'hr', 'sl', 'et', 'lv', 'lt'
    }
    
    # Language to locale mapping for voice selection
    LANGUAGE_TO_LOCALE = {
        'en': 'en-US',
        'es': 'es-ES',
        'fr': 'fr-FR',
        'de': 'de-DE',
        'it': 'it-IT',
        'pt': 'pt-BR',
        'zh': 'zh-CN',
        'ja': 'ja-JP',
        'ko': 'ko-KR',
        'ru': 'ru-RU',
        'ar': 'ar-SA',
        'hi': 'hi-IN',
        'nl': 'nl-NL',
        'pl': 'pl-PL',
        'tr': 'tr-TR',
        'vi': 'vi-VN',
        'th': 'th-TH',
        'id': 'id-ID',
        'ms': 'ms-MY',
        'cs': 'cs-CZ',
        'da': 'da-DK',
        'fi': 'fi-FI',
        'el': 'el-GR',
        'hu': 'hu-HU',
        'no': 'nb-NO',
        'ro': 'ro-RO',
        'sk': 'sk-SK',
        'sv': 'sv-SE',
        'uk': 'uk-UA',
        'bg': 'bg-BG',
        'hr': 'hr-HR',
        'sl': 'sl-SI',
        'et': 'et-EE',
        'lv': 'lv-LV',
        'lt': 'lt-LT'
    }
    
    # Script ranges for fast detection
    SCRIPT_RANGES = {
        'zh': [
            (0x4e00, 0x9fff),   # CJK Unified Ideographs
            (0x3400, 0x4dbf),   # CJK Extension A
            (0xf900, 0xfaff),   # CJK Compatibility Ideographs
            (0x20000, 0x2a6df), # CJK Extension B (surrogate pairs)
        ],
        'ja': [
            (0x3040, 0x309f),   # Hiragana
            (0x30a0, 0x30ff),   # Katakana
        ],
        'ko': [
            (0xac00, 0xd7af),   # Hangul Syllables
            (0x1100, 0x11ff),   # Hangul Jamo
            (0x3130, 0x318f),   # Hangul Compatibility Jamo
        ],
        'ru': [
            (0x0400, 0x04ff),   # Cyrillic
            (0x0500, 0x052f),   # Cyrillic Supplement
        ],
        'ar': [
            (0x0600, 0x06ff),   # Arabic
            (0x0750, 0x077f),   # Arabic Supplement
            (0x08a0, 0x08ff),   # Arabic Extended-A
        ],
        'hi': [
            (0x0900, 0x097f),   # Devanagari
            (0xa8e0, 0xa8ff),   # Devanagari Extended
        ],
        'th': [
            (0x0e00, 0x0e7f),   # Thai
        ],
        'el': [
            (0x0370, 0x03ff),   # Greek and Coptic
        ],
        'he': [
            (0x0590, 0x05ff),   # Hebrew
        ],
    }
    
    # Expanded common words for heuristic detection (100+ per language)
    COMMON_WORDS = {
        'en': [
            # Articles and determiners
            'the', 'a', 'an', 'this', 'that', 'these', 'those', 'my', 'your', 'his',
            'her', 'its', 'our', 'their', 'what', 'which', 'who', 'whom', 'whose',
            # Pronouns
            'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'us', 'them',
            # Common verbs
            'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has',
            'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may',
            'might', 'must', 'can', 'need', 'dare', 'ought', 'used',
            # Common nouns
            'time', 'year', 'people', 'way', 'day', 'man', 'woman', 'child', 'world',
            'life', 'hand', 'part', 'place', 'case', 'week', 'company', 'system',
            'program', 'question', 'work', 'government', 'number', 'night', 'point',
            'home', 'water', 'room', 'mother', 'area', 'money', 'story', 'fact',
            # Common adjectives
            'good', 'new', 'first', 'last', 'long', 'great', 'little', 'own', 'other',
            'old', 'right', 'big', 'high', 'different', 'small', 'large', 'next',
            'early', 'young', 'important', 'few', 'public', 'bad', 'same', 'able',
            # Prepositions and conjunctions
            'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from', 'up', 'about',
            'into', 'over', 'after', 'beneath', 'under', 'above', 'and', 'but', 'or',
            'nor', 'so', 'yet', 'both', 'either', 'neither', 'not', 'only', 'own',
            # Common adverbs
            'how', 'when', 'where', 'why', 'again', 'once', 'here', 'there', 'now',
            'then', 'today', 'always', 'never', 'very', 'often', 'still', 'already',
            # Greetings and common phrases
            'hello', 'hi', 'hey', 'thanks', 'please', 'sorry', 'excuse', 'welcome',
            'goodbye', 'bye', 'yes', 'no', 'maybe', 'okay', 'ok', 'alright',
        ],
        'es': [
            # Articles
            'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas', 'este', 'esta',
            'estos', 'estas', 'ese', 'esa', 'esos', 'esas', 'aquel', 'aquella',
            # Pronouns
            'yo', 'tú', 'él', 'ella', 'nosotros', 'nosotras', 'vosotros', 'vosotras',
            'ellos', 'ellas', 'me', 'te', 'se', 'nos', 'os', 'le', 'les', 'lo', 'la',
            # Verbs
            'ser', 'estar', 'tener', 'haber', 'hacer', 'poder', 'decir', 'ir', 'ver',
            'dar', 'saber', 'querer', 'llegar', 'pasar', 'deber', 'poner', 'parecer',
            'quedar', 'creer', 'hablar', 'llevar', 'dejar', 'seguir', 'encontrar',
            'llamar', 'venir', 'pensar', 'salir', 'volver', 'tomar', 'conocer',
            # Common words
            'y', 'o', 'pero', 'porque', 'cuando', 'donde', 'como', 'que', 'quien',
            'cual', 'cuyo', 'si', 'aunque', 'mientras', 'a', 'de', 'en', 'con', 'por',
            'para', 'sin', 'sobre', 'entre', 'hacia', 'hasta', 'desde', 'durante',
            # Greetings
            'hola', 'adiós', 'gracias', 'por favor', 'perdón', 'disculpe', 'buenos',
            'buenas', 'días', 'tardes', 'noches', 'bienvenido', 'hasta luego',
        ],
        'fr': [
            # Articles
            'le', 'la', 'les', 'un', 'une', 'des', 'du', 'au', 'aux', 'ce', 'cette',
            'ces', 'cet', 'mon', 'ton', 'son', 'ma', 'ta', 'sa', 'mes', 'tes', 'ses',
            # Pronouns
            'je', 'tu', 'il', 'elle', 'nous', 'vous', 'ils', 'elles', 'me', 'te', 'se',
            'le', 'la', 'les', 'lui', 'leur', 'y', 'en', 'qui', 'que', 'quoi', 'dont',
            # Verbs
            'être', 'avoir', 'faire', 'dire', 'aller', 'voir', 'savoir', 'pouvoir',
            'vouloir', 'venir', 'devoir', 'prendre', 'donner', 'parler', 'trouver',
            'mettre', 'aimer', 'passer', 'croire', 'entendre', 'comprendre', 'attendre',
            # Common words
            'et', 'ou', 'mais', 'donc', 'car', 'ni', 'que', 'quand', 'où', 'comment',
            'pourquoi', 'combien', 'si', 'dans', 'sur', 'sous', 'avec', 'sans', 'pour',
            'par', 'en', 'de', 'à', 'chez', 'entre', 'pendant', 'depuis', 'vers',
            # Greetings
            'bonjour', 'bonsoir', 'salut', 'au revoir', 'merci', 's\'il vous plaît',
            'pardon', 'excusez', 'bienvenue', 'à bientôt', 'bonne', 'nuit', 'journée',
        ],
        'de': [
            # Articles
            'der', 'die', 'das', 'den', 'dem', 'des', 'ein', 'eine', 'einer', 'einem',
            'einen', 'eines', 'dieser', 'diese', 'dieses', 'jener', 'jede', 'jeder',
            # Pronouns
            'ich', 'du', 'er', 'sie', 'es', 'wir', 'ihr', 'Sie', 'mich', 'dich', 'sich',
            'uns', 'euch', 'mir', 'dir', 'ihm', 'ihr', 'ihnen', 'mein', 'dein', 'sein',
            # Verbs
            'sein', 'haben', 'werden', 'können', 'müssen', 'wollen', 'sollen', 'dürfen',
            'machen', 'gehen', 'kommen', 'sehen', 'wissen', 'denken', 'nehmen', 'geben',
            'sagen', 'stehen', 'finden', 'bleiben', 'liegen', 'heißen', 'lassen', 'tun',
            # Common words
            'und', 'oder', 'aber', 'denn', 'weil', 'dass', 'wenn', 'ob', 'als', 'wie',
            'was', 'wer', 'wo', 'wann', 'warum', 'woher', 'wohin', 'in', 'auf', 'an',
            'unter', 'über', 'vor', 'hinter', 'neben', 'zwischen', 'bei', 'mit', 'von',
            # Greetings
            'hallo', 'guten', 'tag', 'morgen', 'abend', 'tschüss', 'auf wiedersehen',
            'danke', 'bitte', 'entschuldigung', 'willkommen', 'wie geht', 'geht es',
        ],
        'it': [
            # Articles
            'il', 'lo', 'la', 'i', 'gli', 'le', 'un', 'uno', 'una', 'un\'', 'questo',
            'questa', 'questi', 'queste', 'quello', 'quella', 'quelli', 'quelle',
            # Pronouns
            'io', 'tu', 'lui', 'lei', 'noi', 'voi', 'loro', 'mi', 'ti', 'ci', 'vi',
            'lo', 'la', 'li', 'le', 'ne', 'me', 'te', 'sé', 'mio', 'tuo', 'suo',
            # Verbs
            'essere', 'avere', 'fare', 'dire', 'andare', 'venire', 'vedere', 'sapere',
            'potere', 'volere', 'dovere', 'stare', 'dare', 'parlare', 'trovare',
            'prendere', 'mettere', 'tenere', 'sentire', 'chiamare', 'pensare', 'cercare',
            # Common words
            'e', 'o', 'ma', 'perché', 'quando', 'dove', 'come', 'che', 'chi', 'quale',
            'cui', 'se', 'anche', 'ancora', 'già', 'sempre', 'mai', 'forse', 'in', 'a',
            'da', 'di', 'con', 'su', 'per', 'tra', 'fra', 'senza', 'sotto', 'sopra',
            # Greetings
            'ciao', 'buongiorno', 'buonasera', 'buonanotte', 'arrivederci', 'grazie',
            'prego', 'scusa', 'scusi', 'benvenuto', 'a presto', 'come stai', 'sta',
        ],
        'pt': [
            # Articles
            'o', 'a', 'os', 'as', 'um', 'uma', 'uns', 'umas', 'este', 'esta', 'estes',
            'estas', 'esse', 'essa', 'esses', 'essas', 'aquele', 'aquela', 'aqueles',
            # Pronouns
            'eu', 'tu', 'ele', 'ela', 'nós', 'vós', 'eles', 'elas', 'me', 'te', 'se',
            'nos', 'vos', 'o', 'a', 'os', 'as', 'lhe', 'lhes', 'meu', 'teu', 'seu',
            # Verbs
            'ser', 'estar', 'ter', 'haver', 'fazer', 'poder', 'dizer', 'ir', 'ver',
            'dar', 'saber', 'querer', 'chegar', 'passar', 'dever', 'pôr', 'parecer',
            'ficar', 'crer', 'falar', 'levar', 'deixar', 'seguir', 'encontrar',
            # Common words
            'e', 'ou', 'mas', 'porque', 'quando', 'onde', 'como', 'que', 'quem', 'qual',
            'cujo', 'se', 'embora', 'enquanto', 'a', 'de', 'em', 'com', 'por', 'para',
            'sem', 'sobre', 'entre', 'para', 'desde', 'durante', 'até', 'após',
            # Greetings
            'olá', 'oi', 'tchau', 'adeus', 'obrigado', 'obrigada', 'por favor', 'desculpe',
            'bom', 'boa', 'dia', 'tarde', 'noite', 'bem-vindo', 'até logo', 'como vai',
        ],
        'ru': [
            # Pronouns
            'я', 'ты', 'он', 'она', 'оно', 'мы', 'вы', 'они', 'меня', 'тебя', 'его',
            'её', 'нас', 'вас', 'их', 'мне', 'тебе', 'ему', 'ей', 'нам', 'вам', 'им',
            'мой', 'твой', 'свой', 'наш', 'ваш', 'этот', 'этот', 'тот', 'такой',
            # Verbs (common forms)
            'быть', 'есть', 'был', 'была', 'были', 'будет', 'будут', 'иметь', 'мочь',
            'хотеть', 'знать', 'говорить', 'делать', 'идти', 'видеть', 'думать',
            'стоять', 'сидеть', 'лежать', 'жить', 'работать', 'любить', 'понимать',
            # Common words
            'и', 'а', 'но', 'или', 'если', 'что', 'как', 'где', 'когда', 'почему',
            'кто', 'чего', 'кому', 'чем', 'который', 'весь', 'всё', 'все', 'каждый',
            'в', 'на', 'с', 'из', 'от', 'к', 'по', 'за', 'под', 'над', 'между',
            # Greetings
            'привет', 'здравствуй', 'здравствуйте', 'пока', 'до свидания', 'спасибо',
            'пожалуйста', 'извините', 'добрый', 'доброе', 'утро', 'день', 'вечер',
        ],
        'zh': [
            # Common characters and words
            '的', '是', '在', '不', '了', '有', '和', '人', '这', '中', '大', '为',
            '上', '个', '国', '我', '以', '要', '他', '时', '来', '用', '们', '生',
            '到', '作', '地', '于', '出', '就', '分', '对', '成', '会', '可', '主',
            '发', '年', '动', '同', '工', '也', '能', '下', '过', '子', '说', '产',
            '种', '面', '而', '方', '后', '多', '定', '行', '学', '法', '所', '民',
            '得', '经', '十', '三', '之', '进', '着', '等', '部', '度', '家', '电',
            # Greetings and common phrases
            '你好', '您好', '谢谢', '对不起', '再见', '早上好', '晚上好', '欢迎',
            '什么', '怎么', '为什么', '哪里', '谁', '多少', '几', '吗', '呢', '吧',
        ],
        'ja': [
            # Particles
            'は', 'が', 'を', 'に', 'で', 'と', 'の', 'へ', 'や', 'も', 'か', 'ね',
            'よ', 'わ', 'が', 'を', 'に', 'で', 'と', 'の', 'へ', 'や', 'も', 'か',
            # Common words
            'する', 'ある', 'いる', 'なる', 'こと', 'もの', 'これ', 'それ', 'あれ',
            'どこ', 'だれ', 'なに', 'いつ', 'なぜ', 'どう', 'いくら', 'どれ', 'どちら',
            '私', 'あなた', '彼', '彼女', '私たち', '皆', '人', '時間', '年', '日',
            # Verbs
            '行く', '来る', '見る', '食べる', '飲む', '話す', '聞く', '読む', '書く',
            '買う', '売る', '教える', '学ぶ', '働く', '遊ぶ', '休む', '寝る', '起きる',
            # Greetings
            'こんにちは', 'こんばんは', 'おはよう', 'さようなら', 'ありがとう',
            'すみません', 'ごめんなさい', 'はじめまして', 'よろしく', 'お元気',
        ],
        'ko': [
            # Particles
            '은', '는', '이', '가', '을', '를', '에', '에서', '으로', '와', '과',
            '도', '만', '부터', '까지', '처럼', '마다', '뿐', '조차', '마저',
            # Common words
            '하다', '있다', '없다', '되다', '않다', '같다', '이것', '그것', '저것',
            '여기', '거기', '저기', '누구', '무엇', '어디', '언제', '왜', '어떻게',
            '나', '너', '그', '그녀', '우리', '너희', '그들', '사람', '시간', '년',
            # Greetings
            '안녕', '안녕하세요', '안녕히', '가세요', '계세요', '감사합니다', '고맙습니다',
            '미안합니다', '죄송합니다', '처음', '뵙겠습니다', '잘', '부탁', '드립니다',
        ],
    }
    
    # Character-based indicators for Latin script languages
    CHAR_INDICATORS = {
        'de': {'ä', 'ö', 'ü', 'ß'},
        'fr': {'â', 'ê', 'î', 'ô', 'û', 'ë', 'ï', 'ÿ', 'æ', 'œ', 'ç'},
        'es': {'ñ', '¿', '¡'},
        'pt': {'ã', 'õ', 'ç'},
        'it': {'ì', 'ò', 'ù'},
    }
    
    def __init__(self, min_confidence: float = 0.3, cache_size: int = 1000):
        """
        Initialize the language detector.
        
        Args:
            min_confidence: Minimum confidence threshold for detection (0.0-1.0)
            cache_size: Maximum number of cached detection results
        """
        self.min_confidence = min_confidence
        self._cache: Dict[str, LanguageDetectionResult] = {}
        self._cache_size = cache_size
        self._cache_lock = threading.Lock()
        
        # Precompile regex patterns for performance
        self._word_pattern = re.compile(r'\b\w+\b', re.UNICODE)
        self._sentence_pattern = re.compile(r'[.!?。！？\n]+')
        
        # Pre-calculate common words as sets for O(1) lookups
        self._common_words_sets = {lang: set(words) for lang, words in self.COMMON_WORDS.items()}

        logger.info(f"LanguageDetector initialized (langid available: {_LANGID_AVAILABLE})")
    
    def detect(self, text: str, use_cache: bool = True) -> LanguageDetectionResult:
        """
        Detect the language of the given text.
        
        Args:
            text: Input text to analyze
            use_cache: Whether to use cached results (default: True)
            
        Returns:
            LanguageDetectionResult with language, confidence, and metadata
        """
        if not text or not text.strip():
            return LanguageDetectionResult(
                language='en',
                confidence=0.0,
                method='fallback',
                is_mixed=False
            )
        
        # Check if text has any alphabetic characters
        if not any(c.isalpha() for c in text):
            return LanguageDetectionResult(
                language='en',
                confidence=0.0,
                method='fallback',
                is_mixed=False
            )
        
        # Check cache
        cache_key = text.strip().lower()
        if use_cache:
            with self._cache_lock:
                if cache_key in self._cache:
                    return self._cache[cache_key]
        
        # Perform detection
        result = self._detect_internal(text)
        
        # Cache result
        if use_cache:
            with self._cache_lock:
                if len(self._cache) >= self._cache_size:
                    # Remove oldest entry
                    oldest_key = next(iter(self._cache))
                    del self._cache[oldest_key]
                self._cache[cache_key] = result
        
        return result
    
    def _detect_internal(self, text: str) -> LanguageDetectionResult:
        """Internal detection logic."""
        text_lower = text.lower()
        
        # Step 1: Script-based detection for non-Latin scripts
        script_result = self._detect_by_script(text)
        if script_result and script_result.confidence >= 0.9:
            return script_result
        
        # Step 2: Check for exact word matches in common words (greetings, etc.)
        # This helps with short texts like "Hola", "Bonjour", etc.
        exact_match_result = self._detect_by_exact_word_match(text_lower)
        if exact_match_result:
            return exact_match_result
        
        # Step 3: Use langid if available
        if _LANGID_AVAILABLE:
            langid_result = self._detect_with_langid(text)
            if langid_result and langid_result.confidence >= self.min_confidence:
                # If we had partial script detection, combine results
                if script_result:
                    # Prefer script detection for mixed scripts
                    if script_result.confidence > langid_result.confidence:
                        return script_result
                return langid_result
        
        # Step 4: Heuristic detection as fallback
        heuristic_result = self._detect_by_heuristics(text, text_lower)
        if heuristic_result and heuristic_result.confidence >= self.min_confidence:
            return heuristic_result
        
        # Step 5: Default fallback
        return LanguageDetectionResult(
            language='en',
            confidence=0.0,
            method='fallback',
            is_mixed=False
        )
    
    def _detect_by_exact_word_match(self, text_lower: str) -> Optional[LanguageDetectionResult]:
        """Detect language by checking if the text is an exact match for a known word."""
        # Extract words from text
        words = self._word_pattern.findall(text_lower)
        
        if not words:
            return None
        
        # Check each word against common words sets
        for word in words:
            for lang, common_words_set in self._common_words_sets.items():
                if word in common_words_set:
                    # Found an exact match - return with high confidence
                    return LanguageDetectionResult(
                        language=lang,
                        confidence=0.9,
                        method='heuristic',
                        is_mixed=False
                    )
        
        return None
    
    def _detect_by_script(self, text: str) -> Optional[LanguageDetectionResult]:
        """Detect language based on character scripts."""
        if not text:
            return None
        
        script_counts: Dict[str, int] = {}
        total_script_chars = 0
        
        for char in text:
            code = ord(char)
            
            for lang, ranges in self.SCRIPT_RANGES.items():
                for start, end in ranges:
                    if start <= code <= end:
                        script_counts[lang] = script_counts.get(lang, 0) + 1
                        total_script_chars += 1
                        break
        
        if not script_counts:
            return None
        
        # Find dominant script
        dominant_lang = max(script_counts, key=lambda lang: script_counts[lang])
        dominant_count = script_counts[dominant_lang]
        
        # Calculate confidence based on proportion
        total_alpha = sum(1 for c in text if c.isalpha())
        if total_alpha == 0:
            return None
        
        confidence = min(1.0, dominant_count / total_alpha * 2)  # Scale up for confidence
        
        # Check for mixed scripts
        is_mixed = len([c for c in script_counts.values() if c > total_script_chars * 0.1]) > 1
        
        return LanguageDetectionResult(
            language=dominant_lang,
            confidence=confidence,
            method='script',
            is_mixed=is_mixed
        )
    
    def _detect_with_langid(self, text: str) -> Optional[LanguageDetectionResult]:
        """Detect language using langid library."""
        if langid is None or not _LANGID_AVAILABLE:
            return None

        try:
            # langid returns (language, confidence) where confidence is log probability
            lang, confidence = langid.classify(text)
            
            # Normalize confidence (langid returns log probabilities, typically -30 to 0)
            # Convert to 0-1 range
            normalized_conf = min(1.0, max(0.0, (confidence + 30) / 30))
            
            # Map langid language codes to our supported codes
            lang = self._map_langid_code(lang)
            
            if lang not in self.SUPPORTED_LANGUAGES:
                return None
            
            return LanguageDetectionResult(
                language=lang,
                confidence=normalized_conf,
                method='langid',
                is_mixed=False
            )
        except Exception as e:
            logger.debug(f"langid detection failed: {e}")
            return None
    
    def _map_langid_code(self, code: str) -> str:
        """Map langid language codes to our standard codes."""
        mapping = {
            'zh-cn': 'zh',
            'zh-hant': 'zh',
            'zh-yue': 'zh',  # Cantonese
            'nb': 'no',  # Norwegian Bokmål
            'nn': 'no',  # Norwegian Nynorsk
        }
        return mapping.get(code.lower(), code.lower())
    
    def _detect_by_heuristics(self, text: str, text_lower: str) -> Optional[LanguageDetectionResult]:
        """Detect language using heuristic scoring."""
        scores = self._calculate_heuristic_scores(text, text_lower)
        
        if not scores:
            return None
        
        # Sort by score
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        if not sorted_scores or sorted_scores[0][1] == 0:
            return None
        
        top_lang = sorted_scores[0][0]
        top_score = sorted_scores[0][1]
        second_score = sorted_scores[1][1] if len(sorted_scores) > 1 else 0
        
        # Calculate confidence based on score gap
        total_score = sum(scores.values())
        if total_score == 0:
            return None
        
        confidence = top_score / total_score
        
        # Require minimum score gap for confidence
        if top_score - second_score < 2.0 and confidence < 0.6:
            # Scores too close, reduce confidence
            confidence *= 0.5
        
        return LanguageDetectionResult(
            language=top_lang,
            confidence=confidence,
            method='heuristic',
            is_mixed=False
        )
    
    def _calculate_heuristic_scores(self, text: str, text_lower: str) -> Dict[str, float]:
        """Calculate heuristic language scores."""
        scores: Dict[str, float] = {lang: 0.0 for lang in self.COMMON_WORDS.keys()}
        
        # Character-based indicators
        for char in text_lower:
            for lang, chars in self.CHAR_INDICATORS.items():
                if char in chars:
                    scores[lang] = scores.get(lang, 0) + 3
        
        # Word-based scoring - always apply, not just for longer texts
        words = set(self._word_pattern.findall(text_lower))
        
        for lang, common_words_set in self._common_words_sets.items():
            matches = words.intersection(common_words_set)
            # Give higher weight to word matches for short texts
            weight = 3.0 if len(words) <= 3 else 2.0
            scores[lang] = scores.get(lang, 0) + len(matches) * weight
        
        return scores
    
    def detect_segments(self, text: str) -> List[Tuple[str, str]]:
        """
        Detect language for each segment of text.
        Useful for mixed-language text.
        
        Args:
            text: Input text that may contain multiple languages
            
        Returns:
            List of (segment, language) tuples
        """
        if not text or not text.strip():
            return [(text, 'en')]
        
        # Split into sentences
        sentences = self._sentence_pattern.split(text)
        delimiters = self._sentence_pattern.findall(text)
        
        results = []
        for i, sentence in enumerate(sentences):
            if sentence.strip():
                result = self.detect(sentence.strip())
                results.append((sentence.strip(), result.language))
                # Add back the delimiter
                if i < len(delimiters):
                    results.append((delimiters[i], results[-1][1] if results else 'en'))
        
        return results if results else [(text, 'en')]
    
    def get_primary_language(self, text: str) -> str:
        """
        Get the primary language of text, handling mixed content.
        
        Args:
            text: Input text
            
        Returns:
            Primary language code
        """
        result = self.detect(text)
        
        if result.is_mixed:
            # For mixed text, detect per segment and find most common
            segments = self.detect_segments(text)
            lang_counts: Dict[str, int] = {}
            
            for segment, lang in segments:
                lang_counts[lang] = lang_counts.get(lang, 0) + len(segment)
            
            if lang_counts:
                return max(lang_counts, key=lambda lang: lang_counts[lang])
        
        return result.language
    
    def clear_cache(self):
        """Clear the detection cache."""
        with self._cache_lock:
            self._cache.clear()
    
    def get_supported_languages(self) -> set:
        """Get set of supported language codes."""
        return self.SUPPORTED_LANGUAGES.copy()


# Singleton instance for convenience
_detector_instance: Optional[LanguageDetector] = None
_detector_lock = threading.Lock()


def get_detector(min_confidence: float = 0.3) -> LanguageDetector:
    """
    Get the singleton LanguageDetector instance.
    
    Args:
        min_confidence: Minimum confidence threshold (only used on first call)
        
    Returns:
        LanguageDetector instance
    """
    global _detector_instance
    
    if _detector_instance is None:
        with _detector_lock:
            if _detector_instance is None:
                _detector_instance = LanguageDetector(min_confidence=min_confidence)
    
    return _detector_instance


def detect_language(text: str) -> LanguageDetectionResult:
    """
    Convenience function to detect language using the singleton detector.
    
    Args:
        text: Input text to analyze
        
    Returns:
        LanguageDetectionResult
    """
    return get_detector().detect(text)