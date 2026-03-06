"""
GUI Utilities Module
Utility functions and classes for GUI components.
"""
from .scroll_utils import prevent_scroll_propagation, setup_nested_scrollable, NestedScrollableFrame

__all__ = [
    "prevent_scroll_propagation",
    "setup_nested_scrollable",
    "NestedScrollableFrame",
]
