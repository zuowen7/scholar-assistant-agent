# 句子对齐和排版问题诊断报告

> **问题**：翻译后句子对不齐，排版有问题
> **诊断日期**：2026-05-05

---

## 问题分类

### 1. 句子对不齐

**可能原因**：

| 原因 | 症状 | 解决方案 |
|------|------|----------|
| LLM 输出段落数与输入不一致 | 前端 hover 时高亮错位 | 检查 `ollama_client.py` 的 prompt 是否生效 |
| 对齐算法失败 | 某些块显示为空 | 增强 `_align_translation_to_blocks` 的兜底逻辑 |
| 句子切分正则问题 | 句子边界识别错误 | 优化 `sentenceAlign.ts` 的 `splitSentences` |

**验证方法**：

```bash
# 检查 LLM 实际输出
cd python && python -c "
from src.translator.ollama_client import OllamaClient

client = OllamaClient()
test_input = '''Paragraph one.

Paragraph two.

Paragraph three.'''

result = client.translate(test_input)
print('输入段落数:', 3)
print('输出段落数:', len(result.translated.split('\n\n')))
print('输出内容:')
print(repr(result.translated))
"
```

**预期结果**：
- 输出段落数应为 3
- 如果不是 3，说明 LLM 没有遵循段落保持指令

---

### 2. 排版问题

**可能原因**：

| 原因 | 症状 | 解决方案 |
|------|------|----------|
| 译文包含额外空行 | 段落间距过大 | 增强 `_sanitize_llm_output` 清理多余空行 |
| 译文包含 markdown 格式 | 显示代码块或加粗 | 检查 `_strip_code_block_wrapping` |
| 中文标点符号错误 | 句号、逗号混用 | 后处理替换标点 |

**验证方法**：

检查翻译后的原始输出：

```python
# 在 translate.py 中添加调试日志
for bt in cr.block_translations:
    logger.debug(f"Block {bt.block_id}: {repr(bt.translated[:100])}")
```

---

## 修复方案

### 方案 A：增强段落保持指令（如果 LLM 不遵循）

修改 `src/translator/ollama_client.py` 的 `_build_system_prompt`：

```python
# 在现有指令后增加
parts.append("""
REMEMBER: 每个段落之间必须有 EXACTLY ONE blank line (空行)。
输入有几段，输出就必须有几段。
不要把两段合并成一段，也不要把一段拆成两段。

示例：
输入：
Para 1.

Para 2.

输出：
第1段译文。

第2段译文。
""")
```

### 方案 B：增强句子切分正则（前端）

修改 `src/utils/sentenceAlign.ts` 的 `splitSentences`：

```typescript
// 英文句子切分 - 增强版
const re = /[^.!?]+[.!?]+(?:["')\]]+)?(?=\s+[A-Z0-9"']|\s*$)/g
// 增加：数字开头的句子 (如 "2023, ...")
```

### 方案 C：增强兜底对齐逻辑

修改 `src/translator/block_translator.py` 的 `_distribute_by_char_ratio`：

```python
# 确保每个 block 至少有一些内容
for i in range(len(out)):
    if not out[i].strip() and i < len(originals):
        # 兜底：复制前一个 block 的部分内容
        if i > 0 and out[i-1]:
            out[i] = out[i-1][-50:]  # 取前一段的末尾 50 字符
```

---

## 排查步骤

1. **确认问题类型**
   - 打开浏览器开发者工具 → Network 标签
   - 翻译一个 PDF
   - 查看 `block_translated` 事件的数据
   - 检查 `translated` 字段的内容

2. **检查 LLM 输出**
   - 在后端日志中搜索 "输出段落数"
   - 或在 `ollama_client.py` 中添加日志

3. **检查前端渲染**
   - 在浏览器中检查渲染的 HTML
   - 查看 `data-sent-idx` 属性是否正确

4. **检查对齐状态**
   - 查看 `state.misalignedChunks` 的值
   - 如果 > 0，说明有对齐失败

---

## 需要用户提供的信息

为了精确定位问题，请提供：

1. **具体的翻译结果**
   - 翻译后的 PDF 截图
   - 或者导出的 Markdown 文件

2. **浏览器控制台信息**
   - 打开开发者工具 → Console
   - 翻译时的日志输出
   - 特别是 `misalignedChunks` 的值

3. **后端日志**
   - Python API 的日志输出
   - 特别是包含 "对齐" 或 "aligned" 的日志

---

## 快速测试脚本

```bash
cd python && python -c "
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from src.parser.extractor import extract_pages
from src.parser.article_detector import extract_articles
from src.cleaner.pipeline import clean_text_full
from src.chunker.splitter import parse_blocks, pack_blocks_into_chunks
from src.translator.block_translator import _build_chunk_input_text, _split_paragraphs

pdf = r'C:\\Users\\zuowen\\Desktop\\science.adn8744.pdf'
doc = extract_pages(pdf)
raw_articles = extract_articles(doc.full_text)

# 检查第二篇文章
result = clean_text_full(raw_articles[1])
blocks = parse_blocks(result.text)
chunks = pack_blocks_into_chunks(blocks, max_tokens=800, overlap_tokens=0)

for chunk in chunks[:2]:
    chunk_blocks = [b for b in blocks if b.id in chunk.block_ids]
    input_text = _build_chunk_input_text(chunk_blocks)
    paras = _split_paragraphs(input_text)
    print(f'Chunk {chunk.index}: {len(chunk_blocks)} blocks, {len(paras)} paragraphs')
"
```

---

## 总结

根据管道测试，解析和分块逻辑正常。问题最可能出在：

1. **LLM 输出层面** — Qwen3 模型没有严格遵循段落保持指令
2. **前端渲染层面** — 句子切分或对齐逻辑有边界情况未处理

请根据上述排查步骤定位具体问题，然后选择对应的修复方案。
