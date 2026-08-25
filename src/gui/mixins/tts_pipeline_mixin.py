"""TTSPipelineMixin - extracted from main_window.py (behavior unchanged)."""
from typing import Any
import asyncio
import os
import threading
import time


class TTSPipelineMixin:
    """Mixin methods; expects MainWindow attributes on self."""

    # Attributes/methods provided by MainWindow (mixin contract).
    _abbreviation_cache: Any
    _abbreviation_cache_max_size: Any
    _amplitude_analyzer: Any
    _chatbox: Any
    _get_amplitude_forwarder: Any
    _safe_after: Any
    _send_chatbox_message: Any
    _set_status: Any
    _show_error: Any
    _speaking_lock: Any
    _stop_typing_animation: Any
    _text_preprocessor: Any
    _update_ui_speaking: Any
    _viseme_mapper: Any
    audio_router: Any
    osc_client: Any
    settings: Any
    text_input: Any
    tts_engine: Any


    def _on_speak(self):
        """Handle speak button click."""
        # Stop typing animation when speaking (skip clear to avoid rate limit)
        if self._chatbox.is_typing_active:
            self._stop_typing_animation(send_clear=False)
        
        with self._speaking_lock:
            if self._speaking:
                return
            self._speaking = True
        
        speak_mode = self.settings.get("speak_mode", "current_line")
        if speak_mode == "current_line":
            cursor_index = self.text_input.index("insert")
            line_num = cursor_index.split(".")[0]
            text = self.text_input.get(f"{line_num}.0", f"{line_num}.end").strip()
        else:
            text = self.text_input.get("1.0", "end-1c").strip()
        if not text:
            with self._speaking_lock:
                self._speaking = False
            self._update_ui_speaking(False)
            self._show_error("Current line is empty. Please type some text.")
            return
        
        # Get abbreviations from settings and expand text (with LRU cache)
        abbreviations = self.settings.get("abbreviations", {})
        if abbreviations:
            # Use a stable, content-based cache key instead of id()
            cache_key = (text, tuple(sorted(abbreviations.items())))
            if cache_key in self._abbreviation_cache:
                # Cache hit: move to end (most recently used) for LRU
                processed_text = self._abbreviation_cache.pop(cache_key)
                self._abbreviation_cache[cache_key] = processed_text
            else:
                # Cache miss: evict oldest (first) item if at capacity
                while len(self._abbreviation_cache) >= self._abbreviation_cache_max_size:
                    self._abbreviation_cache.popitem(last=False)
                processed_text = self._text_preprocessor.expand_abbreviations(text, abbreviations)
                self._abbreviation_cache[cache_key] = processed_text
        else:
            processed_text = text
        
        # Send to VRChat chatbox if OSC is enabled and send_on_speak is True
        if self.osc_client and self.settings.get("vrchat_osc_send_on_speak", False):
            try:
                # Wait for VRChat's rate limit cooldown before sending the message
                # This ensures the message is sent after the typing animation text
                # VRChat enforces ~1.5 seconds between chatbox messages
                elapsed = time.time() - self.osc_client._last_chatbox_send_time
                wait_time = max(0, 1.5 - elapsed)
                send_args = (
                    processed_text,
                    self.settings.get("vrchat_osc_play_sound", True),
                    False
                )
                if wait_time > 0:
                    self._safe_after(int(wait_time * 1000), lambda args=send_args: self._send_chatbox_message(*args))
                else:
                    self._send_chatbox_message(*send_args)
            except Exception:
                self._set_status("Failed to send to VRChat chatbox", "⚠️")
        
        # Join previous worker briefly so rapid double-click cannot leak
        # an asyncio loop. The _speaking guard above usually prevents this,
        # but _on_stop clears _speaking before the old thread exits.
        _prev = getattr(self, "_worker_thread", None)
        if _prev is not None and _prev.is_alive():
            try:
                _prev.join(timeout=0.2)
            except Exception:
                import logging as _logging
                _logging.getLogger(__name__).debug("Previous worker join failed", exc_info=True)

        # Start a fresh speak generation with its own stop event.  A previous
        # worker still winding down keeps its own (already-set) event, so it
        # cannot observe this speak's cleared stop signal or clobber the new
        # worker's state when it finally exits.
        self._speak_generation += 1
        generation = self._speak_generation
        stop_event = threading.Event()
        self._stop_event = stop_event

        self._update_ui_speaking(True)
        self._set_status("Generating speech...", "⏳", "speaking")

        # Run TTS in background thread to avoid blocking UI
        self._worker_thread = threading.Thread(
            target=self._speak_async,
            args=(processed_text, stop_event, generation),
            daemon=True,
        )
        self._worker_thread.start()

    def _speak_async(self, text: str, stop_event: threading.Event, generation: int):
        """Run TTS generation and playback in async context."""
        loop = None
        try:
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Get settings
            voice = self.settings.get("voice", "en-US-AriaNeural")
            rate = self.settings.get("rate", 0)
            volume = self.settings.get("volume", 100)
            pitch = self.settings.get("pitch", 0)
            device_idx = self.settings.get("device_index")

            # Linux: configure PulseAudio/PipeWire sink auto-routing.
            # PortAudio on most Linux systems only ships the ALSA backend,
            # so PULSE_SINK has no effect.  AudioRouter._route_to_linux_sink()
            # polls for the just-opened stream and moves it with pactl.
            if self.audio_router.is_linux:
                linux_sink = self.settings.get("linux_sink_name", "")
                self.audio_router.set_linux_sink_name(linux_sink)

            enable_normalization = self.settings.get("enable_normalization", True)
            normalization_type = self.settings.get("normalization_type", "Peak")
            processing_profile = self.settings.get("processing_profile", "balanced")
            enable_streaming = self.settings.get("enable_streaming_playback", False)
            soundboard_enabled = self.settings.get("soundboard_enabled", True)
            soundboard_slots = self.settings.get("soundboard_slots", {})
            if not isinstance(soundboard_slots, dict):
                soundboard_slots = {}

            # Check if stop was requested before generation
            if stop_event.is_set():
                return

            # When soundboard is disabled, keep text untouched so tokens are spoken normally.
            if soundboard_enabled:
                segments = self._text_preprocessor.split_soundboard_segments(text)
            else:
                segments = [{"type": "text", "content": text}]

            has_sound_tokens = any(segment.get("type") == "sound" for segment in segments)

            # Check if streaming is enabled (only for plain text playback).
            if enable_streaming and not has_sound_tokens and len(segments) == 1 and segments[0].get("type") == "text":
                # Use streaming playback for lower latency
                success = loop.run_until_complete(
                    self._speak_streaming_async(text, voice, rate, volume, pitch, device_idx, processing_profile, stop_event, enable_normalization, normalization_type)
                )
            else:
                success = True

                for segment in segments:
                    if stop_event.is_set():
                        return

                    segment_type = segment.get("type")

                    if segment_type == "text":
                        segment_text = segment.get("content", "")
                        if not segment_text.strip():
                            continue

                        self._safe_after(0, lambda: self._set_status("Generating speech...", "🔊", "speaking"))

                        audio_data, error = loop.run_until_complete(
                            self.tts_engine.generate_speech(segment_text, voice, rate, volume, pitch, stop_event)
                        )

                        if stop_event.is_set():
                            return

                        if error:
                            self._safe_after(0, lambda e=error: self._show_error(f"TTS Error: {e}"))
                            return

                        if not audio_data:
                            continue

                        self._safe_after(0, lambda: self._set_status("Playing audio...", "▶️", "speaking"))
                        success = loop.run_until_complete(
                            self._play_audio_segment(
                                audio_data,
                                segment_text,
                                rate,
                                device_idx,
                                enable_normalization,
                                normalization_type,
                                processing_profile,
                                enable_viseme=True,
                            )
                        )

                        if stop_event.is_set():
                            return

                        if not success:
                            self._safe_after(0, lambda: self._show_error("Failed to play audio to device."))
                            return

                    elif segment_type == "sound":
                        slot = str(segment.get("slot", ""))
                        slot_path = soundboard_slots.get(slot, "")

                        if slot_path is None:
                            slot_path = ""
                        if not isinstance(slot_path, str):
                            slot_path = str(slot_path)

                        slot_path = slot_path.strip()

                        if not slot_path:
                            self._safe_after(
                                0,
                                lambda s=slot: self._set_status(
                                    f"Soundboard slot [{s}] is empty. Skipping.",
                                    "⚠️",
                                    "warning"
                                )
                            )
                            continue

                        if not os.path.isfile(slot_path):
                            self._safe_after(
                                0,
                                lambda s=slot, p=slot_path: self._set_status(
                                    f"Soundboard slot [{s}] file not found: {p}",
                                    "⚠️",
                                    "warning"
                                )
                            )
                            continue

                        try:
                            with open(slot_path, "rb") as f:
                                slot_audio_data = f.read()
                        except Exception as file_error:
                            self._safe_after(
                                0,
                                lambda s=slot, e=str(file_error): self._set_status(
                                    f"Failed loading soundboard slot [{s}]: {e}",
                                    "⚠️",
                                    "warning"
                                )
                            )
                            continue

                        if not slot_audio_data:
                            self._safe_after(
                                0,
                                lambda s=slot: self._set_status(
                                    f"Soundboard slot [{s}] file is empty. Skipping.",
                                    "⚠️",
                                    "warning"
                                )
                            )
                            continue

                        self._safe_after(
                            0,
                            lambda s=slot: self._set_status(
                                f"Playing sound slot [{s}]...",
                                "🎵",
                                "speaking"
                            )
                        )
                        success = loop.run_until_complete(
                            self._play_audio_segment(
                                slot_audio_data,
                                f"[{slot}]",
                                rate,
                                device_idx,
                                enable_normalization,
                                normalization_type,
                                processing_profile,
                                enable_viseme=False,
                            )
                        )

                        if stop_event.is_set():
                            return

                        if not success:
                            self._safe_after(
                                0,
                                lambda s=slot: self._set_status(
                                    f"Failed to play soundboard slot [{s}].",
                                    "⚠️",
                                    "warning"
                                )
                            )
                            continue

            # Do not show Finished or success UI when user stopped or playback was interrupted
            if stop_event.is_set():
                return
            if not success:
                self._safe_after(0, lambda: self._show_error("Failed to play audio to device."))
                return
            self._safe_after(0, lambda: self._set_status("Finished", "✅"))
            
        except Exception as error:
            self._safe_after(0, lambda error_str=str(error): self._show_error(f"Error: {error_str}"))
        finally:
            if loop:
                loop.close()
            # Only the current generation may reset shared speak state.  A late
            # worker finishing after a newer speak started must leave the newer
            # worker's state untouched.
            with self._speaking_lock:
                if generation == self._speak_generation:
                    self._speaking = False
                    self._worker_thread = None
            if generation == self._speak_generation:
                self._safe_after(0, lambda: self._update_ui_speaking(False))

    async def _play_audio_segment(
        self,
        audio_data: bytes,
        segment_text: str,
        speech_rate: int,
        device_idx,
        enable_normalization: bool,
        normalization_type: str,
        processing_profile: str,
        enable_viseme: bool,
    ) -> bool:
        """Play a single prepared audio segment using existing routing settings."""
        voice_amplitude_enabled = self.settings.get("vrchat_voice_amplitude_enabled", False)
        enable_clarity_eq = self.settings.get("enable_clarity_eq", True)
        try:
            prepared_audio = await self.audio_router.prepare_audio_for_playback(
                audio_data,
                enable_normalization=enable_normalization,
                normalization_type=normalization_type,
                processing_profile=processing_profile,
                enable_clarity_eq=enable_clarity_eq,
            )
        except RuntimeError:
            return False

        if enable_viseme and self._viseme_mapper is not None and self.osc_client is not None:
            amplitude_callback = None
            if voice_amplitude_enabled and self._amplitude_analyzer is not None:
                amplitude_callback = self._amplitude_analyzer.get_amplitude

            self._viseme_mapper.start_viseme_animation(
                segment_text,
                self.osc_client.send_viseme,
                duration=prepared_audio.duration_seconds,
                speech_rate=speech_rate,
                amplitude_callback=amplitude_callback,
            )

        if voice_amplitude_enabled and self._amplitude_analyzer is not None and self.osc_client is not None:
            forwarder = self._get_amplitude_forwarder()

            def amplitude_callback_with_osc(amplitude: float):
                """Update the analyzer and hand amplitude to the OSC forwarder."""
                self._amplitude_analyzer.update_amplitude(amplitude)
                forwarder.update(amplitude)

            return await self.audio_router.play_audio_with_amplitude(
                audio_data,
                48000,
                device_idx,
                enable_normalization,
                normalization_type,
                amplitude_callback=amplitude_callback_with_osc,
                processing_profile=processing_profile,
                enable_clarity_eq=enable_clarity_eq,
                prepared_audio=prepared_audio,
            )

        return await self.audio_router.play_audio_to_device(
            audio_data,
            48000,
            device_idx,
            enable_normalization,
            normalization_type,
            processing_profile,
            enable_clarity_eq=enable_clarity_eq,
            prepared_audio=prepared_audio,
        )

    async def _speak_streaming_async(self, text: str, voice: str, rate: int, volume: int, pitch: int, device_idx, processing_profile: str, stop_event: threading.Event, enable_normalization: bool = True, normalization_type: str = "Peak") -> bool:
        """
        Stream TTS generation and playback for lower latency.
        
        This method starts playing audio as soon as the first chunks arrive,
        rather than waiting for the entire audio to be generated.
        
        Args:
            text: Text to speak
            voice: Voice identifier
            rate: Speech rate
            volume: Volume level
            pitch: Pitch adjustment
            device_idx: Output device index
            processing_profile: Processing profile name
            enable_normalization: Whether to apply normalization
            normalization_type: Type of normalization ("Peak", "RMS", "LUFS", or "None")
        """
        try:
            # Update status
            self._safe_after(0, lambda: self._set_status("Streaming speech...", "🔊"))
            
            # Check if voice amplitude feature is enabled for VRChat
            voice_amplitude_enabled = self.settings.get("vrchat_voice_amplitude_enabled", False)
            enable_clarity_eq = self.settings.get("enable_clarity_eq", True)
            
            # Start viseme animation if enabled (use estimated duration for streaming)
            if self._viseme_mapper is not None and self.osc_client is not None:
                # Estimate duration based on text length and speech rate
                # Average speaking rate is ~150 words per minute, ~5 chars per word
                estimated_duration = len(text) / 5 / 150 * 60  # seconds
                # Adjust for speech rate
                if rate != 0:
                    estimated_duration *= (100 - rate) / 100
                
                # Get amplitude callback if enabled
                amplitude_callback = None
                if voice_amplitude_enabled and self._amplitude_analyzer is not None:
                    amplitude_callback = self._amplitude_analyzer.get_amplitude
                
                self._viseme_mapper.start_viseme_animation(
                    text, 
                    self.osc_client.send_viseme, 
                    duration=estimated_duration,
                    speech_rate=rate,
                    amplitude_callback=amplitude_callback
                )
            
            # Create the audio chunk generator
            audio_generator = self.tts_engine.stream_speech(
                text, voice, rate, volume, pitch, stop_event
            )
            
            # Create amplitude callback for streaming playback if VRChat voice amplitude is enabled
            streaming_amplitude_callback = None
            if voice_amplitude_enabled and self._amplitude_analyzer is not None and self.osc_client is not None:
                forwarder = self._get_amplitude_forwarder()

                def streaming_amplitude_callback_with_osc(amplitude: float):
                    """Update the analyzer and hand amplitude to the OSC forwarder."""
                    self._amplitude_analyzer.update_amplitude(amplitude)
                    forwarder.update(amplitude)
                streaming_amplitude_callback = streaming_amplitude_callback_with_osc
            
            # Play streaming audio
            success = await self.audio_router.play_audio_streaming(
                audio_generator,
                48000,
                device_idx,
                processing_profile,
                stop_event,
                enable_normalization,
                normalization_type,
                amplitude_callback=streaming_amplitude_callback,
                enable_clarity_eq=enable_clarity_eq,
            )
            
            return success
            
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Streaming playback error: {e}")
            return False

    def _on_stop(self):
        """Handle stop button click."""
        # Stop typing animation when aborting (clear chatbox since no message will replace it)
        if self._chatbox.is_typing_active:
            self._stop_typing_animation(send_clear=True)
        
        # Set stop event to signal background thread to stop
        self._stop_event.set()
        self.audio_router.stop_playback()
        if self._viseme_mapper is not None:
            self._viseme_mapper.stop_viseme_animation()
        with self._speaking_lock:
            self._speaking = False
        self._update_ui_speaking(False)
        self._set_status("Stopped", "⏹")
