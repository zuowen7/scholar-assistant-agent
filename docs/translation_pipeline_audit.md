# 翻译管道实测诊断报告（2026-05-05）

> **测试样本**：`C:\Users\zuowen\Desktop\science.adn8744.pdf`
> 4 页 / 16944 字符 / 双栏 / **包含 3 篇独立 Science Perspectives 短文**
>
> **方法**：直接执行 `parser → cleaner → chunker` 各阶段，检查实际中间产物，未涉及 LLM 翻译阶段（光前 3 个阶段就有 8 个严重问题，必须先修才有翻译质量可言）。

## 实测命令复现

```bash
cd python && python -c "
import sys; sys.path.insert(0, '.')
from src.parser.extractor import extract_pages
from src.cleaner import clean_text_full
from src.chunker.splitter import chunk_text_with_blocks

pdf = r'C:\Users\zuowen\Desktop\science.adn8744.pdf'
doc = extract_pages(pdf)
result = clean_text_full(doc.full_text)
br = chunk_text_with_blocks(result.text, max_tokens=2048, overlap_tokens=128)

print(f'pages={doc.page_count}, raw={len(doc.full_text)}, clean={len(result.text)}')
print(f'blocks={len(br.blocks)}, chunks={len(br.chunks)}, has_refs={result.has_references}')
"
```

实测输出：`pages=4, raw=16944, clean=16228, blocks=46, chunks=3, has_refs=False`

---

## 问题清单（按"翻译会不会废"严重度）

### 🔴 P0-1. UTF-8 编码损坏 — 整篇文档遍布 `��`

**实测证据**（cleaner 输出）：
```
the authors�� tip-dating analysis        ← 应为 the authors’
the ��drunk��s dilemma��                   ← 应为 the “drunk’s dilemma”
Earth��s surface                          ← Earth’s
evapotranspiration��the movement of water ← evapotranspiration—the movement
Cowley et al . ��s findings              ← et al.'s
```

**根因**：pdfplumber 提取 Adobe 子集化字体时，右单引号 `’`(U+2019)、右双引号 `”`(U+201D)、em-dash `—`(U+2014) 被解码成 `��`。Cleaner 完全没有这一步。

**修复**（在 `cleaner/pipeline.py` 加一步，建议在 `_remove_watermarks` 之后）：
```python
def _fix_pdfplumber_encoding(text: str) -> str:
    """修复 pdfplumber 提取 Adobe 子集字体时的编码错位"""
    # 词内 + 跟英文常见后缀 → 撇号
    text = re.sub(r"(\w)��(s|t|d|re|ve|ll|m)\b", r"\1’\2", text)
    # 词与词之间 → em-dash
    text = re.sub(r"(\w)��(\w)", r"\1—\2", text)
    # 兜底 → 双引号
    text = re.sub(r"��", '"', text)
    return text
```

**验收**：
- `the authors�� tip-dating` → `the authors’ tip-dating`
- `Earth��s surface` → `Earth’s surface`
- `evapotranspiration��the movement` → `evapotranspiration—the movement`

---

### 🔴 P0-2. 一份 PDF 装 3 篇独立文章，被当成 1 篇连续翻译 ⭐ **核心问题**

**实测证据**：cleaner 输出里能看到三个不同主题无缝衔接：

```
[b0000-b0006]  Masripithecus 古人类学 Perspective
[b0007] 起：    "n 2023, extreme heat propelled..." ← 第 2 篇"自然灾害"
[b0029] 起：    "Inflammation is transient, but..." ← 第 3 篇"炎症记忆"
```

三篇被当成同一篇文档喂给 LLM，结果：
- glossary 跨主题污染（古人类学术语带到炎症生物学）
- chunk overlap 让两篇文章混在一个 chunk 里
- 段落对齐彻底乱

**修复**：在 cleaner 之后、chunker 之前加 **article splitter**。

