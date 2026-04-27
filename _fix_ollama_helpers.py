"""Replace helper functions in ollama_client.py with imports from _helpers"""

import re

with open('python/src/translator/ollama_client.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add import from _helpers after the logger line
# Find: "logger = logging.getLogger(__name__)"
# After that, add from src.translator._helpers import ...

old_logger = 'logger = logging.getLogger(__name__)'
new_imports = '''logger = logging.getLogger(__name__)

from src.translator._helpers import (
    _extract_term_pairs as _extract_term_pairs_impl,
    _strip_think_tags as _strip_think_tags_impl,
    _strip_code_block_wrapping as _strip_code_block_wrapping_impl,
    _strip_preamble as _strip_preamble_impl,
    _strip_context_leak as _strip_context_leak_impl,
    _validate_translation as _validate_translation_impl,
    _repair_truncation as _repair_truncation_impl,
    _strip_empty_parentheses as _strip_empty_parentheses_impl,
    _strip_trailing_summary as _strip_trailing_summary_impl,
    _deduplicate_repetition as _deduplicate_repetition_impl,
    _deduplicate_line_repetition as _deduplicate_line_repetition_impl,
    _lines_match as _lines_match_impl,
    _is_similar_sentences as _is_similar_sentences_impl,
    _restore_paragraphs as _restore_paragraphs_impl,
)'''

if 'from src.translator._helpers import' not in content:
    content = content.replace(old_logger, new_imports)

# Now replace each function with a one-liner call to the _impl version
# We need to keep the function signature but make it delegate to _impl

replacements = [
    ('def _extract_term_pairs(original: str, translated: str)',
     'def _extract_term_pairs(original: str, translated: str)'),
    ('def _strip_think_tags(text: str) -> str:',
     'def _strip_think_tags(text: str) -> str:'),
    ('def _strip_code_block_wrapping(text: str) -> str:',
     'def _strip_code_block_wrapping(text: str) -> str:'),
    ('def _strip_preamble(text: str) -> str:',
     'def _strip_preamble(text: str) -> str:'),
    ('def _strip_context_leak(text: str) -> str:',
     'def _strip_context_leak(text: str) -> str:'),
    ('def _validate_translation(result: TranslationResult) -> bool:',
     'def _validate_translation(result: TranslationResult) -> bool:'),
    ('def _repair_truncation(text: str) -> str:',
     'def _repair_truncation(text: str) -> str:'),
    ('def _strip_empty_parentheses(text: str) -> str:',
     'def _strip_empty_parentheses(text: str) -> str:'),
    ('def _strip_trailing_summary(text: str) -> str:',
     'def _strip_trailing_summary(text: str) -> str:'),
    ('def _deduplicate_repetition(text: str) -> str:',
     'def _deduplicate_repetition(text: str) -> str:'),
    ('def _deduplicate_line_repetition(text: str) -> str:',
     'def _deduplicate_line_repetition(text: str) -> str:'),
    ('def _lines_match(a: list[str], b: list[str]) -> bool:',
     'def _lines_match(a: list[str], b: list[str]) -> bool:'),
    ('def _is_similar_sentences(a: list[str], b: list[str]) -> bool:',
     'def _is_similar_sentences(a: list[str], b: list[str]) -> bool:'),
    ('def _restore_paragraphs(original: str, translated: str) -> str:',
     'def _restore_paragraphs(original: str, translated: str) -> str:'),
]

# For each function, replace the body with a single delegation statement
# These are all the functions we want to redirect

def delegator(name, impl_name):
    return f'    return {impl_name}(text)'

def delegator_restore(name, impl_name):
    return f'    return {impl_name}(original, translated)'

def delegator_validate(name, impl_name):
    return f'    return {impl_name}(result)'

def delegator_term(name, impl_name):
    return f'    return {impl_name}(original, translated)'

func_map = {
    '_extract_term_pairs': ('def _extract_term_pairs(original: str, translated: str) -> list[tuple[str, str]]:\n    """从原文-译文对中提取可能的术语翻译对\n\n    策略: 找译文中「中文（英文）」模式的括号注解，\n    这些通常是模型按 system_prompt 要求标注的术语。\n    """\n    pairs: list[tuple[str, str]] = []\n    seen: set[str] = set()\n\n    pattern = re.compile(\n        r"([一-鿿][一-鿿\\w\\s]{1,20})"\n        r"[（(]"\n        r"([A-Za-z][A-Za-z\\s\\-/]+[A-Za-z])"\n        r"[）)]"\n    )\n    for m in pattern.finditer(translated):\n        zh_term = m.group(1).strip()\n        en_term = m.group(2).strip()\n        key = en_term.lower()\n        if key not in seen and len(en_term) > 2:\n            pairs.append((en_term, zh_term))\n            seen.add(key)\n\n    return pairs', 'return _extract_term_pairs_impl(original, translated)'),
}

# Let's use a simpler approach: find each function block and replace it with delegation
# Using specific patterns for each function

# 1. _extract_term_pairs
old = '''def _extract_term_pairs(original: str, translated: str) -> list[tuple[str, str]]:
    """从原文-译文对中提取可能的术语翻译对

    策略: 找译文中「中文（英文）」模式的括号注解，
    这些通常是模型按 system_prompt 要求标注的术语。
    """
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()

    pattern = re.compile(
        r"([一-鿿][一-鿿\\w\\s]{1,20})"
        r"[（(]"
        r"([A-Za-z][A-Za-z\\s\\-/]+[A-Za-z])"
        r"[）)]"
    )
    for m in pattern.finditer(translated):
        zh_term = m.group(1).strip()
        en_term = m.group(2).strip()
        key = en_term.lower()
        if key not in seen and len(en_term) > 2:
            pairs.append((en_term, zh_term))
            seen.add(key)

    return pairs'''

new = 'def _extract_term_pairs(original: str, translated: str) -> list[tuple[str, str]]:\n    return _extract_term_pairs_impl(original, translated)'

content = content.replace(old, new)

# 2. _strip_think_tags
old = '''def _strip_think_tags(text: str) -> str:
    """移除推理模型常见思考段，避免进入正文。"""
    for tag in ("think", "redacted_thinking", "redacted_reasoning"):
        pat = rf"<{tag}\\b[^>]*>.*?</{tag}\\s*>"
        text = re.sub(pat, "", text, flags=re.DOTALL | re.IGNORECASE)
    return text.strip()'''

new = 'def _strip_think_tags(text: str) -> str:\n    return _strip_think_tags_impl(text)'

content = content.replace(old, new)

# 3. _strip_code_block_wrapping
old = '''def _strip_code_block_wrapping(text: str) -> str:
    """移除 LLM 用 markdown 代码块包裹翻译结果的格式幻觉

    常见模式:
    ```markdown
    翻译内容...
    ```
    或
    ```
    翻译内容...
    ```
    """
    stripped = text.strip()
    # 匹配 ```lang\\n...\\n``` 或 ```\\n...\\n``` 模式
    m = re.match(r"^```(?:\\w+)?\\s*\\n(.*?)\\n```\\s*$", stripped, re.DOTALL)
    if m:
        inner = m.group(1).strip()
        # 安全检查: 内部不应还有代码块（避免误剥嵌套的公式代码块）
        if inner.count("```") == 0:
            return inner
    return text'''

new = 'def _strip_code_block_wrapping(text: str) -> str:\n    return _strip_code_block_wrapping_impl(text)'

content = content.replace(old, new)

# 4. _strip_preamble
old = '''def _strip_preamble(text: str) -> str:
    preamble_pattern = re.compile(
        r"^(?:"
        r"(?:Here|Below|Following)\\s+(?:is|are)\\s+(?:the\\s+)?(?:translation|result|translated\\s+text)[：:]*\\s*"
        r"|以下是翻译[：:]*\\s*"
        r"|翻译如下[：:]*\\s*"
        # 避免把正文「这是翻译结果」整句误删：要求冒号或换行后再接正文
        r"|这是翻译结果(?:[：:]+\\s*|\\n+\\s*)"
        r"|下面是(?:翻译|译文)[：:]*\\s*"
        r"|这是(?:翻译|译文)(?:[：:]+\\s*|\\n+\\s*)"
        r"|(?:Sure|Certainly|Of\\s+course)[，,\\s]*(?:here|below)\\s+(?:is|are)[^。\\n]*[。.\\n]\\s*"
        r"|(?:好的|没问题|收到)[，,]?\\s*(?:以下是翻译|以下是译文|翻译如下|下面是翻译|下面是译文)[：:]*\\s*"
        r")",
        re.IGNORECASE,
    )
    return preamble_pattern.sub("", text).strip()'''

new = 'def _strip_preamble(text: str) -> str:\n    return _strip_preamble_impl(text)'

content = content.replace(old, new)

# 5. _strip_context_leak
old = '''def _strip_context_leak(text: str) -> str:
    """去掉开头附近的指令回声；仅在扫描窗口内匹配，避免误伤正文。"""
    scan_len = 500
    head = text[:scan_len]
    ctx_markers = [
        "[文档背景",
        "[前文翻译参考",
        "（不要翻译此部分",
        "（仅用于保持术语",
        "[请翻译以下内容]",
    ]
    for marker in ctx_markers:
        idx = head.find(marker)
        if idx < 0:
            continue
        rest = text[idx:]
        if "\\n\\n" in rest[:2500]:
            _, sep, tail = rest.partition("\\n\\n")
            if sep:
                return tail.lstrip()
        return text[idx + len(marker) :].lstrip()
    return text.strip()'''

new = 'def _strip_context_leak(text: str) -> str:\n    return _strip_context_leak_impl(text)'

content = content.replace(old, new)

# 6. _repair_truncation
old = '''def _repair_truncation(text: str) -> str:
    if not text:
        return text

    n = len(text)
    # 短文本（< 100 字符）不进行截断修复，避免误删标题或图注
    if n < 100:
        return text

    zh_endings = ["。", "！", "？", "；", "…"]
    en_endings = ["!", "?"]

    last_zh = max((text.rfind(c) for c in zh_endings), default=-1)
    last_en = max((text.rfind(c) for c in en_endings), default=-1)

    # 对 "." 单独处理：排除小数点 (3.14)、缩写 (Fig. Dr.)、省略号 (...) 等误匹配
    last_dot = text.rfind(".")
    if last_dot >= 0:
        before = text[:last_dot].rstrip()
        # 排除小数点: 前面紧跟数字
        if before and before[-1].isdigit():
            last_dot = -1
        # 排除省略号: 前面紧跟 .
        elif before and before[-1] == ".":
            last_dot = -1
        # 排除常见缩写
        elif before and re.search(
            r"(?:Fig|Eq|Ref|Vol|No|Dr|Mr|Mrs|Prof|Sr|Jr|St|vs|etc|al|ed|e\\.g|i\\.e)$",
            before, re.IGNORECASE
        ):
            last_dot = -1

    last_en = max(last_en, last_dot)

    last_sentence_end = max(last_zh, last_en)

    # 仅当「最后一句边界」落在文末附近时尝试修剪，避免误删未打句号的整段译文
    if last_sentence_end >= 0 and last_sentence_end < n - 1 and last_sentence_end >= int(n * 0.75):
        tail = text[last_sentence_end + 1 :].strip()
        tail_cjk = sum(1 for c in tail if "一" <= c <= "鿿")
        if (
            0 < len(tail) < min(120, int(n * 0.12))
            and tail_cjk == 0
            and not re.search(r"[\\w一-鿿]{6,}", tail)
        ):
            logger.info("截断修复: 移除末尾疑似残缺片段 (%d 字符)", len(tail))
            return text[: last_sentence_end + 1].rstrip()
    return text'''

new = 'def _repair_truncation(text: str) -> str:\n    return _repair_truncation_impl(text)'

content = content.replace(old, new)

# 7. _strip_empty_parentheses
old = '''def _strip_empty_parentheses(text: str) -> str:
    """移除翻译中残留的空括号，如 （）或 ()"""
    text = re.sub(r"（\\s*）", "", text)
    text = re.sub(r"\\(\\s*\\)", "", text)
    return text'''

new = 'def _strip_empty_parentheses(text: str) -> str:\n    return _strip_empty_parentheses_impl(text)'

content = content.replace(old, new)

# 8. _strip_trailing_summary
old = '''def _strip_trailing_summary(text: str) -> str:
    """移除译文末尾的总结段落

    模型有时在翻译完正文后自作主张加总结，如"总之..."、"总而言之..."等。
    """
    if not text or len(text) < 200:
        return text

    summary_patterns = [
        r"\\n[（(]?总之[，,]?\\s*",
        r"\\n[（(]?总而言之[，,]?\\s*",
        r"\\n[（(]?综上所述[，,]?\\s*",
        r"\\n[（(]?总的来说[，,]?\\s*",
        r"\\n[（(]?概括来说[，,]?\\s*",
        r"\\n[（(]?简而言之[，,]?\\s*",
        r"\\n[（(]?总之[，,]?.*?(?:总结|概括|回顾)",
        r"\\n[（(]?In\\s+summary[,.]?\\s*",
        r"\\n[（(]?To\\s+summarize[,.]?\\s*",
        r"\\n[（(]?In\\s+conclusion[,.]?\\s*",
        r"\\n[（(]?Overall[,.]?\\s*",
    ]
    for pattern in summary_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            # 确保这是在文末附近（最后 40% 的位置）
            if m.start() >= len(text) * 0.6:
                logger.info("移除末尾总结段落 (位置 %d/%d)", m.start(), len(text))
                return text[: m.start()].rstrip()
    return text'''

new = 'def _strip_trailing_summary(text: str) -> str:\n    return _strip_trailing_summary_impl(text)'

content = content.replace(old, new)

# 9. _deduplicate_repetition - more complex, has nested calls
old = '''def _deduplicate_repetition(text: str) -> str:
    """检测并移除译文中的循环重复内容

    模型有时陷入生成循环，同一段落重复几十次。
    两级策略:
    1. 行级重复检测: 按 \\n 分割，检测任意位置的连续重复块
    2. 句级重复检测: 按句号分段，检测从头开始的周期性重复
    """
    if not text or len(text) < 300:
        return text

    # ── Level 1: 行级重复检测（检测文本任意位置的连续重复） ──
    line_result = _deduplicate_line_repetition(text)
    if len(line_result) < len(text) * 0.7:
        return line_result

    # ── Level 2: 句级重复检测（原有逻辑，检测从头开始的周期重复） ──
    sentences = re.split(r"(?<=[。！？])", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) < 6:
        return text

    text_len = len(sentences)
    for unit_size in range(1, text_len // 2 + 1):
        if text_len < unit_size * 3:
            break
        unit = sentences[:unit_size]
        is_repetitive = True
        repeat_count = 0
        for i in range(unit_size, text_len, unit_size):
            chunk = sentences[i : i + unit_size]
            if not chunk:
                continue
            if not _is_similar_sentences(unit, chunk):
                is_repetitive = False
                break
            repeat_count += 1

        if is_repetitive and repeat_count >= 2:
            unique_text = "".join(unit)
            logger.warning(
                "检测到句级循环重复: 单元=%d句, 重复%d次, 保留第一份 (原文%d句→%d句)",
                unit_size, repeat_count, text_len, unit_size,
            )
            return unique_text

    return text'''

new = 'def _deduplicate_repetition(text: str) -> str:\n    return _deduplicate_repetition_impl(text)'

content = content.replace(old, new)

# 10. _deduplicate_line_repetition
old = '''def _deduplicate_line_repetition(text: str) -> str:
    """行级重复检测: 在文本任意位置检测连续重复的行块

    当相同的 1-4 行模式连续重复 3 次以上时，保留第一份并截断后续重复。
    """
    lines = text.split("\\n")
    if len(lines) < 8:
        return text

    # 在文本中扫描所有起始位置，寻找重复模式
    for start in range(len(lines)):
        for pat_size in range(1, 5):
            if start + pat_size * 4 > len(lines):
                break

            pattern = [l.strip() for l in lines[start : start + pat_size]]
            # 跳过全空行的模式
            if all(not p for p in pattern):
                continue
            # 跳过过短的模式（每行平均 < 5 字符）
            avg_len = sum(len(p) for p in pattern) / pat_size
            if avg_len < 5:
                continue

            repeat_count = 0
            pos = start + pat_size
            while pos + pat_size <= len(lines):
                chunk = [l.strip() for l in lines[pos : pos + pat_size]]
                if _lines_match(pattern, chunk):
                    repeat_count += 1
                    pos += pat_size
                else:
                    break

            if repeat_count >= 3:
                # 保留: 重复之前的内容 + 第一份模式 + 重复之后的有效内容
                kept = lines[: start + pat_size]
                remaining = lines[pos:]
                if remaining:
                    non_empty = sum(1 for l in remaining if l.strip())
                    if non_empty > 3:
                        kept.extend(remaining)

                result = "\\n".join(kept)
                logger.warning(
                    "行级重复检测: 起始行=%d, 模式=%d行, 重复%d次, %d行→%d行",
                    start, pat_size, repeat_count, len(lines), len(kept),
                )
                return result

    return text'''

new = 'def _deduplicate_line_repetition(text: str) -> str:\n    return _deduplicate_line_repetition_impl(text)'

content = content.replace(old, new)

# 11. _lines_match
old = '''def _lines_match(a: list[str], b: list[str]) -> bool:
    """判断两组行是否高度相似"""
    if len(a) != len(b):
        return False
    for la, lb in zip(a, b):
        if not la and not lb:
            continue
        if not la or not lb:
            return False
        shorter = min(len(la), len(lb))
        check_len = max(int(shorter * 0.8), 1)
        match = sum(1 for ca, cb in zip(la[:check_len], lb[:check_len]) if ca == cb)
        if match / check_len < 0.7:
            return False
    return True'''

new = 'def _lines_match(a: list[str], b: list[str]) -> bool:\n    return _lines_match_impl(a, b)'

content = content.replace(old, new)

# 12. _is_similar_sentences
old = '''def _is_similar_sentences(a: list[str], b: list[str]) -> bool:
    """判断两组句子是否高度相似（允许轻微差异）"""
    if len(a) != len(b):
        return False
    for sa, sb in zip(a, b):
        if not sa or not sb:
            continue
        shorter = min(len(sa), len(sb))
        longer = max(len(sa), len(sb))
        if longer == 0:
            continue
        # 逐字比较前 80% 的较短句
        check_len = int(shorter * 0.8)
        if check_len == 0:
            continue
        match = sum(1 for ca, cb in zip(sa[:check_len], sb[:check_len]) if ca == cb)
        if match / check_len < 0.7:
            return False
    return True'''

new = 'def _is_similar_sentences(a: list[str], b: list[str]) -> bool:\n    return _is_similar_sentences_impl(a, b)'

content = content.replace(old, new)

# 13. _restore_paragraphs
old = '''def _restore_paragraphs(original: str, translated: str) -> str:
    """译文缺少段落分隔时，按原文段落比例恢复 \\n\\n 分段。"""
    orig_paras = [p.strip() for p in original.split("\\n\\n") if p.strip()]
    trans_paras = [p.strip() for p in translated.split("\\n\\n") if p.strip()]

    if len(orig_paras) <= 1 or len(trans_paras) <= 1:
        return translated

    # 计算原文各段字符数比例
    orig_lens = [len(p) for p in orig_paras]
    total_orig = sum(orig_lens)
    if total_orig == 0:
        return translated

    # 找出译文中已经天然有段落分隔的位置（保留）
    trans_text = translated
    if "\\n\\n" not in translated:
        # 按原文段落数均分译文
        trans_lens = [len(p) for p in trans_paras]
        total_trans = sum(trans_lens)
        if total_trans == 0:
            return translated

        result: list[str] = []
        acc = 0
        target_acc = 0
        for i, orig_len in enumerate(orig_lens):
            target_acc += orig_len / total_orig * total_trans
            boundary = int(target_acc)
            chunk = translated[acc:boundary]
            result.append(chunk)
            acc = boundary

        # 最后一段包含剩余内容
        result.append(translated[acc:])
        trans_text = "\\n\\n".join(result)

    return trans_text'''

new = 'def _restore_paragraphs(original: str, translated: str) -> str:\n    return _restore_paragraphs_impl(original, translated)'

content = content.replace(old, new)

# 14. _validate_translation - very long, replace with delegator
old_validate = '''def _validate_translation(result: TranslationResult) -> bool:
    """校验翻译结果质量

    多层校验:
    1. 空值/极短检测
    2. 截断检测（译文过短）
    3. 未翻译检测（原文=译文）
    4. 语言检测（无中文字符）
    5. 格式幻觉检测（markdown 代码块包裹、多份重复翻译）
    """
    if not result.translated:
        return False
    orig = result.original
    trans = result.translated
    orig_len = len(orig)
    trans_len = len(trans)

    # 短块: 标题、图注等（< 30 字符）只做最低检查
    if orig_len < 30:
        return trans_len >= 1 and len(trans.strip()) > 0

    # 原文公式/LaTeX/代码占比高时不做强校验
    latexish = sum(1 for c in orig if c in "\\\\{}$[]_^") / max(orig_len, 1)
    if latexish > 0.04:
        return trans_len >= max(3, int(orig_len * 0.03))

    # 译文太短 (原文 > 100 字符但译文不到 3%) — 明显截断
    if orig_len > 100 and trans_len < orig_len * 0.03:
        return False

    # 译文与原文完全相同（去掉空白后） — 明显未翻译
    orig_no_space = re.sub(r"\\s+", "", orig)
    trans_no_space = re.sub(r"\\s+", "", trans)
    if orig_no_space and orig_no_space == trans_no_space:
        logger.warning("译文与原文完全相同，疑似未翻译")
        return False

    # CJK 占比检查: 如果完全没有中文字符且 ASCII 占比极高，判定未翻译
    cjk_n = sum(1 for c in trans if "一" <= c <= "鿿")
    cjk_ratio = cjk_n / max(trans_len, 1)
    if cjk_ratio < 0.05 and orig_len > 100:
        ascii_ratio = sum(1 for c in trans if c.isascii() and c.isalpha()) / max(trans_len, 1)
        if ascii_ratio > 0.95:
            logger.warning("译文 ASCII 占比 %.0f%% 且无中文，疑似未翻译: %.50s...", ascii_ratio * 100, trans)
            return False

    # 格式幻觉检测: LLM 用 markdown 代码块包裹翻译结果
    stripped = trans.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        logger.warning("译文被 markdown 代码块包裹，疑似格式幻觉")
        return False

    # 重复翻译检测: 译文前半段和后半段高度重复（>80% 相同）
    if trans_len > 400:
        half = trans_len // 2
        first_half = stripped[:half]
        second_half = stripped[half:half * 2]
        if first_half and second_half and len(first_half) > 50:
            # 计算两半的前 100 字符重复率
            shorter_len = min(len(first_half), len(second_half), 100)
            overlap = sum(1 for a, b in zip(first_half[:shorter_len], second_half[:shorter_len]) if a == b)
            if overlap / shorter_len > 0.8:
                logger.warning("译文前后半段高度重复 (%.0f%%)，疑似重复翻译", overlap / shorter_len * 100)
                return False

    # 循环重复检测: 按句号分段后检查是否存在周期性重复
    if trans_len > 600:
        sents = re.split(r"(?<=[。！？])", stripped)
        sents = [s.strip() for s in sents if s.strip()]
        if len(sents) >= 6:
            # 检查是否有连续 3+ 段相同内容循环出现
            for unit_sz in range(1, min(len(sents) // 3, 20) + 1):
                unit = sents[:unit_sz]
                repeats = 0
                for si in range(unit_sz, len(sents), unit_sz):
                    chunk = sents[si:si + unit_sz]
                    if not chunk:
                        continue
                    if _is_similar_sentences(unit, chunk):
                        repeats += 1
                    else:
                        break
                if repeats >= 2:
                    logger.warning(
                        "检测到循环重复 (单元=%d句, 重复%d次), 拒绝该翻译",
                        unit_sz, repeats,
                    )
                    return False

    return True'''

new = 'def _validate_translation(result: TranslationResult) -> bool:\n    return _validate_translation_impl(result)'

content = content.replace(old_validate, new)

with open('python/src/translator/ollama_client.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done replacing functions in ollama_client.py")