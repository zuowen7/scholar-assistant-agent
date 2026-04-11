# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Scholar Translate Python backend.

Produces an --onedir bundle at src-tauri/python-dist/api/ containing:
  - api.exe (FastAPI server)
  - All Python dependencies (pdfplumber, fastapi, uvicorn, etc.)
  - config/default.yaml (bundled as read-only template)
"""

import sys
from pathlib import Path

block_cipher = None

python_dir = Path(SPECPATH).parent / "python"

# Anaconda stores DLLs in Library/bin/ — PyInstaller doesn't find them automatically
conda_bin = Path(sys.executable).parent / "Library" / "bin"

# Collect required Anaconda DLLs that PyInstaller may miss
_conda_dlls = []
_dll_names = [
    "libexpat.dll", "liblzma.dll", "LIBBZ2.dll", "ffi.dll",
    "libssl-3-x64.dll", "libcrypto-3-x64.dll",
]
if conda_bin.exists():
    for dll in _dll_names:
        dll_path = conda_bin / dll
        if dll_path.exists():
            _conda_dlls.append((str(dll_path), "."))

a = Analysis(
    [str(python_dir / "api.py")],
    pathex=[str(python_dir)],
    binaries=_conda_dlls,
    datas=[
        (str(python_dir / "config" / "default.yaml"), "config"),
    ],
    hiddenimports=[
        # FastAPI / uvicorn
        "pydantic",
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.lifespan.on",
        "sse_starlette",
        "starlette.routing",
        "starlette.middleware",
        "starlette.responses",
        # PDF / document parsing
        "pdfplumber",
        "httpx",
        # Config / data
        "yaml",
        "charset_normalizer",
        # Document format parsers
        "striprtf",
        "pylatexenc",
        "ebooklib",
        "bs4",
        "openpyxl",
        "pptx",
        "docx",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Remove heavy unused packages that Anaconda pulls in
        "tkinter",
        "matplotlib",
        "numpy.f2py",
        "scipy",
        "pandas",
        "IPython",
        "notebook",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "sphinx",
        "jupyter",
        "tornado",
        "zmq",
        "psutil",
        "PIL",
        "sqlalchemy",
        "bokeh",
        "plotly",
        "sklearn",
        "scikit-learn",
        "win32com",
        "pythoncom",
        "pywin32",
        "win32ui",
        "win32api",
        "win32con",
        "win32evtlog",
        "win32pdh",
        "win32process",
        "win32profile",
        "win32security",
        "win32service",
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
    [],
    exclude_binaries=True,
    name="api",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="api",
)
