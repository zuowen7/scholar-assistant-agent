# 翻译模块改进计划（对标 DeepL）

> 目标：让翻译界面和体验接近 DeepL / 沉浸式翻译，分阶段实施，每个阶段独立可交付、可回滚。

---

## 0. 现状与目标

### 现状管道
解析（`extract_document_with_layout`）→ 清洗（17 阶段）→ 切块（`Block` + `BlockChunk`）→ 块对齐翻译（`block_translator.py`）→ 格式化（`format_blocks` 拼 markdown）→ 前端三种 viewMode 渲染（对照 / 译文 / 全文）。

### DeepL 的核心体验
1. **段落级双语对照**：原文左、译文右，严格段对段对齐。
2. **悬停句高亮**：hover 原文中某句，译文中对应那句被高亮（视觉对齐）。
3. **翻译质量**：DeepL 自家 NMT。本项目接入 21 个云端 LLM，质量取决于用户选什么模型，**不在本计划范围**。
4. **排版导出**：双语 PDF / Word 保留原文档结构。本项目已有 `extract_document_with_layout` + `markdown_to_docx`。

### 本计划要做的事
聚焦于「界面 + 对齐 + 去重 + 失败处理」，不重写翻译引擎。

---

## 1. 问题定位（根因分析）

### 问题 A：句子对不齐
- 后端只做**段落级**对齐：一个 `Block` = 一段，多 Block 用 `\n\n` 拼接送 LLM。
- LLM 输出按 `\n\n` 拆段后做 1:1 映射；段数不等就走 `_distribute_by_char_ratio` 按字符比例硬切（`block_translator.py:65-106`），不准。
- 前端从未做过句对句对齐，"对照"视图只是 block-pair（段对段，`TranslateView.vue:148-173`）。
- 用户感受到的"不齐" = 段对齐失败兜底 + 段落本身长，视觉上几句话错位。

### 问题 B：译文区有重复 + 杂糅原文
- `translationOnlyHtml` 把所有 block 的 `translated` 字段无脑拼接（`TranslateView.vue:243-253`）。
- **关键 Bug**：`block_translator.py:194-201` 中 chunk 翻译失败时把 `original` 写入 `translated` 兜底 → 译文区夹杂英文。
- alignment 失败时按字符比例分块，LLM 输出比预期短就**多个 block 共享同一段译文** → 视觉上"重复"。
- LLM 输出未清洗：Qwen3 / DeepSeek-R1 等推理模型常出 `<think>...</think>`，或同时输出原文+译文，没有过滤。
- chunker 默认 `overlap_tokens=128`（`routers/translate.py:313`）— block-aware 模式下不应有重叠，这个参数仍传入。

### 问题 C：「全文」视图冗余且难看
- `viewMode='markdown'` 渲染 `state.finalContent` = `format_blocks(output_format='bilingual')` 的产物。
- 它用 `> 原文 blockquote` 后跟译文段落，**信息和「对照」模式 100% 重复**，但用 blockquote 渲染在阅读视图里特别突兀。
- 业界主流（DeepL / 沉浸式翻译 / Readwise Reader）只有：双语对照 + 纯译文 两种。

---

## 2. 改进计划（按优先级 + 阶段）

每个 P 阶段为一个独立 PR，按顺序提交。完成后跑一遍验收清单（见 §3）。

### P0 — 修复核心 Bug（必须先做）

#### P0-1：修复译文区重复 + 杂糅原文

**改动文件**
- `python/src/translator/block_translator.py`
- `python/src/translator/_helpers.py`（或 `ollama_client.py` / `cloud_client.py` 中处理 LLM raw 输出的位置）
- `python/routers/translate.py:313`
- `src/composables/useTranslate.ts`
- `src/components/TranslateView.vue`

**步骤**

