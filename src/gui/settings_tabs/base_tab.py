"""
Base Tab Class
Abstract base class for settings tabs.
"""
import customtkinter as ctk
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional, List, Dict, Tuple

from ..theme_constants import (
    SPACING_XS, SPACING_SM, SPACING_MD, SPACING_LG,
    FONT_SM, FONT_MD, FONT_LG, FONT_WEIGHT_BOLD,
    RADIUS_MD, RADIUS_LG,
    get_color_for_state,
    get_settings_surface_theme,
)

SETTINGS_CARD_BOUNDARY_RULES: Tuple[str, ...] = (
    "Apply card treatment only to top-level section containers and shell surfaces.",
    "Keep inner rows transparent by default so alignment and widths stay unchanged.",
    "Do not wrap textboxes, lists, or notes in extra cards unless an existing secondary surface already communicates structure.",
    "Preserve anchor headers, conditional blocks, and nested scrollables without introducing extra section buttons or wrapper levels.",
)

SETTINGS_TAB_STYLE_AUDIT: Tuple[Dict[str, object], ...] = (
    {
        "tab": "Voice",
        "pattern": "dynamic-and-scroll-heavy",
        "surface_mode": "shared helpers plus manual adapters",
        "manual_adapters": (
            "Voice info panel nested surface",
            "Favorites and recent scrollable frames",
            "Search/selection/preview sections where plain labels currently define structure",
        ),
    },
    {
        "tab": "Audio Output",
        "pattern": "textbox-heavy",
        "surface_mode": "shared helpers plus local readability alignment",
        "manual_adapters": (
            "Device Information textbox surface/readability",
            "VB-Cable warning readability within the section container",
        ),
    },
    {
        "tab": "Appearance",
        "pattern": "standard-form",
        "surface_mode": "direct shared shell/base helpers",
        "manual_adapters": ("None beyond section wrapper hookup.",),
    },
    {
        "tab": "Abbreviations",
        "pattern": "textbox-heavy",
        "surface_mode": "shared helpers plus textbox/readability adapter",
        "manual_adapters": (
            "Abbreviation editor textbox surface",
            "Usage Tips readability inside refreshed surfaces",
        ),
    },
    {
        "tab": "Keybinds",
        "pattern": "row-heavy",
        "surface_mode": "shared helpers plus lightweight row-spacing adapter",
        "manual_adapters": ("Keybind row spacing and alignment",),
    },
    {
        "tab": "Behavior",
        "pattern": "standard-form",
        "surface_mode": "direct shared shell/base helpers",
        "manual_adapters": ("Only if descriptive copy needs spacing tuning.",),
    },
    {
        "tab": "Soundboard",
        "pattern": "row-heavy",
        "surface_mode": "shared helpers plus lightweight row-spacing adapter",
        "manual_adapters": ("Soundboard utility row spacing",),
    },
    {
        "tab": "VRChat OSC",
        "pattern": "stacked-mixed-controls",
        "surface_mode": "shared helpers plus manual adapters",
        "manual_adapters": (
            "Complex subsection spacing across chatbox, viseme, and typing indicator controls",
        ),
    },
    {
        "tab": "Advanced",
        "pattern": "dynamic-and-textbox-heavy",
        "surface_mode": "shared helpers plus manual adapters",
        "manual_adapters": (
            "Cache stats textbox",
            "Dynamic cache/status panel readability",
        ),
    },
    {
        "tab": "TTS Provider",
        "pattern": "conditional",
        "surface_mode": "shared helpers plus manual adapters",
        "manual_adapters": (
            "Provider description surface",
            "Conditional Coqui settings frame",
            "Info-note treatment without turning notes into extra cards",
        ),
    },
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
        self._pending_wraplength: Optional[int] = None
        self._pending_wraplength_job: Optional[str] = None
        self._last_applied_wraplength: Optional[int] = None
        
        # Create the tab content
        self._create_content()

    @staticmethod
    def get_active_surface_theme() -> Dict[str, Any]:
        """Return appearance-aware settings surface tokens for live UI rendering."""
        try:
            appearance_mode = ctk.get_appearance_mode()
        except Exception:
            appearance_mode = "Dark"
        return get_settings_surface_theme(appearance_mode)

    @staticmethod
    def get_section_surface_style() -> Dict[str, Any]:
        """Return reusable styling for top-level settings section cards."""
        surface_theme = BaseTab.get_active_surface_theme()
        return {
            "fg_color": surface_theme["section_fg"],
            "corner_radius": surface_theme["section_corner_radius"],
            "border_width": 1,
            "border_color": surface_theme["border_color"],
        }

    @staticmethod
    def get_input_surface_style() -> Dict[str, Any]:
        """Return reusable styling for nested textboxes and read-only text surfaces."""
        return {
            **BaseTab.get_nested_surface_style(),
            "text_color": BaseTab.get_active_surface_theme()["text_primary"],
        }

    @staticmethod
    def get_nested_surface_style() -> Dict[str, Any]:
        """Return reusable styling for nested informational/read-only surfaces."""
        surface_theme = BaseTab.get_active_surface_theme()
        return {
            "fg_color": surface_theme["pane_fg"],
            "corner_radius": RADIUS_MD,
            "border_width": 1,
            "border_color": surface_theme["border_color"],
        }

    @staticmethod
    def get_status_text_color(state: str) -> str:
        """Return an accessible semantic status color for helper/status copy."""
        return get_color_for_state(state)

    @staticmethod
    def get_surface_status_text_color() -> str:
        """Return the readable text color used for small status copy on section cards."""
        return BaseTab.get_active_surface_theme()["text_supporting"]

    @staticmethod
    def format_surface_status_text(message: str, state: str) -> str:
        """Prefix small surface status copy with a semantic marker while keeping text readable."""
        if not message:
            return ""

        prefixes = {
            "active": "• ",
            "error": "✕ ",
            "warning": "⚠ ",
            "success": "✓ ",
            "idle": "• ",
        }
        return f"{prefixes.get(state, '')}{message}"

    @staticmethod
    def configure_surface_status_label(label: ctk.CTkLabel, message: str, state: str) -> None:
        """Apply readable surface status styling to an existing label."""
        label.configure(
            text=BaseTab.format_surface_status_text(message, state),
            text_color=BaseTab.get_surface_status_text_color(),
        )

    @staticmethod
    def get_subtle_button_style() -> Dict[str, Any]:
        """Return a shared subtle button style for low-emphasis actions inside section cards."""
        surface_theme = BaseTab.get_active_surface_theme()
        return {
            "fg_color": surface_theme["pane_fg"],
            "hover_color": surface_theme["section_fg"],
            "text_color": surface_theme["text_primary"],
            "border_width": 1,
            "border_color": surface_theme["border_color"],
        }
    
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
    
    def create_section_header(
        self,
        text: str,
        parent: ctk.CTkFrame = None,
        register_sidebar: bool = True,
    ) -> ctk.CTkLabel:
        """Create a section header label and add a sidebar button for it."""
        surface_theme = self.get_active_surface_theme()
        parent_widget = parent or getattr(self, "scroll", self.tab)
        label = ctk.CTkLabel(
            parent_widget,
            text=text,
            font=ctk.CTkFont(size=FONT_LG, weight=FONT_WEIGHT_BOLD),
            text_color=surface_theme["text_primary"],
        )

        # Add to sections tracking
        if register_sidebar:
            self._sections.append({"title": text, "label": label})

        # If sidebar exists, add a button
        if register_sidebar and hasattr(self, "sidebar"):
            btn = ctk.CTkButton(
                self.sidebar,
                text=text,
                fg_color="transparent",
                hover_color=surface_theme["sidebar_button_hover"],
                text_color=surface_theme["text_secondary"],
                anchor="w",
                font=ctk.CTkFont(size=FONT_SM),
                corner_radius=RADIUS_MD,
                command=lambda l=label: self._scroll_to_section(l)
            )
            btn.pack(fill="x", padx=SPACING_XS, pady=2)

        return label

    def create_section_surface(
        self,
        title: str,
        parent: ctk.CTkFrame = None,
        description: Optional[str] = None,
        register_sidebar: bool = True,
    ) -> Tuple[ctk.CTkFrame, ctk.CTkFrame]:
        """Create a reusable top-level section card and inner content frame."""
        parent_widget = parent or getattr(self, "scroll", self.tab)
        section_frame = ctk.CTkFrame(parent_widget, **self.get_section_surface_style())
        content_frame = ctk.CTkFrame(section_frame, fg_color="transparent")

        header = self.create_section_header(title, parent=section_frame, register_sidebar=register_sidebar)
        header.pack(anchor="w", padx=SPACING_LG, pady=(SPACING_LG, SPACING_XS))

        if description:
            description_label = self.create_description(description, parent=section_frame)
            description_label.pack(anchor="w", padx=SPACING_LG, pady=(0, SPACING_SM))

        content_frame.pack(fill="both", expand=True, padx=SPACING_LG, pady=(0, SPACING_LG))
        return section_frame, content_frame

    def _scroll_to_section(self, label: ctk.CTkLabel):
        """Scroll the main scrollable frame to the given label.

        Walks up the widget hierarchy from *label* to ``self.scroll`` accumulating
        Y offsets at each level.  This correctly handles labels that live inside
        nested intermediate frames (e.g. _pitch_section_frame, _piper_sliders_frame)
        rather than being direct children of the scroll frame.
        """
        if not hasattr(self, "scroll"):
            return

        # Ensure UI is updated so we get correct coordinates
        self.scroll.update_idletasks()

        try:
            canvas = self.scroll._parent_canvas

            # Accumulate Y by walking from label up to self.scroll
            target_y = 0
            widget = label
            while widget is not None and widget is not self.scroll:
                target_y += widget.winfo_y()
                widget = widget.master

            bbox = canvas.bbox("all")
            if bbox:
                total_height = bbox[3]
                if total_height > 0:
                    # Small offset so the header isn't flush with the top
                    fraction = max(0.0, target_y / total_height - 0.01)
                    canvas.yview_moveto(fraction)
        except Exception as e:
            print(f"Error scrolling: {e}")
            pass

    def setup_layout(self):
        """Setup the two-pane layout with a sidebar on the left and scrollable content on the right."""
        surface_theme = self.get_active_surface_theme()

        self.tab.configure(fg_color="transparent")

        # Main layout container
        self.layout_frame = ctk.CTkFrame(self.tab, fg_color="transparent")
        self.layout_frame.pack(fill="both", expand=True, padx=0, pady=0)
        
        self.sidebar_shell = ctk.CTkFrame(
            self.layout_frame,
            width=170,
            fg_color=surface_theme["pane_fg"],
            corner_radius=RADIUS_LG,
            border_width=1,
            border_color=surface_theme["border_color"],
        )
        self.sidebar_shell.pack(side="left", fill="y", padx=(SPACING_MD, SPACING_SM), pady=SPACING_MD)
        self.sidebar_shell.pack_propagate(False)

        # Left sidebar for navigation
        self.sidebar = ctk.CTkScrollableFrame(
            self.sidebar_shell,
            width=150,
            corner_radius=0,
            fg_color="transparent",
            scrollbar_button_color=surface_theme["scrollbar_button_color"],
            scrollbar_button_hover_color=surface_theme["scrollbar_button_hover_color"],
        )
        self.sidebar.pack(fill="both", expand=True, padx=SPACING_XS, pady=SPACING_XS)

        self.content_shell = ctk.CTkFrame(
            self.layout_frame,
            fg_color=surface_theme["pane_fg"],
            corner_radius=RADIUS_LG,
            border_width=1,
            border_color=surface_theme["border_color"],
        )
        self.content_shell.pack(side="right", fill="both", expand=True, padx=(SPACING_SM, SPACING_MD), pady=SPACING_MD)

        # Right content area
        self.scroll = ctk.CTkScrollableFrame(
            self.content_shell,
            corner_radius=0,
            fg_color="transparent",
            scrollbar_button_color=surface_theme["scrollbar_button_color"],
            scrollbar_button_hover_color=surface_theme["scrollbar_button_hover_color"],
        )
        self.scroll.pack(fill="both", expand=True, padx=SPACING_MD, pady=SPACING_MD)

        # Update wraplength labels when the scroll pane is resized.
        # add="+" preserves CTkScrollableFrame's own <Configure> binding
        # that updates the scrollregion (without it, yview() stays (0.0,1.0)
        # and the mouse-wheel handler refuses to scroll).
        self.scroll.bind("<Configure>", self._on_scroll_resize, add="+")
    
    def _on_scroll_resize(self, event):
        """Update wraplength on all tracked labels when the scroll pane resizes."""
        new_wrap = max(100, event.width - 32)
        self._pending_wraplength = new_wrap

        if new_wrap == getattr(self, "_last_applied_wraplength", None):
            return

        if getattr(self, "_pending_wraplength_job", None) is not None:
            return

        scroll_widget = getattr(self, "scroll", None)
        if scroll_widget is None:
            return

        try:
            self._pending_wraplength_job = scroll_widget.after_idle(self._apply_pending_wraplength)
        except Exception:
            self._pending_wraplength_job = None

    def _apply_pending_wraplength(self):
        """Apply the latest pending wraplength update after the current resize churn settles."""
        pending_wrap = getattr(self, "_pending_wraplength", None)
        self._pending_wraplength = None
        self._pending_wraplength_job = None

        if pending_wrap is None or pending_wrap == getattr(self, "_last_applied_wraplength", None):
            return

        self.update_wraplength(pending_wrap)
        self._last_applied_wraplength = pending_wrap

    def create_description(self, text: str, parent: ctk.CTkFrame = None) -> ctk.CTkLabel:
        """Create a top-level section description label using shared text tokens."""
        surface_theme = self.get_active_surface_theme()
        label = ctk.CTkLabel(
            parent or self.tab,
            text=text,
            font=ctk.CTkFont(size=FONT_SM),
            text_color=surface_theme["text_primary"],
            wraplength=100
        )
        self._wraplength_labels.append(label)
        return label

    def create_inline_frame(
        self,
        parent: ctk.CTkFrame = None,
        *,
        fill: str = "x",
        pady: Any = 5,
        padx: Any = 0,
    ) -> ctk.CTkFrame:
        """Create and pack a transparent inline frame for dense settings rows."""
        frame = ctk.CTkFrame(parent or self.tab, fg_color="transparent")
        frame.pack(fill=fill, pady=pady, padx=padx)
        return frame

    def create_setting_label(
        self,
        text: str,
        parent: ctk.CTkFrame = None,
        *,
        font_size: int = FONT_MD,
        font_weight: Optional[str] = None,
        width: Optional[int] = None,
        anchor: str = "w",
    ) -> ctk.CTkLabel:
        """Create a standard field label for inputs inside section cards."""
        font_kwargs: Dict[str, Any] = {"size": font_size}
        if font_weight is not None:
            font_kwargs["weight"] = font_weight
        label_kwargs: Dict[str, Any] = {
            "text": text,
            "font": ctk.CTkFont(**font_kwargs),
            "anchor": anchor,
        }
        if width is not None:
            label_kwargs["width"] = width
        return ctk.CTkLabel(parent or self.tab, **label_kwargs)

    def create_nested_surface_frame(
        self,
        parent: ctk.CTkFrame = None,
        **kwargs: Any,
    ) -> ctk.CTkFrame:
        """Create a nested frame using the shared settings surface treatment."""
        return ctk.CTkFrame(parent or self.tab, **(self.get_nested_surface_style() | kwargs))

    def create_nested_scrollable_surface(
        self,
        parent: ctk.CTkFrame = None,
        **kwargs: Any,
    ) -> ctk.CTkScrollableFrame:
        """Create a nested scrollable surface using the shared settings surface treatment."""
        return ctk.CTkScrollableFrame(parent or self.tab, **(self.get_nested_surface_style() | kwargs))

    def create_helper_text(
        self,
        text: str,
        parent: ctk.CTkFrame = None,
        *,
        font_size: int = FONT_SM,
        justify: str = "left",
        text_color: Optional[str] = None,
    ) -> ctk.CTkLabel:
        """Create readable supporting copy using shared settings text tokens."""
        surface_theme = self.get_active_surface_theme()
        label = ctk.CTkLabel(
            parent or self.tab,
            text=text,
            font=ctk.CTkFont(size=font_size),
            text_color=text_color or surface_theme["text_supporting"],
            wraplength=100,
            justify=justify,
        )
        self._wraplength_labels.append(label)
        return label

    def create_surface_status_label(
        self,
        parent: ctk.CTkFrame = None,
        *,
        text: str = "",
        wraplength: int = 500,
        justify: str = "left",
    ) -> ctk.CTkLabel:
        """Create a readable status label for use inside section cards."""
        label = ctk.CTkLabel(
            parent or self.tab,
            text=text,
            font=ctk.CTkFont(size=FONT_SM),
            text_color=self.get_surface_status_text_color(),
            wraplength=wraplength,
            justify=justify,
        )
        self._wraplength_labels.append(label)
        return label
    
    def create_separator(self, parent: ctk.CTkFrame = None):
        """Create a horizontal separator line."""
        surface_theme = self.get_active_surface_theme()
        return ctk.CTkFrame(
            parent or self.tab,
            height=1,
            fg_color=surface_theme["border_color"],
            corner_radius=RADIUS_MD,
        )
