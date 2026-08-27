"""Dedicated WayVR floating window for quick VRChat responses — ponytail: 1 file, reuse."""

import customtkinter as ctk

PANEL_W, PANEL_H = 560, 300


class WayVRQuickMenu(ctk.CTkToplevel):
    """Floating, always-on-top panel with 8 large quick-response buttons.

    Intended to run as a WayVR overlay window (``DISPLAY= WAYLAND_DISPLAY=wayland-20``)
    but works on desktop too. Reuses ``MainWindow.speak_quick_response`` pipeline,
    so no duplicated TTS/OSC logic.
    """

    def __init__(self, parent, settings_manager, speak_callback):
        super().__init__(parent)
        self._settings = settings_manager
        self._speak = speak_callback
        self.title("CriTTS — Quick Responses (WayVR)")
        self.geometry(f"{PANEL_W}x{PANEL_H}")
        self.attributes("-topmost", True)
        self.resizable(False, False)
        # ponytail: no extra theme deps, transparent so WayVR compositor handles it
        try:
            self.transient(parent)
        except Exception:
            pass

        self._vars = self._load_slots()
        self._build_ui()
        self._refresh_labels()

    def _load_slots(self) -> dict:
        data = self._settings.get("vrchat_quick_responses", {}) or {}
        if not isinstance(data, dict):
            data = {}
        return {k: (str(data.get(k, "")).strip()) for k in ("1", "2", "3", "4", "5", "6", "7", "8")}

    def _build_ui(self):
        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=12, pady=12)
        inner.grid_columnconfigure((0, 1), weight=1)
        self._btns: dict[str, ctk.CTkButton] = {}
        slots = self._load_slots()
        for idx, slot in enumerate(("1", "2", "3", "4", "5", "6", "7", "8")):
            txt = slots[slot] or f"Slot {slot} (empty)"
            btn = ctk.CTkButton(
                inner,
                text=txt[:28] + ("…" if len(txt) > 28 else ""),
                height=58,
                font=ctk.CTkFont(size=14, weight="bold"),
                command=lambda s=slot: self._on_click(s),
            )
            r, c = divmod(idx, 2)
            btn.grid(row=r, column=c, padx=6, pady=6, sticky="nsew")
            self._btns[slot] = btn
        # small refresh button
        ctk.CTkButton(inner, text="↻ Refresh", height=28, width=90, command=self._refresh_labels).grid(
            row=4, column=0, columnspan=2, pady=(4, 0)
        )

    def _refresh_labels(self):
        slots = self._load_slots()
        for slot, btn in self._btns.items():
            txt = slots[slot]
            label = (txt[:28] + "…") if len(txt) > 28 else txt
            btn.configure(text=label or f"Slot {slot} (empty)", state="normal" if txt else "disabled")

    def _on_click(self, slot: str):
        txt = self._load_slots().get(slot, "").strip()
        if not txt:
            return
        try:
            self._speak(txt)
        except Exception:
            pass
