"""文本切块器 - 将长文本切分为适合模型处理的块"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.chunker.syntax_splitter import _split_long_sentence

# 粗略估算: 1 token ≈ 4 个英文字符 或 1.5 个中文字符
CHARS_PER_TOKEN_EN = 4
CHARS_PER_TOKEN_ZH = 1.5
# 默认混合文本 token 估算字符系数（介于英中之间）
CHARS_PER_TOKEN_MIXED = 2.5


@dataclass
class Chunk:
    """文本块"""

    index: int
    text: str
    char_count: int
    estimated_tokens: int


@dataclass
class ChunkResult:
    """切块结果"""

    chunks: list[Chunk]
    references_text: str  # 未翻译的引用区原文


# ── 类型化块（block-aware 翻译流的核心数据结构） ────────────────────────────

# 块类型枚举（字符串常量，避免引入 Enum 依赖）
BLOCK_PARAGRAPH = "paragraph"
BLOCK_HEADING = "heading"
BLOCK_FORMULA = "formula"        # $$...$$ / \[...\] / \begin{equation}...
BLOCK_CODE = "code"              # ``` ... ```
BLOCK_TABLE = "table"            # markdown 表格
BLOCK_LIST = "list"              # 项目符号列表（整体作为一个块）
BLOCK_FIGURE_CAPTION = "figure_caption"  # Figure 1 / Fig. 1 / Table 1 起始


@dataclass
class Block:
    """类型化文本块——翻译管道的对齐单元

    每个 Block 代表文档中的一个语义单元（段落、标题、公式、表格等）。
    翻译时按块对齐，前端按块渲染，避免猜测式句子拆分。
    """
    id: str
    type: str
    text: str
    level: int = 0           # 标题级别 (1-6)，非标题为 0
    translatable: bool = True  # 公式/表格/代码默认不翻译


@dataclass
class BlockChunk:
    """块感知 chunk——一个 chunk 由一组完整的 Block 组成

    与传统 Chunk 相比，BlockChunk 携带 block_ids，使翻译结果可以
    按块对齐回原文结构，而不是返回一坨黑盒文本。
    """
    index: int
    text: str
    char_count: int
    estimated_tokens: int
    block_ids: list[str]


@dataclass
class BlockChunkResult:
    """块感知切块结果"""
    blocks: list[Block]
    chunks: list[BlockChunk]
    references_text: str


def _estimate_tokens(text: str) -> int:
    """估算文本的 token 数（中英文分开计算）。

    与 _estimate_chars_per_token 逻辑一致，但直接返回 token 数。
    """
    if not text:
        return 1
    zh_chars = sum(1 for c in text if "一" <= c <= "鿿")
    zh_ratio = zh_chars / max(len(text), 1)
    if zh_ratio > 0.3:
        chars_per_token = CHARS_PER_TOKEN_ZH
    elif zh_ratio > 0.1:
        chars_per_token = CHARS_PER_TOKEN_MIXED
    else:
        chars_per_token = CHARS_PER_TOKEN_EN
    return max(1, int(len(text) / chars_per_token))


def _estimate_chars_per_token(text: str) -> float:
    """根据文本的中文比例估算每 token 对应的字符数。

    与 _estimate_tokens 逻辑一致，但返回每 token 字符数而非 token 总数。
    空文本返回英文字符系数（作为安全默认值）。
    """
    if not text:
        return CHARS_PER_TOKEN_EN
    zh_chars = sum(1 for c in text if "一" <= c <= "鿿")
    zh_ratio = zh_chars / max(len(text), 1)
    if zh_ratio > 0.3:
        return CHARS_PER_TOKEN_ZH
    if zh_ratio > 0.1:
        return CHARS_PER_TOKEN_MIXED
    return CHARS_PER_TOKEN_EN


def chunk_text(
    text: str,
    max_tokens: int = 2048,
    overlap_tokens: int = 128,
    strategy: str = "sentence",
    skip_references: bool = True,
) -> list[Chunk]:
    """将文本切分为多个块

    Args:
        text: 清洗后的文本
        max_tokens: 每块最大 token 数
        overlap_tokens: 块间重叠 token 数
        strategy: 切块策略 - sentence | paragraph | fixed
        skip_references: 是否跳过引用区不切块

    Returns:
        Chunk 列表（不含引用区）
    """
    result = chunk_text_full(text, max_tokens, overlap_tokens, strategy, skip_references)
    return result.chunks


def chunk_text_full(
    text: str,
    max_tokens: int = 2048,
    overlap_tokens: int = 128,
    strategy: str = "sentence",
    skip_references: bool = True,
) -> ChunkResult:
    """完整切块，返回引用区原文

    Args:
        text: 清洗后的文本（Cleaner 已移除引用区）
        max_tokens: 每块最大 token 数
        overlap_tokens: 块间重叠 token 数
        strategy: 切块策略 - sentence | paragraph | fixed
        skip_references: 是否尝试分离引用区（Cleaner 通常已处理）

    Returns:
        ChunkResult 包含 chunks 和 references_text
    """
    body_text = text
    references_text = ""

    # Cleaner 通常已在清洗阶段移除引用区，这里做二次安全检测
    if skip_references:
        body_text, references_text = _split_references(text)

    if not body_text.strip():
        return ChunkResult(chunks=[], references_text=references_text)

    if strategy == "sentence":
        segments = _split_sentences(body_text)
    elif strategy == "paragraph":
        segments = _split_paragraphs(body_text)
    elif strategy == "fixed":
        chars_per_token = _estimate_chars_per_token(body_text)
        segments = _split_fixed(body_text, chunk_chars=int(max_tokens * chars_per_token))
    else:
        raise ValueError(f"未知切块策略: {strategy}")

    # 句法感知切分: 对超长句子在从句边界二次切分
    chars_per_token = _estimate_chars_per_token(" ".join(segments))
    max_chars = int(max_tokens * chars_per_token)
    # 只对超过 80% max_tokens 的句子二次切分
    threshold = int(max_chars * 0.8)
    final_segments: list[str] = []
    for seg in segments:
        if len(seg) > threshold:
            split_parts = _split_long_sentence(seg, threshold)
            final_segments.extend(split_parts)
        else:
            final_segments.append(seg)
    segments = final_segments

    chunks = _merge_segments(segments, max_tokens, overlap_tokens)
    return ChunkResult(chunks=chunks, references_text=references_text)


# ---------------------------------------------------------------------------
# 引用区分离
# ---------------------------------------------------------------------------

_REFERENCE_PATTERNS: list[str] = []  # 延迟初始化，避免循环导入


def _ensure_reference_patterns() -> list[str]:
    """延迟初始化引用区正则模式（避免模块导入时的循环依赖）"""
    global _REFERENCE_PATTERNS
    if not _REFERENCE_PATTERNS:
        from src.constants import REFERENCE_SECTION_PATTERNS
        _REFERENCE_PATTERNS = [r"^" + p + r"\s*$" for p in REFERENCE_SECTION_PATTERNS]
    return _REFERENCE_PATTERNS


def _split_references(text: str) -> tuple[str, str]:
    """将正文和引用区拆分（查找最后一个匹配，避免误截多篇文章）

    Returns:
        (body_text, references_text)
    """
    patterns = _ensure_reference_patterns()
    best_pos = -1
    for pattern in patterns:
        for m in re.finditer(pattern, text, re.MULTILINE | re.IGNORECASE):
            if m.start() > best_pos:
                best_pos = m.start()

    if best_pos >= 0:
        body = text[:best_pos].rstrip()
        refs = text[best_pos:]
        # 如果"引用区"占比过大（>50%），可能是多篇文章误判，不切割
        if len(refs) > len(text) * 0.5:
            return text, ""
        return body, refs
    return text, ""


# ---------------------------------------------------------------------------
# 切块策略
# ---------------------------------------------------------------------------

# 常见学术缩写，这些缩写后的句号不代表句子结束
_ACADEMIC_ABBREVS = [
    "et al", "etc", "fig", "figs", "eq", "eqs", "ref", "refs",
    "vol", "no", "pp", "cf", "e.g", "i.e", "vs",
    "ed", "eds", "rev", "proc", "inst", "dept", "univ",
    "sci", "tech", "phys", "chem", "biol", "med",
    "hum", "evol", "anthrop", "soc", "pol", "econ", "psych",
    "nat", "int", "inc", "ltd", "co", "st", "dr", "mr", "mrs",
    "prof", "sr", "jr", "ph", "dc", "ba", "ma",
    "approx", "max", "min", "avg", "std", "var",
    "def", "thm", "lem", "cor", "prop",
]


def _split_sentences(text: str) -> list[str]:
    """按句子拆分文本，保护学术缩写不被误切

    处理步骤:
    1. 保护单字母缩写 (A. B. C. 等)
    2. 保护已知学术缩写 (et al. Fig. Vol. 等)
    3. 按句子边界切分
    4. 还原占位符
    5. 合并过短碎片
    """
    placeholders: list[str] = []
    protected = text

    # 保护单字母 + 句号 (人名首字母 J. A. 等)
    protected = re.sub(
        r"\b([A-Z])\.\s",
        lambda m: _ph(m.group(0), placeholders),
        protected,
    )

    # 保护已知缩写 + 句号
    for abbr in _ACADEMIC_ABBREVS:
        protected = re.sub(
            rf"\b{abbr}\.\s",
            lambda m: _ph(m.group(0), placeholders),
            protected,
            flags=re.IGNORECASE,
        )

    # 保护数字 + 句号 (如 "10.5", "3.14")
    protected = re.sub(
        r"(\d)\.(\d)",
        lambda m: _ph(m.group(0), placeholders),
        protected,
    )

    # 按句子边界切分: 句号/问号/感叹号后跟空格或换行
    parts = re.split(r"(?<=[.!?])\s+", protected)

    # 还原占位符 — 从后向前替换，避免索引低的占位符文本内嵌套高索引标记
    sentences = []
    for p in parts:
        restored = p.strip()
        for i in range(len(placeholders) - 1, -1, -1):
            restored = restored.replace(f"\x00PH{i}\x00", placeholders[i])
        if restored:
            sentences.append(restored)

    # 合并过短碎片 (< 20 字符且不以大写开头)
    merged: list[str] = []
    for s in sentences:
        if merged and len(s) < 20 and not re.match(r"^[A-Z]", s):
            merged[-1] += " " + s
        else:
            merged.append(s)

    return [s for s in merged if s.strip()]


def _ph(match_text: str, placeholders: list[str]) -> str:
    """创建占位符保护缩写不被切分"""
    idx = len(placeholders)
    placeholders.append(match_text)
    return f"\x00PH{idx}\x00"


def _split_paragraphs(text: str) -> list[str]:
    """按段落拆分文本"""
    parts = text.split("\n\n")
    return [p.strip() for p in parts if p.strip()]


def _split_fixed(text: str, chunk_chars: int) -> list[str]:
    """按固定字符数拆分，尽量在句子边界处切割

    chunk_chars 会根据文本中中文比例自动调整。
    """
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_chars
        if end >= len(text):
            chunk = text[start:].strip()
            if chunk:
                chunks.append(chunk)
            break
        # 在 chunk_chars 范围内找最后一个句子边界
        boundary = -1
        for sep in (". ", "! ", "? ", "。", "！", "？", "\n"):
            pos = text.rfind(sep, start, end)
            if pos > boundary:
                boundary = pos
        if boundary > start:
            end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end
    return chunks


def _merge_segments(
    segments: list[str],
    max_tokens: int,
    overlap_tokens: int,
) -> list[Chunk]:
    """将小片段合并为大块，控制 token 上限，重叠保持完整句子"""
    if not segments:
        return []

    # 根据文本内容动态计算每 token 对应字符数
    full_text = " ".join(segments)
    chars_per_token = _estimate_chars_per_token(full_text)
    max_chars = int(max_tokens * chars_per_token)
    overlap_chars = int(overlap_tokens * chars_per_token)

    chunks: list[Chunk] = []
    current_parts: list[str] = []
    current_len = 0
    idx = 0

    for seg in segments:
        seg_len = len(seg)
        # 单个片段就超限 → 独立成块
        if seg_len > max_chars:
            if current_parts:
                chunks.append(_make_chunk(idx, current_parts))
                idx += 1
                current_parts = []
                current_len = 0
            chunks.append(_make_chunk(idx, [seg]))
            idx += 1
            continue

        if current_len + seg_len + 1 > max_chars and current_parts:
            chunks.append(_make_chunk(idx, current_parts))
            idx += 1
            # 重叠: 保留末尾完整的句子 (从后往前找足够长的一段)
            current_parts = _get_overlap_parts(current_parts, overlap_chars)
            current_len = sum(len(p) for p in current_parts) + len(current_parts)

        current_parts.append(seg)
        current_len += seg_len + 1

    if current_parts:
        chunks.append(_make_chunk(idx, current_parts))

    return chunks


def _get_overlap_parts(parts: list[str], overlap_chars: int) -> list[str]:
    """从已有片段中取末尾的完整句子作为重叠上下文"""
    if overlap_chars <= 0 or not parts:
        return []

    # 从后往前累加，直到超过 overlap_chars
    overlap: list[str] = []
    total = 0
    for p in reversed(parts):
        if total + len(p) >= overlap_chars and overlap:
            break
        overlap.insert(0, p)
        total += len(p) + 1

    return overlap


def _make_chunk(index: int, parts: list[str]) -> Chunk:
    """创建一个 Chunk"""
    text = " ".join(parts)
    return Chunk(
        index=index,
        text=text,
        char_count=len(text),
        estimated_tokens=_estimate_tokens(text),
    )


# ---------------------------------------------------------------------------
# 类型化块解析（block-aware）
# ---------------------------------------------------------------------------

# 内部占位符前缀，用于在分段前保护跨段公式/代码块
_PROTECT_PREFIX = "\x01BLOCK"
_PROTECT_SUFFIX = "\x01"

# 段落级启发式：标题判定阈值（字符数）
_HEADING_MAX_CHARS = 100
_HEADING_PUNCT_END = ".!?。！？:;；,"


def _heading_level_from_marker(line: str) -> int:
    """识别 markdown 标题标记 (#, ##...)，返回级别；不是标题返回 0"""
    m = re.match(r"^(#{1,6})\s+\S", line)
    return len(m.group(1)) if m else 0


def _looks_like_pdf_heading(text: str) -> int:
    """启发式识别 PDF 提取后无 markdown 标记的标题

    返回级别 (1-3)；不是标题返回 0。

    判据：
    - 单行（无内部换行）
    - 长度 < _HEADING_MAX_CHARS
    - 不以句末标点结尾
    - 满足以下任一：
        * 形如 "1." / "1.1" / "1.2.3" / "II." 编号开头
        * 全大写 ASCII 词组（如 "ABSTRACT", "INTRODUCTION", "METHODS"）
        * 标题大小写（每个实词首字母大写）且词数 <= 10
    """
    s = text.strip()
    if not s or "\n" in s or len(s) > _HEADING_MAX_CHARS:
        return 0

    # 排除: 含 "F. Last" 模式（人名如 "Laurie S. Huning"）
    if re.search(r"\b[A-Z]\.\s+[A-Z][a-z]+\b", s):
        return 0

    if s[-1] in _HEADING_PUNCT_END:
        # 允许 "1. Introduction" 这种以 "." 在编号后的形式
        if not re.match(r"^\d+(\.\d+)*\.?\s+\S", s):
            return 0

    # 编号式: "1. Introduction" / "2.1 Methods" / "II. Background"
    m = re.match(r"^(\d+(?:\.\d+)*)\.?\s+(.+)$", s)
    if m:
        depth = m.group(1).count(".") + 1
        return min(depth, 3)
    if re.match(r"^[IVXLCDM]+\.?\s+\S", s):
        return 1

    # 全大写 ASCII（学术文档常见 H1）
    ascii_letters = sum(1 for c in s if c.isascii() and c.isalpha())
    if ascii_letters >= 4 and ascii_letters / max(1, sum(1 for c in s if c.isalpha())) > 0.95:
        if s.upper() == s and len(s.split()) <= 8:
            return 1

    # Title Case: "Conclusions and Future Work"
    words = s.split()
    if 1 < len(words) <= 10:
        capitalized = sum(1 for w in words if w[:1].isupper())
        if capitalized / len(words) >= 0.7:
            return 2

    return 0


def _looks_like_table(text: str) -> bool:
    """识别 markdown 表格：第一行多 |，第二行是分隔符"""
    lines = text.split("\n")
    if len(lines) < 2:
        return False
    first = lines[0].strip()
    second = lines[1].strip()
    return first.count("|") >= 2 and bool(re.match(r"^\|?[\s\-:|]+\|?$", second)) and "-" in second


def _looks_like_list(text: str) -> bool:
    """识别项目符号列表（首行为列表项即认为整段是列表）"""
    first = text.split("\n", 1)[0].strip()
    return bool(re.match(r"^[\-*•]\s+\S", first) or re.match(r"^\d+\.\s+\S", first))


def _looks_like_figure_caption(text: str) -> bool:
    """识别图表标注：'Figure 1' / 'Fig. 1' / 'Table 1' 起始"""
    first = text.split("\n", 1)[0].strip()
    return bool(re.match(r"^(?:Figure|Fig\.?|Table|图|表)\s*\d+[.:：\s]", first, re.IGNORECASE))


def parse_blocks(text: str) -> list[Block]:
    """将清洗后的文本解析为类型化块序列

    支持类型: paragraph / heading / formula / code / table / list / figure_caption

    跨段块（公式、代码）会被先行保护，避免被段落分隔切碎。
    """
    if not text or not text.strip():
        return []

    # 第一步：保护跨段块（用占位符替换内容）
    protected = text
    saved: dict[str, tuple[str, str]] = {}  # placeholder -> (type, content)
    counter = [0]

    def _protect(content: str, type_: str) -> str:
        ph = f"{_PROTECT_PREFIX}{counter[0]}{_PROTECT_SUFFIX}"
        saved[ph] = (type_, content)
        counter[0] += 1
        return ph

    # 代码块: ``` ... ```
    protected = re.sub(
        r"```[\s\S]*?```",
        lambda m: _protect(m.group(0), BLOCK_CODE),
        protected,
    )
    # 公式块: $$ ... $$
    protected = re.sub(
        r"\$\$[\s\S]*?\$\$",
        lambda m: _protect(m.group(0), BLOCK_FORMULA),
        protected,
    )
    # 公式块: \[ ... \]
    protected = re.sub(
        r"\\\[[\s\S]*?\\\]",
        lambda m: _protect(m.group(0), BLOCK_FORMULA),
        protected,
    )
    # 公式环境: \begin{xxx} ... \end{xxx}
    protected = re.sub(
        r"\\begin\{(\w+)\}[\s\S]*?\\end\{\1\}",
        lambda m: _protect(m.group(0), BLOCK_FORMULA),
        protected,
    )

    # 第二步：按空行分段
    paragraphs = re.split(r"\n{2,}", protected)

    blocks: list[Block] = []
    bid = 0

    def _next_id() -> str:
        nonlocal bid
        i = bid
        bid += 1
        return f"b{i:04d}"

    for para in paragraphs:
        p = para.strip()
        if not p:
            continue

        # 还原占位符（如果整段恰好就是一个占位符 → 独立块）
        if p in saved:
            type_, content = saved[p]
            blocks.append(Block(_next_id(), type_, content.strip(), translatable=False))
            continue

        # 段落里嵌入的占位符也要还原（极少见但兼容处理）
        if _PROTECT_PREFIX in p:
            for ph, (_, content) in saved.items():
                p = p.replace(ph, content)

        # 类型识别（顺序很重要：先识别强模式，再 fallback 段落）
        # 1. markdown 标题
        lvl = _heading_level_from_marker(p)
        if lvl:
            blocks.append(Block(_next_id(), BLOCK_HEADING, p, level=lvl))
            continue

        # 2. 表格
        if _looks_like_table(p):
            blocks.append(Block(_next_id(), BLOCK_TABLE, p, translatable=False))
            continue

        # 3. PDF 启发式标题（无 markdown 标记的）
        # 必须在列表检测之前——"1. Introduction" 同时匹配两者，标题优先
        h = _looks_like_pdf_heading(p)
        if h:
            blocks.append(Block(_next_id(), BLOCK_HEADING, p, level=h))
            continue

        # 4. 列表（保持整段为一块，便于翻译时上下文）
        if _looks_like_list(p):
            blocks.append(Block(_next_id(), BLOCK_LIST, p))
            continue

        # 5. 图表标注
        if _looks_like_figure_caption(p):
            blocks.append(Block(_next_id(), BLOCK_FIGURE_CAPTION, p))
            continue

        # 6. 普通段落
        blocks.append(Block(_next_id(), BLOCK_PARAGRAPH, p))

    return blocks


def pack_blocks_into_chunks(
    blocks: list[Block],
    max_tokens: int = 2048,
    overlap_tokens: int = 128,
) -> list[BlockChunk]:
    """将块序列打包成翻译 chunk，保持块完整性

    规则：
    - 块边界永远不切断（即使单块超长也独立成 chunk）
    - 同 chunk 内块用 \\n\\n 分隔，便于 LLM 保持段落结构
    - 重叠以"块"为单位，不切句子
    """
    if not blocks:
        return []

    if overlap_tokens > 0:
        import logging
        logging.getLogger(__name__).warning(
            "overlap_tokens=%d 在 block-aware 模式下可能导致重复翻译，建议设置 overlap_tokens=0",
            overlap_tokens,
        )

    full_text = "\n\n".join(b.text for b in blocks)
    chars_per_token = _estimate_chars_per_token(full_text)
    max_chars = int(max_tokens * chars_per_token)
    overlap_chars = int(overlap_tokens * chars_per_token)

    chunks: list[BlockChunk] = []
    current: list[Block] = []
    current_chars = 0
    idx = 0

    def _flush_with_overlap() -> None:
        nonlocal current, current_chars, idx
        if not current:
            return
        text = "\n\n".join(b.text for b in current)
        chunks.append(BlockChunk(
            index=idx,
            text=text,
            char_count=len(text),
            estimated_tokens=_estimate_tokens(text),
            block_ids=[b.id for b in current],
        ))
        idx += 1
        # 取末尾若干完整块作为下一 chunk 的 overlap
        if overlap_chars > 0:
            tail: list[Block] = []
            total = 0
            for b in reversed(current):
                if total + len(b.text) > overlap_chars and tail:
                    break
                tail.insert(0, b)
                total += len(b.text) + 2
            current = tail
            current_chars = total
        else:
            current = []
            current_chars = 0

    for block in blocks:
        block_chars = len(block.text)
        # 单块超限：先 flush 当前，再让超长块独占一 chunk
        if block_chars > max_chars:
            if current:
                _flush_with_overlap()
                current = []  # overlap 也清空，避免继续传播
                current_chars = 0
            chunks.append(BlockChunk(
                index=idx,
                text=block.text,
                char_count=block_chars,
                estimated_tokens=_estimate_tokens(block.text),
                block_ids=[block.id],
            ))
            idx += 1
            continue

        # 加上这块会超 → 先 flush
        if current and current_chars + block_chars + 2 > max_chars:
            _flush_with_overlap()

        current.append(block)
        current_chars += block_chars + 2  # +2 for "\n\n"

    if current:
        # 最后一段：避免重复 overlap 段
        text = "\n\n".join(b.text for b in current)
        chunks.append(BlockChunk(
            index=idx,
            text=text,
            char_count=len(text),
            estimated_tokens=_estimate_tokens(text),
            block_ids=[b.id for b in current],
        ))

    return chunks


def chunk_text_with_blocks(
    text: str,
    max_tokens: int = 2048,
    overlap_tokens: int = 128,
    skip_references: bool = True,
) -> BlockChunkResult:
    """块感知切块——返回 (blocks, chunks, references)

    与传统 chunk_text_full 的区别：
    - 输出附带类型化块序列，每块有稳定 id 用于翻译后对齐
    - chunk 由完整块组成，不会跨段切割
    - 翻译器和前端都基于 blocks 做对齐渲染，告别"猜句子"

    兼容性：旧的 chunk_text / chunk_text_full 仍可用。
    """
    body_text = text
    references_text = ""

    if skip_references:
        body_text, references_text = _split_references(text)

    if not body_text.strip():
        return BlockChunkResult(blocks=[], chunks=[], references_text=references_text)

    blocks = parse_blocks(body_text)
    chunks = pack_blocks_into_chunks(blocks, max_tokens, overlap_tokens)
    return BlockChunkResult(blocks=blocks, chunks=chunks, references_text=references_text)
