import sys
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("sounddevice", MagicMock())
sys.modules.setdefault("soundfile", MagicMock())
sys.modules.setdefault("pyloudnorm", MagicMock())
sys.modules.setdefault("keyboard", MagicMock())
sys.modules.setdefault("langid", MagicMock())

from src.tts.tts_engine import TTSEngine


def _make_settings(provider: str, voice: str, coqui_language: str = "en"):
    settings = {
        "tts_provider": provider,
        "voice": voice,
        "coqui_language": coqui_language,
    }
    manager = MagicMock()
    manager.get.side_effect = lambda key, default=None: settings.get(key, default)
    return manager


class TestOfflinePreprocessing:
    @pytest.mark.asyncio
    async def test_coqui_preprocess_uses_configured_language_for_numbers(self):
        engine = TTSEngine(
            settings_manager=_make_settings(
                provider="coqui",
                voice="Claribel Dervla",
                coqui_language="fr",
            )
        )

        processed = await engine.preprocess_text("J'ai 21 pommes.", "Claribel Dervla")

        assert "vingt-un" in processed

    @pytest.mark.asyncio
    async def test_piper_preprocess_uses_voice_locale_for_numbers(self):
        engine = TTSEngine(
            settings_manager=_make_settings(
                provider="piper",
                voice="de_DE-thorsten-medium",
            )
        )

        processed = await engine.preprocess_text("Wir haben 22 Optionen.", "de_DE-thorsten-medium")

        assert "zweiundzwanzig" in processed

    def test_add_natural_pauses_preserves_offline_clause_breaks(self):
        engine = TTSEngine(
            settings_manager=_make_settings(
                provider="piper",
                voice="en_US-lessac-medium",
            )
        )

        processed = engine._add_natural_pauses("First paragraph\n\nSecond:wait;now—go", "piper")

        assert processed == "First paragraph.\n\nSecond: wait; now, go."


class TestNumberPreprocessing:
    def _engine(self):
        return TTSEngine(
            settings_manager=_make_settings(
                provider="edge",
                voice="en-US-AriaNeural",
            )
        )

    def test_decimals_left_untouched(self):
        engine = self._engine()
        assert engine._format_numbers("Pi is 3.14", "en-US-AriaNeural") == "Pi is 3.14"

    def test_currency_left_untouched(self):
        engine = self._engine()
        assert engine._format_numbers("That costs $5.99", "en-US-AriaNeural") == "That costs $5.99"

    def test_thousands_separators_left_untouched(self):
        engine = self._engine()
        assert engine._format_numbers("Population 1,234,567", "en-US-AriaNeural") == "Population 1,234,567"

    def test_times_left_untouched(self):
        engine = self._engine()
        assert engine._format_numbers("Meet at 12:30", "en-US-AriaNeural") == "Meet at 12:30"

    def test_years_left_untouched(self):
        engine = self._engine()
        assert engine._format_numbers("The year 2026", "en-US-AriaNeural") == "The year 2026"

    def test_percentages_left_untouched(self):
        engine = self._engine()
        assert engine._format_numbers("Up 50%", "en-US-AriaNeural") == "Up 50%"

    def test_standalone_small_numbers_still_convert(self):
        engine = self._engine()
        assert engine._format_numbers("I have 21 apples", "en-US-AriaNeural") == "I have twenty-one apples"

    def test_number_before_sentence_period_still_converts(self):
        engine = self._engine()
        assert engine._format_numbers("I have 21.", "en-US-AriaNeural") == "I have twenty-one."

    def test_number_before_comma_still_converts(self):
        engine = self._engine()
        assert engine._format_numbers("I have 21, and 22 more", "en-US-AriaNeural") == "I have twenty-one, and twenty-two more"

    def test_ordinals_left_untouched(self):
        engine = self._engine()
        assert engine._format_numbers("Finish in 1st place", "en-US-AriaNeural") == "Finish in 1st place"

    def test_number_at_start_of_text_still_converts(self):
        engine = self._engine()
        assert engine._format_numbers("21 apples", "en-US-AriaNeural") == "twenty-one apples"

    def test_number_at_end_of_text_still_converts(self):
        engine = self._engine()
        assert engine._format_numbers("I have 22", "en-US-AriaNeural") == "I have twenty-two"
