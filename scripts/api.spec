# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Scholar Assistant Python backend.

Produces an --onedir bundle at src-tauri/python-dist/api/ containing:
  - api.exe (FastAPI server)
  - All Python dependencies (pdfplumber, fastapi, uvicorn, etc.)
  - config/default.yaml (bundled as read-only template)
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, collect_all

block_cipher = None

python_dir = Path(SPECPATH).parent / "python"

# Make first-party packages importable during spec evaluation so the
# collect_* helpers below can introspect them.
sys.path.insert(0, str(python_dir))

# ── Auto-collect first-party modules ───────────────────────────────────
# Many src.* subsystems are imported dynamically (delayed imports in api.py,
# features.py __import__ gates, plugin discovery), so PyInstaller's static
# analysis misses them. Enumerate the whole package automatically instead of
# maintaining a hand-written list that silently rots when modules are renamed.
_src_hidden = collect_submodules("src")
# Top-level helper packages bundled as data but imported by name at runtime.
_src_hidden += ["prompts", "prompts.loader", "paper_assets", "pandoc_templates"]

# ── Auto-collect heavy third-party packages ────────────────────────────
# chromadb / onnxruntime / tokenizers ship dynamic submodules + data files
# (migrations, ONNX runtime libs, embedding model assets) that static analysis
# under-collects. collect_all grabs submodules + datas + binaries together.
# Guarded so a clean env without an optional package doesn't fail the build.
_extra_datas = []
_extra_binaries = []
for _pkg in ("chromadb", "onnxruntime", "tokenizers", "zstandard"):
    try:
        _d, _b, _h = collect_all(_pkg)
        _extra_datas += _d
        _extra_binaries += _b
        _src_hidden += _h
    except Exception as _e:  # pragma: no cover - build-time only
        print(f"[api.spec] optional package '{_pkg}' not collected: {_e}")

# Anaconda stores DLLs in Library/bin/ — PyInstaller doesn't find them automatically
conda_bin = Path(sys.executable).parent / "Library" / "bin"

# Collect required Anaconda DLLs that PyInstaller may miss
_conda_dlls = []
_dll_names = [
    "libexpat.dll", "liblzma.dll", "LIBBZ2.dll", "ffi.dll",
    "libssl-3-x64.dll", "libcrypto-3-x64.dll",
    # MSVC runtime — bundle explicitly so api.exe + onnxruntime/pydantic-core/
    # tokenizers start on machines without the VC++ 2015-2022 redistributable.
    "vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll",
]
if conda_bin.exists():
    for dll in _dll_names:
        dll_path = conda_bin / dll
        if dll_path.exists():
            _conda_dlls.append((str(dll_path), "."))

a = Analysis(
    [str(python_dir / "api.py")],
    pathex=[str(python_dir)],
    binaries=_conda_dlls + _extra_binaries,
    datas=_extra_datas + [
        # 用根目录 config/default.yaml（源头）而非 python/config/（运行时副本），
        # 防止两者漂移导致打包版和开发版行为不一致。
        (str(python_dir.parent / "config" / "default.yaml"), "config"),
        (str(python_dir / "config" / "docker.yaml"), "config"),
        # 云端供应商预设（providers.yaml 位于仓库根 config/，运行时由 cloud_client 读取）
        (str(python_dir.parent / "config" / "providers.yaml"), "config"),
        # Pandoc 模板目录（包含 generic.tex 等期刊模板）
        (str(python_dir / "pandoc_templates"), "pandoc_templates"),
        # 论文模板素材库（模板源码 + Markdown/LaTeX/Text 范例）
        (str(python_dir / "data" / "paper_assets"), "data/paper_assets"),
        # 翻译术语表
        (str(python_dir / "data" / "translator" / "glossaries"), "data/translator/glossaries"),
        # Agent V2 内置 skills + plugins
        (str(python_dir / "data" / "agent_v2" / "skills"), "data/agent_v2/skills"),
        (str(python_dir / "data" / "agent_v2" / "plugins"), "data/agent_v2/plugins"),
        (str(python_dir / "prompts"), "prompts"),
        # 项目模板定义（project_templates.json）
        (str(python_dir / "templates"), "templates"),
    ] + ([
        # 插件目录（空目录不追踪到 git，CI 可能不存在）
        (str(python_dir / "plugins"), "plugins"),
    ] if (python_dir / "plugins").exists() else []),
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
        "fitz",
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
        # Optional OCR (inside try/except, invisible to static analysis)
        "pytesseract",
        "pdf2image",
        "paddleocr",
        # Optional async HTTP
        "aiohttp",
        # First-party src.* + helpers + chromadb/onnxruntime/tokenizers are
        # appended below via collect_submodules / collect_all (see top of spec).
    ] + _src_hidden,
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
    console=False,
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