/**
 * 句对齐工具 — 模仿 DeepL 的悬停高亮体验
 *
 * 核心思路：
 * - 把段落切分为句子，记录每个句子的字符位置
 * - hover 原文中某句时，根据字符位置占比反查译文中对应位置的句子
 * - 不改翻译逻辑，纯前端视觉层对齐
 */

export interface Sentence {
  text: string
  start: number
  end: number
}

/**
 * 切分句子（英文/中文）
 */
export function splitSentences(text: string, lang: 'en' | 'zh'): Sentence[] {
  const out: Sentence[] = []

  if (lang === 'en') {
    // 英文句末：. ! ? 后跟空格 + 大写字母 或 行尾
    const re = /[^.!?]+[.!?]+(?:["')\]]+)?(?=\s+[A-Z]|\s*$)/g
    let match: RegExpExecArray | null
    while ((match = re.exec(text)) !== null) {
      out.push({
        text: match[0].trim(),
        start: match.index,
        end: match.index + match[0].length,
      })
    }
  } else {
    // 中文句末：。！？；
    const re = /[^。！？；]+[。！？；]+/g
    let match: RegExpExecArray | null
    while ((match = re.exec(text)) !== null) {
      out.push({
        text: match[0].trim(),
        start: match.index,
        end: match.index + match[0].length,
      })
    }
  }

  // 兜底：如果没切出任何句子，整个文本作为一个句子
  if (out.length === 0) {
    out.push({ text, start: 0, end: text.length })
  }

  return out
}

/**
 * 查找对应的译文句子索引
 *
 * @param origSentences 原文句子列表
 * @param origLen 原文总长度
 * @param transSentences 译文句子列表
 * @param transLen 译文总长度
 * @param hoveredOrigIdx 当前 hover 的原文句子索引
 * @returns 对应的译文句子索引
 */
export function findCorrespondingSentenceIdx(
  origSentences: Sentence[],
  origLen: number,
  transSentences: Sentence[],
  transLen: number,
  hoveredOrigIdx: number,
): number {
  if (hoveredOrigIdx < 0 || hoveredOrigIdx >= origSentences.length) return -1
  if (transSentences.length === 0) return -1

  // 计算原文句子的中点位置占比
  const origSent = origSentences[hoveredOrigIdx]
  const origMid = (origSent.start + origSent.end) / 2
  const ratio = origMid / Math.max(origLen, 1)

  // 映射到译文的位置
  const targetPos = ratio * transLen

  // 找到最接近的译文句子
  let bestIdx = 0
  let bestDist = Infinity
  for (let i = 0; i < transSentences.length; i++) {
    const transSent = transSentences[i]
    const transMid = (transSent.start + transSent.end) / 2
    const dist = Math.abs(transMid - targetPos)
    if (dist < bestDist) {
      bestDist = dist
      bestIdx = i
    }
  }

  return bestIdx
}

/**
 * 渲染带句子标记的HTML
 *
 * @param text 原文/译文
 * @param lang 语言
 * @param blockId 块ID
 * @param side 'orig' | 'trans'
 * @returns 带标记的HTML字符串
 */
export function renderSentenceMarkedHtml(
  text: string,
  lang: 'en' | 'zh',
  blockId: string,
  side: 'orig' | 'trans',
): string {
  const sentences = splitSentences(text, lang)

  if (sentences.length <= 1) {
    // 只有一句，不需要标记
    return escapeHtml(text)
  }

  const parts = sentences.map((sent, idx) => {
    const escaped = escapeHtml(sent.text)
    return `<span data-sent-idx="${idx}" data-block-id="${blockId}" data-side="${side}" class="sent">${escaped}</span>`
  })

  return parts.join(' ')
}

/**
 * HTML转义
 */
function escapeHtml(text: string): string {
  const div = document.createElement('div')
  div.textContent = text
  return div.innerHTML
}
