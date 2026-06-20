"""Shared fixtures for headless GUI tests.

Provides a single withdrawn customtkinter root for the whole test session so
widget-constructing tests never pop a window and never pay for repeated root
creation. Tests must NOT call mainloop().
"""
import sys
import os
import pytest
import customtkinter as ctk

# Ensure the project root (parent of tests/) is importable so `import src...` works.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture(scope="session")
def ctk_root():
    """A session-scoped, withdrawn CTk root. Destroyed once at session end."""
    root = ctk.CTk()
    root.withdraw()  # never show a window during tests
    yield root
    try:
        root.destroy()
    except Exception:
        pass
