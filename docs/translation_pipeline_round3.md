# 翻译管道第三轮诊断报告（2026-05-05）

> **测试样本**：`C:\Users\zuowen\Desktop\science.adn8744.pdf`
> **第二轮修复后状态**：多文章拆分 ✅、截断开头 ✅、噪声字符 ✅
> **剩余问题**：1 个 P0 问题

---

## 第二轮修复效果确认

| 问题 | 状态 | 验证 |
|------|------|------|
| 多篇文章未拆分 | ✅ 已修复 | 检测到 3 篇文章 |
| 文章开头截断 (`n 2023`, `nflammation`) | ✅ 已修复 | 全部正常 |
| 噪声字符 `ó ó` | ✅ 已修复 | cleaner 已处理 |
| chunk overlap 警告 | ✅ 已修复 | 配置正确 |

---

## 新问题清单

### 🔴 P0-1. 空行导致续行规则失效 — "other countries" 仍被切开

**实测证据**：

```
[Block b0004] "...production deficits in other"
[Block b0005] "countries (for example, also caused by..."

↑ 两块之间有空行，导致续行规则被跳过
```

**根因**：

`cleaner/pipeline.py` 的 `_merge_lines()` 函数逻辑顺序问题：

```python
for line in lines:
    stripped = line.strip()
    if not stripped:
        # ❌ 空行 = 段落分隔（直接返回，不检查续行）
        if buffer:
            merged.append(buffer)
            buffer = ""
        merged.append("")
        continue  # ← 这里直接跳过了续行检查

    # ... 续行规则在后面才检查
    elif _is_continuation(buffer, stripped):
        buffer += " " + stripped
```

**问题**：即使 `_is_continuation()` 中有完整的规则（包括 R5: `other` + `countries`），但因为空行优先处理，续行规则永远不会被触发。

**修复方案**：

在处理空行之前，先检查"前瞻续行"——如果当前空行后的下一行与当前 buffer 符合续行模式，则忽略空行：

```python
def _merge_lines(text: str) -> str:
    """合并续行，修复空行导致的错误分段

    关键修复：空行不一定是段落分隔符，需要检查前后行是否符合续行模式
    """
    lines = text.split("\n")
    merged: list[str] = []
    buffer: str = ""
    i = 0

    while i < len(lines):
        stripped = lines[i].strip()

        # 空行处理：检查是否应该忽略
        if not stripped:
            # 🔧 新增：前瞻检查 —— 如果下一行与 buffer 符合续行模式，忽略空行
            if buffer and i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and _is_continuation(buffer, next_line):
                    # 忽略空行，将下一行续到 buffer
                    i += 1
                    stripped = lines[i].strip()
                    buffer += " " + stripped
                    i += 1
                    continue

            # 正常空行 = 段落分隔
            if buffer:
                merged.append(buffer)
                buffer = ""
            merged.append("")
            i += 1
            continue

        # 非空行处理
        if not buffer:
            buffer = stripped
        elif _is_continuation(buffer, stripped):
            buffer += " " + stripped
        else:
            merged.append(buffer)
            merged.append("")  # 段落分隔
            buffer = stripped

        i += 1

    if buffer:
        merged.append(buffer)

    return "\n".join(merged)
```

**或者更简洁的方案**（修改量更小）：

在原有逻辑基础上，增加"忽略空行"的判断：

```python
def _merge_lines(text: str) -> str:
    """合并续行，修复空行导致的错误分段"""
    lines = text.split("\n")
    merged: list[str] = []
    buffer: str = ""

    for i, line in enumerate(lines):
        stripped = line.strip()

        # 空行处理
        if not stripped:
            # 🔧 新增：检查是否应该忽略空行（续行模式）
            should_ignore_blank = False
            if buffer and i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and _is_continuation(buffer, next_line):
                    should_ignore_blank = True

            if not should_ignore_blank:
                if buffer:
                    merged.append(buffer)
                    buffer = ""
                merged.append("")
            continue

        # 非空行处理
        if not buffer:
            buffer = stripped
        elif _is_continuation(buffer, stripped):
            buffer += " " + stripped
        else:
            merged.append(buffer)
            merged.append("")
            buffer = stripped

    if buffer:
        merged.append(buffer)

    return "\n".join(merged)
```

**验收**：

```bash
cd python && python -c "
from src.parser.extractor import extract_pages
from src.parser.article_detector import extract_articles
from src.cleaner.pipeline import clean_text_full
from src.chunker.splitter import parse_blocks

pdf = r'C:\\Users\\zuowen\\Desktop\\science.adn8744.pdf'
doc = extract_pages(pdf)
raw_articles = extract_articles(doc.full_text)

# 检查第二篇文章
result = clean_text_full(raw_articles[1])
blocks = parse_blocks(result.text)

# 验证：应该没有 'other' 结尾 + 'countries' 开头的相邻块
for i, b in enumerate(blocks):
    if b.text.rstrip().endswith('other'):
        if i + 1 < len(blocks) and blocks[i+1].text.startswith('countries'):
            print(f'✗ 问题未解决: Block {b.id}')
            exit(1)

# 验证：blocks 数量应减少（因为合并了）
print(f'✓ Blocks: {len(blocks)} (应 ≤ 15，原 16)')
print('✓ 续行问题已修复')
"
```

**预期结果**：
- "other countries" 应在同一 block
- blocks 数量从 16 减少到 15
- 无 "形容词结尾 + 名词开头" 的断点

---

## 修复优先级表

| Pri  | Fix                              | 文件                    | LOC |
| ---- | -------------------------------- | ----------------------- | --- |
| P0   | 空行前瞻续行检查                  | `cleaner/pipeline.py`   | 20  |

**总计 ~20 LOC**

---

## 总结

第二轮修复效果良好，核心问题已解决。第三轮只需要修复一个小逻辑问题：

1. **空行前瞻续行检查**（P0）—— 唯一剩余问题

修复后，翻译管道应该可以正确处理 Science Perspectives 多文章 PDF，所有段落保持完整。

---

**修复后验收脚本**（完整版）：

```bash
cd python && python -c "
import sys; sys.path.insert(0, '.')
from src.parser.extractor import extract_pages
from src.parser.article_detector import extract_articles
from src.cleaner.pipeline import clean_text_full
from src.chunker.splitter import parse_blocks

pdf = r'C:\\Users\\zuowen\\Desktop\\science.adn8744.pdf'
doc = extract_pages(pdf)

# 1. 文章拆分
raw_articles = extract_articles(doc.full_text)
assert len(raw_articles) == 3, f'Expected 3 articles, got {len(raw_articles)}'
print('✓ 文章拆分: 3 篇')

# 2. 每篇文章 blocks
for i, raw_art in enumerate(raw_articles):
    result = clean_text_full(raw_art)
    blocks = parse_blocks(result.text)
    print(f'  文章 {i+1}: {len(blocks)} blocks')

    # 3. 无截断开头
    if blocks:
        assert not blocks[0].text.startswith('n '), f'Article {i+1} truncated start'
        assert not blocks[0].text.startswith('nflam'), f'Article {i+1} truncated start'

    # 4. 无续行问题
    for j, b in enumerate(blocks):
        if b.translatable and j + 1 < len(blocks):
            next_b = blocks[j + 1]
            if next_b.translatable:
                last_word = b.text.rstrip().split()[-1].lower().rstrip('.,;:')
                if last_word in ['other', 'many', 'such', 'western', 'eastern']:
                    raise AssertionError(f'Article {i+1} Block {b.id} 续行问题: {last_word}')

print('\\n✓ 所有验收通过！')
"
```
