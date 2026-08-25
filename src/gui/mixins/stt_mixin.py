"""STTMixin - extracted from main_window.py (behavior unchanged)."""
from typing import Any
import logging
from ..theme_constants import (
    COLOR_ACCENT,
    COLOR_ACCENT_HOVER,
    COLOR_DANGER,
    COLOR_DANGER_HOVER,
    COLOR_TRANSCRIBING,
)
from ..gui_utils import STTState


class STTMixin:
    """Mixin methods; expects MainWindow attributes on self."""

    # Attributes/methods provided by MainWindow (mixin contract).
    _STT_TIMEOUT_MS: Any
    _cancel_after: Any
    _chatbox: Any
    _on_speak: Any
    _overlay_visible: Any
    _recording_overlay: Any
    _refresh_after_text_mutation: Any
    _safe_after: Any
    _set_status: Any
    _stt_spinner_frames: Any
    _text_preprocessor: Any
    settings: Any
    stt_engine: Any
    text_input: Any
    voice_button: Any


    def _set_stt_state(self, new_state: str):
        """
        Safely transition STT state and update UI accordingly.
        
        This method ensures the voice button is always in a consistent state
        and handles timeout management for transcription operations.
        
        Args:
            new_state: One of STTState constants (IDLE, RECORDING, TRANSCRIBING, ERROR)
        """
        old_state = self._stt_state
        self._stt_state = new_state
        
        logger = logging.getLogger(__name__)
        logger.debug(f"STT state transition: {old_state} -> {new_state}")
        
        # Cancel any existing timeout timer
        if self._stt_timeout_timer:
            self._cancel_after(self._stt_timeout_timer)
            self._stt_timeout_timer = None
        
        # Stop spinner animation if not transcribing
        if new_state != STTState.TRANSCRIBING:
            self._stop_stt_spinner()
        
        # Update UI based on new state
        if new_state == STTState.IDLE:
            self._restore_voice_button()
            
        elif new_state == STTState.RECORDING:
            self.voice_button.configure(
                text="⏹  Stop Voice",
                fg_color=COLOR_DANGER,
                hover_color=COLOR_DANGER_HOVER,
                state="normal"
            )
            # Sync overlay state
            if self._overlay_visible and self._recording_overlay:
                self._recording_overlay.set_recording(True)
                
        elif new_state == STTState.TRANSCRIBING:
            self.voice_button.configure(
                text="⏳  Transcribing...",
                fg_color=COLOR_TRANSCRIBING,
                state="disabled"
            )
            # Sync overlay state
            if self._overlay_visible and self._recording_overlay:
                self._recording_overlay.set_recording(False)
            # Start spinner animation
            self._start_stt_spinner()
            # Set timeout to restore button if transcription hangs
            self._stt_timeout_timer = self._safe_after(
                self._STT_TIMEOUT_MS,
                self._on_stt_timeout
            )
            
        elif new_state == STTState.ERROR:
            self.voice_button.configure(
                text="⚠  Error",
                fg_color=COLOR_DANGER,
                hover_color=COLOR_DANGER_HOVER,
                state="normal"
            )
            # Sync overlay state
            if self._overlay_visible and self._recording_overlay:
                self._recording_overlay.set_recording(False)
            # Auto-reset to IDLE after 2 seconds
            self._safe_after(2000, lambda: self._set_stt_state(STTState.IDLE))

    def _on_stt_timeout(self):
        """Handle transcription timeout - restore button and show error."""
        self._stt_timeout_timer = None
        
        if self._stt_state == STTState.TRANSCRIBING:
            self._set_status("⚠ Transcription timed out (30s)", "⚠️")
            self._set_stt_state(STTState.ERROR)

    def _start_stt_spinner(self):
        """Start the loading spinner animation on voice button during transcription."""
        self._stt_spinner_running = True
        self._stt_spinner_index = 0
        self._animate_stt_spinner()

    def _animate_stt_spinner(self):
        """Animate the spinner frames during transcription."""
        if not self._stt_spinner_running:
            return
        
        if self._stt_state == STTState.TRANSCRIBING:
            # Update button text with current spinner frame
            frame = self._stt_spinner_frames[self._stt_spinner_index]
            try:
                self.voice_button.configure(text=f"{frame}  Transcribing...")
            except Exception:
                pass  # Button may have been destroyed
            
            # Cycle through frames
            self._stt_spinner_index = (self._stt_spinner_index + 1) % len(self._stt_spinner_frames)
            
            # Schedule next frame
            self._safe_after(400, self._animate_stt_spinner)

    def _stop_stt_spinner(self):
        """Stop the spinner animation."""
        self._stt_spinner_running = False

    def _on_voice_input(self):
        """Handle voice input button click - toggle recording."""
        self._on_voice_input_toggle()

    def _on_voice_input_toggle(self):
        """Handle voice input toggle keybind - toggle recording based on current state."""
        if not self.stt_engine:
            self._set_status("Voice input not available", "⚠️")
            return
        
        if self._stt_state == STTState.IDLE:
            # Start recording
            success = self.stt_engine.start_listening()
            if success:
                self._set_stt_state(STTState.RECORDING)
                self._set_status("🎙 Listening… press keybind again to stop", "🎙")
            else:
                self._set_status("Failed to start voice recording", "⚠️")
                
        elif self._stt_state == STTState.RECORDING:
            # Stop recording and start transcription
            self._set_stt_state(STTState.TRANSCRIBING)
            self._set_status("⏳ Transcribing…", "⏳")
            self.stt_engine.stop_and_transcribe(
                on_result=self._on_stt_result_safe,
                on_error=self._on_stt_error_safe
            )

    def _on_stt_result_safe(self, text: str):
        """Handle successful STT transcription with guaranteed state restoration."""
        # Use root.after to safely update UI from background thread
        self._safe_after(0, lambda: self._handle_stt_result_safe(text))

    def _handle_stt_result_safe(self, text: str):
        """Safely handle STT result with guaranteed state restoration."""
        try:
            self._insert_stt_text(text)
        except Exception as e:
            logging.getLogger(__name__).error("Error processing STT result: %s", e)
            self._set_status(f"⚠ Error processing text: {e}", "⚠️")
            self._set_stt_state(STTState.ERROR)
        else:
            # Only transition to IDLE if no exception occurred
            self._set_stt_state(STTState.IDLE)

    def _on_stt_error_safe(self, exception: Exception):
        """Handle STT error with guaranteed state restoration."""
        # Use root.after to safely update UI from background thread
        self._safe_after(0, lambda: self._handle_stt_error_safe(exception))

    def _handle_stt_error_safe(self, exception: Exception):
        """Safely handle STT error with guaranteed state restoration."""
        try:
            self._handle_stt_error(exception)
        finally:
            # Always restore to ERROR state (which auto-resets to IDLE)
            self._set_stt_state(STTState.ERROR)

    def _on_stt_result(self, text: str):
        """Handle successful STT transcription (called from background thread)."""
        # Use root.after to safely update UI from background thread
        self._safe_after(0, lambda: self._insert_stt_text(text))

    def _insert_stt_text(self, text: str):
        """Insert transcribed text into the text input (called on main thread)."""
        # Apply abbreviation expansion if enabled
        apply_abbreviations = self.settings.get("stt_apply_abbreviations", False)
        if apply_abbreviations:
            abbreviations = self.settings.get("abbreviations", {})
            if abbreviations:
                text = self._text_preprocessor.expand_abbreviations(text, abbreviations)
        
        # Apply word corrections if configured
        corrections = self.settings.get("stt_corrections", {})
        if corrections:
            text = self._apply_stt_corrections(text, corrections)
        
        # Insert text at current cursor position
        self.text_input.insert("insert", text)
        self._refresh_after_text_mutation()
        
        # Update status
        self._set_status("✅ Voice input added", "✅")
        
        # Check if auto-speak is enabled and automatically speak the text
        if self.settings.get("stt_auto_speak", False) and text.strip():
            # Automatically trigger speak after a short delay to let UI update
            self._safe_after(100, self._on_speak)

    def _send_chatbox_message(self, text: str, play_notification_sound: bool, show_keyboard: bool):
        """Send a message to the VRChat chatbox and track cooldown timing."""
        if not self._chatbox.send_message(text, play_notification_sound, show_keyboard):
            self._set_status("Failed to send to VRChat chatbox", "⚠️")

    @staticmethod
    def _apply_stt_corrections(text: str, corrections: dict) -> str:
        """Apply word-level corrections to STT text."""
        if not corrections or not text:
            return text

        words = text.split()
        corrected_words = []

        for word in words:
            word_lower = word.lower()
            if word_lower in corrections:
                correction = corrections[word_lower]
                if word.isupper():
                    correction = correction.upper()
                elif word and word[0].isupper():
                    correction = correction.capitalize()
                corrected_words.append(correction)
            else:
                corrected_words.append(word)

        return " ".join(corrected_words)

    def _on_stt_error(self, exception: Exception):
        """Handle STT error (called from background thread)."""
        # Use root.after to safely update UI from background thread
        self._safe_after(0, lambda: self._handle_stt_error(exception))

    def _handle_stt_error(self, exception: Exception):
        """Handle STT error on main thread."""
        # Show appropriate error message
        import speech_recognition as sr
        if isinstance(exception, sr.UnknownValueError):
            self._set_status("⚠ Could not understand audio", "⚠️")
        elif isinstance(exception, sr.RequestError):
            self._set_status("⚠ Network error - check connection", "⚠️")
        else:
            self._set_status(f"⚠ Voice input error: {str(exception)}", "⚠️")

    def _restore_voice_button(self):
        """Restore voice button to idle state."""
        self.voice_button.configure(
            text="🎙  Voice",
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            state="normal"
        )
        # Sync overlay state
        if self._overlay_visible and self._recording_overlay:
            self._recording_overlay.set_recording(False)

    def on_stt_auto_stop(self):
        """
        Handle STT auto-stop event (called from STTEngine when buffer limit is hit).
        
        This method is called from the audio callback thread, so it uses root.after
        to safely update the UI on the main thread.
        """
        # Schedule UI update on main thread
        self._safe_after(0, self._handle_stt_auto_stop)

    def _handle_stt_auto_stop(self):
        """Handle STT auto-stop on the main thread."""
        # If we were recording, transition to transcribing
        if self._stt_state == STTState.RECORDING:
            self._set_stt_state(STTState.TRANSCRIBING)
            self._set_status("⏳ Transcribing…", "⏳")
            self.stt_engine.stop_and_transcribe(
                on_result=self._on_stt_result_safe,
                on_error=self._on_stt_error_safe
            )
        
        # Update status to inform user
        self._set_status("⚠ Recording auto-stopped (5 min limit reached)", "⚠️")
