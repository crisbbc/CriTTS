"""
Settings Tabs Module
Individual tab classes for the settings window.

This module provides modular tab classes for the settings window,
each handling a specific category of settings. This decomposition
reduces the complexity of the main SettingsWindow class and improves
code organization and maintainability.

Usage:
    from gui.settings_tabs import VoiceTab, AudioOutputTab, etc.
    
    # Create a tab
    voice_tab = VoiceTab(
        tab_widget=tabview.add("Voice"),
        settings_manager=settings,
        tts_engine=tts,
        audio_router=audio,
        parent_window=window
    )
    
    # Get settings from the tab
    settings = voice_tab.get_settings()
    
    # Validate the tab
    errors = voice_tab.validate()
"""
from .base_tab import BaseTab
from .voice_tab import VoiceTab
from .audio_output_tab import AudioOutputTab
from .appearance_tab import AppearanceTab
from .abbreviations_tab import AbbreviationsTab
from .keybinds_tab import KeybindsTab
from .behavior_tab import BehaviorTab
from .vrchat_osc_tab import VRChatOSCTab
from .advanced_tab import AdvancedTab

__all__ = [
    'BaseTab',
    'VoiceTab',
    'AudioOutputTab',
    'AppearanceTab',
    'AbbreviationsTab',
    'KeybindsTab',
    'BehaviorTab',
    'VRChatOSCTab',
    'AdvancedTab',
]
