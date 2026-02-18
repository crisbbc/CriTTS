"""
VRChat OSC Client Module
Handles sending messages to VRChat's chatbox via OSC protocol.
"""

import threading
import logging
from typing import Optional, Callable
from pythonosc import udp_client
from pythonosc.osc_message_builder import OscMessageBuilder


class VRChatOSCClient:
    """
    OSC client for sending messages to VRChat's chatbox.
    
    VRChat listens for OSC messages on port 9000 (default).
    The chatbox endpoint is /chatbox/input.
    """
    
    DEFAULT_VRCHAT_IP = "127.0.0.1"
    DEFAULT_VRCHAT_PORT = 9000
    CHATBOX_ENDPOINT = "/chatbox/input"
    
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
        self._logger = logging.getLogger('vrchat_osc')
        
        # Setup logging
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self._logger.addHandler(handler)
            self._logger.setLevel(logging.INFO)
    
    def connect(self) -> bool:
        """
        Initialize the OSC client connection.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self._client = udp_client.SimpleUDPClient(self.ip, self.port)
            self._connected = True
            self._logger.info(f"OSC client connected to {self.ip}:{self.port}")
            
            if self.status_callback:
                self.status_callback("OSC: Connected", False)
            
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to connect OSC client: {e}")
            self._connected = False
            
            if self.status_callback:
                self.status_callback(f"OSC: Connection failed - {e}", True)
            
            return False
    
    def disconnect(self) -> None:
        """Close the OSC client connection."""
        self._connected = False
        self._client = None
        self._logger.info("OSC client disconnected")
        
        if self.status_callback:
            self.status_callback("OSC: Disconnected", False)
    
    def is_connected(self) -> bool:
        """Check if OSC client is connected."""
        return self._connected and self._client is not None
    
    def send_to_chatbox(
        self,
        message: str,
        play_notification_sound: bool = True,
        show_keyboard: bool = False
    ) -> bool:
        """
        Send a message to VRChat's chatbox.
        
        Args:
            message: The text message to send
            play_notification_sound: Whether to play the notification sound
            show_keyboard: Whether to show the keyboard (typing indicator)
            
        Returns:
            True if message sent successfully, False otherwise
        """
        if not self.is_connected():
            self._logger.warning("Cannot send message: OSC client not connected")
            
            if self.status_callback:
                self.status_callback("OSC: Not connected", True)
            
            return False
        
        try:
            # VRChat expects the message as a string argument
            # The second argument controls notification sound (integer 0 or 1 for compatibility)
            # The third argument controls keyboard visibility (boolean)
            play_sound_int = 1 if play_notification_sound else 0
            self._client.send_message(
                self.CHATBOX_ENDPOINT,
                [message, play_sound_int, show_keyboard]
            )
            
            self._logger.info(f"Sent message to chatbox (notification_sound={play_sound_int}): {message[:50]}...")
            
            if self.status_callback:
                self.status_callback("OSC: Message sent", False)
            
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to send OSC message: {e}")
            
            if self.status_callback:
                self.status_callback(f"OSC: Send failed - {e}", True)
            
            return False
    
    def clear_chatbox(self) -> bool:
        """
        Clear the VRChat chatbox by sending an empty message.
        
        Returns:
            True if cleared successfully, False otherwise
        """
        return self.send_to_chatbox("", play_notification_sound=False, show_keyboard=False)

    def send_typing_indicator(self, is_typing: bool) -> bool:
        """
        Send a typing indicator to VRChat's chatbox.
        
        Args:
            is_typing: Whether to show typing indicator (True to show, False to hide)
            
        Returns:
            True if message sent successfully, False otherwise
        """
        if not self.is_connected():
            self._logger.warning("Cannot send typing indicator: OSC client not connected")
            
            if self.status_callback:
                self.status_callback("OSC: Not connected", True)
            
            return False
        
        try:
            # VRChat expects the typing indicator as a boolean argument to /chatbox/typing
            self._client.send_message("/chatbox/typing", [is_typing])
            
            self._logger.info(f"Sent typing indicator: {is_typing}")
            
            if self.status_callback:
                self.status_callback(f"OSC: Typing indicator {'on' if is_typing else 'off'}", False)
            
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to send typing indicator: {e}")
            
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
            self._client.send_message("/avatar/parameters/Viseme", [viseme_value])
            
            return True
            
        except Exception as e:
            self._logger.debug(f"Failed to send viseme: {e}")
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
            self._client.send_message("/avatar/parameters/Voice", [amplitude])
            
            return True
            
        except Exception as e:
            self._logger.debug(f"Failed to send voice amplitude: {e}")
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
            
            self._client.send_message(parameter_name, [value])
            
            return True
            
        except Exception as e:
            self._logger.debug(f"Failed to send avatar parameter: {e}")
            return False

    def test_connection(self) -> tuple[bool, str]:
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
        
        # Send a test message (invisible - empty string with no sound)
        success = self.send_to_chatbox("", play_notification_sound=False, show_keyboard=False)
        
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
            self._logger.info("Reconnecting with new settings...")
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
