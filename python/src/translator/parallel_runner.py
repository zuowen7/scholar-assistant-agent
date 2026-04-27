"""Parallel chunk translation with bounded concurrency.

Yields ChunkResult in strict index order regardless of completion order.
When max_concurrency=1, behavior is identical to the old sequential loop
(including prev_trans chaining). When max_concurrency>1, prev_trans is not
chained — slight quality loss accepted.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import AsyncGenerator

from src.translator.ollama_client import TranslationResult

logger = logging.getLogger(__name__)


@dataclass
class ChunkResult:
    index: int
    result: TranslationResult
    error: str | None = None
    is_fallback: bool = False


async def _translate_one(
    client,
    text: str,
    prev_trans: str,
    index: int,
    total: int,
    retry_delay: float = 2.0,
) -> ChunkResult:
    """Translate a single chunk with one retry and fallback to original."""
    try:
        result = await asyncio.to_thread(client.translate, text, prev_trans)
    except Exception as e:
        logger.warning("块 %d/%d 翻译失败，尝试单独重试: %s", index + 1, total, e)
        await asyncio.sleep(retry_delay)
        try:
            result = await asyncio.to_thread(client.translate, text, prev_trans)
        except Exception as e2:
            logger.error("块 %d/%d 重试仍失败: %s，保留原文", index + 1, total, e2)
            result = TranslationResult(original=text, translated=text, model="")
            return ChunkResult(index=index, result=result, error=str(e2), is_fallback=True)

    is_fallback = result.original == result.translated
    return ChunkResult(index=index, result=result, is_fallback=is_fallback)


async def translate_chunks_parallel(
    client,
    chunks: list,
    max_concurrency: int = 4,
    retry_delay: float = 2.0,
) -> AsyncGenerator[ChunkResult, None]:
    """Translate chunks with bounded concurrency, yielding in index order.

    max_concurrency=1  → sequential, prev_trans chained (old behavior).
    max_concurrency>1  → parallel, prev_trans="" (slight quality loss).
    """
    if not chunks:
        return

    total = len(chunks)

    # -- sequential path (max_concurrency=1) --
    if max_concurrency <= 1:
        prev_trans = ""
        for i, chunk in enumerate(chunks):
            cr = await _translate_one(client, chunk.text, prev_trans, i, total, retry_delay)
            yield cr
            prev_trans = cr.result.translated
            await asyncio.sleep(0.1)
        return

    # -- parallel path --
    semaphore = asyncio.Semaphore(max_concurrency)
    completed: dict[int, ChunkResult] = {}
    next_yield = 0

    async def _run_chunk(index: int) -> None:
        async with semaphore:
            cr = await _translate_one(client, chunks[index].text, "", index, total, retry_delay)
        completed[index] = cr

    tasks = [asyncio.create_task(_run_chunk(i)) for i in range(total)]

    try:
        pending = set(tasks)
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task.exception():
                    logger.error("Chunk task raised: %s", task.exception())
            while next_yield in completed:
                yield completed[next_yield]
                next_yield += 1
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
