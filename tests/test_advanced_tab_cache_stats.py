"""Regression tests for AdvancedTab cache statistics loading."""
from unittest.mock import MagicMock
import sys

sys.modules.setdefault("customtkinter", MagicMock())

from src.gui.settings_tabs.advanced_tab import AdvancedTab


def test_load_data_populates_cache_stats_immediately():
    """AdvancedTab._load_data() should populate cache stats on initial refresh."""
    tab = object.__new__(AdvancedTab)
    tab.tts_engine = MagicMock()
    tab.tts_engine.get_audio_cache_statistics.return_value = {
        "enabled": True,
        "entries": 3,
        "size_mb": 1.5,
        "hit_rate": 50.0,
        "total_saved_time": 2.0,
        "cache_dir": "C:/cache",
    }
    tab.cache_max_size_var = MagicMock()
    tab.cache_max_size_var.get.return_value = 500
    tab.cache_size_value_label = MagicMock()
    tab.cache_stats_text = MagicMock()

    AdvancedTab._load_data(tab)

    tab.cache_stats_text.delete.assert_called_once_with("1.0", "end")
    tab.cache_stats_text.insert.assert_called_once()
    _, inserted_text = tab.cache_stats_text.insert.call_args.args
    assert "Cached Entries: 3" in inserted_text
    assert "Current Size: 1.50 MB / 500 MB" in inserted_text