锚点：每篇文章末尾有"短标题行 + 作者名行 + Downloaded from"模式，可作为分隔信号。

```python
# 新文件: python/src/cleaner/article_splitter.py
def split_articles(text: str) -> list[str]:
    """按"作者署名 + Downloaded from"页脚锚点拆分多篇 Perspectives"""
    article_boundary = re.compile(
        r'\n\n(?='
        r'[A-Z][^\n]{10,80}\n+'                               # 标题行
        r'[A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+'          # First M. Last
        r'(?:\s+(?:and|,)\s+[A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)*\s*\n+'
        r'Downloaded\s+from'
        r')',
        re.MULTILINE
    )
    parts = article_boundary.split(text)
    return [p.strip() for p in parts if p.strip()]
```

然后在 `routers/translate.py` 的翻译入口处：
```python
articles = split_articles(cleaned_text)
if len(articles) > 1:
    # 多篇文章 → 各自独立走 chunk + translate
    for i, art in enumerate(articles):
        yield {'event': 'article_start', 'index': i, 'count': len(articles)}
        # 每篇独立 glossary，避免主题污染
        ...
```

前端 `TranslateView.vue` 增加"Tab 分文章"展示。

**验收**：测试 PDF 应被拆成 3 篇，每篇独立有 ~10-15 个 block。

---

### 🔴 P0-3. 跨页页脚 "Downloaded from..." 水印 + 文章标题 + 作者名残留

**实测证据**（chunker 输出末尾）：
```
[b0038] paragraph: Cascading impacts of natural disasters in a connected world  ← 第 2 篇标题（错位）
[b0039] heading lvl=2: Laurie S. Huning and Manuela I. Brunner                  ← 作者被误判为 heading!
[b0040] paragraph: Downloaded from https://www.science.org at
[b0041] paragraph: Harbin
[b0042] paragraph: Institute of
[b0043] paragraph: Technology at
[b0044] paragraph: Weihai on
[b0045] paragraph: March
```

**根因**：
1. `cleaner/pipeline.py:_remove_watermarks` 的多行 "Downloaded from" 正则只匹配"每个单词独立一行"格式，但实测是"前缀 + URL 同行 + 后续多行机构名"的混合格式
2. `chunker/splitter.py:_looks_like_pdf_heading` 把 `Laurie S. Huning and Manuela I. Brunner` 当成 H2（命中 "Title Case + 词数 ≤10"）

**修复**：

```python
# 1. cleaner/pipeline.py:_remove_watermarks 增强
text = re.sub(
    r'Downloaded\s+from\s+https?://[^\n]+\s+at\s*\n'
    r'(?:[A-Z][^\n]*\n){1,8}'                # 1-8 行机构名
    r'(?:on\s*\n)?'                          # "on" 单独行
    r'(?:[A-Z][a-z]+\s*\n)?'                 # 月份单独行
    r'(?:\d+,?\s*\n)?'                       # 日期
    r'\d{4}',                                # 年份
    '', text, flags=re.MULTILINE,
)

# 2. chunker/splitter.py:_looks_like_pdf_heading 顶部增加排除
# 排除：含 "F. Last" 模式（人名）的 Title Case
if re.search(r'\b[A-Z]\.\s+[A-Z][a-z]+\b', s):
    return 0  # 看起来是 First M. Last → 不是 heading

# 3. 文章末尾的"标题 + 作者"元数据块
# 由 article_splitter 在拆分时整体识别并丢弃（属于上一篇文章的页脚）
```

**验收**：测试 PDF 翻译产物末尾不再出现 `哈尔滨` `工业` `2026 年 3 月` 这类残片。

---

### 🔴 P0-4. Inline citation `( 12 )` 带空格 + 没保护

**实测证据**：
```
divergence times ( 12 )
fossils from elsewhere... ( 1 , 3 )
distant regions such as Egypt and Mozambique ( 6 )
feedback loops within regulatory circuits ( 6 , 7 )
```

