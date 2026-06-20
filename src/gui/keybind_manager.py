"""
Keybind Manager Module
Handles dynamic keybind registration and management for the application.
Supports both Tkinter application-wide keybinds and system-wide global hotkeys.
"""
import re
import logging
from typing import Dict, Any, Callable

logger = logging.getLogger(__name__)

# Try to import keyboard library for global hotkeys
_keyboard_available = False
try:
    import keyboard
    _keyboard_available = True
except ImportError:
    logger.debug("keyboard library not available - global hotkeys disabled")


class KeybindManager:
    """Manages dynamic keyboard shortcuts for the application."""
    
    def __init__(self):
        """Initialize the keybind manager."""
        self._registered_keybinds = {}  # Maps keybind_string to bind_id and callback info
        self._parsed_cache = {}  # Cache for parsed keybind strings
        self._keybind_to_actions = {}  # Maps keybind_string to list of action names (for duplicate detection)
        self._global_hotkeys_enabled = False  # Track if global hotkeys are enabled
        self._global_hotkeys = {}  # Maps keybind_string to keyboard hook

    
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
            # Allow Ctrl+T (clear), Ctrl+S (speak), etc. but not Ctrl+A, Ctrl+C, etc.
            keysym = getattr(event, 'keysym', '').lower()
            state = getattr(event, 'state', 0)
            is_ctrl = (state & 0x4) != 0  # Control key is pressed
            
            # Standard clipboard/undo shortcuts that should not trigger keybinds
            # Narrowed to only the essential text editing shortcuts:
            # - a: select all
            # - c: copy
            # - v: paste
            # - x: cut
            # - z: undo
            # - y: redo
            text_editing_keys = {'a', 'c', 'v', 'x', 'z', 'y'}
            
            # If Ctrl is pressed and the key is a text editing key, don't trigger keybind
            if is_ctrl and keysym in text_editing_keys:
                return  # Let the text widget handle it (None allows propagation)
        
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
            bind_id = info.get('bind_id')
            
            # Use unbind with the specific bind_id to avoid removing third-party bindings
            # This is safer than unbind_all which removes ALL bindings for that key sequence
            if bind_id is not None:
                root.unbind(tk_format, bind_id)
            else:
                # Fallback to unbind_all only if bind_id wasn't stored (legacy compatibility)
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
                bind_id = info.get('bind_id')
                if tk_format:
                    # Use unbind with the specific bind_id to avoid removing third-party bindings
                    if bind_id is not None:
                        root.unbind(tk_format, bind_id)
                    else:
                        # Fallback to unbind_all only if bind_id wasn't stored (legacy compatibility)
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
            # Single alphanumeric key - use lowercase for Tkinter
            # (Tkinter uses lowercase for key names, e.g., <Control-t> not <Control-T>)
            key = key.lower()
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
        
        Delegates to the shared validation utility in keybind_utils to avoid
        code duplication and ensure consistent validation across the application.
        
        Args:
            keybind_string: Keybind to validate
            
        Returns:
            True if valid, False otherwise
        """
        from ..utils.keybind_utils import validate_keybind_format
        
        return validate_keybind_format(keybind_string)
    
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
    
    def is_keyboard_available(self) -> bool:
        """
        Check if the keyboard library is available for global hotkeys.
        
        Returns:
            True if keyboard library is available, False otherwise
        """
        return _keyboard_available
    
    def enable_global_hotkeys(self, enabled: bool = True) -> bool:
        """
        Enable or disable system-wide global hotkeys.
        
        Args:
            enabled: Whether to enable global hotkeys
            
        Returns:
            True if successful, False if keyboard library not available
        """
        if not _keyboard_available:
            if enabled:
                logger.warning("Cannot enable global hotkeys: keyboard library not available")
            return False
        
        self._global_hotkeys_enabled = enabled
        
        if not enabled:
            # Unregister all global hotkeys
            self._unregister_all_global_hotkeys()
        
        return True
    
    def register_global_hotkey(self, keybind_string: str, callback, action_name: str = None) -> bool:
        """
        Register a system-wide global hotkey that works even when the app is not focused.
        
        Args:
            keybind_string: User-friendly keybind format (e.g., "Ctrl+Enter")
            callback: Function to call when hotkey is pressed
            action_name: Optional action name for tracking
            
        Returns:
            True if registration successful, False otherwise
        """
        if not _keyboard_available or not self._global_hotkeys_enabled:
            return False
        
        if not keybind_string or not callback:
            return False
        
        # Convert to keyboard library format
        kb_format = self._parse_to_keyboard_format(keybind_string)
        if not kb_format:
            logger.warning("Failed to parse keybind for global hotkey: %s", keybind_string)
            return False
        
        # Unregister existing if present
        if keybind_string in self._global_hotkeys:
            self.unregister_global_hotkey(keybind_string)
        
        try:
            # Register with keyboard library
            hook = keyboard.add_hotkey(kb_format, callback, suppress=False)
            self._global_hotkeys[keybind_string] = {
                'kb_format': kb_format,
                'callback': callback,
                'hook': hook,
                'action_name': action_name or keybind_string
            }
            logger.debug("Registered global hotkey: %s -> %s", keybind_string, kb_format)
            return True
        except Exception as e:
            logger.error("Failed to register global hotkey '%s': %s", keybind_string, e)
            return False
    
    def unregister_global_hotkey(self, keybind_string: str) -> bool:
        """
        Unregister a specific global hotkey.
        
        Args:
            keybind_string: Hotkey to unregister
            
        Returns:
            True if unregistration successful, False otherwise
        """
        if keybind_string not in self._global_hotkeys:
            return False
        
        try:
            info = self._global_hotkeys[keybind_string]
            keyboard.remove_hotkey(info['hook'])
            del self._global_hotkeys[keybind_string]
            logger.debug("Unregistered global hotkey: %s", keybind_string)
            return True
        except Exception as e:
            logger.error("Failed to unregister global hotkey '%s': %s", keybind_string, e)
            return False
    
    def _unregister_all_global_hotkeys(self):
        """Unregister all global hotkeys."""
        for keybind_string in list(self._global_hotkeys.keys()):
            try:
                info = self._global_hotkeys[keybind_string]
                keyboard.remove_hotkey(info['hook'])
            except Exception:
                pass
        
        self._global_hotkeys.clear()
    
    def _parse_to_keyboard_format(self, keybind_string: str) -> str:
        """
        Convert user-friendly keybind format to keyboard library format.
        
        Args:
            keybind_string: User-friendly format (e.g., "Ctrl+Enter", "Ctrl+Shift+A")
            
        Returns:
            Keyboard library format string (e.g., "ctrl+enter", "ctrl+shift+a")
        """
        if not keybind_string:
            return ""
        
        parts = keybind_string.split('+')
        result_parts = []
        
        for part in parts:
            part = part.strip().lower()
            
            # Map modifiers
            if part in ['ctrl', 'control']:
                result_parts.append('ctrl')
            elif part == 'shift':
                result_parts.append('shift')
            elif part == 'alt':
                result_parts.append('alt')
            elif part in ['win', 'super', 'windows']:
                result_parts.append('windows')
            else:
                # Map special keys - use keyboard library's expected names
                key_mapping = {
                    'enter': 'enter',
                    'return': 'enter',
                    'space': 'space',
                    'escape': 'esc',
                    'esc': 'esc',
                    'tab': 'tab',
                    'backspace': 'backspace',
                    'delete': 'delete',
                    'del': 'delete',
                    'insert': 'insert',
                    'home': 'home',
                    'end': 'end',
                    'pageup': 'page up',
                    'pagedown': 'page down',
                    'up': 'up',
                    'down': 'down',
                    'left': 'left',
                    'right': 'right',
                    # Use keyboard library's key names for symbols
                    'comma': 'comma',
                    'period': 'dot',
                    'slash': 'slash',
                    'semicolon': 'semicolon',
                    'quote': 'quote',
                    'backslash': 'backslash',
                    'bracketleft': 'left bracket',
                    'bracketright': 'right bracket',
                    'minus': 'minus',
                    'equal': 'equal',
                    'grave': 'grave',
                    # Function keys
                    'f1': 'f1', 'f2': 'f2', 'f3': 'f3', 'f4': 'f4',
                    'f5': 'f5', 'f6': 'f6', 'f7': 'f7', 'f8': 'f8',
                    'f9': 'f9', 'f10': 'f10', 'f11': 'f11', 'f12': 'f12',
                    'f13': 'f13', 'f14': 'f14', 'f15': 'f15', 'f16': 'f16',
                    'f17': 'f17', 'f18': 'f18', 'f19': 'f19', 'f20': 'f20',
                }
                
                if part in key_mapping:
                    result_parts.append(key_mapping[part])
                elif len(part) == 1 and part.isalnum():
                    # Single alphanumeric key
                    result_parts.append(part)
                elif part in [',', '.', '/', ';', "'", '\\', '[', ']', '-', '=', '`']:
                    # Already a symbol
                    result_parts.append(part)
                else:
                    # Unknown key - pass through as-is (keyboard library may still recognize it)
                    result_parts.append(part)
        
        return '+'.join(result_parts)
    
    def register_all_global_hotkeys(self, keybinds: Dict[str, Callable]) -> int:
        """
        Register multiple global hotkeys at once.
        
        Args:
            keybinds: Dictionary mapping keybind strings to callbacks
            
        Returns:
            Number of successfully registered hotkeys
        """
        if not _keyboard_available or not self._global_hotkeys_enabled:
            return 0
        
        success_count = 0
        for keybind_string, callback in keybinds.items():
            if self.register_global_hotkey(keybind_string, callback, action_name=keybind_string):
                success_count += 1
        
        return success_count
    
    def get_global_hotkeys_status(self) -> Dict[str, Any]:
        """
        Get status information about global hotkeys.
        
        Returns:
            Dictionary with status information
        """
        return {
            'available': _keyboard_available,
            'enabled': self._global_hotkeys_enabled,
            'registered_count': len(self._global_hotkeys),
            'registered_hotkeys': list(self._global_hotkeys.keys())
        }
