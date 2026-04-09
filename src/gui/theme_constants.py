"""
Design System Constants for CriTTS

A modern design system with glassmorphism-inspired aesthetics,
consistent spacing, colors, typography, and component dimensions.
"""

# =============================================================================
# SPACING TOKENS
# Base unit: 4px - all spacing should be multiples of this unit
# =============================================================================
SPACING_BASE = 4
SPACING_XS = 8      # 2 * base - compact spacing
SPACING_SM = 12     # 3 * base - small spacing
SPACING_MD = 16     # 4 * base - medium spacing (default)
SPACING_LG = 24     # 6 * base - large spacing
SPACING_XL = 32     # 8 * base - extra large spacing
SPACING_2XL = 48    # 12 * base - section spacing

# =============================================================================
# MODERN COLOR PALETTE
# Inspired by modern design trends with better accessibility
# =============================================================================

# Primary colors (main brand color - vibrant blue)
COLOR_PRIMARY = "#6366f1"           # Indigo 500
COLOR_PRIMARY_HOVER = "#4f46e5"     # Indigo 600
COLOR_PRIMARY_LIGHT = "#818cf8"     # Indigo 400

# Accent colors (secondary actions)
COLOR_ACCENT = "#8b5cf6"            # Violet 500
COLOR_ACCENT_HOVER = "#7c3aed"      # Violet 600

# Success colors (positive actions like speak)
COLOR_SUCCESS = "#10b981"           # Emerald 500
COLOR_SUCCESS_HOVER = "#059669"     # Emerald 600
COLOR_SUCCESS_LIGHT = "#34d399"     # Emerald 400

# Danger colors (destructive actions like stop, close)
COLOR_DANGER = "#ef4444"            # Red 500
COLOR_DANGER_HOVER = "#dc2626"      # Red 600
COLOR_DANGER_LIGHT = "#f87171"      # Red 400

# Warning colors (caution states)
COLOR_WARNING = "#f59e0b"           # Amber 500
COLOR_WARNING_HOVER = "#d97706"     # Amber 600

# Info colors (informational states)
COLOR_INFO = "#3b82f6"              # Blue 500
COLOR_INFO_HOVER = "#2563eb"        # Blue 600

# Neutral colors (backgrounds, text, borders) - Dark theme optimized
COLOR_NEUTRAL_DARKEST = "#0f172a"   # Slate 900
COLOR_NEUTRAL_DARK = "#1e293b"      # Slate 800
COLOR_NEUTRAL_MEDIUM = "#334155"    # Slate 700
COLOR_NEUTRAL = "#475569"           # Slate 600
COLOR_NEUTRAL_LIGHT = "#64748b"     # Slate 500
COLOR_NEUTRAL_LIGHTER = "#94a3b8"   # Slate 400
COLOR_NEUTRAL_LIGHTEST = "#cbd5e1"  # Slate 300

# Background colors for glassmorphism effect (Dark theme)
COLOR_BG_PRIMARY = "#0f172a"        # Main background
COLOR_BG_SECONDARY = "#1e293b"      # Card/panel background
COLOR_BG_TERTIARY = "#334155"       # Elevated surfaces
COLOR_BG_GLASS = "#1e293b80"        # Semi-transparent for glass effect

# Light mode background colors
COLOR_BG_PRIMARY_LIGHT = "#f8fafc"      # Main background (Slate 50)
COLOR_BG_SECONDARY_LIGHT = "#f1f5f9"    # Card/panel background (Slate 100)
COLOR_BG_TERTIARY_LIGHT = "#e2e8f0"     # Elevated surfaces (Slate 200)

# Light mode text/input colors
COLOR_NEUTRAL_DARK_LIGHT = "#e2e8f0"    # Text input bg (Slate 200)
COLOR_NEUTRAL_MEDIUM_LIGHT = "#cbd5e1"  # Line highlight (Slate 300)
COLOR_TEXT_PRIMARY_LIGHT = "#1e293b"    # Main text (Slate 800)
COLOR_TEXT_SECONDARY_LIGHT = "#334155"  # Secondary text (Slate 700)
COLOR_TEXT_MUTED_LIGHT = "#64748b"      # Muted text (Slate 500)
COLOR_PRIMARY_LIGHT_MODE = "#4f46e5"    # Voice name (Indigo 600)