1. **`BlockTranslation` 加 status 字段**

   ```python
   # block_translator.py
   @dataclass
   class BlockTranslation:
       block_id: str
       type: str
       original: str
       translated: str
       translatable: bool = True
       status: Literal['ok', 'failed', 'partial'] = 'ok'  # 新增
   ```

   翻译失败时不再用 `original` 占位：
   ```python
   # block_translator.py:194-201
   except Exception as e:
       return ChunkBlockResult(
           chunk_index=chunk.index,
           block_translations=[
               BlockTranslation(b.id, b.type, b.text, "", b.translatable, status='failed')
               for b in blocks
           ],
           ...
       )
   ```

2. **清洗 LLM 输出**（在 `translate_block_chunk` 调用 LLM 后立即处理）

   ```python
   def _sanitize_llm_output(raw: str, source_lang: str = "en") -> str:
       # 剥离推理标签
       raw = re.sub(r'<think>[\s\S]*?</think>', '', raw, flags=re.IGNORECASE)
       raw = re.sub(r'<thinking>[\s\S]*?</thinking>', '', raw, flags=re.IGNORECASE)
       # 剥离常见前缀
       raw = re.sub(r'^(Translation|译文|中文译文)[:：]\s*', '', raw.strip())
       # 如果原文是英文，剥离输出里的连续英文段落（避免夹带原文）
       if source_lang == "en":
           paras = raw.split('\n\n')
           paras = [p for p in paras if not _is_mostly_english(p)]
           raw = '\n\n'.join(paras)
       return raw.strip()

   def _is_mostly_english(text: str) -> bool:
       # 连续 ≥ 30 个 ASCII 字符且中文字符占比 < 10%
       if len(text) < 30:
           return False
       en_chars = sum(1 for c in text if c.isascii() and c.isalpha())
       zh_chars = sum(1 for c in text if '一' <= c <= '鿿')
       return en_chars / max(len(text), 1) > 0.6 and zh_chars / max(len(text), 1) < 0.1
   ```

3. **alignment 严重失败时逐 block 重译**

   ```python
   # _align_translation_to_blocks 后：
   if not aligned and abs(len(paras) - len(translatable_blocks)) / max(len(translatable_blocks), 1) > 0.5:
       # 段数差距 > 50%，单块单独重译
       retry_results = []
       for b in translatable_blocks:
           single = await asyncio.to_thread(client.translate, b.text, "")
           retry_results.append(_sanitize_llm_output(single.translated))
       # 用重译结果重建对齐
       ...
   ```

4. **去除残留 overlap**：`routers/translate.py:313`
   ```python
   block_result = await asyncio.to_thread(
       chunk_text_with_blocks,
       clean_result.text,
       chunker_cfg.get("max_tokens", 2048),
       0,  # overlap_tokens — block-aware 模式禁用重叠
       True,
   )
   ```

5. **前端类型 + 渲染**

   ```typescript
   // src/types/index.ts 中 BlockData 添加：
   status?: 'ok' | 'failed' | 'partial'

   // TranslateView.vue translationOnlyHtml:
   const translationOnlyHtml = computed(() => {
     const parts: string[] = []
     for (const b of state.blocks) {
       if (b.status === 'failed') continue  // 跳过失败块
       if (!b.translatable) parts.push(b.original)
       else if (b.translated) parts.push(...)
     }
     return renderMarkdown(parts.join('\n\n'))
   })
   ```

   block 渲染时若 `status==='failed'`：显示红色卡片"翻译失败 · 重试"按钮（点击调 `/api/translate/{task_id}/retry_block`，可作为 P2 跟进，先只显示提示）。

---

### P0-2：删除「全文」视图，重构「对照」为左右双栏

**改动文件**：`src/components/TranslateView.vue`

**步骤**

1. **移除 `viewMode='markdown'`** 选项及 `bilingualMarkdownHtml` 计算属性。

   ```typescript
   const viewOptions = [
     { value: 'bilingual' as const, label: '对照' },
     { value: 'translation' as const, label: '译文' },
   ]
   ```

