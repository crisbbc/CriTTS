"""
Keybinds Tab
Settings for keyboard shortcuts and global hotkeys.
"""
import customtkinter as ctk
from typing import Any, Callable, Optional, List, Dict

from .base_tab import BaseTab
from ..keybind_manager import KeybindManager
from ..theme_constants import (
    BUTTON_HEIGHT,
    COLOR_PRIMARY,
    COLOR_PRIMARY_HOVER,
    COLOR_WARNING,
    COLOR_WARNING_HOVER,
    FONT_SM,
    FONT_MD,
    FONT_WEIGHT_BOLD,
    SPACING_BASE,
    SPACING_MD,
    SPACING_SM,
    SPACING_XS,
)


class KeybindsTab(BaseTab):
    """Tab for keybind settings."""
    
    def __init__(
        self,
        tab_widget: ctk.CTkFrame,
        settings_manager: Any,
        tts_engine: Any = None,
        audio_router: Any = None,
        on_change: Optional[Callable] = None,
        parent_window: ctk.CTk = None
    ):
        self.parent_window = parent_window
        self._keybind_manager = KeybindManager()
        self.keybind_vars: Dict[str, ctk.StringVar] = {}
        self.keybind_validation_labels: Dict[str, ctk.CTkLabel] = {}
        self.keybind_capture_buttons: Dict[str, ctk.CTkButton] = {}
        self._capturing_keybind: Optional[str] = None
        self._capture_alt_held: bool = False
        
        super().__init__(tab_widget, settings_manager, tts_engine, audio_router, on_change)
    
    def _create_content(self):
        """Create the keybinds tab content."""
        self.setup_layout()

        surface_theme = self.get_active_surface_theme()
        keybinds_section, keybinds_content = self.create_section_surface("Keybinds")
        keybinds_section.pack(fill="both", expand=True)

        self.info_label = self.create_helper_text(
            "Keybinds work application-wide regardless of focus. Click 'Set' to capture key combinations.",
            parent=keybinds_content,
        )
        self.info_label.pack(anchor="w", pady=(0, SPACING_XS))

        self.warning_label = self.create_helper_text(
            self.format_surface_status_text(
                "Warning: Avoid system shortcuts (Alt+F4, Windows key). Leave empty to disable an action.",
                "warning",
            ),
            parent=keybinds_content,
        )
        self.warning_label.pack(anchor="w", pady=(0, SPACING_MD))

        keybinds = self.settings.get("keybinds", {})
        defaults = {
            "stop": "Escape",
            "clear": "Ctrl+T",
            "open_settings": "Ctrl+Comma",
            "voice_input": "Ctrl+Shift+V"
        }
        
        labels = {
            "stop": "Stop playback",
            "clear": "Clear text",
            "open_settings": "Open Settings",
            "voice_input": "Toggle voice input"
        }

        self.speak_info_label = self.create_helper_text(
            "Note: Speak is triggered by pressing Enter in the text box. The keybinds below control other actions.",
            parent=keybinds_content,
        )
        self.speak_info_label.pack(anchor="w", pady=(0, SPACING_SM))

        ctk.CTkLabel(
            keybinds_content,
            text="System-Wide Hotkeys:",
            font=ctk.CTkFont(size=FONT_MD, weight=FONT_WEIGHT_BOLD)
        ).pack(anchor="w", pady=(SPACING_BASE, SPACING_BASE))

        self.global_hotkeys_var = ctk.BooleanVar(value=self.settings.get("global_hotkeys_enabled", False))
        self.global_hotkeys_check = ctk.CTkCheckBox(
            keybinds_content,
            text="Enable system-wide hotkeys (work even when app is not focused)",
            variable=self.global_hotkeys_var,
            font=ctk.CTkFont(size=FONT_MD)
        )
        self.global_hotkeys_check.pack(anchor="w", pady=SPACING_BASE)

        self.global_hotkeys_info_label = self.create_helper_text(
            "When enabled, keybinds for Stop, Clear, Settings, and Voice Input will work system-wide. Requires the 'keyboard' library and administrator privileges on some systems.",
            parent=keybinds_content,
        )
        self.global_hotkeys_info_label.pack(anchor="w", pady=(0, SPACING_SM))

        ctk.CTkLabel(
            keybinds_content,
            text="Application Keybinds:",
            font=ctk.CTkFont(size=FONT_MD, weight=FONT_WEIGHT_BOLD)
        ).pack(anchor="w", pady=(SPACING_BASE, SPACING_SM))

        for action in ("stop", "clear", "open_settings", "voice_input"):
            row = ctk.CTkFrame(keybinds_content, fg_color="transparent")
            row.pack(fill="x", pady=SPACING_BASE)
            
            ctk.CTkLabel(
                row, 
                text=labels[action], 
                font=ctk.CTkFont(size=FONT_MD), 
                width=160, 
                anchor="w"
            ).pack(side="left", padx=(0, SPACING_SM))
            
            var = ctk.StringVar(value=keybinds.get(action, defaults.get(action, "")))
            self.keybind_vars[action] = var
            
            entry = ctk.CTkEntry(row, textvariable=var, width=200, font=ctk.CTkFont(size=FONT_MD))
            entry.pack(side="left", padx=SPACING_BASE)
            
            capture_btn = ctk.CTkButton(
                row,
                text="Set",
                font=ctk.CTkFont(size=FONT_SM),
                command=lambda a=action: self._start_keybind_capture(a),
                width=60,
                height=BUTTON_HEIGHT
            )
            capture_btn.pack(side="left", padx=SPACING_BASE)
            self.keybind_capture_buttons[action] = capture_btn
            
            validation_label = ctk.CTkLabel(
                row, 
                text="", 
                font=ctk.CTkFont(size=FONT_MD),
                width=110,
                text_color=surface_theme["text_secondary"],
            )
            validation_label.pack(side="left", padx=SPACING_BASE)
            self.keybind_validation_labels[action] = validation_label
            
            entry.bind("<KeyRelease>", lambda e, a=action: self._validate_keybind_entry(a))
    
    def _validate_keybind_entry(self, action_name: str):
        """Validate a keybind entry in real-time and update the visual indicator."""
        if action_name not in self.keybind_vars:
            return
        
        keybind_string = self.keybind_vars[action_name].get().strip()
        validation_label = self.keybind_validation_labels.get(action_name)
        
        if not validation_label:
            return
        
        if not keybind_string:
            validation_label.configure(text="", text_color=self.get_active_surface_theme()["text_secondary"])
            return
        
        is_valid = self._keybind_manager.validate_keybind(keybind_string)
        
        if not is_valid:
            self.configure_surface_status_label(validation_label, "Invalid", "error")
            return
        
        duplicates = []
        for other_action, other_var in self.keybind_vars.items():
            if other_action != action_name:
                other_value = other_var.get().strip()
                if other_value and other_value.lower() == keybind_string.lower():
                    duplicates.append(other_action)
        
        if duplicates:
            self.configure_surface_status_label(validation_label, "Duplicate", "warning")
        else:
            self.configure_surface_status_label(validation_label, "Ready", "success")
    
    def _start_keybind_capture(self, action_name: str):
        """Start capturing keybind for the specified action."""
        for action, btn in self.keybind_capture_buttons.items():
            if action == action_name:
                btn.configure(
                    text="Press keys...",
                    fg_color=COLOR_WARNING,
                    hover_color=COLOR_WARNING_HOVER,
                )
            else:
                btn.configure(state="disabled")
        
        self._capturing_keybind = action_name
        self._capture_alt_held = False
        
        if self.parent_window:
            self.parent_window.bind("<KeyPress>", self._on_key_capture_press)
            self.parent_window.bind("<KeyRelease>", self._on_key_capture_release)
            self.parent_window.bind("<Alt_L>", self._on_alt_press)
            self.parent_window.bind("<Alt_R>", self._on_alt_press)
            self.parent_window.bind("<KeyRelease-Alt_L>", self._on_alt_release)
            self.parent_window.bind("<KeyRelease-Alt_R>", self._on_alt_release)
            self.parent_window.focus_force()
        
        self.keybind_validation_labels[action_name].configure(
            text=self.format_surface_status_text("Capturing...", "active"),
            text_color=self.get_surface_status_text_color(),
        )
    
    def _on_alt_press(self, event):
        """Handle Alt key press during keybind capture."""
        self._capture_alt_held = True
    
    def _on_alt_release(self, event):
        """Handle Alt key release during keybind capture."""
        self._capture_alt_held = False
    
    def _on_key_capture_press(self, event):
        """Handle key press during keybind capture."""
        if not self._capturing_keybind:
            return
        
        if event.keysym in ['Control_L', 'Control_R', 'Shift_L', 'Shift_R', 'Alt_L', 'Alt_R', 'Super_L', 'Super_R']:
            return
        
        modifiers = []
        if event.state & 0x4:
            modifiers.append('Ctrl')
        if event.state & 0x1:
            modifiers.append('Shift')
        if self._capture_alt_held:
            modifiers.append('Alt')
        
        key = event.keysym
        if key in ['Return', 'Escape', 'Tab', 'BackSpace', 'Delete', 'Insert', 'Home', 'End', 'Prior', 'Next']:
            pass
        elif len(key) == 1 and key.isalnum():
            key = key.upper()
        else:
            key_mapping = {
                'space': 'Space',
                'comma': ',',
                'period': '.',
                'slash': '/',
                'semicolon': ';',
                'quote': "'",
                'backslash': '\\',
                'bracketleft': '[',
                'bracketright': ']',
                'minus': '-',
                'equal': '=',
                'grave': '`'
            }
            key = key_mapping.get(key.lower(), key)
        
        if modifiers:
            keybind_string = "+".join(modifiers + [key])
        else:
            keybind_string = key
        
        self.keybind_vars[self._capturing_keybind].set(keybind_string)
        self._validate_keybind_entry(self._capturing_keybind)
        self._stop_keybind_capture()
    
    def _on_key_capture_release(self, event):
        """Handle key release during keybind capture."""
        pass
    
    def _stop_keybind_capture(self):
        """Stop keybind capture and reset UI."""
        if not self._capturing_keybind:
            return
        
        if self.parent_window:
            self.parent_window.unbind("<KeyPress>")
            self.parent_window.unbind("<KeyRelease>")
            self.parent_window.unbind("<Alt_L>")
            self.parent_window.unbind("<Alt_R>")
            self.parent_window.unbind("<KeyRelease-Alt_L>")
            self.parent_window.unbind("<KeyRelease-Alt_R>")
        
        self._capture_alt_held = False
        
        for action, btn in self.keybind_capture_buttons.items():
            if action == self._capturing_keybind:
                btn.configure(text="Set", fg_color=COLOR_PRIMARY, hover_color=COLOR_PRIMARY_HOVER)
            else:
                btn.configure(state="normal")
        
        self._capturing_keybind = None
    
    def get_settings(self) -> Dict[str, Any]:
        """Get current settings from the tab UI."""
        keybinds_saved = {}
        for action, var in self.keybind_vars.items():
            keybind_value = (var.get() or "").strip()
            if keybind_value and self._keybind_manager.validate_keybind(keybind_value):
                keybinds_saved[action] = keybind_value
        
        return {
            "keybinds": keybinds_saved,
            "global_hotkeys_enabled": self.global_hotkeys_var.get(),
        }
    
    def validate(self) -> List[str]:
        """Validate the tab's settings."""
        errors = []
        
        # Check for invalid keybinds
        for action, var in self.keybind_vars.items():
            keybind_value = var.get().strip()
            if keybind_value and not self._keybind_manager.validate_keybind(keybind_value):
                errors.append(f"Invalid keybind for {action}: '{keybind_value}'")
        
        # Check for duplicates
        keybind_to_actions = {}
        for action, var in self.keybind_vars.items():
            keybind_value = var.get().strip()
            if keybind_value:
                normalized = keybind_value.lower()
                if normalized not in keybind_to_actions:
                    keybind_to_actions[normalized] = []
                keybind_to_actions[normalized].append(action)
        
        for keybind, actions in keybind_to_actions.items():
            if len(actions) > 1:
                action_names = [a.replace("_", " ").title() for a in actions]
                errors.append(f"Duplicate keybind '{keybind}' used by: {', '.join(action_names)}")
        
        return errors