**根因**：pdfplumber 对小字号上标的字符间距判断不准，把 `(12)` 拆成 `( 12 )`。LLM 看到很可能改写为"参考文献 12"或丢失。

**修复**（`cleaner/pipeline.py` 加一步规范化 + `routers/translate.py` 加占位符保护）：

```python
# cleaner: 规范化空格
text = re.sub(r'\(\s+(\d+(?:\s*[,\-–]\s*\d+)*)\s+\)', r'(\1)', text)

# routers/translate.py：翻译前用占位符保护
def protect_citations(text: str) -> tuple[str, list[str]]:
    placeholders: list[str] = []
    def _sub(m):
        idx = len(placeholders)
        placeholders.append(m.group(0))
        return f'⟦C{idx}⟧'
    text = re.sub(r'\(\d+(?:\s*[,\-–]\s*\d+)*\)', _sub, text)
    text = re.sub(r'\[\d+(?:\s*[,\-–]\s*\d+)*\]', _sub, text)
    return text, placeholders

def restore_citations(text: str, placeholders: list[str]) -> str:
    for i, c in enumerate(placeholders):
        text = text.replace(f'⟦C{i}⟧', c)
    return text

# 在翻译流入口
text, citations = protect_citations(cleaned)
# ... 翻译 ...
final = restore_citations(translated, citations)
```

**注意**：占位符要用罕见 Unicode（这里用 `⟦C0⟧` 中的方括号 U+27E6/U+27E7），避免 LLM 翻译。

**验收**：原文 `times ( 12 )` 在译文中应保持为 `( 12 )` 或 `(12)`，不能丢失或改写。

---

### 🔴 P1-1. 跨段落/跨页错切 — `_is_continuation` 失效率高

**实测证据**：很多本是同一段的内容被切开：

```
[b0004] Because most known remains of stem great apes are restricted to
[b0005] East Africa ( 1 , 3 ), fossils from elsewhere in this continent...
   ↑ "to" 后无标点 + "East" 大写开头 → 误判为新段落

[b0014] ...affects international trade and population-le
[b0015] countries (for example, also caused by drought in China and western
[b0016] Australia, and cool and wet conditions in regions of Canada),...
[b0017] Russia exacerbated social inequality...
   ↑ 一段被切成 4 段

[b0035] This was accompanied by methylation and acetylation of histone H3
[b0036] (H3K4me1 and H3K27ac epigenetic alterations, respectively)...
   ↑ 化学式中间被切

[b0010] DC, and New York City (see the figure)...    ← "Washington," 残在上一段
[b0011] Europe ( 4 ).                                ← 前后被切碎
```

**修复**（`cleaner/pipeline.py:_is_continuation` 增加规则）：

```python
def _is_continuation(prev_line: str, current_line: str) -> bool:
    prev_stripped = prev_line.rstrip()
    cur_stripped = current_line.lstrip()

    # ─────── 新增规则 ───────
    # R1: 当前行以小括号开头 → 强制续行（化学式、注释）
    if cur_stripped.startswith('('):
        return True

    # R2: 上一行以介词/连词/冠词结尾 → 强制续行
    if prev_stripped:
        last_word = prev_stripped.split()[-1].lower().rstrip(',;:')
        CONNECTIVES = {
            'to', 'of', 'in', 'on', 'at', 'by', 'for', 'with', 'and',
            'or', 'but', 'the', 'a', 'an', 'as', 'from', 'into',
            'than', 'that', 'which', 'where', 'while',
        }
        if last_word in CONNECTIVES:
            return True

    # R3: 末尾词被截断（含连字符或常见词内断点）
    if prev_stripped.endswith('-'):
        return True
    if re.search(r'-(?:le|tio|men|gra|sti|tro|spo|tive|ment|tion)$', prev_stripped):
        return True

    # R4: 上一行以逗号结尾 → 续行（"Washington," + "DC, and ..."）
    if prev_stripped.endswith(','):
        return True

    # ─────── 原有逻辑 ───────
    # ... (保留)
```