2. **「对照」视图改为左右双栏 / 上下卡片自适应**

   模板替换 `.block-view`：
   ```vue
   <div v-if="viewMode === 'bilingual'" class="dual-view">
     <div
       v-for="(b, i) in renderableBlocks"
       :key="b.id"
       class="dual-row"
       :class="['type-' + b.type]"
       @mouseenter="hoveredBlockId = b.id"
       @mouseleave="hoveredBlockId = null"
     >
       <!-- 标题：跨栏 -->
       <template v-if="b.type === 'heading'">
         <component :is="`h${...}`" class="dual-heading-orig">{{ stripHeadingMark(b.original) }}</component>
         <component :is="`h${...}`" class="dual-heading-trans">{{ stripHeadingMark(b.translated) }}</component>
       </template>
       <!-- 公式/代码/表格：跨栏单列居中 -->
       <div v-else-if="!b.translatable" class="dual-untranslated" v-html="renderBlock(b.original, b.type)" />
       <!-- 普通段落：左原 / 右译 -->
       <template v-else>
         <div class="dual-orig" v-html="renderBlock(b.original, b.type)" />
         <div class="dual-trans" v-html="renderBlock(b.translated, b.type)" />
       </template>
     </div>
   </div>
   ```

   样式骨架：
   ```css
   .dual-view {
     display: flex;
     flex-direction: column;
     max-width: 1200px;
     margin: 0 auto;
     padding: var(--space-4);
   }
   .dual-row {
     display: grid;
     grid-template-columns: 1fr 1fr;
     gap: var(--space-5);
     padding: var(--space-3) 0;
     border-bottom: 1px solid var(--c-surface-3);
   }
   .dual-orig {
     font-size: 14px;
     color: var(--c-text-2);
     line-height: 1.7;
   }
   .dual-trans {
     font-size: var(--read-fs, 15px);
     color: var(--read-trans-color, var(--c-text-0));
     line-height: var(--read-lh, 1.8);
     font-family: var(--read-ff, system-ui);
   }
   /* 标题跨栏 */
   .dual-row.type-heading { grid-template-columns: 1fr; }
   .dual-heading-orig { color: var(--c-text-3); font-size: 0.85em; font-weight: 400; margin: 0; }
   .dual-heading-trans { color: var(--c-text-0); margin: var(--space-1) 0 0; }
   /* 公式/代码跨栏居中 */
   .dual-untranslated {
     grid-column: 1 / -1;
     padding: var(--space-3);
     background: var(--c-surface-2);
     border-radius: var(--radius-sm);
   }
   /* 窄屏 */
   @media (max-width: 900px) {
     .dual-row { grid-template-columns: 1fr; gap: var(--space-2); }
     .dual-orig { padding-bottom: var(--space-2); border-bottom: 1px dashed var(--c-surface-3); }
   }
   ```

3. **下载 / 导出文件保持 bilingual markdown 不变**（用户期望本地文件可读）。UI 不再展示这个 markdown 视图。

---

### P1 — 提升体验（DeepL-like）

#### P1-1：句对齐（视觉层）

**改动文件**
- 新增 `src/utils/sentenceAlign.ts`
- 改 `src/components/TranslateView.vue`

**核心思路**：前端把每段切成句子，按字符位置占比建立映射；hover 原句时，根据起止字符占比反查译文中对应位置的句子高亮。**不改翻译逻辑**，DeepL / 沉浸式翻译都是这么做的。

