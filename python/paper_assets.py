"""论文模板资源库 — 素材扫描、ChromaDB 索引、论文骨架生成。

将 paper_assets/ 目录下的论文模板和素材批量索引入 ChromaDB 的
paper_templates collection，供 Agent 检索和引用。

提供论文骨架生成功能，根据所选模板和章节组装 Markdown 骨架。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ASSETS_DIR = Path(__file__).parent / "data" / "paper_assets"

# 模板元信息
TEMPLATE_META: dict[str, dict[str, str]] = {
    "acm": {
        "name": "ACM",
        "venue": "Conference / Journal",
        "description": "ACM 官方模板，支持 sigconf、acmsmall 等多种格式",
        "icon": "🏛️",
    },
    "ieee_conference": {
        "name": "IEEE Conference",
        "venue": "Conference",
        "description": "IEEE 会议论文模板，适用于 ICCV、CVPR 等 IEEE 会议",
        "icon": "📡",
    },
    "ieee_journal": {
        "name": "IEEE Journal",
        "venue": "Journal",
        "description": "IEEE 期刊模板，适用于 TPAMI、TIP 等 IEEE 期刊",
        "icon": "📰",
    },
    "lncs": {
        "name": "LNCS (Springer)",
        "venue": "Proceedings",
        "description": "Springer LNCS 模板，适用于 ECCV、ICALP 等",
        "icon": "📗",
    },
    "neurips": {
        "name": "NeurIPS",
        "venue": "Conference",
        "description": "NeurIPS 2025 官方模板，AI/ML 顶会",
        "icon": "🧠",
    },
    "generic_article": {
        "name": "Generic Article",
        "venue": "Generic",
        "description": "通用论文模板，适合初学者或无特定格式要求",
        "icon": "📄",
    },
}

# 章节名映射（dir name → 中文标题）
SECTION_TITLES: dict[str, str] = {
    "title": "标题",
    "abstract": "摘要",
    "introduction": "引言",
    "method": "方法",
    "experiment": "实验",
    "conclusion": "结论",
}

SECTION_ORDER = ["title", "abstract", "introduction", "method", "experiment", "conclusion"]


def get_template_list() -> list[dict[str, str]]:
    """返回所有可用模板的元信息列表。"""
    result = []
    for tid, meta in TEMPLATE_META.items():
        result.append({"id": tid, **meta})
    return result


def _scan_text_files(base_dir: Path) -> list[dict[str, Any]]:
    """扫描目录下的 .md/.tex/.txt/.bib 文件，返回文件信息列表。"""
    files = []
    for ext in ("*.md", "*.tex", "*.txt", "*.bib"):
        for fp in base_dir.rglob(ext):
            rel = fp.relative_to(base_dir)
            parts = rel.parts
            category = parts[0] if parts else "unknown"

            # 推断 metadata
            meta: dict[str, str] = {"category": category, "path": str(rel)}

            if category == "templates" and len(parts) >= 2:
                meta["template_name"] = parts[1]
            elif category == "materials" and len(parts) >= 3:
                meta["format"] = parts[1]  # markdown / latex / text
                section_dir = parts[2]
                # 从 section dir 名推断章节
                for sec_key in SECTION_ORDER:
                    if sec_key in section_dir.lower():
                        meta["section"] = sec_key
                        break
            elif category == "components" and len(parts) >= 2:
                comp = parts[1]
                if "figure" in comp:
                    meta["component"] = "figure"
                elif "table" in comp:
                    meta["component"] = "table"
                elif "equation" in comp:
                    meta["component"] = "equation"
                elif "citation" in comp:
                    meta["component"] = "citation"
                elif "appendix" in comp:
                    meta["component"] = "appendix"

            files.append({"path": fp, "metadata": meta, "rel_path": str(rel)})
    return files


def ingest_paper_assets(rag_store: Any) -> dict[str, int]:
    """将 paper_assets 目录下的所有文本文件批量索引入 ChromaDB。

    Args:
        rag_store: RAGStore 实例，使用 paper_templates collection。

    Returns:
        {"files": 文件数, "chunks": chunk 总数}
    """
    if not ASSETS_DIR.exists():
        logger.warning("paper_assets 目录不存在: %s", ASSETS_DIR)
        return {"files": 0, "chunks": 0}

    files = _scan_text_files(ASSETS_DIR)
    total_files = 0
    total_chunks = 0

    for finfo in files:
        fp = finfo["path"]
        try:
            text = fp.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if not text.strip():
            continue

        doc_id = f"paper_{finfo['rel_path'].replace('/', '_').replace('.', '_')}"
        chunks = rag_store.ingest_document(
            doc_id=doc_id,
            text=text,
            metadata=finfo["metadata"],
        )
        if chunks > 0:
            total_files += 1
            total_chunks += chunks

    logger.info("paper_assets 索引完成: %d files, %d chunks", total_files, total_chunks)
    return {"files": total_files, "chunks": total_chunks}


def get_ingestion_status(rag_store: Any) -> dict[str, Any]:
    """返回 paper_templates collection 的索引状态。"""
    docs = rag_store.list_documents()
    paper_docs = [d for d in docs if d.id.startswith("paper_")]
    return {
        "total_documents": len(paper_docs),
        "total_chunks": sum(d.chunk_count for d in paper_docs),
        "documents": [
            {"id": d.id, "title": d.title, "chunks": d.chunk_count}
            for d in paper_docs[:50]
        ],
    }


def generate_scaffold(
    template_id: str = "generic",
    title: str = "",
    sections: list[str] | None = None,
) -> str:
    """根据模板和章节生成论文骨架 Markdown。

    从 materials/markdown/ 目录读取各章节范例作为参考内容。
    """
    if sections is None:
        sections = SECTION_ORDER.copy()

    meta = TEMPLATE_META.get(template_id, TEMPLATE_META.get("generic_article", {}))
    lines: list[str] = []

    lines.append(f"---")
    lines.append(f"template: {template_id}")
    lines.append(f"venue: {meta['venue']}")
    if title:
        lines.append(f"title: {title}")
    lines.append(f"---")
    lines.append("")

    # Title section
    if "title" in sections:
        title_text = title or "Your Paper Title Here"
        lines.append(f"# {title_text}")
        lines.append("")
        sample = _read_material("title", "markdown")
        if sample:
            lines.append(f"<!-- 参考范例 -->")
            lines.append(f"<!-- {sample.strip()} -->")
            lines.append("")

    # Abstract
    if "abstract" in sections:
        lines.append("## Abstract")
        lines.append("")
        sample = _read_material("abstract", "markdown")
        if sample:
            lines.append(sample.strip())
            lines.append("")

    # Introduction
    if "introduction" in sections:
        lines.append("## 1. Introduction")
        lines.append("")
        sample = _read_material("introduction", "markdown")
        if sample:
            lines.append(sample.strip())
            lines.append("")

    # Method
    if "method" in sections:
        lines.append("## 2. Method")
        lines.append("")
        sample = _read_material("method", "markdown")
        if sample:
            lines.append(sample.strip())
            lines.append("")

    # Experiment
    if "experiment" in sections:
        lines.append("## 3. Experiments")
        lines.append("")
        sample = _read_material("experiment", "markdown")
        if sample:
            lines.append(sample.strip())
            lines.append("")

    # Conclusion
    if "conclusion" in sections:
        lines.append("## 4. Conclusion")
        lines.append("")
        sample = _read_material("conclusion", "markdown")
        if sample:
            lines.append(sample.strip())
            lines.append("")

    # References placeholder
    lines.append("## References")
    lines.append("")
    lines.append("<!-- 请在此添加参考文献 -->")
    lines.append("")

    return "\n".join(lines)


def _read_material(section: str, fmt: str) -> str:
    """从 materials/ 目录读取指定章节的范例文本。"""
    # 尝试从 materials/{fmt}/{section}/ 下读取
    section_dir = ASSETS_DIR / "materials" / fmt / section
    if not section_dir.exists():
        # 尝试模糊匹配（如 introduction 对应 intro_case_01）
        for d in (ASSETS_DIR / "materials" / fmt).iterdir():
            if section in d.name.lower() or d.name.lower() in section:
                section_dir = d
                break

    if not section_dir.exists():
        return ""

    # 读取目录下的第一个文件
    ext_map = {"markdown": "*.md", "latex": "*.tex", "text": "*.md"}
    for fp in section_dir.glob(ext_map.get(fmt, "*.md")):
        try:
            return fp.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
    return ""


def get_style_examples(template_id: str, section: str = "") -> str:
    """获取指定模板和章节的风格范例文本，用于风格迁移。

    Returns:
        拼接的范例文本（markdown + latex），供 LLM 参考。
    """
    parts: list[str] = []

    # 读取 materials 中对应章节的 markdown 和 latex 范例
    for fmt in ("markdown", "latex"):
        text = _read_material(section, fmt) if section else ""
        if text:
            parts.append(f"[{fmt} 范例]\n{text.strip()}")

    # 读取模板源码中的相关章节（如果有的话）
    template_dir = ASSETS_DIR / "templates" / template_id / "source"
    if template_dir.exists():
        for tex_file in template_dir.glob("*.tex"):
            try:
                content = tex_file.read_text(encoding="utf-8", errors="ignore")
                # 只提取与 section 相关的片段
                if section:
                    pattern = rf"\\{section}{{.*?}}(.*?)(?=\\(?:section|bibliography)|\Z)"
                    match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
                    if match:
                        snippet = match.group(0)[:2000]
                        parts.append(f"[{template_id} .tex 片段]\n{snippet}")
                else:
                    # 返回整篇的前 2000 字符作为风格参考
                    parts.append(f"[{template_id} .tex 摘录]\n{content[:2000]}")
            except Exception:
                continue

    return "\n\n---\n\n".join(parts) if parts else "未找到相关范例。"
