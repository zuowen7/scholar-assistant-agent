"""块对齐翻译器 — 把翻译结果按块映射回原结构

核心思想：
- 翻译时把一个 BlockChunk 的所有可翻译块用 \\n\\n 拼接送入 LLM
- LLM 输出按 \\n\\n 拆分回段落
- 数量对齐 → 直接 1:1 映射回 block id
- 数量不齐 → 按字符比例分配（兜底，与 _restore_paragraphs 同源）
- 极端不齐 → 第一块拿全部译文，其余空（前端用 aligned=False 提示）

章节感知翻译 (P0):
- 每个 chunk 翻译时自动检测所属章节类型
- 注入章节特定的翻译策略指令（Introduction/Results/Discussion/Methods 等）
- 非翻译块（公式/代码/表格）原样直通，不进入 LLM。
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import AsyncGenerator

from src.chunker import Block, BlockChunk
from src.translator._helpers import TranslationResult, _sanitize_llm_output
from src.cleaner.pipeline import protect_citations, restore_citations
from src.translator.section_aware import (
    SectionType,
    SectionContext,
    detect_section,
    detect_section_from_heading,
    get_section_prompt,
)

logger = logging.getLogger(__name__)


@dataclass
class BlockTranslation:
    """单块翻译结果，按块 id 对齐回原结构"""
    block_id: str
    type: str
    original: str
    translated: str
    translatable: bool = True
    status: str = 'ok'  # 'ok' | 'failed' | 'partial'


@dataclass
class ChunkBlockResult:
    """一个 BlockChunk 的完整翻译结果"""
    chunk_index: int
    block_translations: list[BlockTranslation]
    aligned: bool                    # True = LLM 输出段落数与可翻译块数一致
    is_fallback: bool = False        # True = 整个 chunk 翻译失败，原文直通
    error: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
    section_type: str = "unknown"    # 章节感知：当前 chunk 所属章节类型

    @property
    def chunk_text_original(self) -> str:
        return "\n\n".join(bt.original for bt in self.block_translations)

    @property
    def chunk_text_translated(self) -> str:
        return "\n\n".join(bt.translated for bt in self.block_translations)


_PARA_SPLIT_RE = re.compile(r"\n{2,}")


def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in _PARA_SPLIT_RE.split(text) if p.strip()]


def _distribute_by_char_ratio(originals: list[str], translation: str) -> list[str]:
    """把整段译文按原文字符比例切成 N 段，N = len(originals)

    比 _restore_paragraphs 健壮：即使译文无 \\n\\n 也能产出 N 段。
    """
    n = len(originals)
    if n <= 1 or not translation:
        return [translation] + [""] * (n - 1) if n >= 1 else []

    total_orig = sum(len(o) for o in originals)
    if total_orig == 0:
        # 平均分
        size = len(translation) // n
        out: list[str] = []
        for i in range(n):
            start = i * size
            end = (i + 1) * size if i < n - 1 else len(translation)
            out.append(translation[start:end].strip())
        return out

    out = []
    cursor = 0
    cum = 0
    tlen = len(translation)
    for i, orig in enumerate(originals):
        cum += len(orig)
        if i == n - 1:
            out.append(translation[cursor:].strip())
        else:
            target = int(cum / total_orig * tlen)
            # 尽量切在标点边界（中文句号/英文句号/逗号）
            window = translation[max(cursor, target - 30):min(tlen, target + 30)]
            best_offset = -1
            for sep in ("。", "！", "？", "；", ". ", "! ", "? "):
                p = window.rfind(sep)
                if p > best_offset:
                    best_offset = p + len(sep)
            if best_offset > 0:
                target = max(cursor, target - 30) + best_offset
            out.append(translation[cursor:target].strip())
            cursor = target
    return out


def _align_translation_to_blocks(
    blocks: list[Block],
    full_translation: str,
) -> tuple[list[BlockTranslation], bool]:
    """把整段译文按块对齐回原结构

    返回 (block_translations, aligned)。aligned=True 表示 LLM 输出段落数与
    可翻译块数完全一致，可以直接 1:1 映射；False 表示用兜底分配策略。
    """
    translatable_blocks = [b for b in blocks if b.translatable]

    # 没有可翻译块 → 全部直通原文
    if not translatable_blocks:
        return (
            [BlockTranslation(b.id, b.type, b.text, b.text, b.translatable) for b in blocks],
            True,
        )

    paras = _split_paragraphs(full_translation)
    aligned = len(paras) == len(translatable_blocks)

    if aligned:
        # 完美 1:1 映射
        para_iter = iter(paras)
        out: list[BlockTranslation] = []
        for b in blocks:
            if b.translatable:
                out.append(BlockTranslation(b.id, b.type, b.text, next(para_iter), True))
            else:
                out.append(BlockTranslation(b.id, b.type, b.text, b.text, False))
        return out, True

    # 兜底：按原文字符比例切分整段译文
    distributed = _distribute_by_char_ratio(
        [b.text for b in translatable_blocks],
        full_translation,
    )

    out: list[BlockTranslation] = []
    dist_iter = iter(distributed)
    for b in blocks:
        if b.translatable:
            out.append(BlockTranslation(b.id, b.type, b.text, next(dist_iter), True))
        else:
            out.append(BlockTranslation(b.id, b.type, b.text, b.text, False))
    return out, False


def _build_chunk_input_text(blocks: list[Block]) -> str:
    """生成送给 LLM 的拼接文本，仅含可翻译块"""
    return "\n\n".join(b.text for b in blocks if b.translatable)


def _detect_chunk_section(blocks: list[Block]) -> SectionContext:
    """从 blocks 中检测当前 chunk 所属的章节类型。

    优先从 heading 类型的 block 检测；如果没有 heading，从第一个可翻译 block
    的文本内容检测；如果都检测不到，返回 UNKNOWN。
    """
    # 1. 优先从 heading block 检测
    for b in blocks:
        if b.type == "heading" and b.text.strip():
            ctx = detect_section_from_heading(b.text)
            if ctx.section_type != SectionType.UNKNOWN:
                return ctx

    # 2. 从第一个可翻译 block 的文本内容检测
    for b in blocks:
        if b.translatable and b.text.strip():
            ctx = detect_section(b.text)
            if ctx.section_type != SectionType.UNKNOWN:
                return ctx

    return SectionContext()


def _inject_section_prompt(chunk_input: str, section_ctx: SectionContext) -> str:
    """将章节感知翻译指令注入到 chunk 输入文本前面"""
    if section_ctx.section_type == SectionType.UNKNOWN:
        return chunk_input

    section_prompt = get_section_prompt(section_ctx.section_type)
    if not section_prompt:
        return chunk_input

    return section_prompt.strip() + "\n\n" + chunk_input


async def translate_block_chunk(
    client,
    chunk: BlockChunk,
    blocks_by_id: dict[str, Block],
    prev_trans: str = "",
    source_lang: str = "en",
    prev_section: SectionType = SectionType.UNKNOWN,
) -> ChunkBlockResult:
    """翻译一个 BlockChunk，返回按块对齐的结果

    沿用 client.translate 的同步重试逻辑（asyncio.to_thread），不复制重试代码。
    自动检测章节类型并注入对应的翻译策略指令。
    """
    blocks = [blocks_by_id[bid] for bid in chunk.block_ids]
    chunk_input = _build_chunk_input_text(blocks)

    # 章节感知：检测当前 chunk 所属章节并注入翻译策略
    section_ctx = _detect_chunk_section(blocks)
    if section_ctx.section_type == SectionType.UNKNOWN and prev_section != SectionType.UNKNOWN:
        section_ctx.section_type = prev_section
        section_ctx.confidence = 0.4  # 继承前文章节类型，置信度较低
    chunk_input = _inject_section_prompt(chunk_input, section_ctx)

    # Protect inline citations from LLM rewrites
    chunk_input, citation_placeholders = protect_citations(chunk_input)

    # 没有可翻译内容（整 chunk 全是公式/代码/表格）
    if not chunk_input.strip():
        return ChunkBlockResult(
            chunk_index=chunk.index,
            block_translations=[
                BlockTranslation(b.id, b.type, b.text, b.text, b.translatable, 'ok')
                for b in blocks
            ],
            aligned=True,
            section_type=section_ctx.section_type.value,
        )

    try:
        result: TranslationResult = await asyncio.to_thread(
            client.translate, chunk_input, prev_trans
        )
    except Exception as e:
        logger.error("Block chunk %d 翻译失败: %s", chunk.index, e)
        return ChunkBlockResult(
            chunk_index=chunk.index,
            block_translations=[
                BlockTranslation(b.id, b.type, b.text, "", b.translatable, 'failed')
                for b in blocks
            ],
            aligned=False,
            is_fallback=True,
            error=str(e),
            section_type=section_ctx.section_type.value,
        )

    # Sanitize LLM output before alignment
    sanitized = _sanitize_llm_output(result.translated, source_lang=source_lang)

    # Restore protected citations
    if citation_placeholders:
        sanitized = restore_citations(sanitized, citation_placeholders)

    block_trans, aligned = _align_translation_to_blocks(blocks, sanitized)

    # Severe misalignment: retry each block individually (only for small chunks)
    translatable_blocks = [b for b in blocks if b.translatable]
    if not aligned and translatable_blocks and len(translatable_blocks) <= 4:
        paras = _split_paragraphs(sanitized)
        ratio = abs(len(paras) - len(translatable_blocks)) / max(len(translatable_blocks), 1)
        if ratio > 0.5:
            logger.warning("Chunk %d severely misaligned (%d paras vs %d blocks), retrying per-block",
                           chunk.index, len(paras), len(translatable_blocks))
            retry_results: list[str] = []
            for b in translatable_blocks:
                try:
                    single = await asyncio.to_thread(client.translate, b.text, "")
                    retry_results.append(_sanitize_llm_output(single.translated, source_lang=source_lang))
                except Exception:
                    retry_results.append("")
            out: list[BlockTranslation] = []
            ri = 0
            for b in blocks:
                if b.translatable:
                    text = retry_results[ri] if ri < len(retry_results) else ""
                    # Treat same-as-original as failed
                    if text and text.strip() == b.text.strip():
                        text = ""
                    st = 'ok' if text else 'failed'
                    out.append(BlockTranslation(b.id, b.type, b.text, text, True, st))
                    ri += 1
                else:
                    out.append(BlockTranslation(b.id, b.type, b.text, b.text, False, 'ok'))
            return ChunkBlockResult(
                chunk_index=chunk.index,
                block_translations=out,
                aligned=True,
                is_fallback=any(bt.status == 'failed' for bt in out),
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                model=result.model,
                section_type=section_ctx.section_type.value,
            )

    is_fallback = result.original == result.translated
    # Mark blocks as failed when translation is empty or identical to original
    for bt in block_trans:
        if bt.translatable and (not bt.translated or bt.translated.strip() == bt.original.strip()):
            bt.status = 'failed'
            bt.translated = ""
    return ChunkBlockResult(
        chunk_index=chunk.index,
        block_translations=block_trans,
        aligned=aligned,
        is_fallback=is_fallback,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        model=result.model,
        section_type=section_ctx.section_type.value,
    )


async def translate_block_chunks_parallel(
    client,
    chunks: list[BlockChunk],
    blocks_by_id: dict[str, Block],
    max_concurrency: int = 1,
    source_lang: str = "en",
) -> AsyncGenerator[ChunkBlockResult, None]:
    """并行翻译一组 BlockChunk，按 chunk.index 顺序产出

    max_concurrency=1 时串行并链接 prev_trans；>1 时并行，不链接前文。
    与 translate_chunks_parallel 接口一致。
    """
    if not chunks:
        return

    total = len(chunks)

    # 串行路径
    if max_concurrency <= 1:
        prev_trans = ""
        prev_section = SectionType.UNKNOWN
        for chunk in chunks:
            cr = await translate_block_chunk(client, chunk, blocks_by_id, prev_trans,
                                             source_lang=source_lang, prev_section=prev_section)
            yield cr
            prev_trans = cr.chunk_text_translated
            if cr.section_type != "unknown":
                prev_section = SectionType(cr.section_type)
            await asyncio.sleep(0.05)
        return

    # 并行路径
    sem = asyncio.Semaphore(max_concurrency)
    completed: dict[int, ChunkBlockResult] = {}
    next_yield_idx = 0

    async def _run(idx: int) -> None:
        async with sem:
            cr = await translate_block_chunk(client, chunks[idx], blocks_by_id, "",
                                             source_lang=source_lang, prev_section=SectionType.UNKNOWN)
        completed[chunks[idx].index] = cr

    tasks = [asyncio.create_task(_run(i)) for i in range(total)]
    try:
        pending = set(tasks)
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                if t.exception():
                    logger.error("Block chunk task raised: %s", t.exception())
            # chunk.index 升序产出
            chunk_indices = sorted({c.index for c in chunks})
            while next_yield_idx < len(chunk_indices) and chunk_indices[next_yield_idx] in completed:
                yield completed[chunk_indices[next_yield_idx]]
                next_yield_idx += 1
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
