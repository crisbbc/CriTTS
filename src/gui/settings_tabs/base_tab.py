"""
Base Tab Class
Abstract base class for settings tabs.
"""
import customtkinter as ctk
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional, List, Dict

from ..theme_constants import (
    SPACING_XS, SPACING_SM, SPACING_MD, SPACING_LG,
    FONT_SM, FONT_MD, FONT_LG, FONT_WEIGHT_BOLD,
)


class BaseTab(ABC):
    """
    Abstract base class for settings tabs.
    
    Provides common functionality for all settings tabs including:
    - Reference to settings manager
    - Reference to TTS engine (optional)
    - Reference to audio router (optional)
    - Callback for settings changes
    - Common UI helpers
    """
    
    def __init__(
        self,
        tab_widget: ctk.CTkFrame,
        settings_manager: Any,
        tts_engine: Any = None,
        audio_router: Any = None,
        on_change: Optional[Callable] = None
    ):
        """
        Initialize the base tab.
        
        Args:
            tab_widget: The CTkFrame widget for this tab
            settings_manager: Settings manager instance
            tts_engine: TTS engine instance (optional)
            audio_router: Audio router instance (optional)
            on_change: Callback when settings change (optional)
        """
        self.tab = tab_widget
        self.settings = settings_manager
        self.tts_engine = tts_engine
        self.audio_router = audio_router
        self.on_change = on_change
        
        # Track labels that need dynamic wraplength
        self._wraplength_labels: List[ctk.CTkLabel] = []
        
        # Create the tab content
        self._create_content()
    
    @abstractmethod
    def _create_content(self):
        """Create the tab content. Must be implemented by subclasses."""
        pass
    
    def add_wraplength_label(self, label: ctk.CTkLabel):
        """Add a label to the wraplength tracking list."""
        self._wraplength_labels.append(label)
    
    def update_wraplength(self, available_width: int):
        """Update wraplength for all tracked labels."""
        for label in self._wraplength_labels:
            try:
                if label.winfo_exists():
                    label.configure(wraplength=available_width)
            except Exception:
                pass
    
    @abstractmethod
    def get_settings(self) -> Dict[str, Any]:
        """
        Get current settings from the tab UI.
        
        Returns:
            Dictionary of setting key -> value pairs
        """
        pass
    
    @abstractmethod
    def validate(self) -> List[str]:
        """
        Validate the tab's settings.
        
        Returns:
            List of error messages (empty if valid)
        """
        pass
    
    def create_section_header(self, text: str, parent: ctk.CTkFrame = None) -> ctk.CTkLabel:
        """Create a section header label."""
        return ctk.CTkLabel(
            parent or self.tab,
            text=text,
            font=ctk.CTkFont(size=FONT_LG, weight=FONT_WEIGHT_BOLD)
        )
    
    def create_description(self, text: str, parent: ctk.CTkFrame = None) -> ctk.CTkLabel:
        """Create a description label with gray text."""
        label = ctk.CTkLabel(
            parent or self.tab,
            text=text,
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray",
            wraplength=550
        )
        self._wraplength_labels.append(label)
        return label
    
    def create_separator(self, parent: ctk.CTkFrame = None):
        """Create a horizontal separator line."""
        return ctk.CTkFrame(parent or self.tab, height=2, fg_color="gray")