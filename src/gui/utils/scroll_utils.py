"""
Scroll event utilities for handling nested scrollable frames.

This module provides utilities to prevent scroll event hijacking when 
scrollable widgets are nested inside parent scrollable containers.

The problem: When using the mouse wheel inside nested scrollable areas,
the scroll event can inadvertently scroll the outer parent container instead
of, or in addition to, the inner widget.

The solution: Bind mouse wheel events to consume them when the cursor is
over a nested scrollable, preventing propagation to parent handlers.
"""
import customtkinter as ctk
import tkinter as tk
from typing import Optional


def prevent_scroll_propagation(scrollable_frame: ctk.CTkScrollableFrame):
    """
    Bind mouse wheel events to prevent scroll event propagation to parent containers.
    
    This fixes nested scrolling issues where mouse wheel events in inner scrollable
    widgets would inadvertently scroll outer parent containers.
    
    The function binds to the internal canvas of the CTkScrollableFrame and
    returns "break" when the mouse is over the scrollable, which stops event
    propagation to parent widgets.
    
    Args:
        scrollable_frame: The CTkScrollableFrame to protect from event propagation
        
    Example:
        >>> parent_scroll = ctk.CTkScrollableFrame(root)
        >>> nested_scroll = ctk.CTkScrollableFrame(parent_scroll, height=100)
        >>> prevent_scroll_propagation(nested_scroll)
    """
    def on_mousewheel(event):
        """Handle mouse wheel events and consume if over this scrollable."""
        # Get the widget under the cursor using root coordinates
        x = event.x_root
        y = event.y_root
        
        # Find the widget at the cursor position
        try:
            widget = event.widget.winfo_containing(x, y)
        except tk.TclError:
            widget = None
        
        if widget is None:
            return None
        
        # Walk up the widget hierarchy to find if we're inside this scrollable
        current = widget
        while current is not None:
            if current is scrollable_frame:
                # We're inside this scrollable - consume the event
                # Returning "break" stops event propagation
                return "break"
            try:
                current = current.master
            except (tk.TclError, AttributeError):
                break
        
        # Not inside this scrollable - allow propagation
        return None
    
    # Bind to the internal canvas of the CTkScrollableFrame
    # CTkScrollableFrame uses a canvas internally for scrolling
    try:
        canvas = scrollable_frame._canvas
        
        # Windows/macOS use MouseWheel event
        # delta is positive when scrolling up, negative when scrolling down
        canvas.bind("<MouseWheel>", on_mousewheel, add="+")
        
        # Linux uses Button-4 (scroll up) and Button-5 (scroll down)
        canvas.bind("<Button-4>", on_mousewheel, add="+")
        canvas.bind("<Button-5>", on_mousewheel, add="+")
        
        # Also bind to the parent frame for better coverage
        parent_frame = getattr(scrollable_frame, '_parent_frame', None)
        if parent_frame is not None:
            parent_frame.bind("<MouseWheel>", on_mousewheel, add="+")
            parent_frame.bind("<Button-4>", on_mousewheel, add="+")
            parent_frame.bind("<Button-5>", on_mousewheel, add="+")
            
    except AttributeError:
        # CTkScrollableFrame structure may differ in some CustomTkinter versions
        # Try to bind to the frame itself as a fallback
        try:
            scrollable_frame.bind("<MouseWheel>", on_mousewheel, add="+")
            scrollable_frame.bind("<Button-4>", on_mousewheel, add="+")
            scrollable_frame.bind("<Button-5>", on_mousewheel, add="+")
        except tk.TclError:
            pass


def setup_nested_scrollable(
    parent: ctk.CTkScrollableFrame,
    height: Optional[int] = None,
    **kwargs
) -> ctk.CTkScrollableFrame:
    """
    Create a nested scrollable frame with proper event handling.
    
    This is a convenience function that creates a CTkScrollableFrame
    and automatically applies the scroll propagation fix.
    
    Args:
        parent: The parent scrollable frame (or any container)
        height: Optional fixed height for the nested frame
        **kwargs: Additional keyword arguments passed to CTkScrollableFrame
        
    Returns:
        The configured nested scrollable frame with scroll propagation prevented
        
    Example:
        >>> parent_scroll = ctk.CTkScrollableFrame(root)
        >>> nested = setup_nested_scrollable(parent_scroll, height=100)
        >>> nested.pack(fill="x", pady=5)
    """
    if height is not None:
        kwargs["height"] = height
    
    nested = ctk.CTkScrollableFrame(parent, **kwargs)
    prevent_scroll_propagation(nested)
    
    return nested


class NestedScrollableFrame(ctk.CTkScrollableFrame):
    """
    A scrollable frame that properly handles nested scrolling contexts.
    
    This subclass prevents scroll event hijacking when placed inside
    another scrollable container. It automatically binds mouse wheel
    events to consume them when the cursor is over this frame.
    
    Use this class instead of CTkScrollableFrame when you need to
    nest scrollable frames inside other scrollable containers.
    
    Example:
        >>> parent_scroll = ctk.CTkScrollableFrame(root)
        >>> nested = NestedScrollableFrame(parent_scroll, height=100)
        >>> nested.pack(fill="x", pady=5)
        >>> # Mouse wheel events in nested will not scroll parent_scroll
    """
    
    def __init__(self, master, **kwargs):
        """
        Initialize the nested scrollable frame.
        
        Args:
            master: The parent widget
            **kwargs: Additional keyword arguments passed to CTkScrollableFrame
        """
        super().__init__(master, **kwargs)
        self._setup_nested_scroll_handling()
    
    def _setup_nested_scroll_handling(self):
        """Configure event handling for nested scroll contexts."""
        def consume_if_over_self(event):
            """Consume event if mouse is over this scrollable frame."""
            # Get the widget under the cursor using root coordinates
            try:
                widget = event.widget.winfo_containing(event.x_root, event.y_root)
            except tk.TclError:
                return None
            
            if widget is None:
                return None
            
            # Walk up the widget hierarchy
            current = widget
            while current is not None:
                if current is self:
                    # We're inside this scrollable - consume the event
                    return "break"
                try:
                    current = getattr(current, 'master', None)
                except (tk.TclError, AttributeError):
                    break
            
            return None
        
        # Bind to the internal canvas
        try:
            self._canvas.bind("<MouseWheel>", consume_if_over_self, add="+")
            self._canvas.bind("<Button-4>", consume_if_over_self, add="+")
            self._canvas.bind("<Button-5>", consume_if_over_self, add="+")
            
            # Also bind to parent frame for better coverage
            parent_frame = getattr(self, '_parent_frame', None)
            if parent_frame is not None:
                parent_frame.bind("<MouseWheel>", consume_if_over_self, add="+")
                parent_frame.bind("<Button-4>", consume_if_over_self, add="+")
                parent_frame.bind("<Button-5>", consume_if_over_self, add="+")
        except AttributeError:
            # Fallback: bind to self
            self.bind("<MouseWheel>", consume_if_over_self, add="+")
            self.bind("<Button-4>", consume_if_over_self, add="+")
            self.bind("<Button-5>", consume_if_over_self, add="+")
