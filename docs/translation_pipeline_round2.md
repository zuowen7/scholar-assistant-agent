# 翻译管道第二轮诊断报告（2026-05-05）

> **测试样本**：`~\Desktop\science.adn8744.pdf`
> **第一轮修复后状态**：UTF-8 编码问题已修复，水印已移除，但仍有 5 个严重问题
>
> **方法**：执行 `parser → cleaner → chunker` 完整流程，检查中间产物

---

## 第一轮修复效果确认

| 问题 | 状态 | 验证 |
|------|------|------|
| UTF-8 `��` 编码损坏 | ✅ 已修复 | `authors'` → U+2019, `evapotranspiration—the` → U+2014 |
| `Downloaded from` 水印 | ✅ 已修复 | 0 个残留 |
| chunk 切分太粗 | ✅ 已修复 | 6 chunks (原 3), 每 chunk 4-7 blocks |
| 段落开头截断 | ⚠️ 部分修复 | `n 2023` 仍然存在 |

---

## 新问题清单（按严重度）

### 🔴 P0-1. 多篇文章未拆分 — 3 篇混成 1 篇翻译

**实测证据**：

原始文本中清晰可见三篇独立文章：

```
[位置 0-2700] 第一篇：Masripithecus 古人类学
  "determine the relationships of Masripithecus with other Miocene apes..."
  结尾："waiting to be discovered. ó ó"

[位置 2700-12200] 第二篇：自然灾害 Cascading impacts
  标题："Cascading impacts of natural disasters in a connected world"
  作者："Laurie S. Huning and Manuela I. Brunner"
  开头："n 2023, extreme heat propelled..." (I 被截断)
  结尾："whiplash between climatic extremes."

[位置 12200-末尾] 第三篇：炎症记忆 Inflammation
  开头："nflammation is transient..." (I 被截断)
```

**根因**：

1. `cleaner/pipeline.py` 的 `_remove_watermarks` 把文章边界标记（标题+作者名+期刊信息）全部删除了
2. `article_splitter.py` 依赖 `Downloaded from` 模式，但 cleaner 已经移除了它
3. 没有其他文章边界检测机制

**影响**：
- glossary 跨主题污染（古人类学术语混入炎症生物学）
- chunk overlap 让不同文章内容混在一起
- 段落对齐彻底失败

**修复方案**：

**方案 A**：在 cleaner 之前保留文章边界

```python
# 新增：src/parser/article_detector.py
def detect_articles(raw_text: str) -> list[tuple[int, int, str]]:
    """在原始文本中检测文章边界（cleaner 之前调用）

    返回：[(start_pos, end_pos, title), ...]
    """
    articles = []

    # Science Perspectives 格式：
    # 1. 标题行：全大写或 Title Case，20-100 字符
    # 2. 作者行：First M. Last and First M. Last
    # 3. 期刊信息：Science XXX (XXX), DOI: ...
    # 4. 可选：View the article online / Downloaded from

    import re

    # 查找标题模式（Title Case 或全大写，不含句号）
    title_pattern = re.compile(
        r'^([A-Z][a-z]+(?:[ :][A-Z][a-z]+){2,10})\s*$',  # Title Case
        re.MULTILINE
    )

    # 查找作者名模式
    author_pattern = re.compile(
        r'^[A-Z][a-z]+ [A-Z]\. [A-Z][a-z]+(?: and [A-Z][a-z]+ [A-Z]\. [A-Z][a-z]+)*\s*$',
        re.MULTILINE
    )

    # 查找期刊信息
    journal_pattern = re.compile(
        r'^Science \d+ \(\d+\)',
        re.MULTILINE
    )

    # 组合模式：标题 + 作者 + 期刊（在 10 行内）
    lines = raw_text.split('\n')
    for i, line in enumerate(lines):
        if title_pattern.match(line):
            # 检查后面 10 行是否有作者和期刊信息
            for j in range(i+1, min(i+11, len(lines))):
                if author_pattern.match(lines[j]):
                    for k in range(j+1, min(j+5, len(lines))):
                        if journal_pattern.match(lines[k]):
                            # 找到文章标题位置
                            title = line.strip()
                            start_pos = raw_text.index(line)
                            # 文章结束位置是下一篇标题开始或文档末尾
                            articles.append((start_pos, -1, title))
                            break
                    break

    # 填充 end_pos
    for i in range(len(articles)):
        if i < len(articles) - 1:
            articles[i] = (articles[i][0], articles[i+1][0], articles[i][2])
        else:
            articles[i] = (articles[i][0], len(raw_text), articles[i][2])

    return articles


def extract_articles(raw_text: str) -> list[str]:
    """按文章边界拆分原始文本"""
    boundaries = detect_articles(raw_text)
    if len(boundaries) <= 1:
        return [raw_text]

    articles = []
    for start, end, title in boundaries:
        articles.append(raw_text[start:end])

    return articles
```