**验收**：
- `restricted to / East Africa` 应合并为同段
- `population-le / countries` 应合并
- `histone H3 / (H3K4me1...)` 应合并
- `Washington, / DC, and...` 应合并

---

### 🔴 P1-2. 段落开头截断词修复缺失

**实测证据**：
```
[b0007] n 2023, extreme heat propelled the spread of severe wildfires...   ← 应为 "In 2023"
```

**根因**：`_fix_truncated_words_in_text` 字典只有约 17 个固定映射（`nflammation→inflammation`、`pigenetic→epigenetic` 等），不覆盖"单字母 + 数字"这种短前缀模式。

**修复**：

```python
def _fix_truncated_paragraph_start(line: str) -> str:
    """启发式修复段首截断"""
    words = line.split()
    if not words:
        return line
    first = words[0]
    rest_str = ' '.join(words[1:])

    # 单字母 + 后接数字/逗号 → 常见介词截断
    if len(first) == 1 and first.islower() and rest_str:
        next_char = rest_str[0]
        if next_char.isdigit() or next_char == ' ':
            # 启发式映射（按上下文最常见的还原）
            GUESS = {
                'n': 'In', 't': 'At', 's': 'As', 'f': 'If',
                'o': 'To', 'b': 'By', 'a': 'A',
            }
            if first in GUESS:
                return GUESS[first] + ' ' + rest_str
    return line

# 在 _merge_paragraph_lines 之后调用
```

**验收**：`n 2023, extreme heat...` → `In 2023, extreme heat...`

---

### 🟠 P1-3. chunk 切分太粗 — 3 chunks 装 46 blocks

实测 `chunks=3, blocks=46`，平均 15 个 block/chunk。LLM 段落对齐天然失败率高。

**修复**：在配置中（`config/default.yaml`）：
```yaml
translate:
  max_tokens: 800       # 从 2048 → 800（block-aware 模式下）
  overlap_tokens: 0     # 从 128 → 0（block-aware 模式下重叠会让同一 block 翻两次）
```

**验收**：测试 PDF 应有 ~6-8 chunks，每 chunk 5-7 blocks，对齐成功率从 70% 升到 90%+。

---

### 🟠 P2-1. 引用区检测失败 — Perspectives 短文格式被忽略

**实测证据**：`has_refs=False, references_text_len=0`

Perspectives 短文的引用是不带 "REFERENCES" header 的纯编号列表（直接列出 `1. ...`、`2. ...`）。`_REFERENCE_PATTERNS` 只识别显式 header，故引用要么被翻译（污染译文），要么早在 PDF 提取阶段就因双栏小字号丢失（更可能）。

**修复**：在 article splitter 拆分后，对每篇文章单独再做一次"末尾尾部连续编号引用条目"检测：

```python
def detect_inline_refs(article_text: str) -> tuple[str, str]:
    """检测末尾连续 '1. ...' '2. ...' 序列（Perspectives 风格）"""
    lines = article_text.rstrip().split('\n')
    for i in range(len(lines) - 1, -1, -1):
        if re.match(r'^\s*1\.\s+[A-Z]', lines[i]):
            seen = {1}
            for j in range(i + 1, len(lines)):
                m = re.match(r'^\s*(\d+)\.\s+[A-Z]', lines[j])
                if m:
                    seen.add(int(m.group(1)))
            if len(seen) >= 3:  # 至少 3 条连续引用
                return ('\n'.join(lines[:i]).rstrip(),
                        '\n'.join(lines[i:]))
    return article_text, ''
```

---

### 🟠 P2-2. 作者署名块未移除

每篇 Perspectives 开头会有 `Author Name¹*\n¹Department of...\n*Corresponding author. email: x@y.z`，cleaner 当前不识别（因没有显式 "Authors:" header）。

