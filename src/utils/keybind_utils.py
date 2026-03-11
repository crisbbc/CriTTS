"""
Keybind Utilities Module
Pure validation and parsing functions for keybind strings.
This module avoids circular imports by not depending on GUI modules.
"""
import re
from typing import Optional


# Valid modifier keys
VALID_MODIFIERS = {'ctrl', 'control', 'shift', 'alt', 'win', 'super'}

# Valid non-modifier keys (special keys and single characters)
VALID_KEYS = {
    'enter', 'return', 'space', 'escape', 'esc', 'tab', 'backspace',
    'delete', 'del', 'insert', 'home', 'end', 'pageup', 'pagedown',
    'up', 'down', 'left', 'right', 'f1', 'f2', 'f3', 'f4', 'f5', 'f6',
    'f7', 'f8', 'f9', 'f10', 'f11', 'f12', 'comma', 'period', 'slash',
    'semicolon', 'quote', 'backslash', 'bracketleft', 'bracketright',
    'minus', 'equal', 'grave', 'plus', 'asterisk', 'question', 'exclam',
    'at', 'numbersign', 'dollar', 'percent', 'asciicircum', 'ampersand',
    'parenleft', 'parenright', 'underscore', 'braceleft', 'braceright',
    'bar', 'colon', 'less', 'greater', 'question', 'tilde'
}

# Critical system shortcuts that should not be allowed
CRITICAL_SHORTCUTS = ['alt+f4', 'ctrl+alt+delete', 'win+l', 'win+r', 'win+e', 'ctrl+shift+esc']

# Mapping of special keys to Tkinter format
KEY_TO_TKINTER = {
    'enter': 'Return',
    'return': 'Return',
    'space': 'space',
    'escape': 'Escape',
    'esc': 'Escape',
    'tab': 'Tab',
    'backspace': 'BackSpace',
    'delete': 'Delete',
    'del': 'Delete',
    'insert': 'Insert',
    'home': 'Home',
    'end': 'End',
    'pageup': 'Prior',
    'pagedown': 'Next',
    'up': 'Up',
    'down': 'Down',
    'left': 'Left',
    'right': 'Right',
    'f1': 'F1', 'f2': 'F2', 'f3': 'F3', 'f4': 'F4',
    'f5': 'F5', 'f6': 'F6', 'f7': 'F7', 'f8': 'F8',
    'f9': 'F9', 'f10': 'F10', 'f11': 'F11', 'f12': 'F12',
    'comma': 'comma',
    'period': 'period',
    'slash': 'slash',
    'semicolon': 'semicolon',
    'quote': 'quoteright',
    'backslash': 'backslash',
    'bracketleft': 'bracketleft',
    'bracketright': 'bracketright',
    'minus': 'minus',
    'equal': 'equal',
    'grave': 'grave',
}


def validate_keybind_format(keybind_string: str) -> bool:
    """
    Validate keybind format with comprehensive validation.
    
    This is a pure function that can be called from any module without
    creating circular imports.
    
    Args:
        keybind_string: Keybind to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not keybind_string or not isinstance(keybind_string, str):
        return False
    
    # Strip whitespace
    keybind_string = keybind_string.strip()
    if not keybind_string:
        return False
    
    # Basic format check - should contain only valid characters
    pattern = r'^[A-Za-z0-9+\-_=,\.\/;\'\[\]\\`~!@#$%^&*(){}|:<>? ]+$'
    if not re.match(pattern, keybind_string):
        return False
    
    # Check for critical system shortcuts
    normalized = keybind_string.lower().replace(' ', '')
    if any(cs in normalized for cs in CRITICAL_SHORTCUTS):
        return False
    
    # Check for reasonable length
    if len(keybind_string) > 50:
        return False
    
    # Parse parts and validate
    parts = [part.strip().lower() for part in keybind_string.split('+')]
    
    # Check for at least one non-modifier key
    has_non_modifier = False
    
    for part in parts:
        if part not in VALID_MODIFIERS:
            if len(part) == 1 and part.isalnum():
                has_non_modifier = True
            elif part in VALID_KEYS:
                has_non_modifier = True
            else:
                return False
    
    # Should have at least one non-modifier key
    if not has_non_modifier:
        return False
    
    # Should not have duplicate modifiers
    modifier_parts = [part for part in parts if part in VALID_MODIFIERS]
    if len(set(modifier_parts)) != len(modifier_parts):
        return False
    
    # Validate that the parsed Tkinter format is not empty
    tk_format = parse_keybind_to_tkinter(keybind_string)
    if not tk_format:
        return False
    
    return True


def parse_keybind_to_tkinter(keybind_string: str) -> Optional[str]:
    """
    Convert user-friendly keybind format to Tkinter format.
    
    Args:
        keybind_string: User-friendly format (e.g., "Ctrl+Enter", "Ctrl+Shift+A")
        
    Returns:
        Tkinter format string (e.g., "<Control-Return>", "<Control-Shift-A>")
        or None if parsing fails
    """
    if not keybind_string:
        return None
    
    parts = keybind_string.split('+')
    modifiers = []
    key = None
    
    for part in parts:
        part = part.strip().lower()
        if part in ['ctrl', 'control']:
            modifiers.append('Control')
        elif part == 'shift':
            modifiers.append('Shift')
        elif part == 'alt':
            modifiers.append('Alt')
        elif part in ['win', 'super']:
            modifiers.append('Mod4')
        else:
            key = part
    
    if not key:
        return None
    
    # Check if it's a special key
    if key in KEY_TO_TKINTER:
        key = KEY_TO_TKINTER[key]
    elif len(key) == 1 and key.isalnum():
        # Single alphanumeric key - use lowercase for Tkinter
        # (Tkinter uses lowercase for key names, e.g., <Control-t> not <Control-T>)
        key = key.lower()
    else:
        # Unknown key
        return None
    
    # Build Tkinter format
    if modifiers:
        return f"<{'-'.join(modifiers)}-{key}>"
    else:
        return f"<{key}>"