# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Scholar Assistant Python backend.

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
        (str(python_dir / "config" / "docker.yaml"), "config"),
        # Pandoc 模板目录（包含 generic.tex 等期刊模板）
        (str(python_dir / "pandoc_templates"), "pandoc_templates"),
        # 论文模板素材库（模板源码 + Markdown/LaTeX/Text 范例）
        (str(python_dir / "data" / "paper_assets"), "data/paper_assets"),
        # 翻译术语表
        (str(python_dir / "data" / "translator" / "glossaries"), "data/translator/glossaries"),
        (str(python_dir / "prompts"), "prompts"),
        # 插件目录（打包为空目录，保证 discover_plugins 不报错）
        (str(python_dir / "plugins"), "plugins"),
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
        # ChromaDB (Agent/RAG memory)
        "chromadb",
        "chromadb.api",
        "chromadb.api.types",
        "chromadb.api.client",
        "chromadb.config",
        "chromadb.utils",
        "chromadb.utils.batch_utils",
        "chromadb.utils.messageid_router",
        "chromadb.utils.ranking_utils",
        "chromadb.api.rust",
        "chromadb.telemetry.product.posthog",
        "hnswlib",
        # Agent core
        "src.agent.agent",
        "src.agent.models",
        "src.agent.memory",
        "src.agent.rag",
        "src.agent.tools",
        "src.agent.tools.core",
        "src.agent.tools.atomic_tools",
        "src.agent.tools.builtin_tools",
        "src.agent.tools.workspace_tools",
        # Agent subsystems
        "src.agent.auto_processor",
        "src.agent.prompt_builder",
        "src.agent.session",
        "src.agent.session_store",
        "src.agent.skill_system",
        "src.agent.trajectory",
        "src.agent.workspace",
        "src.agent.change_journal",
        "src.agent.error_classifier",
        "src.agent.hooks",
        "src.agent.security_gate",
        "src.agent.task_queue",
        "src.agent.special_elements",
        "src.agent.review_agent",
        # Agent internal submodules
        "src.agent._elements_parser",
        "src.agent._elements_tools",
        "src.agent._elements_types",
        "src.agent._elements_vision",
        "src.agent._llm_anthropic",
        "src.agent._llm_helpers",
        "src.agent._llm_ollama",
        "src.agent._llm_openai",
        # Translator pipeline
        "src.translator.parallel_runner",
        "src.translator.memory_store",
        "src.translator.glossary_store",
        "src.translator._helpers",
        "src.translator.context",
        # Parser / cleaner / chunker / formatter
        "src.parser.extractor",
        "src.parser.dispatcher",
        "src.cleaner",
        "src.cleaner.pipeline",
        "src.chunker",
        "src.chunker.splitter",
        "src.chunker.syntax_splitter",
        "src.formatter.renderer",
        "src.formatter.word_exporter",
        # Citation / Zotero / MCP
        "src.citation",
        "src.citation.indexer",
        "src.zotero",
        "src.zotero.client",
        "src.mcp",
        "src.mcp.vision_client",
        # Argument system
        "src.argument.models",
        "src.argument.store",
        "src.argument.logic_checker",
        "src.argument.expander",
        "src.argument.observer",
        "src.argument.feedback_generator",
        "src.argument.flatten",
        # Plugin system
        "src.plugin",
        "src.plugin.loader",
        "src.plugin.registry",
        "src.plugin.builtin",
        # Optional OCR (inside try/except, invisible to static analysis)
        "pytesseract",
        "pdf2image",
        "paddleocr",
        # Optional async HTTP
        "aiohttp",
        # Runtime endpoint helpers imported by api_factory routes
        "paper_assets",
        "pandoc_templates",
        # Prompts
        "prompts.loader",
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