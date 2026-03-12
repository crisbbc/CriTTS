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
        self._sections: List[Dict] = []
        
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
        """Create a section header label and add a sidebar button for it."""
        parent_widget = parent or getattr(self, "scroll", self.tab)
        label = ctk.CTkLabel(
            parent_widget,
            text=text,
            font=ctk.CTkFont(size=FONT_LG, weight=FONT_WEIGHT_BOLD)
        )

        # Add to sections tracking
        self._sections.append({"title": text, "label": label})

        # If sidebar exists, add a button
        if hasattr(self, "sidebar"):
            btn = ctk.CTkButton(
                self.sidebar,
                text=text,
                fg_color="transparent",
                text_color=("gray10", "gray90"),
                hover_color=("gray70", "gray30"),
                anchor="w",
                font=ctk.CTkFont(size=FONT_SM),
                command=lambda l=label: self._scroll_to_section(l)
            )
            btn.pack(fill="x", padx=5, pady=2)

        return label

    def _scroll_to_section(self, label: ctk.CTkLabel):
        """Scroll the main scrollable frame to the given label."""
        if not hasattr(self, "scroll"):
            return

        # Ensure UI is updated so we get correct coordinates
        self.scroll.update_idletasks()

        try:
            # We use parent canvas to scroll
            canvas = self.scroll._parent_canvas
            # Get label's Y position relative to the scrollable frame
            target_y = label.winfo_y()

            # The canvas bounding box tells us the total scrollable height
            bbox = canvas.bbox("all")
            if bbox:
                total_height = bbox[3]
                if total_height > 0:
                    # The fraction to scroll to is exactly the element's Y position divided by total height
                    fraction = target_y / total_height
                    # Use slightly less to give a tiny bit of padding
                    fraction = max(0.0, fraction - 0.01)
                    canvas.yview_moveto(fraction)
        except Exception as e:
            print(f"Error scrolling: {e}")
            pass

    def setup_layout(self):
        """Setup the two-pane layout with a sidebar on the left and scrollable content on the right."""
        # Main layout container
        self.layout_frame = ctk.CTkFrame(self.tab, fg_color="transparent")
        self.layout_frame.pack(fill="both", expand=True, padx=0, pady=0)

        # Left sidebar for navigation
        self.sidebar = ctk.CTkScrollableFrame(self.layout_frame, width=150, corner_radius=0, fg_color="transparent")
        self.sidebar.pack(side="left", fill="y", padx=(10, 0), pady=10)

        # Right content area
        self.scroll = ctk.CTkScrollableFrame(self.layout_frame, corner_radius=0, fg_color="transparent")
        self.scroll.pack(side="right", fill="both", expand=True, padx=10, pady=10)
    
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