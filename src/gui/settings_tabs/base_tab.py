"""
Base Tab Class
Abstract base class for settings tabs.
"""

import logging
import tkinter

import customtkinter as ctk
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional, List, Dict, Tuple

from ..theme_constants import (
    SPACING_XS,
    SPACING_SM,
    SPACING_MD,
    SPACING_LG,
    FONT_SM,
    FONT_MD,
    FONT_LG,
    FONT_WEIGHT_BOLD,
    RADIUS_MD,
    get_color_for_state,
    get_settings_surface_theme,
)

SETTINGS_CARD_BOUNDARY_RULES: Tuple[str, ...] = (
    "Top-level sections are flat (a heading, separated from the previous section by a divider); "
    "the only boxed surfaces are read-only text and lists.",
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
        "manual_adapters": ("Complex subsection spacing across chatbox, viseme, and typing indicator controls",),
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


logger = logging.getLogger(__name__)


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
        on_change: Optional[Callable] = None,
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

        # Track labels that need dynamic wraplength.
        #
        # The three coalescing-related states cooperate to damp the
        # CustomTkinter redraw cascade that would otherwise fire when the
        # Settings window pops up at the new 980x720 dimensions:
        #
        #   *_pending_wraplength*    -- latest width captured from `_on_scroll_resize`;
        #                               consumed by the debounced apply.
        #   *_pending_wraplength_job* -- Tk `after()` job ID for the queued apply
        #                               (None when nothing is scheduled).
        #   *_wraplength_apply_in_progress*  -- True while a callback is actively
        #                               running `update_wraplength`, gates
        #                               `_on_scroll_resize` so a label.configure()
        #                               cascade can't pile on more scheduling.
        #   *_last_applied_wraplength*  -- last wraplength we actually pushed to
        #                               the labels; lets us short-circuit no-op
        #                               events and freshly-scheduled callbacks.
        self._wraplength_labels: List[ctk.CTkLabel] = []
        self._sections: List[Dict] = []
        self._pending_wraplength: Optional[int] = None
        self._pending_wraplength_job: Optional[str] = None
        self._wraplength_apply_in_progress: bool = False
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
            # Not section_fg: that is the card behind the button, so the
            # button vanished into it on hover.
            "hover_color": surface_theme["button_neutral_hover"],
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
        """Update wraplength for all tracked labels.

        *available_width* is the width of the scroll pane.  Each label wraps
        at that width minus the horizontal padding of its own container chain;
        otherwise text inside a section card is wider than the card and Tk
        crops it on both sides.
        """
        # Padding is set once at build time, so each label's inset is walked
        # once and cached; resize drags then cost one configure per label.
        insets: Dict[int, int] = getattr(self, "_wrap_insets", None) or {}
        self._wrap_insets = insets
        for label in self._wraplength_labels:
            try:
                if label.winfo_exists():
                    inset = insets.get(id(label))
                    if inset is None:
                        inset = insets[id(label)] = self._horizontal_inset(label)
                    label.configure(wraplength=max(100, available_width - inset))
            except Exception:
                logger.debug("Label wraplength update failed", exc_info=True)

    def _horizontal_inset(self, widget: Any) -> int:
        """Sum the configured horizontal padding between *widget* and the scroll pane.

        Reads pack/grid options rather than measured sizes, so the result does
        not depend on (and cannot feed back into) the label's own width.
        """
        scroll = getattr(self, "scroll", None)
        inset = 0
        while widget is not None and widget is not scroll:
            try:
                manager = widget.winfo_manager()
                if manager == "pack":
                    info = widget.pack_info()
                elif manager == "grid":
                    info = widget.grid_info()
                else:
                    info = {}
            except Exception:
                info = {}
            # Tk reports padx as 8, "8 24" or (8, 24) depending on version;
            # a single value pads both sides.
            raw = info.get("padx", 0)
            values = raw if isinstance(raw, (tuple, list)) else str(raw).split()
            pads = [int(float(v)) for v in values] or [0]
            inset += pads[0] * 2 if len(pads) == 1 else sum(pads)
            widget = getattr(widget, "master", None)
        return inset

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
        parent: Any = None,
        register_sidebar: bool = True,
    ) -> ctk.CTkLabel:
        """Create a section header label; *register_sidebar* records it in ``_sections``."""
        surface_theme = self.get_active_surface_theme()
        parent_widget = parent or getattr(self, "scroll", self.tab)
        label = ctk.CTkLabel(
            parent_widget,
            text=text,
            font=ctk.CTkFont(size=FONT_LG, weight=FONT_WEIGHT_BOLD),
            text_color=surface_theme["text_primary"],
        )

        if register_sidebar:
            self._sections.append({"title": text, "label": label})

        return label

    def create_section_surface(
        self,
        title: str,
        parent: Any = None,
        description: Optional[str] = None,
        register_sidebar: bool = True,
    ) -> Tuple[ctk.CTkFrame, ctk.CTkFrame]:
        """Create a flat top-level section: a heading over its content.

        Sections after the first start with a divider, so the page reads as one
        list of groups instead of a stack of boxes.
        """
        parent_widget = parent or getattr(self, "scroll", self.tab)
        section_frame = ctk.CTkFrame(parent_widget, fg_color="transparent", corner_radius=0)
        content_frame = ctk.CTkFrame(section_frame, fg_color="transparent")

        section_index = getattr(self, "_section_surface_count", 0)
        self._section_surface_count = section_index + 1
        if section_index:
            self.create_separator(section_frame).pack(fill="x", pady=(0, SPACING_MD))

        header = self.create_section_header(title, parent=section_frame, register_sidebar=register_sidebar)
        header.pack(anchor="w", pady=(0, SPACING_XS))

        if description:
            description_label = self.create_description(description, parent=section_frame)
            description_label.pack(anchor="w", pady=(0, SPACING_SM))

        content_frame.pack(fill="both", expand=True, pady=(0, SPACING_SM))
        return section_frame, content_frame

    # --------------------------------------------------------------------------
    # Resize coalescing rule
    # --------------------------------------------------------------------------
    # When ``<Configure>`` fires on ``self.scroll`` (bound below in
    # ``setup_layout``), the CustomTkinter redraw path can emit a burst of
    # nested Configure events during the initial 980x720 Settings-window
    # layout pass.  Three layers protect against that cascade:
    #
    #   _pending_wraplength_job        -- the job ID returned by
    #                                     ``scroll.after(0, apply)``.  While
    #                                     a job is queued, a new
    #                                     ``<Configure>`` event short-circuits
    #                                     without scheduling another apply,
    #                                     collapsing a Configure burst into a
    #                                     single apply.  We use ``after``
    #                                     deliberately, NOT ``after_idle``,
    #                                     because Tk's ``after`` returns the
    #                                     job ID and ``after_idle`` returns
    #                                     ``None`` -- which would silently
    #                                     disable this gate.
    #   _wraplength_apply_in_progress  -- re-entrance guard so Configure
    #                                     events fired *during* an apply
    #                                     cannot pile on more scheduling.
    #   _last_applied_wraplength       -- no-op short-circuit cache so a
    #                                     resize to the same width we last
    #                                     applied skips the schedule
    #                                     entirely.
    def setup_layout(self):
        """Fill the page with one scrollable column (navigation lives in the settings window)."""
        surface_theme = self.get_active_surface_theme()

        self.tab.configure(fg_color="transparent")

        # Main layout container
        self.layout_frame = ctk.CTkFrame(self.tab, fg_color="transparent")
        self.layout_frame.pack(fill="both", expand=True, padx=0, pady=0)

        self.scroll = ctk.CTkScrollableFrame(
            self.layout_frame,
            corner_radius=0,
            fg_color="transparent",
            scrollbar_button_color=surface_theme["scrollbar_button_color"],
            scrollbar_button_hover_color=surface_theme["scrollbar_button_hover_color"],
        )
        self.scroll.pack(fill="both", expand=True, padx=(SPACING_LG, SPACING_XS), pady=(SPACING_LG, 0))

        # Update wraplength labels when the scroll pane is resized.
        # add="+" preserves CTkScrollableFrame's own <Configure> binding
        # that updates the scrollregion (without it, yview() stays (0.0,1.0)
        # and the mouse-wheel handler refuses to scroll).
        self.scroll.bind("<Configure>", self._on_scroll_resize, add="+")

    def _on_scroll_resize(self, event):
        """Update wraplength on all tracked labels when the scroll pane resizes.

        .. note::
            This handler is bound on the same `<Configure>` event as
            ``CTkScrollableFrame``'s own internal handler.  Doing so is
            required -- without ``add="+"``, ``yview`` would stay at
            ``(0.0, 1.0)`` because CTk wouldn't update its scrollregion.
        """
        new_wrap = max(100, event.width - 32)
        self._pending_wraplength = new_wrap

        # No-op: same width we already applied.
        if new_wrap == getattr(self, "_last_applied_wraplength", None):
            return

        # Re-entrance guard: a job is queued or an apply is running.  The
        # latest captured pending value will be picked up by that job.  We
        # don't want to schedule another -- that would only retrigger the
        # CustomTkinter redraw cascade that this whole handler exists to
        # avoid.
        if getattr(self, "_pending_wraplength_job", None) is not None:
            return
        if getattr(self, "_wraplength_apply_in_progress", False):
            return

        scroll_widget = getattr(self, "scroll", None)
        if scroll_widget is None:
            return

        try:
            self._pending_wraplength_job = scroll_widget.after(
                0,
                self._apply_pending_wraplength,
            )
        except Exception:
            self._pending_wraplength_job = None

    def _apply_pending_wraplength(self):
        """Apply the latest pending wraplength update with coarser coalescing.

        Sets ``_wraplength_apply_in_progress`` for the duration of the
        ``update_wraplength`` call so that ``<Configure>`` events the labels
        emit cannot destabilise the queue.  After the run, if a *newer*
        value was captured while we were configuring labels, schedule one
        more apply round so we converge to the latest pending width without
        waiting for another resize event.
        """
        pending_wrap = getattr(self, "_pending_wraplength", None)
        self._pending_wraplength = None
        self._pending_wraplength_job = None

        if pending_wrap is None or pending_wrap == getattr(self, "_last_applied_wraplength", None):
            return

        self._wraplength_apply_in_progress = True
        try:
            # Snapshot the label list: a configure() cascade can re-enter
            # the Tk event loop via `<Configure>` propagation, and a tab
            # hydration hook could mutate `_wraplength_labels` concurrently.
            self.update_wraplength(pending_wrap)
            self._last_applied_wraplength = pending_wrap
        finally:
            self._wraplength_apply_in_progress = False

        # If the apply's own configure() cascade captured a yet-newer pending
        # width, schedule one more apply to converge -- otherwise that
        # captured value would sit in `_pending_wraplength` until the next
        # resize event, which on a settled layout may not come for a while.
        newer_pending = getattr(self, "_pending_wraplength", None)
        if newer_pending is not None and newer_pending != self._last_applied_wraplength:
            scroll_widget = getattr(self, "scroll", None)
            if scroll_widget is not None:
                try:
                    self._pending_wraplength_job = scroll_widget.after(
                        0,
                        self._apply_pending_wraplength,
                    )
                except Exception:
                    self._pending_wraplength_job = None

    def create_description(self, text: str, parent: Any = None) -> ctk.CTkLabel:
        """Create a top-level section description label using shared text tokens."""
        surface_theme = self.get_active_surface_theme()
        label = ctk.CTkLabel(
            parent or self.tab,
            text=text,
            font=ctk.CTkFont(size=FONT_SM),
            text_color=surface_theme["text_primary"],
            wraplength=540,
        )
        self._wraplength_labels.append(label)
        return label

    def create_inline_frame(
        self,
        parent: Any = None,
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
        parent: Any = None,
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
        parent: Any = None,
        **kwargs: Any,
    ) -> ctk.CTkFrame:
        """Create a nested frame using the shared settings surface treatment."""
        return ctk.CTkFrame(parent or self.tab, **(self.get_nested_surface_style() | kwargs))

    def create_nested_scrollable_surface(
        self,
        parent: Any = None,
        **kwargs: Any,
    ) -> ctk.CTkScrollableFrame:
        """Create a nested scrollable surface using the shared settings surface treatment."""
        return ctk.CTkScrollableFrame(parent or self.tab, **(self.get_nested_surface_style() | kwargs))

    def create_helper_text(
        self,
        text: str,
        parent: Any = None,
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
            wraplength=540,
            justify=justify,
        )
        self._wraplength_labels.append(label)
        return label

    def create_surface_status_label(
        self,
        parent: Any = None,
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

    def create_separator(self, parent: Any = None):
        """Create a horizontal separator line."""
        surface_theme = self.get_active_surface_theme()
        # A plain Tk frame: CTkFrame draws its fill as a polygon that vanishes
        # at 1px tall.  Settings rebuilds on theme change, so a fixed color is fine.
        return tkinter.Frame(
            parent or self.tab,
            height=1,
            background=surface_theme["border_color"],
            borderwidth=0,
            highlightthickness=0,
        )
