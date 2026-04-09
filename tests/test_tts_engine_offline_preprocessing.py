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
