"""
Keybind Manager Module
Handles dynamic keybind registration and management for the application.
"""
import re
from typing import Dict, Any, Optional, Callable


class KeybindManager:
    """Manages dynamic keyboard shortcuts for the application."""
    
    def __init__(self):
        """Initialize the keybind manager."""
        self._registered_keybinds = {}  # Maps keybind_string to bind_id and callback info
        self._parsed_cache = {}  # Cache for parsed keybind strings
        self._keybind_to_actions = {}  # Maps keybind_string to list of action names (for duplicate detection)

    
    def register_keybind(self, root, keybind_string: str, callback, action_name: str = None) -> bool:
        """
        Register a keybind with the given callback.
        
        Args:
            root: Tkinter root window
            keybind_string: User-friendly keybind format (e.g., "Ctrl+Enter")
            callback: Function to call when keybind is pressed
            action_name: Optional action name for duplicate detection
            
        Returns:
            True if registration successful, False otherwise
        """
        if not keybind_string or not callback:
            return False
        
        # Parse to Tkinter format
        tk_format = self.parse_keybind(keybind_string)
        if not tk_format:
            return False
        
        # Unregister existing if present
        if keybind_string in self._registered_keybinds:
            self.unregister_keybind(root, keybind_string)
        
        # Register with Tkinter using bind_all for application-wide keybinds
        try:
            # Use bind_all to create application-level binding that works regardless of widget focus
            # Use "break" to prevent the event from propagating to other widgets
            bind_id = root.bind_all(tk_format, lambda e: self._handle_keybind(e, callback))
            self._registered_keybinds[keybind_string] = {
                'tk_format': tk_format,
                'callback': callback,
                'bind_id': bind_id,
                'action_name': action_name or keybind_string
            }
            
            # Update keybind-to-actions mapping for duplicate detection
            if keybind_string not in self._keybind_to_actions:
                self._keybind_to_actions[keybind_string] = []
            if action_name and action_name not in self._keybind_to_actions[keybind_string]:
                self._keybind_to_actions[keybind_string].append(action_name)
            
            return True
        except Exception:
            return False

    def _handle_keybind(self, event, callback):
        """
        Handle keybind event with proper focus checking.
        Only trigger if the keybind is not being used by a text widget for text editing.
        """
        # Get the widget that received the event
        widget = event.widget
        
        # Check if this is a text widget and the keybind would interfere with text editing
        if hasattr(widget, 'tag_add'):  # This is likely a text widget
            # For text widgets, only trigger keybinds that are not standard text editing keys
            # Allow Ctrl+Enter (speak), Ctrl+T (clear), etc. but not Ctrl+A, Ctrl+C, etc.
            keysym = getattr(event, 'keysym', '').lower()
            state = getattr(event, 'state', 0)
            is_ctrl = (state & 0x4) != 0  # Control key is pressed
            is_shift = (state & 0x1) != 0  # Shift key is pressed
            
            # Standard text editing shortcuts that should not trigger keybinds
            text_editing_keys = {
                'a', 'c', 'v', 'x', 'z', 'y', 's', 'o', 'n', 'w', 'f', 'h', 'g'
            }
            
            # If Ctrl is pressed and the key is a text editing key, don't trigger keybind
            if is_ctrl and keysym in text_editing_keys:
                return "continue"  # Let the text widget handle it
            
            # If Shift+Enter is pressed in a text widget, don't trigger keybind (allow line break)
            if is_ctrl and is_shift and keysym == 'return':
                return "continue"
        
        # Execute the callback
        try:
            callback()
        except Exception:
            pass
        
        return "break"  # Prevent further event propagation


    
    def unregister_keybind(self, root, keybind_string: str) -> bool:
        """
        Unregister a specific keybind.
        
        Args:
            root: Tkinter root window
            keybind_string: Keybind to unregister
            
        Returns:
            True if unregistration successful, False otherwise
        """
        if keybind_string not in self._registered_keybinds:
            return False
        
        try:
            info = self._registered_keybinds[keybind_string]
            tk_format = info['tk_format']
            
            # Use unbind_all to properly remove bind_all bindings
            root.unbind_all(tk_format)
            del self._registered_keybinds[keybind_string]
            
            # Remove from keybind-to-actions mapping
            if keybind_string in self._keybind_to_actions:
                del self._keybind_to_actions[keybind_string]
            
            return True
        except Exception:
            return False

    
    def unregister_all(self, root):
        """
        Unregister all registered keybinds.
        
        Args:
            root: Tkinter root window
        """
        for keybind_string, info in list(self._registered_keybinds.items()):
            try:
                tk_format = info.get('tk_format')
                if tk_format:
                    # Use unbind_all to properly remove bind_all bindings
                    root.unbind_all(tk_format)
            except Exception:
                pass
        
        self._registered_keybinds.clear()
        self._keybind_to_actions.clear()
        self._parsed_cache.clear()
    
    def parse_keybind(self, keybind_string: str) -> str:
        """
        Convert user-friendly keybind format to Tkinter format.
        
        Args:
            keybind_string: User-friendly format (e.g., "Ctrl+Enter", "Ctrl+Shift+A")
            
        Returns:
            Tkinter format string (e.g., "<Control-Return>", "<Control-Shift-A>")
        """
        if not keybind_string:
            return ""
        if keybind_string in self._parsed_cache:
            return self._parsed_cache[keybind_string]
        
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
            else:
                key = part
        
        if not key:
            return ""
        
        # Map special keys to Tkinter format
        key_mapping = {
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
        
        # Check if it's a special key
        if key in key_mapping:
            key = key_mapping[key]
        elif len(key) == 1 and key.isalnum():
            # Single alphanumeric key - capitalize it
            key = key.upper()
        else:
            # Unknown key
            return ""
        
        # Build Tkinter format
        if modifiers:
            result = f"<{'-'.join(modifiers)}-{key}>"
        else:
            result = f"<{key}>"
        self._parsed_cache[keybind_string] = result
        return result
    
    def validate_keybind(self, keybind_string: str) -> bool:
        """
        Check if a keybind string is valid with comprehensive validation.
        
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
        import re
        pattern = r'^[A-Za-z0-9+\-_=,\.\/;\'\[\]\\`~!@#$%^&*(){}|:<>? ]+$'
        if not re.match(pattern, keybind_string):
            return False
        
        # Check for critical system shortcuts
        normalized = keybind_string.lower().replace(' ', '')
        critical_shortcuts = ['alt+f4', 'ctrl+alt+delete', 'win+l', 'win+r', 'win+e', 'ctrl+shift+esc']
        if any(cs in normalized for cs in critical_shortcuts):
            return False
        
        # Check for reasonable length
        if len(keybind_string) > 50:
            return False
        
        # Parse parts and validate
        parts = [part.strip().lower() for part in keybind_string.split('+')]
        
        # Check for at least one non-modifier key
        has_non_modifier = False
        valid_modifiers = {'ctrl', 'control', 'shift', 'alt', 'win', 'super'}
        valid_keys = {
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
        
        for part in parts:
            if part not in valid_modifiers:
                if len(part) == 1 and part.isalnum():
                    has_non_modifier = True
                elif part in valid_keys:
                    has_non_modifier = True
                else:
                    return False
        
        # Should have at least one non-modifier key
        if not has_non_modifier:
            return False
        
        # Should not have duplicate modifiers
        modifier_parts = [part for part in parts if part in valid_modifiers]
        if len(set(modifier_parts)) != len(modifier_parts):
            return False
        
        # Validate that the parsed Tkinter format is not empty
        tk_format = self.parse_keybind(keybind_string)
        if not tk_format:
            return False
        
        return True
    
    def check_duplicate_keybind(self, keybind_string: str, current_action: str = None) -> list:
        """
        Check for duplicate keybinds across actions.
        
        Args:
            keybind_string: Keybind string to check
            current_action: Current action name to exclude from conflict check
            
        Returns:
            List of conflicting action names (empty if no conflicts)
        """
        if not keybind_string:
            return []
        
        # Normalize the keybind string for comparison
        normalized = keybind_string.strip().lower()
        
        conflicts = []
        for registered_keybind, actions in self._keybind_to_actions.items():
            if registered_keybind.strip().lower() == normalized:
                for action in actions:
                    if current_action and action == current_action:
                        continue
                    if action not in conflicts:
                        conflicts.append(action)
        
        return conflicts

    
    def get_registered_keybinds(self) -> dict:
        """
        Get all registered keybinds.
        
        Returns:
            Dictionary mapping keybind strings to their callbacks
        """
        return {k: v['callback'] for k, v in self._registered_keybinds.items()}
    
    def check_conflict(self, keybind_string: str) -> bool:
        """
        Check if a keybind is already registered.
        
        Args:
            keybind_string: Keybind to check
            
        Returns:
            True if conflict exists, False otherwise
        """
        return keybind_string in self._registered_keybinds
