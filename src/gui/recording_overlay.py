"""
Recording Overlay Module
A small always-on-top overlay window that displays recording state with
smooth animations and duration timer.
"""
import customtkinter as ctk
from typing import Optional
import time

from .theme_constants import (
    COLOR_RECORDING,
    COLOR_RECORDING_PULSE,
    COLOR_RECORDING_DIM,
    COLOR_OVERLAY_BG,
    COLOR_STATUS_IDLE,
    COLOR_NEUTRAL_LIGHTEST,
    FONT_MD,
    FONT_LG,
    FONT_WEIGHT_BOLD,
    RADIUS_MD,
)


class RecordingOverlay(ctk.CTkToplevel):
    """
    A compact always-on-top overlay window showing recording state.
    
    Features:
    - Smooth pulsing red indicator when recording
    - Recording duration timer
    - Draggable position
    - Show/hide toggle
    """
    
    def __init__(self, master):
        """
        Initialize the recording overlay.
        
        Args:
            master: Parent window (main window)
        """
        super().__init__(master)
        
        # Remove title bar for compact HUD look
        self.overrideredirect(True)
        
        # Always stay on top
        self.attributes("-topmost", True)
        
        # Set slight transparency
        self.attributes("-alpha", 0.92)
        
        # Fixed small size (wider for duration display, taller for two lines)
        self.geometry("180x60")
        
        # Set background color
        self.configure(fg_color=COLOR_OVERLAY_BG)
        
        # Initialize state
        self._recording = False
        self._pulse_job: Optional[str] = None
        self._pulse_state = False
        self._pulse_intensity = 0.0  # For smooth animation
        
        # Recording duration tracking
        self._recording_start_time: Optional[float] = None
        self._duration_job: Optional[str] = None
        
        # Drag state
        self._drag_x = 0
        self._drag_y = 0
        
        # Build UI
        self._create_widgets()
        
        # Position at bottom-right corner
        self._position_bottom_right()
        
        # Bind drag events
        self._bind_drag_events()
        
        # Hide by default
        self.withdraw()
    
    def _create_widgets(self):
        """Create the overlay widgets."""
        # Main frame
        self._frame = ctk.CTkFrame(
            self,
            fg_color=COLOR_OVERLAY_BG,
            corner_radius=RADIUS_MD
        )
        self._frame.pack(fill="both", expand=True, padx=2, pady=2)
        
        # Container for indicator and text
        self._container = ctk.CTkFrame(
            self._frame,
            fg_color="transparent"
        )
        self._container.pack(fill="both", expand=True, padx=8, pady=6)
        
        # Recording dot indicator
        self._dot_label = ctk.CTkLabel(
            self._container,
            text="●",
            font=ctk.CTkFont(size=FONT_LG, weight=FONT_WEIGHT_BOLD),
            text_color=COLOR_STATUS_IDLE,
            width=20
        )
        self._dot_label.pack(side="left", padx=(0, 8))
        
        # Status text container (for text + duration)
        self._text_container = ctk.CTkFrame(
            self._container,
            fg_color="transparent"
        )
        self._text_container.pack(side="left", fill="x", expand=True)
        
        # Status text
        self._text_label = ctk.CTkLabel(
            self._text_container,
            text="Not recording",
            font=ctk.CTkFont(size=FONT_MD),
            text_color=COLOR_NEUTRAL_LIGHTEST,
            anchor="w"
        )
        self._text_label.pack(side="top", fill="x", pady=(0, 2))
        
        # Duration label (hidden by default)
        self._duration_label = ctk.CTkLabel(
            self._text_container,
            text="",
            font=ctk.CTkFont(size=FONT_MD - 2),
            text_color=COLOR_NEUTRAL_LIGHTEST,
            anchor="w"
        )
        self._duration_label.pack(side="top", fill="x")
    
    def _position_bottom_right(self, taskbar_offset: int = 60):
        """
        Position the overlay at the bottom-right corner of the screen.
        
        Args:
            taskbar_offset: Pixels to offset from bottom of screen to account for taskbar.
                           Default 60px works for Windows with default taskbar.
                           Use 0 for auto-hide taskbar or fullscreen apps.
                           Use ~30 for macOS (menu bar at top, no bottom taskbar).
        """
        self.update_idletasks()
        
        # Get screen dimensions
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        # Get overlay dimensions (updated for duration display)
        overlay_width = 180
        overlay_height = 60
        
        # Calculate position (bottom-right with margin)
        margin = 20
        x = screen_width - overlay_width - margin
        y = screen_height - overlay_height - margin - taskbar_offset
        
        self.geometry(f"+{x}+{y}")
    
    def _bind_drag_events(self):
        """Bind mouse events for dragging the overlay."""
        self._frame.bind("<Button-1>", self._on_drag_start)
        self._frame.bind("<B1-Motion>", self._on_drag_motion)
        self._dot_label.bind("<Button-1>", self._on_drag_start)
        self._dot_label.bind("<B1-Motion>", self._on_drag_motion)
        self._text_label.bind("<Button-1>", self._on_drag_start)
        self._text_label.bind("<B1-Motion>", self._on_drag_motion)
        self._duration_label.bind("<Button-1>", self._on_drag_start)
        self._duration_label.bind("<B1-Motion>", self._on_drag_motion)
        self._container.bind("<Button-1>", self._on_drag_start)
        self._container.bind("<B1-Motion>", self._on_drag_motion)
        self._text_container.bind("<Button-1>", self._on_drag_start)
        self._text_container.bind("<B1-Motion>", self._on_drag_motion)
    
    def _on_drag_start(self, event):
        """Record the starting position for dragging."""
        self._drag_x = event.x
        self._drag_y = event.y
    
    def _on_drag_motion(self, event):
        """Update window position during drag."""
        # Get current window position
        current_x = self.winfo_x()
        current_y = self.winfo_y()
        
        # Calculate new position
        new_x = current_x + (event.x - self._drag_x)
        new_y = current_y + (event.y - self._drag_y)
        
        # Update window position
        self.geometry(f"+{new_x}+{new_y}")
    
    def set_recording(self, state: bool):
        """
        Set the recording state of the overlay.
        
        Args:
            state: True if recording, False otherwise
        """
        self._recording = state
        
        if state:
            # Start recording state
            self._recording_start_time = time.time()
            self._text_label.configure(text="Recording")
            self._dot_label.configure(text_color=COLOR_RECORDING)
            self._pulse_animation()
            self._update_duration()
        else:
            # Stop recording state
            self._cancel_pulse()
            self._cancel_duration()
            self._dot_label.configure(text_color=COLOR_STATUS_IDLE)
            self._text_label.configure(text="Not recording")
            self._duration_label.configure(text="")
            self._recording_start_time = None
    
    def _pulse_animation(self):
        """
        Animate the recording indicator with a smooth pulsing effect.
        
        Uses a sinusoidal-like pattern for smoother visual feedback.
        """
        if not self._recording:
            return
        
        # Toggle pulse state
        self._pulse_state = not self._pulse_state
        
        # Use three-step color transition for smoother animation
        # Bright -> Medium -> Dim -> Medium -> Bright (cycle)
        if self._pulse_state:
            color = COLOR_RECORDING_PULSE  # Bright red
        else:
            color = COLOR_RECORDING_DIM    # Dimmer red
        
        self._dot_label.configure(text_color=color)
        
        # Schedule next pulse (400ms for smoother animation)
        self._pulse_job = self.after(400, self._pulse_animation)
    
    def _cancel_pulse(self):
        """Cancel any pending pulse animation."""
        if self._pulse_job:
            self.after_cancel(self._pulse_job)
            self._pulse_job = None
        self._pulse_state = False
    
    def _update_duration(self):
        """Update the recording duration display."""
        if not self._recording or self._recording_start_time is None:
            return
        
        # Calculate elapsed time
        elapsed = time.time() - self._recording_start_time
        
        # Format as MM:SS
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        duration_text = f"{minutes:02d}:{seconds:02d}"
        
        # Update label
        self._duration_label.configure(text=duration_text)
        
        # Schedule next update (every second)
        self._duration_job = self.after(1000, self._update_duration)
    
    def _cancel_duration(self):
        """Cancel the duration update timer."""
        if self._duration_job:
            self.after_cancel(self._duration_job)
            self._duration_job = None
    
    def show_overlay(self):
        """Show the overlay window."""
        self.deiconify()
    
    def hide_overlay(self):
        """Hide the overlay window and stop any recording state."""
        self.set_recording(False)
        self.withdraw()
    
    def destroy(self):
        """Clean up timers before destroying the overlay."""
        self._cancel_pulse()
        self._cancel_duration()
        super().destroy()