"""基于 ChromaDB 的本地文档检索存储 (RAG) — 零配置持久化向量数据库。

本模块实现了 Agent 子系统的「记忆层」，提供文档入库 (ingest) 和语义检索 (retrieve)
两大核心能力。检索增强生成 (RAG) 让 Agent 能够"记住"大量文档内容，
在回答用户提问时自动定位相关段落，结合 LLM 生成准确、有据可查的回答。

架构设计:
- **存储引擎**: ChromaDB PersistentClient，数据持久化于本地文件系统，
  无需外部数据库服务，满足纯本地运行和隐私安全的核心需求。
- **嵌入模型**: 默认使用 all-MiniLM-L6-v2 (CPU 推理, ~80MB 模型体积)，
  不占用 GPU 显存，在消费级 8GB 显卡上可与 Qwen3:8B 模型和平共存。
- **切块策略**: 复用项目已有的 chunker 模块 (src/chunker/splitter.py)，
  但使用更小的 RAG 专用参数 (chunk_size=512, overlap=64)，
  以获得更精细的语义粒度和更高的检索召回率。

数据隐私保护:
- 所有文档和嵌入向量 100% 存储在用户本地设备。
- 不向任何外部服务发送文档内容或检索请求。
- 嵌入模型首次使用时从网络下载，之后缓存在本地（离线可用）。

版权声明: 本模块属于 Scholar Assistant Agent 子系统，
本地化向量检索与隐私保护机制受软件著作权和发明专利保护。
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from src.agent.models import DocumentInfo

logger = logging.getLogger(__name__)


class RAGStore:
    """基于 ChromaDB 的文档检索存储。

    零配置设计:
    - 首次初始化时自动创建持久化目录。
    - 使用 ChromaDB 内置的默认嵌入函数 (all-MiniLM-L6-v2)，
      无需手动配置嵌入模型。
    - 持久化目录不存在时自动创建。

    使用流程:
    1. 初始化: RAGStore(persist_dir="data/chromadb")
    2. 入库:   store.ingest_document("paper_001", full_text, {"title": "..."})
    3. 检索:   results = store.retrieve_context("transformer 注意力机制", top_k=5)
    4. 清理:   store.delete_document("paper_001")

    Attributes:
        persist_dir: ChromaDB 数据持久化目录路径。
        collection_name: 向量集合名称，同一目录下可有多个集合。
    """

    def __init__(
        self,
        persist_dir: str | Path = "data/chromadb",
        collection_name: str = "scholar_docs",
        chunk_size: int = 512,
        chunk_overlap: int = 64,
    ) -> None:
        """初始化 RAG 存储。

        Args:
            persist_dir: 数据持久化目录路径。
            collection_name: ChromaDB 集合名称。
            chunk_size: RAG 专用切块大小（token 数）。
            chunk_overlap: RAG 专用切块重叠（token 数）。
        """
        self.persist_dir = Path(persist_dir)
        self.collection_name = collection_name
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        self.persist_dir.mkdir(parents=True, exist_ok=True)

        # 延迟导入 chromadb，避免在未安装时影响其他模块的导入
        import chromadb
        from chromadb.utils import embedding_functions

        self._client = chromadb.PersistentClient(path=str(self.persist_dir))
        # 使用 ChromaDB 默认的 Sentence Transformers 嵌入模型 (CPU, all-MiniLM-L6-v2)
        self._embedding_fn = embedding_functions.DefaultEmbeddingFunction()
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=self._embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "RAG 存储初始化完成: dir=%s, collection=%s, 现有文档块=%d",
            self.persist_dir, self.collection_name, self._collection.count(),
        )

    def ingest_document(
        self,
        doc_id: str,
        text: str,
        metadata: dict | None = None,
    ) -> int:
        """将文档切块后存入向量数据库。

        入库流程:
        1. 使用 chunker 模块将文档文本切分为语义完整的文本块。
        2. 为每个文本块生成唯一 ID 和元数据（文档 ID、块索引）。
        3. 批量写入 ChromaDB 向量集合。

        切块策略:
        - 使用 RAG 专用参数 (chunk_size, chunk_overlap)，
          比翻译管道的切块更小，以提高语义检索的精确度。
        - 采用 sentence 切块策略，保证块边界落在句子边界处。

        Args:
            doc_id: 文档唯一标识符（由调用方指定，如文件名的哈希值）。
            text: 文档的完整文本内容。
            metadata: 附加元数据（如标题、作者、来源路径）。

        Returns:
            入库的文本块数量。
        """
        if not text.strip():
            logger.warning("文档 %s 内容为空，跳过入库", doc_id)
            return 0

        # 先删除该文档的旧版本（如果存在）
        self.delete_document(doc_id)

        # 使用 chunker 模块进行切块
        from src.chunker import chunk_text_full

        chunk_result = chunk_text_full(
            text,
            max_tokens=self.chunk_size,
            overlap_tokens=self.chunk_overlap,
            strategy="sentence",
            skip_references=False,
        )

        if not chunk_result.chunks:
            logger.warning("文档 %s 切块后为空，跳过入库", doc_id)
            return 0

        # 为每个 chunk 生成唯一 ID 和元数据
        chunk_ids: list[str] = []
        chunk_texts: list[str] = []
        chunk_metadatas: list[dict] = []

        base_meta = {"doc_id": doc_id}
        if metadata:
            base_meta.update(metadata)

        for chunk in chunk_result.chunks:
            chunk_id = f"{doc_id}_chunk_{chunk.index}"
            chunk_ids.append(chunk_id)
            chunk_texts.append(chunk.text)
            chunk_metadatas.append({
                **base_meta,
                "chunk_index": chunk.index,
                "char_count": chunk.char_count,
            })

        self._collection.add(
            ids=chunk_ids,
            documents=chunk_texts,
            metadatas=chunk_metadatas,
        )

        logger.info(
            "文档入库完成: doc_id=%s, chunks=%d, chars=%d",
            doc_id, len(chunk_result.chunks), len(text),
        )
        return len(chunk_result.chunks)

    def ingest_text_chunks(
        self,
        doc_id: str,
        chunks: list[str],
        metadata: dict | None = None,
    ) -> int:
        """将预切分的文本块直接入库（跳过自动切块）。

        适用于已经按段落或其他逻辑单元切分好的文本，
        如从 parser 直接获取的页面内容。

        Args:
            doc_id: 文档唯一标识符。
            chunks: 预切分的文本块列表。
            metadata: 附加元数据。

        Returns:
            入库的文本块数量。
        """
        if not chunks:
            return 0

        self.delete_document(doc_id)

        chunk_ids: list[str] = []
        chunk_metadatas: list[dict] = []
        base_meta = {"doc_id": doc_id}
        if metadata:
            base_meta.update(metadata)

        for i, text in enumerate(chunks):
            if not text.strip():
                continue
            chunk_ids.append(f"{doc_id}_chunk_{i}")
            chunk_metadatas.append({**base_meta, "chunk_index": i, "char_count": len(text)})

        valid_texts = [t for t in chunks if t.strip()]

        if not valid_texts:
            return 0

        self._collection.add(
            ids=chunk_ids[: len(valid_texts)],
            documents=valid_texts,
            metadatas=chunk_metadatas[: len(valid_texts)],
        )

        logger.info("预切分文本入库完成: doc_id=%s, chunks=%d", doc_id, len(valid_texts))
        return len(valid_texts)

    def retrieve_context(
        self,
        query: str,
        top_k: int = 5,
        doc_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """基于语义相似度检索相关文档片段。

        检索策略:
        - 使用 ChromaDB 内置的余弦相似度 (cosine distance) 排序。
        - 返回与查询最相似的 top_k 个文本块。
        - 可选地按 doc_id 过滤，限定在特定文档范围内检索。

        Args:
            query: 查询文本（中英文均可，嵌入模型支持多语言）。
            top_k: 返回的最大结果数量。
            doc_id: 可选的文档 ID 过滤条件，仅在该文档内检索。

        Returns:
            检索结果列表，每项包含:
            - text: 文本块内容。
            - metadata: 块的元数据 (doc_id, chunk_index 等)。
            - distance: 与查询的余弦距离 (越小越相似，0 = 完全相同)。
        """
        if self._collection.count() == 0:
            return []

        where_filter = {"doc_id": doc_id} if doc_id else None

        results = self._collection.query(
            query_texts=[query],
            n_results=min(top_k, self._collection.count()),
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )

        # ChromaDB 返回格式: {"ids": [[...]], "documents": [[...]], ...}
        output: list[dict[str, Any]] = []
        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for i in range(len(ids)):
            output.append({
                "id": ids[i],
                "text": documents[i],
                "metadata": metadatas[i] if metadatas else {},
                "distance": distances[i] if distances else 0.0,
            })

        return output

    def list_documents(self) -> list[DocumentInfo]:
        """列出向量库中所有已入库文档的概要信息。

        通过遍历集合中所有条目的元数据，聚合唯一 doc_id 及其 chunk 数量。
        适用于前端展示文档列表或 Agent 了解可用知识库内容。

        Returns:
            DocumentInfo 列表，按文档 ID 排序。
        """
        if self._collection.count() == 0:
            return []

        # 获取所有元数据以聚合文档信息
        all_data = self._collection.get(include=["metadatas"])

        doc_map: dict[str, dict[str, Any]] = {}
        metadatas = all_data.get("metadatas", [])

        for meta in metadatas:
            if not meta:
                continue
            did = meta.get("doc_id", "unknown")
            if did not in doc_map:
                doc_map[did] = {
                    "id": did,
                    "title": meta.get("title", did),
                    "chunk_count": 0,
                    "metadata": {k: v for k, v in meta.items() if k not in ("chunk_index", "char_count")},
                }
            doc_map[did]["chunk_count"] += 1

        return [
            DocumentInfo(
                id=info["id"],
                title=info["title"],
                chunk_count=info["chunk_count"],
                metadata=info["metadata"],
            )
            for info in sorted(doc_map.values(), key=lambda x: x["id"])
        ]

    def delete_document(self, doc_id: str) -> None:
        """从向量数据库中删除指定文档的所有文本块。

        通过 doc_id 元数据过滤，一次性删除该文档关联的所有条目。

        Args:
            doc_id: 待删除的文档 ID。
        """
        try:
            self._collection.delete(where={"doc_id": doc_id})
            logger.info("文档已删除: doc_id=%s", doc_id)
        except Exception as e:
            logger.debug("删除文档 %s 时无记录或出错 (可忽略): %s", doc_id, e)

    def count_chunks(self) -> int:
        """返回向量库中的总文本块数量。

        Returns:
            文本块总数。
        """
        return self._collection.count()
