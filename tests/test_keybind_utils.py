import pytest
from src.utils.keybind_utils import parse_keybind_to_tkinter

class TestParseKeybindToTkinter:
    """Test suite for parse_keybind_to_tkinter function."""

    @pytest.mark.parametrize(
        "keybind_string, expected",
        [
            # --- Happy Paths: Standard Keys ---
            ("a", "<a>"),
            ("A", "<a>"),  # Capital letter should be lowercased
            ("1", "<1>"),

            # --- Happy Paths: Single Modifiers ---
            ("Ctrl+a", "<Control-a>"),
            ("Control+a", "<Control-a>"),
            ("Shift+a", "<Shift-a>"),
            ("Alt+a", "<Alt-a>"),
            ("Win+a", "<Mod4-a>"),
            ("Super+a", "<Mod4-a>"),

            # --- Happy Paths: Multiple Modifiers ---
            ("Ctrl+Shift+a", "<Control-Shift-a>"),
            ("Ctrl+Alt+a", "<Control-Alt-a>"),
            ("Ctrl+Shift+Alt+a", "<Control-Shift-Alt-a>"),
            ("Win+Shift+a", "<Mod4-Shift-a>"),

            # --- Happy Paths: Special Keys ---
            ("Enter", "<Return>"),
            ("Return", "<Return>"),
            ("Space", "<space>"),
            ("Esc", "<Escape>"),
            ("Escape", "<Escape>"),
            ("Tab", "<Tab>"),
            ("Backspace", "<BackSpace>"),
            ("Del", "<Delete>"),
            ("Delete", "<Delete>"),
            ("Insert", "<Insert>"),
            ("Home", "<Home>"),
            ("End", "<End>"),
            ("PageUp", "<Prior>"),
            ("PageDown", "<Next>"),
            ("Up", "<Up>"),
            ("Down", "<Down>"),
            ("Left", "<Left>"),
            ("Right", "<Right>"),
            ("F1", "<F1>"),
            ("F12", "<F12>"),
            ("Comma", "<comma>"),
            ("Period", "<period>"),
            ("Slash", "<slash>"),
            ("Semicolon", "<semicolon>"),
            ("Quote", "<quoteright>"),
            ("Backslash", "<backslash>"),
            ("BracketLeft", "<bracketleft>"),
            ("BracketRight", "<bracketright>"),
            ("Minus", "<minus>"),
            ("Equal", "<equal>"),
            ("Grave", "<grave>"),

            # --- Happy Paths: Modifiers + Special Keys ---
            ("Ctrl+Enter", "<Control-Return>"),
            ("Shift+Space", "<Shift-space>"),
            ("Alt+F4", "<Alt-F4>"),

            # --- Edge Cases: Extra spaces and mixed casing ---
            (" ctrl + a ", "<Control-a>"),
            ("cTrL+A", "<Control-a>"),
            ("  Shift  +  Enter  ", "<Shift-Return>"),
            ("wIn+aLt+dEl", "<Mod4-Alt-Delete>"),
        ]
    )
    def test_valid_keybinds(self, keybind_string, expected):
        """Test valid keybind strings map correctly to Tkinter format."""
        assert parse_keybind_to_tkinter(keybind_string) == expected

    @pytest.mark.parametrize(
        "keybind_string, expected",
        [
            # --- Error Conditions: Empty strings ---
            ("", None),
            (None, None),

            # --- Error Conditions: Invalid syntax ---
            ("Ctrl+", None),  # Missing key
            ("Ctrl++", None), # Extra plus (empty part)

            # --- Error Conditions: Modifiers only ---
            ("Ctrl", None),
            ("Ctrl+Shift", None),

            # --- Error Conditions: Unsupported/unknown keys ---
            ("Ctrl+UnknownKey", None),
            ("Ctrl+@#$", None),
            ("UnrecognizedKey", None),
        ]
    )
    def test_invalid_keybinds(self, keybind_string, expected):
        """Test invalid keybind strings return None."""
        assert parse_keybind_to_tkinter(keybind_string) == expected
