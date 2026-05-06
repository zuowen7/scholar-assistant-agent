"""Argument Mapping — 降维展开管道（论证骨架 → 学术论文）

四阶段管道:
  1. 节点分类  — 将论证树节点映射到标准学术章节类型
                 （problem→引言/Intro, modeling→方法/Methods 等）
  2. 上下文扩写 — DFS 遍历时传递滚动摘要 + 全树概要 + RAG 文献片段 + 逻辑审查反馈
  3. 二轮 polish — Abstract 生成 + 章节间过渡句注入
  4. 格式化输出 — Markdown / LaTeX（接入现有模板系统） / DOCX
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, AsyncGenerator

from src.argument.models import _now_iso

logger = logging.getLogger(__name__)

# ── 链路关键词（与 logic_checker 保持同步）─────────────────────────────────
_CLASSIC_CHAIN_KEYWORDS: dict[str, list[str]] = {
    "problem":      ["问题", "背景", "挑战", "problem", "challenge", "background", "issue", "现状", "需求"],
    "modeling":     ["建模", "模型", "model", "modeling", "框架", "framework", "体系", "结构设计", "数学模型"],
    "analysis":     ["分析", "analysis", "评估", "evaluation", "研究", "study", "稳定性", "性能", "方法"],
    "verification": ["验证", "实验", "仿真", "simulation", "experiment", "verification", "测试", "对比"],
    "conclusion":   ["结论", "总结", "conclusion", "summary", "展望", "future", "讨论"],
}

# ── 链路类型 → 标准学术章节名（中/英双语）─────────────────────────────────
_CHAIN_TO_SECTION: dict[str, dict[str, str]] = {
    "problem":      {"zh": "引言",          "en": "Introduction"},
    "modeling":     {"zh": "方法",          "en": "Methods"},
    "analysis":     {"zh": "分析",          "en": "Analysis"},
    "verification": {"zh": "实验与结果",    "en": "Experiments and Results"},
    "conclusion":   {"zh": "结论",          "en": "Conclusion"},
}

# ── 每种章节类型的写作提示 ───────────────────────────────────────────────
_SECTION_TYPE_HINTS: dict[str, str] = {
    "problem":      "阐述研究背景、现有问题与本文动机，引出研究目标",
    "modeling":     "描述所提方法、系统架构或数学建模，突出创新点",
    "analysis":     "展开理论分析或对比研究，推导核心结论",
    "verification": "呈现实验设计、数据结果与对比分析，支撑所提方法的有效性",
    "conclusion":   "总结全文贡献、局限性与未来工作方向",
    "unknown":      "围绕节点主题展开学术论述，逻辑清晰，论据充分",
}

# ── Prompt 模板 ──────────────────────────────────────────────────────────────

_EXPAND_PROMPT = """你是一位严谨的学术论文写作助手，擅长写作信息完整、逻辑连贯的学术段落。

## 论文全局结构
{tree_outline}

## 已完成章节摘要（上文语境）
{context_so_far}

## 当前节点
章节角色: {section_role}（{role_hint}）
标题: {section_title}
原始主题关键词: {topic}
节点备注: {content}
逻辑审查反馈: {logic_issues}

## 挂载文献与相关内容片段
{reference_context}

写作要求:
1. 输出 200-400 字的学术段落正文
2. 段落开头自然衔接上文（适当使用"基于此"/"在此基础上"/"进一步地"等过渡语，首节除外）
3. 将文献片段的核心论点融入论述，用 [citation_key] 在行内标注（若无文献则跳过）
4. 如有逻辑审查反馈，在写作中体现改进（但不要在输出中重复反馈内容本身）
5. 只输出段落正文，不要输出标题、编号或任何额外解释"""

_ABSTRACT_PROMPT = """你是一位学术论文写作助手。请为以下论文生成一段规范的摘要。

论文题目: {title}

各章节内容摘要（按章节顺序）:
{sections_summary}

要求:
1. 摘要 150-250 字
2. 结构：研究背景 → 研究目标 → 所提方法 → 主要结果 → 结论贡献
3. 不出现"本节"/"如上所述"/"上文"等自指语
4. 只输出摘要正文，不要"摘要："或"Abstract:"前缀"""

_TRANSITION_PROMPT = """以下是一篇学术论文的章节标题序列和各章节首句：

