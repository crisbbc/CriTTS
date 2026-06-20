"""Lightweight Coqui voice metadata for pre-synthesis UI flows."""
from typing import Any, Dict, List

XTTS_LANGUAGES = [
    "en", "es", "fr", "de", "it", "pt", "pl", "tr", "ru",
    "nl", "cs", "ar", "zh-cn", "ja", "hu", "ko", "hi",
]

COQUI_VOICES: List[Dict[str, Any]] = [
    {"name": "Claribel Dervla",  "short_name": "Claribel Dervla",  "gender": "Female", "locale": "en-US", "language_code": "en", "provider": "coqui"},
    {"name": "Daisy Studious",   "short_name": "Daisy Studious",   "gender": "Female", "locale": "en-US", "language_code": "en", "provider": "coqui"},
    {"name": "Gracie Wise",      "short_name": "Gracie Wise",      "gender": "Female", "locale": "en-US", "language_code": "en", "provider": "coqui"},
    {"name": "Tammie Ema",       "short_name": "Tammie Ema",       "gender": "Female", "locale": "en-US", "language_code": "en", "provider": "coqui"},
    {"name": "Alison Dietlinde", "short_name": "Alison Dietlinde", "gender": "Female", "locale": "en-US", "language_code": "en", "provider": "coqui"},
    {"name": "Ana Florence",     "short_name": "Ana Florence",     "gender": "Female", "locale": "en-US", "language_code": "en", "provider": "coqui"},
    {"name": "Annmarie Nele",    "short_name": "Annmarie Nele",    "gender": "Female", "locale": "en-US", "language_code": "en", "provider": "coqui"},
    {"name": "Asya Anara",       "short_name": "Asya Anara",       "gender": "Female", "locale": "en-US", "language_code": "en", "provider": "coqui"},
    {"name": "Brenda Stern",     "short_name": "Brenda Stern",     "gender": "Female", "locale": "en-US", "language_code": "en", "provider": "coqui"},
    {"name": "Gitta Nikolina",   "short_name": "Gitta Nikolina",   "gender": "Female", "locale": "en-US", "language_code": "en", "provider": "coqui"},
    {"name": "Henriette Usha",   "short_name": "Henriette Usha",   "gender": "Female", "locale": "en-US", "language_code": "en", "provider": "coqui"},
    {"name": "Sofia Hellen",     "short_name": "Sofia Hellen",     "gender": "Female", "locale": "en-US", "language_code": "en", "provider": "coqui"},
    {"name": "Tammy Grit",       "short_name": "Tammy Grit",       "gender": "Female", "locale": "en-US", "language_code": "en", "provider": "coqui"},
    {"name": "Tanja Adelina",    "short_name": "Tanja Adelina",    "gender": "Female", "locale": "en-US", "language_code": "en", "provider": "coqui"},
    {"name": "Vjollca Johnnie",  "short_name": "Vjollca Johnnie",  "gender": "Female", "locale": "en-US", "language_code": "en", "provider": "coqui"},
]

VOICE_NAMES = frozenset(voice["short_name"] for voice in COQUI_VOICES)


def get_coqui_voice_metadata() -> List[Dict[str, Any]]:
    """Return a copy of the built-in Coqui voices without importing the provider runtime."""
    return [dict(voice) for voice in COQUI_VOICES]
