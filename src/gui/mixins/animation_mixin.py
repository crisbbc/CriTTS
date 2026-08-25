"""AnimationMixin - extracted from main_window.py (behavior unchanged)."""
import datetime
import logging
from typing import Optional, Any
from ..theme_constants import (
    SPACING_SM,
    ANIMATION_NORMAL,
    BUTTON_WIDTH_DEFAULT,
    COLOR_NEUTRAL,
    COLOR_NEUTRAL_MEDIUM,
    COLOR_SUCCESS,
    COLOR_WARNING,
    COLOR_ACCENT,
    COLOR_ACCENT_HOVER,
)
from ..gui_utils import LatestWinsTextAnalysisScheduler, DeferredTextAnalysisRequest


class AnimationMixin:
    """Mixin methods; expects MainWindow attributes on self."""

    # Attributes/methods provided by MainWindow (mixin contract).
    _cancel_after: Any
    _safe_after: Any
    _voice_indicator_scheduler: Any
    activity_indicator: Any
    audio_router: Any
    clear_button: Any
    progress_label: Any
    settings: Any
    speak_button: Any
    status_label: Any
    stop_button: Any
    text_input: Any
    tts_engine: Any
    voice_indicator_value: Any


    def _update_status(self):
        """Update status label with current voice and device."""
        voice = self.settings.get("voice", "Default")
        device_idx = self.settings.get("device_index")
        
        if device_idx is not None:
            devices = self.audio_router.get_audio_devices()
            device_name = next(
                (d['name'] for d in devices if d['index'] == device_idx),
                "Unknown Device"
            )
        else:
            device_name = "Default Device"
        
        self.status_label.configure(
            text=f"Voice: {voice} | Output: {device_name}"
        )
        
        # Update voice indicator
        self._update_voice_indicator()

    def _update_voice_indicator(self):
        """Update the voice indicator label with current voice information."""
        self._update_voice_indicator_for_text(self.text_input.get("1.0", "end-1c"))

    def _is_latest_voice_indicator_request(self, request: Optional[DeferredTextAnalysisRequest]) -> bool:
        """Return whether deferred voice-indicator work may still update the UI."""
        return request is None or self._voice_indicator_scheduler.is_latest(request)

    def _update_voice_indicator_for_text(
        self,
        text: str,
        request: Optional[DeferredTextAnalysisRequest] = None,
    ):
        """Update the voice indicator label for a specific text snapshot."""
        voice = self.settings.get("voice", "Default")
        auto_language = self.settings.get("auto_language_detection", False)
        
        if auto_language:
            text = text.strip()
            if text:
                detected_lang = self.tts_engine._detect_language_from_text(text)
                voice_short_name = self.tts_engine._detect_language_voice(text)

                if not self._is_latest_voice_indicator_request(request):
                    return

                if detected_lang and voice_short_name:
                    language_mappings = self.settings.get("language_voice_mappings", {})
                    custom_voice = language_mappings.get(detected_lang)
                    
                    if custom_voice:
                        voice_name = custom_voice
                    else:
                        voice_info = self.tts_engine.get_voice_info(voice_short_name)
                        if voice_info:
                            voice_name = f"{voice_info['name']} ({voice_info['locale']})"
                        else:
                            voice_name = voice_short_name
                    
                    lang_names = {
                        "zh": "Chinese",
                        "ja": "Japanese", 
                        "ko": "Korean",
                        "ru": "Russian",
                        "ar": "Arabic",
                        "hi": "Hindi",
                        "es": "Spanish",
                        "pt": "Portuguese",
                        "fr": "French",
                        "de": "German",
                        "it": "Italian",
                        "en": "English"
                    }
                    
                    detected_lang_name = lang_names.get(detected_lang, detected_lang.title())
                    new_text = f"{voice_name} (Auto: {detected_lang_name})"
                    new_color = "green"

                    if not self._is_latest_voice_indicator_request(request):
                        return

                    self._animate_voice_indicator(new_text, new_color)
                else:
                    self.voice_indicator_value.configure(
                        text=f"{voice} (Auto: Unknown)",
                        text_color="orange"
                    )
            else:
                self.voice_indicator_value.configure(
                    text=f"{voice} (Auto: No text)",
                    text_color="gray"
                )
        else:
            self.voice_indicator_value.configure(
                text=voice,
                text_color="gray"
            )

    def _schedule_voice_indicator_update(self):
        """Debounce expensive voice-indicator analysis with latest-wins semantics."""
        if self._voice_indicator_timer:
            self._cancel_after(self._voice_indicator_timer)
            self._voice_indicator_timer = None

        # Do NOT snapshot the document here: ``text_input.get()`` copies the
        # entire text on every keystroke.  The text is read lazily when the
        # debounce timer fires, at most once per 300ms quiet period.
        request = self._voice_indicator_scheduler.next_request()

        self._voice_indicator_timer = self._safe_after(
            300,
            lambda pending_request=request: self._run_scheduled_voice_indicator_update(pending_request),
        )

    def _run_scheduled_voice_indicator_update(self, request: DeferredTextAnalysisRequest):
        """Run deferred voice-indicator analysis only if it is still current."""
        self._voice_indicator_timer = None

        if not getattr(self, "_async_callbacks_active", True):
            return
        if not self._voice_indicator_scheduler.is_latest(request):
            return

        text = self.text_input.get("1.0", "end-1c")
        self._update_voice_indicator_for_text(text, request=request)

    def _animate_voice_indicator(self, new_text: str, new_color: str):
        """Animate the voice indicator with smooth transitions."""
        # Guard: Skip if already animating to prevent orphaned animation chains
        if self._voice_indicator_animating:
            return
        
        current_text = self.voice_indicator_value.cget("text")
        
        # Only animate if the text actually changed
        if current_text != new_text:
            self._voice_indicator_animating = True
            # Fade out current text
            self._fade_out_text(0.15, lambda: self._fade_in_text_safe(new_text, new_color, 0.15))

    def _fade_in_text_safe(self, new_text: str, new_color: str, duration: float):
        """Fade in the new text with animation state cleanup."""
        try:
            self._fade_in_text(new_text, new_color, duration)
        finally:
            self._voice_indicator_animating = False

    def _fade_out_text(self, duration: float, callback):
        """Fade out the current text (simplified to single-step clear)."""
        # CustomTkinter doesn't support alpha/color interpolation, so just clear and callback
        self.voice_indicator_value.configure(text="")
        if callback:
            callback()

    def _fade_in_text(self, new_text: str, new_color: str, duration: float):
        """Fade in the new text."""
        self.voice_indicator_value.configure(text=new_text, text_color=new_color)
        # Simple fade in by changing opacity of the label
        self._pulse_label(self.voice_indicator_value, duration)

    def _pulse_label(self, label, duration: float):
        """Create a subtle pulse animation for a label.
        
        Note: CustomTkinter doesn't support alpha/opacity animation directly.
        This method is kept as a placeholder for potential future enhancements.
        """
        # CustomTkinter doesn't support alpha interpolation
        # The label is already visible with the new text/color
        pass

    def _update_ui_speaking(self, speaking: bool):
        """
        Update UI state based on speaking status with smooth animations.
        
        This method handles the visual feedback for TTS operations, including
        button state transitions and loading animations.
        """
        if speaking:
            # Start speaking animation
            self._tts_speaking = True
            self._start_speaking_animation()
            
            # Animate speak button to disabled/speaking state
            self._animate_button(self.speak_button, "disabled", "▶  Speaking...", COLOR_NEUTRAL_MEDIUM, ANIMATION_NORMAL)
            # Animate stop button to active state
            self._animate_button(self.stop_button, "normal", "⏹  Stop", COLOR_WARNING, ANIMATION_NORMAL)
            # Animate clear button to disabled state
            self._animate_button(self.clear_button, "disabled", "🗑  Clear", COLOR_NEUTRAL, ANIMATION_NORMAL)
        else:
            # Stop speaking animation
            self._tts_speaking = False
            self._stop_speaking_animation()
            
            # Animate speak button back to normal
            self._animate_button(self.speak_button, "normal", "▶  Speak", COLOR_SUCCESS, ANIMATION_NORMAL)
            # Animate stop button back to disabled
            self._animate_button(self.stop_button, "disabled", "⏹  Stop", COLOR_NEUTRAL_MEDIUM, ANIMATION_NORMAL)
            # Animate clear button back to normal
            self._animate_button(self.clear_button, "normal", "🗑  Clear", COLOR_NEUTRAL_MEDIUM, ANIMATION_NORMAL)

    def _start_speaking_animation(self):
        """Start the speaking animation with animated dots."""
        self._speaking_animation_running = True
        self._speaking_animation_index = 0
        self._speaking_animation_frames = ["▶  Speaking.", "▶  Speaking..", "▶  Speaking..."]
        self._animate_speaking_button()

    def _animate_speaking_button(self):
        """Animate the speaking button with cycling dots."""
        if not self._speaking_animation_running:
            return
        
        if self._tts_speaking:
            try:
                frame = self._speaking_animation_frames[self._speaking_animation_index]
                self.speak_button.configure(text=frame)
            except Exception:
                pass  # Button may have been destroyed
            
            # Cycle through frames
            self._speaking_animation_index = (self._speaking_animation_index + 1) % len(self._speaking_animation_frames)
            
            # Schedule next frame (500ms for smooth animation)
            self._safe_after(500, self._animate_speaking_button)

    def _stop_speaking_animation(self):
        """Stop the speaking animation."""
        self._speaking_animation_running = False

    def _animate_button(self, button, state: str, text: str, color: str, duration: float):
        """
        Animate a button with smooth color and text transitions.
        
        Args:
            button: The CTkButton to animate
            state: Target state ("normal" or "disabled")
            text: Target button text
            color: Target foreground color
            duration: Animation duration in seconds
        """
        # Store original color for hover effect
        button._original_color = color
        
        # Animate color change with pulse effect
        self._animate_button_color(button, color, duration)
        
        # Update text and state
        button.configure(text=text, state=state)

    def _animate_button_color(self, button, target_color: str, duration: float):
        """
        Animate button color transition.
        
        Uses a multi-step color transition for smoother animation.
        """
        # Get current color
        try:
            current_color = button.cget("fg_color")
        except Exception:
            current_color = target_color
        
        # If colors are the same, no animation needed
        if current_color == target_color:
            return
        
        # CustomTkinter doesn't support direct color interpolation,
        # so we use a stepped transition effect
        self._transition_button_color(button, current_color, target_color, 3, duration)

    def _transition_button_color(self, button, from_color: str, to_color: str, steps: int, total_duration: float):
        """
        Transition button color through intermediate steps.
        
        Creates a smoother visual transition by briefly flashing through
        an intermediate state.
        """
        if steps <= 0:
            button.configure(fg_color=to_color)
            return
        
        # For the first step, set to target color immediately with pulse effect
        button.configure(fg_color=to_color)
        
        # Add a subtle scale pulse effect
        self._pulse_button(button, to_color, total_duration)

    def _pulse_button(self, button, target_color: str, duration: float):
        """
        Create a pulse effect for button animation.
        
        This adds visual feedback by briefly expanding the button width
        then returning to normal size.
        """
        try:
            # Add a subtle scale effect by changing size slightly
            # Use the constant to prevent width accumulation on rapid repeated calls
            button.configure(width=BUTTON_WIDTH_DEFAULT + 4)
            
            def reset_size():
                try:
                    button.configure(width=BUTTON_WIDTH_DEFAULT)
                except Exception:
                    pass  # Button may have been destroyed or reconfigured
            
            self._safe_after(int(duration * 300), reset_size)
        except Exception:
            pass  # Button may not support width configuration

    def _set_status(self, message: str, icon: str = "", message_type: str = "info"):
        """Update status message with enhanced formatting and visual indicators."""
        # Format message with timestamp for better logging
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"
        
        # Animate status text change
        self._animate_status_change(f"{icon} {formatted_message}" if icon else formatted_message, message_type)
        
        # Update activity indicator based on message type
        self._animate_activity_indicator(message_type)

    def _animate_status_change(self, new_text: str, message_type: str):
        """Animate the status text change with smooth transitions."""
        current_text = self.status_label.cget("text")
        
        # Only animate if text changed
        if current_text != new_text:
            # Fade out current text
            self._fade_out_status(0.1, lambda: self._fade_in_status(new_text, 0.1))

    def _fade_out_status(self, duration: float, callback):
        """Fade out the current status text (simplified to single-step clear)."""
        # CustomTkinter doesn't support alpha/color interpolation, so just clear and callback
        self.status_label.configure(text="")
        if callback:
            callback()

    def _fade_in_status(self, new_text: str, duration: float):
        """Fade in the new status text."""
        self.status_label.configure(text=new_text)
        # Pulse effect for the new status
        self._pulse_label(self.status_label, duration)

    def _animate_activity_indicator(self, message_type: str):
        """Animate the activity indicator based on message type."""
        # Get target color based on message type
        color_map = {
            "speaking": "#2ecc71",  # Green for active
            "error": "#e74c3c",     # Red for error
            "warning": "#f39c12",   # Orange for warning
            "success": "#27ae60",   # Dark green for success
            "info": "gray60"        # Gray for normal
        }
        
        target_color = color_map.get(message_type, "gray60")
        
        # Animate color change
        self._animate_indicator_color(self.activity_indicator, target_color, 0.2)

    def _animate_indicator_color(self, indicator, target_color: str, duration: float):
        """Animate indicator color transition."""
        indicator.configure(text_color=target_color)
        # Add a subtle pulse effect
        self._pulse_label(indicator, duration)

    def _set_progress(self, message: str, animated: bool = False):
        """
        Update progress indicator with optional animation.
        
        Args:
            message: Progress message to display
            animated: If True, show animated loading indicator
        """
        if animated:
            # Start animated progress
            self._progress_animation_running = True
            self._progress_animation_index = 0
            self._progress_base_message = message
            self._animate_progress()
        else:
            # Stop any running animation
            self._progress_animation_running = False
            self.progress_label.configure(text=message)
        
        if message:
            self.progress_label.pack(side="right", padx=SPACING_SM)
        else:
            self.progress_label.pack_forget()

    def _animate_progress(self):
        """Animate the progress indicator with cycling dots."""
        if not self._progress_animation_running:
            return
        
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        frame = frames[self._progress_animation_index]
        
        try:
            self.progress_label.configure(text=f"{frame} {self._progress_base_message}")
        except Exception:
            pass
        
        self._progress_animation_index = (self._progress_animation_index + 1) % len(frames)
        
        # Schedule next frame (80ms for smooth spinner)
        self._safe_after(80, self._animate_progress)

    def _stop_progress_animation(self):
        """Stop the progress animation."""
        self._progress_animation_running = False
