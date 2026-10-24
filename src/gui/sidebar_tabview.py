"""Settings navigation: one list of categories on the left, one page on the right.

Replaces a top tab strip plus a per-tab section list (two navigation levels
for one window) with a single level.
"""

from typing import Any, Callable, Dict, Optional

import customtkinter as ctk

from .theme_constants import FONT_MD, RADIUS_MD, SPACING_BASE, SPACING_MD, SPACING_SM

NAV_WIDTH = 188


class SidebarTabView(ctk.CTkFrame):
    """Drop-in for the subset of ``CTkTabview`` the settings window uses.

    ``add(name)`` returns the page frame for *name*, ``set``/``get`` select and
    read the current page, and *command* runs after the user picks a page.
    *labels* maps page names to the text shown in the list.
    """

    def __init__(
        self,
        master: Any,
        *,
        surface_theme: Dict[str, Any],
        command: Optional[Callable[[], None]] = None,
        labels: Optional[Dict[str, str]] = None,
    ):
        super().__init__(master, fg_color="transparent", corner_radius=0)
        self._theme = surface_theme
        self._command = command
        self._labels = labels or {}
        self._pages: Dict[str, ctk.CTkFrame] = {}
        self._buttons: Dict[str, ctk.CTkButton] = {}
        self._current: Optional[str] = None

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._nav = ctk.CTkFrame(self, width=NAV_WIDTH, fg_color=surface_theme["pane_fg"], corner_radius=0)
        self._nav.grid(row=0, column=0, sticky="ns")
        self._nav.pack_propagate(False)
        ctk.CTkFrame(self._nav, height=SPACING_MD, fg_color="transparent").pack(fill="x")

        self._content = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self._content.grid(row=0, column=1, sticky="nsew")

    def add(self, name: str) -> ctk.CTkFrame:
        """Create the page for *name* and its entry in the list."""
        page = ctk.CTkFrame(self._content, fg_color="transparent", corner_radius=0)
        button = ctk.CTkButton(
            self._nav,
            text=self._labels.get(name, name),
            anchor="w",
            height=34,
            corner_radius=RADIUS_MD,
            font=ctk.CTkFont(size=FONT_MD),
            command=lambda page_name=name: self._select(page_name, notify=True),
        )
        button.pack(fill="x", padx=SPACING_SM, pady=(0, SPACING_BASE))
        self._pages[name] = page
        self._buttons[name] = button
        self._style_button(name, selected=False)
        if self._current is None:
            self._select(name, notify=False)
        return page

    def set(self, name: str) -> None:
        """Show page *name* without running *command* (like ``CTkTabview.set``)."""
        self._select(name, notify=False)

    def get(self) -> str:
        """Return the name of the page being shown."""
        return self._current or ""

    def step(self, offset: int) -> None:
        """Move the selection *offset* pages up or down the list, wrapping around."""
        names = list(self._pages)
        if not names:
            return
        index = names.index(self._current) if self._current in names else 0
        self._select(names[(index + offset) % len(names)], notify=True)

    def _select(self, name: str, *, notify: bool) -> None:
        if name not in self._pages or name == self._current:
            return
        if self._current is not None:
            self._pages[self._current].pack_forget()
            self._style_button(self._current, selected=False)
        self._pages[name].pack(fill="both", expand=True)
        self._style_button(name, selected=True)
        self._current = name
        if notify and self._command is not None:
            self._command()

    def _style_button(self, name: str, *, selected: bool) -> None:
        theme = self._theme
        if selected:
            # A raised neutral surface, not the accent: selection is state,
            # and the window's one accent is reserved for Save.
            self._buttons[name].configure(
                fg_color=theme["section_fg"],
                hover_color=theme["section_fg"],
                text_color=theme["text_primary"],
            )
        else:
            self._buttons[name].configure(
                fg_color="transparent",
                hover_color=theme["sidebar_button_hover"],
                text_color=theme["text_secondary"],
            )
