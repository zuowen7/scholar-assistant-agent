"""Pandoc md → LaTeX 转换模块 + Tectonic PDF 编译。

设计原则：
- md → .tex 导出（需要 Pandoc）
- .tex → .pdf 编译（需要 Tectonic，可选）
- 支持多模板选择（IEEE, ACM, Springer LNCS, Elsevier, 通用）
- 工具未安装时给出友好错误提示，不崩溃
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Literal

import logging

logger = logging.getLogger(__name__)

# 模板目录
TEMPLATE_DIR = Path(__file__).parent
REGISTRY_PATH = TEMPLATE_DIR / "registry.json"

# Pandoc 安装检测
PANDOC_CMD: str | None = None


def _find_pandoc() -> str | None:
    """查找系统 Pandoc 可执行文件路径。"""
    global PANDOC_CMD
    if PANDOC_CMD is not None:
        return PANDOC_CMD

    import sys
    import os

    # 常见路径（Windows）
    candidates = ["pandoc"]
    if shutil.which("pandoc"):
        PANDOC_CMD = "pandoc"
        return PANDOC_CMD

    # Windows 常见安装位置
    program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
    for pf in [program_files, pf86]:
        for suffix in ["", "\\Pandoc", "\\pandoc"]:
            path = Path(pf) / suffix / "pandoc.exe"
            if path.exists():
                PANDOC_CMD = str(path)
                return PANDOC_CMD

    # 应用自管目录（解压到 LOCALAPPDATA/ScholarTranslate/tools/）
    local_app = os.environ.get("LOCALAPPDATA", "")
    if local_app:
        for subdir in ["ScholarTranslate/tools", "ScholarTranslate/tools/pandoc-3.6.2"]:
            path = Path(local_app) / subdir / "pandoc.exe"
            if path.exists():
                PANDOC_CMD = str(path)
                return PANDOC_CMD

    # PyInstaller 打包后的资源目录（tauri.conf.json resources/pandoc）
    # api.exe 在 python-dist/api/，资源在 python-dist/resources/pandoc/
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        exe_dir = Path(sys.executable).parent
        # 资源在 python-dist/resources/pandoc/，从 api.exe 位置需要 ../../
        for rel in ["../resources/pandoc", "../../resources/pandoc"]:
            bundled_pandoc = exe_dir / rel / "pandoc.exe"
            if bundled_pandoc.exists():
                PANDOC_CMD = str(bundled_pandoc)
                return PANDOC_CMD

    return None


def _load_registry() -> dict:
    """加载期刊模板注册表。"""
    if REGISTRY_PATH.exists():
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"templates": []}


def get_templates() -> list[dict]:
    """返回可用模板列表。"""
    return _load_registry().get("templates", [])


def is_pandoc_available() -> bool:
    """检测 Pandoc 是否已安装。"""
    return _find_pandoc() is not None


def pandoc_version() -> str:
    """返回 Pandoc 版本号，如果未安装返回空字符串。"""
    cmd = _find_pandoc()
    if not cmd:
        return ""
    try:
        result = subprocess.run(
            [cmd, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        first_line = result.stdout.strip().split("\n")[0]
        return first_line
    except Exception:
        return ""


class PandocError(Exception):
    """Pandoc 转换错误。"""
    pass


# ── Tectonic PDF 编译 ──────────────────────────────────────────────

TECTONIC_CMD: str | None = None


def _find_tectonic() -> str | None:
    """查找 Tectonic 可执行文件。"""
    global TECTONIC_CMD
    if TECTONIC_CMD is not None:
        return TECTONIC_CMD if TECTONIC_CMD != "__not_found__" else None

    # 1. 系统 PATH
    if shutil.which("tectonic"):
        TECTONIC_CMD = "tectonic"
        return TECTONIC_CMD

    # 2. 应用自管目录
    import os
    import sys
    local_app = os.environ.get("LOCALAPPDATA", "")
    if local_app:
        app_tectonic = Path(local_app) / "ScholarTranslate" / "tools" / "tectonic.exe"
        if app_tectonic.exists():
            TECTONIC_CMD = str(app_tectonic)
            return TECTONIC_CMD

    # 2b. 打包目录中的 Tectonic（与 api.exe 同目录的 tools/ 子目录）
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        exe_dir = Path(sys.executable).parent
        bundled_tectonic = exe_dir / "tools" / "tectonic.exe"
        if bundled_tectonic.exists():
            TECTONIC_CMD = str(bundled_tectonic)
            return TECTONIC_CMD

    # 3. Program Files
    program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
    for pf in [program_files, pf86]:
        path = Path(pf) / "Tectonic" / "tectonic.exe"
        if path.exists():
            TECTONIC_CMD = str(path)
            return TECTONIC_CMD

    # 4. 常见安装路径（Windows Scoop/官方安装器）
    if local_app:
        for subdir in [
            "Programs/Tectonic",
            "Programs/TectonicPortable",
            "ScholarTranslate/tools/Tectonic",
        ]:
            path = Path(local_app) / subdir / "tectonic.exe"
            if path.exists():
                TECTONIC_CMD = str(path)
                return TECTONIC_CMD

    TECTONIC_CMD = "__not_found__"
    return None


def tectonic_available() -> bool:
    """检测 Tectonic 是否已安装。"""
    return _find_tectonic() is not None


def tectonic_version() -> str:
    """返回 Tectonic 版本号，如果未安装返回空字符串。"""
    cmd = _find_tectonic()
    if not cmd:
        return ""
    try:
        result = subprocess.run(
            [cmd, "--version"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip().split("\n")[0]
    except Exception:
        return ""


def compile_pdf(tex_source: str, output_dir: str | None = None) -> dict:
    """将 LaTeX 源码编译为 PDF。

    Args:
        tex_source: LaTeX 源码内容。
        output_dir: 输出目录，默认使用临时目录。

    Returns:
        {"success": bool, "pdf_path": str, "error": str}
    """
    cmd = _find_tectonic()
    if not cmd:
        return {
            "success": False,
            "pdf_path": "",
            "error": "未找到 Tectonic。请安装：https://github.com/typst/tectonic/releases",
        }

    import tempfile
    out_dir = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="tectonic_"))
    out_dir.mkdir(parents=True, exist_ok=True)

    tex_path = out_dir / "input.tex"
    pdf_path = out_dir / "input.pdf"

    import os
    import sys

    try:
        tex_path.write_text(tex_source, encoding="utf-8")
    except Exception as e:
        return {"success": False, "pdf_path": "", "error": f"写入 .tex 失败: {e}"}

    # Fix Fontconfig on Windows: provide a fonts.conf pointing to system fonts
    env = os.environ.copy()
    if sys.platform == "win32":
        windir = os.environ.get("WINDIR", "C:\\Windows")
        fonts_dir = os.path.join(windir, "Fonts")
        cache_dir = os.path.join(tempfile.gettempdir(), "tectonic_fontcache")
        os.makedirs(cache_dir, exist_ok=True)
        fonts_conf = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">\n'
            '<fontconfig>\n'
            f'  <dir>{fonts_dir}</dir>\n'
            f'  <cachedir>{cache_dir}</cachedir>\n'
            '</fontconfig>'
        )
        conf_path = out_dir / "fonts.conf"
        conf_path.write_text(fonts_conf, encoding="utf-8")
        env["FONTCONFIG_FILE"] = str(conf_path)

    try:
        result = subprocess.run(
            [cmd, "-X", "compile", str(tex_path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120, cwd=str(out_dir), env=env,
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "pdf_path": "", "error": "Tectonic 编译超时（120秒）"}
    except Exception as e:
        return {"success": False, "pdf_path": "", "error": f"编译异常: {e}"}

    if result.returncode != 0:
        error_msg = (result.stderr or "").strip() or (result.stdout or "").strip() or "编译失败"
        # 保留完整错误信息方便排查，截断到 2000 字符
        logger.error("Tectonic compile failed:\n%s", error_msg[:2000])
        return {"success": False, "pdf_path": "", "error": f"Tectonic: {error_msg[:1500]}"}

    if not pdf_path.exists():
        return {"success": False, "pdf_path": "", "error": "编译成功但未生成 PDF 文件"}

    logger.info("PDF 编译成功: %s", pdf_path)
    return {"success": True, "pdf_path": str(pdf_path), "error": ""}


def _escape_latex(text: str) -> str:
    """转义 LaTeX 特殊字符。"""
    escapes = [
        ("\\", "\\textbackslash{}"),
        ("{", "\\{"),
        ("}", "\\}"),
        ("#", "\\#"),
        ("$", "\\$"),
        ("%", "\\%"),
        ("&", "\\&"),
        ("_", "\\_"),
        ("^", "\\textasciicircum{}"),
        ("~", "\\textasciitilde{}"),
        ("<", "\\textless{}"),
        (">", "\\textgreater{}"),
    ]
    for old, new in escapes:
        text = text.replace(old, new)
    return text


def _unescape_latex(text: str) -> str:
    """还原 LaTeX 转义（用于代码块等不需要转义的内容）。"""
    unescapes = [
        ("\\textbackslash{}", "\\\\"),
        ("\\{", "{"),
        ("\\}", "}"),
        ("\\#", "#"),
        ("\\$", "$"),
        ("\\%", "%"),
        ("\\&", "&"),
        ("\\_", "_"),
        ("\\textasciicircum{}", "^"),
        ("\\textasciitilde{}", "~"),
        ("\\textless{}", "<"),
        ("\\textgreater{}", ">"),
    ]
    for old, new in unescapes:
        text = text.replace(old, new)
    return text


def markdown_to_latex(markdown_text: str, metadata: dict | None = None) -> dict:
    """纯 Python Markdown → LaTeX 转换器，不依赖 Pandoc。

    支持：标题、加粗、斜体、行内代码、代码块、链接、图片、
    有序/无序列表、引用块、分割线、公式（$$...$$ 和 $...$）、
    表格（简易）、脚注。
    """
    import re

    meta = metadata or {}
    tex = markdown_text

    # ── 保护：代码块（```...``` 或 ~~~...~~~）─────────────────────
    code_blocks: list[str] = []

    def _protect_code(m):
        idx = len(code_blocks)
        lang = m.group(1) or ""
        content = m.group(2)
        # 还原之前转义的字符，但代码块内容保持原始
        code_blocks.append(f"\\begin{{verbatim}}\n{content}\\end{{verbatim}}")
        return f"__CODEBLOCK_{idx}__"

    tex = re.sub(
        r"```(\w*)\n(.*?)```",
        _protect_code,
        tex,
        flags=re.DOTALL,
    )
    tex = re.sub(
        r"~~~\n(.*?)~~~",
        _protect_code,
        tex,
        flags=re.DOTALL,
    )

    # ── 保护：行内代码（`...`）───────────────────────────────────
    inline_codes: list[str] = []

    def _protect_inline_code(m):
        idx = len(inline_codes)
        raw = m.group(1)
        # 还原代码块内的转义，再重新转义（避免对反斜括号二次转义）
        restored = _unescape_latex(raw)
        escaped = _escape_latex(restored)
        inline_codes.append(f"\\texttt{{{escaped}}}")
        return f"__INLINECODE_{idx}__"

    tex = re.sub(r"`([^`]+)`", _protect_inline_code, tex)

    # ── 数学公式：$$...$$ → \[...\]，$...$ → \(...\) ─────────────
    math_display: list[str] = []

    def _protect_display_math(m):
        idx = len(math_display)
        math_display.append(m.group(1))
        return f"__MATH_DISPLAY_{idx}__"

    tex = re.sub(r"\$\$([\s\S]+?)\$\$", _protect_display_math, tex)
    tex = re.sub(r"\\\[([\s\S]+?)\\\]", _protect_display_math, tex)

    math_inline: list[str] = []

    def _protect_inline_math(m):
        idx = len(math_inline)
        math_inline.append(m.group(1))
        return f"__MATH_INLINE_{idx}__"

    tex = re.sub(r"(?<!\$)\$(?!\$)(.+?)\$(?!\$)", _protect_inline_math, tex)

    # ── 链接和图片 ──────────────────────────────────────────────
    tex = re.sub(
        r"!\[([^\]]*)\]\([^\)]+\)",
        r"\\begin{figure}\\centering\\includegraphics[width=0.8\\textwidth]{img}\\caption{\1}\\end{figure}",
        tex,
    )
    tex = re.sub(
        r"\[([^\]]+)\]\(([^\)]+)\)",
        r"\\href{" + r"\\2" + r"}{\\1}",
        tex,
    )

    # ── 标题 ───────────────────────────────────────────────────
    def _header(m):
        level = len(m.group(1))
        text = m.group(2).strip()
        # 加粗的标题内容先还原
        text = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", text)
        text = re.sub(r"__(.+?)__", r"\\textbf{\1}", text)
        # 斜体
        text = re.sub(r"\*(.+?)\*", r"\\textit{\1}", text)
        text = re.sub(r"_(.+?)_", r"\\textit{\1}", text)
        if level == 1:
            return f"\\section{{{text}}}"
        elif level == 2:
            return f"\\subsection{{{text}}}"
        elif level == 3:
            return f"\\subsubsection{{{text}}}"
        elif level == 4:
            return r"\paragraph{" + text + "}"
        else:
            return r"\subparagraph{" + text + "}"

    tex = re.sub(r"^(#{1,6})\s+(.+)$", _header, tex, flags=re.MULTILINE)

    # ── 引用块 ─────────────────────────────────────────────────
    def _blockquote(m):
        lines = m.group(1).strip().split("\n")
        result = ["\\begin{quotation}"]
        for line in lines:
            line = line.strip()
            if line.startswith(">"):
                line = line.lstrip(">").strip()
            if line:
                result.append(line + "\\\\")
        result.append("\\end{quotation}")
        return "\n".join(result)

    tex = re.sub(r"^(?:>\s?)(.+?)(?:\n(?:>\s?).+)*$", _blockquote, tex, flags=re.MULTILINE)

    # ── 分割线 ─────────────────────────────────────────────────
    tex = re.sub(r"^\s*[-*_]{3,}\s*$", "\\\\hline", tex, flags=re.MULTILINE)

    # ── 无序列表（只用 - 或 + 开头，不用 * 避免与加粗/斜体混淆）────────
    def _ulist_block(m):
        items = re.findall(r"^\s*[-+]\s+([^\n]+)$", m.group(0), flags=re.MULTILINE)
        if not items:
            return m.group(0)
        body = "\n".join(f"\\item {item}" for item in items)
        return f"\\begin{{itemize}}\n{body}\n\\end{{itemize}}"

    tex = re.sub(r"(?:\n?(?:[-+]\s+([^\n]+)))+", _ulist_block, tex, flags=re.MULTILINE)

    # ── 有序列表 ───────────────────────────────────────────────
    def _olist_block(m):
        items = re.findall(r"^\s*\d+\.\s+([^\n]+)$", m.group(0), flags=re.MULTILINE)
        if not items:
            return m.group(0)
        body = "\n".join(f"\\item {item}" for item in items)
        return f"\\begin{{enumerate}}\n{body}\n\\end{{enumerate}}"

    tex = re.sub(r"(?:^|\n)(?:\d+\.\s+([^\n]+))+", _olist_block, tex, flags=re.MULTILINE)

    # ── 加粗和斜体 ─────────────────────────────────────────────
    # 保护占位符里的下划线，防止被斜体 _..._ 模式误匹配
    # 将 __PLACEHOLDER__ 转为 __PLACE\x00HOLDER\x00__（中间加空字节）
    _protected_placeholders: list[str] = []

    def _protect_placeholder(m):
        idx = len(_protected_placeholders)
        # 把中间的下划线用空字节替换，最后再换回来
        protected = m.group(0).replace("_", "\x00")
        _protected_placeholders.append(m.group(0))
        return protected

    tex = re.sub(r"__(?:CODEBLOCK|INLINECODE|MATH_INLINE|MATH_DISPLAY)_\d+__", _protect_placeholder, tex)

    # 先处理加粗（加粗用 ** 或 __，确保不会被斜体处理）
    tex = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", tex)
    tex = re.sub(r"__(.+?)__", r"\\textbf{\1}", tex)
    # 斜体：单 * 或单 _，用前后瞻排除 **bold** 或 __bold__ 的内层 *
    tex = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\\textit{\1}", tex)
    tex = re.sub(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", r"\\textit{\1}", tex)

    # 还原占位符（把空字节换回下划线）
    for ph in _protected_placeholders:
        protected = ph.replace("_", "\x00")
        tex = tex.replace(protected, ph)

    # ── 还原受保护内容 ─────────────────────────────────────────
    for i, block in enumerate(code_blocks):
        tex = tex.replace(f"__CODEBLOCK_{i}__", block)
    for i, code in enumerate(inline_codes):
        tex = tex.replace(f"__INLINECODE_{i}__", code)
    for i, math in enumerate(math_display):
        tex = tex.replace(f"__MATH_DISPLAY_{i}__", f"\\[{math}\\]")
    for i, math in enumerate(math_inline):
        tex = tex.replace(f"__MATH_INLINE_{i}__", f"\\({math}\\)")

    # ── 段落和换行 ─────────────────────────────────────────────
    lines = tex.split("\n")
    result_lines: list[str] = []
    in_verbatim = False
    paragraph_buf: list[str] = []

    def _flush_paragraph():
        if paragraph_buf:
            joined = " ".join(paragraph_buf)
            if joined.strip():
                result_lines.append(f"{joined}\n\\par")
            paragraph_buf.clear()

    for line in lines:
        stripped = line.strip()
        if "\\begin{verbatim}" in line:
            _flush_paragraph()
            in_verbatim = True
            result_lines.append(line)
        elif "\\end{verbatim}" in line:
            result_lines.append(line)
            in_verbatim = False
        elif in_verbatim:
            result_lines.append(line)
        elif not stripped:
            _flush_paragraph()
            result_lines.append("")
        elif stripped.startswith("\\") or stripped.startswith(" "):
            _flush_paragraph()
            result_lines.append(line)
        else:
            paragraph_buf.append(stripped)

    _flush_paragraph()
    tex_body = "\n".join(result_lines)

    # Build LaTeX doc using raw strings to avoid escape issues
    title_tex = _escape_latex(meta.get("title", ""))
    author_tex = _escape_latex(meta.get("author", ""))
    abstract_tex_raw = meta.get("abstract", "")

    _doc_preamble = (
        r"\documentclass[12pt]{article}" + "\n" +
        r"\usepackage[UTF8]{inputenc}" + "\n" +
        r"\usepackage[T1]{fontenc}" + "\n" +
        r"\usepackage{amsmath,amssymb,bm}" + "\n" +
        r"\usepackage{graphicx}" + "\n" +
        r"\usepackage{hyperref}" + "\n" +
        r"\usepackage{geometry}" + "\n" +
        r"\geometry{margin=1in}" + "\n" +
        r"\usepackage{enumitem}" + "\n" +
        r"\setlist{noitemsep}" + "\n" +
        r"\hypersetup{colorlinks=true,linkcolor=blue,citecolor=blue,urlcolor=blue}" + "\n"
    )

    _title_part = (
        (r"\title{" + title_tex + r"}" + "\n" +
         r"\author{" + author_tex + r"}" + "\n" +
         r"\date{}" + "\n" +
         r"\maketitle" + "\n")
        if title_tex
        else ""
    )

    _abstract_part = (
        (r"\begin{abstract}" + "\n" + abstract_tex_raw + "\n" + r"\end{abstract}" + "\n")
        if abstract_tex_raw
        else ""
    )

    _doc_body = (
        r"\begin{document}" + "\n" +
        _title_part +
        _abstract_part +
        tex_body +
        "\n" +
        r"\end{document}" + "\n"
    )

    latex_doc = _doc_preamble + _doc_body

    return {
        "success": True,
        "tex": latex_doc.strip(),
        "error": "",
        "output_path": "",
        "template": "generic",
        "pandoc_version": "",
    }


def convert_markdown(
    markdown_text: str,
    template_id: str = "generic",
    output_format: Literal["tex", "pdf"] = "tex",
    metadata: dict | None = None,
) -> dict:
    """
    将 Markdown 转换为 LaTeX（.tex）。

    Args:
        markdown_text: Markdown 内容
        template_id: 模板 ID（ieee / acm / generic / springer_lncs / elsevier）
        output_format: 输出格式（tex 或 pdf）
        metadata: 元数据（title, author, abstract 等）

    Returns:
        {
            "success": bool,
            "tex": str,          # LaTeX 源码
            "output_path": str,  # 如果保存到文件，返回文件路径
            "error": str,        # 如果失败，返回错误信息
            "pandoc_version": str,
        }
    """
    if output_format == "pdf":
        # PDF 模式：Pandoc md→tex → 清理 pdfTeX 专用包 → 注入 CJK → Tectonic 编译
        tex_result = convert_markdown(markdown_text, template_id, "tex", metadata)
        if not tex_result["success"]:
            return tex_result

        tex = tex_result["tex"]

        # 移除与 XeTeX/fontspec 冲突的包
        tex = re.sub(r"\\usepackage(\[.*?\])?\{inputenc\}\n?", "", tex)
        tex = re.sub(r"\\usepackage(\[.*?\])?\{fontenc\}\n?", "", tex)
        tex = re.sub(r"\\usepackage(\[.*?\])?\{libertine\}\n?", "", tex)
        tex = re.sub(r"\\usepackage(\[.*?\])?\{libertinus\}\n?", "", tex)

        # 注入 CJK 字体 + Pandoc 常用表格/排版包
        inject_preamble = (
            r"\usepackage{fontspec}" + "\n" +
            r"\setmainfont{SimSun}" + "\n" +
            r"\usepackage{xeCJK}" + "\n" +
            r"\setCJKmainfont{SimSun}" + "\n" +
            r"\usepackage{longtable}" + "\n" +
            r"\usepackage{booktabs}" + "\n" +
            r"\usepackage{array}" + "\n" +
            r"\usepackage{calc}" + "\n"
        )
        if r"\usepackage{fontspec}" not in tex:
            def _inject_cjk(m):
                return m.group(1) + inject_preamble
            tex = re.sub(
                r"(\\documentclass[^\n]*\n)",
                _inject_cjk,
                tex,
                count=1,
            )

        pdf_result = compile_pdf(tex)
        return {
            "success": pdf_result["success"],
            "tex": tex,
            "pdf_path": pdf_result.get("pdf_path", ""),
            "error": pdf_result["error"],
            "output_path": pdf_result.get("pdf_path", ""),
            "pandoc_version": pandoc_version(),
        }

    cmd = _find_pandoc()
    if not cmd:
        # 使用纯 Python 转换器（不依赖 Pandoc）
        return markdown_to_latex(markdown_text, metadata)

    # 兼容旧 pandoc ID（ieee → ieee_conference, generic → generic_article 等）
    _LEGACY_ID_MAP: dict[str, str] = {
        "ieee": "ieee_conference",
        "generic": "generic_article",
        "springer_lncs": "lncs",
    }
    template_id = _LEGACY_ID_MAP.get(template_id, template_id)

    # 加载模板
    registry = _load_registry()
    templates = registry.get("templates", [])
    template_map = {t["id"]: t for t in templates}
    template_info = template_map.get(template_id)

    if not template_info:
        template_id = "generic_article"
        template_info = template_map.get("generic_article", {})

    # 模板文件路径
    template_file = TEMPLATE_DIR / f"{template_id}.tex"
    if not template_file.exists():
        template_file = TEMPLATE_DIR / "generic_article.tex"

    # 构建 Pandoc 参数
    args = [
        cmd,
        "-f", "markdown",
        "-t", "latex",
        "-s",
        "--wrap=none",
    ]

    # 指定模板（如果存在且 Pandoc 支持）
    if template_file.exists():
        args += ["--template", str(template_file)]

    # 元数据变量
    meta = metadata or {}
    for key, value in meta.items():
        if value:
            args += ["--metadata", f"{key}:{value}"]

    # 数学引擎（使用 mathjax 而非 LaTeX 原生，避免复杂公式渲染问题）
    args += ["--mathjax=https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"]

    # 引用文献
    if template_info.get("bib_style"):
        args += ["--metadata", f"biblio-style:{template_info['bib_style']}"]

    # 使用 --quiet 减少日志
    args.append("--quiet")

    try:
        # 写入临时文件（避免命令行转义问题）
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", encoding="utf-8", delete=False
        ) as f:
            f.write(markdown_text)
            md_path = f.name

        try:
            result = subprocess.run(
                args,
                input=open(md_path, encoding="utf-8").read(),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip() or "Pandoc 转换失败"
                logger.warning("Pandoc convert failed: %s", error_msg)
                # 尝试不使用模板再跑一次
                fallback_args = [
                    x for x in args
                    if not x.startswith("--template")
                ]
                result2 = subprocess.run(
                    fallback_args,
                    input=open(md_path, encoding="utf-8").read(),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                )
                if result2.returncode == 0:
                    tex_fb = result2.stdout or ""
                    if tex_fb:
                        tex_fb = re.sub(r"\\tightlist\b(?!\{)", "", tex_fb)
                        tex_fb = re.sub(r"\\begin\{Highlighting\}", "", tex_fb)
                        tex_fb = re.sub(r"\\end\{Highlighting\}", "", tex_fb)
                        tex_fb = re.sub(r"\\begin\{Shaded\}", r"\\begin{verbatim}", tex_fb)
                        tex_fb = re.sub(r"\\end\{Shaded\}", r"\\end{verbatim}", tex_fb)
                        tex_fb = re.sub(r"\\[A-Z][a-zA-Z]*Tok\{([^}]*)\}", r"\1", tex_fb)
                        tex_fb = re.sub(r"\\[A-Z][a-zA-Z]*Tok\[[^\]]*\]\{([^}]*)\}", r"\1", tex_fb)
                    return {
                        "success": True,
                        "tex": tex_fb,
                        "error": "",
                        "output_path": "",
                        "template": template_id,
                        "pandoc_version": pandoc_version(),
                    }
                return {
                    "success": False,
                    "tex": "",
                    "error": f"Pandoc 转换失败: {error_msg}",
                    "output_path": "",
                    "pandoc_version": pandoc_version(),
                }

            tex_output = result.stdout or ""

            # 清理 Pandoc 插入的 \tightlist（未定义命令，须去除）
            if tex_output:
                tex_output = re.sub(r"\\tightlist\b(?!\{)", "", tex_output)

            # Pandoc 用 Shaded + Highlighting 环境高亮代码块，转换为 verbatim
            if tex_output:
                tex_output = re.sub(r"\\begin\{Highlighting\}", "", tex_output)
                tex_output = re.sub(r"\\end\{Highlighting\}", "", tex_output)
                tex_output = re.sub(r"\\begin\{Shaded\}", r"\\begin{verbatim}", tex_output)
                tex_output = re.sub(r"\\end\{Shaded\}", r"\\end{verbatim}", tex_output)
                # 清除 Pandoc 语法高亮命令 (\ImportTok{...} → ...), 仅保留文本
                tex_output = re.sub(r"\\[A-Z][a-zA-Z]*Tok\{([^}]*)\}", r"\1", tex_output)
                tex_output = re.sub(r"\\[A-Z][a-zA-Z]*Tok\[[^\]]*\]\{([^}]*)\}", r"\1", tex_output)
                tex_output = re.sub(r"\\NormalTok\b", "", tex_output)
                tex_output = re.sub(r"\\KeywordTok\b", "", tex_output)
                tex_output = re.sub(r"\\OperatorTok\b", "", tex_output)
                tex_output = re.sub(r"\\BuiltInTok\b", "", tex_output)
                tex_output = re.sub(r"\\ControlSequenceTok\b", "", tex_output)

            # output_path 参数默认空字符串，由调用方指定保存路径
            saved_path = ""

            return {
                "success": True,
                "tex": tex_output,
                "error": "",
                "output_path": saved_path,
                "template": template_id,
                "pandoc_version": pandoc_version(),
            }
        finally:
            try:
                Path(md_path).unlink(missing_ok=True)
            except Exception:
                pass

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "tex": "",
            "error": "Pandoc 处理超时（30秒）",
            "output_path": "",
            "pandoc_version": pandoc_version(),
        }
    except FileNotFoundError:
        return {
            "success": False,
            "tex": "",
            "error": f"未找到 Pandoc（{cmd}），请安装：https://pandoc.org/installing.html",
            "output_path": "",
            "pandoc_version": "",
        }
    except Exception as e:
        return {
            "success": False,
            "tex": "",
            "error": f"转换异常: {e}",
            "output_path": "",
            "pandoc_version": pandoc_version(),
        }


# ── Tectonic 自动安装 ──────────────────────────────────────────────

TECTONIC_DOWNLOAD_URL = "https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.16.9/tectonic-0.16.9-x86_64-pc-windows-msvc.zip"
TECTONIC_VERSION = "0.16.9"


def install_tectonic() -> dict:
    """下载并安装 Tectonic LaTeX 引擎到 LOCALAPPDATA/ScholarTranslate/tools/。

    Returns:
        {"success": bool, "error": str, "version": str}
    """
    global TECTONIC_CMD
    import os
    import zipfile
    import tempfile
    import urllib.request

    local_app = os.environ.get("LOCALAPPDATA", "")
    if not local_app:
        return {"success": False, "error": "无法确定 LOCALAPPDATA 路径", "version": ""}

    install_dir = Path(local_app) / "ScholarTranslate" / "tools"
    install_dir.mkdir(parents=True, exist_ok=True)
    tectonic_path = install_dir / "tectonic.exe"

    if tectonic_path.exists():
        TECTONIC_CMD = str(tectonic_path)
        return {"success": True, "error": "", "version": tectonic_version()}

    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp_path = tmp.name
            logger.info("正在下载 Tectonic %s...", TECTONIC_VERSION)
            urllib.request.urlretrieve(TECTONIC_DOWNLOAD_URL, tmp_path,)

        with zipfile.ZipFile(tmp_path, "r") as zf:
            for name in zf.namelist():
                if name.lower().endswith("tectonic.exe"):
                    with zf.open(name) as src, open(tectonic_path, "wb") as dst:
                        dst.write(src.read())
                    break
            else:
                return {"success": False, "error": "压缩包中未找到 tectonic.exe", "version": ""}

        try:
            os.unlink(tmp_path)
        except OSError:
            pass

        TECTONIC_CMD = str(tectonic_path)
        logger.info("Tectonic 安装成功: %s", tectonic_path)
        return {"success": True, "error": "", "version": tectonic_version()}

    except Exception as e:
        logger.error("Tectonic 安装失败: %s", e)
        err_msg = str(e)
        if "SSL" in err_msg or "timeout" in err_msg.lower() or "EOF" in err_msg:
            err_msg = (
                "网络连接失败，无法从 GitHub 下载 Tectonic。"
                "请手动下载：https://github.com/tectonic-typesetting/tectonic/releases"
            )
        return {"success": False, "error": err_msg, "version": ""}
