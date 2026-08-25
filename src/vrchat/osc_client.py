"""
VRChat OSC Client Module
Handles sending messages to VRChat's chatbox via OSC protocol.
"""

import logging
import time
from typing import Optional, Callable, Tuple
from pythonosc import udp_client

logger = logging.getLogger(__name__)


class VRChatOSCClient:
    """
    OSC client for sending messages to VRChat's chatbox.
    
    VRChat listens for OSC messages on port 9000 (default).
    The chatbox endpoint is /chatbox/input.
    """
    
    DEFAULT_VRCHAT_IP = "127.0.0.1"
    DEFAULT_VRCHAT_PORT = 9000
    CHATBOX_ENDPOINT = "/chatbox/input"
    CHATBOX_MIN_INTERVAL = 1.5  # Minimum seconds between chatbox messages (VRChat rate limit)
    CHATBOX_MAX_LENGTH = 144  # VRChat's maximum chatbox message length
    
    def __init__(
        self,
        ip: str = DEFAULT_VRCHAT_IP,
        port: int = DEFAULT_VRCHAT_PORT,
        status_callback: Optional[Callable[[str, bool], None]] = None
    ):
        """
        Initialize the VRChat OSC client.
        
        Args:
            ip: IP address of VRChat (default: localhost)
            port: OSC port VRChat listens on (default: 9000)
            status_callback: Function to call with (status_message, is_error) updates
        """
        self.ip = ip
        self.port = port
        self.status_callback = status_callback
        
        self._client: Optional[udp_client.SimpleUDPClient] = None
        self._connected = False
        self._last_chatbox_send_time: float = 0.0
    
    def connect(self) -> bool:
        """
        Initialize the OSC client connection.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self._client = udp_client.SimpleUDPClient(self.ip, self.port)
            self._connected = True
            logger.info("OSC client connected to %s:%d", self.ip, self.port)
            
            if self.status_callback:
                self.status_callback("OSC: Connected", False)
            
            return True
            
        except Exception as e:
            logger.error("Failed to connect OSC client: %s", e)
            self._connected = False
            
            if self.status_callback:
                self.status_callback(f"OSC: Connection failed - {e}", True)
            
            return False
    
    def disconnect(self) -> None:
        """Close the OSC client connection."""
        self._connected = False
        self._client = None
        logger.info("OSC client disconnected")
        
        if self.status_callback:
            self.status_callback("OSC: Disconnected", False)
    
    def is_connected(self) -> bool:
        """Check if OSC client is connected."""
        return self._connected and self._client is not None
    
    def send_to_chatbox(
        self,
        message: str,
        play_notification_sound: bool = True,
        show_keyboard: bool = False,
        bypass_rate_limit: bool = False
    ) -> bool:
        """
        Send a message to VRChat's chatbox.
        
        Args:
            message: The text message to send
            play_notification_sound: Whether to play the notification sound
            show_keyboard: Whether to show the keyboard (typing indicator)
            bypass_rate_limit: If True, skip VRChat's ~1.5s rate limit check.
                              Use for actual messages that should override typing animation.
                              Leave False for typing animation frames to respect rate limits.
            
        Returns:
            True if message sent successfully, False if rate-limited or not connected.
            Note: Returns False for rate-limit skips, which is expected behavior for
            typing animation - the caller should continue the animation loop.
        """
        if not self.is_connected():
            logger.warning("Cannot send message: OSC client not connected")
            
            if self.status_callback:
                self.status_callback("OSC: Not connected", True)
            
            return False
        
        # Rate limit guard - VRChat enforces ~1.5s between chatbox messages
        # Messages with bypass_rate_limit=True skip this check (e.g., actual messages
        # that should immediately replace typing animation text)
        if not bypass_rate_limit:
            elapsed = time.time() - self._last_chatbox_send_time
            if elapsed < self.CHATBOX_MIN_INTERVAL:
                logger.debug("Chatbox rate limit: skipping send (%.2fs remaining)", self.CHATBOX_MIN_INTERVAL - elapsed)
                return False
        
        try:
            # Truncate message to VRChat's maximum length to prevent silent drops
            if len(message) > self.CHATBOX_MAX_LENGTH:
                message = message[:self.CHATBOX_MAX_LENGTH]
                logger.debug("Truncated message to %d characters", self.CHATBOX_MAX_LENGTH)
            
            # VRChat expects the message as a string argument
            # The second argument controls notification sound (integer 0 or 1 for compatibility)
            # The third argument controls keyboard visibility (boolean)
            play_sound_int = 1 if play_notification_sound else 0
            client = self._client
            if client is None:
                return False
            client.send_message(
                self.CHATBOX_ENDPOINT,
                [message, play_sound_int, show_keyboard]
            )
            
            # Update last send time after successful send
            self._last_chatbox_send_time = time.time()
            
            # Only append "..." if message was truncated
            display_msg = message[:50] + "..." if len(message) > 50 else message
            logger.info("Sent message to chatbox (notification_sound=%d): %s", play_sound_int, display_msg)
            
            if self.status_callback:
                self.status_callback("OSC: Message sent", False)
            
            return True
            
        except Exception as e:
            logger.error("Failed to send OSC message: %s", e)
            
            if self.status_callback:
                self.status_callback(f"OSC: Send failed - {e}", True)
            
            return False
    
    def clear_chatbox(self) -> bool:
        """
        Clear the VRChat chatbox by sending an empty message.
        
        Uses bypass_rate_limit=True to bypass rate limiting, ensuring the clear
        operation always succeeds even if called shortly after another message.
        
        Returns:
            True if cleared successfully, False otherwise
        """
        return self.send_to_chatbox("", play_notification_sound=False, show_keyboard=False, bypass_rate_limit=True)

    def send_typing_indicator(self, is_typing: bool) -> bool:
        """
        Send a typing indicator to VRChat's chatbox.
        
        Args:
            is_typing: Whether to show typing indicator (True to show, False to hide)
            
        Returns:
            True if message sent successfully, False otherwise
        """
        if not self.is_connected():
            logger.warning("Cannot send typing indicator: OSC client not connected")
            
            if self.status_callback:
                self.status_callback("OSC: Not connected", True)
            
            return False
        
        try:
            # VRChat expects the typing indicator as a boolean argument to /chatbox/typing
            client = self._client
            if client is None:
                return False
            client.send_message("/chatbox/typing", [is_typing])
            
            logger.info("Sent typing indicator: %s", is_typing)
            
            if self.status_callback:
                self.status_callback(f"OSC: Typing indicator {'on' if is_typing else 'off'}", False)
            
            return True
            
        except Exception as e:
            logger.error("Failed to send typing indicator: %s", e)
            
            if self.status_callback:
                self.status_callback(f"OSC: Typing indicator failed - {e}", True)
            
            return False
    
    def send_viseme(self, viseme_value: int) -> bool:
        """
        Send a viseme value to VRChat for lip-sync animation.
        
        Args:
            viseme_value: Viseme index (0-14)
                0 = silence, 1 = pp, 2 = ff, 3 = th, 4 = dd,
                5 = kk, 6 = ch, 7 = ss, 8 = nn, 9 = rr,
                10 = aa, 11 = e, 12 = i, 13 = o, 14 = u
            
        Returns:
            True if message sent successfully, False otherwise
        """
        if not self.is_connected():
            return False
        
        try:
            # Clamp viseme value to valid range
            viseme_value = max(0, min(14, int(viseme_value)))
            
            # Send to VRChat's viseme parameter
            client = self._client
            if client is None:
                return False
            client.send_message("/avatar/parameters/Viseme", [viseme_value])
            
            return True
            
        except Exception as e:
            logger.debug("Failed to send viseme: %s", e)
            return False
    
    def send_voice_amplitude(self, amplitude: float) -> bool:
        """
        Send voice amplitude to VRChat for mouth movement.
        
        Args:
            amplitude: Amplitude value (0.0 to 1.0)
            
        Returns:
            True if message sent successfully, False otherwise
        """
        if not self.is_connected():
            return False
        
        try:
            # Clamp amplitude to valid range
            amplitude = max(0.0, min(1.0, float(amplitude)))
            
            # Send to VRChat's Voice parameter
            client = self._client
            if client is None:
                return False
            client.send_message("/avatar/parameters/Voice", [amplitude])
            
            return True
            
        except Exception as e:
            logger.debug("Failed to send voice amplitude: %s", e)
            return False
    
    def send_avatar_parameter(self, parameter_name: str, value) -> bool:
        """
        Send a value to any avatar parameter.
        
        Args:
            parameter_name: Name of the avatar parameter
            value: Value to send (int, float, or bool)
            
        Returns:
            True if message sent successfully, False otherwise
        """
        if not self.is_connected():
            return False
        
        try:
            # Ensure parameter name has correct prefix
            if not parameter_name.startswith("/avatar/parameters/"):
                parameter_name = f"/avatar/parameters/{parameter_name}"
            
            client = self._client
            if client is None:
                return False
            client.send_message(parameter_name, [value])
            
            return True
            
        except Exception as e:
            logger.debug("Failed to send avatar parameter: %s", e)
            return False

    def test_connection(self) -> Tuple[bool, str]:
        """
        Test the OSC configuration. UDP is connectionless so we cannot definitively
        verify that VRChat is running or receiving; we only verify that the client
        can be created and a message can be sent.
        
        Returns:
            Tuple of (success, message)
        """
        if not self.is_connected():
            if not self.connect():
                return False, "Failed to create OSC client. Check IP and port (e.g. 127.0.0.1:9000)."
        
        # Use typing indicator as a no-op probe instead of clearing the chatbox
        # This avoids the visible side effect of clearing the chatbox during settings tests
        success = self.send_typing_indicator(False)
        
        if success:
            return True, "OSC configured correctly. Messages will be sent to VRChat if it's running with OSC enabled."
        else:
            return False, "OSC test failed. Ensure VRChat is running and OSC is enabled in VRChat settings. UDP is connectionless so this test cannot guarantee VRChat is receiving."
    
    def update_settings(
        self,
        ip: Optional[str] = None,
        port: Optional[int] = None
    ) -> None:
        """
        Update OSC client settings.
        
        Args:
            ip: New IP address
            port: New port number
        """
        reconnect_needed = False
        
        if ip is not None and ip != self.ip:
            self.ip = ip
            reconnect_needed = True
        
        if port is not None and port != self.port:
            self.port = port
            reconnect_needed = True
        
        if reconnect_needed and self.is_connected():
            logger.info("Reconnecting with new settings...")
            self.disconnect()
            self.connect()
    
    def get_status(self) -> dict:
        """
        Get current OSC client status.
        
        Returns:
            Dictionary with status information
        """
        return {
            'connected': self.is_connected(),
            'ip': self.ip,
            'port': self.port,
            'endpoint': self.CHATBOX_ENDPOINT
        }