# Status colors for activity indicator
COLOR_STATUS_ACTIVE = "#10b981"     # Emerald 500
COLOR_STATUS_ERROR = "#ef4444"      # Red 500
COLOR_STATUS_WARNING = "#f59e0b"    # Amber 500
COLOR_STATUS_SUCCESS = "#10b981"    # Emerald 500
COLOR_STATUS_IDLE = "#64748b"       # Slate 500

# Recording overlay colors
COLOR_RECORDING = "#ef4444"         # Red 500 — active recording
COLOR_RECORDING_PULSE = "#fca5a5"   # Red 300 — pulse highlight
COLOR_RECORDING_DIM = "#dc2626"     # Red 600 — dim pulse state
COLOR_OVERLAY_BG = "#1e293b"        # Matches COLOR_BG_SECONDARY

# Transcription/loading state colors
COLOR_TRANSCRIBING = "#f59e0b"      # Amber 500 — transcribing state
COLOR_TRANSCRIBING_HOVER = "#d97706"  # Amber 600

# =============================================================================
# TYPOGRAPHY SCALE
# Modern font sizing with better readability
# =============================================================================

# Font sizes
FONT_XS = 11    # Small text, secondary info
FONT_SM = 12    # Labels, small controls
FONT_MD = 14    # Body text, default
FONT_LG = 16    # Subheaders, important labels
FONT_XL = 18    # Headers
FONT_2XL = 24   # Large titles
FONT_3XL = 32   # Hero text

# Font weights
FONT_WEIGHT_NORMAL = "normal"
FONT_WEIGHT_BOLD = "bold"
# Note: CustomTkinter doesn't support medium weight, only normal and bold

# Line heights (for reference, CTk doesn't directly support)
LINE_HEIGHT_TIGHT = 1.25
LINE_HEIGHT_NORMAL = 1.5
LINE_HEIGHT_RELAXED = 1.75

# =============================================================================
# COMPONENT DIMENSIONS
# Modern sizing with touch-friendly targets
# =============================================================================

# Button dimensions
BUTTON_HEIGHT = 44          # Touch-friendly height
BUTTON_HEIGHT_SM = 36       # Compact buttons
BUTTON_HEIGHT_LG = 52       # Prominent actions
BUTTON_MIN_WIDTH = 100
BUTTON_WIDTH_DEFAULT = 140  # Wider default for modern look

# Input field dimensions
INPUT_HEIGHT = 44           # Match button height
INPUT_HEIGHT_SM = 36
INPUT_HEIGHT_LG = 52

# Frame heights
FRAME_CONTROLS_HEIGHT = 72  # Taller for better spacing
FRAME_STATUS_HEIGHT = 56
FRAME_BUTTONS_HEIGHT = 64

# Icon sizes
ICON_SIZE_SM = 16
ICON_SIZE_MD = 20
ICON_SIZE_LG = 24
ICON_SIZE_XL = 32

# =============================================================================
# BORDER RADIUS
# Modern rounded corners for softer look
# =============================================================================
RADIUS_NONE = 0
RADIUS_SM = 6
RADIUS_MD = 10
RADIUS_LG = 14
RADIUS_XL = 20
RADIUS_FULL = 9999         # Fully rounded (pills)

# =============================================================================
# SHADOWS & ELEVATION
# For depth perception (used in styling logic)
# =============================================================================
ELEVATION_NONE = 0
ELEVATION_SM = 1
ELEVATION_MD = 2
ELEVATION_LG = 3
ELEVATION_XL = 4

# =============================================================================
# ANIMATION TIMING
# For smooth transitions
# =============================================================================
ANIMATION_FAST = 100        # ms - quick feedback
ANIMATION_NORMAL = 200      # ms - standard transitions
ANIMATION_SLOW = 300        # ms - deliberate movements
ANIMATION_VERY_SLOW = 500   # ms - complex animations

