"""VRChat chatbox controller.

Extracted from ``MainWindow`` so the OSC chatbox concerns — message sends
with cooldown tracking, the typing-indicator animation state machine, and the
amplitude forwarder thread — live in one focused class.  ``MainWindow`` keeps
thin delegating wrappers with the original method names, so existing callers
and tests keep working unchanged.
"""
import logging
import queue
import threading
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


class OscAmplitudeForwarder:
    """Forward VRChat voice amplitude on a dedicated thread.

    The amplitude callback fires on PortAudio's realtime audio thread, where a
    blocking UDP send can underrun audio.  This class hands the value to a
    daemon thread that coalesces to the newest sample and performs the OSC send
    off the audio thread.
    """

    def __init__(self, send_callback: Callable[[float], None]):
        self._send_callback = send_callback
        self._queue: "queue.Queue" = queue.Queue(maxsize=1)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="osc-amplitude-forwarder", daemon=True
        )
        self._thread.start()

    def update(self, amplitude: float) -> None:
        """Publish a new amplitude value, keeping only the latest."""
        try:
            self._queue.put_nowait(amplitude)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(amplitude)
            except queue.Full:
                pass

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                amplitude = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self._send_callback(amplitude)
            except Exception:
                logger.debug("OSC amplitude send failed", exc_info=True)

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread.is_alive():
            thread.join(timeout=1.0)


class ChatboxController:
    """Owns VRChat chatbox sends and the typing-indicator state machine.

    The OSC client itself stays owned by ``MainWindow`` (tests and settings
    tabs assign it directly); this controller reaches it through *get_client*
    so it always sees the current instance.
    """

    def __init__(
        self,
        get_client: Callable[[], Any],
        settings: Any,
        status_cb: Callable[[str, str], None],
        schedule_cb: Callable[[int, Callable[[], None]], Any],
        cancel_cb: Callable[[Any], None],
    ):
        """Wire the controller to its host window.

        Args:
            get_client: Returns the active :class:`VRChatOSCClient` (may be
                None when OSC is disabled; typed Any so attribute access on
                the client resolves).
            settings: Settings provider with ``get(key, default)``.
            status_cb: ``(message, emoji)`` status-bar callback (Tk thread).
            schedule_cb: Tk-after-style scheduler ``(delay_ms, fn) -> timer_id``.
            cancel_cb: Cancels a previously scheduled timer id.
        """
        self._get_client = get_client
        self._settings = settings
        self._status_cb = status_cb
        self._schedule_cb = schedule_cb
        self._cancel_cb = cancel_cb

        # Typing animation state
        self.typing_animation_timer = None
        self.typing_debounce_timer = None
        self.typing_animation_state = 0
        self.is_typing_active = False
        self.last_typing_time = 0.0
        # Track when last message was sent for cooldown
        self.last_message_sent_time = 0.0

    @property
    def _client(self):
        return self._get_client()

    def _osc_enabled(self) -> bool:
        return self._client is not None and self._settings.get(
            "vrchat_osc_enabled", False
        )

    # ------------------------------------------------------------------
    # Chatbox sends
    # ------------------------------------------------------------------

    def send_message(
        self, text: str, play_notification_sound: bool, show_keyboard: bool
    ) -> bool:
        """Send a message to the VRChat chatbox and track cooldown timing.

        Returns True on success (or when no client is connected), False when
        the send raised — the host surfaces the failure in its status bar.
        """
        client = self._client
        if not client:
            return True

        try:
            client.send_to_chatbox(
                text,
                play_notification_sound=play_notification_sound,
                show_keyboard=show_keyboard,
            )
            self.last_message_sent_time = time.time()
            return True
        except Exception:
            logger.debug("Chatbox send failed", exc_info=True)
            return False

    # ------------------------------------------------------------------
    # Typing indicator state machine
    # ------------------------------------------------------------------

    def handle_typing(self, speaking: bool) -> None:
        """Handle typing animation for the VRChat OSC chatbox."""
        # Guard: Don't restart typing animation while speaking
        # This prevents KeyRelease events (like Enter key release) from restarting
        # the animation that was just stopped by _on_speak()
        if speaking:
            return

        # Check if OSC is enabled and connected
        if not self._osc_enabled():
            return

        # Check if typing animation is enabled
        if not self._settings.get("vrchat_osc_typing_animation", False):
            return

        # Check if we're in the cooldown period after a message was sent
        # This gives others time to read the message before typing animation starts
        cooldown_seconds = self._settings.get("vrchat_osc_message_cooldown", 3.0)
        time_since_message = time.time() - self.last_message_sent_time
        if time_since_message < cooldown_seconds:
            return

        # Update last typing time
        self.last_typing_time = time.time()

        # If not already typing, start typing animation
        if not self.is_typing_active:
            self.is_typing_active = True
            # Send typing indicator ON
            self._client.send_typing_indicator(True)
            # Start animation timer
            self.animate_typing()

        # Reset debounce timer
        if self.typing_debounce_timer:
            self._cancel_cb(self.typing_debounce_timer)

        # Set new debounce timer to stop typing after timeout
        timeout_seconds = self._settings.get("vrchat_osc_typing_timeout", 2.0)
        self.typing_debounce_timer = self._schedule_cb(
            round(timeout_seconds * 1000), self.stop_typing
        )

    def animate_typing(self) -> None:
        """Animate the typing indicator with dots."""
        if not self.is_typing_active:
            return

        # Cycle through animation states: "Typing.", "Typing..", "Typing..."
        animation_texts = ["Typing.", "Typing..", "Typing..."]
        current_text = animation_texts[self.typing_animation_state]

        # Send current animation text to chatbox (only if OSC is enabled)
        if self._osc_enabled():
            self._client.send_to_chatbox(
                current_text,
                play_notification_sound=False,
                show_keyboard=True,
            )

        # Increment animation state
        self.typing_animation_state = (self.typing_animation_state + 1) % 3

        # Schedule next animation frame (1500ms interval to match VRChat rate limit)
        self.typing_animation_timer = self._schedule_cb(1500, self.animate_typing)

    def stop_typing(self, send_clear: bool = True) -> None:
        """Stop the typing animation.

        Args:
            send_clear: If True, clear the chatbox after stopping. Set to False
                       when the actual message will replace the typing text,
                       avoiding VRChat's rate limit on chatbox messages.
        """
        # Cancel animation timer
        if self.typing_animation_timer:
            self._cancel_cb(self.typing_animation_timer)
            self.typing_animation_timer = None

        # Cancel debounce timer
        if self.typing_debounce_timer:
            self._cancel_cb(self.typing_debounce_timer)
            self.typing_debounce_timer = None

        # Send typing indicator OFF (only if OSC is enabled)
        if self._osc_enabled():
            self._client.send_typing_indicator(False)

        # Clear chatbox (only if OSC is enabled and send_clear is True)
        # Skip clearing when the actual message will replace the typing text,
        # to avoid consuming VRChat's rate limit slot
        if send_clear and self._osc_enabled():
            self._client.clear_chatbox()

        # Reset state
        self.is_typing_active = False
        self.typing_animation_state = 0
