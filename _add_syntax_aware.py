"""句法感知切块 — 在句子内按从句/分句边界二次切分"""

content = open('python/src/chunker/splitter.py', 'r', encoding='utf-8').read()

# Add new function before _merge_segments
new_function = '''
# ---------------------------------------------------------------------------
# 句法感知切分（对超长句子的从句边界处理）
# ---------------------------------------------------------------------------

# English clause/subordinate conjunction patterns (前后有空格)
_EN_CLAUSE_CONNECTORS = [
    # Subordinate clauses
    r"\\bwhich\\b", r"\\bthat\\b", r"\\bwhere\\b", r"\\bwhen\\b",
    r"\\bbecause\\b", r"\\balthough\\b", r"\\bwhile\\b", r"\\bif\\b",
    r"\\bsince\\b", r"\\bunless\\b", r"\\bafter\\b", r"\\bbefore\\b",
    r"\\bthough\\b", r"\\bas\\b", r"\\bonce\\b",
    # Transitional adverbs (前有分号或逗号)
    r"\\bhowever\\b", r"\\btherefore\\b", r"\\bfurthermore\\b",
    r"\\bmoreover\\b", r"\\bnevertheless\\b", r"\\bconsequently\\b",
    r"\\bspecifically\\b", r"\\bparticularly\\b", r"\\badditionally\\b",
    # Comparative/summary
    r"\\bcompared\\b", r"\\bhowever\\b", r"\\boverall\\b",
    # In Chinese text, these appear as Chinese characters
]
_EN_CLAUSE_CONNECTOR_PATTERN = "|".join(_EN_CLAUSE_CONNECTORS)

# Chinese clause separators (全角标点 + 复合虚词)
_CN_CLAUSE_SEPARATORS = [
    # 全角分号、冒号（表示分句）
    r"；", r"：",
    # 复合虚词作从句连接词（逗号+虚词）
    r"，但是", r"，然而", r"，因此", r"，所以",
    r"，并且", r"，而且", r"，同时", r"，此外",
    r"，由于", r"，既然", r"，虽然", r"，即使",
    r"，如果", r"，只要", r"，除非",
    r"，于是", r"，从而", r"，故",
]


def _is_inside_paren(text: str, pos: int) -> bool:
    """检查位置 pos 是否在括号对内部（忽略不配对的左括号）"""
    depth = 0
    i = 0
    while i < len(text) and i < pos:
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth = max(0, depth - 1)
        i += 1
    return depth > 0


def _split_long_sentence(text: str, max_chars: int) -> list[str]:
    """对超长句子在从句边界二次切分，返回子句列表

    保护策略:
    - 括号 (...) [...] 内不切分
    - 数字格式 "10.5", "3.14" 不触发切分
    - 只在标点 + 空格处切分，保证读起来自然
    """
    if len(text) <= max_chars:
        return [text]

    # 预保护: 数字+句号格式 (10.5, 3.14)
    protected_digits, digit_map = [], {}
    def _dig_ph(m):
        idx = len(protected_digits)
        protected_digits.append(m.group(0))
        digit_map[f"\\x00D{idx}\\x00"] = m.group(0)
        return f"\\x00D{idx}\\x00"
    text_prot = re.sub(r"\\d+\\.\\d+", _dig_ph, text)

    # 收集所有可切分位置
    candidates: list[tuple[int, str]] = []  # (position, separator)

    # 1. English clause connectors (不在括号内)
    for m in re.finditer(_EN_CLAUSE_CONNECTOR_PATTERN, text_prot, re.IGNORECASE):
        pos = m.start()
        if not _is_inside_paren(text_prot, pos):
            sep = m.group(0)
            # 要求前面有逗号/分号/空格（自然停顿）
            before = text_prot[max(0, pos - 2):pos]
            if re.match(r"[，;,\s]", before[-1] if before else " "):
                candidates.append((pos, sep))

    # 2. Chinese clause separators (，但是、；等)
    for sep in _CN_CLAUSE_SEPARATORS:
        for m in re.finditer(re.escape(sep), text_prot):
            pos = m.start()
            if not _is_inside_paren(text_prot, pos):
                candidates.append((pos, sep))

    # 3. 英文分号/逗号（不在括号内，且前面有内容）
    for m in re.finditer(r"[;,](?=\\s+[A-Z])", text_prot):
        pos = m.start()
        if not _is_inside_paren(text_prot, pos):
            candidates.append((pos, m.group(0)))

    # 去重（同位置保留最短 separator）
    seen_pos: dict[int, str] = {}
    for pos, sep in candidates:
        if pos not in seen_pos or len(sep) < len(seen_pos[pos]):
            seen_pos[pos] = sep

    # 按位置排序
    split_positions = sorted(seen_pos.keys())

    # 如果没有找到切分点，返回原句（可能超限但无法再分）
    if not split_positions:
        # 还原数字占位符
        result = text
        for i in range(len(protected_digits) - 1, -1, -1):
            result = result.replace(f"\\x00D{i}\\x00", protected_digits[i])
        return [result]

    # 在切分点切分，子句长度尽量均匀
    sub_parts: list[str] = []
    prev = 0
    for pos in split_positions:
        sub = text_prot[prev:pos].strip()
        if sub:
            sub_parts.append(sub)
        prev = pos

    last_sub = text_prot[prev:].strip()
    if last_sub:
        sub_parts.append(last_sub)

    # 还原数字占位符
    def _restore(text: str) -> str:
        for i in range(len(protected_digits) - 1, -1, -1):
            text = text.replace(f"\\x00D{i}\\x00", protected_digits[i])
        return text

    sub_parts = [_restore(s) for s in sub_parts]

    # 递归: 如果某个子句仍超限，继续切
    result: list[str] = []
    for part in sub_parts:
        if len(part) > max_chars:
            result.extend(_split_long_sentence(part, max_chars))
        else:
            result.append(part)

    return [p for p in result if p.strip()]


'''

# Insert before _merge_segments function
insert_before = '# ---------------------------------------------------------------------------\n# 句法感知切分（对超长句子的从句边界处理）\n# ---------------------------------------------------------------------------\n\n\ndef _merge_segments('
if insert_before not in content:
    # Try exact marker
    content = content.replace(
        '# ---------------------------------------------------------------------------\n# 切块策略\n# ---------------------------------------------------------------------------',
        '# ---------------------------------------------------------------------------\n# 切块策略\n# ---------------------------------------------------------------------------' + new_function,
        1
    )
else:
    content = content.replace(insert_before, new_function + insert_before)

open('python/src/chunker/splitter.py', 'w', encoding='utf-8').write(content)
print("Done")