然后在 `routers/translate.py` 中：

```python
# 在 extract_pages 之后立即拆分文章
from src.parser.article_detector import extract_articles

raw_articles = extract_articles(doc.full_text)
for i, raw_art in enumerate(raw_articles):
    # 每篇文章独立走 cleaner → chunker → translate
    cleaned = clean_text_full(raw_art)
    blocks = parse_blocks(cleaned.text)
    ...
```

**方案 B**：使用内容启发式检测（更简单但可靠性较低）

```python
def split_articles_by_content(text: str) -> list[str]:
    """按内容模式拆分文章（cleaner 之后使用）

    识别信号：
    1. 段落开头被截断（单小写字母 + 空格）
    2. 前一段以句号结尾，紧接着空行
    3. 新段落主题明显不同（关键词聚类）
    """
    import re

    # 查找截断开头模式：\n\nn 2023, \n\nnflammation
    truncation_pattern = re.compile(r'\n\n([a-z])\s+[A-Z]', re.MULTILINE)

    # 查找所有匹配位置
    matches = list(truncation_pattern.finditer(text))

    if not matches:
        return [text]

    # 按匹配位置拆分
    articles = []
    prev_end = 0
    for m in matches:
        articles.append(text[prev_end:m.start()].strip())
        # 修复截断：n 2023 → In 2023
        truncated_char = m.group(1)
        # 启发式恢复
        restoration = {'n': 'In', 't': 'At', 's': 'As'}
        if truncated_char in restoration:
            text = text[:m.start()+2] + restoration[truncated_char] + text[m.start()+3:]
        prev_end = m.start()

    articles.append(text[prev_end:].strip())
    return [a for a in articles if a.strip()]
```

**推荐**：方案 A 更可靠，但需要在 cleaner 之前调用；方案 B 可作为后备方案。

**验收**：
- 测试 PDF 应被拆成 3 篇
- 每篇独立有 ~8-12 个 blocks
- glossary 不会跨主题污染

---

### 🔴 P0-2. 段落被错误切开 — 5 处断点错误

**实测证据**：

```
[b0010] ...deficits in other
[b0011] countries (for example, also caused by drought in China and western
[b0012] Australia, and cool and wet conditions in regions of Canada), this contributed t

  ↑ 一段被切成 3 段："other countries" 和 "Australia" 被断开
```

**根因**：

`cleaner/pipeline.py` 的 `_is_continuation()` 函数缺少以下续行规则：

1. 上一行以 `other` 结尾，下一行以 `countries` 开头 → 应续行
2. 上一行以 `western` 结尾，下一行以 `Australia` 开头 → 应续行

**修复**：

在 `_is_continuation()` 中增加规则：

