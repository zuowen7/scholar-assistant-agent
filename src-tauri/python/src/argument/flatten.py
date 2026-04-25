"""Argument Mapping — 降维展开（思维导图 → Markdown/LaTeX/DOCX）

沿树 DFS 顺序调用 LLM 扩写每个节点，注入节点挂载的 references，
最终输出 Markdown / LaTeX / DOCX 格式的学术论文初稿。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, AsyncGenerator

from src.argument.models import _now_iso

logger = logging.getLogger(__name__)

_EXPAND_SECTION_PROMPT = """你是一位学术论文写作助手。请将以下节点扩写为完整的学术段落。

节点主题: {topic}
节点内容: {content}
深度: {depth}
领域标签: {tags}
挂载文献: {references}

要求:
1. 扩写为 150-300 字的学术段落
2. 保持逻辑连贯、学术风格
3. 如果有挂载文献，用 [citation_key] 格式在文中引用
4. 只输出扩写后的段落文本，不要标题，不要解释"""

_LATEX_HEADER = r"""\documentclass{{article}}
\usepackage[utf8]{{inputenc}}
\usepackage{{cite}}
\usepackage{{hyperref}}
\title{{{title}}}
\date{{}}
\begin{{document}}
\maketitle
"""

_LATEX_FOOTER = r"""
\end{document}
"""


class ArgumentFlattener:
    """降维展开引擎 — DFS 遍历节点树，LLM 扩写，输出格式化文档。"""

    def __init__(self) -> None:
        pass

    async def flatten_stream(
        self,
        tree_data: dict[str, Any],
        template: str,
        style: str,
        include_references: bool,
        output_dir: Path,
        cloud_client: Any = None,
        ollama_client: Any = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """DFS 遍历 + LLM 扩写 + 格式化输出。

        Yields SSE-style event dicts: {event, data}.
        """
        nodes = tree_data.get("nodes", {})
        root_id = tree_data.get("root_id", "")

        # 1. Build DFS order
        dfs_order = self._build_dfs_order(nodes, root_id)
        if not dfs_order:
            return

        # 2. Expand each node via LLM
        expanded_sections: list[dict[str, Any]] = []
        all_references: list[dict] = []
        seen_doc_ids: set[str] = set()

        for nid in dfs_order:
            ndata = nodes.get(nid, {})
            yield {
                "event": "node_processing",
                "data": json.dumps({"node_id": nid, "status": "processing"}),
            }

            section = await self._expand_node(
                ndata, cloud_client, ollama_client,
            )
            expanded_sections.append({
                "node_id": nid,
                "topic": ndata.get("topic", ""),
                "depth": ndata.get("depth", 0),
                "section": section,
                "references": ndata.get("references", []),
            })

            for ref in ndata.get("references", []):
                doc_id = ref.get("doc_id", "")
                if doc_id and doc_id not in seen_doc_ids:
                    seen_doc_ids.add(doc_id)
                    all_references.append(ref)

            yield {
                "event": "node_complete",
                "data": json.dumps({"node_id": nid, "word_count": len(section)}),
            }

        # 3. Yield reference_processing event
        yield {
            "event": "reference_processing",
            "data": json.dumps({"count": len(all_references), "total": len(all_references)}),
        }

        # 4. Format output
        root_topic = nodes.get(root_id, {}).get("topic", "Paper Draft")
        if template == "latex":
            full_text = self._format_latex(expanded_sections, root_topic, all_references, include_references)
            ext = "tex"
        elif template == "docx":
            full_text = self._format_markdown(expanded_sections, all_references, include_references)
            ext = "md"  # will be converted to docx
        else:
            full_text = self._format_markdown(expanded_sections, all_references, include_references)
            ext = "md"

        output_path = output_dir / f"argument_draft_{_now_iso().replace(':', '-').replace('T', '_')[:19]}.{ext}"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(full_text, encoding="utf-8")

        # 5. Convert to docx if needed
        if template == "docx":
            docx_path = await self._convert_to_docx(full_text, output_path, output_dir)
            if docx_path:
                output_path = docx_path

        yield {
            "event": "complete",
            "data": json.dumps({
                "output_path": str(output_path),
                "word_count": len(full_text),
                "reference_count": len(all_references),
            }),
        }

    def _build_dfs_order(self, nodes: dict, root_id: str) -> list[str]:
        order: list[str] = []
        stack = [root_id] if root_id else list(nodes.keys())
        while stack:
            nid = stack.pop()
            if nid in nodes:
                order.append(nid)
                children = nodes[nid].get("children", [])
                stack.extend(reversed(children))
        return order

    async def _expand_node(
        self,
        ndata: dict,
        cloud_client: Any = None,
        ollama_client: Any = None,
    ) -> str:
        """调用 LLM 扩写单个节点。Fallback 到拼接 topic+content。"""
        topic = ndata.get("topic", "")
        content = ndata.get("content", "")
        depth = ndata.get("depth", 0)
        tags = ", ".join(ndata.get("domain_tags", [])) or "未指定"
        refs = ndata.get("references", [])
        ref_str = ", ".join(
            f"[{r.get('citation_key', r.get('doc_id', ''))}]"
            for r in refs
        ) if refs else "无"

        # 如果节点已有详细内容，直接用
        if content and len(content) > 100:
            return content

        # 调用 LLM 扩写
        prompt = _EXPAND_SECTION_PROMPT.format(
            topic=topic,
            content=content or "(无详细内容)",
            depth=depth,
            tags=tags,
            references=ref_str,
        )

        expanded = await self._call_llm(prompt, cloud_client, ollama_client)
        if expanded:
            return expanded.strip()

        # Fallback: 拼接模板
        if content:
            return f"{content}"
        return f"{topic}方面需要进一步研究和论述。"

    async def _call_llm(self, prompt: str, cloud_client: Any = None, ollama_client: Any = None) -> str:
        from src.argument.llm_client import call_llm_chat
        return await call_llm_chat(prompt, cloud_client, ollama_client, max_tokens=1024, temperature=0.7)

    def _format_markdown(
        self,
        sections: list[dict],
        references: list[dict],
        include_references: bool,
    ) -> str:
        parts: list[str] = []
        for sec in sections:
            depth = sec["depth"]
            prefix = "#" * (depth + 1)
            parts.append(f"{prefix} {sec['topic']}\n\n{sec['section']}\n")

        if include_references and references:
            parts.append("\n## References\n")
            for ref in references:
                key = ref.get("citation_key", ref.get("doc_id", ""))
                parts.append(f"- [{key}]")

        return "\n\n".join(parts)

    def _format_latex(
        self,
        sections: list[dict],
        title: str,
        references: list[dict],
        include_references: bool,
    ) -> str:
        parts: list[str] = [_LATEX_HEADER.format(title=title)]

        for sec in sections:
            depth = sec["depth"]
            if depth == 0:
                parts.append(f"\\section{{{sec['topic']}}}\n\n{sec['section']}\n")
            elif depth == 1:
                parts.append(f"\\subsection{{{sec['topic']}}}\n\n{sec['section']}\n")
            else:
                parts.append(f"\\subsubsection{{{sec['topic']}}}\n\n{sec['section']}\n")

        if include_references and references:
            parts.append("\n\\begin{thebibliography}{99}")
            for i, ref in enumerate(references):
                key = ref.get("citation_key", ref.get("doc_id", f"ref{i}"))
                parts.append(f"\\bibitem{{{key}}} {key}")
            parts.append("\\end{thebibliography}")

        parts.append(_LATEX_FOOTER)
        return "\n".join(parts)

    async def _convert_to_docx(self, markdown_text: str, md_path: Path, output_dir: Path) -> Path | None:
        """尝试用 Pandoc 将 Markdown 转换为 DOCX。"""
        try:
            import subprocess
            docx_path = md_path.with_suffix(".docx")
            result = subprocess.run(
                ["pandoc", str(md_path), "-o", str(docx_path), "--from=markdown", "--to=docx"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and docx_path.exists():
                return docx_path
        except Exception as e:
            logger.warning("Pandoc DOCX conversion failed: %s", e)
        return None
