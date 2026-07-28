"""
CriTTS Recoded - Main Application Entry Point

A modern Text-to-Speech application with GUI, using edge_tts for free TTS
and sounddevice for audio routing to virtual devices like VB-Cable.
"""
import customtkinter as ctk
import sys
import os
import signal
import atexit
import logging
import webbrowser

# Configure logging early before any module imports
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Add src to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import SettingsManager
from src.tts import TTSEngine
from src.audio import AudioRouter
from src.stt import STTEngine
from src.gui import MainWindow, SettingsWindow
from src.gui.theme_constants import (
    WINDOW_MAIN_WIDTH, WINDOW_MAIN_HEIGHT,
    WINDOW_MAIN_MIN_WIDTH, WINDOW_MAIN_MIN_HEIGHT
)


class CriTTSApp(ctk.CTk):
    """Main application class for CriTTS Recoded."""
    
    def _build_passthrough_params(self) -> tuple:
        """
        Build passthrough parameters from settings.
        
        Returns:
            Tuple of (input_device_index, output_device_index, volume)
        """
        input_device_index = self.settings_manager.get("mic_passthrough_device_index")
        # Use dedicated passthrough output device if set, otherwise fall back to main TTS device
        output_device_index = self.settings_manager.get("mic_passthrough_output_device_index")
        if output_device_index is None:
            output_device_index = self.settings_manager.get("device_index")
        volume_percent = self.settings_manager.get("mic_passthrough_volume", 100)
        # Clamp to 0-200 and convert from percent to multiplier
        volume_percent = max(0, min(200, volume_percent))
        volume = volume_percent / 100.0
        return input_device_index, output_device_index, volume
    
    def _center_dialog(self, dialog, width: int, height: int):
        """
        Center a dialog on screen.
        
        Args:
            dialog: The dialog window to center
            width: Dialog width in pixels
            height: Dialog height in pixels
        """
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (dialog.winfo_screenheight() // 2) - (height // 2)
        dialog.geometry(f"+{x}+{y}")
    
    def __init__(self):
        """Initialize the application."""
        super().__init__()
        
        # Track cleanup state to prevent double execution
        self._cleaned_up = False
        
        # Initialize components
        self._init_components()
        
        # Setup window
        self._setup_window()
        
        # Create main window
        self._create_main_window()
        
        # Setup graceful shutdown
        self._setup_shutdown()
    
    def _init_components(self):
        """Initialize application components."""
        # Settings manager
        self.settings_manager = SettingsManager()
        
        # TTS engine - inject settings manager to avoid re-instantiation
        self.tts_engine = TTSEngine(settings_manager=self.settings_manager)
        
        # Audio router
        self.audio_router = AudioRouter()
        
        # STT engine - for voice input (on_auto_stop will be set after main_window is created)
        self.stt_engine = STTEngine(settings_manager=self.settings_manager)
        
        # Settings window reference
        self.settings_window = None
    
    def _setup_window(self):
        """Configure the main application window."""
        # Set appearance mode from settings
        appearance_mode = self.settings_manager.get("appearance_mode", "Dark")
        ctk.set_appearance_mode(appearance_mode)
        ctk.set_default_color_theme("dark-blue")
        
        # Window configuration with theme constants
        self.title("CriTTS Recoded")
        self.geometry(f"{WINDOW_MAIN_WIDTH}x{WINDOW_MAIN_HEIGHT}")
        self.minsize(WINDOW_MAIN_MIN_WIDTH, WINDOW_MAIN_MIN_HEIGHT)
        
        # Set icon if available
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "image.ico")
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass
    
    def _create_main_window(self):
        """Create the main application window."""
        self.main_window = MainWindow(
            root=self,
            settings_manager=self.settings_manager,
            tts_engine=self.tts_engine,
            audio_router=self.audio_router,
            on_open_settings=self._open_settings,
            icon_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "image.ico"),
            stt_engine=self.stt_engine
        )
        
        # Wire STT auto-stop callback to main_window's handler
        self.stt_engine._on_auto_stop = self.main_window.on_stt_auto_stop
        
        # Schedule virtual-audio-device check after window is rendered
        self.after(500, self._check_vbcable)
        
        # Start microphone passthrough if enabled
        self.after(600, self._init_passthrough)
    
    def _init_passthrough(self):
        """Initialize microphone passthrough if enabled in settings."""
        if self.settings_manager.get("mic_passthrough_enabled", False):
            input_device_index, output_device_index, volume = self._build_passthrough_params()
            success, error_msg = self.audio_router.start_mic_passthrough(
                input_device_index=input_device_index,
                output_device_index=output_device_index,
                volume=volume
            )
            if not success and error_msg:
                self._show_passthrough_error(error_msg)
    
    def _check_vbcable(self):
        """Check if a virtual audio device is available and prompt user if not.

        On Windows this checks for VB-Cable.  On Linux/macOS virtual audio
        routing works differently (null sinks, BlackHole, etc.) so we skip the
        dialog as long as any output device exists.
        """
        if self.audio_router.is_windows and not self.audio_router.is_vbcable_installed():
            self._show_vbcable_dialog()
    
    def _show_vbcable_dialog(self):
        """Show dialog prompting user to download VBCable."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("VBCable Not Found")
        dialog.geometry("450x180")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        
        # Center dialog
        self._center_dialog(dialog, 450, 180)
        
        # Message label
        message = ctk.CTkLabel(
            dialog,
            text="No virtual audio cable (VBCable) was detected.\n\n"
                 "For best results with VRChat or other applications,\n"
                 "please install VBCable to route audio output.",
            font=ctk.CTkFont(size=13),
            justify="center"
        )
        message.pack(padx=20, pady=(20, 15))
        
        # Button frame
        button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        button_frame.pack(pady=(0, 20))
        
        # Visit Download Page button
        def on_download():
            webbrowser.open("https://vb-audio.com/Cable/")
            dialog.destroy()
        
        download_button = ctk.CTkButton(
            button_frame,
            text="Visit Download Page",
            command=on_download,
            width=150
        )
        download_button.pack(side="left", padx=10)
        
        # Not Now button
        not_now_button = ctk.CTkButton(
            button_frame,
            text="Not Now",
            command=dialog.destroy,
            width=100,
            fg_color="gray",
            hover_color="darkgray"
        )
        not_now_button.pack(side="left", padx=10)
    
    def _open_settings(self):
        """Open the settings window."""
        if self.settings_window is None or not self.settings_window.window.winfo_exists():
            self.settings_window = SettingsWindow(
                parent=self,
                settings_manager=self.settings_manager,
                tts_engine=self.tts_engine,
                audio_router=self.audio_router,
                on_save=self._on_settings_saved
            )
    
    def _on_settings_saved(self):
        """Handle settings saved callback."""
        # Apply appearance mode from saved settings
        appearance_mode = self.settings_manager.get("appearance_mode", "Dark")
        ctk.set_appearance_mode(appearance_mode)
        
        # Reload TTS engine cache settings to pick up any changes
        if hasattr(self, 'tts_engine'):
            self.tts_engine.handle_committed_provider_change()
            self.tts_engine.reload_cache_settings()
        
        # Update microphone passthrough based on settings
        self._update_passthrough()
        
        # Refresh main window status
        if hasattr(self, 'main_window'):
            # Apply theme to main window's hardcoded colors
            self.main_window.apply_theme(appearance_mode)
            self.main_window.refresh_status()
            # Refresh keybinds after settings change
            self.main_window.rebind_shortcuts()
            # Apply button visibility from saved settings
            self.main_window.apply_button_visibility()
    
    def _update_passthrough(self):
        """Update microphone passthrough based on current settings."""
        enabled = self.settings_manager.get("mic_passthrough_enabled", False)
        
        if enabled:
            input_device_index, output_device_index, volume = self._build_passthrough_params()
            success, error_msg = self.audio_router.start_mic_passthrough(
                input_device_index=input_device_index,
                output_device_index=output_device_index,
                volume=volume
            )
            if not success and error_msg:
                self._show_passthrough_error(error_msg)
        else:
            self.audio_router.stop_mic_passthrough()
    
    def _show_passthrough_error(self, error_msg: str):
        """Show an error dialog for microphone passthrough failure."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Microphone Passthrough Error")
        dialog.geometry("450x200")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        
        # Center dialog
        self._center_dialog(dialog, 450, 200)
        
        # Message label
        message = ctk.CTkLabel(
            dialog,
            text="Failed to start microphone passthrough:\n\n"
                 f"{error_msg}\n\n"
                 "Check your audio device settings and try again.",
            font=ctk.CTkFont(size=12),
            justify="center",
            wraplength=400
        )
        message.pack(padx=20, pady=(20, 15))
        
        # OK button
        ok_button = ctk.CTkButton(
            dialog,
            text="OK",
            command=dialog.destroy,
            width=100
        )
        ok_button.pack(pady=(0, 20))
    
    def _setup_shutdown(self):
        """Setup graceful shutdown handlers."""
        # Register cleanup for normal exit
        atexit.register(self._cleanup)
        
        # Handle SIGTERM (kill command)
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Handle SIGINT (Ctrl+C) - only available on Unix-like systems
        if hasattr(signal, 'SIGINT'):
            signal.signal(signal.SIGINT, self._signal_handler)
        
        # Handle window close button
        self.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _signal_handler(self, _signum, _frame):
        """Handle termination signals."""
        self._cleanup()
        # Schedule destroy on the main loop before exiting
        # This prevents TclError from a still-running Tkinter mainloop
        self.after(0, self.destroy)
        sys.exit(0)
    
    def _on_close(self):
        """Handle window close event."""
        self._cleanup()
        self.destroy()
    
    def _cleanup(self):
        """Cleanup resources on exit (safety net for abnormal exits)."""
        # Prevent double cleanup
        if self._cleaned_up:
            return
        self._cleaned_up = True
        
        # Stop any active audio playback
        if hasattr(self, 'audio_router'):
            self.audio_router.stop_playback()
            self.audio_router.stop_mic_passthrough()
        
        # Shutdown TTS engine if it exists
        if hasattr(self, 'tts_engine'):
            self.tts_engine.shutdown()
        
        # Shutdown STT engine if it exists (stops any active recording stream)
        if hasattr(self, 'stt_engine'):
            self.stt_engine.shutdown()

        # Clean up Linux PulseAudio/PipeWire modules created by CriTTS
        if hasattr(self, 'audio_router'):
            self.audio_router.cleanup_linux_sink_modules()


def main():
    """Main entry point."""
    try:
        app = CriTTSApp()
        app.mainloop()
    except Exception as e:
        logging.exception("Fatal error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