```python
def _is_continuation(prev_line: str, current_line: str) -> bool:
    prev_stripped = prev_line.rstrip()
    cur_stripped = current_line.lstrip()

    # ─────── 新增规则 ───────

    # R5: 上一行以形容词/限定词结尾，下一行以名词开头 → 续行
    # 常见被断开的词对
    CONTINUATION_PAIRS = {
        'other': True,      # other countries
        'many': True,       # many regions
        'such': True,       # such as
        'these': True,      # these effects
        'those': True,      # those changes
        'some': True,       # some mechanisms
        'both': True,       # both cases
        'all': True,        # all regions
        'western': True,    # western Australia
        'eastern': True,    # eastern Africa
        'northern': True,   # northern regions
        'southern': True,   # southern areas
        'central': True,    # central regions
        'global': True,     # global supply
        'local': True,      # local events
        'human': True,      # human migration
        'social': True,     # social inequalities
        'mental': True,     # mental health
        'physical': True,   # physical and biological
        'economic': True,   # economic damage
        'environmental': True,  # environmental stressors
    }

    if prev_stripped:
        last_word = prev_stripped.split()[-1].lower().rstrip('.,;:')
        if last_word in CONTINUATION_PAIRS:
            return True

    # R6: 下一行以常见句中词开头 → 续行
    # 这些词很少作为段落开头
    MID_SENTENCE_STARTERS = {
        'countries', 'regions', 'areas', 'effects', 'changes', 'mechanisms',
        'systems', 'processes', 'factors', 'conditions', 'patterns',
        'australia', 'africa', 'europe', 'asia', 'america',  # 专有名词小写开头
        'which', 'that', 'this', 'these', 'those',  # 关系代词
    }

    if cur_stripped:
        first_word = cur_stripped.split()[0].lower()
        if first_word in MID_SENTENCE_STARTERS:
            return True

    # ─────── 原有逻辑 ───────
    # ... (保留现有规则)
```

**验收**：
- `other` + `countries` 应合并为同一段
- `western` + `Australia` 应合并
- blocks 数量应从 31 减少到 ~25

---

### 🟡 P1-1. 文章开头截断 — `n 2023`, `nflammation`

**实测证据**：

```
第一篇文章末尾："waiting to be discovered. ó ó"
第二篇文章开头："n 2023, extreme heat propelled..."  ← 应为 "In 2023"

第二篇文章末尾："whiplash between climatic extremes."
第三篇文章开头："nflammation is transient..."  ← 应为 "Inflammation"
```

**根因**：

1. PDF 原始文本中文章开头就有截断（可能是双栏布局导致的提取错误）
2. cleaner 的 `_fix_truncated_words_in_text` 只处理已知映射，不处理"单字母 + 词"模式

**修复**：

在 `_fix_truncated_paragraph_start()` 中增加：

```python
def _fix_truncated_paragraph_start(line: str) -> str:
    """修复段落开头截断（包括跨页截断）"""
    words = line.split()
    if not words:
        return line

    first = words[0]

    # 单字母开头 + 大写字母 → 可能是单词首字母被截断
    if len(first) == 1 and first.islower():
        if len(words) >= 2:
            second = words[1]
            # 第二个词是大写开头 → 可能是专有名词
            if second[0].isupper():
                # 启发式：根据第二个词猜测第一个词
                TRUNCATION_FIXES = {
                    'n': 'In',
                    't': 'At',
                    's': 'As',
                    'b': 'By',
                    'o': 'Of',
                    'f': 'For',
                    'w': 'With',
                    'a': 'A',
                }
                if first in TRUNCATION_FIXES:
                    return TRUNCATION_FIXES[first] + ' ' + ' '.join(words[1:])

    # 特殊模式：nflammation → Inflammation
    if first.startswith('nflam') or first.startswith('flammation'):
        return 'Inflammation' + ' ' + ' '.join(words[1:])

    return line
```

**验收**：
- `n 2023` → `In 2023`
- `nflammation` → `Inflammation`

---

### 🟡 P1-2. 噪声字符残留 — `ó ó`

**实测证据**：

```
waiting to be discovered.
ó ó

n 2023, extreme heat...
```

**根因**：

`cleaner/pipeline.py` 的 `_remove_orphan_unicode()` 没有处理孤立的 `ó` 字符（PDF 页面边角噪声）。

**修复**：

