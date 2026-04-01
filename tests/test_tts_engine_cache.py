"""
Tests for TTSEngine.get_available_voices() cache invalidation.

Verifies that the voices cache is automatically busted whenever the active
TTS provider changes, so that switching between Edge TTS and Piper TTS
always returns the new provider's voice list rather than stale cached data.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys

# Mock heavy GUI / audio dependencies that are not needed for engine tests
sys.modules.setdefault("sounddevice", MagicMock())
sys.modules.setdefault("soundfile", MagicMock())
sys.modules.setdefault("scipy", MagicMock())
sys.modules.setdefault("scipy.signal", MagicMock())
sys.modules.setdefault("pyloudnorm", MagicMock())
sys.modules.setdefault("keyboard", MagicMock())
sys.modules.setdefault("langid", MagicMock())

from src.tts.tts_engine import TTSEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine(provider: str = "edge") -> TTSEngine:
    """Create a TTSEngine backed by a mock SettingsManager."""
    mgr = MagicMock()
    mgr.get.side_effect = lambda key, default=None: (
        provider if key == "tts_provider" else default
    )
    return TTSEngine(settings_manager=mgr)


_EDGE_VOICES = [{"name": "Aria", "short_name": "en-US-AriaNeural", "provider": "edge_tts"}]
_PIPER_VOICES = [{"name": "Lessac", "short_name": "en_US-lessac-medium", "provider": "piper"}]


# ---------------------------------------------------------------------------
# Cache respects provider identity
# ---------------------------------------------------------------------------

class TestGetAvailableVoicesCacheInvalidation:

    @pytest.mark.asyncio
    async def test_provider_override_fetches_requested_provider_without_cache_pollution(self):
        """provider_override fetches the requested provider and leaves active-provider cache untouched."""
        engine = _make_engine("edge")
        edge_fetch = AsyncMock(return_value=list(_EDGE_VOICES))
        piper_fetch = AsyncMock(return_value=list(_PIPER_VOICES))

        with (
            patch.object(engine._edge_tts_provider, "get_available_voices", new=edge_fetch),
            patch.object(engine._piper_tts_provider, "get_available_voices", new=piper_fetch),
        ):
            # Override fetch should return Piper voices even when settings provider is Edge.
            override_voices = await engine.get_available_voices(provider_override="piper")
            assert any(v["provider"] == "piper" for v in override_voices)
            assert piper_fetch.call_count == 1
            assert edge_fetch.call_count == 0

            # Regular fetch still resolves and caches using the active settings provider.
            active_voices = await engine.get_available_voices()
            assert any(v["provider"] == "edge_tts" for v in active_voices)
            assert edge_fetch.call_count == 1
            assert engine._cached_provider == "edge"

    @pytest.mark.asyncio
    async def test_cache_hit_same_provider(self):
        """Second call with the same provider returns cached result (no provider fetch)."""
        engine = _make_engine("edge")
        with patch.object(
            engine._edge_tts_provider, "get_available_voices",
            new=AsyncMock(return_value=list(_EDGE_VOICES))
        ) as mock_fetch:
            await engine.get_available_voices()
            await engine.get_available_voices()

        assert mock_fetch.call_count == 1, "Should only fetch once when provider is unchanged"

    @pytest.mark.asyncio
    async def test_cache_bust_on_provider_switch(self):
        """Switching the provider invalidates the cache and fetches from the new provider."""
        # Start as Edge TTS
        mgr = MagicMock()
        current_provider = ["edge"]
        mgr.get.side_effect = lambda key, default=None: (
            current_provider[0] if key == "tts_provider" else default
        )
        engine = TTSEngine(settings_manager=mgr)

        edge_fetch = AsyncMock(return_value=list(_EDGE_VOICES))
        piper_fetch = AsyncMock(return_value=list(_PIPER_VOICES))

        with (
            patch.object(engine._edge_tts_provider, "get_available_voices", new=edge_fetch),
            patch.object(engine._piper_tts_provider, "get_available_voices", new=piper_fetch),
        ):
            # First call – Edge TTS
            voices_edge = await engine.get_available_voices()
            assert any(v["provider"] == "edge_tts" for v in voices_edge)
            assert edge_fetch.call_count == 1
            assert piper_fetch.call_count == 0

            # Switch provider to Piper (simulates settings change)
            current_provider[0] = "piper"

            # Second call – should bypass the Edge TTS cache and fetch Piper voices
            voices_piper = await engine.get_available_voices()
            assert any(v["provider"] == "piper" for v in voices_piper)
            assert edge_fetch.call_count == 1, "Edge TTS should not be fetched again"
            assert piper_fetch.call_count == 1, "Piper should be fetched once after switch"

    @pytest.mark.asyncio
    async def test_switching_back_refetches_edge(self):
        """Switching back from Piper to Edge TTS also busts the cache."""
        mgr = MagicMock()
        current_provider = ["piper"]
        mgr.get.side_effect = lambda key, default=None: (
            current_provider[0] if key == "tts_provider" else default
        )
        engine = TTSEngine(settings_manager=mgr)

        edge_fetch = AsyncMock(return_value=list(_EDGE_VOICES))
        piper_fetch = AsyncMock(return_value=list(_PIPER_VOICES))

        with (
            patch.object(engine._edge_tts_provider, "get_available_voices", new=edge_fetch),
            patch.object(engine._piper_tts_provider, "get_available_voices", new=piper_fetch),
        ):
            await engine.get_available_voices()  # Piper cached
            current_provider[0] = "edge"
            voices = await engine.get_available_voices()  # Should re-fetch Edge

        assert any(v["provider"] == "edge_tts" for v in voices)
        assert edge_fetch.call_count == 1

    @pytest.mark.asyncio
    async def test_clear_voices_cache_resets_provider_tracking(self):
        """clear_voices_cache() resets _cached_provider so next call always refetches."""
        engine = _make_engine("edge")
        edge_fetch = AsyncMock(return_value=list(_EDGE_VOICES))

        with patch.object(engine._edge_tts_provider, "get_available_voices", new=edge_fetch):
            await engine.get_available_voices()  # Populates cache
            engine.clear_voices_cache()           # Should also reset _cached_provider
            await engine.get_available_voices()   # Must refetch

        assert edge_fetch.call_count == 2
        assert engine._cached_provider == "edge"
