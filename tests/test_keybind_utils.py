import pytest
from src.utils.keybind_utils import validate_keybind_format, parse_keybind_to_tkinter

def test_validate_keybind_format_valid_single_keys():
    assert validate_keybind_format("a") is True
    assert validate_keybind_format("1") is True
    assert validate_keybind_format("Enter") is True
    assert validate_keybind_format("space") is True
    assert validate_keybind_format("F1") is True
    assert validate_keybind_format("comma") is True

def test_validate_keybind_format_valid_combinations():
    assert validate_keybind_format("Ctrl+A") is True
    assert validate_keybind_format("Ctrl+Shift+Enter") is True
    assert validate_keybind_format("Alt+Space") is True
    assert validate_keybind_format("ctrl + shift + b") is True  # Should handle spaces around +

def test_validate_keybind_format_invalid_formats():
    assert validate_keybind_format("") is False
    assert validate_keybind_format(None) is False
    assert validate_keybind_format("   ") is False
    assert validate_keybind_format("Ctrl+") is False
    assert validate_keybind_format("Ctrl") is False
    assert validate_keybind_format("Shift+Alt") is False
    assert validate_keybind_format("Ctrl+Ctrl+A") is False
    assert validate_keybind_format("UnknownKey") is False
    assert validate_keybind_format("A" * 51) is False

def test_validate_keybind_format_critical_shortcuts():
    assert validate_keybind_format("Alt+F4") is False
    assert validate_keybind_format("Ctrl+Alt+Delete") is False
    assert validate_keybind_format("Win+L") is False

def test_parse_keybind_to_tkinter_basic():
    assert parse_keybind_to_tkinter("a") == "<a>"
    assert parse_keybind_to_tkinter("A") == "<a>"
    assert parse_keybind_to_tkinter("Enter") == "<Return>"
    assert parse_keybind_to_tkinter("Ctrl+A") == "<Control-a>"
    assert parse_keybind_to_tkinter("Ctrl+Shift+B") == "<Control-Shift-b>"
    assert parse_keybind_to_tkinter("Alt+Enter") == "<Alt-Return>"

def test_parse_keybind_to_tkinter_special_keys():
    assert parse_keybind_to_tkinter("space") == "<space>"
    assert parse_keybind_to_tkinter("backspace") == "<BackSpace>"
    assert parse_keybind_to_tkinter("f1") == "<F1>"
    assert parse_keybind_to_tkinter("comma") == "<comma>"

def test_parse_keybind_to_tkinter_invalid():
    assert parse_keybind_to_tkinter("") is None
    assert parse_keybind_to_tkinter("Ctrl+") is None
    assert parse_keybind_to_tkinter("UnknownKey") is None

def test_win_modifier():
    assert validate_keybind_format("Win+S") is True
    assert parse_keybind_to_tkinter("Win+S") == "<Mod4-s>"

def test_missing_symbols():
    assert validate_keybind_format("plus") is True
    assert parse_keybind_to_tkinter("plus") == "<plus>"
    assert validate_keybind_format("Ctrl+plus") is True
    assert parse_keybind_to_tkinter("Ctrl+plus") == "<Control-plus>"
