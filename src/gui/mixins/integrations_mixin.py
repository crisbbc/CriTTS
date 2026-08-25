"""IntegrationsMixin - extracted from main_window.py (behavior unchanged)."""
from typing import Any
import logging
from ..theme_constants import (
    COLOR_NEUTRAL,
    COLOR_NEUTRAL_MEDIUM,
    COLOR_PRIMARY,
    COLOR_PRIMARY_HOVER,
)
from ..recording_overlay import RecordingOverlay
from ...vrchat import VRChatOSCClient
from ...vrchat.chatbox_controller import OscAmplitudeForwarder
from ...vrchat.viseme_mapper import VisemeMapper, AmplitudeAnalyzer
from ..gui_utils import STTState


class IntegrationsMixin:
    """Mixin methods; expects MainWindow attributes on self."""

    # Attributes/methods provided by MainWindow (mixin contract).
    _chatbox: Any
    _safe_after: Any
    _set_status: Any
    _show_error: Any
    _stop_event: Any
    _stop_typing_animation: Any
    _stt_state: Any
    _recording_overlay: Any
    _worker_thread: Any
    audio_router: Any
    keybind_manager: Any
    overlay_button: Any
    root: Any
    settings: Any
    stt_engine: Any
    tts_engine: Any


    def _on_toggle_overlay(self):
        """Handle overlay toggle button click."""
        previous_visible = self._overlay_visible
        next_visible = not previous_visible
        self.settings.set("overlay_visible", next_visible)
        if not self.settings.save_settings():
            self.settings.set("overlay_visible", previous_visible)
            self._overlay_visible = previous_visible
            self._show_error("Could not save overlay visibility.")
            return

        self._overlay_visible = next_visible
        # Update overlay visibility
        if self._overlay_visible:
            self._recording_overlay.show_overlay()
            # Sync current recording state (using state machine)
            is_recording = (self._stt_state == STTState.RECORDING)
            self._recording_overlay.set_recording(is_recording)
            # Update button appearance to active
            self.overlay_button.configure(
                fg_color=COLOR_PRIMARY,
                hover_color=COLOR_PRIMARY_HOVER
            )
        else:
            self._recording_overlay.hide_overlay()
            # Update button appearance to inactive
            self.overlay_button.configure(
                fg_color=COLOR_NEUTRAL_MEDIUM,
                hover_color=COLOR_NEUTRAL
            )

    def _setup_osc_client(self):
        """Setup OSC client for VRChat chatbox integration."""
        # Disconnect existing client if any
        if self.osc_client:
            try:
                self.osc_client.disconnect()
            except Exception:
                pass
            self.osc_client = None
        
        # Check if OSC is enabled
        if not self.settings.get("vrchat_osc_enabled", False):
            # Also clear viseme mapper when OSC is disabled
            self._setup_viseme_mapper()
            return
        
        # Get OSC settings
        ip = self.settings.get("vrchat_osc_ip", "127.0.0.1")
        port = self.settings.get("vrchat_osc_port", 9000)
        
        # Create and connect client
        try:
            self.osc_client = VRChatOSCClient(ip=ip, port=port)
            if self.osc_client.connect():
                self._set_status(f"OSC connected to {ip}:{port}", "✅")
            else:
                self._set_status(f"OSC failed to connect to {ip}:{port}", "⚠️")
                self.osc_client = None
        except Exception:
            self._set_status("OSC setup failed", "⚠️")
            self.osc_client = None
        
        # Setup viseme mapper after OSC client is configured
        self._setup_viseme_mapper()

    def refresh_vrchat_osc(self):
        """Refresh OSC client and viseme mapping after settings updates."""
        self._setup_osc_client()

    def _setup_viseme_mapper(self):
        """Setup viseme mapper for VRChat lip-sync integration."""
        # Stop and clear existing viseme mapper if any
        if self._viseme_mapper is not None:
            self._viseme_mapper.stop_viseme_animation()
            self._viseme_mapper = None
        
        self._amplitude_analyzer = None
        
        # Check if viseme is enabled and OSC client is connected
        viseme_enabled = self.settings.get("vrchat_viseme_enabled", False)
        if not viseme_enabled:
            return
        
        if self.osc_client is None:
            return
        
        # Get viseme settings
        smoothing = self.settings.get("vrchat_viseme_smoothing", 0.5)
        amplitude_enabled = self.settings.get("vrchat_voice_amplitude_enabled", False)
        
        # Instantiate viseme mapper
        self._viseme_mapper = VisemeMapper(smoothing=smoothing)
        
        # Instantiate amplitude analyzer if amplitude mode is enabled
        if amplitude_enabled:
            self._amplitude_analyzer = AmplitudeAnalyzer()

    def _setup_recording_overlay(self):
        """Setup the recording overlay window."""
        # Create the overlay
        self._recording_overlay = RecordingOverlay(self.root)
        
        # Show or hide based on saved preference
        if self._overlay_visible:
            self._recording_overlay.show_overlay()
        else:
            self._recording_overlay.hide_overlay()

    def _setup_coqui_status_callback(self):
        """Register a status callback on the Coqui TTS provider.

        The callback is invoked from a background thread whenever the Coqui
        model is being downloaded or loaded, allowing the status bar to surface
        progress information to the user.
        """
        if hasattr(self.tts_engine, "set_coqui_status_callback"):
            self.tts_engine.set_coqui_status_callback(self._on_coqui_status)

    def _on_coqui_status(self, message: str) -> None:
        """Called (from a background thread) with a Coqui model status message."""
        self._safe_after(0, lambda msg=message: self._set_status(msg, "⬇️", "info"))

    def _get_amplitude_forwarder(self) -> "OscAmplitudeForwarder":
        """Return the shared OSC amplitude forwarder, creating it on demand."""
        if self._amplitude_forwarder is None:
            self._amplitude_forwarder = OscAmplitudeForwarder(
                self._forward_voice_amplitude
            )
        return self._amplitude_forwarder

    def _forward_voice_amplitude(self, amplitude: float) -> None:
        """Send the current amplitude to the active OSC client (off the audio thread)."""
        if self.osc_client is not None:
            self.osc_client.send_voice_amplitude(amplitude)

    def shutdown(self):
        """Gracefully shutdown the main window and wait for worker threads."""
        if not self._async_callbacks_active:
            return
        # Invalidate callbacks before stopping workers.  Their finally blocks
        # can still run while this method joins the worker.
        self._async_callbacks_active = False

        # Stop typing animation if active
        if self._chatbox.is_typing_active:
            self._stop_typing_animation()
        
        # Signal stop to any running TTS operation
        self._stop_event.set()
        
        # Stop audio playback
        self.audio_router.stop_playback()
        
        # Stop viseme animation if active
        if self._viseme_mapper is not None:
            self._viseme_mapper.stop_viseme_animation()
        
        # Disconnect OSC client
        if self.osc_client:
            try:
                self.osc_client.disconnect()
            except Exception:
                pass
            self.osc_client = None
        
        # Stop the OSC amplitude forwarder thread
        if self._amplitude_forwarder is not None:
            self._amplitude_forwarder.stop()
            self._amplitude_forwarder = None

        # Shutdown STT engine if available
        if self.stt_engine:
            self.stt_engine.shutdown()
        
        # Destroy recording overlay if it exists
        if self._recording_overlay:
            try:
                self._recording_overlay.destroy()
            except Exception:
                pass
            self._recording_overlay = None
        
        # Wait for worker threads to complete (with timeout)
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
        
        # Unregister all keybinds
        self.keybind_manager.unregister_all(self.root)