```typescript
// src/utils/sentenceAlign.ts
export function splitSentences(text: string, lang: 'en' | 'zh'): { text: string; start: number; end: number }[] {
  const out: { text: string; start: number; end: number }[] = []
  if (lang === 'en') {
    // 英文句末：. ! ? 后跟空格 + 大写字母
    const re = /[^.!?]+[.!?]+(?:["')\]]+)?(?=\s+[A-Z]|\s*$)/g
    let m
    while ((m = re.exec(text)) !== null) {
      out.push({ text: m[0].trim(), start: m.index, end: m.index + m[0].length })
    }
  } else {
    // 中文句末：。！？；
    const re = /[^。！？；]+[。！？；]+/g
    let m
    while ((m = re.exec(text)) !== null) {
      out.push({ text: m[0].trim(), start: m.index, end: m.index + m[0].length })
    }
  }
  if (out.length === 0) out.push({ text, start: 0, end: text.length })
  return out
}

export function findCorrespondingSentenceIdx(
  origSentences: { start: number; end: number }[],
  origLen: number,
  transSentences: { start: number; end: number }[],
  transLen: number,
  hoveredOrigIdx: number,
): number {
  // 用字符位置占比映射
  const o = origSentences[hoveredOrigIdx]
  const ratio = (o.start + o.end) / 2 / Math.max(origLen, 1)
  const targetPos = ratio * transLen
  let bestIdx = 0
  let bestDist = Infinity
  for (let i = 0; i < transSentences.length; i++) {
    const t = transSentences[i]
    const mid = (t.start + t.end) / 2
    const dist = Math.abs(mid - targetPos)
    if (dist < bestDist) { bestDist = dist; bestIdx = i }
  }
  return bestIdx
}
```

`TranslateView.vue` 中渲染段落改为按句切分，每句用 `<span data-sent-idx>` 包裹；`@mouseenter` 计算对应译文句索引并加 `.sent-active` class。

```vue
<div class="dual-orig">
  <span
    v-for="(s, idx) in splitSentences(b.original, 'en')"
    :key="idx"
    class="sent"
    :class="{ 'sent-active': hoveredPair?.blockId === b.id && hoveredPair.transIdx === idx }"
    @mouseenter="onSentHover(b, idx, 'orig')"
    @mouseleave="hoveredPair = null"
  >{{ s.text }} </span>
</div>
```

样式：
```css
.sent { transition: background 0.15s; padding: 1px 2px; border-radius: 2px; }
.sent:hover, .sent.sent-active { background: var(--c-accent-soft); }
```

---

#### P1-2：增强 LLM Prompt 降低段落对齐失败率

**改动文件**：`python/src/translator/ollama_client.py` + `cloud_client.py` 的默认 system prompt

在现有 system prompt 末尾追加：
```
CRITICAL: Preserve paragraph structure exactly.
- Input has N paragraphs separated by blank lines (\n\n).
- Output MUST have exactly N paragraphs separated by blank lines.
- Do NOT merge paragraphs. Do NOT split paragraphs.
- Do NOT add explanations, headers, or numbering.
- Do NOT include the original text in your output.
- Output ONLY the translation.

严格保持段落结构：输入有 N 段（用空行分隔），输出必须也是 N 段。不要合并、不要拆分、不要加序号、不要返回原文。
```

构造用户消息时显式注明段数：
```python
n = len([p for p in chunk_input.split("\n\n") if p.strip()])
user_msg = f"The following text has {n} paragraphs. Translate each paragraph into Chinese, preserving the paragraph structure:\n\n{chunk_input}"
```

---

#### P1-3：实时预览改用 block_translated 事件

**改动文件**：`src/components/TranslateView.vue:97-106`

现在 live preview 用 `chunk_done.translated_preview`（截断 200 字）。block-aware 模式下每个 `block_translated` 就是完整段落，应该消费这个事件，显示最新 3 个完整段落对照（不截断）。

```typescript
// useTranslate.ts 已有 state.blocks, 直接在 live-preview 里渲染：
const recentBlocks = computed(() =>
  state.blocks.filter(b => b.translated).slice(-3)
)
```

---

### P2 — 收尾打磨

#### P2-1：导出选项收敛