{sections_preview}

请为相邻章节之间（共 {n_pairs} 对）各生成一句过渡句（中文 20 字以内），
使上下章节衔接自然，体现论证逻辑的递进关系。

严格按以下 JSON 格式输出（不要有其他内容）：
{{"transitions": ["第1到2章节的过渡句", "第2到3章节的过渡句", ...]}}"""


class ArgumentFlattener:
    """降维展开管道 — 从论证树到完整学术论文。"""

    def __init__(self) -> None:
        pass

    async def flatten_stream(
        self,
        tree_data: dict[str, Any],
        template: str,
        style: str,
        include_references: bool,
        output_dir: str | Path,
        cloud_client: Any = None,
        ollama_client: Any = None,
        rag_store: Any = None,
        latex_template: str = "generic_article",
    ) -> AsyncGenerator[dict[str, Any], None]:
        """主管道：分类 → 上下文扩写 → 二轮 polish → 格式化输出。

        Yields SSE-style event dicts: {event, data}.
        """
        nodes = tree_data.get("nodes", {})
        root_id = tree_data.get("root_id", "")
        output_dir = Path(output_dir)

        dfs_order = self._build_dfs_order(nodes, root_id)
        if not dfs_order:
            return

        # ── 阶段 1: 预处理树结构 ──────────────────────────────────────
        tree_outline = self._build_tree_outline(nodes, root_id, style)
        root_topic = nodes.get(root_id, {}).get("topic", "Paper Draft")

        # ── 阶段 2: DFS 节点扩写（带上下文 + RAG + 逻辑反馈）──────────
        expanded_sections: list[dict[str, Any]] = []
        rolling_summaries: list[str] = []
        all_refs_raw: list[dict] = []
        seen_doc_ids: set[str] = set()

        for nid in dfs_order:
            ndata = nodes.get(nid, {})
            yield {"event": "node_processing", "data": json.dumps({"node_id": nid, "status": "processing"})}

            depth = ndata.get("depth", 0)
            chain_type = self._classify_chain_type(ndata.get("topic", ""), ndata.get("content", ""))
            section_title = self._get_section_title(ndata.get("topic", ""), chain_type, depth, style)

            # 从 RAG 拉取文献片段，收集丰富的文献信息
            rag_context_str, enriched_refs = await self._fetch_ref_context(
                ndata.get("references", []), ndata.get("topic", ""), rag_store
            )
            for ref in enriched_refs:
                if ref["doc_id"] not in seen_doc_ids:
                    seen_doc_ids.add(ref["doc_id"])
                    all_refs_raw.append(ref)

            context_so_far = self._build_context_summary(rolling_summaries)

            section_text = await self._expand_node_with_context(
                ndata=ndata,
                section_title=section_title,
                chain_type=chain_type,
                context_so_far=context_so_far,
                tree_outline=tree_outline,
                rag_context_str=rag_context_str,
                cloud_client=cloud_client,
                ollama_client=ollama_client,
            )

            expanded_sections.append({
                "node_id": nid,
                "topic": ndata.get("topic", ""),
                "section_title": section_title,
                "chain_type": chain_type,
                "depth": depth,
                "text": section_text,
            })

            # 滚动摘要：保留最近 4 节的前 150 字
            rolling_summaries.append(f"[{section_title}] {section_text[:150].strip()}…")
            if len(rolling_summaries) > 4:
                rolling_summaries.pop(0)

            yield {"event": "node_complete", "data": json.dumps({"node_id": nid, "word_count": len(section_text)})}

        # ── 阶段 3: 二轮 polish — Abstract + 过渡句 ───────────────────
        yield {"event": "polish_start", "data": json.dumps({"status": "generating_abstract"})}

        abstract = await self._generate_abstract(expanded_sections, root_topic, cloud_client, ollama_client)

        transitions = await self._generate_transitions(expanded_sections, cloud_client, ollama_client)

        # 将过渡句注入到对应章节的段落开头
        if transitions:
            main_sections = [s for s in expanded_sections if s.get("depth", 0) >= 1]
            for i, trans in enumerate(transitions):
                if trans and i + 1 < len(main_sections):
                    target = main_sections[i + 1]
                    # 找到对应节在 expanded_sections 中的位置并更新
                    for sec in expanded_sections:
                        if sec["node_id"] == target["node_id"]:
                            sec["text"] = trans + " " + sec["text"]
                            break

        yield {"event": "reference_processing", "data": json.dumps({"count": len(all_refs_raw)})}

        enriched_bib = self._enrich_references(all_refs_raw, rag_store)

        # ── 阶段 4: 格式化输出 ────────────────────────────────────────
        if template == "latex":
            full_text = self._format_latex(
                abstract, expanded_sections, root_topic, enriched_bib,
                include_references, latex_template, style,
            )
            ext = "tex"
        elif template == "docx":
            full_text = self._format_markdown(abstract, expanded_sections, enriched_bib, include_references)
            ext = "md"
        else:
            full_text = self._format_markdown(abstract, expanded_sections, enriched_bib, include_references)
            ext = "md"

        timestamp = _now_iso().replace(":", "-").replace("T", "_")[:19]
        output_path = output_dir / f"argument_draft_{timestamp}.{ext}"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(full_text, encoding="utf-8")

        if template == "docx":
            docx_path = await self._convert_to_docx(full_text, output_path, output_dir)
            if docx_path:
                output_path = docx_path

        yield {
            "event": "complete",
            "data": json.dumps({
                "output_path": str(output_path),
                "word_count": len(full_text),
                "reference_count": len(enriched_bib),
                "section_count": len(expanded_sections),
            }),
        }

    # ── 树结构分析 ──────────────────────────────────────────────────────

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

    def _build_tree_outline(self, nodes: dict, root_id: str, style: str) -> str:
        """构建缩进文本树概要，在每节点的 prompt 中提供全局结构视图。"""
        lines: list[str] = []

        def _visit(nid: str, indent: int) -> None:
            ndata = nodes.get(nid, {})
            topic = ndata.get("topic", nid)
            depth = ndata.get("depth", 0)
            chain_type = self._classify_chain_type(topic, ndata.get("content", ""))
            section_name = self._get_section_title(topic, chain_type, depth, style)
            prefix = "  " * indent
            if indent == 0:
                lines.append(f"{prefix}[论文] {topic}")
            else:
                lines.append(f"{prefix}├─ {section_name}（{topic}）")
            for child_id in ndata.get("children", []):
                _visit(child_id, indent + 1)

        if root_id and root_id in nodes:
            _visit(root_id, 0)
        return "\n".join(lines) or "（无节点信息）"

    def _classify_chain_type(self, topic: str, content: str) -> str:
        """识别节点所属的论证链类型（problem/modeling/analysis/verification/conclusion）。"""
        text = f"{topic} {content}".lower()
        scores: dict[str, int] = {}
        for chain_name, keywords in _CLASSIC_CHAIN_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw.lower() in text)
            if score > 0:
                scores[chain_name] = score
        if not scores:
            return "unknown"
        return max(scores, key=lambda k: scores[k])

    def _get_section_title(self, topic: str, chain_type: str, depth: int, style: str) -> str:
        """根据节点类型和深度生成合适的章节标题。

        depth == 0: 论文标题 — 原始 topic
        depth == 1: 使用标准章节名（Introduction / Methods 等）
        depth >= 2: 原始 topic 作为子节标题
        """
        if depth == 0:
            return topic
        if depth == 1 and chain_type != "unknown":
            # 根据 topic 中是否含中文决定语言
            lang = "zh" if any(ord(c) > 127 for c in topic) else "en"
            return _CHAIN_TO_SECTION.get(chain_type, {}).get(lang, topic)
        return topic

    # ── 上下文构造 ──────────────────────────────────────────────────────

    def _build_context_summary(self, rolling_summaries: list[str]) -> str:
        if not rolling_summaries:
            return "（本节为首节，无上文）"
        return "\n".join(f"• {s}" for s in rolling_summaries[-3:])

    # ── RAG 文献片段获取 ─────────────────────────────────────────────────

    async def _fetch_ref_context(
        self,
        refs: list[dict],
        topic: str,
        rag_store: Any,
    ) -> tuple[str, list[dict]]:
        """从 RAG 拉取每个 reference 的相关片段，返回 (prompt_context, enriched_refs)。"""
        if not refs:
            return "（无挂载文献）", []

        context_parts: list[str] = []
        enriched: list[dict] = []

        for ref in refs:
            doc_id = ref.get("doc_id", "")
            citation_key = ref.get("citation_key", doc_id)
            entry: dict = {"doc_id": doc_id, "citation_key": citation_key, "title": "", "metadata": {}}
            enriched.append(entry)

            if rag_store is None or not doc_id:
                context_parts.append(f"[{citation_key}]: （RAG 未连接，无法获取文献内容）")
                continue

            try:
                chunks = rag_store.retrieve_context(query=topic, doc_id=doc_id, top_k=2)
                if chunks:
                    snippets = " ".join(c["text"][:200] for c in chunks[:2])
                    context_parts.append(f"[{citation_key}]: {snippets.strip()}")
                    first_meta = chunks[0].get("metadata") or {}
                    entry["metadata"] = first_meta
                    entry["title"] = first_meta.get("title", "")
                else:
                    context_parts.append(f"[{citation_key}]: （RAG 中无该文档的相关片段）")
            except Exception as e:
                logger.warning("RAG retrieval failed for doc_id=%s: %s", doc_id, e)
                context_parts.append(f"[{citation_key}]: （检索失败）")

        return "\n".join(context_parts), enriched

    # ── 节点 LLM 扩写（核心：带全局上下文）──────────────────────────────

    async def _expand_node_with_context(
        self,
        ndata: dict,
        section_title: str,
        chain_type: str,
        context_so_far: str,
        tree_outline: str,
        rag_context_str: str,
        cloud_client: Any,
        ollama_client: Any,
    ) -> str:
        topic = ndata.get("topic", "")
        content = ndata.get("content", "")

        # 逻辑审查反馈注入
        rule_issues = ndata.get("rule_issues", [])
        agent_feedback = ndata.get("agent_feedback") or ""
        if rule_issues or agent_feedback:
            issues_parts = [str(x) for x in rule_issues if x]
            if agent_feedback:
                issues_parts.append(agent_feedback)
            issues_text = "；".join(issues_parts)
        else:
            issues_text = "无"

        # 节点已有详细内容（>200字）且无文献绑定 → 保留原内容但仍通过 LLM 做衔接润色
        if content and len(content) > 200 and not ndata.get("references") and chain_type == "unknown":
            return content

        prompt = _EXPAND_PROMPT.format(
            tree_outline=tree_outline,
            context_so_far=context_so_far,
            section_role=chain_type,
            role_hint=_SECTION_TYPE_HINTS.get(chain_type, ""),
            section_title=section_title,
            topic=topic,
            content=content or "（无详细备注）",
            logic_issues=issues_text,
            reference_context=rag_context_str,
        )

        result = await self._call_llm(prompt, cloud_client, ollama_client, max_tokens=1024)
        if result:
            return result.strip()

        return content or f"{topic}方面需要进一步研究和论述。"

    # ── 二轮 polish — Abstract 生成 + 过渡句 ─────────────────────────────

    async def _generate_abstract(
        self,
        sections: list[dict],
        title: str,
        cloud_client: Any,
        ollama_client: Any,
    ) -> str:
        summary_parts = [
            f"[{s['section_title']}] {s['text'][:200].strip()}"
            for s in sections
            if s.get("depth", 0) >= 1
        ][:6]

        if not summary_parts:
            return ""

        prompt = _ABSTRACT_PROMPT.format(
            title=title,
            sections_summary="\n".join(summary_parts),
        )
        result = await self._call_llm(prompt, cloud_client, ollama_client, max_tokens=512, temperature=0.6)
        return result.strip() if result else ""

    async def _generate_transitions(
        self,
        sections: list[dict],
        cloud_client: Any,
        ollama_client: Any,
    ) -> list[str]:
        """生成相邻主章节之间的过渡句。"""
        main_sections = [s for s in sections if s.get("depth", 0) == 1]
        if len(main_sections) < 2:
            return []

        preview_lines = [
            f"{i + 1}. [{s['section_title']}] {s['text'][:80].strip()}…"
            for i, s in enumerate(main_sections[:8])
        ]
        n_pairs = min(len(main_sections) - 1, 7)

        prompt = _TRANSITION_PROMPT.format(
            sections_preview="\n".join(preview_lines),
            n_pairs=n_pairs,
        )
        result = await self._call_llm(prompt, cloud_client, ollama_client, max_tokens=400, temperature=0.5)
        if not result:
            return []

        try:
            # 提取 JSON（LLM 可能在前后加了额外文字）
            start = result.find("{")
            end = result.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(result[start:end])
                return data.get("transitions", [])
        except (json.JSONDecodeError, AttributeError):
            pass
        return []

    # ── 文献元数据丰富 ────────────────────────────────────────────────────

    def _enrich_references(self, raw_refs: list[dict], rag_store: Any) -> list[dict]:
        """用 RAG list_documents 补全文献元数据（title、authors、year 等）。"""
        if rag_store is None:
            return raw_refs

        try:
            doc_infos = {d.id: d for d in rag_store.list_documents()}
        except Exception:
            doc_infos = {}

        enriched = []
        for ref in raw_refs:
            doc_id = ref.get("doc_id", "")
            info = doc_infos.get(doc_id)
            entry = dict(ref)
            if info:
                if not entry.get("title"):
                    entry["title"] = info.title or ""
                stored_meta = info.metadata or {}
                entry["metadata"] = {**stored_meta, **(entry.get("metadata") or {})}
            enriched.append(entry)
        return enriched

    # ── 格式化输出 ──────────────────────────────────────────────────────

    def _format_markdown(
        self,
        abstract: str,
        sections: list[dict],
        references: list[dict],
        include_references: bool,
    ) -> str:
        parts: list[str] = []

        if abstract:
            parts.append("## Abstract\n\n" + abstract + "\n")

        for sec in sections:
            depth = sec["depth"]
            prefix = "#" * (depth + 1)
            parts.append(f"{prefix} {sec['section_title']}\n\n{sec['text']}\n")

        if include_references and references:
            parts.append("\n## References\n")
            for i, ref in enumerate(references, 1):
                key = ref.get("citation_key", ref.get("doc_id", f"ref{i}"))
                title = ref.get("title", "")
                meta = ref.get("metadata") or {}
                authors = meta.get("authors", meta.get("author", ""))
                year = meta.get("year", meta.get("date", ""))
                venue = meta.get("venue", meta.get("journal", meta.get("conference", "")))

                line = f"[{i}] "
                if authors:
                    line += f"{authors}. "
                line += title or key
                if year:
                    line += f" ({year})"
                if venue:
                    line += f". *{venue}*"
                line += f". `{key}`"
                parts.append(line)

        return "\n\n".join(parts)

    def _format_latex(
        self,
        abstract: str,
        sections: list[dict],
        title: str,
        references: list[dict],
        include_references: bool,
        latex_template: str,
        style: str,
    ) -> str:
        """用 pandoc_templates 系统生成规范 LaTeX（接入 IEEE/ACM/NeurIPS 等模板）。"""
        # 不在 Markdown body 里放 abstract，而是通过 metadata 传给模板
        md_parts: list[str] = []
        for sec in sections:
            depth = sec["depth"]
            prefix = "#" * (depth + 1)
            md_parts.append(f"{prefix} {sec['section_title']}\n\n{sec['text']}\n")
        md_body = "\n\n".join(md_parts)

        # 构造 BibTeX 条目（可被注入到 .tex 末尾）
        bibtex_entries = self._build_bibtex_entries(references) if include_references else []

        metadata = {"title": title, "abstract": abstract, "author": ""}

        try:
            from pandoc_templates import convert_markdown
            result = convert_markdown(md_body, template_id=latex_template, output_format="tex", metadata=metadata)
            if result.get("success") and result.get("tex"):
                tex = result["tex"]
                if bibtex_entries:
                    bib_block = "\n\n% BibTeX entries\n" + "\n\n".join(bibtex_entries)
                    tex = tex.replace(r"\end{document}", bib_block + "\n" + r"\end{document}")
                return tex
        except Exception as e:
            logger.warning("pandoc_templates convert failed (%s), using fallback", e)

        return self._fallback_latex(abstract, sections, title, references, include_references, bibtex_entries)

    def _build_bibtex_entries(self, references: list[dict]) -> list[str]:
        entries: list[str] = []
        for ref in references:
            key = ref.get("citation_key", ref.get("doc_id", "ref"))
            meta = ref.get("metadata") or {}
            title_ref = ref.get("title") or meta.get("title", key)
            authors = meta.get("authors", meta.get("author", "Unknown Author"))
            year = str(meta.get("year", meta.get("date", "2024")))[:4]
            journal = meta.get("journal", meta.get("venue", meta.get("conference", "")))
            entry_type = "article" if journal else "misc"
            entry = (
                f"@{entry_type}{{{key},\n"
                f"  author  = {{{authors}}},\n"
                f"  title   = {{{title_ref}}},\n"
                f"  year    = {{{year}}},\n"
            )
            if journal:
                entry += f"  journal = {{{journal}}},\n"
            entry += "}"
            entries.append(entry)
        return entries

    def _fallback_latex(
        self,
        abstract: str,
        sections: list[dict],
        title: str,
        references: list[dict],
        include_references: bool,
        bibtex_entries: list[str],
    ) -> str:
        """不依赖 Pandoc 的纯 Python LaTeX fallback。"""
        md_parts: list[str] = []
        for sec in sections:
            depth = sec["depth"]
            prefix = "#" * (depth + 1)
            md_parts.append(f"{prefix} {sec['section_title']}\n\n{sec['text']}\n")
        md_body = "\n\n".join(md_parts)

        try:
            from pandoc_templates import markdown_to_latex
            result = markdown_to_latex(md_body, {"title": title, "abstract": abstract, "author": ""})
            tex = result.get("tex", "")
        except Exception:
            tex = self._minimal_latex(title, abstract, sections)

        if include_references and references:
            bib_lines = ["\\begin{thebibliography}{99}"]
            for i, ref in enumerate(references, 1):
                key = ref.get("citation_key", ref.get("doc_id", f"ref{i}"))
                title_ref = ref.get("title", "")
                meta = ref.get("metadata") or {}
                authors = str(meta.get("authors", meta.get("author", "")))
                year = str(meta.get("year", meta.get("date", "")))
                line = f"\\bibitem{{{key}}} "
                if authors:
                    line += f"{authors}. "
                if title_ref:
                    line += f"\\textit{{{title_ref}}}."
                else:
                    line += key
                if year:
                    line += f" {year[:4]}."
                bib_lines.append(line)
            bib_lines.append("\\end{thebibliography}")
            tex = tex.replace(r"\end{document}", "\n".join(bib_lines) + "\n" + r"\end{document}")

        if bibtex_entries:
            bib_comment = "\n\n% BibTeX entries\n" + "\n\n".join(bibtex_entries)
            tex = tex.replace(r"\end{document}", bib_comment + "\n" + r"\end{document}")

        return tex

    def _minimal_latex(self, title: str, abstract: str, sections: list[dict]) -> str:
        """绝对兜底：不依赖任何外部模块的最小 LaTeX 文档。"""
        def _esc(s: str) -> str:
            for old, new in [("\\", "\\textbackslash{}"), ("{", "\\{"), ("}", "\\}"),
                              ("#", "\\#"), ("$", "\\$"), ("%", "\\%"), ("&", "\\&"),
                              ("_", "\\_"), ("^", "\\textasciicircum{}"), ("~", "\\textasciitilde{}")]:
                s = s.replace(old, new)
            return s

        lines = [
            "\\documentclass[12pt]{article}",
            "\\usepackage[utf8]{inputenc}", "\\usepackage{amsmath}",
            "\\usepackage{hyperref}", "\\usepackage{cite}",
            f"\\title{{{_esc(title)}}}", "\\author{}", "\\date{}",
            "\\begin{document}", "\\maketitle",
        ]
        if abstract:
            lines += ["\\begin{abstract}", abstract, "\\end{abstract}"]
        for sec in sections:
            depth = sec["depth"]
            if depth == 0:
                continue
            level = max(0, depth - 1)
            cmd = ["\\section", "\\subsection", "\\subsubsection"][min(level, 2)]
            lines.append(f"{cmd}{{{_esc(sec['section_title'])}}}")
            lines.append(sec["text"])
        lines.append("\\end{document}")
        return "\n".join(lines)

    async def _convert_to_docx(self, markdown_text: str, md_path: Path, output_dir: Path) -> Path | None:
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

    async def _call_llm(
        self,
        prompt: str,
        cloud_client: Any,
        ollama_client: Any,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        from src.argument.llm_client import call_llm_chat
        return await call_llm_chat(
            prompt, cloud_client, ollama_client,
            max_tokens=max_tokens, temperature=temperature,
        )
