#!/usr/bin/env python3
"""翻译对齐和排版问题诊断工具"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from src.parser.extractor import extract_pages
from src.parser.article_detector import extract_articles
from src.cleaner.pipeline import clean_text_full
from src.chunker.splitter import parse_blocks, pack_blocks_into_chunks
from src.translator.block_translator import (
    _align_translation_to_blocks,
    _split_paragraphs,
    _build_chunk_input_text,
    _distribute_by_char_ratio,
)
from src.chunker import Block

pdf = r'C:\Users\zuowen\Desktop\science.adn8744.pdf'
doc = extract_pages(pdf)
raw_articles = extract_articles(doc.full_text)

print("=" * 60)
print("翻译对齐和排版诊断")
print("=" * 60)
print()

# 测试第二篇文章（最大的）
result = clean_text_full(raw_articles[1])
blocks = parse_blocks(result.text)
chunks = pack_blocks_into_chunks(blocks, max_tokens=800, overlap_tokens=0)

print(f"总 Blocks: {len(blocks)}")
print(f"总 Chunks: {len(chunks)}")
print()

# 模拟各种 LLM 输出情况
print("-" * 60)
print("1. 测试 Block 结构")
print("-" * 60)
for i, b in enumerate(blocks[:5]):
    paras = b.text.split('\n\n')
    sentences = b.text.count('. ') + b.text.count('.\n')
    print(f"Block {b.id}:")
    print(f"  字符: {len(b.text)}, 段落: {len(paras)}, 句子(约): {sentences}")
    print(f"  预览: \"{b.text[:60]}...\"")
print()

print("-" * 60)
print("2. 测试 Chunk 输入结构")
print("-" * 60)
for i, chunk in enumerate(chunks[:2]):
    chunk_blocks = [b for b in blocks if b.id in chunk.block_ids]
    input_text = _build_chunk_input_text(chunk_blocks)
    paras = _split_paragraphs(input_text)
    print(f"Chunk {i+1}:")
    print(f"  Blocks: {len(chunk_blocks)}")
    print(f"  输入段落数: {len(paras)}")
    for j, p in enumerate(paras):
        print(f"    段{j+1}: \"{p[:50]}...\" ({len(p)} 字符)")
print()

print("-" * 60)
print("3. 模拟 LLM 输出测试")
print("-" * 60)

# 测试第一个 chunk
test_chunk = chunks[0]
test_blocks = [b for b in blocks if b.id in test_chunk.block_ids]
chunk_input = _build_chunk_input_text(test_blocks)

print(f"测试 Chunk {test_chunk.index}: {len(test_blocks)} blocks")
print()

# 情况 1: LLM 完美对齐
print("情况 A: LLM 完美对齐 (4 段输入 → 4 段输出)")
perfect_trans = '''2023 年，极端高温推动严重野火在加拿大蔓延，造成广泛破坏并对生态系统和人类社区产生深远影响。

自然灾害的级联后果可以在全球众多例子中看到。

严重干旱的影响是另一个例子，在受压力的植被中可以清楚地观察到。

土壤湿度降低进而导致蒸散减少——水从地球表面移动到大气层。'''

result_bts, aligned = _align_translation_to_blocks(test_blocks, perfect_trans)
print(f"  对齐状态: {aligned}")
for bt in result_bts:
    print(f"    {bt.block_id}: \"{bt.translated[:50]}...\"")
print()

# 情况 2: LLM 合并段落
print("情况 B: LLM 合并段落 (4 段输入 → 1 段输出)")
merged_trans = "2023 年，极端高温推动严重野火在加拿大蔓延。自然灾害的级联后果可以在全球众多例子中看到。严重干旱的影响是另一个例子。土壤湿度降低进而导致蒸散减少。"

result_bts, aligned = _align_translation_to_blocks(test_blocks, merged_trans)
print(f"  对齐状态: {aligned}")
for bt in result_bts:
    status = "✓" if bt.translated else "✗ 空"
    print(f"    {bt.block_id}: \"{bt.translated[:50]}...\" {status}")
print()

# 情况 3: LLM 输出包含额外格式
print("情况 C: LLM 输出包含额外格式")
format_trans = '''以下是翻译结果：

2023 年，极端高温推动严重野火在加拿大蔓延。

自然灾害的级联后果可以在全球众多例子中看到。'''

result_bts, aligned = _align_translation_to_blocks(test_blocks, format_trans)
print(f"  对齐状态: {aligned}")
for bt in result_bts:
    status = "✓" if bt.translated else "✗ 空"
    print(f"    {bt.block_id}: \"{bt.translated[:50]}...\" {status}")
print()

print("-" * 60)
print("4. 前端句子对齐测试")
print("-" * 60)

# 模拟前端句子切分
def split_sentences_en(text: str):
    import re
    out = []
    re_sent = re.compile(r'[^.!?]+[.!?]+(?:["\')\]]+)?(?=\s+[A-Z]|\s*$)', re.MULTILINE)
    for m in re_sent.finditer(text):
        out.append({'text': m.group(0).strip(), 'start': m.start(), 'end': m.end()})
    if not out:
        out.append({'text': text, 'start': 0, 'end': len(text)})
    return out

def split_sentences_zh(text: str):
    import re
    out = []
    re_sent = re.compile(r'[^。！？；]+[。！？；]+', re.MULTILINE)
    for m in re_sent.finditer(text):
        out.append({'text': m.group(0).strip(), 'start': m.start(), 'end': m.end()})
    if not out:
        out.append({'text': text, 'start': 0, 'end': len(text)})
    return out

# 测试第一个 block
b0 = blocks[0]
en_sents = split_sentences_en(b0.text)
zh_sents = split_sentences_zh(perfect_trans.split('\n\n')[0])  # 第一段译文

print(f"Block {b0.id}:")
print(f"  英文句子数: {len(en_sents)}")
for i, s in enumerate(en_sents):
    print(f"    {i+1}. \"{s['text'][:50]}...\"")
print(f"  中文句子数: {len(zh_sents)}")
for i, s in enumerate(zh_sents):
    print(f"    {i+1}. \"{s['text'][:50]}...\"")
print()

print("=" * 60)
print("诊断建议")
print("=" * 60)
print("""
可能的问题和解决方案：

1. 句子对齐问题：
   - 原因：LLM 输出段落数与输入不一致
   - 解决：检查 prompt 中的段落保持指令是否生效
   - 兜底：_align_translation_to_blocks 会按字符比例分配

2. 排版问题：
   - 原因：译文包含额外空行或格式字符
   - 解决：增强 _sanitize_llm_output 清理逻辑

3. 空翻译：
   - 原因：对齐失败后某些 block 被分配空字符串
   - 解决：检查 _distribute_by_char_ratio 的边界情况

4. 前端显示问题：
   - 原因：splitSentences 正则表达式无法正确切分
   - 解决：优化句子切分正则表达式
""")