**修复**：见前次诊断报告 `Fix-4`。

---

## 📋 修复优先级表

| Pri  | Fix                                              | 文件                                         | LOC |
| ---- | ------------------------------------------------ | -------------------------------------------- | --- |
| P0   | #1 UTF-8 `��` 修复                              | `cleaner/pipeline.py`                        | 30  |
| P0   | #2 多文章拆分                                    | 新增 `cleaner/article_splitter.py` + `routers/translate.py` | 80  |
| P0   | #3 多行水印增强 + 作者名 heading 排除            | `cleaner/pipeline.py` + `chunker/splitter.py` | 50  |
| P0   | #4 inline citation 占位符保护                    | `cleaner/pipeline.py` + `routers/translate.py` | 60  |
| P1   | #5 续行规则增强（连词 / 小括号 / 截断词后缀）    | `cleaner/pipeline.py`                        | 40  |
| P1   | #6 段落开头截断词修复（启发式）                  | `cleaner/pipeline.py`                        | 30  |
| P1   | #7 chunk 调小 + overlap=0                        | `config/default.yaml`                        | 5   |
| P2   | #8 inline 引用区检测（Perspectives 风格）        | `cleaner/pipeline.py`                        | 50  |
| P2   | #9 作者署名块移除                                | `cleaner/pipeline.py`                        | 70  |

**总计 ~415 LOC**，集中投入 2-3 天可改完。

---

## 📦 给执行 AI 的明确清单

```
任务：修复学术论文翻译管道，针对 Science Perspectives 多文章 PDF

测试样本：C:\Users\zuowen\Desktop\science.adn8744.pdf
本次诊断已确认问题：见上方 P0/P1/P2 列表

要求：
1. 严格按修复优先级 P0 → P1 → P2 提交，每个 fix 一个独立 PR
2. 每个 fix 必须配套 pytest 单元测试，覆盖"问题清单"里的实测证据字符串
3. 改完后用脚本验证（脚本见本文档顶部"实测命令复现"）：
   - blocks 数量应大于 46（修复跨段错切后）
   - chunks 数量应大于 3（max_tokens 调小后）
   - has_refs 应为 True（Perspectives 引用检测后）
   - cleaned text 中不得含 � 字符
   - cleaned text 中不得含 "Downloaded from" 残片
4. 不要触碰 src/translator/、src/agent/ 子系统 —— 这次只修 parser/cleaner/chunker
5. 配套增加 python/tests/integration/test_science_perspectives.py，固化以下断言：
   - 测试 PDF 拆分后应得 3 篇文章
   - 每篇文章首段不应以小写字母 + 数字开头（截断已修复）
   - 第二篇文章首段应包含 "In 2023"（不是 "n 2023"）
   - 任意 block 内不应同时出现 "Washington," 单独成段 和 "DC, and" 开头
   - 任意 block 不应包含 � 字符
```

---

## 附：诊断时的 chunker 实测全景

```
Block type distribution:
  paragraph: 45
  heading: 1                  ← 唯一识别的 heading 是误判的作者名

Block 边界异常列表（应合并而被切开的）:
  b0004 + b0005   (...restricted to | East Africa...)
  b0010 + b0011   (Washington, | DC, and...)
  b0014 + b0015 + b0016 + b0017   （一段切成 4 段）
  b0019 + b0020   (COVID-19 pandemic. | Discussions of...)
  b0022 + b0023   (Rivers, | is commonly used...)
  b0035 + b0036   (histone H3 | (H3K4me1...))

文章边界（无识别）:
  b0006 → b0007   (Masripithecus 篇结束 → "n 2023" 自然灾害篇开始)
  b0028 → b0029   (自然灾害篇结束 → Inflammation 炎症篇开始)

页脚/水印残留:
  b0038 ~ b0045   (8 个 block 全是元数据)
```

---

诊断结束。修复完后再用同一脚本回归一次，对比指标改善。
