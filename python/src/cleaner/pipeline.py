"""文本清洗流水线 - 处理 PDF 提取后的格式问题"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CleanResult:
    """清洗结果"""

    text: str
    has_references: bool
    references_start: int  # 引用区在 text 中的起始位置 (-1 表示无)
    references_text: str  # 引用区原文


def clean_text(raw_text: str) -> str:
    """清洗 PDF 提取的原始文本（向后兼容的快捷方法）

    Args:
        raw_text: PDF 提取的原始文本

    Returns:
        清洗后的文本
    """
    return clean_text_full(raw_text).text


def clean_text_full(raw_text: str) -> CleanResult:
    """完整清洗，返回结构化结果

    处理步骤:
    1. 过滤水印文本
    2. 合并被断行打断的单词 (连字符断词)
    3. 合并同段落内的换行
    4. 规范化空白字符
    5. 移除页码标记
    6. 检测引用区
    6.7. 移除短噪声碎片 (图标签/坐标轴/列标题残留)
    7. 恢复段落分隔
    """
    text = raw_text

    # 1. 过滤水印
    text = _remove_watermarks(text)

    # 1.5 移除 PDF 编码残留 (cid:N)
    text = _remove_cid_artifacts(text)

    # 1.6 移除反向文字和图片标注碎片
    text = _remove_figure_artifacts(text)

    # 1.7 修复双栏提取导致的词内空格: "E pigenetic" → "Epigenetic"
    text = _fix_intra_word_spaces(text)

    # 2. 处理连字符断词: "infor-\nmation" → "information"
    # 必须在 _fix_concatenated_words 之前，因为去断字可能产出新的长连词
    text = _fix_hyphenation(text)

    # 2.5 修复 PDF 无空格提取后的残留长连词
    text = _fix_concatenated_words(text)

    # 3. 合并段落内换行
    text = _merge_paragraph_lines(text)

    # 4. 规范化空白
    text = _normalize_whitespace(text)

    # 5. 移除独立页码行
    text = _remove_page_numbers(text)

    # 6. 移除脚注、致谢、注释等非正文段落
    text = _remove_annotations(text)

    # 6.5 移除孤立编码字符 (ó, ñ 等非正文 Unicode 残留)
    text = _remove_orphan_unicode(text)

    # 6.6 移除期刊页脚 (版权、DOI、文章链接等)
    text = _remove_journal_footer(text)

    # 6.7 移除短噪声碎片（图标签、坐标轴标注、列标题残留等）
    text = _remove_noise_fragments(text)

    # 7. 压缩连续空行
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 8. 检测引用区 → 直接从正文中删除，不翻译、不显示
    ref_pos, ref_text = _detect_references(text)
    if ref_pos >= 0:
        text = text[:ref_pos].rstrip()

    # 8.5 移除末尾残留的期刊元数据（文章标题+作者+DOI 等引用格式行）
    text = _remove_trailing_citation(text)

    # 9. 修复首词截断（含段内截断词）
    text = _fix_truncated_first_word(text)
    text = _fix_truncated_words_in_text(text)

    return CleanResult(
        text=text.strip(),
        has_references=ref_pos >= 0,
        references_start=ref_pos,
        references_text=ref_text,
    )


# ---------------------------------------------------------------------------
# 引用区检测
# ---------------------------------------------------------------------------

# 直接内联 patterns，避免模块缓存导致的常量版本不一致
# 普通字符串中 \\s 在 regex 里是 \s（空白符），可匹配单/多个空格
_REFERENCE_PATTERNS = [
    "REFERENCES\\s+AND\\s+NOTES",
    "REFERENCES",
    "BIBLIOGRAPHY",
    "LITERATURE\\s+CITED",
    "WORKS\\s+CITED",
    "SUPPLEMENTARY\\s+MATERIALS",
]


def _detect_references(text: str) -> tuple[int, str]:
    """检测引用区起始位置（查找最后一个匹配，避免误截多篇文章）

    验证逻辑：匹配行后必须紧跟引用格式行（如 [1] Author, Journal Year）
    避免误删正文中出现的 "REFERENCES" 关键词。

    Returns:
        (position, reference_text) — position 为 -1 表示未检测到
    """
    best_pos = -1
    lines = text.split("\n")
    for pattern in _REFERENCE_PATTERNS:
        for i, line in enumerate(lines):
            stripped = line.strip()
            # 允许 \s 匹配空白（单/多个空格），但必须是完整词匹配
            # 用 re.match 匹配行首，避免子串误匹配（如 "no references" 中的 "references"）
            if re.match(pattern, stripped, re.IGNORECASE):
                # 验证：检查后面几行是否像引用条目
                if _looks_like_reference_section(lines, i):
                    line_start = sum(len(l) + 1 for l in lines[:i])
                    if line_start > best_pos:
                        best_pos = line_start

    if best_pos >= 0:
        return best_pos, text[best_pos:]
    return -1, ""


def _looks_like_reference_section(lines: list[str], header_idx: int) -> bool:
    """验证 header 行后面是否真的是引用条目

    引用条目特征：
    - 数字开头: "[1]" 或 "1."
    - 或包含年份: "(2020)" 或 "2020."
    - 或包含期刊/会议名模式: "vol.", "pp.", "doi:", 等
    - 或以大写字母开头的条目（如 "Figure S1.", "Item 1."）
    - 至少 1 行符合引用模式即可（宽松模式以适应短引用列表）
    """
    # 检查后续 10 行内至少有 1 行像引用
    for i in range(header_idx + 1, min(header_idx + 11, len(lines))):
        line = lines[i].strip()
        if not line:
            continue
        # 引用条目模式
        if re.match(r"^\[\d+\]", line):  # [1] Author
            return True
        if re.match(r"^\d{1,3}\.", line):  # 1. Author
            return True
        if re.match(r"^[A-Z][a-z]+\s+\d+\.", line):  # Item 1.
            return True
        if re.match(r"^[A-Z][a-z]+\s+S\d+\.", line):  # Figure S1.
            return True
        if re.search(r"\(\d{4}[a-z]?\)", line):  # (2020) or (2020a)
            return True
        if re.search(r"\b\d{4}\.", line):  # 2020. Author
            return True
        if re.search(r"\bvol\.?\s+\d+", line, re.IGNORECASE):
            return True
        if re.search(r"\bpp\.?\s+\d+", line, re.IGNORECASE):
            return True
        if re.search(r"\bdoi:\s*10\.", line, re.IGNORECASE):
            return True

    return False


# ---------------------------------------------------------------------------
# 水印过滤
# ---------------------------------------------------------------------------

_WATERMARK_PATTERNS = [
    r"^\d+\s+\d+\s+\w+\s+\d{4}\s+Science$",
    r"^\w+\s+\d{4}\s+Science\s+Vol\s+\d+.*$",
    r"^Science\s+\d+.*$",
    r"^PERSPECTIVES$",
    r"^REVIEW$",
    r"^RESEARCH\s+ARTICLE$",
    r"^REPORTS$",
    # ACM 期刊页眉: "Proc. ACM Manag. Data, Vol. 2, No. 1 (SIGMOD), Article 62. ..."
    r"^Proc\.\s+ACM\s+.*$",
    # ACM 期刊页码: "62:3" 或 "62:22 Jiaming Liang, ..."
    r"^\d+:\d+\s+.*$",
]


def _remove_watermarks(text: str) -> str:
    """移除水印和期刊页眉噪声"""
    # 处理多行分散的 "Downloaded from ... on ..." 水印
    # 模式: "Downloaded\nfrom\nurl\nat\nInstitute\n...\non\nMarch\n28,\n2026"
# 修复: 移除 DOTALL（.+? 会跨行贪婪匹配，误删正文）
    text = re.sub(
        r"Downloaded\s+from\s+[^\n]+\s+on\s+\w+\s+\d+[^\n]*",
        "", text,
    )
    # 多行变体: 每个词一行 (Science 期刊常见)
    text = re.sub(
        r"^Downloaded\s*$\n^from\s*$\n.+?\n^on\s*$\n(?:.+\n)*?\d{4}\s*$",
        "", text, flags=re.MULTILINE,
    )
    for pattern in _WATERMARK_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.MULTILINE)
    return text


def _remove_cid_artifacts(text: str) -> str:
    """移除 PDF CID 编码残留，如 (cid:0)、(cid:123)"""
    text = re.sub(r"\(cid:\d+\)", "", text)
    return text


def _remove_figure_artifacts(text: str) -> str:
    """移除图片区域提取的反向文字和标注碎片

    典型模式:
    1. 反向 ALL-CAPS 行: "TCUDORP", "EKOMS", "METSYS" 等
    2. 图片标注碎片: "GREENLAND", "CANADA", "UNITEDSTATES" 等孤立的地理名
    3. 图片版权标注: ")CIHPARG(", ":STIDERC", ")ATAD(" 等
    """
    # 常见反向文字词表（正向）
    _REVERSE_WORDS = {
        "PRODUCT", "SMOKE", "AND", "FIRE", "SYSTEM", "MAPPING", "HAZARD",
        "NOAA", "INC", "CENTRE", "FOREST", "INTERAGENCY", "CANADIAN",
        "DATA", "SCIENCE", "PENNEY", "GRAPHIC", "CREDITS",
    }

    # 地理标注词（图片中的地图标签）
    _GEO_LABELS = {
        "GREENLAND", "CANADA", "UNITEDSTATES", "UNITED STATES",
        "ALASKA", "MEXICO", "ATLANTIC", "PACIFIC",
    }

    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append(line)
            continue

        # 检测 1: 纯大写 ASCII 单词行 — 反向后匹配已知词表
        if stripped.isupper() and stripped.isalpha() and len(stripped) >= 3:
            reversed_text = stripped[::-1]
            if reversed_text in _REVERSE_WORDS or stripped in _REVERSE_WORDS:
                continue  # 跳过反向文字

        # 检测 2: 含括号/标点的反向标注 (如 ")CIHPARG(", ":STIDERC", ")ATAD(")
        if stripped.startswith(")") or stripped.startswith(":"):
            no_punct = re.sub(r"[^A-Za-z]", "", stripped)
            if no_punct.isupper() and no_punct[::-1] in _REVERSE_WORDS:
                continue

        # 检测 3: 孤立的地理标注（独立一行，纯大写地理名）
        if stripped.upper().replace(" ", "") in _GEO_LABELS:
            continue

        # 检测 4: 混合反向标注+标点 (如 ",.CNI")
        alpha_only = re.sub(r"[^A-Za-z]", "", stripped)
        if alpha_only.isupper() and alpha_only[::-1] in _REVERSE_WORDS:
            continue

        cleaned.append(line)

    return "\n".join(cleaned)


def _remove_orphan_unicode(text: str) -> str:
    """移除孤立的非正文 Unicode 字符（如 ó ó、ñ 等编码残留）

    匹配: 独立一行只有 1-3 个非 ASCII 字符，且不是中日韩文字
    """
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append(line)
            continue
        # 检测: 短行(<=5字符)且全是非ASCII非CJK字符
        non_ascii = sum(1 for c in stripped if ord(c) > 127)
        cjk = sum(1 for c in stripped if "\u4e00" <= c <= "\u9fff")
        if len(stripped) <= 5 and non_ascii > 0 and cjk == 0:
            continue  # 跳过孤立编码字符行
        cleaned.append(line)
    return "\n".join(cleaned)


def _remove_journal_footer(text: str) -> str:
    """移除期刊页脚版权信息、文章链接等

    常见模式:
    - "View the article online https://..."
    - "Permissions https://..."
    - "Use of this article is subject to..."
    - "Science (ISSN ...) is published by..."
    """
    footer_patterns = [
        r"^View\s+the\s+article\s+online\s+https?://.*$",
        r"^Permissions\s+https?://.*$",
        r"^Use\s+of\s+this\s+article\s+is\s+subject\s+to.*$",
        r"^(?:Science|Nature|Cell)\s+\(ISSN\s+\d+-\d+\)\s+is\s+published\s+by.*$",
        r"^Copyright\s+©.*$",
        r"^doi:\s*10\.\d{4,}.*$",
        r"^https?://(?:www\.)?(?:science|nature|cell)\.org/.*$",
        r"^Washington,\s+DC\s+\d{5}\.\s+.*(?:trademark|AAAS).*$",
        r"^The\s+title\s+Science\s+is\s+a\s+registered\s+trademark.*$",
    ]
    for pattern in footer_patterns:
        text = re.sub(pattern, "", text, flags=re.MULTILINE | re.IGNORECASE)
    return text


def _remove_noise_fragments(text: str) -> str:
    """移除 PDF 提取产生的短噪声段落（图标签、坐标轴碎片、列标题残留等）

    典型模式（独立成段）:
    - "ITE" — 坐标轴标签碎片
    - "D S" — 双栏列表碎片
    - "TAT" — 标注残留
    - "EMD" — 各类缩写碎片
    """
    paragraphs = text.split("\n\n")
    filtered = []
    for para in paragraphs:
        stripped = para.strip()
        if stripped and _is_noise_fragment(stripped):
            logger.debug("移除噪声碎片段落: %r", stripped[:40])
            continue
        filtered.append(para)
    return "\n\n".join(filtered)


# 已知有意义的短大写词（章节标题、通用缩写等），不视为噪声
_MEANINGFUL_CAPS = frozenset({
    # 章节标题
    "ABSTRACT", "INTRODUCTION", "METHODS", "METHOD", "RESULTS", "RESULT",
    "DISCUSSION", "CONCLUSION", "CONCLUSIONS", "REFERENCES", "APPENDIX",
    "APPENDICES", "BACKGROUND", "MOTIVATION", "OVERVIEW", "SUMMARY",
    "RELATED", "ACKNOWLEDGMENTS", "ACKNOWLEDGEMENTS", "FUNDING",
    "NOTES", "NOTE", "SUPPLEMENTARY", "SUPPORTING", "LIMITATIONS",
    # 表格 / 图
    "TABLE", "FIGURE", "FIGURES", "TABLES", "BOX", "FIG",
    # 常见学科缩写
    "DNA", "RNA", "PCR", "MRI", "CT", "PET", "NMR", "UV", "IR",
    "USA", "UK", "EU", "UN", "WHO", "CDC",
    # 常见英文词（偶尔独立成段）
    "THE", "AND", "OR", "NOT", "BUT",
})


def _is_noise_fragment(text: str) -> bool:
    """判断一个段落是否为 PDF 提取的噪声碎片

    条件（全部满足才判定为噪声）:
    1. 单行（无换行），长度 ≤ 20 字符
    2. 不含中文、数字、标点
    3. 全大写字母（可含空格）
    4. 去空格后字母数 ≤ 10
    5. 不在已知有意义词表中
    """
    if "\n" in text:
        return False
    if len(text) > 20:
        return False
    if any("一" <= c <= "鿿" for c in text):
        return False
    if any(c.isdigit() for c in text):
        return False
    # 含标点（句号、括号、连字符等）通常有意义
    if re.search(r"[^\w\s]", text):
        return False

    alpha_only = text.replace(" ", "")
    if not alpha_only or not alpha_only.isalpha() or not alpha_only.isupper():
        return False
    if len(alpha_only) > 10:
        return False

    if text.strip().upper() in _MEANINGFUL_CAPS:
        return False

    return True


def _fix_intra_word_spaces(text: str) -> str:
    """修复双栏 PDF 提取导致的词内空格

    典型模式: "E pigenetic" → "Epigenetic", "T he" → "The", "C owley" → "Cowley"
    发生原因: pdfplumber 在双栏模式下，首字母与后续字母被识别为两个独立 word
    """
    # 匹配: 行首或空格后，一个大写字母 + 空格 + 2+个小写字母（看起来像一个被拆开的单词）
    text = re.sub(
        r"(?<=\s)([A-Z])\s([a-z]{2,})",
        lambda m: m.group(1) + m.group(2)
        if _looks_like_merged_word(m.group(1) + m.group(2))
        else m.group(0),
        text,
    )
    # 行首的情况
    text = re.sub(
        r"^([A-Z])\s([a-z]{2,})",
        lambda m: m.group(1) + m.group(2)
        if _looks_like_merged_word(m.group(1) + m.group(2))
        else m.group(0),
        text,
        flags=re.MULTILINE,
    )
    # 小写字母 + 空格 + 小写字母：只处理明确的截断词（"ccompanied" → "accompanied"）
    _KNOWN_LOWER_BREAKS = {
        "a ccompanied": "accompanied",
    }
    for broken, fixed in _KNOWN_LOWER_BREAKS.items():
        text = text.replace(broken, fixed)
    return text


def _looks_like_merged_word(word: str) -> bool:
    """判断合并后的词是否像合法英文单词

    策略: 排除冠词 A 误合并；只合并大写非冠词字母开头的拆分词
    """
    # 不合并冠词 A + 空格 + 单词 的情况
    # 这些是合法的 "A different", "A major" 等短语
    if len(word) >= 3 and word[0] == 'A':
        # "A" + lowercase word → 不合并（冠词+名词/形容词）
        # 但 "Accompanied" 这种实际拆分的词需要合并
        # 简单策略: 如果第二部分本身不像合法英文单词(以辅音开头且短),
        # 则合并；否则不合并
        rest = word[1:]  # 去掉 A 后的部分
        if rest and rest[0].islower():
            # "Adifferent" vs "Accompanied"
            # 如果rest是一个常见英文词，不合并
            if _is_common_english_word(rest):
                return False
    if len(word) >= 3:
        return True
    return False


# 常见英文单词（用于判断 "A xxx" 是否为冠词短语）
_COMMON_WORDS = frozenset({
    "different", "major", "single", "recent", "simple", "common", "critical",
    "key", "large", "small", "specific", "novel", "better", "wide", "new",
    "given", "global", "result", "more", "database", "chain", "positive",
    "given", "local", "myriad", "drought", "groundwater", "wildfire",
    "shift", "stem", "hominid", "crown", "ban", "combination",
    "niche", "specific", "chromatin", "mouse",
    "about", "above", "after", "again", "being", "below", "between",
    "both", "certain", "each", "few", "first", "great", "having",
    "here", "into", "just", "last", "long", "many", "most", "much",
    "never", "next", "only", "other", "over", "part", "same", "some",
    "such", "than", "that", "their", "them", "then", "there", "these",
    "they", "this", "those", "through", "time", "under", "very",
    "well", "were", "what", "when", "where", "which", "while", "will",
    "with", "would", "year", "young",
})


def _is_common_english_word(word: str) -> bool:
    """判断是否为常见英文单词"""
    return word.lower() in _COMMON_WORDS


def _remove_trailing_citation(text: str) -> str:
    """移除末尾残留的期刊文章引用格式

    常见模式（在引用区之后或无引用区的文章末尾）:
    - "Article Title\\nAuthor Names\\nScience 391 (6792), . DOI: ..."
    - "Laurie S. Huning and Manuela I. Brunner"
    """
    lines = text.rstrip().split("\n")

    # 从末尾向前扫描，找到连续的引用格式行并移除
    cutoff = len(lines)
    found_citation = False
    for i in range(len(lines) - 1, max(len(lines) - 10, -1), -1):
        line = lines[i].strip()
        if not line:
            break
        # 匹配: DOI 行
        if re.match(r"^doi:\s*10\.\d{4,}", line, re.IGNORECASE):
            cutoff = i
            found_citation = True
            continue
        # 匹配: "Science 391 (6792), . DOI: ..." 期刊引用格式
        if re.match(r"^(?:Science|Nature|Cell|PNAS|Lancet)\s+\d+", line):
            cutoff = i
            found_citation = True
            continue
        # 匹配: 纯作者行 (大写开头名字，用 and/comma 连接)
        if re.match(r"^[A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+(?:and|&|,)\s+[A-Z][a-z]+(?:\s+[A-Z]\.?)?){0,3}$", line):
            cutoff = i
            found_citation = True
            continue
        # 匹配: 文章标题行（不以句号结尾且较短，紧跟在已识别的引用行之前）
        if not line.endswith((".", "。", "!", "?", ";")) and len(line) < 120:
            # 如果已找到引用行，或上一行不以句号结尾，也视为引用元数据
            if found_citation or (i > 0 and not lines[i - 1].strip().endswith((".", "。", "!", "?"))):
                cutoff = i
                found_citation = True
                continue
        break

    if found_citation and cutoff < len(lines):
        removed = "\n".join(lines[cutoff:])
        logger.info("移除末尾引用元数据: %d 行 (%s...)", len(lines) - cutoff, removed[:80])
        return "\n".join(lines[:cutoff])

    return text


def _fix_truncated_words_in_text(text: str) -> str:
    """修复文本中间出现的截断词（跨页时中间页首词被截断）

    例如: "nflammation" → "Inflammation", "nvironmental" → "Environmental"
    """
    _TRUNCATED_WORDS = {
        "termine": "determine",
        "velop": "develop",
        "tablish": "establish",
        "spond": "respond",
        "search": "research",
        "troduce": "introduce",
        "vestigat": "investigate",
        "nderstand": "understand",
        "forestation": "deforestation",
        "nvironmen": "environment",
        "chani": "mechanism",
        "nflammation": "inflammation",
        "nvironmental": "environmental",
        "pigenetic": "epigenetic",
        "stimated": "estimated",
        "volutionary": "evolutionary",
        "vidence": "evidence",
    }

    lines = text.split("\n")
    fixed_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            fixed_lines.append(line)
            continue

        words = stripped.split()
        first_word = words[0] if words else ""
        first_lower = first_word.lower().rstrip(".,;:!?")

        # 只在行首且以小写字母开头时检查
        if first_word and first_word[0].islower() and first_lower in _TRUNCATED_WORDS:
            replacement = _TRUNCATED_WORDS[first_lower]
            # 段首截断词应首字母大写
            replacement = replacement[0].upper() + replacement[1:]

            # 保留原词尾标点
            trailing = ""
            while first_word and first_word[-1] in ".,;:!?":
                trailing = first_word[-1] + trailing
                first_word = first_word[:-1]

            new_line = replacement + trailing + " " + " ".join(words[1:]) if len(words) > 1 else replacement + trailing
            if new_line != line:
                logger.info("段内截断修复: '%s' → '%s'", stripped[:40], new_line[:40])
            fixed_lines.append(new_line)
        else:
            fixed_lines.append(line)

    return "\n".join(fixed_lines)


def _fix_truncated_first_word(text: str) -> str:
    """修复文本开头的截断首词

    PDF 跨页提取时，第一页的首词可能被截断（如 "termine" 应为 "determine"）。
    检测策略: 如果首行以小写字母开头且不像完整单词，尝试补全。
    """
    if not text:
        return text

    first_line = text.split("\n", 1)[0].strip()
    if not first_line:
        return text

    first_word = first_line.split()[0] if first_line.split() else ""
    if not first_word:
        return text

    # 如果首词以小写字母开头，可能是截断的
    if not first_word[0].islower() or len(first_word) < 3:
        return text

    # 常见截断前缀 → 完整词映射
    _TRUNCATION_FIXES = {
        "termine": "determine",
        "velop": "develop",
        "tablish": "establish",
        "spond": "respond",
        "search": "research",
        "troduce": "introduce",
        "vestigat": "investigate",
        "nderstand": "understand",
        "forestation": "deforestation",
        "nvironmen": "environment",
        "chani": "mechanism",
    }

    first_lower = first_word.lower().rstrip(".,;:!?")
    if first_lower in _TRUNCATION_FIXES:
        fixed = _TRUNCATION_FIXES[first_lower]
        logger.info("首词截断修复: '%s' → '%s'", first_word, fixed)
        text = text.replace(first_word, fixed, 1)

    return text


def _remove_annotations(text: str) -> str:
    """移除脚注、致谢、注释、作者贡献等非正文段落"""
    # 脚注标记: 独立一行只有上标数字或 [数字] 或 上标 a/b/c
    text = re.sub(r"^\^?\d{1,3}[a-z]?$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\[\d+\]$", "", text, flags=re.MULTILINE)
    # 致谢/注释/作者贡献/利益声明 等段落（整段删除）
    # 注意：所有 header 模式都要求"单独占一行"——否则 "Acknowledgment of funding..." 这类
    # 正文段落开头会被整段误删。每个模式末尾都加 `\s*:?\s*$`（允许尾部空格和可选冒号）。
    anno_section_headers = [
        r"^Acknowledgments?\s*:?\s*$",
        r"^Funding\s*:\s*$",
        r"^Author\s+(?:Contributions?|Information)\s*:?\s*$",
        r"^Competing\s+Interests?\s*:?\s*$",
        r"^Data\s+(?:Availability|Access)\s+Statement\s*:?\s*$",
        r"^Ethics\s+(?:Statement|Approval|Declarations?)\s*:?\s*$",
        r"^Consent\s+to\s+(?:Participate|Publish)\s*:?\s*$",
        r"^Conflicts?\s+of\s+Interests?\s*:?\s*$",
        r"^Financial\s+Disclosure\s*:?\s*$",
        r"^Declaration\s+of\s+\w[\w\s]*\s*:?\s*$",
        r"^Supplementary\s+(?:Information|Data|Material|Note)\s*:?\s*$",
        r"^Footnotes?\s*:?\s*$",
        r"^Notes?\s*:?\s*$",
        r"^Additional\s+(?:Information|File)s?\s*:?\s*$",
        r"^Electronic\s+Supplementary(?:\s+\w+)?\s*:?\s*$",
        r"^Supporting\s+Information\s*:?\s*$",
        r"^Author\s+e-?mail\s*:?\s*$",
        r"^Correspondence\s*:?\s*$",
        r"^See\s+(?:also\s+)?(?:Appendix|Table|Figure|Fig\.?|Supplementary)[^\n]*$",
    ]
    for pattern in anno_section_headers:
        # 匹配 header 行及后续直到空行的内容（header 必须单独占行）
        text = re.sub(
            pattern + r"(?:\n(?!\n)[^\n]*)*",
            "", text, flags=re.MULTILINE | re.IGNORECASE,
        )
    # 删除单独的脚注内容行: "1 Author Name, Title, Journal (2020) pp. 1-10"
    text = re.sub(r"^\d{1,3}\s+[A-Z][a-z]+.+?\(\d{4}\).*$", "", text, flags=re.MULTILINE)
    return text


# ---------------------------------------------------------------------------
# 原有清洗函数
# ---------------------------------------------------------------------------


def _fix_hyphenation(text: str) -> str:
    """修复连字符断词

    示例: "infor-\\nmation" → "information"
    支持 \\r\\n 和连字符后有空格的情况。
    """
    # 匹配 word-后跟可选空格和换行符(\r\n, \r, \n)，再跟word
    return re.sub(r"(\w)-\s*\r?\n\s*(\w)", r"\1\2", text)


def _merge_paragraph_lines(text: str) -> str:
    """合并同段落内的换行

    PDF 提取的文本经常在每行末尾产生不必要的换行。
    如果下一行以小写字母开头或不是常见段落起始模式，
    则认为是同一段落的续行。
    """
    lines = text.split("\n")
    merged: list[str] = []
    buffer = ""

    for line in lines:
        stripped = line.strip()
        if not stripped:
            # 空行 = 段落分隔
            if buffer:
                merged.append(buffer)
                buffer = ""
            merged.append("")
            continue

        if not buffer:
            buffer = stripped
        elif _is_continuation(buffer, stripped):
            buffer += " " + stripped
        else:
            # 新段落：在上一段和当前行之间插入空行
            merged.append(buffer)
            merged.append("")  # 空行作为段落分隔
            buffer = stripped

    if buffer:
        merged.append(buffer)

    return "\n".join(merged)


def _is_continuation(prev_line: str, current_line: str) -> bool:
    """判断当前行是否是上一行的续行

    续行特征:
    - 英文: 当前行以小写字母开头
    - 中文: 上一行未以句末标点结尾时视为续行
    - 上一行以句号、问号、感叹号结尾时，通常不是续行
    - LaTeX 环境（\\begin/\\end）始终视为新段落
    """
    prev_stripped = prev_line.rstrip()

    # LaTeX 环境: \begin{...} 或 \end{...} 或 $$ 始终作为新段落边界
    if prev_stripped and re.match(r"^\\(?:begin|end)\{", prev_stripped):
        return False
    if current_line and re.match(r"^\\(?:begin|end)\{", current_line):
        return False
    if prev_stripped and prev_stripped.strip() in ("$$", r"\[", r"\]"):
        return False
    if current_line and current_line.strip() in ("$$", r"\[", r"\]"):
        return False

    # 上一行以句末标点（含中文标点）结尾 → 新段落
    if prev_stripped and prev_stripped[-1] in ".!?。！？；":
        return False

    # 当前行首字符
    first_char = current_line[0]

    # 中文文本: 非句末标点结尾时视为续行
    if prev_stripped and '\u4e00' <= prev_stripped[-1] <= '\u9fff':
        return True

    # 当前行以大写字母开头 → 检查是否为新段落
    if first_char.isupper():
        # 短行且不以标点结尾 → 像标题
        if _looks_like_heading(current_line):
            return False
        # 上一行以句号结尾 + 当前行以大写开头 → 新段落
        # 排除单字母续行情况（如 "I" + "n 2023"）
        if prev_stripped and prev_stripped[-1] in ".!?。！？":
            # 上一行是单字母 → 可能是续行（如 "I" + "n 2023"）
            if len(prev_stripped) <= 3:
                # 检查合并后是否像有效单词
                combined = prev_stripped + current_line[:5]
                # 如果合并后看起来像有效句子开头，则视为续行
                if combined[:2].isalpha() and combined[2:5].isalpha():
                    return True
            # 否则是新段落
            return False
        # 长行以大写开头且单词数>3 → 可能是新段落
        word_count = len(current_line.split())
        if word_count > 3:
            return False

    # 当前行以小写字母开头 → 续行
    if first_char.islower():
        return True

    # 中文行首也视为续行（中文没有大小写）
    if '\u4e00' <= first_char <= '\u9fff':
        return True

    # 默认视为新段落
    return False


def _looks_like_heading(line: str) -> bool:
    """判断是否像标题行"""
    return len(line) < 80 and not line.endswith((".", ",", ";", ":"))


def _normalize_whitespace(text: str) -> str:
    """规范化空白字符"""
    text = text.replace("\t", " ")
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"^ +| +$", "", text, flags=re.MULTILINE)
    return text


def _remove_page_numbers(text: str) -> str:
    """移除独立页码行"""
    patterns = [
        r"^\s*\d+\s*$",
        r"^\s*[-–—]\s*\d+\s*[-–—]\s*$",
        r"^\s*[Pp]age\s+\d+\s*$",
    ]
    for pattern in patterns:
        text = re.sub(pattern, "", text, flags=re.MULTILINE)
    return text


def _fix_concatenated_words(text: str) -> str:
    """修复 PDF 无空格提取后残留的长连词

    对超过 20 个字符的纯小写字母序列，使用贪心正向匹配常见英文单词
    来恢复空格。
    """
    # 最常见的英文单词（覆盖 50%+ 的学术文本词汇）
    _WORDS = {
        "a", "an", "the", "and", "or", "but", "not", "is", "are", "was",
        "were", "be", "been", "being", "have", "has", "had", "do", "does",
        "did", "will", "would", "could", "should", "may", "might", "can",
        "shall", "to", "of", "in", "for", "on", "with", "at", "by", "from",
        "as", "into", "through", "during", "before", "after", "above",
        "below", "between", "under", "over", "about", "without", "within",
        "along", "across", "behind", "beyond", "toward", "upon", "around",
        "that", "this", "these", "those", "it", "its", "he", "she", "they",
        "we", "you", "who", "which", "what", "where", "when", "how", "why",
        "all", "each", "every", "both", "few", "more", "most", "other",
        "some", "such", "no", "nor", "only", "own", "same", "so", "than",
        "too", "very", "also", "just", "then", "there", "here", "now",
        "if", "else", "while", "because", "since", "although", "though",
        "however", "therefore", "thus", "hence", "yet", "still", "even",
        "much", "many", "well", "only", "like", "new", "old", "first",
        "last", "long", "great", "little", "own", "good", "large",
        # 学术常用
        "based", "using", "used", "use", "which", "their", "such", "will",
        "each", "group", "groups", "attention", "self", "matrix",
        "window", "windows", "feature", "features", "model", "models",
        "data", "method", "methods", "time", "timeseries", "result",
        "results", "approach", "approaches", "segment", "segments",
        "embedding", "embeddings", "vector", "vectors", "query", "queries",
        "training", "train", "trained", "batch", "size", "number",
        "making", "making", "tunable", "easily", "efficient", "fully",
        "compressed", "compute", "computed", "computing", "computes",
        "restored", "restore", "restoring", "produces", "produced",
        "produce", "producing", "following", "followed", "follow",
        "include", "includes", "including", "contain", "contains",
        "require", "requires", "required", "requiring", "obtain",
        "obtained", "obtaining", "ensure", "ensures", "ensuring",
        "perform", "performs", "performed", "performing",
        "different", "differs", "similar", "similarly",
        "single", "multiple", "several", "various",
        "input", "output", "given", "according",
        "show", "shown", "shows", "showing",
        "one", "two", "three", "four", "five",
        "set", "sets", "key", "keys", "value", "values",
        "layer", "layers", "level", "levels",
        "process", "processes", "processing",
        "transformer", "transformers", "vanilla",
        "scale", "scales", "scaling", "scalable",
        "learn", "learns", "learned", "learning",
        "correlation", "correlations", "correlate",
        "complexity", "quality", "accuracy",
    }

    def _split_long_word(word: str) -> str:
        """贪心正向匹配分割长词"""
        if len(word) < 20:
            return word

        n = len(word)
        # dp[i] = (can_split, split_positions)
        # 从位置 i 开始能否匹配到末尾
        dp = [None] * (n + 1)
        dp[n] = (True, [])

        for i in range(n - 1, -1, -1):
            best = None
            for length in range(min(15, n - i), 0, -1):
                candidate = word[i:i + length]
                if candidate in _WORDS:
                    rest_can, rest_splits = dp[i + length]
                    if rest_can:
                        splits = [i] + rest_splits
                        if best is None or len(splits) < len(best):
                            best = splits
            if best is not None:
                dp[i] = (True, best)
            else:
                dp[i] = (False, [])

        can, splits = dp[0]
        if not can or not splits:
            # 无法完整分割，回退：在常见短词前插入空格
            result = word
            for w in sorted(_WORDS, key=len, reverse=True):
                if len(w) >= 3:
                    idx = result.find(w)
                    while idx >= 0:
                        before = result[:idx]
                        after = result[idx + len(w):]
                        if (not before or not before[-1].isalpha()) and \
                           (not after or not after[0].isalpha()):
                            pass  # already has boundary
                        elif before and after:
                            result = before + w + " " + after
                        idx = result.find(w, idx + len(w) + 1)
            return result

        # 根据 splits 重建
        parts = []
        prev = 0
        for pos in splits:
            if pos > prev:
                parts.append(word[prev:pos])
            prev = pos
        if prev < n:
            parts.append(word[prev:])
        return " ".join(parts)

    # 只处理纯小写长词
    def _replace_long(m):
        word = m.group(0)
        return _split_long_word(word)

    return re.sub(r'\b[a-z]{20,}\b', _replace_long, text)