# =============================================================================
# WINDOW DIMENSIONS
# Default and minimum window sizes
# =============================================================================
WINDOW_MAIN_WIDTH = 1200
WINDOW_MAIN_HEIGHT = 640
WINDOW_MAIN_MIN_WIDTH = 1180
WINDOW_MAIN_MIN_HEIGHT = 500

WINDOW_SETTINGS_WIDTH = 860
WINDOW_SETTINGS_HEIGHT = 640
WINDOW_SETTINGS_MIN_WIDTH = 820
WINDOW_SETTINGS_MIN_HEIGHT = 540

# =============================================================================
# SETTINGS SURFACE TOKENS
# Shared settings-shell and section styling derived from the main window.
# =============================================================================
SETTINGS_WINDOW_FG = COLOR_BG_PRIMARY
SETTINGS_PANE_FG = COLOR_BG_SECONDARY
SETTINGS_SECTION_FG = COLOR_BG_TERTIARY
SETTINGS_BORDER_COLOR = COLOR_NEUTRAL_MEDIUM
SETTINGS_SUPPORTING_TEXT_COLOR = "#b7c4d6"
SETTINGS_MUTED_TEXT_COLOR = COLOR_NEUTRAL_LIGHT
SETTINGS_TAB_SELECTED_COLOR = "#4338ca"
SETTINGS_TAB_SELECTED_HOVER = "#3730a3"
SETTINGS_TAB_UNSELECTED_HOVER = COLOR_NEUTRAL_MEDIUM
SETTINGS_TAB_TEXT_COLOR = COLOR_NEUTRAL_LIGHTEST


def get_active_appearance_mode() -> str:
    """Return the current CTk appearance mode with a dark fallback."""
    try:
        import customtkinter as ctk
        mode = ctk.get_appearance_mode()
    except Exception:
        return "Dark"

    return mode if mode in {"Light", "Dark"} else "Dark"


def get_settings_surface_theme(mode: str | None = None) -> dict:
    """
    Get shared style tokens for the settings shell and section surfaces.

    Returns:
        Dictionary of semantic settings surface tokens.
    """
    resolved_mode = "Dark" if mode is None else mode
    colors = get_theme_colors(resolved_mode)

    if resolved_mode == "Light":
        tab_selected_color = "#c7d2fe"
        tab_selected_hover = "#a5b4fc"
        tab_unselected_hover = COLOR_BG_TERTIARY_LIGHT
        tab_text_color = COLOR_TEXT_PRIMARY_LIGHT
        text_supporting = COLOR_TEXT_SECONDARY_LIGHT
    else:
        if resolved_mode == "System":
            resolved_mode = get_active_appearance_mode()

        if resolved_mode == "Light":
            tab_selected_color = "#c7d2fe"
            tab_selected_hover = "#a5b4fc"
            tab_unselected_hover = COLOR_BG_TERTIARY_LIGHT
            tab_text_color = COLOR_TEXT_PRIMARY_LIGHT
            text_supporting = COLOR_TEXT_SECONDARY_LIGHT
        else:
            tab_selected_color = SETTINGS_TAB_SELECTED_COLOR
            tab_selected_hover = SETTINGS_TAB_SELECTED_HOVER
            tab_unselected_hover = SETTINGS_TAB_UNSELECTED_HOVER
            tab_text_color = SETTINGS_TAB_TEXT_COLOR
            text_supporting = SETTINGS_SUPPORTING_TEXT_COLOR

    return {
        "window_fg": colors["bg_primary"],
        "pane_fg": colors["bg_secondary"],
        "section_fg": colors["bg_tertiary"],
        "border_color": colors["border_color"],
        "sidebar_button_hover": colors["bg_tertiary"],
        "scrollbar_button_color": colors["border_color"],
        "scrollbar_button_hover_color": colors["text_muted"],
        "text_primary": colors["text_primary"],
        "text_supporting": text_supporting,
        "text_secondary": colors["text_secondary"],
        "text_muted": colors["text_muted"],
        "tab_selected_color": tab_selected_color,
        "tab_selected_hover": tab_selected_hover,
        "tab_unselected_hover": tab_unselected_hover,
        "tab_text_color": tab_text_color,
        "button_neutral": colors["button_neutral"],
        "button_neutral_hover": colors["button_neutral_hover"],
        "shell_corner_radius": RADIUS_LG,
        "section_corner_radius": RADIUS_MD,
    }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_font(size: int, weight: str = FONT_WEIGHT_NORMAL) -> dict:
    """
    Get font configuration dictionary.
    
    Args:
        size: Font size in pixels
        weight: Font weight ('normal' or 'bold')
    
    Returns:
        Dictionary with font configuration for CTkFont
    """
    return {"size": size, "weight": weight}