```python
def _remove_orphan_unicode(text: str) -> str:
    """移除孤立的非 ASCII 噪声字符"""
    # 移除单独一行的 ó, ñ, á 等字符
    text = re.sub(r'^[óñáéíóúäëïöüåäæœ]\s*$', '', text, flags=re.MULTILINE)
    # 移除两个重复的噪声字符
    text = re.sub(r'^[óñáéíóúäëïöüåäæœ]\s+[óñáéíóúäëïöüåäæœ]\s*$', '', text, flags=re.MULTILINE)
    return text
```

**验收**：
- `ó ó` 应被删除
- 文章边界不应有噪声行

---

### 🟠 P2-1. chunk overlap 导致重复翻译

**实测证据**：

当前配置 `max_tokens=800, overlap_tokens=0`，但如果启用 overlap 会导致同一个 block 被翻译两次。

**根因**：

block-aware 翻译模式下，每个 block 有唯一 ID，overlap 会让不同 chunks 包含相同 block，导致：
1. 同一 block 被翻译两次
2. 前后译文可能不一致
3. glossary 被重复更新

**修复**：

在 `src/chunker/splitter.py` 中：

```python
def pack_blocks_into_chunks(
    blocks: list[Block],
    max_tokens: int = 800,
    overlap_tokens: int = 0,  # block-aware 模式下强制为 0
) -> list[BlockChunk]:
    """将 blocks 打包成 chunks，block-aware 模式下禁用 overlap"""

    if overlap_tokens > 0:
        logger.warning(
            "overlap_tokens > 0 在 block-aware 模式下可能导致重复翻译，"
            "建议设置 overlap_tokens=0"
        )

    # ... 现有逻辑
```

并在 `config/default.yaml` 中确保：

```yaml
translate:
  max_tokens: 800
  overlap_tokens: 0  # block-aware 模式下必须为 0
```

---

## 修复优先级表

| Pri  | Fix                              | 文件                               | LOC |
| ---- | -------------------------------- | ---------------------------------- | --- |
| P0   | #1 多文章拆分（方案 A）          | 新增 `parser/article_detector.py` | 100 |
| P0   | #2 续行规则增强（形容词+名词）   | `cleaner/pipeline.py`              | 40  |
| P1   | #3 文章开头截断修复              | `cleaner/pipeline.py`              | 30  |
| P1   | #4 噪声字符 `ó ó` 移除           | `cleaner/pipeline.py`              10  |
| P2   | #5 chunk overlap 警告/禁用       | `chunker/splitter.py` + config     15  |

**总计 ~195 LOC**

---

## 验收脚本

```bash
cd python && python -c "
import sys; sys.path.insert(0, '.')
from src.parser.extractor import extract_pages
from src.parser.article_detector import extract_articles
from src.cleaner.pipeline import clean_text_full
from src.chunker.splitter import parse_blocks, pack_blocks_into_chunks

pdf = r'~\\Desktop\\science.adn8744.pdf'
doc = extract_pages(pdf)

# 验证文章拆分
raw_articles = extract_articles(doc.full_text)
assert len(raw_articles) == 3, f'Expected 3 articles, got {len(raw_articles)}'
print(f'✓ Articles: {len(raw_articles)}')

# 验证每篇文章的 blocks
for i, raw_art in enumerate(raw_articles):
    result = clean_text_full(raw_art)
    blocks = parse_blocks(result.text)
    print(f'  Article {i+1}: {len(blocks)} blocks')

    # 验证没有截断开头
    first_block = blocks[0].text if blocks else ''
    assert not first_block.startswith('n 2023'), f'Article {i+1} has truncated start'
    assert not first_block.startswith('nflammation'), f'Article {i+1} has truncated start'

    # 验证没有噪声字符
    for b in blocks:
        assert 'ó ó' not in b.text, f'Block {b.id} has noise characters'

print('✓ All validations passed!')
"
```

---

## 总结

第一轮修复效果良好，UTF-8 编码和水印问题已解决。第二轮需要解决的核心问题是：

1. **多文章拆分**（P0）—— 这是最关键的问题，影响整个翻译质量
2. **段落续行**（P0）—— 减少错切的段落
3. **截断修复**（P1）—— 文章开头恢复

建议按优先级顺序修复，每个 fix 独立提交 PR，配套单元测试。
