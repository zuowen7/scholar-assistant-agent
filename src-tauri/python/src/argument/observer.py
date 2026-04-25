"""Argument Mapping — ChromaDB 文献推荐（无 LLM）

纯本地 ChromaDB 余弦相似度检索，不调用大模型。
基于节点 topic + content + domain_tags 构建查询，返回相关文献。
"""

from __future__ import annotations

import logging
from typing import Any

from src.argument.models import RecommendationItem
from src.argument.store import ArgumentStore

logger = logging.getLogger(__name__)

# ChromaDB cosine distance 阈值: distance 范围 [0, 1]，similarity = 1 - distance
# 0.15 → similarity > 0.85
_DISTANCE_THRESHOLD = 0.15


class ArgumentObserver:
    """ChromaDB 文献推荐 — 不调用 LLM，纯向量检索。"""

    def __init__(self, store: ArgumentStore) -> None:
        self._store = store

    def observe(
        self,
        node_id: str,
        content_hint: str | None = None,
        rag_store: Any = None,
    ) -> dict[str, Any]:
        """为节点推荐相关文献。

        Args:
            node_id: 目标节点 ID。
            content_hint: 可选的内容片段，用于更精准检索。
            rag_store: RAGStore 实例。

        Returns:
            dict with node_id and recommendations list.
        """
        node = self._store.get_node(node_id)
        if not node:
            return {"node_id": node_id, "recommendations": []}

        if rag_store is None:
            return {"node_id": node_id, "recommendations": []}

        # 构建查询文本
        query_parts = [node.topic]
        if node.content:
            query_parts.append(node.content[:500])
        if content_hint:
            query_parts.append(content_hint[:300])
        if node.domain_tags:
            query_parts.extend(node.domain_tags)
        query = " ".join(query_parts)

        if not query.strip():
            return {"node_id": node_id, "recommendations": []}

        try:
            results = rag_store.retrieve_context(query, top_k=10)
        except Exception as e:
            logger.warning("ChromaDB 检索失败: %s", e)
            return {"node_id": node_id, "recommendations": []}

        # 过滤和格式化
        recommendations: list[RecommendationItem] = []
        for r in results:
            distance = r.get("distance", 2.0)
            if distance > _DISTANCE_THRESHOLD:
                continue

            similarity = 1.0 - distance
            metadata = r.get("metadata", {})

            # 已绑定的文献不再推荐
            doc_id = metadata.get("doc_id", r.get("id", ""))
            if any(ref.doc_id == doc_id for ref in node.references):
                continue

            # 判断 match_type
            match_type = "keyword"
            if node.domain_tags:
                text = r.get("text", "").lower()
                if any(tag.lower() in text for tag in node.domain_tags):
                    match_type = "domain_tag"

            # 从 metadata 提取文献信息
            title = metadata.get("title", metadata.get("doc_id", ""))
            authors_str = metadata.get("authors", "")
            authors = [a.strip() for a in authors_str.split(",")] if authors_str else []
            year = metadata.get("year")
            citation_key = metadata.get("citation_key", metadata.get("doc_id", ""))

            recommendations.append(RecommendationItem(
                doc_id=doc_id,
                citation_key=citation_key,
                title=title,
                authors=authors,
                year=int(year) if year else None,
                relevance_score=round(similarity, 2),
                excerpt=r.get("text", "")[:200],
                match_type=match_type,
            ))

        # 按相关性排序
        recommendations.sort(key=lambda x: x.relevance_score, reverse=True)

        return {
            "node_id": node_id,
            "recommendations": [r.model_dump() for r in recommendations],
        }