def get_color_for_state(state: str) -> str:
    """
    Get semantic color for a given state.
    
    Args:
        state: State name ('active', 'error', 'warning', 'success', 'idle')
    
    Returns:
        Color hex string
    """
    color_map = {
        "active": COLOR_STATUS_ACTIVE,
        "error": COLOR_STATUS_ERROR,
        "warning": COLOR_STATUS_WARNING,
        "success": COLOR_STATUS_SUCCESS,
        "idle": COLOR_STATUS_IDLE,
    }
    return color_map.get(state, COLOR_STATUS_IDLE)




def get_theme_colors(mode: str) -> dict:
    """
    Get theme colors for the specified appearance mode.
    
    Args:
        mode: Appearance mode ('Dark', 'Light', or 'System')
    
    Returns:
        Dictionary mapping semantic color keys to hex values
    """
    # Handle System mode by detecting current appearance
    if mode == "System":
        try:
            import customtkinter as ctk
            mode = ctk.get_appearance_mode()
        except Exception:
            mode = "Dark"
    
    if mode == "Light":
        return {
            "bg_primary": COLOR_BG_PRIMARY_LIGHT,
            "bg_secondary": COLOR_BG_SECONDARY_LIGHT,
            "bg_tertiary": COLOR_BG_TERTIARY_LIGHT,
            "input_bg": COLOR_NEUTRAL_DARK_LIGHT,
            "line_highlight": COLOR_NEUTRAL_MEDIUM_LIGHT,
            "text_primary": COLOR_TEXT_PRIMARY_LIGHT,
            "text_secondary": COLOR_TEXT_SECONDARY_LIGHT,
            "text_muted": COLOR_TEXT_MUTED_LIGHT,
            "voice_name": COLOR_PRIMARY_LIGHT_MODE,
            "border_color": COLOR_NEUTRAL_MEDIUM_LIGHT,
            "button_active": COLOR_PRIMARY_LIGHT_MODE,
            "button_active_hover": COLOR_PRIMARY_HOVER,
            "button_neutral": COLOR_BG_TERTIARY_LIGHT,
            "button_neutral_hover": COLOR_NEUTRAL_MEDIUM_LIGHT,
        }
    else:  # Dark mode (default)
        return {
            "bg_primary": COLOR_BG_PRIMARY,
            "bg_secondary": COLOR_BG_SECONDARY,
            "bg_tertiary": COLOR_BG_TERTIARY,
            "input_bg": COLOR_NEUTRAL_DARK,
            "line_highlight": COLOR_NEUTRAL_MEDIUM,
            "text_primary": COLOR_NEUTRAL_LIGHTEST,
            "text_secondary": COLOR_NEUTRAL_LIGHTER,
            "text_muted": COLOR_NEUTRAL_LIGHT,
            "voice_name": COLOR_PRIMARY_LIGHT,
            "border_color": COLOR_NEUTRAL_MEDIUM,
            "button_active": COLOR_PRIMARY,
            "button_active_hover": COLOR_PRIMARY_HOVER,
            "button_neutral": COLOR_NEUTRAL_MEDIUM,
            "button_neutral_hover": COLOR_NEUTRAL,
        }
