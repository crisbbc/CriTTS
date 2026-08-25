"""QuickControlsMixin - extracted from main_window.py (behavior unchanged)."""
from typing import Any
import customtkinter as ctk
from ..theme_constants import (
    get_theme_colors,
    COLOR_BG_SECONDARY,
    COLOR_NEUTRAL_LIGHTER,
    FONT_SM,
    RADIUS_MD,
    SPACING_MD,
    SPACING_SM,
)


class QuickControlsMixin:
    """Mixin methods; expects MainWindow attributes on self."""

    # Attributes/methods provided by MainWindow (mixin contract).
    _show_error: Any
    controls_toggle_button: Any
    main_frame: Any
    settings: Any


    def _apply_quick_controls_theme(self, mode: str):
        """Recolor quick controls surfaces to match the active appearance mode."""
        colors = get_theme_colors(mode)
        self.quick_controls_frame.configure(fg_color=colors["bg_secondary"])
        self._qc_rate_label.configure(text_color=colors["text_secondary"])
        self._qc_volume_label.configure(text_color=colors["text_secondary"])
        self._qc_pitch_label.configure(text_color=colors["text_secondary"])

        self.controls_toggle_button.configure(
            **self._get_toggle_button_theme_colors(
                colors=colors,
                is_active=self._quick_controls_visible,
            )
        )

    @staticmethod
    def _get_toggle_button_theme_colors(colors: dict, is_active: bool) -> dict:
        """Return the active or neutral theme colors for toggle-style control buttons."""
        if is_active:
            return {
                "fg_color": colors["button_active"],
                "hover_color": colors["button_active_hover"],
            }
        return {
            "fg_color": colors["button_neutral"],
            "hover_color": colors["button_neutral_hover"],
        }

    def _create_quick_controls(self):
        """Create the collapsible quick controls panel with rate/volume/pitch sliders."""
        self.quick_controls_frame = ctk.CTkFrame(
            self.main_frame,
            fg_color=COLOR_BG_SECONDARY,
            corner_radius=RADIUS_MD
        )
        self.quick_controls_frame.grid(
            row=3, column=0, padx=SPACING_MD, pady=(0, SPACING_SM), sticky="ew"
        )
        self.quick_controls_frame.grid_columnconfigure(0, weight=1)

        # Inner row that holds all slider groups side-by-side
        self._qc_inner = ctk.CTkFrame(self.quick_controls_frame, fg_color="transparent")
        self._qc_inner.pack(fill="x", padx=SPACING_MD, pady=(SPACING_SM, SPACING_SM))

        # --- Rate slider (always shown) ---
        self._qc_rate_group = ctk.CTkFrame(self._qc_inner, fg_color="transparent")
        self._qc_rate_group.pack(side="left", fill="x", expand=True, padx=(0, SPACING_SM))
        self._qc_rate_var = ctk.IntVar(value=self.settings.get("rate", 0))
        self._qc_rate_label = ctk.CTkLabel(
            self._qc_rate_group,
            text=f"Speed: {self._qc_rate_var.get():+d}%",
            font=ctk.CTkFont(size=FONT_SM),
            text_color=COLOR_NEUTRAL_LIGHTER
        )
        self._qc_rate_label.pack(anchor="w")
        ctk.CTkSlider(
            self._qc_rate_group,
            from_=-100, to=100, number_of_steps=200,
            variable=self._qc_rate_var,
            command=self._on_quick_rate_change
        ).pack(fill="x")

        # --- Volume slider (always shown) ---
        self._qc_volume_group = ctk.CTkFrame(self._qc_inner, fg_color="transparent")
        self._qc_volume_group.pack(side="left", fill="x", expand=True, padx=SPACING_SM)
        self._qc_volume_var = ctk.IntVar(value=self.settings.get("volume", 100))
        self._qc_volume_label = ctk.CTkLabel(
            self._qc_volume_group,
            text=f"Volume: {self._qc_volume_var.get()}%",
            font=ctk.CTkFont(size=FONT_SM),
            text_color=COLOR_NEUTRAL_LIGHTER
        )
        self._qc_volume_label.pack(anchor="w")
        ctk.CTkSlider(
            self._qc_volume_group,
            from_=0, to=100, number_of_steps=100,
            variable=self._qc_volume_var,
            command=self._on_quick_volume_change
        ).pack(fill="x")

        # --- Pitch slider (Edge TTS only) ---
        self._qc_pitch_group = ctk.CTkFrame(self._qc_inner, fg_color="transparent")
        self._qc_pitch_var = ctk.IntVar(value=self.settings.get("pitch", 0))
        self._qc_pitch_label = ctk.CTkLabel(
            self._qc_pitch_group,
            text=f"Pitch: {self._qc_pitch_var.get():+d}%",
            font=ctk.CTkFont(size=FONT_SM),
            text_color=COLOR_NEUTRAL_LIGHTER
        )
        self._qc_pitch_label.pack(anchor="w")
        ctk.CTkSlider(
            self._qc_pitch_group,
            from_=-100, to=100, number_of_steps=200,
            variable=self._qc_pitch_var,
            command=self._on_quick_pitch_change
        ).pack(fill="x")

        # Apply provider-specific slider visibility and show/hide the panel
        self._update_quick_controls_provider()
        if not self._quick_controls_visible:
            self.quick_controls_frame.grid_remove()

    def _toggle_quick_controls(self):
        """Show or hide the quick controls panel."""
        previous_visible = self._quick_controls_visible
        next_visible = not previous_visible
        self.settings.set("quick_controls_visible", next_visible)
        if not self.settings.save_settings():
            self.settings.set("quick_controls_visible", previous_visible)
            self._quick_controls_visible = previous_visible
            self._show_error("Could not save quick controls visibility.")
            return

        self._quick_controls_visible = next_visible

        if self._quick_controls_visible:
            self.quick_controls_frame.grid()
        else:
            self.quick_controls_frame.grid_remove()

        self._apply_quick_controls_theme(self.settings.get("appearance_mode", "Dark"))

    def _update_quick_controls_provider(self):
        """Show pitch slider for all providers (Coqui does not use temperature controls)."""
        if self._qc_pitch_group.winfo_manager() == "pack":
            return
        self._qc_pitch_group.pack(side="left", fill="x", expand=True, padx=(SPACING_SM, 0))

    def refresh_quick_controls(self):
        """Sync quick controls sliders from current settings (called after settings save)."""
        try:
            rate = self.settings.get("rate", 0)
            if self._qc_rate_var.get() != rate:
                self._qc_rate_var.set(rate)
                self._qc_rate_label.configure(text=f"Speed: {rate:+d}%")

            volume = self.settings.get("volume", 100)
            if self._qc_volume_var.get() != volume:
                self._qc_volume_var.set(volume)
                self._qc_volume_label.configure(text=f"Volume: {volume}%")

            pitch = self.settings.get("pitch", 0)
            if self._qc_pitch_var.get() != pitch:
                self._qc_pitch_var.set(pitch)
                self._qc_pitch_label.configure(text=f"Pitch: {pitch:+d}%")

            next_visible = self.settings.get("quick_controls_visible", False)
            visibility_changed = self._quick_controls_visible != next_visible
            self._quick_controls_visible = next_visible
            if visibility_changed:
                if self._quick_controls_visible:
                    self.quick_controls_frame.grid()
                else:
                    self.quick_controls_frame.grid_remove()
                self._apply_quick_controls_theme(self.settings.get("appearance_mode", "Dark"))

            if self._qc_pitch_group.winfo_manager() != "pack":
                self._update_quick_controls_provider()
        except Exception:
            pass

    def _persist_quick_control_value(self, key, value, variable, label, format_label):
        """Persist a quick-control setting and restore the previous value on failure."""
        previous_value = self.settings.get(key, value)
        if previous_value == value:
            if variable.get() != previous_value:
                variable.set(previous_value)
            return True
        self.settings.set(key, value)
        if self.settings.save_settings():
            label.configure(text=format_label(value))
            return True

        self.settings.set(key, previous_value)
        variable.set(previous_value)
        label.configure(text=format_label(previous_value))
        self._show_error("Could not save quick controls.")
        return False

    def _on_quick_rate_change(self, value):
        """Handle quick controls rate slider change."""
        v = int(round(float(value)))
        self._persist_quick_control_value(
            "rate",
            v,
            self._qc_rate_var,
            self._qc_rate_label,
            lambda current_value: f"Speed: {current_value:+d}%",
        )

    def _on_quick_volume_change(self, value):
        """Handle quick controls volume slider change."""
        v = int(round(float(value)))
        self._persist_quick_control_value(
            "volume",
            v,
            self._qc_volume_var,
            self._qc_volume_label,
            lambda current_value: f"Volume: {current_value}%",
        )

    def _on_quick_pitch_change(self, value):
        """Handle quick controls pitch slider change."""
        v = int(round(float(value)))
        self._persist_quick_control_value(
            "pitch",
            v,
            self._qc_pitch_var,
            self._qc_pitch_label,
            lambda current_value: f"Pitch: {current_value:+d}%",
        )
