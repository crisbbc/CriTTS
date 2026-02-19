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
    
    def __init__(self):
        """Initialize the application."""
        super().__init__()
        
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
        
        # STT engine - for voice input
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
        
        # Schedule VBCable check after window is rendered
        self.after(500, self._check_vbcable)
    
    def _check_vbcable(self):
        """Check if VBCable is installed and prompt user if not."""
        if not self.audio_router.is_vbcable_installed():
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
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (450 // 2)
        y = (dialog.winfo_screenheight() // 2) - (180 // 2)
        dialog.geometry(f"+{x}+{y}")
        
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
            self.tts_engine.reload_cache_settings()
        
        # Refresh main window status
        if hasattr(self, 'main_window'):
            # Apply theme to main window's hardcoded colors
            self.main_window.apply_theme(appearance_mode)
            self.main_window.refresh_status()
            # Refresh keybinds after settings change
            self.main_window._rebind_shortcuts()

    
    def _setup_shutdown(self):
        """Setup graceful shutdown handlers."""
        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self._on_closing)
        
        # Handle SIGINT (Ctrl+C)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        # Register cleanup on exit
        atexit.register(self._cleanup)
    
    def _signal_handler(self, signum, frame):
        """Handle system signals."""
        self._on_closing()
    
    def _on_closing(self):
        """Handle application closing."""
        # Shutdown main window and wait for worker threads
        if hasattr(self, 'main_window'):
            self.main_window.shutdown()
        
        # Shutdown STT engine
        if hasattr(self, 'stt_engine'):
            self.stt_engine.shutdown()
        
        # Shutdown TTS engine (persist cache index and phrase stats)
        if hasattr(self, 'tts_engine'):
            self.tts_engine.shutdown()
        
        # Save settings
        self.settings_manager.save_settings()
        
        # Destroy window
        self.destroy()

    
    def _cleanup(self):
        """Cleanup resources on exit (safety net for abnormal exits)."""
        # Shutdown TTS engine if it exists
        if hasattr(self, 'tts_engine'):
            self.tts_engine.shutdown()


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
