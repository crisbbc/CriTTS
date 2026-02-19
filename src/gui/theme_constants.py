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
COLOR_OVERLAY_BG = "#1e293b"        # Matches COLOR_BG_SECONDARY

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
FONT_WEIGHT_MEDIUM = "normal"  # CustomTkinter doesn't support medium
FONT_WEIGHT_BOLD = "bold"

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
WINDOW_MAIN_WIDTH = 1020
WINDOW_MAIN_HEIGHT = 640
WINDOW_MAIN_MIN_WIDTH = 1020
WINDOW_MAIN_MIN_HEIGHT = 500

WINDOW_SETTINGS_WIDTH = 720
WINDOW_SETTINGS_HEIGHT = 640
WINDOW_SETTINGS_MIN_WIDTH = 660
WINDOW_SETTINGS_MIN_HEIGHT = 540

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


def get_elevation_shadow(elevation: int) -> dict:
    """
    Get shadow properties for elevation level.
    
    Args:
        elevation: Elevation level (0-4)
    
    Returns:
        Dictionary with shadow properties (for reference)
    """
    shadows = {
        0: {"blur": 0, "spread": 0, "color": "transparent"},
        1: {"blur": 4, "spread": 0, "color": "rgba(0,0,0,0.1)"},
        2: {"blur": 8, "spread": 0, "color": "rgba(0,0,0,0.12)"},
        3: {"blur": 16, "spread": 0, "color": "rgba(0,0,0,0.14)"},
        4: {"blur": 24, "spread": 0, "color": "rgba(0,0,0,0.16)"},
    }
    return shadows.get(elevation, shadows[0])


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
            "input_bg": COLOR_NEUTRAL_DARK_LIGHT,
            "line_highlight": COLOR_NEUTRAL_MEDIUM_LIGHT,
            "text_primary": COLOR_TEXT_PRIMARY_LIGHT,
            "text_secondary": COLOR_TEXT_SECONDARY_LIGHT,
            "text_muted": COLOR_TEXT_MUTED_LIGHT,
            "voice_name": COLOR_PRIMARY_LIGHT_MODE,
        }
    else:  # Dark mode (default)
        return {
            "bg_primary": COLOR_BG_PRIMARY,
            "bg_secondary": COLOR_BG_SECONDARY,
            "input_bg": COLOR_NEUTRAL_DARK,
            "line_highlight": COLOR_NEUTRAL_MEDIUM,
            "text_primary": COLOR_NEUTRAL_LIGHTEST,
            "text_secondary": COLOR_NEUTRAL_LIGHTER,
            "text_muted": COLOR_NEUTRAL_LIGHT,
            "voice_name": COLOR_PRIMARY_LIGHT,
        }
