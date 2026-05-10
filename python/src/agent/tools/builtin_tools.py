"""内置工具 — arXiv 爬取与知识库管理。

版权声明: 本模块属于 Scholar Assistant Agent 子系统。
"""

from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# arXiv 爬取工具
# ---------------------------------------------------------------------------

def _crawl_arxiv(query: str, max_results: int = 5) -> str:
    """搜索 arXiv 学术论文，返回标题、作者和摘要。通过 arXiv API 检索最新学术论文信息。

    Args:
        query: 搜索关键词（英文）。
        max_results: 最大返回结果数，默认 5。
    """
    try:
        url = "https://export.arxiv.org/api/query"
        params = {
            "search_query": f"all:{query}",
            "max_results": str(max_results),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        resp = None
        with httpx.Client(timeout=30.0, trust_env=False) as client:
            for attempt in range(3):
                resp = client.get(url, params=params)
                if resp.status_code == 429:
                    time.sleep(3.0 * (attempt + 1))
                    continue
                resp.raise_for_status()
                break
            else:
                if resp is not None:
                    resp.raise_for_status()

        # 解析 Atom XML 响应
        root = ET.fromstring(resp.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns)

        if not entries:
            return "未找到相关论文。"

        results: list[str] = []
        for entry in entries:
            title = entry.find("atom:title", ns)
            summary = entry.find("atom:summary", ns)
            published = entry.find("atom:published", ns)
            authors = entry.findall("atom:author/atom:name", ns)

            title_text = title.text.strip().replace("\n", " ") if title is not None else "无标题"
            summary_text = summary.text.strip().replace("\n", " ")[:300] if summary is not None else ""
            pub_date = published.text[:10] if published is not None else "未知日期"
            author_names = ", ".join(a.text for a in authors[:3] if a.text)
            if len(authors) > 3:
                author_names += " et al."

            results.append(
                f"标题: {title_text}\n"
                f"作者: {author_names}\n"
                f"日期: {pub_date}\n"
                f"摘要: {summary_text}"
            )

        return "\n\n---\n\n".join(results)
    except Exception as e:
        return f"arXiv 搜索失败: {e}"


# ---------------------------------------------------------------------------
# 知识库管理工具（占位实现）
# ---------------------------------------------------------------------------

def _manage_knowledge(
    action: str,
    doc_id: str = "",
    file_path: str = "",
    text: str = "",
    query: str = "",
    top_k: int = 5,
) -> str:
    """管理知识库文档。支持入库、删除、列出和检索知识库中的文档。

    Args:
        action: 操作类型。ingest（入库）、delete（删除）、list（列出所有）、retrieve（检索）。
        doc_id: 文档 ID（ingest/delete 时必需）。
        file_path: 文档路径（ingest 时可选，与 text 二选一）。
        text: 直接文本内容（ingest 时可选，与 file_path 二选一）。
        query: 检索查询文本（retrieve 时必需）。
        top_k: 检索返回的最大结果数，默认 5。
    """
    # 当 create_default_registry(rag_store=None) 时使用本占位实现，返回友好提示
    # 而非抛 NotImplementedError，避免 Agent 在用户未启用知识库时崩溃。
    return (
        "知识库未启用：请先在 Agent 设置中开启 RAG 知识库，"
        "再使用 manage_knowledge 工具。"
    )


# 导出公共接口
__all__ = [
    "_crawl_arxiv",
    "_manage_knowledge",
]
