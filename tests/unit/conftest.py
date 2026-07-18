"""Shared test stubs for CustomTkinter to avoid headless Tcl/Tk errors.

Imported automatically by pytest via conftest discovery. Sets up
``sys.modules['customtkinter']`` once before any test module runs.
"""

from __future__ import annotations

import sys
import tkinter as tk
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Stub Tkinter Variables (prevents 'no default root window' errors)
# ---------------------------------------------------------------------------

class DummyVar:
    def __init__(self, master=None, value=None, name=None) -> None:
        self._value = value

    def get(self) -> Any:
        return self._value

    def set(self, val: Any) -> None:
        self._value = val

# Expose Any for typing in stubs
from typing import Any

tk.StringVar = DummyVar  # type: ignore[misc]
tk.BooleanVar = DummyVar  # type: ignore[misc]
tk.IntVar = DummyVar  # type: ignore[misc]
tk.DoubleVar = DummyVar  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Stub widget classes
# ---------------------------------------------------------------------------

class _W:
    """Minimal widget stub covering every method used by MainWindow."""

    _content: str = ""

    def __init__(self, *a, **kw) -> None:
        self._state = kw.get("state", "normal")

    # Geometry / layout
    def grid(self, *a, **kw) -> None: pass
    def grid_remove(self, *a, **kw) -> None: pass
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
    def configure(self, *a, **kw) -> None:
        if "state" in kw:
            self._state = kw["state"]

    def cget(self, attr: str) -> Any:
        if attr == "state":
            return self._state
        return None
    def after(self, ms, func=None, *a): return "after#stub"
    def after_cancel(self, id_) -> None: pass
    def resizable(self, *a, **kw) -> None: pass
    def transient(self, *a, **kw) -> None: pass
    def grab_set(self, *a, **kw) -> None: pass
    def focus_set(self, *a, **kw) -> None: pass

    # Textbox extras
    def get(self, *a) -> str: return self._content
    def delete(self, *a) -> None: self._content = ""
    def insert(self, pos, text) -> None: self._content += text
    def see(self, *a) -> None: pass

    # ProgressBar extras
    def set(self, v) -> None: pass


class _Tabview(_W):
    def add(self, name: str) -> None: pass
    def tab(self, name: str) -> _W: return _W()


class _Font:
    def __init__(self, *a, **kw) -> None: pass


# ---------------------------------------------------------------------------
# Install mock module
# ---------------------------------------------------------------------------

def _install() -> None:
    mock_ctk = MagicMock()
    mock_ctk.CTk = _W
    mock_ctk.CTkToplevel = _W
    mock_ctk.CTkFrame = _W
    mock_ctk.CTkLabel = _W
    mock_ctk.CTkScrollableFrame = _W
    mock_ctk.CTkFont = _Font
    mock_ctk.CTkProgressBar = _W
    mock_ctk.CTkButton = _W
    mock_ctk.CTkTextbox = _W
    mock_ctk.CTkTabview = _Tabview
    mock_ctk.CTkOptionMenu = _W
    mock_ctk.CTkEntry = _W
    mock_ctk.CTkComboBox = _W
    mock_ctk.CTkCheckBox = _W
    mock_ctk.set_appearance_mode = MagicMock()
    mock_ctk.set_default_color_theme = MagicMock()
    sys.modules["customtkinter"] = mock_ctk


_install()