`TranslateView.vue` 顶部的「下载」+「双语 Word」改为单个 `UiDropdown` "导出 ▾"：
- 双语 Markdown
- 双语 Word
- 仅译文 Markdown
- 仅译文 Word（新增，复用 `markdown_to_docx`，传 `format_blocks(..., output_format='translated_only')` 的产物）

#### P2-2：失败块重试

后端：`POST /api/translate/{task_id}/retry_block` body `{block_id}`，调用 LLM 重译该块，更新 task['block_translations']，SSE 推 `block_translated` 事件。

前端：失败块卡片上"重试"按钮调用此 API。

#### P2-3：清理无用配置

- 从 UI 设置面板和 `default.yaml` 中移除 `chunker.overlap_tokens`（block-aware 路径下无意义）。
- 评估 `format_output` 中的 `parallel`（表格对照）模式：前端已无入口，若也无导出路径则删除（`renderer.py:139-152`）。

---

## 3. 验收清单

每阶段提交后逐条验证：

### P0 验收
- [ ] 翻译一篇 5 页英文 PDF，切到「译文」视图：纯中文，无英文夹杂，无重复段落。
- [ ] 故意断网触发 LLM 失败：失败块显示红色卡片"翻译失败"，**不混入**译文流。
- [ ] 不再有「全文」按钮，只剩「对照」+「译文」。
- [ ] 「对照」视图：宽屏左右双栏，原文（左/灰小字）+ 译文（右/黑大字）严格按 block 对齐，块间细线分隔。
- [ ] 窄屏（< 900px）：自动切换为上下堆叠卡片。

### P1 验收
- [ ] hover 原文段中某句：译文段中**字符占比相近**的那句被高亮（淡蓝底）。
- [ ] 翻译完成后查看 `state.misalignedChunks`：5 页 PDF 应 ≤ 1（即 alignment 成功率 ≥ 95%）。
- [ ] 实时预览展示完整段落对照，不截断 200 字。

### P2 验收
- [ ] 导出下拉菜单四个选项均可下载且打开正常。
- [ ] 点击失败块的"重试"按钮，块状态从 failed 变回 ok 并填充译文。
- [ ] 设置面板和 `default.yaml` 不再有 `overlap_tokens`。

---

## 4. 改动量与排期建议

| 文件 | 行数变更 | 阶段 |
|---|---|---|
| `python/src/translator/block_translator.py` | +60 / -20 | P0-1 |
| `python/src/translator/_helpers.py`（或 LLM 客户端）| +30 | P0-1 |
| `python/routers/translate.py` | +1 / -1 | P0-1 |
| `src/components/TranslateView.vue` | +200 / -120 | P0-2 + P1-1 + P1-3 |
| `src/composables/useTranslate.ts` | +20 | P0-1 |
| `src/types/index.ts` | +1 | P0-1 |
| `src/utils/sentenceAlign.ts`（新文件）| +60 | P1-1 |
| `python/src/translator/ollama_client.py` + `cloud_client.py` | +20 | P1-2 |
| `python/routers/translate.py`（重试接口）| +30 | P2-2 |

总工作量约 **4-6 小时**。建议排期：

- **第 1 次 PR（P0）**：修 bug + 删全文视图 + 双栏对照。这一步交付后翻译界面就接近 DeepL 主体验。
- **第 2 次 PR（P1）**：句对齐 + Prompt 强化 + 实时预览。这一步补齐 DeepL 的"高级感"。
- **第 3 次 PR（P2）**：导出菜单 + 重试 + 配置清理。打磨细节。

---

## 5. 不做的事（避免 scope creep）

- **替代译文选词**（点击单词换译法）：需要 token-level alignment，工程量是本计划的 5 倍以上。DeepL 的核心专利。
- **重写翻译引擎**：项目已接入 21 个云端 LLM，质量靠选模型解决。
- **PDF 原版叠加翻译层**（DeepL Document 输出 PDF）：项目已有 `extract_document_with_layout` 但当前只用于 docx 导出，PDF 叠加是另一个独立特性，不在本计划。
