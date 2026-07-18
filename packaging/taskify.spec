# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Locate customtkinter package installation path programmatically
import customtkinter
customtkinter_path = os.path.dirname(customtkinter.__file__)

# Collect taskify assets (default configurations, schemas, sql scripts)
taskify_datas = collect_data_files("taskify")

# Aggregate all data files to bundle inside the executable
datas = taskify_datas + [
    (customtkinter_path, "customtkinter")
]

# Ensure dynamic imports are collected by PyInstaller
hiddenimports = collect_submodules("taskify") + [
    "sounddevice",
    "soundfile",
    "numpy",
    "vosk",
    "click",
    "customtkinter",
]

# Resolve script entrypoint relative to workspace root
entrypoint = os.path.abspath(
    os.path.join(os.path.dirname("__file__"), "src", "taskify", "__main__.py")
)

a = Analysis(
    [entrypoint],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "torch",
        "tensorflow",
        "scipy",
        "pandas",
        "matplotlib",
        "pygame",
        "moviepy",
        "sklearn",
        "lxml",
        "nltk",
        "pyarrow",
        "numba",
        "llvmlite",
        "openpyxl",
        "yt_dlp",
        "IPython",
        "jedi",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="taskify",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Standard console is required for Click CLI commands output
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
