"""Shared test stubs for CustomTkinter to avoid headless Tcl/Tk errors.

Imported automatically by pytest via conftest discovery. Sets up
``sys.modules['customtkinter']`` once before any test module runs.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Stub widget classes
# ---------------------------------------------------------------------------

class _W:
    """Minimal widget stub covering every method used by MainWindow."""

    _content: str = ""

    def __init__(self, *a, **kw) -> None:
        pass

    # Geometry / layout
    def grid(self, *a, **kw) -> None: pass
    def grid_propagate(self, *a, **kw) -> None: pass
    def pack(self, *a, **kw) -> None: pass
    def winfo_children(self): return []
    def grid_rowconfigure(self, *a, **kw) -> None: pass
    def grid_columnconfigure(self, *a, **kw) -> None: pass

    # Event / window
    def bind(self, *a, **kw) -> None: pass
    def destroy(self, *a, **kw) -> None: pass

    # Tk root methods (needed for CTk / MainWindow base)
    def title(self, *a, **kw) -> None: pass
    def geometry(self, *a, **kw) -> None: pass
    def minsize(self, *a, **kw) -> None: pass
    def configure(self, *a, **kw) -> None: pass
    def after(self, ms, func=None, *a): return "after#stub"
    def after_cancel(self, id_) -> None: pass

    # Textbox extras
    def get(self, *a) -> str: return self._content
    def delete(self, *a) -> None: self._content = ""
    def insert(self, pos, text) -> None: self._content += text
    def see(self, *a) -> None: pass

    # ProgressBar extras
    def set(self, v) -> None: pass


class _Font:
    def __init__(self, *a, **kw) -> None: pass


# ---------------------------------------------------------------------------
# Install mock module
# ---------------------------------------------------------------------------

def _install() -> None:
    mock_ctk = MagicMock()
    mock_ctk.CTk = _W
    mock_ctk.CTkFrame = _W
    mock_ctk.CTkLabel = _W
    mock_ctk.CTkScrollableFrame = _W
    mock_ctk.CTkFont = _Font
    mock_ctk.CTkProgressBar = _W
    mock_ctk.CTkButton = _W
    mock_ctk.CTkTextbox = _W
    mock_ctk.set_appearance_mode = MagicMock()
    mock_ctk.set_default_color_theme = MagicMock()
    sys.modules["customtkinter"] = mock_ctk


_install()
