"""TextEditorMixin - extracted from main_window.py (behavior unchanged)."""
from typing import Any
import tkinter as tk


class TextEditorMixin:
    """Mixin methods; expects MainWindow attributes on self."""

    # Attributes/methods provided by MainWindow (mixin contract).
    _on_speak: Any
    _schedule_voice_indicator_update: Any
    root: Any
    settings: Any
    text_input: Any


    def _get_line_tag_bounds(self, cursor_index: str) -> tuple[str, str]:
        """Return the text bounds used for the highlighted line tag."""
        line_num = cursor_index.split(".")[0]
        return f"{line_num}.0", f"{line_num}.end"

    def _highlight_current_line(self):
        """Incrementally retag only the old and new active line."""
        new_start, new_end = self._get_line_tag_bounds(self.text_input.index("insert"))
        current_ranges = self.text_input.tag_ranges("current_line")

        if current_ranges:
            for range_index in range(0, len(current_ranges), 2):
                current_start = str(current_ranges[range_index])
                current_end = str(current_ranges[range_index + 1])

                if current_start == new_start and current_end == new_end:
                    return

                self.text_input.tag_remove("current_line", current_start, current_end)

        self.text_input.tag_add("current_line", new_start, new_end)

    def _refresh_after_text_mutation(self):
        """Refresh lightweight editor state after any text mutation."""
        self._highlight_current_line()
        self._schedule_voice_indicator_update()

    def _bind_text_editing_shortcuts(self):
        """Bind text editing shortcuts with higher priority to prevent custom keybind interference."""
        # These bindings ensure standard text editing works properly
        text_shortcuts = {
            "<Control-a>": lambda e: self._on_text_select_all(),
            "<Control-c>": lambda e: self._on_text_copy(),
            "<Control-v>": lambda e: self._on_text_paste(),
            "<Control-x>": lambda e: self._on_text_cut(),
            "<Control-z>": lambda e: self._on_text_undo(),
        }
        
        for sequence, handler in text_shortcuts.items():
            self.text_input.bind(sequence, handler)

    def _on_text_select_all(self):
        """Select all text in the input."""
        self.text_input.tag_add("sel", "1.0", "end")
        self.text_input.mark_set("insert", "end")
        return "break"

    def _on_text_copy(self):
        """Copy selected text to clipboard."""
        try:
            selected = self.text_input.get("sel.first", "sel.last")
            self.root.clipboard_clear()
            self.root.clipboard_append(selected)
        except Exception:
            pass  # No selection
        return "break"

    def _on_text_paste(self):
        """Paste text from clipboard."""
        try:
            clipboard_text = self.root.clipboard_get()
            self.text_input.insert("insert", clipboard_text)
            self._refresh_after_text_mutation()
        except Exception:
            pass  # Clipboard empty or error
        return "break"

    def _on_text_cut(self):
        """Cut selected text to clipboard."""
        try:
            selected = self.text_input.get("sel.first", "sel.last")
            self.root.clipboard_clear()
            self.root.clipboard_append(selected)
            self.text_input.delete("sel.first", "sel.last")
            self._refresh_after_text_mutation()
        except Exception:
            pass  # No selection
        return "break"

    def _on_text_undo(self):
        """Undo last action (limited support)."""
        try:
            self.text_input.edit_undo()
        except Exception:
            pass  # Nothing to undo
        return "break"

    def _on_enter_key(self, event):
        """Handle Enter key press - prevent line breaks unless Shift is held."""
        # Only trigger speak action, don't insert newline
        self._on_speak()
        return "break"  # Prevent default Enter behavior (new line)

    def _on_shift_enter_key(self, event):
        """Handle Shift+Enter key press - allow line breaks."""
        # Allow default Shift+Enter behavior (new line)
        return "continue"  # Allow default behavior

    def _setup_text_context_menu(self):
        """Create and bind right-click context menu for text input."""
        self._text_context_menu = tk.Menu(self.root, tearoff=0)
        edit_menu = tk.Menu(self._text_context_menu, tearoff=0)
        edit_menu.add_command(label="Cut", command=self._on_text_cut)
        edit_menu.add_command(label="Copy", command=self._on_text_copy)
        edit_menu.add_command(label="Paste", command=self._on_text_paste)
        edit_menu.add_separator()
        edit_menu.add_command(label="Select All", command=self._on_text_select_all)
        self._text_context_menu.add_cascade(label="Edit", menu=edit_menu)

        self._text_sound_token_menu = tk.Menu(self._text_context_menu, tearoff=0)
        self._text_context_menu.add_cascade(label="Insert Sound Token", menu=self._text_sound_token_menu)
        self._rebuild_text_token_menu()

        # Windows/Linux right-click is Button-3; include additional bindings for macOS compatibility.
        self.text_input.bind("<Button-3>", self._show_text_context_menu, add="+")
        self.text_input.bind("<Button-2>", self._show_text_context_menu, add="+")
        self.text_input.bind("<Control-Button-1>", self._show_text_context_menu, add="+")

    def _get_soundboard_slots_for_menu(self) -> list:
        """Return sorted slot numbers for context-menu token insertion."""
        soundboard_slots = self.settings.get("soundboard_slots", {})
        if not isinstance(soundboard_slots, dict):
            return [str(i) for i in range(1, 11)]

        slots = []
        for key in soundboard_slots.keys():
            if isinstance(key, str) and key.isdigit():
                slot_num = int(key)
                if 1 <= slot_num <= 99:
                    slots.append(slot_num)

        if not slots:
            slots = list(range(1, 11))

        return [str(slot) for slot in sorted(set(slots))]

    def _rebuild_text_token_menu(self):
        """Rebuild token menu so it tracks current soundboard settings."""
        if self._text_sound_token_menu is None:
            return

        self._text_sound_token_menu.delete(0, "end")
        for slot in self._get_soundboard_slots_for_menu():
            self._text_sound_token_menu.add_command(
                label=f"Insert [{slot}]",
                command=lambda s=slot: self._insert_soundboard_token(s),
            )

    def _show_text_context_menu(self, event):
        """Show the text context menu at mouse position."""
        if self._text_context_menu is None:
            return "break"

        self._rebuild_text_token_menu()

        try:
            click_index = self.text_input.index(f"@{event.x},{event.y}")
            self.text_input.mark_set("insert", click_index)
        except Exception:
            pass

        self.text_input.focus_set()

        try:
            self._text_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._text_context_menu.grab_release()

        return "break"

    def _insert_soundboard_token(self, slot: str):
        """Insert a soundboard token at the current cursor position."""
        self.text_input.insert("insert", f"[{slot}]")
        self._refresh_after_text_mutation()
        self.text_input.focus_set()
